"""Verify reversible selection, source preservation and compatibility of keys."""

import pandas as pd

from scripts.swissvotes import clean_swissvotes as cleaning
from scripts.swissvotes.select_swissvotes_columns import select_swissvotes_columns


def test_selection_keeps_sparse_and_semantic_values_without_mutating_source():
    clean = pd.DataFrame({
        "vote_key": [str(n) for n in range(1, 21)],
        "swissvotes_id": [str(n / 10) for n in range(1, 21)],
        "empty": [pd.NA] * 20,
        "rare_theme": ["health"] + [pd.NA] * 19,
        "zero": [0] * 20, "special_code": ["9999"] * 20,
        "volkja": [50] * 20, "vd-japroz": [50] * 20,
        "dat-force": ["0"] * 20,
        "flag_national_pct_mismatch": [False] * 20,
        "finanz-link-fr": ["https://example.test"] * 20,
        "finanz-ja-tot": [1000] * 20, "nrja": [120] * 20,
        "pdev-sps_VD": ["1"] * 20, "swissvoteslink": ["https://swissvotes.ch"] * 20,
    })
    original = clean.copy(deep=True)
    selected, log = select_swissvotes_columns(clean)
    assert selected.columns.tolist() == [
        "vote_key", "swissvotes_id", "rare_theme", "zero", "special_code",
        "finanz-ja-tot", "nrja", "pdev-sps_VD", "swissvoteslink",
    ]
    pd.testing.assert_frame_equal(clean, original)
    pd.testing.assert_frame_equal(selected, clean[selected.columns])
    decisions = log.set_index("column")
    assert decisions.loc["empty", "reason"] == "entirely_empty"
    assert decisions.loc["rare_theme", "missing_share"] == 0.95
    assert set(log["column"]) == set(clean.columns)


def test_cleaning_writes_full_interim_and_selected_processed(tmp_path, monkeypatch):
    paths = {
        "SWISSVOTES_PATH": tmp_path / "raw.csv",
        "SWISSVOTES_INTERIM_PATH": tmp_path / "interim" / "swissvotes_clean.parquet",
        "SWISSVOTES_CLEAN_PATH": tmp_path / "processed" / "swissvotes_clean.parquet",
        "SWISSVOTES_REPORT_PATH": tmp_path / "reports" / "swissvotes_cleaning.md",
    }
    for name, path in paths.items():
        monkeypatch.setattr(cleaning, name, path)
    pd.DataFrame({
        "anr": ["682.1", "682.2"], "datum": ["08.03.2026"] * 2,
        "titel_kurz_d": ["A", "B"], "titel_kurz_f": ["A", "B"], "rechtsform": ["3", "4"],
        "empty": [".", " "], "volkja": ["60", "70"], "volknein": ["40", "30"],
        "init_formul": ["1", "9999"],
    }).to_csv(paths["SWISSVOTES_PATH"], sep=";", index=False)
    raw_bytes = paths["SWISSVOTES_PATH"].read_bytes()
    cleaning.main()
    interim = pd.read_parquet(paths["SWISSVOTES_INTERIM_PATH"])
    processed = pd.read_parquet(paths["SWISSVOTES_CLEAN_PATH"])
    assert interim["empty"].isna().all()
    assert interim["volkja"].tolist() == [60, 70]
    assert {"anr", "datum", "volkja", "volknein", "empty"}.isdisjoint(processed.columns)
    assert processed["vote_key"].tolist() == ["6821", "6822"]
    assert {"swissvotes_id", "vote_date", "is_tiebreak_question"} <= set(processed.columns)
    pd.testing.assert_frame_equal(processed, interim[processed.columns])
    assert paths["SWISSVOTES_PATH"].read_bytes() == raw_bytes
    assert (paths["SWISSVOTES_REPORT_PATH"].parent / "swissvotes_column_selection.csv").is_file()
