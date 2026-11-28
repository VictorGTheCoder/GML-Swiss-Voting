"""V26.2e: inspect only the published month of pinned SECO archives.

Outputs are quarantine diagnostics, not model inputs. Raw status/precision
codes are preserved until the source-specific metadata is certified.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
from pathlib import Path

from scripts.modeling.seco_schema_v262c import acquire, verify_pinned
from scripts.modeling.seco_vintages_v262 import validate_catalog

CANTONS = dict(enumerate((
    "Zürich", "Bern", "Luzern", "Uri", "Schwyz", "Obwalden", "Nidwalden",
    "Glarus", "Zug", "Freiburg", "Solothurn", "Basel-Stadt", "Basel-Landschaft",
    "Schaffhausen", "Appenzell Ausserrhoden", "Appenzell Innerrhoden",
    "St. Gallen", "Graubünden", "Aargau", "Thurgau", "Tessin", "Waadt",
    "Wallis", "Neuenburg", "Genf", "Jura",
), 1))
KEYS = {"CH"} | {str(k) for k in CANTONS}
MONTHS = ("Jan.", "Febr.", "März", "April", "Mai", "Juni", "Juli",
          "Aug.", "Sept.", "Okt.", "Nov.", "Dez.")
FIELDS = ["REGION", "CANTON", "PERIOD", "VALUE", "STATUS", "OBS_COEF"]


def rate(value):
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 100:
        raise ValueError("Rate outside percentage bounds")
    return result


def add(result, key, record):
    if key in result:
        raise ValueError(f"Duplicate geographic key {key}")
    result[key] = record


def complete(result):
    if set(result) != KEYS:
        raise ValueError(f"Missing geographic keys: {sorted(KEYS - set(result))}")
    return result


def csv_month(data, period):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";")
    if reader.fieldnames != FIELDS:
        raise ValueError("Unrecognized CSV schema")
    result = {}
    for row in reader:
        if row["PERIOD"] != period:
            continue
        canton, region = row["CANTON"], row["REGION"]
        if canton == "Total" and region != "Total":
            continue  # regional subtotals
        key = "CH" if canton == region == "Total" else canton
        if key not in KEYS:
            raise ValueError(f"Unexpected canton {key}")
        add(result, key, {"rate_pp": rate(row["VALUE"]),
                          "status_raw": row["STATUS"],
                          "coefficient_raw": row["OBS_COEF"],
                          "region_raw": region})
    return complete(result)


def label(value):
    return re.sub(r"\s+\d+\)\s*$", "", str(value).strip())


def excel_month(frame, period):
    month = int(period[-2:])
    rows = frame.fillna("").values.tolist()
    names = {v: str(k) for k, v in CANTONS.items()}
    names["Total"] = "CH"
    # Exact official historical spellings, not fuzzy matching.
    names.update({"Appenzell A.Rh.": "15", "Appenzell I.Rh.": "16",
                  "Appenzell A. Rh.": "15", "Appenzell I. Rh.": "16"})
    headers = [(i, j) for i, row in enumerate(rows[:12])
               for j, value in enumerate(row)
               if label(value) in {period, MONTHS[month - 1]}]
    if len(headers) != 1:
        raise ValueError("Missing or ambiguous month header")
    i, j = headers[0]
    units = [str(value) for row in rows[:i] for value in row
             if "Quoten in %" in str(value)]
    if len(units) != 1:
        raise ValueError("Missing percentage unit")
    result = {}
    appenzell_labels = []
    for row in rows[i + 1:]:
        name = label(row[0])
        if name.startswith("Appenzell"):
            appenzell_labels.append(name)
        if name in names:
            add(result, names[name], {"rate_pp": rate(row[j]),
                                     "source_label": name})
    if not KEYS <= set(result):
        raise ValueError(f"Missing geographic keys: {sorted(KEYS - set(result))}; "
                         f"Appenzell labels: {appenzell_labels!r}")
    return complete(result), units[0]


def extract(data, asset):
    period = asset["end"][:7]
    if asset["format"] == "csv":
        return csv_month(data, period), None
    import pandas as pd

    engine = "xlrd" if asset["format"] == "xls" else "openpyxl"
    frame = pd.read_excel(io.BytesIO(data), engine=engine,
                          sheet_name=period[:4], header=None)
    return excel_month(frame, period)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only-asset", type=int, action="append", default=[])
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Preserve prior audit")
    assets = [row for path in args.audit
              for row in json.loads(path.read_text(encoding="utf-8"))["assets"]]
    validate_catalog(assets)
    if args.only_asset:
        selected = set(args.only_asset)
        if not selected <= {asset["id"] for asset in assets}:
            raise ValueError("Unknown selected asset")
        assets = [asset for asset in assets if asset["id"] in selected]
    results = []
    for asset in assets:
        entry = {k: asset[k] for k in ("id", "end", "published", "sha256")}
        try:
            if asset["status"] != "format_checked_not_admitted":
                raise ValueError("Unverified source")
            data = acquire(asset)
            verify_pinned(data, asset)
            records, unit = extract(data, asset)
            entry.update(status="extracted_quarantine", records=records, unit=unit)
        except (OSError, ValueError, KeyError, IndexError, csv.Error, ImportError) as exc:
            entry.update(status="blocked", error=str(exc))
        results.append(entry)
    report = {"status": "quarantine_only", "assets": results,
              "complete_archives": sum(r["status"] == "extracted_quarantine" for r in results),
              "training_rows_admitted": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    summary = {**report, "assets": [{k: v for k, v in r.items() if k != "records"}
                                    | {"records_count": len(r.get("records", {}))}
                                    for r in results]}
    print("SECO_EXTRACT", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
