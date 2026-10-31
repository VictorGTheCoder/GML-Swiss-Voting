"""Temporal eligibility and availability evidence for the prepared table.

This module only applies documentary dates supplied by the caller. It never
derives brochure or result publication dates from voting dates.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scripts.common.config import PROCESSED_DIR, REPORTS_DIR
from scripts.integration.prepare_modeling import BasePreparation, prepare_base_table

FORECAST_EVIDENCE_COLUMNS = (
    "vote_id", "forecast_at", "forecast_source", "forecast_source_version", "forecast_evidence",
)
RESULT_EVIDENCE_COLUMNS = (
    "vote_id", "result_available_at", "result_source", "result_source_version",
    "result_availability_evidence",
)
MODEL_OUTPUT = PROCESSED_DIR / "modeling" / "prepared_municipal_voting.parquet"
STRICT_OUTPUT = PROCESSED_DIR / "modeling" / "strict_modeling_population.parquet"
READINESS_OUTPUT = REPORTS_DIR / "modeling" / "temporal_readiness.json"
EXCLUSION_OUTPUT = REPORTS_DIR / "modeling" / "temporal_exclusions.csv"
FEATURE_REPORT_OUTPUT = REPORTS_DIR / "modeling" / "feature_availability.csv"


@dataclass(frozen=True)
class ModelingPreparation:
    """Complete prepared table plus the independently gated strict population."""

    prepared: pd.DataFrame
    strict_population: pd.DataFrame
    exclusions: pd.DataFrame
    readiness: dict
    base: BasePreparation
    feature_join_report: pd.DataFrame
    feature_manifests: dict
    feature_coverage: dict


def attach_temporal_evidence(
    prepared: pd.DataFrame,
    forecast_publications: pd.DataFrame | None,
    result_publications: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Attach object-level publication records while preserving unknown evidence.

    Each evidence table has one row per vote. Conflicting or duplicate keys are
    rejected so a merge cannot multiply observations or silently pick a value.
    Missing evidence rows produce null instants and explicit ``unknown`` status.
    """
    rows = prepared.copy(deep=True).reset_index(drop=True)
    if rows.vote_id.isna().any():
        # Invalid target keys remain in the preparation table but cannot be
        # joined to object-level evidence; the temporal status records that.
        rows["vote_id"] = rows.vote_id.astype("string")

    rows = _attach_evidence_table(
        rows, forecast_publications, FORECAST_EVIDENCE_COLUMNS,
        prefix="forecast", date_column="forecast_at", evidence_column="forecast_evidence",
    )
    rows = _attach_evidence_table(
        rows, result_publications, RESULT_EVIDENCE_COLUMNS,
        prefix="result", date_column="result_available_at",
        evidence_column="result_availability_evidence",
    )
    forecast_provenance = (
        _evidence_present(rows.forecast_source) & _evidence_present(rows.forecast_source_version)
    )
    rows["forecast_status"] = "unknown"
    has_forecast_record = rows.forecast_at.notna() & _evidence_present(rows.forecast_evidence)
    has_forecast = has_forecast_record & forecast_provenance
    rows.loc[has_forecast, "forecast_status"] = "verified"
    bad_forecast = has_forecast & rows.forecast_at.ge(rows.voting_date)
    rows.loc[bad_forecast, "forecast_status"] = "forecast_not_before_vote"
    invalid_forecast = rows.forecast_at.notna() & ~_evidence_present(rows.forecast_evidence)
    rows.loc[invalid_forecast, "forecast_status"] = "forecast_evidence_missing"
    missing_forecast_provenance = has_forecast_record & ~forecast_provenance
    rows.loc[missing_forecast_provenance, "forecast_status"] = "forecast_provenance_missing"

    rows["result_availability_status"] = "unknown"
    result_provenance = (
        _evidence_present(rows.result_source) & _evidence_present(rows.result_source_version)
    )
    has_result_record = rows.result_available_at.notna() & _evidence_present(rows.result_availability_evidence)
    has_result = has_result_record & result_provenance
    rows.loc[has_result, "result_availability_status"] = "verified"
    result_before_vote = has_result & rows.result_available_at.lt(rows.voting_date)
    rows.loc[result_before_vote, "result_availability_status"] = "invalid_result_publication"
    rows["reported_result_available_at"] = rows.result_available_at
    rows.loc[result_before_vote, "result_available_at"] = pd.NaT
    missing_result_evidence = rows.result_available_at.notna() & ~_evidence_present(rows.result_availability_evidence)
    rows.loc[missing_result_evidence, "result_availability_status"] = "result_evidence_missing"
    rows.loc[has_result_record & ~result_provenance, "result_availability_status"] = "result_provenance_missing"
    return rows


