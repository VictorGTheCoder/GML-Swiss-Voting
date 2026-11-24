# V9 — Text, economic exposures and complementary communes

**Completed three separate matched suites.** Best observed exploratory score: **7.1319 pp**, E5 document 16 components, all heads. V8.1 reference 7.2295 pp reproduced in all three suites. Gain 0.0976 pp; paired descriptive interval crosses zero. No model promoted. The 4 pp objective remains unmet.

## Protocol

[Predeclared plan](../../../experiments/municipal_v9/plan.json). Same 66 objects, 23 dates, 138,868 municipal observations, 2016–2022, three chronological windows, PCA5 recency-weighted basis and frozen V8.1 poll correction. All municipalities retained; no 2023+ outcome used for fitting or scoring. Earlier preparation follows the repository's retrospective snapshot. No model replacement or strict forecast certification. These development dates have already been explored; paired date-bootstrap intervals are descriptive and do not adjust for multiple comparisons. Six new unit tests pass in the dedicated modeling job and acquisition gates.

## 1. Text acquisition and embeddings

The target-blind roster contains 306 historical objects from 1990 through 2022, all with Swissvotes French title metadata. Candidate brochure links require same vote date, source identity, official Chancellery URL, PDF hash and explicit source-specific candidate link, with a mutual unique high title-similarity match. 99 matches remain; 68 have a nonempty reasonable-length extracted summary; 16 of the 66 validation objects have an accepted summary candidate. Ambiguous/unmatched items use title-only fallback. This is a retrospective automatic linkage, **not independent semantic or historical version review**, and does not alter strict admission flags. Full legal sections not automatically admitted. Title and summary embeddings use `intfloat/multilingual-e5-small` (revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`, 384 dimensions, mean-pooled normalized token chunks, frozen pretrained model). The 2024 pretrained model's historic availability and training-corpus content are not certified. TF-IDF char 3–5 grams and SVD/PCA compression fit only on each historical train; validation objects never fit those transformations.

| Variant | MAE pp | Centered MAE pp | Oracle | Gain interval vs reference |
|---|---:|---:|---|---|
| reference | 7.2295 | 5.3701 | no | [0.0000, 0.0000] |
| tfidf_title_8_all | 7.5181 | 5.4336 | no | [-0.5805, -0.0179] |
| tfidf_title_8_local | 7.2393 | 5.4336 | no | [-0.1179, 0.1169] |
| tfidf_title_8_ridgeblend | 7.2101 | 5.3611 | no | [-0.0952, 0.1280] |
| tfidf_document_8_all | 7.3325 | 5.4428 | no | [-0.3337, 0.0753] |
| tfidf_document_8_local | 7.2554 | 5.4428 | no | [-0.1062, 0.0487] |
| tfidf_document_8_ridgeblend | 7.2203 | 5.3848 | no | [-0.1030, 0.1102] |
| e5_title_8_all | 7.3263 | 5.5557 | no | [-0.3109, 0.1289] |
| e5_title_8_local | 7.3989 | 5.5557 | no | [-0.3413, -0.0156] |
| e5_title_8_ridgeblend | 7.2227 | 5.3838 | no | [-0.1059, 0.1105] |
| e5_document_8_all | 7.2549 | 5.5126 | no | [-0.2438, 0.2270] |
| e5_document_8_local | 7.3584 | 5.5126 | no | [-0.2694, 0.0059] |
| e5_document_8_ridgeblend | 7.2371 | 5.4011 | no | [-0.1234, 0.0940] |
| e5_document_16_all | 7.1319 | 5.4815 | no | [-0.1268, 0.3474] |
| e5_document_16_local | 7.3208 | 5.4815 | no | [-0.2327, 0.0514] |
| e5_document_16_ridgeblend | 7.2179 | 5.3664 | no | [-0.1392, 0.1414] |

Best E5 variant improves the overall MAE by 0.0976 pp but raises centered MAE by 0.1115 pp. On the 16 summary-covered objects, average gain is 0.0572 pp (11 improved); on 50 without a summary it is 0.1106 pp (21 improved). Window gains: 2016–18 +0.2884, 2019–20 −0.1971, 2021–22 +0.0065 pp. This does not isolate a reliable summary benefit. No claim of generalizable improvement or causal explanation.

[Acquisition and immutable embeddings](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45295220148/artifacts/14877020317) · [text benchmark](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45295665767/artifacts/14875374515).

## 2. Municipal economic exposures

Official OFS STATENT table `px-x-0602010000_102`, [catalogue](https://statistik.admin.ch/fr/asset/36734273), 2026-08-20 edition, geography 2024-01-01. The original acquisition encountered ISO-8859-15 instead of UTF-8; explicit decoding and metadata-validated sector codes resolved this. Use only 2011–2020 data; 2,131 original communes remapped to 2,110 reference communes using official 2024–2026 mutation history, no unresolved code. 21,100 commune-year rows. Sum counts before computing shares; keep protected missing cells missing rather than zero. The raw and processed file hashes are in results.json and the acquisition artifact. Use year Y no earlier than 1 January Y+2 as a conservative release proxy; the exact historic vintage remains unverified. Employment is measured at workplaces and is not a measure of the occupations of individual voters.

Predict per-object regression coefficients for municipal variation unexplained by historical PCA5, via regularized Ridge on object features. Center/scale municipal covariates within each known object; neutral missing model-space value after centering, no raw-value imputation. Economic block: three sector shares and log jobs/establishments. Control: demographic share foreign, share 0–19, log population. Economic + demographic combination. Ridge penalties 30/100. Available covariate training objects for economic block: 29/59/71; demographic control 41/71/83. This is an initial interaction design, not an exhaustive test of socioeconomic data, and the control's training support differs from the economic block.

| Variant | MAE pp | Centered MAE pp | Oracle | Gain interval vs reference |
|---|---:|---:|---|---|
| reference | 7.2295 | 5.3701 | no | [0.0000, 0.0000] |
| demographic_control_30 | 7.2312 | 5.3729 | no | [-0.0406, 0.0286] |
| demographic_control_100 | 7.2285 | 5.3695 | no | [-0.0227, 0.0199] |
| economy_30 | 7.2250 | 5.3687 | no | [-0.0351, 0.0339] |
| economy_100 | 7.2277 | 5.3693 | no | [-0.0210, 0.0201] |
| demographic_economy_30 | 7.2273 | 5.3723 | no | [-0.0385, 0.0335] |
| demographic_economy_100 | 7.2281 | 5.3708 | no | [-0.0221, 0.0207] |

Best economic variant 7.2250 pp, improvement only 0.0045 pp; interval crosses zero. Broad employment sectors and the current regularized interaction design do not provide convincing extra signal. Income, housing and more specific exposure measures have not yet been acquired or tested. Do not generalize this result to all economic variables.

[Verified STATENT recovery](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45295827067/artifacts/14876756029) · [economic benchmark](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45296058385/artifacts/14877270072).

## 3. Complementary municipality selection

Past-only PCA loadings; greedy D-optimal information criterion (including intercept) and fixed seeded random panels of 10/20 communes with ≥95% historical coverage. Each window learns panel outcome heads from pre-vote object features. Predict all municipalities by regularized inverse projection, with either panel-derived global level or original global head. Original V8.1 poll corrections applied to every actual forecast. The hindsight-only oracle supplies actual held-out panel outcomes and reconstructs without survey correction. These oracles are scored on all municipalities including selected panel members; not pre-vote forecasts or independent reconstruction-only estimates. The single fixed random panel per size is a limited control; do not claim D-optimal superiority on random panels generally.

| Variant | MAE pp | Centered MAE pp | Oracle | Gain interval vs reference |
|---|---:|---:|---|---|
| reference | 7.2295 | 5.3701 | no | [0.0000, 0.0000] |
| panel_diverse_10 | 7.5869 | 5.6553 | no | [-0.7593, 0.0128] |
| panel_diverse_10_local | 7.4170 | 5.6553 | no | [-0.3838, 0.0097] |
| oracle_panel_diverse_10 | 5.4762 | 4.7773 | yes | [1.0455, 2.4737] |
| panel_random_10 | 7.7860 | 6.0879 | no | [-0.7881, -0.3078] |
| panel_random_10_local | 7.7155 | 6.0882 | no | [-0.7063, -0.2603] |
| oracle_panel_random_10 | 5.9818 | 5.9231 | yes | [0.4202, 2.1105] |
| panel_diverse_20 | 7.4655 | 5.4313 | no | [-0.5455, 0.0343] |
| panel_diverse_20_local | 7.2703 | 5.4313 | no | [-0.1701, 0.0866] |
| oracle_panel_diverse_20 | 4.7083 | 4.2190 | yes | [1.8019, 3.2840] |
| panel_random_20 | 7.3195 | 5.4209 | no | [-0.2719, 0.0775] |
| panel_random_20_local | 7.2498 | 5.4209 | no | [-0.1382, 0.0943] |
| oracle_panel_random_20 | 4.2679 | 4.2152 | yes | [2.2929, 3.6761] |

Neither predictive panel improves reference. D-optimal 10 has a lower oracle MAE than the tested random 10, but D-optimal 20 has a higher oracle MAE than the tested random 20. The model cannot access observed held-out panel results before a vote. Selection of geographically complementary municipalities may be more useful for election-night nowcasting or actual pre-vote observations, outside this objective.

[Panel benchmark and exact selected commune IDs](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45295665767/artifacts/14876581949).

## Decision

Retain V8.1 as frozen reference. The best V9 observed score 7.1319 pp is exploratory and not sufficiently robust to promote. No major reduction toward 4 pp achieved. Next data priority, if pursued: improve actual official brochure matching and semantic quality; acquire more informative time-aligned municipal economic measures, rather than repeatedly optimizing this narrow block. Separate structural vs poll-anchored contributions and establish an independent or prospective evaluation. The exact numerical registry is [results.json](results.json).

## Reproduction

Use the original acquisition artifact for text/panels and the recovered artifact for economy. Both include hashes. Re-run with `requirements-experiments.txt` and the stage workflows:
- `.github/workflows/acquire-v9.yml`
- `.github/workflows/statent-recovery-v9.yml`
- `.github/workflows/remaining-v9.yml`
- `.github/workflows/economy-v9.yml`

The acquisition and benchmark scripts preserve the original models; no strict model or production forecast altered. Dedicated tests and runs completed successfully. Artifact retention is subject to GitHub Actions expiration; the plan, numerical registry, code and provenance manifest are committed.
