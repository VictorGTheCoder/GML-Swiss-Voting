"""Targeted audit: are votes, STATPOP and National Council elections on the same territory?

Not a pipeline. It fetches (and caches under data/raw/geography/) a few official OFS
sources, then writes comparison tables to reports/geography_audit.md:

1. which commune state each source uses (code sets compared with register snapshots);
2. which communes of the vote geography (01.01.2026) are affected by mutations that
   happened after each source's reference date;
3. a sample of ~20 mutation cases followed across years in each source;
4. a bulk ratio scan over all communes: the vote cube's registered voters divided by
   STATPOP's Swiss residents aged 18+ (resp. the election cube's registered voters).
   The same territory gives a stable ratio; a different territory gives an offset or a jump.

Usage: python scripts/audit_municipality_geography.py [--refresh]
(first run downloads ~20 MB and takes ~10 min because STATPOP is queried in chunks)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from parse_votes import data_cube, parse_px_text
from votes_config import PROCESSED_PATH, RAW_DIR, REPORTS_DIR

CACHE = RAW_DIR / "geography"
REPORT_PATH = REPORTS_DIR / "geography_audit.md"
REGISTER_API = "https://www.agvchapp.bfs.admin.ch/api/communes"
PXWEB = "https://www.pxweb.bfs.admin.ch/api/v1/fr/{0}/{0}.px"
PX_DOWNLOAD = "https://www.pxweb.bfs.admin.ch/DownloadFile.aspx?file={0}"
STATPOP_TABLE = "px-x-0102010000_101"
ELECTORS_TABLE = "px-x-1702020000_101"
PARTIES_TABLE = "px-x-1702020000_105"

# Reference states stated in each cube's NOTE (verified below against register snapshots).
REFERENCE_DATES = {"votes": "2026-01-01", "statpop": "2025-04-06", "elections": "2023-07-01"}
ELECTION_DATES = {2011: "2011-10-23", 2015: "2015-10-18", 2019: "2019-10-20", 2023: "2023-10-22"}
PERIOD = (2013, 2024)
# Register step codes (Mutationsart): 21 creation, 23 renaming, 24 other district/canton,
# 26 change of territory, 29 abolition.
ABOLITION, TERRITORY = 29, 26

# Commune without own ballot box -> commune whose ballot box counts its votes (vote-cube NOTE;
# the note prints "629 Zäziwil", but Zäziwil is 0628 in the register and in the data).
SHARED_BALLOT_BOX = {"0389": "0383", "0408": "0410", "0535": "0553", "0629": "0628", "0877": "0888"}

# code in the vote geography (01.01.2026), label, mutation, year of mutation,
# related codes as they may appear in other sources (predecessors / partners).
CASES = [
    ("0001", "Aeugst am Albis", "control, unchanged", None, []),
    ("5586", "Lausanne", "control, unchanged (large)", None, []),
    ("1630", "Glarus Nord", "merger of 8 communes, new code", 2011, []),
    ("6487", "Val-de-Ruz", "merger of 15 communes, new code", 2013, []),
    ("0292", "Stammheim", "merger of 3 communes, new code", 2019, []),
    ("5399", "Verzasca", "merger + territory transfer from Lavertezzo/Cugnasco-Gerra", 2020, ["5112", "5138"]),
    ("3871", "Klosters", "renaming only (Klosters-Serneus)", 2021, []),
    ("2275", "Murten", "absorbs Clavaleyres, which changes canton BE -> FR", 2022, ["0661"]),
    ("0062", "Kloten", "partial territory exchange with Nürensdorf", 2024, ["0064"]),
    ("4021", "Baden", "absorbs Turgi, keeps code", 2024, ["4042"]),
    ("6812", "Basse-Vendline", "merger, new code", 2024, ["6773", "6775"]),
    ("6513", "Laténa", "merger of 4 communes, new code", 2025, ["6453", "6454", "6459", "6461"]),
    ("5395", "Lema", "merger of 5 communes on 06.04.2025, new code", 2025, ["5146", "5149", "5181", "5200", "5207"]),
    ("4095", "Brugg", "absorbs Villnachern on 01.01.2026, keeps code", 2026, ["4122"]),
    ("2056", "Fétigny-Ménières", "merger on 01.01.2026, new code", 2026, ["2016", "2027"]),
    ("6831", "Moutier", "canton change BE -> JU, code 0700 -> 6831", 2026, ["0700"]),
    ("2787", "Laufen", "canton change BE -> BL (1994)", 1994, []),
    ("0362", "Ittigen", "split from Bolligen (1983)", 1983, []),
    ("0868", "Jaberg", "shared ballot box with Kirchdorf until 2017", 2018, ["0872"]),
    ("9010", "ZH-Ausland-CH", "special unit of political statistics", None, []),
]


# ---------------------------------------------------------------- fetching (cached)

def _px_last_updated(table: str) -> str:
    """LAST-UPDATED stamp of an OFS cube, read from the PX header only (streamed)."""
    with requests.get(PX_DOWNLOAD.format(table), stream=True, timeout=120) as response:
        response.raise_for_status()
        head = b""
        for chunk in response.iter_content(1 << 16):
            head += chunk
            if b"\nDATA=" in head or len(head) > 5_000_000:
                break
    match = re.search(rb'LAST-UPDATED="([^"]+)"', head)
    return match.group(1).decode() if match else "unknown"


def _cached_csv(name: str, fetch, refresh: bool, source: str, table: str | None = None) -> pd.DataFrame:
    """Read a cached source, fetching it first if needed; a sidecar JSON records its provenance."""
    path = CACHE / name
    sidecar = path.with_suffix(".provenance.json")
    if refresh or not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        fetch().to_csv(path, index=False)
        sidecar.unlink(missing_ok=True)
    if not sidecar.exists():
        fetched_now = refresh or path.stat().st_mtime > pd.Timestamp.now().timestamp() - 60
        provenance = {
            "source": source, "ofs_table": table,
            "px_last_updated": _px_last_updated(table) if table else None,
            # For caches created before sidecars existed, the file time is the best available date.
            "retrieved_at_utc": pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").isoformat(timespec="seconds"),
            "retrieved_at_basis": "fetch" if fetched_now else "file modification time",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        sidecar.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return pd.read_csv(path, dtype={"code": str})


def provenance_table() -> pd.DataFrame:
    rows = [{"file": f.name.replace(".provenance.json", ".csv"), **json.loads(f.read_text(encoding="utf-8"))}
            for f in sorted(CACHE.glob("*.provenance.json"))]
    frame = pd.DataFrame(rows)
    frame["sha256"] = frame["sha256"].str[:12]
    return frame


def _get(url: str, **kwargs) -> requests.Response:
    response = requests.get(url, timeout=300, **kwargs)
    response.raise_for_status()
    return response


def register_mutations(refresh: bool) -> pd.DataFrame:
    def fetch() -> pd.DataFrame:
        text = _get(f"{REGISTER_API}/mutations", params={"startPeriod": "01-01-2010", "endPeriod": "01-01-2026"}).text
        return pd.read_csv(io.StringIO(text))
    mutations = _cached_csv("register_mutations_2010_2026.csv", fetch, refresh,
                            f"{REGISTER_API}/mutations?startPeriod=01-01-2010&endPeriod=01-01-2026")
    mutations["date"] = pd.to_datetime(mutations["MutationDate"], format="%d.%m.%Y")
    for column in ["InitialCode", "TerminalCode"]:
        mutations[column] = mutations[column].map("{:04d}".format)
    return mutations


def register_snapshot(date: str, refresh: bool) -> set[str]:
    day = pd.Timestamp(date).strftime("%d-%m-%Y")

    def fetch() -> pd.DataFrame:
        frame = pd.read_csv(io.StringIO(_get(f"{REGISTER_API}/snapshot", params={"date": day}).text))
        return frame[frame["Level"] == 3].assign(code=lambda f: f["BfsCode"].map("{:04d}".format))
    return set(_cached_csv(f"register_snapshot_{date}.csv", fetch, refresh,
                           f"{REGISTER_API}/snapshot?date={day}")["code"])


def _pxweb_query(table: str, selections: dict[str, list[str]]) -> pd.DataFrame:
    """PXWeb json-stat2 query -> long frame of codes + value (order taken from the response)."""
    payload = {"query": [{"code": c, "selection": {"filter": "item", "values": v}} for c, v in selections.items()],
               "response": {"format": "json-stat2"}}
    for attempt in range(1, 4):  # PXWeb occasionally stalls a request; retry instead of hanging
        try:
            response = requests.post(PXWEB.format(table), json=payload, timeout=120)
            response.raise_for_status()
            break
        except requests.RequestException as error:
            if attempt == 3:
                raise
            print(f"  PXWeb request failed ({error}); retry {attempt}/2", flush=True)
    cube = response.json()
    axes = []
    for dim in cube["id"]:
        index = cube["dimension"][dim]["category"]["index"]
        axes.append(sorted(index, key=index.get))
    grid = pd.MultiIndex.from_product(axes, names=cube["id"]).to_frame(index=False)
    values = cube["value"]
    grid["value"] = values if isinstance(values, list) else [values.get(str(i)) for i in range(len(grid))]
    return grid


def statpop_swiss_adults(refresh: bool) -> pd.DataFrame:
    """Permanent resident Swiss citizens aged 18+, per commune and year (31 Dec)."""
    def fetch() -> pd.DataFrame:
        meta = _get(PXWEB.format(STATPOP_TABLE)).json()["variables"]
        year, geo, ptype, nat, sex, age = (v["code"] for v in meta)
        codes = [c for c in meta[1]["values"] if re.fullmatch(r"\d{4}", c) and c != "8100"]
        chunks = []
        n_chunks = -(-len(codes) // 100)
        for start in range(0, len(codes), 100):  # the FSO firewall rejects large responses
            # Each chunk is cached so an interrupted run resumes where it stopped.
            chunk_path = CACHE / f"statpop_chunk_{start // 100:02d}.csv"
            if not chunk_path.exists():
                print(f"  STATPOP chunk {start // 100 + 1}/{n_chunks}", flush=True)
                _pxweb_query(STATPOP_TABLE, {
                    year: meta[0]["values"], geo: codes[start:start + 100], ptype: ["1"], nat: ["1"],
                    sex: ["-99999"], age: ["-99999"] + [str(a) for a in range(18)]}).to_csv(chunk_path, index=False)
            chunks.append(pd.read_csv(chunk_path, dtype=str).assign(value=lambda f: pd.to_numeric(f["value"])))
        raw = pd.concat(chunks, ignore_index=True)
        wide = raw.pivot_table(index=[year, geo], columns=age, values="value", aggfunc="first")
        minors = wide[[str(a) for a in range(18)]].sum(axis=1)
        return pd.DataFrame({"year": wide.index.get_level_values(0).astype(int),
                             "code": wide.index.get_level_values(1),
                             "swiss_adults": (wide["-99999"] - minors).to_numpy()})
    return _cached_csv("statpop_swiss_adults.csv", fetch, refresh, PXWEB.format(STATPOP_TABLE), STATPOP_TABLE)


def election_electors(refresh: bool) -> pd.DataFrame:
    def fetch() -> pd.DataFrame:
        meta = _get(PXWEB.format(ELECTORS_TABLE)).json()["variables"]
        geo, year, result = (v["code"] for v in meta)
        codes = [c for c in meta[0]["values"] if re.fullmatch(r"\d{4}", c)]
        raw = _pxweb_query(ELECTORS_TABLE, {geo: codes, year: ["2011", "2015", "2019", "2023"], result: ["1"]})
        return pd.DataFrame({"code": raw[geo], "year": raw[year].astype(int), "electors": raw["value"]})
    return _cached_csv("election_electors.csv", fetch, refresh, PXWEB.format(ELECTORS_TABLE), ELECTORS_TABLE)


def election_parties(refresh: bool) -> pd.DataFrame:
    """Party suffrages and party strength per commune and election (full PX cube)."""
    def fetch() -> pd.DataFrame:
        px = parse_px_text(_get(PX_DOWNLOAD.format(PARTIES_TABLE)).content.decode("latin-1"))  # truly ISO-8859-15
        dims = px.metadata["STUB"] + px.metadata["HEADING"]
        cube = data_cube(px, dims)
        grid = pd.MultiIndex.from_product([px.metadata[f'CODES("{d}")'] for d in dims[:3]],
                                          names=["code", "year", "party"]).to_frame(index=False)
        flat = cube.reshape(len(grid), -1)
        grid["suffrages"], grid["strength_pct"] = flat[:, 0], flat[:, 1]
        return grid[grid["code"].str.fullmatch(r"\d{4}")]
    return _cached_csv("election_parties.csv", fetch, refresh, PX_DOWNLOAD.format(PARTIES_TABLE), PARTIES_TABLE)


def vote_electorate() -> pd.DataFrame:
    votes = pd.read_parquet(PROCESSED_PATH, columns=["vote_date", "vote_id", "municipality_id", "eligible_voters"])
    # One value per commune and date (all objects of a date share the electorate).
    per_date = votes.groupby(["municipality_id", "vote_date"], observed=True)["eligible_voters"].max().reset_index()
    per_date = per_date.rename(columns={"municipality_id": "code"})
    per_date["code"] = per_date["code"].astype(str)
    return per_date


# ---------------------------------------------------------------- analyses

def reference_states(codes_by_source: dict[str, set[str]], refresh: bool) -> pd.DataFrame:
    rows = []
    for source, codes in codes_by_source.items():
        for date in sorted(set(REFERENCE_DATES.values())):
            snapshot = register_snapshot(date, refresh)
            rows.append({"source": source, "register_snapshot": date, "source_codes": len(codes),
                         "snapshot_codes": len(snapshot), "only_in_source": len(codes - snapshot),
                         "only_in_snapshot": len(snapshot - codes),
                         "exact_match": codes == snapshot})
    return pd.DataFrame(rows)


def gap_mutations(mutations: pd.DataFrame, after: str, until: str = REFERENCE_DATES["votes"]) -> pd.DataFrame:
    """Mutations changing territory or code in (after, until]; renamings and pure district moves ignored."""
    window = mutations[(mutations["date"] > after) & (mutations["date"] <= until)]
    relevant = window[window["InitialStep"].isin([ABOLITION, TERRITORY]) | window["TerminalStep"].isin([TERRITORY])
                      | (window["InitialCode"] != window["TerminalCode"])]
    rows = []
    for number, group in relevant.groupby("MutationNumber"):
        abolished = group["InitialStep"].eq(ABOLITION).any()
        code_change = (group["InitialCode"] != group["TerminalCode"]).any()
        kind = "merger" if abolished else "code change" if code_change else "territory exchange"
        for terminal, sub in group.groupby("TerminalCode"):
            rows.append({"mutation": number, "date": sub["date"].iloc[0].date(), "kind": kind,
                         "vote_geography_code": terminal, "name": sub["TerminalName"].iloc[0],
                         "codes_in_source": ", ".join(sorted(sub["InitialCode"].unique())),
                         "code_kept": terminal in set(sub["InitialCode"])})
    return pd.DataFrame(rows)


def last_vote_per_year(electorate: pd.DataFrame) -> pd.DataFrame:
    frame = electorate.assign(year=electorate["vote_date"].dt.year)
    last_dates = frame.groupby("year")["vote_date"].max()
    return frame[frame["vote_date"].isin(last_dates)][["code", "year", "vote_date", "eligible_voters"]]


def last_vote_before(electorate: pd.DataFrame, date: str) -> pd.DataFrame:
    before = electorate[electorate["vote_date"] < date]
    return before[before["vote_date"] == before["vote_date"].max()][["code", "vote_date", "eligible_voters"]]


def ratio_scan_statpop(electorate: pd.DataFrame, statpop: pd.DataFrame, canton: pd.Series) -> pd.DataFrame:
    """Naive same-code join; ratio = vote electorate (last vote of year) / STATPOP Swiss 18+ (31.12)."""
    joined = last_vote_per_year(electorate).merge(statpop, on=["code", "year"], how="left")
    joined = joined[joined["year"].between(*PERIOD)]
    joined["ratio"] = joined["eligible_voters"] / joined["swiss_adults"]
    joined["canton"] = joined["code"].map(canton)
    joined["canton_median"] = joined.groupby(["canton", "year"])["ratio"].transform("median")
    joined["log_dev"] = np.log(joined["ratio"] / joined["canton_median"])
    per_code = joined.sort_values("year").groupby("code").agg(
        years=("ratio", "count"), missing_in_statpop=("swiss_adults", lambda s: int(s.isna().sum())),
        median_ratio=("ratio", "median"), median_log_dev=("log_dev", "median"),
        max_year_jump=("ratio", lambda r: float(np.nanmax(np.abs(np.diff(np.log(r.to_numpy()))))) if r.notna().sum() > 1 else np.nan),
        electorate=("eligible_voters", "median"))
    return per_code


def ratio_scan_elections(electorate: pd.DataFrame, electors: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, date in ELECTION_DATES.items():
        if year < PERIOD[0] - 2:
            continue
        votes = last_vote_before(electorate, date)
        joined = votes.merge(electors[electors["year"] == year], on="code", how="outer", indicator=True)
        joined["year"] = year
        rows.append(joined)
    frame = pd.concat(rows, ignore_index=True)
    frame["ratio"] = frame["eligible_voters"] / frame["electors"]
    return frame


def case_table(electorate: pd.DataFrame, statpop: pd.DataFrame, electors: pd.DataFrame,
               vote_codes: set[str], statpop_codes: set[str], election_codes: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    yearly = last_vote_per_year(electorate)
    rows = []
    for code, name, mutation, year, related in CASES:
        years = {2013, 2024}
        if year and 2010 <= year <= 2026:
            years |= {year - 1, year, year + 1}
        for y in sorted(v for v in years if 2010 <= v <= 2025):
            vote = yearly[(yearly["code"] == code) & (yearly["year"] == y)]["eligible_voters"]
            pop = statpop[(statpop["code"] == code) & (statpop["year"] == y)]["swiss_adults"]
            related_pop = statpop[statpop["code"].isin(related) & (statpop["year"] == y)]["swiss_adults"]
            election_year = max((e for e in ELECTION_DATES if e <= y), default=None)
            elec = electors[(electors["code"] == code) & (electors["year"] == election_year)]["electors"]
            related_elec = electors[electors["code"].isin(related) & (electors["year"] == election_year)]["electors"]
            vote_value = vote.iloc[0] if len(vote) else np.nan
            pop_value = pop.iloc[0] if len(pop) else np.nan
            rows.append({
                "case": f"{name} ({code})", "mutation": mutation, "year": y,
                "votes_electorate": vote_value,
                "statpop_swiss18_same_code": pop_value,
                "statpop_swiss18_related": related_pop.sum() if len(related_pop) else np.nan,
                "ratio_votes/statpop": vote_value / pop_value if pop_value else np.nan,
                "election_year": election_year,
                "electors_same_code": elec.iloc[0] if len(elec) else np.nan,
                "electors_related": related_elec.sum() if len(related_elec) else np.nan,
            })
    table = pd.DataFrame(rows)
    presence = pd.DataFrame([{"case": f"{name} ({code})", "in_votes": code in vote_codes,
                              "in_statpop": code in statpop_codes, "in_elections": code in election_codes,
                              "related_in_statpop": ", ".join(c for c in related if c in statpop_codes) or "-",
                              "related_in_elections": ", ".join(c for c in related if c in election_codes) or "-"}
                             for code, name, _, _, related in CASES])
    return table, presence


def party_strength_identity(parties: pd.DataFrame) -> pd.Series:
    """strength = suffrages / sum(suffrages) per commune & year? If so, summing suffrages of
    predecessor communes and recomputing shares is an exact aggregation."""
    p = parties.dropna(subset=["suffrages"])
    total = p.groupby(["code", "year"])["suffrages"].transform("sum")
    recomputed = 100 * p["suffrages"] / total
    diff = (recomputed - p["strength_pct"]).abs()
    return pd.Series({"rows": len(p), "max_abs_diff_pp": diff.max(), "rows_diff_gt_0.01pp": int((diff > 0.01).sum())})


def territory_only_mutations(mutations: pd.DataFrame, years: tuple[int, int]) -> pd.DataFrame:
    """Territory exchanges between communes that all survive (no abolition in the same mutation)."""
    window = mutations[mutations["date"].dt.year.between(*years)]
    with_abolition = set(window.loc[window["InitialStep"] == ABOLITION, "MutationNumber"])
    exchanges = window[(window["InitialStep"] == TERRITORY) & ~window["MutationNumber"].isin(with_abolition)]
    return exchanges[["MutationNumber", "date", "InitialCode", "InitialName"]].drop_duplicates()


def mergers_in_period(mutations: pd.DataFrame) -> set[str]:
    window = mutations[mutations["date"].dt.year.between(*PERIOD) & (mutations["InitialStep"] == ABOLITION)]
    return set(window["TerminalCode"])


def impact(gaps: dict[str, pd.DataFrame], mutations: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    votes = pd.read_parquet(PROCESSED_PATH, columns=["vote_date", "municipality_id", "is_special_unit", "is_tiebreak_question"])
    votes["municipality_id"] = votes["municipality_id"].astype(str)
    period = votes[votes["vote_date"].dt.year.between(*PERIOD) & ~votes["is_tiebreak_question"]]
    n_rows, n_codes = len(period), period["municipality_id"].nunique()
    exchanges = territory_only_mutations(mutations, (PERIOD[0], PERIOD[1] + 1))
    groups = {
        "A. special units (not communes, no STATPOP)": set(period.loc[period["is_special_unit"], "municipality_id"]),
        "B. mutation after STATPOP state (06.04.2025): needs code map / predecessor sum": set(gaps["statpop"]["vote_geography_code"]),
        "C. mutation after elections state (01.07.2023): needs code map / predecessor sum": set(gaps["elections"]["vote_geography_code"]),
        "D. counts the ballots of a commune without own ballot box": set(SHARED_BALLOT_BOX.values()),
        "E. partial territory exchange 2013-2025 (communes survive)": set(exchanges["InitialCode"]),
        "F. created by a merger 2013-2024, consistent in all sources (information)": mergers_in_period(mutations),
    }
    groups["union A-E (need a rule)"] = set().union(*(v for k, v in groups.items() if k[0] in "ABCDE"))
    rows = []
    for label, codes in groups.items():
        mask = period["municipality_id"].isin(codes)
        rows.append({"group": label, "communes": int(period.loc[mask, "municipality_id"].nunique()),
                     "share_communes": period.loc[mask, "municipality_id"].nunique() / n_codes,
                     "rows_2013_2024": int(mask.sum()), "share_rows": mask.sum() / n_rows})
    return pd.DataFrame(rows), n_rows, n_codes


def predecessor_sums(gaps: dict[str, pd.DataFrame], electorate: pd.DataFrame, statpop: pd.DataFrame,
                     electors: pd.DataFrame) -> pd.DataFrame:
    """For communes mutated after a source's state: vote electorate (vote geography) vs the sum of
    the source's values over the codes that make up the commune. Ratio ~ same as for unchanged
    communes => the vote cube's history is the sum of the predecessors (reconstruction, case A)."""
    rows = []
    yearly = last_vote_per_year(electorate)
    for _, gap in gaps["elections"].iterrows():
        parts = gap["codes_in_source"].split(", ")
        for year, date in ELECTION_DATES.items():
            if year < 2015:
                continue
            vote = last_vote_before(electorate, date)
            vote = vote.loc[vote["code"] == gap["vote_geography_code"], "eligible_voters"]
            part_values = electors[(electors["code"].isin(parts)) & (electors["year"] == year)]["electors"]
            statpop_merged = statpop[(statpop["code"] == gap["vote_geography_code"]) & (statpop["year"] == year)]["swiss_adults"]
            rows.append({"source": "elections", "vote_geography_code": gap["vote_geography_code"], "name": gap["name"],
                         "kind": gap["kind"], "year": year, "codes_summed": gap["codes_in_source"],
                         "votes_electorate": vote.iloc[0] if len(vote) else np.nan,
                         "sum_of_parts": part_values.sum() if len(part_values) == len(parts) else np.nan,
                         "statpop_same_code_2025_state": statpop_merged.iloc[0] if len(statpop_merged) else np.nan})
    for _, gap in gaps["statpop"].iterrows():
        parts = gap["codes_in_source"].split(", ")
        for year in (2015, 2019, 2023):
            vote = yearly[(yearly["code"] == gap["vote_geography_code"]) & (yearly["year"] == year)]["eligible_voters"]
            part_values = statpop[(statpop["code"].isin(parts)) & (statpop["year"] == year)]["swiss_adults"]
            rows.append({"source": "statpop", "vote_geography_code": gap["vote_geography_code"], "name": gap["name"],
                         "kind": gap["kind"], "year": year, "codes_summed": gap["codes_in_source"],
                         "votes_electorate": vote.iloc[0] if len(vote) else np.nan,
                         "sum_of_parts": part_values.sum() if len(part_values) == len(parts) else np.nan})
    frame = pd.DataFrame(rows)
    frame["ratio_votes/sum"] = frame["votes_electorate"] / frame["sum_of_parts"]
    return frame


