"""Fail-closed verifier for the PB-03 physical payload member inventory."""

from __future__ import annotations

import hashlib
import argparse
import functools
import json
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = "docs/baselines/pb-03-payload-inventory.v1.yaml"
MEMBER_MAP_PATH = "docs/baselines/pb-03-payload-member-map.v1.json"
CANDIDATE_COMMIT = "7859a72e00a7a2f4c7699f935e1cee98a3f0c1e6"
CANDIDATE_TREE = "356cc526062817d28a8edd22f5c4325ce0a75ee0"
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HOST_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/Users/|/home/|\\\\Users\\)")
AUDIT_ANCHOR = re.compile(r"^(member_map|verifier|mutation_test|source_map|notice)_sha256: [0-9a-f]{64}$", re.MULTILINE)
EXPECTED_AUDIT_NORMALIZED = """# PB-03 sim-rust payload integrity audit

This record binds a caller-recorded member observation. It is not execution
provenance, replay custody, an oracle attestation, whole-payload parity, or a
release result.

Candidate authority is commit `7859a72e00a7a2f4c7699f935e1cee98a3f0c1e6`,
tree `356cc526062817d28a8edd22f5c4325ce0a75ee0`. The Git archive receipt is
statically recomputed from that object. The NPZ and per-member receipts are
caller-recorded integrity observations; this gate does not bind the runner,
toolchain, output directory, or reconstruction procedure that produced them.

The member graph records candidate 140, oracle 150, 127 exact, 11 shared hash
drift, 2 candidate-only, and 12 oracle-only. Removing the 27 members whose
producer is `pb03_serializer_projection` mechanically derives the before graph:
candidate 113, oracle 150, 107 exact, 4 shared drift, 2 candidate-only, and 39
oracle-only.

Seven response members are only logical f64 hash drift. Their source, dtype,
shape, count, and order must match across candidate and oracle. No ULP bound is
claimed. Eye, contour, AMI, IBIS, DLL, GetWave, vendor-noise, class-pickle,
product, global-closure, and release claims remain blocked.

The Git gate binds the full gate commit/tree and the verifier/test blobs. The
record HEAD must be its strict descendant, while candidate `7859a72e` must be
the gate ancestor. This is an integrity gate, not a signature or provenance
claim.

member_map_sha256: <bound>
verifier_sha256: <bound>
mutation_test_sha256: <bound>
source_map_sha256: <bound>
notice_sha256: <bound>
"""
COUNTS = {
    "candidate_count": 140,
    "oracle_count": 150,
    "exact_count": 127,
    "shared_drift_count": 11,
    "candidate_only_count": 2,
    "oracle_only_count": 12,
}
BEFORE_COUNTS = {
    "candidate_count": 113,
    "oracle_count": 150,
    "exact_count": 107,
    "shared_drift_count": 4,
    "candidate_only_count": 2,
    "oracle_only_count": 39,
}
PRODUCTION_FILES = {
    "crates/sipi-pybert-direct/NOTICE-PYBERT-PB03-PAYLOAD.md": {"blob": "41fa6122a2bed6c2eb8cead8ec6ba0e54b8a0abd", "bytes": 934, "sha256": "cc193bce808949987fa5764bbb5e3539f304816e2f9bbb425bf712c558ea6938"},
    "crates/sipi-pybert-direct/SOURCE-MAP-PB03-PAYLOAD.md": {"blob": "6b53226c3214c25b678d858c9c076e53d2e0c866", "bytes": 3826, "sha256": "19b2546170d8a771d6b5b06c8115fbae3094f34a27e9284017a360d171596c88"},
    "crates/sipi-pybert-direct/src/legacy_runtime.rs": {"blob": "e216e50cc7f847c08816d1777265dea2c5e92a23", "bytes": 131649, "sha256": "e3fe8bc7b8626d26e78109a9a6c981e2cba30fa613889e2e317372694ebc539e"},
    "crates/sipi-pybert-direct/src/workflows.rs": {"blob": "110d4fe01b6994b3d4fe58a7495167350b57154c", "bytes": 64892, "sha256": "5dff2527ae8cf3df3d0e75feb7b748714996246e37d6ceefeb4c489938894a96"},
    "crates/sipi-pybert-direct/tests/pb03_payload.rs": {"blob": "a9ed8ced91769e91e8a38b81cccff0644b771d0a", "bytes": 2140, "sha256": "4a80e4e0a49e65daba19c44b4bd40b19c2e52163f2451a5dfc19c6b912a1c362"},
}
CANDIDATE_ARCHIVE = {"format": "git-archive-tar", "bytes": 52254720, "sha256": "26fbc9d8114dd63a9da7da0d7fbedfde30c6c6f91e4490789fdc078e7644f274"}
UPSTREAM_ARCHIVE = {"format": "git-archive-tar", "bytes": 132587520, "sha256": "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25"}
RESPONSE_HASH_DRIFT = {
    "chnl_H.npy",
    "chnl_trimmed_H.npy",
    "ctle_out_H.npy",
    "dfe_out_H.npy",
    "rx_out_H.npy",
    "tx_H.npy",
    "tx_out_H.npy",
}
UPSTREAM_FILES = {
    "src/pybert_web/engine_adapter.py": {
        "blob": "8cdb9fb612635b58cf2e071a9e90d07d272faa61",
        "bytes": 50326,
        "sha256": "c86a84a9787c542b81247784eb14a1a4c7aa266c36a2e33e73a7e74f7c2452b5",
        "license": "BSD-3-Clause",
    },
    "src/pybert_web/simulation.py": {
        "blob": "cdc065bd692ca4836a7c62eb5a71492ff34620c1",
        "bytes": 45813,
        "sha256": "e5e0c0ba1e3cdc4356f027a8ea79a1e459d11377657a1ba231be5b7cbdf98c3c",
        "license": "BSD-3-Clause",
    },
    "LICENSE": {
        "blob": "64d198ba43675ede5fbdef1ec918a63954951640",
        "bytes": 1466,
        "sha256": "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1",
        "license": "BSD-3-Clause",
    },
}
EXPECTED_PROJECTIONS = [
    {
        "id": "channel_time_and_pulse",
        "members": ["t_ns_chnl.npy", "chnl_h.npy", "chnl_s.npy", "chnl_p.npy"],
        "source_arrays": ["channel_impulse_v_per_v.npy", "timebase.sample_interval", "timebase.samples_per_ui"],
        "upstream_paths": ["src/pybert_web/engine_adapter.py:635-655", "src/pybert_web/simulation.py:787-811"],
    },
    {
        "id": "frequency_and_stage_response",
        "members": ["f_GHz.npy", "chnl_H_raw.npy", "chnl_H.npy", "chnl_trimmed_H.npy", "tx_H.npy", "tx_out_H.npy", "ctle_H.npy", "ctle_out_H.npy", "dfe_H.npy", "dfe_out_H.npy", "rx_out_H.npy"],
        "source_arrays": ["legacy_channel_frequency_hz.npy", "legacy_channel_complex_telemetry", "legacy_stage_complex_telemetry"],
        "upstream_paths": ["src/pybert_web/engine_adapter.py:570-649", "src/pybert_web/simulation.py:823-847"],
    },
    {
        "id": "parity_aliases",
        "members": ["parity_channel_impulse_v_per_v.npy", "parity_ctle_output_v.npy", "parity_rx_output_v.npy", "parity_dfe_output_v.npy", "parity_dfe_decisions.npy", "parity_dfe_clock_times_s.npy"],
        "source_arrays": ["channel_impulse_v_per_v.npy", "ctle_output_v.npy", "rx_output_v.npy", "dfe_output_v.npy", "dfe_decisions.npy", "dfe_clock_times_s.npy"],
        "upstream_paths": ["src/pybert_web/engine_adapter.py:440-444", "src/pybert_web/simulation.py:772-811"],
    },
    {
        "id": "jitter_bins",
        "members": ["jitter_bins.npy"],
        "source_arrays": ["jitter_bin_centers_s.npy"],
        "upstream_paths": ["src/pybert_web/engine_adapter.py:681-685", "src/pybert_web/simulation.py:771"],
    },
    {
        "id": "bathtub_presentations",
        "members": ["bathtub_chnl.npy", "bathtub_tx.npy", "bathtub_ctle.npy", "bathtub_dfe.npy", "bathtub_rx.npy"],
        "source_arrays": ["bathtub_chnl_ber.npy", "bathtub_tx_ber.npy", "bathtub_ctle_ber.npy", "bathtub_dfe_ber.npy"],
        "upstream_paths": ["src/pybert_web/engine_adapter.py:687-692", "src/pybert_web/simulation.py:624-770"],
    },
]
EXPECTED_BLOCKERS = [
    {"id": "eye_display_payload", "members": ["eye_chnl.npy", "eye_tx.npy", "eye_ctle.npy", "eye_dfe.npy", "eye_rx.npy"], "reason": "no existing typed two-dimensional eye source", "disposition": "blocked_do_not_add_algorithm"},
    {"id": "native_eye_payload", "members": ["native_eye_chnl.npy", "native_eye_tx.npy", "native_eye_ctle.npy", "native_eye_dfe.npy", "native_eye_rx.npy"], "reason": "no existing typed native eye source", "disposition": "blocked_do_not_add_algorithm"},
    {"id": "contour_coordinates", "members": ["eye_contour_2_x_ui.npy", "eye_contour_2_y_v.npy"], "reason": "candidate has two contours while the oracle has three", "disposition": "blocked_do_not_add_algorithm"},
    {"id": "response_hash_drift", "members": ["chnl_H.npy", "chnl_trimmed_H.npy", "ctle_out_H.npy", "dfe_out_H.npy", "rx_out_H.npy", "tx_H.npy", "tx_out_H.npy"], "reason": "candidate and oracle logical f64 hashes differ; no ULP claim is made", "disposition": "recorded_shared_drift"},
    {"id": "contour_cardinality", "members": ["eye_contour_ber.npy", "eye_contour_height_v.npy", "eye_contour_point_count.npy", "eye_contour_width_ps.npy"], "reason": "candidate has two contour summaries while the oracle has three", "disposition": "recorded_shared_drift"},
]
EXPECTED_NON_CLAIMS = [
    "NPZ and member receipts are caller-recorded integrity observations, not execution provenance.",
    "The 140-member candidate inventory is not whole-payload parity.",
    "Twelve eye and contour-coordinate oracle members remain absent.",
    "Four contour summaries remain cardinality drifted.",
    "Seven response magnitude fields remain non-exact hashes.",
    "Two candidate-only internal arrays remain intentionally present.",
    "AMI, IBIS, DLL, GetWave, vendor noise, and class pickle remain blocked.",
    "No product, global closure, or release claim is made.",
]


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fail(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def exact_keys(value: Any, expected: set[str], label: str, errors: list[str]) -> bool:
    valid = type(value) is dict and set(value) == expected
    fail(errors, valid, f"{label} schema drift")
    return valid


def strict_string(value: Any) -> bool:
    return type(value) is str and bool(value)


def strict_int(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def git(repo: Path, *args: str, raw: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


@functools.lru_cache(maxsize=2)
def git_archive_receipt(repo: Path, commit: str) -> dict[str, Any]:
    payload = git(repo, "archive", "--format=tar", commit, raw=True)
    if not isinstance(payload, bytes):
        raise TypeError("git archive did not return bytes")
    return {"format": "git-archive-tar", "bytes": len(payload), "sha256": sha256(payload)}


def git_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def verify_git_gate(gate: Any, errors: list[str]) -> None:
    if not exact_keys(gate, {"candidate_ancestor", "commit", "tree", "files"}, "git_gate", errors):
        return
    commit, tree = gate["commit"], gate["tree"]
    fail(errors, gate["candidate_ancestor"] == CANDIDATE_COMMIT, "git_gate candidate ancestor drift")
    commit_valid = type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit) is not None
    tree_valid = type(tree) is str and re.fullmatch(r"[0-9a-f]{40}", tree) is not None
    fail(errors, commit_valid, "git_gate commit format drift")
    fail(errors, tree_valid, "git_gate tree format drift")
    files = gate["files"]
    if not exact_keys(files, {"verifier", "mutation_test"}, "git_gate.files", errors):
        return
    if not commit_valid or not tree_valid:
        return
    try:
        head = git(ROOT, "rev-parse", "HEAD")
        fail(errors, git(ROOT, "rev-parse", f"{commit}^{{tree}}") == tree, "git_gate full tree drift")
        fail(errors, commit != head and git_is_ancestor(ROOT, commit, head), "record HEAD is not a strict git_gate descendant")
        fail(errors, git_is_ancestor(ROOT, CANDIDATE_COMMIT, commit), "candidate commit is not a git_gate ancestor")
        for label, expected_path in (("verifier", "tools/verify_pb_03_payload_inventory.py"), ("mutation_test", "tools/test_verify_pb_03_payload_inventory.py")):
            item = files[label]
            if not exact_keys(item, {"path", "blob", "bytes", "sha256"}, f"git_gate.files.{label}", errors):
                continue
            fail(errors, item["path"] == expected_path and type(item["bytes"]) is int, f"git_gate.files.{label} path/type drift")
            payload = git(ROOT, "show", f"{commit}:{expected_path}", raw=True)
            blob = git(ROOT, "rev-parse", f"{commit}:{expected_path}")
            fail(errors, blob == item["blob"] and len(payload) == item["bytes"] and sha256(payload) == item["sha256"], f"git_gate.files.{label} blob/raw drift")
            path = safe_repo_file(expected_path, errors, f"git_gate.files.{label}")
            if path is not None:
                fail(errors, path.read_bytes() == payload, f"git_gate.files.{label} changed after gate")
            parent_has_tool = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}^:{expected_path}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0
            fail(errors, not parent_has_tool, f"git_gate did not introduce {expected_path}")
        for path in (MANIFEST_PATH, MEMBER_MAP_PATH, "docs/baselines/audits/2026-08-27-pb-03-payload-inventory.md"):
            gate_has_formal = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}:{path}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0
            fail(errors, not gate_has_formal, f"formal artifact already existed at git_gate: {path}")
            worktree = safe_repo_file(path, errors, f"record.{path}")
            if worktree is not None:
                fail(errors, git(ROOT, "show", f"HEAD:{path}", raw=True) == worktree.read_bytes(), f"record artifact is not committed: {path}")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        errors.append(f"git_gate verification failed: {type(error).__name__}")


