"""Run the pinned Agent-COM COM-03 oracle against the lane-local Rust port.

The generated result JSON files are temporary and are never copied into SIPI.
The report records only input digests, branch outcomes, and source identity.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Callable


UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
SCHEMA = "sipi.com-03-direct-port-oracle.v1"


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.STDOUT, text=True
    ).strip()


def git_archive_sha256(root: Path, revision: str, *paths: str) -> str:
    command = ["git", "-C", str(root), "archive", "--format=tar", revision]
    if paths:
        command.extend(["--", *paths])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    digest_state = hashlib.sha256()
    for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
        digest_state.update(block)
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.wait() != 0:
        raise RuntimeError(f"cannot hash Git archive: {stderr}")
    return digest_state.hexdigest()


def git_blob_sha256(root: Path, revision: str, path: str) -> str:
    payload = subprocess.check_output(
        ["git", "-C", str(root), "cat-file", "blob", f"{revision}:{path}"],
        stderr=subprocess.STDOUT,
    )
    return digest(payload)


def file_sha256(path: Path) -> str:
    return digest(path.read_bytes())


def scenario_set_sha256(
    scenarios: list[tuple[str, dict[str, Any], dict[str, Any], float, str]],
) -> str:
    canonical = [
        {
            "id": name,
            "golden": golden,
            "result": result,
            "atol": atol,
            "mode": mode,
        }
        for name, golden, result, atol, mode in scenarios
    ]
    return digest(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode())


def candidate_identity(candidate_root: Path, candidate_commit: str) -> dict[str, Any]:
    if not candidate_root.is_dir() or not candidate_commit:
        raise RuntimeError("bound oracle runs require candidate root and commit")
    actual_commit = git(candidate_root, "rev-parse", "HEAD")
    if actual_commit != candidate_commit:
        raise RuntimeError("candidate commit does not match the candidate worktree")
    return {
        "status": "immutable_candidate_bound",
        "commit": candidate_commit,
        "tree": git(candidate_root, "rev-parse", f"{candidate_commit}^{{tree}}"),
        "direct_crate_inventory_sha256": git_archive_sha256(
            candidate_root, candidate_commit, "crates/sipi-agent-com-direct"
        ),
        "cargo_lock_sha256": git_blob_sha256(
            candidate_root, candidate_commit, "crates/sipi-agent-com-direct/Cargo.lock"
        ),
    }


def materialize_git_archive(root: Path, revision: str, directory: Path) -> None:
    process = subprocess.Popen(
        ["git", "-C", str(root), "archive", revision],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
        archive.extractall(directory)
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.wait() != 0:
        raise RuntimeError(f"candidate archive materialization failed: {stderr}")


def resolve_cargo_executable(explicit: Path | None) -> Path:
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    environment_cargo = os.environ.get("CARGO")
    if environment_cargo:
        candidates.append(Path(environment_cargo))
    discovered = shutil.which("cargo")
    if discovered:
        candidates.append(Path(discovered))
    candidates.append(Path.home() / ".cargo" / "bin" / "cargo.exe")
    candidates.append(Path.home() / ".cargo" / "bin" / "cargo")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("bound oracle cannot locate cargo")


@contextlib.contextmanager
def bound_candidate_binary(
    *, candidate_root: Path, candidate_commit: str, toolchain: str, cargo_executable: Path | None
):
    identity = candidate_identity(candidate_root, candidate_commit)
    cargo = resolve_cargo_executable(cargo_executable)
    with tempfile.TemporaryDirectory(prefix="sipi-com-03-candidate-source-") as source_directory:
        with tempfile.TemporaryDirectory(prefix="sipi-com-03-candidate-target-") as target_directory:
            source_root = Path(source_directory)
            target_root = Path(target_directory)
            materialize_git_archive(candidate_root, candidate_commit, source_root)
            environment = os.environ.copy()
            environment.update({"CARGO_TARGET_DIR": str(target_root), "CARGO_INCREMENTAL": "0"})
            if toolchain:
                environment["RUSTUP_TOOLCHAIN"] = toolchain
            completed = subprocess.run(
                [
                    str(cargo),
                    "build",
                    "--manifest-path",
                    str(source_root / "crates" / "sipi-agent-com-direct" / "Cargo.toml"),
                    "--release",
                    "--locked",
                ],
                cwd=source_root,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError("bound candidate build failed")
            binary = target_root / "release" / "sipi-com-direct-compare"
            if os.name == "nt":
                binary = binary.with_suffix(".exe")
            if not binary.is_file():
                raise RuntimeError("bound candidate build did not produce the comparator binary")
            identity.update(
                {
                    "toolchain": toolchain,
                    "cargo_build": "clean_git_archive_with_independent_cargo_target_dir",
                    "binary_sha256": file_sha256(binary),
                }
            )
            yield binary, identity


@contextlib.contextmanager
def pinned_source(root: Path):
    """Yield a clean Git-object checkout even when an unrelated asset dirties root."""
    head = git(root, "rev-parse", "HEAD")
    tree = git(root, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}")
    if head != UPSTREAM_COMMIT or tree != UPSTREAM_TREE:
        raise RuntimeError("Agent-COM worktree does not expose the pinned commit/tree")
    if not git(root, "status", "--porcelain"):
        yield root
        return
    with tempfile.TemporaryDirectory(prefix="sipi-agent-com-pinned-") as directory:
        process = subprocess.Popen(
            ["git", "-C", str(root), "archive", UPSTREAM_COMMIT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdout is not None
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            archive.extractall(directory)
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        if process.wait() != 0:
            raise RuntimeError(f"cannot materialize pinned Agent-COM archive: {stderr}")
        yield Path(directory)


def ensure_pinned_clean(root: Path) -> None:
    if git(root, "rev-parse", "HEAD") != UPSTREAM_COMMIT:
        raise RuntimeError("Agent-COM worktree HEAD is not the pinned commit")
    if git(root, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}") != UPSTREAM_TREE:
        raise RuntimeError("Agent-COM worktree tree does not match the pinned commit")
    if git(root, "status", "--porcelain"):
        raise RuntimeError("Agent-COM worktree is dirty; refusing an unpinned oracle run")


def base_document() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_revision": "r480",
        "profile": {
            "source_revision": "r480",
            "reader_semantics": "r480",
            "fix_ids": [],
        },
        "cases": [
            {
                "case_index": 0,
                "metrics": {"COM_dB": 1.2, "array": [1.0, 2.0]},
            }
        ],
        "provenance": {
            "stable": "same",
            "platform": "oracle-platform",
            "python_version": "oracle-python",
        },
        "warnings": [],
        "timings_s": {"pipeline": 1.0},
    }


def scenario_documents() -> list[tuple[str, dict[str, Any], dict[str, Any], float, str]]:
    scenarios: list[tuple[str, dict[str, Any], dict[str, Any], float, str]] = []

    left = base_document()
    scenarios.append(("identical", left, copy.deepcopy(left), 1.0e-12, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    left["schema_version"] = True
    right["schema_version"] = True
    scenarios.append(("schema_version_true_equals_one", left, right, 1.0e-12, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    left["schema_version"] = 1.0
    right["schema_version"] = 1.0
    scenarios.append(("schema_version_float_equals_one", left, right, 1.0e-12, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    left["provenance"] = []
    right["provenance"] = []
    scenarios.append(("provenance_empty_sequence", left, right, 1.0e-12, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    left["provenance"] = [["stable", "same"], ["platform", "left"], ["python_version", "left"]]
    right["provenance"] = [["stable", "same"], ["platform", "right"], ["python_version", "right"]]
    scenarios.append(("provenance_pair_sequence_metadata_ignored", left, right, 1.0e-12, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    right["timings_s"] = {"pipeline": 999.0}
    right["provenance"]["platform"] = "other-platform"
    right["provenance"]["python_version"] = "other-python"
    scenarios.append(("non_comparable_metadata_ignored", left, right, 1.0e-12, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    right["cases"][0]["metrics"]["COM_dB"] = 1.2005
    scenarios.append(("numeric_within_absolute_atol", left, right, 0.001, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    right["cases"][0]["metrics"]["COM_dB"] = 1.3
    right["cases"][0]["metrics"]["array"] = [1.0, 3.0]
    scenarios.append(("numeric_and_nested_mismatch", left, right, 0.0, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    right["cases"][0]["metrics"]["extra"] = True
    scenarios.append(("object_key_mismatch", left, right, 1.0e-12, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    right["cases"][0]["metrics"]["array"] = [1.0]
    scenarios.append(("array_length_mismatch", left, right, 1.0e-12, "compare"))

    left = base_document()
    right = copy.deepcopy(left)
    left["cases"][0]["metrics"]["label"] = "left"
    right["cases"][0]["metrics"]["label"] = "right"
    scenarios.append(("scalar_string_mismatch", left, right, 1.0e-12, "compare"))

    invalid = base_document()
    invalid["schema_version"] = 2
    scenarios.append(("invalid_schema_version", invalid, copy.deepcopy(invalid), 1.0e-12, "error"))

    invalid = base_document()
    invalid.pop("warnings")
    scenarios.append(("missing_required_key", invalid, copy.deepcopy(invalid), 1.0e-12, "error"))

    invalid = base_document()
    invalid["profile"]["source_revision"] = "other"
    scenarios.append(("invalid_profile", invalid, copy.deepcopy(invalid), 1.0e-12, "error"))

    invalid = base_document()
    invalid["cases"] = []
    scenarios.append(("empty_cases", invalid, copy.deepcopy(invalid), 1.0e-12, "error"))

    invalid = base_document()
    invalid["cases"][0]["case_index"] = 1
    scenarios.append(("non_contiguous_case_index", invalid, copy.deepcopy(invalid), 1.0e-12, "error"))

    invalid = base_document()
    invalid["cases"][0]["metrics"] = {"A_s": -1.0}
    scenarios.append(("negative_signal", invalid, copy.deepcopy(invalid), 1.0e-12, "error"))

    invalid = base_document()
    invalid["cases"][0]["metrics"] = {"optimization_cursor": 1.5}
    scenarios.append(("non_integer_cursor", invalid, copy.deepcopy(invalid), 1.0e-12, "error"))

    invalid = base_document()
    invalid["cases"][0]["metrics"] = {"L": 4, "EW_UI": [0.1, 0.2]}
    scenarios.append(("invalid_eye_width_shape", invalid, copy.deepcopy(invalid), 1.0e-12, "error"))

    # A malformed JSON input exercises the CLI's ValueError -> exit 2 branch.
    scenarios.append(("malformed_json", {"$malformed": True}, {"$malformed": True}, 1.0e-12, "malformed"))

    # A negative tolerance is validated before either artifact is read.
    scenarios.append(("negative_atol", base_document(), base_document(), -1.0, "negative_atol"))
    scenarios.append(("missing_golden", base_document(), base_document(), 1.0e-12, "missing_golden"))
    scenarios.append(("missing_result", base_document(), base_document(), 1.0e-12, "missing_result"))
    return scenarios


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def diagnostic_category(text: str, *, exit_code: int | None = None) -> str:
    lowered = text.lower()
    if not text:
        return "empty"
    if "no such file" in lowered or "cannot read" in lowered or "os error 2" in lowered:
        return "io_error"
    if "json" in lowered or "property name" in lowered:
        return "json_error"
    if "schema" in lowered or "tolerance" in lowered or "configuration" in lowered:
        return "config_error"
    if exit_code == 2:
        return "argument_or_input_error"
    return "diagnostic"


def invoke_python_cli(cli_main: Callable[..., int], golden: Path, result: Path, atol: float) -> dict[str, Any]:
    args = ["compare", "--golden", str(golden), "--result", str(result), "--atol", str(atol)]
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = cli_main(args)
        except SystemExit as error:  # argparse's observable invalid-argument branch
            code = error.code if isinstance(error.code, int) else 1
            return {
                "kind": "system_exit",
                "exit_code": code,
                "stdout": stdout.getvalue(),
                "stderr_category": diagnostic_category(stderr.getvalue(), exit_code=code),
            }
        except Exception as error:  # pragma: no cover - retained for source boundary diagnostics
            return {
                "kind": "return",
                "exit_code": 1,
                "stdout": stdout.getvalue(),
                "stderr_category": diagnostic_category(stderr.getvalue(), exit_code=1),
                "exception": type(error).__name__,
            }
    return {
        "kind": "return",
        "exit_code": code,
        "stdout": stdout.getvalue(),
        "stderr_category": diagnostic_category(stderr.getvalue(), exit_code=code),
    }


def invoke_rust(binary: Path, golden: Path, result: Path, atol: float) -> dict[str, Any]:
    completed = subprocess.run(
        [str(binary), "--golden", str(golden), "--result", str(result), "--atol", str(atol)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "kind": "return",
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr_category": diagnostic_category(completed.stderr, exit_code=completed.returncode),
    }


def semantic_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": value.get("kind"),
        "exit_code": value.get("exit_code"),
        "stdout": value.get("stdout"),
    }


def run(
    *,
    upstream_root: Path,
    rust_binary: Path | None = None,
    run_id: str,
    candidate_root: Path | None = None,
    candidate_commit: str | None = None,
    toolchain: str | None = None,
    cargo_executable: Path | None = None,
) -> dict[str, Any]:
    if candidate_root is None:
        if candidate_commit or toolchain or cargo_executable:
            raise RuntimeError("bound candidate options require --candidate-root")
        if rust_binary is None or not rust_binary.is_file():
            raise RuntimeError("unbound oracle runs require --rust-binary")
        binary_context = contextlib.nullcontext(
            (
                rust_binary,
                {
                    "status": "unbound_observation",
                    "reason": "preparation_worktree_is_not_an_immutable_candidate",
                },
            )
        )
    else:
        if rust_binary is not None:
            raise RuntimeError("--rust-binary is forbidden in immutable candidate mode")
        if not candidate_commit or not toolchain:
            raise RuntimeError("bound oracle runs require candidate commit and toolchain")
        binary_context = bound_candidate_binary(
            candidate_root=candidate_root,
            candidate_commit=candidate_commit,
            toolchain=toolchain,
            cargo_executable=cargo_executable,
        )
    with binary_context as (effective_binary, candidate):
        upstream_archive_sha256 = git_archive_sha256(upstream_root, UPSTREAM_COMMIT)
        with pinned_source(upstream_root) as clean_root:
            return _run_clean(
                clean_root=clean_root,
                rust_binary=effective_binary,
                run_id=run_id,
                source_mode="git_worktree" if clean_root == upstream_root else "git_archive",
                candidate=candidate,
                upstream_archive_sha256=upstream_archive_sha256,
            )


def _run_clean(
    *,
    clean_root: Path,
    rust_binary: Path,
    run_id: str,
    source_mode: str,
    candidate: dict[str, Any],
    upstream_archive_sha256: str,
) -> dict[str, Any]:
    sys.path.insert(0, str(clean_root / "src"))
    from agent_com.cli import main as upstream_cli_main
    from agent_com.reporting import compare_result_json
    from agent_com.errors import ConfigError

    scenarios_report = []
    scenarios = scenario_documents()
    scenario_digest = scenario_set_sha256(scenarios)
    with tempfile.TemporaryDirectory(prefix="sipi-com-03-oracle-") as directory:
        root = Path(directory)
        for name, golden_document, result_document, atol, mode in scenarios:
            if mode == "malformed":
                golden_bytes = b"{ not JSON"
                result_bytes = b"{ not JSON"
            else:
                golden_bytes = json.dumps(golden_document, sort_keys=True, separators=(",", ":")).encode()
                result_bytes = json.dumps(result_document, sort_keys=True, separators=(",", ":")).encode()
            golden = root / f"{name}.golden.json"
            result = root / f"{name}.result.json"
            if mode != "missing_golden":
                golden.write_bytes(golden_bytes)
            if mode != "missing_result":
                result.write_bytes(result_bytes)

            if mode == "compare":
                try:
                    expected_mismatches = compare_result_json(golden, result, atol=atol)
                    oracle_function = {"kind": "matched" if not expected_mismatches else "mismatched", "mismatches": expected_mismatches}
                except ConfigError as error:
                    del error
                    oracle_function = {"kind": "config_error"}
            elif mode == "malformed":
                oracle_function = {"kind": "value_error"}
            elif mode in {"missing_golden", "missing_result"}:
                oracle_function = {"kind": "io_error"}
            else:
                oracle_function = {"kind": "config_error"}
            python_cli = invoke_python_cli(upstream_cli_main, golden, result, atol)
            rust_cli = invoke_rust(rust_binary, golden, result, atol)
            scenarios_report.append(
                {
                    "id": name,
                    "atol": atol,
                    "golden_sha256": digest(golden_bytes),
                    "result_sha256": digest(result_bytes),
                    "oracle_function": oracle_function,
                    "python_cli": python_cli,
                    "rust_cli": rust_cli,
                    "cli_contract_match": semantic_projection(python_cli) == semantic_projection(rust_cli),
                    "stderr_exact_match": python_cli.get("stderr_category") == rust_cli.get("stderr_category"),
                }
            )

    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "source": {
            "repository": "https://github.com/z331225718/agent-com.git",
            "commit": UPSTREAM_COMMIT,
            "tree": UPSTREAM_TREE,
            "working_tree_clean": True,
            "source_mode": source_mode,
            "archive_inventory_sha256": upstream_archive_sha256,
        },
        "rust_binary": {
            "mode": "unbound_external_binary"
            if candidate["status"] == "unbound_observation"
            else "candidate_archive_build"
        },
        "candidate": candidate,
        "scenario_set_sha256": scenario_digest,
        "scenario_count": len(scenarios_report),
        "scenarios": scenarios_report,
        "all_cli_contracts_match": all(item["cli_contract_match"] for item in scenarios_report),
        "stderr_is_not_a_frozen_contract": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-com-root", type=Path, required=True)
    parser.add_argument("--rust-binary", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--toolchain")
    parser.add_argument("--cargo-executable", type=Path)
    arguments = parser.parse_args()
    report = run(
        upstream_root=arguments.agent_com_root,
        rust_binary=arguments.rust_binary,
        run_id=arguments.run_id,
        candidate_root=arguments.candidate_root,
        candidate_commit=arguments.candidate_commit,
        toolchain=arguments.toolchain,
        cargo_executable=arguments.cargo_executable,
    )
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    with arguments.report.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"scenario_count": report["scenario_count"], "all_cli_contracts_match": report["all_cli_contracts_match"]}, sort_keys=True))
    return 0 if report["all_cli_contracts_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
