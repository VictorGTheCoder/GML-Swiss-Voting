"""Collecte du tableau OFS px-x-1702020000_105 :
« Elections au Conseil national (suffrages des partis et force des partis depuis 1971 :
districts et communes) ».

On ne garde que les élections postérieures à 2010 (voir ANNEES), qui couvrent la fenêtre de
votations 2013-2024 du projet.

Sortie : data/raw/elections_conseil_national_brut.csv (format long, 466 600 lignes pour 4 années).

Usage (depuis la racine du dépôt) :
    python -m scripts.elections.collect_elections_conseil_national
    python -m scripts.elections.collect_elections_conseil_national --force
"""

import argparse
import json

import pandas as pd

from scripts.common.communes import record_provenance
from scripts.common.config import RAW_DIR
from scripts.common.pxweb_utils import (
    expected_rows,
    fetch_table,
    find_variable,
    is_complete,
    open_session,
    raw_dir,
    save_if_complete,
)

URL = "https://www.pxweb.bfs.admin.ch/api/v1/fr/px-x-1702020000_105/px-x-1702020000_105.px"
PAGE_URL = "https://www.pxweb.bfs.admin.ch/pxweb/fr/px-x-1702020000_105/-/px-x-1702020000_105.px"
OUT_NAME = "elections_conseil_national_brut.csv"

ANNEES = ["2011", "2015", "2019", "2023"]  # élections retenues (14 disponibles, 1971-2023)
PARTI_BATCH = 5  # partis par requête (25 d'un coup est trop volumineux)


def main(force: bool = False) -> None:
    out_path = raw_dir() / OUT_NAME
    session, headers_post = open_session(PAGE_URL)
    meta = session.get(URL).json()

    var_annee = find_variable(meta, "année", "jahr")
    var_parti = find_variable(meta, "parti", "partei")

    codes_annee = [
        code for code, texte in zip(var_annee["values"], var_annee["valueTexts"])
        if texte.strip() in ANNEES
    ]
    if not codes_annee:
        raise ValueError(f"Aucune année retenue. Libellés de l'API : {var_annee['valueTexts']}")

    selections = {var_annee["code"]: codes_annee}
    expected = expected_rows(meta, selections)

    px_path = RAW_DIR / "elections" / "px-x-1702020000_105.px"
    if force or not px_path.exists():
        px_url = "https://www.pxweb.bfs.admin.ch/DownloadFile.aspx?file=px-x-1702020000_105"
        response = session.get(px_url, timeout=120)
        response.raise_for_status()
        px_path.parent.mkdir(parents=True, exist_ok=True)
        px_path.write_bytes(response.content)
        record_provenance(px_path.stem, px_path, px_url)

    if not force and is_complete(out_path, expected) and any(
        column.startswith("code_") for column in pd.read_csv(out_path, nrows=0).columns
    ):
        print(f"Fichier déjà présent et complet : {out_path} ({expected:,} lignes).")
        return

    print(f"Années {ANNEES}, {expected:,} lignes attendues.")
    frames, failed = [], []
    for code in codes_annee:
        f, fail = fetch_table(
            session, headers_post, URL, meta,
            split_code=var_parti["code"], batch_size=PARTI_BATCH,
            selections={**selections, var_annee["code"]: [code]},
            label=f"année {code}, ",
            include_codes=True,
        )
        frames += f
        failed += fail

    save_if_complete(frames, failed, expected, out_path)
    metadata_path = out_path.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    record_provenance(out_path.stem, out_path, URL, years=ANNEES)
    record_provenance(metadata_path.stem, metadata_path, URL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="retélécharger même si le fichier est complet")
    main(force=parser.parse_args().force)
