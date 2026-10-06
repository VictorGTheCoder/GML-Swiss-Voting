"""Audit the raw vote cube BEFORE cleaning and write reports/data_audit.md.

Runs on the lossless long table produced by parse_votes.py (all levels, all cells,
missing values untouched). Every number in the report is computed here.

Usage: python scripts/audit_votes.py  (reads data/interim/votes_all_levels.parquet)
"""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from parse_votes import map_categories
from votes_config import (
    DIM_LOCATION, DIM_RESULT, DIM_VOTE, INTERIM_PATH, PROVENANCE_PATH, RAW_PX_PATH, REPORTS_DIR,
    RESULT_COLUMNS, SPECIAL_UNIT_MIN_CODE, is_special_code,
)

AUDIT_PATH = REPORTS_DIR / "data_audit.md"
RESULTS = list(RESULT_COLUMNS.values())
# First year the OFS says commune-level data are complete (1960-1980 come from sotomo).
COMPLETE_FROM_YEAR = 1981
# A few well-known mergers used as spot checks of the harmonisation (code as of 01.01.2026).
KNOWN_MERGERS = [
    ("1630", "Glarus Nord", "2011-01-01"),
    ("6487", "Val-de-Ruz", "2013-01-01"),
    ("5002", "Bellinzona", "2017-04-02"),
    ("0292", "Stammheim", "2019-01-01"),
]


def _md(frame: pd.DataFrame, index: bool = False) -> str:
    return frame.to_markdown(index=index, floatfmt=".6g")


def _pct(part: float, whole: float) -> str:
    return f"{part:,} ({part / whole:.2%})" if whole else f"{part:,}"


