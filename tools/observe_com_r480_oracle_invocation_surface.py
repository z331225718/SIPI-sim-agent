"""Observe a hash-pinned external R480 runner surface without importing it."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com.r480.oracle-invocation-surface-report.v1"
ORIGIN = "https://github.com/z331225718/agent-com.git"
COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
TOOL_PATH = "tools/run_matlab_oracle.py"
TOOL_BLOB = "36d4fa55f6eaf9ecdd72ba2cebfbc1b01908e8bc"
TOOL_SHA256 = "db63ed42375ac990cb53d9926f603e050b652b0706c079f2e4456a5d97d87d42"
TOOL_BYTES = 30851


class ObservationError(RuntimeError):
    pass


def _outside_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return True
    return False


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=text).stdout


def _source_bytes(source_root: Path) -> bytes:
    try:
        if str(_git(source_root, "status", "--porcelain")).strip():
            raise ObservationError("external_source_worktree_not_clean")
        if str(_git(source_root, "remote", "get-url", "origin")).strip() != ORIGIN:
            raise ObservationError("external_source_origin_mismatch")
        if str(_git(source_root, "rev-parse", "HEAD")).strip() != COMMIT:
            raise ObservationError("external_source_commit_mismatch")
        if str(_git(source_root, "rev-parse", f"{COMMIT}^{{tree}}")).strip() != TREE:
            raise ObservationError("external_source_tree_mismatch")
        blob = str(_git(source_root, "rev-parse", f"{COMMIT}:{TOOL_PATH}")).strip()
        payload = _git(source_root, "cat-file", "blob", blob, text=False)
    except subprocess.CalledProcessError as error:
        raise ObservationError("external_source_git_object_unavailable") from error
    if blob != TOOL_BLOB or len(payload) != TOOL_BYTES or hashlib.sha256(payload).hexdigest() != TOOL_SHA256:
        raise ObservationError("external_runner_tool_identity_mismatch")
    return payload


class _SurfaceVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.options: set[str] = set()
        self.argparse_constructor_observed = False
        self.subprocess_launch_api_observed = False
        self.file_io_api_observed = False
        self.entrypoint_guard_observed = False

    def visit_Call(self, node: ast.Call) -> None:
        function = node.func
        if isinstance(function, ast.Attribute):
            if function.attr == "add_argument":
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str) and argument.value.startswith("-"):
                        self.options.add(argument.value)
            if function.attr in {"run", "Popen", "call", "check_call", "check_output"}:
                self.subprocess_launch_api_observed = True
            if function.attr == "open":
                self.file_io_api_observed = True
        elif isinstance(function, ast.Name):
            if function.id == "open":
                self.file_io_api_observed = True
            if function.id == "ArgumentParser":
                self.argparse_constructor_observed = True
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        values = [child.value for child in ast.walk(node.test) if isinstance(child, ast.Constant) and isinstance(child.value, str)]
        if "__main__" in values:
            self.entrypoint_guard_observed = True
        self.generic_visit(node)


def _scan(payload: bytes) -> dict:
    try:
        tree = ast.parse(payload.decode("utf-8"), filename=TOOL_PATH)
    except (SyntaxError, UnicodeDecodeError) as error:
        raise ObservationError("external_runner_tool_not_static_python") from error
    visitor = _SurfaceVisitor()
    visitor.visit(tree)
    return {
        "declared_cli_options": sorted(visitor.options),
        "argparse_constructor_observed": visitor.argparse_constructor_observed,
        "help_surface": "not_executed" if visitor.argparse_constructor_observed else "not_observed",
        "dry_run_surface": "declared_but_not_executed" if "--dry-run" in visitor.options else "not_observed",
        "subprocess_launch_api_observed": visitor.subprocess_launch_api_observed,
        "file_io_api_observed": visitor.file_io_api_observed,
        "entrypoint_guard_observed": visitor.entrypoint_guard_observed,
        "dynamic_invocation_dependencies": "unknown",
    }


def observe(source_root: Path) -> dict:
    payload = _source_bytes(source_root)
    return {
        "schema": SCHEMA,
        "status": "runner_interface_partially_observed",
        "source": {"canonical_origin": ORIGIN, "commit": COMMIT, "tree": TREE, "object_format": "sha1"},
        "tool": {"path": TOOL_PATH, "git_blob": TOOL_BLOB, "content_sha256": TOOL_SHA256, "byte_length": TOOL_BYTES},
        "surface": _scan(payload),
        "execution": {"authorized": False, "invoked": False, "status": "dynamic_invocation_not_authorized_or_not_safe"},
        "non_claims": [
            "The runner was parsed as an external Git blob and was not imported or executed.",
            "No MATLAB, workbook, fixture, parameter, input, result, default, formula, or code fragment is recorded.",
            "This does not establish a runnable oracle, an authoritative reference, or COM parity.",
        ],
    }


def validate_report(report: object) -> None:
    if not isinstance(report, dict) or set(report) != {"schema", "status", "source", "tool", "surface", "execution", "non_claims"}:
        raise ObservationError("report_shape_invalid")
    if report["schema"] != SCHEMA or report["status"] != "runner_interface_partially_observed":
        raise ObservationError("report_status_invalid")
    if report["source"] != {"canonical_origin": ORIGIN, "commit": COMMIT, "tree": TREE, "object_format": "sha1"}:
        raise ObservationError("source_identity_invalid")
    if report["tool"] != {"path": TOOL_PATH, "git_blob": TOOL_BLOB, "content_sha256": TOOL_SHA256, "byte_length": TOOL_BYTES}:
        raise ObservationError("tool_identity_invalid")
    surface = report["surface"]
    expected_surface_keys = {"declared_cli_options", "argparse_constructor_observed", "help_surface", "dry_run_surface", "subprocess_launch_api_observed", "file_io_api_observed", "entrypoint_guard_observed", "dynamic_invocation_dependencies"}
    if not isinstance(surface, dict) or set(surface) != expected_surface_keys or not isinstance(surface["declared_cli_options"], list) or surface["declared_cli_options"] != sorted(set(surface["declared_cli_options"])) or not all(isinstance(item, str) and item.startswith("-") for item in surface["declared_cli_options"]) or not all(isinstance(surface[key], bool) for key in ("argparse_constructor_observed", "subprocess_launch_api_observed", "file_io_api_observed", "entrypoint_guard_observed")) or surface["help_surface"] not in {"not_executed", "not_observed"} or surface["dry_run_surface"] not in {"declared_but_not_executed", "not_observed"} or surface["dynamic_invocation_dependencies"] != "unknown":
        raise ObservationError("surface_invalid")
    if report["execution"] != {"authorized": False, "invoked": False, "status": "dynamic_invocation_not_authorized_or_not_safe"}:
        raise ObservationError("execution_must_remain_blocked")
    if not isinstance(report["non_claims"], list) or len(report["non_claims"]) != 3 or not all(isinstance(item, str) and item for item in report["non_claims"]):
        raise ObservationError("non_claims_invalid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not _outside_root(args.report):
        raise SystemExit("report must be outside the SIPI worktree")
    try:
        report = observe(args.source_root)
        validate_report(report)
        args.report.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    except (OSError, ObservationError, subprocess.SubprocessError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": report["status"], "report_sha256": hashlib.sha256(args.report.read_bytes()).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
