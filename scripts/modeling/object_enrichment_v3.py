"""Additional pre-vote object cues from the controlled Swissvotes snapshot.

This adds information already present in the source but unused by V2: stakeholder
recommendations and petition/procedure descriptors. It does not certify source
vintages. Post-vote fields, campaign totals, editor-written retrospective summaries
and individual survey answers are deliberately outside the source allowlist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.political_features_v2 import PARTY_CODES

STAKEHOLDERS = {
    "eco": "Economiesuisse / historical predecessor",
    "sgv": "Swiss trade association",
    "sbv": "Swiss farmers association",
    "sgb": "Swiss trade union federation",
    "travs": "Travail.Suisse / historical predecessor",
    "sav": "Swiss employers association",
    "vsa": "Federation of Swiss employee associations",
    "vpod": "Public service union",
    "voev": "Public transport association",
    "tcs": "Touring Club Suisse",
    "vcs": "Transport and environment association",
    "acs": "Automobile Club Suisse",
    "sbk": "Swiss bishops conference",
    "ssv": "Swiss cities association",
    "gem": "Swiss communes association",
    "kdk": "Conference of cantonal governments",
    "kkjpd": "Cantonal justice and police directors",
    "gdk": "Cantonal health directors",
    "ldk": "Cantonal agriculture directors",
    "vdk": "Cantonal economic affairs directors",
    "sodk": "Cantonal social affairs directors",
    "endk": "Cantonal energy directors",
    "fdk": "Cantonal finance directors",
    "bpuk": "Cantonal construction planning and environment directors",
}
PROCEDURE_FIELDS = (
    "anzahl", "dep", "unter_g", "unter-quorum", "sammeltempo",
    "dat-submit", "dat-parl", "dat-success", "rechtsform",
)
DOMAIN_FIELDS = tuple(f"d{slot}e{level}" for slot in (1, 2, 3) for level in (1, 2, 3))
SOURCE_FIELDS = tuple(f"p-{code}" for code in STAKEHOLDERS) + PROCEDURE_FIELDS + DOMAIN_FIELDS
PARTIALLY_CERTIFIED = frozenset(str(i * 10) for i in (644, 645, 647, 650, 653, 654, 655, 656, 660, 661))
CODEBOOK_URL = "https://swissvotes.ch/page/dataset/codebook-de.pdf"


def number(series):
    """Swiss grouping apostrophes are separators, never decimal punctuation."""
    text = series.astype("string").str.strip().str.replace(r"['’\s]", "", regex=True)
    text = text.replace({".": pd.NA, "": pd.NA})
    result = pd.to_numeric(text, errors="coerce").astype(float)
    return result.where(np.isfinite(result))


def _date(series):
    # The controlled Swissvotes source uses DD.MM.YYYY, including legacy '0'.
    return pd.to_datetime(series.astype("string"), format="%d.%m.%Y", errors="coerce")


def _domain_token(value):
    if pd.isna(value) or str(value).strip() in ("", ".", "0", "0.0"):
        return None
    token = str(value).strip()
    if re.fullmatch(r"\d+\.0", token):
        token = token[:-2]
    if not re.fullmatch(r"\d+(?:\.\d+){0,2}", token):
        raise ValueError(f"Invalid Swissvotes domain code: {token}")
    # Codes such as 6.12 are labels, not measured numeric magnitudes.
    return token


def build_object_features(objects, swiss):
    """Return one row per exact object, preserving the supplied object order."""
    keys = ["vote_id", "vote_key", "vote_date"]
    obj = objects[keys].copy().reset_index(drop=True)
    if obj.empty or obj[keys].isna().any().any():
        raise ValueError("Object keys and dates must be present")
    obj["vote_key"] = obj.vote_key.astype(str)
    obj["vote_date"] = pd.to_datetime(obj.vote_date)
    if obj.vote_id.duplicated().any() or obj.vote_key.duplicated().any():
        raise ValueError("Require one unique row per object")
    src = swiss[["vote_key", "vote_date", *[c for c in SOURCE_FIELDS if c in swiss]]].copy()
    if src.vote_key.isna().any():
        raise ValueError("Swissvotes keys must be unique and known")
    src["vote_key"] = src.vote_key.astype(str)
    if src.vote_key.isna().any() or src.vote_key.duplicated().any():
        raise ValueError("Swissvotes keys must be unique and known")
    src = src.set_index("vote_key")
    if not obj.vote_key.isin(src.index).all():
        raise ValueError("Unmatched object in source")
    src = src.reindex(obj.vote_key).reset_index(drop=True)
    if not np.array_equal(pd.to_datetime(src.vote_date).to_numpy(), obj.vote_date.to_numpy()):
        raise ValueError("Object dates disagree with Swissvotes")
    absent = [c for c in SOURCE_FIELDS if c not in src]
    for column in absent:
        src[column] = np.nan
    out = obj.copy()
    groups = {"stakeholders": {"numeric": [], "categorical": []},
              "procedure": {"numeric": [], "categorical": []}}
    invalid = {}
    for code in STAKEHOLDERS:
        raw = number(src[f"p-{code}"])
        supplied = src[f"p-{code}"].astype("string").str.strip()
        present = supplied.notna() & ~supplied.isin(["", "."])
        invalid[code] = int((present & ~raw.isin(PARTY_CODES)).sum())
        if invalid[code]:
            raise ValueError(f"Unknown recommendation codes for {code}")
        name = f"extra_stakeholder_{code}"
        out[name] = raw.map(PARTY_CODES)
        groups["stakeholders"]["categorical"].append(name)

    def add(name, value, category=False):
        name = "extra_" + name
        out[name] = value
        groups["procedure"]["categorical" if category else "numeric"].append(name)

    cutoff = obj.vote_date - pd.Timedelta(days=1)
    legal = number(src.rechtsform)
    mandatory = legal.eq(1)
    collected = legal.isin([2, 3, 4])
    submitted = _date(src["dat-submit"])
    certified = _date(src["dat-success"])
    signature_eligible = collected & submitted.le(cutoff) & certified.le(cutoff)
    count = number(src.unter_g).where(signature_eligible)
    count = count.where(count.ge(0))
    quota = number(src["unter-quorum"]).where(signature_eligible)
    quota = quota.where(quota.gt(0))
    speed = number(src.sammeltempo).where(signature_eligible)
    speed = speed.where(speed.ge(0))
    add("ballot_object_count", number(src.anzahl).where(number(src.anzahl).ge(1)))
    department = number(src.dep)
    add("responsible_department", department.map(lambda x: str(int(x)) if pd.notna(x) else np.nan), True)
    add("log_valid_signatures", np.log1p(count))
    add("signature_quorum_ratio", count / quota)
    add("log_signatures_per_day", np.log1p(speed))
    add("signature_status", pd.Series(np.select(
        [mandatory, signature_eligible, collected],
        ["not_applicable", "date_gated_observation", "missing_or_not_yet_certified"],
        default="other_legal_form"), index=out.index), True)
    add("partial_signature_certification", obj.vote_key.isin(PARTIALLY_CERTIFIED).astype(float))
    parliament_date = _date(src["dat-parl"])
    add("days_since_parliament", (obj.vote_date - parliament_date).dt.days.where(parliament_date.le(cutoff)))

    # Keep three topic levels as sets. The vocabulary must be fitted per train.
    for level in (1, 2, 3):
        columns = [f"d{slot}e{level}" for slot in (1, 2, 3)]
        out[f"extra_domain_tokens_{level}"] = src[columns].apply(
            lambda row: "|".join(sorted({token for v in row if (token := _domain_token(v))})), axis=1)
    audit = {
        "source": "controlled data/processed/swissvotes/swissvotes_clean.parquet",
        "codebook": CODEBOOK_URL, "source_fields": list(SOURCE_FIELDS),
        "source_fields_missing": absent, "objects": len(out), "groups": groups,
        "stakeholder_names": STAKEHOLDERS,
        "numeric_features": sum((g["numeric"] for g in groups.values()), []),
        "categorical_features": sum((g["categorical"] for g in groups.values()), []),
        "domain_token_fields": [f"extra_domain_tokens_{i}" for i in (1, 2, 3)],
        "nonmissing_objects": {c: int(out[c].notna().sum()) for c in out if c.startswith("extra_")},
        "signature_date_gate_passed_objects": int(signature_eligible.sum()),
        "signature_gate": "submission AND certification dates <= previous calendar day",
        "recommendations": "Codes retained distinctly, including free vote, unknown, and organisation not existing; no assumed individual response",
        "domain_encoding": "Unordered level-specific sets; learn vocabulary on training objects only",
        "strict_forecast_ready": False,
        "historical_availability": "Pre-vote events described by current source; historical source editions unverified",
        "post_vote_fields_read": False,
    }
    return out, audit


def fit_domain_vocabulary(train_objects):
    result = {}
    for level in (1, 2, 3):
        field = f"extra_domain_tokens_{level}"
        result[field] = sorted({t for value in train_objects[field] for t in value.split("|") if t})
    return result


def encode_domains(objects, vocabulary):
    """Multi-hot encoding; unseen domains yield no invented fitted coefficient."""
    columns = {}
    for field, tokens in vocabulary.items():
        observed = objects[field].map(lambda value: set(value.split("|")) - {""})
        for token in tokens:
            name = field.replace("tokens", "present") + "_" + token.replace(".", "_")
            columns[name] = observed.map(lambda values: token in values).astype("uint8")
    return pd.DataFrame(columns, index=objects.index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "reports/generated/municipal_v3_base")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/municipal_v3")
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    if (output / "object_features.csv").exists():
        raise FileExistsError("Preserve the existing feature snapshot; choose a new directory")
    data = pd.read_parquet(args.input / "dataset.parquet", columns=["vote_id", "vote_key", "vote_date"])
    objects = data.drop_duplicates("vote_id").reset_index(drop=True)
    source = ROOT / "data/processed/swissvotes/swissvotes_clean.parquet"
    features, audit = build_object_features(objects, pd.read_parquet(source))
    features.to_csv(output / "object_features.csv", index=False)
    audit["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    audit["preparation_code_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    audit["features_sha256"] = hashlib.sha256((output / "object_features.csv").read_bytes()).hexdigest()
    (output / "manifest.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"objects": len(features), "added_features": len(audit["numeric_features"]) + len(audit["categorical_features"]),
                      "signature_observed": audit["signature_date_gate_passed_objects"]}))


if __name__ == "__main__":
    main()
