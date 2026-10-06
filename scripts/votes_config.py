"""Shared constants for the federal vote results pipeline (OFS px-x-1703030000_101)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
INTERIM_DIR = ROOT / "data" / "interim"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

OFS_TABLE_ID = "px-x-1703030000_101"
DATASET_NAME_FR = "Votations populaires (résultats au niveau des communes depuis 1960)"
# PXWeb serves the complete cube as a PX file keyed on the stable table id.
# (The DAM asset number behind bfs.admin.ch changes with every data update.)
DOWNLOAD_URL = f"https://www.pxweb.bfs.admin.ch/DownloadFile.aspx?file={OFS_TABLE_ID}"
SOURCE_PAGE_URL = f"https://www.bfs.admin.ch/asset/fr/{OFS_TABLE_ID}"
PXWEB_API_URL = f"https://www.pxweb.bfs.admin.ch/api/v1/fr/{OFS_TABLE_ID}/{OFS_TABLE_ID}.px"

RAW_PX_PATH = RAW_DIR / f"{OFS_TABLE_ID}.px"
PROVENANCE_PATH = RAW_DIR / f"{OFS_TABLE_ID}.provenance.json"
INTERIM_PATH = INTERIM_DIR / "votes_all_levels.parquet"
PROCESSED_PATH = PROCESSED_DIR / "votes_communes.parquet"

# PX dimension names (German is the file's default language).
DIM_LOCATION = "Kanton (-) / Bezirk (>>) / Gemeinde (......)"
DIM_VOTE = "Datum und Vorlage"
DIM_RESULT = "Ergebnis"
DIM_LOCATION_FR = "Canton (-) / District (>>) / Commune (......)"
DIM_VOTE_FR = "Date et objet"

# Result codes of the "Ergebnis" dimension -> project column names.
# Meanings checked against VALUES/VALUES[fr] in the PX metadata.
RESULT_COLUMNS = {
    "1": "eligible_voters",   # Stimmberechtigte / Electeurs inscrits
    "2": "ballots_cast",      # Abgegebene Stimmen / Bulletins rentrés
    "3": "turnout_pct_ofs",   # Beteiligung in % / Participation en %
    "4": "valid_ballots",     # Gültige Stimmzettel / Bulletins valables
    "5": "votes_yes",         # Ja / Oui
    "6": "votes_no",          # Nein / Non
    "7": "yes_pct_ofs",       # Ja in % / Oui en %
}
COUNT_COLUMNS = ["eligible_voters", "ballots_cast", "valid_ballots", "votes_yes", "votes_no"]
# Codes >= 9000 are "special communes" of political statistics
# (Swiss abroad, correspondence votes, unassigned ballots), see PX NOTE.
SPECIAL_UNIT_MIN_CODE = 9000


def is_special_code(code: str) -> bool:
    """True for commune-level special units; False for communes and aggregate levels."""
    return len(code) == 4 and code.isdigit() and int(code) >= SPECIAL_UNIT_MIN_CODE
