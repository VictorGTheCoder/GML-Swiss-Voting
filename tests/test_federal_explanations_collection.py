from scripts.collect_federal_explanations import parse_archive_entries


def test_archive_parser_keeps_pdf_links_and_ballot_dates_in_period():
    html = '''<a href="/dam/fr/2016-02-28_explications.pdf">2016-02-28 - Explications PDF</a>
    <a href="/dam/fr/2010-11-28.pdf">2010-11-28 PDF</a>
    <a href="/other/2016-02-28.txt">2016-02-28 notes</a>'''
    assert parse_archive_entries(html) == [
        {"vote_date": "2016-02-28", "official_url": "https://www.bk.admin.ch/dam/fr/2016-02-28_explications.pdf"}
    ]
