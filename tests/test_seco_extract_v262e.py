import pandas as pd
import pytest

from scripts.modeling.seco_extract_v262e import CANTONS, csv_month, excel_month, rate


def csv_data(extra=""):
    header = "REGION;CANTON;PERIOD;VALUE;STATUS;OBS_COEF\n"
    rows = ["Total;Total;2021-08;3.1;A;A",
            "1;Total;2021-08;4;A;A",
            "Total;Total;2021-12;;O;A"]
    rows += [f"1;{i};2021-08;2.5;A;B" for i in CANTONS]
    return (header + "\n".join(rows) + "\n" + extra).encode()


def test_csv_exact_month():
    result = csv_month(csv_data(), "2021-08")
    assert len(result) == 27
    assert result["CH"]["rate_pp"] == 3.1
    assert result["1"]["coefficient_raw"] == "B"


def test_csv_duplicate():
    with pytest.raises(ValueError, match="Duplicate"):
        csv_month(csv_data("1;1;2021-08;3;A;B\n"), "2021-08")


def test_csv_missing():
    with pytest.raises(ValueError, match="Missing"):
        csv_month(csv_data().replace(b"1;26;2021-08;2.5;A;B", b"1;26;2021-07;2.5;A;B"),
                  "2021-08")


def test_excel_month():
    frame = pd.DataFrame([["Quoten in %", "", ""], ["", "VK", "Aug."],
                          ["Total", "A", 2.1]]
                         + [[name, "B", 3.2] for name in CANTONS.values()])
    result, unit = excel_month(frame, "2017-08")
    assert len(result) == 27 and result["CH"]["rate_pp"] == 2.1
    assert unit == "Quoten in %"


def test_invalid_rate():
    for value in ("", "nan", "inf", -1, 101):
        with pytest.raises(ValueError):
            rate(value)
