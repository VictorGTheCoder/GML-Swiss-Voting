"""Extract labeled official fields from a brochure section."""

import re


def _section_fields(pages: list[str]) -> dict:
    text = "\n".join(pages)
    match = re.search(r"(?im)^Objet\s+(\d+)\s*:\s*(.+?)\s*$", text)
    if not match:
        raise ValueError("modern one-object section heading not found (expected 'Objet N: title')")
    start = match.start()
    later = re.search(r"(?im)^Objet\s+\d+\s*:", text[match.end():])
    end = match.end() + later.start() if later else len(text)
    section = text[start:end]

    def field(label: str) -> str:
        aliases = {"Résumé officiel": "Resume officiel", "Conseil fédéral": "Conseil federal"}
        actual = label
        found = re.search(rf"(?ims)^{re.escape(actual)}\s*:\s*(.*?)(?=^(?:Résumé officiel|Resume officiel|Texte complet|Conseil fédéral|Conseil federal|Parlement)\s*:|\Z)", section)
        if not found and label in aliases:
            actual = aliases[label]
            found = re.search(rf"(?ims)^{re.escape(actual)}\s*:\s*(.*?)(?=^(?:Résumé officiel|Resume officiel|Texte complet|Conseil fédéral|Conseil federal|Parlement)\s*:|\Z)", section)
        return " ".join(found.group(1).split()) if found else ""

    return {
        "section_order": int(match.group(1)),
        "title": match.group(2).strip(),
        "summary_official": field("Résumé officiel"),
        "full_text": field("Texte complet"),
        "council_recommendation_raw": field("Conseil fédéral"),
        "parliament_recommendation_raw": field("Parlement"),
        "source_pages": ",".join(str(i + 1) for i, page in enumerate(pages) if page.strip()),
    }
