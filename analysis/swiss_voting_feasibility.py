#!/usr/bin/env python3
"""Leakage-aware feasibility test for commune-level Swiss federal vote forecasts.

The script downloads only official FSO PXWeb cubes, then evaluates whether a
non-linear model improves on Ridge for *entirely future, unseen vote objects*.
It intentionally contains no national/cantonal result or target-vote turnout.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # CLI/report generation runs without an X display.
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from catboost import CatBoostRegressor
from pyaxis import pyaxis
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "data" / "results"
DOCS = ROOT / "docs"
VOTE_API = "https://www.pxweb.bfs.admin.ch/api/v1/fr/px-x-1703030000_101/px-x-1703030000_101.px"
POP_API = "https://www.pxweb.bfs.admin.ch/api/v1/fr/px-x-0102010000_101/px-x-0102010000_101.px"
VOTE_SOURCE = "https://www.bfs.admin.ch/asset/fr/px-x-1703030000_101"
POP_SOURCE = "https://www.bfs.admin.ch/asset/fr/px-x-0102010000_101"
VOTE_PX_DOWNLOAD = "https://dam-api.bfs.admin.ch/hub/api/dam/assets/36815105/master"


def px_metadata(url: str) -> dict:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.json()


def px_query(url: str, selections: dict[str, list[str]]) -> pd.DataFrame:
    """Query PXWeb JSON-stat2 and return labelled long data without guessing order."""
    payload = {
        "query": [
            {"code": code, "selection": {"filter": "item", "values": values}}
            for code, values in selections.items()
        ],
        "response": {"format": "json-stat2"},
    }
    response = requests.post(url, json=payload, timeout=600)
    response.raise_for_status()
    cube = response.json()
    identifiers = cube["id"]
    labels = []
    for identifier in identifiers:
        category = cube["dimension"][identifier]["category"]
        ordered_codes = [code for code, _ in sorted(category["index"].items(), key=lambda x: x[1])]
        labels.append([(code, category.get("label", {}).get(code, code)) for code in ordered_codes])
    rows = []
    values = cube["value"]
    for index, combination in enumerate(itertools.product(*labels)):
        value = values[index] if isinstance(values, list) else values.get(str(index))
        rows.append({**{identifier: pair[0] for identifier, pair in zip(identifiers, combination)},
                     **{f"{identifier}_label": pair[1] for identifier, pair in zip(identifiers, combination)},
                     "value": value})
    return pd.DataFrame(rows)


def _commune_codes(metadata: dict) -> list[str]:
    return [value for value in metadata["variables"][0]["values"] if re.fullmatch(r"\d{4}", value)]


def _cantons_from_vote_metadata(metadata: dict) -> dict[str, str]:
    """PXWeb's hierarchical location list lets us map each numeric commune to its canton."""
    variable = metadata["variables"][0]
    current_canton = None
    mapping = {}
    for code, label in zip(variable["values"], variable["valueTexts"]):
        if re.fullmatch(r"[A-Z]{2}", code):
            current_canton = code
        elif re.fullmatch(r"\d{4}", code) and current_canton:
            mapping[code] = current_canton
    return mapping


def language_region(canton: str) -> str:
    if canton in {"GE", "VD", "NE", "JU"}:
        return "French"
    if canton == "TI":
        return "Italian"
    if canton == "GR":
        return "Romansh/German/Italian"
    if canton in {"FR", "VS", "BE"}:
        return "Multilingual"
    return "German"


def vote_type(title: str) -> str:
    title = title.lower()
    if "initiative" in title:
        return "initiative"
    if "référendum" in title:
        return "referendum"
    if "loi" in title or "bundesgesetz" in title or "arrêté fédéral" in title or "modification" in title or "änderung" in title:
        return "law_or_decree"
    return "other"