def _attach_evidence_table(
    rows: pd.DataFrame,
    evidence: pd.DataFrame | None,
    columns: tuple[str, ...],
    *,
    prefix: str,
    date_column: str,
    evidence_column: str,
) -> pd.DataFrame:
    result = rows.drop(columns=[date_column, evidence_column], errors="ignore").copy()
    source_column, version_column = f"{prefix}_source", f"{prefix}_source_version"
    if evidence is None:
        result[date_column] = pd.Series(pd.NaT, index=result.index, dtype="datetime64[ns, UTC]")
        result[evidence_column] = pd.NA
        result[source_column] = pd.NA
        result[version_column] = pd.NA
        return result
    missing = set(columns) - set(evidence.columns)
    if missing:
        raise ValueError(f"{prefix} publication evidence missing columns: {sorted(missing)}")
    source = evidence.loc[:, list(columns)].copy()
    source["vote_id"] = source.vote_id.astype("string").str.strip()
    source.loc[source.vote_id.eq(""), "vote_id"] = pd.NA
    if source.vote_id.isna().any():
        raise ValueError(f"{prefix} publication evidence has a missing vote identifier")
    if source.vote_id.duplicated(keep=False).any():
        raise ValueError(f"{prefix} publication evidence has duplicate vote identifiers")
    source[date_column] = pd.to_datetime(source[date_column], errors="coerce", utc=True, format="mixed")
    source[evidence_column] = source[evidence_column].astype("string").str.strip()
    source.loc[source[evidence_column].eq(""), evidence_column] = pd.NA
    for column in (source_column, version_column):
        source[column] = source[column].astype("string").str.strip()
        source.loc[source[column].eq(""), column] = pd.NA
    result["vote_id"] = result.vote_id.astype("string")
    if (date_column in result and result[date_column].notna().any()) or (
        evidence_column in result and result[evidence_column].notna().any()
    ) or (
        source_column in result and result[source_column].notna().any()
    ) or (
        version_column in result and result[version_column].notna().any()
    ):
        raise ValueError(f"Prepared rows already contain {prefix} evidence; refusing to overwrite it")
    result = result.merge(source, how="left", on="vote_id", validate="many_to_one", sort=False)
    return result


def _evidence_present(values: pd.Series) -> pd.Series:
    return values.notna() & values.astype("string").str.strip().ne("").fillna(False)


