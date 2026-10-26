"""Build the explicitly retrospective, structured municipality x object table.

This exploratory table is NOT an input to the strict forecast evaluator: release
evidence and a historical forecast instant are still missing. No model is fitted.
Run: python -m scripts.integration.build_modeling_dataset
"""

from __future__ import annotations

import argparse
import hashlib
import json

import pandas as pd

from scripts.common.config import PROCESSED_DIR, REPORTS_DIR, ROOT
from scripts.integration.prepare_join import prepare_join

SOURCES = {
    "ofs": "ofs-votes/votes_communes.parquet",
    "swissvotes": "swissvotes/swissvotes_clean.parquet",
    "statpop": "statpop/statpop_features.parquet",
    "elections": "elections/elections_communes.parquet",
    "typologies": "typologies/commune_typologies.parquet",
}
DEMOGRAPHICS = ["pop_total", "share_foreign", "share_0_19", "share_20_39",
                "share_40_64", "share_65_plus", "share_80_plus", "mean_age"]
PARTIES = {"1": "plr", "2": "pdc", "3": "ps", "4": "udc", "7": "pev",
           "13": "verts", "31": "pvl", "32": "pbd", "34": "centre"}
TYPOLOGIES = ["urban_rural", "language_region"]
OBJECT_FIELDS = {"rechtsform": "object_legal_form", "d1e1": "object_domain_1",
                 "d2e1": "object_domain_2", "d3e1": "object_domain_3"}
KEYS = ["municipality_id", "vote_id"]
FLAGS = ["is_special_unit", "is_tiebreak_question", "is_provisional",
         "flag_valid_gt_ballots", "flag_yes_no_gt_valid"]


def unique_keys(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f"{label}: null or duplicate keys {keys}")


