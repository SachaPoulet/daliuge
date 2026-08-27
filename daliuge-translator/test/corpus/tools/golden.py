#!/usr/bin/env python3
"""Generate and verify the Phase 0 golden outputs.

Every artefact here was produced by the pre-restructure translator — DALiuGE at the
``daliuge_baseline_commit`` recorded in ``MANIFEST.toml``. They are the reference every
later phase is diffed against, so they are regenerated only when a change to translator
output is *intended*.

    python3 tools/golden.py generate            # (re)produce golden/ from scratch
    python3 tools/golden.py verify              # re-run and compare, exit 1 on drift
    python3 tools/golden.py show <case> <name>  # print one artefact as JSON

Both walking commands take an optional case id to work on a single case.

Two things about the CLI that this module exists to encapsulate:

* **Never read a stage's output from stdout.** `mysarkar` and `min_num_parts` print
  "Merging ugid ..." progress lines to stdout, ahead of the JSON, so the documented
  `partition | map` pipe hands `map` an unparseable stream. Every stage here writes with
  `-o` to a file instead, which is clean for all three algorithms.
* **`partition` swallows its own failure.** `GPGTNoNeedMergeException` is caught in
  `dlg_partition`, printed as prose, and the *unpartitioned* graph is emitted with exit
  code 0. Detected here by matching that prose, and recorded as an outcome rather than
  mistaken for a successful partitioning.
"""

import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Iterator, NamedTuple

try:                                    # `python3 -m tools.golden`, and type checkers
    from .cases import Case, load_cases
except ImportError:                      # `python3 tools/golden.py`
    from cases import Case, load_cases  # type: ignore[import-not-found,no-redef]

CORPUS = Path(__file__).resolve().parent.parent
GOLDEN = CORPUS / "golden"
INDEX = GOLDEN / "INDEX.toml"
CASES_FILE = CORPUS / "CASES.toml"

# The prose dlg_partition prints instead of letting GPGTNoNeedMergeException escape.
NO_NEED_MERGE = "does not work for the graph provided"


class Setting(NamedTuple):
    """One partition configuration, applied across the corpus."""

    id: str
    algorithms: list[str]
    partitions: int
    islands: int


def load_settings() -> list[Setting]:
    document = tomllib.loads(CASES_FILE.read_text())
    return [Setting(**entry) for entry in document["partition"]]


# --------------------------------------------------------------------- running dlg

def _dlg(argv: list[str], out: Path) -> tuple[int, str]:
    """Run one dlg stage, writing its JSON to `out`. Returns (returncode, stdout)."""
    done = subprocess.run(["dlg", *argv, "-o", str(out)],
                          capture_output=True, check=False)
    return done.returncode, done.stdout.decode(errors="replace")


def _drops(path: Path) -> list[dict[str, Any]]:
    """The DROP list of a PGT-shaped artefact, minus the trailing reprodata element."""
    parsed: list[dict[str, Any]] = json.loads(path.read_text())
    return parsed[:-1]


def _lg_nodes(path: Path) -> int:
    """Node count of a logical graph, which is a dict rather than a DROP list."""
    return len(json.loads(path.read_text())["nodeDataArray"])


class Artefact(NamedTuple):
    name: str          # "pgt", "pgtp.n2i1.metis", ...
    payload: bytes     # raw JSON as the CLI wrote it
    elements: int      # DROPs for pgt/pgtp/pg; LGT nodes for lg, which is a dict
    partitions: int | None = None
    islands: int | None = None


