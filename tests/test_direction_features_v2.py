"""Direction semantics, abstention and invariance to forbidden outcome columns."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling.direction_features_v2 import (
    NUMERIC_FEATURES,
    add_direction_features,
    extract_title_directions,
)


def directions(title, short=None):
    fields = {"titel_off_f": title}
    if short is not None:
        fields["titel_kurz_f"] = short
    return extract_title_directions(fields)


@pytest.mark.parametrize("title,axis,sign", [
    ("Loi fédérale sur la réduction des émissions de gaz à effet de serre", "environmental_protection", 1),
    ("Initiative pour la suppression de la protection de l’environnement", "environmental_protection", -1),
    ("Arrêté sur le relèvement de la TVA", "tax_burden", 1),
    ("Oui à la suppression des redevances radio et télévision", "tax_burden", -1),
    ("Relèvement des déductions fiscales pour enfants", "tax_burden", -1),
    ("Abolition des forfaits fiscaux", "tax_burden", 1),
    ("Maintien du taux de la TVA", "tax_burden", 0),
    ("Initiative pour une 13e rente AVS", "social_public_support", 1),
    ("Réduction des prestations sociales", "social_public_support", -1),
    ("Naturalisation facilitée des étrangers de la troisième génération", "immigration_openness", 1),
    ("Initiative populaire «Contre l’immigration de masse»", "immigration_openness", -1),
    ("Approbation de l’Accord de partenariat économique", "international_cooperation", 1),
    ("Oui à l’abrogation du service militaire obligatoire", "military_commitment", -1),
    ("Acquisition de nouveaux avions de combat", "military_commitment", 1),
    ("Modification du code civil suisse (Mariage pour tous)", "civil_equality", 1),
    ("Oui à l’interdiction de se dissimuler le visage", "regulatory_restriction", 1),
    ("Suppression de l’interdiction de travailler", "regulatory_restriction", -1),
])
def test_explicit_actions_have_direction(title, axis, sign):
    values, evidence = directions(title)
    assert values[f"direction__{axis}"] == sign
    assert values[f"direction__{axis}__known"] == 1
    assert evidence["axes"][axis]["status"] == "lexical_proxy"
    assert evidence["axes"][axis]["matches"]


@pytest.mark.parametrize("title", [
    "Loi fédérale sur la protection de l’environnement",
    "Modification de la loi sur la chasse et la protection des mammifères",
    "Réforme de la prévoyance professionnelle",
    "Loi sur l’énergie",
    "Loi sur l’impôt anticipé (Renforcement du marché des capitaux)",
])
def test_topic_alone_never_becomes_a_direction(title):
    values, _ = directions(title)
    assert all(np.isnan(values[name]) for name in NUMERIC_FEATURES if not name.endswith("__known"))


@pytest.mark.parametrize("title", [
    "Initiative «Non à la hausse des impôts»",
    "Initiative contre la suppression des taxes",
    "Initiative «Pas de réduction des impôts»",
])
def test_negation_abstains_instead_of_inventing_a_change(title):
    values, evidence = directions(title)
    assert np.isnan(values["direction__tax_burden"])
    assert evidence["axes"]["tax_burden"]["status"] == "ambiguous_negation"


@pytest.mark.parametrize("title,axis", [
    ("Abrogation de la réduction des émissions de gaz à effet de serre", "environmental_protection"),
    ("Interdiction de l’augmentation des impôts", "tax_burden"),
    ("Abrogation du mariage pour tous", "civil_equality"),
    ("Non à la hausse des impôts et à la réduction des prestations sociales", "social_public_support"),
])
def test_nested_actions_and_coordinated_negations_remain_unresolved(title, axis):
    values, evidence = directions(title)
    assert np.isnan(values[f"direction__{axis}"])
    assert evidence["axes"][axis]["status"] == "ambiguous_negation"


def test_mixed_directions_and_disagreeing_titles_stay_unknown():
    values, evidence = directions("Alléger les impôts sur les salaires, imposer équitablement le capital")
    assert np.isnan(values["direction__tax_burden"])
    assert evidence["axes"]["tax_burden"]["status"] == "ambiguous_conflicting_directions"
    values, _ = directions("Augmentation des impôts", "Réduction des impôts")
    assert np.isnan(values["direction__tax_burden"])


def test_counterproposal_does_not_inherit_quoted_initiative_direction():
    values, _ = directions("Modification de la loi (contre-projet indirect à l’initiative «Pour un revenu de base inconditionnel»)")
    assert np.isnan(values["direction__social_public_support"])


def source():
    return pd.DataFrame({
        "vote_key": ["10", "11"], "vote_date": ["2020-03-01", "2020-03-01"],
        "titel_off_f": ["Augmentation des impôts", "Suppression des impôts"],
        "volkja": [1, 99], "p-sps": [1, 2], "brochure": ["unexpected", "unexpected"],
    })


def panel():
    return pd.DataFrame({
        "vote_id": ["11", "10", "10", "12"], "voting_date": ["2020-03-01"] * 4,
        "target_share": [.1, .9, .2, .8], "municipality_id": ["a", "a", "b", "a"],
    }, index=[9, 2, 2, 7])


def test_panel_join_preserves_index_order_rows_and_does_not_read_targets():
    table, swiss = panel(), source()
    original_table, original_swiss = table.copy(deep=True), swiss.copy(deep=True)
    result, manifest = add_direction_features(table, swiss)
    assert result.index.tolist() == [9, 2, 2, 7]
    np.testing.assert_equal(result["direction__tax_burden"].to_numpy(), [-1., 1., 1., np.nan])
    pd.testing.assert_frame_equal(result[table.columns], table)
    pd.testing.assert_frame_equal(table, original_table)
    pd.testing.assert_frame_equal(swiss, original_swiss)
    swiss["volkja"], swiss["p-sps"], swiss["brochure"] = 12345, 999, "opposite"
    table["target_share"] = np.nan
    poisoned, poisoned_manifest = add_direction_features(table, swiss)
    pd.testing.assert_frame_equal(result[list(NUMERIC_FEATURES)], poisoned[list(NUMERIC_FEATURES)])
    assert manifest == poisoned_manifest
    assert manifest["outcome_columns_read"] == []
    assert not manifest["human_reviewed"]


def test_dates_and_exact_keys_are_required_for_admissible_match():
    table = panel()
    table.loc[table.vote_id.eq("10"), "voting_date"] = "2021-03-01"
    result, manifest = add_direction_features(table, source())
    assert result.loc[result.vote_id.eq("10"), "direction__tax_burden"].isna().all()
    assert manifest["date_rejected_rows"] == 3  # two mismatches and a missing source key
    assert manifest["object_evidence"]["12"]["join_status"] == "missing_exact_key"
    assert manifest["coverage"]["tax_burden"]["known_objects"] == 1


def test_duplicate_metadata_and_feature_overwrite_are_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        add_direction_features(panel(), pd.concat([source(), source().iloc[:1]]))
    enriched, _ = add_direction_features(panel(), source())
    with pytest.raises(ValueError, match="already exist"):
        add_direction_features(enriched, source())
