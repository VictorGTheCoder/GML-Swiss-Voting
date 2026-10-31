# Executed verification · 2026-10-31

Base: main `529bee3` (includes merged PRs #68 and #69).
Original notebook: `6741747853304ed2d2e16f66e13b60cb52020615`.
Dataset SHA-256:
`c8a488826093a53f307af0b4a04627fa6d78118a8ac4b25ca8c8e097fdf8e043`.
All five input source hashes matched the structured dataset manifest on current main.

Commands successfully executed from the repository root:

```bash
.venv/bin/python -m scripts.modeling.retrospective_demo
uv venv --python python3.12 /tmp/swiss-voting-demo-clean
uv pip install --python /tmp/swiss-voting-demo-clean/bin/python -r requirements-demo.txt
/tmp/swiss-voting-demo-clean/bin/python -m scripts.modeling.retrospective_demo --output /tmp/swiss-voting-demo-clean-results
```

The fresh environment independently installed the pinned dependencies. Both runs
produced byte-identical SVG figures and bit-identical prediction tables (252,600 rows = five models × 50,520
validation observations), identical metrics and identical serialized boosting bytes.
Boosting artifact SHA-256:
`d8a61eb47b1d843d32f6306f65c38a317d099cbbf14941152eeb412e6326a83f`.
Each run also checked identical raw boosting predictions after pipeline reload.
The model is generated at `reports/generated/retrospective_demo/boosting.joblib`;
the binary and full prediction table are intentionally regenerated rather than
versioned. Curated figures, scores, split counts and manifest accompany this record.

The fresh run was performed by the same agent, not another teammate. Independent
human reproduction remains outstanding and must not be claimed complete for #51.

Validation MAE (percentage points, equal municipality–object row weight):

| Model | MAE |
| --- | ---: |
| Constant | 13.172507 |
| Municipal history | 12.969979 |
| HistGradientBoostingRegressor | 12.005408 |
| Ridge history (alpha 1) | 13.042580 |
| Ridge combined (alpha 1) | 10.697160 |

Object-weighted MAE equals row-weighted MAE because every object has 2,105 rows;
date-weighted scores are in the metrics table. Boosting improves on municipal
history by 0.964571 percentage points, but combined Ridge performs better on this
reused validation set. No hyperparameter search or final-test evaluation occurred.
Strict V1 eligibility remains zero. Availability and geographic-vintage assumptions
remain retrospective; no operational forecasting performance is demonstrated.

Final local checks:

- `.venv/bin/python -m pytest tests -q`: **270 passed** (149.94 s).
- `.venv/bin/python -m pytest tests/test_retrospective_demo.py -q`: **4 passed**;
  rerun after the SVG export adjustment.
- `.venv/bin/ruff check scripts tests`: passed.
- `git diff --cached --check`: passed.

The final complete-run synthetic checks include Parquet predicate filtering of the
reserved period before reading targets; malformed reserved outcomes never enter
training/validation checks or exports. These tests verify implementation isolation,
not real historical publication evidence. PNG and SVG figures were visually inspected.
Remote CI and human PR review are separate from these local checks.