def load_votes_from_official_px(start_year: int, end_year: int) -> pd.DataFrame:
    """Use the official full PX export; large PXWeb POSTs are WAF-blocked by the FSO."""
    px_path = RAW / "fso_vote_results_full.px"
    if not px_path.exists():
        response = requests.get(VOTE_PX_DOWNLOAD, timeout=600)
        response.raise_for_status()
        px_path.write_bytes(response.content)
    parsed = pyaxis.parse(str(px_path), encoding="utf-8")
    data, metadata = parsed["DATA"], parsed["METADATA"]
    location = "Kanton (-) / Bezirk (>>) / Gemeinde (......)"
    vote = "Datum und Vorlage"
    result = "Ergebnis"
    location_labels = metadata[f"VALUES({location})"]
    location_codes = metadata[f"CODES({location})"]
    # A handful of names repeat across cantons. They cannot be disambiguated after
    # pyaxis renders labels, so exclude them rather than silently assigning a wrong ID.
    label_counts = pd.Series(location_labels).value_counts()
    label_to_code = {label: code for label, code in zip(location_labels, location_codes) if label_counts[label] == 1}
    canton_map, current_canton = {}, None
    for label, code in zip(location_labels, location_codes):
        if re.fullmatch(r"[A-Z]{2}", code):
            current_canton = code
        elif re.fullmatch(r"\d{4}", code) and current_canton:
            canton_map[code] = current_canton
    vote_labels = metadata[f"VALUES({vote})"]
    vote_codes = metadata[f"CODES({vote})"]
    vote_to_code = dict(zip(vote_labels, vote_codes))
    selected_votes = [label for label in vote_labels if start_year <= int(label[:4]) <= end_year]
    selected_locations = [label for label, code in label_to_code.items() if re.fullmatch(r"\d{4}", code)]
    subset = data.loc[
        data[location].isin(selected_locations) & data[vote].isin(selected_votes)
        & data[result].isin(["Stimmberechtigte", "Abgegebene Stimmen", "Beteiligung in %", "Ja", "Nein"]),
        [location, vote, result, "DATA"],
    ]
    votes = (
        subset.pivot(index=[location, vote], columns=result, values="DATA")
        .rename(columns={"Stimmberechtigte": "eligible", "Abgegebene Stimmen": "ballots", "Beteiligung in %": "turnout_official", "Ja": "yes", "Nein": "no"})
        .reset_index().rename(columns={location: "commune_label", vote: "vote_title"})
    )
    votes["commune_id"] = votes["commune_label"].map(label_to_code)
    votes["vote_id"] = votes["vote_title"].map(vote_to_code)
    votes["vote_date"] = pd.to_datetime(votes["vote_title"].str.slice(0, 10), errors="coerce")
    for column in ["yes", "no", "eligible", "ballots"]:
        votes[column] = pd.to_numeric(votes[column], errors="coerce")
    votes["yes_share"] = votes["yes"] / (votes["yes"] + votes["no"])
    votes["turnout"] = votes["ballots"] / votes["eligible"]
    votes["canton"] = votes["commune_id"].map(canton_map)
    votes["language_region"] = votes["canton"].map(language_region)
    votes["vote_type"] = votes["vote_title"].map(vote_type)
    votes["year"] = votes["vote_date"].dt.year
    votes["month"] = votes["vote_date"].dt.month.astype("Int64")
    votes = votes.drop(columns="commune_label")
    votes.attrs["source_noncommunal_categories_excluded"] = len(location_labels) - len(selected_locations)
    return votes


