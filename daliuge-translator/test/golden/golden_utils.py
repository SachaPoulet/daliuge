"""Helpers for deterministic, stage-by-stage DALiuGE golden tests."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


STAGE_FILENAMES = {
    "LG": "lg.json",
    "PGT": "pgt.json",
    "PGT-P": "pgtp.json",
    "PG": "pg.json",
}


class PipelineError(RuntimeError):
    """Raised when a translator CLI stage cannot produce its output."""


@dataclass(frozen=True)
class JsonDifference:
    """The first structural difference between two JSON-compatible values."""

    path: str
    expected: Any
    actual: Any
    reason: str


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 digest for an in-memory payload."""
    return hashlib.sha256(payload).hexdigest()


def deterministic_gzip(payload: bytes) -> bytes:
    """Compress *payload* without embedding a timestamp or source filename."""
    compressed = io.BytesIO()
    with gzip.GzipFile(
        filename="",
        mode="wb",
        compresslevel=9,
        fileobj=compressed,
        mtime=0,
    ) as stream:
        stream.write(payload)
    return compressed.getvalue()


def read_fixture_bytes(path: Path) -> bytes:
    """Read a plain JSON fixture or transparently decompress a .json.gz file."""
    payload = path.read_bytes()
    if path.suffix == ".gz":
        try:
            return gzip.decompress(payload)
        except (gzip.BadGzipFile, EOFError) as error:
            raise PipelineError(f"Invalid gzip fixture at {path}") from error
    return payload


def find_dlg_executable() -> str:
    """Locate the ``dlg`` console script belonging to the active environment."""
    configured = os.environ.get("DLG_CLI")
    if configured:
        return configured

    sibling = Path(sys.executable).with_name("dlg")
    if sibling.is_file():
        return str(sibling)

    executable = shutil.which("dlg")
    if executable:
        return executable

    raise PipelineError(
        "Cannot locate the dlg CLI. Activate the DALiuGE virtual environment "
        "or set DLG_CLI to the console-script path."
    )


