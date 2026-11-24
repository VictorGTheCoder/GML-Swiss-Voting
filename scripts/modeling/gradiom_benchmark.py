"""Score Gradiom's published point forecasts against official OFS counts.

The public map embeds numeric 50th-quantile approvals and OFS IDs; colors
are not measurements. Compare only unchanged geographic units. Outcomes
are scoring inputs, never features. Raw third-party tables are not committed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

import numpy as np
import pandas as pd
import requests

from scripts.common.config import ROOT

ORIGIN = "https://www.gradiom.ch"
ARCHIVE = ORIGIN + "/en/swiss-popular-votes"
REGISTER = "https://www.agvchapp.bfs.admin.ch/api/communes"
OGD = "https://ogd-static.voteinfo-app.ch/v1/ogd/sd-t-17-02-{}-eidgAbstimmung.json"
DAYS = ("2024-11-24", "2025-02-09", "2025-09-28", "2025-11-30",
        "2026-03-08", "2026-06-14", "2026-09-27")
OBJECTS = {
    "2024-11-24": ("6730", "6740", "6750", "6760"),
    "2025-02-09": ("6770",),
    "2025-09-28": ("6780", "6790"),
    "2025-11-30": ("6800", "6810"),
    "2026-03-08": ("6821", "6822", "6830", "6840", "6850"),
    "2026-06-14": ("6860", "6870"),
    "2026-09-27": ("6880", "6890"),
}
V2_SCORES = ROOT / "reports/datasets/municipal_v2_20261123/comparison_by_object.csv"


def soup(raw):
    from bs4 import BeautifulSoup
    return BeautifulSoup(raw, "html.parser")


def parse_stamp(text):
    match = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", text)
    if not match:
        raise ValueError("Missing displayed date")
    return datetime.strptime(match.group(1), "%d %B %Y").replace(tzinfo=timezone.utc).date().isoformat()


def parse_map(raw, vote, day, level):
    """Validate visible object identity, map level, point quantile and chronology."""
    html = soup(raw)
    container = html.select_one("#map-container")
    if (container is None or container.get("data-vote") != vote
            or container.get("data-level") != level or container.get("data-quantile") != "50"):
        raise ValueError("Wrong map object, level or forecast quantile")
    links = [a["href"] for a in html.select("a[href]")]
    if not any(re.search(r"/swiss-popular-votes/" + day + r"$", link) for link in links):
        raise ValueError("Object date link not verified")
    h4 = [h.get_text(" ", strip=True) for h in html.find_all("h4")
          if "Results generated and predicted on" in h.get_text(" ", strip=True)]
    if len(h4) != 1:
        raise ValueError("Expected a unique generation stamp")
    generated = parse_stamp(h4[0])
    if generated >= day:
        raise ValueError("Forecast generation is not pre-vote")
    headings = [h.get_text(" ", strip=True) for h in html.find_all("h2")]
    if len(headings) < 2:
        raise ValueError("Missing object title")
    national = [float(m.group(1)) for node in html.select("div")
                if (m := re.fullmatch(r"Yes:\s*([\d.]+)\s*%", node.get_text(" ", strip=True)))]
    # Nested divs may repeat the same visible label.
    if len(set(national)) != 1 or not 0 <= national[0] <= 100:
        raise ValueError("No unambiguous national point forecast")
    vintage = None
    comments = []
    if level == "commune":
        from bs4 import Comment
        comments = [str(x)[:300] for x in container.find_all(string=lambda x: isinstance(x, Comment))]
        patterns = r"(?:communes?|gemeinden?|municipalities)\s*(?:au\s+|am\s+|as of\s+)?(\d{1,2}\.\d{1,2}\.\d{4}|\d{4}-\d{2}-\d{2})"
        matches = set(re.findall(patterns, "\n".join(comments), re.I))
        if len(matches) == 1:
            raw_date = matches.pop()
            vintage = (date.fromisoformat(raw_date).isoformat() if "-" in raw_date else
                       datetime.strptime(raw_date, "%d.%m.%Y").replace(tzinfo=timezone.utc).date().isoformat())
        elif len(matches) > 1:
            raise ValueError("Conflicting municipality geometry comments")
    records, sources = {}, {}
    for tag in container.select("[data-approval]"):
        key = re.fullmatch(re.escape(level) + r"-(\d+)", str(tag.get("id", "")))
        if key is None:
            raise ValueError("Unexpected map unit ID")
        unit = int(key.group(1))
        val = tag["data-approval"]
        if not re.fullmatch(r"\d+(?:\.\d+)?", val):
            raise ValueError("Non-numeric displayed approval")
        p = float(val)
        if not 0 <= p <= 100:
            raise ValueError("Forecast outside probability range")
        source = str(tag.get("data-source", ""))
        if source.strip().casefold() not in ("", "forecast", "prediction"):
            # Do not interpret unreviewed source flags as predictions.
            raise ValueError(f"Unreviewed map source flag: {source!r}")
        row = (p, tag.get("data-name", ""))
        if unit in records and records[unit] != row:
            raise ValueError("Conflicting duplicate map unit")
        records[unit] = row
        sources[source] = sources.get(source, 0) + 1
    if not records:
        raise ValueError("No numerical forecasts")
    return {"vote": vote, "day": day, "generated": generated, "title": headings[1],
            "national": national[0], "geometry": vintage, "records": records, "sources": sources,
            "geometry_comments": comments}


def observed_share(record):
    """Use exact counts, only when the geographic unit is fully counted."""
    if record.get("gebietAusgezaehlt") is not True:
        return None
    yes, no = record.get("jaStimmenAbsolut"), record.get("neinStimmenAbsolut")
    if (not isinstance(yes, (int, float)) or not isinstance(no, (int, float))
            or yes < 0 or no < 0 or yes + no <= 0):
        return None
    percent = 100 * yes / (yes + no)
    published = record.get("jaStimmenInProzent")
    if isinstance(published, (int, float)) and abs(percent - published) > 1e-5:
        raise ValueError("Official share and counts disagree")
    return percent


def official_vote(payload, day, vote):
    if payload["abstimmtag"] != day.replace("-", ""):
        raise ValueError("Wrong official voting date")
    selected = [v for v in payload["schweiz"]["vorlagen"] if str(v["vorlagenId"]) == vote]
    if len(selected) != 1 or selected[0]["vorlageBeendet"] is not True:
        raise ValueError("Official object missing or incomplete")
    v = selected[0]
    vintage = [s["spatial_date"] for s in payload["spatial_reference"] if s["spatial_unit"] == "voge"]
    if len(vintage) != 1:
        raise ValueError("Official geography is ambiguous")
    municipalities, cantons = {}, {}
    for c in v["kantone"]:
        cid = int(c["geoLevelnummer"])
        if cid in cantons:
            raise ValueError("Repeated canton")
        val = observed_share(c["resultat"])
        if val is not None:
            cantons[cid] = val
        for g in c["gemeinden"]:
            mid = int(g["geoLevelnummer"])
            if mid in municipalities:
                raise ValueError("Repeated municipality")
            municipalities[mid] = (observed_share(g["resultat"]), g["geoLevelname"], cid)
    return {"national": observed_share(v["resultat"]), "cantons": cantons,
            "municipalities": municipalities, "geometry": vintage[0],
            "provisional": bool(v.get("provisorisch")), "timestamp": payload.get("timestamp"),
            "title": v["vorlagenTitel"]}


def changed_codes(events, source_date, target_date):
    """Exclude both sides of every mutation in the interval, even retained IDs."""
    lo, hi = sorted((source_date, target_date))
    out = set()
    for event in events:
        stamp = datetime.strptime(event["MutationDate"], "%d.%m.%Y").replace(tzinfo=timezone.utc).date().isoformat()
        if lo < stamp <= hi:
            for key in ("InitialCode", "TerminalCode"):
                raw = event[key].strip()
                if raw.isdigit():
                    out.add(int(raw))
    return out


def errors(predicted, actual):
    err = np.asarray(predicted, float) - np.asarray(actual, float)
    if not len(err) or not np.isfinite(err).all():
        raise ValueError("No finite matched values")
    return {"mae_pp": float(np.abs(err).mean()),
            "bias_pp": float(err.mean()),
            "centered_mae_pp": float(np.abs(err - err.mean()).mean()),
            "rmse_pp": float(np.sqrt(np.square(err).mean())),
            "within4_share": float((np.abs(err) <= 4).mean())}


def date_bootstrap(detail, column):
    groups = [g[column].to_numpy(float) for _, g in detail.groupby("vote_date", sort=True)]
    rng = np.random.default_rng(20261124)
    estimates = [np.concatenate([groups[i] for i in rng.integers(len(groups), size=len(groups))]).mean()
                 for _ in range(3000)]
    return np.quantile(estimates, [.025, .975]).tolist()


class Collector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "GML-Research/1.0 (public aggregate forecast accuracy)"
        self.evidence = []
        self.snapshots = {}
        self.robots = RobotFileParser()
        r = self.session.get(ORIGIN + "/robots.txt", timeout=25)
        if r.status_code == 200:
            self.robots.parse(r.text.splitlines())
        elif r.status_code == 404:
            self.robots.parse([])
        else:
            raise ValueError(f"Cannot confirm robots policy: {r.status_code}")

    def get(self, url, params=None):
        if url.startswith(ORIGIN) and not self.robots.can_fetch("GML-Research", url):
            raise ValueError("Robots policy disallows collection")
        time.sleep(.25)
        r = self.session.get(url, params=params, timeout=40)
        r.raise_for_status()
        self.evidence.append({"url": r.url, "sha256": hashlib.sha256(r.content).hexdigest(),
                              "bytes": len(r.content), "retrieved_at": datetime.now(timezone.utc).isoformat(),
                              "last_modified": r.headers.get("Last-Modified")})
        return r.content

    def registry(self, vintage):
        if vintage not in self.snapshots:
            raw = self.get(REGISTER + "/snapshot", {"date": date.fromisoformat(vintage).strftime("%d-%m-%Y"),
                                                       "useBfsCode": "true"})
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
            ids = {int(r["BfsCode"]) for r in rows if r["Level"] == "3"}
            if not 2000 <= len(ids) <= 2300:
                raise ValueError(f"Unexpected commune registry {vintage}: {len(ids)}")
            self.snapshots[vintage] = ids
        return self.snapshots[vintage]

    def mutations(self, lo, hi):
        raw = self.get(REGISTER + "/mutations", {
            "includeTerritoryExchange": "true",
            "startPeriod": date.fromisoformat(lo).strftime("%d-%m-%Y"),
            "endPeriod": date.fromisoformat(hi).strftime("%d-%m-%Y"),
            "useBfsCode": "true",
        })
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        if rows and not {"MutationDate", "InitialCode", "TerminalCode"}.issubset(rows[0]):
            raise ValueError("Unexpected mutation schema")
        return rows


def run(output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Do not overwrite evidence")
    output.mkdir(parents=True, exist_ok=True)
    c = Collector()
    registry = soup(c.get(ARCHIVE))
    links = [a["href"] for a in registry.select("a[href]")]
    for day in DAYS:
        if not any(x.endswith("/swiss-popular-votes/" + day) for x in links):
            raise ValueError("Archive date missing")
    rows, paired_rows, incidents, audit = [], [], [], []
    all_mutations = c.mutations("2024-01-01", "2026-09-27")
    for day in DAYS:
        # Date-limited archive only. Never request the forthcoming vote.
        day_page = soup(c.get(ARCHIVE + "/" + day))
        page_ids = {m.group(1) for a in day_page.select("a[href]")
                    if (m := re.search(r"/swiss-popular-votes/(\d+)/canton$", a["href"]))}
        if page_ids != set(OBJECTS[day]):
            raise ValueError(f"Unexpected date roster {day}: {page_ids}")
        official = json.loads(c.get(OGD.format(day.replace("-", ""))))
        for vote in OBJECTS[day]:
            try:
                comm = parse_map(c.get(ARCHIVE + "/" + vote + "/commune"), vote, day, "commune")
                cant = parse_map(c.get(ARCHIVE + "/" + vote + "/canton"), vote, day, "canton")
                actual = official_vote(official, day, vote)
                if (comm["generated"] != cant["generated"] or comm["national"] != cant["national"]
                        or comm["title"] != cant["title"]):
                    raise ValueError("Map forecasts disagree on national identity")
                src, dst = comm["geometry"], actual["geometry"]
                pred = comm["records"]
                source_basis = "SVG vintage comment"
                if src is None:
                    # Require an exact official code roster rather than guessing from date.
                    # Conservatively exclude every 2024--2026 changed code because a
                    # roster alone cannot date unchanged-ID territory exchanges.
                    candidates = [stamp for stamp in ("2024-01-01", "2025-01-01", "2026-01-01")
                                  if stamp <= day and set(pred) == c.registry(stamp)]
                    if not candidates:
                        raise ValueError("No explicit map vintage or exact official roster: "
                                         + repr(comm["geometry_comments"]))
                    src = candidates[0]
                    source_basis = "exact register roster only; exclude all 2024--2026 mutations"
                if not "2024-01-01" <= min(src, dst) <= max(src, dst) <= "2026-09-27":
                    raise ValueError("Geography outside reviewed mutation range")
                source_ids, target_ids = c.registry(src), c.registry(dst)
                if not set(pred).issubset(source_ids):
                    raise ValueError("Map ID outside official geometry roster")
                obs = {k: v for k, v in actual["municipalities"].items() if k in target_ids and v[0] is not None}
                affected = (changed_codes(all_mutations, "2024-01-01", "2026-09-27")
                            if comm["geometry"] is None else changed_codes(all_mutations, src, dst))
                common = sorted((set(pred) & set(obs)) - affected)
                if len(common) < .95 * len(obs):
                    raise ValueError("Less than 95% of official scored communes matched")
                ccommon = sorted(set(cant["records"]) & set(actual["cantons"]))
                if len(ccommon) != 26 or actual["national"] is None:
                    raise ValueError("Missing national or canton outcome")
                p = [pred[k][0] for k in common]
                y = [obs[k][0] for k in common]
                cm = errors([cant["records"][k][0] for k in ccommon], [actual["cantons"][k] for k in ccommon])
                m = errors(p, y)
                row = {"vote_id": vote, "vote_date": day, "generated": comm["generated"],
                       "lead_days": (date.fromisoformat(day) - date.fromisoformat(comm["generated"])).days,
                       "title": comm["title"], "municipal_forecasts": len(pred),
                       "official_scored_communes": len(obs), "matched_communes": len(common),
                       "coverage": len(common) / len(obs), "source_geometry": src, "official_geometry": dst,
                       "source_geometry_basis": source_basis,
                       "provisional": actual["provisional"],
                       "national_prediction_pp": comm["national"], "national_actual_pp": actual["national"],
                       "national_mae_pp": abs(comm["national"] - actual["national"]),
                       "canton_mae_pp": cm["mae_pp"], **m}
                rows.append(row)
                audit.append({"vote_id": vote, "vote_date": day, "official_timestamp": actual["timestamp"],
                              "official_title": actual["title"], "excluded_changed": sorted((set(pred) & set(obs)) & affected),
                              "forecast_only": sorted(set(pred)-set(obs)),
                              "observed_only": sorted(set(obs)-set(pred)),
                              "map_flags": comm["sources"], "geometry_comments": comm["geometry_comments"]})
                # Retain research-only matched rows in short-lived artifact.
                paired_rows.extend({"vote_id": vote, "vote_date": day, "municipality_id": str(k).zfill(4),
                                    "gradiom_prediction": pred[k][0]/100, "official_yes_share": obs[k][0]/100,
                                    "canton_id": obs[k][2]} for k in common)
                print("OBJECT", json.dumps(row, ensure_ascii=False), flush=True)
            except (requests.RequestException, ValueError, KeyError, TypeError) as e:
                incidents.append({"vote_id": vote, "vote_date": day, "reason": str(e)})
                print("REJECT", vote, str(e), flush=True)
    if not rows:
        raise ValueError("No usable archived object")
    detail = pd.DataFrame(rows)
    detail.to_csv(output / "object_metrics.csv", index=False)
    pd.DataFrame(paired_rows).to_parquet(output / "matched_rows.parquet", index=False)
    (output / "coverage_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False))
    (output / "source_manifest.json").write_text(json.dumps(c.evidence, indent=2, ensure_ascii=False))
    comparison = pd.read_csv(V2_SCORES, dtype={"vote_id": str})[["vote_id", "mae_pp", "n_communes"]]
    matched = detail.merge(comparison, on="vote_id", suffixes=("_gradiom", "_v2"), validate="one_to_one")
    matched.to_csv(output / "indicative_v2_object_comparison.csv", index=False)
    summary = {"status": "complete" if len(detail) == 18 else "partial",
               "expected_objects": 18, "objects": len(detail), "dates": int(detail.vote_date.nunique()),
               "rows": int(detail.matched_communes.sum()),
               "mean_coverage": float(detail.coverage.mean()),
               "provisional_objects": int(detail.provisional.sum()),
               "all": {k: float(detail[k].mean()) for k in ("mae_pp", "centered_mae_pp", "national_mae_pp",
                                                          "canton_mae_pp", "bias_pp", "rmse_pp")},
               "mae_interval_descriptive": date_bootstrap(detail, "mae_pp"),
               "overlap_v2": {"objects": len(matched), "gradiom_mae_pp": float(matched.mae_pp_gradiom.mean()),
                              "v2_mae_pp_original_population": float(matched.mae_pp_v2.mean()),
                              "warning": "same objects, not yet same municipalities"},
               "incidents": incidents, "historical_generation_stamp_verified": True,
               "matched_rows_sha256": hashlib.sha256((output / "matched_rows.parquet").read_bytes()).hexdigest(),
               "independent_historical_snapshot_verified": False}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    print("SUMMARY", json.dumps(summary, ensure_ascii=False, allow_nan=False), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    run(a.output)


if __name__ == "__main__":
    main()
