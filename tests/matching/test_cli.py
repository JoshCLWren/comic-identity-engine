"""Tests for CLI entry points."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def csv_data() -> str:
    return (
        "Core ComicID,Series,Issue,Issue Nr,Cover Year,Barcode,Publisher,Series Group\n"
        "1,Amazing Spider-Man,1,1,1990,,Marvel Comics,\n"
    )


class TestCliMainEntryPoint:
    """Tests for the CLI main function and argument parsing."""

    def test_main_processes_rows(self, tmp_path: Path, csv_data: str) -> None:
        """main() loads CSV, initializes adapter, and writes output."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_data, encoding="utf-8")
        output_file = tmp_path / "output.csv"

        mock_adapter = MagicMock()
        mock_adapter.series_count = 1
        mock_adapter.issue_count = 1
        mock_adapter._loaded = True
        mock_adapter.get_series_info.return_value = {"name": "Amazing Spider-Man"}
        mock_adapter.get_issue_cover_year.return_value = 1990

        from comic_identity_engine.matching.service import GCDMatchingService
        from comic_identity_engine.matching.types import (
            MatchConfidence,
            StrategyResult,
        )

        fake_result = StrategyResult(
            confidence=MatchConfidence.EXACT_ONE_ISSUE,
            gcd_issue_id=1,
            gcd_series_id=10,
            strategy_name="exact_one_issue",
        )

        old_argv = sys.argv
        sys.argv = ["cie-match", "--force"]
        try:
            with (
                patch(
                    "comic_identity_engine.matching.cli.CSV_PATH",
                    csv_file,
                ),
                patch(
                    "comic_identity_engine.matching.cli.OUTPUT_PATH",
                    output_file,
                ),
                patch(
                    "comic_identity_engine.matching.cli.GCDLocalAdapter",
                    return_value=mock_adapter,
                ),
                patch.object(GCDMatchingService, "match", return_value=fake_result),
            ):
                from comic_identity_engine.matching.cli import main

                main()
        finally:
            sys.argv = old_argv

        assert output_file.exists()
        content = output_file.read_text()
        assert "gcd_issue_id" in content
        assert "1" in content

    def test_main_skips_existing_without_force(
        self, tmp_path: Path, csv_data: str
    ) -> None:
        """Without --force, existing rows are preserved."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_data, encoding="utf-8")
        output_file = tmp_path / "output.csv"
        output_file.write_text(
            "Core ComicID,Series,Issue,Issue Nr,Cover Year,Barcode,Publisher,Series Group,gcd_issue_id\n"
            "1,Amazing Spider-Man,1,1,1990,,Marvel Comics,,42\n",
            encoding="utf-8",
        )

        mock_adapter = MagicMock()
        mock_adapter.series_count = 1
        mock_adapter.issue_count = 1

        old_argv = sys.argv
        sys.argv = ["cie-match"]
        try:
            with (
                patch(
                    "comic_identity_engine.matching.cli.CSV_PATH",
                    csv_file,
                ),
                patch(
                    "comic_identity_engine.matching.cli.OUTPUT_PATH",
                    output_file,
                ),
                patch(
                    "comic_identity_engine.matching.cli.GCDLocalAdapter",
                    return_value=mock_adapter,
                ),
            ):
                from comic_identity_engine.matching.cli import main

                main()
        finally:
            sys.argv = old_argv

        content = output_file.read_text()
        assert "42" in content

    def test_main_handles_empty_csv(self, tmp_path: Path) -> None:
        """When no rows to process, main prints nothing to do."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "Core ComicID,Series,Issue,Issue Nr,Cover Year,Barcode,Publisher,Series Group\n",
            encoding="utf-8",
        )
        output_file = tmp_path / "output.csv"

        old_argv = sys.argv
        sys.argv = ["cie-match"]
        try:
            with (
                patch(
                    "comic_identity_engine.matching.cli.CSV_PATH",
                    csv_file,
                ),
                patch(
                    "comic_identity_engine.matching.cli.OUTPUT_PATH",
                    output_file,
                ),
            ):
                from comic_identity_engine.matching.cli import main

                main()
        finally:
            sys.argv = old_argv

        assert not output_file.exists()

    def test_main_with_debug_flag(self, tmp_path: Path, csv_data: str) -> None:
        """--debug flag runs without error and collects mismatches."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_data, encoding="utf-8")
        output_file = tmp_path / "output.csv"

        mock_adapter = MagicMock()
        mock_adapter.series_count = 1
        mock_adapter.issue_count = 1
        mock_adapter.get_series_info.return_value = {"name": "Amazing Spider-Man"}
        mock_adapter.get_issue_cover_year.return_value = 2000

        from comic_identity_engine.matching.service import GCDMatchingService
        from comic_identity_engine.matching.types import (
            MatchConfidence,
            StrategyResult,
        )

        fake_result = StrategyResult(
            confidence=MatchConfidence.EXACT_ONE_ISSUE,
            gcd_issue_id=1,
            gcd_series_id=10,
            strategy_name="exact_one_issue",
        )

        old_argv = sys.argv
        sys.argv = ["cie-match", "--debug"]
        try:
            with (
                patch(
                    "comic_identity_engine.matching.cli.CSV_PATH",
                    csv_file,
                ),
                patch(
                    "comic_identity_engine.matching.cli.OUTPUT_PATH",
                    output_file,
                ),
                patch(
                    "comic_identity_engine.matching.cli.GCDLocalAdapter",
                    return_value=mock_adapter,
                ),
                patch.object(GCDMatchingService, "match", return_value=fake_result),
            ):
                from comic_identity_engine.matching.cli import main

                main()
        finally:
            sys.argv = old_argv

    def test_main_with_report_fp_flag(self, tmp_path: Path, csv_data: str) -> None:
        """--report-fp flag runs false positive report."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_data, encoding="utf-8")
        output_file = tmp_path / "output.csv"

        mock_adapter = MagicMock()
        mock_adapter.series_count = 1
        mock_adapter.issue_count = 1
        mock_adapter.get_series_info.return_value = {"name": "Amazing Spider-Man"}
        mock_adapter.get_issue_cover_year.return_value = 1990

        from comic_identity_engine.matching.service import GCDMatchingService
        from comic_identity_engine.matching.types import (
            MatchConfidence,
            StrategyResult,
        )

        fake_result = StrategyResult(
            confidence=MatchConfidence.EXACT_ONE_ISSUE,
            gcd_issue_id=1,
            gcd_series_id=10,
            strategy_name="exact_one_issue",
        )

        old_argv = sys.argv
        sys.argv = ["cie-match", "--report-fp"]
        try:
            with (
                patch(
                    "comic_identity_engine.matching.cli.CSV_PATH",
                    csv_file,
                ),
                patch(
                    "comic_identity_engine.matching.cli.OUTPUT_PATH",
                    output_file,
                ),
                patch(
                    "comic_identity_engine.matching.cli.GCDLocalAdapter",
                    return_value=mock_adapter,
                ),
                patch.object(GCDMatchingService, "match", return_value=fake_result),
            ):
                from comic_identity_engine.matching.cli import main

                main()
        finally:
            sys.argv = old_argv

    def test_false_positive_report_function(self, tmp_path: Path) -> None:
        """_print_false_positive_report handles missing gcd fields gracefully."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "Core ComicID,Series,Issue Nr,gcd_strategy,gcd_cover_year,Cover Year\n",
            encoding="utf-8",
        )
        output_file = tmp_path / "output.csv"
        output_file.write_text(
            "Core ComicID,Series,Issue Nr,gcd_strategy,gcd_cover_year,Cover Year\n"
            "1,X-Men,1,exact_one_issue,1990,1990\n",
            encoding="utf-8",
        )

        with (
            patch(
                "comic_identity_engine.matching.cli.CSV_PATH",
                csv_file,
            ),
            patch(
                "comic_identity_engine.matching.cli.OUTPUT_PATH",
                output_file,
            ),
        ):
            from comic_identity_engine.matching.cli import _print_false_positive_report

            _print_false_positive_report()

    def test_false_positive_report_with_large_gap(self, tmp_path: Path) -> None:
        """_print_false_positive_report shows entries with gap > 2."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "Core ComicID,Series,Issue Nr,gcd_strategy,gcd_cover_year,Cover Year\n"
            "1,X-Men,1,exact_one_issue,1990,1987\n",
            encoding="utf-8",
        )
        output_file = tmp_path / "output.csv"
        output_file.write_text(
            "Core ComicID,Series,Issue Nr,gcd_strategy,gcd_cover_year,Cover Year\n"
            "1,X-Men,1,exact_one_issue,1990,1987\n",
            encoding="utf-8",
        )

        with (
            patch(
                "comic_identity_engine.matching.cli.CSV_PATH",
                csv_file,
            ),
            patch(
                "comic_identity_engine.matching.cli.OUTPUT_PATH",
                output_file,
            ),
        ):
            from comic_identity_engine.matching.cli import _print_false_positive_report

            _print_false_positive_report()

    def test_false_positive_report_non_numeric_years(self, tmp_path: Path) -> None:
        """_print_false_positive_report handles non-numeric year values gracefully."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "Core ComicID,Series,Issue Nr,gcd_strategy,gcd_cover_year,Cover Year\n"
            "1,X-Men,1,exact_one_issue,foo,bar\n",
            encoding="utf-8",
        )
        output_file = tmp_path / "output.csv"
        output_file.write_text(
            "Core ComicID,Series,Issue Nr,gcd_strategy,gcd_cover_year,Cover Year\n"
            "1,X-Men,1,exact_one_issue,foo,bar\n",
            encoding="utf-8",
        )

        with (
            patch(
                "comic_identity_engine.matching.cli.CSV_PATH",
                csv_file,
            ),
            patch(
                "comic_identity_engine.matching.cli.OUTPUT_PATH",
                output_file,
            ),
        ):
            from comic_identity_engine.matching.cli import _print_false_positive_report

            _print_false_positive_report()


class TestModuleMain:
    def test_module_main_is_importable(self) -> None:
        """comic_identity_engine.matching.__main__ is importable."""
        from comic_identity_engine.matching import __main__

        assert hasattr(__main__, "main")

    def test_module_main_runs_as_script(self) -> None:
        """python -m comic_identity_engine.matching runs without import error."""
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from comic_identity_engine.matching import __main__",
            ],
            capture_output=True,
            cwd=Path(__file__).parents[3],
        )
        assert result.returncode == 0
