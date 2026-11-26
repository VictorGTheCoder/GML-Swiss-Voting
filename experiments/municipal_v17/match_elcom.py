"""V17.1b: source coverage only, projected historical keys; no outcome columns."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def municipality(value):
    value = str(value)
    require(re.fullmatch(r"[1-9][0-9]*", value) is not None, "Unexpected municipality ID")
    return int(value)


def coverage(keys, rows, year):
    source = {}
    for row in rows:
        ident = municipality(row["bfs_id"])
        require(ident not in source and row["year"] == year, "Duplicate or wrong vintage")
        require(row["status"] == "quarantine", "Unexpected admission")
        n, o = row["rows"], row["operators"]
        require(type(n) is int and type(o) is int and n >= o >= 1, "Invalid counts")
        source[ident] = n == o == 1
    require(bool(keys) and bool(source), "Empty coverage population")
    counts = Counter(keys)
    hit = set(counts) & set(source)
    single = {i for i in hit if source[i]}
    return {
        "year": year, "reference_unique_ids": len(counts), "reference_rows": len(keys),
        "source_unique_ids": len(source), "matched_ids": len(hit),
        "matched_single_ids": len(single), "source_only_ids": len(set(source) - set(counts)),
        "missing_ids": len(set(counts) - set(source)),
        "raw_id_coverage": len(hit) / len(counts),
        "strict_id_coverage": len(single) / len(counts),
        "strict_row_coverage": sum(counts[i] for i in single) / len(keys),
    }


def self_test():
    def row(i, n=1, year=2016):
        return dict(bfs_id=i, year=year, rows=n, operators=n, status="quarantine")
    rows = [row(1), row(2, 2), row(4)]
    got = coverage([1, 1, 2, 3], rows, 2016)
    assert got["raw_id_coverage"] == 2 / 3
    assert got["strict_id_coverage"] == 1 / 3
    assert got["strict_row_coverage"] == 1 / 2
    assert got["source_only_ids"] == 1
    assert got["missing_ids"] == 1
    for invalid in ([row(1), row(1)], [row(1, year=2017)], [row(1, 0)]):
        try:
            coverage([1], invalid, 2016)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid input accepted")
    print("8 synthetic checks passed", flush=True)


def digest(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def run(source, reference, output):
    import pyarrow.parquet as pq

    expected = json.loads(Path("experiments/municipal_v17/elcom_acquisition_v171.json").read_text())
    path, = reference.rglob("predictions.parquet")
    require(digest(path) == "622654c965648400469066ac36ee5bb3b886f120d3124f0c786f533275e17089",
            "Wrong frozen reference artifact")
    table = pq.read_table(path, columns=["vote_date", "vote_id", "municipality_id"])
    keys = table.to_pylist()
    require(len(keys) == 138868, "Wrong number of rows")
    triples = [(str(r["vote_date"])[:10], str(r["vote_id"]), municipality(r["municipality_id"]))
               for r in keys]
    require(len(set(triples)) == len(triples), "Duplicate reference keys")
    require(len({v for _, v, _ in triples}) == 66, "Wrong object population")
    require(len({d for d, _, _ in triples}) == 23, "Wrong date population")
    require(all("2016-01-01" <= d < "2023-01-01" for d, _, _ in triples), "Forbidden date")
    results = []
    for entry in expected["years"]:
        year = entry["year"]
        file = source / f"{year}.json"
        rows = json.loads(file.read_text())
        require(len(rows) == entry["municipalities"], "Source count differs from CI logs")
        require(sum(r["rows"] > 1 for r in rows) == entry["multiple_rows"], "Multiple row mismatch")
        require(sum(r["operators"] > 1 for r in rows) == entry["multiple_operators"], "Operator mismatch")
        result = coverage([i for d, _, i in triples if int(d[:4]) == year], rows, year)
        result["normalized_sha256"] = digest(file)
        results.append(result)
    summary = {"version": "V17.1b", "reference_rows": len(keys), "objects": 66, "dates": 23,
               "source_run": expected["source_run"], "source_artifact": expected["source_artifact"],
               "years": results, "years_strict_ge_90pct": sum(r["strict_id_coverage"] >= .9 for r in results),
               "admitted": 0, "boundary_certified": False, "historical_vintage_certified": False}
    output.mkdir(parents=True, exist_ok=False)
    (output / "manifest.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    self_test()
    if not args.self_test:
        run(args.source, args.reference, args.output)