def verify_gate_checkout_without_formal_artifacts() -> dict[str, Any]:
    errors: list[str] = []
    formal = [ROOT / MANIFEST_PATH, ROOT / MEMBER_MAP_PATH, ROOT / "docs/baselines/audits/2026-08-27-pb-03-payload-inventory.md"]
    fail(errors, not any(path.exists() for path in formal), "formal artifacts are partially present")
    try:
        head = git(ROOT, "rev-parse", "HEAD")
        tree = git(ROOT, "rev-parse", "HEAD^{tree}")
        fail(errors, head != CANDIDATE_COMMIT and git_is_ancestor(ROOT, CANDIDATE_COMMIT, head), "gate checkout is not a candidate descendant")
        for path in ("tools/verify_pb_03_payload_inventory.py", "tools/test_verify_pb_03_payload_inventory.py"):
            worktree = safe_repo_file(path, errors, f"gate_checkout.{path}")
            if worktree is not None:
                fail(errors, git(ROOT, "show", f"HEAD:{path}", raw=True) == worktree.read_bytes(), f"gate checkout tool drift: {path}")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        errors.append(f"gate checkout verification failed: {type(error).__name__}")
        head, tree = None, None
    return {"valid": not errors, "errors": errors, "status": "skipped_formal_artifacts_absent", "gate_commit": head, "gate_tree": tree}


