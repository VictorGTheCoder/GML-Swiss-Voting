"""Download the OFS typologies territoriales / régions linguistiques (Excel) into data/raw/typologies/.

Excel export of the "Niveaux géographiques" query of the Application des communes suisses
(typologie des communes 2020 and régions linguistiques 2020 on the 2026 commune register). This is
a web form, not a documented API, so the export may change without notice.

Usage: python -m scripts.typologies.download_typologies [--force]
"""

from __future__ import annotations

import argparse

import requests

from scripts.common.communes import (
    AGVCH_BASE,
    REFERENCE_DATE,
    ROOT,
    TIMEOUT_SECONDS,
    TYPOLOGIES_RAW_DIR,
    record_provenance,
    request_with_retry,
    should_skip,
    write_atomic,
)

# Level codes of the "Typologies" query form (see /fr/typologies/query). Older vintages such as
# HR_GDETYP2012 are only accepted for snapshot dates within their validity period.
TYPOLOGY_LEVELS = ["HR_GDETYP2020", "HR_SPRGEB2020"]


def download_typologies(session: requests.Session, force: bool) -> None:
    """Excel export of the 'Niveaux géographiques' query (typology 2020, language regions 2020)."""
    path = TYPOLOGIES_RAW_DIR / f"typologies_{REFERENCE_DATE.isoformat()}.xlsx"
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


def ensure_raw_data(force: bool = False) -> None:
    """Download the raw files that are missing (all of them with ``force``); used by run_pipeline."""
    download_typologies(requests.Session(), force)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="replace the existing raw file")
    args = parser.parse_args()
    try:
        ensure_raw_data(args.force)
    except (requests.RequestException, RuntimeError) as error:
        raise SystemExit(f"Typologies download failed: {error}") from error


if __name__ == "__main__":
    main()
