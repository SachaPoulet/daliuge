"""Generate candidate fixtures for selected manifest cases."""

import argparse
import copy
import json
import subprocess
from pathlib import Path

from .golden_utils import (
    PipelineError,
    deterministic_gzip,
    isolated_cli_environment,
    run_pipeline,
    sha256_bytes,
    sha256_file,
)


GOLDEN_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = GOLDEN_DIR / "manifest.json"
REPOSITORY_ROOT = GOLDEN_DIR.parents[2]


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic compressed fixtures and a manifest candidate "
            "into an empty review directory. "
            "This command never overwrites committed expected files."
        )
    )
    parser.add_argument(
        "--dlg",
        required=True,
        help="Path to dlg installed in the isolated legacy virtual environment",
    )
    parser.add_argument(
        "--legacy-repo",
        required=True,
        type=Path,
        help="Legacy DALiuGE worktree whose HEAD must match the manifest",
    )
    parser.add_argument(
        "--case",
        dest="case_names",
        action="append",
        help="Manifest case name to generate; repeat as needed (default: all cases)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Empty/review directory for generated outputs",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print one status line per case instead of every stage",
    )
    return parser.parse_args()


def _git_head(repository: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _git_status(repository: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _dlg_git_head(executable: str) -> str:
    result = subprocess.run(
        [executable, "version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=isolated_cli_environment(),
    )
    prefix = "Git version:"
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    raise SystemExit(
        "Cannot determine the Git version of the supplied dlg executable"
    )


def _select_cases(manifest, requested_names):
    cases = manifest["cases"]
    if not cases:
        raise SystemExit("Manifest must contain at least one case")
    by_name = {case["name"]: case for case in cases}
    if len(by_name) != len(cases):
        raise SystemExit("Manifest case names must be unique")
    if not requested_names:
        return cases
    if len(requested_names) != len(set(requested_names)):
        raise SystemExit("A manifest case may only be selected once")

    unknown = sorted(set(requested_names) - set(by_name))
    if unknown:
        raise SystemExit(f"Unknown manifest case(s): {', '.join(unknown)}")
    return [by_name[name] for name in requested_names]


def _planned_output_dirs(output_dir: Path, cases):
    output_dir = output_dir.resolve()
    planned = []
    for case in cases:
        case_output = (output_dir / case["expected_dir"]).resolve()
        if output_dir != case_output and output_dir not in case_output.parents:
            raise SystemExit(
                f"Expected directory escapes review directory: {case['name']}"
            )
        planned.append(case_output)
    if len(planned) != len(set(planned)):
        raise SystemExit("Manifest case names resolve to duplicate output directories")
    return planned


def _repository_path(relative_path: str) -> Path:
    repository_root = REPOSITORY_ROOT.resolve()
    resolved = (repository_root / relative_path).resolve()
    if repository_root != resolved and repository_root not in resolved.parents:
        raise SystemExit(f"Case input escapes repository: {relative_path}")
    return resolved


def _assert_review_outputs_are_safe(planned_outputs, manifest):
    committed_outputs = [
        (GOLDEN_DIR / case["expected_dir"]).resolve()
        for case in manifest["cases"]
    ]
    for planned in planned_outputs:
        for committed in committed_outputs:
            if (
                planned == committed
                or planned in committed.parents
                or committed in planned.parents
            ):
                raise SystemExit(
                    "Refusing to write into or around committed expected fixtures"
                )


def _assert_empty_review_directory(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(
            f"Review directory must be empty before generation: {output_dir}"
        )


def _compress_case_outputs(outputs):
    fixtures = {}
    for stage in ("LG", "PGT", "PGT-P", "PG"):
        raw_path = outputs[stage]
        raw_payload = raw_path.read_bytes()
        stored_payload = deterministic_gzip(raw_payload)
        stored_path = raw_path.with_suffix(raw_path.suffix + ".gz")
        stored_path.write_bytes(stored_payload)
        raw_path.unlink()
        fixtures[stage] = {
            "file": stored_path.name,
            "sha256": sha256_bytes(raw_payload),
            "stored_sha256": sha256_bytes(stored_payload),
            "bytes": len(raw_payload),
            "stored_bytes": len(stored_payload),
        }
    return fixtures


def _write_manifest_candidate(output_dir: Path, manifest, generated):
    candidate = copy.deepcopy(manifest)
    by_name = {case["name"]: case for case in candidate["cases"]}
    for name, fixtures in generated.items():
        by_name[name]["expected"] = fixtures
    candidate_path = output_dir / "manifest.generated.json"
    candidate_path.write_text(
        json.dumps(candidate, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return candidate_path


def main():
    args = _parse_args()
    with MANIFEST_PATH.open(encoding="utf-8") as stream:
        manifest = json.load(stream)

    expected_commit = manifest["legacy_daliuge"]["commit"]
    actual_commit = _git_head(args.legacy_repo)
    if actual_commit != expected_commit:
        raise SystemExit(
            "Legacy checkout mismatch:\n"
            f"Expected: {expected_commit}\n"
            f"Actual:   {actual_commit}"
        )
    dirty = _git_status(args.legacy_repo)
    if dirty:
        raise SystemExit(
            "Legacy checkout must be clean before generating fixtures:\n"
            f"{dirty}"
        )

    actual_dlg_commit = _dlg_git_head(args.dlg)
    if actual_dlg_commit != expected_commit:
        raise SystemExit(
            "Legacy dlg mismatch:\n"
            f"Expected: {expected_commit}\n"
            f"Actual:   {actual_dlg_commit}"
        )

    cases = _select_cases(manifest, args.case_names)
    output_dir = args.output_dir.resolve()
    planned_outputs = _planned_output_dirs(output_dir, cases)
    _assert_review_outputs_are_safe(planned_outputs, manifest)
    _assert_empty_review_directory(output_dir)

    generated = {}
    failures = []
    total_raw = 0
    total_stored = 0
    for case, case_output in zip(cases, planned_outputs):
        input_path = _repository_path(case["input"])
        expected_input_digest = case["source"]["sha256"]
        actual_input_digest = sha256_file(input_path)
        if actual_input_digest != expected_input_digest:
            raise SystemExit(
                f"Pinned logical graph mismatch for {case['name']}:\n"
                f"Expected: {expected_input_digest}\n"
                f"Actual:   {actual_input_digest}"
            )
        try:
            outputs = run_pipeline(
                args.dlg, input_path, case_output, case["pipeline"]
            )
        except PipelineError as error:
            failures.append((case["name"], str(error)))
            print(f"FAIL: {case['name']}: {error}", flush=True)
            continue
        fixtures = _compress_case_outputs(outputs)
        generated[case["name"]] = fixtures

        if args.quiet:
            print(f"OK: {case['name']}", flush=True)
        for stage in ("LG", "PGT", "PGT-P", "PG"):
            fixture = fixtures[stage]
            total_raw += fixture["bytes"]
            total_stored += fixture["stored_bytes"]
            if not args.quiet:
                print(
                    f"{stage}: {case_output / fixture['file']} "
                    f"sha256={fixture['sha256']} "
                    f"bytes={fixture['bytes']} "
                    f"stored_bytes={fixture['stored_bytes']}"
                )
    if failures:
        print(
            f"Generation failed for {len(failures)} of {len(cases)} case(s); "
            "no manifest candidate was written."
        )
        for name, error in failures:
            first_line = error.splitlines()[0]
            print(f"- {name}: {first_line}")
        raise SystemExit(1)

    candidate_path = _write_manifest_candidate(output_dir, manifest, generated)
    ratio = (total_stored / total_raw) if total_raw else 0
    print(
        f"Generated {len(cases)} case(s): raw_bytes={total_raw} "
        f"stored_bytes={total_stored} ratio={ratio:.3f}"
    )
    print(
        f"Review {candidate_path} and the expected/ tree before deliberately "
        "copying them into the golden suite."
    )


if __name__ == "__main__":
    main()
