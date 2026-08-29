#!/usr/bin/env python3
"""Read, and re-prove, the corpus invocation manifest.

``CASES.toml`` records how each corpus graph is driven and what it is expected to
produce. This module is the single reader of that file — golden generation (#6) should
import :func:`load_cases` rather than walking ``graphs/`` itself.

    python3 tools/cases.py list     # the manifest as a table
    python3 tools/cases.py check    # re-run every case, exit 1 on any disagreement

``check`` drives a DALiuGE install (see :func:`dlg_executable`) and takes a couple of
minutes; ``cont_img_mvp`` alone unrolls to 144 DROPs.
"""

import functools
import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CORPUS = Path(__file__).resolve().parent.parent
CASES = CORPUS / "CASES.toml"
GRAPHS = CORPUS / "graphs"


@functools.lru_cache(maxsize=1)
def dlg_executable() -> str:
    """The ``dlg`` CLI every corpus tool drives.

    Resolution order is deliberate. ``$PATH`` is consulted *last* because it is the one
    source that has nothing to do with the interpreter running the corpus: with a DALiuGE
    venv active, ``shutil.which("dlg")`` answers the same way no matter which Python
    invoked the tooling, so a run can silently measure a different install than the one
    under test. The interpreter's own sibling script is the build the caller actually
    chose.

    ``DLG_CLI`` overrides both, for the case where the CLI genuinely lives elsewhere.
    """
    configured = os.environ.get("DLG_CLI")
    if configured:
        return configured

    sibling = Path(sys.executable).with_name("dlg")
    if sibling.is_file():
        return str(sibling)

    found = shutil.which("dlg")
    if found:
        return found

    raise SystemExit(
        "Cannot locate the dlg CLI. Activate the DALiuGE environment, or set DLG_CLI "
        "to the console-script path."
    )


@dataclass(frozen=True)
class Case:
    """One graph plus everything needed to drive it through the translator."""

    id: str
    graph: Path
    status: str
    prepare: str
    fill_params: list[str]
    reproducibility: str
    oid_prefix: str
    zerorun: bool
    app: int
    graph_config: Path | None = None
    golden: bool = True
    expect_drops: int | None = None
    broken_stage: str | None = None
    broken_error: str | None = None
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def goldenable(self) -> bool:
        """Whether this case can produce a stable golden.

        A case is excluded when the translator's output for it is not byte-reproducible —
        not a property of the case, but of a defect it exposes. It stays a case: the DROP
        count is still checked, and the exclusion is documented at its entry.
        """
        return self.ok and self.golden

    @property
    def expected_failure(self) -> tuple[str, str]:
        """The ``(stage, error)`` a known-broken case is recorded as raising.

        Both fields are optional on the dataclass because ``ok`` cases leave them
        out; :func:`load_cases` guarantees a known-broken case carries both.
        """
        if self.broken_stage is None or self.broken_error is None:
            raise ValueError(f"{self.id}: not a known-broken case")
        return self.broken_stage, self.broken_error

    def prepare_argv(self) -> list[str]:
        """The `dlg fill` / `dlg fill-config` invocation for this case."""
        if self.prepare == "fill-config":
            return ["fill-config", "-L", str(self.graph),
                    "--graph_config", str(self.graph_config),
                    "-R", self.reproducibility]
        argv = ["fill", "-L", str(self.graph), "-R", self.reproducibility]
        for param in self.fill_params:
            argv += ["-p", param]
        return argv

    def unroll_argv(self, lg_path: Path | None = None) -> list[str]:
        """The `dlg unroll` invocation for this case.

        Reads the LG from stdin unless `lg_path` names a file to read instead.
        """
        argv = ["unroll", "-p", self.oid_prefix]
        if lg_path is not None:
            argv += ["-L", str(lg_path)]
        if self.zerorun:
            argv.append("-z")
        if self.app:
            argv += ["--app", str(self.app)]
        return argv


