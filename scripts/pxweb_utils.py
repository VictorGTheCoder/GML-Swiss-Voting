"""Utilitaires communs pour interroger l'API PX-Web de l'OFS (STAT-TAB).

Contraintes rencontrées en pratique avec ce serveur :
- il faut d'abord visiter la page HTML du tableau pour obtenir un cookie de session ;
- les requêtes POST doivent porter l'en-tête ``X-Requested-With: XMLHttpRequest`` ;
- les requêtes trop volumineuses sont refusées (403), indépendamment de la limite de
  2 500 000 cellules de l'interface web : on découpe donc en petits lots.
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

import pandas as pd
import requests
from pyjstat import pyjstat

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def find_project_root(marker: str = ".git") -> Path:
    """Remonte depuis le dossier courant jusqu'au dossier contenant ``marker``."""
    start = Path.cwd()
    for path in [start, *start.parents]:
        if (path / marker).exists():
            return path
    raise FileNotFoundError(f"Impossible de trouver '{marker}' en remontant depuis {start}")


def raw_dir() -> Path:
    """Dossier ``data/raw`` du dépôt (créé s'il n'existe pas)."""
    path = find_project_root() / "data" / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def open_session(page_url: str):
    """Ouvre une session avec cookie ; renvoie (session, en-têtes pour les POST)."""
    headers_get = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-CH,fr;q=0.9",
        "Referer": page_url,
    }
    headers_post = {
        **headers_get,
        "Content-Type": "application/json;charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    session = requests.Session()
    session.headers.update(headers_get)
    session.get(page_url)  # nécessaire pour obtenir le cookie de session
    return session, headers_post


def find_variable(meta: dict, *keywords: str) -> dict:
    """Première variable de la métadonnée dont le libellé contient un des mots-clés."""
    for var in meta["variables"]:
        text = var["text"].lower()
        if any(k.lower() in text for k in keywords):
            return var
    libelles = [v["text"] for v in meta["variables"]]
    raise KeyError(f"Aucune variable ne contient {keywords}. Variables disponibles : {libelles}")


def expected_rows(meta: dict, selections: dict | None = None) -> int:
    """Nombre de lignes attendu (produit des tailles des variables, après sélection)."""
    selections = selections or {}
    total = 1
    for var in meta["variables"]:
        total *= len(selections.get(var["code"], var["values"]))
    return total


def count_rows(csv_path: Path) -> int:
    """Nombre de lignes d'un CSV (lit une seule colonne pour rester rapide)."""
    return pd.read_csv(csv_path, usecols=[0]).shape[0]


def is_complete(csv_path: Path, expected: int) -> bool:
    return csv_path.exists() and count_rows(csv_path) == expected


def fetch_table(
    session,
    headers_post: dict,
    url: str,
    meta: dict,
    split_code: str,
    batch_size: int,
    selections: dict | None = None,
    pause: float = 2.0,
    label: str = "",
):
    """Télécharge un tableau en découpant la variable ``split_code`` en lots.

    ``selections`` : {code de variable: liste de valeurs} pour restreindre une variable
    (par défaut, toutes les valeurs sont demandées).
    Renvoie (liste de DataFrames, liste des lots en échec).
    """
    selections = selections or {}
    split_values = selections.get(
        split_code, next(v for v in meta["variables"] if v["code"] == split_code)["values"]
    )
    n_batches = math.ceil(len(split_values) / batch_size)

    frames, failed = [], []
    for b, i in enumerate(range(0, len(split_values), batch_size), start=1):
        chunk = split_values[i : i + batch_size]
        query = {
            "query": [
                {
                    "code": var["code"],
                    "selection": {
                        "filter": "item",
                        "values": chunk
                        if var["code"] == split_code
                        else selections.get(var["code"], var["values"]),
                    },
                }
                for var in meta["variables"]
            ],
            "response": {"format": "json-stat2"},
        }
        print(f"{label}lot {b}/{n_batches}...")
        response = session.post(url, json=query, headers=headers_post)
        if response.status_code != 200:
            print(f"  Erreur {response.status_code} : {response.text[:200]}")
            failed.append((label, b, response.status_code))
            continue
        frames.append(pyjstat.Dataset.read(response.text).write("dataframe"))
        time.sleep(pause)
    return frames, failed


def save_if_complete(frames: list, failed: list, expected: int, out_path: Path) -> pd.DataFrame:
    """Assemble les lots et n'écrit le CSV final que s'il est complet.

    Un fichier partiel n'est jamais enregistré sous le nom définitif : cela évite qu'un
    cache incomplet soit pris pour un téléchargement réussi.
    """
    if not frames:
        raise RuntimeError(f"Aucun lot récupéré. Lots en échec : {failed}")
    df = pd.concat(frames, ignore_index=True)
    if len(df) != expected or failed:
        raise RuntimeError(
            f"Téléchargement incomplet : {len(df):,} lignes sur {expected:,} attendues, "
            f"{len(failed)} lot(s) en échec {failed}. Relancez le script (essayez un lot plus petit)."
        )
    tmp_path = out_path.with_suffix(".csv.tmp")
    df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    os.replace(tmp_path, out_path)
    print(f"Sauvegardé : {out_path} ({len(df):,} lignes)")
    return df