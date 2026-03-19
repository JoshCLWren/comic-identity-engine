"""Round-robin GCD matching service - tries all strategies, picks the best."""

from __future__ import annotations

from dataclasses import dataclass

from .adapter import GCDLocalAdapter
from .types import CLZInput, MatchConfidence, StrategyResult

CONFIDENCE_THRESHOLD = 50
YEAR_GAP_RETRY_THRESHOLD = 4
GROUP_YEAR_GAP_MAX = 15


@dataclass
class GCDMatchingService:
    """GCD matching service with round-robin strategy selection.

    For each CLZ input, runs all applicable strategies and picks
    the highest-confidence match that meets the threshold.
    """

    adapter: GCDLocalAdapter

    def match(self, clz_input: CLZInput) -> StrategyResult:
        """Match a CLZ comic to GCD using all strategies.

        Returns the best result across all strategies.
        """
        if clz_input.barcode and clz_input.barcode != "00000000000000":
            result = self._try_barcode(clz_input.barcode)
            if result.is_match():
                return result

        # Run group-name strategies first (Series Group often matches GCD better)
        group_differs = bool(clz_input.series_group) and (
            clz_input.series_group_normalized.lower()
            != clz_input.series_name_normalized.lower()
        )
        group_exact = (
            self._try_exact_one_issue_for(clz_input, use_group=True)
            if group_differs
            else StrategyResult(confidence=MatchConfidence.NO_MATCH)
        )
        group_year = (
            self._try_exact_closest_year_for(clz_input, use_group=True)
            if group_differs
            else StrategyResult(confidence=MatchConfidence.NO_MATCH)
        )

        # Run series-name strategies
        name_exact = self._try_exact_one_issue_for(clz_input, use_group=False)
        name_year = self._try_exact_closest_year_for(clz_input, use_group=False)

        results = [
            group_exact,
            group_year,
            name_exact,
            name_year,
            self._try_exact_series(clz_input),
            self._try_normalized_series(clz_input),
            self._try_word_order_series(clz_input),
            self._try_colon_comma_series(clz_input),
            self._try_article_series(clz_input),
            self._try_substring_series(clz_input),
            self._try_reverse_lookup(clz_input),
        ]

        best = StrategyResult(confidence=MatchConfidence.NO_MATCH)
        for r in results:
            if r.confidence.value > best.confidence.value:
                best = r
            elif (
                r.confidence.value == best.confidence.value
                and r.year_distance is not None
            ):
                if best.year_distance is None or r.year_distance < best.year_distance:
                    best = r

        # Year-gap retry: if best has a large cover year gap AND group differs from
        # series_name, check whether the series_name exact strategies give a closer match.
        if (
            best.is_match()
            and best.confidence != MatchConfidence.BARCODE
            and clz_input.year is not None
            and best.gcd_series_id is not None
            and group_differs
        ):
            cy = self.adapter.get_issue_cover_year(
                best.gcd_series_id, clz_input.issue_nr
            )
            if cy is not None and abs(cy - clz_input.year) >= YEAR_GAP_RETRY_THRESHOLD:
                for candidate in (name_exact, name_year):
                    if candidate.is_match() and candidate.gcd_series_id is not None:
                        cand_cy = self.adapter.get_issue_cover_year(
                            candidate.gcd_series_id, clz_input.issue_nr
                        )
                        if cand_cy is not None and abs(cand_cy - clz_input.year) < abs(
                            cy - clz_input.year
                        ):
                            best = candidate
                            break

        # Reject group-strategy matches with implausibly large year gaps — likely omnibus false positives
        if (
            best.is_match()
            and "group" in (best.strategy_name or "")
            and best.gcd_series_id is not None
            and clz_input.year is not None
        ):
            cy = self.adapter.get_issue_cover_year(
                best.gcd_series_id, clz_input.issue_nr
            )
            if cy is not None and abs(cy - clz_input.year) > GROUP_YEAR_GAP_MAX:
                best = StrategyResult(confidence=MatchConfidence.NO_MATCH)

        if not best.gcd_issue_id and best.gcd_series_id:
            variant_result = self._try_variant_fallback(clz_input, best)
            if variant_result.is_match():
                return variant_result

        return best

    def _try_barcode(self, barcode: str) -> StrategyResult:
        """Try exact barcode match. BARCODE=100."""
        gcd_id = self.adapter.find_issue_by_barcode(barcode)
        if gcd_id:
            return StrategyResult(
                confidence=MatchConfidence.BARCODE,
                gcd_issue_id=gcd_id,
                strategy_name="barcode",
            )

        result = self.adapter.find_issue_by_barcode_prefix(barcode)
        if result:
            return StrategyResult(
                confidence=MatchConfidence.BARCODE,
                gcd_issue_id=result[0],
                strategy_name="barcode_prefix",
                match_details=f"matched_barcode={result[1]}",
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    def _try_exact_one_issue_for(
        self, clz: CLZInput, *, use_group: bool
    ) -> StrategyResult:
        """Try exact series name + issue number, single match. EXACT_ONE_ISSUE=90.

        Uses series_group_normalized when use_group=True, series_name_normalized otherwise.
        """
        name_lower = (
            clz.series_group_normalized.lower()
            if use_group
            else clz.series_name_normalized.lower()
        )
        strategy_suffix = "_group" if use_group else ""
        series_list = self.adapter.find_series_exact(
            name_lower, clz.publisher_normalized
        )

        if not series_list:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        candidates_with_issue = []
        for series in series_list:
            issue = self.adapter.find_issue(series["id"], clz.issue_nr)
            if issue:
                candidates_with_issue.append((series, issue))

        if len(candidates_with_issue) == 1:
            series, issue = candidates_with_issue[0]
            cy = self.adapter.get_issue_cover_year(series["id"], clz.issue_nr)
            year_dist = abs(cy - clz.year) if cy and clz.year else None
            return StrategyResult(
                confidence=MatchConfidence.EXACT_ONE_ISSUE,
                gcd_issue_id=issue[0],
                gcd_series_id=series["id"],
                strategy_name=f"exact_one_issue{strategy_suffix}",
                series_name=clz.series_name,
                issue_number=clz.issue_nr,
                year_distance=year_dist,
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    # Keep original name for backwards compatibility in callers
    def _try_exact_one_issue(self, clz: CLZInput) -> StrategyResult:
        return self._try_exact_one_issue_for(clz, use_group=False)

    def _try_exact_closest_year_for(
        self, clz: CLZInput, *, use_group: bool
    ) -> StrategyResult:
        """Try exact name + multiple matches, pick closest year. EXACT_CLOSEST_YEAR=85.

        Uses series_group_normalized when use_group=True, series_name_normalized otherwise.
        """
        name_lower = (
            clz.series_group_normalized.lower()
            if use_group
            else clz.series_name_normalized.lower()
        )
        strategy_suffix = "_group" if use_group else ""
        series_list = self.adapter.find_series_exact(
            name_lower, clz.publisher_normalized
        )

        if not series_list:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        candidates_with_issue = []
        for series in series_list:
            issue = self.adapter.find_issue(series["id"], clz.issue_nr)
            if issue:
                candidates_with_issue.append(series)

        if len(candidates_with_issue) > 1 and clz.year is not None:

            def year_dist(s: dict) -> int:
                cy = self.adapter.get_issue_cover_year(s["id"], clz.issue_nr)
                if cy is not None and clz.year is not None:
                    return abs(cy - clz.year)
                return abs(s["year_began"] - clz.year) if clz.year is not None else 0

            best = min(candidates_with_issue, key=year_dist)
            issue = self.adapter.find_issue(best["id"], clz.issue_nr)
            return StrategyResult(
                confidence=MatchConfidence.EXACT_CLOSEST_YEAR,
                gcd_issue_id=issue[0] if issue else None,
                gcd_series_id=best["id"],
                strategy_name=f"exact_closest_year{strategy_suffix}",
                series_name=clz.series_name,
                issue_number=clz.issue_nr,
                year_distance=year_dist(best),
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    # Keep original name for backwards compatibility in callers
    def _try_exact_closest_year(self, clz: CLZInput) -> StrategyResult:
        return self._try_exact_closest_year_for(clz, use_group=False)

    def _try_exact_series(self, clz: CLZInput) -> StrategyResult:
        """Try exact series name only. EXACT_SERIES=80."""
        name_lower = clz.series_name_normalized.lower()
        series_list = self.adapter.find_series_exact(
            name_lower, clz.publisher_normalized
        )

        if len(series_list) == 1:
            return StrategyResult(
                confidence=MatchConfidence.EXACT_SERIES,
                gcd_series_id=series_list[0]["id"],
                strategy_name="exact_series",
                series_name=clz.series_name,
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    def _try_normalized_series(self, clz: CLZInput) -> StrategyResult:
        """Try strict-normalized name match. NORMALIZED_SERIES=75."""
        series_list = self.adapter.find_series_strict(
            clz.series_name_strict, clz.publisher_normalized
        )

        if len(series_list) == 1:
            return StrategyResult(
                confidence=MatchConfidence.NORMALIZED_SERIES,
                gcd_series_id=series_list[0]["id"],
                strategy_name="normalized_series",
                series_name=clz.series_name,
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    def _try_word_order_series(self, clz: CLZInput) -> StrategyResult:
        """Try word-set match (reversed word order). WORD_ORDER_SERIES=70."""
        search_words = set(clz.series_name.split())
        if len(search_words) < 2:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        name_lower = clz.series_name_normalized.lower()
        results = []
        for series_list in self.adapter.iter_series_groups():
            s = series_list[0]
            if (
                clz.publisher_normalized
                and s.get("publisher_normalized") != clz.publisher_normalized
            ):
                continue
            key = s["name"]
            if set(key.split()) == search_words and key != name_lower:
                results.extend(series_list)

        if len(results) == 1:
            return StrategyResult(
                confidence=MatchConfidence.WORD_ORDER_SERIES,
                gcd_series_id=results[0]["id"],
                strategy_name="word_order_series",
                series_name=clz.series_name,
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    def _try_colon_comma_series(self, clz: CLZInput) -> StrategyResult:
        """Try colon/comma variant. COLON_COMMA_SERIES=68."""
        name_lower = clz.series_name_normalized.lower()
        comma_name = name_lower.replace(": ", ", ")
        if comma_name == name_lower:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        series_list = self.adapter.find_series_exact(
            comma_name, clz.publisher_normalized
        )
        if len(series_list) == 1:
            return StrategyResult(
                confidence=MatchConfidence.COLON_COMMA_SERIES,
                gcd_series_id=series_list[0]["id"],
                strategy_name="colon_comma_series",
                series_name=clz.series_name,
                match_details=f"matched_as={comma_name}",
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    def _try_article_series(self, clz: CLZInput) -> StrategyResult:
        """Try with/without 'The' prefix. ARTICLE_SERIES=60."""
        name_lower = clz.series_name_normalized.lower()

        if name_lower.startswith("the "):
            alt = name_lower[4:]
        else:
            alt = f"the {name_lower}"

        series_list = self.adapter.find_series_exact(alt, clz.publisher_normalized)

        if not series_list:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        if len(series_list) == 1:
            series = series_list[0]
            issue = self.adapter.find_issue(series["id"], clz.issue_nr)
            if issue:
                cy = self.adapter.get_issue_cover_year(series["id"], clz.issue_nr)
                year_dist = abs(cy - clz.year) if cy and clz.year else None
                return StrategyResult(
                    confidence=MatchConfidence.EXACT_ONE_ISSUE,
                    gcd_issue_id=issue[0],
                    gcd_series_id=series["id"],
                    strategy_name="article_series",
                    series_name=clz.series_name,
                    issue_number=clz.issue_nr,
                    year_distance=year_dist,
                )
            return StrategyResult(
                confidence=MatchConfidence.ARTICLE_SERIES,
                gcd_series_id=series["id"],
                strategy_name="article_series",
                series_name=clz.series_name,
                match_details=f"matched_as={alt}",
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    def _try_substring_series(self, clz: CLZInput) -> StrategyResult:
        """Try substring match. SUBSTRING_SERIES=50."""
        if len(clz.series_name) < 4:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        name_lower = clz.series_name_normalized.lower()
        search_terms = name_lower
        for prefix in ["the ", "a ", "an "]:
            if search_terms.startswith(prefix):
                search_terms = search_terms[len(prefix) :]
                break
        search_terms = search_terms.rstrip(" the")

        results = []
        for series_list in self.adapter.iter_series_groups():
            s = series_list[0]
            if (
                clz.publisher_normalized
                and s.get("publisher_normalized") != clz.publisher_normalized
            ):
                continue
            key = s["name"].lower()
            if search_terms in key or key in search_terms:
                results.extend(series_list)

        if results and clz.year is not None:
            filtered = []
            for s in results:
                cy = self.adapter.get_issue_cover_year(s["id"], clz.issue_nr)
                if cy and abs(cy - clz.year) <= 5:
                    filtered.append(s)
            if filtered:
                results = filtered

        if len(results) == 1:
            return StrategyResult(
                confidence=MatchConfidence.SUBSTRING_SERIES,
                gcd_series_id=results[0]["id"],
                strategy_name="substring_series",
                series_name=clz.series_name,
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    def _try_reverse_lookup(self, clz: CLZInput) -> StrategyResult:
        """Try reverse lookup by issue number + year. REVERSE_LOOKUP_*=65/55."""
        if clz.year is None:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        matches = self.adapter.find_issues_by_number_and_year(clz.issue_nr, clz.year)
        if not matches:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        unique_series = list(set(sid for sid, _ in matches))

        if len(unique_series) == 1:
            sid = unique_series[0]
            for s_id, gid in matches:
                if s_id == sid:
                    return StrategyResult(
                        confidence=MatchConfidence.REVERSE_LOOKUP_ONE,
                        gcd_issue_id=gid,
                        gcd_series_id=sid,
                        strategy_name="reverse_lookup_one",
                        series_name=clz.series_name,
                        issue_number=clz.issue_nr,
                    )

        if len(unique_series) > 1:
            if clz.publisher_normalized:
                pub_matches = [
                    sid
                    for sid in unique_series
                    if self.adapter.get_series_info(sid).get("publisher_normalized")
                    == clz.publisher_normalized
                ]
                if pub_matches:
                    unique_series = pub_matches

            if len(unique_series) == 1:
                sid = unique_series[0]
                for s_id, gid in matches:
                    if s_id == sid:
                        return StrategyResult(
                            confidence=MatchConfidence.REVERSE_LOOKUP_ONE,
                            gcd_issue_id=gid,
                            gcd_series_id=sid,
                            strategy_name="reverse_lookup_one",
                            series_name=clz.series_name,
                            issue_number=clz.issue_nr,
                        )

            best, best_score = None, 0.0
            for sid in unique_series:
                info = self.adapter.get_series_info(sid)
                score = self._similarity(
                    clz.series_name.lower(), info.get("name", "").lower()
                )
                if score > best_score:
                    best_score = score
                    best = sid
            if best:
                for s_id, gid in matches:
                    if s_id == best:
                        return StrategyResult(
                            confidence=MatchConfidence.REVERSE_LOOKUP_SIMILARITY,
                            gcd_issue_id=gid,
                            gcd_series_id=best,
                            strategy_name="reverse_lookup_similarity",
                            series_name=clz.series_name,
                            issue_number=clz.issue_nr,
                            match_details=f"matched_series={self.adapter.get_series_info(best).get('name', '')}",
                        )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    def _try_variant_fallback(
        self, clz: CLZInput, prior_result: StrategyResult
    ) -> StrategyResult:
        """Try the full Issue field when prior result had series but no issue."""
        if not clz.issue_full:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        if clz.issue_full == clz.issue_nr:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        has_letter = any(c.isalpha() for c in clz.issue_full)
        has_digit = any(c.isdigit() for c in clz.issue_full)
        if not (has_letter and has_digit):
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        sid = prior_result.gcd_series_id
        if sid is None:
            return StrategyResult(confidence=MatchConfidence.NO_MATCH)

        issue = self.adapter.find_issue(sid, clz.issue_full)
        if issue:
            cy = self.adapter.get_issue_cover_year(sid, clz.issue_full)
            year_dist = abs(cy - clz.year) if cy and clz.year else None
            return StrategyResult(
                confidence=MatchConfidence.EXACT_ONE_ISSUE,
                gcd_issue_id=issue[0],
                gcd_series_id=sid,
                strategy_name=f"{prior_result.strategy_name}_variant",
                series_name=clz.series_name,
                issue_number=clz.issue_full,
                year_distance=year_dist,
            )

        return StrategyResult(confidence=MatchConfidence.NO_MATCH)

    def _similarity(self, s1: str, s2: str) -> float:
        """Simple substring similarity score."""
        if s1 == s2:
            return 1.0
        if s1 in s2 or s2 in s1:
            shorter = s1 if len(s1) <= len(s2) else s2
            longer = s2 if len(s1) <= len(s2) else s1
            if longer.startswith(shorter):
                return min(0.9, 1.4 * len(shorter) / len(longer))
            return 0.8 * len(shorter) / len(longer)
        words1 = {w for w in s1.split() if w}
        words2 = {w for w in s2.split() if w}
        if words1 and words2:
            return len(words1 & words2) / len(words1 | words2)
        return 0.0
