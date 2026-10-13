"""Download the commune reference datasets (répertoire, typologies, STATPOP) into data/raw/.

Sources (all Office fédéral de la statistique, OFS/BFS):
- Répertoire historique des communes (agvchapp API): snapshot of the communes at a
  reference date and the full mutation history, used to harmonise commune codes.
- Typologies territoriales / régions linguistiques: Excel export of the "Niveaux
  géographiques" query of the Application des communes suisses. This is a web form,
  not a documented API, so the export may change without notice.
- STATPOP (px-x-0102010000_101): permanent resident population by commune, nationality
  and age, fetched from the PXWeb JSON API one year at a time in batches of communes (the cube is
  too large for a single query).

Existing files are never replaced unless --force is given. A provenance file
(data/raw/communes/provenance.json) records URL, retrieval time, size and SHA-256.

Usage: python scripts/download_commune_refs.py [--only repertoire|typologies|statpop] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
COMMUNES_DIR = ROOT / "data" / "raw" / "communes"
STATPOP_DIR = ROOT / "data" / "raw" / "statpop"
PROVENANCE_PATH = COMMUNES_DIR / "provenance.json"

AGVCH_BASE = "https://www.agvchapp.bfs.admin.ch"
REFERENCE_DATE = date(2026, 1, 1)  # commune geography used by the vote results
SNAPSHOT_DATES = [date(2010, 1, 1), REFERENCE_DATE]
MUTATIONS_START = date(1960, 1, 1)

# Level codes of the "Typologies" query form (see /fr/typologies/query). Older vintages such as
# HR_GDETYP2012 are only accepted for snapshot dates within their validity period.
TYPOLOGY_LEVELS = ["HR_GDETYP2020", "HR_SPRGEB2020"]

STATPOP_TABLE_ID = "px-x-0102010000_101"
STATPOP_API_URL = f"https://www.pxweb.bfs.admin.ch/api/v1/fr/{STATPOP_TABLE_ID}/{STATPOP_TABLE_ID}.px"
DIM_YEAR, DIM_PLACE = "Jahr", "Kanton (-) / Bezirk (>>) / Gemeinde (......)"
DIM_POPTYPE, DIM_NATIONALITY, DIM_SEX, DIM_AGE = (
    "Bevölkerungstyp", "Staatsangehörigkeit (Kategorie)", "Geschlecht", "Alter",
)
PERMANENT_POPULATION = "1"
TOTAL_CODE = "-99999"

TIMEOUT_SECONDS = 300
MAX_RETRIES = 6
PAUSE_SECONDS = 3  # PXWeb answers 429 when queries come too fast
STATPOP_BATCH_SIZE = 100  # communes per query: the firewall answers 403 to large POST bodies/results


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def record_provenance(key: str, path: Path, url: str, **extra) -> None:
    content = path.read_bytes()
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8")) if PROVENANCE_PATH.exists() else {}
    provenance[key] = {
        "source": "Office fédéral de la statistique (OFS)",
        "url": url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file": path.relative_to(ROOT).as_posix(),
        "bytes": len(content),
        "sha256": sha256(content),
        **extra,
    }
    PROVENANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE_PATH.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def should_skip(path: Path, force: bool) -> bool:
    if path.exists() and not force:
        print(f"Already present, skipping: {path.relative_to(ROOT)} (use --force to replace)")
        return True
    return False


def request_with_retry(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    """Retry on 429/5xx and transient connection errors with exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            response = session.request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as error:
            if attempt == MAX_RETRIES - 1:
                raise
            print(f"  {type(error).__name__} for {url}, retrying in {10 * 2**attempt}s")
        else:
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response
            print(f"  HTTP {response.status_code} from {url}, retrying in {10 * 2**attempt}s")
        time.sleep(10 * 2**attempt)
    response.raise_for_status()
    return response


def write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_bytes(content)
    partial.replace(path)


def fr_date(day: date) -> str:
    return day.strftime("%d-%m-%Y")


def download_repertoire(session: requests.Session, force: bool) -> None:
    """Snapshots at the given dates + full mutation history (end date cannot be in the future)."""
    for day in SNAPSHOT_DATES:
        path = COMMUNES_DIR / f"snapshot_{day.isoformat()}.csv"
        if should_skip(path, force):
            continue
        url = f"{AGVCH_BASE}/api/communes/snapshot"
        response = request_with_retry(session, "GET", url, params={"date": fr_date(day), "useBfsCode": "true"})
        content = response.content
        if not content.lstrip(b"\xef\xbb\xbf").startswith(b"HistoricalCode"):
            raise RuntimeError(f"Unexpected snapshot payload: {content[:80]!r}")
        write_atomic(path, content)
        record_provenance(path.stem, path, response.url, snapshot_date=day.isoformat())
        print(f"Saved {path.relative_to(ROOT)} ({len(content):,} bytes)")

    path = COMMUNES_DIR / "mutations.csv"
    if should_skip(path, force):
        return
    end = date.today()
    params = {"includeTerritoryExchange": "false", "startPeriod": fr_date(MUTATIONS_START), "endPeriod": fr_date(end)}
    response = request_with_retry(session, "GET", f"{AGVCH_BASE}/api/communes/mutations", params=params)
    if not response.content.lstrip(b"\xef\xbb\xbf").startswith(b"MutationNumber"):
        raise RuntimeError(f"Unexpected mutations payload: {response.content[:80]!r}")
    write_atomic(path, response.content)
    record_provenance("mutations", path, response.url, start=MUTATIONS_START.isoformat(), end=end.isoformat())
    print(f"Saved {path.relative_to(ROOT)} ({len(response.content):,} bytes)")


