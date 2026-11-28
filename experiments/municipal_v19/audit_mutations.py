"""V19.1: retrospective audit of official geographic mutations, never a model input."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

HOST = "www.agvchapp.bfs.admin.ch"
BASE = f"https://{HOST}/api/communes/mutations"
FIELDS = ("MutationNumber", "MutationDate", "InitialHistoricalCode", "InitialCode",
          "TerminalHistoricalCode", "TerminalCode")


def parse(raw):
    text = raw.decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(text[:8192], delimiters=";,\t")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("Invalid header")
    if not set(FIELDS).issubset(reader.fieldnames):
        raise ValueError("Required OFS fields missing")
    rows = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed row")
        if not row["MutationNumber"].strip() or not row["MutationDate"].strip():
            raise ValueError("Missing mutation identifier/date")
        rows.append(tuple(row[name].strip() for name in FIELDS))
    if not rows:
        raise ValueError("Empty mutation table")
    return rows


def compare(without, with_exchange):
    a, b = Counter(without), Counter(with_exchange)
    added, missing = b - a, a - b
    return {
        "rows_without": len(without),
        "rows_with": len(with_exchange),
        "mutation_ids_without": len({row[0] for row in without}),
        "mutation_ids_with": len({row[0] for row in with_exchange}),
        "added_rows": sum(added.values()),
        "missing_rows": sum(missing.values()),
        "added_mutation_ids": len({row[0] for row in added}),
        "missing_mutation_ids": len({row[0] for row in missing}),
        "equivalent_projected_multisets": a == b,
    }


def self_test():
    header = ";".join(FIELDS)
    a = "1;01.01.2017;100;1;101;1"
    b = "2;01.01.2018;101;1;102;1"
    raw = (header + "\n" + a + "\n").encode()
    one = parse(raw)
    two = parse((header + "\n" + a + "\n" + b + "\n").encode())
    assert compare(one, two)["added_rows"] == 1
    assert compare(two, one)["missing_rows"] == 1
    assert compare(one, one)["equivalent_projected_multisets"]
    assert not compare(one, one + one)["equivalent_projected_multisets"]
    assert compare(two, list(reversed(two)))["equivalent_projected_multisets"]
    for invalid in (b"html", header.encode(), (header + "\n1;2").encode()):
        try:
            parse(invalid)
        except (ValueError, csv.Error):
            continue
        raise AssertionError("Invalid data accepted")
    print("SELF_TEST_OK", flush=True)


def acquire(include):
    query = urlencode({"includeTerritoryExchange": str(include).lower(),
                       "startPeriod": "01-01-2016", "endPeriod": "31-12-2022",
                       "format": "csv"})
    url = BASE + "?" + query
    with urlopen(Request(url, headers={"User-Agent": "GML-research-geography-audit/1"}),
                 timeout=45) as response:
        final = response.geturl()
        parsed = urlparse(final)
        if parsed.scheme != "https" or parsed.hostname != HOST:
            raise ValueError("Unexpected response origin")
        raw = response.read(15_000_001)
        if len(raw) > 15_000_000:
            raise ValueError("Response exceeds audit limit")
        meta = {"url": url, "final_url": final, "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "content_type": response.headers.get("Content-Type")}
    return parse(raw), meta


def run(output):
    result = {"status": "started", "training_rows_admitted": 0, "requests": {}}
    tables = {}
    for include in (False, True):
        key = str(include).lower()
        try:
            tables[key], result["requests"][key] = acquire(include)
        except (OSError, ValueError, csv.Error) as exc:
            result["requests"][key] = {"error": f"{type(exc).__name__}: {exc}"}
    if len(tables) == 2:
        result["status"] = "complete"
        result["comparison"] = compare(tables["false"], tables["true"])
    else:
        result["status"] = "blocked"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print("SUMMARY", json.dumps(result, allow_nan=False), flush=True)
    if result["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    self_test()
    if not args.self_test:
        if args.output is None:
            parser.error("--output is required")
        run(args.output)
