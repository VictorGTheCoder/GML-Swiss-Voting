"""V28.3: metadata-only audit of the polls actually used by V8.1/V24.1."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

DIRECT = Path("data/external/polls/srg_gfs_polls.csv")
HISTORICAL = Path("data/external/polls_historical_v3/polls.csv")
REGIONAL = Path("data/external/polls_regional_v8/regional_polls.csv")
KEYS = ["vote_key", "vote_date", "wave"]
META = [*KEYS, "published_at", "survey_midpoint", "chart_url", "historical_version_verified"]
CUTOFF = "2023-01-01"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical(frame, roster):
    """Filter dates before joining; never use source vote-share columns."""
    dates = pd.to_datetime(frame.vote_date, format="%Y-%m-%d", errors="raise")
    if dates.isna().any():
        raise ValueError("Missing vote date")
    frame = frame.loc[dates.lt(CUTOFF)].copy()
    if frame.merge(roster, on=KEYS[:2], how="inner").shape[0] != len(frame):
        raise ValueError("Source key/date outside historical roster")
    frame["wave"] = pd.to_numeric(frame.wave, errors="raise")
    pub = pd.to_datetime(frame.published_at, utc=True, errors="raise")
    vote = pd.to_datetime(frame.vote_date, utc=True, errors="raise")
    if pub.isna().any() or (pub > vote - pd.Timedelta(days=1)).any():
        raise ValueError("Publication misses frozen cutoff")
    frame["published_at"] = pub
    return frame


def audit(national, margins, roster):
    """Count selected waves and certification; no vote shares, fit or targets."""
    n = historical(national, roster)
    if n.duplicated(KEYS).any():
        raise ValueError("Duplicate national wave")
    n["late"] = n["late"].fillna("").astype(str).str.lower().eq("true")
    n["verified"] = n.historical_version_verified.astype(str).str.lower().eq("true")
    selected = n.sort_values("wave").groupby("vote_key").tail(2)
    latest = selected.groupby("vote_key").tail(1)
    result = {
        "national_objects": int(selected.vote_key.nunique()),
        "national_selected_waves": len(selected),
        "national_source_objects": selected.groupby("source").vote_key.nunique().to_dict(),
        "national_objects_any_late_chart": int(selected.loc[selected.late, "vote_key"].nunique()),
        "national_objects_latest_late_chart": int(latest.late.sum()),
        "national_objects_all_waves_verified": int(selected.groupby("vote_key").verified.all().sum()),
        "national_selected_waves_verified": int(selected.verified.sum()),
        "structural_fallback_objects": len(roster) - int(selected.vote_key.nunique()),
    }
    for name, raw in margins.items():
        m = historical(raw, roster)
        if m.duplicated(KEYS + ["region"]).any():
            raise ValueError("Duplicate margin cell")
        if not m.groupby(KEYS).region.nunique().eq(3).all():
            raise ValueError("Incomplete margin wave")
        # The actual loaders require exact same wave metadata as DIRECT, not
        # the retrospective LeeWas table or the supplemental historical pairs.
        fields = ["published_at", "survey_midpoint", "chart_url"]
        joined = m.merge(
            n.loc[n.source.eq("direct"), KEYS + fields],
            on=KEYS, how="left", validate="many_to_one", suffixes=("", "_national"),
        )
        if any(not joined[c].eq(joined[c + "_national"]).all() for c in fields):
            raise ValueError("Margin/national identity mismatch")
        m["verified"] = m.historical_version_verified.astype(str).str.lower().eq("true")
        updated = pd.to_datetime(m.chart_updated_at, utc=True, errors="raise")
        m["late"] = updated.ge(pd.to_datetime(m.vote_date, utc=True))
        m = m.loc[m.wave.eq(m.groupby("vote_key").wave.transform("max"))]
        result[name] = {
            "objects": int(m.vote_key.nunique()),
            "selected_cells": len(m),
            "objects_latest_late_chart": int(m.loc[m.late, "vote_key"].nunique()),
            "objects_all_cells_verified": int(m.groupby("vote_key").verified.all().sum()),
        }
    return result


def run(frozen, acquisition, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve existing audit")
    # Only identities/variant are read from the existing frozen development artifact.
    detail = pd.read_csv(frozen, dtype=str, usecols=["vote_id", "vote_date", "variant"])
    roster = detail.loc[detail.variant.eq("scaled_squared"), ["vote_id", "vote_date"]]
    roster = roster.rename(columns={"vote_id": "vote_key"})
    if (len(roster) != 66 or roster.vote_date.nunique() != 23
            or roster.vote_key.duplicated().any()
            or not roster.vote_date.between("2016-01-01", "2022-12-31").all()):
        raise ValueError("Unexpected frozen development population")
    a = pd.read_csv(DIRECT, dtype=str, usecols=META + ["chart_updated_on_or_after_vote_date"])
    a = a.rename(columns={"chart_updated_on_or_after_vote_date": "late"}).assign(source="direct")
    b = pd.read_csv(HISTORICAL, dtype=str, usecols=META).assign(source="historical_v3", late="")
    settlement = acquisition / "settlement_polls.csv"
    manifest = json.loads((acquisition / "manifest.json").read_text())
    if digest(settlement) != manifest["hashes"]["settlement_polls.csv"]:
        raise ValueError("Settlement artifact hash mismatch")
    margins = {
        name: pd.read_csv(path, dtype=str, usecols=META + ["region", "chart_updated_at"])
        for name, path in [("language", REGIONAL), ("settlement", settlement)]
    }
    report = audit(pd.concat([a, b], ignore_index=True), margins, roster)
    if report["national_source_objects"] != {"direct": 24, "historical_v3": 24}:
        raise ValueError("Frozen national source coverage changed")
    report.update({
        "status": "metadata_only",
        "objects": 66,
        "dates": 23,
        "excluded_direct_future_rows": int(a.vote_date.ge(CUTOFF).sum()),
        "source_sha256": {str(p): digest(p) for p in [DIRECT, HISTORICAL, REGIONAL, settlement, frozen]},
        "no_fit": True,
        "new_admitted_inputs": 0,
    })
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print("AUDIT", json.dumps(report, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("frozen", "acquisition", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.frozen, args.acquisition, args.output)


if __name__ == "__main__":
    main()
