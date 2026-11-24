"""Public archive extraction and geography gates."""
import pytest

from scripts.modeling.gradiom_benchmark import changed_codes, errors, observed_share, parse_map


def test_mutations_exclude_both_initial_and_terminal_retained_ids():
    events = [{"MutationDate":"01.01.2025","InitialCode":"100","TerminalCode":"101"},
              {"MutationDate":"01.01.2024","InitialCode":"50","TerminalCode":"51"},
              {"MutationDate":"01.01.2027","InitialCode":"200","TerminalCode":"201"}]
    assert changed_codes(events,"2024-01-01","2026-01-01")=={100,101}
    assert changed_codes(events,"2026-01-01","2024-01-01")=={100,101}


def test_official_votes_require_complete_counts():
    assert observed_share({"gebietAusgezaehlt":False,"jaStimmenAbsolut":1,"neinStimmenAbsolut":3}) is None
    assert observed_share({"gebietAusgezaehlt":True,"jaStimmenAbsolut":1,"neinStimmenAbsolut":3})==25.
    with pytest.raises(ValueError):
        observed_share({"gebietAusgezaehlt":True,"jaStimmenAbsolut":1,"neinStimmenAbsolut":3,"jaStimmenInProzent":30.})


def test_score_centered():
    m = errors([20.,40.,60.],[10.,30.,50.])
    assert m["mae_pp"]==10.
    assert m["centered_mae_pp"]==0.


def test_map_requires_point_quantile_and_predate():
    pytest.importorskip("bs4")
    raw = b'''<h2>Prediction</h2><h2>Object title</h2><h4>Results generated and predicted on 29 January 2025</h4>
        <a href="/en/swiss-popular-votes/2025-02-09">Back</a><div>Yes: 42.1%</div>
        <div id="map-container" data-vote="6770" data-level="commune" data-quantile="50">
        <svg><!-- Communes 01.01.2024 --><path id="commune-1" data-approval="42.4" data-name="X"/></svg></div>'''
    m = parse_map(raw,"6770","2025-02-09","commune")
    assert m["records"]=={1:(42.4,"X")}
    with pytest.raises(ValueError):
        parse_map(raw.replace(b'data-quantile="50"',b'data-quantile="95"'),"6770","2025-02-09","commune")
    with pytest.raises(ValueError):
        parse_map(raw.replace(b"29 January 2025",b"10 February 2025"),"6770","2025-02-09","commune")
