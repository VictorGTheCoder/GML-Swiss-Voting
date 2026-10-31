"""Prepare the Swissvotes legal-form and broad political-domain feature block."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scripts.common.config import SWISSVOTES_URL
from scripts.common.vote_keys import ofs_keys, swissvotes_key
from scripts.modeling.feature_blocks import FeatureBlock

LEGAL_FORM_LABELS = {
    1: "mandatory_referendum",
    2: "optional_referendum",
    3: "popular_initiative",
    4: "direct_counterproposal",
}
DOMAIN_COLUMNS = tuple(f"policy_domain_{number:02d}" for number in range(1, 13))
DOMAIN_SOURCE_COLUMNS = ("d1e1", "d2e1", "d3e1")
DOMAIN_DEFINITIONS = {
    name: f"1 if broad Swissvotes policy domain {number} is assigned; 0 if known absent; missing if classification is unknown"
    for number, name in enumerate(DOMAIN_COLUMNS, start=1)
}
FEATURE_DEFINITIONS = {
    "legal_form": "Swissvotes legal form as a category: mandatory referendum, optional referendum, popular initiative, or direct counterproposal",
    **DOMAIN_DEFINITIONS,
}


@dataclass(frozen=True)
class ObjectFeaturePreparation:
    """Feature block plus complete object-match and domain-history audit tables."""

    feature_block: FeatureBlock
    join_audit: pd.DataFrame
    domain_metadata: pd.DataFrame
    unmatched_swissvotes: pd.DataFrame


@dataclass(frozen=True)
class SwissvotesSource:
    """Loaded Swissvotes data and the version record verified against its bytes."""

    records: pd.DataFrame
    source_version: str
    source_url: str
    retrieved_at: str
    sha256: str


def read_swissvotes_csv(path: str | Path) -> pd.DataFrame:
    """Read a source CSV without numeric inference or global missing-code coercion."""
    return pd.read_csv(path, dtype="string", keep_default_na=False, encoding="utf-8-sig")


def load_swissvotes_source(data_root: str | Path) -> SwissvotesSource:
    """Load the checked local Swissvotes CSV and validate its provenance hash.

    ``data_root`` is an explicit workspace path whose `raw/features` folder
    contains the CSV and its `.provenance.json` sidecar. No download is made.
    """
    feature_dir = Path(data_root) / "raw" / "features"
    source_path = feature_dir / "swissvotes_dataset.csv"
    provenance_path = source_path.with_suffix(".provenance.json")
    if not source_path.is_file() or not provenance_path.is_file():
        raise FileNotFoundError(f"Swissvotes CSV and provenance sidecar are required under {feature_dir}")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    actual_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    expected_sha256 = provenance.get("sha256")
    if not expected_sha256 or actual_sha256 != expected_sha256:
        raise ValueError("Swissvotes CSV bytes do not match the provenance sidecar SHA-256")
    records = read_swissvotes_csv(source_path)
    return SwissvotesSource(
        records=records,
        source_version=f"sha256:{actual_sha256}",
        source_url=provenance.get("source") or SWISSVOTES_URL,
        retrieved_at=str(provenance.get("retrieved_at_utc", "")),
        sha256=actual_sha256,
    )


def build_object_feature_block(
    ofs_objects: pd.DataFrame,
    swissvotes: pd.DataFrame,
    *,
    source_version: str,
    source_url: str = SWISSVOTES_URL,
    published_at: str | pd.Timestamp | None = None,
    publication_evidence: str | None = None,
    reference_date: str | pd.Timestamp | None = None,
    publication_records: pd.DataFrame | None = None,
) -> ObjectFeaturePreparation:
    """Build one object-scoped feature record per OFS key using exact IDs.

    ``published_at`` and its evidence are optional, because the current dataset
    snapshot does not itself establish the metadata's availability in historical
    forecasts. A keyed ``publication_records`` table may instead supply
    `vote_id`, `published_at`, `reference_date`, `availability_evidence`, and
    `source_version` for individually evidenced object metadata.
    """
    if not source_version or not source_version.strip() or not source_url.strip():
        raise ValueError("Swissvotes source URL and version must be nonempty")
    if 'vote_id' not in ofs_objects:
        raise ValueError('OFS objects require vote_id')
    valid_keys = ofs_objects.vote_id.astype('string').str.strip().str.fullmatch(r'[1-9][0-9]*', na=False)
    invalid_ofs = ofs_objects.loc[~valid_keys].copy()
    ofs = _normalize_ofs_objects(ofs_objects.loc[valid_keys])
    swiss, invalid_swissvotes = _normalize_swissvotes(swissvotes)
    source_duplicates = set(swiss.loc[swiss.vote_key.duplicated(keep=False), "vote_key"])
    ofs_conflicts = set(
        ofs.groupby("vote_key", dropna=False).filter(
            lambda group: group[["vote_id", "voting_date", "is_subsidiary"]].nunique(dropna=False).gt(1).any()
        ).vote_key
    )
    ofs = ofs.drop_duplicates("vote_key", keep="first").copy()

    swiss_by_key = {
        key: group.iloc[0]
        for key, group in swiss.loc[~swiss.vote_key.isin(source_duplicates)].groupby("vote_key", sort=False)
    }
    object_rows: list[dict] = []
    audit_rows: list[dict] = []
    for question in ofs.itertuples(index=False):
        vote_key = question.vote_key
        vote_id = question.vote_id
        source = swiss_by_key.get(vote_key)
        status = "matched"
        if vote_key in ofs_conflicts:
            status = "conflicting_ofs_metadata"
        elif vote_key in source_duplicates:
            status = "duplicate_swissvotes_key"
        elif source is None:
            status = "missing_swissvotes"
        elif pd.isna(source.vote_date):
            status = "invalid_swissvotes_date"
        elif source.vote_date != question.voting_date:
            status = "date_mismatch"
        elif pd.isna(source.is_subsidiary) or source.is_subsidiary != question.is_subsidiary:
            status = "question_type_mismatch"

        metadata = _empty_metadata_record(vote_id, source_version)
        if source is not None and status == "matched":
            metadata.update(_source_features(source))
            metadata["object_match_status"] = "validated"
            metadata["object_match_evidence"] = f"exact vote identifier {vote_key}; date and question type checked"
            metadata["metadata_date"] = question.voting_date
        else:
            metadata["metadata_date"] = pd.NaT
        object_rows.append(metadata)
        audit_rows.append({
            "vote_id": vote_id,
            "vote_key": vote_key,
            "voting_date": question.voting_date,
            "join_status": status,
            "swissvotes_id": None if source is None else source.swissvotes_id,
            "swissvotes_date": None if source is None else source.vote_date,
            "ofs_is_subsidiary": question.is_subsidiary,
            "swissvotes_is_subsidiary": None if source is None else source.is_subsidiary,
        })

    records = pd.DataFrame(object_rows, columns=[*_empty_metadata_record('', source_version), 'metadata_date'])
    records = _attach_publication_evidence(
        records, source_version=source_version, published_at=published_at,
        publication_evidence=publication_evidence, reference_date=reference_date,
        publication_records=publication_records,
    )
    # Object keys must be unique before the municipal replication performed by
    # prepare_modeling_table. Conflicting source rows remain in the audit only.
    if records.vote_id.duplicated().any():
        raise ValueError("OFS object table must have one normalized record per vote_id")
    records["reference_date"] = records["reference_date"].where(
        records.reference_date.notna(), records["metadata_date"]
    )
    records = records.drop(columns="metadata_date")
    audit = pd.DataFrame(audit_rows, columns=[
        'vote_id', 'vote_key', 'voting_date', 'join_status', 'swissvotes_id',
        'swissvotes_date', 'ofs_is_subsidiary', 'swissvotes_is_subsidiary',
    ])
    if not invalid_ofs.empty:
        invalid_audit = invalid_ofs[['vote_id']].copy()
        invalid_audit['vote_key'] = pd.NA
        invalid_audit['join_status'] = 'invalid_ofs_identifier'
        audit = pd.concat([audit, invalid_audit], ignore_index=True)
    unmatched = invalid_swissvotes.copy()
    represented = set(ofs.vote_key)
    right_only = swiss.loc[~swiss.vote_key.isin(represented)].copy()
    if not right_only.empty:
        right_only["join_status"] = "not_in_ofs_coverage"
    if not unmatched.empty:
        unmatched["join_status"] = "invalid_swissvotes_identifier"
    unmatched = pd.concat([right_only, unmatched], ignore_index=True, sort=False)
    domains = records[[
        "vote_id", "domain_codes", "domain_status", "object_match_status",
        "object_match_evidence", "availability_status", "availability_evidence",
        "published_at", "reference_date", "source_version",
    ]].copy()
    block = FeatureBlock(
        block_id="swissvotes", scope="object", records=records,
        numeric_features=DOMAIN_COLUMNS, categorical_features=("legal_form",),
        definitions=FEATURE_DEFINITIONS, source_url=source_url,
        source_version=source_version, geography_mode="retrospective_fixed",
    )
    return ObjectFeaturePreparation(block, audit, domains, unmatched)


def object_history_domains(domain_metadata: pd.DataFrame) -> pd.DataFrame:
    """Expose object domain memberships and their provenance for history features."""
    required = {
        "vote_id", "domain_codes", "domain_status", "object_match_status",
        "object_match_evidence", "availability_status", "availability_evidence",
        "published_at", "reference_date", "source_version",
    }
    if required - set(domain_metadata.columns):
        raise ValueError(f"Swissvotes domain metadata missing columns: {sorted(required - set(domain_metadata))}")
    if domain_metadata.vote_id.isna().any() or domain_metadata.vote_id.duplicated().any():
        raise ValueError("Swissvotes domain metadata needs unique vote identifiers")
    return domain_metadata.sort_values("vote_id", kind="stable").reset_index(drop=True).copy()


def _normalize_ofs_objects(frame: pd.DataFrame) -> pd.DataFrame:
    vote_column = "vote_id" if "vote_id" in frame else None
    date_column = "voting_date" if "voting_date" in frame else "vote_date"
    subsidiary_column = "is_subsidiary" if "is_subsidiary" in frame else "is_tiebreak_question"
    if vote_column is None or date_column not in frame or subsidiary_column not in frame:
        raise ValueError("OFS objects require vote_id, vote_date/voting_date, and subsidiary status")
    objects = frame[[vote_column, date_column, subsidiary_column]].copy()
    objects = objects.rename(columns={vote_column: "vote_id", date_column: "voting_date", subsidiary_column: "is_subsidiary"})
    objects["vote_id"] = ofs_keys(objects.vote_id)
    objects["vote_key"] = objects.vote_id
    objects["voting_date"] = pd.to_datetime(objects.voting_date, errors="coerce", utc=True, format="mixed").dt.normalize()
    objects["is_subsidiary"] = _nullable_bool(objects.is_subsidiary)
    if objects.vote_id.isna().any():
        raise ValueError("OFS object identifiers cannot be missing")
    return objects


def _normalize_swissvotes(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"anr", "datum", "rechtsform", *DOMAIN_SOURCE_COLUMNS}
    if required - set(frame.columns):
        raise ValueError(f"Swissvotes source missing columns: {sorted(required - set(frame.columns))}")
    source = frame.copy(deep=True).reset_index(drop=True)
    source["swissvotes_id"] = source.anr.astype("string").str.strip()
    source["vote_key"] = source.swissvotes_id.map(_swissvotes_key_or_missing).astype("string")
    # ISO dates must retain year-month-day ordering, including with dayfirst
    # parsing of the original Swissvotes day.month.year CSV values.
    iso = source.datum.astype("string").str.match(r"^\d{4}-\d{2}-\d{2}", na=False)
    source["vote_date"] = pd.to_datetime(source.datum.where(iso), errors="coerce", utc=True, format="ISO8601")
    source.loc[~iso, "vote_date"] = pd.to_datetime(
        source.loc[~iso, "datum"], errors="coerce", utc=True, format="mixed", dayfirst=True)
    source["vote_date"] = source.vote_date.dt.normalize()
    source["_legal_form_code"] = source.rechtsform.map(_integer_code)
    source["is_subsidiary"] = source["_legal_form_code"].eq(5).astype("boolean").where(source["_legal_form_code"].notna())
    invalid = source.loc[source.vote_key.isna()].copy()
    return source.loc[source.vote_key.notna()].copy(), invalid


def _source_features(source: pd.Series) -> dict:
    legal_form_code = source["_legal_form_code"]
    legal_form = LEGAL_FORM_LABELS.get(legal_form_code)
    domains, domain_status = _domain_codes(source)
    result = {"legal_form": legal_form, "domain_codes": domains, "domain_status": domain_status}
    for domain_number, name in enumerate(DOMAIN_COLUMNS, start=1):
        result[name] = float(domain_number in domains) if domain_status == "known" else float("nan")
    return result


def _empty_metadata_record(vote_id: str, source_version: str) -> dict:
    return {
        "vote_id": vote_id, "legal_form": None,
        "domain_codes": (), "domain_status": "unknown_classification",
        **{name: float("nan") for name in DOMAIN_COLUMNS},
        "object_match_status": "unmatched", "object_match_evidence": None,
        "source_version": source_version,
    }


def _domain_codes(source: pd.Series) -> tuple[tuple[int, ...], str]:
    codes: set[int] = set()
    for column in DOMAIN_SOURCE_COLUMNS:
        raw = source[column]
        if _is_missing_code(raw):
            continue
        code = _integer_code(raw)
        if code not in range(1, 13):
            return (), "unknown_classification"
        codes.add(code)
    if not codes:
        return (), "unknown_classification"
    return tuple(sorted(codes)), "known"


def _is_missing_code(value) -> bool:
    if pd.isna(value):
        return True
    return str(value).strip().casefold() in {"", ".", "nan", "<na>"}


def _integer_code(value) -> int | None:
    if _is_missing_code(value):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not number.is_integer():
        return None
    return int(number)


def _swissvotes_key_or_missing(value) -> str | None:
    try:
        return swissvotes_key(value)
    except (ValueError, TypeError):
        return None


def _nullable_bool(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.astype("boolean")
    normalized = values.astype("string").str.strip().str.casefold()
    return normalized.map({"true": True, "1": True, "false": False, "0": False}).astype("boolean")


def _attach_publication_evidence(
    records: pd.DataFrame,
    *,
    source_version: str,
    published_at: str | pd.Timestamp | None,
    publication_evidence: str | None,
    reference_date: str | pd.Timestamp | None,
    publication_records: pd.DataFrame | None,
) -> pd.DataFrame:
    result = records.copy(deep=True)
    result["published_at"] = pd.to_datetime(published_at, errors="coerce", utc=True)
    result["reference_date"] = pd.to_datetime(reference_date, errors="coerce", utc=True)
    result["availability_evidence"] = publication_evidence
    result["availability_status"] = "unknown"
    if publication_records is not None:
        required = {"vote_id", "published_at", "reference_date", "availability_evidence", "source_version"}
        if required - set(publication_records.columns):
            raise ValueError(f"Swissvotes publication records missing columns: {sorted(required - set(publication_records))}")
        evidence = publication_records.loc[:, list(required)].copy()
        evidence["vote_id"] = ofs_keys(evidence.vote_id)
        if evidence.vote_id.duplicated().any():
            raise ValueError("Swissvotes publication records require unique vote_id values")
        evidence["published_at"] = pd.to_datetime(evidence.published_at, errors="coerce", utc=True, format="mixed")
        evidence["reference_date"] = pd.to_datetime(evidence.reference_date, errors="coerce", utc=True, format="mixed")
        if evidence.source_version.isna().any() or evidence.source_version.ne(source_version).any():
            raise ValueError("Swissvotes publication evidence must identify the exact metadata version")
        evidence = evidence.drop(columns="source_version")
        result = result.drop(columns=["published_at", "reference_date", "availability_evidence"])
        result = result.merge(evidence, on="vote_id", how="left", validate="one_to_one", sort=False)
    evidence_present = result.availability_evidence.notna() & result.availability_evidence.astype("string").str.strip().ne("")
    verified = result.published_at.notna() & result.reference_date.notna() & evidence_present
    if "source_version" in result:
        verified &= result.source_version.eq(source_version)
    result.loc[verified, "availability_status"] = "verified"
    return result
