"""V10.3: historical aggregate turnout and valid-ballot exposure.

Only strictly earlier voting dates are used to estimate eligible counts,
participation and valid-ballot rates. All current counts are scoring targets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.integration.build_modeling_dataset import clean_outcomes
from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.spatial_margins_v81 import contexts, joint_adjust, observation_system

SOURCE = ROOT / "data/processed/ofs-votes/votes_communes.parquet"
METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")
VARIANTS = ("reference", "eligible_only", "last_weights_only", "last_reanchor",
            "pooled_weights_only", "pooled_reanchor", "domain_reanchor")


def load_ballots():
    cols = ["municipality_id", "vote_id", "vote_key", "vote_date", "canton",
            "votes_yes", "votes_no", "eligible_voters", "ballots_cast",
            "is_special_unit", "is_tiebreak_question", "is_provisional",
            "flag_valid_gt_ballots", "flag_yes_no_gt_valid"]
    raw = pd.read_parquet(SOURCE, columns=cols,
                          filters=[("vote_date", ">=", pd.Timestamp("1990-01-01")),
                                   ("vote_date", "<", pd.Timestamp("2023-01-01"))])
    if raw.vote_date.ge("2023-01-01").any():
        raise ValueError("Comparison outcomes forbidden")
    clean, _ = clean_outcomes(raw)
    for name in ("municipality_id", "vote_id"):
        clean[name] = clean[name].astype(str)
    for name in ("votes_yes", "votes_no", "eligible_voters", "ballots_cast"):
        clean[name] = clean[name].astype(float)
    return clean


def history_weights(history, day, ids, proxy, domain):
    """Estimate relative exposure; use date means, not replicated date counts."""
    h = history.loc[history.vote_date.lt(day) &
                    history.vote_date.ge(day - pd.DateOffset(years=5))].copy()
    if h.empty:
        raise ValueError("No earlier turnout data")
    h["valid"] = h.votes_yes + h.votes_no
    h = h.loc[h.eligible_voters.gt(0) & h.ballots_cast.ge(h.valid) &
              h.ballots_cast.le(h.eligible_voters)]
    h["turnout"] = h.ballots_cast / h.eligible_voters
    h["valid_rate"] = h.valid / h.eligible_voters
    daily = h.groupby(["municipality_id", "vote_date"], as_index=False)[
        ["eligible_voters", "turnout", "valid_rate"]].mean()
    last = daily.sort_values("vote_date").drop_duplicates("municipality_id", keep="last").set_index("municipality_id")
    avg = daily.groupby("municipality_id")[["turnout", "valid_rate"]].mean()
    n = daily.groupby("municipality_id").size().reindex(ids).fillna(0).to_numpy(float)
    e = last.eligible_voters.reindex(ids).to_numpy(float)
    good = np.isfinite(e) & (e > 0)
    # Fallback population proxy scaled to match known eligible counts; no current ballots.
    ratio = np.sum(e[good]) / max(np.sum(proxy[good]), 1.)
    if not np.isfinite(ratio) or ratio <= 0:
        ratio = 1.
    e = np.where(good, e, proxy * ratio)
    weights, rates = {"eligible": e}, {}
    matching = h[h.domain.eq(domain)] if domain else h.iloc[:0]
    domain_daily = matching.groupby(["municipality_id", "vote_date"], as_index=False)[
        ["turnout", "valid_rate"]].mean()
    domain_avg = domain_daily.groupby("municipality_id")[["turnout", "valid_rate"]].mean()
    dn = domain_daily.groupby("municipality_id").size().reindex(ids).fillna(0).to_numpy(float)
    for name in ("turnout", "valid_rate"):
        overall = float(daily[name].mean())
        recent = last[name].reindex(ids).fillna(overall).to_numpy(float)
        mean = avg[name].reindex(ids).fillna(overall).to_numpy(float)
        pooled = (n * mean + 3 * overall) / (n + 3)
        cond = domain_avg[name].reindex(ids).fillna(overall).to_numpy(float)
        conditional = (dn * cond + 5 * pooled) / (dn + 5)
        rates[name] = {"last": recent, "pooled": pooled, "domain": conditional}
    for method, rate in rates["valid_rate"].items():
        weights[method] = e * rate
    if any(not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0
           for w in weights.values()):
        raise ValueError("Invalid historical exposure")
    return weights, rates, good, dn


def run(base, acquisition, fusion, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve earlier results")
    data, cases = contexts(base, acquisition, fusion)
    metadata = data[["vote_id", "object_domain_1"]].drop_duplicates()
    if metadata.vote_id.duplicated().any():
        raise ValueError("Object domain not unique")
    domains = metadata.set_index("vote_id").object_domain_1.fillna("").astype(str).to_dict()
    outcomes = load_ballots()
    outcomes["domain"] = outcomes.vote_id.map(domains).fillna("")
    by_vote = {k: g.set_index("municipality_id", verify_integrity=True)
               for k, g in outcomes.groupby("vote_id")}
    rows, canton_rows, predictions = [], [], []
    for vote, day, v, f, lm, um in cases:
        ids = v.municipality_id.to_numpy()
        w = v.weight.to_numpy(float)
        p = f.v8_reference.to_numpy(float)
        system = observation_system(w, v.language.to_numpy(), v.urban.to_numpy(), lm, um)
        q = joint_adjust(p, w, *system[:3], .1, True, system[3])
        weights, rates, known, dn = history_weights(outcomes, day, ids, w, domains.get(vote, ""))
        anchor = float(np.average(p, weights=w))
        forecasts = {"reference": (q, w), "eligible_only": (q, weights["eligible"])}
        for method in ("last", "pooled", "domain"):
            new_w = weights[method]
            if method != "domain":
                forecasts[method + "_weights_only"] = (q, new_w)
            a, z, b, i = observation_system(new_w, v.language.to_numpy(), v.urban.to_numpy(), lm, um)
            forecasts[method + "_reanchor"] = (joint_adjust(
                shift_to(p, new_w, anchor), new_w, a, z, b, .1, True, i), new_w)
        # Only here access current counts for scoring.
        observed = by_vote[vote].reindex(ids)
        y = v.yes_share.to_numpy(float)
        yes, no = observed.votes_yes.to_numpy(float), observed.votes_no.to_numpy(float)
        eligible = observed.eligible_voters.to_numpy(float)
        cast = observed.ballots_cast.to_numpy(float)
        valid = yes + no
        turnout_ok = np.isfinite(eligible + cast) & (eligible > 0) & (cast >= valid) & (cast <= eligible)
        actual_rate = np.divide(cast, eligible, out=np.full(len(y), np.nan), where=turnout_ok)
        actual_valid_rate = np.divide(valid, eligible, out=np.full(len(y), np.nan), where=turnout_ok)
        block = v[["vote_id", "municipality_id", "vote_date", "yes_share"]].copy()
        fold = "2016-18" if day.year <= 2018 else "2019-20" if day.year <= 2020 else "2021-22"
        for name in VARIANTS:
            pred, exposure = forecasts[name]
            m, c = multiscale(y, pred, exposure, yes, no, observed.canton.astype(str).to_numpy())
            # Common aggregation control isolates prediction changes from weights.
            common, _ = multiscale(y, pred, w, yes, no, observed.canton.astype(str).to_numpy())
            method = name.split("_")[0]
            method = method if method in rates["turnout"] else None
            turnout_mae = float(100 * np.nanmean(np.abs(rates["turnout"][method] - actual_rate))) if method else None
            valid_mae = float(100 * np.nanmean(np.abs(rates["valid_rate"][method] - actual_valid_rate))) if method else None
            rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                         "fold": fold, **m, "common_weight_national_mae_pp": common["national_mae_pp"],
                         "common_weight_canton_mae_pp": common["canton_mae_pp"],
                         "ballot_weight_tv_pp": float(50 * np.abs(exposure/exposure.sum()-valid/valid.sum()).sum()),
                         "turnout_mae_pp": turnout_mae, "valid_rate_mae_pp": valid_mae,
                         "turnout_score_rows": int(turnout_ok.sum()),
                         "eligible_coverage": float(known.mean()), "domain_coverage": float((dn > 0).mean())})
            canton_rows.extend({"variant": name, "vote_id": vote, **r} for r in c)
            block[name] = pred
            block[name + "_weight"] = exposure
        predictions.append(block)
    detail = pd.DataFrame(rows)
    summaries = []
    extra = ["common_weight_national_mae_pp", "common_weight_canton_mae_pp",
             "ballot_weight_tv_pp", "turnout_mae_pp", "valid_rate_mae_pp",
             "eligible_coverage", "domain_coverage"]
    for name, g in detail.groupby("variant", sort=False):
        if len(g) != 66 or g.vote_date.nunique() != 23:
            raise ValueError("Incomplete benchmark")
        summary = {"variant": name, "objects": len(g), **{m: float(g[m].mean()) for m in METRICS},
                   **{m: float(g[m].mean()) if g[m].notna().any() else None for m in extra},
                   "gain_interval": [0., 0.] if name == "reference" else paired_date_bootstrap(detail, "reference", name)}
        summaries.append(summary)
    if not np.isclose(summaries[0]["mae_pp"], REFERENCE, atol=.0002, rtol=0):
        raise ValueError("Reference mismatch")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    detail.groupby(["variant", "fold"])[list(METRICS) + extra].mean().to_csv(output / "fold_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    pd.DataFrame(summaries).to_csv(output / "summary.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    manifest = {"status": "complete", "strict_forecast_ready": False,
                "history": "1990-2022 source; trailing five years; strict prior dates",
                "source_sha256": sha(SOURCE), "prediction_sha256": sha(output / "predictions.parquet"),
                "summary": summaries}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False))
    print("SUMMARY", json.dumps(summaries, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "acquisition", "fusion", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    run(a.base, a.acquisition, a.fusion, a.output)


if __name__ == "__main__":
    main()
