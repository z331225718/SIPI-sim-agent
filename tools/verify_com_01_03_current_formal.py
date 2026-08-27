"""Verify the immutable COM-01/COM-03 current-candidate formal bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PREP_COMMIT = "e74e10d2933b1ddbc73f7da1a7785ca15ba49e09"
PREP_TREE = "2e49b25641439d29110747edde157eb232d1250c"
GATE_SCHEMA = "sipi.com-01-03.current-formal-gate.v1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_GIT_BYTES = 8 * 1024 * 1024

PREP_TOOLS = {
    "tools/run_com_01_current_candidate.py": (83652, "199080030f9d07bdd8d9c8b087268c25e12c8caf2d4bc0f61be2fc1540de68bb", "e64e3dbd5d98e00a7136dc2e533a374d0c9e0077"),
    "tools/aggregate_com_01_current_candidate.py": (11321, "678256aa893d1d03a6e952dbdee62d5dd787849cea5107ce766ca59ac82dff15", "d07fbd804d8348042fb422a9b0376eec0c11693a"),
    "tools/verify_com_01_current_candidate.py": (21938, "1e3fc34efa93844a9115bb78316b49bf5f8c8eae30249c346aeee60d6e15903d", "f9698adc980704bc7ff6cb250fc6928189cdcde7"),
    "tools/test_verify_com_01_current_candidate.py": (23658, "69ad3d83a35e70aaeaa4f8031afbab1c8e512301472baf310c89640cfcf39128", "99bc4c4296a52fde9ba261ee36792c6d26ad89d2"),
    "tools/run_com_03_current_candidate.py": (39038, "284695fe20609cff4276e7edd9017af8b4f3996d94e3f256e6bc43d05a81de3e", "b85b5a1f109cc4f0001737de532cfb49bd6c1ff9"),
    "tools/aggregate_com_03_current_candidate.py": (13476, "d777685ce4d6b254bf0311c699f29e71d0cdd1cc41c827a7f678a6486ae566d3", "20996d205dcb38d1ab2d2bf4e9f52f36c42921a5"),
    "tools/verify_com_03_current_candidate.py": (21434, "26bc004ad6b871e5b7919123fb6fc92aef677199ea4dc6f83c697a85454e7a5a", "86f2740bb3296cd0209d66408d283dc379b33977"),
    "tools/test_verify_com_03_current_candidate.py": (8667, "445ccfadcb24073b579e74d6d964b6d529b131db599615564e83159563adcc90", "23f30f8d1f71c7297f814b3de87163ef19b7181f"),
}

GATE_FILES = {
    "verifier": "tools/verify_com_01_03_current_formal.py",
    "mutation_tests": "tools/test_verify_com_01_03_current_formal.py",
}

ROWS = {
    "COM-01": {
        "manifest": "docs/baselines/com-01-current-candidate-replay.v1.yaml",
        "normalized_sha256": "ce4d47e690786e9f319a325e0b78d9457cb485f0d112c48cd3c51ecb6fee32a9",
        "root_keys": {"schema", "status", "scope", "policy", "candidate", "upstream", "harness", "fixtures", "reports", "aggregate", "audit", "physical", "non_claims", "formal_verification_gate"},
        "harness_keys": {"commit", "tree", "runner", "runner_blob", "runner_sha256", "aggregate_runner", "aggregate_runner_blob", "aggregate_runner_sha256", "verifier_blob", "mutation_test_blob", "semantic_runner", "semantic_runner_blob", "semantic_runner_sha256", "scenario_count", "scenario_set_sha256", "archive_only_inputs", "same_crate_self_comparison", "no_s_fit", "channel_impulse_only"},
        "physical": ["tools/run_com_01_current_candidate.py", "tools/aggregate_com_01_current_candidate.py", "tools/verify_com_01_current_candidate.py", "tools/test_verify_com_01_current_candidate.py", "tools/run_com_01_direct_oracle.py", "crates/sipi-agent-com-direct/SOURCE-MAP-COM-01.md", "crates/sipi-agent-com-direct/NOTICE-AGENT-COM-MIT.md"],
        "reports": [
            ("docs/baselines/com-01-current-candidate-replay-run1.v1.json", 35122, "53415dcbf1d7eb45ca1c62fc8bdccd8ba8c14f014a08eba22a7057f575df00ee", "cde918c354b8c69033c5a4b1ae0700ecdd9e092efc742545f03900d6dad7390c", "0d29ba9ed7baf5753e6076d01de735d5076d9570eea006da1127e2e9f622c3e7"),
            ("docs/baselines/com-01-current-candidate-replay-run2.v1.json", 35122, "29d947762dc3dc04cea3aac08366f494dfa6faac1d277d2d2f9f8d47befe671d", "70c4a1c1187c17b0f350a5d00d45df83fb5f6b666908cf52bf3b411362ce7acf", "bda431695c2b0b09d91c07d1cab00d5dc6ba33aec750fba83100f6e1ad7a6889"),
        ],
        "aggregate": ("docs/baselines/com-01-current-candidate-replay.aggregate.v1.json", 18178, "07c1f59bb2bfa61c35c0ad1eaadfdd4077048db8d4ee09c9b5db4bb0f2118c78"),
        "audit": ("docs/baselines/audits/2026-08-27-com-01-current-candidate-replay.md", 2220, "7758810b2f72dc0cffebb57bad0b739ddd7985ebc800750a9b9f50b546a26b01"),
        "verifier": "tools/verify_com_01_current_candidate.py",
        "aggregate_tool": "tools/aggregate_com_01_current_candidate.py",
        "verify_result": {"schema": "sipi.com-01.current-candidate-replay.v1", "status": "scoped_current_candidate_observed", "scenario_count": 14, "fresh_replays": 2},
    },
    "COM-03": {
        "manifest": "docs/baselines/com-03-current-candidate-replay.v1.yaml",
        "normalized_sha256": "99406a5e252e181b972540ffca0268e154a2ab38979ac2fc754560a79d81a659",
        "root_keys": {"schema", "status", "scope", "policy", "candidate", "upstream", "harness", "reports", "aggregate", "audit", "physical", "non_claims", "formal_verification_gate"},
        "harness_keys": {"commit", "tree", "runner", "runner_blob", "runner_sha256", "aggregate_runner", "aggregate_runner_blob", "aggregate_runner_sha256", "verifier_blob", "mutation_test_blob", "shared_com01_runner_blob", "shared_com01_runner_sha256", "semantic_runner", "semantic_runner_blob", "semantic_runner_sha256", "scenario_count", "scenario_set_sha256", "independent_payload_paths", "same_crate_self_comparison", "no_s_fit", "channel_impulse_only"},
        "physical": ["tools/run_com_01_current_candidate.py", "tools/run_com_03_current_candidate.py", "tools/aggregate_com_03_current_candidate.py", "tools/verify_com_03_current_candidate.py", "tools/test_verify_com_03_current_candidate.py", "tools/run_com_03_direct_oracle.py", "crates/sipi-agent-com-direct/SOURCE-MAP.md", "crates/sipi-agent-com-direct/NOTICE-AGENT-COM-MIT.md"],
        "reports": [
            ("docs/baselines/com-03-current-candidate-replay-run3.v1.json", 42129, "b2f42694211b7a6a614023627b54612407171fa6d6fbed058f95ec353b20573f", "6fb8522f1fc2c1b887bc7eb55596acff95103bbefe7d8c106e0dc33a64f673d5", "b3c953b07120695dc5db4d483c062022b71bc440e2842d5cdbf6a20e92ed4d7e"),
            ("docs/baselines/com-03-current-candidate-replay-run4.v1.json", 42129, "a16438887fb11bedcea9e6cd867b1d95b76a17b072690af1ca217c7e082d2d35", "3ff8757706459bd74e7613755fc9c77307d8d4d9d814231094290e177b3276fc", "8c74c0844364eb1e99fc592ce8d65340428cba8386b511a02019609af15957da"),
        ],
        "aggregate": ("docs/baselines/com-03-current-candidate-replay.aggregate.v1.json", 43030, "841647723f0f215f1d08d2e56d3ba1acaf612807c91d339b9516353f22762bf0"),
        "audit": ("docs/baselines/audits/2026-08-27-com-03-current-candidate-replay.md", 2247, "f024a2d4e78221b16aac3a35fc5a5cea3e778cc325b72bc411b14b038dd8972d"),
        "verifier": "tools/verify_com_03_current_candidate.py",
        "aggregate_tool": "tools/aggregate_com_03_current_candidate.py",
        "verify_result": {"schema": "sipi.com-03.current-candidate-replay.v1", "status": "scoped_current_candidate_observed", "scenario_count": 23, "fresh_replays": 2},
    },
}


class VerificationError(ValueError):
    """Raised when the formal graph is not exactly the admitted graph."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except OSError:
        return True


