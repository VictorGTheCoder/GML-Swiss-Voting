"""V17.2c: inspect immutable STRU header and historical key coverage, never outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

from match_elcom import digest, municipality, require

ARCHIVE_SHA = "b341a57a0eb8c2d589f7232db5775a0bf69169ba03fa73688f0bfe4b4d129f36"
REFERENCE_SHA = "622654c965648400469066ac36ee5bb3b886f120d3124f0c786f533275e17089"
PUBLICATION = "2019-05-28"


def fields(header, key):
    return [
        (m[1], re.findall(r'"((?:[^"]|"")*)"', m[2]))
        for m in re.finditer(
            rf'^\s*{key}(?:\[[^\]]+\])?\s*\(\s*"([^"]+)"\s*\)\s*=\s*([^;]*);',
            header, flags=re.MULTILINE | re.IGNORECASE,
        )
    ]


def geographic_header(header):
    geos = [(name, values) for name, values in fields(header, "VALUES")
            if "Gemeinde" in name and "Bezirk" in name]
    require(len(geos) == 1, "Ambiguous German geographic dimension")
    name, values = geos[0]
    code_lists = [codes for field, codes in fields(header, "CODES") if field == name]
    require(len(code_lists) <= 1, "Ambiguous geographic codes")
    codes = code_lists[0] if code_lists else None
    require(codes is None or len(codes) == len(values), "Geographic codes length mismatch")
    ids = []
    unresolved = []
    for i, label in enumerate(values):
        if not re.match(r"^\s*\.{6}\s*", label):
            continue
        label_id = re.match(r"^\s*\.{6}\s*(\d{1,4})(?:\s|$)", label)
        code_id = re.fullmatch(r"\s*(?:\.{6}\s*)?(\d{1,4})\s*", codes[i]) if codes else None
        if label_id and code_id:
            require(int(label_id[1]) == int(code_id[1]), "Label/code disagreement")
        match = label_id or code_id
        if match:
            ids.append(municipality(match[1]))
        else:
            unresolved.append(label[:120])
    require(len(ids) == len(set(ids)), "Duplicate geographic municipality IDs")
    metadata = [
        line[:400] for line in header.splitlines()
        if re.search(r"Gebietsstand|Gemeindestand|territorial|état des communes|état au|Raumgliederung", line, re.I)
    ]
    return {
        "dimension": name, "total_categories": len(values),
        "code_dimension_present": codes is not None,
        "municipal_ids": ids, "unresolved_municipal_labels": len(unresolved),
        "unresolved_examples": unresolved[:8], "label_examples": values[:12],
        "code_examples": codes[:12] if codes else [], "geography_metadata": metadata[:30],
    }


def coverage(triples, ids):
    available = [(d, v, i) for d, v, i in triples if d > PUBLICATION]
    matched = [(d, v, i) for d, v, i in available if i in ids]
    return {
        "rows": len(triples), "available_rows": len(available),
        "available_objects": len({v for _, v, _ in available}),
        "available_dates": len({d for d, _, _ in available}),
        "raw_matched_rows": len(matched),
        "raw_matched_by_year": dict(sorted(Counter(d[:4] for d, _, _ in matched).items())),
        "available_by_year": dict(sorted(Counter(d[:4] for d, _, _ in available).items())),
        "boundary_certified": False, "admitted": 0,
    }


def self_test():
    geo = "Kanton (-) / Bezirk (>>) / Gemeinde (......)"
    header = f'VALUES("{geo}")="Schweiz","- Zürich",">> Bezirk","......0001 A","...... B";\n'
    header += f'CODES("{geo}")="CH","ZH","D","1","0002";'
    got = geographic_header(header)
    assert got["municipal_ids"] == [1, 2]
    assert got["total_categories"] == 5
    assert got["unresolved_municipal_labels"] == 0
    assert geographic_header(header.splitlines()[0])["unresolved_municipal_labels"] == 1
    assert geographic_header(header.splitlines()[0])["municipal_ids"] == [1]
    for bad in (header.replace('"0002"', '"1"'), header.replace('"1","0002"', '"3","0002"'),
                header.replace(',"0002"', "")):
        try:
            geographic_header(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid geography accepted")
    c = coverage([("2019-05-28", "a", 1), ("2019-05-29", "b", 1),
                  ("2020-01-01", "c", 3)], {1})
    assert c["available_rows"] == 2
    assert c["raw_matched_rows"] == 1
    assert c["available_objects"] == 2
    assert not c["boundary_certified"] and c["admitted"] == 0
    print("12 synthetic checks passed", flush=True)


def run(reference, output):
    import pyarrow.parquet as pq

    path, = reference.rglob("predictions.parquet")
    require(digest(path) == REFERENCE_SHA, "Wrong reference artifact")
    keys = pq.read_table(path, columns=["vote_date", "vote_id", "municipality_id"]).to_pylist()
    triples = [(str(r["vote_date"])[:10], str(r["vote_id"]), municipality(r["municipality_id"]))
               for r in keys]
    require(len(triples) == len(set(triples)) == 138868, "Wrong or duplicate keys")
    require(len({v for _, v, _ in triples}) == 66, "Wrong objects")
    require(len({d for d, _, _ in triples}) == 23, "Wrong dates")
    require(all("2016-01-01" <= d < "2023-01-01" for d, _, _ in triples), "Forbidden date")
    url = "https://dam-api.bfs.admin.ch/hub/api/dam/assets/8346718/master"
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - fixed official HTTPS URL
        raw = response.read(21_000_000)
    require(hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA, "Archive changed")
    prefix = raw[:8_000_000].decode("cp1252", errors="replace")
    end = re.search(r"^\s*DATA\s*=", prefix, flags=re.MULTILINE | re.IGNORECASE)
    require(end is not None, "PX header unavailable")
    geo = geographic_header(prefix[:end.start()])
    ids = set(geo.pop("municipal_ids"))
    result = {
        "version": "V17.2c", "archive_sha256": ARCHIVE_SHA, "publication": PUBLICATION,
        "geography": geo, "recognized_municipal_ids": len(ids),
        "coverage": coverage(triples, ids),
        "status": "raw_identifier_diagnostic_only",
        "warning": "IDs alone cannot certify stable boundaries; no values extracted.",
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print("SUMMARY", json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    self_test()
    if not args.self_test:
        run(args.reference, args.output)
