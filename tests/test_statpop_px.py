from io import StringIO

import pytest

from scripts.statpop.parse_statpop_px import data_rows


def test_age_rows_can_cross_physical_line_boundaries():
    assert list(data_rows(StringIO('1 2\n3 4 5\n6;\n'), 3)) == [
        ['1', '2', '3'], ['4', '5', '6'],
    ]


def test_truncated_age_row_is_rejected():
    with pytest.raises(ValueError, match='Truncated'):
        list(data_rows(StringIO('1 2 3\n4;'), 3))
