"""V8.1 acquisition gate: validate national poll reconstruction and collect
settlement margins from reviewed charts, without loading any vote outcomes.

Latest-only retrospective LeeWas data are explicitly weaker provenance than
a dated pre-vote report. The second-wave source controls the pair's availability.
"""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.collect_poll_features import (
    DATE_RE,
    FIELDS,
    NATIONAL_BARE_DATE_CHARTS,
    date_de,
    extract_national_rows,
    fetch,
    find_tables,
    label_field,
    norm,
    sha,
)
from scripts.modeling.semantic_poll_comparison_v4 import load_expanded_polls

SOURCE = ROOT / "data/external/polls_v81"
SSR = ROOT / "data/external/polls/srg_gfs_polls.csv"
HIST = ROOT / "data/external/polls_historical_v3/polls.csv"
# Explicit keys checked against Swissvotes titles, not report row order.
# Abbreviations in the report are allowed only through this reviewed crosswalk.
TITLE_TOKENS = {
    "5960": "heirat|eheundfamilie", "5970": "durchsetzung", "5980": "spekulation",
    "5990": "gotthard", "6000": "servicepublic", "6010": "grundeinkommen",
    "6020": "verkehrsfinanzierung", "6030": "fortpflanzung", "6040": "asylgesetz",
    "6050": "grunewirtschaft", "6060": "ahvplus", "6070": "nachrichtendienst",
    "6080": "atomausstieg", "6090": "einburgerung", "6100": "nationalstrassen|naf",
    "6110": "unternehmenssteuer", "6120": "energiegesetz",
    "6130": "ernahrungssicherheit", "6140": "mehrwertsteuer", "6150": "altersvorsorge",
    "6160": "finanzordnung", "6170": "billag", "6180": "vollgeld", "6190": "geldspiel",
    "6200": "veloweg", "6210": "fairfood", "6220": "ernahrungssouveranitat",
    "6230": "hornkuh", "6240": "selbstbestimmung", "6250": "uberwachungvonversicherten",
    "6260": "zersiedelung", "6270": "steuerreform", "6280": "waffen",
    "6290": "bezahlbarewohnungen", "6300": "diskriminierung",
    "6310": "begrenzung", "6320": "jagd", "6330": "kinderabzug",
    "6340": "vaterschaft", "6350": "kampfflugzeug", "6360": "konzernverantwort",
    "6370": "kriegsgeschafte", "6380": "verhullung", "6390": "identifizier",
    "6400": "indonesien", "6410": "trinkwasser", "6420": "pestizid",
    "6430": "covid19", "6440": "co2gesetz", "6450": "terrorismus",
    "6460": "99|lohneentlasten", "6470": "ehefur alle|ehefuralle",
    "6480": "pflege", "6490": "justiz", "6500": "covid19",
    "6510": "tierversuch|tierundmenschenversuch|tierundmenschenversuchen",
    "6520": "tabakwerbung", "6530": "stempelabgab", "6540": "medienpaket|medien",
    "6550": "filmgesetz", "6560": "organspende|transplantation", "6570": "frontex",
    "6580": "massentierhaltung", "6590": "mehrwertsteuer", "6600": "ahv",
    "6610": "verrechnungssteuer",
}
SETTLEMENT = {
    "landlich": "rural",
    "kleinemittlereagglomeration": "medium",
    "kleineundmittlereagglomeration": "medium",
    "grosseagglomeration": "large",
}
URBAN_LABELS = ("rural", "medium", "large")


