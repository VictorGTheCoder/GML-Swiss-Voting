from datetime import date

import pytest

from scripts.modeling.aps_report_audit_v131 import cover_status, report_url


def test_cover_dates_and_identity():
    vote = date(2022, 9, 25)
    title = "APS- Zeitungs- und Inserateanalyse zu den Abstimmungen vom 25. September 2022"
    assert cover_status(title + " Zwischenstand vom 15.09.2022", vote) == {
        "status": "dated_candidate", "cover_date": "2022-09-15", "lead_days": 10,
    }
    assert cover_status(title + " Zwischenstand vom 25.09.2022", vote)["status"] == "not_prevote"
    assert cover_status(title, vote)["status"] == "cover_date_unverified"
    assert cover_status(title, date(2022, 9, 26))["status"] == "cover_identity_unverified"


def test_report_url():
    assert report_url("6610") == "https://swissvotes.ch/vote/661.00/inserateanalyse.pdf"
    assert report_url("6611") == "https://swissvotes.ch/vote/661.10/inserateanalyse.pdf"
    with pytest.raises(ValueError, match="Invalid roster key"):
        report_url("../661")
