"""V19.2: retrospective mutation exposure of benchmark numeric keys, never a feature."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from audit_mutations import acquire

REFERENCE_SHA = "622654c965648400469066ac36ee5bb3b886f120d3124f0c786f533275e17089"
SOURCE_SHA = {False: "5b71b290e70937ff254c2c7753f920884aeaf10192870c038e82efdeefc463d5", True: "73111625aa5a799bcf638435c4b1fd372d66fc430beb44d4fbcb81f727b5db03"}
START, END = date(2016,1,1), date(2022,12,31)

def ident(value, optional=False):
    value = str(value).strip()
    if optional and value in ("", "0"):
        return None
    if not re.fullmatch(r"[0-9]+", value) or int(value) <= 0:
        raise ValueError("Unexpected numeric identifier: " + repr(value))
    return int(value)

def day(value):
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("Unexpected date: " + repr(value))

def events(rows):
    by_code = defaultdict(set)
    for mutation, when, hi, initial, ht, terminal in rows:
        d = day(when)
        if not START <= d <= END:
            raise ValueError("Mutation outside declared interval")
        i, t = ident(initial, True), ident(terminal, True)
        h1, h2 = ident(hi, True), ident(ht, True)
        for code in {i, t} - {None}:
            by_code[code].add((d, mutation, i, t, h1, h2))
    return by_code

def audit(keys, without, full):
    a, b = events(without), events(full)
    delta = events(list((Counter(full) - Counter(without)).elements()))
    by_date = defaultdict(Counter)
    for d, obj, code in keys:
        c = by_date[d.isoformat()]
        c["rows"] += 1
        for label, mapping in (("without_exchange", a), ("with_exchange", b), ("added_records", delta)):
            es = mapping.get(code, ())
            c[label + "_any"] += bool(es)
            c[label + "_before_or_same"] += any(e[0] <= d for e in es)
            c[label + "_after"] += any(e[0] > d for e in es)
    totals = Counter()
    for counts in by_date.values():
        totals.update(counts)
    return {"totals": dict(totals), "by_date": dict(sorted(by_date.items())),
            "distinct_codes_with": len(b), "distinct_codes_added_records": len(delta),
            "benchmark_codes": len({k[2] for k in keys}),
            "boundary_certified": False, "training_rows_admitted": 0,
            "warning": "Numeric overlap only; no proof of identity or unchanged boundaries. Mutations outside 2016–2022 not covered. Retrospective audit only."}

def self_test():
    a = [("1","01.01.2017","100","1","101","1")]
    b = a + [("2","2018-01-01","101","1","102","2")]
    keys = [(date(2016,1,1),"a",1),(date(2018,1,1),"b",2),(date(2018,1,1),"b",3)]
    got = audit(keys,a,b)
    assert got["totals"]["rows"] == 3
    assert got["totals"]["with_exchange_any"] == 2
    assert got["totals"]["with_exchange_before_or_same"] == 1
    assert got["totals"]["with_exchange_after"] == 1
    assert got["totals"]["added_records_any"] == 2
    assert got["totals"]["without_exchange_any"] == 1
    assert got["distinct_codes_added_records"] == 2
    assert got["training_rows_admitted"] == 0 and not got["boundary_certified"]
    assert ident("0001") == 1 and ident("", True) is None
    for bad in ("1.0","CH1","-1"):
        try: ident(bad)
        except ValueError: pass
        else: raise AssertionError("Invalid ID accepted")
    print("12 synthetic assertions passed", flush=True)

def run(reference, output):
    import pyarrow.parquet as pq
    path, = reference.rglob("predictions.parquet")
    with path.open("rb") as f:
        sha = hashlib.file_digest(f,"sha256").hexdigest()
    if sha != REFERENCE_SHA:
        raise ValueError("Unexpected reference SHA")
    rows = pq.read_table(path, columns=["vote_date","vote_id","municipality_id"]).to_pylist()
    keys = [(day(str(x["vote_date"])[:10]),str(x["vote_id"]),ident(x["municipality_id"])) for x in rows]
    if not (len(keys)==len(set(keys))==138868 and len({x[0] for x in keys})==23
            and len({x[1] for x in keys})==66 and all(START<=x[0]<=END for x in keys)):
        raise ValueError("Unexpected reference population")
    tables, meta = {}, {}
    for flag in (False, True):
        tables[flag], meta[str(flag)] = acquire(flag)
        if meta[str(flag)]["sha256"] != SOURCE_SHA[flag]:
            raise ValueError("OFS snapshot changed since V19.1; explicit review required")
    result = audit(keys,tables[False],tables[True])
    result.update({"version":"V19.2","reference_sha256":sha,"sources":meta})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print("SUMMARY",json.dumps(result,allow_nan=False),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--reference",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    self_test()
    if not args.self_test:
        if args.reference is None or args.output is None: p.error("reference and output required")
        run(args.reference,args.output)
