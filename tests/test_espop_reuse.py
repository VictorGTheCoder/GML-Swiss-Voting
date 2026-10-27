"""Public audit outputs: conservative geography, counts and explicit absences."""

from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from scripts.espop.audit_reuse import compare_population, harmonize_counts


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
