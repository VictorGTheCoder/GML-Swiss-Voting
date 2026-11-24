import numpy as np
import pandas as pd

from scripts.modeling.acquire_v9 import choose_matches, map_counts, title_score


def test_title_matching_is_conservative():
    assert title_score("Loi fédérale sur l’énergie", "Loi fédérale sur l'énergie") == 1
    assert title_score("Oui", "Oui") == 0
    roster = pd.DataFrame({"vote_id":["1","2"],"vote_date":["2020-01-01"]*2,
        "source_id":["s"]*2,"pdf_sha256":["abc"]*2,
        "titel_kurz_f":["Loi fédérale sur l’énergie","Loi fédérale sur l’énergie"],
        "titel_off_f":["Loi fédérale sur l’énergie","Loi fédérale sur l’énergie"]})
    sections = pd.DataFrame({"source_id":["s"],"pdf_sha256":["abc"],"object_id":["x"],
                            "title":["Loi fédérale sur l’énergie"]})
    assert choose_matches(roster,sections).empty
    assert len(choose_matches(roster.iloc[:1],sections)) == 1


def test_merge_counts_before_shares_and_preserve_suppression():
    f=pd.DataFrame({"year":[2011,2011],"source_code":["1","2"],
        "jobs_total":[100.,300.],"jobs_primary":[10.,90.],"jobs_secondary":[20.,np.nan],
        "jobs_tertiary":[70.,180.],"establishments_total":[10.,20.]})
    out=map_counts(f,{"1":"0003","2":"0003"}).iloc[0]
    assert out.jobs_total==400
    assert out.econ_share_primary==.25
    assert pd.isna(out.econ_share_secondary)
    assert out.available_from_proxy==pd.Timestamp("2013-01-01")
