# Translator Rewrite — Source-to-Target Migration Map

Companion to [ARCHITECTURE_PROPOSAL.md](ARCHITECTURE_PROPOSAL.md). Answers one question for
every proposed file: **where does its code come from?**

Built from a line-level read of `dlg/dropmake/**` and `dlg/translator/**` on 2026-08-09.
Line numbers are against the current `base-architecture` branch. Ranges marked *approx* were
inferred from block structure rather than counted exactly — verify before cutting.

## How to read this

| Verb | Meaning |
|------|---------|
| **MOVE** | Code transfers essentially unchanged. `git mv` or cut-and-paste. Lowest risk. |
| **SPLIT** | One current function feeds two or more target files. Cut along a stated seam. |
| **EXTRACT** | A block inside a larger function becomes a function of its own in the target. |
| **REWRITE** | Same behaviour, new shape. Target does not resemble the source. Highest risk. |
| **NEW** | No source. Must be written. See §5. |
| **DELETE** | Confirmed dead or superseded. See §6. |
| **FACADE** | Old symbol stays as a thin delegator for an external caller. See proposal §7. |

---

## 1. Coverage summary

Every current source file, and where it ends up. 8258 LOC total.

| Current file | LOC | Disposition |
|--------------|-----|-------------|
| `pg_generator.py` | 267 | SPLIT across all four `stages/*/stage.py` + FACADE (engine imports it) |
| `dm_utils.py` | 1030 | SPLIT into `stages/prepare/**` + `errors.py`; ~340 LOC DELETE |
| `graph_config.py` | 262 | MOVE → `stages/prepare/config.py` |
| `lg.py` | 825 | SPLIT into `stages/unroll/**`; `unroll_to_tpl` REWRITE |
| `lg_node.py` | 1025 | SPLIT into `stages/unroll/{model,constructs/**}` |
| `definition_classes.py` | 122 | MOVE → `stages/unroll/constructs/vocabulary.py`; MKN entries DELETE |
| `pgt.py` | 495 | SPLIT across `partition/**`, `projections/`, `map/`, `artefacts.py` |
| `pgtp.py` | 665 | SPLIT into `partition/algorithms/*` + `partition/islands.py` |
| `scheduler.py` | 1261 | MOVE → `partition/{dag.py, algorithms/**}` |
| `utils/**` | ~843 | MOVE → `partition/algorithms/utils/` — **all four modules, `bash_parameter.py` included**. Landed 2026-08-31 (P2-3); see §6 for why the three unused ones are retained |
| `tool_commands.py` | 638 | SPLIT: CLI arg plumbing MOVE, pipeline bodies REWRITE |
| `web/translator_utils.py` | 185 | Tier 2 — mostly MOVE; one function REWRITE (proposal §6 Phase 7) |
| `web/translator_rest.py` | 1247 | Tier 2 — call-site edits only |
| `pg_manager.py` | 170 | Tier 2 — MOVE with `web/` |

---

## 2. `stages/prepare/` — LGT → LG

