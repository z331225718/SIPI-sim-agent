"""Verify the immutable PB-01/PB-02 replay preparation gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/baselines/pb-01-02-candidate-matrix-prep.v1.yaml"
AUDIT_PATH = "docs/baselines/audits/2026-08-29-pb-01-02-candidate-matrix-prep.md"
EXPECTED_PARENT = "0d57b36f965588bed3393d2a0a529e4d573a493c"
EXPECTED_PARENT_TREE = "26f2390c90dd9f44753da27041e12b10b8186d55"
EXPECTED_PARENT_PARENT = "af518684936f8656eda61288abe2647f7d909ea4"
EXPECTED_PARENT_ARCHIVE = "97cbfeb61d94c7b473314e407286bde2391c6b83e59324d4faaa873ec41f8354"
EXPECTED_PARENT_ARCHIVE_BYTES = 54661120
EXPECTED_INTERPOSED_COMMIT = "2dea3bbe6039224704f1e07aebc3ebd6c178abed"
EXPECTED_INTERPOSED_TREE = "2d680777f93c86373104c9b294cc833e28ea1cba"
EXPECTED_INTERPOSED_PARENT = "e5d9bfe5fa946ee88b9eb06df1db3b574dd43c05"
EXPECTED_INTERPOSED_ARCHIVE = "5afec4afba5902ee1faf7e054411fd595058b8f95b2b09dc8a81e2be546edb18"
EXPECTED_INTERPOSED_ARCHIVE_BYTES = 55592960
STAGE1_COMMIT = "4042f0d9fdd0846e20ea95e8da7752812a4eea45"
STAGE1_TREE = "8f60a9c35be8e981c6637fbd87cfd5b5a16080fe"
STAGE1_PARENT = "d44581ac8b10adbc8f803bb0292107ae3303e015"
STAGE1_ARCHIVE = "6ec8d67ea7a18fd0063431df88c549ed10b86d6aa6e952bf98466b23254e417c"
STAGE1_ARCHIVE_BYTES = 53504000
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
UPSTREAM_PARENT = "1d6565e5c0398faeef9b757fc6ff21c91d36ccfd"
UPSTREAM_ARCHIVE = "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25"
UPSTREAM_ARCHIVE_BYTES = 132587520
ARCHIVE_LIMIT = 512 * 1024 * 1024
FILE_LIMIT = 16 * 1024 * 1024
GIT_TIMEOUT = 120
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_RELATIVE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}\Z")
RUN_ID_PATTERN = r"^pb-01-02-candidate-run-(01|02)$"
PREP_PATHS = (
    "tools/run_pb_01_02_candidate_matrix.py",
    "tools/verify_pb_01_02_candidate_matrix_prep.py",
    "tools/test_verify_pb_01_02_candidate_matrix_prep.py",
    "docs/baselines/pb-01-02-candidate-matrix-prep.v1.yaml",
    AUDIT_PATH,
)
FORMAL_PATHS = (
    "docs/baselines/pb-01-02-candidate-matrix-run-01.v1.json",
    "docs/baselines/pb-01-02-candidate-matrix-run-02.v1.json",
    "docs/baselines/pb-01-02-candidate-matrix-aggregate.v1.json",
    "docs/baselines/pb-01-02-candidate-matrix-formal.v1.yaml",
    "docs/baselines/audits/2026-08-29-pb-01-02-candidate-matrix-formal.md",
)
EXPECTED_CASES = (
    ("pb01_duo_binary_analytic_line", "PB-01"),
    ("pb02_nrz_impulse", "PB-02"),
    ("pb02_pam4_impulse", "PB-02"),
    ("pb02_duo_binary_impulse", "PB-02"),
    ("pb02_impulse_tx_rx_equalization", "PB-02"),
    ("pb02_impulse_analytic_ctle", "PB-02"),
    ("pb02_impulse_jitter_bathtub_analysis", "PB-02"),
)
EXPECTED_PB01_NAMES = (
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h",
    "chnl_s", "tx_out_s", "ctle_out_s", "dfe_out_s",
    "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p",
)
EXPECTED_PB02_MEMBERS = (
    "channel_impulse_v_per_v.npy", "channel_output_v.npy", "ctle_output_v.npy",
    "rx_ffe_impulse_v_per_v.npy", "rx_filter_impulse_v_per_v.npy", "rx_input_v.npy",
    "rx_output_v.npy", "symbols_v.npy", "time_s.npy",
    "tx_channel_impulse_v_per_v.npy", "tx_waveform_v.npy",
)
EXPECTED_NEW_PATHS = list(PREP_PATHS)
EXPECTED_INTERPOSED_NAME_STATUS = [
    ("A", "docs/baselines/as-06-ngspice-result-parity-aggregate.v2.json"),
    ("A", "docs/baselines/as-06-ngspice-result-parity-run-01.v2.json"),
    ("A", "docs/baselines/as-06-ngspice-result-parity-run-02.v2.json"),
    ("A", "docs/baselines/as-06-ngspice-result-parity.v2.yaml"),
    ("A", "docs/baselines/audits/2026-08-29-as-06-ngspice-result-parity-v2.md"),
    ("A", "docs/baselines/audits/2026-08-29-com-02-04-result-surface-formal.md"),
    ("M", "docs/baselines/audits/2026-08-29-com-02-04-result-surface.md"),
    ("A", "docs/baselines/com-02-04-result-surface-formal-aggregate.v1.json"),
    ("A", "docs/baselines/com-02-04-result-surface-formal.v1.yaml"),
    ("A", "docs/baselines/com-02-result-surface-formal-run1.v1.json"),
    ("A", "docs/baselines/com-02-result-surface-formal-run2.v1.json"),
    ("A", "docs/baselines/com-04-result-surface-formal-run1.v1.json"),
    ("A", "docs/baselines/com-04-result-surface-formal-run2.v1.json"),
    ("A", "tools/aggregate_as_06_ngspice_result_parity.py"),
    ("A", "tools/aggregate_com_02_04_result_surface.py"),
    ("M", "tools/com_direct_semantic_replay.py"),
    ("M", "tools/com_direct_semantic_replay_v2.py"),
    ("A", "tools/run_as_06_ngspice_result_parity.py"),
    ("A", "tools/test_com_direct_semantic_replay_prep.py"),
    ("A", "tools/test_verify_as_06_ngspice_result_parity.py"),
    ("A", "tools/test_verify_as_06_ngspice_result_parity_formal.py"),
    ("A", "tools/test_verify_com_02_04_result_surface_gate.py"),
    ("A", "tools/verify_as_06_ngspice_result_parity.py"),
    ("A", "tools/verify_as_06_ngspice_result_parity_formal.py"),
    ("A", "tools/verify_com_02_04_result_surface_gate.py"),
]
EXPECTED_PROTECTED_PATHS = [
    "crates/sipi-pybert-direct",
    "docs/baselines/pb-01-02-portable-matrix-inputs.v1.json",
    "tools/run_pb_01_02_portable_matrix.py",
    "tools/run_pb_02_direct_replay.py",
]
EXPECTED_FORMAL_CLAIM_KEYS = (
    "candidate_production_implemented", "pb01_selected_array_parity",
    "pb02_complete_typed_output_parity", "global_branch_parity",
    "whole_payload_parity", "release_acceptance", "product_capability_admission",
    "license_decision",
)
EXPECTED_NON_CLAIMS = [
    "no_formal_replay_record",
    "no_aggregate_or_reciprocal_audit_binding",
    "no_pb02_complete_typed_output_parity",
    "no_global_branch_parity",
    "no_release_acceptance",
    "no_product_capability_admission",
    "no_license_decision",
    "no_class_pickle_byte_parity",
    "no_external_ami_ibis_admission",
    "no_s_parameter_fit_or_new_channel_path",
]
REQUIRED_REPORT_FIELDS = (
    "schema", "version", "status", "run_id", "challenge", "fresh_run_nonce",
    "candidate", "upstream", "corpus", "fixtures", "toolchain", "custody",
    "cases", "claims",
)
EXPECTED_BLOCKERS = {
    "pb01_duo_binary_analytic_line": [],
    "pb02_nrz_impulse": ["complete_metadata_drift"],
    "pb02_pam4_impulse": ["complete_metadata_drift"],
    "pb02_duo_binary_impulse": ["complete_metadata_drift"],
    "pb02_impulse_tx_rx_equalization": [
        "candidate_artifact_invalid", "oracle_artifact_invalid", "strict_native_npz_member_set_drift"
    ],
    "pb02_impulse_analytic_ctle": [
        "complete_array_payload_drift", "complete_metadata_drift",
        "local_ctle_impulse_extension_not_in_pinned_native_schema",
    ],
    "pb02_impulse_jitter_bathtub_analysis": [
        "candidate_or_oracle_process_failed", "candidate_output_missing",
        "jitter_span_invalid_for_16_bit_prbs7_fixture", "oracle_output_missing",
    ],
}


class VerifyError(RuntimeError):
    """A preparation gate invariant failed."""


class _StrictLoader(yaml.SafeLoader):
    pass


def _strict_mapping(loader: _StrictLoader, node: yaml.Node, deep: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str or key in result:
            raise VerifyError("manifest mapping keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _strict_mapping)


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise VerifyError(f"{label} key set drift")
    return value


def _finite_tree(value: Any) -> None:
    nodes = 0

    def visit(item: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > 100_000 or depth > 64:
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


def _safe_relative(value: Any, label: str) -> str:
    if type(value) is not str or SAFE_RELATIVE.fullmatch(value) is None:
        raise VerifyError(f"{label} is not a safe relative path")
    path = Path(value)
    if path.is_absolute() or "\\" in value or any(part == ".." for part in value.split("/")):
        raise VerifyError(f"{label} escapes its repository")
    return value


def validate_future_report_header(report: Any) -> dict[str, Any]:
    """Validate the fixed run/challenge envelope without admitting parity."""

    if type(report) is not dict:
        raise VerifyError("future report is not a mapping")
    missing = [key for key in REQUIRED_REPORT_FIELDS if key not in report]
    if missing:
        raise VerifyError(f"future report is missing required fields: {','.join(missing)}")
    if report["schema"] != "sipi.pb-01-02-candidate-matrix-replay.v1" or report["version"] != 1:
        raise VerifyError("future report schema/version drift")
    run_id = report["run_id"]
    if type(run_id) is not str or re.fullmatch(RUN_ID_PATTERN, run_id) is None:
        raise VerifyError("future report run_id drift")
    run_index = ("pb-01-02-candidate-run-01", "pb-01-02-candidate-run-02").index(run_id) + 1
    expected_challenge = {
        "id": "pb-01-02-candidate-matrix-v1", "run_index": run_index, "run_count": 2,
        "fresh_archive_replay": True, "nonce_required": True, "report_sha256_required": True,
    }
    if report["challenge"] != expected_challenge:
        raise VerifyError("future report challenge drift")
    if type(report["fresh_run_nonce"]) is not str or HEX64.fullmatch(report["fresh_run_nonce"]) is None:
        raise VerifyError("future report nonce drift")
    return {"run_id": run_id, "challenge": expected_challenge, "nonce": report["fresh_run_nonce"]}


def _hash(value: Any, label: str, *, allow_zero: bool = False) -> str:
    if type(value) is not str or HEX64.fullmatch(value) is None or (not allow_zero and value == "0" * 64):
        raise VerifyError(f"{label} is not a valid SHA-256")
    return value


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    try:
        result = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise VerifyError(f"git command failed: {' '.join(args)}") from error
    return result.stdout if binary else result.stdout.decode("ascii").strip()


def _git_exit(repo: Path, *args: str) -> int:
    try:
        result = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise VerifyError(f"git command failed: {' '.join(args)}") from error
    return result.returncode


def _bounded_archive(repo: Path, commit: str) -> tuple[str, int]:
    try:
        process = subprocess.Popen(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), "archive", "--format=tar", commit],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise VerifyError("cannot start bounded git archive") from error
    assert process.stdout is not None and process.stderr is not None
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = process.stdout.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > ARCHIVE_LIMIT:
                process.kill()
                process.wait(timeout=GIT_TIMEOUT)
                raise VerifyError("git archive exceeds the bounded archive budget")
            digest.update(chunk)
        stderr = process.stderr.read(4 * 1024 * 1024 + 1)
        if len(stderr) > 4 * 1024 * 1024:
            process.kill()
            raise VerifyError("git archive stderr exceeds the capture budget")
        try:
            return_code = process.wait(timeout=GIT_TIMEOUT)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            raise VerifyError("git archive timed out") from error
    finally:
        process.stdout.close()
        process.stderr.close()
    if return_code != 0:
        raise VerifyError("git archive returned a non-zero status")
    return digest.hexdigest(), total


def _commit_facts(repo: Path, commit: str, label: str) -> tuple[str, str, list[str]]:
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    parents = str(_git(repo, "show", "-s", "--format=%P", resolved)).split()
    if not HEX40.fullmatch(resolved) or not HEX40.fullmatch(tree):
        raise VerifyError(f"{label} commit/tree is malformed")
    return resolved, tree, parents


def _blob(repo: Path, commit: str, relative: str) -> tuple[str, bytes]:
    entry = _git(repo, "ls-tree", "-z", commit, "--", relative, binary=True)
    assert isinstance(entry, bytes)
    if not entry:
        raise VerifyError(f"missing Git path: {relative}")
    record = entry.rstrip(b"\0")
    try:
        header, path = record.split(b"\t", 1)
    except ValueError as error:
        raise VerifyError(f"malformed Git tree entry: {relative}") from error
    fields = header.split()
    if len(fields) != 3 or fields[0] != b"100644" or fields[1] != b"blob" or path.decode("utf-8") != relative:
        raise VerifyError(f"Git path is not an exact regular blob: {relative}")
    blob = fields[2].decode("ascii")
    if HEX40.fullmatch(blob) is None:
        raise VerifyError(f"Git blob id is malformed: {relative}")
    size_text = str(_git(repo, "cat-file", "-s", blob))
    if not size_text.isdigit() or int(size_text) > FILE_LIMIT:
        raise VerifyError(f"Git blob exceeds the bounded file budget: {relative}")
    payload = _git(repo, "cat-file", "blob", blob, binary=True)
    assert isinstance(payload, bytes)
    if len(payload) != int(size_text):
        raise VerifyError(f"Git blob size drift: {relative}")
    return blob, payload


def _live_file(repo: Path, relative: str) -> bytes:
    path = repo / Path(relative)
    try:
        info = os.lstat(path)
    except OSError as error:
        raise VerifyError(f"live preparation file is unavailable: {relative}") from error
    if not stat.S_ISREG(info.st_mode) or os.path.islink(path) or int(info.st_nlink) < 1:
        raise VerifyError(f"live preparation file is not a regular non-link: {relative}")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise VerifyError(f"live preparation file cannot be read: {relative}") from error
    if len(payload) > FILE_LIMIT:
        raise VerifyError(f"live preparation file exceeds budget: {relative}")
    return payload


def _verify_identity(repo: Path, item: dict[str, Any], label: str, *, expected_parent: str | None = None) -> dict[str, Any]:
    commit = item["commit"]
    resolved, tree, parents = _commit_facts(repo, commit, label)
    if resolved != commit or tree != item["tree"]:
        raise VerifyError(f"{label} commit/tree drift")
    bound_parent = expected_parent if expected_parent is not None else item.get("parent")
    if bound_parent is not None and parents != [bound_parent]:
        raise VerifyError(f"{label} parent drift")
    archive_sha, archive_bytes = _bounded_archive(repo, resolved)
    if archive_sha != item["archive_sha256"] or archive_bytes != item["archive_bytes"]:
        raise VerifyError(f"{label} bounded archive drift")
    return {"commit": resolved, "tree": tree, "parents": parents, "archive_sha256": archive_sha, "archive_bytes": archive_bytes}


def _verify_interposed_checkpoint(repo: Path, document: dict[str, Any]) -> dict[str, Any]:
    checkpoint = document["interposed_checkpoint"]
    resolved, tree, parents = _commit_facts(repo, checkpoint["to_commit"], "interposed checkpoint")
    if resolved != EXPECTED_INTERPOSED_COMMIT or tree != EXPECTED_INTERPOSED_TREE or parents != [EXPECTED_INTERPOSED_PARENT]:
        raise VerifyError("interposed checkpoint commit/tree/parent drift")
    ancestor = _git_exit(repo, "merge-base", "--is-ancestor", EXPECTED_PARENT, resolved)
    if ancestor != 0:
        raise VerifyError("fixed production candidate is not an ancestor of the interposed checkpoint")
    archive_sha, archive_bytes = _bounded_archive(repo, resolved)
    if archive_sha != checkpoint["to_archive_sha256"] or archive_bytes != checkpoint["to_archive_bytes"]:
        raise VerifyError("interposed checkpoint archive drift")
    raw = _git(repo, "diff", "--name-status", "-z", EXPECTED_PARENT, resolved, "--", binary=True)
    assert isinstance(raw, bytes)
    fields = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    if len(fields) % 2:
        raise VerifyError("interposed checkpoint name-status encoding is malformed")
    actual = [(fields[index], fields[index + 1]) for index in range(0, len(fields), 2)]
    expected = [(item["status"], item["path"]) for item in checkpoint["exact_name_status"]]
    if actual != expected:
        raise VerifyError("interposed checkpoint exact name-status drift")
    for relative in checkpoint["protected_paths"]:
        if _git_exit(repo, "diff", "--quiet", EXPECTED_PARENT, resolved, "--", relative) != 0:
            raise VerifyError(f"protected PB path drifted across interposed checkpoint: {relative}")
    return {"from_commit": EXPECTED_PARENT, "to_commit": resolved, "to_tree": tree, "exact_name_status": actual, "protected_blobs_unchanged": True, "archive_sha256": archive_sha, "archive_bytes": archive_bytes}


def _verify_manifest_shape(document: Any) -> dict[str, Any]:
    _finite_tree(document)
    root = _exact(
        document,
        {
            "schema", "version", "status", "scope", "candidate",
            "interposed_checkpoint", "prep_parent",
            "historical_stage1_preparation", "upstream", "corpus", "fixtures",
            "cases", "comparator_policy", "claims", "custody_policy", "harness",
            "toolchain", "future_replay", "audit", "non_claims",
        },
        "manifest",
    )
    if root["schema"] != "sipi.pb-01-02-candidate-matrix-prep.v1" or root["version"] != 1 or root["status"] != "preparation_only_pending_immutable_harness_commit":
        raise VerifyError("manifest identity/status drift")
    scope = _exact(root["scope"], {"workflow", "product_crate", "purpose", "production_changes", "new_domain_functionality", "formal_replay_generated", "release_acceptance", "global_branch_parity", "codec_byte_parity"}, "scope")
    expected_scope = {
        "workflow": "PB-01/PB-02", "product_crate": "crates/sipi-pybert-direct",
        "purpose": "bind a future two-run immutable replay without recording formal evidence",
        "production_changes": False, "new_domain_functionality": False,
        "formal_replay_generated": False, "release_acceptance": False,
        "global_branch_parity": False, "codec_byte_parity": False,
    }
    if scope != expected_scope:
        raise VerifyError("scope cross-field drift")
    parent = _exact(root["candidate"], {"commit", "tree", "parent", "archive_sha256", "archive_bytes", "archive_limit_bytes", "archive_mode"}, "candidate")
    if parent != {
        "commit": EXPECTED_PARENT, "tree": EXPECTED_PARENT_TREE, "parent": EXPECTED_PARENT_PARENT,
        "archive_sha256": EXPECTED_PARENT_ARCHIVE, "archive_bytes": EXPECTED_PARENT_ARCHIVE_BYTES,
        "archive_limit_bytes": ARCHIVE_LIMIT, "archive_mode": "git_archive_format_tar",
    }:
        raise VerifyError("candidate binding drift")
    checkpoint = _exact(root["interposed_checkpoint"], {"from_commit", "from_tree", "to_commit", "to_tree", "to_parent", "to_archive_sha256", "to_archive_bytes", "archive_limit_bytes", "archive_mode", "exact_name_status", "protected_paths", "protected_blobs_unchanged"}, "interposed checkpoint")
    if checkpoint != {
        "from_commit": EXPECTED_PARENT, "from_tree": EXPECTED_PARENT_TREE,
        "to_commit": EXPECTED_INTERPOSED_COMMIT, "to_tree": EXPECTED_INTERPOSED_TREE,
        "to_parent": EXPECTED_INTERPOSED_PARENT, "to_archive_sha256": EXPECTED_INTERPOSED_ARCHIVE,
        "to_archive_bytes": EXPECTED_INTERPOSED_ARCHIVE_BYTES, "archive_limit_bytes": ARCHIVE_LIMIT,
        "archive_mode": "git_archive_format_tar",
        "exact_name_status": [{"status": status, "path": path} for status, path in EXPECTED_INTERPOSED_NAME_STATUS],
        "protected_paths": EXPECTED_PROTECTED_PATHS, "protected_blobs_unchanged": True,
    }:
        raise VerifyError("interposed checkpoint binding drift")
    prep_parent = _exact(root["prep_parent"], {"commit", "tree", "parent", "archive_sha256", "archive_bytes", "archive_limit_bytes", "archive_mode", "exact_new_paths", "exact_new_mode", "first_introduction_required", "raw_blob_live_equality_required", "unrelated_worktree_changes_allowed"}, "preparation parent")
    if prep_parent != {
        "commit": EXPECTED_INTERPOSED_COMMIT, "tree": EXPECTED_INTERPOSED_TREE, "parent": EXPECTED_INTERPOSED_PARENT,
        "archive_sha256": EXPECTED_INTERPOSED_ARCHIVE, "archive_bytes": EXPECTED_INTERPOSED_ARCHIVE_BYTES,
        "archive_limit_bytes": ARCHIVE_LIMIT, "archive_mode": "git_archive_format_tar",
        "exact_new_paths": EXPECTED_NEW_PATHS, "exact_new_mode": "100644",
        "first_introduction_required": True, "raw_blob_live_equality_required": True,
        "unrelated_worktree_changes_allowed": True,
    }:
        raise VerifyError("preparation parent binding drift")
    historical = _exact(root["historical_stage1_preparation"], {"commit", "tree", "parent", "archive_sha256", "archive_bytes", "exact_paths", "role"}, "historical preparation")
    if historical != {
        "commit": STAGE1_COMMIT, "tree": STAGE1_TREE, "parent": STAGE1_PARENT,
        "archive_sha256": STAGE1_ARCHIVE, "archive_bytes": STAGE1_ARCHIVE_BYTES,
        "exact_paths": [
            "docs/baselines/pb-01-02-portable-matrix-inputs.v1.json",
            "tools/aggregate_pb_01_02_portable_matrix.py", "tools/run_pb_01_02_portable_matrix.py",
            "tools/test_verify_pb_01_02_portable_matrix.py", "tools/verify_pb_01_02_portable_matrix.py",
        ],
        "role": "historical_bounded_matrix_primitives_only",
    }:
        raise VerifyError("historical preparation binding drift")
    upstream = _exact(root["upstream"], {"repository_label", "commit", "tree", "parent", "archive_sha256", "archive_bytes", "archive_limit_bytes", "archive_mode", "execution"}, "upstream")
    if upstream != {
        "repository_label": "pybert-agent", "commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE,
        "parent": UPSTREAM_PARENT, "archive_sha256": UPSTREAM_ARCHIVE, "archive_bytes": UPSTREAM_ARCHIVE_BYTES,
        "archive_limit_bytes": ARCHIVE_LIMIT, "archive_mode": "git_archive_format_tar",
        "execution": "uv_frozen_offline_from_clean_archive",
    }:
        raise VerifyError("upstream binding drift")
    corpus = _exact(root["corpus"], {"path", "bytes", "sha256", "source", "schema"}, "corpus")
    if corpus != {"path": "docs/baselines/pb-01-02-portable-matrix-inputs.v1.json", "bytes": 5339, "sha256": "77d6db2f34de256bea69888122e86281ba578a71da1a1719b790f9b9ed332ddb", "source": "candidate_archive", "schema": "sipi.pb-01-02-portable-matrix-inputs.v1"}:
        raise VerifyError("corpus binding drift")
    fixtures = _exact(root["fixtures"], {"PB-01", "PB-02"}, "fixtures")
    expected_fixtures = {
        "PB-01": {"path": "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml", "bytes": 1171, "sha256": "d63bb7ab3466ae70406cd2a555ae5a95cda1264021fed8fb1cdca85da961cc48", "source": "candidate_archive"},
        "PB-02": {"path": "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json", "bytes": 1245, "sha256": "5bcd0b905f8a7f0ec5e2b7c3761a998e9553ac24a71b54f8b0d4e8e84261ea13", "source": "candidate_archive"},
    }
    for lane, item in fixtures.items():
        if _exact(item, {"path", "bytes", "sha256", "source"}, f"fixture {lane}") != expected_fixtures[lane]:
            raise VerifyError(f"fixture binding drift: {lane}")
    cases = root["cases"]
    if type(cases) is not list or len(cases) != len(EXPECTED_CASES):
        raise VerifyError("case list cardinality drift")
    for item, (expected_id, expected_lane) in zip(cases, EXPECTED_CASES):
        case = _exact(item, {"id", "lane", "patch_sha256", "derived_bytes", "derived_sha256", "diagnostic_status", "diagnostic_blockers", "comparator"}, f"case {expected_id}")
        if case["id"] != expected_id or case["lane"] != expected_lane:
            raise VerifyError("case order/lane drift")
        _hash(case["patch_sha256"], f"{expected_id}.patch_sha256")
        _hash(case["derived_sha256"], f"{expected_id}.derived_sha256")
        if type(case["derived_bytes"]) is not int or case["derived_bytes"] <= 0 or case["diagnostic_status"] not in {"passed_selected_arrays", "blocked"}:
            raise VerifyError(f"case scalar type drift: {expected_id}")
        if type(case["diagnostic_blockers"]) is not list or case["diagnostic_blockers"] != EXPECTED_BLOCKERS[expected_id]:
            raise VerifyError(f"case blocker provenance drift: {expected_id}")
        expected_comparator = "selected_numeric_arrays" if expected_lane == "PB-01" else "strict_complete_metadata_and_logical_npz"
        if case["comparator"] != expected_comparator:
            raise VerifyError(f"case comparator drift: {expected_id}")
    comparator = _exact(root["comparator_policy"], {"PB-01", "PB-02"}, "comparator policy")
    pb01 = _exact(comparator["PB-01"], {"kind", "names", "atol", "rtol", "codec_byte_parity"}, "PB-01 comparator")
    if pb01 != {"kind": "selected_numeric_arrays", "names": list(EXPECTED_PB01_NAMES), "atol": 0.0000011, "rtol": 0.0, "codec_byte_parity": False}:
        raise VerifyError("PB-01 comparator policy drift")
    pb02 = _exact(comparator["PB-02"], {"kind", "metadata_projection", "metadata_drop_allowed", "npz_member_policy", "npz_members", "logical_dtype", "wrapper_metadata_silently_ignored"}, "PB-02 comparator")
    if pb02 != {"kind": "strict_complete_metadata_and_logical_npz", "metadata_projection": "complete_normalized_metadata", "metadata_drop_allowed": False, "npz_member_policy": "exact_fixed_member_set", "npz_members": list(EXPECTED_PB02_MEMBERS), "logical_dtype": "float64", "wrapper_metadata_silently_ignored": False}:
        raise VerifyError("PB-02 comparator policy drift")
    claims = _exact(root["claims"], set(EXPECTED_FORMAL_CLAIM_KEYS), "claims")
    if claims != {"candidate_production_implemented": True, "pb01_selected_array_parity": False, "pb02_complete_typed_output_parity": False, "global_branch_parity": False, "whole_payload_parity": False, "release_acceptance": False, "product_capability_admission": False, "license_decision": False}:
        raise VerifyError("claim boundary drift")
    custody = _exact(root["custody_policy"], {"candidate_materialization", "upstream_materialization", "oracle_materialization", "candidate_worktree_overlay", "upstream_worktree_overlay", "derived_inputs_from_archived_base", "output_root_outside_source_repositories", "fresh_work_root_per_run", "work_root_preexisting_content_allowed", "path_redacted_records", "unsafe_relative_fixture_rejected", "symlink_and_reparse_escape_rejected", "source_inventory_pre_post_equal_required", "archive_limit_bytes", "file_limit_bytes", "report_limit_bytes"}, "custody policy")
    expected_custody = {"candidate_materialization": "clean_git_archive_only", "upstream_materialization": "clean_git_archive_only", "oracle_materialization": "separate_copy_of_upstream_archive", "candidate_worktree_overlay": False, "upstream_worktree_overlay": False, "derived_inputs_from_archived_base": True, "output_root_outside_source_repositories": True, "fresh_work_root_per_run": True, "work_root_preexisting_content_allowed": False, "path_redacted_records": True, "unsafe_relative_fixture_rejected": True, "symlink_and_reparse_escape_rejected": True, "source_inventory_pre_post_equal_required": True, "archive_limit_bytes": ARCHIVE_LIMIT, "file_limit_bytes": FILE_LIMIT, "report_limit_bytes": ARCHIVE_LIMIT}
    if custody != expected_custody:
        raise VerifyError("custody policy drift")
    harness = _exact(root["harness"], {"source_mode", "immutable_harness_commit", "runner", "verifier", "tests", "legacy_matrix_primitives", "native_custody_primitives"}, "harness")
    if harness["source_mode"] != "working_tree_content_hash_pending_prep_commit" or harness["immutable_harness_commit"] is not None:
        raise VerifyError("harness state drift")
    for key in ("runner", "verifier", "tests", "legacy_matrix_primitives", "native_custody_primitives"):
        ref = _exact(harness[key], {"path", "sha256"}, f"harness {key}")
        _safe_relative(ref["path"], f"harness {key}.path")
        _hash(ref["sha256"], f"harness {key}.sha256")
    if harness["runner"]["path"] != "tools/run_pb_01_02_candidate_matrix.py" or harness["verifier"]["path"] != "tools/verify_pb_01_02_candidate_matrix_prep.py" or harness["tests"]["path"] != "tools/test_verify_pb_01_02_candidate_matrix_prep.py" or harness["legacy_matrix_primitives"]["path"] != "tools/run_pb_01_02_portable_matrix.py" or harness["native_custody_primitives"]["path"] != "tools/run_pb_02_direct_replay.py":
        raise VerifyError("harness path binding drift")
    toolchain = _exact(root["toolchain"], {"mode", "timeout_seconds", "rust_wrappers_cleared", "cargo_offline", "uv_frozen_offline", "roles"}, "toolchain")
    if toolchain["mode"] != "explicit_resolved_path_with_path_free_identity" or toolchain["timeout_seconds"] != 1200 or toolchain["rust_wrappers_cleared"] is not True or toolchain["cargo_offline"] is not True or toolchain["uv_frozen_offline"] is not True:
        raise VerifyError("toolchain policy drift")
    roles = _exact(toolchain["roles"], {"cargo", "rustc", "uv", "link"}, "toolchain roles")
    expected_toolchain = {
        "cargo": ("cargo.exe", "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7", "e11749bef57e0f2056f4a11bb00871623d935559227c35a7b373e983f1eea6bb", "allowed_and_recorded"),
        "rustc": ("rustc.exe", "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7", "d6dec673ca010f6a7d90aa3f4a896ad9d88b66b8fe090296c298eddfe9a406db", "allowed_and_recorded"),
        "uv": ("uv.exe", "5a7ec85884c2ccb1be560cb8fac3eb890df1adf49bfcc070a270ba70401bdd68", "ab0d29803cb58959acc6cf64650fb215c72c2989b94fb6f9de5f22814ceca82d", "require_regular_nonlink"),
        "link": ("link.exe", "ca11e6c45debd34bf652dfe984c5360a531a005ed78bf72852330c9c2590cf0d", "f5967e8fed8a0058b2813fa1c42f18645e258cb02d8817bef7760e09d0441412", "require_regular_nonlink"),
    }
    for role, expected in expected_toolchain.items():
        item = _exact(roles[role], {"executable", "file_sha256", "version_sha256", "version_exit", "path_redacted", "hardlink_policy"}, f"toolchain {role}")
        if item != {"executable": expected[0], "file_sha256": expected[1], "version_sha256": expected[2], "version_exit": 0, "path_redacted": True, "hardlink_policy": expected[3]}:
            raise VerifyError(f"toolchain identity drift: {role}")
    future = _exact(root["future_replay"], {"run_count", "run_ids", "run_id_pattern", "nonce_hex_bytes", "nonces_distinct_required", "report_sha256_distinct_required", "challenge", "required_report_fields", "formal_record_not_created_in_prep", "formal_paths"}, "future replay")
    expected_future = {"run_count": 2, "run_ids": ["pb-01-02-candidate-run-01", "pb-01-02-candidate-run-02"], "run_id_pattern": RUN_ID_PATTERN, "nonce_hex_bytes": 32, "nonces_distinct_required": True, "report_sha256_distinct_required": True, "challenge": {"id": "pb-01-02-candidate-matrix-v1", "run_count": 2, "fresh_archive_replay": True, "nonce_required": True, "report_sha256_required": True}, "required_report_fields": ["schema", "version", "status", "run_id", "challenge", "fresh_run_nonce", "candidate", "upstream", "corpus", "fixtures", "toolchain", "custody", "cases", "claims"], "formal_record_not_created_in_prep": True, "formal_paths": list(FORMAL_PATHS)}
    if future != expected_future:
        raise VerifyError("future replay/challenge binding drift")
    audit = _exact(root["audit"], {"path", "sha256", "bytes", "status"}, "audit")
    _hash(audit["sha256"], "audit.sha256")
    if audit != {"path": AUDIT_PATH, "sha256": audit["sha256"], "bytes": audit["bytes"], "status": "preparation_only"} or type(audit["bytes"]) is not int or audit["bytes"] <= 0:
        raise VerifyError("audit binding/type drift")
    if root["non_claims"] != EXPECTED_NON_CLAIMS:
        raise VerifyError("non-claim boundary drift")
    return root


def _verify_corpus_and_fixtures(repo: Path, document: dict[str, Any]) -> None:
    if str(ROOT / "tools") not in sys.path:
        sys.path.insert(0, str(ROOT / "tools"))
    from run_pb_01_02_candidate_matrix import _case_patch, _derive_input
    from run_pb_01_02_portable_matrix import load_corpus

    commit = document["candidate"]["commit"]
    _, corpus_payload = _blob(repo, commit, document["corpus"]["path"])
    if len(corpus_payload) != document["corpus"]["bytes"] or hashlib.sha256(corpus_payload).hexdigest() != document["corpus"]["sha256"]:
        raise VerifyError("candidate archived corpus hash/length drift")
    corpus = load_corpus(corpus_payload)
    if corpus["base_fixtures"] != {lane: document["fixtures"][lane]["path"] for lane in ("PB-01", "PB-02")}:
        raise VerifyError("corpus/fixture path cross-field drift")
    base_payloads: dict[str, bytes] = {}
    for lane in ("PB-01", "PB-02"):
        ref = document["fixtures"][lane]
        _, payload = _blob(repo, commit, ref["path"])
        if len(payload) != ref["bytes"] or hashlib.sha256(payload).hexdigest() != ref["sha256"]:
            raise VerifyError(f"candidate archived fixture hash/length drift: {lane}")
        base_payloads[lane] = payload
    for case in document["cases"]:
        lane, patch = _case_patch(corpus, case["id"])
        derived = _derive_input(base_payloads[lane], patch, lane)
        canonical_patch = json.dumps(patch, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if hashlib.sha256(canonical_patch).hexdigest() != case["patch_sha256"] or len(derived) != case["derived_bytes"] or hashlib.sha256(derived).hexdigest() != case["derived_sha256"]:
            raise VerifyError(f"derived input provenance drift: {case['id']}")


def _verify_prep_commit(repo: Path, prep_commit: str, manifest: dict[str, Any]) -> dict[str, Any]:
    resolved, tree, parents = _commit_facts(repo, prep_commit, "preparation commit")
    if parents != [EXPECTED_INTERPOSED_COMMIT]:
        raise VerifyError("preparation commit must be a direct child of the fixed interposed checkpoint")
    changed = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", EXPECTED_INTERPOSED_COMMIT, resolved, "--", binary=True)
    assert isinstance(changed, bytes)
    paths = tuple(sorted(item.decode("utf-8") for item in changed.split(b"\0") if item))
    if paths != tuple(sorted(PREP_PATHS)):
        raise VerifyError("preparation commit changed paths are not the exact five-file set")
    for relative in PREP_PATHS:
        parent_entry = _git(repo, "ls-tree", "-z", EXPECTED_INTERPOSED_COMMIT, "--", relative, binary=True)
        assert isinstance(parent_entry, bytes)
        if parent_entry:
            raise VerifyError(f"preparation path was not first introduced: {relative}")
        blob, payload = _blob(repo, resolved, relative)
        live = _live_file(repo, relative)
        if live != payload:
            raise VerifyError(f"preparation raw Git blob/live file drift: {relative}")
        if hashlib.sha256(payload).hexdigest() != manifest["harness"]["runner"]["sha256"] and relative == manifest["harness"]["runner"]["path"]:
            raise VerifyError("runner blob/hash binding drift")
    for relative in FORMAL_PATHS:
        present = _git(repo, "ls-tree", "-r", "-z", resolved, "--", relative, binary=True)
        assert isinstance(present, bytes)
        if present:
            raise VerifyError(f"formal record path is present in preparation commit: {relative}")
    archive_sha, archive_bytes = _bounded_archive(repo, resolved)
    return {"commit": resolved, "tree": tree, "parent": EXPECTED_INTERPOSED_COMMIT, "archive_sha256": archive_sha, "archive_bytes": archive_bytes, "changed_paths": list(paths), "first_introduction": True, "raw_live_equal": True, "formal_paths_absent": True}


def _verify_live_bindings(repo: Path, document: dict[str, Any]) -> dict[str, Any]:
    for key in ("runner", "verifier", "tests", "legacy_matrix_primitives", "native_custody_primitives"):
        ref = document["harness"][key]
        payload = _live_file(repo, ref["path"])
        if hashlib.sha256(payload).hexdigest() != ref["sha256"]:
            raise VerifyError(f"live harness hash drift: {key}")
    try:
        import run_pb_01_02_candidate_matrix as runner

        if tuple(runner.FUTURE_RUN_IDS) != ("pb-01-02-candidate-run-01", "pb-01-02-candidate-run-02") or runner.CHALLENGE_ID != "pb-01-02-candidate-matrix-v1":
            raise VerifyError("runner fixed challenge constants drift")
        for run_id, index in zip(runner.FUTURE_RUN_IDS, (1, 2)):
            challenge = runner._challenge_for_run_id(run_id)
            if challenge != {"id": "pb-01-02-candidate-matrix-v1", "run_index": index, "run_count": 2, "fresh_archive_replay": True, "nonce_required": True, "report_sha256_required": True}:
                raise VerifyError("runner challenge projection drift")
    except (ImportError, AttributeError, RuntimeError) as error:
        raise VerifyError("runner fixed challenge contract is unavailable") from error
    audit = document["audit"]
    audit_payload = _live_file(repo, audit["path"])
    if len(audit_payload) != audit["bytes"] or hashlib.sha256(audit_payload).hexdigest() != audit["sha256"]:
        raise VerifyError("live audit hash/length drift")
    for relative in FORMAL_PATHS:
        if os.path.lexists(repo / Path(relative)):
            raise VerifyError(f"formal record path is present in the preparation worktree: {relative}")
    return {"harness_live": True, "audit_live": True, "formal_paths_absent": True}


def _verify_git_paths_absent(repo: Path, commit: str, paths: tuple[str, ...], label: str) -> None:
    for relative in paths:
        present = _git(repo, "ls-tree", "-r", "-z", commit, "--", relative, binary=True)
        assert isinstance(present, bytes)
        if present:
            raise VerifyError(f"{label} contains a formal record path: {relative}")


def verify(
    document: dict[str, Any],
    repo: Path = ROOT,
    upstream_repo: Path | None = None,
    *,
    prep_commit: str | None = None,
    require_sources: bool = True,
    require_prep_commit: bool = False,
) -> dict[str, Any]:
    try:
        manifest = _verify_manifest_shape(document)
        live: dict[str, Any] = {}
        if require_sources:
            _verify_identity(repo, manifest["candidate"], "fixed production candidate")
            _verify_git_paths_absent(repo, EXPECTED_PARENT, FORMAL_PATHS, "fixed production parent")
            interposed = _verify_interposed_checkpoint(repo, manifest)
            _verify_identity(repo, manifest["prep_parent"], "fixed preparation parent")
            _verify_identity(repo, manifest["historical_stage1_preparation"], "historical Stage-1 preparation", expected_parent=STAGE1_PARENT)
            if upstream_repo is None:
                raise VerifyError("upstream repository is required for source verification")
            _verify_identity(upstream_repo, manifest["upstream"], "pinned upstream", expected_parent=UPSTREAM_PARENT)
            _verify_corpus_and_fixtures(repo, manifest)
            live = {**_verify_live_bindings(repo, manifest), "interposed_checkpoint": interposed}
        prep: dict[str, Any] | None = None
        if require_prep_commit and not prep_commit:
            raise VerifyError("--prep-commit is required for the immutable preparation gate")
        if prep_commit:
            prep = _verify_prep_commit(repo, prep_commit, manifest)
        return {"valid": True, "status": manifest["status"], "prep_commit": prep, "source_bindings": live, "formal_record_absent": True}
    except (VerifyError, OSError, ValueError, TypeError, yaml.YAMLError, UnicodeError) as error:
        return {"valid": False, "blockers": [str(error)]}


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise VerifyError("cannot load preparation manifest") from error
    if type(value) is not dict:
        raise VerifyError("preparation manifest root is not a mapping")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\Py-bert-agent"))
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--prep-commit", required=True)
    args = parser.parse_args()
    try:
        document = load_manifest(args.manifest)
        result = verify(document, args.repo.resolve(), args.upstream_repo.resolve(), prep_commit=args.prep_commit, require_prep_commit=True)
    except (VerifyError, OSError, UnicodeError, yaml.YAMLError) as error:
        result = {"valid": False, "blockers": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
