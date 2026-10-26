"""Audit source tables and identifier compatibility without merging their features."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.common.config import PROCESSED_DIR, RAW_DIR, REPORTS_DIR, ROOT

TABLES = {
    "ofs": ("ofs-votes/votes_communes.parquet", ["municipality_id", "vote_id"]),
    "swissvotes": ("swissvotes/swissvotes_clean.parquet", ["vote_key"]),
    "statpop": ("statpop/statpop_features.parquet", ["municipality_id", "year"]),
    "typologies": ("typologies/commune_typologies.parquet", ["municipality_id"]),
    "elections": ("elections/elections_communes.parquet", ["municipality_id", "election_year", "party_code"]),
    "communes": ("repertoire_communes/crosswalk_2010-01-01_to_2026-01-01.parquet", ["source_code", "target_code"]),
    "brochure_objects": ("federal_explanations/objects.parquet", ["vote_id"]),
    "brochure_sources": ("federal_explanations/sources.parquet", ["source_id"]),
    "brochure_sections": ("federal_explanations/sections.parquet", ["source_id", "object_id"]),
    "brochure_pages": ("federal_explanations/pages.parquet", ["source_id", "page_number"]),
    "brochure_links": ("federal_explanations/section_links.parquet", ["source_id", "object_id", "vote_id"]),
}


def audit() -> dict:
    result = {"tables": {}, "joins": {}, "errors": [], "limitations": [
        "Compatible identifiers do not prove identical historical territorial boundaries.",
        "STATPOP availability uses a conservative calendar, not archived historical releases.",
        "Typology and election historical publication dates remain unverified.",
        "Brochure candidate links and temporal eligibility require review before modeling.",
        "The model evaluation contract requires additional forecast/publication evidence.",
    ]}
    frames = {}
    for name, (relative, keys) in TABLES.items():
        path = PROCESSED_DIR / relative
        if not path.is_file():
            result["errors"].append(f"Missing {relative}")
            continue
        frame = pd.read_parquet(path)
        frames[name] = frame
        missing = sorted(set(keys) - set(frame.columns))
        duplicates = None if missing else int(frame.duplicated(keys).sum())
        null_keys = None if missing else int(frame[keys].isna().any(axis=1).sum())
        result["tables"][name] = {
            "path": path.relative_to(ROOT).as_posix(), "rows": len(frame),
            "columns": len(frame.columns), "keys": keys,
            "duplicate_keys": duplicates, "null_keys": null_keys,
            "schema": {c: str(t) for c, t in frame.dtypes.items()},
            "missing_values": {c: int(n) for c, n in frame.isna().sum().items() if n},
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if missing or duplicates or null_keys:
            result["errors"].append(f"{name}: missing={missing}, duplicate keys={duplicates}, null keys={null_keys}")
        for column in [c for c in keys if c in {"municipality_id", "vote_id", "vote_key", "source_code", "target_code"}]:
            if column in frame and not all(isinstance(v, str) for v in frame[column].dropna().unique()):
                result["errors"].append(f"{name}.{column} must contain string identifiers")
        if "municipality_id" in frame and not frame.municipality_id.str.fullmatch(r"\d{4}").all():
            result["errors"].append(f"{name}: noncanonical municipality identifiers")

    def compare(label, left, right):
        left, right = set(left.dropna()), set(right.dropna())
        result["joins"][label] = {
            "left_unique": len(left), "right_unique": len(right), "matched": len(left & right),
            "left_unmatched": sorted(left - right), "right_unmatched_count": len(right - left),
        }

    if "ofs" in frames:
        votes = frames["ofs"]
        ordinary = votes.loc[~votes.is_special_unit]
        for source in ("statpop", "typologies", "elections"):
            if source in frames:
                compare(f"ofs_to_{source}", ordinary.municipality_id, frames[source].municipality_id)
                if result["joins"][f"ofs_to_{source}"]["left_unmatched"]:
                    result["errors"].append(f"OFS communes missing from {source}")
        if "swissvotes" in frames:
            compare("ofs_to_swissvotes", votes.vote_key, frames["swissvotes"].vote_key)
            joined = votes[["vote_key", "vote_date"]].drop_duplicates().merge(
                frames["swissvotes"][["vote_key", "vote_date"]], on="vote_key", how="left", validate="many_to_one",
                suffixes=("_ofs", "_swissvotes"))
            if joined.vote_date_swissvotes.isna().any() or not pd.to_datetime(joined.vote_date_ofs).eq(pd.to_datetime(joined.vote_date_swissvotes)).all():
                result["errors"].append("OFS/Swissvotes date or coverage mismatch")
        if "brochure_objects" in frames:
            objects = frames["brochure_objects"]
            covered = objects.loc[objects.brochure_status.eq("FOUND")]
            compare("ofs_to_brochures", votes.vote_id, covered.vote_id)
            period = votes.loc[pd.to_datetime(votes.vote_date).between("2011-01-01", "2026-12-31")]
            compare("ofs_2011_2026_to_brochures", period.vote_id, covered.vote_id)
            historical_period = votes.loc[pd.to_datetime(votes.vote_date).between("1978-01-01", "2026-12-31")]
            compare("ofs_1978_2026_to_brochures", historical_period.vote_id, covered.vote_id)
            if result["joins"]["ofs_1978_2026_to_brochures"]["left_unmatched"]:
                result["limitations"].append("Some 1978-2026 voting objects have no collected brochure.")
            result["brochure_statuses"] = {
                c: objects[c].fillna("MISSING").value_counts().to_dict()
                for c in ("brochure_status", "match_status", "availability_status", "semantic_status")
            }
    if {"statpop", "typologies"} <= frames.keys():
        compare("statpop_to_typologies", frames["statpop"].municipality_id, frames["typologies"].municipality_id)
    if "brochure_pages" in frames:
        pages = frames["brochure_pages"]
        result["brochure_extraction"] = {
            "page_statuses": pages.status.value_counts(dropna=False).to_dict(),
            "methods": pages.method.value_counts(dropna=False).to_dict(),
            "empty_text_pages": int(pages.text.fillna("").str.strip().eq("").sum()),
        }
        failed = int(pages.status.ne("EXTRACTED").sum())
        if failed:
            result["limitations"].append(f"{failed} brochure pages could not be extracted (see per-page error).")
    if "statpop" in frames:
        frame = frames["statpop"]
        result["statpop_years"] = sorted(frame.year.unique().tolist())
        if result["statpop_years"] != list(range(2010, 2026)):
            result["errors"].append("STATPOP does not cover all expected years 2010-2025")
    if {"brochure_links", "brochure_sections", "brochure_sources"} <= frames.keys():
        links, sections = frames["brochure_links"], frames["brochure_sections"]
        linked = links.merge(sections[["source_id", "object_id"]], on=["source_id", "object_id"], how="left", indicator=True, validate="many_to_one")
        if linked._merge.ne("both").any():
            result["errors"].append("Brochure links reference missing sections")
        for name in ("brochure_links", "brochure_sections", "brochure_pages"):
            if not set(frames[name].source_id) <= set(frames["brochure_sources"].source_id):
                result["errors"].append(f"{name}: unknown source identifiers")
    checked = 0
    for path in RAW_DIR.rglob("*.json"):
        if "provenance" not in path.name:
            continue
        content = json.loads(path.read_text(encoding="utf-8"))
        records = [content] if "sha256" in content else list(content.values())
        for record in records:
            if not isinstance(record, dict) or not record.get("sha256"):
                continue
            if record.get("file"):
                source = ROOT / record["file"]
            elif path.name == "swissvotes.provenance.json":
                source = path.with_name("swissvotes.csv")
            else:
                continue
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]:
                result["errors"].append(f"Provenance hash mismatch: {source}")
            checked += 1
    result["provenance_files_checked"] = checked
    manifest = RAW_DIR / "federal_explanations" / "sources.json"
    if manifest.is_file():
        documents = json.loads(manifest.read_text(encoding="utf-8"))["documents"]
        for document in documents:
            path = Path(document["pdf_path"])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != document["pdf_sha256"]:
                result["errors"].append(f"Brochure hash mismatch: {document['source_id']}")
        result["brochure_hashes_checked"] = len(documents)
    result["status"] = "PASS_WITH_LIMITATIONS" if not result["errors"] else "FAIL"
    return result


def main() -> None:
    result = audit()
    output = REPORTS_DIR / "generated" / "dataset_compatibility"
    output.mkdir(parents=True, exist_ok=True)
    (output / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Audit des datasets", "", f"Statut : **{result['status']}**", "",
             "| Table | Lignes | Colonnes | Doublons de clé |", "|---|---:|---:|---:|"]
    for name, info in result["tables"].items():
        lines.append(f"| {name} | {info['rows']} | {info['columns']} | {info['duplicate_keys']} |")
    lines += ["", "## Correspondances", ""]
    for name, info in result["joins"].items():
        absent = info['left_unmatched']
        detail = str(absent[:10]) + (f" … ({len(absent)} au total, liste complète dans audit.json)" if len(absent) > 10 else "")
        lines.append(f"- {name}: {info['matched']}/{info['left_unique']} identifiants couverts ; absents : {detail}.")
    lines += ["", "## Limites", ""] + [f"- {line}" for line in result["limitations"]]
    if "brochure_extraction" in result:
        lines += ["", "## Extraction des brochures", "", json.dumps(result["brochure_extraction"], ensure_ascii=False)]
    lines += ["", "## Erreurs", ""] + ([f"- {line}" for line in result["errors"]] or ["Aucune erreur structurelle détectée."])
    (output / "audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "errors": result["errors"], "report": str(output / "audit.md")}, ensure_ascii=False))
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