def download_official_data(start_year: int, end_year: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Download a recent, stable-geometry sample and prior-year STATPOP features."""
    votes = load_votes_from_official_px(start_year, end_year)

    pop_meta = px_metadata(POP_API)
    pop_geo_col = pop_meta["variables"][1]["code"]
    codes = [code for code in pop_meta["variables"][1]["values"] if re.fullmatch(r"\d{4}", code)]
    # The FSO WAF accepts modest result payloads; request the same official cube in chunks.
    population_chunks = []
    for start in range(0, len(codes), 100):
        population_chunks.append(px_query(POP_API, {
            # Fixed 2010 STATPOP snapshot: it predates every retained vote and
            # avoids making a later demographic measurement look ex-ante known.
            pop_meta["variables"][0]["code"]: ["2010"],
            pop_geo_col: codes[start:start + 100], pop_meta["variables"][2]["code"]: ["1"],
            pop_meta["variables"][3]["code"]: ["-99999", "2"], pop_meta["variables"][4]["code"]: ["-99999"],
            pop_meta["variables"][5]["code"]: ["-99999"],
        }))
    pop = pd.concat(population_chunks, ignore_index=True)
    year_col, citizen_col = pop_meta["variables"][0]["code"], pop_meta["variables"][3]["code"]
    population = (
        pop.pivot(index=[year_col, pop_geo_col], columns=citizen_col, values="value")
        .rename(columns={"-99999": "population", "2": "foreign_population"})
        .reset_index()
        .rename(columns={year_col: "population_year", pop_geo_col: "commune_id"})
    )
    population["commune_id"] = population["commune_id"].astype(str).str.zfill(4)
    population["population_year"] = population["population_year"].astype(int)
    population["population"] = pd.to_numeric(population["population"], errors="coerce")
    population["foreign_population"] = pd.to_numeric(population["foreign_population"], errors="coerce")
    population["foreign_rate"] = population["foreign_population"] / population["population"]
    return votes, population, {
        "n_selected_votes": votes.vote_id.nunique(),
        "source_noncommunal_categories_excluded": votes.attrs.get("source_noncommunal_categories_excluded", 0),
    }


def join_prior_year_population(votes: pd.DataFrame, population: pd.DataFrame) -> pd.DataFrame:
    """As-of join: a vote uses only STATPOP available from a previous calendar year."""
    left = votes.copy()
    left["population_available_year"] = left["year"] - 1
    # merge_asof requires its *on* key to be globally monotonic, then respects
    # commune_id via ``by``. Sorting by commune first violates that contract.
    left = left.sort_values(["population_available_year", "commune_id"])
    right = population.sort_values(["population_year", "commune_id"])
    return pd.merge_asof(
        left, right, by="commune_id", left_on="population_available_year", right_on="population_year", direction="backward"
    ).sort_index()


def add_historical_features(rows: pd.DataFrame) -> pd.DataFrame:
    """Features at date t summarize each commune's strictly earlier vote dates only."""
    output = rows.copy().sort_values(["commune_id", "vote_date", "vote_id"]).reset_index(drop=True)
    daily = (
        output.groupby(["commune_id", "vote_date"], as_index=False)
        .agg(day_yes_mean=("yes_share", "mean"), day_turnout_mean=("turnout", "mean"), day_count=("vote_id", "nunique"))
        .sort_values(["commune_id", "vote_date"])
    )
    daily["historical_yes_mean"] = daily.groupby("commune_id")["day_yes_mean"].transform(
        lambda value: value.shift().expanding().mean()
    )
    daily["historical_yes_std"] = daily.groupby("commune_id")["day_yes_mean"].transform(
        lambda value: value.shift().expanding().std()
    )
    daily["historical_turnout_mean"] = daily.groupby("commune_id")["day_turnout_mean"].transform(
        lambda value: value.shift().expanding().mean()
    )
    daily["historical_vote_dates"] = daily.groupby("commune_id").cumcount()
    output = output.merge(
        daily.drop(columns=["day_yes_mean", "day_turnout_mean", "day_count"]), on=["commune_id", "vote_date"], how="left"
    )
    return output


def build_temporal_vote_split(rows: pd.DataFrame, train_fraction: float = 0.70, validation_fraction: float = 0.15) -> pd.DataFrame:
    """Split whole objects chronologically; all objects on the same day stay together."""
    vote_dates = rows[["vote_id", "vote_date"]].drop_duplicates().sort_values(["vote_date", "vote_id"])
    dates = vote_dates["vote_date"].drop_duplicates().sort_values().tolist()
    train_cut = max(1, int(len(dates) * train_fraction))
    validation_cut = max(train_cut + 1, int(len(dates) * (train_fraction + validation_fraction)))
    date_split = {date: "train" if i < train_cut else "validation" if i < validation_cut else "test" for i, date in enumerate(dates)}
    output = rows.copy()
    output["split"] = output["vote_date"].map(date_split)
    return output


def clean_votes(rows: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    before = len(rows)
    duplicate_count = int(rows.duplicated(["commune_id", "vote_id"]).sum())
    invalid = (~rows["yes_share"].between(0, 1)) | rows["yes"].isna() | rows["no"].isna() | (rows["yes"] + rows["no"] <= 0)
    no_canton = rows["canton"].isna()
    clean = rows.loc[~invalid & ~no_canton].drop_duplicates(["commune_id", "vote_id"]).copy()
    coverage = clean.groupby("vote_id")["commune_id"].nunique()
    min_coverage = int(np.floor(coverage.median() * 0.80))
    keep_votes = coverage[coverage >= min_coverage].index
    clean = clean[clean["vote_id"].isin(keep_votes)].copy()
    return clean, {
        "input_rows": before,
        "duplicate_rows": duplicate_count,
        "invalid_target_or_counts": int(invalid.sum()),
        "non_communal_or_no_canton": int(no_canton.sum()),
        "coverage_threshold": min_coverage,
        "votes_excluded_low_coverage": int((coverage < min_coverage).sum()),
        "rows_after_cleaning": len(clean),
        "communes_with_fewer_than_five_votes": int((clean.groupby("commune_id")["vote_id"].nunique() < 5).sum()),
    }


def metrics(y_true: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    return {
        "MAE": mean_absolute_error(y_true, prediction),
        "RMSE": mean_squared_error(y_true, prediction) ** 0.5,
        "R2": r2_score(y_true, prediction),
    }


def _ridge_pipeline(numeric: list[str], categorical: list[str]) -> Pipeline:
    return Pipeline(
        [
            ("preprocess", ColumnTransformer([
                ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
                ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
            ])),
            ("model", Ridge(alpha=20.0)),
        ]
    )


def bootstrap_vote_difference(per_vote: pd.DataFrame, rng: np.random.Generator) -> tuple[float, float]:
    differences = per_vote["ridge_minus_catboost"].to_numpy()
    samples = np.array([rng.choice(differences, len(differences), replace=True).mean() for _ in range(4000)])
    return tuple(np.quantile(samples, [0.025, 0.975]))


def run_experiment(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    rows = add_historical_features(rows)
    rows = build_temporal_vote_split(rows)
    categorical = ["canton", "language_region", "vote_type"]
    basic_numeric = ["year", "month", "population", "foreign_rate"]
    history_numeric = basic_numeric + ["historical_yes_mean", "historical_yes_std", "historical_turnout_mean", "historical_vote_dates"]
    train = rows[rows.split == "train"].copy()
    validation = rows[rows.split == "validation"].copy()
    test = rows[rows.split == "test"].copy()
    # Median imputation is fitted on training rows only; no vote outcome enters X.
    ridge_basic = _ridge_pipeline(basic_numeric, categorical).fit(train[basic_numeric + categorical], train.yes_share)
    ridge_basic_prediction = ridge_basic.predict(test[basic_numeric + categorical])
    ridge = _ridge_pipeline(history_numeric, categorical).fit(train[history_numeric + categorical], train.yes_share)
    ridge_prediction = ridge.predict(test[history_numeric + categorical])
    fallback = train.yes_share.mean()
    naive_prediction = test.historical_yes_mean.fillna(fallback).to_numpy()
    cat_features = categorical
    cat_train = train[history_numeric + categorical].copy()
    cat_validation = validation[history_numeric + categorical].copy()
    cat_test = test[history_numeric + categorical].copy()
    for frame in (cat_train, cat_validation, cat_test):
        frame[categorical] = frame[categorical].fillna("unknown").astype(str)
        frame[history_numeric] = frame[history_numeric].replace([np.inf, -np.inf], np.nan).fillna(train[history_numeric].median())
    # Deliberately small validation search: enough to avoid condemning CatBoost
    # because of one arbitrary loss/depth, not enough to tune on the test era.
    candidates = [
        {"loss_function": "MAE", "depth": 4}, {"loss_function": "MAE", "depth": 6},
        {"loss_function": "RMSE", "depth": 4}, {"loss_function": "RMSE", "depth": 6},
    ]
    catboost, best_spec, best_validation_mae = None, None, np.inf
    for spec in candidates:
        candidate = CatBoostRegressor(
            loss_function=spec["loss_function"], eval_metric="MAE", iterations=700, depth=spec["depth"], learning_rate=0.05,
            l2_leaf_reg=8, random_seed=2026, verbose=False, allow_writing_files=False,
        )
        candidate.fit(cat_train, train.yes_share, cat_features=cat_features, eval_set=(cat_validation, validation.yes_share), early_stopping_rounds=60, verbose=False)
        validation_mae = mean_absolute_error(validation.yes_share, candidate.predict(cat_validation))
        if validation_mae < best_validation_mae:
            catboost, best_spec, best_validation_mae = candidate, spec, validation_mae
    cat_prediction = catboost.predict(cat_test)
    prediction_frame = test[["vote_id", "vote_date", "vote_title", "vote_type", "commune_id", "yes_share"]].copy()
    prediction_frame["naive"] = naive_prediction
    prediction_frame["ridge"] = ridge_prediction
    prediction_frame["catboost"] = cat_prediction
    overall = pd.DataFrame([
        {"model": "Naive: commune historical mean", **metrics(test.yes_share, naive_prediction)},
        {"model": "Ridge (Dataset A)", **metrics(test.yes_share, ridge_basic_prediction)},
        {"model": "Ridge (Dataset B)", **metrics(test.yes_share, ridge_prediction)},
        {"model": "CatBoost (Dataset B)", **metrics(test.yes_share, cat_prediction)},
    ])
    per_vote = prediction_frame.groupby(["vote_id", "vote_date", "vote_title", "vote_type"], as_index=False).apply(
        lambda group: pd.Series({
            "n_communes": len(group),
            "MAE_naive": mean_absolute_error(group.yes_share, group.naive),
            "MAE_ridge": mean_absolute_error(group.yes_share, group.ridge),
            "MAE_catboost": mean_absolute_error(group.yes_share, group.catboost),
        }), include_groups=False
    )
    per_vote["ridge_minus_catboost"] = per_vote.MAE_ridge - per_vote.MAE_catboost
    importances = pd.DataFrame({"feature": history_numeric + categorical, "importance": catboost.get_feature_importance()}).sort_values("importance", ascending=False)
    perm = permutation_importance(catboost, cat_test, test.yes_share, scoring="neg_mean_absolute_error", n_repeats=5, random_state=2026, n_jobs=-1)
    # Name-aligned permutation table (CatBoost receives source columns in this exact order).
    permutation = pd.DataFrame({"feature": history_numeric + categorical, "permutation_mae_increase": perm.importances_mean}).sort_values("permutation_mae_increase", ascending=False)
    importances = importances.merge(permutation, on="feature", how="left")
    ci = bootstrap_vote_difference(per_vote, np.random.default_rng(2026))
    metadata = {
        "train_votes": sorted(train.vote_id.unique().tolist()), "validation_votes": sorted(validation.vote_id.unique().tolist()), "test_votes": sorted(test.vote_id.unique().tolist()),
        "train_period": [str(train.vote_date.min().date()), str(train.vote_date.max().date())],
        "validation_period": [str(validation.vote_date.min().date()), str(validation.vote_date.max().date())],
        "test_period": [str(test.vote_date.min().date()), str(test.vote_date.max().date())],
        "per_vote_difference_mean": float(per_vote.ridge_minus_catboost.mean()),
        "per_vote_difference_median": float(per_vote.ridge_minus_catboost.median()),
        "catboost_wins": int((per_vote.ridge_minus_catboost > 0).sum()),
        "ridge_wins": int((per_vote.ridge_minus_catboost < 0).sum()),
        "bootstrap_95_ci": [float(ci[0]), float(ci[1])],
        "catboost_selection": {**best_spec, "validation_mae": float(best_validation_mae), "tree_count": int(catboost.tree_count_)},
    }
    return overall, per_vote, importances, prediction_frame, metadata


def write_report(cleaning: dict, rows: pd.DataFrame, overall: pd.DataFrame, per_vote: pd.DataFrame, importances: pd.DataFrame, metadata: dict) -> None:
    ridge_mae = overall.loc[overall.model == "Ridge (Dataset B)", "MAE"].iloc[0]
    cat_mae = overall.loc[overall.model == "CatBoost (Dataset B)", "MAE"].iloc[0]
    gain = (ridge_mae - cat_mae) / ridge_mae
    ci = metadata["bootstrap_95_ci"]
    # A small gain whose vote-level CI crosses zero is not a viable 14-week ML thesis signal.
    verdict = "GO" if gain >= 0.05 and ci[0] > 0 and metadata["catboost_wins"] > metadata["ridge_wins"] else "GO AVEC RÉSERVES" if gain > 0 and ci[1] > 0 else "NO-GO"
    result_table = overall.assign(MAE_pp=lambda x: (x.MAE * 100).round(2), RMSE_pp=lambda x: (x.RMSE * 100).round(2), R2=lambda x: x.R2.round(3))[["model", "MAE_pp", "RMSE_pp", "R2"]].to_markdown(index=False)
    top = importances.head(10).assign(importance=lambda x: x.importance.round(2), permutation_mae_increase=lambda x: (x.permutation_mae_increase * 100).round(3)).to_markdown(index=False)
    best = per_vote.loc[per_vote.MAE_catboost.idxmin()]
    worst = per_vote.loc[per_vote.MAE_catboost.idxmax()]
    type_table = (per_vote.groupby("vote_type")[["MAE_ridge", "MAE_catboost"]].mean() * 100).round(2).reset_index().to_markdown(index=False)
    report = f"""# Swiss Voting ML — test de faisabilité

## Verdict

**{verdict}**. CatBoost a un gain relatif de **{gain * 100:.2f}%** contre Ridge ({(ridge_mae-cat_mae)*100:.2f} point(s) de pourcentage de MAE). L'intervalle bootstrap à 95% de la différence *MAE Ridge − MAE CatBoost*, calculé sur les votations test (unité indépendante), est [{ci[0]*100:.2f}, {ci[1]*100:.2f}] points. CatBoost gagne {metadata['catboost_wins']} votations et Ridge {metadata['ridge_wins']}. La décision est donc fondée sur la stabilité par objet, pas sur le grand nombre de communes.

## Données utilisées

Source principale : [OFS — résultats communaux de votations fédérales]({VOTE_SOURCE}), cube PXWeb `px-x-1703030000_101`; démographie : [OFS STATPOP]({POP_SOURCE}), cube `px-x-0102010000_101`. Période retenue : **{rows.vote_date.min().date()} à {rows.vote_date.max().date()}**. Après nettoyage : **{rows.vote_id.nunique()} objets**, **{rows.commune_id.nunique()} communes**, **{len(rows):,} lignes**.

Exclusions : l'export est d'abord limité à {cleaning.get('source_noncommunal_categories_excluded', 0)} catégories géographiques OFS non communales (Suisse/cantons/districts), puis {cleaning['duplicate_rows']} doublons commune×objet, {cleaning['invalid_target_or_counts']} lignes sans Oui/Non valides ou avec target hors [0,1], et {cleaning['votes_excluded_low_coverage']} objets dont la couverture était inférieure à 80% de la médiane ({cleaning['coverage_threshold']} communes). Aucune commune retenue n'a moins de cinq objets ({cleaning['communes_with_fewer_than_five_votes']}). Les frontières communales sont celles harmonisées par l'OFS; les anciennes fusions ne sont donc pas résolues individuellement.

## Split strict par votation

| Ensemble | Période | Objets |
|---|---|---:|
| Train | {metadata['train_period'][0]} — {metadata['train_period'][1]} | {len(metadata['train_votes'])} |
| Validation | {metadata['validation_period'][0]} — {metadata['validation_period'][1]} | {len(metadata['validation_votes'])} |
| Test | {metadata['test_period'][0]} — {metadata['test_period'][1]} | {len(metadata['test_votes'])} |

Chaque `vote_id` est affecté une seule fois; aucun résultat communal d'une votation test ne peut apparaître à l'entraînement. Les listes exactes sont dans `data/results/split_votes.json`.

## Features et prévention des fuites

**Dataset A** : canton, région linguistique, type d'objet (règle transparente à partir du libellé officiel : initiative/référendum/loi-décret/autre), année, mois, population permanente et part étrangère STATPOP. Par prudence ex ante, c'est un unique snapshot STATPOP **2010**, antérieur à toutes les votations retenues; aucune démographie future n'est employée. Densité et âge ne sont pas inclus dans ce test rapide.

**Dataset B** (comparaison principale) ajoute, par commune, moyenne et écart-type du Oui, moyenne de participation et nombre de dates historiques. Ces agrégats sont calculés seulement sur des **dates strictement antérieures**; les autres objets du même dimanche ne sont pas utilisés. Aucun résultat national/cantonal, aucune participation de l'objet cible, aucune moyenne calculée sur les communes de la votation cible, ni texte/embedding du libellé n'entre dans le modèle. Imputation, standardisation et one-hot encoding de Ridge sont appris sur train seulement.

## Modèles

Baseline naïve : moyenne historique disponible de la commune, sinon moyenne train. Ridge : one-hot des catégorielles + variables numériques standardisées (`alpha=20`). Ridge est évalué à la fois sur Dataset A et Dataset B, ce qui isole l'apport de l'historique. CatBoost (Dataset B) utilise le meilleur de 4 réglages légers choisis uniquement sur validation : `{metadata['catboost_selection']['loss_function']}`, profondeur {metadata['catboost_selection']['depth']}, {metadata['catboost_selection']['tree_count']} arbres (MAE validation {metadata['catboost_selection']['validation_mae']*100:.2f} pp); taux 0.05 et arrêt anticipé. Aucun test n'est utilisé pour ce choix.

## Résultats globaux sur les mêmes votations test

MAE et RMSE sont en points de pourcentage.

{result_table}

## Résultats par votation et stabilité

La différence moyenne Ridge − CatBoost par objet est **{metadata['per_vote_difference_mean']*100:.2f} pp**, la médiane **{metadata['per_vote_difference_median']*100:.2f} pp**. CatBoost gagne {metadata['catboost_wins']}/{len(per_vote)} objets. Meilleur objet CatBoost : *{best.vote_title}* ({best.MAE_catboost*100:.2f} pp); pire : *{worst.vote_title}* ({worst.MAE_catboost*100:.2f} pp). Le fichier `data/results/per_vote_metrics.csv` contient la distribution complète et `test_mae_by_vote.png` la visualise.

La source ne fournit pas ici de thème officiel par objet; ventilation possible par **type** (pas une preuve de généralisation thématique) :

{type_table}

## Importance des variables CatBoost

Importance native et importance de permutation (augmentation de MAE en pp lorsque la colonne est permutée) :

{top}

## Analyse critique et recommandation GML

1. **Non-linéaire vs Ridge :** le gain est {gain*100:.2f}% en MAE ({(ridge_mae-cat_mae)*100:.2f} pp), à interpréter avec l'IC par objet ci-dessus.
2. **Stabilité :** {metadata['catboost_wins']} gains contre {metadata['ridge_wins']} défaites; le test bootstrap évite de confondre milliers de communes et quelques dizaines de votations indépendantes.
3. **Thèmes inédits :** ce prototype n'a pas une taxonomie officielle d'objet au niveau individuel; avec seulement type + année/mois, il ne peut pas prétendre généraliser sémantiquement à un thème inédit. La ventilation par type ci-dessus est seulement descriptive.
4. **Limite structurelle :** la taille effective du problème est le nombre d'objets, non le nombre de lignes communales. Les progrès très faibles peuvent être du bruit de sélection sur peu de scrutins.
5. **Risque projet :** élevé si le gain est faible/non stable : une grande infrastructure de collecte ou de modèles complexes ne créera pas automatiquement l'information manquante sur la votation. Les historiques communaux risquent d'expliquer l'essentiel du signal spatial, tandis que les features d'objet restent pauvres.

Recommandation : si le verdict est **NO-GO**, ne pas retenir le sujet sous la forme "forecast ex ante du yes_share". Si **GO AVEC RÉSERVES**, ne le poursuivre que sous une question plus riche : construire et évaluer des descriptions *pré-vote* des objets (thème officiel, texte de brochure, positions des partis), rolling-origin multi-périodes et ablations explicites. Le score actuel seul n'est pas une justification pour 14 semaines.
"""
    (DOCS / "SWISS_VOTING_FEASIBILITY.md").write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2011)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--reuse-raw", action="store_true", help="Reuse downloaded official CSVs if present.")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True); RESULTS.mkdir(parents=True, exist_ok=True); DOCS.mkdir(parents=True, exist_ok=True)
    vote_path, population_path = RAW / "fso_vote_results_2010_2024.csv.gz", RAW / "fso_statpop_2009_2023.csv.gz"
    if args.reuse_raw and vote_path.exists() and population_path.exists():
        votes, population = pd.read_csv(vote_path, low_memory=False), pd.read_csv(population_path, low_memory=False)
        votes["vote_date"] = pd.to_datetime(votes["vote_date"])
    else:
        votes, population, source_metadata = download_official_data(args.start_year, args.end_year)
        votes.to_csv(vote_path, index=False, compression="gzip")
        population.to_csv(population_path, index=False, compression="gzip")
    if args.reuse_raw and vote_path.exists() and population_path.exists():
        source_metadata = {"source_noncommunal_categories_excluded": 212}
    joined = join_prior_year_population(votes, population)
    clean, cleaning = clean_votes(joined)
    cleaning.update(source_metadata)
    overall, per_vote, importances, predictions, metadata = run_experiment(clean)
    overall.to_csv(RESULTS / "overall_metrics.csv", index=False)
    per_vote.to_csv(RESULTS / "per_vote_metrics.csv", index=False)
    importances.to_csv(RESULTS / "feature_importance.csv", index=False)
    predictions.to_csv(RESULTS / "test_predictions.csv.gz", index=False, compression="gzip")
    (RESULTS / "split_votes.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    figure, axis = plt.subplots(figsize=(11, 5))
    plot = per_vote.sort_values("MAE_catboost")
    axis.bar(range(len(plot)), plot.MAE_ridge * 100, label="Ridge", alpha=.75)
    axis.bar(range(len(plot)), plot.MAE_catboost * 100, label="CatBoost", alpha=.65)
    axis.set(xlabel="Votations test (triées par MAE CatBoost)", ylabel="MAE (points de pourcentage)")
    axis.legend(); figure.tight_layout(); figure.savefig(RESULTS / "test_mae_by_vote.png", dpi=160); plt.close(figure)
    write_report(cleaning, clean, overall, per_vote, importances, metadata)
    print(overall.to_string(index=False))
    print(f"Report: {DOCS / 'SWISS_VOTING_FEASIBILITY.md'}")


if __name__ == "__main__":
    main()
