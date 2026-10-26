"""Prepare separate municipal party results with official identifiers.

Run from the repository root: python -m scripts.elections.build_election_features.
Publication dates and historical geography are not inferred from election years.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from scripts.common.config import INTERIM_DIR, PROCESSED_DIR, RAW_DIR
from scripts.repertoire_communes.commune_crosswalk import (
    load_mutations,
    load_snapshot_codes,
    resolve,
)

RAW_PATH = RAW_DIR / "elections_conseil_national_brut.csv"
GEO = "Bezirk (>>) / Gemeinde (......)"
SOURCE_GEOGRAPHY_DATE = date(2023, 7, 1)  # NOTE[fr] du cube PX officiel.
REFERENCE_DATE = date(2026, 1, 1)


def build(raw: pd.DataFrame) -> pd.DataFrame:
    required = [f"code_{name}" for name in (GEO, "Jahr", "Partei", "Ergebnisse")]
    if not set(required).issubset(raw.columns):
        raise ValueError("Re-run election collection to preserve official dimension codes")
    # Les libellés identifient le niveau ; la jointure utilise uniquement le code OFS.
    label = raw.columns[0]
    communes = raw.loc[raw[label].str.startswith("......")].copy()
    communes["municipality_id"] = communes[f"code_{GEO}"].astype("string").str.zfill(4)
    communes["election_year"] = pd.to_numeric(communes["code_Jahr"]).astype("int16")
    communes["party_code"] = communes["code_Partei"].astype("string")
    communes["party_name"] = communes[raw.columns[2]].astype("string")
    communes["municipality_name"] = communes[label].str.removeprefix("......")
    communes["value"] = pd.to_numeric(communes["value"], errors="raise")
    keys = ["municipality_id", "election_year", "party_code", "party_name", "municipality_name"]
    if communes.duplicated(keys[:3] + ["code_Ergebnisse"]).any():
        raise ValueError("Duplicate municipality/year/party/result keys")
    table = communes.pivot(index=keys, columns="code_Ergebnisse", values="value")
    table = table.rename(columns={"1": "party_votes", "2": "party_strength_pct"}).reset_index()
    table.columns.name = None
    table["party_votes"] = table["party_votes"].astype("Int64")
    strength = table["party_strength_pct"].dropna()
    if not strength.between(0, 100).all() or table["party_votes"].dropna().lt(0).any():
        raise ValueError("Invalid party votes or percentages")
    table["party_share"] = table["party_strength_pct"] / 100
    table["is_special_unit"] = pd.to_numeric(table["municipality_id"]).ge(9000)
    # Les valeurs manquantes restent manquantes, elles ne représentent pas forcément zéro.
    table["available_from"] = pd.NaT
    table["availability_status"] = "UNVERIFIED"
    return table.sort_values(keys[:3]).reset_index(drop=True)


def harmonize(table: pd.DataFrame) -> pd.DataFrame:
    """Sum counts on the reference geography, never average party percentages."""
    table = table.copy()
    mutations = load_mutations()
    reference = load_snapshot_codes(REFERENCE_DATE)
    mapping = {}
    for code in table.loc[~table.is_special_unit, "municipality_id"].unique():
        targets = resolve(str(int(code)), SOURCE_GEOGRAPHY_DATE, REFERENCE_DATE, mutations)
        if len(targets) != 1 or not targets <= reference.keys():
            raise ValueError(f"Election commune requires reviewed geographic weights: {code}: {targets}")
        mapping[code] = next(iter(targets)).zfill(4)
    table["source_municipality_id"] = table.municipality_id
    table["municipality_id"] = table.municipality_id.map(mapping).fillna(table.municipality_id)
    # Le total des suffrages permet de recalculer la force après les fusions.
    totals = table.groupby(["municipality_id", "election_year"]).party_votes.sum(min_count=1)
    keys = ["municipality_id", "election_year", "party_code", "party_name"]
    grouped = table.groupby(keys, sort=True)
    output = grouped.agg(
        party_votes=("party_votes", lambda s: s.sum(min_count=len(s))),
        source_communes=("source_municipality_id", "nunique"),
        source_values_missing=("party_votes", lambda s: int(s.isna().sum())),
    ).reset_index()
    output = output.merge(totals.rename("total_party_votes"), on=["municipality_id", "election_year"], validate="many_to_one")
    output["party_share"] = output.party_votes / output.total_party_votes.where(output.total_party_votes.gt(0))
    output["party_strength_pct"] = output.party_share * 100
    names = {code.zfill(4): name for code, name in reference.items()}
    source_names = table.set_index("municipality_id").municipality_name.to_dict()
    output["municipality_name"] = output.municipality_id.map(names).fillna(output.municipality_id.map(source_names))
    output["is_special_unit"] = pd.to_numeric(output.municipality_id).ge(9000)
    output["geography_date"] = pd.Timestamp(REFERENCE_DATE)
    output["available_from"] = pd.NaT
    output["availability_status"] = "UNVERIFIED"
    crosswalk = pd.DataFrame([{"source_code": k, "target_code": v} for k, v in mapping.items()])
    crosswalk.to_parquet(INTERIM_DIR / "elections" / "commune_crosswalk.parquet", index=False)
    return output


def main() -> None:
    px_path = RAW_DIR / "elections" / "px-x-1702020000_105.px"
    # La géographie doit être vérifiée de nouveau si l'OFS change de millésime.
    header = px_path.read_text(encoding="cp1252").split("\nDATA=", 1)[0]
    if "communes au 01.07.2023" not in header:
        raise ValueError("Election source geography changed; review the official PX metadata")
    raw = pd.read_csv(RAW_PATH, dtype="string")
    interim = INTERIM_DIR / "elections"
    interim.mkdir(parents=True, exist_ok=True)
    raw["value"] = pd.to_numeric(raw["value"], errors="raise")
    raw.to_parquet(interim / "elections_all_levels.parquet", index=False)
    table = build(raw)
    table.to_parquet(interim / "elections_communes_2023_geography.parquet", index=False)
    table = harmonize(table)
    output = PROCESSED_DIR / "elections"
    output.mkdir(parents=True, exist_ok=True)
    table.to_parquet(output / "elections_communes.parquet", index=False)
    print(f"Elections: {len(table):,} rows, {table.municipality_id.nunique()} units, "
          f"years {sorted(table.election_year.unique().tolist())}")


if __name__ == "__main__":
    main()
