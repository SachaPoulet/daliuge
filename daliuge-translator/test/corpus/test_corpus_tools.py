#!/usr/bin/env python3
"""Unit tests for the corpus tooling itself.

The corpus is a measuring instrument, and an instrument that reports "no change" is
indistinguishable from one that cannot report anything. Everything tested here is a piece
of machinery whose failure mode is silence rather than an exception:

* the trailing-reprodata sniff, which used to be `parsed[:-1]` and would have eaten a real
  DROP from any artefact that carried no reprodata;
* the partition-extent arithmetic, where "how many hosts does `map` need" is the highest
  index plus one, not the number of distinct partitions;
* whether `partition` actually partitioned, which its exit code does not tell you;
* the index round trip, which is the only thing standing between a golden and its digest;
* and `drift.py`'s rules, checked by deliberately malforming a real corpus graph and
  confirming each rule fires — and, just as importantly, that it stays quiet on the
  unmodified graph.

These are pure unit tests: no `dlg` process is spawned and no golden is regenerated. The
drift controls do build `LG` objects, so they need the translator importable.
"""
# The helpers under test are deliberately module-private; testing them is the point.
# pylint: disable=protected-access

import json
import sys
from pathlib import Path

import pytest

# tomllib is stdlib from 3.11; the project still supports 3.10, where this tooling (and
# therefore these tests) simply does not apply.
pytest.importorskip("tomllib",
                    reason="corpus tooling reads TOML with tomllib, stdlib from 3.11")

CORPUS = Path(__file__).resolve().parent
sys.path.insert(0, str(CORPUS / "tools"))

import golden  # noqa: E402
import drift  # noqa: E402


# --------------------------------------------------------------------- _drops

def _write(tmp_path: Path, payload) -> Path:
    path = tmp_path / "artefact.json"
    path.write_text(json.dumps(payload))
    return path


def test_drops_strips_a_trailing_reprodata_element(tmp_path):
    wire = [{"oid": "a"}, {"oid": "b"}, {"rmode": "1", "merkleroot": "x"}]
    assert golden._drops(_write(tmp_path, wire)) == wire[:2]


def test_drops_keeps_every_element_when_there_is_no_reprodata(tmp_path):
    """The regression `parsed[:-1]` would have caused: a silently discarded DROP."""
    wire = [{"oid": "a"}, {"oid": "b"}]
    assert golden._drops(_write(tmp_path, wire)) == wire


def test_drops_treats_a_falsy_oid_as_reprodata(tmp_path):
    """Matches the translator's own sniff, which tests truthiness rather than presence."""
    wire = [{"oid": "a"}, {"oid": "", "rmode": "1"}]
    assert golden._drops(_write(tmp_path, wire)) == wire[:1]


def test_drops_of_an_empty_list(tmp_path):
    assert golden._drops(_write(tmp_path, [])) == []


# --------------------------------------------------------------------- extents and hosts

def test_extent_counts_the_highest_index_not_the_distinct_values():
    """metis leaves gaps: #0,#2,#3,#5,#7 is five partitions that needs eight hosts."""
    drops = [{"node": f"#{i}"} for i in (0, 2, 3, 5, 7)]
    assert golden._extent(drops, "node") == 8


def test_extent_of_a_single_partition():
    assert golden._extent([{"node": "#0"}, {"node": "#0"}], "node") == 1


def test_map_hosts_puts_island_managers_first():
    assert golden._map_hosts(2, 3) == ["dim0", "dim1", "nm0", "nm1", "nm2"]


# --------------------------------------------------------------- partition classification

def test_partitioned_drops_carry_node_and_island_labels():
    assert golden._is_partitioned([{"node": "#0", "island": "#0"}])


def test_unpartitioned_drops_are_recognised():
    """What `dlg partition` emits after a NoNeedMerge — with exit code 0."""
    assert not golden._is_partitioned([{"oid": "a"}, {"oid": "b"}])


def test_partially_labelled_drops_are_not_partitioned():
    assert not golden._is_partitioned([{"node": "#0", "island": "#0"}, {"oid": "b"}])


# --------------------------------------------------------------------- failure reporting

def test_run_failure_carries_the_reason():
    run = golden.Run(1, "", "Traceback ...\nKeyError: 'fromPort'")
    assert "KeyError: 'fromPort'" in run.failure("unroll")
    assert "exit 1" in run.failure("unroll")


