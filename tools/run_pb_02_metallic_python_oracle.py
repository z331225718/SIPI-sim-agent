"""Run PB-02 metallic/CTLE cases against an independent pinned Python oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import run_pb_03_python_oracle_matrix as matrix
from pb_03_replay_common import _tool as tool_identity, resolve_executable


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "docs/baselines/pb-02-metallic-python-oracle-corpus.v1.json"
ORACLE_HELPER = ROOT / "tools/pb_02_metallic_python_oracle.py"
CANDIDATE = {
    "commit": "dc82489d109f27b70940a5f1037cb08d3c10a8b6",
    "tree": "6311d5a0e88cd008e22ab9dcc0e7c18f57120ed3",
    "archive_sha256": "dcf9e38aaf0980c40a6c7640e5c229ac851a11e7c287d4bde386b21b1e9c5b00",
}
CHILD_PYTHON_IDENTITY = """
import hashlib
import json
import platform
import sys
import warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import numpy as np
import scipy
python_file = Path(sys.executable)
print(json.dumps({
    "python": {"executable": python_file.name, "file_sha256": hashlib.sha256(python_file.read_bytes()).hexdigest(), "implementation": platform.python_implementation(), "version": platform.python_version(), "path_redacted": True},
    "numpy": {"module": np.__name__, "version": np.__version__, "core_module": np.core.__name__},
    "scipy": {"module": scipy.__name__, "version": scipy.__version__},
}, sort_keys=True), file=sys.stderr)
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_host_python(value: str | None) -> Path:
    candidate = Path(value) if value else Path(sys.executable)
    if "windowsapps" in str(candidate).lower() or not candidate.is_file():
        candidate = Path(sys.executable)
    if "windowsapps" in str(candidate).lower() or not candidate.is_file():
        raise RuntimeError("host Python must resolve to an actual executable file")
    return candidate.resolve()


def is_oracle_command(command: list[str]) -> bool:
    return any(Path(str(item)).name == ORACLE_HELPER.name for item in command)


def resolve_toolchain_for_host(host_python: Path, timeout: int) -> tuple[dict[str, object], dict[str, Path]]:
    specs = {
        "cargo": ("cargo", ("-Vv",)),
        "rustc": ("rustc", ("-Vv",)),
        "uv": ("uv", ("--version",)),
    }
    report: dict[str, object] = {"timeout_seconds": timeout}
    tool_paths: dict[str, Path] = {}
    for role, (value, version_args) in specs.items():
        executable = resolve_executable(value)
        if executable is None or "windowsapps" in str(executable).lower():
            raise RuntimeError(f"{role} executable is unavailable or an app alias")
        tool_paths[role] = executable
        report[role] = tool_identity(executable, role, version_args)
    report["python"] = tool_identity(host_python, "python", ("--version",))
    tool_paths["python"] = host_python
    return report, tool_paths


