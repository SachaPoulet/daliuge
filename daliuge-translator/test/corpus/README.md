# Phase 0 golden corpus

Behaviour compatibility is the acceptance criterion for every phase of the translator
restructure ([ARCHITECTURE_PROPOSAL.md](../../ARCHITECTURE_PROPOSAL.md) §6). This directory
holds the frozen inputs that compatibility is measured against, and — once
[#5](https://github.com/SachaPoulet/daliuge/issues/5) and
[#6](https://github.com/SachaPoulet/daliuge/issues/6) land — the golden outputs produced from
them by the *pre-restructure* translator.

This is [#4](https://github.com/SachaPoulet/daliuge/issues/4).

## Layout

```
corpus/
├── MANIFEST.toml            generated: pins + sha256 of every vendored file
├── CASES.toml               hand-written: how each graph is driven, and what it produces
├── graphs/
│   ├── logical_graphs/      21 logical graphs
│   └── graph_config/        3 logical graphs + 2 .graphConfig files
├── golden/                  generated: the reference outputs, one directory per case
│   └── INDEX.toml           generated: sha256 + shape of every artefact
└── tools/
    ├── manifest.py          generate / verify MANIFEST.toml
    ├── cases.py             read / re-prove CASES.toml
    └── golden.py            generate / verify / show golden outputs
```

## Why the graphs are vendored rather than pip-installed

The rest of the test suite reaches for these graphs through the `daliuge_tests` package,
installed from `ICRAR/EAGLE_test_repo` at whatever `master` happens to be — see
[TestData.md](../TestData.md) and the `test` target in the top-level Makefile, which clones
the repo unpinned on every run.

That is fine for unit tests and fatal for a golden corpus: an upstream edit to a `.graph`
file would silently invalidate every stored output, and the resulting diff would look like a
regression in our code. So the inputs are copied into this repository and their hashes
recorded. `MANIFEST.toml` is the audit trail back to upstream.

## Pins

| Thing | Pin |
|---|---|
| `ICRAR/EAGLE_test_repo` | `2f1db6c` — release v0.2.4, `master` head as of 2026-01-22 |
| PyPI `eagle_test_graphs` | `0.2.4` |
| DALiuGE that generates the goldens | `c96d83fb` — merge-base of the restructure branch with `origin/master` |

Every vendored `.graph` / `.graphConfig` file is byte-identical to the one the pinned
`eagle_test_graphs==0.2.4` wheel installs, so results measured against the installed package
and against this directory are interchangeable.

## What was vendored, and what was not

Taken: everything under `eagle_test_graphs/daliuge_tests/translator/` that is a translator
**input** — the `.graph` and `.graphConfig` files.

Left behind, deliberately:

- `drop_spec/`, `go_js_json/`, `pickle/` — upstream's *expected outputs*, consumed by the
  existing `test/dropmake` unit tests. The corpus generates its own goldens from the pinned
  baseline; carrying upstream's as well would give two competing sources of truth.
- `dlg-lg*.schema` — the translator ships its own copies under `dlg/dropmake/` (see
  `MANIFEST.in`); these are stale duplicates.
- `__init__.py` markers — the corpus is read by path, not imported as a package.

## Bare-build coverage

Issue #4 asks which graphs work against a bare CLI build. Answer, measured on a clean venv
with no extras, `fill → unroll → partition -a metis → map`:

**19 of the 21 logical graphs translate end-to-end, and none of them needed an extra
dependency.** `Plasma_test`, `SharedMemoryTest_update` and `pyfunc_glob_shell_test` all pass:
translation never imports an app's payload, so the dependency question the issue anticipated
only bites at *execution* time, which Phase 0 does not test.

The two that do not pass fail for their own reasons, neither of them dependency-related:

| Graph | Stage | Failure |
|---|---|---|
| `cont_img_mvp` | `fill` | `KeyError: 'param1'` — unbound template parameters; needs `-p param1=… -p …`, the way `test_tool_trans.py` feeds `ArrayLoop`. Recoverable. |
| `ExampleSubgraphSimple` | `unroll` | `KeyError: 'fromPort'` — a defect in the current SubGraph path. Not recoverable from the CLI; excluded from the golden set and tracked as known-broken. |

## Driving the graphs — `CASES.toml`

A graph on its own is not runnable: `cont_img_mvp` needs four fill parameters, the
`graph_config/` graphs have two different config mechanisms, and one graph is expected to
fail. `CASES.toml` records all of that, one entry per (graph, preparation) pair — 28 cases,
27 of them usable. Golden generation reads it via `tools/cases.py`; nothing downstream should
walk `graphs/` directly.

```bash
python3 tools/cases.py list      # the manifest as a table
python3 tools/cases.py check     # re-run every case against its recorded expectation
```

`check` is a regression net in its own right, and it is bidirectional: an `ok` case that
starts failing is a break, a `known-broken` case that starts passing is *also* reported, so a
phase that accidentally fixes `ExampleSubgraphSimple` cannot do it silently.

Three things the manifest pins down that are easy to get wrong:

- **`fill` is not optional.** The CLI marks it deprecated, and a raw `.graph` fed straight to
  `unroll` does translate — but its reprodata comes out as `{}` instead of stamped. Since
  [#8](https://github.com/SachaPoulet/daliuge/issues/8) is about reprodata stamping, every
  case goes through `fill` or `fill-config`.
- **`-z` and `--app` stay off by default.** Zerorun rewrites `sleep_time` and `--app 1|2`
  overwrites every Application's `dropclass` — both erase translator output the corpus
  exists to protect. They are still translator code the restructure will move, so they get
  two dedicated cases on `testLoop` rather than a flag on every case: both are mechanical
  rewrites over the DROP list, independent of graph shape, so one carrier graph covers
  them. `testLoop` is that carrier because it is the smallest corpus graph where *both*
  flags change the output — `--app` bites on any graph with an Application, but `-z` only
  bites where a dropspec carries `sleep_time`, which most corpus graphs lack.
- **The two `graph_config` paths are different code.** An embedded `activeGraphConfigId` is
  applied by `LG.__init__` during `unroll` with no CLI flag at all
  ([lg.py:88](../../dlg/dropmake/lg.py#L88)); an external `.graphConfig` goes through
  `fill-config` → `pg_generator.apply_config` instead. Both are covered. The external path
  yields 79-83 DROPs against the embedded path's 23, and the EAGLE and non-EAGLE config
  formats differ from each other by 4 DROPs — so neither is a stand-in for the other.

## Verifying

```bash
cd daliuge-translator/test/corpus
python3 tools/manifest.py verify     # exit 1 on any drift
```

Re-pinning to a newer upstream commit means editing `PINS` in `tools/manifest.py`, replacing
the files under `graphs/`, running `generate`, and regenerating every golden output. It is a
deliberate act, not a refresh.

## Licence

The vendored graphs are the work of ICRAR, from `ICRAR/EAGLE_test_repo`, which is licensed
**GPL-3.0**. DALiuGE itself is **LGPL-2.1-or-later**. These files are test data — never
compiled, imported or linked into the distributed packages, and not part of any DALiuGE
wheel — but the licence difference is real and is recorded here rather than glossed over.

## Golden outputs

`golden/` holds what the **pre-restructure** translator produces for every usable case —
the reference each later phase is diffed against.

```bash
python3 tools/golden.py generate            # (re)produce golden/ from scratch
python3 tools/golden.py verify              # re-run and compare, exit 1 on drift
python3 tools/golden.py show <case> <name>  # print one artefact as JSON
```

Per case: `lg` (post-`fill`), `pgt` (post-`unroll`), then `pgtp` and `pg` for each
partition setting × algorithm. `INDEX.toml` records a sha256 and the shape
(elements, partitions, islands) of each, so drift is identified without decompressing.

### No checkout dance was needed

Goldens must come from `c96d83fb`, the recorded baseline. They do: this branch carries no
translator source change from that commit — `git diff c96d83fb HEAD -- daliuge-*/dlg` is
empty, and the installed packages are editable installs of this tree. The only Python added
since the baseline is corpus tooling under `test/corpus/tools/`. **Before regenerating,
re-check that diff.** Once a phase lands, the goldens can no longer be regenerated in place.

### Why the files are gzipped

The JSON is enormously repetitive — every DROP repeats the same reprodata and field
scaffolding — so it compresses about 20-30×. `cont_img_mvp`'s PGT alone is 888 KB raw and
30 KB gzipped. Uncompressed, the corpus would be tens of megabytes of files no human reads
directly and no PR review can meaningfully diff.

`gzip.compress(..., mtime=0)` is used deliberately: the default stamps the current clock
into the gzip header, which would make every regeneration differ byte-for-byte even when
the content is identical. Comparison is on the sha256 of the *decompressed* payload
regardless, so the storage format cannot mask a real change.

### Two CLI traps this tooling exists to absorb

**Never read a stage's output from stdout.** `mysarkar` and `min_num_parts` print
`Merging ugid ...` progress lines to stdout ahead of their JSON, so the documented
`partition | map` pipe hands `map` an unparseable stream — the failure looks like corrupt
JSON, not like a chatty algorithm. Every stage here writes with `-o` to a file, which is
clean for all three algorithms.

**`partition` swallows its own failure.** `GPGTNoNeedMergeException` is caught in
`dlg_partition`, printed as prose, and the *unpartitioned* graph is emitted with exit
code 0. A generator trusting the exit code would store an unpartitioned graph as a
partitioned golden. `golden.py` matches that prose and records the outcome instead.

### Partition settings

Two, because one cannot do both jobs.

| Setting | Algorithms | `-N` / `-i` | Why |
|---|---|---|---|
| `n2i1` | metis, mysarkar, min_num_parts | 2 / 1 | The only setting all three survive — mysarkar and min_num_parts hit NoNeedMerge at 4 partitions even on a 22-DROP graph. The comparable-across-the-corpus baseline. |
| `n8i2` | metis | 8 / 2 | `n2i1` leaves most of the corpus at one partition and one island, exercising none of the island-forming code. Small graphs NoNeedMerge here; that is recorded per case, not treated as an error. |

The `map -N` host list is **not** recorded in `CASES.toml`, because it cannot be sized in
advance. `resource_map` takes the first `-i` entries as island managers and the rest as node
managers, then subscripts each slice by the index parsed out of the DROP's label — so the
list must cover the highest index the partitioner actually emitted. That is neither the
requested `-N` (mysarkar and min_num_parts overshoot it on larger graphs) nor the number of
distinct partitions (metis leaves gaps — an 11-DROP graph lands on `#0, #2, #3, #5, #7`:
five partitions, eight entries needed). Undersized, `map` dies with a bare `IndexError`.

`golden.py` reads each PGT-P back, takes the highest node and island index, and builds
`dim0…` + `nm0…` to match, passing that island count as `map -i` for the same reason. Hosts
are named rather than all `localhost` so a change in *which* partition lands on *which*
manager surfaces as a diff instead of hiding among identical strings.

### How much the three algorithms are actually worth

Measured over the generated corpus, the coverage is not evenly distributed, and it is worth
knowing that before trusting a green `verify`:

| | Partitions produced |
|---|---|
| `metis` @ `n2i1` | 2 in all 28 cases |
| `mysarkar` @ `n2i1` | 1 in 21 cases, 2 in 2, 3 in 5 |
| `min_num_parts` @ `n2i1` | identical to `mysarkar`, in all 28 cases, byte for byte |
| `metis` @ `n8i2` | 8 in 16 cases, 7 in 2 (10 cases NoNeedMerge) |

Two consequences. **`mysarkar` and `min_num_parts` are the same golden**: `min_num_parts`
subclasses the mysarkar scheduler and they do not diverge anywhere in this corpus. They are
both kept — if a later phase makes them differ, that is a signal worth catching — but they
are one algorithm's worth of coverage, not two. And **both collapse to a single partition on
three quarters of the corpus**: they are bottom-up merging schedulers that treat `-N` as a
ceiling rather than a target, so raising it changes nothing on most graphs (`ArrayLoop` goes
3 → 5 → 6 partitions as `-N` goes 2 → 4 → 8; `testLoop` and `chiles_simple` stay at 1 no
matter what). Real partitioning coverage rests on `metis`.

Relatedly, NoNeedMerge is driven by **islands, not partitions** — `-N 16 -i 1` is fine where
`-N 4 -i 2` is not, which matches the CLI's own advice to reduce the island count.

### Algorithm coverage is 3 of 5, not by choice

`known_algorithms()` offers five. Two do not work in the current build, so no golden can
exist for them:

| Algorithm | State |
|---|---|
| `metis`, `mysarkar`, `min_num_parts` | Usable (with `-o`; see above). |
| `none` | `GPGTException: The graph has not been partitioned yet` — `to_pg_spec` rejects the unpartitioned graph the option exists to produce. |
| `pso` | `ValueError: too many values to unpack (expected 2)` at `scheduler.py:837`; the installed `pso()` no longer returns a 2-tuple. |

This narrows ARCHITECTURE_PROPOSAL §6, which asks for "all five algorithms" and treats
`pso` as merely stochastic ("seed it and compare byte-for-byte"). `pso` is not stochastic
here, it is broken, and `none` never worked through this path. Both want their own issues.
