"""V28.1: descriptive source-timing audit of frozen development scores, no fit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FILES = {
    "srg": "data/external/polls/srg_gfs_polls.csv",
    "pairs": "data/external/polls_v81/srg_missing_two_waves.csv",
    "retrospective": "data/external/polls_v81/leewas_latest_2016_2022.csv",
    "tamedia_candidate": "data/external/polls_v132/candidates.csv",
    "expectation": "data/external/expectations_v10/reviewed.csv",
    "media": "data/external/media_v10/reviewed.csv",
}
METRICS = ["mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp"]
KEYS = ["vote_key", "vote_date"]
REF = 7.229527497606818
BEST = 6.950427808889042


def bucket(age):
    if pd.isna(age):
        return "absent_or_undated"
    if age <= 0:
        raise ValueError("Publication not strictly before voting date")
    return "0-14" if age <= 14 else "15-30" if age <= 30 else ">30"


def latest(source, roster, publication):
    """Retain latest declared calendar publication, not fieldwork date."""
    s = source.copy()
    if "vote_date" in s:
        if s.merge(roster, on=KEYS, how="inner").shape[0] != len(s):
            raise ValueError("Source key/date outside pinned population")
    else:
        s = s.merge(roster, on="vote_key", how="left", validate="many_to_one")
    if s.vote_date.isna().any():
        raise ValueError("Unknown object")
    day = pd.to_datetime(s.vote_date, format="%Y-%m-%d")
    # Dates refer to local publication calendar day, not UTC conversion.
    pub = pd.to_datetime(s[publication].str.slice(0, 10), format="%Y-%m-%d")
    s["age"] = (day - pub).dt.days
    if s.age.dropna().le(0).any():
        raise ValueError("Non-ex-ante publication")
    return s.dropna(subset=["age"]).groupby("vote_key").age.min()


def paired_interval(group):
    """Resample dates jointly; macro-object weighting, descriptive only."""
    if group.vote_date.nunique() < 2:
        return None
    by_day = group.groupby("vote_date").gain_national.agg(["sum", "size"])
    rng = np.random.default_rng(281)
    ix = rng.integers(0, len(by_day), size=(4000, len(by_day)))
    gains = by_day["sum"].to_numpy()[ix].sum(axis=1)
    counts = by_day["size"].to_numpy()[ix].sum(axis=1)
    return np.quantile(gains / counts, [.025, .975]).tolist()


def audit(sources, detail):
    base = detail[detail.variant.eq("reference")].copy()
    best = detail[detail.variant.eq("scaled_squared")].copy()
    for frame, score in [(base, REF), (best, BEST)]:
        if len(frame) != 66 or frame.vote_date.nunique() != 23:
            raise ValueError("Wrong frozen population")
        if not frame.vote_date.between("2016-01-01", "2022-12-31").all():
            raise ValueError("Outside development")
        if not np.isclose(frame.mae_pp.mean(), score, atol=2e-6, rtol=0):
            raise ValueError("Frozen score mismatch")
        if not np.isfinite(frame[METRICS].to_numpy()).all():
            raise ValueError("Invalid frozen score")
    base = base.rename(columns={"vote_id": "vote_key"})
    best = best.rename(columns={"vote_id": "vote_key"})
    roster = best[KEYS].copy()
    if roster.vote_key.duplicated().any():
        raise ValueError("Duplicate object")
    out = best[KEYS + METRICS + ["fold"]].merge(
        base[KEYS + METRICS], on=KEYS, validate="one_to_one", suffixes=("", "_reference")
    )
    if len(out) != 66:
        raise ValueError("Unmatched frozen scores")
    out["gain_national"] = out.national_mae_pp_reference - out.national_mae_pp

    srg = sources["srg"]
    pairs = sources["pairs"]
    retrospect = sources["retrospective"]
    if set(retrospect.vote_key) != set(roster.vote_key) or retrospect.vote_key.duplicated().any():
        raise ValueError("Retrospective roster mismatch")
    srg_age = pd.concat([
        latest(srg, roster, "published_at"),
        latest(pairs, roster, "last_published_date"),
    ]).groupby(level=0).min()
    expectation = sources["expectation"]
    join = KEYS + ["wave", "source_url"]
    checked = expectation.merge(
        srg[join + ["published_at"]], on=join, validate="one_to_one", how="left"
    )
    if checked.published_at.isna().any():
        raise ValueError("Unmatched expectation publication")
    ages = {
        "srg_declared": srg_age,
        "expectation_declared": latest(checked, roster, "published_at"),
        "media_declared": latest(sources["media"], roster, "published_at"),
        "tamedia_candidate": latest(
            sources["tamedia_candidate"], roster, "stated_release_date"
        ),
    }
    summary = []
    for signal, values in ages.items():
        out[signal + "_days"] = out.vote_key.map(values)
        out[signal + "_bucket"] = out[signal + "_days"].map(bucket)
        for label, g in out.groupby(signal + "_bucket"):
            summary.append({
                "signal": signal, "bucket": label, "objects": len(g),
                "dates": g.vote_date.nunique(),
                **{m: float(g[m].mean()) for m in METRICS},
                "national_reference": float(g.national_mae_pp_reference.mean()),
                "national_paired_gain": float(g.gain_national.mean()),
                "paired_date_interval": paired_interval(g),
            })
    return out, summary


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = {
        k: pd.read_csv(args.root / v, dtype=str) for k, v in FILES.items()
    }
    detail = pd.read_csv(args.frozen, dtype={"vote_id": str, "vote_date": str})
    out, summary = audit(sources, detail)
    args.output.mkdir(parents=True, exist_ok=False)
    out.to_csv(args.output / "object_audit.csv", index=False)
    manifest = {
        "status": "descriptive_only", "no_fit": True, "new_admitted_inputs": 0,
        "objects": 66, "dates": 23, "reference": REF, "best": BEST,
        "frozen_sha256": sha(args.frozen),
        "source_sha256": {k: sha(args.root / v) for k, v in FILES.items()},
        "expectation_rows": len(sources["expectation"]),
        "srg_chart_later_updates": int(
            sources["srg"].chart_updated_on_or_after_vote_date.str.lower().eq("true").sum()
        ),
        "srg_historical_version_verified": int(
            sources["srg"].historical_version_verified.str.lower().eq("true").sum()
        ),
        "summary": summary,
        "caveat": "Declared date is not historical vintage certification; candidate not admitted."
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False))
    print("SIGNAL_AUDIT", json.dumps(manifest, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