def safe_repo_file(relative: Any, errors: list[str], label: str) -> Path | None:
    if not strict_string(relative) or "\\" in relative:
        errors.append(f"{label} path is unsafe")
        return None
    posix, windows = PurePosixPath(relative), PureWindowsPath(relative)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts or "." in posix.parts:
        errors.append(f"{label} path is unsafe")
        return None
    candidate = ROOT.joinpath(*posix.parts)
    try:
        root, resolved = ROOT.resolve(strict=True), candidate.resolve(strict=True)
        resolved.relative_to(root)
        current = root
        for part in posix.parts:
            current /= part
            metadata = current.lstat()
            if current.is_symlink() or getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise OSError("link/reparse component")
        if not candidate.is_file() or candidate.stat().st_nlink != 1:
            raise OSError("file/link-count gate")
    except (OSError, ValueError):
        errors.append(f"{label} failed containment/link/nlink gate")
        return None
    return candidate


def binding(value: Any, label: str, errors: list[str]) -> Path | None:
    if not exact_keys(value, {"path", "sha256"}, label, errors):
        return None
    path = safe_repo_file(value["path"], errors, label)
    fail(errors, type(value["sha256"]) is str and HEX64.fullmatch(value["sha256"]) is not None, f"{label} digest format drift")
    if path is not None and type(value["sha256"]) is str:
        fail(errors, sha256(path.read_bytes()) == value["sha256"], f"{label} content drift")
    return path