def safe_file(repo_root: Path, relative: str, label: str) -> Path:
    require(type(relative) is str and relative and "\\" not in relative and ":" not in relative, f"{label} path malformed")
    candidate = Path(relative)
    require(not candidate.is_absolute(), f"{label} path must be relative")
    parts = candidate.parts
    require(parts and all(part not in {"", ".", ".."} for part in parts), f"{label} path escapes root")
    root = repo_root.resolve(strict=True)
    raw = root.joinpath(*parts)
    current = raw
    while current != root:
        if current.exists() or current.is_symlink():
            require(not _is_reparse(current), f"{label} path contains symlink/reparse")
        current = current.parent
    try:
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError(f"{label} is missing") from error
    require(resolved != root and root in resolved.parents, f"{label} escaped repository")
    info = resolved.stat(follow_symlinks=False)
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not _is_reparse(resolved), f"{label} is not a single-link regular file")
    return resolved


def read_file(repo_root: Path, relative: str, label: str) -> bytes:
    path = safe_file(repo_root, relative, label)
    before = path.stat(follow_symlinks=False)
    require(0 < before.st_size <= MAX_FILE_BYTES, f"{label} size is outside budget")
    payload = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_nlink)
    require(identity(before) == identity(after) and len(payload) == before.st_size, f"{label} changed while reading")
    return payload


