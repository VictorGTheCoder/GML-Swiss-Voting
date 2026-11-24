import numpy as np
import pandas as pd

from scripts.modeling.income_v109 import MEANS, NONSUM, aggregate_group, name_code_match
from scripts.modeling.text_v108 import cues, pick_pages, title_match


def test_title_match_and_ambiguous_page():
    title="Initiative pour des logements abordables"
    page={"page_number":4,"text":"En bref\n"+title+"\n"+"Explications du projet. "*15}
    assert title_match(title,page["text"])==1.
    assert "a" in pick_pages([page],{"a":[title]})
    assert not pick_pages([page],{"a":[title],"b":[title]})
    page["page_number"]=1
    assert not pick_pages([page],{"a":[title]})


def test_cues_are_literal_not_inferred():
    assert cues("Suppression de l'impôt")["abolish"]==1
    assert cues("Modification de la loi")["ban"]==0


def test_income_merger_weighted_means_not_medians():
    a=pd.DataFrame({"stpf":[100.,300.],**{c:[10.,30.] for c in MEANS},**{c:[.1,.2] for c in NONSUM}})
    r=aggregate_group(a,2)
    assert r["tax_units"]==400
    assert r["tax_mean_steink"]==25.
    assert np.isnan(r["tax_median_steinka"])
    assert aggregate_group(a,3) is None
    assert aggregate_group(a.iloc[:1],1)["tax_median_steinka"]==.1


def test_2012_name_encoding_correction_is_exact_and_year_limited():
    assert name_code_match(2012,"Tr|llikon","Trüllikon")== (True,True)
    assert name_code_match(2011,"Tr|llikon","Trüllikon")== (False,False)
    assert name_code_match(2012,"Tr|llikon","Truttikon")== (False,False)
    assert name_code_match(2012,"Trüllikon","Trüllikon")== (True,False)
