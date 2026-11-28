import json
from datetime import date
from pathlib import Path

import pytest

from scripts.modeling.seco_vintages_v262 import inspect_bytes, select_vintage, validate_catalog

CATALOG = Path("reports/experiments/v26_campaign/V26.2-vintages.json")


def test_catalog():
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))["assets"]
    validate_catalog(rows)
    assert len(rows) == 6
    with pytest.raises(ValueError):
        validate_catalog(rows + rows[:1])


def test_strict_asof_and_staleness():
    rows = [{"published": "2018-06-07", "end": "2018-05-31"}]
    assert select_vintage(rows, date(2018, 6, 7)) is None
    assert select_vintage(rows, date(2018, 6, 8)) == rows[0]
    assert select_vintage(rows, date(2018, 8, 1)) is None
    with pytest.raises(ValueError):
        select_vintage(rows, date(2023, 1, 1))


def test_format_rejection():
    assert inspect_bytes(b"date,value\n2018,2.5\n", "csv")["bytes"] == len(b"date,value\n2018,2.5\n")
    with pytest.raises(ValueError):
        inspect_bytes(b"<html>error</html>", "csv")
    with pytest.raises(ValueError):
        inspect_bytes(b"not excel", "xls")