def clean_outcomes(ofs: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    unique_keys(ofs, KEYS, "OFS")
    frame = ofs.copy()
    exclusions = []
    for flag in FLAGS:
        rejected = ~frame[flag].eq(False).fillna(False)
        exclusions.append({"reason": flag, "rows": int(rejected.sum())})
        frame = frame.loc[~rejected].copy()
    total = frame.votes_yes + frame.votes_no
    invalid = total.isna() | total.le(0) | frame.votes_yes.lt(0) | frame.votes_no.lt(0)
    exclusions.append({"reason": "undefined_target", "rows": int(invalid.sum())})
    frame = frame.loc[~invalid].copy()
    frame["yes_share"] = frame.votes_yes / (frame.votes_yes + frame.votes_no)
    return frame, exclusions


def prior_history(clean: pd.DataFrame) -> pd.DataFrame:
    """Equal-object municipal mean; exclude every object on the target date."""
    daily = clean.groupby(["municipality_id", "vote_date"], as_index=False).yes_share.agg(["sum", "count"])
    daily = daily.sort_values(["municipality_id", "vote_date"])
    groups = daily.groupby("municipality_id", sort=False)
    count = groups["count"].cumsum() - daily["count"]
    total = groups["sum"].cumsum() - daily["sum"]
    daily["history_n_objects"] = count
    daily["history_mean_yes"] = total / count.where(count.gt(0))
    daily["history_last_vote_date"] = groups["vote_date"].shift(1)
    return daily[["municipality_id", "vote_date", "history_n_objects", "history_mean_yes", "history_last_vote_date"]]


def asof_join(left: pd.DataFrame, right: pd.DataFrame, time_column: str) -> pd.DataFrame:
    """Preserve row count and order; select the latest source at the declared cutoff."""
    left, right = left.copy(), right.copy()
    for frame in (left, right):
        frame["municipality_id"] = frame.municipality_id.astype("string")
    left["feature_cutoff"] = pd.to_datetime(left.feature_cutoff).astype("datetime64[ns]")
    right[time_column] = pd.to_datetime(right[time_column]).astype("datetime64[ns]")
    unique_keys(right, ["municipality_id", time_column], time_column)
    if right[time_column].isna().any():
        raise ValueError(f"Missing source time: {time_column}")
    indexed = left.assign(_row_order=range(len(left)))
    result = pd.merge_asof(
        indexed.sort_values("feature_cutoff"), right.sort_values(time_column),
        left_on="feature_cutoff", right_on=time_column, by="municipality_id", direction="backward",
    ).sort_values("_row_order").drop(columns="_row_order").reset_index(drop=True)
    if len(result) != len(left):
        raise ValueError("As-of join multiplied observations")
    if (result[time_column].notna() & result[time_column].gt(result.feature_cutoff)).any():
        raise ValueError("Future source entered the table")
    return result


def election_wide(elections: pd.DataFrame) -> pd.DataFrame:
    source = elections.loc[~elections.is_special_unit].copy()
    unique_keys(source, ["municipality_id", "election_year", "party_code"], "elections")
    wide = source.pivot(index=["municipality_id", "election_year"], columns="party_code", values="party_share")
    # Absence d'un parti ou d'un résultat : ne jamais remplacer par zéro.
    wide = wide.reindex(columns=list(PARTIES)).rename(columns={code: f"party_share_{name}" for code, name in PARTIES.items()})
    wide = wide.reset_index()
    wide.columns.name = None
    # Hypothèse exploratoire, PAS une date de publication attestée.
    wide["election_selection_from"] = pd.to_datetime((wide.election_year + 1).astype(str) + "-01-01")
    return wide


def build(sources: dict[str, pd.DataFrame], start: str = "2012-01-01") -> tuple[pd.DataFrame, dict]:
    ofs, swiss = sources["ofs"], sources["swissvotes"]
    prepare_join(ofs, swiss)  # exact identifiers, dates and subsidiary-question consistency
    clean, exclusions = clean_outcomes(ofs)
    history = prior_history(clean)
    base = clean.loc[clean.vote_date.ge(pd.Timestamp(start)), KEYS + ["vote_key", "vote_date", "canton", "yes_share"]].copy()
    if base.empty:
        raise ValueError("No eligible outcomes in requested period")
    base["feature_cutoff"] = base.vote_date - pd.Timedelta(days=1)
    table = base.merge(history, on=["municipality_id", "vote_date"], how="left", validate="many_to_one")
    stats = sources["statpop"][["municipality_id", "year", "available_from"] + DEMOGRAPHICS].rename(
        columns={"year": "statpop_year", "available_from": "statpop_selection_from", **{c: f"statpop_{c}" for c in DEMOGRAPHICS}})
    table = asof_join(table, stats, "statpop_selection_from")
    table = asof_join(table, election_wide(sources["elections"]), "election_selection_from")
    typologies = sources["typologies"][["municipality_id"] + TYPOLOGIES]
    unique_keys(typologies, ["municipality_id"], "typologies")
    table = table.merge(typologies, on="municipality_id", how="left", validate="many_to_one")
    metadata = swiss[["vote_key"] + list(OBJECT_FIELDS)].rename(columns=OBJECT_FIELDS)
    for column in OBJECT_FIELDS.values():
        metadata[column] = metadata[column].astype("string")
    table = table.merge(metadata, on="vote_key", how="left", validate="many_to_one")
    table["history_missing"] = table.history_mean_yes.isna()
    table["statpop_missing"] = table.statpop_year.isna()
    table["elections_missing"] = table[[f"party_share_{name}" for name in PARTIES.values()]].isna().all(axis=1)
    table["geography_id"] = "retrospective_fixed_2026-01-01"
    table["strict_forecast_ready"] = False
    table = table.sort_values(["vote_date", "vote_id", "municipality_id"]).reset_index(drop=True)
    unique_keys(table, KEYS, "modeling table")
    if len(table) != len(base):
        raise ValueError("A source join changed row count")
    if (table.history_last_vote_date.notna() & table.history_last_vote_date.ge(table.vote_date)).any():
        raise ValueError("Same-date or future voting history")
    numeric = ["history_mean_yes", "history_n_objects"] + [f"statpop_{c}" for c in DEMOGRAPHICS] + [f"party_share_{name}" for name in PARTIES.values()]
    categorical = TYPOLOGIES + list(OBJECT_FIELDS.values())
    indicators = ["history_missing", "statpop_missing", "elections_missing"]
    report = {
        "mode": "exploratory_retrospective", "strict_forecast_ready": False,
        "requested_start": start, "first_vote": str(table.vote_date.min().date()), "last_vote": str(table.vote_date.max().date()),
        "input_rows": len(ofs), "eligible_history_rows": len(clean),
        "rows_before_start": int(clean.vote_date.lt(pd.Timestamp(start)).sum()), "exclusions_sequential": exclusions,
        "rows_before_joins": len(base), "rows_after_joins": len(table), "join_row_losses": len(base) - len(table),
        "communes": int(table.municipality_id.nunique()), "objects": int(table.vote_id.nunique()), "dates": int(table.vote_date.nunique()),
        "target": "yes_share", "numeric_features": numeric, "categorical_features": categorical, "missing_indicators": indicators,
        "block_matched_rows": {
            "history": int(table.history_mean_yes.notna().sum()), "statpop": int(table.statpop_year.notna().sum()),
            "elections": int(table.election_year.notna().sum()), "typologies": int(table[TYPOLOGIES].notna().all(axis=1).sum()),
            "swissvotes": int(table.object_legal_form.notna().sum()),
        },
        "missing_values": {c: int(table[c].isna().sum()) for c in numeric + categorical},
        "blocks": {
            "history": "Dates strictement antérieures, tous les objets du même jour exclus. Publication historique non vérifiée. Historique roulant rétrospectif, à recalculer selon le protocole train/validation/test.",
            "statpop": "Dernière année dont available_from <= veille du scrutin. Règle conservatrice du 2 septembre Y+1 ; édition actuelle et géographie 2026 rétrospectives.",
            "elections": "Dernière élection d'une année strictement antérieure au scrutin. Le 1er janvier Y+1 est un seuil de sélection supposé, jamais une preuve de publication. PDC, PBD et Centre restent distincts.",
            "typologies": "Classification statique du snapshot 2026. Date de publication non vérifiée ; analyse rétrospective uniquement.",
            "swissvotes": "Forme juridique et codes de domaines seulement. Jointure exacte vote_key, dates et types contrôlés. Classification de l'édition actuelle, disponibilité historique non vérifiée.",
            "brochures": "Exclues : correspondances et admissibilité temporelle à valider.",
        },
        "excluded_predictors": ["yes_share (cible uniquement)", "identifiants", "participation du scrutin", "résultats nationaux/cantonaux du scrutin", "campagne et financement", "recommandations", "texte"],
        "evaluation_note": "Aucun modèle ni partition choisi. Ne pas passer cette table au moteur strict evaluate_votes. Les dates de prévision et de publication attestées restent à établir. Aucune imputation ni normalisation ajustée ici.",
    }
    return table, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2012-01-01")
    args = parser.parse_args()
    frames, hashes = {}, {}
    for name, relative in SOURCES.items():
        path = PROCESSED_DIR / relative
        hashes[name] = {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        frames[name] = pd.read_parquet(path)
    table, report = build(frames, args.start)
    report["sources"] = hashes
    output = PROCESSED_DIR / "modeling"
    output.mkdir(parents=True, exist_ok=True)
    table.to_parquet(output / "municipal_structured.parquet", index=False)
    (output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dictionary = []
    for column in table.columns:
        role = ("target" if column == report["target"] else "numeric_candidate" if column in report["numeric_features"]
                else "categorical_candidate" if column in report["categorical_features"]
                else "missing_indicator" if column in report["missing_indicators"] else "metadata_not_predictor")
        block = ("statpop" if column.startswith("statpop_") else "elections" if column.startswith(("party_share_", "election"))
                 else "history" if column.startswith("history_") else "typologies" if column in TYPOLOGIES
                 else "swissvotes" if column.startswith("object_") else "ofs_or_protocol")
        dictionary.append({"column": column, "role": role, "block": block, "dtype": str(table[column].dtype),
                           "strict_forecast_validated": False, "missing_rows": int(table[column].isna().sum()),
                           "temporal_rule": report["blocks"].get(block, "Identifiant, cible ou métadonnée ; ne pas utiliser comme prédicteur.")})
    pd.DataFrame(dictionary).to_csv(output / "feature_dictionary.csv", index=False)
    report_dir = REPORTS_DIR / "generated" / "modeling_dataset"
    report_dir.mkdir(parents=True, exist_ok=True)
    coverage = table.groupby("vote_date").agg(
        rows=("vote_id", "size"), objects=("vote_id", "nunique"), communes=("municipality_id", "nunique"),
        missing_statpop=("statpop_missing", "sum"), missing_elections=("elections_missing", "sum"), missing_history=("history_missing", "sum"))
    coverage.to_csv(report_dir / "coverage_by_date.csv")
    lines = ["# Table structurée exploratoire", "", "**Mode rétrospectif ; non validé pour une prévision historique stricte.**", "",
             f"{len(table):,} lignes ; {report['objects']} objets ; {report['dates']} dates ; {report['communes']} communes.",
             f"Période : {report['first_vote']} → {report['last_vote']}. Aucune perte de lignes lors des jointures.", "",
             "## Hypothèses par source", ""]
    lines.extend(f"- **{name}** : {text}" for name, text in report["blocks"].items())
    lines += ["", "## Exclusions OFS (séquentielles)", ""]
    lines.extend(f"- {row['reason']} : {row['rows']} lignes." for row in report["exclusions_sequential"])
    lines += ["", "## Valeurs manquantes", "", "| Variable | Nombre | Part |", "|---|---:|---:|"]
    lines.extend(f"| {name} | {n} | {n / len(table):.2%} |" for name, n in report["missing_values"].items())
    lines += ["", report["evaluation_note"]]
    (report_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["rows_after_joins", "objects", "dates", "communes", "first_vote", "last_vote", "strict_forecast_ready"]}))
    print(f"Table: {output / 'municipal_structured.parquet'}")
    print(f"Report: {report_dir / 'report.md'}")


if __name__ == "__main__":
    main()