def shared_ballot_box_check(electorate: pd.DataFrame, statpop: pd.DataFrame, electors: pd.DataFrame) -> pd.DataFrame:
    rows = []
    yearly = last_vote_per_year(electorate)
    for silent, host in SHARED_BALLOT_BOX.items():
        for year in (2015, 2023):
            def value(frame, code, column):
                hit = frame[(frame["code"] == code) & (frame["year"] == year)][column]
                return hit.iloc[0] if len(hit) else np.nan
            rows.append({"silent_commune": silent, "host_commune": host, "year": year,
                         "votes_host": value(yearly, host, "eligible_voters"),
                         "votes_silent": value(yearly, silent, "eligible_voters"),
                         "electors_host": value(electors, host, "electors"),
                         "electors_silent": value(electors, silent, "electors"),
                         "statpop_host": value(statpop, host, "swiss_adults"),
                         "statpop_silent": value(statpop, silent, "swiss_adults")})
    frame = pd.DataFrame(rows)
    frame["ratio_votes/statpop_host"] = frame["votes_host"] / frame["statpop_host"]
    frame["ratio_votes/statpop_host+silent"] = frame["votes_host"] / (frame["statpop_host"] + frame["statpop_silent"])
    return frame


# ---------------------------------------------------------------- report

def _md(frame: pd.DataFrame, index: bool = False) -> str:
    return frame.to_markdown(index=index, floatfmt=".4g")


