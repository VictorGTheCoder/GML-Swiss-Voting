"""Pre-vote semantic representation of Swiss federal ballot objects (V4 pilot).

A vote has ONE unordered set of most-specific Swissvotes topics, plus zero or
more separately reviewed legal changes implied by YES. Topic and effect are
different concepts: 'clean water' does not imply a general pesticide ban.

Only source-reviewed changes in the curated JSON are model inputs. Missing
annotations are unknown, not 'no change'. The current public brochure editions
have not all been historically authenticated: this is retrospective research.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

SOURCE_ID = "vote_id"
TAG_SEPARATOR = "|"
FORBIDDEN_KEYS = frozenset({
    "yes_share", "volkja", "volknein", "popular_result", "national_yes",
    "cantonal_result", "municipal_result", "observed_mean", "prediction",
})
TOPIC_FIELDS = ("extra_domain_tokens_1", "extra_domain_tokens_2", "extra_domain_tokens_3")
FACETS = ("domain", "instrument", "direction", "quantity", "targets")
ALLOWED_DIRECTIONS = frozenset({
    "increase", "decrease", "introduce", "remove", "restrict", "extend",
    "reallocate", "preserve", "mixed",
})
TAG_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
DOMAIN_TOKEN = re.compile(r"^(?:[1-9]|1[0-2])(?:\.[0-9]{1,2}){0,2}$")


def _tokens(value):
    if pd.isna(value) or str(value).strip() in ("", "."):
        return set()
    return {part.strip() for part in str(value).split(TAG_SEPARATOR) if part.strip()}


def _is_ancestor(parent, child):
    """Swissvotes levels: 4 -> 4.2 -> 4.24, *not* 4.2.4."""
    if parent == child or "." not in child:
        return False
    major, suffix = child.split(".")
    if "." not in parent:
        return parent == major
    p_major, p_suffix = parent.split(".")
    return (p_major == major and len(p_suffix) == 1
            and len(suffix) == 2 and suffix.startswith(p_suffix))


def canonical_topics(row):
    """One sorted minimal antichain of policy codes, independent of d1/d2/d3 slots."""
    candidates = set()
    for name in TOPIC_FIELDS:
        if name not in row:
            raise ValueError(f"Missing Swissvotes theme level {name}")
        for code in _tokens(row[name]):
            if not DOMAIN_TOKEN.fullmatch(code):
                raise ValueError(f"Invalid Swissvotes topic code {code!r}")
            candidates.add(code)
    leaves = {code for code in candidates
              if not any(_is_ancestor(code, other) for other in candidates)}
    return TAG_SEPARATOR.join(sorted(leaves, key=lambda s: tuple(int(v) for v in s.split("."))))


def build_topic_table(extras):
    """Derive canonical leaf themes from V3's source-derived unordered level sets."""
    required = {"vote_id", *TOPIC_FIELDS}
    if not required.issubset(extras) or extras.vote_id.isna().any() or extras.vote_id.duplicated().any():
        raise ValueError("One non-null unique vote_id and all three Swissvotes topic levels required")
    result = extras[["vote_id"]].copy()
    result["topic_leaves"] = extras.apply(canonical_topics, axis=1)
    return result


def topic_features(values, *, hierarchy=False):
    """Expand leaves into nodes only when hierarchy is requested.

    Include a parent once, irrespective of how many leaves descend from it.
    """
    nodes = set()
    for leaf in _tokens(values):
        if not DOMAIN_TOKEN.fullmatch(leaf):
            raise ValueError(f"Invalid topic {leaf!r}")
        if hierarchy:
            major, dot, suffix = leaf.partition(".")
            nodes.add(major)
            if dot:
                nodes.add(leaf)
                if len(suffix) == 2:
                    nodes.add(major + "." + suffix[0])
        else:
            nodes.add(leaf)
    return TAG_SEPARATOR.join(sorted(nodes, key=lambda s: tuple(int(v) for v in s.split("."))))


def _safe_tag(value):
    if not isinstance(value, str) or not TAG_TOKEN.fullmatch(value):
        raise ValueError(f"Invalid controlled semantic tag: {value!r}")
    return value


