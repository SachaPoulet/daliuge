# LG to PG golden test suite

This directory contains the Issue #5 seed compatibility test and the completed
manifest-driven Issue #6 corpus suite. It protects the
translator wire format at four boundaries:

1. LG after `dlg fill`;
2. PGT after `dlg unroll`;
3. partitioned PGT (PGT-P) after `dlg partition`;
4. PG after `dlg map`.

The test intentionally does not submit or execute the graph. It uses repository
fixtures only, does not access the network, and writes candidate output only to
pytest's temporary directory.

## Frozen Issue #6 scope

Issue #6 is frozen to two independently pinned corpora:

- 90 graphs under `test/corpus/graphs/eagle-graphs`, copied from
  `ICRAR/EAGLE-graph-repo` commit
  `829e3efc6dc7f86b79c12ec4381f24c72f30f4a8` (84 runnable and 6 known-bad);
- 21 graphs under `test/corpus/graphs/eagle-test-graphs`, copied from
  `ICRAR/EAGLE_test_repo` commit
  `2f1db6c99898c43a25d9a7d3a07acf8cfb7becff` (20 runnable and 1 known-bad).

The manifest stores those scopes in a dictionary keyed by corpus name and
records a separate inventory SHA-256 over each sorted repository-relative path
and file digest. A fast contract test iterates both corpora and detects graph
additions, removals, renames, content changes, known-bad classification drift,
missing cases, and unreferenced fixture files. All 104 runnable base graphs have
complete LG, PGT, PGT-P, and PG legacy outputs, along with the additional
`ADACS_MWA_Compress_Graph` METIS 8-partition/2-island variant.

## Pinned baseline and pipeline profiles

`inputs/ArrayLoop.graph` is copied without modification from
`ICRAR/EAGLE_test_repo` commit
`2f1db6c99898c43a25d9a7d3a07acf8cfb7becff`, path
`eagle_test_graphs/daliuge_tests/translator/logical_graphs/ArrayLoop.graph`.
Its SHA-256 is recorded in `manifest.json` and verified before each run. The
source repository publishes the graph under GPL-3.0.

The legacy baseline is DALiuGE commit
`c96d83fb56d523bfcf43e061a822e960dc48a2f6`. Before replacing any expected
fixture, maintainers must confirm that this remains the intended pre-refactor
baseline. All graph source, environment, CLI options and fixture hashes are
recorded in `manifest.json`.

The Issue #5 seed retains its original `-z --app 1` invocation. The 84
runnable `eagle-graphs` cases use empty fill parameters, reproducibility mode
0, OID prefix `1`, and the unroll defaults so sleep times and application
classes remain visible to the regression test. 82 use METIS two-way
partitioning. The two `wsclean_*` graphs use mysarkar because legacy METIS
rejects their string node weights; that exception is explicit in the manifest.

The 20 runnable `eagle-test-graphs` cases use the same defaults and METIS
two-way partitioning. Nineteen use empty fill parameters.
`cont_img_mvp.graph` requires `param1=hello`, `param2=1`,
`param1.param2=hi`, and `param4.what=False`; those values are pinned in its
case. The separate `ADACS_MWA_Compress_Graph` variant uses METIS with 8
partitions and 2 islands.

Map resources are derived from the highest actual `node` and `island` labels
in each PGT-P, rather than assuming the requested partition count. The runner
also rejects the legacy partition command's exit-0/no-label
`GPGTNoNeedMergeException` behavior as an incomplete pipeline.

Each stage is stored independently as deterministic `*.json.gz` with both
compressed and uncompressed SHA-256 digests. Paired legacy candidate runs were
byte-for-byte identical. The 424 fixtures contain 215,011,270 bytes of raw JSON
and occupy 6,003,741 bytes after compression. The JSON includes the trailing
reproducibility payload; the test does not remove or broadly ignore fields.

## Run the regression test

From the repository root with the DALiuGE development environment active:

```bash
python -m pytest -q \
  daliuge-translator/test/golden/test_single_graph_golden.py
```

A complete run currently collects 124 tests: 106 golden cases, 7 exact
known-bad checks, and 11 contract/comparator tests.

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
the normal test. Use an isolated worktree and virtual environment. The engine
package is not required:

```bash
CURRENT="$PWD"
LEGACY="../daliuge-legacy"
LEGACY_VENV="../daliuge-legacy-venv"

git worktree add --detach "$LEGACY" \
  c96d83fb56d523bfcf43e061a822e960dc48a2f6
python3 -m venv "$LEGACY_VENV"
"$LEGACY_VENV/bin/python" -m pip install \
  -r "$CURRENT/daliuge-translator/test/golden/legacy-requirements.txt"

(
  cd "$LEGACY/daliuge-common"
  "$LEGACY_VENV/bin/python" -m pip install \
    --no-deps --no-build-isolation -e .
)
(
  cd "$LEGACY/daliuge-translator"
  "$LEGACY_VENV/bin/python" -m pip install \
    --no-deps --no-build-isolation -e .
)
"$LEGACY_VENV/bin/dlg" version
```

Return to the current worktree and generate into a review directory:

```bash
PYTHONPATH=daliuge-translator python -m test.golden.generate_single_graph_golden \
  --dlg ../daliuge-legacy-venv/bin/dlg \
  --legacy-repo ../daliuge-legacy \
  --output-dir /tmp/issue6-golden-review-a \
  --quiet
```

Use `--case NAME` one or more times for a subset; omitting it generates every
case. The generator verifies the clean legacy worktree HEAD and the Git version
reported by the supplied `dlg`, strips the caller's Python import path from
legacy subprocesses, requires an empty review directory, and refuses to write
into or around committed `expected/` directories.

It mirrors the committed `expected/` layout and writes
`manifest.generated.json` with fixture metadata. Before accepting a full
baseline, generate a second directory and require both trees and manifests to
match:

```bash
diff -rq /tmp/issue6-golden-review-a/expected \
  /tmp/issue6-golden-review-b/expected
cmp /tmp/issue6-golden-review-a/manifest.generated.json \
  /tmp/issue6-golden-review-b/manifest.generated.json
```

Review the structural changes before deliberately copying the candidate
`expected/` tree and manifest into this directory.

## Known limits

- The 7 known-bad corpus entries have stage-specific expected-failure checks.
  If one is fixed, its test fails so maintainers can reclassify it deliberately.
- It does not start the Engine or validate workflow business output.
- The complete suite is intentionally slower than the contract-only checks;
  use pytest's `-k` selection only for local iteration, not delivery sign-off.