def test_run_failure_survives_empty_stderr():
    assert golden.Run(2, "", "").failure("map") == "map failed (exit 2)"


# --------------------------------------------------------------------- index round trip

def test_index_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(golden, "INDEX", tmp_path / "INDEX.toml")
    rows = [
        {"case": "a", "name": "lg", "sha256": "0" * 64, "elements": 8,
         "partitions": None, "islands": None},
        {"case": "a", "name": "pgtp.n2i1.metis", "sha256": "1" * 64, "elements": 12,
         "partitions": 2, "islands": 1},
    ]
    skips = [golden.Skipped("a/n8i2.metis", "no-need-merge (too few DROPs)", True)]

    golden._write_index(rows, skips)
    index = golden.load_index()

    assert set(index) == {("a", "lg"), ("a", "pgtp.n2i1.metis")}
    assert index[("a", "lg")]["sha256"] == "0" * 64
    assert index[("a", "pgtp.n2i1.metis")]["partitions"] == 2
    assert golden.load_expected_skips() == {
        "a/n8i2.metis": "no-need-merge (too few DROPs)"}


def test_index_rows_read_back_can_be_rewritten(tmp_path, monkeypatch):
    """`generate <case>` re-emits rows it read from the index, which lack absent keys."""
    monkeypatch.setattr(golden, "INDEX", tmp_path / "INDEX.toml")
    golden._write_index(
        [{"case": "a", "name": "lg", "sha256": "0" * 64, "elements": 8,
          "partitions": None, "islands": None}], [])
    golden._write_index(list(golden.load_index().values()), [])
    assert golden.load_index()[("a", "lg")]["elements"] == 8


def test_reason_with_quotes_survives_the_index(tmp_path, monkeypatch):
    monkeypatch.setattr(golden, "INDEX", tmp_path / "INDEX.toml")
    golden._write_index([], [golden.Skipped("a/x", 'fell over: "boom" \\ hard', True)])
    assert golden.load_expected_skips()["a/x"] == 'fell over: "boom" \\ hard'


# --------------------------------------------------------------------- drift explanation

def test_first_difference_is_none_for_equal_documents():
    document = {"a": [1, {"b": "c"}]}
    assert golden.first_difference(document, json.loads(json.dumps(document))) is None


def test_first_difference_ignores_key_order():
    assert golden.first_difference({"a": 1, "b": 2}, {"b": 2, "a": 1}) is None


def test_first_difference_names_the_path_of_a_changed_value():
    found = golden.first_difference([{"node": "#0"}], [{"node": "#1"}])
    assert found == '$[0].node: "#0" -> "#1"'


def test_first_difference_reports_a_length_change():
    assert "length 2 -> 1" in golden.first_difference([1, 2], [1])


def test_first_difference_reports_a_missing_key():
    found = golden.first_difference({"a": {"b": 1}}, {"a": {}})
    assert found is not None and "missing" in found and "$.a.b" in found


def test_first_difference_reports_an_unexpected_key():
    found = golden.first_difference({"a": {}}, {"a": {"b": 1}})
    assert found is not None and "unexpected" in found and "$.a.b" in found


def test_first_difference_distinguishes_types():
    found = golden.first_difference({"a": 1}, {"a": "1"})
    assert found is not None and "type differs" in found


def test_first_difference_does_not_confuse_bool_and_int():
    found = golden.first_difference({"a": 1}, {"a": True})
    assert found is not None


# --------------------------------------------------------------------- drift controls

@pytest.mark.parametrize("row,description,detected", drift.run_controls(),
                         ids=lambda value: value if isinstance(value, str) else "")
def test_every_drift_rule_still_fires_on_a_malformed_graph(row, description, detected):
    """The positive controls behind EXPECTED_DRIFT.md's "why believe a zero"."""
    assert detected, f"{row} did not fire: {description}"


@pytest.mark.parametrize("case_id", ["SuperBasicScatterGather", "testLoop",
                                     "HelloWorld_simple"])
def test_drift_rules_stay_quiet_on_the_unmodified_graph(case_id):
    """The negative control: without it, a rule that always fires would look healthy."""
    found = drift.scan_raw(case_id, golden.read_golden(case_id, "lg"))
    assert found.clean, (
        f"{case_id} tripped a rule unmodified: {found}")
