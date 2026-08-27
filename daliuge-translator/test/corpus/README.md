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
└── tools/
    ├── manifest.py          generate / verify MANIFEST.toml
    └── cases.py             read / re-prove CASES.toml
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
fail. `CASES.toml` records all of that, one entry per (graph, preparation) pair — 26 cases,
25 of them usable. Golden generation reads it via `tools/cases.py`; nothing downstream should
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
- **`-z` and `--app` stay off.** Zerorun rewrites `sleep_time` and `--app 1|2` overwrites
  every Application's `dropclass` — both erase translator output the corpus exists to
  protect. Wanted as a variant, they should be extra cases, not changed defaults.
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