def check_raw(repo_root: Path, relative: str, size: int, digest: str, label: str) -> bytes:
    require(type(size) is int and size > 0 and type(digest) is str and HEX64.fullmatch(digest), f"{label} receipt malformed")
    payload = read_file(repo_root, relative, label)
    require((len(payload), sha256(payload)) == (size, digest), f"{label} raw binding drift")
    return payload


def check_head_bytes(repo_root: Path, relative: str, payload: bytes, label: str) -> None:
    require(git(repo_root, "show", f"HEAD:{relative}") == payload, f"{label} is not byte-identical to record HEAD")


def _bounded_process(command: list[str], cwd: Path, timeout: int = 30) -> tuple[int, bytes, bytes]:
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    streams = [bytearray(), bytearray()]
    overflow: list[BaseException] = []

    def drain(index: int, pipe: Any) -> None:
        try:
            while True:
                chunk = pipe.read(65536)
                if not chunk:
                    return
                streams[index].extend(chunk)
                if len(streams[index]) > MAX_GIT_BYTES:
                    overflow.append(VerificationError("subprocess output exceeded budget"))
                    process.kill()
                    return
        except BaseException as error:  # pragma: no cover - defensive pipe failure
            overflow.append(error)
            process.kill()

    threads = [threading.Thread(target=drain, args=(0, process.stdout)), threading.Thread(target=drain, args=(1, process.stderr))]
    for thread in threads:
        thread.start()
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait()
        raise VerificationError("subprocess timed out") from error
    finally:
        for thread in threads:
            thread.join(timeout=5)
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
    require(not overflow and all(not thread.is_alive() for thread in threads), "subprocess capture failed")
    return code, bytes(streams[0]), bytes(streams[1])


