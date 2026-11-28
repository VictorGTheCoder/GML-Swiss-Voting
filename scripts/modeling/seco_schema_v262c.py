"""V26.2c: inspect pinned unemployment archive schemas; quarantine only."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from scripts.modeling.seco_vintages_v262 import HOST, LIMIT, inspect_bytes


def verify_pinned(data, row):
    metadata = inspect_bytes(data, row["format"])
    if metadata["sha256"] != row["sha256"] or metadata["bytes"] != row["bytes"]:
        raise ValueError("Historical source changed")
    return metadata


def preview(data, fmt):
    """Bounded structural preview only; no extraction of model features."""
    if fmt == "csv":
        decoded = data.decode("utf-8-sig")
        dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=";,\t")
        rows = csv.reader(io.StringIO(decoded), dialect)
        from itertools import islice

        sample = list(islice(rows, 12))
        return {"delimiter": dialect.delimiter, "first_rows": [r[:16] for r in sample],
                "sample_widths": [len(r) for r in sample]}
    import pandas as pd

    with pd.ExcelFile(io.BytesIO(data), engine="xlrd" if fmt == "xls" else "openpyxl") as book:
        sheets = {}
        for sheet in book.sheet_names[:20]:
            frame = book.parse(sheet, header=None, nrows=12).iloc[:, :16]
            sheets[sheet] = frame.fillna("").astype(str).values.tolist()
        return {"sheet_names": book.sheet_names, "first_rows_by_sheet": sheets}


def acquire(row):
    req = Request(row["download"], headers={"User-Agent": "GML historical schema audit"})
    with urlopen(req, timeout=25) as response:
        if urlsplit(response.geturl()).hostname != HOST:
            raise ValueError("Unexpected final host")
        data = response.read(LIMIT + 1)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Preserve existing schema audit")
    prior = json.loads(args.audit.read_text(encoding="utf-8"))
    rows = []
    for row in prior["assets"]:
        result = {"id": row["id"], "format": row["format"], "sha256": row["sha256"]}
        try:
            data = acquire(row)
            verify_pinned(data, row)
            result.update(status="schema_preview_only", preview=preview(data, row["format"]))
        except (OSError, ValueError, csv.Error, ImportError) as exc:
            result.update(status="blocked", error=str(exc))
        rows.append(result)
    report = {"status": "quarantine_only", "assets": rows,
              "schema_preview_count": sum(r["status"] == "schema_preview_only" for r in rows),
              "training_rows_admitted": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("SECO_SCHEMA", json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
