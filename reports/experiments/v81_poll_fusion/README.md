# V8.1 — Multi-institute polls and conditional municipal profiles

**Status: all four experimental stages completed successfully; exploratory, not deployment-ready.** 
The original V8 reference reproduces exactly: 7.3402 pp. The best observed configuration is `v8_reference__joint_urban_weaker`, 7.2295 pp; the target of 4 pp is not reached. No frozen candidate is replaced.

## Plan and matched evaluation

The predeclared plan is [experiments/municipal_v81/plan.json](../../../experiments/municipal_v81/plan.json). This campaign is limited to polling and geographic conditioning, not embeddings, economics, commune panels or other feature enrichment. Evaluate the same 66 votes, 23 dates and 138,868 municipal observations from 2016–2022. MAE averages the municipal absolute error within each vote, then gives every object equal weight. The national anchor uses a population proxy rather than actual ballot counts. The modeling evaluation excludes 2023+ targets. The original V7 recent-PCA structural profile and original V8 forecast are frozen. All institute weighting and empirical poll error covariance fits use completed earlier voting dates only, with no same-day outcomes. Chronological folds govern historical profiles.

## 1. Acquisition and validation (2 tests passed)

- Latest LeeWas/Tamedia reported pre-vote yes margins: 66 objects, transcribed from tables 43–44 of the institute's 29 May 2024 report. This retrospective compilation is a weaker provenance tier: exact original publication timestamps and historical version identity are not certified. No results or accuracy columns were acquired as inputs.
- SSR: 17 additional two-wave pairs documented in contemporary publications, increasing coverage from 48 to 65 objects. The assisted reproduction vote (6030) has no SSR poll in the reviewed source. Some midpoints are arithmetic approximations; yes-only waves do not justify inventing undecided/no figures. Primary-source pairs govern the historical trend estimate.
- Of the 48 frozen SSR latest margins, 47 agree with the retrospective table. Preserve the directly sourced 56% for 6350 rather than the table's 58%; for 6000 retain the primary-source 46% instead of the retrospective 40%.
- Settlement poll margins: 141/144, 47 complete waves for 24 objects. The second wave for 6390 was rejected because three unambiguous categories could not be recovered; use its first complete admissible wave. Linguistic margins remain 135/144 for the same 24 objects. Earlier regional/settlement charts could not be reliably recovered, so the uncovered 42 objects retain their national-only predictions.

Source snapshots and extraction evidence: [acquisition artifact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45292731014/artifacts/14873834489). Original national evidence is versioned under `data/external/polls_v81/`. Manifest contains SHA-256 values of the extracted tables.

## 2. National fusion (4 tests passed)

Compare all 13 predeclared variants, applying the original V8 linguistic adjustment where available. Mixtures are convex weights on the SSR trend-anchored national estimate and Tamedia latest yes share (not two comparable last waves unless explicitly indicated). Adaptive weights minimize historical paired squared errors with shrinkage and optional bias correction. The borrowed-trend variant partially transfers the SSR trend to Tamedia; it is not an observed second Tamedia wave.

| Configuration | Overall MAE | National only MAE | 17 added SSR votes MAE | Gain vs V8, date-bootstrap 95% interval |
|---|---:|---:|---:|---|
| v8_reference | 7.3402 | 7.5472 | 8.7633 | [0.0000, 0.0000] |
| ssr_extended | 7.4732 | 7.6802 | 9.2797 | [-0.5660, 0.3689] |
| ssr_extended_tamedia_fallback | 7.4835 | 7.6905 | 9.2797 | [-0.5851, 0.3646] |
| ssr_latest_tamedia_fallback | 8.5307 | 8.7077 | 9.6972 | [-2.0984, -0.3505] |
| tamedia_latest | 8.5536 | 8.7228 | 9.2977 | [-2.5062, 0.0319] |
| blend25 | 7.9319 | 8.1274 | 8.9558 | [-1.6370, 0.3941] |
| blend50 | 7.5308 | 7.7390 | 8.8556 | [-0.9484, 0.5533] |
| blend75 | 7.3804 | 7.5902 | 8.9679 | [-0.5360, 0.5019] |
| blend_latest50 | 8.2359 | 8.4172 | 9.1266 | [-1.9623, 0.1086] |
| blend_borrowed_trend50 | 7.3993 | 7.6134 | 8.9593 | [-0.6985, 0.5898] |
| adaptive_mse | 7.4804 | 7.6897 | 8.8575 | [-0.8534, 0.4999] |
| adaptive_bias_mse | 7.5260 | 7.7347 | 8.8888 | [-0.8927, 0.4598] |
| consensus_disagreement_shrink | 7.5491 | 7.7522 | 8.8307 | [-0.9501, 0.5201] |

