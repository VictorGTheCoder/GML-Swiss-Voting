"""Inventory public AFF files; never admit features or export source bytes."""
import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LIMIT = 20 * 1024 * 1024


def inspect_bytes(data, kind):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if kind == "xlsx":
            if "xl/workbook.xml" not in names or "[Content_Types].xml" not in names:
                raise ValueError("not an XLSX workbook")
            return {"worksheet_parts": sum(
                n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
                for n in names
            )}
        return {"members": [
            {"name": item.filename, "bytes": item.file_size, "crc32": f"{item.CRC:08x}"}
            for item in archive.infolist() if not item.is_dir()
        ]}


def fetch(source):
    url = source["url"]
    if source["status"] != "candidate_not_admitted" or not 2016 <= source["year"] <= 2022:
        raise ValueError("outside source audit scope")
    if urlparse(url).scheme != "https" or urlparse(url).hostname != "www.efv.admin.ch":
        raise ValueError("unexpected host")
    kind = "xlsx" if url.endswith(".xlsx") else "zip"
    with urlopen(Request(url, headers={"User-Agent": "GML-source-audit/1.0"}), timeout=25) as response:
        final = response.geturl()
        if urlparse(final).scheme != "https" or urlparse(final).hostname != "www.efv.admin.ch":
            raise ValueError("unexpected redirect")
        data = response.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("source exceeds limit")
        metadata = {
            "final_url": final,
            "http_status": response.status,
            "content_type": response.headers.get("Content-Type"),
            "last_modified": response.headers.get("Last-Modified"),
        }
    return {
        **metadata, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        **inspect_bytes(data, kind),
    }


def self_test():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("sample.txt", "synthetic")
    assert inspect_bytes(buffer.getvalue(), "zip")["members"][0]["bytes"] == 9
    try:
        inspect_bytes(buffer.getvalue(), "xlsx")
    except ValueError:
        pass
    else:
        raise AssertionError("accepted non-XLSX")
    try:
        inspect_bytes(b"not a zip", "zip")
    except zipfile.BadZipFile:
        pass
    else:
        raise AssertionError("accepted corrupt file")
    print("3 synthetic checks passed")


def main():
    self_test()
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    records = []
    for source in manifest["sources"]:
        record = dict(source)
        try:
            record.update(fetch(source))
            record["fetch_status"] = "downloaded_inventory_only"
        except Exception as exc:
            record.update(fetch_status="failed", error=f"{type(exc).__name__}: {exc}")
        records.append(record)
    result = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "training_rows_admitted": 0,
        "publication_vintage_verified": False,
        "license_verified": False,
        "records": records,
    }
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"requested": len(records), "downloaded": sum(
        r["fetch_status"] == "downloaded_inventory_only" for r in records
    )}))
    if all(r["fetch_status"] == "failed" for r in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
