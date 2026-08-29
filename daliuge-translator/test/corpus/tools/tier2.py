#!/usr/bin/env python3
"""Generate and verify the Tier 2 corpus — gojs output and HTTP response bodies.

ARCHITECTURE_PROPOSAL §6 asks for a second corpus beside the CLI goldens: `to_gojs_json`
output, and the HTTP response body of every `Updated` endpoint, for a handful of graphs.
Tier 2 is the part of the translator the restructure *edits* rather than merely moves, so
this is the net under `web/` and under the two `to_gojs_json` implementations.

    python3 tools/tier2.py generate    # (re)produce tier2/ from scratch
    python3 tools/tier2.py verify      # re-run and compare, exit 1 on drift
    python3 tools/tier2.py show <case> <name>

`generate` and `verify` start their own translator server on a free port, with temporary
graph directories, and shut it down afterwards. Nothing needs to be running first.

Determinism notes, both of which cost a debugging session to find:

* Every route that unrolls must be given an `oid_prefix`. Without one, `LG.__init__`
  (lg.py:73-75) falls back to `datetime.now()` for the session id, and every OID in the
  response carries a wall-clock timestamp.
* `/gen_pg_spec` cannot be pinned that way — it reads a PGT registered by `/gen_pgt`, and
  `gen_pgt` takes no oid_prefix at all, so its session id is *always* a timestamp. That one
  response is normalised (see `_normalise`) before it is hashed.
"""

import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

try:                                    # `python3 -m tools.tier2`, and type checkers
    from .cases import Case, dlg_executable, load_cases
    from .golden import (
        Artefact, _digest, _store, _take_legacy_repo, read_golden)
    from .provenance import ProvenanceError, assert_baseline, describe
except ImportError:                     # `python3 tools/tier2.py`
    from cases import (  # type: ignore[import-not-found,no-redef]
        Case, dlg_executable, load_cases)
    from golden import (  # type: ignore[import-not-found,no-redef,attr-defined]
        Artefact, _digest, _store, _take_legacy_repo, read_golden)
    from provenance import (  # type: ignore[import-not-found,no-redef]
        ProvenanceError, assert_baseline, describe)

CORPUS = Path(__file__).resolve().parent.parent
TIER2 = CORPUS / "tier2"
INDEX = TIER2 / "INDEX.toml"

# "A handful of graphs" (§6). Chosen to span the construct vocabulary rather than to be
# large: a trivial baseline, a loop, scatter+gather, a group-by, a realistic mid-size
# graph, and one carrying an embedded graph configuration.
#
# Deliberately *not* `ArrayLoopScatter-LoopConfig`: no `Updated` route applies an external
# .graphConfig, so driving that case over HTTP would exercise the embedded path while
# carrying a name that claims otherwise. The external path stays a CLI-golden concern.
SUBSET = [
    "HelloWorld_simple",
    "testLoop",
    "SuperBasicScatterGather",
    "test_grpby_gather",
    "chiles_simple",
    "ArrayLoopScatter",
]

OID_PREFIX = "1"          # matches the CLI goldens, and pins the session id
NUM_PARTITIONS = 2
NUM_ISLANDS = 1
ALGORITHM = "metis"

