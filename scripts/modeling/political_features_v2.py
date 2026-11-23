"""Target-blind political cues for explicitly retrospective municipal experiments.

The current Swissvotes edition describes recommendations made before voting, but
does not prove when its exact historical values were available. This module does
not make these features admissible to the project's strict forecasting pipeline.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

CODEBOOK_URL = "https://swissvotes.ch/page/dataset/codebook-de.pdf"
SOURCE_URL = "https://swissvotes.ch/page/dataset/swissvotes_dataset.csv"
PREFIX = "political_"

# Local electoral shares retain the original party identities. In particular,
# Centre does not inherit PDC/PBD shares or instructions by an implicit fallback.
PARTIES = {
    "plr": "fdp", "pdc": "cvp", "ps": "sps", "udc": "svp", "pev": "evp",
    "verts": "gps", "pvl": "glp", "pbd": "bdp", "centre": "mitte",
}
PARTY_CODES = {
    1: "yes", 2: "no", 3: "no_recommendation", 4: "blank_ballot",
    5: "free_vote", 8: "prefer_counterproposal", 9: "prefer_initiative",
    66: "neutral_legacy", 9999: "not_existing",
}
INSTITUTIONS = {"federal_council": "br-pos", "parliament": "bv-pos",
                "national_council": "nr-pos", "council_of_states": "sr-pos"}
INSTITUTION_CODES = {1: "yes", 2: "no", 3: "no_recommendation",
                     8: "prefer_counterproposal", 9: "prefer_initiative"}
DOMAIN_FIELDS = tuple(f"d{topic}e{level}" for topic in range(1, 4) for level in (2, 3))
NATIONAL_SUPPORT_FIELDS = {"yes": "ja-lager", "no": "nein-lager"}
SOURCE_FIELDS = (
    tuple(f"p-{code}" for code in PARTIES.values())
    + tuple(INSTITUTIONS.values())
    + ("nrja", "nrnein", "srja", "srnein")
    + tuple(NATIONAL_SUPPORT_FIELDS.values())
    + DOMAIN_FIELDS
)


def _clean_numeric(series: pd.Series) -> pd.Series:
    """Coerce only this selected field, without interpreting 9999 globally."""
    result = pd.to_numeric(series.replace({".": pd.NA, "": pd.NA}), errors="coerce")
    return result.astype(float).where(np.isfinite(result.astype(float)))


def _present(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip()
    return normalized.notna() & ~normalized.isin(["", "."])


def _category(series: pd.Series, codes: dict[int, str]) -> tuple[pd.Series, pd.Series, int]:
    raw = _clean_numeric(series)
    valid = raw.isin(codes)
    invalid = int((_present(series) & ~valid).sum())
    raw = raw.where(valid)
    # Keeping the non-binary categories distinct avoids inventing an ideological
    # midpoint for abstention, free voting, a nonexistent party, or an unknown.
    return raw.map(codes).astype(object), raw.map({1: 1.0, 2: -1.0}), invalid


def _validate_keys(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    if not frame.columns.is_unique:
        raise ValueError(f"{label}: duplicate column names")
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"{label}: missing required columns {sorted(missing)}")
    keys = frame[columns].astype("string")
    if keys.isna().any().any() or keys.apply(lambda c: c.str.strip().eq("")).any().any():
        raise ValueError(f"{label}: null or empty keys")
    if keys.duplicated().any():
        raise ValueError(f"{label}: duplicate keys {columns}")


def _date_values(series: pd.Series, label: str) -> pd.Series:
    values = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    if values.isna().any():
        raise ValueError(f"{label}: missing or invalid voting date")
    return values.dt.normalize()


def add_political_features(
    table: pd.DataFrame, swiss: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Append allowlisted object cues and local electoral interactions.

    Parameters
    ----------
    table:
        A unique municipality_id x vote_id table, with vote_key, vote_date, and
        optional party_share_* fields in [0, 1]. Existing columns are preserved.
    swiss:
        Swissvotes records with unique vote_key and matching vote_date. Only
        SOURCE_FIELDS and correspondence/type metadata are read. Optional absent
        source fields become missing and are reported; mismatched objects fail.

    Returns
    -------
    (enriched, manifest):
        The input index, order and row keys are preserved. The manifest provides
        exact numeric/categorical allowlists, feature groups, encoding decisions,
        missingness, rejected values and unverified availability status. Callers
        must select predictors from these lists, not all returned columns.
    """
    _validate_keys(table, ["municipality_id", "vote_id"], "municipal table")
    _validate_keys(swiss, ["vote_key"], "Swissvotes")
    if {"vote_key", "vote_date"} - set(table) or "vote_date" not in swiss:
        raise ValueError("Both inputs require vote_key and vote_date")
    if table.vote_key.isna().any() or table.vote_key.astype("string").str.strip().eq("").any():
        raise ValueError("municipal table: null or empty vote_key")
    if any(str(column).startswith(PREFIX) for column in table):
        raise ValueError("Political output columns already exist; refusing to overwrite them")

    original_dates = _date_values(table.vote_date, "municipal table")
    correspondence = pd.DataFrame({"vote_id": table.vote_id.astype(str).to_numpy(),
                                   "vote_key": table.vote_key.astype(str).to_numpy(),
                                   "date": original_dates.to_numpy()})
    if correspondence.groupby("vote_id")[["vote_key", "date"]].nunique().gt(1).any().any():
        raise ValueError("A vote_id maps to inconsistent keys or dates")
    if correspondence.groupby("vote_key").vote_id.nunique().gt(1).any():
        raise ValueError("A vote_key maps to multiple vote_id values")

    selected_fields = [name for name in SOURCE_FIELDS if name in swiss]
    metadata = ["vote_key", "vote_date"] + (["rechtsform"] if "rechtsform" in swiss else [])
    source = swiss[metadata + selected_fields].copy()
    source["vote_key"] = source.vote_key.astype(str)
    source = source.set_index("vote_key")
    keys = table.vote_key.astype(str)
    unique_keys = pd.Index(keys.unique(), name="vote_key")
    absent = unique_keys.difference(source.index)
    if len(absent):
        raise ValueError(f"Unmatched Swissvotes objects: {absent[:10].tolist()}")
    source = source.reindex(unique_keys)
    source_dates = _date_values(source.vote_date, "matched Swissvotes objects")
    mapped_dates = source_dates.reindex(keys.to_numpy()).to_numpy()
    if not np.array_equal(original_dates.to_numpy(), mapped_dates):
        raise ValueError("Swissvotes object voting dates disagree with the municipal table")
    if "rechtsform" in source and _clean_numeric(source.rechtsform).eq(5).any():
        raise ValueError("Subsidiary questions must be excluded before binary-yes feature preparation")

    fingerprint = source.sort_index().to_json(orient="split", date_format="iso")
    missing_source_fields = [name for name in SOURCE_FIELDS if name not in source]
    for name in missing_source_fields:
        source[name] = np.nan

    features = pd.DataFrame(index=source.index)
    numeric: list[str] = []
    categorical: list[str] = []
    invalid: dict[str, int] = {}
    groups = {name: [] for name in (
        "party_categories", "party_signs", "local_interactions", "local_support",
        "institutions", "parliamentary_votes", "national_support", "detailed_domains")}

    def add(name, values, group, *, category=False):
        name = PREFIX + name
        features[name] = values
        (categorical if category else numeric).append(name)
        groups[group].append(name)

    for party, code in PARTIES.items():
        field = f"p-{code}"
        category, direction, invalid[field] = _category(source[field], PARTY_CODES)
        add(f"recommendation_{party}", category, "party_categories", category=True)
        add(f"direction_{party}", direction, "party_signs")

    for institution, field in INSTITUTIONS.items():
        codes = INSTITUTION_CODES if institution == "federal_council" else {
            key: value for key, value in INSTITUTION_CODES.items() if key != 9}
        category, direction, invalid[field] = _category(source[field], codes)
        add(f"recommendation_{institution}", category, "institutions", category=True)
        add(f"direction_{institution}", direction, "institutions")

    for chamber, maximum in (("nr", 200), ("sr", 46)):
        yes, no = (_clean_numeric(source[chamber + suffix]) for suffix in ("ja", "nein"))
        valid = (yes.ge(0) & no.ge(0) & yes.mod(1).eq(0) & no.mod(1).eq(0)
                 & (yes + no).gt(0) & (yes + no).le(maximum))
        fraction = (yes / (yes + no)).where(valid)
        present = _present(source[chamber + "ja"]) | _present(source[chamber + "nein"])
        invalid[f"{chamber}_vote_pair"] = int((present & ~valid).sum())
        add(f"{chamber}_yes_fraction", fraction, "parliamentary_votes")

    support = {}
    for name, field in NATIONAL_SUPPORT_FIELDS.items():
        values = _clean_numeric(source[field])
        invalid[field] = int((_present(source[field]) & ~values.between(0, 100)).sum())
        support[name] = values.where(values.between(0, 100)) / 100.0
    invalid_total = (support["yes"] + support["no"]).gt(1.0001)
    invalid["national_support_sum_over_one"] = int(invalid_total.sum())
    for name, values in support.items():
        support[name] = values.mask(invalid_total)
        add(f"national_{name}_electoral_share", support[name], "national_support")
    coverage = support["yes"] + support["no"]
    add("national_binary_coverage", coverage, "national_support")
    add("national_yes_fraction_known", support["yes"] / coverage.where(coverage.gt(0)), "national_support")

    for field in DOMAIN_FIELDS:
        # These are nominal codes, never ordinal scores or policy directions.
        values = source[field].astype("string").str.strip().replace({"": pd.NA, ".": pd.NA})
        valid = values.str.fullmatch(r"(?:[1-9]|1[0-2])\.[0-9]{1,2}", na=False)
        invalid[field] = int((values.notna() & ~valid).sum())
        add(f"domain_{field}", values.where(valid).astype(object), "detailed_domains", category=True)

    # Keep explicit scope allowlists; accidental constancy of a local feature on
    # a particular training sample must not make it an object-level predictor.
    object_numeric = numeric.copy()
    object_categorical = categorical.copy()
    # Replicate object-level features only after target-blind transformation.
    aligned = features.reindex(keys.to_numpy()).reset_index(drop=True)
    aligned.index = table.index
    local_shares = pd.DataFrame(index=table.index)
    signs = pd.DataFrame(index=table.index)
    invalid_local: dict[str, int] = {}
    missing_local: list[str] = []
    for party in PARTIES:
        field = f"party_share_{party}"
        if field in table:
            share = _clean_numeric(table[field])
            invalid_local[field] = int((_present(table[field]) & ~share.between(0, 1)).sum())
            share = share.where(share.between(0, 1))
        else:
            missing_local.append(field)
            share = pd.Series(np.nan, index=table.index, dtype=float)
            invalid_local[field] = 0
        local_shares[party] = share
        signs[party] = aligned[f"{PREFIX}direction_{party}"]
        column = f"{PREFIX}local_cue_{party}"
        aligned[column] = share * signs[party]
        numeric.append(column)
        groups["local_interactions"].append(column)

    # These are observed electoral masses, not estimates of actual voter choices.
    # A zero contribution from an unknown recommendation is always accompanied by
    # observed mass / binary coverage; individual unknown signed cues remain NaN.
    known_local = local_shares.notna()
    yes_mass = local_shares.where(signs.eq(1), 0).where(known_local).sum(axis=1, min_count=1)
    no_mass = local_shares.where(signs.eq(-1), 0).where(known_local).sum(axis=1, min_count=1)
    known_mass = local_shares.sum(axis=1, min_count=1)
    binary_mass = yes_mass + no_mass
    local_aggregates = {
        "local_yes_mass": yes_mass,
        "local_no_mass": no_mass,
        "local_binary_coverage": binary_mass,
        "local_observed_party_mass": known_mass,
        "local_nonbinary_or_unknown_mass": known_mass - binary_mass,
        "local_yes_fraction_known": yes_mass / binary_mass.where(binary_mass.gt(0)),
        "local_missing_party_count": local_shares.isna().sum(axis=1),
    }
    for name, values in local_aggregates.items():
        column = PREFIX + name
        aligned[column] = values
        numeric.append(column)
        groups["local_support"].append(column)

    # Ordinary floats / Python string-or-NaN categories work with sklearn and
    # CatBoost adapters without leaking pandas' pd.NA into encoders.
    aligned[numeric] = aligned[numeric].astype(np.float32)
    for name in categorical:
        aligned[name] = aligned[name].astype(object).where(aligned[name].notna(), np.nan)
    enriched = pd.concat([table.copy(), aligned], axis=1)
    if len(enriched) != len(table) or not enriched.index.equals(table.index):
        raise AssertionError("Political feature preparation changed municipal row identity")

    manifest = {
        "schema_version": 1,
        "mode": "exploratory_retrospective",
        "strict_forecast_ready": False,
        "availability_status": "historically_unverified",
        "availability_note": "Current Swissvotes edition; per-object historical release evidence is not established.",
        "source_url": SOURCE_URL,
        "codebook_url": CODEBOOK_URL,
        "codebook_pages": {"institutions_and_parliament": [12, 13, 14],
                           "party_recommendations": [21, 22, 23], "national_electoral_support": [26, 27, 28]},
        "source_fields": list(SOURCE_FIELDS),
        "source_selected_sha256": hashlib.sha256(fingerprint.encode()).hexdigest(),
        "numeric_features": numeric,
        "categorical_features": categorical,
        "object_numeric_features": object_numeric,
        "object_categorical_features": object_categorical,
        "feature_groups": groups,
        "party_mapping": PARTIES.copy(),
        "party_codes": {str(key): value for key, value in PARTY_CODES.items()},
        "party_direction_rule": "1 => +1; 2 => -1; every other category or missing value => NaN",
        "party_merger_policy": "PDC, PBD and Centre remain separate; no inherited shares or recommendations.",
        "local_support_definition": "Observed prior local electoral shares summed for explicit yes/no recommendations; zero mass is not evidence of opposition. Read binary coverage and missing-party count alongside it.",
        "national_support_definition": "Swissvotes ja-lager/nein-lager sum party shares at the last national election before the vote; these are not referendum outcomes.",
        "domain_note": "Detailed policy-domain categories describe subject matter, not the effect of a yes vote.",
        "excluded_source_families": ["referendum outcomes", "turnout", "current electorate", "campaign advertising", "media tone", "campaign finance", "cantonal dissidence with ambiguous missingness", "free-text post-vote descriptions"],
        "rows": len(table),
        "objects": len(unique_keys),
        "join": {"matched_rows": len(table), "missing_objects": 0, "date_mismatches": 0,
                 "row_losses": 0, "same_object_type": "subsidiary questions rejected when rechtsform is present"},
        "missing_source_columns": missing_source_fields,
        "missing_local_columns": missing_local,
        "invalid_source_values_by_field_on_unique_objects": invalid,
        "invalid_local_values_by_field_on_rows": invalid_local,
        "missing_feature_rows": {name: int(aligned[name].isna().sum()) for name in numeric + categorical},
    }
    return enriched, manifest