def load_cases() -> list[Case]:
    """Parse CASES.toml, folding [defaults] into every entry."""
    document = tomllib.loads(CASES.read_text())
    defaults = document["defaults"]
    cases = []
    for entry in document["case"]:
        merged = {**defaults, **entry}
        config = merged.get("graph_config")
        if merged["prepare"] == "fill-config" and not config:
            raise ValueError(f"{merged['id']}: prepare='fill-config' needs graph_config")
        if merged["status"] == "ok":
            if merged.get("expect_drops") is None:
                raise ValueError(f"{merged['id']}: status='ok' needs expect_drops")
        elif merged.get("broken_stage") is None or merged.get("broken_error") is None:
            raise ValueError(
                f"{merged['id']}: status='known-broken' needs broken_stage and broken_error")
        cases.append(Case(
            id=merged["id"],
            graph=GRAPHS / merged["graph"],
            status=merged["status"],
            prepare=merged["prepare"],
            fill_params=list(merged["fill_params"]),
            reproducibility=merged["reproducibility"],
            oid_prefix=merged["oid_prefix"],
            zerorun=merged["zerorun"],
            app=merged["app"],
            graph_config=GRAPHS / config if config else None,
            golden=merged.get("golden", True),
            expect_drops=merged.get("expect_drops"),
            broken_stage=merged.get("broken_stage"),
            broken_error=merged.get("broken_error"),
            note=merged.get("note", ""),
        ))
    return cases


def _run(argv: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([dlg_executable(), *argv], input=stdin,
                          capture_output=True, check=False)


def unroll(case: Case) -> tuple[list[dict[str, Any]] | None, str, str]:
    """Drive one case as far as a PGT.

    Returns ``(drops, failed_stage, stderr)``. ``drops`` is None when a stage failed,
    and excludes the trailing reprodata element when it is not.
    """
    prepared = _run(case.prepare_argv())
    if prepared.returncode != 0:
        return None, case.prepare, prepared.stderr.decode(errors="replace")

    unrolled = _run(case.unroll_argv(), stdin=prepared.stdout)
    if unrolled.returncode != 0:
        return None, "unroll", unrolled.stderr.decode(errors="replace")

    return json.loads(unrolled.stdout)[:-1], "", ""


def _last_exception_line(stderr: str) -> str:
    for line in reversed(stderr.strip().splitlines()):
        if line and not line.startswith((" ", "\t")):
            return line.strip()
    return "<no exception line>"


def check() -> int:
    problems = []
    print(f"driving {dlg_executable()}\n")
    for case in load_cases():
        drops, failed_stage, stderr = unroll(case)

        if case.ok:
            if drops is None:
                problems.append(
                    f"{case.id}: recorded ok, but {failed_stage} failed with "
                    f"{_last_exception_line(stderr)}")
                print(f"  FAIL  {case.id}")
            elif len(drops) != case.expect_drops:
                problems.append(
                    f"{case.id}: expected {case.expect_drops} DROPs, got {len(drops)}")
                print(f"  DRIFT {case.id}  {case.expect_drops} -> {len(drops)}")
            else:
                print(f"  ok    {case.id}  ({len(drops)} DROPs)")
            continue

        # known-broken: the failure itself is the expectation
        broken_stage, broken_error = case.expected_failure
        if drops is not None:
            problems.append(
                f"{case.id}: recorded known-broken at {broken_stage}, but it now "
                f"succeeds with {len(drops)} DROPs — has it been fixed?")
            print(f"  FIXED {case.id}")
        elif failed_stage != broken_stage:
            problems.append(f"{case.id}: expected failure at {broken_stage}, "
                            f"got one at {failed_stage}")
            print(f"  MOVED {case.id}")
        elif broken_error not in stderr:
            problems.append(f"{case.id}: expected {broken_error!r}, got "
                            f"{_last_exception_line(stderr)!r}")
            print(f"  CHANGED {case.id}")
        else:
            print(f"  known {case.id}  ({broken_error}, as recorded)")

    print()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} case(s) disagree with CASES.toml", file=sys.stderr)
        return 1
    print("every case matches CASES.toml")
    return 0


def show() -> int:
    cases = load_cases()
    width = max(len(c.id) for c in cases)
    for case in cases:
        prepare = case.prepare
        if case.graph_config:
            prepare += f" ({case.graph_config.name})"
        expected = (f"{case.expect_drops:>4} DROPs" if case.ok
                    else f"broken at {case.broken_stage}")
        print(f"{case.id:<{width}}  {prepare:<34}  {expected}")
    print(f"\n{len(cases)} cases, {sum(1 for c in cases if c.ok)} usable")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    if command not in ("list", "check"):
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(show() if command == "list" else check())
