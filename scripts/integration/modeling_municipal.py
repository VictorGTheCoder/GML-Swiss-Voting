"""Prepare the eight municipal feature candidates for the V1 table.

The adapters retain source geography, versions, reference dates and documented
publication evidence. A retrospective common geography is recorded separately
from publication-time eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.commune_crosswalk import parse_fr_date, resolve
from scripts.feature_blocks import FeatureBlock
from scripts.integration.modeling_temporal import ModelingPreparation, prepare_modeling_table

MUNICIPALITY_FEATURES = (
    "population_total", "share_foreign", "share_age_0_19", "share_age_20_39",
    "share_age_65_plus", "canton", "language_region", "urban_rural_type",
)
SOURCE_START_YEAR = 2010
SOURCE_END_YEAR = 2025
AGE_BUCKETS = tuple([*range(0, 100, 5), 100])
AGE_FEATURE_BUCKETS = {
    "share_age_0_19": (0, 5, 10, 15),
    "share_age_20_39": (20, 25, 30, 35),
    "share_age_65_plus": (65, 70, 75, 80, 85, 90, 95, 100),
}
URBAN_RURAL_LABELS = {"1": "urban", "2": "intermediate", "3": "rural"}


@dataclass(frozen=True)
class MunicipalPreparation:
    """Complete prepared table and source-level municipal-feature audit."""

    preparation: ModelingPreparation
    audit: dict
    feature_blocks: tuple[FeatureBlock, ...]


def normalize_municipality_id(values: pd.Series) -> pd.Series:
    """Normalize numeric-looking OFS IDs as strings without losing identity."""
    codes = values.astype("string").str.strip()
    codes = codes.str.replace(r"\.0+$", "", regex=True)
    codes = codes.str.lstrip("0")
    return codes.mask(codes.eq(""), "0")


def build_register_crosswalk(
    source_snapshot: pd.DataFrame,
    target_snapshot: pd.DataFrame,
    mutations: pd.DataFrame,
    *,
    source_geography_id: str,
    target_geography_id: str,
    crosswalk_version: str,
    crosswalk_evidence: str,
) -> tuple[pd.DataFrame, dict]:
    """Map one BFS commune-register snapshot to another, without assigning split weights."""
    for label, value in {
        "source_geography_id": source_geography_id,
        "target_geography_id": target_geography_id,
        "crosswalk_version": crosswalk_version,
        "crosswalk_evidence": crosswalk_evidence,
    }.items():
        if not str(value).strip():
            raise ValueError(f"{label} must be explicit")
    source_codes = _snapshot_commune_codes(source_snapshot, "source")
    target_codes = _snapshot_commune_codes(target_snapshot, "target")
    required_mutation_fields = {"MutationDate", "MutationNumber", "InitialCode", "TerminalCode"}
    missing = required_mutation_fields - set(mutations.columns)
    if missing:
        raise ValueError(f"Mutation history missing columns: {sorted(missing)}")
    grouped: dict[tuple[date, int], dict[str, set[str]]] = {}
    for row in mutations.to_dict(orient="records"):
        key = (parse_fr_date(str(row["MutationDate"])), int(row["MutationNumber"]))
        rules = grouped.setdefault(key, {})
        rules.setdefault(str(row["InitialCode"]), set()).add(str(row["TerminalCode"]))
    ordered_mutations = [(day, number, rules) for (day, number), rules in sorted(grouped.items())]
    from_date = pd.Timestamp(source_snapshot.attrs.get("snapshot_date", ""))
    to_date = pd.Timestamp(target_snapshot.attrs.get("snapshot_date", ""))
    if pd.isna(from_date) or pd.isna(to_date) or from_date >= to_date:
        raise ValueError("Snapshots must declare increasing snapshot_date values")
    source_day, target_day = from_date.date(), to_date.date()

    rows = []
    target_sources: dict[str, list[str]] = {}
    unresolved = []
    for source in source_codes:
        targets = resolve(source, source_day, target_day, ordered_mutations)
        valid_targets = targets & target_codes
        if len(targets) != 1 or len(valid_targets) != 1:
            unresolved.append(source)
            target = pd.NA
            mapping_type = "unsupported_split_or_target"
        else:
            target = next(iter(valid_targets))
            mapping_type = "unchanged" if source == target else "recoded_or_merged"
            target_sources.setdefault(target, []).append(source)
        rows.append({
            "source_municipality_id": source,
            "target_municipality_id": target,
            "mapping_type": mapping_type,
            "source_geography_id": source_geography_id,
            "target_geography_id": target_geography_id,
            "crosswalk_version": crosswalk_version,
            "crosswalk_evidence": crosswalk_evidence,
            "mapping_available_at": pd.NaT,
        })
    for row in rows:
        target = row["target_municipality_id"]
        if pd.notna(target) and len(target_sources[str(target)]) > 1:
            row["mapping_type"] = "merge"
    target_without_source = sorted(target_codes - set(target_sources))
    report = {
        "status": "PASS" if not unresolved and not target_without_source else "AUDIT_REQUIRED",
        "source_geography_id": source_geography_id,
        "target_geography_id": target_geography_id,
        "source_snapshot_date": source_day.isoformat(),
        "target_snapshot_date": target_day.isoformat(),
        "source_communes": len(source_codes),
        "target_communes": len(target_codes),
        "mapped_target_communes": len(target_sources),
        "unsupported_source_codes": sorted(unresolved, key=int),
        "target_communes_without_source": target_without_source,
        "merger_groups": {
            target: sorted(sources, key=int) for target, sources in sorted(target_sources.items())
            if len(sources) > 1
        },
        "crosswalk_version": crosswalk_version,
        "crosswalk_evidence": crosswalk_evidence,
    }
    return pd.DataFrame(rows), report


def prepare_municipal_table(
    outcomes: pd.DataFrame,
    forecast_publications: pd.DataFrame | None,
    statpop_nationality: pd.DataFrame,
    statpop_age_classes: pd.DataFrame,
    commune_levels: pd.DataFrame,
    geography_crosswalk: pd.DataFrame,
    *,
    geography_id: str,
    source_version: str,
    population_source_version: str,
    population_source_url: str,
    age_source_version: str,
    age_source_url: str,
    territory_source_version: str,
    territory_source_url: str,
    source_geography_id: str | None = None,
    crosswalk_version: str | None = None,
    crosswalk_evidence: str | None = None,
    population_publication_evidence: pd.DataFrame | None = None,
    age_publication_evidence: pd.DataFrame | None = None,
    territory_publication_evidence: pd.DataFrame | None = None,
    language_publication_evidence: pd.DataFrame | None = None,
    result_publications: pd.DataFrame | None = None,
    source_start: str = "2010-01-01",
) -> MunicipalPreparation:
    """Build all available municipal blocks through the complete table seam."""
    blocks, audit = build_municipal_feature_blocks(
        statpop_nationality, statpop_age_classes, commune_levels, geography_crosswalk,
        geography_id=geography_id,
        population_source_version=population_source_version,
        population_source_url=population_source_url,
        age_source_version=age_source_version,
        age_source_url=age_source_url,
        territory_source_version=territory_source_version,
        territory_source_url=territory_source_url,
        source_geography_id=source_geography_id,
        crosswalk_version=crosswalk_version,
        crosswalk_evidence=crosswalk_evidence,
        population_publication_evidence=population_publication_evidence,
        age_publication_evidence=age_publication_evidence,
        territory_publication_evidence=territory_publication_evidence,
        language_publication_evidence=language_publication_evidence,
    )
    preparation = prepare_modeling_table(
        outcomes, geography_id=geography_id, source_version=source_version,
        forecast_publications=forecast_publications, result_publications=result_publications,
        source_start=source_start, feature_blocks=blocks, geography_mode="retrospective_fixed",
    )
    audit["feature_coverage"] = preparation.feature_coverage
    audit["feature_manifests"] = preparation.feature_manifests
    territory_report = preparation.feature_join_report
    audit["missing_territory_records"] = int(territory_report.loc[
        territory_report.block_id.eq("municipal_context") & territory_report.status.eq("missing_entity"),
        "municipality_id",
    ].nunique())
    audit["unresolved_features"] = {
        name: reason for name, reason in audit["feature_prerequisites"].items()
    }
    return MunicipalPreparation(preparation, audit, blocks)


def build_municipal_feature_blocks(
    statpop_nationality: pd.DataFrame,
    statpop_age_classes: pd.DataFrame,
    commune_levels: pd.DataFrame,
    geography_crosswalk: pd.DataFrame,
    *,
    geography_id: str,
    population_source_version: str,
    population_source_url: str,
    age_source_version: str,
    age_source_url: str,
    territory_source_version: str,
    territory_source_url: str,
    source_geography_id: str | None = None,
    crosswalk_version: str | None = None,
    crosswalk_evidence: str | None = None,
    population_publication_evidence: pd.DataFrame | None = None,
    age_publication_evidence: pd.DataFrame | None = None,
    territory_publication_evidence: pd.DataFrame | None = None,
    language_publication_evidence: pd.DataFrame | None = None,
) -> tuple[tuple[FeatureBlock, ...], dict]:
    """Adapt prepared STATPOP and BFS commune-level exports into allowlisted blocks."""
    versions = {
        "population": population_source_version,
        "age": age_source_version,
        "territory": territory_source_version,
        "geography": crosswalk_version or "declared-crosswalk",
    }
    urls = {"population": population_source_url, "age": age_source_url,
            "territory": territory_source_url}
    for name, value in {**versions, **urls, "geography_id": geography_id}.items():
        if not str(value).strip():
            raise ValueError(f"Source metadata {name} must be explicit")

    mapping, mapping_audit = _validate_feature_crosswalk(
        geography_crosswalk, geography_id=geography_id,
        source_geography_id=source_geography_id,
        crosswalk_version=crosswalk_version, crosswalk_evidence=crosswalk_evidence,
    )
    geography_ok = mapping_audit["status"] == "PASS"
    population_rows, population_audit = _build_population_records(
        statpop_nationality, mapping, geography_id, population_source_version,
        population_publication_evidence,
    )
    age_rows, age_audit = _build_age_records(
        statpop_age_classes, statpop_nationality, mapping, geography_id,
        age_source_version, age_publication_evidence,
    )
    territory_rows, territory_audit = _build_territory_records(
        commune_levels, geography_id, territory_source_version,
        territory_publication_evidence,
    )
    language_rows, language_audit = _build_language_records(
        commune_levels, geography_id, territory_source_version,
        language_publication_evidence,
    )

    mapping_problem = None if geography_ok else "STATPOP source geography mapping is incomplete or ambiguous"
    population_block = FeatureBlock(
        "statpop_population", "municipality", population_rows if mapping_problem is None else pd.DataFrame(),
        ("population_total", "share_foreign"), (),
        {
            "population_total": "Permanent resident population on 31 December; counts are summed over complete merger constituents.",
            "share_foreign": "Foreign permanent resident population / total permanent resident population, after aggregating counts.",
            "source_geography_reference": mapping_audit["source_geography_id"],
            "target_geography_reference": mapping_audit["target_geography_id"],
            "geography_crosswalk_version": mapping_audit["crosswalk_version"],
            "geography_crosswalk_evidence": mapping_audit["crosswalk_evidence"],
        },
        population_source_url, population_source_version, "retrospective_fixed",
        mapping_problem,
    )
    age_block = FeatureBlock(
        "statpop_age", "municipality", age_rows if mapping_problem is None else pd.DataFrame(),
        ("share_age_0_19", "share_age_20_39", "share_age_65_plus"), (),
        {
            "share_age_0_19": "Permanent residents aged 0–19 / total permanent residents; five-year bins 0, 5, 10 and 15.",
            "share_age_20_39": "Permanent residents aged 20–39 / total permanent residents; five-year bins 20, 25, 30 and 35.",
            "share_age_65_plus": "Permanent residents aged 65 or more / total permanent residents; bins 65–95 and 100+.",
            "source_geography_reference": mapping_audit["source_geography_id"],
            "target_geography_reference": mapping_audit["target_geography_id"],
            "geography_crosswalk_version": mapping_audit["crosswalk_version"],
            "geography_crosswalk_evidence": mapping_audit["crosswalk_evidence"],
        },
        age_source_url, age_source_version, "retrospective_fixed",
        mapping_problem,
    )
    territory_block = FeatureBlock(
        "municipal_context", "municipality", territory_rows,
        (), ("canton", "urban_rural_type"),
        {
            "canton": "Canton label from the BFS commune register.",
            "urban_rural_type": "BFS urban–rural typology 2020: urban, intermediate or rural (STALAN2020).",
            "typology_version": "BFS STALAN2020, current geography 2026-01-01; value codes remain categorical.",
            "geography_reference": geography_id,
        },
        territory_source_url, territory_source_version, "retrospective_fixed",
        None,
    )
    language_block = FeatureBlock(
        "language_region", "municipality", language_rows,
        (), ("language_region",),
        {
            "language_region": "BFS linguistic region code from SPRGEB2020, retained as a nominal category.",
            "classification_version": "SPRGEB2020; output is a current-vintage category, not a historical publication claim.",
            "geography_reference": geography_id,
        },
        territory_source_url, territory_source_version, "retrospective_fixed",
        language_audit.get("prerequisite_reason"),
    )
    blocks = (population_block, age_block, territory_block, language_block)
    audit = {
        "status": "AUDIT_REQUIRED" if mapping_problem or language_audit.get("prerequisite_reason") else "PREPARED",
        "target_geography_id": geography_id,
        "candidate_features": list(MUNICIPALITY_FEATURES),
        "feature_prerequisites": {
            "language_region": language_audit.get("prerequisite_reason"),
        },
        "sources": {
            "statpop_nationality": {"version": population_source_version, "url": population_source_url},
            "statpop_age_classes": {"version": age_source_version, "url": age_source_url},
            "commune_levels": {"version": territory_source_version, "url": territory_source_url},
        },
        "geography_crosswalk": mapping_audit,
        "population": population_audit,
        "age": age_audit,
        "territory": territory_audit,
        "language_region": language_audit,
    }
    return blocks, audit


def load_local_municipal_sources(source_root: Path) -> dict:
    """Read the checked-in prepared STATPOP and commune-level sources without editing them."""
    root = Path(source_root)
    features = root / "features"
    nationality = pd.read_csv(features / "statpop_nationality.csv", dtype={"code": "string"})
    age_classes = pd.read_csv(features / "statpop_age_classes.csv", dtype={"code": "string"})
    levels = pd.read_csv(features / "commune_levels_2026-01-01.csv", dtype="string")
    snapshots = root / "geography"
    source_snapshot = pd.read_csv(snapshots / "register_snapshot_2025-04-06.csv", dtype="string")
    target_snapshot = pd.read_csv(snapshots / "register_snapshot_2026-01-01.csv", dtype="string")
    mutations = pd.read_csv(snapshots / "register_mutations_2010_2026.csv", dtype="string")
    source_snapshot.attrs["snapshot_date"] = "2025-04-06"
    target_snapshot.attrs["snapshot_date"] = "2026-01-01"
    crosswalk, geography_audit = build_register_crosswalk(
        source_snapshot, target_snapshot, mutations,
        source_geography_id="bfs-2025-04-06", target_geography_id="bfs-2026-01-01",
        crosswalk_version="register_mutations_2010_2026",
        crosswalk_evidence="data/raw/geography/register_mutations_2010_2026.provenance.json; "
                            "snapshots register_snapshot_2025-04-06 and register_snapshot_2026-01-01",
    )
    versions = {
        "population_source_version": _sidecar_version(features / "statpop_nationality.provenance.json"),
        "age_source_version": _sidecar_version(features / "statpop_age_classes.provenance.json"),
        "territory_source_version": _sidecar_version(features / "commune_levels_2026-01-01.provenance.json"),
    }
    urls = {
        "population_source_url": "https://www.pxweb.bfs.admin.ch/api/v1/fr/px-x-0102010000_101/px-x-0102010000_101.px",
        "age_source_url": "https://www.pxweb.bfs.admin.ch/api/v1/fr/px-x-0102010000_103/px-x-0102010000_103.px",
        "territory_source_url": "https://www.agvchapp.bfs.admin.ch/api/communes/levels?date=01-01-2026",
    }
    return {
        "statpop_nationality": nationality,
        "statpop_age_classes": age_classes,
        "commune_levels": levels,
        "geography_crosswalk": crosswalk,
        "geography_audit": geography_audit,
        **versions,
        **urls,
    }


def _snapshot_commune_codes(snapshot: pd.DataFrame, name: str) -> set[str]:
    if "BfsCode" not in snapshot:
        raise ValueError(f"{name} snapshot needs BfsCode")
    rows = snapshot.copy()
    if "Level" in rows:
        rows = rows.loc[rows.Level.astype(str).eq("3")]
    codes = normalize_municipality_id(rows.BfsCode)
    if codes.isna().any() or codes.eq("").any() or codes.duplicated().any():
        raise ValueError(f"{name} snapshot has missing or duplicate commune codes")
    return set(codes.astype(str))


def _validate_feature_crosswalk(
    crosswalk: pd.DataFrame,
    *,
    geography_id: str,
    source_geography_id: str | None,
    crosswalk_version: str | None,
    crosswalk_evidence: str | None,
) -> tuple[pd.DataFrame, dict]:
    required = {
        "source_municipality_id", "target_municipality_id", "mapping_type",
        "source_geography_id", "target_geography_id", "crosswalk_version", "crosswalk_evidence",
    }
    missing = required - set(crosswalk.columns)
    if missing:
        raise ValueError(f"Geography crosswalk missing columns: {sorted(missing)}")
    mapping = crosswalk.copy()
    mapping["source_municipality_id"] = normalize_municipality_id(mapping.source_municipality_id)
    mapping["target_municipality_id"] = normalize_municipality_id(mapping.target_municipality_id)
    if mapping.source_municipality_id.isna().any() or mapping.source_municipality_id.duplicated().any():
        raise ValueError("Geography crosswalk needs unique nonmissing source municipality IDs")
    for column in ("mapping_type", "source_geography_id", "target_geography_id", "crosswalk_version", "crosswalk_evidence"):
        mapping[column] = mapping[column].astype("string").str.strip()
        if mapping[column].isna().any() or mapping[column].eq("").any():
            raise ValueError(f"Geography crosswalk has missing {column}")
    if not mapping.target_geography_id.eq(geography_id).all():
        raise ValueError("Geography crosswalk target reference does not match the prepared outcome geography")
    if source_geography_id is not None and not mapping.source_geography_id.eq(source_geography_id).all():
        raise ValueError("Geography crosswalk source reference differs from the declared source geography")
    if crosswalk_version is not None and not mapping.crosswalk_version.eq(crosswalk_version).all():
        raise ValueError("Geography crosswalk versions conflict with the declared version")
    if crosswalk_evidence is not None and not mapping.crosswalk_evidence.eq(crosswalk_evidence).all():
        raise ValueError("Geography crosswalk evidence conflicts with the declared evidence")
    unresolved = ~mapping.mapping_type.isin(["unchanged", "recoded_or_merged", "merge"])
    audit = {
        "status": "AUDIT_REQUIRED" if unresolved.any() else "PASS",
        "source_geography_id": ",".join(sorted(mapping.source_geography_id.unique())),
        "target_geography_id": geography_id,
        "crosswalk_version": ",".join(sorted(mapping.crosswalk_version.unique())),
        "crosswalk_evidence": ",".join(sorted(mapping.crosswalk_evidence.unique())),
        "source_rows": len(mapping),
        "mapped_source_rows": int((~unresolved).sum()),
        "unsupported_sources": sorted(mapping.loc[unresolved, "source_municipality_id"].astype(str), key=int),
        "target_coverage": int(mapping.loc[~unresolved, "target_municipality_id"].nunique()),
        "mapping_available_at": None,
    }
    return mapping.loc[~unresolved].copy(), audit


def _normalize_statpop(frame: pd.DataFrame, required: set[str], label: str) -> pd.DataFrame:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{label} source missing columns: {sorted(missing)}")
    rows = frame.copy()
    rows["year"] = pd.to_numeric(rows.year, errors="coerce")
    rows["code"] = normalize_municipality_id(rows.code)
    rows = rows.loc[rows.year.between(SOURCE_START_YEAR, SOURCE_END_YEAR)].copy()
    rows["year"] = rows.year.astype(int)
    if rows[["year", "code"]].isna().any().any():
        raise ValueError(f"{label} source has missing year or commune key")
    return rows


def _count(values: pd.Series) -> pd.Series:
    parsed = pd.to_numeric(values, errors="coerce")
    valid = np.isfinite(parsed) & parsed.ge(0) & parsed.mod(1).eq(0)
    return parsed.where(valid)


def _publication_table(
    evidence: pd.DataFrame | None,
    *,
    keys: list[str],
    source_version: str,
    source_name: str,
) -> pd.DataFrame:
    output_columns = keys + ["published_at", "availability_evidence"]
    if evidence is None:
        return pd.DataFrame(columns=output_columns)
    required = set(output_columns) | {"source_version"}
    missing = required - set(evidence.columns)
    if missing:
        raise ValueError(f"{source_name} publication evidence missing columns: {sorted(missing)}")
    table = evidence.loc[:, output_columns].copy()
    if "code" in keys:
        table["code"] = normalize_municipality_id(table.code)
    table["year"] = pd.to_numeric(table.year, errors="coerce")
    table["published_at"] = pd.to_datetime(table.published_at, errors="coerce", utc=True, format="mixed")
    table["availability_evidence"] = table.availability_evidence.astype("string").str.strip()
    table.loc[table.availability_evidence.eq(""), "availability_evidence"] = pd.NA
    if table[keys].isna().any().any() or table.duplicated(keys).any():
        raise ValueError(f"{source_name} publication evidence has missing or duplicate keys")
    if "source_version" in evidence:
        versions = evidence.source_version.astype("string")
        if versions.isna().any() or versions.ne(source_version).any():
            raise ValueError(f"{source_name} publication evidence must cite the exact source version")
    return table


def _aggregate_mapped(
    source: pd.DataFrame,
    mapping: pd.DataFrame,
    *,
    value_columns: tuple[str, ...],
    expected_by_target: dict[str, int],
) -> pd.DataFrame:
    mapped = source.merge(
        mapping[["source_municipality_id", "target_municipality_id"]],
        left_on="code", right_on="source_municipality_id", how="inner", validate="many_to_one",
    )
    results = []
    for (year, target), group in mapped.groupby(["year", "target_municipality_id"], sort=True):
        expected = expected_by_target[str(target)]
        complete_codes = group.source_municipality_id.nunique() == expected
        result = {"year": int(year), "municipality_id": str(target),
                  "source_municipality_ids": "|".join(sorted(group.source_municipality_id.astype(str).unique(), key=int)),
                  "geography_source_rows": int(group.source_municipality_id.nunique()),
                  "geography_expected_rows": expected}
        for column in value_columns:
            values = group[column]
            complete_values = values.notna().sum() == expected
            result[column] = values.sum(min_count=expected) if complete_codes and complete_values else np.nan
        if "published_at" in group:
            dates = group.published_at
            evidence = group.availability_evidence
            verified = complete_codes and dates.notna().sum() == expected and evidence.notna().sum() == expected
            result["published_at"] = dates.max() if verified else pd.NaT
            result["availability_evidence"] = " | ".join(sorted(evidence.dropna().astype(str).unique())) if verified else pd.NA
            result["availability_status"] = "verified" if verified else "unknown"
        results.append(result)
    years = sorted(source.year.unique().tolist())
    targets = sorted(expected_by_target, key=int)
    grid = pd.MultiIndex.from_product([years, targets], names=["year", "municipality_id"]).to_frame(index=False)
    aggregate = pd.DataFrame(results)
    return grid.merge(aggregate, on=["year", "municipality_id"], how="left", validate="one_to_one")


def _build_population_records(
    nationality: pd.DataFrame,
    mapping: pd.DataFrame,
    geography_id: str,
    source_version: str,
    publication_evidence: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    rows = _normalize_statpop(nationality, {"year", "code", "population", "foreign"}, "STATPOP nationality")
    if rows.duplicated(["year", "code"]).any():
        raise ValueError("STATPOP nationality has duplicate year/code keys")
    rows["population"] = _count(rows.population)
    rows["foreign"] = _count(rows.foreign)
    rows["population"] = rows.population.where(rows.population.gt(0))
    rows["foreign"] = rows.foreign.where(rows.foreign.le(rows.population))
    audit = {
        "source_rows_2010_2025": len(rows),
        "years": sorted(rows.year.unique().tolist()),
        "aggregate_8100_rows_excluded": int(rows.code.eq("8100").sum()),
        "invalid_or_missing_population_rows": int(rows.population.isna().sum()),
        "invalid_or_missing_foreign_rows": int(rows.foreign.isna().sum()),
        "unmapped_source_codes": sorted(set(rows.code.dropna()) - set(mapping.source_municipality_id) - {"8100"}, key=int),
        "missing_source_codes_by_year": {str(year): sorted(set(mapping.source_municipality_id) - set(group.code), key=int)
                                         for year, group in rows.groupby("year", sort=True)},
    }
    rows = rows.loc[~rows.code.eq("8100")].copy()
    evidence = _publication_table(
        publication_evidence, keys=["year", "code"], source_version=source_version,
        source_name="STATPOP nationality",
    )
    if not evidence.empty:
        rows = rows.merge(evidence, on=["year", "code"], how="left", validate="one_to_one")
    else:
        rows["published_at"] = pd.NaT
        rows["availability_evidence"] = pd.NA
    expected = mapping.groupby("target_municipality_id").source_municipality_id.nunique().astype(int).to_dict()
    aggregate = _aggregate_mapped(
        rows, mapping, value_columns=("population", "foreign"), expected_by_target=expected,
    )
    aggregate["population_total"] = aggregate.pop("population")
    total = aggregate.population_total
    foreign = aggregate.pop("foreign")
    aggregate["share_foreign"] = foreign.div(total.where(total.gt(0)))
    aggregate["reference_date"] = pd.to_datetime(aggregate.year.astype(str) + "-12-31", utc=True)
    aggregate["geography_id"] = geography_id
    aggregate["source_geography_id"] = ",".join(sorted(mapping.source_geography_id.unique()))
    aggregate["source_version"] = source_version
    missing = aggregate["geography_source_rows"].fillna(0).ne(aggregate["geography_expected_rows"])
    aggregate.loc[missing, "availability_status"] = "unknown"
    if "availability_status" not in aggregate:
        aggregate["availability_status"] = "unknown"
    aggregate["availability_status"] = aggregate.availability_status.fillna("unknown")
    aggregate["published_at"] = pd.to_datetime(aggregate.get("published_at"), errors="coerce", utc=True)
    return aggregate, audit


def _build_age_records(
    age_classes: pd.DataFrame,
    nationality: pd.DataFrame,
    mapping: pd.DataFrame,
    geography_id: str,
    source_version: str,
    publication_evidence: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    ages = _normalize_statpop(age_classes, {"year", "code", "age_from", "population"}, "STATPOP age")
    ages["age_from"] = pd.to_numeric(ages.age_from, errors="coerce")
    if ages.age_from.isna().any() or not ages.age_from.isin(AGE_BUCKETS).all():
        raise ValueError("STATPOP age contains unknown five-year bins")
    ages["age_from"] = ages.age_from.astype(int)
    if ages.duplicated(["year", "code", "age_from"]).any():
        raise ValueError("STATPOP age has duplicate year/code/age_from keys")
    ages["population"] = _count(ages.population)
    ages = ages.loc[~ages.code.eq("8100")].copy()
    rows = []
    for (year, code), group in ages.groupby(["year", "code"], sort=True):
        by_age = group.set_index("age_from").population
        row = {"year": int(year), "code": str(code)}
        for feature, buckets in AGE_FEATURE_BUCKETS.items():
            values = by_age.reindex(buckets)
            row[f"count_{feature}"] = values.sum(min_count=len(buckets))
        row["age_bin_count"] = int(group.population.notna().sum())
        rows.append(row)
    grouped = pd.DataFrame(rows)
    pop = _normalize_statpop(nationality, {"year", "code", "population"}, "STATPOP nationality")
    pop = pop.loc[~pop.code.eq("8100"), ["year", "code", "population"]].copy()
    pop["population"] = _count(pop.population)
    grouped = grouped.merge(pop, on=["year", "code"], how="left", validate="one_to_one")
    # A complete age vector is checked against its source population total.
    complete_vector = grouped.age_bin_count.eq(len(AGE_BUCKETS))
    age_totals = ages.groupby(["year", "code"], sort=False).population.sum(min_count=len(AGE_BUCKETS))
    grouped["age_total"] = pd.MultiIndex.from_frame(grouped[["year", "code"]]).map(age_totals)
    inconsistent = complete_vector & grouped.age_total.ne(grouped.population)
    age_feature_counts = list(f"count_{name}" for name in AGE_FEATURE_BUCKETS)
    grouped.loc[inconsistent, age_feature_counts] = np.nan
    evidence = _publication_table(
        publication_evidence, keys=["year", "code"], source_version=source_version,
        source_name="STATPOP age",
    )
    if not evidence.empty:
        grouped = grouped.merge(evidence, on=["year", "code"], how="left", validate="one_to_one")
    else:
        grouped["published_at"] = pd.NaT
        grouped["availability_evidence"] = pd.NA
    expected = mapping.groupby("target_municipality_id").source_municipality_id.nunique().astype(int).to_dict()
    counts = tuple(age_feature_counts)
    aggregate = _aggregate_mapped(grouped, mapping, value_columns=counts, expected_by_target=expected)
    pop_totals, _pop_audit = _build_population_records(
        nationality, mapping, geography_id, source_version="_internal_", publication_evidence=None,
    )
    aggregate = aggregate.merge(
        pop_totals[["year", "municipality_id", "population_total"]],
        on=["year", "municipality_id"], how="left", validate="one_to_one",
    )
    for feature in AGE_FEATURE_BUCKETS:
        numerator = aggregate.pop(f"count_{feature}")
        aggregate[feature] = numerator.div(aggregate.population_total.where(aggregate.population_total.gt(0)))
    aggregate["reference_date"] = pd.to_datetime(aggregate.year.astype(str) + "-12-31", utc=True)
    aggregate["geography_id"] = geography_id
    aggregate["source_geography_id"] = ",".join(sorted(mapping.source_geography_id.unique()))
    aggregate["source_version"] = source_version
    aggregate["availability_status"] = aggregate.availability_status.fillna("unknown")
    aggregate["published_at"] = pd.to_datetime(aggregate.get("published_at"), errors="coerce", utc=True)
    inconsistent_count = int(inconsistent.sum())
    return aggregate, {
        "source_rows_2010_2025": len(ages),
        "years": sorted(ages.year.unique().tolist()),
        "aggregate_8100_rows_excluded": int(_normalize_statpop(age_classes, {"year", "code", "age_from", "population"}, "STATPOP age").code.eq("8100").sum()),
        "incomplete_age_vectors": int(grouped.age_bin_count.ne(len(AGE_BUCKETS)).sum()),
        "inconsistent_complete_age_totals": inconsistent_count,
        "missing_selected_bins_by_feature": {
            name: int(grouped[f"count_{name}"].isna().sum()) for name in AGE_FEATURE_BUCKETS
        },
    }


def _categorical(value: object) -> str | None:
    return None if pd.isna(value) or str(value).strip() in {"", ".", "..", "...", "*"} else str(value).strip()


def _territory_evidence(
    evidence: pd.DataFrame | None,
    *,
    municipality_ids: pd.Series,
    source_version: str,
) -> pd.DataFrame:
    if evidence is None:
        return pd.DataFrame({
            "municipality_id": municipality_ids,
            "published_at": pd.NaT,
            "availability_evidence": pd.NA,
            "availability_status": "unknown",
        })
    required = {"municipality_id", "published_at", "availability_evidence", "source_version"}
    if required - set(evidence.columns):
        raise ValueError(f"Territory publication evidence missing columns: {sorted(required-set(evidence.columns))}")
    proof = evidence.copy()
    proof["municipality_id"] = normalize_municipality_id(proof.municipality_id)
    if proof.municipality_id.isna().any() or proof.municipality_id.duplicated().any():
        raise ValueError("Territory publication evidence has missing or duplicate municipality keys")
    if "source_version" in proof and proof.source_version.astype(str).ne(source_version).any():
        raise ValueError("Territory evidence must identify the exact source version")
    proof["published_at"] = pd.to_datetime(proof.published_at, errors="coerce", utc=True, format="mixed")
    proof["availability_evidence"] = proof.availability_evidence.astype("string").str.strip()
    verified = proof.published_at.notna() & proof.availability_evidence.notna() & proof.availability_evidence.ne("")
    proof["availability_status"] = np.where(verified, "verified", "unknown")
    return proof[["municipality_id", "published_at", "availability_evidence", "availability_status"]]


def _build_territory_records(
    commune_levels: pd.DataFrame,
    geography_id: str,
    source_version: str,
    publication_evidence: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    required = {"BfsCode", "Canton", "STALAN2020"}
    missing = required - set(commune_levels.columns)
    if missing:
        raise ValueError(f"BFS commune levels missing required typology columns: {sorted(missing)}")
    levels = commune_levels.copy()
    levels["municipality_id"] = normalize_municipality_id(levels.BfsCode)
    if levels.municipality_id.isna().any() or levels.municipality_id.duplicated().any():
        raise ValueError("BFS commune levels has missing or duplicate BfsCode values")
    levels["canton"] = levels.Canton.map(_categorical)
    raw_urban = levels.STALAN2020.astype("string").str.strip()
    levels["urban_rural_type"] = raw_urban.map(URBAN_RURAL_LABELS)
    levels["reference_date"] = pd.Timestamp("2026-01-01", tz="UTC")
    proof = _territory_evidence(
        publication_evidence, municipality_ids=levels.municipality_id,
        source_version=source_version,
    )
    levels = levels.merge(proof, on="municipality_id", how="left", validate="one_to_one")
    levels["availability_status"] = levels.availability_status.fillna("unknown")
    levels["published_at"] = pd.to_datetime(levels.published_at, errors="coerce", utc=True)
    levels["source_version"] = source_version
    levels["geography_id"] = geography_id
    levels["source_geography_id"] = geography_id
    counts = levels.urban_rural_type.value_counts(dropna=False).to_dict()
    return levels[["municipality_id", "reference_date", "published_at", "availability_status",
                   "availability_evidence", "source_version", "geography_id", "source_geography_id",
                   "canton", "urban_rural_type"]], {
        "source_rows": len(levels),
        "missing_communes": 0,
        "missing_canton": int(levels.canton.isna().sum()),
        "unknown_STALAN2020_codes": int(levels.urban_rural_type.isna().sum()),
        "urban_rural_counts": {str(k): int(v) for k, v in counts.items()},
        "typology": "STALAN2020",
        "reference_date": "2026-01-01",
        "availability_status": {str(k): int(v) for k, v in levels.availability_status.value_counts().items()},
        "excluded_fields": ["DEGURB2021", "REGCH", "GDETYP2020_9", "GDETYP2020_25"],
    }


def _build_language_records(
    commune_levels: pd.DataFrame,
    geography_id: str,
    source_version: str,
    publication_evidence: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    if "SPRGEB2020" not in commune_levels:
        return pd.DataFrame(), {
            "status": "unavailable",
            "prerequisite_reason": "BFS commune levels source lacks the SPRGEB2020 language-region field",
            "source_field": None,
            "reference_date": None,
        }
    levels = commune_levels[["BfsCode", "SPRGEB2020"]].copy()
    levels["municipality_id"] = normalize_municipality_id(levels.BfsCode)
    if levels.municipality_id.isna().any() or levels.municipality_id.duplicated().any():
        raise ValueError("BFS linguistic-region source has missing or duplicate commune codes")
    levels["language_region"] = levels.SPRGEB2020.map(_categorical)
    levels["reference_date"] = pd.Timestamp("2026-01-01", tz="UTC")
    proof = _territory_evidence(
        publication_evidence, municipality_ids=levels.municipality_id,
        source_version=source_version,
    )
    levels = levels.merge(proof, on="municipality_id", how="left", validate="one_to_one")
    levels["availability_status"] = levels.availability_status.fillna("unknown")
    levels["published_at"] = pd.to_datetime(levels.published_at, errors="coerce", utc=True)
    levels["source_version"] = source_version
    levels["geography_id"] = geography_id
    levels["source_geography_id"] = geography_id
    return levels[["municipality_id", "reference_date", "published_at", "availability_status",
                   "availability_evidence", "source_version", "geography_id", "source_geography_id",
                   "language_region"]], {
        "status": "prepared",
        "prerequisite_reason": None,
        "source_rows": len(levels),
        "missing_communes": 0,
        "missing_language_region": int(levels.language_region.isna().sum()),
        "language_region_codes": sorted(levels.language_region.dropna().unique().tolist()),
        "source_field": "SPRGEB2020",
        "reference_date": "2026-01-01",
        "availability_status": {str(k): int(v) for k, v in levels.availability_status.value_counts().items()},
    }


def _sidecar_version(path: Path) -> str:
    import json

    metadata = json.loads(Path(path).read_text(encoding="utf-8"))
    return f"{metadata.get('ofs_table') or metadata.get('source')}; " \
           f"updated={metadata.get('px_last_updated') or 'unknown'}; sha256={metadata.get('sha256') or 'unknown'}"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-root", type=Path, required=True,
                        help="data/raw root containing features/ and geography/ source snapshots")
    parser.add_argument("--outcomes", type=Path, required=True, help="Clean municipal OFS results parquet")
    parser.add_argument("--forecast-evidence", type=Path,
                        help="Brochure publication evidence CSV (omission leaves forecast time unknown)")
    parser.add_argument("--result-evidence", type=Path,
                        help="Result-publication evidence CSV for historical uses")
    parser.add_argument("--geography-id", default="bfs-2026-01-01")
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--output", type=Path, default=Path("data/processed/modeling/prepared_municipal_v1.parquet"))
    parser.add_argument("--audit", type=Path, default=Path("reports/modeling/municipal_features.json"))
    args = parser.parse_args()
    sources = load_local_municipal_sources(args.source_root)
    forecasts = pd.read_csv(args.forecast_evidence, dtype={"vote_id": "string"}) if args.forecast_evidence else None
    results = pd.read_csv(args.result_evidence, dtype={"vote_id": "string"}) if args.result_evidence else None
    result = prepare_municipal_table(
        pd.read_parquet(args.outcomes), forecasts,
        sources["statpop_nationality"], sources["statpop_age_classes"], sources["commune_levels"],
        sources["geography_crosswalk"], geography_id=args.geography_id,
        source_version=args.source_version,
        population_source_version=sources["population_source_version"],
        population_source_url=sources["population_source_url"],
        age_source_version=sources["age_source_version"], age_source_url=sources["age_source_url"],
        territory_source_version=sources["territory_source_version"],
        territory_source_url=sources["territory_source_url"],
        source_geography_id="bfs-2025-04-06",
        crosswalk_version="register_mutations_2010_2026",
        result_publications=results,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.preparation.prepared.to_parquet(args.output, index=False)
    audit_path = args.audit
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(__import__("json").dumps(result.audit, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(result.preparation.prepared):,} rows; strict rows: "
          f"{len(result.preparation.strict_population):,}; readiness: "
          f"{result.preparation.readiness['status']}; audit: {audit_path}")


if __name__ == "__main__":
    main()
