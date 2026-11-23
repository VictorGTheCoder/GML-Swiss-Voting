"""Auditable, target-blind lexical direction proxies for the meaning of YES.

These are conservative *title* features, not reviewed policy-effect annotations.
No vote results, party recommendations, brochure matches or model scores are
read.  An uninformative title, a negated action or conflicting directions leaves
the affected axis unknown (NaN), never neutral by default.  In particular a law
merely named "protection de l'environnement" is not assumed to strengthen it.

The source snapshot is retrospective.  Official titles are pre-vote concepts,
but this module does not manufacture historical publication evidence: strict
as-of admission remains the caller's responsibility.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
import unicodedata

import numpy as np
import pandas as pd

from scripts.common.vote_keys import ofs_keys


VERSION = "title_direction_v2.1"
SOURCE_URL = "https://swissvotes.ch/page/dataset"
AXES = {
    "environmental_protection": "+1: stated strengthening of environmental protection; -1: weakening",
    "tax_burden": "+1: increase/introduce a tax or remove a tax preference; -1: decrease/remove tax",
    "social_public_support": "+1: expand social benefits or their public financing; -1: reduce",
    "immigration_openness": "+1: facilitate residence/naturalisation; -1: restrict immigration/residence",
    "international_cooperation": "+1: join/approve an international agreement; -1: withdraw",
    "military_commitment": "+1: expand military resources/obligations; -1: reduce",
    "civil_equality": "+1: extend equal civil rights/protection; -1: remove",
    "regulatory_restriction": "+1: introduce an explicit prohibition; -1: abolish an explicit prohibition",
}
NUMERIC_FEATURES = tuple(
    feature
    for axis in AXES
    for feature in (f"direction__{axis}", f"direction__{axis}__known")
)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    axis: str
    sign: int
    pattern: str
    interpretation: str = "explicit_action"
    excludes: tuple[str, ...] = ()


# Short grammatical links prevent actions from being attached to a distant
# topic in the same title.  There is deliberately no unrestricted .* bridge.
LINK = r"(?:(?:de|du|des|d'|la|le|les|l'|un|une|nouveau|nouvelle|nouveaux|nouvelles)\s*){0,5}"
TAX = r"(?:impots?|taxes?|tva|redevances?)\b"
SOCIAL = r"(?:rentes?|prestations sociales|allocations|avs|retraites?)\b"
ENV = r"(?:protection (?:de |du |des |de l'|de la )?(?:environnement|climat|nature|paysage|biodiversite)|normes environnementales)\b"
RULES = (
    Rule("environment_emissions_reduction", "environmental_protection", 1,
         rf"\b(?:reduction|reduire|diminution|limitation) {LINK}(?:emissions|gaz a effet de serre)\b"),
    Rule("environment_protection_strengthen", "environmental_protection", 1,
         rf"\b(?:renforcement|renforcer|amelioration|accroissement) {LINK}{ENV}"),
    Rule("environment_protection_weaken", "environmental_protection", -1,
         rf"\b(?:abolition|abrogation|suppression|reduction|affaiblissement|assouplissement) {LINK}{ENV}"),
    Rule("environment_climate_objectives", "environmental_protection", 1,
         r"\bobjectifs en matiere de protection du climat\b", "stated_goal"),
    Rule("environment_responsible_economy", "environmental_protection", 1,
         r"\bpour une economie (?:durable|responsable respectant les limites planetaires)\b", "stated_goal"),
    Rule("environment_protect_people_and_environment", "environmental_protection", 1,
         r"\bpour proteger l'etre humain et l'environnement\b", "stated_goal"),
    Rule("environment_pesticide_removal", "environmental_protection", 1,
         r"\b(?:interdiction des pesticides|suisse libre de pesticides de synthese)\b"),
    Rule("environment_renewable_supply", "environmental_protection", 1,
         r"\bapprovisionnement en electricite sur reposant sur des energies renouvelables\b", "stated_goal"),
    Rule("tax_increase", "tax_burden", 1,
         rf"\b(?:augmentation|hausse|relevement|introduction|instauration) {LINK}{TAX}"),
    Rule("tax_decrease", "tax_burden", -1,
         rf"\b(?:abolition|abrogation|suppression|reduction|baisse|allegement|alleger|reduire) {LINK}{TAX}"),
    Rule("tax_inheritances", "tax_burden", 1, r"\bimposer les successions\b"),
    Rule("tax_capital", "tax_burden", 1, r"\bimposer (?:equitablement )?le capital\b"),
    Rule("tax_new_exemption", "tax_burden", -1,
         r"\b(?:allocations|revenus)\b[^,;:–—]{0,65}\bexonere(?:e|es|s)? de l'impot\b"),
    Rule("tax_deductions_expand", "tax_burden", -1,
         rf"\b(?:augmentation|relevement|introduction|extension) {LINK}deductions? fiscales?\b"),
    Rule("tax_preferences_remove", "tax_burden", 1,
         rf"\b(?:abolition|abrogation|suppression|reduction) {LINK}(?:forfaits fiscaux|exonerations fiscales|deductions fiscales)\b"),
    Rule("tax_explicit_maintain", "tax_burden", 0, rf"\bmaintien {LINK}(?:taux {LINK})?{TAX}"),
    Rule("social_expand", "social_public_support", 1,
         rf"\b(?:augmentation|hausse|relevement|amelioration|renforcement) {LINK}{SOCIAL}"),
    Rule("social_reduce", "social_public_support", -1,
         rf"\b(?:reduction|baisse|suppression|abolition|abrogation) {LINK}{SOCIAL}"),
    Rule("social_basic_income", "social_public_support", 1,
         r"\b(?:pour un|introduction d'un|instauration d'un) revenu de base inconditionnel\b"),
    Rule("social_additional_avs_pension", "social_public_support", 1,
         r"\b(?:pour une|introduction d'une) 13e rente avs\b"),
    Rule("social_additional_avs_financing", "social_public_support", 1,
         r"\bfinancement additionnel de l'avs\b"),
    Rule("social_remove_insurance_coverage", "social_public_support", -1,
         r"\bradiant les couts de l'interruption de grossesse de l'assurance de base\b"),
    Rule("migration_naturalisation_facilitate", "immigration_openness", 1,
         r"\bnaturalisation facilitee\b"),
    Rule("migration_restrict", "immigration_openness", -1,
         rf"\b(?:limitation|reduction|restriction) {LINK}immigration\b"),
    Rule("migration_against_mass_immigration", "immigration_openness", -1,
         r"\bcontre l'immigration de masse\b"),
    Rule("migration_moderate_limitation", "immigration_openness", -1,
         r"\bpour une immigration moderee\s*\(initiative de limitation\)"),
    Rule("migration_remove_free_movement", "immigration_openness", -1,
         rf"\b(?:abolition|abrogation|suppression) {LINK}libre circulation des personnes\b"),
    Rule("migration_expand_free_movement", "immigration_openness", 1,
         rf"\b(?:introduction|extension|elargissement) {LINK}libre circulation des personnes\b"),
    Rule("migration_criminal_deportation", "immigration_openness", -1,
         r"\bpour le renvoi (?:effectif )?des etrangers criminels\b"),
    Rule("international_agreement_approve", "international_cooperation", 1,
         r"\b(?:approbation|ratification) (?:et mise en oeuvre )?(?:de |du |des |d'|la |le |les |l')*(?:accord|echange de notes|traite|convention)\b"),
    Rule("international_join", "international_cooperation", 1,
         r"\badhesion (?:de la suisse )?a (?:l'|la |le )?(?:onu|union europeenne|espace economique europeen)\b"),
    Rule("international_leave", "international_cooperation", -1,
         r"\b(?:denonciation|retrait|sortie) (?:de |du |des |d'|la |le |les |l')*(?:accord|traite|convention|union europeenne)\b"),
    Rule("military_remove_compulsory_service", "military_commitment", -1,
         rf"\b(?:abrogation|abolition|suppression) {LINK}service militaire obligatoire\b"),
    Rule("military_aircraft_purchase", "military_commitment", 1,
         r"\b(?:acquisition|achat) (?:de |d'|l'|nouveaux |nouvel )*(?:avion|avions) de combat\b"),
    Rule("military_budget_expand", "military_commitment", 1,
         rf"\b(?:augmentation|hausse|relevement) {LINK}(?:budget militaire|depenses militaires)\b"),
    Rule("military_budget_reduce", "military_commitment", -1,
         rf"\b(?:reduction|baisse|suppression) {LINK}(?:budget militaire|depenses militaires)\b"),
    Rule("civil_marriage_equality", "civil_equality", 1, r"\bmariage pour tous\b", "stated_goal"),
    Rule("civil_discrimination_prohibit", "civil_equality", 1,
         r"\binterdiction de la discrimination\b"),
    Rule("civil_voting_rights_expand", "civil_equality", 1,
         rf"\b(?:introduction|extension|elargissement) {LINK}droit de vote\b"),
    Rule("civil_voting_rights_reduce", "civil_equality", -1,
         rf"\b(?:suppression|abrogation|reduction) {LINK}droit de vote\b"),
    Rule("regulation_explicit_prohibition", "regulatory_restriction", 1,
         r"\binterdiction (?:de |des |du |d')", excludes=(r"\b(?:suppression|abolition|abrogation|levee)\b",)),
    Rule("regulation_remove_prohibition", "regulatory_restriction", -1,
         rf"\b(?:suppression|abolition|abrogation|levee) {LINK}interdiction\b"),
)


def _title_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    # Replace curly apostrophes before ASCII folding, which would drop them.
    value = str(value).replace("’", "'").replace("‘", "'").replace("œ", "oe")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", value).strip()


def extract_title_directions(titles: dict[str, str]) -> tuple[dict[str, float], dict]:
    """Extract deterministic directions using only allowlisted French titles.

    ``known=1`` means a lexical rule fired without conflict, not external review.
    0 direction is reserved for an explicit maintenance rule.  A missing match
    remains NaN, including when the title only supplies a policy topic.
    """
    matches = {axis: [] for axis in AXES}
    blocked = {axis: [] for axis in AXES}
    title_evidence = {}
    for field in ("titel_off_f", "titre_off_f", "titel_kurz_f"):
        if field not in titles:
            continue
        original = titles[field]
        text = _title_text(original)
        if not text:
            continue
        title_evidence[field] = str(original)
        # An initiative named inside a counterproposal is not the ballot object.
        text = re.split(r"\(?\bcontre[- ]projet\b", text, maxsplit=1)[0]
        for rule in RULES:
            if any(re.search(pattern, text) for pattern in rule.excludes):
                continue
            for match in re.finditer(rule.pattern, text):
                evidence = {
                    "rule_id": rule.rule_id, "source_column": field,
                    "matched_text_normalized": match.group(), "sign": rule.sign,
                    "interpretation": rule.interpretation,
                }
                prefix = text[max(0, match.start() - 50):match.start()]
                # Do not silently invert a negated proposal: blocking a change
                # may preserve the status quo rather than create its opposite.
                negated = re.search(
                    r"\b(?:non a |contre |pas de |sans |refus (?:de |d')|"
                    r"(?:abrogation|abolition|suppression|interdiction) (?:de |du |des |d'))"
                    r"(?:l'|la |le |les |une? )?$", prefix,
                )
                # Scope across coordination cannot safely be recovered from
                # these lexical rules: "Non a X et a Y" abstains for both.
                negated = negated or re.search(r"\bnon a\b.*\bet\b", text)
                # "Pas de suppression" and "contre l'interdiction" are
                # deliberately abstentions, not signed policy assertions.
                if negated:
                    evidence["blocked_reason"] = "negated_action"
                    blocked[rule.axis].append(evidence)
                else:
                    matches[rule.axis].append(evidence)
    values, audit = {}, {}
    for axis in AXES:
        signs = {item["sign"] for item in matches[axis]}
        known = len(signs) == 1 and not blocked[axis]
        values[f"direction__{axis}"] = float(next(iter(signs))) if known else np.nan
        values[f"direction__{axis}__known"] = float(known)
        status = ("ambiguous_negation" if blocked[axis] else
                  "ambiguous_conflicting_directions" if len(signs) > 1 else
                  "lexical_proxy" if known else "no_explicit_direction")
        audit[axis] = {"status": status, "matches": matches[axis], "blocked_matches": blocked[axis]}
    return values, {"titles": title_evidence, "axes": audit}


def add_direction_features(table: pd.DataFrame, swiss: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Enrich panel rows from exact Swissvotes identifiers without reading y.

    ``table`` needs ``vote_id`` or ``vote_key``.  ``swiss`` needs ``vote_key``
    and one French title column.  Where dates exist on both sides, mismatches
    are rejected per row.  Duplicate metadata identifiers are an error.
    No source title is inferred from brochure text or from result columns.
    """
    table_key = "vote_id" if "vote_id" in table else "vote_key"
    title_fields = [name for name in ("titel_off_f", "titre_off_f", "titel_kurz_f") if name in swiss]
    if table_key not in table or "vote_key" not in swiss or not title_fields:
        raise ValueError("Direction features require exact vote keys and French Swissvotes titles")
    collision = set(NUMERIC_FEATURES) & set(table)
    if collision:
        raise ValueError(f"Direction feature columns already exist: {sorted(collision)}")
    table_keys = ofs_keys(table[table_key])
    source_keys = ofs_keys(swiss["vote_key"])
    if source_keys.duplicated().any():
        raise ValueError("Duplicate Swissvotes vote_key in direction metadata")
    table_date = next((name for name in ("voting_date", "vote_date") if name in table), None)
    source_date = next((name for name in ("vote_date", "voting_date") if name in swiss), None)
    allowed = ["vote_key"] + title_fields + ([source_date] if source_date else [])
    # This projection is also the hash input: outcomes cannot affect the result
    # or the manifest, even when the caller passed a full source DataFrame.
    source = swiss.loc[:, allowed].copy()
    source["vote_key"] = source_keys
    source = source.set_index("vote_key")
    outputs, records = {}, {}
    for key in sorted(set(table_keys)):
        if key not in source.index:
            outputs[key] = {name: np.nan if not name.endswith("__known") else 0.0 for name in NUMERIC_FEATURES}
            records[key] = {"join_status": "missing_exact_key", "titles": {}, "axes": {}}
            continue
        row = source.loc[key]
        outputs[key], audit = extract_title_directions({field: row[field] for field in title_fields})
        records[key] = {"join_status": "exact_key", **audit}
    enriched = table.copy()
    for name in NUMERIC_FEATURES:
        enriched[name] = table_keys.map({key: values[name] for key, values in outputs.items()}).to_numpy(dtype=float)
    date_mismatch = np.zeros(len(table), dtype=bool)
    if table_date and source_date:
        dates = pd.to_datetime(table[table_date], errors="coerce", utc=True).dt.normalize()
        source_dates = pd.to_datetime(source[source_date], errors="coerce", utc=True).dt.normalize()
        expected = table_keys.map(source_dates)
        date_mismatch = (dates.isna() | expected.isna() | dates.ne(expected)).to_numpy()
        for name in NUMERIC_FEATURES:
            enriched.loc[date_mismatch, name] = 0.0 if name.endswith("__known") else np.nan
        for key in set(table_keys.iloc[np.flatnonzero(date_mismatch)]):
            records[key]["date_check"] = "missing_or_mismatched_date_for_some_rows"
    rules_json = json.dumps([asdict(rule) for rule in RULES], sort_keys=True, ensure_ascii=False)
    manifest = {
        "version": VERSION, "numeric_features": list(NUMERIC_FEATURES),
        "source_url": SOURCE_URL, "source_columns_read": allowed,
        "source_titles_sha256": hashlib.sha256(source.sort_index().to_json(orient="split", date_format="iso").encode()).hexdigest(),
        "rules_sha256": hashlib.sha256(rules_json.encode()).hexdigest(),
        "axes": AXES, "labels": {"-1": "decrease", "0": "explicit_maintenance", "1": "increase", "NaN": "unknown_or_ambiguous"},
        "target_blind": True, "outcome_columns_read": [], "party_recommendations_read": False,
        "brochures_read": False, "human_reviewed": False,
        "quality_status": "experimental_lexical_proxy_not_validated_policy_effect",
        "availability_status": "retrospective_titles_historical_publication_unverified",
        "date_check": "checked" if table_date and source_date else "unverified_missing_date_column",
        "date_rejected_rows": int(date_mismatch.sum()),
        "coverage": {axis: {
            "known_rows": int(enriched[f"direction__{axis}__known"].sum()),
            "total_rows": len(enriched),
            "known_objects": int(pd.DataFrame({
                "vote_key": table_keys.to_numpy(),
                "known": enriched[f"direction__{axis}__known"].to_numpy(),
            }).groupby("vote_key")["known"].max().sum()),
        } for axis in AXES},
        "object_evidence": records,
        "limitations": [
            "Lexical title proxies, not manually reviewed legal effects or guaranteed causal impacts.",
            "No match means unknown, never neutral; negations and mixed directions abstain.",
            "Short Swissvotes titles are editorial metadata; historical publication dates are not certified.",
            "Unresolved brochure-to-object links are not used.",
        ],
    }
    return enriched, manifest
