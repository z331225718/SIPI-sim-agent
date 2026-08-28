"""Verify the PB-01/PB-02 Stage-2 aggregate gate and future record bundle.

The Stage-2 gate is deliberately additive.  It freezes the exact three-tool
adapter before any replay reports or formal documents are introduced.  The
future record verifier is kept in the same module so a later record cannot
silently bypass the gate, source custody, or the aggregate recomputation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
from pathlib import Path
from typing import Any

import yaml

try:  # pragma: no cover - direct script execution uses the fallback
    from . import aggregate_pb_01_02_candidate_matrix_stage2 as aggregate
except ImportError:  # pragma: no cover
    import aggregate_pb_01_02_candidate_matrix_stage2 as aggregate

try:  # pragma: no cover - package import is only used by external callers
    from .verify_pb_01_02_candidate_matrix_prep import (
        _blob,
        _bounded_archive,
        _commit_facts,
        _git,
        _live_file,
    )
except ImportError:  # pragma: no cover
    from verify_pb_01_02_candidate_matrix_prep import (
        _blob,
        _bounded_archive,
        _commit_facts,
        _git,
        _live_file,
    )


ROOT = Path(__file__).resolve().parents[1]
GATE_PATHS = (
    "tools/aggregate_pb_01_02_candidate_matrix_stage2.py",
    "tools/verify_pb_01_02_candidate_matrix_stage2.py",
    "tools/test_verify_pb_01_02_candidate_matrix_stage2.py",
)
ORIGINAL_GATE_COMMIT = "840806ef117af8cc19533e8d23a22fb6fc85a290"
ORIGINAL_GATE_TREE = "ee86a0cb8f39c661a2f5108389efc2f48ab0bf3f"
ORIGINAL_GATE_PARENT = "176956771a0d24255b427c0243d3dabc4e3fdeca"
ORIGINAL_GATE_FILE_RECEIPTS = {
    "tools/aggregate_pb_01_02_candidate_matrix_stage2.py": {
        "blob": "4095fa444216a26455af47e95022f83cbfed535e",
        "sha256": "d6ecc5535ebcd8320718ccc8d4fb6f89d7025f15c85815b37c84cc38b8d0b28f",
        "bytes": 47_014,
    },
    "tools/verify_pb_01_02_candidate_matrix_stage2.py": {
        "blob": "0c8fe9701b4099641aea1ce8a2a83c283a1bf82e",
        "sha256": "a09ca6c588577313309bd02389d9654161ee42e41add2f55bf586f73becad795",
        "bytes": 24_282,
    },
    "tools/test_verify_pb_01_02_candidate_matrix_stage2.py": {
        "blob": "d5ef5e754725297b573d38cda1de062d7040de5d",
        "sha256": "54045c845d06c35f9e40bceb35cf3b4713ae6a093d14fa713527ba28c9de3351",
        "bytes": 18_099,
    },
}
FORMAL_PATHS = aggregate.FORMAL_PATHS
FILE_LIMIT = 16 * 1024 * 1024
GIT_TIMEOUT = 120
FORMAL_SCHEMA = "sipi.pb-01-02-candidate-matrix-formal.v1"
AUDIT_SCHEMA = "sipi.pb-01-02-candidate-matrix-formal-audit.v1"
AUDIT_PATH = FORMAL_PATHS[4]
REPORT_PATHS = FORMAL_PATHS[:2]
AGGREGATE_PATH = FORMAL_PATHS[2]
MANIFEST_PATH = FORMAL_PATHS[3]
PREP_FILES = aggregate.PREP_FILES
PREP_FILE_RECEIPTS = aggregate.PREP_FILE_RECEIPTS
PREP_COMMIT = aggregate.PREP_COMMIT
PREP_TREE = aggregate.PREP_TREE
PREP_PARENT = aggregate.PREP_PARENT
PREP_ARCHIVE_SHA256 = aggregate.PREP_ARCHIVE_SHA256
PREP_ARCHIVE_BYTES = aggregate.PREP_ARCHIVE_BYTES
CANDIDATE = aggregate.CANDIDATE
UPSTREAM = aggregate.UPSTREAM
CORPUS = aggregate.CORPUS
FIXTURES = aggregate.FIXTURES
NON_CLAIMS = [
    "PB-01 selected-array parity does not claim full PyBertData class-pickle or whole-branch parity.",
    "PB-02 metadata, artifact, CTLE schema, and jitter-span blockers are preserved; no blocked case is promoted.",
    "This aggregate is not a license decision, product capability admission, release approval, or global parity claim.",
]


class VerifyError(RuntimeError):
    """A Stage-2 gate or formal-record invariant failed."""


class _StrictLoader(yaml.SafeLoader):
    pass


def _strict_mapping(loader: _StrictLoader, node: yaml.Node, deep: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str or key in result:
            raise VerifyError("YAML mapping keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _strict_mapping)


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise VerifyError(f"{label} key set drift")
    return value


def _finite(value: Any, label: str = "document") -> None:
    nodes = 0

    def visit(item: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > aggregate.MAX_JSON_NODES or depth > aggregate.MAX_JSON_DEPTH:
            raise VerifyError(f"{label} structure budget exceeded")
        if item is None or type(item) in (bool, int, str):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise VerifyError(f"{label} contains a non-finite number")
            return
        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                visit(child, depth + 1)
            return
        raise VerifyError(f"{label} contains an unsupported value")

    visit(value)


def _read_regular(path: Path, limit: int = FILE_LIMIT) -> bytes:
    try:
        info = os.lstat(path)
    except OSError as error:
        raise VerifyError(f"file is unavailable: {path}") from error
    if not stat.S_ISREG(info.st_mode) or os.path.islink(path) or int(info.st_nlink) != 1:
        raise VerifyError("file must be a regular non-link with one link")
    if int(info.st_size) > limit:
        raise VerifyError("file exceeds bounded read budget")
    payload = path.read_bytes()
    if len(payload) != int(info.st_size) or len(payload) > limit:
        raise VerifyError("file changed during bounded read")
    return payload


def _load_json(path: Path) -> tuple[dict[str, Any], str, bytes]:
    payload = _read_regular(path)

    def pairs(items: list[tuple[Any, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise VerifyError("JSON keys must be unique strings")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(VerifyError(f"non-finite JSON constant: {token}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerifyError("invalid JSON document") from error
    if type(value) is not dict:
        raise VerifyError("JSON root must be an object")
    _finite(value, "JSON document")
    return value, hashlib.sha256(payload).hexdigest(), payload


def _commit_facts_checked(repo: Path, commit: str, label: str) -> tuple[str, str, list[str]]:
    try:
        return _commit_facts(repo, commit, label)
    except Exception as error:
        raise VerifyError(f"cannot resolve {label} commit") from error


def _bounded_archive_checked(repo: Path, commit: str, label: str) -> tuple[str, int]:
    try:
        return _bounded_archive(repo, commit)
    except Exception as error:
        raise VerifyError(f"cannot verify bounded {label} archive") from error


def _path_entry(repo: Path, commit: str, relative: str) -> tuple[str, bytes]:
    try:
        blob, payload = _blob(repo, commit, relative)
    except Exception as error:  # normalize helper-specific errors for this gate
        raise VerifyError(f"Git path is unavailable: {relative}") from error
    return blob, payload


def _assert_regular_blob(repo: Path, commit: str, relative: str, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    blob, payload = _path_entry(repo, commit, relative)
    digest = hashlib.sha256(payload).hexdigest()
    if len(payload) > FILE_LIMIT:
        raise VerifyError(f"Git blob exceeds file budget: {relative}")
    receipt = {"path": relative, "blob": blob, "sha256": digest, "bytes": len(payload)}
    if expected is not None:
        if receipt != {"path": relative, **{key: expected[key] for key in ("blob", "sha256", "bytes")}}:
            raise VerifyError(f"Git blob receipt drift: {relative}")
    return receipt


def _assert_absent(repo: Path, commit: str, relative: str, label: str) -> None:
    raw = _git(repo, "ls-tree", "-z", commit, "--", relative, binary=True)
    assert isinstance(raw, bytes)
    if raw:
        raise VerifyError(f"{label} contains forbidden path: {relative}")


def _changed_name_status(repo: Path, parent: str, commit: str) -> list[tuple[str, str]]:
    raw = _git(
        repo,
        "diff-tree",
        "--no-commit-id",
        "--name-status",
        "--no-renames",
        "-r",
        "-z",
        parent,
        commit,
        binary=True,
    )
    assert isinstance(raw, bytes)
    fields = [field.decode("utf-8", "strict") for field in raw.split(b"\0") if field]
    if len(fields) % 2:
        raise VerifyError("Git name-status encoding is malformed")
    return [(fields[index], fields[index + 1]) for index in range(0, len(fields), 2)]


def _verify_fixed_sources(repo: Path, upstream_repo: Path) -> dict[str, Any]:
    resolved, tree, parents = _commit_facts_checked(repo, CANDIDATE["commit"], "candidate")
    if resolved != CANDIDATE["commit"] or tree != CANDIDATE["tree"] or parents != ["af518684936f8656eda61288abe2647f7d909ea4"]:
        raise VerifyError("candidate commit/tree/parent drift")
    archive_sha, archive_bytes = _bounded_archive_checked(repo, resolved, "candidate")
    if archive_sha != CANDIDATE["archive_sha256"] or archive_bytes != 54_661_120:
        raise VerifyError("candidate bounded archive drift")
    upstream_resolved, upstream_tree, upstream_parents = _commit_facts_checked(upstream_repo, UPSTREAM["commit"], "upstream")
    if upstream_resolved != UPSTREAM["commit"] or upstream_tree != UPSTREAM["tree"] or upstream_parents != ["1d6565e5c0398faeef9b757fc6ff21c91d36ccfd"]:
        raise VerifyError("upstream commit/tree/parent drift")
    upstream_archive_sha, upstream_archive_bytes = _bounded_archive_checked(upstream_repo, upstream_resolved, "upstream")
    if upstream_archive_sha != UPSTREAM["archive_sha256"] or upstream_archive_bytes != 132_587_520:
        raise VerifyError("upstream bounded archive drift")
    for label, source_repo, commit, facts in (
        ("candidate", repo, resolved, CANDIDATE),
        ("upstream", upstream_repo, upstream_resolved, UPSTREAM),
    ):
        if facts["archive_sha256"] != (archive_sha if label == "candidate" else upstream_archive_sha):
            raise VerifyError(f"{label} archive binding drift")
    corpus_blob, corpus_payload = _path_entry(repo, resolved, CORPUS["path"])
    del corpus_blob
    if len(corpus_payload) != CORPUS["bytes"] or hashlib.sha256(corpus_payload).hexdigest() != CORPUS["sha256"]:
        raise VerifyError("candidate corpus receipt drift")
    for fixture in FIXTURES.values():
        _, payload = _path_entry(repo, resolved, fixture["path"])
        if len(payload) != fixture["bytes"] or hashlib.sha256(payload).hexdigest() != fixture["sha256"]:
            raise VerifyError(f"candidate fixture receipt drift: {fixture['path']}")
    return {
        "candidate": {**CANDIDATE, "parents": parents, "archive_bytes": archive_bytes},
        "upstream": {**UPSTREAM, "parents": upstream_parents, "archive_bytes": upstream_archive_bytes},
    }


def _verify_prep(repo: Path, *, require_live: bool) -> dict[str, Any]:
    resolved, tree, parents = _commit_facts_checked(repo, PREP_COMMIT, "PB preparation")
    if resolved != PREP_COMMIT or tree != PREP_TREE or parents != [PREP_PARENT]:
        raise VerifyError("PB preparation commit/tree/parent drift")
    archive_sha, archive_bytes = _bounded_archive_checked(repo, resolved, "PB preparation")
    if archive_sha != PREP_ARCHIVE_SHA256 or archive_bytes != PREP_ARCHIVE_BYTES:
        raise VerifyError("PB preparation bounded archive drift")
    files: dict[str, Any] = {}
    for relative in PREP_FILES:
        expected = PREP_FILE_RECEIPTS[relative]
        receipt = _assert_regular_blob(repo, resolved, relative, expected)
        if require_live:
            live = _live_file(repo, relative)
            if live != _path_entry(repo, resolved, relative)[1]:
                raise VerifyError(f"PB preparation live/blob drift: {relative}")
        files[relative] = receipt
    for relative in FORMAL_PATHS:
        _assert_absent(repo, resolved, relative, "PB preparation")
    return {
        "commit": resolved,
        "tree": tree,
        "parent": PREP_PARENT,
        "archive_sha256": archive_sha,
        "archive_bytes": archive_bytes,
        "files": files,
        "formal_paths_absent": True,
    }


def _verify_original_gate(repo: Path, gate_commit: str, *, upstream_repo: Path, require_live: bool = True) -> dict[str, Any]:
    source = _verify_fixed_sources(repo, upstream_repo)
    prep = _verify_prep(repo, require_live=require_live)
    resolved, tree, parents = _commit_facts_checked(repo, gate_commit, "Stage-2 gate")
    if resolved != ORIGINAL_GATE_COMMIT or tree != ORIGINAL_GATE_TREE or parents != [ORIGINAL_GATE_PARENT]:
        raise VerifyError("original Stage-2 gate commit/tree/parent drift")
    changed = _changed_name_status(repo, PREP_COMMIT, resolved)
    if sorted(changed) != sorted(("A", path) for path in GATE_PATHS):
        raise VerifyError("original Stage-2 gate changed paths are not the exact three-file set")
    files: list[dict[str, Any]] = []
    for relative in GATE_PATHS:
        _assert_absent(repo, PREP_COMMIT, relative, "PB preparation")
        receipt = _assert_regular_blob(repo, resolved, relative, ORIGINAL_GATE_FILE_RECEIPTS[relative])
        if require_live:
            live = _live_file(repo, relative)
            if live != _path_entry(repo, resolved, relative)[1]:
                raise VerifyError(f"Stage-2 gate live/blob drift: {relative}")
        files.append(receipt)
    for relative in FORMAL_PATHS:
        _assert_absent(repo, resolved, relative, "Stage-2 gate")
    return {
        "valid": True,
        "commit": resolved,
        "tree": tree,
        "parent": ORIGINAL_GATE_PARENT,
        "changed_paths": list(GATE_PATHS),
        "first_introduction": True,
        "files": files,
        "formal_paths_absent": True,
        "prep": prep,
        "source": source,
    }


def verify_gate(repo: Path = ROOT, gate_commit: str = "", *, upstream_repo: Path | None = None, require_live: bool = True) -> dict[str, Any]:
    """Verify the immutable original three-file gate; formal records are absent."""

    if not gate_commit:
        raise VerifyError("gate commit is required")
    source_repo = (upstream_repo or Path(r"C:\Users\z3312\code\Py-bert-agent")).resolve()
    return _verify_original_gate(repo.resolve(), gate_commit, upstream_repo=source_repo, require_live=require_live)


def verify_successor(repo: Path, successor_commit: str, *, upstream_repo: Path | None = None, require_live: bool = True) -> dict[str, Any]:
    """Verify the exact-three-file modified successor of the immutable gate."""

    if not successor_commit:
        raise VerifyError("successor commit is required")
    source_repo = (upstream_repo or Path(r"C:\Users\z3312\code\Py-bert-agent")).resolve()
    original = _verify_original_gate(repo.resolve(), ORIGINAL_GATE_COMMIT, upstream_repo=source_repo, require_live=False)
    resolved, tree, parents = _commit_facts_checked(repo.resolve(), successor_commit, "Stage-2 successor")
    if resolved != successor_commit or parents != [ORIGINAL_GATE_COMMIT]:
        raise VerifyError("Stage-2 successor must be the direct child of original gate 840")
    changed = _changed_name_status(repo.resolve(), ORIGINAL_GATE_COMMIT, resolved)
    if sorted(changed) != sorted(("M", path) for path in GATE_PATHS):
        raise VerifyError("Stage-2 successor changed paths are not the exact three-file modification set")
    files: list[dict[str, Any]] = []
    for relative in GATE_PATHS:
        previous = _assert_regular_blob(repo, ORIGINAL_GATE_COMMIT, relative, ORIGINAL_GATE_FILE_RECEIPTS[relative])
        receipt = _assert_regular_blob(repo, resolved, relative)
        if receipt["blob"] == previous["blob"] or receipt["sha256"] == previous["sha256"]:
            raise VerifyError(f"Stage-2 successor did not modify {relative}")
        if require_live:
            live = _live_file(repo, relative)
            if live != _path_entry(repo, resolved, relative)[1]:
                raise VerifyError(f"Stage-2 successor live/blob drift: {relative}")
        files.append(receipt)
    for relative in FORMAL_PATHS:
        _assert_absent(repo, resolved, relative, "Stage-2 successor")
    return {"valid": True, "commit": resolved, "tree": tree, "parent": ORIGINAL_GATE_COMMIT, "changed_paths": list(GATE_PATHS), "first_introduction": False, "files": files, "formal_paths_absent": True, "original_gate": original}


def verify_record_commit(repo: Path, gate_commit: str, record_commit: str, *, upstream_repo: Path | None = None, require_live: bool = True, require_clean: bool = True) -> dict[str, Any]:
    """Verify future five-document custody without parsing the documents."""

    if upstream_repo is None:
        upstream_repo = Path(r"C:\Users\z3312\code\Py-bert-agent")
    gate = verify_successor(repo.resolve(), gate_commit, upstream_repo=upstream_repo.resolve(), require_live=False)
    resolved, tree, parents = _commit_facts_checked(repo.resolve(), record_commit, "PB formal record")
    if resolved != record_commit or parents != [gate_commit]:
        raise VerifyError("formal record must be the direct child of the Stage-2 gate")
    changed = _changed_name_status(repo.resolve(), gate_commit, resolved)
    if sorted(changed) != sorted(("A", path) for path in FORMAL_PATHS):
        raise VerifyError("formal record changed paths are not the exact five-file set")
    if require_clean:
        status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
        if status:
            raise VerifyError("formal record checkout is not clean")
    files: dict[str, dict[str, Any]] = {}
    for relative in FORMAL_PATHS:
        _assert_absent(repo, gate_commit, relative, "Stage-2 gate")
        receipt = _assert_regular_blob(repo, resolved, relative)
        if require_live:
            live = _live_file(repo, relative)
            if live != _path_entry(repo, resolved, relative)[1]:
                raise VerifyError(f"formal record live/blob drift: {relative}")
        files[relative] = receipt
    return {"valid": True, "commit": resolved, "tree": tree, "parent": gate_commit, "files": files, "clean": require_clean, "gate": gate}


def _manifest_audit_payload(manifest: dict[str, Any]) -> bytes:
    reports = manifest["reports"]
    lines = [
        f"schema: {AUDIT_SCHEMA}",
        f"status: {manifest['status']}",
        f"gate_commit: {manifest['gate']['commit']}",
        f"prep_commit: {manifest['prep']['commit']}",
        f"report_01_sha256: {reports[0]['sha256']}",
        f"report_02_sha256: {reports[1]['sha256']}",
        f"aggregate_sha256: {manifest['aggregate']['sha256']}",
        "blockers: " + json.dumps(manifest["blockers"], ensure_ascii=True, sort_keys=True),
        "claims: " + json.dumps(manifest["claims"], ensure_ascii=True, sort_keys=True),
        "non_claims: " + json.dumps(manifest["non_claims"], ensure_ascii=True, sort_keys=True),
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def expected_audit(manifest: dict[str, Any]) -> bytes:
    """Return the deterministic audit body bound by the future manifest."""

    return _manifest_audit_payload(manifest)


def _validate_ref(value: Any, label: str, *, path: str | None = None) -> dict[str, Any]:
    item = _exact(value, {"path", "sha256", "bytes"}, label)
    if path is not None and item["path"] != path:
        raise VerifyError(f"{label} path drift")
    aggregate._safe_relative(item["path"], f"{label}.path")
    aggregate._sha(item["sha256"], f"{label}.sha256")
    if type(item["bytes"]) is not int or item["bytes"] <= 0 or item["bytes"] > FILE_LIMIT:
        raise VerifyError(f"{label}.bytes drift")
    return item


def _validate_manifest(value: Any, gate: dict[str, Any], expected_document: dict[str, Any], report_values: list[dict[str, Any]], report_facts: list[dict[str, Any]], aggregate_fact: dict[str, Any], audit_payload: bytes) -> dict[str, Any]:
    _finite(value, "formal manifest")
    manifest = _exact(value, {"aggregate", "audit", "blockers", "candidate", "cases", "claims", "corpus", "fixtures", "gate", "non_claims", "prep", "reports", "schema", "status", "upstream", "version"}, "formal manifest")
    if manifest["schema"] != FORMAL_SCHEMA or manifest["version"] != 1 or manifest["status"] != expected_document["status"]:
        raise VerifyError("formal manifest identity/status drift")
    gate_ref = _exact(manifest["gate"], {"commit", "tree", "parent", "files"}, "formal manifest gate")
    if gate_ref["commit"] != gate["commit"] or gate_ref["tree"] != gate["tree"] or gate_ref["parent"] != ORIGINAL_GATE_COMMIT:
        raise VerifyError("formal manifest gate identity drift")
    if type(gate_ref["files"]) is not list or len(gate_ref["files"]) != len(GATE_PATHS):
        raise VerifyError("formal manifest gate file cardinality drift")
    for actual, bound in zip(gate["files"], gate_ref["files"]):
        _exact(bound, {"path", "blob", "sha256", "bytes"}, "formal manifest gate file")
        if bound != actual:
            raise VerifyError("formal manifest gate file receipt drift")
    if manifest["prep"] != aggregate._prep_binding() or manifest["candidate"] != CANDIDATE or manifest["upstream"] != UPSTREAM or manifest["corpus"] != CORPUS or manifest["fixtures"] != FIXTURES:
        raise VerifyError("formal manifest source binding drift")
    if type(manifest["reports"]) is not list or len(manifest["reports"]) != 2:
        raise VerifyError("formal manifest report cardinality drift")
    for index, ref in enumerate(manifest["reports"]):
        if set(ref) != {"path", "sha256", "bytes", "run_id", "fresh_run_nonce"}:
            raise VerifyError("formal manifest report key set drift")
        _validate_ref({key: ref[key] for key in ("path", "sha256", "bytes")}, f"formal manifest report {index}", path=REPORT_PATHS[index])
        report = report_values[index]
        if ref["sha256"] != report_facts[index]["sha256"] or ref["bytes"] != report_facts[index]["bytes"] or ref["run_id"] != report["run_id"] or ref["fresh_run_nonce"] != report["fresh_run_nonce"]:
            raise VerifyError("formal manifest report cross-field drift")
    aggregate_ref = _validate_ref(manifest["aggregate"], "formal manifest aggregate", path=AGGREGATE_PATH)
    if aggregate_ref != {"path": AGGREGATE_PATH, "sha256": aggregate_fact["sha256"], "bytes": aggregate_fact["bytes"]}:
        raise VerifyError("formal manifest aggregate receipt drift")
    audit_ref = _validate_ref(manifest["audit"], "formal manifest audit", path=AUDIT_PATH)
    if audit_ref["sha256"] != hashlib.sha256(audit_payload).hexdigest() or audit_ref["bytes"] != len(audit_payload):
        raise VerifyError("formal manifest audit receipt drift")
    for key in ("cases", "claims", "blockers"):
        if manifest[key] != expected_document[key]:
            raise VerifyError(f"formal manifest {key} drift")
    if manifest["non_claims"] != NON_CLAIMS:
        raise VerifyError("formal manifest non-claim boundary drift")
    if audit_payload != expected_audit(manifest):
        raise VerifyError("audit/manifest reciprocal binding drift")
    return manifest


def verify_formal_record(repo: Path, upstream_repo: Path, gate_commit: str, record_commit: str) -> dict[str, Any]:
    """Verify a future exact-five-file formal record and recompute its aggregate."""

    repo = repo.resolve()
    record = verify_record_commit(repo, gate_commit, record_commit, upstream_repo=upstream_repo, require_live=True, require_clean=True)
    reports: list[dict[str, Any]] = []
    report_facts: list[dict[str, Any]] = []
    for index, relative in enumerate(REPORT_PATHS):
        report, digest, payload = _load_json(repo / Path(relative))
        expected_report, expected_digest = aggregate.load_report(repo / Path(relative), aggregate.RUN_IDS[index])
        if report != expected_report or digest != expected_digest or digest != hashlib.sha256(payload).hexdigest():
            raise VerifyError("formal report validation drift")
        reports.append(report)
        report_facts.append({"path": relative, "sha256": digest, "bytes": len(payload)})
    expected_document = aggregate.aggregate_documents(
        reports[0],
        report_facts[0]["sha256"],
        reports[1],
        report_facts[1]["sha256"],
        repo / Path(REPORT_PATHS[0]),
        repo / Path(REPORT_PATHS[1]),
        repository_root=repo,
    )
    aggregate_report, aggregate_digest, aggregate_payload = _load_json(repo / Path(AGGREGATE_PATH))
    expected_payload = json.dumps(expected_document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if aggregate_payload != expected_payload or aggregate_report != expected_document:
        raise VerifyError("formal aggregate is not the mechanical recomputation")
    aggregate_fact = {"path": AGGREGATE_PATH, "sha256": aggregate_digest, "bytes": len(aggregate_payload)}
    manifest_payload = _read_regular(repo / Path(MANIFEST_PATH))
    try:
        manifest = yaml.load(manifest_payload.decode("utf-8"), Loader=_StrictLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise VerifyError("formal manifest YAML is invalid") from error
    if type(manifest) is not dict:
        raise VerifyError("formal manifest root is not an object")
    manifest = _validate_manifest(manifest, record["gate"], expected_document, reports, report_facts, aggregate_fact, _read_regular(repo / Path(AUDIT_PATH)))
    del manifest
    return {"valid": True, "status": aggregate_report["status"], "gate_commit": gate_commit, "record_commit": record_commit, "fresh_replays": 2, "aggregate_sha256": aggregate_digest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", "--repo", type=Path, default=ROOT)
    parser.add_argument("--upstream-repository", "--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\Py-bert-agent"))
    parser.add_argument("--gate-commit", required=True)
    parser.add_argument("--successor-commit")
    parser.add_argument("--record-commit")
    args = parser.parse_args()
    try:
        if args.record_commit:
            successor = args.successor_commit or args.gate_commit
            result = verify_formal_record(args.repository, args.upstream_repository, successor, args.record_commit)
        elif args.successor_commit:
            result = verify_successor(args.repository, args.successor_commit, upstream_repo=args.upstream_repository)
        else:
            result = verify_gate(args.repository, args.gate_commit, upstream_repo=args.upstream_repository)
    except (aggregate.AggregateError, VerifyError, OSError, ValueError, TypeError, yaml.YAMLError, UnicodeError) as error:
        result = {"valid": False, "blockers": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
