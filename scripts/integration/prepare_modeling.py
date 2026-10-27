"""Build the auditable municipal voting table foundation.

The command intentionally prepares observations and provenance only. Temporal
availability and feature blocks are added by later preparation stages.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import PROCESSED_DIR, REPORTS_DIR
from scripts.common.vote_keys import ofs_keys
from scripts.ofs_votes.clean_ofs_votes import CLEAN_PATH

TARGET_START = pd.Timestamp("2012-01-01", tz="UTC")
TARGET_END = pd.Timestamp("2026-01-01", tz="UTC")
OUTPUT_PATH = PROCESSED_DIR / "modeling" / "prepared_municipal_voting_base.parquet"
REPORT_PATH = REPORTS_DIR / "modeling" / "base_preparation.json"
REQUIRED_OUTCOME_COLUMNS = {
    "municipality_id", "vote_id", "vote_date", "votes_yes", "votes_no",
    "is_special_unit", "is_tiebreak_question", "is_provisional",
}


@dataclass(frozen=True)
class BasePreparation:
    """Prepared base table and machine-readable audit products."""

    prepared: pd.DataFrame
    exclusions: pd.DataFrame
    join_report: dict
    coverage: dict


def prepare_base_table(
    outcomes: pd.DataFrame,
    *,
    geography_id: str,
    source_version: str,
    geography_crosswalk: pd.DataFrame | None = None,
    source_geography_id: str | None = None,
    source_start: str = "2010-01-01",
) -> BasePreparation:
    """Prepare one municipality × vote row, preserving unresolved rows for audit.

    `geography_crosswalk`, when supplied, maps source municipal codes to a
    retrospective reference. Supported mapping types are unchanged/recoded and
    complete merges. Splits remain in the output with an exclusion status.
    """
    missing = REQUIRED_OUTCOME_COLUMNS - set(outcomes.columns)
    if missing:
        raise ValueError(f"Outcomes missing required columns: {sorted(missing)}")
    if not geography_id.strip() or not source_version.strip():
        raise ValueError("geography_id and source_version must be nonempty")
    source_start_at = pd.to_datetime(source_start, utc=True)

    rows = outcomes.copy(deep=True)
    if "harmonization_applied" in rows and rows.harmonization_applied.fillna(False).astype(bool).any():
        if geography_crosswalk is not None:
            raise ValueError("Cannot apply a geography crosswalk to already harmonized outcomes")
    rows["_input_order"] = np.arange(len(rows))
    rows["preparation_status"] = "ready_for_enrichment"
    rows["voting_date"] = pd.to_datetime(rows.pop("vote_date"), errors="coerce", utc=True, format="mixed").dt.normalize()
    before_source_start = rows.voting_date.notna() & rows.voting_date.lt(source_start_at)
    excluded_before_source_start = int(before_source_start.sum())
    rows = rows.loc[~before_source_start].copy()
    for name in ("municipality_id", "vote_id"):
        rows[name] = rows[name].astype("string").str.strip()
        rows.loc[rows[name].eq(""), name] = pd.NA
    rows["municipality_id"] = rows.municipality_id.map(_normalize_municipality_code).astype("string")
    try:
        rows["vote_id"] = ofs_keys(rows["vote_id"])
    except ValueError:
        valid_vote_id = rows.vote_id.str.fullmatch(r"[1-9][0-9]*", na=False)
        rows.loc[~valid_vote_id, "vote_id"] = pd.NA
        rows.loc[~valid_vote_id, "preparation_status"] = "invalid_identifier"
    rows["yes_count"] = pd.to_numeric(rows.pop("votes_yes"), errors="coerce")
    rows["no_count"] = pd.to_numeric(rows.pop("votes_no"), errors="coerce")
    if geography_crosswalk is not None and not source_geography_id:
        raise ValueError("source_geography_id is required when a geography crosswalk is supplied")
    if "geography_id" not in rows:
        rows["geography_id"] = source_geography_id or geography_id
    elif geography_crosswalk is not None:
        rows["geography_id"] = source_geography_id
    if "source_geography_id" not in rows:
        already_harmonized = ("harmonization_applied" in rows
                              and rows.harmonization_applied.fillna(False).astype(bool).any())
        rows["source_geography_id"] = pd.NA if already_harmonized and geography_crosswalk is None else (
            source_geography_id or geography_id
        )
    if "source_version" not in rows:
        rows["source_version"] = source_version
    else:
        rows["source_version"] = rows.source_version.fillna(source_version).astype("string")
    rows["is_subsidiary"] = rows.pop("is_tiebreak_question").astype("boolean")

    # Keep a single evidence schema compatible with evaluate_votes.REQUIRED.
    rows["forecast_at"] = pd.NaT
    rows["forecast_evidence"] = pd.NA
    rows["result_available_at"] = pd.NaT
    rows["result_availability_evidence"] = pd.NA
    rows["target_share"] = np.nan
    if "harmonization_applied" not in rows:
        rows["harmonization_applied"] = False
    if "crosswalk_version" not in rows:
        rows["crosswalk_version"] = pd.NA
    if "crosswalk_evidence" not in rows:
        rows["crosswalk_evidence"] = pd.NA
    rows["target_period_eligible"] = False

    source_duplicate = rows.duplicated(["municipality_id", "vote_id"], keep=False)
    rows.loc[source_duplicate, "preparation_status"] = "duplicate_key"
    rows["_source_counts_valid"] = (
        np.isfinite(rows.yes_count) & np.isfinite(rows.no_count)
        & rows.yes_count.ge(0) & rows.no_count.ge(0)
        & rows.yes_count.mod(1).eq(0) & rows.no_count.mod(1).eq(0)
        & (rows.yes_count + rows.no_count).gt(0)
    )
    if geography_crosswalk is not None:
        rows = _apply_base_geography(rows, geography_crosswalk, source_geography_id, geography_id)

    duplicate = rows.duplicated(["municipality_id", "vote_id"], keep=False)
    rows.loc[duplicate, "preparation_status"] = "duplicate_key"
    conflicting_vote_dates = rows.groupby("vote_id", dropna=True).voting_date.nunique(dropna=True).gt(1)
    conflicting_votes = set(conflicting_vote_dates.index[conflicting_vote_dates])
    rows.loc[rows.vote_id.isin(conflicting_votes), "preparation_status"] = "conflicting_object_date"
    missing_key = rows.municipality_id.isna() | rows.vote_id.isna()
    rows.loc[missing_key, "preparation_status"] = "missing_identifier"
    missing_date = rows.voting_date.isna()
    rows.loc[missing_date & ~missing_key, "preparation_status"] = "invalid_voting_date"

    denominator = rows.yes_count + rows.no_count
    valid_counts = (np.isfinite(rows.yes_count) & np.isfinite(rows.no_count)
                    & rows.yes_count.ge(0) & rows.no_count.ge(0) & denominator.gt(0))
    valid_counts &= rows.yes_count.mod(1).eq(0) & rows.no_count.mod(1).eq(0)
    invalid_target = ~valid_counts
    rows.loc[invalid_target & ~missing_key & ~missing_date & ~duplicate
             & ~rows.preparation_status.eq("conflicting_object_date"),
             "preparation_status"] = "invalid_target"
    rows["target_share"] = (rows.yes_count / denominator.where(valid_counts)).astype(float)
    rows.loc[rows.preparation_status.isin(["duplicate_key", "conflicting_object_date"]), "target_share"] = np.nan

    rows["target_period_eligible"] = rows.voting_date.ge(TARGET_START) & rows.voting_date.lt(TARGET_END)
    for flag, reason in (("is_special_unit", "special_unit"), ("is_subsidiary", "subsidiary"),
                         ("is_provisional", "provisional")):
        known = rows[flag].isin([True, False])
        rows.loc[~known & rows.preparation_status.eq("ready_for_enrichment"), "preparation_status"] = f"unknown_{flag}"
        rows.loc[rows[flag].eq(True) & rows.preparation_status.eq("ready_for_enrichment"), "preparation_status"] = reason

    # Rows outside the target window remain available as possible historical
    # context; only target_period_eligible controls the provisional target scope.
    rows = rows.drop(columns="_input_order").sort_values(
        ["voting_date", "vote_id", "municipality_id"], na_position="last", kind="stable"
    ).reset_index(drop=True)
    rows = rows.drop(columns="_source_counts_valid", errors="ignore")
    exclusions = (rows.groupby("preparation_status", dropna=False).size()
                  .rename("rows").reset_index().sort_values("preparation_status").reset_index(drop=True))
    join_report = {
        "status": "PASS" if not rows.duplicated(["municipality_id", "vote_id"], keep=False).any() else "AUDIT_REQUIRED",
        "input_rows": len(outcomes), "prepared_rows": len(rows),
        "rows_before_source_start": excluded_before_source_start,
        "source_start_inclusive": source_start_at.isoformat(),
        "geography_reference": geography_id,
        "source_geography_reference": source_geography_id or geography_id,
        "target_geography_reference": geography_id,
        "geography_mapping_rows": 0 if geography_crosswalk is None else len(geography_crosswalk),
        "geography_mapping_applied": int(rows.harmonization_applied.sum()),
        "unresolved_rows": int((~rows.preparation_status.eq("ready_for_enrichment")).sum()),
    }
    coverage = {
        "input_rows": len(outcomes), "prepared_rows": len(rows),
        "rows_before_source_start": excluded_before_source_start,
        "source_start_inclusive": source_start_at.isoformat(),
        "unique_municipalities": int(rows.municipality_id.nunique(dropna=True)),
        "unique_objects": int(rows.vote_id.nunique(dropna=True)),
        "unique_dates": int(rows.voting_date.nunique(dropna=True)),
        "target_period": {"start_inclusive": TARGET_START.isoformat(), "end_exclusive": TARGET_END.isoformat(),
                          "rows": int(rows.target_period_eligible.sum()),
                          "objects": int(rows.loc[rows.target_period_eligible, "vote_id"].nunique())},
        "preparation_status": {str(row.preparation_status): int(row.rows) for row in exclusions.itertuples()},
        "by_object": _coverage_by(rows, "vote_id"),
        "by_date": _coverage_by(rows, "voting_date"),
    }
    return BasePreparation(rows, exclusions, join_report, coverage)


def _coverage_by(rows: pd.DataFrame, key: str) -> dict:
    """Counts and status breakdown for each object or complete voting date."""
    coverage = {}
    for value, group in rows.dropna(subset=[key]).groupby(key, sort=True):
        label = value.isoformat() if isinstance(value, pd.Timestamp) else str(value)
        coverage[label] = {
            "rows": int(len(group)),
            "municipalities": int(group.municipality_id.nunique(dropna=True)),
            "objects": int(group.vote_id.nunique(dropna=True)),
            "preparation_status": {str(status): int(count) for status, count in
                                   group.preparation_status.value_counts(dropna=False).sort_index().items()},
        }
    return coverage


def _normalize_municipality_code(value):
    if pd.isna(value):
        return pd.NA
    code = str(value).strip()
    if code.isdigit():
        return str(int(code))
    return code or pd.NA


def _apply_base_geography(rows: pd.DataFrame, crosswalk: pd.DataFrame,
                          source_geography_id: str, target_geography_id: str) -> pd.DataFrame:
    required = {"source_municipality_id", "target_municipality_id", "mapping_type",
                "source_geography_id", "target_geography_id", "crosswalk_version", "crosswalk_evidence",
                "mapping_available_at", "target_valid_from"}
    missing = required - set(crosswalk.columns)
    if missing:
        raise ValueError(f"Geography crosswalk missing columns: {sorted(missing)}")
    mapping = crosswalk[sorted(required)].copy().rename(columns={
        "crosswalk_version": "_crosswalk_version", "crosswalk_evidence": "_crosswalk_evidence",
        "source_geography_id": "_source_geography_id", "target_geography_id": "_target_geography_id",
    })
    for column in ("source_municipality_id", "target_municipality_id", "mapping_type",
                   "_source_geography_id", "_target_geography_id", "_crosswalk_version", "_crosswalk_evidence"):
        mapping[column] = mapping[column].astype("string").str.strip()
    mapping["source_municipality_id"] = mapping.source_municipality_id.map(_normalize_municipality_code).astype("string")
    mapping["target_municipality_id"] = mapping.target_municipality_id.map(_normalize_municipality_code).astype("string")
    declared_split_sources = set(mapping.loc[mapping.mapping_type.eq("split"), "source_municipality_id"])
    if mapping[["source_municipality_id", "target_municipality_id", "mapping_type", "_source_geography_id",
                "_target_geography_id", "_crosswalk_version", "_crosswalk_evidence"]].isna().any().any():
        raise ValueError("Geography crosswalk identifiers and provenance must be nonempty")
    if not mapping._source_geography_id.eq(source_geography_id).all() or not mapping._target_geography_id.eq(target_geography_id).all():
        raise ValueError("Geography crosswalk source/target references do not match requested geography")
    if mapping._source_geography_id.eq(mapping._target_geography_id).any():
        raise ValueError("Geography crosswalk cannot map within the same reference")
    mapping_key = ["source_municipality_id", "_source_geography_id"]
    ambiguous_mask = mapping.duplicated(mapping_key, keep=False)
    if ambiguous_mask.any():
        by_source = mapping.loc[ambiguous_mask].groupby(mapping_key, dropna=False)
        valid_splits = set()
        invalid_sources = set()
        for key, group in by_source:
            if (group.mapping_type.eq("split").all() and not group.target_municipality_id.duplicated().any()
                    and not group.duplicated().any()):
                valid_splits.add(key[0])
            else:
                invalid_sources.add(key[0])
        ambiguous = invalid_sources
        rows.loc[rows.municipality_id.isin(ambiguous), "preparation_status"] = "ambiguous_geography_mapping"
        mapping = mapping.loc[~mapping.source_municipality_id.isin(ambiguous | valid_splits)]
    supported_types = {"identity", "merger"}
    for target_key, group in mapping.groupby(["target_municipality_id", "_target_geography_id"], sort=True):
        supported = group.loc[group.mapping_type.isin(supported_types)]
        if len(supported) > 1 and not supported.mapping_type.eq("merger").all():
            raise ValueError("Many-to-one geography target requires explicit merger mappings")
        if group.mapping_type.eq("merger").any() and not group.mapping_type.eq("merger").all():
            raise ValueError("Geography merger target cannot mix identity and merger mappings")
        for provenance_column in ("_crosswalk_version", "_crosswalk_evidence", "mapping_available_at",
                                  "target_valid_from", "target_valid_to"):
            if provenance_column in group and group[provenance_column].nunique(dropna=False) > 1:
                raise ValueError("Geography constituents have conflicting version, evidence, or validity provenance")
        for date_column in ("target_valid_from", "target_valid_to"):
            if date_column in group and group[date_column].nunique(dropna=False) > 1:
                raise ValueError("Geography merger constituents have conflicting target validity")
        if group.mapping_type.eq("merger").any() and len(group) < 2:
            raise ValueError("A geography merger must declare at least two source constituents")
    for date_column in ("mapping_available_at", "target_valid_from", "target_valid_to"):
        if date_column in mapping:
            mapping[date_column] = pd.to_datetime(mapping[date_column], errors="coerce", utc=True, format="mixed")
    split_sources = declared_split_sources
    rows.loc[rows.municipality_id.isin(split_sources)
             & rows.preparation_status.eq("ready_for_enrichment"), "preparation_status"] = "unsupported_geography_mapping"
    mapping = mapping.loc[~mapping.mapping_type.eq("split")].copy()
    duplicate_keys = rows.duplicated(["municipality_id", "vote_id"], keep=False)
    rows.loc[duplicate_keys, "preparation_status"] = "duplicate_key"
    merged = rows.merge(mapping, how="left", left_on="municipality_id", right_on="source_municipality_id",
                        validate="many_to_one", indicator=True, suffixes=("", "_crosswalk"))
    absent = merged._merge.eq("left_only")
    merged.loc[absent & merged.preparation_status.eq("ready_for_enrichment"), "preparation_status"] = "geography_mapping_missing"
    unsupported = merged._merge.eq("both") & ~merged.mapping_type.isin(supported_types)
    merged.loc[unsupported & merged.preparation_status.eq("ready_for_enrichment"), "preparation_status"] = "unsupported_geography_mapping"
    merged["_original_municipality_id"] = merged.municipality_id

    merger_targets = mapping.loc[mapping.mapping_type.eq("merger")].groupby(
        ["target_municipality_id", "_target_geography_id"], sort=True
    ).source_municipality_id.agg(lambda values: frozenset(values))
    if merger_targets.empty:
        merger_target_by_key = {}
    else:
        merger_target_by_key = {key: expected for key, expected in merger_targets.items()}
    merged["_target_key"] = list(zip(merged.target_municipality_id, merged._target_geography_id))
    merged["_expected_constituents"] = merged._target_key.map(merger_target_by_key)
    is_merger = merged.mapping_type.eq("merger") & merged._merge.eq("both")

    # Validate each object against the complete declared source set before any
    # aggregation. Duplicate source rows, missing constituents, bad counts or
    # inconsistent metadata keep source rows separate for inspection.
    metadata_columns = ["voting_date", "is_special_unit", "is_subsidiary", "is_provisional", "source_version"]
    bad_merge_keys = set()
    conflict_keys = set()
    incomplete_keys = set()
    for (vote_id, target_id, target_geo), group in merged.loc[is_merger].groupby(
            ["vote_id", "target_municipality_id", "_target_geography_id"], dropna=False, sort=False):
        key = (vote_id, target_id, target_geo)
        expected = merger_target_by_key.get((target_id, target_geo), frozenset())
        actual_values = group._original_municipality_id.astype(str)
        actual = set(actual_values)
        duplicate_source = actual_values.duplicated(keep=False).any()
        if duplicate_source or actual != set(expected):
            incomplete_keys.add(key)
        elif not group._source_counts_valid.all():
            bad_merge_keys.add(key)
        elif any(group[column].nunique(dropna=False) > 1 for column in metadata_columns):
            conflict_keys.add(key)
    merge_key_series = list(zip(merged.vote_id, merged.target_municipality_id, merged._target_geography_id))
    keys = pd.Series(merge_key_series, index=merged.index)
    incomplete_mask = is_merger & keys.isin(incomplete_keys)
    invalid_mask = is_merger & keys.isin(bad_merge_keys)
    conflict_mask = is_merger & keys.isin(conflict_keys)
    preserve_mask = incomplete_mask | invalid_mask | conflict_mask
    merged.loc[incomplete_mask & merged.preparation_status.eq("ready_for_enrichment"),
               "preparation_status"] = "incomplete_geography_merger"
    merged.loc[invalid_mask, "preparation_status"] = "invalid_target"
    merged.loc[conflict_mask & merged.preparation_status.eq("ready_for_enrichment"),
               "preparation_status"] = "conflicting_merger_metadata"

    supported = merged._merge.eq("both") & merged.mapping_type.isin(supported_types) & ~preserve_mask
    merged.loc[supported, "municipality_id"] = merged.loc[supported, "target_municipality_id"]
    merged.loc[supported, "geography_id"] = merged.loc[supported, "_target_geography_id"]
    merged.loc[supported, "harmonization_applied"] = True
    merged.loc[supported, "crosswalk_version"] = merged.loc[supported, "_crosswalk_version"]
    merged.loc[supported, "crosswalk_evidence"] = merged.loc[supported, "_crosswalk_evidence"]
    merged.loc[preserve_mask, "geography_id"] = source_geography_id
    merged = merged.drop(columns=["_merge"])

    mapped_mergers = is_merger & ~preserve_mask
    merger = mapped_mergers
    if merger.any():
        passthrough = merged.loc[~merger].copy()
        merged_rows = merged.loc[merger].copy()
        aggregated = merged_rows.groupby(["vote_id", "municipality_id", "geography_id"], dropna=False, sort=False).agg(
            yes_count=("yes_count", lambda values: values.sum(min_count=1)),
            no_count=("no_count", lambda values: values.sum(min_count=1)),
            source_municipality_ids=("_original_municipality_id", lambda values: "|".join(sorted(values.astype(str)))),
        ).reset_index()
        first = merged_rows.drop_duplicates(["vote_id", "municipality_id", "geography_id"]).drop(
            columns=["yes_count", "no_count", "_original_municipality_id", "_target_key", "_expected_constituents"]
        )
        merged = pd.concat([passthrough.drop(columns=["_target_key", "_expected_constituents"]),
                            first.merge(aggregated, on=["vote_id", "municipality_id", "geography_id"],
                                        validate="one_to_one")], ignore_index=True)
    else:
        merged = merged.drop(columns=["_target_key", "_expected_constituents"])
    merged["target_share"] = merged.yes_count / (merged.yes_count + merged.no_count).where(
        (merged.yes_count + merged.no_count).gt(0)
    )
    return merged.drop(columns=["_crosswalk_version", "_crosswalk_evidence", "_original_municipality_id",
                                "mapping_type", "source_municipality_id", "target_municipality_id",
                                "_source_geography_id", "_target_geography_id"], errors="ignore")


def write_base_artifacts(result: BasePreparation, output_path: Path = OUTPUT_PATH,
                         report_path: Path = REPORT_PATH) -> None:
    """Write sorted prepared rows, coverage and exclusions without changing source files."""
    import json

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    result.prepared.to_parquet(output_path, index=False)
    report_path.write_text(json.dumps({"join": result.join_report, "coverage": result.coverage,
                                      "exclusions": result.exclusions.to_dict(orient="records")},
                                     indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=CLEAN_PATH, help="Cleaned OFS outcomes parquet")
    parser.add_argument("--geography-id", required=True, help="Verified source or target geography reference")
    parser.add_argument("--source-geography-id", help="Required source reference when using a crosswalk")
    parser.add_argument("--source-version", required=True, help="Version/provenance label for the input")
    parser.add_argument("--source-start", default="2010-01-01", help="Inclusive floor for current source/history scope")
    parser.add_argument("--geography-crosswalk", type=Path, help="Optional validated crosswalk CSV")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    outcomes = pd.read_parquet(args.input)
    crosswalk = pd.read_csv(args.geography_crosswalk, dtype="string") if args.geography_crosswalk else None
    result = prepare_base_table(outcomes, geography_id=args.geography_id,
                                source_version=args.source_version, geography_crosswalk=crosswalk,
                                source_geography_id=args.source_geography_id,
                                source_start=args.source_start)
    write_base_artifacts(result, args.output, args.report)
    print(f"Prepared {len(result.prepared):,} rows; see {args.report}")


if __name__ == "__main__":
    main()
