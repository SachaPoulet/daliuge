#!/usr/bin/env python3
"""Enumerate the corpus graphs that the sanctioned §5 breaks will change.

ARCHITECTURE_PROPOSAL §6: "No phase may change PGT output for the corpus except where §5
rows 5/5b/5c are deliberately enabled — those are sanctioned changes, and the graphs they
affect must be enumerated in Phase 0 so the drift is expected rather than investigated."

This is that enumeration. It writes EXPECTED_DRIFT.md.

    python3 tools/drift.py report     # rewrite EXPECTED_DRIFT.md
    python3 tools/drift.py show       # print the findings without writing

Rows 5 and 5b are decided by building each graph's real `LG` and asking the real
`LGNode` predicates — not by matching category strings here, which would drift from the
translator the moment either side changed. Rows 5d/5e are decided on the node dict as
`LGNode` receives it, because both are about what the `jd` setter does with a node that
arrives without a `categoryType`.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:                                    # `python3 -m tools.drift`
    from .cases import Case, load_cases
    from .golden import read_golden
except ImportError:                     # `python3 tools/drift.py`
    from cases import Case, load_cases  # type: ignore[import-not-found,no-redef]
    from golden import read_golden  # type: ignore[import-not-found,no-redef,attr-defined]

CORPUS = Path(__file__).resolve().parent.parent
REPORT = CORPUS / "EXPECTED_DRIFT.md"

# lg_node.py:616-627 — the three spellings Scatter accepts before falling back to 4.
SCATTER_KEYS = ("num_of_copies", "num_of_splits", "Number of copies")
# lg_node.py:645-651 — Loop's three, with no fallback at all.
LOOP_KEYS = ("num_of_iter", "Number of Iterations", "Number of loops")


@dataclass
class Findings:
    """Per-case §5 hits."""

    case: str
    row5: list[str] = field(default_factory=list)    # Scatter with no DoP field
    row5b: list[str] = field(default_factory=list)   # Loop with no iteration count
    row5d: list[str] = field(default_factory=list)   # no categoryType, category unknown
    row5e: list[str] = field(default_factory=list)   # no categoryType, category "Data"
    error: str = ""

    @property
    def clean(self) -> bool:
        return not (self.row5 or self.row5b or self.row5d or self.row5e or self.error)


def _label(node: dict[str, Any]) -> str:
    name = node.get("name") or node.get("text") or "<unnamed>"
    return f"{name} ({str(node.get('id'))[:8]})"


def scan(case: Case) -> Findings:
    """Scan one corpus case, via its filled-LG golden."""
    return scan_raw(case.id, read_golden(case.id, "lg"))


def scan_raw(name: str, raw: bytes) -> Findings:
    """Scan one filled logical graph. Split out from `scan` so it can be tested with a
    deliberately malformed graph — a rule scanner that reports nothing is worthless
    unless it has been shown to report something."""
    from dlg.dropmake.definition_classes import APP_TYPES, DATA_TYPES
    from dlg.dropmake.lg import LG

    found = Findings(case=name)

    # Rows 5d/5e: judged before LGNode's jd setter mutates the node. `Data` sits in both
    # APP_TYPES and DATA_TYPES and APP_TYPES is tested first, so a `Data` node with no
    # categoryType is inferred to be an Application.
    for node in json.loads(raw).get("nodeDataArray", []):
        if "categoryType" in node:
            continue
        category = node.get("category")
        if category == "Data":
            found.row5e.append(_label(node))
        elif category not in APP_TYPES and category not in DATA_TYPES:
            found.row5d.append(_label(node))

    # Rows 5/5b: judged on the built graph, using the translator's own predicates.
    # Re-parsed because LG() mutates the dict it is handed.
    try:
        graph = LG(json.loads(raw), ssid="1")
    except Exception as failure:                     # noqa: BLE001 - reported, not raised
        found.error = f"{type(failure).__name__}: {failure}"
        return found

    for lgn in graph._lgn_list:
        if lgn.is_scatter and not any(k in lgn.jd for k in SCATTER_KEYS):
            found.row5.append(_label(lgn.jd))
        if lgn.is_loop and not any(k in lgn.jd for k in LOOP_KEYS):
            found.row5b.append(_label(lgn.jd))

    return found


def collect() -> list[Findings]:
    # Reads each case's `lg` golden, so it can only cover cases that have one.
    return [scan(case) for case in load_cases() if case.goldenable]


# ------------------------------------------------------------------- positive controls

def _strip_fields(node: dict[str, Any], names: tuple[str, ...]) -> None:
    node["fields"] = [f for f in node.get("fields", []) if f.get("name") not in names]


def _node_where(graph: dict[str, Any], predicate) -> dict[str, Any]:
    return next(n for n in graph["nodeDataArray"] if predicate(n))


def _control_row5(graph):
    _strip_fields(_node_where(graph, lambda n: n.get("category") == "Scatter"),
                  SCATTER_KEYS)


def _control_row5b(graph):
    _strip_fields(_node_where(graph, lambda n: n.get("category") == "Loop"), LOOP_KEYS)


def _control_row5d(graph):
    _node_where(graph, lambda n: n.get("category") == "Scatter").pop("categoryType", None)


def _control_row5e(graph):
    node = _node_where(graph, lambda n: n.get("category") == "File")
    node["category"] = "Data"
    node.pop("categoryType", None)


CONTROLS = [
    ("row5", "SuperBasicScatterGather", "`num_of_copies` stripped from the Scatter",
     _control_row5),
    ("row5b", "testLoop", "`num_of_iter` stripped from the Loop", _control_row5b),
    ("row5d", "SuperBasicScatterGather", "`categoryType` stripped from a Scatter node",
     _control_row5d),
    ("row5e", "HelloWorld_simple", "a File node forced to `category: Data` with no "
     "`categoryType`", _control_row5e),
]


def run_controls() -> list[tuple[str, str, bool]]:
    """Prove each rule can still fire, by feeding it a graph that should trip it.

    A scanner that reports nothing is indistinguishable from a broken one, and this
    corpus reports nothing for all four rows. The claim that the zero is real therefore
    rests entirely on these controls — so they are measured on every run and rendered
    from the measurement, rather than asserted in prose the generator prints regardless.

    Returns `(row, description, detected)` per control.
    """
    results = []
    for row, case_id, description, mutate in CONTROLS:
        try:
            graph = json.loads(read_golden(case_id, "lg"))
            mutate(graph)
            found = scan_raw(f"control:{row}", json.dumps(graph).encode())
        # pylint: disable=broad-exception-caught  # noqa: BLE001 - reported, not raised
        except Exception as failure:
            results.append((row, f"{description} — control itself failed: {failure}",
                            False))
            continue

        if getattr(found, row):
            results.append((row, description, True))
        elif found.error:
            # Once Phase 1a lands, a graph that trips row 5 or 5b stops building at all,
            # so the rule fires as an exception rather than as a row. That still counts —
            # but it is a different observation, and saying so keeps the two from
            # quietly becoming interchangeable.
            results.append((row, f"{description} (fired as `{found.error}`)", True))
        else:
            results.append((row, description, False))
    return results


ROWS = [
    ("row5", "Scatter with no DoP field",
     "silently 4 (lg_node.py:629)", "`GInvalidNode` naming the node", "#14"),
    ("row5b", "Loop with no iteration count",
     "`TypeError: 'NoneType'` from `range(None)`", "`GInvalidNode` naming the node", "#15"),
    ("row5d", "No `categoryType`, category in neither list",
     "bare `KeyError: 'categoryType'` (lg_node.py:60)", "`GInvalidNode`", "#26"),
    ("row5e", "No `categoryType`, category `Data`",
     "inferred `Application` (APP_TYPES wins)", "depends which list keeps `Data`", "#26"),
]


def render(findings: list[Findings],
           controls: list[tuple[str, str, bool]] | None = None) -> str:
    hits = [f for f in findings if not f.clean]
    controls = run_controls() if controls is None else controls
    lines = [
        "# Expected drift",
        "",
        "GENERATED by `tools/drift.py` — do not hand-edit.",
        "",
        "ARCHITECTURE_PROPOSAL §6 allows exactly one kind of golden change: the sanctioned",
        "§5 breaks. It also requires the affected graphs to be listed during Phase 0, so",
        "that when a golden moves in Phase 1a it is *expected* rather than investigated.",
        "This is that list.",
        "",
        "| Row | Condition | Nodes hit | Today | After the break | Issue |",
        "|---|---|---|---|---|---|",
    ]
    for key, condition, today, after, issue in ROWS:
        count = sum(len(getattr(f, key)) for f in findings)
        lines.append(
            f"| {key} | {condition} | **{count}** | {today} | {after} | {issue} |")
    lines += ["", f"Scanned {len(findings)} usable cases.", ""]

    if not hits:
        lines += [
            "## Nothing to expect",
            "",
            "**No corpus graph triggers any of these rows.** Every Scatter carries a DoP",
            "field, every Loop carries an iteration count, and every node carries a",
            "`categoryType`.",
            "",
            "That is a useful result, not an empty one: it means Phase 1a can turn all four",
            "into hard errors and **the goldens must not move at all**. Any golden diff",
            "during #14, #15 or #26 is a genuine regression, not sanctioned drift.",
            "",
            "It also means the corpus does not *cover* these paths — it cannot catch a",
            "mistake in the new error handling. Those issues need their own unit tests with",
            "purpose-built malformed graphs; the corpus will not do it for them.",
            "",
            "### Why believe a zero",
            "",
            "A rule scanner that reports nothing is indistinguishable from a broken one, so",
            "each row is positively controlled: a corpus graph is deliberately malformed and",
            "re-scanned. The table below is the result of running those controls during this",
            "report, not a claim recorded when they were last run by hand.",
            "",
            "| Row | Control | Detected |",
            "|---|---|---|",
        ]
        lines += [f"| {row} | {description} | {'yes' if detected else '**NO**'} |"
                  for row, description, detected in controls]
        lines += [
            "",
            "`scan_raw()` is split out from `scan()` precisely so those controls can be run",
            "against synthetic graphs.",
        ]
        if not all(detected for _, _, detected in controls):
            lines += [
                "",
                "> ⚠ **A control did not fire.** The zero above is unproven for that row —",
                "> the scanner may be reporting nothing because it cannot report anything.",
            ]
    else:
        lines += ["## Affected graphs", ""]
        for finding in hits:
            lines.append(f"### {finding.case}")
            lines.append("")
            if finding.error:
                lines += [f"Could not be built: `{finding.error}`", ""]
            for key, condition, _, _, issue in ROWS:
                for node in getattr(finding, key):
                    lines.append(f"- **{key}** ({issue}) — {condition}: `{node}`")
            lines.append("")

    errors = [f for f in findings if f.error]
    if errors and hits:
        lines += ["## Not scanned", ""]
        lines += [f"- `{f.case}`: {f.error}" for f in errors] + [""]
    return "\n".join(lines)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "show"
    if command not in ("report", "show"):
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    text = render(collect())
    if command == "report":
        REPORT.write_text(text)
        print(f"wrote {REPORT.relative_to(CORPUS)}")
    else:
        print(text)
    raise SystemExit(0)
