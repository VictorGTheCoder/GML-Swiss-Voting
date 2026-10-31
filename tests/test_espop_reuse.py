"""Public audit outputs: conservative geography, counts and explicit absences."""

import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.espop.audit_reuse import compare_population, harmonize_counts


@pytest.fixture
def audit_inputs(tmp_path):
    """Invented source-format files exercise the offline command without redistribution."""
    raw = tmp_path / "raw"
    raw.mkdir()
    years = [1981, 1990, 2000, 2009, 2010, 2011]
    events = [
        ("1498", "01.01.1990", "253", "261"),
        *[("3181", "01.01.2011", code, "1630") for code in
          ("1602", "1608", "1618", "1617", "1623", "1624", "1619", "1622")],
        ("1472", "01.01.1980", "624", "624"),
        ("1472", "01.01.1980", "624", "629"),
        ("9999", "01.01.2020", "10", "12"),
        ("9999", "01.01.2020", "11", "12"),
    ]
    pd.DataFrame(events, columns=["MutationNumber", "MutationDate", "InitialCode", "TerminalCode"]).to_csv(raw / "mutations.csv", index=False)
    snapshots = {
        "2025-04-06": ["1", "261", "12"], "2026-01-01": ["1", "261", "12"],
        "1980-12-02": ["1", "253", "10", "11"],
        "1990-12-04": ["1", "261", "10", "11"],
        "2000-12-05": ["1", "261", "10", "11"],
        "1989-12-31": ["253"], "1990-01-01": ["261"],
        "2010-12-31": [row[2] for row in events if row[0] == "3181"],
        "2011-01-01": ["1630"], "1979-12-31": ["624"], "1980-01-01": ["624", "629"],
    }
    for day, codes in snapshots.items():
        pd.DataFrame({"Level": "3", "BfsCode": codes, "Name": [f"Fixture {code}" for code in codes]}).to_csv(raw / f"snapshot_{day}.csv", index=False)

    annual = [(year, code, total, foreign) for year in years for code, total, foreign in
              [("1", 100, 10), ("261", 200, 40), ("12", 400, 100), ("4505", 0, 0)]]
    pd.DataFrame(annual, columns=["Année", "Code", "Population_totale", "Population_etrangere"]).to_csv(raw / "rts_proportion_population_etrangere_etat_actuel.csv", index=False)

    def cube(name, rows):
        data = [(year, f"......{int(code):04d} Fixture", nationality, value)
                for year, code, total, foreign in rows
                for nationality, value in [("Nationalité (catégorie) - total", total), ("Étranger", foreign)]]
        pd.DataFrame(data, columns=["Année", "Commune", "Nationalité (catégorie)", "Valeur"]).to_csv(raw / name, index=False, encoding="cp1252")

    cube("balance.csv", [row for row in annual if row[1] != "4505"])
    cube("balance_anomalies.csv", [row for row in annual if row[1] == "4505"])
    cube("statpop.csv", [(year, code, 104 if year == 2010 and code == "1" else total,
                          14 if year == 2010 and code == "1" else foreign)
                         for year, code, total, foreign in annual if year in (2010, 2011) and code != "4505"])
    history = [(year, code, total, foreign) for year in (1980, 1990, 2000)
               for code, total, foreign in [("1", 100, 10), ("261", 200, 40), ("12", 400, 100)]]
    pd.DataFrame(history, columns=["Année", "Code", "Population_totale", "Population_etrangere"]).to_csv(raw / "rts_proportion_population_etrangere_historique.csv", index=False)
    ages = [(year, code, label, value) for year, code, total, _ in history
            for label, value in [("0-19", total // 5), ("20-64", total * 7 // 10), ("65+", total // 10)]
            if (year, code, label) != (2000, "1", "65+")]
    pd.DataFrame(ages, columns=["Année", "Code", "Classe_age", "Population"]).to_csv(raw / "rts_population_classes_age_historique.csv", index=False)
    with pd.ExcelWriter(raw / "census.xlsx") as writer:
        for year in (1980, 1990, 2000):
            rows = [(year, int(code), f"Fixture {code}", total, total - foreign, foreign,
                     total // 10, total // 10, total * 3 // 10, total // 5, total // 5, total // 10)
                    for code, total, foreign in [("1", 100, 10), ("253" if year == 1980 else "261", 200, 40), ("10", 100, 10), ("11", 300, 90)]]
            pd.DataFrame(rows).to_excel(writer, sheet_name=f"VZ RFP {year}", header=False, index=False)
    pd.DataFrame([(year, code, total) for year, code, total, _ in annual if code != "4505"],
                 columns=["jahr", "bfs", "value"]).to_csv(raw / "zurich.csv", index=False)
    sources = [{"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "url": "https://example.invalid/synthetic-fixture", "retrieved_at_utc": "2026-10-27T00:00:00+00:00",
                "territorial_reference": "synthetic snapshots", "population_definition": "invented counts"}
               for path in sorted(raw.iterdir())]
    (raw / "manifest.json").write_text(json.dumps({"sources": sources}))
    return raw


def run_audit(raw, output):
    return subprocess.run(
        [sys.executable, "-m", "scripts.espop.audit_reuse", "--raw-dir", str(raw),
         "--output-dir", str(output)], capture_output=True, text=True,
    )


def refresh_fingerprint(raw, path):
    manifest_path = raw / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    next(source for source in manifest["sources"] if source["file"] == path.name)["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))


def test_offline_command_publishes_comparisons_coverage_and_geography(audit_inputs, tmp_path):
    output = tmp_path / "output"
    result = run_audit(audit_inputs, output)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert json.loads((output / "summary.json").read_text()) == summary
    assert summary["annual_rows"] == 24
    assert summary["zero_denominators"] == 6
    assert summary["legacy_codes"] == ["4505"]
    assert summary["historical_availability"].startswith("not_proven")
    assert json.loads((output / "source_manifest.json").read_text()) == json.loads((audit_inputs / "manifest.json").read_text())
    statpop = pd.read_csv(output / "comparison_statpop.csv", dtype={"code": str}).set_index(["year", "code"])
    assert statpop.loc[(2010, "1"), ["population_delta", "foreign_delta", "status"]].tolist() == [-4, -4, "different"]
    assert statpop.loc[(2011, "1"), "status"] == "equal"
    census = pd.read_csv(output / "comparison_census.csv", dtype={"code": str}).set_index(["year", "code"])
    assert census.loc[(1980, "12"), ["population_ofs", "foreign_ofs", "share_foreign_ofs", "status"]].tolist() == [400, 100, 0.25, "equal"]
    assert census.loc[(1980, "261"), "status"] == "equal"
    coverage = pd.read_csv(output / "age_coverage.csv").set_index(["year", "age_group"])
    assert coverage.loc[(1980, "20-64"), ["rts_observations", "equal_counts"]].tolist() == [3, 3]
    assert coverage.loc[(2000, "65+"), ["rts_observations", "ofs_comparable"]].tolist() == [2, 3]
    assert coverage.loc[(1980, "20-39"), "rts_observations"] == 0
    anomalies = pd.read_csv(output / "anomalies.csv")
    assert len(anomalies) == 6
    assert not anomalies.in_target_snapshot.any()
    assert anomalies.resolution.str.contains("unresolved").all()
    legacy = pd.read_csv(output / "legacy_comparison.csv")
    assert legacy.status.eq("equal").all()
    assert legacy.share_foreign_rts.isna().all()
    mutations = pd.read_csv(output / "mutation_examples.csv")
    assert mutations.snapshot_constituents_verified.all()
    assert mutations.loc[mutations.kind.eq("split"), "decision"].eq("exclude_unproven_allocation").all()


def test_command_excludes_nonfinite_official_counts(audit_inputs, tmp_path):
    path = audit_inputs / "balance.csv"
    frame = pd.read_csv(path, encoding="cp1252")
    frame["Valeur"] = frame.Valeur.astype(float)
    frame.loc[frame.Commune.str.contains("0001") & frame.Année.eq(1981), "Valeur"] = float("inf")
    frame.to_csv(path, index=False, encoding="cp1252")
    refresh_fingerprint(audit_inputs, path)
    output = tmp_path / "output"
    result = run_audit(audit_inputs, output)
    assert result.returncode == 0, result.stderr
    compared = pd.read_csv(output / "comparison_balance.csv", dtype={"code": str}).set_index(["year", "code"])
    assert compared.loc[(1981, "1"), "status"] == "missing_ofs"
    excluded = pd.read_csv(output / "geography_exclusions.csv", dtype={"code": str})
    assert excluded.loc[excluded.source.eq("balance") & excluded.year.eq(1981) & excluded.code.eq("1"), "reason"].tolist() == ["invalid_counts"]


def test_command_never_computes_a_share_from_nonfinite_rts_counts(audit_inputs, tmp_path):
    path = audit_inputs / "rts_proportion_population_etrangere_etat_actuel.csv"
    frame = pd.read_csv(path)
    frame["Population_totale"] = frame.Population_totale.astype(float)
    frame.loc[frame.Code.eq(1) & frame.Année.eq(1981), "Population_totale"] = float("inf")
    frame.to_csv(path, index=False)
    refresh_fingerprint(audit_inputs, path)
    output = tmp_path / "output"
    result = run_audit(audit_inputs, output)
    assert result.returncode == 0, result.stderr
    compared = pd.read_csv(output / "comparison_balance.csv", dtype={"code": str}).set_index(["year", "code"])
    assert compared.loc[(1981, "1"), "status"] == "invalid_counts"
    assert pd.isna(compared.loc[(1981, "1"), "share_foreign_rts"])
    anomalies = pd.read_csv(output / "anomalies.csv", dtype={"code": str})
    assert len(anomalies.loc[anomalies.year.eq(1981) & anomalies.code.eq("1")]) == 1


def test_command_excludes_split_counts_even_after_destinations_merge(audit_inputs, tmp_path):
    path = audit_inputs / "mutations.csv"
    # Both branches later reach 12; that does not prove a historical allocation.
    with path.open("a") as handle:
        handle.write("9998,01.01.2010,10,10\n9998,01.01.2010,10,11\n")
    refresh_fingerprint(audit_inputs, path)
    output = tmp_path / "output"
    result = run_audit(audit_inputs, output)
    assert result.returncode == 0, result.stderr
    census = pd.read_csv(output / "comparison_census.csv", dtype={"code": str})
    assert census.loc[census.code.eq("12"), "status"].tolist() == ["missing_ofs"] * 3
    excluded = pd.read_csv(output / "geography_exclusions.csv", dtype={"code": str})
    assert excluded.loc[excluded.source.eq("census") & excluded.code.eq("10"), "reason"].tolist() == ["unproven_split_or_transfer"] * 3
    assert excluded.loc[excluded.source.eq("census") & excluded.code.eq("12"), "reason"].tolist() == ["incomplete_or_ambiguous_constituents"] * 3


def test_complete_merger_sums_counts_before_computing_share():
    counts = pd.DataFrame({"code": ["1", "2"], "year": [2000, 2000],
                           "population": [100, 300], "foreign": [10, 90]})
    mutations = [(date(2001, 1, 1), 1, {"1": {"3"}, "2": {"3"}})]
    result, excluded = harmonize_counts(
        counts, {"1", "2"}, {"3"}, date(2000, 12, 31), date(2001, 1, 1), mutations,
    )
    assert excluded.empty
    assert result[["code", "population", "foreign", "share_foreign"]].to_dict("records") == [
        {"code": "3", "population": 400, "foreign": 100, "share_foreign": 0.25},
    ]


@pytest.mark.parametrize("problem", ["missing", "null", "split"])
def test_unproven_constituents_never_produce_a_plausible_merger(problem):
    counts = pd.DataFrame({"code": ["1", "2"], "year": [2000, 2000],
                           "population": [100, 300], "foreign": [10, 90]})
    mutations = [(date(2001, 1, 1), 1, {"1": {"3"}, "2": {"3"}})]
    if problem == "missing":
        counts = counts.iloc[:1]
    elif problem == "null":
        counts.loc[1, "population"] = float("nan")
    else:
        mutations[0][2]["2"] = {"3", "4"}
    result, excluded = harmonize_counts(
        counts, {"1", "2"}, {"3", "4"}, date(2000, 12, 31), date(2001, 1, 1), mutations,
    )
    assert result.empty
    assert not excluded.empty


def test_zero_denominator_and_unknown_source_remain_explicit():
    counts = pd.DataFrame({"code": ["1", "4505"], "year": [2000, 2000],
                           "population": [0, 10], "foreign": [0, 2]})
    result, excluded = harmonize_counts(counts, {"1"}, {"1"}, date(2000, 1, 1), date(2001, 1, 1), [])
    assert pd.isna(result.iloc[0].share_foreign)
    assert excluded.to_dict("records") == [{"year": 2000, "code": "4505", "reason": "unknown_source"}]


def test_comparison_preserves_absences_and_the_2010_transition_difference():
    rts = pd.DataFrame({"year": [2010, 2010], "code": ["1", "2"],
                        "population": [1820, 0], "foreign": [221, 0]})
    official = pd.DataFrame({"year": [2010, 2010], "code": ["1", "3"],
                             "population": [1824, 40], "foreign": [225, 4]})
    result = compare_population(rts, official).set_index("code")
    assert result.loc["1", "population_delta"] == -4
    assert result.loc["1", "foreign_delta"] == -4
    assert result.loc["1", "status"] == "different"
    assert result.loc["2", "status"] == "missing_ofs"
    assert result.loc["3", "status"] == "missing_rts"
    assert pd.isna(result.loc["2", "share_foreign_rts"])


def test_duplicate_comparison_keys_are_rejected():
    frame = pd.DataFrame({"year": [2000, 2000], "code": ["1", "1"],
                          "population": [10, 20], "foreign": [1, 2]})
    with pytest.raises(ValueError, match="duplicate"):
        compare_population(frame, frame)


def test_command_refuses_modified_sources_before_writing_outputs(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "source.csv").write_bytes(b"modified bytes")
    (raw / "manifest.json").write_text(json.dumps({"sources": [{
        "file": "source.csv", "sha256": hashlib.sha256(b"original bytes").hexdigest(),
    }]}))
    output = tmp_path / "output"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.espop.audit_reuse", "--raw-dir", str(raw),
         "--output-dir", str(output)], capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "source fingerprint mismatch: source.csv" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("foreign", [-1, 11])
def test_invalid_numerators_never_become_shares(foreign):
    frame = pd.DataFrame({"year": [2000], "code": ["1"],
                          "population": [10], "foreign": [foreign]})
    result = compare_population(frame, frame)
    assert pd.isna(result.loc[0, "share_foreign_rts"])
    assert result.loc[0, "status"] == "invalid_counts"


def test_command_requires_manifest_for_every_audit_input(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "manifest.json").write_text(json.dumps({"sources": []}))
    output = tmp_path / "output"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.espop.audit_reuse", "--raw-dir", str(raw),
         "--output-dir", str(output)], capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "unmanifested audit inputs" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("edges", [[], [("253", "999")]])
def test_command_rejects_missing_or_changed_required_mutation(tmp_path, edges):
    # Use the published input inventory; no downloaded source data is needed.
    inventory = json.loads(
        (Path(__file__).parents[1] /
         "docs/datasets/espop/reuse_sources_2026-10-27.json").read_text()
    )
    raw = tmp_path / "raw"
    raw.mkdir()
    sources = []
    for source in inventory["sources"]:
        content = b"unused in this rejected audit"
        if source["file"] == "mutations.csv":
            content = ("MutationNumber,MutationDate,InitialCode,TerminalCode\n" +
                       "".join(f"1498,01.01.1990,{initial},{terminal}\n"
                               for initial, terminal in edges)).encode()
        (raw / source["file"]).write_bytes(content)
        sources.append({"file": source["file"],
                        "sha256": hashlib.sha256(content).hexdigest()})
    (raw / "manifest.json").write_text(json.dumps({"sources": sources}))
    output = tmp_path / "output"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.espop.audit_reuse", "--raw-dir", str(raw),
         "--output-dir", str(output)], capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "mutation 1498 missing or changed constituents" in result.stderr
    assert not output.exists()
