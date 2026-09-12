"""Regression tests for manifest cases and the frozen translator corpus."""

import hashlib
import json
from pathlib import Path

import pytest

from .generate_single_graph_golden import (
    _assert_review_outputs_are_safe,
    _planned_output_dirs,
    _select_cases,
)
from .golden_utils import (
    PipelineError,
    STAGE_FILENAMES,
    find_dlg_executable,
    first_json_difference,
    format_json_value,
    load_json,
    run_pipeline,
    sha256_file,
)


GOLDEN_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = GOLDEN_DIR / "manifest.json"
REPOSITORY_ROOT = GOLDEN_DIR.parents[2]
KNOWN_BAD_PIPELINE = {
    "reproducibility": 0,
    "oid_prefix": "issue6-known-bad",
    "fill": {"parameters": []},
    "unroll": {"zerorun": True, "app": 1},
    "partition": {"algorithm": "metis", "partitions": 2, "islands": 1},
    "map": {"nodes": ["island0", "node0", "node1"], "islands": 1},
}


def _load_manifest():
    with MANIFEST_PATH.open(encoding="utf-8") as stream:
        return json.load(stream)


def _assert_digest(path: Path, expected_digest: str, description: str) -> None:
    actual_digest = sha256_file(path)
    assert actual_digest == expected_digest, (
        f"{description} SHA-256 mismatch\n"
        f"Path: {path}\n"
        f"Expected: {expected_digest}\n"
        f"Actual:   {actual_digest}"
    )


def _resolve_inside(base: Path, relative_path: str, description: str) -> Path:
    base = base.resolve()
    resolved = (base / relative_path).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        pytest.fail(
            f"{description} escapes its allowed directory: {relative_path}",
            pytrace=False,
        )
    return resolved


def _corpus_graph_paths(corpus_root: Path, pattern: str):
    return sorted(
        path.relative_to(corpus_root).as_posix()
        for path in corpus_root.glob(pattern)
        if path.is_file()
    )


