"""Checks for the poll formats that can otherwise silently switch survey waves."""

import json
from argparse import Namespace

import pandas as pd
import pytest

from scripts.modeling import collect_poll_features as collector
from scripts.modeling.collect_poll_features import (
    PageParser,
    date_de,
    date_span,
    extract_national_rows,
)

LABELS = [
    "bestimmt dafür",
    "eher dafür",
    "weiss nicht/keine Antwort",
    "eher dagegen",
    "bestimmt dagegen",
]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("11. – 24. Januar 2021", ("2021-01-11", "2021-01-24")),
        ("31. August – 7. September 2022", ("2022-08-31", "2022-09-07")),
        ("17. Dezember – 3. Januar 2022", ("2021-12-17", "2022-01-03")),
        ("4. August– 18. August 2025", ("2025-08-04", "2025-08-18")),
    ],
)
def test_survey_interval_formats(text, expected):
    assert date_span(text) == expected


def test_numeric_and_html_dates():
    assert date_de("27.05.2023") == "2023-05-27"
    assert date_de("6. September<br>2025") == "2025-09-06"


def test_transposed_datawrapper_keeps_both_wave_dates():
    sheet = [["row_labels", "10. August<br>2025", "6. September<br>2025"]]
    sheet += [
        [label, str(v1), str(v2)]
        for label, v1, v2 in zip(LABELS, [37, 21, 9, 14, 19], [40, 11, 4, 12, 33], strict=True)
    ]
    rows = extract_national_rows([("/data.csv", sheet)], "datawrapper")
    assert [r["survey_midpoint"] for r in rows] == ["2025-08-10", "2025-09-06"]
    assert rows[0]["yes_certain"] + rows[0]["yes_lean"] == 58
    assert rows[1]["yes_certain"] + rows[1]["yes_lean"] == 51


def test_horizontal_datawrapper_keeps_dated_waves():
    sheet = [["welle", *LABELS], ["30.4.2023", 55, 29, 4, 5, 6], ["27.05.2023", 53, 21, 3, 9, 15]]
    rows = extract_national_rows([("/data.csv", sheet)], "datawrapper")
    assert [r["survey_midpoint"] for r in rows] == ["2023-04-30", "2023-05-27"]
    assert rows[1]["no_certain"] == 15


def test_undated_multicolumn_chart_is_not_silently_wave_one():
    sheet = [["row_labels", "wave A", "wave B"]]
    sheet += [[label, 20, 20] for label in LABELS]
    assert extract_national_rows([("/data.csv", sheet)], "datawrapper") == []


def test_infogram_uses_country_total_and_excludes_subgroups():
    sheet = [
        [None, *LABELS],
        ["Gesamte Schweiz 14. Februar 2021", 22, 20, 4, 20, 34],
        ["GPS 14. Februar 2021", 70, 15, 4, 5, 6],
        ["französischsprachige Schweiz 14. Februar 2021", 30, 20, 4, 20, 26],
    ]
    rows = extract_national_rows([("/data/0", sheet)], "infogram")
    assert len(rows) == 1
    assert rows[0]["yes_certain"] == 22


def test_exceptional_bare_date_requires_explicit_review_and_first_sheet():
    sheet = [[None, *LABELS], ["5. September 2021", 53, 10, 2, 8, 27]]
    assert extract_national_rows([("/data/0", sheet)], "infogram") == []
    assert len(extract_national_rows([("/data/0", sheet)], "infogram", allow_bare_dates=True)) == 1
    assert extract_national_rows([("/data/1", sheet)], "infogram", allow_bare_dates=True) == []


def test_page_parser_supports_official_embed_generations():
    parser = PageParser()
    parser.feed(
        "<h1>1. SRG-Trendumfrage zur Abstimmung vom 7. März 2021</h1>"
        "<h2>Reviewed object</h2>"
        '<script id="infogram_0__/abc" title="Old poll"></script>'
        '<div class="infogram-embed" data-id="_/def" data-title="Poll"></div>'
        '<iframe title="Stimmabsicht" src="https://datawrapper.dwcdn.net/ABCDE/2/"></iframe>'
        '<iframe src="https://www.googletagmanager.com/tracker"></iframe>'
    )
    assert len(parser.embeds) == 3
    assert parser.embeds[0]["chart_url"] == "https://e.infogram.com/_/abc?src=embed"
    assert all(c["section"] == "Reviewed object" for c in parser.embeds)


def test_empty_scope_overwrites_stale_csv_with_empty_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "OUT", tmp_path)
    (tmp_path / "source_evidence.json").write_text(
        json.dumps({"retrieved_at": "2026-11-23T12:00:00+00:00", "pages": [], "errors": []})
    )
    (tmp_path / "srg_gfs_polls.csv").write_text("stale\nwrong\n")
    metadata = pd.DataFrame(
        {
            "vote_key": ["5550"],
            "vote_date": pd.to_datetime(["2012-03-11"]),
            "titel_kurz_d": ["Example"],
            "titel_off_d": ["Example"],
        }
    )

    def read_metadata(path, *, columns):
        assert columns == ["vote_key", "vote_date", "titel_kurz_d", "titel_off_d"]
        return metadata.copy()

    monkeypatch.setattr(collector.pd, "read_parquet", read_metadata)
    collector.run(Namespace(start_year=2012, end_year=2015, offline=True, reuse_sources=False, include_vote_date=[]))
    output = pd.read_csv(tmp_path / "srg_gfs_polls.csv")
    assert output.empty
    assert output.columns.tolist() == collector.CSV_COLUMNS