def side(value: Any, label: str, errors: list[str]) -> dict[str, Any] | None:
    if value is None:
        return None
    keys = {"producer", "source", "count", "dtype", "shape", "fortran_order", "f64_sha256"}
    if not exact_keys(value, keys, label, errors):
        return None
    fail(errors, value["producer"] in {"pb03_serializer_projection", "native_typed_result", "pinned_sim_rust_adapter"}, f"{label} producer drift")
    fail(errors, strict_string(value["source"]), f"{label} source drift")
    fail(errors, strict_int(value["count"]), f"{label} count type drift")
    fail(errors, value["dtype"] in {"<f8", "|f8", ">f8"}, f"{label} dtype drift")
    shape = value["shape"]
    fail(errors, type(shape) is list and all(strict_int(item) for item in shape), f"{label} shape type drift")
    if type(shape) is list and all(strict_int(item) for item in shape):
        product = 1
        for dimension in shape:
            product *= dimension
        fail(errors, product == value["count"], f"{label} shape/count drift")
    fail(errors, type(value["fortran_order"]) is bool, f"{label} order type drift")
    fail(errors, type(value["f64_sha256"]) is str and HEX64.fullmatch(value["f64_sha256"]) is not None, f"{label} digest drift")
    return value


def logical(value: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if value is None:
        return None
    return (value["source"], value["count"], value["dtype"], value["shape"], value["fortran_order"], value["f64_sha256"])


def response_metadata(value: dict[str, Any]) -> tuple[Any, ...]:
    return (value["source"], value["count"], value["dtype"], value["shape"], value["fortran_order"])


def verify_member_map(value: Any, errors: list[str]) -> tuple[dict[str, int], dict[str, int], dict[str, set[str]], set[str]]:
    counts = {key: 0 for key in COUNTS}
    before = {key: 0 for key in BEFORE_COUNTS}
    classes = {name: set() for name in ("exact", "shared_drift", "candidate_only", "oracle_only")}
    projected: set[str] = set()
    top = {"schema", "version", "row", "candidate", "oracle", "fixture", "members"}
    if not exact_keys(value, top, "member_map", errors):
        return counts, before, classes, projected
    fail(errors, value["schema"] == "sipi.pb-03-payload-member-map.v1", "member_map schema drift")
    fail(errors, type(value["version"]) is int and value["version"] == 1, "member_map version type/value drift")
    fail(errors, value["row"] == "PB-03", "member_map row drift")
    observation_keys = {"kind", "arrays_bytes", "arrays_sha256", "logical_sha256", "member_count"}
    expected_sources = (
        ("candidate", CANDIDATE_COMMIT, CANDIDATE_TREE, CANDIDATE_ARCHIVE, {"kind": "caller_recorded_npz_receipt", "arrays_bytes": 2434670, "arrays_sha256": "3e1dd61beadba20461264087eeca0df37b11924c4747465277fcb9cdf2eaaeb7", "logical_sha256": "649b49abb7d8a5ae31ed8aef2b4b8d186a72e8a5e2239dadd5c95309cbde7fc1", "member_count": 140}),
        ("oracle", UPSTREAM_COMMIT, UPSTREAM_TREE, UPSTREAM_ARCHIVE, {"kind": "caller_recorded_npz_receipt", "arrays_bytes": 3852401, "arrays_sha256": "28da30db995bc3350f4d6c2993fd0e2f495c345392451a358add09397127daaa", "logical_sha256": "4604b7e6d440568d1a7bbd14ae607da612a5103204e1f69fc355be261ceb0694", "member_count": 150}),
    )
    for label, commit, tree, archive, replay in expected_sources:
        source = value[label]
        if exact_keys(source, {"commit", "tree", "archive", "observation"}, f"member_map.{label}", errors):
            fail(errors, source == {"commit": commit, "tree": tree, "archive": archive, "observation": replay}, f"member_map {label} integrity receipt drift")
            exact_keys(source["archive"], {"format", "bytes", "sha256"}, f"member_map.{label}.archive", errors)
            exact_keys(source["observation"], observation_keys, f"member_map.{label}.observation", errors)
    if exact_keys(value["fixture"], {"path", "blob", "bytes", "sha256"}, "member_map.fixture", errors):
        fail(errors, value["fixture"] == {"path": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml", "blob": "7f5186d2767c0c24415d35c02660f85586810724", "bytes": 1170, "sha256": "2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f"}, "member_map fixture drift")
    members = value["members"]
    fail(errors, type(members) is list, "member_map members type drift")
    names: list[str] = []
    if type(members) is not list:
        return counts, before, classes, projected
    for index, member in enumerate(members):
        label = f"member_map.members[{index}]"
        if not exact_keys(member, {"name", "classification", "candidate", "oracle"}, label, errors):
            continue
        name = member["name"]
        fail(errors, strict_string(name) and name.endswith(".npy"), f"{label} name drift")
        if not strict_string(name):
            continue
        names.append(name)
        candidate = side(member["candidate"], f"{label}.candidate", errors)
        oracle = side(member["oracle"], f"{label}.oracle", errors)
        if name in RESPONSE_HASH_DRIFT:
            fail(errors, candidate is not None and oracle is not None, f"{label} response sides missing")
            if candidate is not None and oracle is not None:
                fail(errors, response_metadata(candidate) == response_metadata(oracle), f"{label} response metadata/source drift")
                fail(errors, candidate["f64_sha256"] != oracle["f64_sha256"], f"{label} response hashes unexpectedly exact")
        expected = "exact" if candidate is not None and oracle is not None and logical(candidate) == logical(oracle) else "shared_drift" if candidate is not None and oracle is not None else "candidate_only" if candidate is not None else "oracle_only" if oracle is not None else "invalid"
        fail(errors, member["classification"] == expected, f"{label} classification drift")
        if expected in classes:
            classes[expected].add(name)
            counts[f"{expected}_count"] += 1
        if candidate is not None:
            counts["candidate_count"] += 1
            if candidate["producer"] == "pb03_serializer_projection":
                projected.add(name)
        if oracle is not None:
            counts["oracle_count"] += 1
            fail(errors, oracle["producer"] == "pinned_sim_rust_adapter", f"{label} oracle producer drift")
    fail(errors, names == sorted(names) and len(names) == len(set(names)), "member_map member order/uniqueness drift")
    fail(errors, RESPONSE_HASH_DRIFT <= classes["shared_drift"], "response hash-drift inventory incomplete")
    base_candidate = {member["name"]: member["candidate"] for member in members if type(member) is dict and type(member.get("candidate")) is dict and member["candidate"].get("producer") != "pb03_serializer_projection"}
    oracle_members = {member["name"]: member["oracle"] for member in members if type(member) is dict and type(member.get("oracle")) is dict}
    before["candidate_count"], before["oracle_count"] = len(base_candidate), len(oracle_members)
    for name in sorted(set(base_candidate) | set(oracle_members)):
        candidate, oracle = base_candidate.get(name), oracle_members.get(name)
        classification = "exact" if candidate is not None and oracle is not None and logical(candidate) == logical(oracle) else "shared_drift" if candidate is not None and oracle is not None else "candidate_only" if candidate is not None else "oracle_only"
        before[f"{classification}_count"] += 1
    fail(errors, before == BEFORE_COUNTS, "producer-derived before inventory drift")
    return counts, before, classes, projected


def verify(value: Any, upstream_repo: Path | None, member_map_override: Any | None = None) -> dict[str, Any]:
    errors: list[str] = []
    top_keys = {"schema", "version", "row", "status", "scope", "git_gate", "source", "fixture", "production_files", "upstream_files", "bindings", "inventory_before_projection", "inventory", "projections", "remaining_blockers", "claims", "non_claims"}
    if not exact_keys(value, top_keys, "manifest", errors):
        return {"valid": False, "errors": errors}
    fail(errors, value["schema"] == "sipi.pb-03-payload-inventory.v1", "manifest schema drift")
    fail(errors, type(value["version"]) is int and value["version"] == 1, "manifest version type/value drift")
    fail(errors, value["row"] == "PB-03", "manifest row drift")
    fail(errors, value["status"] == "implemented_scoped_serializer_projection", "manifest status drift")
    if exact_keys(value["scope"], {"source_mode", "whole_payload_parity", "description"}, "scope", errors):
        fail(errors, value["scope"]["source_mode"] == "caller_recorded_integrity_only_member_observation", "scope mode drift")
        fail(errors, value["scope"]["whole_payload_parity"] is False, "scope parity drift")
        fail(errors, value["scope"]["description"] == "Static Git archive recomputation plus caller-recorded NPZ/member receipts; no execution provenance claim.", "scope description drift")
    verify_git_gate(value["git_gate"], errors)
    if exact_keys(value["source"], {"candidate", "upstream"}, "source", errors):
        candidate, upstream = value["source"]["candidate"], value["source"]["upstream"]
        if exact_keys(candidate, {"commit", "tree", "archive_static_recomputed"}, "source.candidate", errors):
            fail(errors, candidate == {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive_static_recomputed": True}, "candidate source drift")
        if exact_keys(upstream, {"commit", "tree"}, "source.upstream", errors):
            fail(errors, upstream == {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE}, "upstream source drift")
    if upstream_repo is None:
        errors.append("upstream repository argument is required")
        upstream_repo = Path(".")
    try:
        upstream_repo = upstream_repo.resolve(strict=True)
        fail(errors, upstream_repo.is_dir() and (upstream_repo / ".git").exists(), "upstream repository is not a Git worktree")
        fail(errors, upstream_repo != ROOT.resolve(strict=True), "upstream repository must be distinct")
        fail(errors, git(ROOT, "rev-parse", CANDIDATE_COMMIT) == CANDIDATE_COMMIT, "candidate commit unavailable")
        fail(errors, git(ROOT, "rev-parse", f"{CANDIDATE_COMMIT}^{{tree}}") == CANDIDATE_TREE, "candidate tree drift")
        fail(errors, git(upstream_repo, "rev-parse", UPSTREAM_COMMIT) == UPSTREAM_COMMIT, "upstream commit unavailable")
        fail(errors, git(upstream_repo, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}") == UPSTREAM_TREE, "upstream tree drift")
        fail(errors, git_archive_receipt(ROOT, CANDIDATE_COMMIT) == CANDIDATE_ARCHIVE, "candidate clean archive drift")
        fail(errors, git_archive_receipt(upstream_repo, UPSTREAM_COMMIT) == UPSTREAM_ARCHIVE, "upstream clean archive drift")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        errors.append(f"git source verification failed: {type(error).__name__}")

    fixture = value["fixture"]
    if exact_keys(fixture, {"path", "blob", "bytes", "sha256"}, "fixture", errors):
        path = safe_repo_file(fixture["path"], errors, "fixture")
        fail(errors, fixture["blob"] == "7f5186d2767c0c24415d35c02660f85586810724", "fixture blob drift")
        fail(errors, type(fixture["bytes"]) is int and fixture["bytes"] == 1170, "fixture byte type/value drift")
        fail(errors, fixture["sha256"] == "2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f", "fixture digest drift")
        if path is not None:
            payload = path.read_bytes()
            fail(errors, len(payload) == fixture["bytes"] and sha256(payload) == fixture["sha256"], "fixture worktree content drift")
            try:
                fail(errors, git(ROOT, "rev-parse", f"{CANDIDATE_COMMIT}:{fixture['path']}") == fixture["blob"], "fixture Git blob drift")
                fail(errors, git(ROOT, "show", f"{CANDIDATE_COMMIT}:{fixture['path']}", raw=True) == payload, "fixture Git payload drift")
            except (OSError, subprocess.CalledProcessError):
                errors.append("fixture Git payload unavailable")

    production_files = value["production_files"]
    fail(errors, type(production_files) is list and len(production_files) == len(PRODUCTION_FILES), "production file inventory drift")
    observed_production: set[str] = set()
    if type(production_files) is list:
        for index, item in enumerate(production_files):
            label = f"production_files[{index}]"
            if not exact_keys(item, {"path", "blob", "bytes", "sha256"}, label, errors):
                continue
            path, expected = item["path"], PRODUCTION_FILES.get(item["path"])
            if strict_string(path):
                observed_production.add(path)
            fail(errors, expected is not None and type(item["bytes"]) is int and all(item[key] == expected[key] for key in expected), f"{label} binding/type drift")
            worktree_path = safe_repo_file(path, errors, label)
            if expected is not None and worktree_path is not None:
                try:
                    payload = git(ROOT, "show", f"{CANDIDATE_COMMIT}:{path}", raw=True)
                    fail(errors, git(ROOT, "rev-parse", f"{CANDIDATE_COMMIT}:{path}") == item["blob"] and len(payload) == item["bytes"] and sha256(payload) == item["sha256"], f"{label} Git content drift")
                    fail(errors, worktree_path.read_bytes() == payload, f"{label} worktree drift")
                except (OSError, subprocess.CalledProcessError):
                    errors.append(f"{label} Git payload unavailable")
    fail(errors, observed_production == set(PRODUCTION_FILES), "production file paths drift")

    upstream_files = value["upstream_files"]
    fail(errors, type(upstream_files) is list and len(upstream_files) == 3, "upstream file inventory drift")
    observed: set[str] = set()
    if type(upstream_files) is list:
        for index, item in enumerate(upstream_files):
            label = f"upstream_files[{index}]"
            if not exact_keys(item, {"path", "blob", "bytes", "sha256", "license"}, label, errors):
                continue
            path, expected = item["path"], UPSTREAM_FILES.get(item["path"])
            if strict_string(path):
                observed.add(path)
            fail(
                errors,
                expected is not None
                and type(item["path"]) is str
                and type(item["blob"]) is str
                and type(item["bytes"]) is int
                and type(item["sha256"]) is str
                and type(item["license"]) is str
                and all(item[key] == expected[key] for key in expected),
                f"{label} binding/type drift",
            )
            if expected is not None:
                try:
                    payload = git(upstream_repo, "show", f"{UPSTREAM_COMMIT}:{path}", raw=True)
                    fail(errors, git(upstream_repo, "rev-parse", f"{UPSTREAM_COMMIT}:{path}") == item["blob"] and len(payload) == item["bytes"] and sha256(payload) == item["sha256"], f"{label} Git content drift")
                except (OSError, subprocess.CalledProcessError):
                    errors.append(f"{label} Git payload unavailable")
    fail(errors, observed == set(UPSTREAM_FILES), "upstream paths drift")

    bindings = value["bindings"]
    keys = {"member_map", "audit", "verifier", "mutation_test"}
    paths: dict[str, Path | None] = {}
    if exact_keys(bindings, keys, "bindings", errors):
        expected_paths = {"member_map": MEMBER_MAP_PATH, "audit": "docs/baselines/audits/2026-08-27-pb-03-payload-inventory.md", "verifier": "tools/verify_pb_03_payload_inventory.py", "mutation_test": "tools/test_verify_pb_03_payload_inventory.py"}
        for label in sorted(keys):
            paths[label] = binding(bindings[label], f"bindings.{label}", errors)
            if type(bindings[label]) is dict:
                fail(errors, bindings[label].get("path") == expected_paths[label], f"bindings.{label} path drift")

    physical_map = None
    if paths.get("member_map") is not None:
        try:
            physical_map = json.loads(paths["member_map"].read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"member map parse failed: {type(error).__name__}")
    if member_map_override is not None:
        fail(errors, member_map_override == physical_map, "member_map override differs from physical bound map")
    member_map = member_map_override if member_map_override is not None else physical_map
    counts, before_counts, classes, projected = verify_member_map(member_map, errors)
    fail(errors, counts == COUNTS, "derived member counts drift")

    before_inventory = value["inventory_before_projection"]
    if exact_keys(before_inventory, set(BEFORE_COUNTS), "inventory_before_projection", errors):
        for key, expected in BEFORE_COUNTS.items():
            fail(errors, type(before_inventory[key]) is int and before_inventory[key] == expected and before_inventory[key] == before_counts[key], f"inventory_before_projection {key} drift")

    inventory = value["inventory"]
    if exact_keys(inventory, set(COUNTS) | {"whole_payload_parity"}, "inventory", errors):
        for key, expected in COUNTS.items():
            fail(errors, type(inventory[key]) is int and inventory[key] == expected and inventory[key] == counts[key], f"inventory {key} type/value drift")
        fail(errors, inventory["whole_payload_parity"] is False, "inventory parity drift")

    projections = value["projections"]
    fail(errors, type(projections) is list, "projections type drift")
    fail(errors, projections == EXPECTED_PROJECTIONS, "projection graph value drift")
    projected_manifest: set[str] = set()
    if type(projections) is list:
        ids: list[str] = []
        for index, item in enumerate(projections):
            label = f"projections[{index}]"
            if not exact_keys(item, {"id", "members", "source_arrays", "upstream_paths"}, label, errors):
                continue
            ids.append(item["id"])
            fail(errors, type(item["members"]) is list and all(strict_string(name) and name.endswith(".npy") for name in item["members"]), f"{label} members drift")
            if type(item["members"]) is list:
                projected_manifest.update(name for name in item["members"] if strict_string(name))
            fail(errors, type(item["source_arrays"]) is list and all(strict_string(name) for name in item["source_arrays"]), f"{label} sources drift")
            fail(errors, type(item["upstream_paths"]) is list and all(strict_string(path) and path.split(":", 1)[0] in UPSTREAM_FILES for path in item["upstream_paths"]), f"{label} paths drift")
        fail(errors, ids == ["channel_time_and_pulse", "frequency_and_stage_response", "parity_aliases", "jitter_bins", "bathtub_presentations"], "projection IDs/order drift")
    fail(errors, projected_manifest == projected, "projection/member-map producer drift")

    blockers = value["remaining_blockers"]
    fail(errors, type(blockers) is list, "blockers type drift")
    fail(errors, blockers == EXPECTED_BLOCKERS, "blocker graph value drift")
    blocked: set[str] = set()
    if type(blockers) is list:
        for index, item in enumerate(blockers):
            label = f"remaining_blockers[{index}]"
            if not exact_keys(item, {"id", "members", "reason", "disposition"}, label, errors):
                continue
            fail(errors, strict_string(item["id"]) and strict_string(item["reason"]) and item["disposition"] in {"blocked_do_not_add_algorithm", "recorded_shared_drift"}, f"{label} values drift")
            fail(errors, type(item["members"]) is list and all(strict_string(name) for name in item["members"]), f"{label} members drift")
            if type(item["members"]) is list:
                blocked.update(name for name in item["members"] if strict_string(name))
    fail(errors, classes["oracle_only"] <= blocked and classes["shared_drift"] <= blocked, "blockers do not cover physical gaps")

    expected_claims = {"serializer_projection": True, "scoped_member_reduction": True, "execution_provenance": False, "replay_custody": False, "whole_payload_parity": False, "exact_whole_payload_parity": False, "global_row_closed": False, "product_capability": False, "release_approval": False}
    fail(errors, type(value["claims"]) is dict and value["claims"] == expected_claims and all(type(item) is bool for item in value["claims"].values()), "claims drift")
    fail(errors, type(value["non_claims"]) is list and value["non_claims"] == EXPECTED_NON_CLAIMS, "non_claims drift")

    source_map_text = (ROOT / "crates/sipi-pybert-direct/SOURCE-MAP-PB03-PAYLOAD.md").read_text(encoding="utf-8")
    notice_text = (ROOT / "crates/sipi-pybert-direct/NOTICE-PYBERT-PB03-PAYLOAD.md").read_text(encoding="utf-8")
    for path, expected in UPSTREAM_FILES.items():
        for token in (path, expected["blob"], str(expected["bytes"]), expected["sha256"], expected["license"]):
            fail(errors, token in source_map_text, f"source map missing {path} anchor")
    for token in ("This slice makes no claim of whole-payload parity", "They do not include copied PyBERT", "No public wire schema v2 or second engine"):
        fail(errors, token in source_map_text + notice_text, f"source-map/notice semantic anchor missing: {token}")
    fail(errors, HOST_PATH.search(source_map_text + notice_text) is None, "source-map/notice contains a host path")
    if paths.get("audit") is not None and type(bindings) is dict:
        text = paths["audit"].read_text(encoding="utf-8")
        for label in ("member_map", "verifier", "mutation_test"):
            item = bindings[label]
            fail(errors, f"{label}_sha256: {item['sha256']}" in text, f"audit missing reciprocal {label} anchor")
        for label, expected in (("source_map", PRODUCTION_FILES["crates/sipi-pybert-direct/SOURCE-MAP-PB03-PAYLOAD.md"]), ("notice", PRODUCTION_FILES["crates/sipi-pybert-direct/NOTICE-PYBERT-PB03-PAYLOAD.md"])):
            fail(errors, f"{label}_sha256: {expected['sha256']}" in text, f"audit missing production {label} anchor")
        fail(errors, AUDIT_ANCHOR.sub(lambda match: f"{match.group(1)}_sha256: <bound>", text) == EXPECTED_AUDIT_NORMALIZED, "audit coordinated semantic/nonclaim drift")
        fail(errors, HOST_PATH.search(text) is None, "audit contains a host path")
    for label, document in (("manifest", value), ("member_map", member_map)):
        try:
            serialized = json.dumps(document, sort_keys=True)
        except (TypeError, ValueError):
            errors.append(f"{label} is not JSON-compatible")
        else:
            fail(errors, HOST_PATH.search(serialized) is None, f"{label} contains a host path")
    return {"valid": not errors, "errors": errors, "before": before_counts, **counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-repo", type=Path)
    arguments = parser.parse_args()
    if not (ROOT / MANIFEST_PATH).exists():
        result = verify_gate_checkout_without_formal_artifacts()
        print(json.dumps(result, sort_keys=True))
        return 0 if result["valid"] else 1
    if arguments.upstream_repo is None:
        parser.error("--upstream-repo is required when formal artifacts are present")
    try:
        value = yaml.safe_load((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        print(json.dumps({"valid": False, "errors": [str(error)]}, sort_keys=True))
        return 1
    result = verify(value, arguments.upstream_repo)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
