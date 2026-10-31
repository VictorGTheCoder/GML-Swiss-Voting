"""Collect a limited, timestamped ESPOP reuse audit; never redistribute raw files.

Usage: python -m scripts.espop.collect_reuse --raw-dir data/raw/espop_reuse/run1
The destination must not exist. Run audit_reuse on this directory afterwards.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

YEARS = ["1981", "1990", "2000", "2009", "2010", "2011"]
RTS_BASE = "https://rtsinfo-data.s3.eu-central-1.amazonaws.com/vt/2026/demographie-naissance/build/"
BALANCE_URL = "https://www.pxweb.bfs.admin.ch/api/v1/fr/px-x-0102020000_201/px-x-0102020000_201.px"
STATPOP_URL = "https://www.pxweb.bfs.admin.ch/api/v1/fr/px-x-0102010000_101/px-x-0102010000_101.px"
REGISTER = "https://www.agvchapp.bfs.admin.ch/api/communes/"
SAMPLE = {"1", "261", "1630", "1631", "1632", "2275", "4505", "4670", "4695", "5002", "5192", "5586"}
SNAPSHOTS = ["2025-04-06", "2026-01-01", "1980-12-02", "1990-12-04", "2000-12-05",
             "1989-12-31", "1990-01-01", "2010-12-31", "2011-01-01", "1979-12-31", "1980-01-01"]


def collect(raw_dir: Path) -> None:
    """Archive every response and request with its own actual retrieval time."""
    raw_dir.mkdir(parents=True, exist_ok=False)
    sources: list[dict] = []
    manifest = {"purpose": "issue #67; isolated feasibility audit", "sources": sources}
    session = requests.Session()

    def fetch(name, url, geography, population, reuse, query=None, params=None):
        response = session.request("POST" if query else "GET", url, json=query,
                                   params=params, timeout=120)
        response.raise_for_status()
        (raw_dir / name).write_bytes(response.content)
        sources.append({
            "file": name, "url": response.url, "method": "POST" if query else "GET",
            "query": query, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(response.content).hexdigest(), "bytes": len(response.content),
            "http_last_modified": response.headers.get("Last-Modified"),
            "http_etag": response.headers.get("ETag"), "territorial_reference": geography,
            "population_definition": population, "reuse": reuse,
            "historical_availability": "not_proven_by_current_download",
        })
        (raw_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        print(name, flush=True)
        return response

    rts_reuse = "Specific CSV redistribution license not established; local research only; see docs/datasets/espop/reuse_conditions.md"
    ofs_reuse = "OFS attribution required; see docs/datasets/espop/reuse_conditions.md; raw files kept outside Git"
    for stem, population in [
        ("proportion_population_etrangere_etat_actuel", "Annual ESPOP/STATPOP permanent residents; total and foreign; 1981-2024"),
        ("proportion_population_etrangere_historique", "Census resident population; harmonized counts; not annual ESPOP"),
        ("population_classes_age_historique", "Census ages 0-19/20-64/65+; not annual observations"),
    ]:
        fetch(f"rts_{stem}.csv", RTS_BASE + f"clean_data/{stem}.csv", "RTS declared 2026 communes; not certified by matching codes", population, rts_reuse)
    fetch("rts_index.html", RTS_BASE + "index.html", "RTS 2026", "Application credits/license inspection", rts_reuse)
    fetch("census.xlsx", "https://dam-api.bfs.admin.ch/hub/api/dam/assets/32067221/appendix",
          "Historical census territories, each census date", "Census resident population, not the ESPOP permanent resident definition", ofs_reuse)
    fetch("mutations.csv", REGISTER + "mutations", "1960-01-01 through 2026-01-01; exchanges included", "Administrative register; no demographic allocation weights", ofs_reuse,
          params={"includeTerritoryExchange": "true", "startPeriod": "01-01-1960", "endPeriod": "01-01-2026"})
    for day in SNAPSHOTS:
        fetch(f"snapshot_{day}.csv", REGISTER + "snapshot", day, "Administrative register; commune Level=3", ofs_reuse,
              params={"date": datetime.fromisoformat(day).strftime("%d-%m-%Y"), "useBfsCode": "true"})

    meta = fetch("balance_metadata.json", BALANCE_URL, "Cube declares 2025-04-06", "ESPOP to 2010, STATPOP from 2011; 31 December stocks", ofs_reuse).json()
    variables = meta["variables"]
    places = variables[1]
    communes = [v for v, label in zip(places["values"], places["valueTexts"]) if label.startswith("......")]

    def px_query(variables, selections):
        return {"query": [{"code": var["code"], "selection": {"filter": "item", "values": selected}}
                          for var, selected in zip(variables, selections)], "response": {"format": "csv"}}

    fetch("balance.csv", BALANCE_URL, "2025-04-06 plus three unresolved legacy codes", "Permanent residents at 31 December; total/Swiss/foreign; sex total", ofs_reuse,
          query=px_query(variables, [YEARS, communes, ["0", "1", "2"], ["0"], ["16"]]))
    import pandas as pd
    rts = pd.read_csv(raw_dir / "rts_proportion_population_etrangere_etat_actuel.csv", dtype={"Code": str})
    zero_codes = set(rts.loc[rts.Population_totale.eq(0), "Code"]) | SAMPLE
    selected = [v for v, label in zip(places["values"], places["valueTexts"])
                if label.startswith("......") and label[6:10].lstrip("0") in zero_codes]
    fetch("balance_anomalies.csv", BALANCE_URL, "2025-04-06 plus legacy codes", "Permanent residents at 31 December; annually 1981-2024; anomaly/sample communes", ofs_reuse,
          query=px_query(variables, [[str(y) for y in range(1981, 2025)], selected, ["0", "1", "2"], ["0"], ["16"]]))

    meta = fetch("statpop_metadata.json", STATPOP_URL, "Read cube notes; harmonization audited against snapshots", "Permanent residents, including change from ESPOP at 2010", ofs_reuse).json()
    variables = meta["variables"]
    print([(v["code"], v["valueTexts"][:3]) for v in variables], flush=True)
    selections = []
    for var in variables:
        code = var["code"]
        if code == "Jahr":
            selected = ["2010", "2011"]
        elif "Gemeinde" in code:
            selected = [v for v, label in zip(var["values"], var["valueTexts"]) if label.startswith("......")]
        elif code == "Bevölkerungstyp":
            selected = ["1"]
        elif code == "Staatsangehörigkeit (Kategorie)":
            selected = var["values"]
        else:
            selected = ["-99999"]
        selections.append(selected)
    fetch("statpop.csv", STATPOP_URL, "Cube current territory; inspect metadata, no inferred historical availability", "Permanent residents; 31 December; nationality; sex/age total", ofs_reuse,
          query=px_query(variables, selections))
    revision = "cbee3824065e206120aa06d4f9a0b083ef676e8e"
    for path, name in [("data/input/bev_gem.csv", "zurich.csv"), ("analyse/04_data_bev_gem.R", "zurich_source.R"), ("LICENSE", "zurich_license.txt")]:
        fetch(name, f"https://raw.githubusercontent.com/awelZH/energy/{revision}/{path}", "OFS geography of pinned source; not assumed identical to 2026", "Population 31 December, total nationality/sex; see pinned R script", "Repository GPL-3.0; source OFS terms distinct; do not redistribute CSV")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    args = parser.parse_args()
    collect(args.raw_dir)


if __name__ == "__main__":
    main()