def _corpus_inventory_digest(corpus_root: Path, paths) -> str:
    payload = "".join(
        f"{path}\0{sha256_file(corpus_root / path)}\n" for path in paths
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _path_list_digest(paths) -> str:
    payload = "".join(f"{path}\n" for path in sorted(paths)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_frozen_corpus_scope_matches_checkout():
    """Guard the Issue #4 corpus membership used by Issue #6."""
    scope = _load_manifest()["corpus_scope"]
    corpus_root = _resolve_inside(
        REPOSITORY_ROOT, scope["root"], "Frozen corpus root"
    )

    assert corpus_root.is_dir(), (
        f"Frozen corpus directory is missing: {corpus_root}"
    )
    graph_paths = _corpus_graph_paths(corpus_root, scope["glob"])
    known_bad = scope["known_bad"]
    known_bad_paths = [entry["path"] for entry in known_bad]

    assert len(graph_paths) == scope["expected_graphs"]
    assert len(known_bad_paths) == len(set(known_bad_paths))
    assert set(known_bad_paths) <= set(graph_paths)
    assert len(graph_paths) - len(known_bad_paths) == scope["expected_runnable"]
    assert _path_list_digest(known_bad_paths) == scope["known_bad_sha256"]
    assert (
        _corpus_inventory_digest(corpus_root, graph_paths)
        == scope["inventory_sha256"]
    ), "Frozen corpus inventory changed"


def test_manifest_cases_are_complete_and_isolated():
    """Validate the multi-case contract before running the translator."""
    manifest = _load_manifest()
    cases = manifest["cases"]

    assert manifest["schema_version"] == 2
    assert cases, "At least one golden case is required"

    names = [case["name"] for case in cases]
    expected_dirs = [case["expected_dir"] for case in cases]
    assert len(names) == len(set(names)), "Golden case names must be unique"
    assert len(expected_dirs) == len(
        set(expected_dirs)
    ), "Golden expected directories must be unique"

    for case in cases:
        assert case["coverage"] in {"issue5-seed", "frozen-corpus"}
        input_path = _resolve_inside(
            REPOSITORY_ROOT, case["input"], f"{case['name']} input"
        )
        assert input_path.is_file(), f"Golden input is missing: {input_path}"
        _assert_digest(
            input_path,
            case["source"]["sha256"],
            f"{case['name']} pinned logical graph",
        )

        expected_dir = _resolve_inside(
            GOLDEN_DIR, case["expected_dir"], f"{case['name']} expected directory"
        )
        assert expected_dir.is_dir(), (
            f"Golden directory is missing: {expected_dir}"
        )
        assert set(case["expected"]) == set(STAGE_FILENAMES)
        assert {
            "reproducibility",
            "oid_prefix",
            "fill",
            "unroll",
            "partition",
            "map",
        } <= set(case["pipeline"])

        for stage, fixture in case["expected"].items():
            fixture_path = _resolve_inside(
                expected_dir,
                fixture["file"],
                f"{case['name']} {stage} fixture",
            )
            assert fixture_path.is_file(), (
                f"Golden fixture is missing: {fixture_path}"
            )
            _assert_digest(
                fixture_path,
                fixture["sha256"],
                f"{case['name']} legacy {stage} fixture",
            )


def test_generator_selects_cases_and_isolates_multiple_outputs(tmp_path):
    """Generate all cases by default and isolate multi-case review outputs."""
    manifest = _load_manifest()
    cases = manifest["cases"]

    assert _select_cases(manifest, None) == cases
    assert _select_cases(manifest, [cases[0]["name"]]) == [cases[0]]

    multiple_cases = [{"name": "first"}, {"name": "nested/second"}]
    outputs = _planned_output_dirs(tmp_path.resolve(), multiple_cases)
    assert outputs == [
        (tmp_path / "first").resolve(),
        (tmp_path / "nested/second").resolve(),
    ]
    with pytest.raises(SystemExit, match="escapes review directory"):
        _planned_output_dirs(
            tmp_path.resolve(),
            [{"name": "../escape"}, {"name": "safe"}],
        )


def test_generator_rejects_unknown_or_duplicate_case():
    """Reject ambiguous selections before generating any fixtures."""
    manifest = _load_manifest()
    case_name = manifest["cases"][0]["name"]

    with pytest.raises(SystemExit, match="Unknown manifest case"):
        _select_cases(manifest, ["missing-case"])
    with pytest.raises(SystemExit, match="only be selected once"):
        _select_cases(manifest, [case_name, case_name])


def test_generator_rejects_committed_fixture_directory():
    """Never generate candidates into committed expected fixtures."""
    manifest = _load_manifest()
    committed = (
        GOLDEN_DIR / manifest["cases"][0]["expected_dir"]
    ).resolve()

    with pytest.raises(SystemExit, match="Refusing to write"):
        _assert_review_outputs_are_safe([committed], manifest)


@pytest.mark.parametrize(
    "known_bad",
    _load_manifest()["corpus_scope"]["known_bad"],
    ids=lambda entry: entry["path"],
)
def test_known_bad_graph_fails_as_documented(known_bad, tmp_path):
    """Keep known-bad graphs out of golden cases until their defect is fixed."""
    scope = _load_manifest()["corpus_scope"]
    corpus_root = _resolve_inside(
        REPOSITORY_ROOT, scope["root"], "Frozen corpus root"
    )
    input_path = _resolve_inside(
        corpus_root, known_bad["path"], "Known-bad graph"
    )

    with pytest.raises(PipelineError) as raised:
        run_pipeline(
            find_dlg_executable(),
            input_path,
            tmp_path,
            KNOWN_BAD_PIPELINE,
        )

    message = str(raised.value)
    assert message.startswith(f"{known_bad['stage']} failed")
    assert known_bad["error_contains"] in message


@pytest.mark.parametrize(
    "case",
    _load_manifest()["cases"],
    ids=lambda case: case["name"],
)
def test_graph_matches_legacy_outputs(case, tmp_path):
    """Compare each configured pipeline case with its legacy JSON outputs."""
    input_path = REPOSITORY_ROOT / case["input"]
    expected_dir = GOLDEN_DIR / case["expected_dir"]

    _assert_digest(
        input_path,
        case["source"]["sha256"],
        f"{case['name']} pinned logical graph",
    )
    for stage, fixture in case["expected"].items():
        _assert_digest(
            expected_dir / fixture["file"],
            fixture["sha256"],
            f"Legacy {stage} fixture",
        )

    try:
        actual_outputs = run_pipeline(
            find_dlg_executable(), input_path, tmp_path, case["pipeline"]
        )
    except PipelineError as error:
        pytest.fail(str(error), pytrace=False)

    for stage in ("LG", "PGT", "PGT-P", "PG"):
        fixture = case["expected"][stage]
        expected_path = expected_dir / fixture["file"]
        actual_path = actual_outputs[stage]
        difference = first_json_difference(
            load_json(expected_path), load_json(actual_path)
        )
        if difference:
            pytest.fail(
                f"Stage: {stage}\n"
                f"Path: {difference.path}\n"
                f"Reason: {difference.reason}\n"
                f"Expected: {format_json_value(difference.expected)}\n"
                f"Actual:   {format_json_value(difference.actual)}",
                pytrace=False,
            )


def test_comparator_ignores_object_key_order():
    """JSON formatting and object key order are not wire-format differences."""
    expected = {"outer": {"first": 1, "second": 2}}
    actual = {"outer": {"second": 2, "first": 1}}
    assert first_json_difference(expected, actual) is None


def test_comparator_reports_first_nested_difference():
    """A field mutation is reported with the exact JSON path."""
    expected = [{"node": "#0", "weight": 1}]
    actual = [{"node": "#1", "weight": 1}]
    difference = first_json_difference(expected, actual)
    assert difference is not None
    assert difference.path == "$[0].node"
    assert difference.expected == "#0"
    assert difference.actual == "#1"


def test_comparator_detects_mutated_golden_fixture():
    """A mutation of a real fixture is caught without altering the fixture file."""
    pgt_path = GOLDEN_DIR / "expected/ArrayLoop/metis/pgt.json"
    expected = load_json(pgt_path)
    actual = json.loads(json.dumps(expected))
    actual[0]["name"] = "mutated-array"

    difference = first_json_difference(expected, actual)
    assert difference is not None
    assert difference.path == "$[0].name"
    assert difference.expected == "array"
    assert difference.actual == "mutated-array"
