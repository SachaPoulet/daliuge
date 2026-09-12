# LG to PG golden test suite

This directory contains the Issue #5 seed compatibility test and the
manifest-driven test suite being extended by Issue #6. It protects the
translator wire format at four boundaries:

1. LG after `dlg fill`;
2. PGT after `dlg unroll`;
3. partitioned PGT (PGT-P) after `dlg partition`;
4. PG after `dlg map`.

The test intentionally does not submit or execute the graph. It uses repository
fixtures only, does not access the network, and writes candidate output only to
pytest's temporary directory.

## Frozen Issue #6 scope

Issue #6 is frozen to the 90 graphs bundled by Issue #4 under
`test/corpus/graphs/eagle-graphs`, copied from `ICRAR/EAGLE-graph-repo` commit
`829e3efc6dc7f86b79c12ec4381f24c72f30f4a8`. That set contains 84 translation
candidates and 6 known-bad graphs. PR #51 is deliberately excluded from this
scope.

The manifest records an inventory SHA-256 over each sorted repository-relative
path and file digest. A fast contract test detects graph additions, removals,
renames, content changes, or known-bad classification drift.

Freezing the corpus does not claim that all 84 candidates already have legacy
golden outputs. At present, `ArrayLoop-metis` is the only complete four-stage
case. New corpus cases are added only after their pipeline configuration and
legacy outputs have been reviewed.

## Initial pinned case and baseline

`inputs/ArrayLoop.graph` is copied without modification from
`ICRAR/EAGLE_test_repo` commit
`2f1db6c99898c43a25d9a7d3a07acf8cfb7becff`, path
`eagle_test_graphs/daliuge_tests/translator/logical_graphs/ArrayLoop.graph`.
Its SHA-256 is recorded in `manifest.json` and verified before each run. The
source repository publishes the graph under GPL-3.0.

The current legacy baseline is DALiuGE commit
`c96d83fb56d523bfcf43e061a822e960dc48a2f6`. Before replacing any expected
fixture, maintainers must confirm that this remains the intended pre-refactor
baseline. All graph source, environment, CLI options and fixture hashes are
recorded in `manifest.json`.

The fixtures were produced before adding this test. Two consecutive runs were
byte-for-byte identical for LG, PGT, PGT-P and PG with METIS two-way partitioning.
The JSON includes the trailing reproducibility payload; the test does not remove
or broadly ignore fields.

## Run the regression test

From the repository root with the DALiuGE development environment active:

```bash
python -m pytest -q \
  daliuge-translator/test/golden/test_single_graph_golden.py
```

The runner locates `dlg` in the active environment. Set `DLG_CLI` only when the
console script is elsewhere:

```bash
DLG_CLI=/path/to/venv/bin/dlg python -m pytest -q \
  daliuge-translator/test/golden/test_single_graph_golden.py
```

Objects are compared structurally, so indentation and object-key order do not
matter. Array order, lengths, field names, JSON types and values must match. A
failure identifies the earliest stage and first differing JSON path, for
example:

```text
Stage: PGT-P
Path: $[7].node
Expected: "#0"
Actual:   "#1"
```

## Regenerate candidate fixtures

Expected files are review artifacts and must never be rebuilt automatically by
the normal test. Use an isolated worktree and virtual environment:

```bash
git worktree add ../daliuge-legacy \
  c96d83fb56d523bfcf43e061a822e960dc48a2f6
python3 -m venv ../daliuge-legacy-venv
source ../daliuge-legacy-venv/bin/activate
cd ../daliuge-legacy
python -m pip install --upgrade pip setuptools wheel
make local
```

Return to the current worktree and generate into a review directory:

```bash
PYTHONPATH=daliuge-translator python -m test.golden.generate_single_graph_golden \
  --dlg ../daliuge-legacy-venv/bin/dlg \
  --legacy-repo ../daliuge-legacy \
  --case ArrayLoop-metis \
  --output-dir /tmp/issue6-golden-review
```

Omit `--case` to generate every manifest case. When multiple cases are selected,
each writes to its own named subdirectory. The generator verifies both the
legacy worktree HEAD and the Git version reported by the supplied `dlg`, and
refuses to write into or around committed `expected/` directories. Review the
structural diff and printed hashes before deliberately copying LG, PGT, PGT-P
and PG into `expected/` and updating the manifest hashes.

## Known limits

- The runner supports multiple manifest cases, but only the Issue #5
  `ArrayLoop-metis` seed currently has reviewed four-stage golden outputs.
- The 6 known-bad corpus entries have stage-specific expected-failure checks.
  If one is fixed, its test fails so maintainers can reclassify it deliberately.
- It does not start the Engine or validate workflow business output.
- The manifest records key dependency versions but is not a complete dependency
  lock. If dependency drift affects output, reproduce the recorded environment
  before approving a baseline change.