def select_evidenced_publication(
    records: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    entity: str,
    value_columns: tuple[str, ...],
    geography_mode: str | None = None,
) -> pd.DataFrame:
    """Select the latest evidenced compatible release available at each cutoff.

    ``records`` must contain entity, reference/publication instants, evidence,
    source version, and ``availability_status``. Both reference and publication
    dates must be at or before the forecast instant. When geography is supplied
    on both frames, only equal geography IDs are compatible.
    """
    required = {entity, "reference_date", "published_at", "availability_status",
                "availability_evidence", "source_version", *value_columns}
    if geography_mode is not None:
        if geography_mode not in {"historically_existing", "retrospective_fixed"}:
            raise ValueError("Invalid geography_mode")
        required.add("geography_id")
    missing = required - set(records.columns)
    if missing:
        raise ValueError(f"Feature release missing columns: {sorted(missing)}")
    if {entity, "forecast_at"} - set(observations.columns):
        raise ValueError("Observations require the entity identifier and forecast_at")
    if geography_mode is not None and "geography_id" not in observations:
        raise ValueError("Geographic feature selection requires observation geography_id")

    source = records.copy(deep=True).reset_index(drop=True)
    source[entity] = source[entity].astype("string").str.strip()
    source["reference_date"] = pd.to_datetime(source.reference_date, errors="coerce", utc=True, format="mixed")
    source["published_at"] = pd.to_datetime(source.published_at, errors="coerce", utc=True, format="mixed")
    source["availability_evidence"] = source.availability_evidence.astype("string").str.strip()
    source["source_version"] = source.source_version.astype("string").str.strip()
    if source.duplicated([entity, "reference_date", "published_at", *(["geography_id"] if geography_mode else [])], keep=False).any():
        raise ValueError("Feature releases contain duplicate keys")
    valid = (
        source.reference_date.notna() & source.published_at.notna()
        & source.availability_status.eq("verified")
        & _evidence_present(source.availability_evidence)
        & source.source_version.notna() & source.source_version.ne("")
    )
    if "object_match_status" in source:
        valid &= source.object_match_status.eq("validated")
        if "object_match_evidence" not in source:
            valid &= False
        else:
            valid &= _evidence_present(source.object_match_evidence)
    source["_valid"] = valid
    grouped = {key: group for key, group in source.groupby(entity, sort=False, dropna=False)}  # noqa: C416
    obs = observations.copy(deep=True).reset_index(drop=True)
    obs[entity] = obs[entity].astype("string").str.strip()
    obs["forecast_at"] = pd.to_datetime(obs.forecast_at, errors="coerce", utc=True, format="mixed")
    if geography_mode is not None:
        obs["geography_id"] = obs.geography_id.astype("string")
        source["geography_id"] = source.geography_id.astype("string")

    output = []
    for observation in obs.to_dict(orient="records"):
        candidates = grouped.get(observation.get(entity))
        record = dict(observation)
        if candidates is None:
            output.append(record | {"selection_status": "missing_entity"})
            continue
        if geography_mode is not None:
            candidates = candidates.loc[candidates.geography_id.eq(observation.get("geography_id"))]
            if candidates.empty:
                output.append(record | {"selection_status": "incompatible_geography"})
                continue
        verified = candidates.loc[candidates._valid]
        cutoff = observation.get("forecast_at")
        if pd.isna(cutoff):
            output.append(record | {"selection_status": "unknown_forecast"})
            continue
        timely = verified.loc[verified.published_at.le(cutoff) & verified.reference_date.le(cutoff)]
        if timely.empty:
            status = "unavailable_at_forecast" if not verified.empty else "unknown_availability"
            output.append(record | {"selection_status": status})
            continue
        selected = timely.sort_values(["published_at", "reference_date", "source_version"], kind="stable").iloc[-1]
        for column in set(value_columns) | {
            "reference_date", "published_at", "availability_status", "availability_evidence", "source_version",
        }:
            record[column] = selected[column]
        record["selection_status"] = "matched"
        output.append(record)
    return pd.DataFrame(output)


