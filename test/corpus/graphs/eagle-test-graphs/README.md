# EAGLE translator test graphs (supplementary corpus)

Closes #50.

This is a **second, additional** graph corpus alongside the one PR #41 bundled
from `EAGLE-graph-repo` (issue #4, merged) — not a replacement for it. Per
client feedback, the more test coverage the better, so both sources are kept:
#41's operational graphs from `EAGLE-graph-repo`
(`test/corpus/graphs/eagle-graphs/`), and this directory, sourced from the
client-designated test repository named directly in their feedback
("Additional Information" section): `https://github.com/icrar/EAGLE_test_repo`,
translator-specific directory at `eagle_test_graphs/daliuge_tests/translator`.

Pinned to `ICRAR/EAGLE_test_repo` commit `2f1db6c99898c43a25d9a7d3a07acf8cfb7becff`
(2026-01-22), from `eagle_test_graphs/daliuge_tests/translator/logical_graphs/`.

Surveyed all 21 `.graph` files (the 3 `.schema`/`.json.schema` files in that
directory are schema definitions, not test graphs, and are excluded) by
loading each graph's raw JSON and running it through `unroll -> partition`
(`metis`, 2 partitions / 1 island) -- the same `pg_generator` entry points
PR #41's survey used. Note this survey does not go through the `dlg fill`
CLI step; it feeds the on-disk LG JSON straight to `unroll()`.

- **20 run cleanly** and are included as-is.
- **1 is a known-broken fixture**, kept deliberately rather than excluded:

| Graph | Known issue |
|---|---|
| `ExampleSubgraphSimple.graph` | Fails during `unroll` with `KeyError: 'fromPort'` -- genuine issue in the graph's link data, unrelated to missing dependencies. Kept as a fixture for testing how the pipeline surfaces malformed-link errors. |

Unlike PR #41's corpus, nothing was excluded here for needing app-specific
dependencies (RASCIL/casacore/astropy/numpy.recarray) — this directory is
purpose-built as a translator test corpus, so it doesn't carry the
production-graph baggage that repo does. That's a difference in what each
source happens to contain, not a claim that this corpus is more "correct"
than #41's — both are being kept, per client direction.
