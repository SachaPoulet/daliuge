#!/usr/bin/env python3
"""Generate and verify the corpus MANIFEST.toml.

The manifest is the record of *where the Phase 0 corpus came from*. Regenerate it
only when the vendored inputs are deliberately re-pinned to a new upstream commit;
the rest of the time, run ``verify`` to prove the working tree still matches.

    python3 tools/manifest.py verify      # exit 1 on any drift
    python3 tools/manifest.py generate    # rewrite MANIFEST.toml from disk
"""

import hashlib
import sys
import tomllib
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent
MANIFEST = CORPUS / "MANIFEST.toml"
GRAPHS = CORPUS / "graphs"

# Where the vendored files came from, upstream. Everything under graphs/ *except*
# graphs/authored/ is a verbatim copy of the same-named file under this prefix at the
# pinned commit.
UPSTREAM_PREFIX = "eagle_test_graphs/daliuge_tests/translator"

# Graphs we wrote ourselves, because no upstream repository contains one. They carry no
# upstream path and are not covered by the pins — recording them as vendored would be a
# false provenance claim.
AUTHORED_DIR = "authored"

PINS = {
    "eagle_test_repo_url": "https://github.com/ICRAR/EAGLE_test_repo",
    "eagle_test_repo_commit": "2f1db6c99898c43a25d9a7d3a07acf8cfb7becff",
    "eagle_test_repo_release": "v0.2.4",
    "eagle_test_repo_tarball_sha256":
        "f27c424f7ed8a331197c1dd1bad6c02fc5178b4664a4691fe00cbffab6136558",
    "eagle_test_graphs_pypi_version": "0.2.4",
    "daliuge_baseline_commit": "c96d83fb56d523bfcf43e061a822e960dc48a2f6",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus_files() -> list[Path]:
    return sorted(p for p in GRAPHS.rglob("*") if p.is_file())


def generate() -> int:
    lines = [
        "# Phase 0 corpus manifest — GENERATED, do not hand-edit.",
        "# Regenerate with: python3 tools/manifest.py generate",
        "# Verify with:     python3 tools/manifest.py verify",
        "",
        "[pins]",
    ]
    for key, value in PINS.items():
        lines.append(f'{key} = "{value}"')
    lines += ["", f'upstream_prefix = "{UPSTREAM_PREFIX}"', ""]

    for path in corpus_files():
        rel = path.relative_to(GRAPHS).as_posix()
        origin = ('origin = "authored"' if rel.startswith(f"{AUTHORED_DIR}/")
                  else f'upstream = "{UPSTREAM_PREFIX}/{rel}"')
        lines += [
            "[[files]]",
            f'path = "{rel}"',
            origin,
            f'sha256 = "{digest(path)}"',
            "",
        ]

    MANIFEST.write_text("\n".join(lines))
    print(f"wrote {MANIFEST.relative_to(CORPUS)} ({len(corpus_files())} files)")
    return 0


def verify() -> int:
    manifest = tomllib.loads(MANIFEST.read_text())
    recorded = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    on_disk = {p.relative_to(GRAPHS).as_posix(): digest(p) for p in corpus_files()}

    problems = []

    # The pins are the corpus's whole provenance claim — which upstream commit the graphs
    # came from, and which DALiuGE produced the goldens. They live in PINS above so they
    # are reviewed as code; checking them here is what stops the copy in MANIFEST.toml
    # being edited to agree with whatever was actually run.
    # `generate` emits upstream_prefix after the PINS block with no new table header, so
    # TOML reads it as one more key of [pins]. Expected here rather than at top level.
    expected_pins = {**PINS, "upstream_prefix": UPSTREAM_PREFIX}
    pins = manifest.get("pins", {})
    for key, value in expected_pins.items():
        if key not in pins:
            problems.append(f"pin missing:  {key}")
        elif pins[key] != value:
            problems.append(f"pin altered:  {key} = {pins[key]!r}, expected {value!r}")
    for key in sorted(set(pins) - set(expected_pins)):
        problems.append(f"pin unlisted: {key}")

    for rel, sha in sorted(recorded.items()):
        if rel not in on_disk:
            problems.append(f"missing:  {rel}")
        elif on_disk[rel] != sha:
            problems.append(f"modified: {rel}")
    for rel in sorted(set(on_disk) - set(recorded)):
        problems.append(f"unlisted: {rel}")

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s); corpus does not match the manifest",
              file=sys.stderr)
        return 1
    print(f"corpus matches the manifest ({len(recorded)} files)")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if command not in ("generate", "verify"):
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(generate() if command == "generate" else verify())
