from scripts.federal_explanations.collect_federal_explanations import (
    parse_archive_entries,
)


def test_archive_parser_keeps_pdf_links_and_ballot_dates_in_period():
    html = '''<a href="/dam/fr/2016-02-28_explications.pdf">2016-02-28 - Explications PDF</a>
    <a href="/dam/fr/2010-11-28.pdf">2010-11-28 PDF</a>
    <a href="/other/2016-02-28.txt">2016-02-28 notes</a>'''
    assert parse_archive_entries(html) == [
        {"vote_date": "2016-02-28", "official_url": "https://www.bk.admin.ch/dam/fr/2016-02-28_explications.pdf"}
    ]


def test_archive_parser_accepts_historical_period_when_requested():
    html = '<a href="/dam/fr/1978-02-26.pdf">1978-02-26</a><a href="/dam/fr/1977-01-01.pdf">1977-01-01</a>'
    assert parse_archive_entries(html, start_year=1978) == [
        {"vote_date": "1978-02-26", "official_url": "https://www.bk.admin.ch/dam/fr/1978-02-26.pdf"}
    ]
