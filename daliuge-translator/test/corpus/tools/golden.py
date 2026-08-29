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

`generate` refuses to run unless the CLI it would drive is the pinned baseline — see
`provenance.py`. `--legacy-repo PATH` additionally requires that CLI to come from that
checkout. `verify` has no such requirement: measuring the *current* build against the
goldens is the entire point of it.

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
    from .cases import Case, dlg_executable, load_cases
    from .provenance import ProvenanceError, assert_baseline, describe
except ImportError:                      # `python3 tools/golden.py`
    from cases import (  # type: ignore[import-not-found,no-redef]
        Case, dlg_executable, load_cases)
    from provenance import (  # type: ignore[import-not-found,no-redef]
        ProvenanceError, assert_baseline, describe)

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

class Run(NamedTuple):
    """The outcome of one `dlg` invocation."""

    code: int
    stdout: str
    stderr: str

    def failure(self, what: str) -> str:
        """A failure line that carries the reason, not just the fact."""
        tail = " | ".join(line for line in self.stderr.strip().splitlines()[-3:])
        return f"{what} failed (exit {self.code}){': ' + tail if tail else ''}"


def _dlg(argv: list[str], out: Path) -> Run:
    """Run one dlg stage, writing its JSON to `out`."""
    done = subprocess.run([dlg_executable(), *argv, "-o", str(out)],
                          capture_output=True, check=False)
    return Run(done.returncode,
               done.stdout.decode(errors="replace"),
               done.stderr.decode(errors="replace"))


def _drops(path: Path) -> list[dict[str, Any]]:
    """The DROP list of a PGT-shaped artefact, minus the trailing reprodata element.

    The trailing element is identified the way the translator itself identifies it — a
    dict with no truthy `oid` — rather than by position. `parsed[:-1]` would silently
    discard a real DROP from any artefact that carries no reprodata, and be off by one
    ever after.
    """
    parsed: list[dict[str, Any]] = json.loads(path.read_text())
    if parsed and isinstance(parsed[-1], dict) and not parsed[-1].get("oid"):
        return parsed[:-1]
    return parsed


def _lg_nodes(path: Path) -> int:
    """Node count of a logical graph, which is a dict rather than a DROP list."""
    return len(json.loads(path.read_text())["nodeDataArray"])


class Artefact(NamedTuple):
    name: str          # "pgt", "pgtp.n2i1.metis", ...
    payload: bytes     # raw JSON as the CLI wrote it
    elements: int      # DROPs for pgt/pgtp/pg; LGT nodes for lg, which is a dict
    partitions: int | None = None
    islands: int | None = None


class Skipped(NamedTuple):
    """A stage that produced no artefact.

    `expected` separates the two reasons, which must not share a type. A NoNeedMerge is a
    property of the graph and the setting and is part of the recorded corpus; a stage that
    fell over is a regression. Collapsing both into a bare string — as this module first
    did — means `verify` cannot tell "this case has always skipped here" from "the
    translator just broke", and silently reports neither.
    """

    key: str           # "branchTest/n8i2.metis" — case, or case/tag
    reason: str
    expected: bool


