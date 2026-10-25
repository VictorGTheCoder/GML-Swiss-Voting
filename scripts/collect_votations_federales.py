"""Collecte du tableau OFS px-x-1703030000_101 :
« Votations populaires (résultats au niveau des communes depuis 1960) ».

Sortie : data/raw/votations_communes_1960_2026_brut.csv (format long, ~8,45 M de lignes).

Usage (depuis n'importe où dans le dépôt) :
    python scripts/collect_votations_federales.py            # télécharge si nécessaire
    python scripts/collect_votations_federales.py --force    # retélécharge dans tous les cas
"""

import argparse

from pxweb_utils import (
    expected_rows,
    fetch_table,
    find_variable,
    is_complete,
    open_session,
    raw_dir,
    save_if_complete,
)

URL = "https://www.pxweb.bfs.admin.ch/api/v1/fr/px-x-1703030000_101/px-x-1703030000_101.px"
PAGE_URL = (
    "https://www.pxweb.bfs.admin.ch/pxweb/fr/px-x-1703030000_101/"
    "px-x-1703030000_101/px-x-1703030000_101.px/"
)
OUT_NAME = "votations_communes_1960_2026_brut.csv"
BATCH_SIZE = 5  # objets de votation par requête (20 est refusé par le serveur : 403)


def main(force: bool = False) -> None:
    out_path = raw_dir() / OUT_NAME
    session, headers_post = open_session(PAGE_URL)
    meta = session.get(URL).json()

    expected = expected_rows(meta)
    if not force and is_complete(out_path, expected):
        print(f"Fichier déjà présent et complet : {out_path} ({expected:,} lignes).")
        return

    var_objet = find_variable(meta, "objet", "vorlage")
    print(f"{len(var_objet['values'])} objets de votation, {expected:,} lignes attendues.")

    frames, failed = fetch_table(
        session, headers_post, URL, meta,
        split_code=var_objet["code"], batch_size=BATCH_SIZE,
    )
    save_if_complete(frames, failed, expected, out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="retélécharger même si le fichier est complet")
    main(force=parser.parse_args().force)