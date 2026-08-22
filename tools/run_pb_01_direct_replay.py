"""Prepare or run the two-stage PB-01 legacy-sim oracle boundary.

Stage one materializes the pinned candidate and upstream commits from immutable
Git archives and snapshots source identities before any build/runtime writes.
Stage two optionally runs the pinned external ``pybert sim`` oracle and a
caller-supplied Rust candidate with the same caller-owned configuration bytes.
The runner inventories only the legacy result file; it never decodes or
stores PyBert's pickle payload in a committed report.  A successful stage two
observation is deliberately ``observed_open`` rather than numerical parity:
the Rust legacy-config projection and a result comparator are not yet bound.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PureWindowsPath, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM = Path(r"C:\Users\z3312\code\Py-bert-agent")
EXPECTED_UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
EXPECTED_UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
UPSTREAM_FACT_PATHS = (
    "LICENSE",
    "uv.lock",
    "src/pybert/cli.py",
    "src/pybert/configuration.py",
    "src/pybert/pybert.py",
    "src/pybert/results.py",
    "src/pybert/engine/python_backend.py",
)
CRATE_RELATIVE = Path("crates/sipi-pybert-direct")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def _commit_tree(repo: Path, commit: str) -> tuple[str, str]:
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    return resolved, tree


def _extract_archive(payload: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escapes destination: {member.name}")
            if member.issym() or member.islnk():
                raise RuntimeError(f"archive links are not accepted: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(f"archive member kind is not accepted: {member.name}")
            archive.extract(member, destination)


def _materialize_git_archive(repo: Path, commit: str, destination: Path) -> dict[str, str]:
    payload = bytes(_git(repo, "archive", "--format=tar", commit, raw=True))
    _extract_archive(payload, destination)
    resolved, tree = _commit_tree(repo, commit)
    return {"commit": resolved, "tree": tree, "archive_sha256": _sha256(payload)}


def _file_digest(path: Path) -> str | None:
    try:
        return _sha256(path.read_bytes())
    except OSError:
        return None


def _iter_files(root: Path, prefixes: tuple[str, ...]):
    for prefix in prefixes:
        path = root / prefix
        if path.is_file():
            yield prefix.replace("\\", "/"), path
            continue
        if not path.is_dir():
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file() and not child.is_symlink():
                yield child.relative_to(root).as_posix(), child


def _inventory(root: Path, prefixes: tuple[str, ...]) -> dict[str, Any]:
    entries = [
        {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path.read_bytes())}
        for relative, path in _iter_files(root, prefixes)
    ]
    entries.sort(key=lambda item: item["path"])
    return {"entries": entries, "sha256": _sha256(_canonical(entries))}


def _source_facts(root: Path, commit_info: dict[str, str], prefixes: tuple[str, ...]) -> dict[str, Any]:
    return {**commit_info, "inventory": _inventory(root, prefixes)}


def _upstream_facts(root: Path, commit_info: dict[str, str]) -> dict[str, Any]:
    return {
        **commit_info,
        "inventory": _inventory(root, UPSTREAM_FACT_PATHS),
        "license_sha256": _file_digest(root / "LICENSE"),
        "uv_lock_sha256": _file_digest(root / "uv.lock"),
    }


def _safe_relative(value: str | Path) -> Path:
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise RuntimeError("relative path must be non-empty")
    host = Path(raw)
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if (
        host.is_absolute()
        or bool(host.anchor)
        or posix.is_absolute()
        or bool(posix.anchor)
        or windows.is_absolute()
        or bool(windows.anchor)
        or bool(windows.drive)
        or raw.startswith(("/", "\\"))
    ):
        raise RuntimeError("path must be repository-relative")
    pieces = [piece for piece in re.split(r"[\\/]+", raw) if piece not in ("", ".")]
    if not pieces or any(piece == ".." for piece in pieces):
        raise RuntimeError("path traversal is not accepted")
    return Path(*pieces)


def _runtime_identity(value: str, role: str, version_args: tuple[str, ...]) -> tuple[dict[str, Any], Path]:
    literal = Path(value)
    resolved = literal.resolve() if literal.is_file() else shutil.which(value)
    if resolved is None:
        raise RuntimeError(f"{role} executable cannot be resolved")
    executable = Path(resolved).resolve()
    file_sha256 = _file_digest(executable)
    if file_sha256 is None or HEX64.fullmatch(file_sha256) is None:
        raise RuntimeError(f"{role} executable digest unavailable")
    version = subprocess.run(
        [str(executable), *version_args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if version.returncode != 0:
        raise RuntimeError(f"{role} version command returned nonzero")
    version_sha256 = _sha256(version.stdout + b"\x00" + version.stderr)
    return (
        {
            "role": role,
            "executable": executable.name,
            "path_redacted": True,
            "file_sha256": file_sha256,
            "version_exit_code": version.returncode,
            "version_output_sha256": version_sha256,
        },
        executable,
    )


def _copy_input(source: Path, destination_root: Path) -> dict[str, Any]:
    payload = source.read_bytes()
    extension = source.suffix
    if extension not in {".yaml", ".yml", ".pybert_cfg"}:
        raise RuntimeError("PB-01 config must end in .yaml, .yml, or .pybert_cfg")
    name = f"oracle-input{extension}"
    target = destination_root / name
    target.write_bytes(payload)
    return {"path": "external-input", "bytes": len(payload), "sha256": _sha256(payload), "extension": extension}


def _artifact_summary(root: Path, relative: str) -> dict[str, Any]:
    path = root / _safe_relative(relative)
    try:
        metadata = path.stat()
    except OSError:
        return {"present": False, "path": relative}
    if not path.is_file():
        return {"present": False, "path": relative, "kind": "not_regular_file"}
    return {"present": True, "path": relative, "bytes": metadata.st_size, "sha256": _sha256(path.read_bytes())}


def _process_summary(process: subprocess.CompletedProcess[bytes], root: Path, result_relative: str) -> dict[str, Any]:
    return {
        "exit_code": process.returncode,
        "stdout_sha256": _sha256(process.stdout),
        "stderr_sha256": _sha256(process.stderr),
        "artifact": _artifact_summary(root, result_relative),
    }


def _run_one(
    *,
    candidate_root: Path,
    upstream_root: Path,
    candidate_executable: Path | None,
    uv: Path,
    timeout: int,
) -> dict[str, Any]:
    candidate_input = _copy_input(_INPUT_SOURCE, candidate_root)
    upstream_input = _copy_input(_INPUT_SOURCE, upstream_root)
    candidate_result = "candidate-result.pybert_data"
    oracle_result = "oracle-result.pybert_data"
    oracle = subprocess.run(
        [
            str(uv),
            "run",
            "--project",
            str(upstream_root),
            "--frozen",
            "pybert",
            "sim",
            "oracle-input" + upstream_input["extension"],
            "--results",
            oracle_result,
        ],
        cwd=upstream_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if candidate_executable is None:
        candidate = {"skipped": True, "reason": "candidate_executable_not_supplied"}
    else:
        process = subprocess.run(
            [
                str(candidate_executable),
                "sim",
                "oracle-input" + candidate_input["extension"],
                "--results",
                candidate_result,
            ],
            cwd=candidate_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        candidate = _process_summary(process, candidate_root, candidate_result)
    return {
        "status": "observed_open",
        "oracle": _process_summary(oracle, upstream_root, oracle_result),
        "candidate": candidate,
        "artifact_contract": {
            "oracle_result_relative": oracle_result,
            "candidate_result_relative": candidate_result,
            "result_codec": "legacy_pybert_data_pickle_opaque",
            "numeric_payload_decoded": False,
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    global _INPUT_SOURCE
    _INPUT_SOURCE = args.config.resolve()
    if not _INPUT_SOURCE.is_file():
        raise RuntimeError("PB-01 config must be a regular file")
    if _INPUT_SOURCE.suffix not in {".yaml", ".yml", ".pybert_cfg"}:
        raise RuntimeError("PB-01 config must end in .yaml, .yml, or .pybert_cfg")
    candidate_repo = args.candidate_repo.resolve()
    upstream_repo = args.upstream_repo.resolve()
    candidate_commit, candidate_tree = _commit_tree(candidate_repo, args.candidate_commit)
    upstream_commit, upstream_tree = _commit_tree(upstream_repo, args.upstream_commit)
    if (upstream_commit, upstream_tree) != (EXPECTED_UPSTREAM_COMMIT, EXPECTED_UPSTREAM_TREE):
        raise RuntimeError("upstream commit/tree is not the pinned PB-01 source")
    candidate_identity, candidate_executable = (None, None)
    if args.candidate_executable:
        candidate_identity, candidate_executable = _runtime_identity(
            str(args.candidate_executable), "candidate", ("--version",)
        )
    uv_identity, uv_executable = _runtime_identity(str(args.uv), "uv", ("--version",))
    work_parent = args.work_root.resolve() if args.work_root else Path(tempfile.mkdtemp(prefix="sipi-pb-01-replay-"))
    work_parent.mkdir(parents=True, exist_ok=True)
    run_root = work_parent / args.run_id
    if run_root.exists():
        raise RuntimeError(f"run root already exists: {run_root}")
    run_root.mkdir()
    candidate_root = run_root / "candidate"
    upstream_root = run_root / "upstream"
    candidate_info = _materialize_git_archive(candidate_repo, candidate_commit, candidate_root)
    upstream_info = _materialize_git_archive(upstream_repo, upstream_commit, upstream_root)
    candidate_facts = _source_facts(candidate_root, candidate_info, (str(CRATE_RELATIVE),))
    upstream_facts = _upstream_facts(upstream_root, upstream_info)
    config_facts = {"path": "external-input", "bytes": _INPUT_SOURCE.stat().st_size, "sha256": _sha256(_INPUT_SOURCE.read_bytes()), "extension": _INPUT_SOURCE.suffix}
    replay = None
    if args.execute:
        replay = _run_one(
            candidate_root=candidate_root,
            upstream_root=upstream_root,
            candidate_executable=candidate_executable,
            uv=uv_executable,
            timeout=args.timeout_seconds,
        )
    report = {
        "schema": "sipi.pb-01-direct-replay.v1",
        "status": "observed_open" if replay is not None else "prepared_open",
        "run_id": args.run_id,
        "fresh_run_nonce": secrets.token_hex(32),
        "source_mode": "git_archive_at_immutable_commit",
        "stage_1_source_preparation": {"candidate": candidate_facts, "upstream": upstream_facts, "config": config_facts},
        "stage_2_oracle_replay": replay or {"status": "not_run", "reason": "prepare_only"},
        "runtime": {"uv": uv_identity, "candidate": candidate_identity},
        "non_claims": [
            "This report does not prove PB-01 numeric parity or PyBertData pickle compatibility.",
            "The Rust legacy-config projection and result comparator remain open.",
            "SIPI wrapper behavior is not upstream parity and no pickle payload is decoded or committed.",
            "This report is not a license decision, product admission, release approval, or source redistribution authorization.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        stream.write("\n")
    if not args.keep_work and args.work_root is None:
        shutil.rmtree(work_parent, ignore_errors=True)
    return report


_INPUT_SOURCE = Path(".")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--upstream-commit", default=EXPECTED_UPSTREAM_COMMIT)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--candidate-executable", type=Path)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=__import__("sys").stderr)
        return 2
    print(json.dumps({"status": report["status"], "report": str(args.report)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
