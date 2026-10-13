# Forecast-time brochure text export

Use `scripts.federal_explanations_temporal.build_forecast_text_export(records,
output_dir)` with one reviewed object record per vote ID. The function reuses
existing brochure eligibility gates; it does not convert a proposed match or
unreviewed section into validated object text.

Records carry `vote_id`, `voting_date` (legacy `vote_date` also accepted), `text`
(legacy `full_text` accepted), and the existing `availability_status`,
`match_status`, `extraction_status`, `semantic_status`, `source_sha256`,
`decision_source_sha256`, and subsidiary-question flag. Require
`forecast_at` and `forecast_evidence` (or `forecast_reference`) documenting the
brochure-publication instant, plus `availability_at` and
`availability_reference` documenting public availability of that exact PDF
version. A reference is an auditable documentary pointer, never a collection
date inferred as publication. The reviewed decision must describe the current
hash; changing the hash requires renewed review.

Instants accept ISO calendar dates or timezone-aware ISO timestamps. Date-only
inputs mean midnight UTC; use timestamps when intra-day ordering matters.
Availability equal to the cutoff is eligible. A release after the cutoff is
excluded even when it preceded voting day. Missing evidence or an unknown
instant is excluded. Duplicate object records are all retained for review
rather than silently choosing a section or brochure.

The return value contains `documents`, `exclusions`, and `report`. Output records
expose `vote_id`, `voting_date`, `text`, `forecast_at`, `forecast_evidence`, and
source provenance for attachment to municipal evaluation rows. The optional
directory receives corresponding JSON files. The report counts eligible
objects, distinct dates, documents, and exclusions by reason. An empty result
writes an empty documents file and `empty_eligible_corpus`; nontext evaluation
can continue independently. Exclusions retain source fields, including ambiguous
object relationships, for review.

Strict export validates the voting calendar date and requires the forecast instant to be strictly
before its start in UTC. Invalid voting dates and cutoffs on/after voting day remain audited
exclusions, even when the other text/version gates pass.