def validate_annotation_document(document):
    """Fail closed on ambiguous identities, postvote indicators or absent evidence."""
    if not isinstance(document, dict) or document.get("version") != "yes-effects-v4-pilot-1":
        raise ValueError("Unknown annotation schema version")
    sources = document.get("sources")
    rows = document.get("votes")
    if not isinstance(sources, dict) or not isinstance(rows, list):
        raise TypeError("Sources dictionary and votes list required")
    identities = set()
    for key, source in sources.items():
        if not isinstance(key, str) or not isinstance(source, dict):
            raise TypeError("Invalid brochure entry")
        if not str(source.get("url", "")).startswith("https://www.bk.admin.ch/"):
            raise ValueError("Official brochure URL required")
        if source.get("published_at") is not None:
            raise ValueError("Do not invent an archived publication timestamp")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(source.get("editorial_cutoff", ""))):
            raise ValueError("Printed editorial cutoff required")
    for row in rows:
        if not isinstance(row, dict) or set(row) & FORBIDDEN_KEYS:
            raise ValueError("Forbidden outcome-related annotation field")
        key = str(row.get("vote_id", ""))
        when = row.get("vote_date")
        source = sources.get(row.get("source"))
        if not key.isdigit() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(when)):
            raise ValueError("Invalid vote ID or date")
        if key in identities or source is None:
            raise ValueError("Duplicate vote or missing brochure")
        identities.add(key)
        if pd.Timestamp(source["editorial_cutoff"]) >= pd.Timestamp(when):
            raise ValueError("Brochure editorial cutoff cannot be on or after vote")
        if row.get("source_review") != "checked_against_prevote_booklet":
            raise ValueError("Only evidence-checked rows are admissible")
        if row.get("independent_review") not in ("pending", "approved"):
            raise ValueError("Independent review state must be explicit")
        if not isinstance(row.get("effects"), list) or not row["effects"]:
            raise ValueError("An evidenced vote needs one or more direct effects")
        for effect in row["effects"]:
            if not isinstance(effect, dict) or set(effect) & FORBIDDEN_KEYS:
                raise ValueError("Outcome field in effect")
            for field in ("domain", "instrument", "direction", "quantity"):
                _safe_tag(effect.get(field))
            if effect["direction"] not in ALLOWED_DIRECTIONS:
                raise ValueError("Unknown or ambiguous direction")
            if not isinstance(effect.get("targets"), list) or not effect["targets"]:
                raise ValueError("Explicitly affected population/sector is required")
            for target in effect["targets"]:
                _safe_tag(target)
            if not isinstance(effect.get("page"), int) or effect["page"] < 1:
                raise ValueError("Printed brochure page required")
            if effect.get("evidence_kind") != "direct_mechanism":
                raise ValueError("Goals, speculative impacts and rhetoric cannot be used")
            if not isinstance(effect.get("note"), str) or not effect["note"].strip():
                raise ValueError("Evidence paraphrase required")
            if "conditional_on" in effect:
                if not isinstance(effect["conditional_on"], list):
                    raise ValueError("Conditional ballot identifiers must be a list")
                if any(not str(v).isdigit() or str(v) == key for v in effect["conditional_on"]):
                    raise ValueError("Invalid condition reference")
    return document


def load_annotations(path):
    return validate_annotation_document(json.loads(Path(path).read_text(encoding="utf-8")))


def annotation_tags(row):
    """Multi-label facets and directed quantity; do not infer politics or value judgments."""
    tags = set()
    for effect in row["effects"]:
        for facet in ("domain", "instrument", "direction", "quantity"):
            tags.add(f"{facet}_{effect[facet]}")
        for target in effect["targets"]:
            tags.add(f"target_{target}")
        tags.add(f"signed_{effect['quantity']}_{effect['direction']}")
        if effect.get("conditional_on"):
            tags.add("conditional_on_other_ballot")
    return TAG_SEPARATOR.join(sorted(tags))


def build_semantic_table(objects, document):
    """Exact vote/date join; outcomes, annotations' prose and source URLs never enter X."""
    validate_annotation_document(document)
    if not {"vote_id", "vote_date"}.issubset(objects):
        raise ValueError("Missing vote identity")
    if objects.vote_id.isna().any():
        raise ValueError("Missing vote ID")
    ids = objects.vote_id.astype(str)
    dates = pd.to_datetime(objects.vote_date, errors="coerce")
    if ids.duplicated().any() or dates.isna().any():
        raise ValueError("Unusable vote identity")
    by_id = {str(v["vote_id"]): v for v in document["votes"]}
    missing = set(by_id) - set(ids)
    if missing:
        raise ValueError(f"Annotations do not match source object universe: {sorted(missing)}")
    mapped = objects[["vote_id"]].copy()
    tags = []
    is_documented = []
    for vote_id, vote_date in zip(ids, dates):
        record = by_id.get(vote_id)
        if record is not None and pd.Timestamp(record["vote_date"]) != vote_date.normalize():
            raise ValueError(f"Vote/date mismatch for {vote_id}")
        tags.append(annotation_tags(record) if record else "")
        is_documented.append(int(record is not None))
    mapped["semantic_tags"] = tags
    mapped["semantic_documented"] = is_documented
    return mapped


def fit_vocabulary(train, field):
    """Must be called on training objects only, never pooled across folds."""
    return sorted(set().union(*(_tokens(value) for value in train[field])))


def encode_multihot(rows, field, vocabulary, prefix):
    """Stable dense 0/1 columns; an unknown/unseen token yields no invented label."""
    if len(vocabulary) != len(set(vocabulary)):
        raise ValueError("Repeated fitted category")
    observed = rows[field].map(_tokens)
    cols = {}
    for tag in vocabulary:
        safe = tag.replace(".", "_")
        if not re.fullmatch(r"[a-z0-9_]+", safe):
            raise ValueError("Invalid encoded category")
        cols[f"{prefix}_{safe}"] = observed.map(lambda t: int(tag in t)).astype("uint8")
    return pd.DataFrame(cols, index=rows.index)
