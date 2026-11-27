"""Scoring-only domain support audit of pinned historical object metrics."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts.modeling.stability_v251 import METRICS, NAMES, read_panel


def metadata(path, keys):
    rows = {}
    coverage = {}
    seen = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["vote_date"], row["vote_id"])
            tag = (row["variant"], key)
            if tag in seen or key not in keys or row["variant"] not in NAMES:
                raise ValueError("Invalid metadata key")
            seen.add(tag)
            value = (row["domain"], row["fold"])
            if key in rows and rows[key] != value:
                raise ValueError("Inconsistent domain or fold")
            rows[key] = value
            if row["variant"] == "v113_institution":
                flag = row["covered"].lower()
                if flag not in {"true", "false"}:
                    raise ValueError("Invalid coverage")
                coverage[key] = flag == "true"
    if set(rows) != keys or set(coverage) != keys or len(seen) != len(keys) * len(NAMES):
        raise ValueError("Incomplete metadata")
    return rows, coverage


def summarize(panel, rows, coverage):
    n = len(rows)
    result = {}
    for domain in sorted({v[0] for v in rows.values()}):
        keys = sorted(k for k, v in rows.items() if v[0] == domain)
        days = sorted({k[0] for k in keys})
        scores = {
            name: {m: math.fsum(p[k][m] for k in keys) / len(keys) for m in METRICS}
            for name, p in panel.items()
        }
        mae = scores["scaled_squared"]["mae_pp"]
        leave = []
        for day in days:
            keep = [k for k in keys if k[0] != day]
            if keep:
                leave.append(math.fsum(panel["scaled_squared"][k]["mae_pp"] for k in keep) / len(keep))
        folds = {rows[k][1] for k in keys}
        result[domain] = {
            "objects": len(keys), "dates": len(days),
            "dates_by_fold": {f: len({k[0] for k in keys if rows[k][1] == f}) for f in sorted(folds)},
            "document_covered_v113": sum(coverage[k] for k in keys),
            "scores": scores,
            "gain_vs_v81": scores["reference"]["mae_pp"] - mae,
            "global_mae_contribution": mae * len(keys) / n,
            "signed_excess_contribution_vs_4": (mae - 4.0) * len(keys) / n,
            "leave_date_mae_range": [min(leave), max(leave)] if leave else None,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    panel = read_panel(args.input)
    rows, coverage = metadata(args.input, set(panel[NAMES[0]]))
    result = summarize(panel, rows, coverage)
    payload = {"status": "descriptive_only", "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
               "objects": len(rows), "dates": len({k[0] for k in rows}), "domains": result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("DOMAIN_SUPPORT", json.dumps(payload, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