def _with_dates(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["vote_date"] = pd.to_datetime(map_categories(frame["vote_label_de"], lambda s: s[:10]),
                                        format="%Y-%m-%d", errors="coerce")
    frame["is_special"] = map_categories(frame["location_code"], is_special_code).astype(bool)
    frame["is_tiebreak"] = map_categories(frame["vote_label_de"], lambda s: "Stichfrage" in s).astype(bool)
    frame["year"] = frame["vote_date"].dt.year
    frame["has_result"] = frame[RESULTS].notna().any(axis=1)
    frame["has_yes_no"] = frame["votes_yes"].notna() & frame["votes_no"].notna()
    return frame


def section_provenance(meta: dict[str, list[str]]) -> str:
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8")) if PROVENANCE_PATH.exists() else {}
    note = "".join(meta.get("NOTE[fr]", []))
    note_items = [re.sub(r"<[^>]+>", "", item).strip() for item in note.split("#") if item.strip()]
    lines = ["## 1. Provenance", ""]
    lines += [f"- **{key}**: {value}" for key, value in provenance.items()] or ["- provenance file missing"]
    lines += [f"- **PX TITLE[fr]**: {meta.get('TITLE[fr]', [''])[0]}",
              f"- **PX CONTENTS[fr]**: {meta.get('CONTENTS[fr]', [''])[0]}",
              f"- **PX SOURCE[fr]**: {meta.get('SOURCE[fr]', [''])[0]}",
              "", "OFS note (NOTE[fr]), verbatim items:", ""]
    lines += [f"> {item}  " for item in note_items]
    return "\n".join(lines)


def section_structure(meta: dict[str, list[str]], frame: pd.DataFrame) -> str:
    dims = [(DIM_LOCATION, "stub"), (DIM_VOTE, "stub"), (DIM_RESULT, "heading")]
    dim_table = pd.DataFrame([{"dimension": d, "role": role, "n_codes": len(meta[f'CODES("{d}")'])} for d, role in dims])
    n_cells = int(np.prod(dim_table["n_codes"]))
    result_table = pd.DataFrame({"code": meta[f'CODES("{DIM_RESULT}")'], "label_de": meta[f'VALUES("{DIM_RESULT}")'],
                                 "label_fr": meta['VALUES[fr]("Résultat")'],
                                 "project_column": [RESULT_COLUMNS[c] for c in meta[f'CODES("{DIM_RESULT}")']]})
    levels = frame.groupby("level", observed=True)["location_code"].nunique().rename("n_units").reset_index()
    missing = frame[RESULTS].isna().sum().rename("n_missing").to_frame()
    missing["share"] = (missing["n_missing"] / len(frame)).map("{:.2%}".format)
    dtypes = frame.dtypes.astype(str).rename("dtype").to_frame()
    sample = frame[frame["level"] == "commune"].dropna(subset=["votes_yes"]).head(5)
    symbols = frame.attrs.get("missing_symbols") or {}
    return "\n".join([
        "## 2. Raw structure", "",
        "The PX file is a 3-dimensional cube (location x vote object x result measure). "
        "`parse_votes.py` reshapes it without loss: one row per location x vote, one column per result measure.", "",
        _md(dim_table), "",
        f"- Values in DATA: {n_cells:,} (= product of the dimensions; checked at parse time)",
        f"- Missing-value symbols in DATA: {symbols if symbols else 'n/a'}",
        f"- Long table: {len(frame):,} rows x {frame.shape[1]} columns", "",
        "Result measures (meaning taken from the PX labels, not guessed from names):", "", _md(result_table), "",
        "There is **no separate count of blank or invalid ballots**; only `ballots_cast - valid_ballots` "
        "(blank + invalid combined) can be derived.", "",
        "Location levels (hierarchy from the ordered location list: canton code, district `>>`, commune `......`):", "",
        _md(levels), "", "Column types:", "", _md(dtypes, index=True), "",
        "Missing values per result column (all levels):", "", _md(missing, index=True), "",
        "Sample commune rows:", "", _md(sample.drop(columns=["vote_label_fr"])),
    ])


def section_identifiers() -> str:
    return "\n".join([
        "## 3. Unit of observation and identifiers", "",
        "After reshaping, a commune-level row is one **commune x vote object** (each OFS vote code is one "
        "question; several questions share a date). No further pivot is needed.", "",
        "| concept | source field | notes |", "|---|---|---|",
        "| vote object id | `CODES(\"Datum und Vorlage\")` -> `vote_id` | OFS numeric code, unique per question |",
        "| vote date | first 10 chars of the vote label (`YYYY-MM-DD`) | no separate date field in the cube |",
        "| vote title | rest of the label, DE and FR | |",
        "| commune code | 4-digit location code -> `municipality_id` | BFS commune number (state 01.01.2026) |",
        "| commune name | location label, FR (and DE) | hierarchy prefix removed |",
        "| canton | preceding 2-letter location code | |",
        "| district | preceding 6-digit location code (`00` + 4-digit BFS district number) | |",
        f"| special unit | commune code >= {SPECIAL_UNIT_MIN_CODE} | Swiss abroad / correspondence / other, not a commune |",
    ])


def section_statistics(df: pd.DataFrame) -> str:
    communes = df[df["level"] == "commune"]
    with_result = communes[communes["has_result"]]
    critical = ["vote_id", "vote_date", "location_code", "location_name_fr", "canton", "votes_yes", "votes_no",
                "eligible_voters", "ballots_cast", "valid_ballots"]
    missing = pd.DataFrame({"n_missing_all_cells": communes[critical].isna().sum(),
                            "n_missing_cells_with_any_result": with_result[critical].isna().sum()})
    missing["share_all_cells"] = (missing["n_missing_all_cells"] / len(communes)).map("{:.2%}".format)
    missing["share_cells_with_result"] = (missing["n_missing_cells_with_any_result"] / len(with_result)).map("{:.2%}".format)
    duplicates = communes.duplicated(["location_code", "vote_id"], keep=False).sum()
    name_dups = communes.groupby("location_name_fr", observed=True)["location_code"].nunique().gt(1).sum()
    special = communes["is_special"]
    stats = pd.DataFrame([
        ("commune-level rows (full grid)", f"{len(communes):,}"),
        ("rows with at least one result", _pct(len(with_result), len(communes))),
        ("rows with yes and no", _pct(int(communes["has_yes_no"].sum()), len(communes))),
        ("distinct commune codes", communes["location_code"].nunique()),
        ("  of which special units (code >= 9000)", communes.loc[special, "location_code"].nunique()),
        ("distinct commune names (FR)", communes["location_name_fr"].nunique()),
        ("names shared by several codes", int(name_dups)),
        ("commune codes never having any result", int((~communes.groupby("location_code", observed=True)["has_result"].any()).sum())),
        ("cantons", communes["canton"].nunique()),
        ("districts", communes["district_code"].nunique()),
        ("distinct vote objects", communes["vote_id"].nunique()),
        ("distinct vote dates", communes["vote_date"].nunique()),
        ("first vote date", communes["vote_date"].min().date()),
        ("last vote date", communes["vote_date"].max().date()),
        ("duplicate commune x vote rows", int(duplicates)),
    ], columns=["statistic", "value"])
    return "\n".join(["## 4. Main statistics (commune level, before cleaning)", "", _md(stats), "",
                      "Missing values on critical fields:", "", _md(missing, index=True)])


def section_coverage(df: pd.DataFrame) -> str:
    communes = df[(df["level"] == "commune") & df["has_result"]]
    regular = communes[~communes["is_special"]]
    per_year = communes.groupby("year").agg(dates=("vote_date", "nunique"), vote_objects=("vote_id", "nunique"),
                                             rows=("vote_id", "size"))
    per_vote = regular.groupby(["year", "vote_id"], observed=True)["location_code"].nunique()
    per_year["regular_communes_per_vote_min"] = per_vote.groupby(level=0).min()
    per_year["regular_communes_per_vote_median"] = per_vote.groupby(level=0).median()
    all_communes = df[df["level"] == "commune"]
    canton_units = all_communes.groupby("canton", observed=True)["location_code"].nunique().rename("commune_codes")
    cov = regular.assign(period=np.where(regular["year"] < COMPLETE_FROM_YEAR, "1960-1980", "1981+"))
    per_canton = cov.pivot_table(index="canton", columns="period", values="vote_id", aggfunc="nunique", observed=True)
    per_canton.columns = [f"vote_objects_{c}" for c in per_canton.columns]
    per_canton = per_canton.join(canton_units)
    per_canton["rows_with_result"] = regular.groupby("canton", observed=True).size()
    per_canton["first_year_with_data"] = regular.groupby("canton", observed=True)["year"].min()
    return "\n".join(["## 5. Coverage", "", "### By year", "", _md(per_year, index=True), "",
                      "### By canton (regular communes only)", "", _md(per_canton, index=True)])


def section_consistency(df: pd.DataFrame) -> str:
    c = df[(df["level"] == "commune") & df["has_result"]]
    yes_no = c["votes_yes"] + c["votes_no"]
    counts = c[["eligible_voters", "ballots_cast", "valid_ballots", "votes_yes", "votes_no"]]
    share = c["votes_yes"] / yes_no.where(yes_no != 0)
    turnout = c["ballots_cast"] / c["eligible_voters"].where(c["eligible_voters"] != 0)
    checks = pd.DataFrame([
        ("negative counts", int((counts < 0).sum().sum())),
        ("non-integer counts", int((((counts % 1) != 0) & counts.notna()).sum().sum())),
        ("yes + no == 0", int((yes_no == 0).sum())),
        ("yes_share < 0 or > 1", int(((share < 0) | (share > 1)).sum())),
        ("ballots_cast > eligible_voters", int((c["ballots_cast"] > c["eligible_voters"]).sum())),
        ("valid_ballots > ballots_cast", int((c["valid_ballots"] > c["ballots_cast"]).sum())),
        ("yes + no > valid_ballots", int((yes_no > c["valid_ballots"]).sum())),
        ("yes + no < valid_ballots", int((yes_no < c["valid_ballots"]).sum())),
        ("max |100*yes_share - OFS yes %|", f"{(share * 100 - c['yes_pct_ofs']).abs().max():.2e}"),
        ("max |100*turnout - OFS turnout %|", f"{(turnout * 100 - c['turnout_pct_ofs']).abs().max():.2e}"),
    ], columns=["check", "value"])
    lt = c[yes_no < c["valid_ballots"]]
    lt_dates = lt.groupby("vote_date").size().sort_values(ascending=False).head(8).rename("rows").reset_index()
    lt_dates["vote_date"] = lt_dates["vote_date"].dt.date
    gt = c[yes_no > c["valid_ballots"]].groupby("year").size().rename("rows").reset_index()
    bad_valid = c.loc[c["valid_ballots"] > c["ballots_cast"],
                      ["location_code", "location_name_fr", "vote_label_fr", "ballots_cast", "valid_ballots"]]
    return "\n".join([
        "## 6. Internal consistency of results", "", _md(checks), "",
        "`yes + no < valid_ballots` by date (top 8). These are dates where one ballot carried an initiative, "
        "its counter-proposal and a tie-break question: a voter may leave one question blank, so the "
        "per-question yes + no is below the per-ballot valid count. Structural, not an error:", "", _md(lt_dates), "",
        "`yes + no > valid_ballots` by year (inconsistent, kept and flagged):", "", _md(gt), "",
        "`valid_ballots > ballots_cast` (inconsistent, kept and flagged):", "", _md(bad_valid),
    ])


def section_target(df: pd.DataFrame) -> str:
    c = df[df["level"] == "commune"]
    yes_no = c["votes_yes"] + c["votes_no"]
    share = (c["votes_yes"] / yes_no.where(yes_no != 0)).dropna()
    tie = c[c["is_tiebreak"]]
    return "\n".join([
        "## 7. Target `yes_share = votes_yes / (votes_yes + votes_no)`", "",
        f"- computable rows: {len(share):,} of {len(c):,} commune cells",
        f"- rows with yes/no missing: {int(yes_no.isna().sum()):,}; rows with yes + no = 0: {int((yes_no == 0).sum())}",
        f"- range: [{share.min():.4f}, {share.max():.4f}], mean {share.mean():.4f}, median {share.median():.4f}",
        f"- exactly 0: {int((share == 0).sum())}, exactly 1: {int((share == 1).sum())} (small communes)",
        f"- tie-break questions (`Stichfrage`): {tie['vote_id'].nunique()} vote objects. "
        "OFS: *yes = for the initiative, no = for the counter-proposal*, so `yes_share` there is **not** "
        "an approval share. Flagged `is_tiebreak_question`.",
    ])


def section_special_units(df: pd.DataFrame) -> str:
    c = df[df["level"] == "commune"]
    special = c[c["is_special"]]
    keys = ["location_code", "location_name_fr"]
    table = special.groupby(keys, observed=True).agg(vote_objects_with_result=("has_result", "sum"))
    years = special[special["has_result"]].groupby(keys, observed=True)["year"]
    table["first_year"] = years.min().astype("Int64")
    table["last_year"] = years.max().astype("Int64")
    table = table.reset_index()
    no_result = c.groupby(["location_code", "location_name_fr"], observed=True)["has_result"].any()
    no_result = no_result[~no_result].reset_index()[["location_code", "location_name_fr"]]
    return "\n".join([
        "## 8. Special units and communes without own results", "",
        f"{table['location_code'].nunique()} special units (code >= {SPECIAL_UNIT_MIN_CODE}); they are not "
        "communes and cannot be joined to commune characteristics. Kept, flagged `is_special_unit`.", "",
        _md(table), "", "Location codes that never have a result (communes counted with another commune's "
        "ballot box, and unused special units):", "", _md(no_result),
    ])


def section_harmonisation(df: pd.DataFrame, meta: dict[str, list[str]]) -> str:
    note = "".join(meta.get("NOTE[fr]", []))
    spatial = next((s for s in note.split("#") if "Référence spatiale" in s), "(not found in NOTE)")
    communes = df[df["level"] == "commune"]
    cantons = df[df["level"] == "canton"].set_index(["canton", "vote_id"], verify_integrity=True)
    sums = communes.groupby(["canton", "vote_id"], observed=True)["votes_yes"].sum(min_count=1)
    comparison = cantons[["votes_yes", "year"]].join(sums.rename("sum_communes")).dropna(subset=["votes_yes"])
    comparison["period"] = np.where(comparison["year"] < COMPLETE_FROM_YEAR, "1960-1980", "1981+")
    comparison["diff"] = comparison["votes_yes"] - comparison["sum_communes"]
    grouped = comparison.groupby(["period", "canton"], observed=True)
    by_canton = pd.DataFrame({
        "votes_with_canton_row": grouped.size(),
        "no_commune_data": grouped["sum_communes"].apply(lambda s: int(s.isna().sum())),
        "sum_differs": grouped["diff"].apply(lambda d: int((d.notna() & (d != 0)).sum())),
        "min_diff": grouped["diff"].min(), "max_diff": grouped["diff"].max(),
    })
    by_canton = by_canton[(by_canton["no_commune_data"] > 0) | (by_canton["sum_differs"] > 0)]

    has_result = communes[communes["has_result"]]
    first_year = has_result.groupby(["location_code", "location_name_fr"], observed=True)["year"].min()
    first_year = first_year[[not is_special_code(code) for code in first_year.index.get_level_values(0)]]
    late = first_year[first_year > COMPLETE_FROM_YEAR].sort_values().rename("first_year_with_data").reset_index()
    merged = pd.DataFrame(KNOWN_MERGERS, columns=["location_code", "commune", "created_by_merger"])
    merged["first_year_with_data"] = merged["location_code"].map(first_year.droplevel(1)).astype("Int64")
    merged["vote_objects_with_data"] = merged["location_code"].map(
        has_result.groupby("location_code", observed=True)["vote_id"].nunique())
    pre1981 = by_canton.loc["1960-1980"] if "1960-1980" in by_canton.index.get_level_values(0) else by_canton.iloc[:0]
    missing_cantons = ", ".join(pre1981.index[pre1981["no_commune_data"] > pre1981["votes_with_canton_row"] / 2])
    return "\n".join([
        "## 9. Municipal mergers / harmonisation", "",
        "OFS statement (NOTE[fr]):", "", f"> {spatial.strip()}", "",
        "Implications, checked in the data:", "",
        "- Commune codes are the BFS numbers valid on 01.01.2026. Results of communes that later merged are "
        "**re-attributed to today's commune**: a merged commune has one row per vote going back before its "
        "creation, and former communes do not appear as separate units. The cube cannot show results on "
        "historical boundaries. Examples (merger dates from the official commune register, not from this cube):", "",
        _md(merged), "",
        "- Canton totals keep their *original* state, while commune rows are harmonised. So the sum of a canton's "
        "communes differs from the canton row wherever communes changed canton: Moutier BE -> JU (effective "
        "2026, mirror-image BE/JU differences), the Laufental BE -> BL (1994), and before 1979 the communes of "
        "today's canton of Jura (counted in BE at the time). Per-canton aggregates must be computed from commune "
        "rows and never mixed with canton rows.", "",
        "Canton row minus sum of its commune rows (`votes_yes`). `no_commune_data`: the canton row exists but no "
        "commune of that canton has data for the vote:", "",
        _md(by_canton, index=True), "",
        f"- The OFS note says 1960-1980 data are incomplete, with FR, AG and TI missing. Confirmed: cantons with "
        f"no commune data for most pre-1981 votes: **{missing_cantons or 'none'}**.",
        f"- {len(late)} regular communes only have data from after {COMPLETE_FROM_YEAR}. Some were created by a "
        "**split** that is not back-cast (e.g. Ittigen and Ostermundigen, separated from Bolligen in 1983). For "
        "others the likely reason is that they previously shared a ballot box with another commune. This was "
        "not verified case by case:", "", _md(late),
    ])


def build_audit(frame: pd.DataFrame, meta: dict[str, list[str]]) -> str:
    df = _with_dates(frame)
    sections = [
        "# Data audit: OFS federal vote results by commune (px-x-1703030000_101)",
        "*Generated by `scripts/audit_votes.py` from the raw cube before any cleaning. Do not edit by hand.*",
        section_provenance(meta), section_structure(meta, frame), section_identifiers(), section_statistics(df),
        section_coverage(df), section_consistency(df), section_target(df), section_special_units(df),
        section_harmonisation(df, meta),
    ]
    return "\n\n".join(sections) + "\n"


def main() -> None:
    from parse_votes import read_px_metadata

    frame = pd.read_parquet(INTERIM_PATH)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(build_audit(frame, read_px_metadata(RAW_PX_PATH)), encoding="utf-8")
    print(f"Wrote {AUDIT_PATH}")


if __name__ == "__main__":
    main()
