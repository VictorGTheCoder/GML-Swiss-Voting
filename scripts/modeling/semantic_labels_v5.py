"""Controlled broad mechanism families from source-evidenced historical YES effects.

Separate substantive policy topics from mechanisms and target groups. Historical
2015-and-earlier annotations and V4 2016+ pilot annotations are *first-pass*,
not independently validated and not certified to historic publication editions.
No outcome-derived attribute is permitted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from scripts.common.config import ROOT

HISTORICAL = ROOT / "data/annotations/yes_effects_historical_v5.json"
V4 = ROOT / "data/annotations/yes_effects_v4.json"

FORBIDDEN = frozenset({
    "yes_share", "yes_count", "no_count", "prediction", "popular_result",
    "municipal_result", "cantonal_result", "national_result",
    "observed_mean", "volkja", "volknein", "volkja-proz",
})
CODE = re.compile(r"^[a-z][a-z0-9_]*$")
DIRECTIONS = {
    "increase", "decrease", "introduce", "remove", "extend", "restrict",
    "reallocate", "preserve", "mixed",
}
BASE_DOMAINS = {
    "international": "foreign",
    "civil_rights": "institutions",
    "agriculture": "agriculture",
    "labour": "employment",
    "education": "education",
    "pensions": "welfare",
    "migration": "migration",
    "family": "welfare",
    "health": "health",
    "defense": "security",
    "taxation": "taxation",
    "institutions": "institutions",
    "justice": "security",
    "environment": "environment",
    "commerce": "business",
    "security": "security",
    "social_insurance": "welfare",
    "finance": "business",
    "housing": "housing",
    "animals": "agriculture",
    "transport": "transport",
    "energy": "environment",
    "media": "institutions",
}
V4_DOMAINS = {
    "family": "welfare", "taxation": "taxation", "immigration": "migration",
    "finance": "business", "transport": "transport", "agriculture": "agriculture",
    "pensions": "welfare", "corporate_tax": "taxation", "public_safety": "security",
    "housing": "housing", "civil_rights": "institutions", "wildlife": "agriculture",
    "social_policy": "welfare", "military": "security", "environment": "environment",
    "public_health": "health", "climate": "environment", "animal_welfare": "agriculture",
    "healthcare": "health", "energy": "environment", "housing_tax": "taxation",
    "digital_government": "institutions",
}
HIST_FAMILIES = {
    "international_agreement": "treaty",
    "legal_rights": "rights",
    "labour_rule": "employment_rule",
    "environment_regulation": "environment_rule",
    "institutional_rule": "institutional",
    "public_financing": "public_finance",
    "immigration_rule": "migration_rule",
    "social_benefit": "benefit",
    "insurance_rule": "insurance",
    "social_insurance_rule": "insurance",
    "prohibition": "legal_restriction",
    "tax_rule": "taxation",
    "political_rule": "democratic_rule",
    "health_rule": "health_rule",
    "market_rule": "business_rule",
    "planning_rule": "planning_rule",
    "security_rule": "security_rule",
    "identity_rule": "security_rule",
    "corporate_rule": "business_rule",
    "military_rule": "defense_rule",
}
V4_FAMILIES = {
    "constitutional_rule": "institutional", "deportation_rule": "migration_rule",
    "prohibition": "legal_restriction", "infrastructure_investment": "public_finance",
    "vat_tax": "taxation", "retirement_rule": "insurance",
    "tax_reform": "taxation", "public_financing": "public_finance",
    "firearms_registration": "security_rule", "construction_quota": "planning_rule",
    "criminal_protection": "rights", "treaty_termination": "treaty",
    "hunting_regulation": "environment_rule", "tax_allowance": "taxation",
    "paid_leave": "employment_rule", "defence_procurement": "public_finance",
    "subsidy_conditionality": "public_finance",
    "emergency_legal_framework": "health_rule", "carbon_pricing": "taxation",
    "police_powers": "security_rule", "husbandry_standard": "environment_rule",
    "tax_exemption": "taxation", "minimum_tax": "taxation",
    "public_subsidy": "public_finance", "public_benefit": "benefit",
    "premium_subsidy": "benefit", "cost_growth_control": "health_rule",
    "renewable_energy_rules": "environment_rule",
    "nature_protection": "environment_rule", "pension_reform": "insurance",
    "road_expansion": "public_finance", "tenancy_rule": "rights",
    "financing_rule": "public_finance", "cantonal_tax_option": "taxation",
    "digital_identity": "rights",
}

# Broad, objectively identifiable direct recipients, not inferred electorate types.
TARGET_MAP = {
    "households": "households", "families": "households", "married_couples": "households",
    "families_with_children": "households", "new_fathers": "households",
    "workers": "workers", "employees": "workers", "cross_border_workers": "workers",
    "employers": "employers", "businesses": "employers", "companies": "employers",
    "corporations": "employers", "multinational_corporations": "employers",
    "pensioners": "pensioners", "women_near_retirement": "pensioners",
    "future_pensioners": "pensioners", "retired_homeowners": "pensioners",
    "insured": "insured", "low_income_insured": "insured", "health_insurers": "insured",
    "patients": "patients", "healthcare_providers": "patients",
    "farmers": "agriculture", "agricultural_sector": "agriculture",
    "livestock_farmers": "agriculture", "food_importers": "business",
    "consumers": "consumers", "taxpayers": "consumers", "restaurants": "business",
    "retailers": "business", "arms_industry": "business",
    "industry": "business", "financial_intermediaries": "business",
    "pension_funds": "business", "renewable_industry": "business",
    "electricity_producers": "business", "bond_investors": "business",
    "bond_issuers": "business", "online_service_providers": "business",
    "housing_cooperatives": "housing", "tenants": "housing", "landlords": "housing",
    "homeowners": "housing", "secondary_homeowners": "housing",
    "property_owners": "housing", "building_owners": "housing",
    "landowners": "housing", "voters": "voters", "canton": "government",
    "cantons": "government", "public_authorities": "government",
    "health_authorities": "government", "local_communities": "government",
    "cantonal_wildlife_authorities": "government", "central_bank": "government",
    "government": "government", "foreign_cooperation": "foreign",
    "migrants": "migrants", "asylum_seekers": "migrants",
    "foreign_residents_convicted": "migrants",
    "armed_forces": "security", "military": "security", "police": "security",
    "gun_owners": "security", "arms_dealers": "security",
    "convicted_persons": "security", "persons_under_prevention_measures": "security",
    "children": "children", "students": "students",
    "religious_communities": "civil_rights",
    "sexual_minorities": "civil_rights", "public_service_providers": "government",
    "environmental_organizations": "environment",
    "travellers": "travellers", "road_users": "travellers",
    "rail_users": "travellers", "aviation": "travellers",
    "general": "general", "residents": "general",
    "researchers": "researchers", "pension_system": "government",
    "emitters": "business", "fuel_users": "consumers",
}
# Abstract types not present in this table stay 'other' explicitly.


def _tag(value):
    if not isinstance(value, str) or not CODE.fullmatch(value):
        raise ValueError(f"Uncontrolled or blank tag: {value!r}")
    return value


def validate_history(document):
    if document.get("version") != "historic-yes-effect-v5-1":
        raise ValueError("Wrong annotation dataset edition")
    sources, votes = document.get("sources"), document.get("votes")
    if not isinstance(sources, dict) or not isinstance(votes, list):
        raise TypeError("History requires sources and votes")
    seen = set()
    for key, source in sources.items():
        if not re.fullmatch(r"\d{4}-\d{2}", key):
            raise ValueError(f"Invalid source date group {key}")
        if source.get("kind") not in ("pdf", "html"):
            raise ValueError("Unknown source type")
        if not source.get("url", "").startswith("https://www.bk.admin.ch/"):
            raise ValueError("Only documented Federal Chancellery primary sources allowed")
        if source.get("published_at_verified") is not None:
            raise ValueError("Do not assert unsupported historical edition availability")
    for vote in votes:
        if set(vote) & FORBIDDEN:
            raise ValueError("Outcome information in annotation")
        vote_id, date, src = vote.get("vote_id"), vote.get("vote_date"), vote.get("source")
        if not str(vote_id).isdigit() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
            raise ValueError("Invalid ID/date")
        if vote_id in seen:
            raise ValueError(f"Duplicate vote: {vote_id}")
        seen.add(vote_id)
        if pd.Timestamp(date).year > 2015 or str(date)[:7] != src or src not in sources:
            raise ValueError(f"Historical source/date mismatch {vote_id}")
        if vote.get("review_status") != "first_pass_not_independently_reviewed":
            raise ValueError("Do not silently promote the review status")
        if not isinstance(vote.get("effects"), list) or not vote["effects"]:
            raise ValueError("Missing evidence-backed effects")
        for e in vote["effects"]:
            if set(e) & FORBIDDEN:
                raise ValueError("Outcome field in effect")
            for key in ("domain", "family", "direction", "target"):
                _tag(e.get(key))
            if e["domain"] not in BASE_DOMAINS or e["family"] not in HIST_FAMILIES:
                raise ValueError("Unmapped domain/mechanism")
            if e["direction"] not in DIRECTIONS:
                raise ValueError("Unknown direction")
            if e.get("evidence_confidence") not in ("high", "medium"):
                raise ValueError("Confidence required")
            if not isinstance(e.get("evidence_note"), str) or len(e["evidence_note"].strip()) < 20:
                raise ValueError("Specific source-based explanation required")
            page = e.get("source_section_page")
            if page is not None and (not isinstance(page, int) or page < 1):
                raise ValueError("PDF section page must be positive")
    return document


def load_history(path=HISTORICAL):
    return validate_history(json.loads(Path(path).read_text(encoding="utf-8")))


def _coarse_effect_tags(domain, family, direction, targets):
    tags = {f"domain_{domain}", f"mechanism_{family}", f"direction_{direction}"}
    for target in targets:
        tags.add("target_" + TARGET_MAP.get(target, "other"))
    return tags


def coarse_tags_historical(vote):
    """Only sufficiently supported first-pass entries; medium uncertain => unknown."""
    tags = set()
    for effect in vote["effects"]:
        if effect["evidence_confidence"] != "high":
            continue
        tags |= _coarse_effect_tags(
            BASE_DOMAINS[effect["domain"]], HIST_FAMILIES[effect["family"]],
            effect["direction"], [effect["target"]],
        )
    return tags


def coarse_tags_v4(vote):
    tags = set()
    for e in vote["effects"]:
        if e["domain"] not in V4_DOMAINS or e["instrument"] not in V4_FAMILIES:
            raise ValueError(f"Unmapped V4 effect for {vote['vote_id']}")
        direction = e["direction"]
        if direction not in DIRECTIONS:
            raise ValueError(f"V4 effect direction missing from V5: {direction}")
        tags |= _coarse_effect_tags(
            V4_DOMAINS[e["domain"]], V4_FAMILIES[e["instrument"]],
            direction, e["targets"],
        )
    return tags


def build_coarse_table(objects, history, current):
    """Align exact unique vote ID/date, never read municipal targets or results."""
    validate_history(history)
    if not {"vote_id", "vote_date"}.issubset(objects) or objects.vote_id.isna().any():
        raise ValueError("Missing object/date identity")
    ids = objects.vote_id.astype(str)
    dates = pd.to_datetime(objects.vote_date, errors="coerce")
    if ids.duplicated().any() or dates.isna().any():
        raise ValueError("Unusable input identity")
    historical = {v["vote_id"]: v for v in history["votes"]}
    new = {v["vote_id"]: v for v in current["votes"]}
    if set(historical) & set(new):
        raise ValueError("Historical and V4 annotations overlap")
    if not (set(historical) | set(new)) <= set(ids):
        raise ValueError("Annotations contain unknown vote identifiers")
    flags, values, origins = [], [], []
    for key, date in zip(ids, dates):
        record = historical.get(key)
        if record:
            if date.normalize() != pd.Timestamp(record["vote_date"]):
                raise ValueError(f"Historical vote/date mismatch: {key}")
            tags = coarse_tags_historical(record)
            origin = "history" if tags else "unreviewed"
        else:
            record = new.get(key)
            if record and date.normalize() != pd.Timestamp(record["vote_date"]):
                raise ValueError(f"V4 vote/date mismatch: {key}")
            tags = coarse_tags_v4(record) if record else set()
            origin = "v4" if record else "unannotated"
        flags.append(int(bool(tags)))
        values.append("|".join(sorted(tags)))
        origins.append(origin)
    result = objects[["vote_id"]].copy()
    result["coarse_tags"] = values
    result["coarse_documented"] = flags
    result["annotation_origin"] = origins
    return result


def vocabulary(train, min_count=3):
    """Learn frequent tags on TRAIN objects only, with no outcome information."""
    if min_count < 1:
        raise ValueError("min_count must be >= 1")
    counts = {}
    for value in train.coarse_tags:
        for token in set(value.split("|")) - {""}:
            counts[token] = counts.get(token, 0) + 1
    return sorted(token for token, count in counts.items() if count >= min_count)


def encode_tags(rows, vocab):
    # On unknown objects all effect indicators are 0, but documented flag is separate.
    known = rows.coarse_tags.map(lambda value: set(value.split("|")) - {""})
    return pd.DataFrame({
        "coarse_" + tag: known.map(lambda x, t=tag: int(t in x)).astype("uint8")
        for tag in vocab
    }, index=rows.index)
