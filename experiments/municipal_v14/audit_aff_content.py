"""Audit pinned AFF archives; export only metadata and aggregate checks."""
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

LIMIT = 20 * 1024 * 1024
BASE = Path("data/external/fiscal_equalization_v141")
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pinned(data, expected):
    if len(data) > LIMIT or digest(data) != expected:
        raise ValueError("source hash or size mismatch")
    return data


def fetch(source, expected):
    url = source["url"]
    parsed = urlparse(url)
    if (parsed.scheme, parsed.hostname) != ("https", "www.efv.admin.ch"):
        raise ValueError("unexpected origin")
    if source["status"] != "candidate_not_admitted" or not 2016 <= source["year"] <= 2022:
        raise ValueError("outside audit scope")
    with urlopen(Request(url, headers={"User-Agent": "GML-source-audit/1.0"}), timeout=30) as response:
        final = urlparse(response.geturl())
        if (final.scheme, final.hostname) != ("https", "www.efv.admin.ch"):
            raise ValueError("unexpected redirect")
        return pinned(response.read(LIMIT + 1), expected)


def member(archive, name):
    matches = [i for i in archive.infolist() if Path(i.filename).name == name and not i.is_dir()]
    if len(matches) != 1 or matches[0].file_size > LIMIT:
        raise ValueError("missing, ambiguous, or oversized member")
    return archive.read(matches[0])


def schema(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        info = archive.getinfo("xl/workbook.xml")
        if info.file_size > LIMIT:
            raise ValueError("oversized workbook metadata")
        root = ElementTree.fromstring(archive.read(info))
        return [s.attrib["name"] for s in root.findall("s:sheets/s:sheet", NS)]


def table_check(pages, candidates):
    # Strict evidence: same table page, canton order and a matching full row
    # or full numeric column. Ambiguous/mismatching layout remains unresolved.
    codes = list(candidates)
    expected = list(candidates.values())
    result = []
    for page_number, page in enumerate(pages, 1):
        if not re.search(r"Tabelle\s*7\b", page, re.I) or "Ressourcen" not in page:
            continue
        found = re.findall(r"\b[A-Z]{2}\b", page)
        filtered = [code for code in found if code in candidates]
        if filtered != codes:
            continue
        lines = page.splitlines()
        rows = {}
        for line in lines:
            match = re.match(r"\s*([A-Z]{2})\s+", line)
            if match and match.group(1) in candidates:
                code = match.group(1)
                if code in rows:
                    rows = {}
                    break
                rows[code] = re.findall(r"(?<![\d.])\d{1,3}[.,]\d(?![\d.])", line)
        if list(rows) == codes and len({len(v) for v in rows.values()}) == 1:
            columns = list(zip(*(rows[code] for code in codes)))
        else:
            columns = []
        # Some landscape PDFs extract as horizontal canton vectors.
        for line in lines:
            nums = re.findall(r"(?<![\d.])\d{1,3}[.,]\d(?![\d.])", line)
            if len(nums) == len(codes) or (len(nums) == len(codes) + 1 and nums[-1] in ("100.0", "100,0")):
                columns.append(nums[:len(codes)])
        matches = sum([Decimal(x.replace(",", ".")) for x in col] == expected for col in columns)
        result.append({"page_1based": page_number, "candidate_vectors": len(columns), "exact_vectors": matches})
    return result


def self_test():
    expected = digest(b"test")
    assert pinned(b"test", expected) == b"test"
    try:
        pinned(b"wrong", expected)
    except ValueError:
        pass
    else:
        raise AssertionError("hash mismatch accepted")
    candidates = {"ZH": Decimal("120.6"), "BE": Decimal("74.2")}
    page = "Tabelle 7 Ressourcenindex 2016\nZH 120.6 119.5\nBE 74.2 74.9"
    assert table_check([page], candidates)[0]["exact_vectors"] == 1
    assert not table_check([page.replace("Tabelle 7", "Tabelle 8")], candidates)
    assert table_check([page.replace("120.6", "120.7")], candidates)[0]["exact_vectors"] == 0
    print("5 synthetic checks passed")


def main():
    self_test()
    if "--self-test" in sys.argv:
        return
    with (BASE / "archive_inventory_hashes.csv").open() as stream:
        hashes = {(int(row["year"]), row["family"]): row["sha256"] for row in csv.DictReader(stream)}
    sources = json.loads((BASE / "archive_sources.json").read_text())["sources"]
    if len(hashes) != len(sources) or len(sources) != 13:
        raise ValueError("manifest cardinality changed")
    blobs = {}
    for source in sources:
        key = source["year"], source["family"]
        blobs[key] = fetch(source, hashes[key])
    with (BASE / "resource_index_candidates.csv").open() as stream:
        candidates = {row["canton"]: Decimal(row["resource_index_consultation"])
                      for row in csv.DictReader(stream) if row["reference_year"] == "2016"}
    if len(candidates) != 26:
        raise ValueError("unexpected candidate cardinality")
    result = {"pinned_sources": len(blobs), "pairs": [], "schemas": [],
              "training_rows_admitted": 0, "publication_vintage_verified": False,
              "license_verified": False}
    for source in sources:
        year, family = source["year"], source["family"]
        if family == "archive":
            continue
        data = blobs[year, family]
        result["schemas"].append({"year": year, "family": family, "sheets": schema(data)})
        if year in (2017, 2018):
            name = source["url"].rsplit("/", 1)[-1]
            with zipfile.ZipFile(io.BytesIO(blobs[year, "archive"])) as archive:
                inner = member(archive, name)
            result["pairs"].append({"year": year, "family": family, "member": name,
                                    "nested_sha256": digest(inner), "identical": digest(inner) == digest(data)})
    with zipfile.ZipFile(io.BytesIO(blobs[2016, "archive"])) as archive:
        pdf = member(archive, "Bericht_FDK_2016_Anhoerung.pdf")
        for info in archive.infolist():
            name = Path(info.filename).name
            if re.fullmatch(r"(?:1\.7_RA|2\.[234]_[A-Z_]+)_2016\.xlsx", name):
                inner = member(archive, name)
                result["schemas"].append({"year": 2016, "member": name, "sha256": digest(inner),
                                          "sheets": schema(inner)})
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.pdf"
        path.write_bytes(pdf)
        raw = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True,
                             capture_output=True, timeout=60).stdout.decode("utf-8")
    pages = raw.split("\f")
    result["pdf_2016"] = {"sha256": digest(pdf), "bytes": len(pdf),
                          "cover_june_2015": bool(re.search(r"Juni\s+2015", pages[0])),
                          "table_checks": table_check(pages, candidates),
                          "candidate_count": len(candidates)}
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
