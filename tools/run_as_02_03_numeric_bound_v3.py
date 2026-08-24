"""Run a pinned upstream-vs-Rust numeric observation for AS-02 or AS-03."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tarfile
from pathlib import PurePosixPath
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
UPSTREAM_ROOT = Path(r"C:\Users\z3312\code\agent-spice")
FIXTURE = "# Hz S RI R 50\n1e6 0.01 0 0.8 0 0.8 0 0.01 0\n1e7 0.01 0 0.79 0 0.79 0 0.01 0\n1e8 0.01 0 0.7 0 0.7 0 0.01 0\n1e9 0.01 0 0.4 0 0.4 0 0.01 0\n"
FIXTURE_KIND = "fixed_touchstone_line_s2p_v1"
FIXTURE_GENERATED_BY = "tools/run_as_02_03_numeric_bound_v3.py:FIXTURE"
AS03_ARGS = (
    "--n-poles-real",
    "1",
    "--n-poles-cmplx",
    "0",
    "--max-order",
    "1",
    "--fit-iterations",
    "2",
    "--max-y-rms-siemens",
    "100",
    "--passivity",
    "off",
)
AS02_ARGS = (
    "--rms-target",
    "1",
    "--max-order",
    "1",
    "--min-order",
    "1",
    "--max-order-step",
    "1",
    "--cascade-samples",
    "8",
)
RUN_TIMEOUT_SECONDS = 300
WRAPPER_POLICY = {
    "schema": "sipi.path-free-wrapper-policy.v1",
    "clear_inherited_rustc_wrapper": True,
    "clear_inherited_rustc_workspace_wrapper": True,
    "rustc_wrapper": "unset",
    "rustc_workspace_wrapper": "unset",
}


def _has_reparse_component(path: Path) -> bool:
    current = path.absolute()
    while True:
        try:
            stat_result = current.lstat()
        except FileNotFoundError:
            stat_result = None
        except OSError as error:
            raise RuntimeError(f"cannot inspect {current.name} custody") from error
        if stat_result is not None and (current.is_symlink() or bool(getattr(stat_result, "st_file_attributes", 0) & 0x400)):
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _outside(path: Path, ancestor: Path) -> bool:
    try:
        path.relative_to(ancestor)
    except ValueError:
        return True
    return False


def _fresh_root(path: Path, label: str, protected_repositories: tuple[Path, ...] = (ROOT, UPSTREAM_ROOT)) -> Path:
    if not path.is_absolute():
        raise RuntimeError(f"{label} must be absolute")
    candidate = path.absolute()
    if candidate.exists():
        raise RuntimeError(f"{label} must be create-new")
    parent = candidate.parent.resolve(strict=True)
    if _has_reparse_component(parent):
        raise RuntimeError(f"{label} has a reparse ancestor")
    resolved_repositories = tuple(repo.resolve(strict=True) for repo in protected_repositories)
    if any(not _outside(parent, repo) or not _outside(repo, candidate) for repo in resolved_repositories):
        raise RuntimeError(f"{label} must be outside protected repositories")
    try:
        candidate.mkdir(parents=False, exist_ok=False)
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        try:
            if candidate.is_dir() and not candidate.is_symlink():
                candidate.rmdir()
        except OSError:
            pass
        raise RuntimeError(f"{label} creation failed closed") from error
    try:
        if _has_reparse_component(candidate) or not resolved.is_dir() or any(not _outside(resolved, repo) or not _outside(repo, resolved) for repo in resolved_repositories):
            raise RuntimeError(f"{label} custody is not regular and external")
    except Exception:
        try:
            if candidate.is_dir() and not candidate.is_symlink():
                candidate.rmdir()
        except OSError:
            pass
        raise
    return resolved


def _regular_tool(path: Path, role: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"{role} resolution failed closed") from error
    if _has_reparse_component(path) or not resolved.is_file():
        raise RuntimeError(f"{role} must be a regular executable")
    return resolved


def _checked_repo(path: Path, label: str, run_root: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"{label} resolution failed closed") from error
    if _has_reparse_component(path) or _has_reparse_component(run_root) or not resolved.is_dir() or not _outside(resolved, run_root) or not _outside(run_root, resolved):
        raise RuntimeError(f"{label} repository custody failed")
    return resolved


def _git_env() -> dict[str, str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} or key.startswith("GIT_CONFIG_"):
            environment.pop(key, None)
    return environment


def _build_env(candidate_root: Path, target: Path, rustc: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if key in {"RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "UV_OFFLINE", "PIP_NO_INDEX", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} or key.startswith("CARGO_BUILD_") or key.startswith("GIT_CONFIG_"):
            environment.pop(key, None)
    environment.update({"CARGO_TARGET_DIR": str(target), "CARGO_INCREMENTAL": "0", "SOURCE_DATE_EPOCH": "0", "RUSTC": str(rustc), "CARGO_NET_OFFLINE": "true", "UV_OFFLINE": "1", "PIP_NO_INDEX": "1"})
    sep = "\x1f"
    environment["CARGO_ENCODED_RUSTFLAGS"] = sep.join((f"--remap-path-prefix={candidate_root}=/sipi-candidate", f"--remap-path-prefix={target}=/sipi-target", "-Cmetadata=as-numeric", "-Clink-arg=/Brepro"))
    return environment


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def has_absolute_payload(value: object) -> bool:
    if isinstance(value, dict):
        return any(has_absolute_payload(key) or has_absolute_payload(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_absolute_payload(item) for item in value)
    return isinstance(value, str) and bool(__import__("re").search(r"(?:^[A-Za-z]:[\\/]|^//|^/)", value))


def profile_for(row: str, fixture_sha256: str) -> dict[str, Any]:
    if row == "AS-03":
        return {"fixture_sha256": fixture_sha256, "as03_args": list(AS03_ARGS), "as03_profile": "governing_v2_v3_current_exact_fixture_and_args"}
    if row == "AS-02":
        return {"fixture_sha256": fixture_sha256, "as02_args": list(AS02_ARGS), "as02_profile": "governing_v2_v3_current_exact_fixture_and_cascade_args"}
    raise ValueError(f"unsupported workflow: {row}")


def archive(repo: Path, revision: str, destination: Path, run_root: Path) -> str:
    checked_repo = _checked_repo(repo, "archive", run_root)
    if destination.exists() or _has_reparse_component(destination.parent):
        raise RuntimeError("archive destination must be create-new")
    try:
        payload = subprocess.check_output(["git", "-C", str(checked_repo), "archive", "--format=tar", revision], env=_git_env(), timeout=RUN_TIMEOUT_SECONDS)
        destination.mkdir(parents=False, exist_ok=False)
        root = destination.resolve(strict=True)
        with tarfile.open(fileobj=__import__("io").BytesIO(payload), mode="r:") as tar:
            members = []
            for member in tar:
                members.append(member)
            _validate_archive_members(destination, root, members)
            tar.extractall(destination, members=members)
        if _has_reparse_component(destination) or destination.resolve(strict=True) != root:
            raise RuntimeError("archive materialization custody changed")
    except (OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        raise RuntimeError("archive materialization failed closed") from error
    return sha_bytes(payload)


def _validate_archive_members(destination: Path, root: Path, members: list[tarfile.TarInfo]) -> None:
    seen: set[str] = set()
    for member in members:
        name = member.name
        pure = PurePosixPath(name)
        if not name or "\\" in name or pure.is_absolute() or ".." in pure.parts or ":" in pure.parts[0]:
            raise RuntimeError(f"archive path escape: {name}")
        folded = name.casefold()
        if folded in seen:
            raise RuntimeError(f"archive duplicate member: {name}")
        seen.add(folded)
        target = (destination / Path(*pure.parts)).resolve()
        if target != root and root not in target.parents:
            raise RuntimeError(f"archive path escape: {name}")
        if not (member.isfile() or member.isdir()) or member.issym() or member.islnk():
            raise RuntimeError(f"unsupported archive member: {name}")


def _tool_snapshot(path: Path, role: str, args: tuple[str, ...]) -> dict[str, Any]:
    checked = _regular_tool(path, role)
    try:
        result = subprocess.run([str(checked), *args], capture_output=True, check=False, timeout=RUN_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"{role} version probe failed closed") from error
    if result.returncode != 0:
        raise RuntimeError(f"{role} version probe returned nonzero")
    return {"schema": "sipi.path-free-tool-identity.v1", "role": role, "executable": checked.name, "path_redacted": True, "file_sha256": sha(checked), "version_sha256": sha_bytes(result.stdout + b"\0" + result.stderr), "exit_code": result.returncode}


def tool_identity(path: Path, role: str, args: tuple[str, ...], pre: dict[str, Any] | None = None) -> dict[str, Any]:
    before = pre or _tool_snapshot(path, role, args)
    after = _tool_snapshot(path, role, args)
    if before != after:
        raise RuntimeError(f"{role} identity drift")
    return {**after, "pre": before, "post": after, "pre_post_equal": True}


def run(command: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=RUN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode()
        if isinstance(stderr, str):
            stderr = stderr.encode()
        return {"returncode": 124, "stdout_sha256": sha_bytes(stdout), "stderr_sha256": sha_bytes(stderr), "stdout_bytes": len(stdout), "stderr_bytes": len(stderr)}
    # Keep diagnostics content-addressed but never persist compiler/runtime paths.
    return {
        "returncode": result.returncode,
        "stdout_sha256": sha_bytes(result.stdout.encode()),
        "stderr_sha256": sha_bytes(result.stderr.encode()),
        "stdout_bytes": len(result.stdout.encode()),
        "stderr_bytes": len(result.stderr.encode()),
    }


def execute(row: str, *, run_id: str, report_path: Path, run_root_path: Path, python: Path, cargo: Path, candidate_commit: str, candidate_tree: str, candidate_archive_sha256: str) -> dict[str, Any]:
    if row not in {"AS-02", "AS-03"}:
        raise ValueError("row must be AS-02 or AS-03")
    if len(candidate_commit) != 40 or len(candidate_tree) != 40 or len(candidate_archive_sha256) != 64 or any(c not in "0123456789abcdef" for c in candidate_commit + candidate_tree + candidate_archive_sha256):
        raise ValueError("candidate commit/tree/archive must be lowercase hexadecimal identities")
    report_target = report_path if report_path.is_absolute() else ROOT / report_path
    if report_target.exists():
        raise RuntimeError("report output must be create-new")
    checked_python = _regular_tool(python, "python")
    checked_cargo = _regular_tool(cargo, "cargo")
    rustc = _regular_tool(checked_cargo.with_name("rustc.exe"), "rustc")
    tool_pre = {
        "cargo": _tool_snapshot(checked_cargo, "cargo", ("--version",)),
        "rustc": _tool_snapshot(rustc, "rustc", ("--version",)),
        "python": _tool_snapshot(checked_python, "python", ("--version",)),
    }
    fresh_nonce = secrets.token_hex(32)
    run_root = _fresh_root(run_root_path, "run root")
    try:
        try:
            if not _outside(report_target.parent.resolve(strict=True), run_root):
                raise RuntimeError("report output must be outside run root")
        except OSError as error:
            raise RuntimeError("report output parent resolution failed closed") from error
        candidate_root = run_root / "candidate"
        upstream_root = run_root / "upstream"
        actual_tree = subprocess.check_output(["git", "-C", str(ROOT), "show", "-s", "--format=%T", candidate_commit], env=_git_env(), text=True, timeout=RUN_TIMEOUT_SECONDS).strip()
        if actual_tree != candidate_tree:
            raise RuntimeError("candidate commit/tree binding mismatch")
        actual_upstream_tree = subprocess.check_output(["git", "-C", str(UPSTREAM_ROOT), "show", "-s", "--format=%T", UPSTREAM_COMMIT], env=_git_env(), text=True, timeout=RUN_TIMEOUT_SECONDS).strip()
        if actual_upstream_tree != UPSTREAM_TREE:
            raise RuntimeError("upstream commit/tree binding mismatch")
        candidate_archive_sha = archive(ROOT, candidate_commit, candidate_root, run_root)
        if candidate_archive_sha != candidate_archive_sha256:
            raise RuntimeError("candidate archive SHA binding mismatch")
        upstream_archive_sha = archive(UPSTREAM_ROOT, UPSTREAM_COMMIT, upstream_root, run_root)
        target = run_root / "target"
        env = _build_env(candidate_root, target, rustc)
        binary_name = "sipi-agent-spice-fit-sparam-cascade.exe" if row == "AS-02" else "sipi-agent-spice-fit-yparam.exe"
        build = run([str(checked_cargo), "build", "--offline", "--manifest-path", str(candidate_root / "crates/sipi-agent-spice-direct/Cargo.toml"), "--release", "--locked", "--bin", binary_name.removesuffix(".exe")], candidate_root, env)
        binary = target / "release" / binary_name
        if build["returncode"] != 0 or not binary.is_file():
            raise RuntimeError("candidate archive build failed")
        input_path = run_root / "line.s2p"
        input_path.write_text(FIXTURE, encoding="ascii", newline="\n")
        if row == "AS-02":
            manifest = run_root / "cascade.json"
            manifest.write_text(json.dumps({"version": 1, "blocks": [{"name": "a", "touchstone": "line.s2p"}, {"name": "b", "touchstone": "line.s2p"}], "cascade": ["a", "b"]}), encoding="utf-8")
            args = list(AS02_ARGS)
            upstream_command = [str(checked_python), "-I", "-c", "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=['agent-spice','fit-sparam-cascade',*sys.argv[2:]];runpy.run_module('agent_spice.cli',run_name='__main__')", str(upstream_root / "src"), str(run_root / "cascade.json"), "--output-root", str(run_root / "upstream-out"), *args]
            candidate_command = [str(binary), str(manifest), "--output-root", str(run_root / "candidate-out"), *args]
            upstream_result = run(upstream_command, run_root, env)
            candidate_result = run(candidate_command, run_root, env)
            upstream_report = run_root / "upstream-out/cascade_report.json"
            candidate_report = run_root / "candidate-out/cascade_report.json"
            if not upstream_report.is_file() or not candidate_report.is_file():
                raise RuntimeError(f"AS-02 report missing upstream={upstream_result} candidate={candidate_result}")
            up = json.loads(upstream_report.read_text(encoding="utf-8")); cand = json.loads(candidate_report.read_text(encoding="utf-8"))
            metrics = {"upstream_cascade_mean_rms": up["cascade_mean_rms_error"], "candidate_cascade_mean_rms": cand["cascade_mean_rms_error"], "upstream_block_rms": [x["full_band_mean_rms_error"] for x in up["blocks"]], "candidate_block_rms": [x["gate"]["full_band_rms"] for x in cand["blocks"]], "upstream_snapshot": {"cascade_order": up.get("cascade_order"), "selected_scales": up.get("selected_scales"), "blocks": [{"name": x.get("name"), "selected_order": x.get("selected_order"), "pole_relocation_iterations": x.get("pole_relocation_iterations"), "scale": x.get("scale"), "full_band_mean_rms_error": x.get("full_band_mean_rms_error"), "priority_band_mean_rms_error": x.get("priority_band_mean_rms_error")} for x in up.get("blocks", [])]}, "candidate_snapshot": {"cascade_order": cand.get("cascade_order"), "selected_scales": cand.get("selected_scales"), "blocks": [{"name": x.get("name"), "selected_order": x.get("selected_order"), "pole_relocation_iterations": x.get("pole_relocation_iterations"), "scale": x.get("scale"), "gate": {"full_band_rms": x.get("gate", {}).get("full_band_rms"), "priority_band_rms": x.get("gate", {}).get("priority_band_rms"), "target_met": x.get("gate", {}).get("target_met")}} for x in cand.get("blocks", [])]}}
        else:
            args = list(AS03_ARGS)
            upstream_command = [str(checked_python), "-I", "-c", "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=['agent-spice','fit-yparam',*sys.argv[2:]];runpy.run_module('agent_spice.cli',run_name='__main__')", str(upstream_root / "src"), str(input_path), "--output", str(run_root / "upstream.y.sp"), "--report", str(run_root / "upstream.y.json"), *args]
            candidate_command = [str(binary), str(input_path), "--output", str(run_root / "candidate.y.sp"), "--report", str(run_root / "candidate.y.json"), *args]
            upstream_result = run(upstream_command, run_root, env)
            candidate_result = run(candidate_command, run_root, env)
            upstream_report = run_root / "upstream.y.json"
            candidate_report = run_root / "candidate.y.json"
            if not upstream_report.is_file() or not candidate_report.is_file():
                raise RuntimeError(f"AS-03 report missing upstream={upstream_result} candidate={candidate_result}")
            up = json.loads(upstream_report.read_text(encoding="utf-8")); cand = json.loads(candidate_report.read_text(encoding="utf-8"))
            metrics = {"upstream_y_rms_siemens": up["y_rms_siemens"], "candidate_y_rms_siemens": cand["y_rms_siemens"], "upstream_y_mean_rms_siemens": up["y_mean_rms_siemens"], "candidate_y_mean_rms_siemens": cand["y_mean_rms_siemens"], "upstream_snapshot": {key: up.get(key) for key in ("selected_order", "model_order", "pole_relocation_iterations", "target_met", "exact_delivery_gate") if key in up}, "candidate_snapshot": {key: cand.get(key) for key in ("selected_order", "model_order", "pole_relocation_iterations", "target_met", "exact_delivery_gate") if key in cand}}
        report = {"schema": "sipi.agent-spice-as-numeric-bound.v3", "workflow": row, "status": "completed_numeric_mismatch_open", "parity_claim": False, "numeric_parity": False, "run_id": run_id, "fresh_run_nonce": fresh_nonce, "runner": {"repo_relative_path": "tools/run_as_02_03_numeric_bound_v3.py", "sha256": sha(Path(__file__))}, "wrapper_policy": WRAPPER_POLICY, "custody": {"fresh_root": True, "create_new": True, "root_external_to_repository": True, "archive_links_rejected": True, "archive_overlay": False, "offline_build": True, "path_redacted": True}, "profile": profile_for(row, sha(input_path)), "candidate": {"commit": candidate_commit, "tree": candidate_tree, "archive_sha256": candidate_archive_sha}, "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "archive_sha256": upstream_archive_sha}, "build": {**build, "binary_sha256": sha(binary)}, "toolchain": {"cargo": tool_identity(checked_cargo, "cargo", ("--version",), tool_pre["cargo"]), "rustc": tool_identity(rustc, "rustc", ("--version",), tool_pre["rustc"]), "python": tool_identity(checked_python, "python", ("--version",), tool_pre["python"])}, "fixture": {"kind": FIXTURE_KIND, "generated_by_runner_constant": FIXTURE_GENERATED_BY, "sha256": sha(input_path)}, "fixture_sha256": sha(input_path), "execution": {"upstream": upstream_result, "candidate": candidate_result, "upstream_report_sha256": sha(upstream_report), "candidate_report_sha256": sha(candidate_report)}, "metrics": metrics, "non_claims": ["Numeric mismatch remains open.", "No parity or acceptance tolerance is claimed.", "No SI-channel S-parameter fitting is claimed.", "No product or release promotion is claimed."]}
        if has_absolute_payload(report):
            raise RuntimeError("report path disclosure")
        report_target.parent.mkdir(parents=True, exist_ok=True)
        with report_target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report
    finally:
        shutil.rmtree(run_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("row", choices=["AS-02", "AS-03"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, default=Path.home() / ".cargo/bin/cargo.exe")
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--candidate-archive-sha256", required=True)
    args = parser.parse_args()
    report = execute(args.row, run_id=args.run_id, report_path=args.report, run_root_path=args.run_root, python=args.python.resolve(), cargo=args.cargo.resolve(), candidate_commit=args.candidate_commit, candidate_tree=args.candidate_tree, candidate_archive_sha256=args.candidate_archive_sha256)
    print(json.dumps({"workflow": args.row, "status": report["status"], "report": args.report.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
