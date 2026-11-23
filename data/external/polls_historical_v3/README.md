# Historical SSR / gfs.bern polls for V3 development

This addition contains **48 national poll observations for 24 referendum objects**
on **10 complete federal voting dates between 2016 and 2020**. Every object has
two waves. The existing V2 poll file, models, predictions and freeze are unchanged.

The observations were recovered from original publications by the commissioning
SSR outlets, principally SRF and SWI swissinfo.ch, and two gfs.bern reports archived
by Année politique suisse. Sources were selected by date, title, accessibility and
recoverability, without consulting model errors or referendum outcomes. This is
an initial source-availability sample, not exhaustive coverage of 2016–2020.

## Files and coverage

- `polls.csv`: model-compatible national totals and provenance fields.
- `evidence.json`: the same records with supporting source identifiers, extraction
  notes, source URLs and hashes, mapping details, exclusions and validation results.
- This README: interpretation and integration instructions.

| Voting date | Objects | Poll rows |
| --- | ---: | ---: |
| 2016-11-27 | 1 | 2 |
| 2017-05-21 | 1 | 2 |
| 2017-09-24 | 3 | 6 |
| 2018-03-04 | 2 | 4 |
| 2018-09-23 | 3 | 6 |
| 2018-11-25 | 3 | 6 |
| 2019-05-19 | 2 | 4 |
| 2020-02-09 | 2 | 4 |
| 2020-09-27 | 5 | 10 |
| 2020-11-29 | 2 | 4 |
| **Total** | **24** | **48** |

All objects on each selected date are included, checked against the local
Swissvotes identifier/date/title projection. Other dates were not completed in
this acquisition; `evidence.json` records these omissions. No results columns
were read for mapping or collection.

The 48 rows do not overlap the existing 96-row poll table. Their union contains
144 rows for 72 objects, including the existing future objects; these counts do
not imply that every object belongs to a particular model evaluation split.

## Values and dates

`yes_total`, `no_total` and `undecided` are published percentages on a **0–100**
scale. They describe national respondents intending to participate, not polls
conducted in individual municipalities. Every triplet sums to 100. All three
shares are explicitly recoverable from article text, original chart labels or
the report tables. **No undecided share was filled as a residual.** When chart
components were needed, summing the explicitly labelled certain/lean components
was cross-checked against the published aggregate.

The four detailed response columns are deliberately absent: their source
coverage is inconsistent, and no split into certain versus leaning responses
has been invented. Swissvotes identifiers use the repository representation,
for example `6160`, not the external Swissvotes number `616`.

Publication timestamps retain the source's timezone. HTML publications use the
current page's `datePublished` metadata. The March 2018 PDF reports use the
explicit embargo release on printed page 3, rather than the earlier report
preparation date. Survey dates are calendar dates.

**21 rows have a reported reference/middle interview day.** For the other
**27 rows**, `survey_midpoint` is the arithmetic calendar midpoint rounded down:

```text
survey_start + floor((survey_end - survey_start) / 2) days
```

These 27 rows carry `survey_midpoint_is_approximate=True` and
`survey_midpoint_method=arithmetic_floor_between_fieldwork_bounds`. Their full
fieldwork intervals are retained as `survey_midpoint_lower` and
`survey_midpoint_upper`. A reported chart/reference date is not automatically
claimed to be an empirical weighted median.

Later wave-2 charts identify earlier reference dates differing from the
calculated proxies by one day for May 2019 and two days for November 2020. These
later checks are recorded in the evidence; they are not backfilled into the
earlier publication row. This avoids implying that the later metadata was
already available at the first wave's publication.

## Availability and source provenance

**This is a retrospective reconstruction from current public sources.** Every
row keeps these three flags false:

```text
historical_version_verified
captured_before_vote
strict_forecast_ready
```

The announced dates precede the votes, but no independently archived pre-vote
version has been verified. A source hash establishes which current bytes were
inspected; it cannot establish that all of those bytes were available unchanged
at the historic prediction cutoff. Current `dateModified` timestamps are
retained and can include later publishing-system migrations.

The manifest references 40 sources and includes binary SHA-256 hashes for 38.
The remaining two are the March 2018 primary PDF reports: their text and tables
were inspected through the web PDF tool, but direct binary download returned
HTTP 403. No access restriction was bypassed and no binary hash is claimed.
Their four poll rows therefore have an empty `page_sha256`.

The checked numerical facts and provenance are retained in `evidence.json`.
Full articles, reports, photographs and charts are not redistributed here;
their publisher rights continue to apply. No open license on that underlying
material is asserted.

## Integration and verification

The existing `add_poll_features` implementation accepts totals-only input.
Before concatenation, remove the four detailed columns from an in-memory copy
of the old table; otherwise its validator will correctly reject the missing
detailed values on the new records.

```python
import pandas as pd
from scripts.modeling.poll_anchor import add_poll_features

existing = pd.read_csv(
    "data/external/polls/srg_gfs_polls.csv", dtype={"vote_key": str}
)
historical = pd.read_csv(
    "data/external/polls_historical_v3/polls.csv", dtype={"vote_key": str}
)
polls = pd.concat(
    [
        existing.drop(columns=["yes_certain", "yes_lean", "no_lean", "no_certain"]),
        historical,
    ],
    ignore_index=True,
)
enriched, audit = add_poll_features(municipal_table, polls)
```

The published CSV passed the existing `_validated_polls` checks both alone and
in the 144-row combined view. Collection validation also checked exact
identifier/date/title mappings, completeness of selected voting dates, unique
object/wave pairs, two increasing waves per object, percentages, chronology,
hash consistency and the absence of overlap with the old table.

Using the existing `add_poll_features`, all 24 objects additionally passed
four publication-boundary checks: immediately before wave 1, exactly at wave 1,
immediately before wave 2 and exactly at wave 2. No poll or trend is available
before its corresponding publication; exact published shares are preserved.
These checks use synthetic municipal identifiers and missing population values,
not referendum outcomes. Results and the CSV hash are recorded in the evidence.

## Evaluation implications

Compare latest-wave-only anchoring with the frozen trend configuration on the
same development dates. For approximate midpoint rows, vary the date within
the retained fieldwork interval. The evidence contains an endpoint sensitivity
calculation for all 16 affected objects, based only on the observed poll shares:

```text
full linear trend component =
    (yes_wave2 - yes_wave1)
    * (vote_date - midpoint_wave2)
    / (midpoint_wave2 - midpoint_wave1)
```

These ranges concern an uncapped trend factor of 1. They are **not** statistical
confidence intervals or bounds on end-to-end model error. For example, the
food-sovereignty object in September 2018 has a steep published decline; its
full linear component varies from about -34.21 to -12.65 percentage points
when only the approximate interview dates move to the fieldwork endpoints.
Any actual shrinkage, caps and national-to-municipal anchoring must be applied
by the model before interpreting the practical prediction effect.

Do not treat multiple municipalities as independent poll observations, infer
individual elector types from these national aggregates, or silently remove
objects without recovered polls when scoring the broader model.