def produce(case: Case, settings: list[Setting]) -> Iterator[Artefact | Skipped]:
    """Drive one case through the full pipeline, yielding each artefact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        lg, pgt = tmp / "lg.json", tmp / "pgt.json"

        run = _dlg(case.prepare_argv(), lg)
        if run.code != 0:
            yield Skipped(case.id, run.failure(case.prepare), expected=False)
            return
        yield Artefact("lg", lg.read_bytes(), _lg_nodes(lg))

        run = _dlg(case.unroll_argv(lg), pgt)
        if run.code != 0:
            yield Skipped(case.id, run.failure("unroll"), expected=False)
            return
        yield Artefact("pgt", pgt.read_bytes(), len(_drops(pgt)))

        for setting in settings:
            for algo in setting.algorithms:
                yield from _partition_and_map(case, setting, algo, pgt, tmp)


def _is_partitioned(drops: list[dict[str, Any]]) -> bool:
    """Whether `partition` actually partitioned, judged on the DROPs it emitted.

    `dlg_partition` catches GPGTNoNeedMergeException, prints prose, and emits the
    *unpartitioned* graph with exit code 0 — so neither the exit code nor the absence of a
    traceback distinguishes the two. The DROPs do: a partitioned graph carries `node` and
    `island` labels and an unpartitioned one does not.
    """
    return bool(drops) and all("node" in d and "island" in d for d in drops)


def _partition_and_map(case: Case, setting: Setting, algo: str,
                       pgt: Path, tmp: Path) -> Iterator[Artefact | Skipped]:
    tag = f"{setting.id}.{algo}"
    key = f"{case.id}/{tag}"
    pgtp, pg = tmp / f"pgtp.{tag}.json", tmp / f"pg.{tag}.json"

    run = _dlg(["partition", "-P", str(pgt), "-a", algo,
                "-N", str(setting.partitions),
                "-i", str(setting.islands)], pgtp)
    if run.code != 0:
        yield Skipped(key, run.failure("partition"), expected=False)
        return

    drops = _drops(pgtp)
    partitioned = _is_partitioned(drops)
    prose = NO_NEED_MERGE in run.stdout
    if partitioned != (not prose):
        # The prose and the DROPs disagree: one of the two detectors has gone stale, and
        # which one is not guessable from here. Refuse rather than file whichever the
        # coin lands on — an unpartitioned graph stored as a partitioned golden is
        # exactly the corruption this check exists to prevent.
        yield Skipped(key,
                      f"cannot classify partition result: DROPs "
                      f"{'are' if partitioned else 'are not'} labelled but the "
                      f"no-need-merge notice {'was' if prose else 'was not'} printed",
                      expected=False)
        return
    if not partitioned:
        yield Skipped(key, "no-need-merge (too few DROPs for this setting)", expected=True)
        return

    parts, isles = _extent(drops, "node"), _extent(drops, "island")
    yield Artefact(f"pgtp.{tag}", pgtp.read_bytes(), len(drops), parts, isles)

    # `map -i` and the host list are both dictated by the PGT-P, not by the setting: they
    # have to cover the highest index the partitioner actually emitted.
    run = _dlg(["map", "-P", str(pgtp),
                "-N", ",".join(_map_hosts(isles, parts)),
                "-i", str(isles)], pg)
    if run.code != 0:
        yield Skipped(key, run.failure("map"), expected=False)
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


def _stored_digest(case_id: str, name: str) -> str:
    """The sha256 of the stored blob, or a description of why it could not be read."""
    try:
        return _digest(read_golden(case_id, name))
    except FileNotFoundError:
        return "missing"
    except (OSError, gzip.BadGzipFile, EOFError) as error:
        return f"unreadable: {type(error).__name__}"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _write_index(rows: list[dict[str, Any]], skipped: list[Skipped]) -> None:
    lines = ["# Phase 0 goldens — GENERATED, do not hand-edit.",
             "# Regenerate with: python3 tools/golden.py generate",
             "# Verify with:     python3 tools/golden.py verify",
             ""]
    for row in rows:
        lines += ["[[artefact]]",
                  f'case = "{row["case"]}"',
                  f'name = "{row["name"]}"',
                  f'sha256 = "{row["sha256"]}"',
                  f'elements = {row["elements"]}']
        # `.get`, not `[...]`: rows round-tripped through INDEX.toml carry these keys only
        # when they were written, so a row read back is not shaped like a fresh one.
        if row.get("partitions") is not None:
            lines.append(f'partitions = {row["partitions"]}')
            lines.append(f'islands = {row["islands"]}')
        lines.append("")

    # Recorded, not commented: `verify` holds the skip set to this list in both
    # directions, so a stage that starts or stops skipping is reported like any drift.
    for skip in sorted(skipped):
        lines += ["[[skipped]]",
                  f'key = "{_toml_escape(skip.key)}"',
                  f'reason = "{_toml_escape(skip.reason)}"',
                  ""]
    INDEX.write_text("\n".join(lines))


def load_index() -> dict[tuple[str, str], dict[str, Any]]:
    document = tomllib.loads(INDEX.read_text())
    return {(row["case"], row["name"]): row for row in document.get("artefact", [])}


def load_expected_skips() -> dict[str, str]:
    """The skips the corpus records, keyed by `case` or `case/tag`."""
    document = tomllib.loads(INDEX.read_text())
    return {row["key"]: row["reason"] for row in document.get("skipped", [])}


# --------------------------------------------------------------- explaining a drift

def _child(path: str, key: str) -> str:
    return f"{path}.{key}" if key.isidentifier() else f"{path}[{json.dumps(key)}]"


def first_difference(expected: Any, actual: Any, path: str = "$") -> str | None:
    """The first structural difference between two decoded artefacts, as a JSON path.

    A sha256 mismatch says an artefact moved; it never says *what* moved, and the
    produced bytes used to live in a TemporaryDirectory that was gone by the time anyone
    read the report. This turns "DRIFT chiles_simple/pgt" into a line a reviewer can act
    on without decompressing anything.
    """
    if type(expected) is not type(actual):
        return (f"{path}: type differs "
                f"({type(expected).__name__} != {type(actual).__name__})")

    if isinstance(expected, dict):
        for key in sorted(set(expected) - set(actual)):
            return f"{_child(path, key)}: missing (golden has {_render(expected[key])})"
        for key in sorted(set(actual) - set(expected)):
            return f"{_child(path, key)}: unexpected (now {_render(actual[key])})"
        for key in expected:                       # document order, not sorted
            found = first_difference(expected[key], actual[key], _child(path, key))
            if found:
                return found
        return None

    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: length {len(expected)} -> {len(actual)}"
        for index, item in enumerate(expected):
            found = first_difference(item, actual[index], f"{path}[{index}]")
            if found:
                return found
        return None

    if expected != actual:
        return f"{path}: {_render(expected)} -> {_render(actual)}"
    return None


def _render(value: Any, limit: int = 120) -> str:
    rendered = json.dumps(value, sort_keys=True)
    return rendered if len(rendered) <= limit else rendered[:limit] + "..."


# --------------------------------------------------------------------- commands

def _usable(only: str | None) -> list[Case]:
    cases = [c for c in load_cases() if c.goldenable]
    if only:
        cases = [c for c in cases if c.id == only]
        if not cases:
            raise SystemExit(f"no usable case with id {only!r}")
    return cases


def generate(only: str | None = None, legacy_repo: Path | None = None) -> int:
    # Refused rather than warned about: a golden written by the current build is
    # indistinguishable from a real one afterwards, and `verify` would pass on it forever.
    try:
        repository = assert_baseline(legacy_repo=legacy_repo)
    except ProvenanceError as error:
        print(error, file=sys.stderr)
        return 1
    print(describe(dlg_executable(), repository) + "\n")

    settings = load_settings()
    if only is None and GOLDEN.exists():
        shutil.rmtree(GOLDEN)
    GOLDEN.mkdir(exist_ok=True)

    # A single-case run must still leave INDEX.toml describing what is on disk. Writing
    # only the blobs — as this used to — leaves the index describing the previous output
    # while `drift.py`, which reads the blobs, sees the new one, and nothing reports the
    # disagreement.
    rows: list[dict[str, Any]] = []
    skipped: list[Skipped] = []
    if only is not None:
        rows = [row for row in load_index().values() if row["case"] != only]
        skipped = [Skipped(key, reason, expected=True)
                   for key, reason in load_expected_skips().items()
                   if key.split("/")[0] != only]

    failures = 0
    for case in _usable(only):
        (GOLDEN / case.id).mkdir(exist_ok=True)
        produced = 0
        for item in produce(case, settings):
            if isinstance(item, Skipped):
                if item.expected:
                    skipped.append(item)
                    print(f"  --    {item.key}: {item.reason}")
                else:
                    failures += 1
                    print(f"  FAIL  {item.key}: {item.reason}", file=sys.stderr)
                continue
            path_of(case.id, item.name).write_bytes(_store(item.payload))
            rows.append({"case": case.id, "name": item.name,
                         "sha256": _digest(item.payload), "elements": item.elements,
                         "partitions": item.partitions, "islands": item.islands})
            produced += 1
        print(f"  ok    {case.id}  ({produced} artefacts)")

    rows.sort(key=lambda row: (row["case"], row["name"]))
    _write_index(rows, skipped)
    print(f"\n{len(rows)} artefacts, {len(skipped)} stages skipped")
    if failures:
        print(f"{failures} stage(s) failed; the corpus written is incomplete",
              file=sys.stderr)
        return 1
    return 0


def _explain(case_id: str, name: str, payload: bytes) -> str:
    """Say what moved, and leave the produced artefact on disk to diff against."""
    actual = path_of(case_id, name).with_suffix("").with_suffix(".actual.json")
    actual.write_bytes(payload)
    try:
        difference = first_difference(json.loads(read_golden(case_id, name)),
                                      json.loads(payload))
    except (OSError, gzip.BadGzipFile, json.JSONDecodeError) as error:
        return f"could not diff against the stored golden ({error}); wrote {actual}"
    return f"{difference or 'byte-level difference only'}; wrote {actual}"


def verify(only: str | None = None) -> int:
    settings = load_settings()
    index = load_index()
    expected_skips = load_expected_skips()
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    skipped: set[str] = set()
    broken: set[str] = set()

    print(f"driving {dlg_executable()}\n")
    for case in _usable(only):
        for item in produce(case, settings):
            if isinstance(item, Skipped):
                # A stage that produced nothing is a result, not an absence of one.
                skipped.add(item.key)
                if not item.expected:
                    broken.add(case.id)
                    problems.append(f"{item.key}: {item.reason}")
                    print(f"  FAIL  {item.key}: {item.reason}")
                elif item.key not in expected_skips:
                    problems.append(f"{item.key}: skipped, but INDEX.toml does not "
                                    f"record a skip here ({item.reason})")
                    print(f"  SKIP? {item.key}")
                else:
                    print(f"  --    {item.key}")
                continue

            key = (case.id, item.name)
            seen.add(key)
            recorded = index.get(key)
            if recorded is None:
                problems.append(f"{case.id}/{item.name}: new artefact, not in INDEX.toml")
                print(f"  NEW   {case.id}/{item.name}")
                continue
            if recorded["sha256"] != _digest(item.payload):
                problems.append(f"{case.id}/{item.name}: content differs from golden — "
                                + _explain(case.id, item.name, item.payload))
                print(f"  DRIFT {case.id}/{item.name}")
                continue
            # The stored blob is the artefact this corpus claims to hold; INDEX.toml is
            # only its description. Checking the description alone leaves a corrupt or
            # half-regenerated blob invisible here while `drift.py`, which reads blobs,
            # quietly scans it.
            stored = _stored_digest(case.id, item.name)
            if stored != recorded["sha256"]:
                problems.append(f"{case.id}/{item.name}: stored golden disagrees with "
                                f"INDEX.toml ({stored})")
                print(f"  BLOB  {case.id}/{item.name}")
                continue
            print(f"  ok    {case.id}/{item.name}")

    # Restricted to the selected case rather than switched off: with the check disabled,
    # a single-case run in which every stage failed produced nothing, compared nothing,
    # and reported success.
    for key in sorted(k for k in index if only is None or k[0] == only):
        if key not in seen:
            problems.append(f"{key[0]}/{key[1]}: golden exists but was not reproduced")
            print(f"  GONE  {key[0]}/{key[1]}")

    # A recorded skip that no longer fires is news — unless the case fell over before
    # reaching it, in which case the earlier failure is the finding and "the stage now
    # runs" would be the opposite of what happened.
    for key in sorted(expected_skips):
        case_id = key.split("/")[0]
        if only is not None and case_id != only:
            continue
        if key not in skipped and case_id not in broken:
            problems.append(f"{key}: recorded as skipped, but the stage now runs")
            print(f"  FIXED {key}")

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


def _take_legacy_repo(argv: list[str]) -> tuple[list[str], Path | None]:
    """Pull `--legacy-repo PATH` out of the argument list, if it is there."""
    if "--legacy-repo" not in argv:
        return argv, None
    at = argv.index("--legacy-repo")
    if at + 1 >= len(argv):
        raise SystemExit("--legacy-repo needs a path")
    return argv[:at] + argv[at + 2:], Path(argv[at + 1])


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "verify"
    rest = sys.argv[2:]
    if command == "generate":
        rest, repo = _take_legacy_repo(rest)
        raise SystemExit(generate(*rest, legacy_repo=repo))
    if command == "verify":
        raise SystemExit(verify(*rest))
    if command == "show" and len(rest) == 2:
        raise SystemExit(show(*rest))
    print(__doc__, file=sys.stderr)
    raise SystemExit(2)
