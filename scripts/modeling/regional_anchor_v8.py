"""Regional poll anchoring with national coherence and explicit hindsight oracles.

The real forecast adjustment receives only admissible pre-vote poll margins,
prior municipal outcomes, and the frozen national prediction. Oracle functions
use observed held-out outcomes only after predictions are frozen, and never
return values to model fitting or calibration. No canton-level polls invented.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.modeling.audit_xgboost_capacity import diagnostics
from scripts.modeling.diagnose_v5_errors import load_outcomes
from scripts.modeling.local_profiles_v7 import historical_matrix
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.semantic_training_v5 import (
    CURRENT_POLLS,
    EXTRAS,
    HISTORICAL,
    HISTORICAL_POLLS,
    PLAN,
    V4,
    prepare_data,
)

REGIONS = {"1": "de", "2": "fr", "3": "it"}
LANGUAGES = ("de", "fr", "it")
# Polls are a source of contrasts, not an independent national estimate.
# Fixed variants; retain the original national target (including Romansh).
VARIANTS = {
    "national_only": ("none", 0., 0., "yes"),
    "gap_latest25": ("gap", .25, 0., "yes"),
    "gap_latest50": ("gap", .50, 0., "yes"),
    "gap_latest100": ("gap", 1., 0., "yes"),
    "gap_trend25": ("gap", .25, 1., "yes"),
    "gap_trend50": ("gap", .50, 1., "yes"),
    "gap_trend100": ("gap", 1., 1., "yes"),
    "gap_decided50": ("gap", .50, 0., "decided"),
    "gap_decided100": ("gap", 1., 0., "decided"),
    "gap_undecided50": ("gap", .50, 0., "half"),
    "absolute_latest50": ("absolute", .50, 0., "yes"),
    "absolute_trend50": ("absolute", .50, 1., "yes"),
    "latent_latest50": ("latent", .50, 0., "yes"),
    "latent_latest100": ("latent", 1., 0., "yes"),
    "latent_trend50": ("latent", .50, 1., "yes"),
    "latent_trend100": ("latent", 1., 1., "yes"),
}
ORACLES = ("oracle_national_offset", "oracle_language_offset", "oracle_canton_offset",
           "oracle_language_urban_offset", "oracle_language_gap_proxy", "oracle_canton_gap_proxy")


def load_regional(path, national):
    """Require exact pre-vote identity, wave dates, and complete margins."""
    data = pd.read_csv(path, dtype={"vote_key": str})
    columns = {"vote_key", "vote_date", "wave", "region", "survey_midpoint",
               "published_at", "yes_certain", "yes_lean", "undecided",
               "no_lean", "no_certain", "yes_total", "no_total", "chart_url",
               "historical_version_verified"}
    if not columns.issubset(data):
        raise ValueError("Missing regional source columns")
    if data.duplicated(["vote_key", "wave", "region"]).any():
        raise ValueError("Duplicate regional margin")
    if not data.region.isin(LANGUAGES).all():
        raise ValueError("Unknown linguistic region")
    if data.historical_version_verified.astype(str).str.lower().ne("false").any():
        raise ValueError("Historical versions are not certified")
    fields = ["yes_certain", "yes_lean", "undecided", "no_lean", "no_certain"]
    if not np.isfinite(data[fields].to_numpy(float)).all() or not data[fields].apply(
        lambda s: s.between(0, 100).all()
    ).all():
        raise ValueError("Invalid poll proportions")
    if (data[fields].sum(axis=1) - 100).abs().gt(2.01).any():
        raise ValueError("Regional totals exceed five-cell rounding tolerance")
    if not np.allclose(data.yes_total, data.yes_certain + data.yes_lean):
        raise ValueError("Invalid yes total")
    if not np.allclose(data.no_total, data.no_certain + data.no_lean):
        raise ValueError("Invalid no total")
    if not data.groupby(["vote_key", "wave"]).region.nunique().eq(3).all():
        raise ValueError("Incomplete three-region wave")
    keys = ["vote_key", "wave"]
    fields = ["vote_date", "survey_midpoint", "published_at", "chart_url"]
    joined = data.merge(national[keys + fields], on=keys, how="left",
                        validate="many_to_one", suffixes=("", "_national"))
    for field in fields:
        if not joined[field].eq(joined[field + "_national"]).all():
            raise ValueError(f"Regional poll mismatch: {field}")
    published = pd.to_datetime(data.published_at, utc=True)
    vote = pd.to_datetime(data.vote_date, utc=True)
    if not published.le(vote - pd.Timedelta(days=1)).all():
        raise ValueError("Regional poll published after the evaluation cutoff")
    if not pd.to_datetime(data.survey_midpoint).lt(pd.to_datetime(data.vote_date)).all():
        raise ValueError("Invalid survey chronology")
    return data


def regional_target(rows, vote_date, trend, undecided):
    """Choose latest complete wave and extrapolate, only from past publications."""
    if rows.empty:
        return None
    cutoff = pd.Timestamp(vote_date, tz="UTC") - pd.Timedelta(days=1)
    admissible = rows[pd.to_datetime(rows.published_at, utc=True).le(cutoff)]
    waves = sorted(admissible.wave.unique())
    if not waves:
        return None
    latest = admissible[admissible.wave.eq(waves[-1])].set_index("region").reindex(LANGUAGES)
    if latest.yes_total.isna().any():
        return None

    def value(wave):
        if undecided == "yes":
            return wave.yes_total.to_numpy(float) / 100
        if undecided == "half":
            return (wave.yes_total.to_numpy(float) + .5 * wave.undecided.to_numpy(float)) / 100
        if undecided == "decided":
            yes = wave.yes_total.to_numpy(float)
            return yes / (yes + wave.no_total.to_numpy(float))
        raise ValueError("Invalid undecided policy")

    target = value(latest)
    if trend and len(waves) >= 2:
        prior = admissible[admissible.wave.eq(waves[-2])].set_index("region").reindex(LANGUAGES)
        t1, t2 = pd.Timestamp(prior.survey_midpoint.iloc[0]), pd.Timestamp(latest.survey_midpoint.iloc[0])
        span, remaining = (t2 - t1).days, (pd.Timestamp(vote_date) - t2).days
        if span <= 0 or remaining <= 0:
            raise ValueError("Invalid regional trend dates")
        change = np.clip(trend * (target - value(prior)) * remaining / span, -.15, .15)
        target = target + change
    return np.clip(target, 0, 1)


def shift_to(p, w, target):
    """Exact weighted level after clipping, with monotone bisection."""
    if not np.isfinite(p).all() or not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0:
        raise ValueError("Invalid calibration weights")
    w = w / w.sum()
    target = float(np.clip(target, 0, 1))
    lo, hi = -float(p.max()), 1. - float(p.min())
    for _ in range(48):
        mid = (lo + hi) / 2
        if w @ np.clip(p + mid, 0, 1) < target:
            lo = mid
        else:
            hi = mid
    adjusted = np.clip(p + (lo + hi) / 2, 0, 1)
    if abs(w @ adjusted - target) > 1e-9:
        raise ValueError("Anchor did not converge")
    return adjusted


def group_stats(p, w, groups, labels):
    mass, means = [], []
    for label in labels:
        mask = groups == label
        weight = w[mask]
        if not mask.any() or weight.sum() <= 0:
            raise ValueError(f"No positive exposure for region {label}")
        mass.append(weight.sum())
        means.append(float(np.average(p[mask], weights=weight)))
    mass = np.asarray(mass)
    return mass / mass.sum(), np.asarray(means)


def gap_targets(p, w, groups, labels, margins, strength):
    """Keep the weighted mean over covered groups, preserve their contrasts."""
    mass, current = group_stats(p, w, groups, labels)
    target = (1 - strength) * current + strength * (margins + mass @ current - mass @ margins)
    # Feasible box constraint + exact covered group mean even at extremes.
    return shift_to(target, mass, mass @ current)


def gap_adjust(p, w, groups, labels, margins, strength):
    target = gap_targets(p, w, groups, labels, margins, strength)
    result = p.copy()
    for label, value in zip(labels, target, strict=True):
        mask = groups == label
        result[mask] = shift_to(p[mask], w[mask], value)
    if abs(np.average(result - p, weights=w)) > 1e-9:
        raise ValueError("Regional gaps changed national weighted level")
    return result


def latent_operator(train_residual, indices, w, groups):
    """Condition historical municipal covariance on regional contrasts.

    Learn a smooth spatial update from historical aggregate profiles, not from
    the held-out vote. Rows are centered; missing historical residuals are zero.
    Region-level uncertainty is regularized (not estimated from opt-in n).
    """
    valid = indices >= 0
    complete = np.nan_to_num(train_residual, nan=0.)
    complete -= complete.mean(axis=0, keepdims=True)
    mapped = np.zeros((len(complete), len(indices)))
    mapped[:, valid] = complete[:, indices[valid]]
    national = mapped @ (w / w.sum())
    aggregated = []
    for region in LANGUAGES:
        mask = groups == region
        aggregated.append(mapped[:, mask] @ (w[mask] / w[mask].sum()) - national)
    a = np.column_stack(aggregated)
    # Historical covariance, 3x3. Fixed ridge on the group contrasts protects
    # against noisy/collinear regional margins. No effective n is invented.
    cov = a.T @ a / len(a)
    ridge = .15 * max(float(np.trace(cov) / len(LANGUAGES)), 1e-6)
    return (mapped.T @ a / len(a)) @ np.linalg.inv(cov + ridge * np.eye(len(LANGUAGES)))


def real_adjust(p, w, language, rows, vote_date, config, operator=None):
    method, strength, trend, allocation = config
    if method == "none":
        return p.copy(), False
    target = regional_target(rows, vote_date, trend, allocation)
    if target is None:
        return p.copy(), False
    if method == "gap":
        return gap_adjust(p, w, language, LANGUAGES, target, strength), True
    if method == "absolute":
        out = p.copy()
        for region, value in zip(LANGUAGES, target, strict=True):
            mask = language == region
            current = np.average(p[mask], weights=w[mask])
            out[mask] = shift_to(p[mask], w[mask], (1-strength)*current + strength*value)
        return out, True
    if method != "latent" or operator is None:
        raise ValueError("Unknown or unavailable regional calibration")
    mass, base = group_stats(p, w, language, LANGUAGES)
    delta = strength * ((target - mass @ target) - (base - mass @ base))
    offset = operator @ delta
    return shift_to(np.clip(p + offset, 0, 1), w, np.average(p, weights=w)), True


def oracle_adjust(p, y, w, language, canton, urban, name):
    """Separate retrospective diagnostic; never a candidate prediction."""
    if name == "oracle_national_offset":
        return np.clip(p + np.median(y - p), 0, 1)
    if name == "oracle_language_offset":
        groups = language
    elif name == "oracle_canton_offset":
        groups = canton
    elif name == "oracle_language_urban_offset":
        groups = np.char.add(np.char.add(language.astype(str), "_"), urban.astype(str))
    elif name in {"oracle_language_gap_proxy", "oracle_canton_gap_proxy"}:
        groups = language if name == "oracle_language_gap_proxy" else canton
        labels = tuple(str(g) for g in np.unique(groups) if w[groups == g].sum() > 0)
        if not labels:
            return p.copy()
        _, margins = group_stats(y, w, groups, labels)
        return gap_adjust(p, w, groups, labels, margins, 1.)
    else:
        raise ValueError("Unknown oracle")
    out = p.copy()
    for group in np.unique(groups):
        mask = groups == group
        out[mask] = np.clip(p[mask] + np.median(y[mask] - p[mask]), 0, 1)
    return out


def summarize(rows):
    detail = pd.DataFrame(rows)
    summaries = []
    for (base, variant), group in detail.groupby(["base", "variant"], sort=False):
        if len(group) != 66 or group.vote_id.nunique() != 66:
            raise ValueError("Full population must be preserved")
        covered = group[group.regional_available]
        summaries.append({
            "base": base, "variant": variant, "objects": len(group),
            "regional_objects": len(covered),
            "mae": float(group.mae.mean()),
            "covered_mae": float(covered.mae.mean()) if len(covered) else None,
            "centered_mae": float(group.centered_mae.mean()),
            "covered_centered_mae": float(covered.centered_mae.mean()) if len(covered) else None,
        })
    return detail, summaries


def run(base, inductive, regional, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Do not overwrite diagnostic")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    data, _, _, _, _ = prepare_data(
        base, EXTRAS, HISTORICAL, V4, CURRENT_POLLS, HISTORICAL_POLLS, plan
    )
    national = pd.read_csv(CURRENT_POLLS, dtype={"vote_key": str})
    poll_rows = load_regional(regional, national)
    counts = load_outcomes()
    lookup = counts[["vote_id", "municipality_id", "canton"]]
    types = pd.read_parquet(ROOT / "data/processed/typologies/commune_typologies.parquet",
                            columns=["municipality_id", "language_region", "urban_rural"])
    types["municipality_id"] = types.municipality_id.astype(str)
    data["municipality_id"] = data.municipality_id.astype(str)
    data = data.merge(lookup, on=["vote_id", "municipality_id"], how="left", validate="one_to_one")
    data = data.merge(types, on="municipality_id", how="left", validate="many_to_one")
    data["language"] = data.language_region.astype(str).map(REGIONS).fillna("other")
    data["weight"] = (data.statpop_pop_total * (1 - data.statpop_share_foreign) *
                      (1 - data.statpop_share_0_19)).fillna(0)
    manifest = json.loads((inductive / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete":
        raise ValueError("Inductive benchmark incomplete")
    output.mkdir(parents=True, exist_ok=True)
    # Construct history/operator once for all three base models.
    contexts = {}
    with threadpool_limits(limits=2):
        for window in plan["validation_windows"]:
            train = data[data.vote_date.lt(window["start"])]
            evaluation = data[data.vote_date.between(window["start"], window["end"])]
            ids = train.vote_id.drop_duplicates().astype(str).tolist()
            munis, _, residual = historical_matrix(train, ids)
            for vote, v in evaluation.groupby("vote_id", sort=False):
                v = v.sort_values("municipality_id")
                p_rows = poll_rows[poll_rows.vote_key.eq(str(v.vote_key.iloc[0]))]
                weight = v.weight.to_numpy(float)
                if weight.sum() <= 0:
                    # Oracle-only early vote without covariates: equal weights,
                    # no regional survey adjustment is made for these cases.
                    weight = np.ones(len(v))
                language = v.language.astype(str).to_numpy()
                date = str(v.vote_date.iloc[0].date())
                operator = None
                if not p_rows.empty:
                    operator = latent_operator(residual, pd.Index(munis).get_indexer(v.municipality_id),
                                               weight, language)
                contexts[str(vote)] = (v, weight, language, p_rows, date, operator)
    rows, calibration = [], []
    for name, checksum in manifest["prediction_hashes"].items():
        path = inductive / f"{name}_predictions.parquet"
        if sha(path) != checksum:
            raise ValueError("Frozen predictions changed")
        pred = pd.read_parquet(path)
        pred["municipality_id"] = pred.municipality_id.astype(str)
        pred["vote_id"] = pred.vote_id.astype(str)
        if len(pred) != 138868 or pred.vote_date.ge("2023-01-01").any():
            raise ValueError("Wrong evaluation population")
        # Fit shrinkage selection only on complete earlier voting dates;
        # initialize with the fixed, conservative half-strength regional gap.
        history = []
        for date, same_day in pred.sort_values("vote_date").groupby("vote_date", sort=True):
            if history:
                history_frame = pd.DataFrame(history)
                # Weak regularizer: one pseudo-object favoring 50% shrink.
                shrink_names = ["national_only", "gap_latest25", "gap_latest50", "gap_latest100",
                                "gap_trend25", "gap_trend50", "gap_trend100"]
                averages = history_frame.groupby("variant").mae.mean()
                choice = min(shrink_names, key=lambda c: averages.get(c, np.inf) +
                             .05 * abs(VARIANTS[c][1] - .5))
            else:
                choice = "gap_latest50"
            new_history = []
            for vote, frame in same_day.groupby("vote_id", sort=False):
                frame = frame.sort_values("municipality_id")
                v, w, language, poll, stamp, operator = contexts[vote]
                if not np.array_equal(frame.municipality_id.to_numpy(), v.municipality_id.to_numpy()):
                    raise ValueError("Municipal keys mismatch")
                y, p = frame.yes_share.to_numpy(float), frame.prediction.to_numpy(float)
                if not np.allclose(y, v.yes_share):
                    raise ValueError("Target mismatch")
                available = regional_target(poll, stamp, 0., "yes") is not None
                forecasts = {variant: real_adjust(p, w, language, poll, stamp, config, operator)[0]
                             for variant, config in VARIANTS.items()}
                forecasts["walk_forward_shrink"] = forecasts[choice].copy()
                # All real predictions are fixed before any oracle is evaluated.
                for oracle in ORACLES:
                    forecasts[oracle] = oracle_adjust(
                        p, y, w, language, v.canton.fillna("unknown").astype(str).to_numpy(),
                        v.urban_rural.fillna("unknown").astype(str).to_numpy(), oracle
                    )
                for variant, forecast in forecasts.items():
                    score, _ = diagnostics(y, forecast, np.zeros(len(y), dtype=int), 1)
                    row = {"base": name, "variant": variant, "vote_id": vote, "vote_date": stamp,
                           "regional_available": available, "oracle": variant.startswith("oracle_"),
                           "mae": score["mae"], "centered_mae": score["centered_mae"]}
                    rows.append(row)
                    if available and variant in VARIANTS:
                        new_history.append(row)
                if available:
                    calibration.append({"base": name, "vote_id": vote, "vote_date": stamp,
                                        "chosen": choice, "prior_objects": len({h["vote_id"] for h in history})})
            # Same-date outcomes cannot affect any choice on this date.
            history.extend(new_history)
    detail, summary = summarize(rows)
    for row in summary:
        if row["variant"] != "national_only" and not row["variant"].startswith("oracle_"):
            sub = detail[detail.base.eq(row["base"])].rename(columns={"mae": "mae_pp"})
            row["gain_interval"] = paired_date_bootstrap(sub, "national_only", row["variant"])
    detail.to_csv(output / "object_metrics.csv", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    pd.DataFrame(calibration).to_csv(output / "walk_forward_selection.csv", index=False)
    output_manifest = {"status": "complete", "strict_forecast_ready": False,
                       "regional_rows": len(poll_rows), "source_sha256": sha(regional),
                       "inductive_manifest_sha256": sha(inductive / "manifest.json"),
                       "comparison_targets_loaded": False, "summary": summary,
                       "oracle_status": "Uses observed outcomes; never a forecast"}
    (output / "manifest.json").write_text(json.dumps(output_manifest, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--inductive", required=True, type=Path)
    parser.add_argument("--regional", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.base, args.inductive, args.regional, args.output)


if __name__ == "__main__":
    main()
