"""Guard against ambiguous joins, identifier rounding and destructive cleaning."""

from datetime import date

import pandas as pd
import pytest

from scripts.common.vote_keys import swissvotes_key
from scripts.integration.prepare_join import prepare_join
from scripts.swissvotes.clean_swissvotes import clean_swissvotes


@pytest.fixture
def raw_swiss():
    return pd.DataFrame({
        "anr": ["682.1", "682.2", "682.3"],
        "datum": ["08.03.2026"] * 3,
        "titel_kurz_d": ["Initiative", "Gegenvorschlag", "Stichfrage"],
        "titel_kurz_f": [" Initiative ", "Contre-projet", "Question subsidiaire"],
        "rechtsform": ["3", "4", "5"],
        "init_formul": ["1", "9999", "9999"],
        "volkja": ["60", "70", "40"], "volknein": ["40", "30", "60"],
        "volkja-proz": ["60.00", "70.00", "40.00"],
        "stichwort": [".", "", "NA"],
        "dat-limit": ["9999", "0", "."],
    })


@pytest.mark.parametrize(("raw", "key"), [("687", "6870"), ("687.0", "6870"),
                                         ("682.1", "6821"), (" 682.30 ", "6823")])
def test_keys_are_exact(raw, key):
    assert swissvotes_key(raw) == key


@pytest.mark.parametrize("raw", ["", ".", "nan", "682.31", "-1", "0", "1e2"])
def test_keys_reject_missing_or_rounding(raw):
    with pytest.raises(ValueError):
        swissvotes_key(raw)


def test_cleaning_preserves_semantic_codes_and_questions(raw_swiss):
    clean, report = clean_swissvotes(raw_swiss, today=date(2026, 10, 6))
    assert clean["vote_key"].tolist() == ["6821", "6822", "6823"]
    assert clean["is_tiebreak_question"].tolist() == [False, False, True]
    assert clean["init_formul"].tolist() == ["1", "9999", "9999"]
    assert clean["dat-limit"].iloc[:2].tolist() == ["9999", "0"]
    assert clean["stichwort"].isna().tolist() == [True, True, False]
    assert clean.loc[2, "stichwort"] == "NA"
    assert clean.loc[0, "titel_kurz_f"] == "Initiative"
    assert str(clean["volkja"].dtype) == "Int64"
    assert "PASS" in report


@pytest.mark.parametrize(("column", "value"), [("datum", "31.02.2026"), ("rechtsform", "8"),
                                              ("volkja", "1.5"), ("volkja", "-1"),
                                              ("volkja", "inf"), ("volkja-proz", "101")])
def test_invalid_swissvotes_values_block_publication(raw_swiss, column, value):
    raw_swiss.loc[0, column] = value
    with pytest.raises(ValueError):
        clean_swissvotes(raw_swiss)


def test_colliding_normalized_keys_are_rejected(raw_swiss):
    raw_swiss.loc[1, "anr"] = "682.10"
    with pytest.raises(ValueError, match="duplicate normalized"):
        clean_swissvotes(raw_swiss)


def test_future_votes_are_retained_and_flagged(raw_swiss):
    clean, _ = clean_swissvotes(raw_swiss, today=date(2025, 1, 1))
    assert len(clean) == len(raw_swiss)
    assert clean["is_future_vote"].all()


def test_known_inconsistency_is_visible(raw_swiss):
    raw_swiss.loc[0, "volkja-proz"] = "59"
    clean, _ = clean_swissvotes(raw_swiss)
    assert clean["flag_national_pct_mismatch"].tolist() == [True, False, False]


@pytest.fixture
def join_frames(raw_swiss):
    swiss, _ = clean_swissvotes(raw_swiss)
    ofs = pd.concat([swiss[["vote_key", "vote_date", "is_tiebreak_question"]].assign(municipality_id=unit)
                     for unit in ("0001", "0002")], ignore_index=True)
    ofs["vote_id"] = ofs["vote_key"]
    return ofs, swiss


def test_same_day_questions_join_without_multiplying_communes(join_frames):
    ofs, swiss = join_frames
    crosswalk, extras, report = prepare_join(ofs, swiss)
    assert crosswalk["swissvotes_id"].tolist() == ["682.1", "682.2", "682.3"]
    assert crosswalk["join_status"].eq("matched").all()
    assert extras.empty
    assert "no municipal join performed" in report


def test_missing_match_does_not_disappear(join_frames):
    ofs, swiss = join_frames
    crosswalk, _, report = prepare_join(ofs, swiss.iloc[1:])
    assert crosswalk["join_status"].tolist() == ["missing_swissvotes", "matched", "matched"]
    assert "Status: FAIL" in report


@pytest.mark.parametrize(("column", "value", "status"), [
    ("vote_date", pd.Timestamp("2026-03-09"), "date_mismatch"),
    ("is_tiebreak_question", True, "question_type_mismatch"),
])
def test_metadata_conflicts_block_matches(join_frames, column, value, status):
    ofs, swiss = join_frames
    swiss.loc[0, column] = value
    crosswalk, _, _ = prepare_join(ofs, swiss)
    assert crosswalk.loc[0, "join_status"] == status


def test_duplicate_swissvotes_key_is_not_many_to_many(join_frames):
    ofs, swiss = join_frames
    with pytest.raises(ValueError, match="must be unique"):
        prepare_join(ofs, pd.concat([swiss, swiss.iloc[:1]]))


def test_duplicate_municipality_question_is_rejected(join_frames):
    ofs, swiss = join_frames
    with pytest.raises(ValueError, match="duplicate municipality"):
        prepare_join(pd.concat([ofs, ofs.iloc[:1]]), swiss)


def test_swissvotes_only_objects_are_reported(join_frames):
    ofs, swiss = join_frames
    crosswalk, extras, report = prepare_join(ofs[ofs["vote_key"] != "6823"], swiss)
    assert len(crosswalk) == 2
    assert extras["swissvotes_id"].tolist() == ["682.3"]
    assert extras["reason"].tolist() == ["not_in_clean_ofs"]
    assert "Status: PASS" in report


def test_preparation_keeps_features_separate_and_inputs_unchanged(join_frames):
    ofs, swiss = join_frames
    ofs["votes_yes"] = 123
    swiss["topic"] = "health"
    original_ofs, original_swiss = ofs.copy(deep=True), swiss.copy(deep=True)
    crosswalk, extras, _ = prepare_join(ofs, swiss)
    for frame in (crosswalk, extras):
        assert "votes_yes" not in frame
        assert "topic" not in frame
        assert "municipality_id" not in frame
    pd.testing.assert_frame_equal(ofs, original_ofs)
    pd.testing.assert_frame_equal(swiss, original_swiss)
