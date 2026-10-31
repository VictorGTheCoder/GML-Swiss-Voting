"""Compare candidate ESPOP sources without extending the modeling dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.espop.collect_reuse import SNAPSHOTS, YEARS
from scripts.repertoire_communes.commune_crosswalk import load_mutations, resolve


def harmonize_counts(counts, source_codes, target_codes, from_date, to_date, mutations):
    """Return complete sums and exclusions, never distributing a split's counts.

    Source codes are the entire source snapshot, not just the supplied counts.
    A destination requires every constituent in every supplied year. Both counts
    must be finite and nonnegative. Missing/zero denominators remain explicit.
    """
    count_columns = ["population", "foreign"] + [c for c in counts if c.startswith("age_")]
    if counts.duplicated(["year", "code"]).any():
        raise ValueError("duplicate year/code")
    mapping = {}
    reasons = {}
    for code in source_codes:
        targets = {code}
        for day, _, rules in mutations:
            if from_date < day <= to_date:
                targets = set().union(*(rules.get(item, {item}) for item in targets))
                if len(targets) != 1:
                    reasons[code] = "unproven_split_or_transfer"
                    break
        if code not in reasons:
            target = next(iter(targets))
            if target in target_codes:
                mapping[code] = target
            else:
                reasons[code] = "unknown_target"
    constituents = defaultdict(set)
    for code, target in mapping.items():
        constituents[target].add(code)
    ambiguous_targets = set()
    for code in reasons:
        ambiguous_targets.update(resolve(code, from_date, to_date, mutations))
    excluded = []
    accepted = []
    for year, frame in counts.groupby("year"):
        for row in frame.to_dict("records"):
            if row["code"] not in mapping:
                excluded.append({"year": year, "code": row["code"],
                                 "reason": reasons.get(row["code"], "unknown_source")})
        for target, required in sorted(constituents.items(), key=lambda pair: int(pair[0])):
            # An excluded branching source may still contribute to this target.
            part = frame.loc[frame.code.isin(required)]
            if part.empty:
                continue
            values = part[count_columns]
            if target in ambiguous_targets or set(part.code) != required:
                reason = "incomplete_or_ambiguous_constituents"
            elif not np.isfinite(values).all().all() or (values < 0).any().any() or (part.foreign > part.population).any():
                reason = "invalid_counts"
            else:
                sums = values.sum().to_dict()
                total, foreign = sums["population"], sums["foreign"]
                accepted.append({"year": year, "code": target, **sums,
                                 "share_foreign": foreign / total if total > 0 else None,
                                 "constituents": "|".join(sorted(required, key=int))})
                continue
            excluded.append({"year": year, "code": target, "reason": reason})
    return (pd.DataFrame(accepted, columns=["year", "code", *count_columns,
                                          "share_foreign", "constituents"]),
            pd.DataFrame(excluded, columns=["year", "code", "reason"]))


def compare_population(rts, official):
    """Outer comparison: differences and missingness are findings, not failures."""
    for frame in (rts, official):
        if frame.duplicated(["year", "code"]).any():
            raise ValueError("duplicate year/code in comparison")
    columns = ["year", "code", "population", "foreign"]
    result = rts[columns].merge(official[columns], on=["year", "code"], how="outer",
                                suffixes=("_rts", "_ofs"), validate="one_to_one", indicator=True)
    # An entirely excluded official input leaves object-typed empty columns.
    # Coerce both sides before arithmetic and finiteness checks.
    for field in ("population", "foreign"):
        for source in ("rts", "ofs"):
            column = f"{field}_{source}"
            result[column] = pd.to_numeric(result[column], errors="coerce")
    for field in ("population", "foreign"):
        result[f"{field}_delta"] = result[f"{field}_rts"] - result[f"{field}_ofs"]
    for source in ("rts", "ofs"):
        denominator = result[f"population_{source}"]
        numerator = result[f"foreign_{source}"]
        valid = (np.isfinite(denominator) & np.isfinite(numerator) &
                 denominator.gt(0) & numerator.ge(0) & numerator.le(denominator))
        result[f"share_foreign_{source}"] = numerator / denominator.where(valid)
    result["status"] = "different"
    result.loc[result.population_delta.eq(0) & result.foreign_delta.eq(0), "status"] = "equal"
    result.loc[result._merge.eq("left_only"), "status"] = "missing_ofs"
    result.loc[result._merge.eq("right_only"), "status"] = "missing_rts"
    matched = result._merge.eq("both")
    result.loc[matched & result[[c for c in result if c.endswith(("_rts", "_ofs")) and not c.startswith("share_")]].isna().any(axis=1), "status"] = "missing_counts"
    for source in ("rts", "ofs"):
        denominator, numerator = result[f"population_{source}"], result[f"foreign_{source}"]
        nonfinite = ((denominator.notna() & ~np.isfinite(denominator)) |
                     (numerator.notna() & ~np.isfinite(numerator)))
        result.loc[nonfinite | denominator.lt(0) | numerator.lt(0) | numerator.gt(denominator), "status"] = "invalid_counts"
    return result.drop(columns="_merge").sort_values(["year", "code"]).reset_index(drop=True)


def snapshot(raw_dir, day):
    frame = pd.read_csv(raw_dir / f"snapshot_{day}.csv", dtype=str)
    return frame.loc[frame.Level.eq("3")].set_index("BfsCode").Name.to_dict()


def read_cube(path):
    frame = pd.read_csv(path, encoding="cp1252", dtype=str)
    value = frame.columns[-1]
    frame["code"] = frame.iloc[:, 1].str.extract(r"^\.+(\d+) ")[0].str.lstrip("0")
    frame["year"] = pd.to_numeric(frame.iloc[:, 0], errors="raise")
    nationality = next(c for c in frame if c.startswith("Nationalité"))
    frame["value"] = pd.to_numeric(frame[value], errors="coerce")
    pivot = frame.pivot(index=["year", "code"], columns=nationality, values="value")
    return pivot.rename(columns={"Nationalité (catégorie) - total": "population", "Étranger": "foreign"})[["population", "foreign"]].reset_index()


def read_rts(path):
    frame = pd.read_csv(path, dtype={"Code": str})
    frame = frame.loc[frame.Code.str.fullmatch(r"\d+")].copy()
    frame = frame.rename(columns={"Année": "year", "Code": "code", "Population_totale": "population", "Population_etrangere": "foreign"})
    frame["code"] = frame.code.str.lstrip("0")
    if frame.duplicated([c for c in ("year", "code", "Classe_age") if c in frame]).any():
        raise ValueError("duplicate RTS keys")
    return frame


def verify_manifest(raw_dir):
    """Refuse altered inputs rather than attaching an old collection time to them."""
    manifest = json.loads((raw_dir / "manifest.json").read_text())
    for source in manifest["sources"]:
        path = raw_dir / source["file"]
        if not path.resolve().is_relative_to(raw_dir.resolve()):
            raise ValueError("manifest file outside raw directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"source fingerprint mismatch: {source['file']}")
    return manifest


def read_census(path, year):
    frame = pd.read_excel(path, sheet_name=f"VZ RFP {year}", header=None)
    frame = frame.loc[pd.to_numeric(frame[0], errors="coerce").eq(year)].copy()
    values = frame[list(range(3, 12))].apply(pd.to_numeric, errors="coerce")
    result = pd.DataFrame({"year": year, "code": frame[1].astype(int).astype(str),
                           "population": values[3], "foreign": values[5],
                           "age_0_19": values[[6, 7]].sum(axis=1, min_count=2),
                           "age_20_39": values[8],
                           "age_20_64": values[[8, 9, 10]].sum(axis=1, min_count=3),
                           "age_65_plus": values[11]})
    complete = values.notna().all(axis=1)
    if (values.loc[complete, list(range(6, 12))].sum(axis=1) != values.loc[complete, 3]).any():
        raise ValueError("census age groups do not sum to population")
    return result


def audit(raw_dir: Path, output_dir: Path) -> dict:
    """Write reproducible comparisons, exclusions and coverage, offline.

    Outputs are research findings, never inputs to the V1 modeling pipeline.
    Source bytes must match their timestamped collection manifest.
    """
    manifest = verify_manifest(raw_dir)
    required = {
        "mutations.csv", "balance.csv", "balance_anomalies.csv", "statpop.csv",
        "census.xlsx", "zurich.csv",
        "rts_proportion_population_etrangere_etat_actuel.csv",
        "rts_proportion_population_etrangere_historique.csv",
        "rts_population_classes_age_historique.csv",
        *[f"snapshot_{day}.csv" for day in SNAPSHOTS],
    }
    missing = required - {source["file"] for source in manifest["sources"]}
    if missing:
        raise ValueError(f"unmanifested audit inputs: {', '.join(sorted(missing))}")
    mutations = load_mutations(raw_dir / "mutations.csv")
    raw_mutations = pd.read_csv(raw_dir / "mutations.csv", dtype=str)
    # Pin the administrative examples too: a refreshed export must not silently
    # remove an event or one of a complete merger's constituents.
    expected_events = {
        "1498": ("01.01.1990", {("253", "261")}),
        "3181": ("01.01.2011", {(code, "1630") for code in
                                 ("1602", "1608", "1618", "1617", "1623", "1624", "1619", "1622")}),
        "1472": ("01.01.1980", {("624", "624"), ("624", "629")}),
    }
    for number, (day, expected_edges) in expected_events.items():
        event = raw_mutations.loc[raw_mutations.MutationNumber.eq(number)]
        edges = set(zip(event.InitialCode, event.TerminalCode))
        if edges != expected_edges or set(event.MutationDate) != {day}:
            raise ValueError(f"mutation {number} missing or changed constituents")
    output_dir.mkdir(parents=True, exist_ok=True)
    target_day = date(2026, 1, 1)
    target = snapshot(raw_dir, str(target_day))
    source = snapshot(raw_dir, "2025-04-06")
    annual = read_rts(raw_dir / "rts_proportion_population_etrangere_etat_actuel.csv")
    annual = annual[["year", "code", "population", "foreign"]]
    balance = read_cube(raw_dir / "balance.csv")
    mapped, exclusions = harmonize_counts(balance, source, target, date(2025, 4, 6), target_day, mutations)
    comparisons = {"balance": compare_population(annual.loc[annual.year.isin(map(int, YEARS))], mapped)}
    statpop = read_cube(raw_dir / "statpop.csv")
    # Both current OFS cubes have the complete 2025-04-06 identifier set.
    # Harmonize subsequent mutations, rather than comparing different territories.
    # Matching identifiers alone does not certify historical territorial allocation.
    statpop_extras = sorted(set(statpop.code) - set(target), key=int)
    if set(statpop.code) != set(source):
        raise ValueError("STATPOP code set differs from the 2025-04-06 reference; reassess geography")
    statpop_mapped, statpop_exclusions = harmonize_counts(
        statpop, source, target, date(2025, 4, 6), target_day, mutations,
    )
    comparisons["statpop"] = compare_population(annual.loc[annual.year.isin([2010, 2011])], statpop_mapped)

    anomalies = annual.loc[annual.population.le(0) | ~np.isfinite(annual.population) |
                           ~np.isfinite(annual.foreign) | annual.foreign.lt(0) |
                           annual.foreign.gt(annual.population)].copy()
    official_anomalies = read_cube(raw_dir / "balance_anomalies.csv")
    anomalies = anomalies.merge(official_anomalies, on=["year", "code"], how="left",
                                suffixes=("_rts", "_ofs"), validate="one_to_one")
    anomalies["name"] = anomalies.code.map(target)
    anomalies["in_target_snapshot"] = anomalies.code.isin(target)
    anomalies["resolution"] = "unresolved_population_or_territory; excluded_from_shares"
    anomaly_periods = anomalies.groupby(["code", "name"], dropna=False).agg(
        first_year=("year", "min"), last_year=("year", "max"), observations=("year", "size"),
        official_zero=("population_ofs", lambda s: s.eq(0).sum()),
        official_missing=("population_ofs", lambda s: s.isna().sum()),
    ).reset_index()

    history = read_rts(raw_dir / "rts_proportion_population_etrangere_historique.csv")
    ages = read_rts(raw_dir / "rts_population_classes_age_historique.csv")
    census_comparisons, age_comparisons, census_exclusions = [], [], []
    for year, census_day in [(1980, "1980-12-02"), (1990, "1990-12-04"), (2000, "2000-12-05")]:
        census = read_census(raw_dir / "census.xlsx", year)
        official, dropped = harmonize_counts(census, snapshot(raw_dir, census_day), target,
                                             date.fromisoformat(census_day), target_day, mutations)
        census_exclusions.append(dropped)
        census_comparisons.append(compare_population(history.loc[history.year.eq(year)], official))
        denominator = history.loc[history.year.eq(year), ["year", "code", "population"]]
        for label, column in [("0-19", "age_0_19"), ("20-64", "age_20_64"), ("65+", "age_65_plus")]:
            observed = ages.loc[ages.year.eq(year) & ages.Classe_age.eq(label), ["year", "code", "Population"]]
            observed = observed.rename(columns={"Population": "foreign"}).merge(denominator, on=["year", "code"], how="outer", validate="one_to_one")
            reference = official[["year", "code", "population", column]].rename(columns={column: "foreign"})
            compared = compare_population(observed, reference)
            compared["age_group"] = label
            age_comparisons.append(compared.rename(columns={c: c.replace("foreign", "age") for c in compared if "foreign" in c}))
    comparisons["census"] = pd.concat(census_comparisons, ignore_index=True)
    age_comparison = pd.concat(age_comparisons, ignore_index=True)
    age_coverage = age_comparison.groupby(["year", "age_group"]).agg(
        rts_observations=("age_rts", "count"), ofs_comparable=("age_ofs", "count"),
        equal_counts=("age_delta", lambda s: s.eq(0).sum()),
        differing_counts=("age_delta", lambda s: (s.notna() & s.ne(0)).sum()),
        positive_rts_denominators=("population_rts", lambda s: s.gt(0).sum()),
    ).reset_index()
    unavailable = pd.DataFrame({"year": [1980, 1990, 2000], "age_group": "20-39",
                                "rts_observations": 0, "ofs_comparable": pd.NA,
                                "equal_counts": pd.NA, "differing_counts": pd.NA,
                                "positive_rts_denominators": pd.NA})
    age_coverage = pd.concat([age_coverage, unavailable], ignore_index=True).sort_values(["year", "age_group"])

    # Exact administrative examples, with snapshots bracketing each event.
    mutation_examples = []
    for number, before, after, kind in [("1498", "1989-12-31", "1990-01-01", "renumbering"),
                                       ("3181", "2010-12-31", "2011-01-01", "complete_merger"),
                                       ("1472", "1979-12-31", "1980-01-01", "split")]:
        event = raw_mutations.loc[raw_mutations.MutationNumber.eq(number)].copy()
        initial = snapshot(raw_dir, before)
        terminal = snapshot(raw_dir, after)
        if not set(event.InitialCode) <= set(initial) or not set(event.TerminalCode) <= set(terminal):
            raise ValueError(f"mutation {number} constituents not confirmed by snapshots")
        for row in event.to_dict("records"):
            destinations = resolve(row["InitialCode"], date.fromisoformat(before), date.fromisoformat(after), mutations)
            row.update({"kind": kind, "snapshot_constituents_verified": True,
                        "project_targets": "|".join(sorted(destinations, key=int)),
                        "decision": "exclude_unproven_allocation" if len(destinations) != 1 else "compatible_counts_only"})
            mutation_examples.append(row)

    zurich = pd.read_csv(raw_dir / "zurich.csv", dtype={"bfs": str}).rename(
        columns={"bfs": "code", "jahr": "year", "value": "population"})
    zurich = zurich.loc[zurich.year.isin(map(int, YEARS)), ["year", "code", "population"]]
    if zurich.duplicated(["year", "code"]).any():
        raise ValueError("duplicate Zurich year/code")
    zurich_comparison = zurich.merge(balance, on=["year", "code"], how="outer", suffixes=("_zurich", "_ofs"), validate="one_to_one")
    zurich_comparison["population_delta"] = zurich_comparison.population_zurich - zurich_comparison.population_ofs
    zurich_comparison["geography_status"] = "pinned_source_geography_not_certified_as_2026"

    for name, frame in comparisons.items():
        frame.to_csv(output_dir / f"comparison_{name}.csv", index=False)
    outputs = {"anomalies": anomalies, "anomaly_periods": anomaly_periods,
               "geography_exclusions": pd.concat([exclusions.assign(source="balance"),
                    statpop_exclusions.assign(source="statpop"),
                    *[frame.assign(source="census") for frame in census_exclusions]], ignore_index=True),
               "age_comparison": age_comparison, "age_coverage": age_coverage,
               "mutation_examples": pd.DataFrame(mutation_examples), "zurich_comparison": zurich_comparison}
    # A small, explicit sample for the published report, not a third-party dataset.
    sample_codes = {"1": "small", "261": "city", "5586": "city",
                    "1630": "merged", "1631": "merged", "1632": "merged"}
    outputs["population_sample"] = pd.concat([
        frame.loc[frame.code.isin(sample_codes)].assign(source=name)
        for name, frame in comparisons.items() if name != "census"
    ], ignore_index=True)
    outputs["population_sample"]["name"] = outputs["population_sample"].code.map(target)
    outputs["population_sample"]["sample_kind"] = outputs["population_sample"].code.map(sample_codes)
    outputs["census_differences"] = comparisons["census"].loc[
        comparisons["census"].status.eq("different")]
    outputs["statpop_2011_differences"] = comparisons["statpop"].loc[
        comparisons["statpop"].year.eq(2011) & comparisons["statpop"].status.eq("different")]
    outputs["zurich_status_counts"] = zurich_comparison.assign(
        status="different").assign(status=lambda frame: frame.status.mask(
            frame.population_delta.eq(0), "equal").mask(
            frame.population_zurich.isna(), "missing_zurich").mask(
            frame.population_ofs.isna(), "missing_ofs")).groupby(
                ["year", "status"]).size().rename("rows").reset_index()
    legacy_codes = set(annual.code) - set(target)
    outputs["legacy_comparison"] = compare_population(
        annual.loc[annual.code.isin(legacy_codes)],
        official_anomalies.loc[official_anomalies.code.isin(legacy_codes)],
    ).assign(geography_status="unresolved_legacy_code_even_when_counts_equal")
    # Links from problematic identifiers are evidence only; never infer successors by name.
    outputs["anomaly_mutation_evidence"] = raw_mutations.loc[
        raw_mutations.InitialCode.isin(anomalies.code) | raw_mutations.TerminalCode.isin(anomalies.code)]
    for name, frame in outputs.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)
    summary = {
        "annual_rows": len(annual), "annual_codes": annual.code.nunique(),
        "zero_denominators": int(annual.population.eq(0).sum()),
        "anomalous_codes": sorted(set(anomalies.code), key=int),
        "legacy_codes": sorted(set(annual.code) - set(target), key=int),
        "statpop_codes_not_in_target": statpop_extras,
        "comparison_status_counts": {name: frame.groupby(["year", "status"]).size().rename("rows").reset_index().to_dict("records") for name, frame in comparisons.items()},
        "age_coverage": age_coverage.astype(object).where(age_coverage.notna(), None).to_dict("records"),
        "historical_availability": "not_proven; no feature integration or V1 change",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (output_dir / "source_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/generated/espop_reuse"))
    args = parser.parse_args()
    print(json.dumps(audit(args.raw_dir, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
