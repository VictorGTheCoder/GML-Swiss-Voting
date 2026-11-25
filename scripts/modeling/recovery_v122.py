"""V12.2: target-blind byte and page evidence, never a training corpus."""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

LIMIT = 25 * 1024 * 1024
PAGES = {"6130": [4, 5, 8], "6140": [12, 13, 24, 25],
         "6150": [12, 13, 26], "6550": [4, 5], "6560": [6, 7],
         "6570": [8, 9]}
KEYS = {"2017-09-24": ["securite alimentaire", "financement additionnel", "prevoyance vieillesse"],
        "2022-05-15": ["cinema", "transplantation", "schengen"]}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.lower())
                            if not unicodedata.combining(c)).split())


def valid_url(url):
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.hostname in
            {"www.admin.ch", "www.bk.admin.ch", "www.fr.ch"}
            and not parsed.username and not parsed.password
            and parsed.port in (None, 443))


def validate_source(source):
    vote = source["vote_date"]
    if not date.fromisoformat(vote) < date(2023, 1, 1):
        raise ValueError("outside development")
    for key in ("catalog_publication", "publication_evidence_date", "editorial_cutoff"):
        if source.get(key) and not date.fromisoformat(source[key]) < date.fromisoformat(vote):
            raise ValueError("non-prior evidence")
    if vote not in KEYS:
        raise ValueError("unexpected date")
    for obj in source["objects"]:
        if obj["vote_id"] not in PAGES:
            raise ValueError("unexpected object")


def download(url):
    if not valid_url(url):
        raise ValueError("non-official URL")
    with urlopen(url, timeout=45) as response:
        if not valid_url(response.geturl()):
            raise ValueError("non-official redirect")
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT or not data.startswith(b"%PDF-"):
        raise ValueError("invalid PDF or size")
    return data


def page_text(path, page):
    return subprocess.check_output(
        ["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(path), "-"],
        timeout=30).decode("utf-8")


def inspect_pdf(data, source):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "source.pdf"
        path.write_bytes(data)
        info = subprocess.check_output(["pdfinfo", str(path)], text=True, timeout=30)
        count = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
        toc = normalized(page_text(path, source["toc_page"]))
        if not all(key in toc for key in KEYS[source["vote_date"]]):
            raise ValueError("TOC identity mismatch")
        records = []
        for obj in source["objects"]:
            for page in PAGES[obj["vote_id"]]:
                if not 1 <= page <= count:
                    raise ValueError("page out of range")
                content = page_text(path, page)
                if len(content.strip()) < 40:
                    raise ValueError("empty page")
                records.append({"vote_id": obj["vote_id"], "physical_page": page,
                                "text_sha256": digest(content.encode("utf-8")),
                                "text_chars": len(content)})
        return {"pdf_sha256": digest(data), "bytes": len(data), "page_count": count,
                "toc_identity_pass": True, "pages": records}


def source_urls(source):
    """Preserve order and record each distinct, explicitly listed mirror."""
    return list(dict.fromkeys([source["url"]] +
                              ([source["alternate_url"]] if source.get("alternate_url") else []) +
                              source.get("additional_urls", [])))


def audit(manifest):
    results = []
    for source in manifest["sources"]:
        validate_source(source)
        for url in source_urls(source):
            record = {"vote_date": source["vote_date"], "url": url}
            try:
                record.update(inspect_pdf(download(url), source))
                record["status"] = "hashed_candidate"
            except (OSError, ValueError, subprocess.SubprocessError, AttributeError) as exc:
                record.update(status="blocked", error=str(exc))
            results.append(record)
    by_date = {}
    for vote_date in sorted({x["vote_date"] for x in results}):
        candidates = [x for x in results if x["vote_date"] == vote_date
                      and x["status"] == "hashed_candidate"]
        hashes = [x["pdf_sha256"] for x in candidates]
        by_date[vote_date] = {"hashed_mirrors": len(hashes),
                              "mirror_bytes_equal": len(set(hashes)) == 1 if len(hashes) >= 2 else None}
    return {"status": "audit_only_not_admitted", "sources": results,
            "by_date": by_date,
            "mirror_bytes_equal": by_date.get("2022-05-15", {}).get("mirror_bytes_equal"),
            "strict_forecast_ready": False, "training_rows": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(json.loads(args.manifest.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if any(x["status"] != "hashed_candidate" for x in report["sources"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
