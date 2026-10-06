import numpy as np
import pandas as pd
import pytest

from clean_votes import clean_votes, compute_yes_share, parse_provisional_months
from parse_votes import parse_px_text, px_to_long
from validate_votes import ValidationError, assert_valid, run_checks

LOC = "Kanton (-) / Bezirk (>>) / Gemeinde (......)"
LOC_FR = "Canton (-) / District (>>) / Commune (......)"

# 5 locations x 2 votes x 7 measures, same layout as the OFS cube.
# Row order: location outer, vote inner. Commune 0002 has no result for vote 20.
MINI_PX = f'''﻿CHARSET="ANSI";
MATRIX="px-x-1703030000_101";
STUB="{LOC}","Datum und Vorlage";
HEADING="Ergebnis";
VALUES("{LOC}")="Schweiz","- Zürich",">> Bezirk Affoltern",
"......Aeugst am Albis","......Affoltern (Gemeinsame Urne, Standort: X          )";
VALUES[fr]("{LOC_FR}")="Suisse","- Zurich",">> District d'Affoltern",
"......Aeugst am Albis","......Affoltern (Urne commune, emplacement: X          )";
CODES("{LOC}")="CH","ZH","000101","0001","0002";
VALUES("Datum und Vorlage")="2020-02-09 Vorlage A","2021-03-07 Initiative und Gegenvorschlag: Stichfrage";
VALUES[fr]("Date et objet")="2020-02-09 Objet A","2021-03-07 Initiative et contre-projet: question subsidiaire";
CODES("Datum und Vorlage")="10","20";
CODES("Ergebnis")="1","2","3","4","5","6","7";
NOTE[fr]="Ligne 1; avec point-virgule#Résultats provisoires: novembre 2020, "
"mars et juin 2021#";
DATA=
300 150 50 140 70 70 50
300 120 40 110 80 30 72.7272727
300 150 50 140 70 70 50
300 120 40 110 80 30 72.7272727
300 150 50 140 70 70 50
300 120 40 110 80 30 72.7272727
200 100 50 90 60 30 66.6666667
200 80 40 70 55 15 78.5714286
100 50 50 50 10 40 20
"..." "..." "..." "..." "..." "..." "...";
'''


@pytest.fixture
def px():
    return parse_px_text(MINI_PX)


@pytest.fixture
def long_frame(px):
    return px_to_long(px)


def test_header_parsing_handles_semicolons_and_multiline_strings(px):
    note = "".join(px.metadata["NOTE[fr]"])
    assert "Ligne 1; avec point-virgule" in note
    assert "mars et juin 2021" in note
    assert px.metadata['CODES("Datum und Vorlage")'] == ["10", "20"]


def test_px_to_long_keeps_every_cell_in_row_major_order(long_frame):
    assert len(long_frame) == 5 * 2
    row = long_frame[(long_frame["location_code"] == "0001") & (long_frame["vote_id"] == "20")].iloc[0]
    assert (row["votes_yes"], row["votes_no"], row["eligible_voters"]) == (55, 15, 200)
    empty = long_frame[(long_frame["location_code"] == "0002") & (long_frame["vote_id"] == "20")]
    assert empty[["votes_yes", "votes_no", "valid_ballots"]].isna().all(axis=None)
    assert long_frame.attrs["missing_symbols"] == {'"..."': 7}


def test_location_hierarchy_assigns_canton_and_district(long_frame):
    communes = long_frame[long_frame["level"] == "commune"].drop_duplicates("location_code")
    assert set(communes["canton"]) == {"ZH"}
    assert set(communes["district_code"]) == {"000101"}
    assert "Affoltern (Urne commune, emplacement: X)" in set(communes["location_name_fr"])


def test_data_size_mismatch_raises():
    broken = MINI_PX.replace("100 50 50 50 10 40 20\n", "")
    with pytest.raises(ValueError, match="expected"):
        px_to_long(parse_px_text(broken))


def test_compute_yes_share_handles_zero_and_missing():
    yes = pd.Series([30, 0, 0, np.nan])
    no = pd.Series([10, 5, 0, 4])
    share = compute_yes_share(yes, no)
    assert share.iloc[0] == 0.75
    assert share.iloc[1] == 0.0
    assert np.isnan(share.iloc[2]) and np.isnan(share.iloc[3])


def test_parse_provisional_months():
    note = "x#Résultats provisoires: novembre 2025, mars et juin 2026#Etat: août 2026"
    assert parse_provisional_months(note) == {(2025, 11), (2026, 3), (2026, 6)}
    assert parse_provisional_months("no such segment") == set()


def test_clean_votes_logs_each_removal_and_flags(long_frame, px):
    months = parse_provisional_months("".join(px.metadata["NOTE[fr]"]))
    clean, log = clean_votes(long_frame, months)
    removed = {step["step"]: step["rows_removed"] for step in log.steps}
    assert removed == {"keep_commune_level": 6, "drop_empty_cells": 1,
                       "drop_missing_yes_no": 0, "drop_zero_yes_plus_no": 0}
    assert len(clean) == 3
    assert clean["yes_share"].between(0, 1).all()
    tiebreak = clean[clean["vote_id"] == "20"]
    assert tiebreak["is_tiebreak_question"].all() and tiebreak["is_provisional"].all()
    assert not clean.loc[clean["vote_id"] == "10", "is_provisional"].any()
    assert (clean["blank_invalid_ballots"] == clean["ballots_cast"] - clean["valid_ballots"]).all()


def test_validation_passes_on_consistent_data(long_frame):
    clean, _ = clean_votes(long_frame)
    assert_valid(run_checks(clean))


def test_validation_fails_on_duplicate_unit_of_observation(long_frame):
    clean, _ = clean_votes(long_frame)
    duplicated = pd.concat([clean, clean.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValidationError, match="unique"):
        assert_valid(run_checks(duplicated))


def test_validation_fails_on_invalid_target_and_negative_counts(long_frame):
    clean, _ = clean_votes(long_frame)
    clean.loc[0, "yes_share"] = 1.2
    clean.loc[1, "votes_no"] = -1
    failed = {c.name for c in run_checks(clean) if c.severity == "error" and not c.passed}
    assert {"yes_share in [0, 1]", "non_negative:votes_no"} <= failed
