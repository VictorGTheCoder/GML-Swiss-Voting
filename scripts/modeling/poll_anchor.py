"""Pre-vote national poll features and an evaluated municipal anchoring variant.

National polls measure a different population from an equal-municipality mean.
The anchor therefore uses the explicit STATPOP proxy
``population * (1 - foreign share) * (1 - age 0..19 share)``. This product of
marginals is an approximation: citizenship and age are not independent, Swiss
voters aged 18/19 are omitted, and participation/expatriate voters are absent.
It is neither an electoral-register count nor a current referendum outcome.

All naive timestamps, including ``as_of``, are interpreted as UTC. A date-only
cutoff means midnight, not an implicitly extended end of day. Poll publication
dates are announced dates on current sources; this module does not certify
historical versions or relax the project's strict availability gates.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.utils.validation import check_is_fitted

POLL_SHARES = ["poll_yes_share", "poll_no_share", "poll_undecided_share"]
POLL_TREND_FEATURES = ["poll_yes_trend_per_day", "poll_days_to_vote", "poll_trend_available"]
POLL_FEATURES = [*POLL_SHARES, "poll_available", *POLL_TREND_FEATURES]
POLL_ADDED_COLUMNS = [
    *POLL_FEATURES,
    "poll_population_weight",
    "poll_published_at",
    "poll_wave",
    "poll_source_url",
]
POPULATION_COLUMNS = ["statpop_pop_total", "statpop_share_foreign", "statpop_share_0_19"]
ROUNDING_TOLERANCE = 0.010000001
POPULATION_EXPLANATION = (
    "STATPOP population * (1 - foreign share) * (1 - age 0..19 share). "
    "Approximate resident electorate, using marginal shares: age/citizenship "
    "dependence, voters aged 18/19, expatriates and turnout are not represented. "
    "No current referendum outcome is used."
)


def _required(frame, columns, name):
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")
    if frame.columns.duplicated().any():
        raise ValueError(f"{name} has duplicate column names")


def _keys(values, name):
    result = values.astype("string").str.strip()
    if result.isna().any() or result.eq("").any():
        raise ValueError(f"{name} contains missing or empty identifiers")
    return result


def _dates(values, name):
    """Calendar vote dates must be explicit midnights; preserve local date."""
    try:
        lookup = {}
        for value in values.unique():
            stamp = pd.Timestamp(value)
            if pd.isna(stamp) or stamp != stamp.normalize():
                raise ValueError("not a calendar date")
            lookup[value] = pd.Timestamp(stamp.date())
        return pd.to_datetime(values.map(lookup))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain valid calendar dates") from exc


def _timestamps(values, name):
    try:
        result = pd.to_datetime(values, utc=True, format="mixed", errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} contains invalid timestamps") from exc
    if result.isna().any():
        raise ValueError(f"{name} contains missing timestamps")
    return result


def _numbers(values, name, allow_missing=False):
    try:
        result = pd.to_numeric(values, errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if np.isinf(result).any() or (not allow_missing and result.isna().any()):
        raise ValueError(f"{name} contains non-finite values")
    return result


def _population_weights(frame):
    _required(frame, POPULATION_COLUMNS, "municipal population data")
    pop = _numbers(frame.statpop_pop_total, "statpop_pop_total", allow_missing=True)
    foreign = _numbers(frame.statpop_share_foreign, "statpop_share_foreign", allow_missing=True)
    young = _numbers(frame.statpop_share_0_19, "statpop_share_0_19", allow_missing=True)
    if (pop.dropna() < 0).any():
        raise ValueError("statpop_pop_total must be nonnegative")
    for name, values in [("statpop_share_foreign", foreign), ("statpop_share_0_19", young)]:
        if ((values.dropna() < 0) | (values.dropna() > 1)).any():
            raise ValueError(f"{name} must be a share in [0, 1]")
    return pop * (1 - foreign) * (1 - young)


def _object_keys(frame, name):
    _required(frame, ["municipality_id", "vote_key", "vote_date"], name)
    keys = pd.DataFrame(
        {
            "municipality_id": _keys(frame.municipality_id, "municipality_id"),
            "vote_key": _keys(frame.vote_key, "vote_key"),
            "vote_date": _dates(frame.vote_date, "vote_date"),
        }
    )
    if keys.groupby("vote_key").vote_date.nunique().gt(1).any():
        raise ValueError("A vote_key maps to multiple vote_date values")
    if keys.duplicated(["vote_key", "municipality_id"]).any():
        raise ValueError("Duplicate municipality/vote_key rows are ambiguous")
    if "vote_id" in frame:
        vote_ids = _keys(frame.vote_id, "vote_id")
        pairs = pd.DataFrame({"vote_id": vote_ids, "vote_key": keys.vote_key})
        if pairs.groupby("vote_id").vote_key.nunique().gt(1).any():
            raise ValueError("A vote_id maps to multiple vote_key values")
        if pairs.groupby("vote_key").vote_id.nunique().gt(1).any():
            raise ValueError("A vote_key maps to multiple vote_id values")
    return keys


def _validated_polls(polls):
    _required(polls, ["vote_key", "vote_date", "published_at", "survey_midpoint", "undecided"], "polls")
    result = polls.reset_index(drop=True).copy()
    result["vote_key"] = _keys(result.vote_key, "poll vote_key")
    result["vote_date"] = _dates(result.vote_date, "poll vote_date")
    result["published_at"] = _timestamps(result.published_at, "published_at")
    result["survey_midpoint"] = _dates(result.survey_midpoint, "survey_midpoint")
    if result.groupby("vote_key").vote_date.nunique().gt(1).any():
        raise ValueError("A poll vote_key maps to multiple dates")
    if result.duplicated(["vote_key", "published_at"]).any():
        raise ValueError("Ambiguous duplicate poll publications for an object")
    if "wave" in result and result.duplicated(["vote_key", "wave"]).any():
        raise ValueError("Ambiguous duplicate poll waves for an object")
    if "mapping_status" in result and result.mapping_status.ne("reviewed_date_and_title").any():
        raise ValueError("Poll mapping_status must be reviewed_date_and_title")
    detailed = ["yes_certain", "yes_lean", "no_lean", "no_certain"]
    if any(column in result for column in detailed):
        _required(result, detailed, "poll response categories")
        for column in detailed:
            result[column] = _numbers(result[column], column)
            if ((result[column] < 0) | (result[column] > 100)).any():
                raise ValueError(f"{column} must be a percentage in [0, 100]")
        for total, parts in [("yes_total", ["yes_certain", "yes_lean"]), ("no_total", ["no_certain", "no_lean"])]:
            derived = result[parts].sum(axis=1)
            if total in result and not np.allclose(_numbers(result[total], total), derived, atol=1e-9, rtol=0):
                raise ValueError(f"{total} disagrees with its response categories")
            result[total] = derived
    _required(result, ["yes_total", "no_total"], "poll percentages")
    for column in ["yes_total", "no_total", "undecided"]:
        result[column] = _numbers(result[column], column)
        if ((result[column] < 0) | (result[column] > 100)).any():
            raise ValueError(f"{column} must be a percentage in [0, 100]")
    totals = result[["yes_total", "no_total", "undecided"]].sum(axis=1)
    if ((totals - 100).abs() > 100 * ROUNDING_TOLERANCE).any():
        raise ValueError("Poll percentages must sum to 100%, within one published rounding point")
    if (result.published_at >= result.vote_date.dt.tz_localize("UTC")).any():
        raise ValueError("Poll publication must precede the referendum date")
    if (result.survey_midpoint >= result.vote_date).any() or (
        result.survey_midpoint.dt.tz_localize("UTC") > result.published_at
    ).any():
        raise ValueError("survey_midpoint must precede publication and the referendum date")
    if "survey_start" in result or "survey_end" in result:
        _required(result, ["survey_start", "survey_end"], "poll survey dates")
        start = _dates(result.survey_start, "survey_start")
        end = _dates(result.survey_end, "survey_end")
        if (start > end).any() or (end.dt.tz_localize("UTC") > result.published_at).any():
            raise ValueError("Poll survey dates must precede publication")
        if ((result.survey_midpoint < start) | (result.survey_midpoint > end)).any():
            raise ValueError("survey_midpoint must lie within the survey interval")
    ordered = result.sort_values(["vote_key", "published_at"])
    gaps = ordered.groupby("vote_key").survey_midpoint.diff().dt.days
    if gaps.dropna().le(0).any():
        raise ValueError("Poll survey midpoints must be strictly increasing in publication chronology")
    return result, totals


def add_poll_features(table, polls, as_of=None):
    """Enrich every input row using the latest admissible, exactly matched poll.

    Explicit ``feature_cutoff`` wins; missing cutoffs fall back to vote_date minus
    one day. ``as_of`` imposes an additional common upper bound. Cutoffs must be
    identical within each object. Missing polls preserve all municipal rows.
    Percentages are divided by 100 exactly, with only +/-1 percentage point of
    source rounding accepted; no implicit renormalization occurs.
    The trend uses only the two latest admissible publications and their survey
    midpoints. Without a prior admissible wave its rate and availability are 0.
    """
    collisions = sorted(set(POLL_ADDED_COLUMNS) & set(table.columns))
    if collisions:
        raise ValueError(f"Refusing to overwrite existing poll columns: {collisions}")
    work = table.reset_index(drop=True)
    keys = _object_keys(work, "table")
    weights = _population_weights(work)
    source, totals = _validated_polls(polls)
    default_cutoff = (keys.vote_date - pd.Timedelta(days=1)).dt.tz_localize("UTC")
    if "feature_cutoff" in work:
        cutoff = pd.to_datetime(work.feature_cutoff, utc=True, format="mixed", errors="raise")
        cutoff = cutoff.fillna(default_cutoff)
    else:
        cutoff = default_cutoff
    if (cutoff >= keys.vote_date.dt.tz_localize("UTC")).any():
        raise ValueError("feature_cutoff must precede the referendum date")
    if as_of is not None:
        as_of_time = _timestamps(pd.Series([as_of]), "as_of").iloc[0]
        cutoff = cutoff.clip(upper=as_of_time)
    else:
        as_of_time = None
    objects = keys[["vote_key", "vote_date"]].assign(cutoff=cutoff)
    if objects.groupby("vote_key").cutoff.nunique().gt(1).any():
        raise ValueError("Poll cutoff must be constant within an object")
    objects = objects.drop_duplicates("vote_key")
    dates = objects.set_index("vote_key").vote_date
    overlap = source[source.vote_key.isin(dates.index)]
    if overlap.vote_date.ne(overlap.vote_key.map(dates)).any():
        raise ValueError("Poll vote_key/date mismatch with the municipal table")
    selected, trends = {}, {}
    for obj in objects.itertuples(index=False):
        eligible = source[(source.vote_key == obj.vote_key) & (source.published_at <= obj.cutoff)]
        if not eligible.empty:
            eligible = eligible.sort_values("published_at")
            latest = eligible.iloc[-1]
            selected[obj.vote_key] = latest
            rate, prior = 0.0, None
            if len(eligible) > 1:
                prior = eligible.iloc[-2]
                days = int((latest.survey_midpoint - prior.survey_midpoint).days)
                # Strict positivity has already been checked independently of targets.
                rate = (float(latest.yes_total) - float(prior.yes_total)) / 100 / days
            trends[obj.vote_key] = {
                "poll_yes_trend_per_day": rate,
                "poll_days_to_vote": float((obj.vote_date - latest.survey_midpoint).days),
                "poll_trend_available": float(prior is not None),
                "latest_midpoint": latest.survey_midpoint.date().isoformat(),
                "prior_midpoint": prior.survey_midpoint.date().isoformat() if prior is not None else None,
                "prior_published_at": prior.published_at.isoformat() if prior is not None else None,
            }
    result = table.copy()
    row_keys = keys.vote_key
    for name, field in zip(POLL_SHARES, ["yes_total", "no_total", "undecided"], strict=True):
        values = {key: float(row[field]) / 100 for key, row in selected.items()}
        result[name] = row_keys.map(values).to_numpy(dtype=float)
    result["poll_available"] = row_keys.isin(selected).to_numpy(dtype=float)
    for name in POLL_TREND_FEATURES:
        result[name] = row_keys.map({key: row[name] for key, row in trends.items()}).fillna(0.0).to_numpy(float)
    result["poll_population_weight"] = weights.to_numpy(dtype=float)
    for name, field in [
        ("poll_published_at", "published_at"),
        ("poll_wave", "wave"),
        ("poll_source_url", "source_url"),
    ]:
        values = {key: row.get(field, np.nan) for key, row in selected.items()}
        result[name] = row_keys.map(values).to_numpy()
    if not selected:
        result["poll_published_at"] = pd.NaT
    selection_audit = [
        {
            "vote_key": key,
            "vote_date": row.vote_date.date().isoformat(),
            "published_at": row.published_at.isoformat(),
            "wave": None if pd.isna(row.get("wave")) else int(row.wave),
            **trends[key],
        }
        for key, row in selected.items()
    ]
    manifest = {
        "mode": "exploratory_poll_variant",
        "strict_forecast_ready": False,
        "historical_version_verified": False,
        "evaluation_targets_used": False,
        "rows": len(result),
        "objects": len(objects),
        "poll_objects": len(selected),
        "objects_without_poll": len(objects) - len(selected),
        "poll_rows": int(result.poll_available.sum()),
        "source_poll_rows": len(source),
        "objects_with_prior_admissible_poll": int(sum(row["poll_trend_available"] for row in trends.values())),
        "trend_rule": "(latest yes share - prior yes share) / survey midpoint days; only publications admissible at cutoff",
        "trend_horizon": "Calendar days from latest survey midpoint to vote_date; not days from publication",
        "trend_missing_prior_policy": "Rate=0, availability=0; latest midpoint horizon retained if a poll exists",
        "numeric_features": list(POLL_FEATURES),
        "categorical_features": [],
        "object_numeric_features": list(POLL_FEATURES),
        "object_categorical_features": [],
        "population_weight_column": "poll_population_weight",
        "population_proxy": POPULATION_EXPLANATION,
        "population_weight_missing_rows": int(weights.isna().sum()),
        "percentage_rule": "Exact division by 100; no renormalization; source sum may differ by at most 1 point",
        "source_rows_with_rounding": int(((totals - 100).abs() > 1e-9).sum()),
        "selected_rows_with_rounding": int(
            sum(abs(row.yes_total + row.no_total + row.undecided - 100) > 1e-9 for row in selected.values())
        ),
        "timestamp_policy": "Naive timestamps are UTC; date-only cutoff is start of day",
        "as_of": as_of_time.isoformat() if as_of_time is not None else None,
        "cutoff_policy": "min(feature_cutoff or vote_date minus one day, optional as_of)",
        "selection": selection_audit,
        "retained_all_input_rows": True,
    }
    return result, manifest


class PollAnchoredRegressor(RegressorMixin, BaseEstimator):
    """Shift a fitted model's municipal predictions towards a national poll.

    ``base_model`` must already be fitted and expose ``predict(frame)``. ``fit``
    only stores the last training-date municipal population reference. It never
    fits or clones the base model and does not read a target.

    Prediction must include the full national municipality batch for each
    anchored object. Both its observed proxy weight and the represented share
    of the training reference population must reach ``min_population_fraction``.
    A single-municipality batch is always rejected when an anchor acts. Objects
    without a poll (and weight=0) preserve the exact base predictions.

    The anchor is a model variant to evaluate, not an assertion that a national
    intention poll equals the eventual nationwide referendum share.

    Optional ``trend_factor`` extrapolates the pre-vote yes-share slope from the
    latest survey midpoint to vote day. The capped adjustment transfers support
    between no and yes, preserving undecided and the published rounded total.
    Bounds also keep the allocated poll target feasible. No trend parameter is
    learned in ``fit``; the default factor of zero retains the original anchor.
    """

    def __init__(
        self,
        base_model,
        weight=1.0,
        undecided_yes_fraction=0.5,
        min_population_fraction=0.9,
        trend_factor=0.0,
        max_trend_adjustment=0.15,
    ):
        self.base_model = base_model
        self.weight = weight
        self.undecided_yes_fraction = undecided_yes_fraction
        self.min_population_fraction = min_population_fraction
        self.trend_factor = trend_factor
        self.max_trend_adjustment = max_trend_adjustment

    def __setstate__(self, state):
        """Load pre-trend pickles with the exact original prediction defaults."""
        state = dict(state)
        state.setdefault("trend_factor", 0.0)
        state.setdefault("max_trend_adjustment", 0.15)
        super().__setstate__(state)

    def _validate_parameters(self):
        for name in ["weight", "undecided_yes_fraction", "min_population_fraction"]:
            value = getattr(self, name)
            if not isinstance(value, (int, float, np.number)) or not np.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if self.min_population_fraction == 0:
            raise ValueError("min_population_fraction must be positive")
        if (
            not isinstance(self.trend_factor, (int, float, np.number))
            or not np.isfinite(self.trend_factor)
            or self.trend_factor < 0
        ):
            raise ValueError("trend_factor must be finite and nonnegative")
        if (
            not isinstance(self.max_trend_adjustment, (int, float, np.number))
            or not np.isfinite(self.max_trend_adjustment)
            or not 0 <= self.max_trend_adjustment <= 1
        ):
            raise ValueError("max_trend_adjustment must be finite and in [0, 1]")
        if not callable(getattr(self.base_model, "predict", None)):
            raise TypeError("base_model must already expose predict(frame)")

    @staticmethod
    def _weights(frame):
        if "poll_population_weight" in frame:
            weights = _numbers(frame.poll_population_weight, "poll_population_weight", allow_missing=True)
            if (weights.dropna() < 0).any():
                raise ValueError("poll_population_weight must be nonnegative")
            return weights
        return _population_weights(frame)

    def fit(self, frame):
        self._validate_parameters()
        work = frame.reset_index(drop=True)
        keys = _object_keys(work, "training frame")
        if work.empty:
            raise ValueError("Population reference requires training municipalities")
        weights = self._weights(work)
        reference_date = keys.vote_date.max()
        reference = keys.loc[keys.vote_date == reference_date, ["municipality_id"]].assign(weight=weights)
        if reference.groupby("municipality_id").weight.nunique(dropna=False).gt(1).any():
            raise ValueError("Conflicting population weights on the last training date")
        reference = reference.drop_duplicates("municipality_id").set_index("municipality_id").weight
        if reference.isna().any() or reference.sum() <= 0:
            raise ValueError("Last training population reference must have known positive total weight")
        if (reference > 0).sum() < 2:
            raise ValueError("National population reference requires multiple municipalities")
        self.reference_population_ = reference.copy()
        self.reference_population_total_ = float(reference.sum())
        self.reference_date_ = reference_date
        self.audit_ = {
            "reference_date": reference_date.date().isoformat(),
            "reference_municipalities": len(reference),
            "reference_population_total": self.reference_population_total_,
            "population_proxy": POPULATION_EXPLANATION,
            "reference_policy": "Unique municipalities at the last global training vote_date; no union of obsolete municipalities",
            "base_model_retrained": False,
            "evaluation_targets_used": False,
            "trend_factor": self.trend_factor,
            "max_trend_adjustment": self.max_trend_adjustment,
            "trend_parameters_learned": False,
            "trend_adjustment_policy": "Capped pre-vote midpoint slope; transfer no to yes, preserve undecided and rounded total; bound shares and allocated target",
            "prediction_population_requirement": "Full national batch per object; both observed total and represented reference population must pass coverage guard",
            "strict_forecast_ready": False,
        }
        return self

    def predict(self, frame):
        return self.predict_components(frame)["prediction"].to_numpy(dtype=float)

    def predict_components(self, frame):
        check_is_fitted(self, ["reference_population_", "reference_population_total_", "reference_date_"])
        self._validate_parameters()
        work = frame.reset_index(drop=True)
        keys = _object_keys(work, "prediction frame")
        trend_inputs = None
        if self.trend_factor != 0:
            _required(work, POLL_TREND_FEATURES, "trend_factor != 0 prediction features")
            trend_inputs = work[POLL_TREND_FEATURES].copy()
            for column in POLL_TREND_FEATURES:
                trend_inputs[column] = _numbers(trend_inputs[column], column)
            if not trend_inputs.poll_trend_available.isin([0.0, 1.0]).all():
                raise ValueError("poll_trend_available must be 0 or 1")
            if (trend_inputs.poll_days_to_vote < 0).any():
                raise ValueError("poll_days_to_vote must be nonnegative")
            if ((trend_inputs.poll_trend_available == 0) & (trend_inputs.poll_yes_trend_per_day != 0)).any():
                raise ValueError("Unavailable poll trend must have a zero rate")
            grouped = trend_inputs.assign(vote_key=keys.vote_key).groupby("vote_key")
            if (grouped[POLL_TREND_FEATURES].nunique(dropna=False) > 1).any().any():
                raise ValueError("National trend features must be constant within each object")
        baseline = np.asarray(self.base_model.predict(frame), dtype=float)
        if baseline.ndim != 1 or len(baseline) != len(frame) or not np.isfinite(baseline).all():
            raise ValueError("base_model.predict must return one finite prediction per row")
        components = pd.DataFrame(
            {
                "baseline_prediction": baseline,
                "prediction": baseline.copy(),
                "poll_applied": False,
                "anchor_offset": 0.0,
            },
            index=work.index,
        )
        audit_columns = [
            "national_baseline_mean",
            "national_poll_target",
            "national_target_mean",
            "national_achieved_mean",
            "observed_population_fraction",
            "reference_population_fraction",
            "observed_population_total",
        ]
        for column in audit_columns:
            components[column] = np.nan
        trend_audit_columns = [
            "poll_yes_share_before_trend",
            "poll_no_share_before_trend",
            "poll_undecided_share_before_trend",
            "poll_yes_share_after_trend",
            "poll_no_share_after_trend",
            "poll_undecided_share_after_trend",
            "national_poll_target_before_trend",
        ]
        for column in trend_audit_columns:
            components[column] = np.nan
        for column in ["trend_adjustment_raw", "trend_adjustment_capped", "trend_adjustment_applied"]:
            components[column] = 0.0
        if frame.empty or self.weight == 0:
            components.index = frame.index
            return components
        _required(work, ["poll_available"], "prediction poll features")
        available = _numbers(work.poll_available, "poll_available")
        if not available.isin([0.0, 1.0]).all():
            raise ValueError("poll_available must be 0 or 1")
        if trend_inputs is not None:
            if ((trend_inputs.poll_trend_available == 1) & (available == 0)).any():
                raise ValueError("An available trend requires an available poll")
            if ((available == 1) & (trend_inputs.poll_days_to_vote <= 0)).any():
                raise ValueError("An available poll must have positive poll_days_to_vote")
        flags = keys[["vote_key"]].assign(available=available)
        if flags.groupby("vote_key").available.nunique().gt(1).any():
            raise ValueError("Poll availability must be constant within each object")
        if not available.any():
            components.index = frame.index
            return components
        _required(work, POLL_SHARES, "prediction poll features")
        weights = self._weights(work)
        for vote_key, indices in keys.groupby("vote_key", sort=False).groups.items():
            pos = np.asarray(indices, dtype=int)
            if not available.iloc[pos[0]]:
                continue
            shares = work.iloc[pos][POLL_SHARES].apply(pd.to_numeric, errors="raise")
            if (shares.nunique(dropna=False) != 1).any():
                raise ValueError(f"National poll shares must be constant within object {vote_key}")
            values = shares.iloc[0].to_numpy(float, copy=True)
            if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
                raise ValueError("Selected poll shares must be finite in [0, 1]")
            if abs(values.sum() - 1) > ROUNDING_TOLERANCE:
                raise ValueError("Selected poll shares must sum to 1 within published rounding")
            before = values.copy()
            before_target = float(before[0] + self.undecided_yes_fraction * before[2])
            if not 0 <= before_target <= 1:
                raise ValueError("Allocated pre-trend poll target is outside [0, 1]")
            raw_delta, capped_delta, applied_delta = 0.0, 0.0, 0.0
            if trend_inputs is not None and trend_inputs.poll_trend_available.iloc[pos[0]]:
                row_trend = trend_inputs.iloc[pos[0]]
                raw_delta = float(self.trend_factor * row_trend.poll_yes_trend_per_day * row_trend.poll_days_to_vote)
                if not np.isfinite(raw_delta):
                    raise ValueError("Trend extrapolation must be finite")
                capped_delta = float(np.clip(raw_delta, -self.max_trend_adjustment, self.max_trend_adjustment))
                # Move the same mass from no to yes; keep undecided and sum exactly.
                delta_lower = max(-before[0], before[1] - 1.0, -before_target)
                delta_upper = min(1.0 - before[0], before[1], 1.0 - before_target)
                applied_delta = float(np.clip(capped_delta, delta_lower, delta_upper))
                values[0] = before[0] + applied_delta
                values[1] = before[1] - applied_delta
            components.loc[pos, trend_audit_columns] = [*before, *values, before_target]
            components.loc[pos, ["trend_adjustment_raw", "trend_adjustment_capped", "trend_adjustment_applied"]] = [
                raw_delta,
                capped_delta,
                applied_delta,
            ]
            municipality_ids = keys.iloc[pos].municipality_id
            valid = weights.iloc[pos].notna().to_numpy() & (weights.iloc[pos].to_numpy() > 0)
            if valid.sum() < 2:
                raise ValueError(
                    f"National poll anchoring requires a full population batch, not one municipality: {vote_key}"
                )
            observed = weights.iloc[pos].fillna(0).to_numpy(float)
            observed_total = float(observed.sum())
            observed_fraction = observed_total / self.reference_population_total_
            covered = self.reference_population_.reindex(municipality_ids[valid]).fillna(0).sum()
            reference_fraction = float(covered / self.reference_population_total_)
            if min(observed_fraction, reference_fraction) + 1e-12 < self.min_population_fraction:
                raise ValueError(
                    f"Insufficient population coverage for national poll anchor {vote_key}: "
                    f"observed={observed_fraction:.3f}, reference={reference_fraction:.3f}, "
                    f"required={self.min_population_fraction:.3f}; predict the full municipal population"
                )
            normalized_weights = observed / observed_total
            base = baseline[pos]
            national_base = float(normalized_weights @ base)
            poll_target = float(values[0] + self.undecided_yes_fraction * values[2])
            national_target = (1 - self.weight) * national_base + self.weight * poll_target
            if not 0 <= poll_target <= 1 or not 0 <= national_target <= 1:
                raise ValueError("Allocated poll or blended national target is outside [0, 1]")
            lower, upper = -float(base.max()), 1 - float(base.min())
            for _ in range(64):
                offset = (lower + upper) / 2
                mean = float(normalized_weights @ np.clip(base + offset, 0, 1))
                if mean < national_target:
                    lower = offset
                else:
                    upper = offset
            offset = (lower + upper) / 2
            adjusted = np.clip(base + offset, 0, 1)
            achieved = float(normalized_weights @ adjusted)
            if abs(achieved - national_target) > 1e-10:
                raise RuntimeError("National anchor bisection did not reach its weighted target")
            components.loc[pos, "prediction"] = adjusted
            components.loc[pos, "poll_applied"] = True
            components.loc[pos, "anchor_offset"] = offset
            components.loc[pos, audit_columns] = [
                national_base,
                poll_target,
                national_target,
                achieved,
                observed_fraction,
                reference_fraction,
                observed_total,
            ]
        components.index = frame.index
        return components