def git(repo_root: Path, *arguments: str, check: bool = True) -> bytes:
    code, stdout, stderr = _bounded_process(["git", "-c", "core.autocrlf=false", "-C", str(repo_root), *arguments], repo_root)
    if check:
        require(code == 0, f"git {' '.join(arguments)} failed: {stderr[-240:].decode('utf-8', errors='replace')}")
    return stdout if code == 0 else b""


def git_text(repo_root: Path, *arguments: str) -> str:
    value = git(repo_root, *arguments).decode("ascii").strip()
    require(value and "\n" not in value, f"git {' '.join(arguments)} output malformed")
    return value


class UniqueLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def _unique_mapping(loader: UniqueLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        require(key not in result, f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_manifest(repo_root: Path, relative: str) -> dict[str, Any]:
    payload = read_file(repo_root, relative, relative)
    check_head_bytes(repo_root, relative, payload, relative)
    try:
        value = yaml.load(payload.decode("utf-8"), Loader=UniqueLoader)
    except (UnicodeError, yaml.YAMLError) as error:
        raise VerificationError(f"{relative} is not valid YAML") from error
    require(type(value) is dict, f"{relative} root type drift")
    return value


def normalized_manifest_sha256(document: dict[str, Any]) -> str:
    value = dict(document)
    value.pop("formal_verification_gate", None)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return sha256(payload)


def validate_prep(repo_root: Path) -> None:
    require(git_text(repo_root, "rev-parse", f"{PREP_COMMIT}^{{commit}}") == PREP_COMMIT, "prep commit drift")
    require(git_text(repo_root, "rev-parse", f"{PREP_COMMIT}^{{tree}}") == PREP_TREE, "prep tree drift")
    for relative, (size, digest, blob) in PREP_TOOLS.items():
        current = check_raw(repo_root, relative, size, digest, f"prep tool {relative}")
        require(git_text(repo_root, "rev-parse", f"{PREP_COMMIT}:{relative}") == blob, f"prep blob drift: {relative}")
        committed = git(repo_root, "show", f"{PREP_COMMIT}:{relative}")
        require(committed == current, f"prep committed/current bytes drift: {relative}")
        check_head_bytes(repo_root, relative, current, f"prep tool {relative}")


def _commit_shape(repo_root: Path, commit: str) -> tuple[str, list[str]]:
    parents = git(repo_root, "rev-list", "--parents", "-n", "1", commit).decode("ascii").strip().split()
    require(parents == [commit, PREP_COMMIT], "formal gate parent/prep relation drift")
    changes = git(repo_root, "diff-tree", "--no-commit-id", "--no-renames", "--name-status", "-r", commit).decode("utf-8").splitlines()
    expected = [f"A\t{path}" for path in GATE_FILES.values()]
    require(sorted(changes) == sorted(expected), "formal gate must first introduce only the two gate tools")
    for relative in required_bundle_paths():
        code, _, _ = _bounded_process(["git", "-C", str(repo_root), "cat-file", "-e", f"{commit}:{relative}"], repo_root)
        require(code != 0, "formal gate commit contains a formal artifact")
    return parents[0], changes


def validate_stage1_gate(repo_root: Path) -> str:
    head = git_text(repo_root, "rev-parse", "HEAD")
    _commit_shape(repo_root, head)
    for relative in GATE_FILES.values():
        current = read_file(repo_root, relative, f"stage1 gate {relative}")
        require(git(repo_root, "show", f"{head}:{relative}") == current, f"stage1 gate source drift: {relative}")
    return head


def validate_gate(repo_root: Path, gate: Any) -> None:
    require(type(gate) is dict and set(gate) == {"schema", "commit", "tree", "files"}, "formal gate schema drift")
    require(gate["schema"] == GATE_SCHEMA and type(gate["commit"]) is str and HEX40.fullmatch(gate["commit"]) and type(gate["tree"]) is str and HEX40.fullmatch(gate["tree"]), "formal gate identity malformed")
    require(type(gate["files"]) is dict and set(gate["files"]) == set(GATE_FILES), "formal gate file role drift")
    commit = gate["commit"]
    head = git_text(repo_root, "rev-parse", "HEAD")
    require(commit != head, "record HEAD must be a strict gate descendant")
    code, _, _ = _bounded_process(["git", "-C", str(repo_root), "merge-base", "--is-ancestor", commit, head], repo_root)
    require(code == 0, "formal gate is not an ancestor of record HEAD")
    require(git_text(repo_root, "rev-parse", f"{commit}^{{tree}}") == gate["tree"], "formal gate tree drift")
    _commit_shape(repo_root, commit)
    for role, relative in GATE_FILES.items():
        receipt = gate["files"][role]
        require(type(receipt) is dict and set(receipt) == {"path", "bytes", "sha256", "git_blob_sha1"}, f"formal gate {role} receipt shape drift")
        require(receipt["path"] == relative and type(receipt["bytes"]) is int and receipt["bytes"] > 0 and type(receipt["sha256"]) is str and HEX64.fullmatch(receipt["sha256"]) and type(receipt["git_blob_sha1"]) is str and HEX40.fullmatch(receipt["git_blob_sha1"]), f"formal gate {role} receipt malformed")
        current = check_raw(repo_root, relative, receipt["bytes"], receipt["sha256"], f"formal gate {role}")
        require(git_text(repo_root, "rev-parse", f"{commit}:{relative}") == receipt["git_blob_sha1"], f"formal gate {role} blob drift")
        require(git(repo_root, "show", f"{commit}:{relative}") == current, f"formal gate {role} committed/current source drift")


def validate_row(repo_root: Path, row_name: str, row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    document = load_manifest(repo_root, row["manifest"])
    require(set(document) == row["root_keys"], f"{row_name} manifest root set drift")
    require(normalized_manifest_sha256(document) == row["normalized_sha256"], f"{row_name} normalized manifest drift")
    require(type(document.get("harness")) is dict and set(document["harness"]) == row["harness_keys"], f"{row_name} harness set drift")
    require(document["harness"].get("commit") == PREP_COMMIT and document["harness"].get("tree") == PREP_TREE, f"{row_name} prep identity drift")
    physical = document.get("physical")
    require(type(physical) is list and [item.get("path") for item in physical if type(item) is dict] == row["physical"], f"{row_name} physical path/order drift")
    require(all(type(item) is dict and set(item) == {"path", "sha256"} for item in physical), f"{row_name} physical shape drift")

    reports = []
    expected_bindings = []
    for relative, size, digest, run_id, nonce in row["reports"]:
        payload = check_raw(repo_root, relative, size, digest, f"{row_name} report")
        check_head_bytes(repo_root, relative, payload, f"{row_name} report")
        try:
            report = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise VerificationError(f"{row_name} report JSON drift") from error
        require(type(report) is dict and report.get("run_id") == run_id and report.get("nonce") == nonce, f"{row_name} report replay identity drift")
        reports.append(report)
        expected_bindings.append({"path": relative, "sha256": digest, "run_id": run_id, "nonce": nonce})
    require(document.get("reports") == expected_bindings, f"{row_name} manifest report bindings drift")

    aggregate_path, aggregate_size, aggregate_sha = row["aggregate"]
    aggregate_payload = check_raw(repo_root, aggregate_path, aggregate_size, aggregate_sha, f"{row_name} aggregate")
    check_head_bytes(repo_root, aggregate_path, aggregate_payload, f"{row_name} aggregate")
    require(document.get("aggregate") == {"path": aggregate_path, "sha256": aggregate_sha}, f"{row_name} aggregate binding drift")
    audit_path, audit_size, audit_sha = row["audit"]
    audit_payload = check_raw(repo_root, audit_path, audit_size, audit_sha, f"{row_name} audit")
    check_head_bytes(repo_root, audit_path, audit_payload, f"{row_name} audit")
    require(document.get("audit") == {"path": audit_path, "sha256": audit_sha}, f"{row_name} audit binding drift")

    verifier_path = safe_file(repo_root, row["verifier"], f"{row_name} verifier")
    manifest_path = safe_file(repo_root, row["manifest"], f"{row_name} manifest")
    code, stdout, stderr = _bounded_process(
        [sys.executable, str(verifier_path), "--manifest", str(manifest_path)],
        repo_root,
    )
    require(code == 0, f"{row_name} original verifier failed: {stderr[-240:].decode('utf-8', errors='replace')}")
    try:
        verified = json.loads(stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{row_name} original verifier output drift") from error
    require(verified == row["verify_result"], f"{row_name} original verifier result drift")

    aggregate_tool = safe_file(repo_root, row["aggregate_tool"], f"{row_name} aggregate tool")
    with tempfile.TemporaryDirectory(prefix=f"sipi-{row_name.lower()}-formal-aggregate-") as directory:
        output = Path(directory) / "aggregate.json"
        code, _, stderr = _bounded_process(
            [
                sys.executable,
                str(aggregate_tool),
                "--first",
                str(safe_file(repo_root, row["reports"][0][0], f"{row_name} report 1")),
                "--second",
                str(safe_file(repo_root, row["reports"][1][0], f"{row_name} report 2")),
                "--output",
                str(output),
                "--candidate-repo",
                str(repo_root),
            ],
            repo_root,
        )
        require(code == 0, f"{row_name} aggregate replay failed: {stderr[-240:].decode('utf-8', errors='replace')}")
        require(output.is_file() and output.read_bytes() == aggregate_payload, f"{row_name} aggregate mechanical replay drift")
    return document, reports[0]


def required_bundle_paths() -> list[str]:
    paths = []
    for row in ROWS.values():
        paths.extend([row["manifest"], *(item[0] for item in row["reports"]), row["aggregate"][0], row["audit"][0]])
    return paths


def verify(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve(strict=True)
    paths = required_bundle_paths()
    present = [relative for relative in paths if repo_root.joinpath(*Path(relative).parts).is_file()]
    if not present:
        validate_prep(repo_root)
        gate_commit = validate_stage1_gate(repo_root)
        return {"schema": GATE_SCHEMA, "status": "skipped_formal_artifacts_absent", "formal": False, "missing": paths, "gate_commit": gate_commit}
    require(len(present) == len(paths), "partial formal bundle is forbidden")
    validate_prep(repo_root)
    documents = {}
    all_ids: list[str] = []
    all_nonces: list[str] = []
    for row_name, row in ROWS.items():
        documents[row_name], _ = validate_row(repo_root, row_name, row)
        all_ids.extend(item[3] for item in row["reports"])
        all_nonces.extend(item[4] for item in row["reports"])
    require(len(set(all_ids)) == 4 and len(set(all_nonces)) == 4 and not set(all_ids) & set(all_nonces), "global replay identity freshness drift")
    gates = [documents[name].get("formal_verification_gate") for name in ROWS]
    require(gates[0] == gates[1], "formal gate blocks differ between rows")
    validate_gate(repo_root, gates[0])
    return {"schema": GATE_SCHEMA, "status": "valid", "formal": True, "rows": {"COM-01": 2, "COM-03": 2}, "prep_commit": PREP_COMMIT, "gate_commit": gates[0]["commit"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = verify(repo_root=args.repo_root)
    except (OSError, VerificationError, yaml.YAMLError) as error:
        print(json.dumps({"schema": GATE_SCHEMA, "status": "blocked", "formal": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