def download_typologies(session: requests.Session, force: bool) -> None:
    """Excel export of the 'Niveaux géographiques' query (typology 2020, language regions 2020)."""
    path = COMMUNES_DIR / f"typologies_{REFERENCE_DATE.isoformat()}.xlsx"
    if should_skip(path, force):
        return
    query_url = f"{AGVCH_BASE}/fr/typologies/query"
    session.get(query_url, timeout=TIMEOUT_SECONDS).raise_for_status()  # session cookie
    snapshot = REFERENCE_DATE.strftime("%d.%m.%Y")
    form = [
        ("SnapshotDate", snapshot), ("category", "HCL_HRGDE"),
        ("VersionDate", snapshot), ("MinDate", "12.09.1848"),  # hidden fields of the form
    ]
    form += [("SelectedTypologies", code) for code in TYPOLOGY_LEVELS]
    # The form answers with a redirect to the results page, whose query string we reuse.
    redirect = session.post(query_url, data=form, allow_redirects=False, timeout=TIMEOUT_SECONDS)
    location = redirect.headers.get("Location", "")
    if redirect.status_code != 302 or "/typologies/results" not in location:
        raise RuntimeError(f"Typology query was not accepted (HTTP {redirect.status_code}, {location!r})")
    query_string = location.split("?", 1)[1]
    export_url = f"{AGVCH_BASE}/fr/typologies/results/xls?{query_string}"
    response = request_with_retry(session, "POST", export_url)
    if not response.content.startswith(b"PK"):
        raise RuntimeError("Typology export is not an xlsx file")
    write_atomic(path, response.content)
    record_provenance(path.stem, path, export_url, levels=TYPOLOGY_LEVELS, snapshot_date=REFERENCE_DATE.isoformat())
    print(f"Saved {path.relative_to(ROOT)} ({len(response.content):,} bytes)")


def download_statpop(session: requests.Session, force: bool) -> None:
    """One CSV per year: communes only, permanent residents, nationality x age, both sexes."""
    metadata = request_with_retry(session, "GET", STATPOP_API_URL).json()
    variables = {variable["code"]: variable for variable in metadata["variables"]}
    years = variables[DIM_YEAR]["values"]
    place = variables[DIM_PLACE]
    communes = [code for code, text in zip(place["values"], place["valueTexts"]) if text.startswith("......")]
    print(f"STATPOP: {len(years)} years, {len(communes)} commune codes")

    for year in years:
        path = STATPOP_DIR / f"statpop_{year}.csv"
        if should_skip(path, force):
            continue
        parts = []
        for start in range(0, len(communes), STATPOP_BATCH_SIZE):
            query = {
                "query": [
                    {"code": DIM_YEAR, "selection": {"filter": "item", "values": [year]}},
                    {"code": DIM_PLACE, "selection": {"filter": "item", "values": communes[start:start + STATPOP_BATCH_SIZE]}},
                    {"code": DIM_POPTYPE, "selection": {"filter": "item", "values": [PERMANENT_POPULATION]}},
                    {"code": DIM_NATIONALITY, "selection": {"filter": "all", "values": ["*"]}},
                    {"code": DIM_SEX, "selection": {"filter": "item", "values": [TOTAL_CODE]}},
                    {"code": DIM_AGE, "selection": {"filter": "all", "values": ["*"]}},
                ],
                "response": {"format": "csv"},
            }
            response = request_with_retry(session, "POST", STATPOP_API_URL, json=query)
            lines = response.content.decode("latin-1").splitlines(keepends=True)  # PXWeb CSV is ISO-8859-1
            parts.extend(lines if not parts else lines[1:])  # keep a single header row
            time.sleep(PAUSE_SECONDS)
        write_atomic(path, "".join(parts).encode("utf-8"))
        record_provenance(
            path.stem, path, STATPOP_API_URL, table=STATPOP_TABLE_ID, year=year,
            filters="communes only, permanent residents, sex total, nationality and single-year age detail",
        )
        print(f"Saved {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")


STEPS = {"repertoire": download_repertoire, "typologies": download_typologies, "statpop": download_statpop}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=STEPS, help="run a single step")
    parser.add_argument("--force", action="store_true", help="replace existing raw files")
    args = parser.parse_args()
    session = requests.Session()
    for name, step in STEPS.items():
        if args.only in (None, name):
            try:
                step(session, args.force)
            except (requests.RequestException, RuntimeError) as error:
                raise SystemExit(f"{name} download failed: {error}") from error


if __name__ == "__main__":
    main()