def run(args: argparse.Namespace) -> dict[str, object]:
    matrix.CORPUS_PATH = CORPUS
    matrix.ORACLE_HELPER = ORACLE_HELPER
    original_metadata_summary = matrix.metadata_summary

    def metadata_summary(path: Path) -> dict[str, object]:
        summary = original_metadata_summary(path)
        try:
            metadata = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return summary
        diagnostics = metadata.get("diagnostics")
        if isinstance(diagnostics, dict):
            summary["diagnostics"] = diagnostics
        return summary

    matrix.metadata_summary = metadata_summary
    original_run_command = matrix.run_command
    host_python = resolve_host_python(args.host_python)
    child_identities: list[dict[str, object]] = []

    def resolve_toolchain(timeout):
        return resolve_toolchain_for_host(host_python, timeout)

    def run_command(command, cwd, timeout, tool_paths=None):
        cargo_wrapper = os.environ.pop("CARGO_BUILD_RUSTC_WRAPPER", None)
        try:
            result = original_run_command(command, cwd, timeout, tool_paths)
        finally:
            if cargo_wrapper is not None:
                os.environ["CARGO_BUILD_RUSTC_WRAPPER"] = cargo_wrapper
        if command and command[0] == "uv" and is_oracle_command(command):
            project = command[command.index("--project") + 1]
            identity = original_run_command(
                ["uv", "run", "--project", project, "--frozen", "python", "-c", CHILD_PYTHON_IDENTITY],
                cwd,
                timeout,
                tool_paths,
            )
            if identity.get("exit_code") != 0 or not isinstance(identity.get("stderr_json"), dict):
                raise RuntimeError("archive uv child Python identity resolution failed")
            child_identities.append({"identity": identity["stderr_json"], "process": identity})
        return result

    matrix.resolve_toolchain = resolve_toolchain
    matrix.run_command = run_command
    if args.candidate_commit != CANDIDATE["commit"] or args.candidate_tree != CANDIDATE["tree"] or args.candidate_archive_sha256 != CANDIDATE["archive_sha256"]:
        raise ValueError("candidate identity must be the immutable dc82489d prep archive")
    result = matrix.run_matrix(
        candidate_repo=args.candidate_repo.resolve(),
        upstream_repo=args.upstream_repo.resolve(),
        output=args.output.resolve(),
        run_id=args.run_id,
        candidate_commit=args.candidate_commit,
        candidate_tree=args.candidate_tree,
        candidate_archive_sha256=args.candidate_archive_sha256,
        timeout=args.timeout,
    )
    if not child_identities or any(item["identity"] != child_identities[0]["identity"] for item in child_identities):
        raise RuntimeError("archive uv child Python identity is missing or inconsistent")
    result["toolchain"]["child_python"] = {
        "command": "uv run --project <archive> --frozen python -c <identity>",
        **child_identities[0],
    }
    result["toolchain"]["host_python"] = {
        "executable": host_python.name,
        "file_sha256": sha256(host_python),
        "path_redacted": True,
        "source": "--host-python" if args.host_python else "sys.executable",
    }
    result["schema"] = "sipi.pb-02-metallic-python-oracle-replay.v1"
    result["row"] = "PB-02"
    result["scope"] = "analytic_ctle_metallic_noninteger_grid"
    result["harness"] = {
        **(result.get("harness") or {}),
        "wrapper": {
            "path": "tools/run_pb_02_metallic_python_oracle.py",
            "sha256": sha256(Path(__file__)),
        },
        "python_oracle": {
            "path": "tools/pb_02_metallic_python_oracle.py",
            "sha256": sha256(ORACLE_HELPER),
            "snapshot": "candidate_prep_archive_harness_snapshot",
        },
    }
    result["build"]["environment_policy"] = {
        "rustc_wrapper_cleared": True,
        "rustc_workspace_wrapper_cleared": True,
        "cargo_build_rustc_wrapper_cleared": True,
    }
    result["claims"] = {
        "independent_python_payload_oracle": bool(child_identities),
        "ordinary_payload_parity": False,
        "near_integral_external_blocked": False,
        "near_integral_counted_as_parity": False,
        "global_branch_parity": False,
        "promotion": False,
    }
    policy_blockers = []
    ordinary_policy_passed = False
    near_policy_passed = False
    for case in result.get("cases", []):
        if case.get("id") == "metallic-ctle-ordinary-3ghz-10ghz":
            if not (
                case.get("candidate_process", {}).get("exit_code") == 0
                and case.get("oracle_process", {}).get("exit_code") == 0
                and case.get("status") == "passed"
                and case.get("payload", {}).get("compared_field_count") == 17
                and case.get("payload", {}).get("equal") is True
            ):
                policy_blockers.append("ordinary_case_policy_failed")
            else:
                ordinary_policy_passed = True
        elif case.get("id") == "metallic-ctle-near-integral-3ghz":
            diagnostics = case.get("oracle", {}).get("diagnostics", {})
            if not (
                case.get("candidate_process", {}).get("exit_code") == 0
                and case.get("oracle_process", {}).get("exit_code") == 1
                and diagnostics.get("failure_code") == "pinned_channel_cubic_interp1d_two_point_boundary"
                and diagnostics.get("failure_stage") == "channel"
                and case.get("payload", {}).get("compared_field_count") == 0
            ):
                policy_blockers.append("near_integral_failure_policy_failed")
            else:
                case["blockers"] = ["pinned_channel_cubic_interp1d_two_point_boundary"]
                near_policy_passed = True
    result["claims"]["near_integral_external_blocked"] = near_policy_passed
    if policy_blockers:
        result["status"] = "blocked"
        result["policy_blockers"] = policy_blockers
    elif ordinary_policy_passed:
        result["claims"]["ordinary_payload_parity"] = True
    args.output.write_bytes(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path, default=matrix.DEFAULT_UPSTREAM)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-commit", default=CANDIDATE["commit"])
    parser.add_argument("--candidate-tree", default=CANDIDATE["tree"])
    parser.add_argument("--candidate-archive-sha256", default=CANDIDATE["archive_sha256"])
    parser.add_argument("--host-python", type=str)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({"status": result["status"], "run_id": result["run_id"], "case_count": len(result["cases"])}, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
