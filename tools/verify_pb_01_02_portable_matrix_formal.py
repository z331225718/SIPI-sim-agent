"""Verify the PB matrix formal-tool gate and future immutable evidence bundle."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml

try:
    from .aggregate_pb_01_02_portable_matrix import AggregateError, aggregate_documents, validate_report
    from .verify_pb_01_02_portable_matrix import (
        HEX40,
        HEX64,
        PREP_PATHS as STAGE1_HARNESS_PATHS,
        VerifyError,
        _canonical,
        _git,
        _json_loads,
        _physical_source,
        _read,
        _safe_relative,
        verify_preparation,
    )
except ImportError:  # pragma: no cover - direct script execution
    from aggregate_pb_01_02_portable_matrix import AggregateError, aggregate_documents, validate_report
    from verify_pb_01_02_portable_matrix import (
        HEX40,
        HEX64,
        PREP_PATHS as STAGE1_HARNESS_PATHS,
        VerifyError,
        _canonical,
        _git,
        _json_loads,
        _physical_source,
        _read,
        _safe_relative,
        verify_preparation,
    )


STAGE1_PREP_COMMIT = "4042f0d9fdd0846e20ea95e8da7752812a4eea45"
STAGE1_PREP_TREE = "8f60a9c35be8e981c6637fbd87cfd5b5a16080fe"
STAGE1_PREP_PARENT = "d44581ac8b10adbc8f803bb0292107ae3303e015"
# Mechanically update this one constant to the actual repository HEAD immediately
# before the two-file formal-tool gate commit is created.
FORMAL_GATE_PARENT = "b96828c209006960cbd519d8ce62e33db527a849"
PRODUCTION_PATH = "crates/sipi-pybert-direct"
FORMAL_GATE_PATHS = (
    "tools/test_verify_pb_01_02_portable_matrix_formal.py",
    "tools/verify_pb_01_02_portable_matrix_formal.py",
)
REPORT_PATHS = (
    "docs/baselines/pb-01-02-portable-matrix-run-01.v1.json",
    "docs/baselines/pb-01-02-portable-matrix-run-02.v1.json",
)
AGGREGATE_PATH = "docs/baselines/pb-01-02-portable-matrix-aggregate.v1.json"
MANIFEST_PATH = "docs/baselines/pb-01-02-portable-matrix.v1.yaml"
AUDIT_PATH = "docs/baselines/audits/pb-01-02-portable-matrix.audit.json"
FORMAL_ARTIFACT_PATHS = (*REPORT_PATHS, AGGREGATE_PATH, MANIFEST_PATH, AUDIT_PATH)
AUDIT_MARKER = "sipi-pb-01-02-formal-binding-v1"
CLAIM_KEYS = {"global_branch_parity", "whole_payload_parity", "release_acceptance", "numeric_parity"}
NON_CLAIMS = [
    "no_global_branch_parity",
    "no_whole_payload_parity",
    "no_release_acceptance",
    "no_numeric_parity_promotion",
    "scoped_portable_matrix_only",
]


class _StrictLoader(yaml.SafeLoader):
    pass


def _strict_mapping(loader: _StrictLoader, node: yaml.Node, deep: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str or key in result:
            raise VerifyError("manifest keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _strict_mapping)


def _exact(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise VerifyError(f"{name} schema is not exact")
    return value


def _finite_json_tree(value: Any) -> None:
    nodes = 0

    def visit(item: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > 1_000_000 or depth > 128:
            raise VerifyError("manifest structure budget exceeded")
        if item is None or type(item) in (bool, int, str):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise VerifyError("manifest contains a non-finite number")
            return
        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                visit(child, depth + 1)
            return
        raise VerifyError("manifest contains an unsupported value type")

    visit(value)


def verify_formal_gate(repo: Path, commit: str, *, require_live: bool = True) -> dict[str, Any]:
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    parents = str(_git(repo, "show", "-s", "--format=%P", resolved)).split()
    if parents != [FORMAL_GATE_PARENT]:
        raise VerifyError("formal-tool gate is not the direct single-parent child of the pinned integration parent")
    _git(repo, "merge-base", "--is-ancestor", STAGE1_PREP_COMMIT, resolved)
    protected_raw = _git(repo, "diff", "--name-only", "-z", STAGE1_PREP_COMMIT, resolved, "--", *STAGE1_HARNESS_PATHS, PRODUCTION_PATH, binary=True)
    assert isinstance(protected_raw, bytes)
    if protected_raw:
        raise VerifyError("PB Stage1 harness or sipi-pybert-direct production drifted after Stage1 prep")
    changed_raw = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", FORMAL_GATE_PARENT, resolved, binary=True)
    assert isinstance(changed_raw, bytes)
    changed = tuple(sorted(item.decode("utf-8", "strict") for item in changed_raw.split(b"\0") if item))
    if changed != FORMAL_GATE_PATHS:
        raise VerifyError("formal-tool gate changed paths are not the exact two-file set")
    files: dict[str, Any] = {}
    for relative in FORMAL_GATE_PATHS:
        old = _git(repo, "ls-tree", "-z", FORMAL_GATE_PARENT, "--", relative, binary=True)
        assert isinstance(old, bytes)
        if old:
            raise VerifyError("formal-tool path is not first introduced")
        if str(_git(repo, "cat-file", "-t", f"{resolved}:{relative}")) != "blob":
            raise VerifyError("formal-tool entry is not a blob")
        blob = str(_git(repo, "rev-parse", f"{resolved}:{relative}"))
        size_text = str(_git(repo, "cat-file", "-s", blob))
        if not size_text.isascii() or not size_text.isdigit() or int(size_text) > 16 * 1024 * 1024:
            raise VerifyError("formal-tool blob size invalid")
        raw = _git(repo, "cat-file", "blob", blob, binary=True)
        assert isinstance(raw, bytes)
        if len(raw) != int(size_text):
            raise VerifyError("formal-tool raw blob size drift")
        fact: dict[str, Any] = {"path": relative, "blob": blob, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        if require_live:
            live, live_fact = _read(repo, relative)
            if live != raw:
                raise VerifyError("current formal-tool file differs from its raw Git blob")
            fact["current"] = live_fact
        files[relative] = fact
    for relative in FORMAL_ARTIFACT_PATHS:
        present = _git(repo, "ls-tree", "-z", resolved, "--", relative, binary=True)
        assert isinstance(present, bytes)
        if present:
            raise VerifyError("formal artifact is present in the two-file formal-tool gate")
    return {"commit": resolved, "tree": tree, "parent": FORMAL_GATE_PARENT, "stage1_ancestor": True, "protected_paths_unchanged": True, "changed_paths": list(FORMAL_GATE_PATHS), "first_introduction": True, "formal_artifacts_absent": True, "files": files}


def verify_record_gate(repo: Path, formal_gate_commit: str) -> dict[str, Any]:
    head = str(_git(repo, "rev-parse", "HEAD^{commit}"))
    tree = str(_git(repo, "rev-parse", f"{head}^{{tree}}"))
    parents = str(_git(repo, "show", "-s", "--format=%P", head)).split()
    if parents != [formal_gate_commit]:
        raise VerifyError("formal record HEAD is not the direct single-parent child of the formal-tool gate")
    changed_raw = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", formal_gate_commit, head, binary=True)
    assert isinstance(changed_raw, bytes)
    changed = tuple(sorted(item.decode("utf-8", "strict") for item in changed_raw.split(b"\0") if item))
    if changed != tuple(sorted(FORMAL_ARTIFACT_PATHS)):
        raise VerifyError("formal record changed paths are not the exact fixed artifact set")
    status = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)
    assert isinstance(status, bytes)
    if status:
        raise VerifyError("formal record checkout is not clean, tracked, and free of untracked files")
    files: dict[str, Any] = {}
    for relative in FORMAL_ARTIFACT_PATHS:
        old = _git(repo, "ls-tree", "-z", formal_gate_commit, "--", relative, binary=True)
        assert isinstance(old, bytes)
        if old:
            raise VerifyError("formal record artifact is not first introduced")
        if str(_git(repo, "cat-file", "-t", f"{head}:{relative}")) != "blob":
            raise VerifyError("formal record artifact is not a Git blob")
        blob = str(_git(repo, "rev-parse", f"{head}:{relative}"))
        size_text = str(_git(repo, "cat-file", "-s", blob))
        if not size_text.isascii() or not size_text.isdigit() or int(size_text) > 16 * 1024 * 1024:
            raise VerifyError("formal record artifact blob size invalid")
        raw = _git(repo, "cat-file", "blob", blob, binary=True)
        assert isinstance(raw, bytes)
        live, live_fact = _read(repo, relative)
        if len(raw) != int(size_text) or live != raw:
            raise VerifyError("formal record raw Git blob/current file drift")
        files[relative] = {"path": relative, "blob": blob, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "current": live_fact}
    return {"commit": head, "tree": tree, "parent": formal_gate_commit, "changed_paths": list(sorted(FORMAL_ARTIFACT_PATHS)), "first_introduction": True, "clean": True, "files": files}


def normalized_manifest_sha256(value: dict[str, Any]) -> str:
    normalized = copy.deepcopy(value)
    audit = _exact(normalized.get("audit_binding"), {"path", "sha256", "bytes", "normalized_manifest_sha256"}, "audit binding")
    audit["sha256"] = "0" * 64
    audit["bytes"] = 0
    audit["normalized_manifest_sha256"] = "0" * 64
    return hashlib.sha256(_canonical(normalized)).hexdigest()


def validate_manifest_shape(value: Any) -> dict[str, Any]:
    _finite_json_tree(value)
    value = _exact(value, {"schema", "version", "status", "stage1_preparation", "formal_gate", "evidence", "audit_binding", "claims"}, "formal manifest")
    if value["schema"] != "sipi.pb-01-02-portable-matrix-formal.v1" or type(value["version"]) is not int or value["version"] != 1:
        raise VerifyError("formal manifest identity invalid")
    if value["status"] not in {"passed_scoped", "scoped_matrix_blocked"}:
        raise VerifyError("formal manifest status invalid")
    if value["stage1_preparation"] != {"commit": STAGE1_PREP_COMMIT, "tree": STAGE1_PREP_TREE, "parent": STAGE1_PREP_PARENT}:
        raise VerifyError("Stage1 preparation binding drift")
    gate = _exact(value["formal_gate"], {"commit", "tree", "parent", "files"}, "formal gate")
    if not HEX40.fullmatch(gate["commit"] or "") or not HEX40.fullmatch(gate["tree"] or "") or gate["parent"] != FORMAL_GATE_PARENT:
        raise VerifyError("formal gate Git identity invalid")
    if type(gate["files"]) is not list or len(gate["files"]) != 2:
        raise VerifyError("formal gate file list invalid")
    paths: list[str] = []
    for item in gate["files"]:
        item = _exact(item, {"path", "blob", "sha256", "bytes"}, "formal gate file")
        paths.append(_safe_relative(item["path"]))
        if not HEX40.fullmatch(item["blob"] or "") or not HEX64.fullmatch(item["sha256"] or "") or type(item["bytes"]) is not int or item["bytes"] < 0:
            raise VerifyError("formal gate file binding invalid")
    if tuple(sorted(paths)) != FORMAL_GATE_PATHS:
        raise VerifyError("formal gate file paths invalid")
    evidence = _exact(value["evidence"], {"reports", "aggregate"}, "evidence")
    if type(evidence["reports"]) is not list or len(evidence["reports"]) != 2:
        raise VerifyError("formal evidence needs exactly two reports")
    for ref in [*evidence["reports"], evidence["aggregate"]]:
        ref = _exact(ref, {"path", "sha256", "bytes"}, "evidence ref")
        _safe_relative(ref["path"])
        if not HEX64.fullmatch(ref["sha256"] or "") or type(ref["bytes"]) is not int or ref["bytes"] <= 0:
            raise VerifyError("evidence ref invalid")
    if tuple(item["path"] for item in evidence["reports"]) != REPORT_PATHS or evidence["aggregate"]["path"] != AGGREGATE_PATH:
        raise VerifyError("formal evidence paths invalid")
    audit = _exact(value["audit_binding"], {"path", "sha256", "bytes", "normalized_manifest_sha256"}, "audit binding")
    if audit["path"] != AUDIT_PATH or not HEX64.fullmatch(audit["sha256"] or "") or type(audit["bytes"]) is not int or audit["bytes"] <= 0 or not HEX64.fullmatch(audit["normalized_manifest_sha256"] or ""):
        raise VerifyError("audit identity invalid")
    if normalized_manifest_sha256(value) != audit["normalized_manifest_sha256"]:
        raise VerifyError("normalized manifest digest drift")
    claims = _exact(value["claims"], CLAIM_KEYS, "claims")
    if any(type(item) is not bool or item for item in claims.values()):
        raise VerifyError("all formal claims must remain false")
    return value


def _read_ref(repo: Path, ref: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    payload, fact = _read(repo, ref["path"])
    if fact["sha256"] != ref["sha256"] or fact["bytes"] != ref["bytes"]:
        raise VerifyError("artifact ref hash/length drift")
    return payload, fact


def verify_formal_bundle(repo: Path, manifest_relative: str, upstream_repo: Path) -> dict[str, Any]:
    manifest_payload, manifest_fact = _read(repo, manifest_relative)
    try:
        manifest = yaml.load(manifest_payload, Loader=_StrictLoader)
    except yaml.YAMLError as error:
        raise VerifyError("formal manifest YAML invalid") from error
    manifest = validate_manifest_shape(manifest)
    stage1 = verify_preparation(repo, STAGE1_PREP_COMMIT, STAGE1_PREP_PARENT, require_live=False)
    if stage1["tree"] != STAGE1_PREP_TREE:
        raise VerifyError("Stage1 prep tree drift")
    gate = verify_formal_gate(repo, manifest["formal_gate"]["commit"], require_live=True)
    if {key: gate[key] for key in ("commit", "tree", "parent")} != {key: manifest["formal_gate"][key] for key in ("commit", "tree", "parent")}:
        raise VerifyError("formal gate Git binding drift")
    for item in manifest["formal_gate"]["files"]:
        actual = gate["files"][item["path"]]
        if any(actual[key] != item[key] for key in ("path", "blob", "sha256", "bytes")):
            raise VerifyError("formal gate raw/current file binding drift")
    record = verify_record_gate(repo, gate["commit"])
    reports: list[dict[str, Any]] = []
    report_facts: list[dict[str, Any]] = []
    for ref in manifest["evidence"]["reports"]:
        payload, fact = _read_ref(repo, ref)
        try:
            report = validate_report(_json_loads(payload))
        except (AggregateError, ValueError, TypeError) as error:
            raise VerifyError("formal report invalid") from error
        if {key: report["preparation"][key] for key in ("commit", "tree", "parent")} != {"commit": STAGE1_PREP_COMMIT, "tree": STAGE1_PREP_TREE, "parent": STAGE1_PREP_PARENT}:
            raise VerifyError("formal report is not bound to Stage1 prep")
        for path, actual in stage1["files"].items():
            bound = report["preparation"]["files"][path]
            if any(bound[key] != actual[key] for key in ("blob", "sha256", "bytes")):
                raise VerifyError("formal report harness differs from raw Stage1 prep")
        reports.append(report)
        report_facts.append(fact)
        record_fact = record["files"][ref["path"]]
        if record_fact["sha256"] != ref["sha256"] or record_fact["bytes"] != ref["bytes"]:
            raise VerifyError("report manifest/Git-record binding drift")
    if report_facts[0]["sha256"] == report_facts[1]["sha256"]:
        raise VerifyError("fresh report hashes must differ")
    for role, source_repo in (("candidate", repo), ("upstream", upstream_repo)):
        physical = _physical_source(source_repo, reports[0]["source"][role]["commit"])
        for report in reports:
            source = report["source"][role]
            if any(physical[key] != source[key] for key in ("commit", "tree", "archive_sha256")) or physical["inventory_sha256"] != source["inventory_pre_sha256"] or source["inventory_pre_sha256"] != source["inventory_post_sha256"]:
                raise VerifyError(f"{role} physical source binding drift")
    expected = aggregate_documents(reports[0], reports[1])
    aggregate_payload, aggregate_fact = _read_ref(repo, manifest["evidence"]["aggregate"])
    if record["files"][AGGREGATE_PATH]["sha256"] != aggregate_fact["sha256"]:
        raise VerifyError("aggregate Git-record binding drift")
    actual_aggregate = _json_loads(aggregate_payload)
    if _canonical(actual_aggregate) != _canonical({**expected, "report_files": report_facts}):
        raise VerifyError("aggregate is not the mechanical recomputation")
    audit_payload, audit_fact = _read_ref(repo, manifest["audit_binding"])
    if record["files"][AUDIT_PATH]["sha256"] != audit_fact["sha256"]:
        raise VerifyError("audit Git-record binding drift")
    audit = _exact(_json_loads(audit_payload), {"schema", "marker", "status", "binding", "claims", "non_claims"}, "audit")
    if audit["schema"] != "sipi.pb-01-02-portable-matrix-audit.v1" or audit["marker"] != AUDIT_MARKER or audit["status"] != manifest["status"]:
        raise VerifyError("audit identity/status drift")
    audit_claims = _exact(audit["claims"], CLAIM_KEYS, "audit claims")
    if audit_claims != manifest["claims"] or any(audit_claims.values()) or audit["non_claims"] != NON_CLAIMS:
        raise VerifyError("audit claims/non-claims drift")
    binding = _exact(audit["binding"], {"normalized_manifest_sha256", "reports", "aggregate", "stage1_prep_commit", "formal_gate_commit"}, "audit binding marker")
    expected_binding = {
        "normalized_manifest_sha256": manifest["audit_binding"]["normalized_manifest_sha256"],
        "reports": [item["sha256"] for item in manifest["evidence"]["reports"]],
        "aggregate": manifest["evidence"]["aggregate"]["sha256"],
        "stage1_prep_commit": STAGE1_PREP_COMMIT,
        "formal_gate_commit": gate["commit"],
    }
    if binding != expected_binding or audit_fact["sha256"] != manifest["audit_binding"]["sha256"]:
        raise VerifyError("audit/manifest reciprocal binding drift")
    if record["files"][MANIFEST_PATH]["sha256"] != manifest_fact["sha256"]:
        raise VerifyError("manifest Git-record binding drift")
    return {"valid": True, "status": actual_aggregate["status"], "manifest": manifest_fact, "formal_gate": gate["commit"], "record_commit": record["commit"], "fresh_replays": 2}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\Py-bert-agent"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prep-commit")
    group.add_argument("--manifest")
    args = parser.parse_args()
    try:
        result = verify_formal_gate(args.repo, args.prep_commit) if args.prep_commit else verify_formal_bundle(args.repo, args.manifest, args.upstream_repo)
    except (AggregateError, OSError, VerifyError, UnicodeDecodeError, yaml.YAMLError, json.JSONDecodeError):
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
