import pytest

from scripts.modeling.domain_support_v261 import metadata, summarize
from scripts.modeling.stability_v251 import METRICS, NAMES


def test_contributions_and_single_date():
    a, b, c = ("2016-01-01", "1"), ("2016-01-01", "2"), ("2017-01-01", "3")
    rows = {a: ("4", "f1"), b: ("4", "f1"), c: ("5", "f1")}
    panel = {n: {a: dict.fromkeys(METRICS, 6.0), b: dict.fromkeys(METRICS, 9.0),
                 c: dict.fromkeys(METRICS, 3.0)} for n in NAMES}
    result = summarize(panel, rows, {a: True, b: False, c: True})
    assert result["4"]["objects"] == 2
    assert result["4"]["dates"] == 1
    assert result["4"]["leave_date_mae_range"] is None
    assert result["4"]["document_covered_v113"] == 1
    assert sum(r["global_mae_contribution"] for r in result.values()) == 6.0
    assert sum(r["signed_excess_contribution_vs_4"] for r in result.values()) == pytest.approx(2.0)


def test_inconsistent_domain(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("variant,vote_date,vote_id,domain,fold,covered\n"
                    "reference,2016-01-01,a,4,f1,true\n"
                    "v113_institution,2016-01-01,a,5,f1,true\n")
    with pytest.raises(ValueError, match="Inconsistent"):
        metadata(path, {("2016-01-01", "a")})