def prepare_modeling_table(
    outcomes: pd.DataFrame,
    *,
    geography_id: str,
    source_version: str,
    forecast_publications: pd.DataFrame | None,
    result_publications: pd.DataFrame | None = None,
    geography_crosswalk: pd.DataFrame | None = None,
    source_geography_id: str | None = None,
    source_start: str = "2010-01-01",
    feature_blocks: tuple = (),
    geography_mode: str = "retrospective_fixed",
) -> ModelingPreparation:
    """Build the complete prepared table and separately gate strict rows.

    The target result's own publication instant is retained for future history;
    it is not required to precede its own forecast. Missing forecast evidence,
    unresolved preparation statuses and invalid eligibility flags do gate strict
    use. Ordinary missing predictor values are not consulted here.
    """
    base = prepare_base_table(
        outcomes, geography_id=geography_id, source_version=source_version,
        geography_crosswalk=geography_crosswalk, source_geography_id=source_geography_id,
        source_start=source_start,
    )
    prepared = attach_temporal_evidence(base.prepared, forecast_publications, result_publications)
    prepared["geography_status"] = "verified"
    if geography_crosswalk is not None and geography_mode == "historically_existing":
        mapped = prepared.harmonization_applied.fillna(False).astype(bool)
        mapping_available = pd.to_datetime(prepared.mapping_available_at, errors="coerce", utc=True, format="mixed")
        target_valid_from = pd.to_datetime(prepared.target_valid_from, errors="coerce", utc=True, format="mixed")
        target_valid_to = pd.to_datetime(
            prepared.get("target_valid_to", pd.Series(pd.NaT, index=prepared.index)),
            errors="coerce", utc=True, format="mixed",
        )
        known = mapped & mapping_available.notna() & target_valid_from.notna()
        timely = known & mapping_available.le(prepared.forecast_at) & target_valid_from.le(prepared.forecast_at)
        if "target_valid_to" in prepared:
            timely &= target_valid_to.isna() | prepared.forecast_at.lt(target_valid_to)
        prepared.loc[mapped & ~known, "geography_status"] = "unknown_availability"
        prepared.loc[known & ~timely, "geography_status"] = "unavailable_or_not_valid_at_forecast"
    feature_join_report = pd.DataFrame()
    feature_manifests: dict = {}
    feature_coverage: dict = {}
    if feature_blocks:
        from scripts.modeling.feature_blocks import join_feature_blocks

        joined, feature_join_report, feature_manifests, feature_coverage = join_feature_blocks(
            prepared, feature_blocks, geography_mode, retain_unverified=True
        )
        prepared = pd.concat([prepared, joined], axis=1)
    reasons: list[pd.Series] = []

    def exclude(mask: pd.Series, reason: str, source_block: str = "base") -> None:
        mask = mask.fillna(True).astype(bool)
        if mask.any():
            rows = prepared.loc[mask, ["municipality_id", "vote_id", "voting_date"]].copy()
            rows["reason"] = reason
            rows["source_block"] = source_block
            reasons.append(rows)

    exclude(~prepared.preparation_status.eq("ready_for_enrichment"), "base_preparation_unresolved")
    exclude(~prepared.target_period_eligible, "outside_target_period")
    exclude(prepared.target_share.isna(), "target_invalid")
    for flag in ("is_special_unit", "is_subsidiary", "is_provisional"):
        exclude(~prepared[flag].isin([False]), f"ineligible_{flag}")
    exclude(prepared.forecast_status.eq("unknown"), "forecast_evidence_missing")
    exclude(prepared.forecast_status.eq("forecast_evidence_missing"), "forecast_evidence_missing")
    exclude(prepared.forecast_status.eq("forecast_provenance_missing"), "forecast_provenance_missing")
    exclude(prepared.forecast_status.eq("forecast_not_before_vote"), "forecast_not_before_vote")
    exclude(prepared.geography_id.isna() | prepared.geography_id.astype("string").str.strip().eq(""), "geography_missing")
    exclude(prepared.source_version.isna() | prepared.source_version.astype("string").str.strip().eq(""), "source_version_missing")
    exclude(prepared.geography_status.eq("unknown_availability"), "geography_evidence_missing")
    exclude(prepared.geography_status.eq("unavailable_or_not_valid_at_forecast"), "geography_unavailable_at_forecast")
    if not feature_join_report.empty:
        unresolved = feature_join_report.status.isin(
            {"unknown_availability", "unavailable_at_forecast", "incompatible_geography", "skipped"}
        )
        exclude_rows = feature_join_report.loc[
            unresolved, ["municipality_id", "vote_id", "block_id", "status"]
        ].copy()
        if not exclude_rows.empty:
            exclude_rows["reason"] = "feature_" + exclude_rows.pop("status").astype(str)
            exclude_rows["source_block"] = exclude_rows.pop("block_id")
            reasons.append(exclude_rows)

    excluded = pd.concat(reasons, ignore_index=True) if reasons else pd.DataFrame(
        columns=["municipality_id", "vote_id", "voting_date", "reason", "source_block"]
    )
    # Use a row-level gate assembled independently from the long exclusion log.
    strict_mask = (
        prepared.preparation_status.eq("ready_for_enrichment")
        & prepared.target_period_eligible
        & prepared.target_share.notna()
        & prepared.is_special_unit.eq(False)
        & prepared.is_subsidiary.eq(False)
        & prepared.is_provisional.eq(False)
        & prepared.forecast_status.eq("verified")
        & prepared.geography_status.eq("verified")
        & prepared.geography_id.notna()
        & prepared.source_version.notna()
    )
    if not feature_join_report.empty:
        blocked = feature_join_report.loc[
            feature_join_report.status.isin(
                {"unknown_availability", "unavailable_at_forecast", "incompatible_geography", "skipped"}
            ), ["municipality_id", "vote_id"]
        ].drop_duplicates()
        if not blocked.empty:
            blocked_keys = pd.MultiIndex.from_frame(blocked)
            prepared_keys = pd.MultiIndex.from_frame(prepared[["municipality_id", "vote_id"]])
            strict_mask &= ~prepared_keys.isin(blocked_keys)
    strict_population = prepared.loc[strict_mask].copy().reset_index(drop=True)
    if not strict_population.empty:
        strict_population["voting_date"] = pd.to_datetime(strict_population.voting_date, utc=True).dt.normalize()
    exclusions = excluded.sort_values(["vote_id", "municipality_id", "reason"], kind="stable").reset_index(drop=True)
    readiness = {
        "status": "ready" if len(strict_population) else "strict_population_empty",
        "prepared_rows": len(prepared),
        "strict_population_rows": len(strict_population),
        "strict_objects": int(strict_population.vote_id.nunique()),
        "strict_dates": int(strict_population.voting_date.nunique()),
        "target_period": base.coverage["target_period"],
        "forecast_status": {str(key): int(value) for key, value in prepared.forecast_status.value_counts(dropna=False).sort_index().items()},
        "result_availability_status": {str(key): int(value) for key, value in prepared.result_availability_status.value_counts(dropna=False).sort_index().items()},
        "geography_status": {str(key): int(value) for key, value in prepared.geography_status.value_counts(dropna=False).sort_index().items()},
        "source_version": source_version,
        "source_geography_reference": base.join_report["source_geography_reference"],
        "target_geography_reference": base.join_report["target_geography_reference"],
        "exclusions_by_reason": {str(key): int(value) for key, value in exclusions.reason.value_counts().sort_index().items()},
        "exclusions_by_source_block": {
            str(block): {str(reason): int(count) for reason, count in group.reason.value_counts().sort_index().items()}
            for block, group in exclusions.groupby("source_block", dropna=False, sort=True)
        } if not exclusions.empty else {},
        "availability_by_vote": prepared.groupby("vote_id", dropna=False, sort=True).agg(
            rows=("municipality_id", "size"), voting_date=("voting_date", "first"),
            forecast_status=("forecast_status", "first"),
            result_availability_status=("result_availability_status", "first"),
            geography_status=("geography_status", "first"),
        ).reset_index().assign(
            vote_id=lambda frame: frame.vote_id.astype("string").fillna(""),
            voting_date=lambda frame: frame.voting_date.astype(str),
        ).to_dict("records"),
        "strict_dates_are_complete_vote_dates": True,
        "partitions": None,
        "partition_status": "not_configured; boundaries await eligible-coverage audit",
        "final_test_used": False,
        "feature_blocks": feature_coverage,
        "feature_manifests": feature_manifests,
    }
    return ModelingPreparation(
        prepared, strict_population, exclusions, readiness, base,
        feature_join_report, feature_manifests, feature_coverage,
    )


