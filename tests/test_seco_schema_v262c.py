import hashlib

import pytest

from scripts.modeling.seco_schema_v262c import preview, verify_pinned


def test_hash_pin():
    data = b"year;rate\n2017;2.5\n"
    row = {"format": "csv", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    assert verify_pinned(data, row)["bytes"] == len(data)
    with pytest.raises(ValueError, match="changed"):
        verify_pinned(data.replace(b"2.5", b"2.6"), row)


def test_csv_preview():
    report = preview(b"year;rate\n2017;2.5\n2018;2.6\n", "csv")
    assert report["delimiter"] == ";"
    assert report["sample_widths"] == [2, 2, 2]
    assert report["first_rows"][1] == ["2017", "2.5"]