def validate_national(table, pairs, metadata, old):
    if set(table.columns) != {"vote_key", "source_label", "tamedia_yes", "srg_yes", "table"}:
        raise ValueError("Only source poll columns are permitted")
    if table.vote_key.duplicated().any() or set(table.vote_key) != set(TITLE_TOKENS):
        raise ValueError("Incomplete or duplicate expected historical vote keys")
    meta = metadata.set_index("vote_key", verify_integrity=True)
    joined = table.merge(metadata, on="vote_key", validate="one_to_one", how="left")
    if joined.vote_date.isna().any() or not joined.vote_date.between("2016-01-01", "2022-12-31").all():
        raise ValueError("Missing or invalid Swissvotes date")
    mismatches = []
    for row in joined.itertuples():
        title = norm(str(row.titel_kurz_d) + " " + str(row.titel_off_d))
        if not re.search(TITLE_TOKENS[row.vote_key], title):
            mismatches.append([row.vote_key, row.source_label, row.titel_kurz_d, row.titel_off_d])
    if mismatches:
        raise ValueError(f"Title crosswalk failed: {mismatches}")
    for c in ["tamedia_yes", "srg_yes"]:
        if not joined[c].dropna().between(0, 100).all():
            raise ValueError("Invalid percentage")
    if joined.tamedia_yes.isna().any() or set(joined[joined.srg_yes.isna()].vote_key) != {"6030"}:
        raise ValueError("Unexpected missing poll")
    old_latest = old[old.vote_date.between("2016-01-01", "2022-12-31")].sort_values(
        ["vote_key", "wave"]
    ).drop_duplicates("vote_key", keep="last")
    if len(old_latest) != 48:
        raise ValueError("Expected frozen coverage of 48 objects")
    checked = joined.merge(old_latest[["vote_key", "yes_total"]], on="vote_key", how="left")
    conflicts = checked[checked.yes_total.notna() & checked.srg_yes.ne(checked.yes_total)]
    agreements = int((checked.srg_yes.eq(checked.yes_total) & checked.yes_total.notna()).sum())
    if agreements < 45:
        raise ValueError("Retrospective table does not reconcile with existing directly sourced SSR polls")
    missing = set(joined.vote_key) - set(old_latest.vote_key)
    if pairs.vote_key.duplicated().any() or set(pairs.vote_key) != missing - {"6030"}:
        raise ValueError("Expected exactly the 17 missing SSR-polled objects")
    for r in pairs.itertuples():
        date = pd.Timestamp(meta.loc[r.vote_key, "vote_date"])
        first, last, p1, p2 = map(pd.Timestamp, (r.first_midpoint, r.last_midpoint,
                                                 r.first_published_date, r.last_published_date))
        if not first < last or not first <= p1 < p2 < date or not last <= p2:
            raise ValueError("Invalid fieldwork or publication order")
        if not (0 <= r.first_yes <= 100 and 0 <= r.last_yes <= 100):
            raise ValueError("Invalid reconstructed shares")
    out = joined[["vote_key", "vote_date", "source_label", "tamedia_yes", "srg_yes", "table"]].copy()
    out["vote_date"] = pd.to_datetime(out.vote_date).dt.strftime("%Y-%m-%d")
    audit = {
        "tamedia_objects": len(out), "srg_retrospective_objects": int(out.srg_yes.notna().sum()),
        "primary_two_wave_pairs": len(pairs), "directly_sourced_srg_before": len(old_latest),
        "directly_sourced_srg_after": len(old_latest) + len(pairs),
        "retrospective_srg_agreements": agreements,
        "retrospective_srg_conflicts": conflicts[["vote_key", "srg_yes", "yes_total"]].to_dict("records"),
        "primary_vs_retrospective_conflicts": pairs.merge(
            table[["vote_key", "srg_yes"]], on="vote_key"
        ).query("last_yes != srg_yes")[["vote_key", "last_yes", "srg_yes"]].to_dict("records"),
        "historical_version_verified": False, "strict_forecast_ready": False,
        "availability_tamedia": "reported last pre-vote poll; exact release time unverified",
    }
    return out, audit


def settlement_label(value):
    raw = re.sub(DATE_RE, "", str(value), flags=re.I)
    raw = re.sub(r"\b\d{1,2}\.\d{1,2}\.20\d{2}\b", "", raw)
    return SETTLEMENT.get(norm(raw))


def extract_settlement(tables, midpoint, wave):
    found = {}
    for path, sheet in tables:
        if not sheet or not isinstance(sheet[0], list):
            continue
        header = sheet[0]
        columns = {i: label_field(v) for i, v in enumerate(header) if label_field(v)}
        if set(columns.values()) != set(FIELDS):
            continue
        for row in sheet[1:]:
            if not row:
                continue
            label = settlement_label(row[0])
            stamp = date_de(str(row[0]))
            if label is None or (stamp != midpoint and not (stamp is None and wave == 1)):
                continue
            try:
                values = {field: float(str(row[i]).replace(",", ".")) for i, field in columns.items()}
            except (TypeError, ValueError, IndexError):
                continue
            if not all(0 <= v <= 100 for v in values.values()) or abs(sum(values.values()) - 100) > 2.01:
                continue
            found.setdefault(label, []).append({
                "region": label, "path": path, "header": header, "row": row, **values,
            })
    result = []
    for label in URBAN_LABELS:
        candidates = found.get(label, [])
        unique = {tuple(r[k] for k in FIELDS) for r in candidates}
        if len(unique) != 1:
            return []
        result.append(candidates[0])
    return result