Conclusion: none of the national fusion variants beats V8 globally. The 17 new SSR votes have an MAE of 9.2797 after adding SSR, versus 8.7633 before. More survey coverage alone does not guarantee a lower error. Six national bases fixed in the stage-02 code before seeing the results are passed to subsequent stages. 

[National benchmark](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45293115635) · [results artifact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45293115635/artifacts/14875157414).

## 3. Overlapping language/settlement contrasts (4 tests passed)

The actual OFS snapshot contains 509 urban, 580 intermediate and 1021 rural communes. The three-class mapping to large agglomeration, small/medium agglomeration and rural is **only a proxy**, not a verified crosswalk to the gfs.bern survey classification. See [OFS 2020 typology](https://www.swissstats.bfs.admin.ch/data/webviewer/appId/ch.admin.bfs.swissstat/article/issue242122972000-05/package). The source geography is frozen at 2026; strict pre-vote availability is not certified. 
Each group-average operator is normalized by the municipal population proxy. Use two independent contrasts per three-category family; fit a common national-centered indicator-space ridge adjustment. The contrast pair covariance accounts for a shared reference category; the fixed prior assumes zero cross-family covariance and the empirical variant in stage 04 learns cross-family second moments. Every adjusted vector is clipped/projected to preserve its national weighted mean. Compare 6 national bases × 8 methods (48 entries).

| Method on original V8 national base | MAE all 66 | MAE 24 covered | Centered MAE | Gain interval vs V8 |
|---|---:|---:|---:|---|
| national | 7.5472 | 6.9891 | 5.6115 | [-0.3785, -0.0623] |
| language | 7.3402 | 6.4198 | 5.3680 | [0.0000, 0.0000] |
| urban25 | 7.4732 | 6.7858 | 5.5778 | [-0.2626, -0.0243] |
| urban50 | 7.4349 | 6.6803 | 5.5782 | [-0.2136, 0.0109] |
| urban100 | 7.4768 | 6.7957 | 5.6821 | [-0.3218, 0.0300] |
| joint_ridge10 | 7.2562 | 6.1888 | 5.4207 | [0.0072, 0.1821] |
| joint_ridge30 | 7.2398 | 6.1437 | 5.3918 | [0.0308, 0.1847] |
| joint_urban_weaker | 7.2295 | 6.1156 | 5.3701 | [0.0357, 0.1956] |

Winner: `joint_urban_weaker`, with ridge 0.1 and four times the contrast noise variance assigned to settlement vs language. Gain of 0.1106 pp overall; covered-object MAE falls from 6.4198 to 6.1156. Centered MAE changes only slightly: the benefit is not evidence of a large improvement in within-object local pattern learning.

[Spatial artifact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45293413993/artifacts/14875381990).

## 4. Conditional Gaussian low-rank prior (4 tests passed)

Five-year recency-weighted historical municipal contrasts are decomposed into 20 components for each outer fold, then ranks 5/10/20 are tested with fixed and empirical observation noise. The prior point estimate is the frozen national-anchored structural prediction. The conditional mean update uses
`B C H.T (H C H.T + R)^-1 (z - A p)`, with `H = A B`, historic coefficient covariance `C`, poll contrasts `z`, national-centered basis `B`, and positive definite regularized observation covariance `R`. Empirical second moments include cross-family correlations and use only complete contrast-error vectors from dates strictly before the current date; shrink toward eight pseudo-observations from the fixed prior. The national weighted anchor is preserved. This is a conditional mean experiment, not a calibrated posterior interval. Compare 6 bases × 9 entries (54 including language reference).

| Method on original V8 national base | MAE all 66 | MAE 24 covered | Centered MAE | Gain interval vs V8 |
|---|---:|---:|---:|---|
| language | 7.3402 | 6.4198 | 5.3680 | [0.0000, 0.0000] |
| latent5_noise4 | 7.3237 | 6.3747 | 5.3965 | [-0.1197, 0.1325] |
| latent10_noise4 | 7.2906 | 6.2837 | 5.3641 | [-0.0457, 0.1431] |
| latent20_noise4 | 7.2886 | 6.2780 | 5.3636 | [-0.0440, 0.1457] |
| latent10_noise8 | 7.3387 | 6.4159 | 5.4047 | [-0.0581, 0.0531] |
| latent20_noise8 | 7.3379 | 6.4137 | 5.4049 | [-0.0580, 0.0545] |
| latent10_empirical | 7.2482 | 6.1670 | 5.3337 | [-0.0104, 0.2083] |
| latent20_empirical | 7.2463 | 6.1617 | 5.3333 | [-0.0085, 0.2113] |
| latent10_language | 7.4294 | 6.6651 | 5.4462 | [-0.2890, 0.0379] |

Best conditional variant: v8_reference__latent20_empirical, 7.2463 pp. It does not beat stage 03. Its interval crosses zero. Retain the simpler joint adjustment as the best **observed** exploratory model; no prospective deployment decision.

[Combined stage 03–04 benchmark](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45293413993) · [conditional artifact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45293413993/artifacts/14874982682).

## 5. Reproduction

From the repo root in an environment with pinned experiment dependencies:

```bash
pip install -r requirements-experiments.txt
python -m pytest -q tests/test_poll_acquisition_v81.py
python -m scripts.modeling.poll_acquisition_v81 --output reports/generated/acquisition_v81
python -m scripts.modeling.municipal_v2 prepare --output reports/generated/fusion_v81_base
python -m scripts.modeling.inductive_profiles_v8 --base reports/generated/fusion_v81_base --output reports/generated/inductive_v8
python -m pytest -q tests/test_national_fusion_v81.py
python -m scripts.modeling.national_fusion_v81 --base reports/generated/fusion_v81_base --predictions reports/generated/inductive_v8 --acquisition reports/generated/acquisition_v81 --output reports/generated/national_v81
python -m pytest -q tests/test_spatial_margins_v81.py
python -m scripts.modeling.spatial_margins_v81 --base reports/generated/fusion_v81_base --acquisition reports/generated/acquisition_v81 --fusion reports/generated/national_v81 --output reports/generated/spatial_v81
python -m pytest -q tests/test_conditional_profiles_v81.py
python -m scripts.modeling.conditional_profiles_v81 --base reports/generated/fusion_v81_base --acquisition reports/generated/acquisition_v81 --fusion reports/generated/national_v81 --spatial reports/generated/spatial_v81 --output reports/generated/conditional_v81
```

For byte-exact comparisons use the archived acquisition and inductive artifacts rather than re-fetching source charts. A fresh run validates hashes and independently replays the V8 score; the artifacts may expire, while the code and compact numerical registry are committed. 
[Full machine-readable registry](results.json): every configuration (115 scored entries including duplicated references) and descriptive paired-date bootstrap interval.

## Decision and limitations

The V8.1 exploratory best improves V8 by 0.1106 pp (1.51% relative). The remaining gap to 4 pp is 3.2295 pp. The results reuse the same development objects and are subject to selection multiplicity; confidence intervals are descriptive rather than independent confirmation. National and survey dates/versions, geography, subgroup crosswalk and sample noise are not all prospectively verified. Only 24 objects have geographic polls; the 42 missing must not be presented as surveyed. Do not promote a model solely from these experiments; use independently held-out later dates only under a separately locked protocol, with verified pre-vote inputs.