def produce(case: Case, settings: list[Setting]) -> Iterator[Artefact | str]:
    """Drive one case through the full pipeline, yielding each artefact.

    Yields a `str` instead of an `Artefact` to report a stage that did not produce one
    — a NoNeedMerge, or an unexpected failure.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        lg, pgt = tmp / "lg.json", tmp / "pgt.json"

        code, _ = _dlg(case.prepare_argv(), lg)
        if code != 0:
            yield f"{case.id}: {case.prepare} failed"
            return
        yield Artefact("lg", lg.read_bytes(), _lg_nodes(lg))

        code, _ = _dlg(case.unroll_argv(lg), pgt)
        if code != 0:
            yield f"{case.id}: unroll failed"
            return
        yield Artefact("pgt", pgt.read_bytes(), len(_drops(pgt)))

        for setting in settings:
            for algo in setting.algorithms:
                yield from _partition_and_map(case, setting, algo, pgt, tmp)


def _partition_and_map(case: Case, setting: Setting, algo: str,
                       pgt: Path, tmp: Path) -> Iterator[Artefact | str]:
    tag = f"{setting.id}.{algo}"
    pgtp, pg = tmp / f"pgtp.{tag}.json", tmp / f"pg.{tag}.json"

    code, stdout = _dlg(["partition", "-P", str(pgt), "-a", algo,
                         "-N", str(setting.partitions),
                         "-i", str(setting.islands)], pgtp)
    if code != 0:
        yield f"{case.id}/{tag}: partition failed"
        return
    if NO_NEED_MERGE in stdout:
        yield f"{case.id}/{tag}: no-need-merge (too few DROPs for this setting)"
        return

    drops = _drops(pgtp)
    parts, isles = _extent(drops, "node"), _extent(drops, "island")
    yield Artefact(f"pgtp.{tag}", pgtp.read_bytes(), len(drops), parts, isles)

    # `map -i` and the host list are both dictated by the PGT-P, not by the setting: they
    # have to cover the highest index the partitioner actually emitted.
    code, _ = _dlg(["map", "-P", str(pgtp),
                    "-N", ",".join(_map_hosts(isles, parts)),
                    "-i", str(isles)], pg)
    if code != 0:
        yield f"{case.id}/{tag}: map failed"
        return
    yield Artefact(f"pg.{tag}", pg.read_bytes(), len(_drops(pg)))


# --------------------------------------------------------------------- storage

def _extent(drops: list[dict[str, Any]], key: str) -> int:
    """How many managers a PGT-P needs for `key` — its highest index plus one.

    Not the number of distinct values: metis leaves gaps, assigning an 11-DROP graph to
    partitions #0, #2, #3, #5 and #7. Five partitions, but resource_map subscripts the
    host list by the index in the label, so it needs eight entries.
    """
    return max(int(d[key][1:]) for d in drops) + 1


def _map_hosts(islands: int, nodes: int) -> list[str]:
    """The `dlg map -N` host list: island managers first, then node managers.

    resource_map (pg_generator.py:255-257) slices this list — first `-i` entries are
    island managers, the rest are node managers — and subscripts each slice by the index
    parsed out of the DROP's label, so an undersized list dies with a bare IndexError.
    """
    return [f"dim{i}" for i in range(islands)] + [f"nm{i}" for i in range(nodes)]


def _store(payload: bytes) -> bytes:
    """gzip with a zeroed mtime — the default stamps the clock into the header."""
    return gzip.compress(payload, mtime=0)


def path_of(case_id: str, name: str) -> Path:
    return GOLDEN / case_id / f"{name}.json.gz"


def read_golden(case_id: str, name: str) -> bytes:
    return gzip.decompress(path_of(case_id, name).read_bytes())


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_index(rows: list[dict[str, Any]], skipped: list[str]) -> None:
    lines = ["# Phase 0 goldens — GENERATED, do not hand-edit.",
             "# Regenerate with: python3 tools/golden.py generate",
             "# Verify with:     python3 tools/golden.py verify",
             ""]
    for note in skipped:
        lines.append(f"# skipped: {note}")
    lines.append("")
    for row in rows:
        lines += ["[[artefact]]",
                  f'case = "{row["case"]}"',
                  f'name = "{row["name"]}"',
                  f'sha256 = "{row["sha256"]}"',
                  f'elements = {row["elements"]}']
        if row["partitions"] is not None:
            lines.append(f'partitions = {row["partitions"]}')
            lines.append(f'islands = {row["islands"]}')
        lines.append("")
    INDEX.write_text("\n".join(lines))


def load_index() -> dict[tuple[str, str], dict[str, Any]]:
    document = tomllib.loads(INDEX.read_text())
    return {(row["case"], row["name"]): row for row in document.get("artefact", [])}


# --------------------------------------------------------------------- commands

def _usable(only: str | None) -> list[Case]:
    cases = [c for c in load_cases() if c.ok]
    if only:
        cases = [c for c in cases if c.id == only]
        if not cases:
            raise SystemExit(f"no usable case with id {only!r}")
    return cases


def generate(only: str | None = None) -> int:
    settings = load_settings()
    if only is None and GOLDEN.exists():
        shutil.rmtree(GOLDEN)
    GOLDEN.mkdir(exist_ok=True)

    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    for case in _usable(only):
        (GOLDEN / case.id).mkdir(exist_ok=True)
        produced = 0
        for item in produce(case, settings):
            if isinstance(item, str):
                skipped.append(item)
                print(f"  --    {item}")
                continue
            path_of(case.id, item.name).write_bytes(_store(item.payload))
            rows.append({"case": case.id, "name": item.name,
                         "sha256": _digest(item.payload), "elements": item.elements,
                         "partitions": item.partitions, "islands": item.islands})
            produced += 1
        print(f"  ok    {case.id}  ({produced} artefacts)")

    if only is None:
        _write_index(rows, skipped)
        print(f"\n{len(rows)} artefacts, {len(skipped)} stages skipped")
    return 0


def verify(only: str | None = None) -> int:
    settings = load_settings()
    index = load_index()
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()

    for case in _usable(only):
        for item in produce(case, settings):
            if isinstance(item, str):
                continue
            key = (case.id, item.name)
            seen.add(key)
            recorded = index.get(key)
            if recorded is None:
                problems.append(f"{case.id}/{item.name}: new artefact, not in INDEX.toml")
                print(f"  NEW   {case.id}/{item.name}")
            elif recorded["sha256"] != _digest(item.payload):
                problems.append(f"{case.id}/{item.name}: content differs from golden")
                print(f"  DRIFT {case.id}/{item.name}")
            else:
                print(f"  ok    {case.id}/{item.name}")

    for key in sorted(set(index) - seen) if only is None else []:
        problems.append(f"{key[0]}/{key[1]}: golden exists but was not reproduced")
        print(f"  GONE  {key[0]}/{key[1]}")

    print()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} artefact(s) drifted from the goldens", file=sys.stderr)
        return 1
    print("every artefact matches its golden")
    return 0


def show(case_id: str, name: str) -> int:
    print(read_golden(case_id, name).decode())
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "verify"
    rest = sys.argv[2:]
    if command == "generate":
        raise SystemExit(generate(*rest))
    if command == "verify":
        raise SystemExit(verify(*rest))
    if command == "show" and len(rest) == 2:
        raise SystemExit(show(*rest))
    print(__doc__, file=sys.stderr)
    raise SystemExit(2)
