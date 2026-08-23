"""Run one immutable AS-02..AS-06 preparation replay.

The direct leaf is always executed from a clean candidate Git archive.  This
runner is deliberately an observation harness: it records external-runtime
blockers and never promotes numerical parity.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_COMMIT = "64b783f66d7e986d0975be5ac3946b453b15c4ed"
CANDIDATE_TREE = "0e11721f2bb5b564002820cc7a5aaab45e30ba3b"
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
UPSTREAM_ROOT = Path(r"C:\Users\z3312\code\agent-spice")
TIMEOUT_SECONDS = 120


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE).stdout


def archive(repo: Path, revision: str, destination: Path) -> str:
    payload = git(repo, "archive", "--format=tar", revision)
    destination.mkdir()
    with tarfile.open(fileobj=__import__("io").BytesIO(payload), mode="r:") as tar:
        tar.extractall(destination)
    return sha(payload)


def tool_identity(path: Path, role: str, args: tuple[str, ...]) -> dict[str, Any]:
    result = subprocess.run([str(path), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {"role": role, "executable": path.name, "path_redacted": True, "file_sha256": sha(path.read_bytes()), "version_exit_code": result.returncode, "version_output_sha256": sha(result.stdout + b"\0" + result.stderr)}


def load_preparation_helper(candidate_root: Path):
    # The case generator is part of the candidate archive.  Loading the
    # working-tree helper would make a clean leaf replay depend on an
    # unbound sibling even when the bytes happen to match.
    path = candidate_root / "tools" / "run_as_remaining.py"
    spec = importlib.util.spec_from_file_location("as_remaining_preparation_helper", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("preparation helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def hash_tree(root: Path, *, inputs_only: bool = False) -> tuple[str, list[str]]:
    digest = hashlib.sha256()
    files: list[str] = []
    tokens = {str(root).encode(), str(root).replace("\\", "/").encode(), str(root).replace("\\", "\\\\").encode()}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if inputs_only and "/out/" in f"/{relative}/":
            continue
        data = path.read_bytes()
        for token in tokens:
            data = data.replace(token, b"<RUN_ROOT>")
        digest.update(relative.encode() + b"\0" + data)
        files.append(relative)
    return digest.hexdigest(), files


def scrub(value: str, roots: tuple[Path, ...]) -> str:
    result = value
    for root in roots:
        result = result.replace(str(root), "<RUN_ROOT>")
        result = result.replace(str(root).replace("\\", "/"), "<RUN_ROOT>")
    return result


def replay(helper: Any, row: str, candidate_root: Path, run_root: Path) -> dict[str, Any]:
    cases = []
    cases_root = run_root / "cases"
    cases_root.mkdir(parents=True)
    for case_id in helper.CORPUS[row]:
        case_root = cases_root / case_id
        case_root.mkdir(parents=True)
        args, binary, expected = helper._prepare_case(row, case_id, case_root)
        command = [shutil.which("cargo") or str(Path.home() / ".cargo" / "bin" / "cargo.exe"), "run", "--quiet", "--manifest-path", str(candidate_root / "crates/sipi-agent-spice-direct/Cargo.toml"), "--bin", binary, "--"] + args
        try:
            result = subprocess.run(command, cwd=candidate_root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS, check=False)
            code, stdout, stderr = result.returncode, result.stdout[-4096:], result.stderr[-4096:]
        except subprocess.TimeoutExpired as error:
            code, stdout, stderr = 124, str(error.stdout or ""), str(error.stderr or "")
        cases.append({"case": case_id, "binary": binary, "expected_returncode": expected, "returncode": code, "expected_result": code == expected, "stdout": scrub(stdout, (run_root, candidate_root)), "stderr": scrub(stderr, (run_root, candidate_root))})
    tree, files = hash_tree(run_root)
    inputs, input_files = hash_tree(run_root, inputs_only=True)
    return {"cases": cases, "corpus_expected": all(item["expected_result"] for item in cases), "tree_sha256": tree, "input_tree_sha256": inputs, "files": files, "input_files": input_files}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("row", choices=["AS-02", "AS-03", "AS-04", "AS-05", "AS-06"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cargo = Path(shutil.which("cargo") or Path.home() / ".cargo" / "bin" / "cargo.exe").resolve()
    rustc = cargo.with_name("rustc.exe") if cargo.with_name("rustc.exe").is_file() else Path(shutil.which("rustc") or "rustc").resolve()
    python = Path(sys.executable).resolve()
    with tempfile.TemporaryDirectory(prefix=f"sipi-{args.row.lower()}-bound-") as temporary:
        root = Path(temporary)
        candidate_root = root / "candidate"
        candidate_archive_sha = archive(ROOT, CANDIDATE_COMMIT, candidate_root)
        helper = load_preparation_helper(candidate_root)
        upstream_archive_sha = sha(git(UPSTREAM_ROOT, "archive", "--format=tar", UPSTREAM_COMMIT))
        with tempfile.TemporaryDirectory(prefix=f"sipi-{args.row.lower()}-run-") as run_temp:
            run = replay(helper, args.row, candidate_root, Path(run_temp))
        binary = candidate_root / "target" / "debug" / ("sipi-agent-spice-" + {"AS-02": "fit-sparam-cascade", "AS-03": "fit-yparam", "AS-04": "tune-yparam-tran", "AS-05": "run-hspice", "AS-06": "run-rfm"}[args.row] + ".exe")
        payload = {
            "schema": f"sipi.agent-spice-{args.row.lower()}-bound-replay.v2",
            "status": "completed_external_blocker_open" if args.row in {"AS-04", "AS-05", "AS-06"} else "completed_portable_observation_open",
            "run_id": args.run_id,
            "fresh_run_nonce": sha(os.urandom(32)),
            "source_mode": "candidate_and_upstream_git_archive_at_immutable_commit",
            "candidate": {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive_sha256": candidate_archive_sha},
            "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "archive_sha256": upstream_archive_sha},
            "runner": {"path": "tools/run_as_remaining_bound.py", "sha256": sha((ROOT / "tools/run_as_remaining_bound.py").read_bytes())},
            "helper": {"path": "tools/run_as_remaining.py", "sha256": sha((candidate_root / "tools/run_as_remaining.py").read_bytes())},
            "toolchain": {"cargo": tool_identity(cargo, "cargo", ("--version",)), "rustc": tool_identity(rustc, "rustc", ("--version",)), "python": tool_identity(python, "python", ("--version",))},
            "corpus": helper.CORPUS[args.row],
            "replay": run,
            "parity_claim": False,
            "numeric_parity": False,
            "acceptance_tolerance": None,
            "external_runtime_blocked": args.row in {"AS-04", "AS-05", "AS-06"},
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps({"run_id": args.run_id, "sha256": sha(args.output.read_bytes()), "corpus_expected": run["corpus_expected"]}, sort_keys=True))
    return 0 if run["corpus_expected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