def collect_settlement(record):
    try:
        url = record["chart_url"]
        if not url.startswith("https://e.infogram.com/"):
            raise ValueError("Unsupported chart")
        body, _ = fetch(url)
        payload, _ = json.JSONDecoder().raw_decode(body.decode("utf-8").split("window.infographicData=", 1)[1])
        tables = list(find_tables(payload))
        national = extract_national_rows(tables, "infogram", allow_bare_dates=url in NATIONAL_BARE_DATE_CHARTS)
        selected = [r for r in national if r["survey_midpoint"] == record["survey_midpoint"]]
        if not selected and len(national) == 1 and national[0]["survey_midpoint"] is None:
            selected = national
        if len(selected) != 1 or any(abs(selected[0][f] - float(record[f])) > 1e-8 for f in FIELDS):
            raise ValueError("National margin no longer reconciles")
        rows = extract_settlement(tables, record["survey_midpoint"], int(record["wave"]))
        if not rows:
            raise ValueError("No unique complete three-category settlement margin")
        return {"record": record, "rows": rows, "chart_sha256": sha(body),
                "chart_updated_at": payload.get("updatedAt")}
    except Exception as exc:
        return {"record": record, "error": str(exc)[:500]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    table = pd.read_csv(SOURCE / "leewas_latest_2016_2022.csv", dtype={"vote_key": str})
    pairs = pd.read_csv(SOURCE / "srg_missing_two_waves.csv", dtype={"vote_key": str})
    metadata = pd.read_parquet(ROOT / "data/processed/swissvotes/swissvotes_clean.parquet",
                               columns=["vote_key", "vote_date", "titel_kurz_d", "titel_off_d"])
    metadata["vote_key"] = metadata.vote_key.astype(str)
    metadata = metadata[metadata.vote_key.isin(TITLE_TOKENS)].copy()
    metadata["vote_date"] = pd.to_datetime(metadata.vote_date)
    old = load_expanded_polls(SSR, HIST)
    old["vote_key"] = old.vote_key.astype(str)
    out, audit = validate_national(table, pairs, metadata, old)
    out.to_csv(output / "national_latest.csv", index=False)
    pairs.to_csv(output / "national_pairs.csv", index=False)
    print("NATIONAL_AUDIT", json.dumps(audit, ensure_ascii=False), flush=True)

    national = pd.read_csv(SSR, dtype={"vote_key": str})
    national = national[national.vote_date.between("2021-01-01", "2022-12-31")]
    fields = ["vote_key", "vote_date", "wave", "survey_midpoint", "survey_start", "survey_end",
              "published_at", "source_url", "chart_url", "chart_title", *FIELDS]
    with ThreadPoolExecutor(max_workers=6) as pool:
        evidence = list(pool.map(collect_settlement, national[fields].to_dict("records")))
    result = []
    for entry in evidence:
        if "rows" not in entry:
            continue
        record = entry["record"]
        for row in entry["rows"]:
            result.append({
                **{k: v for k, v in record.items() if k not in FIELDS},
                **{k: row[k] for k in ("region", *FIELDS)},
                "yes_total": row["yes_certain"] + row["yes_lean"],
                "no_total": row["no_certain"] + row["no_lean"],
                "chart_sha256": entry["chart_sha256"],
                "chart_updated_at": entry["chart_updated_at"],
                "historical_version_verified": False,
            })
    settlement = pd.DataFrame(result)
    if not len(settlement):
        raise ValueError("No settlement observations collected")
    if settlement.duplicated(["vote_key", "wave", "region"]).any():
        raise ValueError("Duplicate settlement margins")
    if not settlement.groupby(["vote_key", "wave"]).region.nunique().eq(3).all():
        raise ValueError("Incomplete settlement margins")
    settlement.to_csv(output / "settlement_polls.csv", index=False)
    (output / "settlement_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    audit.update({"settlement_rows": len(settlement), "settlement_objects": int(settlement.vote_key.nunique()),
                  "settlement_waves": int(len(settlement)/3),
                  "settlement_rejects": [{"vote_key": e["record"]["vote_key"], "wave": e["record"]["wave"],
                                          "reason": e["error"]} for e in evidence if "error" in e]})
    audit["hashes"] = {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}
    (output / "manifest.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    print("ACQUISITION", json.dumps(audit, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
