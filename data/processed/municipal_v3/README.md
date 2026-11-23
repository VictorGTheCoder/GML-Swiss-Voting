# Additional object information, V3

`object_features.csv` contains one row per each of the 380 objects in the V2
prepared population. It adds 24 stakeholder recommendation categories and eight
procedure descriptors, plus three fields containing unordered domain-code sets.
The sets are encoded using a vocabulary learned separately on each training
window; they are not target encodings.

The controlled, existing Swissvotes snapshot is the source. This file adds
previously unused information to the feature preparation; it is not a new
collection of referendum outcomes. `manifest.json` contains definitions,
source fields, hashes and coverage. The separately acquired historical polls
are in `data/external/polls_historical_v3/`.

Recommendations keep yes, no, free voting, no recommendation, nonexistence and
missingness distinct. Numerical procedure fields include the log of valid
signatures, signature/quorum ratio, log collection speed, number of objects
on the ballot date, days since the parliamentary decision and the documented
partial-certification indicator for certain Covid-era petitions. Responsible
department and signature applicability are categorical. Signature quantities
require both submission and certification dates preceding the vote.

`strict_forecast_ready` remains false: the current source describes pre-vote
events but its precise historical versions are not independently established.
The source does not establish how an individual elector followed a recommendation.

To reproduce without replacing this snapshot:

```bash
.venv/bin/python -m scripts.modeling.object_enrichment_v3 \
  --input reports/generated/municipal_v3_base \
  --output reports/generated/municipal_v3_object_rebuild
```

Source and coding: [Swissvotes dataset](https://swissvotes.ch/page/dataset) and
[codebook](https://swissvotes.ch/page/dataset/codebook-de.pdf), CC BY 4.0,
Année Politique Suisse, University of Bern.