# `YYYY-MM-DDThh:mm:ss` session ids, as LG.__init__ formats them.
SESSION_TIMESTAMP = re.compile(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _normalise(payload: bytes) -> bytes:
    """Canonicalise a `/gen_pg_spec` body — the one response that cannot be pinned.

    Two sources of noise, neither of which carries information:

    * the wall-clock session id, because `gen_pgt` accepts no `oid_prefix` and
      `LG.__init__` falls back to `datetime.now()`;
    * the order of `root_uids`, which `gen_pg_spec` builds with `list(get_roots(...))`
      over a **set**. Python randomises string hashing per process, so a freshly started
      server reorders it. The `pg_spec` payload beside it is byte-stable; only this list
      moves, and sorting it removes noise rather than masking a change.

    Applied only here. Every other Tier 2 artefact is pinned with `oid_prefix`, and
    normalising those would risk hiding something real.
    """
    payload = SESSION_TIMESTAMP.sub(b"<SESSION>", payload)
    try:
        decoded = json.loads(payload)
        if isinstance(decoded, str):        # JSONResponse(json.dumps(...)) — encoded twice
            decoded = json.loads(decoded)
        decoded["root_uids"] = sorted(decoded["root_uids"])
    except (ValueError, KeyError, TypeError):
        return payload                      # not the shape we expected; leave it alone
    return json.dumps(decoded, sort_keys=True).encode()


# --------------------------------------------------------------------- the server

class Translator:
    """The translator REST app, running on a free port with throwaway directories."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.port = self._free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        root = Path(self._tmp.name)
        (root / "lg").mkdir()
        (root / "pgt").mkdir()
        self._proc = subprocess.Popen(
            [dlg_executable(), "tm", "-H", "127.0.0.1", "-p", str(self.port),
             "-d", str(root / "lg"), "-t", str(root / "pgt")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    def wait_until_ready(self, timeout: float = 60.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError("translator exited before becoming ready")
            try:
                urllib.request.urlopen(self.base + "/", timeout=2).read()
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError(f"translator not ready after {timeout}s")

    def post(self, path: str, fields: dict[str, Any],
             as_json: bool = False) -> tuple[int, bytes]:
        if as_json:
            body, content_type = json.dumps(fields).encode(), "application/json"
        else:
            body = urllib.parse.urlencode(fields).encode()
            content_type = "application/x-www-form-urlencoded"
        request = urllib.request.Request(self.base + path, data=body,
                                         headers={"Content-Type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as failure:
            return failure.code, failure.read()

    def close(self) -> None:
        self._proc.terminate()
        try:
            self._proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._tmp.cleanup()

    def __enter__(self) -> "Translator":
        self.wait_until_ready()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# --------------------------------------------------------------------- gojs

def gojs_artefacts(case: Case) -> Iterator[Artefact]:
    """`to_gojs_json` from both implementations, in-process.

    `PGT.to_gojs_json` (pgt.py:343) and `MetisPGTP.to_gojs_json` (pgtp.py:514) are
    different code, and the restructure touches both, so both are captured.
    """
    from dlg.dropmake.pg_generator import partition, unroll
    from dlg.dropmake.pgt import PGT

    # Start from the case's own `lg` golden, so Tier 2 and the CLI goldens are provably
    # looking at the same filled logical graph.
    #
    # Re-parsed for every unroll, not shared: `unroll` MUTATES the logical graph dict it
    # is given (§5 row 9 — three passes rewrite the logical model), and a second unroll of
    # the same object dies with `KeyError: 'fromPort'`. Reusing one parse here cost a
    # confusing failure on SuperBasicScatterGather, a graph that is otherwise fine.
    raw = read_golden(case.id, "lg")

    plain = PGT(unroll(json.loads(raw), OID_PREFIX)[:-1])
    plain.to_gojs_json(string_rep=False)
    yield Artefact("gojs.pgt", _dump(plain.gojs_json_obj), plain._drop_list_len)

    # partition() takes the bare DROP list and builds the PGTP subclass itself.
    partitioned = partition(unroll(json.loads(raw), OID_PREFIX)[:-1], ALGORITHM,
                            num_partitions=NUM_PARTITIONS, num_islands=NUM_ISLANDS,
                            show_gojs=True)
    yield Artefact(f"gojs.{ALGORITHM}", _dump(partitioned.gojs_json_obj),
                   partitioned._drop_list_len)


def _dump(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True).encode()


# --------------------------------------------------------------------- REST

def rest_artefacts(case: Case, server: Translator) -> Iterator[Artefact | str]:
    """The five `Updated` endpoints, plus `gen_pg_spec` from the `Original` set.

    `gen_pg_spec` is not an Updated route, but §5 (line 121) makes it explicit that two
    cleanup sites stay untouched unless the Phase 0 HTTP corpus covers it — so it is
    covered deliberately rather than by accident.
    """
    lg = case.graph.read_text()

    status, filled = server.post("/lg_fill", {
        "lg_content": lg, "parameters": _fill_parameters(case), "rmode": "NOTHING"})
    if status != 200:
        yield f"{case.id}/lg_fill: HTTP {status}"
        return
    yield Artefact("rest.lg_fill", filled, 0)

    status, pgt = server.post("/unroll", {"lg_content": lg, "oid_prefix": OID_PREFIX})
    if status != 200:
        yield f"{case.id}/unroll: HTTP {status}"
        return
    yield Artefact("rest.unroll", pgt, len(json.loads(pgt)) - 1)

    status, pgtp = server.post("/partition", {
        "pgt_content": pgt.decode(), "num_partitions": NUM_PARTITIONS,
        "num_islands": NUM_ISLANDS, "algorithm": ALGORITHM})
    if status != 200:
        yield f"{case.id}/partition: HTTP {status}"
        return
    yield Artefact("rest.partition", pgtp, len(json.loads(pgtp)) - 1)

    status, combined = server.post("/unroll_and_partition", {
        "lg_content": lg, "oid_prefix": OID_PREFIX, "num_partitions": NUM_PARTITIONS,
        "num_islands": NUM_ISLANDS, "algorithm": ALGORITHM})
    if status == 200:
        yield Artefact("rest.unroll_and_partition", combined,
                       len(json.loads(combined)) - 1)
    else:
        yield f"{case.id}/unroll_and_partition: HTTP {status}"

    # NOTE: this response is *wrong*, and deliberately captured wrong. The route declares
    # `nodes: str` and hands it to resource_map unsplit, so resource_map slices the string
    # and every DROP ends up on a single-character "host". The CLI splits on "," first
    # (tool_commands.dlg_map); this route never does. Baseline is baseline.
    status, pg = server.post("/map", {
        "pgt_content": pgtp.decode(), "nodes": "dim0,nm0,nm1",
        "num_islands": NUM_ISLANDS, "co_host_dim": "true"})
    if status == 200:
        yield Artefact("rest.map", pg, len(json.loads(pg)) - 1)
    else:
        yield f"{case.id}/map: HTTP {status}"

    yield from _gen_pg_spec(case, lg, server)


def _gen_pg_spec(case: Case, lg: str, server: Translator) -> Iterator[Artefact | str]:
    status, html = server.post("/gen_pgt", {
        "lg_name": f"{case.id}.graph", "json_data": lg, "rmode": "0",
        "algo": ALGORITHM, "num_par": NUM_PARTITIONS, "num_islands": NUM_ISLANDS})
    if status != 200:
        yield f"{case.id}/gen_pgt: HTTP {status}"
        return
    found = re.search(r'name="pgt_id" value="([^"]+)"', html.decode("utf-8-sig"))
    if not found:
        yield f"{case.id}/gen_pgt: no pgt_id in the response"
        return

    status, spec = server.post("/gen_pg_spec", {
        "pgt_id": found.group(1), "node_list": [f"nm{i}" for i in range(NUM_PARTITIONS)],
        "manager_host": "localhost", "tpl_nodes_len": NUM_PARTITIONS}, as_json=True)
    if status != 200:
        yield f"{case.id}/gen_pg_spec: HTTP {status}"
        return
    yield Artefact("rest.gen_pg_spec", _normalise(spec), 0)


def _fill_parameters(case: Case) -> str:
    """`fill_params` from CASES.toml, as the JSON object /lg_fill wants."""
    pairs = (param.split("=", 1) for param in case.fill_params)
    return json.dumps(dict(pairs))


# --------------------------------------------------------------------- commands

def _subset() -> list[Case]:
    by_id = {c.id: c for c in load_cases() if c.ok}
    missing = [i for i in SUBSET if i not in by_id]
    if missing:
        raise SystemExit(f"SUBSET names unusable cases: {missing}")
    return [by_id[i] for i in SUBSET]


def _produce(case: Case, server: Translator) -> Iterator[Artefact | str]:
    yield from gojs_artefacts(case)
    yield from rest_artefacts(case, server)


def _write_index(rows: list[dict[str, Any]], skipped: list[str]) -> None:
    lines = ["# Tier 2 corpus — GENERATED, do not hand-edit.",
             "# Regenerate with: python3 tools/tier2.py generate",
             "# Verify with:     python3 tools/tier2.py verify",
             ""]
    lines += [f"# skipped: {note}" for note in skipped]
    lines.append("")
    for row in rows:
        lines += ["[[artefact]]",
                  f'case = "{row["case"]}"',
                  f'name = "{row["name"]}"',
                  f'sha256 = "{row["sha256"]}"',
                  ""]
    INDEX.write_text("\n".join(lines))


def _path(case_id: str, name: str) -> Path:
    return TIER2 / case_id / f"{name}.json.gz"


def generate(legacy_repo: Path | None = None) -> int:
    # Tier 2 stores goldens like Tier 1 does, so it carries the same requirement:
    # the server about to answer these requests must be the pinned baseline.
    try:
        repository = assert_baseline(legacy_repo=legacy_repo)
    except ProvenanceError as error:
        print(error, file=sys.stderr)
        return 1
    print(describe(dlg_executable(), repository) + "\n")

    import shutil
    if TIER2.exists():
        shutil.rmtree(TIER2)
    TIER2.mkdir()

    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    with Translator() as server:
        for case in _subset():
            (TIER2 / case.id).mkdir()
            produced = 0
            for item in _produce(case, server):
                if isinstance(item, str):
                    skipped.append(item)
                    print(f"  --    {item}")
                    continue
                _path(case.id, item.name).write_bytes(_store(item.payload))
                rows.append({"case": case.id, "name": item.name,
                             "sha256": _digest(item.payload)})
                produced += 1
            print(f"  ok    {case.id}  ({produced} artefacts)")

    _write_index(rows, skipped)
    print(f"\n{len(rows)} artefacts, {len(skipped)} skipped")
    return 0


def verify() -> int:
    import tomllib
    recorded = {(r["case"], r["name"]): r["sha256"]
                for r in tomllib.loads(INDEX.read_text()).get("artefact", [])}
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()

    with Translator() as server:
        for case in _subset():
            for item in _produce(case, server):
                if isinstance(item, str):
                    continue
                key = (case.id, item.name)
                seen.add(key)
                if key not in recorded:
                    problems.append(f"{case.id}/{item.name}: new, not in INDEX.toml")
                    print(f"  NEW   {case.id}/{item.name}")
                elif recorded[key] != _digest(item.payload):
                    problems.append(f"{case.id}/{item.name}: content differs")
                    print(f"  DRIFT {case.id}/{item.name}")
                else:
                    print(f"  ok    {case.id}/{item.name}")

    for key in sorted(set(recorded) - seen):
        problems.append(f"{key[0]}/{key[1]}: recorded but not reproduced")
        print(f"  GONE  {key[0]}/{key[1]}")

    print()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} artefact(s) drifted", file=sys.stderr)
        return 1
    print("every Tier 2 artefact matches")
    return 0


def show(case_id: str, name: str) -> int:
    import gzip
    print(gzip.decompress(_path(case_id, name).read_bytes()).decode())
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if command == "generate":
        argv, repo = _take_legacy_repo(sys.argv[2:])
        if argv:
            raise SystemExit(f"unexpected arguments: {argv}")
        raise SystemExit(generate(legacy_repo=repo))
    if command == "verify":
        raise SystemExit(verify())
    if command == "show" and len(sys.argv) == 4:
        raise SystemExit(show(sys.argv[2], sys.argv[3]))
    print(__doc__, file=sys.stderr)
    raise SystemExit(2)
