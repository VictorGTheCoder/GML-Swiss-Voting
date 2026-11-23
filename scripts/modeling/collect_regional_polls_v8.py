"""Acquire regional SRG poll margins from the same reviewed national charts.

Uses exact vote_key/date/wave/chart mappings in the existing national collection.
No election results are an input. The current Infogram editions are not
certified historical snapshots. Keep raw source cells and hashes, and abstain
on any ambiguous row or changed national margin.
"""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.collect_poll_features import (
    FIELDS,
    NATIONAL_BARE_DATE_CHARTS,
    date_de,
    extract_national_rows,
    fetch,
    find_tables,
    label_field,
    norm,
    sha,
)

REGIONS = {
    "dch": "de", "deutschschweiz": "de", "deutschsprachigeschweiz": "de",
    "fch": "fr", "westschweiz": "fr", "franzosischsprachigeschweiz": "fr",
    "romandie": "fr", "ich": "it", "tessin": "it",
    "italienischsprachigeschweiz": "it",
}


def region_label(label):
    # Remove explicitly recognized dates; never infer a region from its order.
    raw = str(label)
    from scripts.modeling.collect_poll_features import DATE_RE
    raw = re.sub(DATE_RE, "", raw, flags=re.I)
    raw = re.sub(r"\b\d{1,2}\.\d{1,2}\.20\d{2}\b", "", raw)
    return REGIONS.get(norm(raw))


def candidate_rows(tables, midpoint, wave):
    rows = []
    for path, sheet in tables:
        header = sheet[0]
        mapping = {i: label_field(v) for i, v in enumerate(header) if label_field(v)}
        if set(mapping.values()) != set(FIELDS):
            continue
        for row in sheet[1:]:
            if not row:
                continue
            region = region_label(row[0])
            when = date_de(str(row[0]))
            if region is None or (when != midpoint and not (when is None and wave == 1)):
                continue
            try:
                values = {name: float(str(row[i]).replace(",", ".")) for i, name in mapping.items()}
            except (ValueError, TypeError, IndexError):
                continue
            if not all(0 <= v <= 100 for v in values.values()) or abs(sum(values.values()) - 100) > 1.01:
                continue
            rows.append({"region": region, "path": path, "header": header, "row": row,
                         "date_label": when, **values})
    return rows


def collect(record):
    url = record["chart_url"]
    try:
        if not url.startswith("https://e.infogram.com/"):
            raise ValueError("Only reviewed Infogram charts are supported")
        body, _ = fetch(url)
        raw = body.decode("utf-8")
        payload, _ = json.JSONDecoder().raw_decode(raw.split("window.infographicData=", 1)[1])
        tables = list(find_tables(payload))
        national = extract_national_rows(
            tables, "infogram", allow_bare_dates=url in NATIONAL_BARE_DATE_CHARTS
        )
        matching = [r for r in national if r["survey_midpoint"] == record["survey_midpoint"]]
        if not matching and len(national) == 1 and national[0]["survey_midpoint"] is None:
            matching = national
        if len(matching) != 1 or any(abs(matching[0][f] - float(record[f])) > 1e-8 for f in FIELDS):
            raise ValueError("National chart no longer reproduces the reviewed wave")
        rows = candidate_rows(tables, record["survey_midpoint"], int(record["wave"]))
        accepted = []
        for reg in ("de", "fr", "it"):
            candidates = [row for row in rows if row["region"] == reg]
            values = {tuple(c[f] for f in FIELDS) for c in candidates}
            if len(values) == 1:
                accepted.append(candidates[0])
        if len(accepted) != 3:
            # Compact inventory helps improve parsing, not a permission to guess.
            inventory = []
            for path, sheet in tables:
                if len(sheet) and isinstance(sheet[0], list):
                    mapping = [label_field(v) for v in sheet[0]]
                    if len(set(mapping) - {None}) == len(FIELDS):
                        inventory.append({"path": path, "header": sheet[0],
                                          "labels": [str(r[0]) for r in sheet[1:8] if r]})
            return {"record": record, "error": "Incomplete/ambiguous regional margins",
                    "inventory": inventory[:20]}
        return {"record": record, "rows": accepted,
                "chart_sha256": sha(body), "chart_created_at": payload.get("createdAt"),
                "chart_updated_at": payload.get("updatedAt")}
    except Exception as e:
        return {"record": record, "error": str(e)[:500]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = ROOT / "data/external/polls/srg_gfs_polls.csv"
    source = pd.read_csv(path, dtype={"vote_key": str})
    source = source[source.vote_date.between("2021-01-01", "2022-12-31")]
    fields = ["vote_key", "vote_date", "wave", "survey_midpoint", "survey_start",
              "survey_end", "published_at", "source_url", "chart_url", "chart_title", *FIELDS]
    records = source[fields].to_dict("records")
    if len(records) != 48:
        raise ValueError("Expected all 24 historical objects and two waves")
    with ThreadPoolExecutor(max_workers=6) as pool:
        evidence = list(pool.map(collect, records))
    args.output.mkdir(parents=True, exist_ok=True)
    result = []
    for entry in evidence:
        if "rows" not in entry:
            continue
        record = entry["record"]
        for row in entry["rows"]:
            result.append({
                **{k: v for k, v in record.items() if k not in FIELDS},
                **{k: row[k] for k in ("region", *FIELDS)},
                "yes_total": row["yes_certain"] + row["yes_lean"],
                "no_total": row["no_certain"] + row["no_lean"],
                "chart_sha256": entry["chart_sha256"],
                "chart_updated_at": entry["chart_updated_at"],
                "historical_version_verified": False,
            })
    pd.DataFrame(result).to_csv(args.output / "regional_polls.csv", index=False)
    (args.output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REGIONAL_ROWS", json.dumps(result, ensure_ascii=False), flush=True)
    for e in evidence:
        if "error" in e:
            print("REJECT", e["record"]["vote_key"], e["record"]["wave"], e["error"],
                  json.dumps(e.get("inventory", []), ensure_ascii=False), flush=True)
    print("COVERAGE", len(result), "of 144 expected regional margins", flush=True)


if __name__ == "__main__":
    main()
