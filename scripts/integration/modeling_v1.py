"""Assemble the thirty V1 candidates and export an auditable preparation bundle."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.integration.modeling_objects import DOMAIN_COLUMNS, ObjectFeaturePreparation
from scripts.integration.modeling_temporal import prepare_modeling_table

MUNICIPAL_FEATURES = (
    "population_total", "share_foreign", "share_age_0_19", "share_age_20_39",
    "share_age_65_plus", "canton", "language_region", "urban_rural_type",
)
HISTORY_FEATURES = tuple(
    prefix + suffix for prefix in ("history", "history_5y", "history_same_domain")
    for suffix in ("_yes_mean", "_vote_count", "_missing")
)
CANDIDATE_FEATURES = MUNICIPAL_FEATURES + HISTORY_FEATURES + ("legal_form",) + DOMAIN_COLUMNS


@dataclass(frozen=True)
class V1Preparation:
    prepared: pd.DataFrame
    strict_population: pd.DataFrame
    exclusions: pd.DataFrame
    join_report: pd.DataFrame
    history_report: pd.DataFrame
    coverage: dict
    readiness: dict
    manifest: dict
    feature_blocks: tuple
    domain_records: pd.DataFrame
    candidate_columns: tuple[str, ...] = CANDIDATE_FEATURES


def prepare_v1_table(
    outcomes: pd.DataFrame, *, geography_id: str, source_version: str,
    municipal_blocks: tuple, object_features: ObjectFeaturePreparation,
    forecast_publications: pd.DataFrame | None = None,
    result_publications: pd.DataFrame | None = None,
    history_config=None, source_start: str = "2010-01-01",
    source_audit: dict | None = None,
) -> V1Preparation:
    """Prepare rows without fitting models or choosing chronological boundaries.

    Canonical candidate columns alias explicit source-block allowlists. History
    columns are diagnostic until an evaluation recomputes them with its policy.
    """
    blocks = tuple(municipal_blocks) + (object_features.feature_block,)
    aliases = {}
    for block in blocks:
        for name in block.numeric_features + block.categorical_features:
            if name not in MUNICIPAL_FEATURES + ("legal_form",) + DOMAIN_COLUMNS:
                raise ValueError(f"Feature outside V1 candidate allowlist: {name}")
            if name in aliases:
                raise ValueError(f"V1 candidate supplied by multiple blocks: {name}")
            aliases[name] = f"{block.block_id}__{name}"
    required = set(MUNICIPAL_FEATURES + ("legal_form",) + DOMAIN_COLUMNS)
    if set(aliases) != required:
        raise ValueError(f"V1 source blocks missing candidates: {sorted(required - set(aliases))}")
    preparation = prepare_modeling_table(
        outcomes, geography_id=geography_id, source_version=source_version,
        forecast_publications=forecast_publications, result_publications=result_publications,
        source_start=source_start, feature_blocks=blocks, geography_mode="retrospective_fixed",
    )
    prepared = preparation.prepared.copy()
    for name, column in aliases.items():
        prepared[name] = prepared[column]
    if history_config is None:
        for name in HISTORY_FEATURES:
            prepared[name] = float("nan")
        history_report = prepared[["municipality_id", "vote_id"]].copy()
        history_report["status"] = "not_configured"
        history_report["reason"] = "Chronological partitions and history policy await eligible-coverage audit"
        history_manifest = None
    else:
        from scripts.voting_history import build_v1_history_features

        _validate_partitions(history_config)
        history = build_v1_history_features(
            prepared, prepared, history_config, domain_records=object_features.domain_metadata,
        )
        for column in history:
            prepared[column] = history[column]
        history_report = pd.concat([
            prepared[["municipality_id", "vote_id"]], history.drop(columns=list(HISTORY_FEATURES)),
        ], axis=1)
        history_manifest = asdict(history_config)
    strict_keys = pd.MultiIndex.from_frame(preparation.strict_population[["municipality_id", "vote_id"]])
    strict_mask = pd.Series(pd.MultiIndex.from_frame(prepared[["municipality_id", "vote_id"]]).isin(strict_keys), index=prepared.index)
    if history_config is None:
        history_ok = pd.Series(False, index=prepared.index)
        history_reason = "history_policy_not_configured"
    else:
        history_ok = prepared[[f"{prefix}_status" for prefix in (
            "history", "history_5y", "history_same_domain",
        )]].isin(["known", "no_antecedents"]).all(axis=1)
        history_reason = "history_unresolved"
    history_exclusions = prepared.loc[~history_ok, ["municipality_id", "vote_id", "voting_date"]].assign(
        reason=history_reason, source_block="history",
    )
    exclusion_parts = [part for part in (preparation.exclusions, history_exclusions) if not part.empty]
    exclusions = (pd.concat(exclusion_parts, ignore_index=True) if exclusion_parts else preparation.exclusions.copy()).sort_values(
        ["vote_id", "municipality_id", "reason"], kind="stable",
    ).reset_index(drop=True)
    strict = prepared.loc[strict_mask & history_ok].copy()
    readiness = dict(preparation.readiness)
    readiness.update(status="ready" if len(strict) else "strict_population_empty",
                     strict_population_rows=len(strict), strict_objects=int(strict.vote_id.nunique()),
                     strict_dates=int(strict.voting_date.nunique()))
    readiness["exclusion_reasons"] = {str(key): int(value) for key, value in exclusions.reason.value_counts().sort_index().items()}
    readiness["history_status"] = "not_configured" if history_config is None else "diagnostic; evaluator recomputes"
    readiness["modeling_ready"] = bool(len(strict) and history_config is not None)
    readiness["candidate_feature_count"] = 30
    readiness["final_test_used"] = False
    coverage = {
        "base": preparation.base.coverage,
        "blocks": preparation.feature_coverage,
        "by_object": _group_coverage(prepared, "vote_id"),
        "by_date": _group_coverage(prepared, "voting_date"),
    }
    manifest = {
        "schema": "swiss-voting.modeling-v1", "source_start": source_start,
        "source_version": source_version, "geography_id": geography_id,
        "geography_mode": "retrospective_fixed", "candidate_features": list(CANDIDATE_FEATURES),
        "feature_aliases": aliases, "feature_blocks": preparation.feature_manifests,
        "source_audit": source_audit or {}, "history_config": history_manifest,
        "partitions": None if history_config is None else {
            name: list(getattr(history_config, f"{name}_dates")) for name in ("train", "validation", "test")
        },
        "history_values": "diagnostic; recompute inside evaluator for every fold and policy",
        "final_test_used": False,
        "input_sha256": hashlib.sha256(outcomes.to_json(orient="split", date_format="iso").encode()).hexdigest(),
    }
    return V1Preparation(
        prepared, strict.reset_index(drop=True), exclusions,
        preparation.feature_join_report, history_report, coverage, readiness, manifest,
        blocks, object_features.domain_metadata,
    )


def _validate_partitions(config) -> None:
    groups = [pd.to_datetime(list(getattr(config, f"{name}_dates")), utc=True).normalize()
              for name in ("train", "validation", "test")]
    dates = [date for group in groups for date in group]
    if any(len(group) == 0 or group.isna().any() for group in groups):
        raise ValueError("All three history partitions must declare valid complete dates")
    if len(dates) != len(set(dates)):
        raise ValueError("History partition dates must be disjoint and unique")
    if not (max(groups[0]) < min(groups[1]) and max(groups[1]) < min(groups[2])):
        raise ValueError("History partitions must be chronological")
    if config.history_policy not in ("frozen", "rolling"):
        raise ValueError("History policy must be frozen or rolling")


def _group_coverage(rows: pd.DataFrame, key: str) -> dict:
    result = {}
    for value, group in rows.groupby(key, sort=True, dropna=True):
        label = value.isoformat() if isinstance(value, pd.Timestamp) else str(value)
        result[label] = {
            "rows": len(group), "municipalities": int(group.municipality_id.nunique()),
            "missing_candidates": {name: int(group[name].isna().sum()) for name in CANDIDATE_FEATURES},
            "block_availability": {
                name.removesuffix("__availability_status"): {
                    str(status): int(count) for status, count in group[name].value_counts(dropna=False).sort_index().items()
                } for name in group if name.endswith("__availability_status")
            },
        }
    return result


def write_v1_artifacts(result: V1Preparation, output_dir: Path) -> None:
    """Persist deterministic preparation, strict population and audit artifacts."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result.prepared.to_parquet(output / "prepared.parquet", index=False)
    result.strict_population.to_parquet(output / "strict_population.parquet", index=False)
    result.exclusions.to_csv(output / "exclusions.csv", index=False)
    result.join_report.to_csv(output / "feature_joins.csv", index=False)
    result.history_report.to_csv(output / "history_readiness.csv", index=False)
    for name, value in (("coverage", result.coverage), ("readiness", result.readiness),
                        ("manifest", result.manifest)):
        (output / f"{name}.json").write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    descriptors = []
    for number, block in enumerate(result.feature_blocks):
        descriptor = {field: getattr(block, field) for field in block.__dataclass_fields__ if field != "records"}
        path = f"block_{number}.csv"
        block.records.to_csv(output / path, index=False)
        descriptor["records_path"] = path
        descriptors.append(descriptor)
    (output / "blocks.json").write_text(json.dumps(descriptors, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    result.domain_records.to_parquet(output / "domain_records.parquet", index=False)


def main() -> None:
    import argparse

    from scripts.integration.modeling_municipal import build_municipal_feature_blocks, load_local_municipal_sources
    from scripts.integration.modeling_objects import build_object_feature_block, load_swissvotes_source

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True, help="Read-only project data directory")
    parser.add_argument("--outcomes", type=Path, required=True, help="Cleaned municipal outcomes parquet")
    parser.add_argument("--geography-id", required=True, help="Verified outcome geography reference")
    parser.add_argument("--source-version", required=True, help="Verified outcome source version")
    parser.add_argument("--output", type=Path, required=True, help="Destination of the complete preparation bundle")
    parser.add_argument("--forecast-evidence", type=Path)
    parser.add_argument("--result-evidence", type=Path)
    parser.add_argument("--history-config", type=Path, help="Optional justified EvaluationConfig JSON; no model is fitted")
    args = parser.parse_args()
    sources = load_local_municipal_sources(args.data_root / "raw")
    geography_audit = sources.pop("geography_audit")
    blocks, municipal_audit = build_municipal_feature_blocks(**sources, geography_id=args.geography_id)
    outcomes = pd.read_parquet(args.outcomes)
    swissvotes = load_swissvotes_source(args.data_root)
    objects = build_object_feature_block(
        outcomes, swissvotes.records, source_version=swissvotes.source_version, source_url=swissvotes.source_url,
    )
    def evidence(path):
        return pd.read_csv(path, dtype={"vote_id": "string"}) if path else None
    history_config = None
    if args.history_config:
        from scripts.evaluate_votes import EvaluationConfig

        history_config = EvaluationConfig(**json.loads(args.history_config.read_text(encoding="utf-8")))
    result = prepare_v1_table(
        outcomes, geography_id=args.geography_id, source_version=args.source_version,
        municipal_blocks=blocks, object_features=objects,
        forecast_publications=evidence(args.forecast_evidence), result_publications=evidence(args.result_evidence),
        history_config=history_config,
        source_audit={"municipal": municipal_audit, "geography": geography_audit,
                      "object_join_status": objects.join_audit.join_status.value_counts().to_dict()},
    )
    # Outputs may live elsewhere, but must never replace a source file.
    if args.output.resolve() == args.data_root.resolve() or args.data_root.resolve() in args.output.resolve().parents:
        parser.error("Choose an output directory outside the read-only data-root")
    write_v1_artifacts(result, args.output)
    objects.join_audit.to_csv(args.output / "object_join_audit.csv", index=False)
    objects.unmatched_swissvotes.to_csv(args.output / "unmatched_swissvotes.csv", index=False)
    print(json.dumps({"status": result.readiness["status"], "prepared_rows": len(result.prepared),
                      "strict_rows": len(result.strict_population), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