def isolated_cli_environment() -> Dict[str, str]:
    """Prevent the runner's import path from contaminating another dlg install."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    return environment


def _run_stage(
    stage: str, command: Iterable[str], output_path: Path
) -> subprocess.CompletedProcess[str]:
    command = list(command)
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=isolated_cli_environment(),
    )
    if result.returncode != 0:
        rendered = " ".join(command)
        raise PipelineError(
            f"{stage} failed with exit code {result.returncode}\n"
            f"Command: {rendered}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    if not output_path.is_file():
        raise PipelineError(f"{stage} did not create {output_path}")

    try:
        with output_path.open(encoding="utf-8") as stream:
            json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise PipelineError(f"{stage} produced invalid JSON at {output_path}") from error
    return result


def _drop_records(path: Path) -> list[Mapping[str, Any]]:
    """Load translator DROPs, excluding the trailing reproducibility record."""
    document = load_json(path)
    if not isinstance(document, list):
        raise PipelineError(f"Expected a DROP list at {path}")
    if document and isinstance(document[-1], dict) and not document[-1].get("oid"):
        document = document[:-1]
    if not all(isinstance(drop, dict) for drop in document):
        raise PipelineError(f"Expected every DROP in {path} to be an object")
    return document


def _resource_extent(drops: list[Mapping[str, Any]], key: str) -> int:
    """Return the highest numbered resource label plus one."""
    labels = []
    for drop in drops:
        label = drop.get(key)
        if not isinstance(label, str) or not label.startswith("#"):
            raise PipelineError(
                "PGT-P/partition returned exit code 0 without assigning "
                f"a valid {key} label to DROP {drop.get('oid', '<unknown>')}. "
                "The legacy CLI may have swallowed GPGTNoNeedMergeException."
            )
        try:
            labels.append(int(label[1:]))
        except ValueError as error:
            raise PipelineError(
                f"PGT-P/partition produced an invalid {key} label: {label!r}"
            ) from error
    if not labels:
        raise PipelineError("PGT-P/partition produced no DROPs to map")
    return max(labels) + 1


def _automatic_map_configuration(
    pgtp_path: Path, map_config: Mapping[str, Any]
) -> tuple[list[str], int]:
    """Build a host list large enough for the actual partition label extents."""
    drops = _drop_records(pgtp_path)
    islands = _resource_extent(drops, "island")
    nodes = _resource_extent(drops, "node")
    island_prefix = map_config.get("island_prefix", "island")
    node_prefix = map_config.get("node_prefix", "node")
    hosts = [f"{island_prefix}{index}" for index in range(islands)]
    hosts.extend(f"{node_prefix}{index}" for index in range(nodes))
    return hosts, islands


def run_pipeline(
    dlg_executable: str,
    input_graph: Path,
    output_dir: Path,
    pipeline: Mapping[str, Any],
) -> Dict[str, Path]:
    """Run fill, unroll, partition and map with manifest-defined options."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        stage: output_dir / filename for stage, filename in STAGE_FILENAMES.items()
    }

    fill_config = pipeline["fill"]
    fill_command = [
        dlg_executable,
        "fill",
        "-L",
        str(input_graph),
        "-R",
        str(pipeline["reproducibility"]),
    ]
    for parameter in fill_config["parameters"]:
        fill_command.extend(["-p", parameter])
    fill_command.extend(["-o", str(outputs["LG"]), "-f"])
    _run_stage("LG/fill", fill_command, outputs["LG"])

    unroll_config = pipeline["unroll"]
    unroll_command = [
        dlg_executable,
        "unroll",
        "-L",
        str(outputs["LG"]),
        "-p",
        pipeline["oid_prefix"],
        "-o",
        str(outputs["PGT"]),
        "-f",
    ]
    if unroll_config["zerorun"]:
        unroll_command.append("-z")
    if unroll_config["app"]:
        unroll_command.extend(["--app", str(unroll_config["app"])])
    _run_stage("PGT/unroll", unroll_command, outputs["PGT"])

    partition_config = pipeline["partition"]
    partition_command = [
        dlg_executable,
        "partition",
        "-P",
        str(outputs["PGT"]),
        "-a",
        partition_config["algorithm"],
        "-N",
        str(partition_config["partitions"]),
        "-i",
        str(partition_config["islands"]),
        "-o",
        str(outputs["PGT-P"]),
        "-f",
    ]
    _run_stage("PGT-P/partition", partition_command, outputs["PGT-P"])

    map_config = pipeline["map"]
    if map_config["nodes"] == "auto":
        map_nodes, map_islands = _automatic_map_configuration(
            outputs["PGT-P"], map_config
        )
    else:
        map_nodes = map_config["nodes"]
        map_islands = map_config["islands"]
    map_command = [
        dlg_executable,
        "map",
        "-P",
        str(outputs["PGT-P"]),
        "-N",
        ",".join(map_nodes),
        "-i",
        str(map_islands),
        "-o",
        str(outputs["PG"]),
        "-f",
    ]
    _run_stage("PG/map", map_command, outputs["PG"])
    return outputs


def _child_path(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key, ensure_ascii=False)}]"


def first_json_difference(
    expected: Any, actual: Any, path: str = "$"
) -> JsonDifference | None:
    """Return the first exact structural difference, ignoring object key order."""
    if type(expected) is not type(actual):
        return JsonDifference(
            path,
            expected,
            actual,
            f"type differs ({type(expected).__name__} != {type(actual).__name__})",
        )

    if isinstance(expected, dict):
        missing = sorted(set(expected) - set(actual))
        if missing:
            key = missing[0]
            return JsonDifference(
                _child_path(path, key), expected[key], "<missing>", "key is missing"
            )

        unexpected = sorted(set(actual) - set(expected))
        if unexpected:
            key = unexpected[0]
            return JsonDifference(
                _child_path(path, key), "<missing>", actual[key], "unexpected key"
            )

        for key in sorted(expected):
            difference = first_json_difference(
                expected[key], actual[key], _child_path(path, key)
            )
            if difference:
                return difference
        return None

    if isinstance(expected, list):
        if len(expected) != len(actual):
            return JsonDifference(
                path,
                len(expected),
                len(actual),
                "array length differs",
            )
        for index, expected_item in enumerate(expected):
            difference = first_json_difference(
                expected_item, actual[index], f"{path}[{index}]"
            )
            if difference:
                return difference
        return None

    if expected != actual:
        return JsonDifference(path, expected, actual, "value differs")
    return None


def load_json(path: Path) -> Any:
    """Load a plain or gzip-compressed UTF-8 JSON document."""
    try:
        return json.loads(read_fixture_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PipelineError(f"Invalid JSON fixture at {path}") from error


def format_json_value(value: Any, limit: int = 500) -> str:
    """Render a bounded value for an actionable pytest failure message."""
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(rendered) > limit:
        return rendered[:limit] + "..."
    return rendered