| Target | Verb | Source |
|--------|------|--------|
| `loader.py` | MOVE | `dm_utils.load_lg` [:1020-1030](dlg/dropmake/dm_utils.py#L1020) |
| `versions.py` | MOVE | `dm_utils.get_lg_ver_type` [:58-107](dlg/dropmake/dm_utils.py#L58); plus the version→recipe `if/elif` EXTRACTed from `LG.__init__` [lg.py:91-102](dlg/dropmake/lg.py#L91-L102) — turn the three branches into a `dict[version, list[normaliser]]` |
| `config.py` | MOVE | all of `graph_config.py`; exceptions [:37-66](dlg/dropmake/graph_config.py#L37) → `errors.py` |
| `params.py` | MOVE | `pg_generator.{_LGTemplate, _flatten_dict, fill}` [:41-64](dlg/dropmake/pg_generator.py#L41) |
| `normalise/globals.py` | MOVE | `dm_utils.extract_globals` [:788-837](dlg/dropmake/dm_utils.py#L788) |
| `normalise/fields.py` | MOVE | `dm_utils.convert_fields` [:120-143](dlg/dropmake/dm_utils.py#L120) |
| `normalise/constructs.py` | MOVE | `dm_utils.convert_construct` [:410-544](dlg/dropmake/dm_utils.py#L410) + helpers `_create_from_node` [:545-593](dlg/dropmake/dm_utils.py#L545), `_has_app_keywords` [:594-618](dlg/dropmake/dm_utils.py#L594), `_update_keys` [:619-641](dlg/dropmake/dm_utils.py#L619) |
| `normalise/subgraphs.py` | MOVE | `dm_utils.convert_subgraphs` [:838-914](dlg/dropmake/dm_utils.py#L838) + `identify_and_connect_output_input` [:642-679](dlg/dropmake/dm_utils.py#L642), `_extract_subgraph_nodes` [:680-748](dlg/dropmake/dm_utils.py#L680), `_build_apps_from_subgraph_construct` [:749-787](dlg/dropmake/dm_utils.py#L749) |
| `normalise/_index.py` | MOVE | shared helpers `get_keyset` [:108-111](dlg/dropmake/dm_utils.py#L108), `_build_node_index` [:144-151](dlg/dropmake/dm_utils.py#L144) — called from `convert_construct` and `convert_subgraphs` |
| `stage.py` | REWRITE | sequencing logic currently inlined in `LG.__init__` [lg.py:73-102](dlg/dropmake/lg.py#L73-L102): load → ssid default → `apply_active_configuration` → version recipe. The `LGNode` construction that follows (lines 104-154) belongs to `unroll/`, not here — that is the seam. |

**Note on `convert_construct`.** Proposal §8 Q1 established it could legally move to
unroll-time. This map keeps it in `prepare/normalise/` — moving stages *and* moving code is
two risks at once. Revisit after Phase 4.

---

## 3. `stages/unroll/` — LG → PGT

The hard part. `lg.py` + `lg_node.py` = 1850 LOC, and the construct `if/elif` chains inside
them are what `constructs/` exists to dissolve.

### 3.1 Straightforward

| Target | Verb | Source |
|--------|------|--------|
| `model.py` | MOVE | `LGNode.__init__` [lg_node.py:47-98](dlg/dropmake/lg_node.py#L47) and the plain accessors `jd`/`id`/`name`/`category`/`categoryType`/`group`/`children`/`inputs`/`outputs`/`weight`/`h_level`/`group_hierarchy` [:126-344](dlg/dropmake/lg_node.py#L126). Strip the `is_*` predicates — those become handler identity. |
| `model.py` | MOVE | `LGNode.{add_output, add_input, add_child}` [:256-287](dlg/dropmake/lg_node.py#L256) — note `add_child` [:270-287](dlg/dropmake/lg_node.py#L270) already branches on scatter/loop/groupby; that branch becomes a handler call |
| `stage.py` | MOVE | `pg_generator.unroll` [:79-96](dlg/dropmake/pg_generator.py#L79) — the `zerorun` / `app=` post-passes and the final flatten from `unroll_to_tpl` [lg.py:812-816](dlg/dropmake/lg.py#L812) |
| `validate.py` | SPLIT | `LG.validate_link` [:156-251](dlg/dropmake/lg.py#L156) — each clause routes to a handler `validate_as_source` / `validate_as_target` (§3.4) |
| `coordinate.py` | REWRITE | the `iid` string arithmetic: construction at [lg.py:328-334](dlg/dropmake/lg.py#L328), the `np.unravel_index` multi-key encoding at [lg.py:317-325](dlg/dropmake/lg.py#L317), and the three parse sites — `split("-")` [lg.py:702](dlg/dropmake/lg.py#L702), `split("$")[1].split("-")` [lg.py:717](dlg/dropmake/lg.py#L717), `"-".join(src_ctx[0:-2])` [lg.py:710](dlg/dropmake/lg.py#L710). `__str__` must reproduce all three forms exactly. |
| `instantiate.py` | REWRITE | driver loop [lg.py:553-556](dlg/dropmake/lg.py#L553), the DoP loop skeleton [lg.py:327-359](dlg/dropmake/lg.py#L327), and the cleanup deletions [lg.py:786-806](dlg/dropmake/lg.py#L786) — the latter becomes a per-handler `finalise()` rather than one `if/elif` over `_done_dict` |
| `wire.py` | REWRITE | the link loop and its dispatch [lg.py:563-573](dlg/dropmake/lg.py#L563) + the default chunked distribution [lg.py:683-691](dlg/dropmake/lg.py#L683); helpers `_split_list` [:389-395](dlg/dropmake/lg.py#L389), `_get_chunk_size` [:408-420](dlg/dropmake/lg.py#L408), `_is_stream_link` [:421-435](dlg/dropmake/lg.py#L421) MOVE as-is |
| `wire.py` | SPLIT | `_link_drops` [:436-544](dlg/dropmake/lg.py#L436): the three wiring styles — stream/NullDROP [:466-491](dlg/dropmake/lg.py#L466), App/Control port_map [:492-511](dlg/dropmake/lg.py#L492), data consumer/input [:520-541](dlg/dropmake/lg.py#L520) — stay here as `Edge` emitters. The gather-cache writes [:454-460](dlg/dropmake/lg.py#L454) and [:512-518](dlg/dropmake/lg.py#L512) DELETE. |

### 3.2 `constructs/*.py` — where each construct's scattered pieces land

Every handler file draws from four current locations. This is the table to work from.

| Handler | `degree_of_parallelism` | `instantiate` | `synthesise_links` | `resolve_edges` | `validate_*` |
|---------|------------------------|---------------|--------------------|-----------------|--------------|
| **scatter.py** | [lg_node.py:619-629](dlg/dropmake/lg_node.py#L619) (incl. the `4` default) | none — Scatter emits no DROP; loop body at [lg.py:327-359](dlg/dropmake/lg.py#L327) | none | within-group len-equality link [lg.py:604-611](dlg/dropmake/lg.py#L604) | [lg.py:158-165](dlg/dropmake/lg.py#L158) |
| **gather.py** | [lg_node.py:630-641](dlg/dropmake/lg_node.py#L630) + `gather_width` [:510-525](dlg/dropmake/lg_node.py#L510) | `_create_gather_drops` [lg_node.py:814-848](dlg/dropmake/lg_node.py#L814) | group-start artificial links [lg.py:302-315](dlg/dropmake/lg.py#L302) | sequentialisation [lg.py:577-601](dlg/dropmake/lg.py#L577); as target [lg.py:743-746](dlg/dropmake/lg.py#L743) via `_unroll_gather_as_output` [:396-407](dlg/dropmake/lg.py#L396); **cache drain [lg.py:761-782](dlg/dropmake/lg.py#L761) DELETE** | [lg.py:171-182](dlg/dropmake/lg.py#L171), [:200-209](dlg/dropmake/lg.py#L200) |
| **loop.py** | [lg_node.py:644-651](dlg/dropmake/lg_node.py#L644) — **and add the missing fallback**, §7 B4 | none — Loop emits no DROP | iteration circle [lg.py:287-301](dlg/dropmake/lg.py#L287) | end→start relink [lg.py:620-645](dlg/dropmake/lg.py#L620); cross-loop stepwise lock [lg.py:646-655](dlg/dropmake/lg.py#L646); `loop_aware` first/last iteration [lg.py:657-682](dlg/dropmake/lg.py#L657) | [lg.py:166-170](dlg/dropmake/lg.py#L166), [:218-232](dlg/dropmake/lg.py#L218) |
| **groupby.py** | [lg_node.py:642-643](dlg/dropmake/lg_node.py#L642) + `groupby_width` [:526-543](dlg/dropmake/lg_node.py#L526) + `group_by_scatter_layers` [:544-611](dlg/dropmake/lg_node.py#L544) + `group_keys` [:489-509](dlg/dropmake/lg_node.py#L489) | `_create_groupby_drops` [lg_node.py:779-813](dlg/dropmake/lg_node.py#L779); multikey shape [lg.py:317-325](dlg/dropmake/lg.py#L317) | group-start links [lg.py:302-315](dlg/dropmake/lg.py#L302) | key bucketing [lg.py:693-742](dlg/dropmake/lg.py#L693) — **the `iid` parsing here is what `coordinate.py` replaces**; GroupBy→Gather [lg.py:612-616](dlg/dropmake/lg.py#L612) | [lg.py:183-199](dlg/dropmake/lg.py#L183), [:210-217](dlg/dropmake/lg.py#L210) |
| **mpi.py** | [lg_node.py:663-664](dlg/dropmake/lg_node.py#L663) | [lg.py:360-367](dlg/dropmake/lg.py#L360); rank handling [lg_node.py:307-312](dlg/dropmake/lg_node.py#L307) | none | default | none |
| **service.py** | [lg_node.py:653-654](dlg/dropmake/lg_node.py#L653) | no-op [lg.py:368-370](dlg/dropmake/lg.py#L368); `make_single_drop` service branch [lg_node.py:995-1001](dlg/dropmake/lg_node.py#L995) | none | [lg.py:747-752](dlg/dropmake/lg.py#L747) — **dead, DELETE in P4-2, §7 B1** | none |
| **subgraph.py** | [lg_node.py:655-656](dlg/dropmake/lg_node.py#L655) | [lg.py:371-377](dlg/dropmake/lg.py#L371) | none | pass-throughs [lg.py:602-603](dlg/dropmake/lg.py#L602), [:753-754](dlg/dropmake/lg.py#L753) | none |
| **leaf.py** | `1` [lg_node.py:665-666](dlg/dropmake/lg_node.py#L665) | [lg.py:378-388](dlg/dropmake/lg.py#L378) + `make_single_drop` [lg_node.py:962-1011](dlg/dropmake/lg_node.py#L962), `_create_app_drop` [:880-931](dlg/dropmake/lg_node.py#L880), `_create_data_drop` [:932-961](dlg/dropmake/lg_node.py#L932), `_create_listener_drops` [:849-879](dlg/dropmake/lg_node.py#L849) | none | default chunked [lg.py:683-691](dlg/dropmake/lg.py#L683) | [lg.py:233-251](dlg/dropmake/lg.py#L233) |

Shared by all handlers, MOVE to `constructs/base.py` or `model.py`:
`make_oid` [lg_node.py:720-731](dlg/dropmake/lg_node.py#L720), `getPortName`
[:755-778](dlg/dropmake/lg_node.py#L755), `_update_key_value_attributes`
[:732-754](dlg/dropmake/lg_node.py#L732), `dop_diff` [:669-707](dlg/dropmake/lg_node.py#L669),
`h_related` [:708-719](dlg/dropmake/lg_node.py#L708), `str_to_bool`
[:1012-1016](dlg/dropmake/lg_node.py#L1012).

Handler *identity* replaces the predicates `is_scatter`/`is_gather`/`is_loop`/`is_groupby`/
`is_mpi`/`is_service`/`is_subgraph`/`is_branch` [lg_node.py:450-488](dlg/dropmake/lg_node.py#L450)
— they are the registry lookup, so they DELETE rather than move. The *structural* predicates
`is_group`, `is_start`, `is_group_start`, `is_group_end`, `is_start_listener`, `is_data`,
`is_app`, `is_dag_root` [:151-158, 345-449](dlg/dropmake/lg_node.py#L345) stay on `model.py`
— they describe graph position, not construct kind.

### 3.3 `constructs/vocabulary.py`

MOVE `Categories` [definition_classes.py:28-114](dlg/dropmake/definition_classes.py#L28) and
`ConstructTypes` [:115-122](dlg/dropmake/definition_classes.py#L115), minus the MKN entries
(§6). The file's existing TODO — that explicit `Categories` treatment should give way to
`CategoryType` — is exactly what handler registration accomplishes; expect this file to
shrink to a registry keyed on `CategoryType` once Phase 3 lands.

### 3.4 The `unroll_to_tpl` decision matrix

`unroll_to_tpl` [lg.py:545-822](dlg/dropmake/lg.py#L545) is 278 lines of nested conditional
and the single highest-risk region in the rewrite. The nesting order *is* the specification;
nothing states it. Written out, top to bottom:

| # | Lines | Guard | Goes to |
|---|-------|-------|---------|
| 1 | 553-556 | — (pass-1 driver) | `instantiate.py` |
| 2 | 563-573 | per-link preamble: resolve `slgn`/`tlgn`/`sdrops`/`tdrops`/`chunk_size` | `wire.py` dispatcher |
| 3 | 577-601 | `src group`, `tgt leaf`, `src is_gather`, `tgt.gid != sid` | `gather.py` |
| 4 | 602-603 | `src group`, `tgt leaf`, either is subgraph | `subgraph.py` |
| 5 | 604-611 | `src group`, `tgt leaf`, else — requires `len(sdrops) == len(tdrops)` | `scatter.py` |
| 6 | 612-616 | `src group`, `tgt group` — GroupBy→Gather only | `groupby.py` → `gather.py` |
| 7 | 618-619 | both leaf, `src.is_start_node` → skip | `wire.py` |
| 8 | 620-645 | both leaf, same loop gid, `src.is_group_end`, `tgt.is_group_start` | `loop.py` |
| 9 | 646-655 | both leaf, both in loops, not `h_related` — stepwise lock on `loop_ctx` | `loop.py` |
| 10 | 657-670 | both leaf, `loop_aware`, `src.h_level > tgt.h_level` — last iteration only | `loop.py` |
| 11 | 671-682 | both leaf, `loop_aware`, `src.h_level < tgt.h_level` — first iteration only | `loop.py` |
| 12 | 683-687 | both leaf, `src.h_level >= tgt.h_level` — chunk src | `wire.py` default |
| 13 | 688-691 | both leaf, else — chunk tgt | `wire.py` default |
| 14 | 693-742 | `src leaf`, `tgt.is_groupby` — bucket by `iid`-derived key | `groupby.py` + `coordinate.py` |
| 15 | 743-746 | `src leaf`, `tgt.is_gather` | `gather.py` |
| 16 | 747-752 | `src leaf`, `tgt.is_service` | `service.py` — **broken, §7 B1** |
| 17 | 753-754 | `src leaf`, `tgt.is_subgraph` | `subgraph.py` |
| 18 | 755-759 | `src leaf`, unknown target group → raise | `wire.py` — **broken, §7 B2** |
| 19 | 761-782 | gather cache drain | **DELETE** — two-pass removes the need; **contains a bug, §7 B3** |
| 20 | 786-806 | scaffolding cleanup | per-handler `finalise()` |
| 21 | 812-816 | flatten `_drop_dict` → list | `stage.py` |

Rows 3, 8-11 and 14 carry essentially all the semantic weight. Land them one per PR, corpus
run between each (proposal §6 Phase 4).

---

## 4. `stages/partition/`, `map/`, `projections/`

### 4.1 `partition/dag.py`

| Verb | Source |
|------|--------|
| MOVE | `DAGUtil` in full [scheduler.py:976-1260](dlg/dropmake/scheduler.py#L976) — `get_longest_path`, `get_max_width`, `get_max_dop`, `get_max_antichains`, `prune_antichains`, `label_schedule`, `ganttchart_matrix`, `import_metis`, `build_dag_from_drops` |
| MOVE | `PGT.dag` [pgt.py:156-166](dlg/dropmake/pgt.py#L156) |
| MOVE | metrics `PGT.data_movement` [:167-177](dlg/dropmake/pgt.py#L167), `PGT.pred_exec_time` [:178-195](dlg/dropmake/pgt.py#L178) — consumed by `PGT.result()` and the REST gantt endpoints, so they need a home; `dag.py` is the natural one. *Layout addendum to proposal §3.* |

### 4.2 `partition/algorithms/`

| Target | Verb | Source |
|--------|------|--------|
| `base.py` | MOVE | `Scheduler` [scheduler.py:494-582](dlg/dropmake/scheduler.py#L494); `PGT.{to_partition_input, get_opt_num_parts, get_partition_info}` [pgt.py:118-138](dlg/dropmake/pgt.py#L118) |
| `utils/schedule.py` | MOVE | `Schedule` [scheduler.py:46-155](dlg/dropmake/scheduler.py#L46) |
| `utils/partition.py` | MOVE | `Partition` [scheduler.py:156-411](dlg/dropmake/scheduler.py#L156), `KFamilyPartition` [:412-493](dlg/dropmake/scheduler.py#L412) |
| `utils/antichains.py` | **DONE** | moved verbatim 2026-08-31 (P2-3) — the only live module; see §6 for its four unused graph-builders |
| `utils/anneal.py` | **DONE** | moved verbatim 2026-08-31 (P2-3), zero importers — retained, see §6 |
| `utils/heft/base.py` | **DONE** | moved verbatim 2026-08-31 (P2-3), zero importers — retained, see §6 |
| `utils/bash_parameter.py` | **DONE** | moved verbatim 2026-08-31 (P2-3), zero importers — retained, see §6 |
| `none.py` | MOVE | base `PGT` construction path, `pg_generator.partition` `ALGO_NONE` branch [:181-182](dlg/dropmake/pg_generator.py#L181) |
| `metis.py` | SPLIT | `MetisPGTP` [pgtp.py:41-391](dlg/dropmake/pgtp.py#L41): `__init__` [:48-87](dlg/dropmake/pgtp.py#L48), `to_partition_input` [:88-166](dlg/dropmake/pgtp.py#L88), `_parse_metis_output` [:180-234](dlg/dropmake/pgtp.py#L180) MOVE; `to_gojs_json` [:235-291](dlg/dropmake/pgtp.py#L235) SPLIT — the METIS invocation stays, the `super().to_gojs_json` call goes to `projections/`; `merge_partitions` [:292-391](dlg/dropmake/pgtp.py#L292) → `islands.py` |
| `mysarkar.py` | SPLIT | `MySarkarScheduler` [scheduler.py:583-757](dlg/dropmake/scheduler.py#L583) MOVE; `MySarkarPGTP` [pgtp.py:392-595](dlg/dropmake/pgtp.py#L392) — `merge_partitions` [:444-513](dlg/dropmake/pgtp.py#L444) → `islands.py`, `to_gojs_json` [:514-595](dlg/dropmake/pgtp.py#L514) SPLIT partitioning-vs-serialisation |
| `min_num_parts.py` | MOVE | `MinNumPartsScheduler` [scheduler.py:758-773](dlg/dropmake/scheduler.py#L758), `MinNumPartsPGTP` [pgtp.py:596-633](dlg/dropmake/pgtp.py#L596) |
| `pso.py` | MOVE | `PSOScheduler` [scheduler.py:774-975](dlg/dropmake/scheduler.py#L774), `PSOPGTP` [pgtp.py:634-665](dlg/dropmake/pgtp.py#L634) |
| `registry.py` | REWRITE | `_known_algos` + the `if/elif` construction block [pg_generator.py:97-230](dlg/dropmake/pg_generator.py#L97) — the bidirectional name↔int dict and the eight `_get_algo_param` defaults become one registry entry per algorithm carrying its own parameter schema |

### 4.3 `partition/islands.py`, `linearise.py`, `placeholders.py`

| Target | Verb | Source |
|--------|------|--------|
| `islands.py` | MOVE | `PGT.{partitions, _can_merge, merge_partitions}` [pgt.py:77-107, 214-218](dlg/dropmake/pgt.py#L77); the two concrete `merge_partitions` overrides listed in §4.2; the merge/island block inside `to_pg_spec` (*approx* [pgt.py:283-300](dlg/dropmake/pgt.py#L283)) |
| `linearise.py` | EXTRACT | the synthetic-DROP branch of `to_gojs_json` [pgt.py:374-462](dlg/dropmake/pgt.py#L374) — everything under `if self._extra_drops is None:`. **This is partitioning logic, not visualisation** (proposal §8 Q3). Its consumers are `MinNumPartsPGTP`/`PSOPGTP`, which set `_extra_drops = None` at [pgtp.py:619](dlg/dropmake/pgtp.py#L619) and [:652](dlg/dropmake/pgtp.py#L652). |
| `placeholders.py` | EXTRACT | the `tpl_fl` branch (*approx* [pgt.py:316-323](dlg/dropmake/pgt.py#L316)) and the `node`/`island` stamping loop (*approx* [:325-340](dlg/dropmake/pgt.py#L325)) |
| `stage.py` | REWRITE | `pg_generator.partition` [:131-241](dlg/dropmake/pg_generator.py#L131); `PGT.__init__` state [pgt.py:53-76](dlg/dropmake/pgt.py#L53); `result`/`_extra_result` [:139-155](dlg/dropmake/pgt.py#L139) |

### 4.4 `stages/map/stage.py`

| Verb | Source |
|------|--------|
| MOVE | `pg_generator.resource_map` [:244-267](dlg/dropmake/pg_generator.py#L244) — the whole function, near-verbatim |
| MERGE | the real-`node_list` half of `to_pg_spec`: validation (*approx* [pgt.py:249-283](dlg/dropmake/pgt.py#L249)), `co_host_dim` split, and the hostname write. Today there are two code paths writing hostnames into DROPs; this collapses them to one. |

### 4.5 `projections/gojs.py`

| Verb | Source |
|------|--------|
| MOVE | `PGT.to_gojs_json` [pgt.py:343-494](dlg/dropmake/pgt.py#L343) **minus** the synthesis branch that goes to `linearise.py`: keep node/link emission (*approx* [:346-373](dlg/dropmake/pgt.py#L346)), the non-synthesis `else` [:464-472](dlg/dropmake/pgt.py#L464), and extra-drop emission [:473-486](dlg/dropmake/pgt.py#L473) |
| MOVE | `PGT.json` [pgt.py:196-206](dlg/dropmake/pgt.py#L196) |
| MOVE | the GOJS-shaping halves of `MetisPGTP.to_gojs_json` [pgtp.py:235-291](dlg/dropmake/pgtp.py#L235) and `MySarkarPGTP.to_gojs_json` [pgtp.py:514-595](dlg/dropmake/pgtp.py#L514) — the group-node/`isGroup` construction |
| FACADE | `PGT.to_gojs_json` stays as a delegator — REST and `PGManager` both call it |

---

## 5. `artefacts.py`, `pipeline.py`, `errors.py`, `cli/`

| Target | Verb | Source |
|--------|------|--------|
| `artefacts.py` | REWRITE | the trailing-element convention, currently spelled out at 12 sites (proposal §1.1). The clearest existing statements of the rule: `unroll`'s `drop_list.append(lg.reprodata)` [pg_generator.py:95](dlg/dropmake/pg_generator.py#L95), the shape-sniff `if not graph[-1].get("oid")` [translator_rest.py:955](dlg/dropmake/web/translator_rest.py#L955), and `resource_map`'s `if type(pgt[0]) is str: pgt = pgt[1]` [pg_generator.py:262](dlg/dropmake/pg_generator.py#L262) — that last one is an undocumented second wire form worth preserving deliberately |
| `artefacts.py` | MOVE | `LG.reprodata` [lg.py:824-825](dlg/dropmake/lg.py#L824), `PGT.reprodata` [pgt.py:207-213](dlg/dropmake/pgt.py#L207), `PGT.drops`/`links` [:108-117](dlg/dropmake/pgt.py#L108) |
| `pipeline.py` | REWRITE | the `init_*_repro_data` call pattern, best read from `tool_commands.dlg_unroll_and_partition` [:421-439](dlg/translator/tool_commands.py#L421) — it is the only place all four hooks appear near each other |
| `errors.py` | MOVE | `GraphException`/`GInvalidLink`/`GInvalidNode` [dm_utils.py:46-57](dlg/dropmake/dm_utils.py#L46), `GPGTException`/`GPGTNoNeedMergeException` [pgt.py:40-47](dlg/dropmake/pgt.py#L40), `SchedulerException` [scheduler.py:42-45](dlg/dropmake/scheduler.py#L42), `GraphConfigException` family [graph_config.py:37-66](dlg/dropmake/graph_config.py#L37) |
| `cli/` | MOVE | option parsers and IO plumbing: `_open_i`/`_open_o` [:48-63](dlg/translator/tool_commands.py#L48), `_add_output_options`/`_setup_output` [:153-179](dlg/translator/tool_commands.py#L153), `_add_unroll_options` [:282-324](dlg/translator/tool_commands.py#L282), `_add_partition_options` [:340-378](dlg/translator/tool_commands.py#L340), `parse_partition_algo_params` [:89-103](dlg/translator/tool_commands.py#L89), `register_commands` [:603-638](dlg/translator/tool_commands.py#L603) |
| `cli/` | REWRITE | the command bodies `dlg_fill` [:180-230](dlg/translator/tool_commands.py#L180), `dlg_graph_config` [:231-281](dlg/translator/tool_commands.py#L231), `dlg_unroll` [:325-339](dlg/translator/tool_commands.py#L325), `dlg_partition` [:379-420](dlg/translator/tool_commands.py#L379), `dlg_unroll_and_partition` [:421-439](dlg/translator/tool_commands.py#L421), `dlg_map` [:440-522](dlg/translator/tool_commands.py#L440) — each becomes a `Pipeline` invocation |
| `cli/` | MOVE | `submit` [:119-152](dlg/translator/tool_commands.py#L119), `dlg_submit` [:523-602](dlg/translator/tool_commands.py#L523) — untouched; the only outward-reaching command |

### Written from scratch — no source exists

| Target | Why there is nothing to copy |
|--------|------------------------------|
| `constructs/base.py`, `constructs/registry.py` | the interface is new; today its shape is implicit in `if/elif` order |
| `algorithms/base.py`, `algorithms/registry.py` | ditto — the parameter schema per algorithm currently exists only as eight `_get_algo_param` defaults |
| `unroll/coordinate.py` | `InstanceId` has no current type; only string operations |
| `pipeline.py` `Stage` protocol | no current abstraction |
| the Phase 0 golden-file harness | does not exist. Nearest prior art: `test/dropmake/test_pg_gen.py` already asserts on `min_exec_time`/`total_data_movement` per graph [:118-143](test/dropmake/test_pg_gen.py#L118) — useful as a template, not as a substitute |

### Tier 2 — `web/`, for completeness

| Target | Verb | Source |
|--------|------|--------|
| `web/translator_utils.py` | MOVE | path/repo helpers [:33-80](dlg/dropmake/web/translator_utils.py#L33), mgr-URL helpers [:93-123](dlg/dropmake/web/translator_utils.py#L93), `filter_dict_to_algo_params`/`make_algo_param_dict` [:85-92, 124-147](dlg/dropmake/web/translator_utils.py#L85) |
| `web/translator_utils.py` | REWRITE | `unroll_and_partition_with_params` [:148-185](dlg/dropmake/web/translator_utils.py#L148) → `Pipeline`. **Signature frozen** — `daliuge-engine` calls it (proposal §8 Q5) |
| `web/translator_rest.py` | edit-in-place | imports; the three reprodata pop/append pairs; `load_graph` [:823-852](dlg/dropmake/web/translator_rest.py#L823) |

---

## 6. Deletions

Confirmed dead by whole-repo grep across `daliuge-translator` and `daliuge-engine`.

| Code | Lines | Evidence |
|------|-------|----------|
| `convert_mkn` | [dm_utils.py:170-323](dlg/dropmake/dm_utils.py#L170) | zero callers |
| `convert_mkn_all_share_m` | [dm_utils.py:324-409](dlg/dropmake/dm_utils.py#L324) | zero callers |
| `_check_MKN` | [dm_utils.py:152-165](dlg/dropmake/dm_utils.py#L152) | called only from the two above |
| `_make_unique_port_key` | [dm_utils.py:166-169](dlg/dropmake/dm_utils.py#L166) | all four call sites (`:202`, `:207`, `:294`, `:295`) are inside the two above |
| `_mkn_substitution` | [lg_node.py:1017-1025](dlg/dropmake/lg_node.py#L1017) | zero callers |
| `mkn` kwargs pass-through | [lg_node.py:926-927](dlg/dropmake/lg_node.py#L926) | nothing downstream reads the key |
| `Categories.MKN`, `ConstructTypes.MKN` | [definition_classes.py:49, 108, 120](dlg/dropmake/definition_classes.py#L49) | vocabulary for the above |
| `convert_eagle_to_daliuge_json` | [dm_utils.py:915-1019](dlg/dropmake/dm_utils.py#L915) | **zero callers** — 105 LOC |
| `getNodesKeyDict` | [dm_utils.py:112-119](dlg/dropmake/dm_utils.py#L112) | **zero callers** |
| gather cache | [lg.py:81-83](dlg/dropmake/lg.py#L81), writes at [:454-460](dlg/dropmake/lg.py#L454) and [:512-518](dlg/dropmake/lg.py#L512), drain at [:761-782](dlg/dropmake/lg.py#L761) | superseded by two-pass unroll |
| `is_scatter`/`is_gather`/`is_loop`/`is_groupby`/`is_mpi`/`is_service`/`is_subgraph` | [lg_node.py:450-488](dlg/dropmake/lg_node.py#L450) | replaced by handler identity |
| `MetisPGTP._metis_path` | `"gpmetis"` assignment in `__init__` | vestigial; `DAGUtil.import_metis` [scheduler.py:1133](dlg/dropmake/scheduler.py#L1133) uses the Python binding. **Verify before deleting** — proposal §5 row 7 |
| `antichains` graph builders | [utils/antichains.py:138-186](dlg/dropmake/utils/antichains.py#L138) | `create_small_seq_graph` etc. look like test fixtures living in `dlg/`. Verify, then move to `test/` or delete |

Rough total: **~600 LOC deleted outright**, over 7% of the translator, before any
restructuring.

### Not deleted — retained by client decision (2026-08-31)

Three modules under `partition/algorithms/utils/` have **zero importers repo-wide** and read
as dead weight, but are **kept deliberately**: the client wants them available in case those
algorithms are implemented later. Do not file a deletion issue for them, and do not "tidy"
them during a later phase.

| Module | LOC | Importers |
|--------|-----|-----------|
| `anneal.py` | 321 | 0 |
| `heft/base.py` | 232 | 0 |
| `bash_parameter.py` | 93 | 0 |
| *(`antichains.py`)* | *197* | *1 — `scheduler.py:34`, live* |

This supersedes the earlier reading of `utils/**` as "~600 LOC of dead weight" and the §1
row's "except `bash_parameter.py`". All four moved intact in P2-3.

---

## 7. Latent bugs found while mapping

Not fixed here. Flagged so nobody "cleans them up" mid-move and silently changes behaviour.
Each needs a decision recorded in the proposal's changes log.

**B1 — `is_service` wiring branch cannot execute. ✅ Resolved 2026-08-31: DELETE it.**
[lg.py:750-755](dlg/dropmake/lg.py#L750) does `tlgn["categoryType"] = "Application"` where
`tlgn` is an `LGNode`. `LGNode` defines neither `__setitem__` nor `__getitem__` (grep
confirms), so this raises `TypeError: 'LGNode' object does not support item assignment` the
moment it is reached.

This entry originally asked which of two cases held — targets never reach the branch, or
Service links are broken today. Phase 0 answered it with authored corpus cases: **both, and
neither is behaviour.**

- **Service *with* an input application — unreachable.** `convert_construct` gives the
  generated app node the construct's original `id` (`_create_from_node`
  [dm_utils.py:545-593](dlg/dropmake/dm_utils.py#L545), `new_node["id"] = node["id"]`), then
  reassigns the construct a fresh `uuid.uuid4()`. Every link authored "into the Service"
  therefore resolves to the app node, `tlgn.is_service` is False, and the branch is skipped.
  Corpus case `service_simple`.
- **Service *without* one — runs, crashes.** `convert_construct` gates on
  `_has_app_keywords` and `continue`s, so the id is unchanged and links still target the
  group. The branch fires and raises. Corpus case `service_no_input_app`, filed known-broken
  to pin it.

**Decision:** delete, alongside proposal §5 rows 6 and 10 — **do not** port it into
`ServiceHandler.instantiate`. Recorded as proposal [§5 row 9b](ARCHITECTURE_PROPOSAL.md), which
supersedes row 9's original "move the rewrite into the handler" plan (struck through there).
The delete executes in **P4-2**, not in P3-1; `service.py` needs no probe before it is written.
`service.py`'s real `instantiate` content is the *working* twin of this rewrite — the
`make_single_drop` service branch at
[lg_node.py:995-1001](dlg/dropmake/lg_node.py#L995), which assigns into `kwargs` and `self.jd`,
both of which are dicts.

**B1b — a Service DROP's `oid`/`lg_key` are not reproducible.** Found in the same Phase 0 run,
and unlike B1 it is *live*. `convert_construct` assigns each construct a fresh `uuid.uuid4()`
[dm_utils.py:410-544](dlg/dropmake/dm_utils.py#L410). Scatter and Gather do not care — they
emit no DROP. **Service does**, so the same logical graph translates to a different PGT on
every run. Reprodata is unaffected. This is what blocks `service_simple` from having a golden,
and it has no issue and no phase yet.

**B2 — the unknown-target error path is itself broken.**
[lg.py:757](dlg/dropmake/lg.py#L757) formats `tlgn.jd.category`, but `jd` is a `dict` — this
raises `AttributeError` instead of the intended `GraphException`. A user hitting an
unsupported construct gets the wrong error.

**B3 — the gather cache drain reads a leaked loop variable.**
[lg.py:769](dlg/dropmake/lg.py#L769) calls `slgn.getPortName(ports="outputPorts")` inside
`for _, v in self._gather_cache.items():`, but `slgn` is not bound in that scope — it holds
whatever the *previous* `for lk in self._lg_links` iteration left behind. So gather output
port names depend on link iteration order. The two-pass rewrite removes this code, which
means **the corpus may legitimately drift here** — treat drift in gather port names as
expected, not as a regression, and confirm the new value is the correct one.

**B4 — Loop DoP returns `None`.** [lg_node.py:644-651](dlg/dropmake/lg_node.py#L644): if none
of the three iteration-count keys is present, `_dop` is never assigned, so `dop` returns
`None` and `range(lgn.dop)` raises a bare `TypeError` with no node name. Already recorded as
proposal §5 row 5b.

**B6 — `import_metis` never selects the macOS binary.** The extension picker at
[scheduler.py:1136-1139](dlg/dropmake/scheduler.py#L1136) tests
`platform.platform().startswith("Darwin")`. `platform.platform()` rewrites the system name
`Darwin` → `macOS` whenever `mac_ver()[0]` is non-empty, which it is on any real macOS —
CPython's `platform.py` does this unconditionally:

```python
if system == 'Darwin':
    macos_release = mac_ver()[0]
    if macos_release:
        system = 'macOS'
```

So the branch is always False there, `ext` is `"so"`, and a Darwin developer is handed the
Linux `libmetis.so`. The correct predicate is `platform.system()`, which does return
`"Darwin"`. Pre-existing — P2-3 moved the binaries without touching the selector, so the
`.dylib` has been unreachable the whole time and CI (Linux-only) cannot see it. **Out of scope
for the rewrite and deliberately has no issue in the plan** — recorded as proposal §5 row 15.
Verified against the stdlib source on Python 3.12.13, 2026-08-31.

**B5 — a second, undocumented PGT wire form.**
[pg_generator.py:262](dlg/dropmake/pg_generator.py#L262): `if type(pgt[0]) is str: pgt = pgt[1]`
— `resource_map` accepts `[name, drops]` as well as a bare drop list, with a `TODO: we may
want to retain that`. `artefacts.py` must decide whether to keep this form.

**B6 — missing `categoryType` dies as a bare `KeyError`.**
[lg_node.py:60](dlg/dropmake/lg_node.py#L60) subscripts `self.jd["categoryType"]` directly, two
lines after the `jd` setter's inference ([lg_node.py:135-139](dlg/dropmake/lg_node.py#L135))
has had its only chance to supply it. The inference covers `APP_TYPES`/`DATA_TYPES` categories
only, so every construct category — and any EAGLE app category newer than `APP_TYPES` — raises
`KeyError: 'categoryType'` naming no node. Recorded as proposal §5 row 5d. **Note for whoever
writes `model.py`:** this subscript is why the Gather default at
[lg.py:201-202](dlg/dropmake/lg.py#L201-L202) is dead (proposal §8 Q11). If `model.py` softens
it to `.get()`, that default comes back to life — soften it to a `GInvalidNode` instead.

**B7 — `Categories.DATA` is in both type lists.**
[definition_classes.py:80](dlg/dropmake/definition_classes.py#L80) and
[:91](dlg/dropmake/definition_classes.py#L91) both contain `"Data"`, and the `jd` setter tests
`APP_TYPES` first, so a `category: "Data"` node omitting `categoryType` is classified
`Application`. Recorded as proposal §5 row 5e; fixing it is a possible corpus change, so it
does not ride along with a move.

---

## 8. Changes log

Same rules as the proposal's §9. Append-only, newest at the bottom.

| Date | Author | Change |
|------|--------|--------|
| 2026-08-09 | Claude (Opus 5) | Initial map. Line-level read of `dlg/dropmake/**` and `dlg/translator/**`; every target file in proposal §3 has a stated source or is listed as NEW. Found ~600 LOC of confirmed-dead code (§6) and five latent bugs (§7) |
| 2026-08-27 | Claude (Opus 5) | Two latent bugs added from proposal §8 Q11 — **B6** (missing `categoryType` raises a bare `KeyError` at [lg_node.py:60](dlg/dropmake/lg_node.py#L60), naming no node) and **B7** (`Categories.DATA` is in both `DATA_TYPES` and `APP_TYPES`, `APP_TYPES` tested first). B6 carries a constraint on `model.py`: the bare subscript is what makes the Gather `categoryType` default dead code, so relaxing it to `.get()` would revive a default the proposal deletes |
| 2026-09-01 | Claude (Opus 5) | **B1 closed.** The entry still asked for a determination that Phase 0 had already made on 2026-08-31; proposal §5 row 9b records the verdict (dead code, delete, do not port) and this map contradicted it. B1 rewritten with both cases and their corpus pins, §3.2's `service.py` row repointed from "broken today" to "dead, DELETE in P4-2". **B1b added** — the Service `oid`/`lg_key` `uuid.uuid4()` nondeterminism from the same run, which is live, blocks `service_simple`'s golden, and has no issue yet |
