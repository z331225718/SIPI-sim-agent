"""Verify the AS-03 formal-tool gate and future immutable evidence bundle."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_as_03_power_wave_solve_replay as replay
import verify_as_03_power_wave_solve_replay as stage1_verify


STAGE1_PREP_COMMIT = "e3b1d2dc482be64bff8a3f69f1fdf03eb0792d26"
STAGE1_PREP_TREE = "115cf9755bfd988bc4f72fd2a3123229d403669c"
STAGE1_PREP_PARENT = "4042f0d9fdd0846e20ea95e8da7752812a4eea45"
ORIGINAL_GATE_COMMIT = "743c57d8d612643df7e116c6ee04c950cb370ff1"
ORIGINAL_GATE_TREE = "c716591a0db27030c06a3adcf8feb8d7dd96ce83"
ORIGINAL_GATE_PARENT = "6a9b2cbe96eb51b4e406cb94be9ef11a3a487944"
FORMAL_GATE_PARENT = ORIGINAL_GATE_COMMIT
FORMAL_GATE_PATHS = (
    "tools/test_verify_as_03_power_wave_solve_replay_formal.py",
    "tools/verify_as_03_power_wave_solve_replay_formal.py",
)
REPORT_PATHS = (
    "docs/baselines/as-03-power-wave-solve-replay-run-01.v1.json",
    "docs/baselines/as-03-power-wave-solve-replay-run-02.v1.json",
)
AGGREGATE_PATH = "docs/baselines/as-03-power-wave-solve-replay-aggregate.v1.json"
MANIFEST_PATH = "docs/baselines/as-03-power-wave-solve-replay.v1.yaml"
AUDIT_PATH = "docs/baselines/audits/2026-08-27-as-03-power-wave-solve-replay.md"
FORMAL_ARTIFACT_PATHS = (*REPORT_PATHS, AGGREGATE_PATH, MANIFEST_PATH, AUDIT_PATH)
AS_LOCKED_PATHS = (
    *replay.PREP_PATHS,
    "crates/sipi-agent-spice-direct/src/as03_fit_yparam.rs",
    "crates/sipi-agent-spice-direct/NOTICE-SCIKIT-RF-AS-03-POWER-WAVE.txt",
    "docs/baselines/as-03-power-wave-solve-source-map.v1.yaml",
)
AUDIT_PREFIX = b"<!-- sipi-as-03-power-wave-solve-formal-binding-v1:"
AUDIT_MARKERS = (
    b"Status: blocked_numeric_semantics",
    b"Scope: committed 4 real bits vs pinned scikit-rf leaf",
    b"Independent complex: diagnostic-only",
    b"Agent-Spice: provenance-only",
    b"No S-parameter fit",
    b"AS-05 Xyce/XDM: out of scope",
)
CLAIM_KEYS = {
    "numeric_parity",
    "acceptance_tolerance",
    "complete_complex_checkpoint",
    "agent_spice_yparam_path_execution",
    "s_parameter_fit",
    "as05_xyce_xdm",
    "release_acceptance",
}
MAX_FORMAL_FILE_BYTES = 16 * 1024 * 1024


class FormalError(RuntimeError):
    pass


class StrictLoader(yaml.SafeLoader):
    pass


def _strict_mapping(loader: StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as error:
            raise ConstructorError("while constructing a mapping", node.start_mark, "unhashable mapping key", key_node.start_mark) from error
        if duplicate:
            raise ConstructorError("while constructing a mapping", node.start_mark, f"duplicate key: {key!r}", key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _strict_mapping)


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise FormalError(f"{label} schema is not exact")
    return value


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if result.returncode != 0 or len(result.stdout) > MAX_FORMAL_FILE_BYTES:
        raise FormalError("Git query failed or exceeded its bound")
    return result.stdout if binary else result.stdout.decode("utf-8", "strict").strip()


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
    )
    if result.returncode not in (0, 1):
        raise FormalError("Git ancestry query failed")
    return result.returncode == 0


def _safe_relative(raw: str) -> str:
    return replay._safe_relative(raw).as_posix()


def _read(repo: Path, relative: str, maximum: int = MAX_FORMAL_FILE_BYTES) -> tuple[bytes, dict[str, Any]]:
    relative = _safe_relative(relative)
    try:
        root = replay._safe_directory(repo)
        path = root
        parts = Path(relative).parts
        for index, part in enumerate(parts):
            path /= part
            info = path.stat(follow_symlinks=False)
            if replay._is_reparse(path) or (index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode)):
                raise FormalError("formal file path component is unsafe")
        path = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise FormalError("formal file path custody invalid") from error
    if root not in path.parents:
        raise FormalError("formal file escaped repository")
    payload = replay._read_regular(path, maximum)
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise FormalError("formal file custody invalid")
    return payload, {"path": relative, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "nlink": 1, "path_redacted": True}


def _verify_stage1_prep(repo: Path) -> None:
    if str(_git(repo, "rev-parse", f"{STAGE1_PREP_COMMIT}^{{tree}}")) != STAGE1_PREP_TREE:
        raise FormalError("Stage1 prep tree drift")
    parents = str(_git(repo, "show", "-s", "--format=%P", STAGE1_PREP_COMMIT)).split()
    if parents != [STAGE1_PREP_PARENT]:
        raise FormalError("Stage1 prep parent drift")
    changed_raw = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", STAGE1_PREP_PARENT, STAGE1_PREP_COMMIT, binary=True)
    assert isinstance(changed_raw, bytes)
    changed = tuple(sorted(item.decode("utf-8", "strict") for item in changed_raw.split(b"\0") if item))
    if changed != tuple(sorted(replay.PREP_PATHS)):
        raise FormalError("Stage1 prep changed-path set drift")
    for relative in replay.PREP_PATHS:
        old = _git(repo, "ls-tree", "-z", STAGE1_PREP_PARENT, "--", relative, binary=True)
        current = _git(repo, "ls-tree", "-z", STAGE1_PREP_COMMIT, "--", relative, binary=True)
        assert isinstance(old, bytes) and isinstance(current, bytes)
        if old or not current:
            raise FormalError("Stage1 prep first-introduction gate failed")
    for relative in FORMAL_ARTIFACT_PATHS:
        present = _git(repo, "ls-tree", "-z", STAGE1_PREP_COMMIT, "--", relative, binary=True)
        assert isinstance(present, bytes)
        if present:
            raise FormalError("formal artifact unexpectedly present in Stage1 prep")


def _verify_original_gate(repo: Path) -> None:
    if str(_git(repo, "rev-parse", f"{ORIGINAL_GATE_COMMIT}^{{tree}}")) != ORIGINAL_GATE_TREE:
        raise FormalError("original formal gate tree drift")
    parents = str(_git(repo, "show", "-s", "--format=%P", ORIGINAL_GATE_COMMIT)).split()
    if parents != [ORIGINAL_GATE_PARENT]:
        raise FormalError("original formal gate parent drift")
    changed_raw = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", ORIGINAL_GATE_PARENT, ORIGINAL_GATE_COMMIT, binary=True)
    assert isinstance(changed_raw, bytes)
    changed = tuple(sorted(item.decode("utf-8", "strict") for item in changed_raw.split(b"\0") if item))
    if changed != FORMAL_GATE_PATHS:
        raise FormalError("original formal gate changed-path set drift")
    for relative in FORMAL_GATE_PATHS:
        old = _git(repo, "ls-tree", "-z", ORIGINAL_GATE_PARENT, "--", relative, binary=True)
        current = _git(repo, "ls-tree", "-z", ORIGINAL_GATE_COMMIT, "--", relative, binary=True)
        assert isinstance(old, bytes) and isinstance(current, bytes)
        if old or not current or str(_git(repo, "cat-file", "-t", f"{ORIGINAL_GATE_COMMIT}:{relative}")) != "blob":
            raise FormalError("original formal gate first-introduction drift")
    for relative in FORMAL_ARTIFACT_PATHS:
        present = _git(repo, "ls-tree", "-z", ORIGINAL_GATE_COMMIT, "--", relative, binary=True)
        assert isinstance(present, bytes)
        if present:
            raise FormalError("formal artifact unexpectedly present in original gate")


def verify_formal_gate(repo: Path, commit: str, *, require_live: bool = True) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    _verify_stage1_prep(repo)
    _verify_original_gate(repo)
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    if not _is_ancestor(repo, replay.PRODUCTION_COMMIT, STAGE1_PREP_COMMIT) or not _is_ancestor(repo, STAGE1_PREP_COMMIT, FORMAL_GATE_PARENT) or not _is_ancestor(repo, FORMAL_GATE_PARENT, resolved):
        raise FormalError("production/Stage1/formal ancestry gate failed")
    parents = str(_git(repo, "show", "-s", "--format=%P", resolved)).split()
    if parents != [FORMAL_GATE_PARENT]:
        raise FormalError("formal gate is not the direct single-parent child of its fixed parent")
    changed_raw = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", FORMAL_GATE_PARENT, resolved, binary=True)
    assert isinstance(changed_raw, bytes)
    changed = tuple(sorted(item.decode("utf-8", "strict") for item in changed_raw.split(b"\0") if item))
    if changed != FORMAL_GATE_PATHS:
        raise FormalError("formal gate must change exactly the two verifier files")
    files: dict[str, Any] = {}
    for relative in FORMAL_GATE_PATHS:
        if str(_git(repo, "cat-file", "-t", f"{resolved}:{relative}")) != "blob":
            raise FormalError("formal successor verifier is not a blob")
        blob = str(_git(repo, "rev-parse", f"{resolved}:{relative}"))
        size_text = str(_git(repo, "cat-file", "-s", blob))
        if not size_text.isascii() or not size_text.isdigit() or int(size_text) > MAX_FORMAL_FILE_BYTES:
            raise FormalError("formal verifier blob size invalid")
        raw = _git(repo, "cat-file", "blob", blob, binary=True)
        assert isinstance(raw, bytes)
        if len(raw) != int(size_text):
            raise FormalError("formal verifier raw blob size drift")
        fact: dict[str, Any] = {"path": relative, "blob": blob, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        if require_live:
            live, live_fact = _read(repo, relative)
            if live != raw:
                raise FormalError("live formal verifier differs from raw Git blob")
            fact["current"] = live_fact
        files[relative] = fact
    for relative in AS_LOCKED_PATHS:
        stage1_blob = str(_git(repo, "rev-parse", f"{STAGE1_PREP_COMMIT}:{relative}"))
        gate_blob = str(_git(repo, "rev-parse", f"{resolved}:{relative}"))
        if stage1_blob != gate_blob:
            raise FormalError("AS production/Stage1 locked path drifted before formal gate")
    for relative in FORMAL_ARTIFACT_PATHS:
        present = _git(repo, "ls-tree", "-z", resolved, "--", relative, binary=True)
        assert isinstance(present, bytes)
        if present:
            raise FormalError("formal artifact is present in the verifier-only gate")
    return {"commit": resolved, "tree": tree, "parent": FORMAL_GATE_PARENT, "original_gate": ORIGINAL_GATE_COMMIT, "stage1_ancestor": STAGE1_PREP_COMMIT, "changed_paths": list(FORMAL_GATE_PATHS), "first_introduction": False, "original_gate_first_introduction": True, "successor_exact_two": True, "formal_artifacts_absent": True, "locked_paths_stable": True, "files": files}


def _finite_tree(value: Any) -> None:
    nodes = 0

    def visit(item: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > 100_000 or depth > 64:
            raise FormalError("manifest structure budget exceeded")
        if item is None or type(item) in (bool, int, str):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                visit(child, depth + 1)
            return
        raise FormalError("manifest value type invalid")

    visit(value)


def normalized_manifest_sha256(value: dict[str, Any]) -> str:
    normalized = copy.deepcopy(value)
    audit = _exact(normalized.get("audit_binding"), {"path", "sha256", "bytes", "normalized_manifest_sha256"}, "audit binding")
    audit.update({"sha256": "0" * 64, "bytes": 0, "normalized_manifest_sha256": "0" * 64})
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _audit_payload(binding: dict[str, Any]) -> bytes:
    first = AUDIT_PREFIX + json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b" -->\n"
    return first + b"\n".join(AUDIT_MARKERS) + b"\n"


def _strict_yaml_load(payload: bytes) -> Any:
    try:
        return yaml.load(payload.decode("utf-8", "strict"), Loader=StrictLoader)
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise FormalError("strict formal manifest YAML invalid") from error


def validate_manifest_shape(value: Any) -> dict[str, Any]:
    _finite_tree(value)
    value = _exact(value, {"schema", "version", "status", "stage1_preparation", "formal_gate", "evidence", "audit_binding", "claims"}, "formal manifest")
    if value["schema"] != "sipi.as-03-power-wave-solve-replay-formal.v1" or type(value["version"]) is not int or value["version"] != 1 or value["status"] != "blocked_numeric_semantics":
        raise FormalError("formal manifest identity drift")
    if value["stage1_preparation"] != {"commit": STAGE1_PREP_COMMIT, "tree": STAGE1_PREP_TREE, "parent": STAGE1_PREP_PARENT}:
        raise FormalError("Stage1 prep binding drift")
    gate = _exact(value["formal_gate"], {"commit", "tree", "parent", "files"}, "formal gate")
    if not replay.HEX40.fullmatch(gate["commit"] or "") or not replay.HEX40.fullmatch(gate["tree"] or "") or gate["parent"] != FORMAL_GATE_PARENT or type(gate["files"]) is not list or len(gate["files"]) != 2:
        raise FormalError("formal gate identity drift")
    paths = []
    for raw in gate["files"]:
        item = _exact(raw, {"path", "blob", "sha256", "bytes"}, "formal gate file")
        paths.append(_safe_relative(item["path"]))
        if not replay.HEX40.fullmatch(item["blob"] or "") or not replay.HEX64.fullmatch(item["sha256"] or "") or type(item["bytes"]) is not int or item["bytes"] <= 0:
            raise FormalError("formal gate file binding invalid")
    if tuple(sorted(paths)) != FORMAL_GATE_PATHS:
        raise FormalError("formal gate paths drift")
    evidence = _exact(value["evidence"], {"reports", "aggregate"}, "evidence")
    if type(evidence["reports"]) is not list or len(evidence["reports"]) != 2:
        raise FormalError("formal evidence must have two reports")
    refs = [*evidence["reports"], evidence["aggregate"]]
    for raw in refs:
        ref = _exact(raw, {"path", "sha256", "bytes"}, "evidence ref")
        _safe_relative(ref["path"])
        if not replay.HEX64.fullmatch(ref["sha256"] or "") or type(ref["bytes"]) is not int or ref["bytes"] <= 0:
            raise FormalError("evidence ref invalid")
    if tuple(item["path"] for item in evidence["reports"]) != REPORT_PATHS or evidence["aggregate"]["path"] != AGGREGATE_PATH:
        raise FormalError("formal evidence paths drift")
    audit = _exact(value["audit_binding"], {"path", "sha256", "bytes", "normalized_manifest_sha256"}, "audit binding")
    if audit["path"] != AUDIT_PATH or not replay.HEX64.fullmatch(audit["sha256"] or "") or type(audit["bytes"]) is not int or audit["bytes"] <= 0 or not replay.HEX64.fullmatch(audit["normalized_manifest_sha256"] or "") or normalized_manifest_sha256(value) != audit["normalized_manifest_sha256"]:
        raise FormalError("audit/manifest binding invalid")
    claims = _exact(value["claims"], CLAIM_KEYS, "claims")
    if any(type(item) is not bool or item for item in claims.values()):
        raise FormalError("formal claims must remain false")
    return value


def _read_ref(repo: Path, ref: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    payload, fact = _read(repo, ref["path"], replay.MAX_REPORT_BYTES)
    if fact["sha256"] != ref["sha256"] or fact["bytes"] != ref["bytes"]:
        raise FormalError("artifact ref drift")
    return payload, fact


def verify_record_commit(repo: Path, formal_gate_commit: str) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    head = str(_git(repo, "rev-parse", "HEAD^{commit}"))
    parents = str(_git(repo, "show", "-s", "--format=%P", head)).split()
    if parents != [formal_gate_commit]:
        raise FormalError("formal record must be the direct single-parent child of the formal gate")
    changed_raw = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", formal_gate_commit, head, binary=True)
    assert isinstance(changed_raw, bytes)
    changed = tuple(sorted(item.decode("utf-8", "strict") for item in changed_raw.split(b"\0") if item))
    if changed != tuple(sorted(FORMAL_ARTIFACT_PATHS)):
        raise FormalError("formal record changed paths are not the exact fixed artifact set")
    files: dict[str, Any] = {}
    for relative in FORMAL_ARTIFACT_PATHS:
        old = _git(repo, "ls-tree", "-z", formal_gate_commit, "--", relative, binary=True)
        assert isinstance(old, bytes)
        if old or str(_git(repo, "cat-file", "-t", f"{head}:{relative}")) != "blob":
            raise FormalError("formal record path is not a first-introduced tracked blob")
        blob = str(_git(repo, "rev-parse", f"{head}:{relative}"))
        size_text = str(_git(repo, "cat-file", "-s", blob))
        if not size_text.isascii() or not size_text.isdigit() or int(size_text) > MAX_FORMAL_FILE_BYTES:
            raise FormalError("formal record blob size invalid")
        raw = _git(repo, "cat-file", "blob", blob, binary=True)
        assert isinstance(raw, bytes)
        live, live_fact = _read(repo, relative)
        if len(raw) != int(size_text) or raw != live:
            raise FormalError("formal record raw/live binding drift")
        files[relative] = {"path": relative, "blob": blob, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "current": live_fact}
    status = _git(repo, "status", "--porcelain=v1", "-z", binary=True)
    assert isinstance(status, bytes)
    if status:
        raise FormalError("formal record worktree is not clean")
    return {"commit": head, "tree": str(_git(repo, "rev-parse", f"{head}^{{tree}}")), "parent": formal_gate_commit, "changed_paths": list(sorted(FORMAL_ARTIFACT_PATHS)), "first_introduction": True, "worktree_clean": True, "files": files}


def _bridge_receipts(root: Path, expected: tuple[str, ...]) -> list[dict[str, Any]]:
    root = replay._safe_directory(root)
    entries = list(root.iterdir())
    if len(entries) != len(expected) or {entry.name for entry in entries} != set(expected):
        raise FormalError("external evidence bridge exact-file gate failed")
    receipts = []
    for name in expected:
        path = root / name
        if replay._is_reparse(path):
            raise FormalError("external evidence bridge contains a reparse entry")
        payload = replay._read_regular(path, replay.MAX_REPORT_BYTES)
        receipts.append({"basename": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "nlink": 1})
    return receipts


def _verify_stage1_through_external_bridge(
    repo: Path,
    agent_spice_repo: Path,
    skrf_repo: Path,
    temp_root: Path,
    report_payloads: list[tuple[bytes, dict[str, Any]]],
    aggregate_payload: bytes,
) -> None:
    repo = replay._safe_directory(repo)
    agent_spice_repo = replay._safe_directory(agent_spice_repo)
    skrf_repo = replay._safe_directory(skrf_repo)
    parent = replay._safe_directory(temp_root)
    replay._require_disjoint_roots({"repository": repo, "agent_spice": agent_spice_repo, "scikit_rf": skrf_repo, "temp": parent})
    evidence_root: Path | None = None
    verifier_temp: Path | None = None
    try:
        evidence_root = replay._fresh_child(parent, "as03-formal-evidence")
        verifier_temp = replay._fresh_child(parent, "as03-formal-verify")
        _bridge_receipts(evidence_root, ())
        names = (Path(REPORT_PATHS[0]).name, Path(REPORT_PATHS[1]).name, Path(AGGREGATE_PATH).name)
        payloads = (report_payloads[0][0], report_payloads[1][0], aggregate_payload)
        for name, payload in zip(names, payloads, strict=True):
            replay._create_file(evidence_root / name, payload, replay.MAX_REPORT_BYTES)
        before = _bridge_receipts(evidence_root, names)
        stage1_verify.verify_files(
            repo,
            agent_spice_repo,
            skrf_repo,
            STAGE1_PREP_COMMIT,
            evidence_root,
            evidence_root / names[0],
            evidence_root / names[1],
            evidence_root / names[2],
            "git",
            verifier_temp,
        )
        after = _bridge_receipts(evidence_root, names)
        if before != after:
            raise FormalError("external evidence bridge changed during Stage1 verification")
    finally:
        cleanup_errors: list[BaseException] = []
        for child in (verifier_temp, evidence_root):
            if child is not None and child.exists():
                try:
                    replay._remove_fresh_tree(child, parent)
                except BaseException as error:
                    cleanup_errors.append(error)
        if cleanup_errors:
            raise FormalError("external evidence bridge cleanup failed") from cleanup_errors[0]


def verify_formal_bundle(repo: Path, manifest_relative: str, agent_spice_repo: Path, skrf_repo: Path, temp_root: Path) -> dict[str, Any]:
    if _safe_relative(manifest_relative) != MANIFEST_PATH:
        raise FormalError("formal manifest path drift")
    manifest_payload, manifest_fact = _read(repo, MANIFEST_PATH)
    manifest = validate_manifest_shape(_strict_yaml_load(manifest_payload))
    gate = verify_formal_gate(repo, manifest["formal_gate"]["commit"])
    if {key: gate[key] for key in ("commit", "tree", "parent")} != {key: manifest["formal_gate"][key] for key in ("commit", "tree", "parent")}:
        raise FormalError("formal gate Git binding drift")
    for item in manifest["formal_gate"]["files"]:
        actual = gate["files"][item["path"]]
        if any(actual[key] != item[key] for key in ("path", "blob", "sha256", "bytes")):
            raise FormalError("formal gate file binding drift")
    verify_record_commit(repo, gate["commit"])
    report_payloads = [_read_ref(repo, ref) for ref in manifest["evidence"]["reports"]]
    aggregate_payload, _ = _read_ref(repo, manifest["evidence"]["aggregate"])
    reports = [replay.validate_report(json.loads(payload)) for payload, _ in report_payloads]
    aggregate = json.loads(aggregate_payload)
    stage1_verify.verify_values(reports[0], reports[1], aggregate, report_payloads[0][0], report_payloads[1][0], Path(REPORT_PATHS[0]).name, Path(REPORT_PATHS[1]).name)
    _verify_stage1_through_external_bridge(repo, agent_spice_repo, skrf_repo, temp_root, report_payloads, aggregate_payload)
    audit_payload, audit_fact = _read_ref(repo, manifest["audit_binding"])
    expected = {
        "normalized_manifest_sha256": manifest["audit_binding"]["normalized_manifest_sha256"],
        "reports": [item["sha256"] for item in manifest["evidence"]["reports"]],
        "aggregate": manifest["evidence"]["aggregate"]["sha256"],
        "stage1_prep_commit": STAGE1_PREP_COMMIT,
        "formal_gate_commit": gate["commit"],
    }
    if audit_payload != _audit_payload(expected) or audit_fact["sha256"] != manifest["audit_binding"]["sha256"]:
        raise FormalError("audit reciprocal binding drift")
    return {"valid": True, "status": "blocked_numeric_semantics", "fresh_replays": 2, "formal_gate": gate["commit"], "manifest": manifest_fact}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--formal-gate-commit")
    group.add_argument("--manifest")
    parser.add_argument("--agent-spice-repository", type=Path)
    parser.add_argument("--scikit-rf-repository", type=Path)
    parser.add_argument("--temp-root", type=Path)
    args = parser.parse_args()
    try:
        if args.formal_gate_commit:
            result = verify_formal_gate(args.repository, args.formal_gate_commit)
        else:
            if args.agent_spice_repository is None or args.scikit_rf_repository is None or args.temp_root is None:
                raise FormalError("bundle verification requires source repositories and temp root")
            result = verify_formal_bundle(args.repository, args.manifest, args.agent_spice_repository, args.scikit_rf_repository, args.temp_root)
    except (OSError, ValueError, FormalError, yaml.YAMLError, json.JSONDecodeError, subprocess.SubprocessError):
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