def write_modeling_artifacts(
    result: ModelingPreparation,
    *,
    prepared_path: Path = MODEL_OUTPUT,
    strict_path: Path = STRICT_OUTPUT,
    readiness_path: Path = READINESS_OUTPUT,
    exclusions_path: Path = EXCLUSION_OUTPUT,
    feature_report_path: Path = FEATURE_REPORT_OUTPUT,
) -> None:
    """Write deterministic artifacts without editing source files."""
    prepared_path.parent.mkdir(parents=True, exist_ok=True)
    strict_path.parent.mkdir(parents=True, exist_ok=True)
    readiness_path.parent.mkdir(parents=True, exist_ok=True)
    exclusions_path.parent.mkdir(parents=True, exist_ok=True)
    feature_report_path.parent.mkdir(parents=True, exist_ok=True)
    result.prepared.to_parquet(prepared_path, index=False)
    result.strict_population.to_parquet(strict_path, index=False)
    readiness_path.write_text(json.dumps(result.readiness, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    result.exclusions.to_csv(exclusions_path, index=False)
    result.feature_join_report.to_csv(feature_report_path, index=False)


def main() -> None:
    import argparse

    from scripts.integration.prepare_modeling import CLEAN_PATH

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=CLEAN_PATH, help="Cleaned OFS commune outcomes")
    parser.add_argument("--forecast-evidence", type=Path, help="CSV with vote_id,forecast_at,forecast_evidence")
    parser.add_argument("--result-evidence", type=Path, help="CSV with vote_id,result_available_at,result_availability_evidence")
    parser.add_argument("--geography-id", default="BFS commune register 2026-01-01")
    parser.add_argument("--source-version", default="OFS PX px-x-1703030000_101; retrieved 2026-09-29")
    parser.add_argument("--blocks", type=Path, help="Optional JSON manifest of prepared FeatureBlock descriptors")
    parser.add_argument("--output", type=Path, default=MODEL_OUTPUT)
    parser.add_argument("--strict-output", type=Path, default=STRICT_OUTPUT)
    parser.add_argument("--readiness-report", type=Path, default=READINESS_OUTPUT)
    parser.add_argument("--exclusions", type=Path, default=EXCLUSION_OUTPUT)
    parser.add_argument("--feature-report", type=Path, default=FEATURE_REPORT_OUTPUT)
    parser.add_argument("--geography-mode", choices=("historically_existing", "retrospective_fixed"),
                        default="retrospective_fixed")
    args = parser.parse_args()
    if args.input.suffix == ".parquet":
        outcomes = pd.read_parquet(args.input)
    else:
        outcomes = pd.read_csv(args.input, dtype={"municipality_id": "string", "vote_id": "string"})
    forecasts = pd.read_csv(args.forecast_evidence, dtype={"vote_id": "string"}) if args.forecast_evidence else None
    results = pd.read_csv(args.result_evidence, dtype={"vote_id": "string"}) if args.result_evidence else None
    if args.blocks:
        from scripts.modeling.feature_blocks import load_feature_blocks

        feature_blocks = load_feature_blocks(args.blocks)
    else:
        feature_blocks = ()
    result = prepare_modeling_table(
        outcomes, geography_id=args.geography_id, source_version=args.source_version,
        forecast_publications=forecasts, result_publications=results,
        geography_mode=args.geography_mode, feature_blocks=feature_blocks,
    )
    write_modeling_artifacts(
        result, prepared_path=args.output, strict_path=args.strict_output,
        readiness_path=args.readiness_report, exclusions_path=args.exclusions,
        feature_report_path=args.feature_report,
    )
    print(json.dumps({
        "status": result.readiness["status"],
        "prepared_rows": result.readiness["prepared_rows"],
        "strict_population_rows": result.readiness["strict_population_rows"],
        "readiness_report": str(args.readiness_report),
    }, indent=2))


if __name__ == "__main__":
    main()