def build_report(refresh: bool) -> str:
    mutations = register_mutations(refresh)
    statpop = statpop_swiss_adults(refresh)
    electors = election_electors(refresh)
    parties = election_parties(refresh)
    electorate = vote_electorate()

    votes_meta = pd.read_parquet(PROCESSED_PATH, columns=["municipality_id", "canton", "is_special_unit"]).drop_duplicates()
    votes_meta["municipality_id"] = votes_meta["municipality_id"].astype(str)
    canton = votes_meta.set_index("municipality_id")["canton"].astype(str)
    vote_codes = set(votes_meta.loc[~votes_meta["is_special_unit"], "municipality_id"])
    statpop_codes = set(statpop["code"])
    election_codes = {c for c in parties["code"].unique() if int(c) < 9000}
    elector_codes = {c for c in electors["code"].unique() if int(c) < 9000}
    # Five 'shared ballot box' communes are in the vote cube's code list but never have results.
    vote_codes_listed = vote_codes | {"0389", "0408", "0535", "0629", "0877"}

    states = reference_states({"votes (listed codes, regular)": vote_codes_listed, "statpop": statpop_codes,
                               "elections parties (regular)": election_codes,
                               "elections electors (regular)": elector_codes}, refresh)
    gaps = {"statpop": gap_mutations(mutations, REFERENCE_DATES["statpop"]),
            "elections": gap_mutations(mutations, REFERENCE_DATES["elections"])}
    cases, presence = case_table(electorate, statpop, electors, vote_codes, statpop_codes, election_codes)

    scan = ratio_scan_statpop(electorate, statpop, canton)
    explained = set(gaps["statpop"]["vote_geography_code"])
    scan["explained_by_gap_mutation"] = scan.index.isin(explained)
    flagged = scan[(scan["median_log_dev"].abs() > 0.08) | (scan["max_year_jump"] > 0.08) | (scan["missing_in_statpop"] > 0)]
    flagged = flagged.join(canton.rename("canton")).sort_values("electorate", ascending=False)
    ok = scan[~scan.index.isin(flagged.index)]

    election_scan = ratio_scan_elections(electorate, electors)
    regular = election_scan[election_scan["code"].map(lambda c: int(c) < 9000)]
    by_year = regular.groupby("year").agg(
        vote_date=("vote_date", "max"), matched=("_merge", lambda m: int((m == "both").sum())),
        only_votes=("_merge", lambda m: int((m == "left_only").sum())),
        only_elections=("_merge", lambda m: int((m == "right_only").sum())),
        median_ratio=("ratio", "median"), p01=("ratio", lambda r: r.quantile(0.01)), p99=("ratio", lambda r: r.quantile(0.99)))
    election_outliers = regular[(regular["ratio"] - 1).abs() > 0.08].sort_values("electors", ascending=False)

    impact_table, n_rows, n_codes = impact(gaps, mutations)
    sums = predecessor_sums(gaps, electorate, statpop, electors)
    urns = shared_ballot_box_check(electorate, statpop, electors)
    merged = mergers_in_period(mutations)
    merged_scan = scan[scan.index.isin(merged)]
    exchanges = territory_only_mutations(mutations, (PERIOD[0], PERIOD[1] + 1))
    identity = party_strength_identity(parties)

    sections = [
        "# Geography audit tables (generated)",
        "*Generated by `scripts/audit_municipality_geography.py`. Interpretation: "
        "`docs/geography_compatibility_audit.md`.*",
        "## 0. Provenance of the cached sources (data/raw/geography/)", _md(provenance_table()),
        "## 1. Commune state of each source (code sets vs official register snapshots)", _md(states),
        "## 2. Mutations after each source's reference state, up to the vote state 01.01.2026",
        "### STATPOP (state 06.04.2025)", _md(gaps["statpop"]),
        "### Elections (state 01.07.2023)", _md(gaps["elections"]),
        "## 3. Sample cases", "### Presence of the vote-geography code in each source", _md(presence),
        "### Values across years",
        "`votes_electorate`: registered voters at the last vote of the year (vote cube, 2026 geography). "
        "`statpop_swiss18_*`: Swiss permanent residents aged 18+ on 31.12 (STATPOP, 2025 geography). "
        "`electors_*`: registered voters at the last National Council election <= year (2023 geography). "
        "`*_related`: sum over the predecessor/partner codes listed in the script.", _md(cases),
        "## 4. Bulk ratio scan: vote electorate / STATPOP Swiss 18+ (same code, 2013-2024)",
        f"- communes scanned: {len(scan)}; not flagged: {len(ok)}",
        f"- among non-flagged communes: median |deviation from canton median| "
        f"{ok['median_log_dev'].abs().median():.3%}, median max year-to-year jump {ok['max_year_jump'].median():.3%}",
        "- flagged if |median log-deviation from canton median| > 8 %, a year-to-year jump > 8 %, or missing in STATPOP:",
        _md(flagged.reset_index()),
        "## 5. Vote electorate (last vote before the election) / election registered voters (same code)",
        _md(by_year, index=True), "Communes with |ratio - 1| > 8 %:",
        _md(election_outliers[["code", "year", "vote_date", "eligible_voters", "electors", "ratio", "_merge"]].head(40)),
        "## 6. Predecessor sums for communes mutated after a source's state",
        "`statpop_same_code_2025_state`: for elections-gap communes merged before 06.04.2025, STATPOP already "
        "publishes the merged commune back to 2010; compare it with the elections sum of the old communes.",
        _md(sums),
        "## 7. Communes without own ballot box",
        "`votes_silent` / `electors_silent` are empty: the votes are counted in the host commune's row.",
        _md(urns),
        f"## 8. Communes created by a merger in {PERIOD[0]}-{PERIOD[1]} (both sources reconstruct)",
        f"{len(merged)} vote-geography communes; {len(merged_scan)} scanned; flagged by the ratio scan: "
        f"{int(merged_scan.index.isin(flagged.index).sum())} "
        f"({', '.join(sorted(merged_scan.index[merged_scan.index.isin(flagged.index)])) or '-'}). "
        f"Median |deviation| {merged_scan['median_log_dev'].abs().median():.3%}, median max year jump "
        f"{merged_scan['max_year_jump'].median():.3%} (all communes: {scan['max_year_jump'].median():.3%}).",
        f"## 9. Territory exchanges between surviving communes {PERIOD[0]}-{PERIOD[1] + 1}", _md(exchanges),
        "## 10. Party strength = party suffrages / total suffrages?", _md(identity.to_frame("value"), index=True),
        "## 11. Impact on the 2013-2024 vote rows (regular + special units, tie-break questions excluded)",
        f"Total: {n_rows:,} rows, {n_codes} units.", _md(impact_table),
    ]
    return "\n\n".join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit geographic compatibility of votes, STATPOP and elections")
    parser.add_argument("--refresh", action="store_true", help="re-download cached sources")
    args = parser.parse_args()
    if args.refresh:
        for chunk in CACHE.glob("statpop_chunk_*.csv"):
            chunk.unlink()
    report = build_report(args.refresh)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
