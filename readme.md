# Comic Identity Engine

A canonical identity and reconciliation layer for comic books across structured catalogs and freeform marketplaces.

## Overview

Comic Identity Engine is a domain-specific entity resolution system designed to:

* Normalize comic series and issues into a stable canonical model.
* Map structured platforms (CLZ, League of Comic Geeks, CCL, Atomic Avenue) into a unified internal identity.
* Reconcile freeform marketplace listings (eBay, HipComic) to canonical issues.
* Support variant-aware pricing and review linking.
* Power higher-level applications such as Comic Pile.

This project treats identity as a first-class concern.

Everything converges on a single internal Issue UUID.

---

## Why This Exists

Comic platforms disagree about:

* Where a series splits into volumes.
* When a rename creates a new series.
* How legacy numbering is handled.
* How variants are modeled.
* How annuals and specials are categorized.

Marketplaces add additional chaos:

* Freeform titles.
* Omitted volume indicators.
* Event prefixes.
* Dash inconsistencies (`-1`, `#-1`, `  - 1`).
* Variant ambiguity.

This engine provides:

A neutral identity layer that reconciles all of the above without becoming dependent on any one platform.

---

## Design Principles

1. Canonical First
   Internal identity is authoritative. External systems are adapters.

2. Structured and Freeform Separation
   Structured catalogs and freeform listings are handled differently.

3. Deterministic Before ML
   Clear parsing and scoring rules come before machine learning.

4. Variant Optionality
   Variant precision is required for pricing, optional for buying.

5. Explainable Matching
   Every match produces a confidence score and explanation.

---

## Core Concepts

### SeriesRun

Represents a publishing run with stable identity.

Example:

* X-Men (1991)
* Daredevil Vol 2 (1998)

Handles renames and legacy numbering via aliasing and continuity grouping.

---

### Issue

Canonical issue identity.

* Issue number stored as `VARCHAR` (supports `-1`, `1/2`, `0`, `600.1`)
* Cover date
* Legacy numbering
* External cross references

All external mappings converge here.

---

### Variant (Optional)

Variant modeling is separated from issue identity.

Used when:

* Pricing owned inventory.
* Matching incentive covers.
* Distinguishing newsstand vs direct.

Ignored when:

* Simply buying a reading copy.

---

### External Links

Each issue can attach:

* GCD ID
* Metron ID
* League of Comic Geeks ID
* Structured marketplace IDs

External identity is stored, never inferred repeatedly.

---

### Platform Listings

Marketplace listings are stored as:

* Raw title
* Parsed issue number
* Parsed series tokens
* Year
* Condition
* Raw JSON payload

These are reconciled against canonical issues via scoring.

---

## Architecture

```
SeriesRun
Issue
Variant (optional)

ExternalSeriesLink
ExternalIssueLink

Platform
PlatformSeriesMapping
PlatformListing

IssueListingMatch
```

Everything maps inward.

Nothing maps sideways.

---

## Matching Strategy

1. Candidate Generation

   * Trigram similarity
   * Tokenized search
   * Numeric filters on issue number and year

2. Deterministic Scoring

   * Exact issue number match required
   * Series alias similarity scoring
   * Publisher match boosting
   * Year proximity boosting
   * Variant confidence optional

3. Confidence Output

   * issue_confidence
   * variant_confidence
   * overall_confidence
   * explanation

---

## Initial Test Case

The first canonical stress test:

X-Men #-1 (1991 series)

Why:

* Negative issue number
* Event prefix contamination
* Dash formatting inconsistencies
* Variant ambiguity
* Marketplace noise

If identity survives this case, it is structurally sound.

---

## Intended Use Cases

* Cross-platform price reconciliation.
* Accurate sold listing matching.
* Linking reviews from League of Comic Geeks.
* Reading order awareness.
* Cross-series recommendation engines.
* Multi-platform collection syncing.

---

## Non-Goals (For Now)

* Becoming a public canonical standard.
* Scraping entire external catalog graphs.
* Replacing structured catalog providers.
* Building a recommendation engine before identity is stable.

---

## Status

Initial design phase.

First milestone:

* Canonical schema
* X-Men #-1 reconciliation test
* Deterministic scoring prototype

---

## Philosophy

Identity is infrastructure.

Once identity is stable, everything else becomes simpler:

* Pricing.
* Recommendations.
* Reading order logic.
* Cross-platform linking.

This engine builds that foundation.

