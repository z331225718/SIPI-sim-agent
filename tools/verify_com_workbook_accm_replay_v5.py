"""Verify the immutable, bounded COM v5 formal replay evidence.

This gate is deliberately narrower than a parity gate.  It verifies two fresh
replays of the exact pinned archives, the committed replay harness, and the
scoped mismatch result without promoting the candidate to a product claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

try:
    from tools import aggregate_com_workbook_accm_replay_v5 as aggregate
except ModuleNotFoundError as error:
    if error.name != "tools":
        raise
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "com_workbook_accm_aggregate",
        Path(__file__).with_name("aggregate_com_workbook_accm_replay_v5.py"),
    )
    if spec is None or spec.loader is None:
        aggregate = None
    else:
        aggregate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(aggregate)
except ImportError:
    # Commit 1 intentionally carries only this verifier and its tests.  The
    # formal aggregate helper is an optional Commit 2 dependency; trust-root
    # tests must remain runnable without it.
    aggregate_path = Path(__file__).with_name("aggregate_com_workbook_accm_replay_v5.py")
    if not aggregate_path.is_file():
        aggregate = None
    else:
        import importlib.util

        spec = importlib.util.spec_from_file_location("com_workbook_accm_aggregate", aggregate_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("COM v5 aggregate module is unavailable")
        aggregate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(aggregate)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "com-workbook-accm-replay-v5.manifest.yaml"
MANIFEST_SCHEMA = "sipi.com.workbook-accm-replay-v5.formal-manifest.v1"
AUDIT_SCHEMA = "sipi.com.workbook-accm-replay-v5.audit.v1"
HARNESS_COMMIT = "6011374f8f84e205c19ff4f7052ab25dcd6f2cd9"
HARNESS_TREE = "fee5cb6d2bdae26aa66f46ce2a3eea494827706a"
CANDIDATE_COMMIT = "bc882d2e5a19c2a844bacc485ede5b874e8f9c37"
CANDIDATE_TREE = "d87cfecea77ccd670073a6c069658e6b4e8c3137"
CANDIDATE_ARCHIVE = {"bytes": 51384320, "sha256": "1f44f6dccba7a00684a82c4c7ce6248eb5ea7f353875af5d9589d17ece6883d0"}
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
UPSTREAM_ARCHIVE = {"bytes": 43694080, "sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"}
REPORT_SCHEMA = "sipi.com.workbook-accm-replay.v5.diagnostic"
AGGREGATE_SCHEMA = "sipi.com.workbook-accm-replay.v5.aggregate"
STATUS = "scoped_mismatch_observed"
BLOCKERS = ["candidate_dfe_taps_not_published"]
NON_CLAIMS = [
    "no S-parameter fit",
    "channel uses one final FD-to-TD impulse",
    "no upstream or global numeric parity",
    "no release or promotion claim",
    "candidate DFE publication is not inferred from hidden state",
]
CONTROL_VECTORS = [[0.0, 0.0], [0.0, 0.001]]
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
MANIFEST_RELATIVE = "docs/baselines/com-workbook-accm-replay-v5.manifest.yaml"
REPORT_BINDINGS = [
    {
        "slot": "run1",
        "path": "docs/baselines/com-workbook-accm-replay-v5-run1.json",
        "bytes": 58401,
        "sha256": "fc14c562020883d0706bfaa16c3d970cb9834bcbf971f9e57b260021a8ca1a64",
        "run_id": "1374cb690e7f1eb90247caa4b63ed0a6ce6873556f899452046260b8b9007868",
        "nonce": "03049bcdfa43e0e8907cc2a69e9265d89579be21059d18928162a9ef31302e5b",
    },
    {
        "slot": "run2",
        "path": "docs/baselines/com-workbook-accm-replay-v5-run2.json",
        "bytes": 58401,
        "sha256": "ef732c7b063a72e422aa5f68325df1d029da056b2eb092502e7a7c7eb26fda01",
        "run_id": "950d932509047d64c89177cc54146d1a65301068c88c3f8bdcba1fe916328f77",
        "nonce": "8289a1caa5ac62c36229b62cce2dc9a43dac4f355f5d021ac8683ce9841d71c5",
    },
]
AGGREGATE_BINDING = {
    "path": "docs/baselines/com-workbook-accm-replay-v5-aggregate.json",
    "bytes": 113947,
    "sha256": "6ec879783ef1ef2310b72c4bbc19e590b84c727055e374af0f59913a8fdb2242",
    "schema": AGGREGATE_SCHEMA,
    "status": STATUS,
    "blockers": BLOCKERS,
}
AUDIT_BINDING = {
    "path": "docs/baselines/audits/2026-08-27-com-workbook-accm-replay-v5.md",
    "bytes": 2638,
    "sha256": "1937951fc001f82511ea6f7b42ca3c2880b068e0a34ac3776bdde3e8596df4ab",
}
TOOLCHAIN_SHA256 = "fb742e87d6c468cd45a9cb9bbc149af0ea9fe90780190c802c636252e77b7cbb"


class VerificationError(ValueError):
    """Raised when a formal evidence binding is not exact."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_bool(value: Any, expected: bool, label: str) -> None:
    require(type(value) is bool and value is expected, f"{label} must be {expected!r}")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return sha256_bytes(payload)


def expected_anchor_bindings() -> dict[str, Any]:
    return {
        "algorithm": "json-canonical-sha256-v1",
        "harness": {"source_commit": HARNESS_COMMIT, "source_tree": HARNESS_TREE},
        "reports": REPORT_BINDINGS,
        "aggregate": {"path": AGGREGATE_BINDING["path"], "bytes": AGGREGATE_BINDING["bytes"], "sha256": AGGREGATE_BINDING["sha256"]},
        "audit": AUDIT_BINDING,
    }


def is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except (OSError, ValueError):
        return True


def safe_repo_file(repo_root: Path, value: Any, label: str) -> Path:
    require(isinstance(value, str) and value and "\\" not in value, f"{label} path malformed")
    relative = Path(value)
    require(not relative.is_absolute() and ":" not in value, f"{label} path is absolute")
    require(".." not in relative.parts and "." not in relative.parts, f"{label} path escapes root")
    root = repo_root.resolve(strict=True)
    raw = root.joinpath(*relative.parts)
    current = raw
    while current != root:
        require(not is_reparse(current), f"{label} path contains a symlink/reparse point")
        current = current.parent
    try:
        candidate = raw.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError(f"{label} path cannot be resolved") from error
    require(candidate != root and root in candidate.parents, f"{label} path is outside repository")
    require(not is_reparse(candidate) and candidate.is_file(), f"{label} is not a regular file")
    return candidate


def file_record(path: Path, label: str) -> dict[str, Any]:
    payload = path.read_bytes()
    return {"bytes": len(payload), "sha256": sha256_bytes(payload)}


def git_value(repo_root: Path, expression: str, label: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", expression],
        capture_output=True,
        text=True,
        check=False,
    )
    require(completed.returncode == 0, f"{label} cannot be resolved")
    value = completed.stdout.strip()
    require(value and "\n" not in value, f"{label} output malformed")
    return value


def git_bytes(repo_root: Path, arguments: list[str], label: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"{label} cannot be resolved")
    return completed.stdout


class UniqueLoader(yaml.SafeLoader):
    """PyYAML loader that rejects duplicate mapping keys."""


def _unique_mapping(loader: UniqueLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        require(key not in result, f"duplicate manifest/audit key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_yaml(path: Path, label: str) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError, VerificationError) as error:
        raise VerificationError(f"{label} is not valid YAML: {error}") from error
    require(isinstance(value, dict), f"{label} root must be a mapping")
    return value


def check_sha_record(path: Path, expected: dict[str, Any], label: str) -> None:
    require(isinstance(expected, dict) and set(expected) == {"bytes", "sha256"}, f"{label} receipt shape drift")
    require(type(expected["bytes"]) is int and expected["bytes"] >= 0, f"{label} byte receipt malformed")
    require(isinstance(expected["sha256"], str) and HEX64.fullmatch(expected["sha256"]), f"{label} digest malformed")
    actual = file_record(path, label)
    require(actual == expected, f"{label} bytes/hash drift")


def validate_harness(document: dict[str, Any], repo_root: Path) -> None:
    harness = document.get("harness")
    require(isinstance(harness, dict), "harness binding missing")
    require(
        set(harness) == {"source_commit", "source_tree", "source_mode", "files"},
        "harness schema drift",
    )
    require(harness["source_commit"] == HARNESS_COMMIT and harness["source_tree"] == HARNESS_TREE, "harness source drift")
    require(harness["source_mode"] == "committed_harness_source_separate_from_business_candidate", "harness source mode drift")
    expected_paths = [
        "tools/run_com_workbook_accm_replay_v5.py",
        "tools/aggregate_com_workbook_accm_replay_v5.py",
        "tools/test_run_com_workbook_accm_replay_v5.py",
        "tools/test_aggregate_com_workbook_accm_replay_v5.py",
    ]
    files = harness["files"]
    require(isinstance(files, list) and len(files) == len(expected_paths), "harness file count drift")
    for item, expected_path in zip(files, expected_paths, strict=True):
        require(isinstance(item, dict) and set(item) == {"path", "bytes", "sha256", "git_blob_sha1"}, "harness file receipt drift")
        require(item["path"] == expected_path, "harness file path/order drift")
        path = safe_repo_file(repo_root, item["path"], "harness file")
        check_sha_record(path, {"bytes": item["bytes"], "sha256": item["sha256"]}, f"harness {expected_path}")
        require(isinstance(item["git_blob_sha1"], str) and SHA1.fullmatch(item["git_blob_sha1"]), "harness blob receipt malformed")
        if (repo_root / ".git").exists():
            require(git_value(repo_root, f"{HARNESS_COMMIT}:{expected_path}", "harness blob") == item["git_blob_sha1"], "harness blob drift")


def validate_source(document: dict[str, Any], repo_root: Path, upstream_root: Path | None) -> None:
    candidate = document.get("candidate")
    upstream = document.get("upstream")
    require(isinstance(candidate, dict) and isinstance(upstream, dict), "source binding missing")
    require(
        set(candidate) == {"commit", "tree", "archive", "source_mode"}
        and candidate["commit"] == CANDIDATE_COMMIT
        and candidate["tree"] == CANDIDATE_TREE
        and candidate["archive"] == CANDIDATE_ARCHIVE
        and candidate["source_mode"] == "git_archive_at_immutable_business_commit",
        "candidate source binding drift",
    )
    require(
        set(upstream) == {"commit", "tree", "archive", "source_mode", "runtime_policy"}
        and upstream["commit"] == UPSTREAM_COMMIT
        and upstream["tree"] == UPSTREAM_TREE
        and upstream["archive"] == UPSTREAM_ARCHIVE
        and upstream["source_mode"] == "git_archive_at_immutable_upstream_commit"
        and upstream["runtime_policy"] == "single_uv_frozen_offline_clean_archive",
        "upstream source binding drift",
    )
    if (repo_root / ".git").exists():
        require(git_value(repo_root, f"{CANDIDATE_COMMIT}", "candidate commit") == CANDIDATE_COMMIT, "candidate commit unavailable")
        require(git_value(repo_root, f"{CANDIDATE_COMMIT}^{{tree}}", "candidate tree") == CANDIDATE_TREE, "candidate tree unavailable")
    if upstream_root is not None and (upstream_root / ".git").exists():
        require(git_value(upstream_root, UPSTREAM_COMMIT, "upstream commit") == UPSTREAM_COMMIT, "upstream commit unavailable")
        require(git_value(upstream_root, f"{UPSTREAM_COMMIT}^{{tree}}", "upstream tree") == UPSTREAM_TREE, "upstream tree unavailable")


VERIFICATION_GATE_FILES = {
    "verifier": "tools/verify_com_workbook_accm_replay_v5.py",
    "mutation_tests": "tools/test_verify_com_workbook_accm_replay_v5.py",
}


def validate_verification_gate(document: dict[str, Any], repo_root: Path) -> None:
    """Validate the committed trust root for this verifier and its tests.

    This deliberately uses raw Git objects and raw working-tree bytes.  A
    normalized source digest, a self-referential audit receipt, or a manifest
    receipt updated in tandem with the files is not sufficient evidence.
    """
    gate = document.get("verification_gate")
    require(isinstance(gate, dict) and set(gate) == {"commit", "tree", "files"}, "verification gate schema drift")
    commit = gate["commit"]
    tree = gate["tree"]
    require(isinstance(commit, str) and SHA1.fullmatch(commit), "verification gate commit malformed")
    require(isinstance(tree, str) and SHA1.fullmatch(tree), "verification gate tree malformed")
    files = gate["files"]
    require(isinstance(files, dict) and set(files) == set(VERIFICATION_GATE_FILES), "verification gate file set drift")

    # The gate must be a real commit strictly before the record being checked.
    head = git_value(repo_root, "HEAD", "record HEAD")
    require(SHA1.fullmatch(head), "record HEAD malformed")
    resolved_commit = git_value(repo_root, f"{commit}^{{commit}}", "verification gate commit")
    require(resolved_commit == commit, "verification gate commit drift")
    require(head != commit, "verification gate must be a strict ancestor")
    ancestor_check = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", commit, head],
        capture_output=True,
        check=False,
    )
    require(ancestor_check.returncode == 0, "verification gate is not an ancestor of record HEAD")
    require(git_value(repo_root, f"{commit}^{{tree}}", "verification gate tree") == tree, "verification gate tree drift")

    for role, expected_path in VERIFICATION_GATE_FILES.items():
        item = files[role]
        require(
            isinstance(item, dict) and set(item) == {"path", "bytes", "sha256", "git_blob_sha1"},
            f"verification gate {role} receipt shape drift",
        )
        require(item["path"] == expected_path, f"verification gate {role} path swap")
        require(type(item["bytes"]) is int and item["bytes"] >= 0, f"verification gate {role} byte receipt malformed")
        require(isinstance(item["sha256"], str) and HEX64.fullmatch(item["sha256"]), f"verification gate {role} digest malformed")
        require(isinstance(item["git_blob_sha1"], str) and SHA1.fullmatch(item["git_blob_sha1"]), f"verification gate {role} blob malformed")

        current_path = safe_repo_file(repo_root, expected_path, f"verification gate {role}")
        current_record = file_record(current_path, f"verification gate {role}")
        expected_record = {"bytes": item["bytes"], "sha256": item["sha256"]}
        require(current_record == expected_record, f"verification gate {role} current bytes/hash drift")

        gate_blob = git_value(repo_root, f"{commit}:{expected_path}", f"verification gate {role} blob")
        require(gate_blob == item["git_blob_sha1"], f"verification gate {role} blob receipt drift")
        gate_payload = git_bytes(repo_root, ["show", f"{commit}:{expected_path}"], f"verification gate {role} source")
        require(
            {"bytes": len(gate_payload), "sha256": sha256_bytes(gate_payload)} == expected_record,
            f"verification gate {role} committed bytes/hash drift",
        )
        require(gate_payload == current_path.read_bytes(), f"verification gate {role} current source drift")


def validate_fixtures(document: dict[str, Any]) -> None:
    expected = {
        "workbook": {
            "path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx",
            "git_blob_sha1": "22b633b6092b4b0de0ca89273515329b362eabae",
            "bytes": 67087,
            "sha256": "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925",
            "source_commit": UPSTREAM_COMMIT,
        },
        "s4p": {
            "path": "fixtures/synthetic/kappa_asymmetric_reflective_10db_at_26p56ghz.s4p",
            "git_blob_sha1": "a1fe8618043b31f63dfb24454ac1d296000010c0",
            "bytes": 6457063,
            "sha256": "3a563543ba664fcc04c1ac5603ad305cb0b1d110c3d9020727444b1c3fd2d0ec",
            "source_commit": UPSTREAM_COMMIT,
        },
    }
    require(document.get("fixtures") == expected, "fixture binding drift")


def comparison_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "port_order_match": value["port_order_match"],
        "port_order_observed": value["port_order_observed"],
        "port_order_status": value["port_order_status"],
        "cursor_index_match": value["cursor_index_match"],
        "sigma_n_v_abs_delta": value["sigma_n_v_abs_delta"],
        "fom_db_abs_delta": value["fom_db_abs_delta"],
        "metric_abs_delta": value["metric_abs_delta"],
        "dfe": value["dfe"],
    }


def candidate_case_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_index": value["case_index"],
        "channel_impulse": value["arrays"]["channel_impulse"],
        "channel_pulse": value["arrays"]["channel_pulse"],
    }


def validate_observation_comparison(value: Any, label: str) -> None:
    require(isinstance(value, dict), f"{label} comparison must be an object")
    require(set(value) == {"port_order_match", "port_order_observed", "port_order_status", "cursor_index_match", "sigma_n_v_abs_delta", "fom_db_abs_delta", "metric_abs_delta", "dfe"}, f"{label} comparison schema drift")
    for key in ("port_order_match", "port_order_observed"):
        require_bool(value[key], False, f"{label} {key}")
    require_bool(value["cursor_index_match"], True, f"{label} cursor_index_match")
    require(value["port_order_status"] == "not_observed", f"{label} port order status drift")
    dfe = value["dfe"]
    require(isinstance(dfe, dict) and set(dfe) == {"upstream_published", "candidate_published", "status"}, f"{label} dfe schema drift")
    require_bool(dfe["upstream_published"], True, f"{label} dfe upstream_published")
    require_bool(dfe["candidate_published"], False, f"{label} dfe candidate_published")
    require(dfe["status"] == "candidate_missing", f"{label} dfe status drift")


def validate_observation_artifacts(value: Any, label: str) -> None:
    require(isinstance(value, dict), f"{label} artifacts must be an object")
    if "artifacts" in value:
        entries = value["artifacts"]
        require(isinstance(entries, list), f"{label} artifact list drift")
        for index, entry in enumerate(entries):
            require(isinstance(entry, dict), f"{label} artifact {index} is not an object")
            require_bool(entry.get("path_redacted"), True, f"{label} artifact {index} path_redacted")


def validate_observations(document: dict[str, Any], reports: list[dict[str, Any]]) -> None:
    observations = document.get("observations")
    require(isinstance(observations, list) and len(observations) == len(CONTROL_VECTORS), "observation count drift")
    for index, (observation, vector) in enumerate(zip(observations, CONTROL_VECTORS, strict=True)):
        require(
            isinstance(observation, dict)
            and set(observation)
            == {"index", "vector", "comparison_sha256", "comparison", "candidate_cases", "artifacts"},
            "observation schema drift",
        )
        require(type(observation["index"]) is int and observation["index"] == index, "observation index type/value drift")
        require(observation["vector"] == vector, "observation vector drift")
        comparisons = observation["comparison"]
        require(isinstance(comparisons, list) and len(comparisons) == 2, f"observation {index} comparison count drift")
        for comparison_index, comparison in enumerate(comparisons):
            validate_observation_comparison(comparison, f"observation {index} comparison {comparison_index}")
        candidate_cases = observation["candidate_cases"]
        require(isinstance(candidate_cases, list) and len(candidate_cases) == 2, f"observation {index} candidate case schema drift")
        for case_index, case in enumerate(candidate_cases):
            require(isinstance(case, dict) and set(case) == {"case_index", "channel_impulse", "channel_pulse"}, f"observation {index} candidate case drift")
            require(type(case["case_index"]) is int and case["case_index"] == case_index, f"observation {index} candidate case index drift")
        validate_observation_artifacts(observation["artifacts"]["run1"], f"observation {index} run1")
        validate_observation_artifacts(observation["artifacts"]["run2"], f"observation {index} run2")
        validate_observation_artifacts(observation["artifacts"]["upstream"], f"observation {index} upstream")
        for report in reports:
            control = report["controls"][index]
            require(canonical_sha256(control["comparison"]) == observation["comparison_sha256"], "numeric comparison digest drift")
            projected = [comparison_projection(item) for item in control["comparison"]]
            require(projected == observation["comparison"], "numeric comparison values drift")
            cases = [candidate_case_projection(item) for item in control["candidate"]["cases"]]
            require(cases == observation["candidate_cases"], "candidate array receipt drift")
        artifacts = observation["artifacts"]
        require(isinstance(artifacts, dict) and set(artifacts) == {"run1", "run2", "upstream"}, "artifact observation schema drift")
        for slot, report in zip(("run1", "run2"), reports, strict=True):
            candidate = report["controls"][index]["candidate"]
            expected = {"artifact_sha256": candidate["artifact_sha256"], "artifacts": candidate["artifacts"]}
            require(artifacts[slot] == expected, f"{slot} artifact receipt drift")
        upstream = reports[0]["controls"][index]["upstream"]["artifact"]
        require(artifacts["upstream"] == upstream, "upstream artifact receipt drift")


def validate_run_record(item: Any, slot: str, report_path: Path, repo_root: Path, report: dict[str, Any], toolchain_sha: str) -> None:
    require(isinstance(item, dict), "run binding malformed")
    required = {"slot", "path", "bytes", "sha256", "run_id", "nonce", "status", "toolchain_sha256", "binary_pre", "binary_post"}
    require(set(item) == required and item["slot"] == slot, "run schema/order drift")
    check_sha_record(report_path, {"bytes": item["bytes"], "sha256": item["sha256"]}, f"{slot} report")
    require(item["path"] == report_path.relative_to(repo_root.resolve()).as_posix(), f"{slot} report path drift")
    require(item["run_id"] == report["run_id"] and item["nonce"] == report["nonce"], f"{slot} identity drift")
    require(item["status"] == STATUS and report["status"] == STATUS, f"{slot} status drift")
    require(item["toolchain_sha256"] == toolchain_sha and canonical_sha256(report["toolchain"]) == toolchain_sha, f"{slot} toolchain drift")
    build = report["build"]
    require(item["binary_pre"] == build["binary_pre"] and item["binary_post"] == build["binary_post"], f"{slot} binary receipt drift")


def validate_audit(document: dict[str, Any], repo_root: Path, reports: list[dict[str, Any]]) -> None:
    audit_binding = document.get("audit")
    require(isinstance(audit_binding, dict) and audit_binding == AUDIT_BINDING, "audit binding hard anchor drift")
    audit_path = safe_repo_file(repo_root, audit_binding["path"], "audit")
    check_sha_record(audit_path, {"bytes": audit_binding["bytes"], "sha256": audit_binding["sha256"]}, "audit")
    audit = load_yaml(audit_path, "audit")
    require(
        set(audit)
        == {"schema", "manifest", "scope", "provenance", "evidence", "result", "non_claims"},
        "audit schema drift",
    )
    require(audit["schema"] == AUDIT_SCHEMA, "audit schema identifier drift")
    require(
        audit["manifest"]
        == {"path": MANIFEST_RELATIVE, "schema": MANIFEST_SCHEMA},
        "audit manifest reciprocal drift",
    )
    require(audit["scope"] == "formal_replay_observation_only", "audit scope drift")
    require(audit["provenance"] == {"harness_commit": HARNESS_COMMIT, "harness_tree": HARNESS_TREE, "candidate_commit": CANDIDATE_COMMIT, "upstream_commit": UPSTREAM_COMMIT}, "audit provenance drift")
    evidence = audit["evidence"]
    require(isinstance(evidence, dict) and set(evidence) == {"reports", "aggregate"}, "audit evidence schema drift")
    require(evidence["reports"] == REPORT_BINDINGS, "audit report reciprocal drift")
    require(evidence["aggregate"] == {"path": AGGREGATE_BINDING["path"], "bytes": AGGREGATE_BINDING["bytes"], "sha256": AGGREGATE_BINDING["sha256"]}, "audit aggregate reciprocal drift")
    # Re-read every evidence edge from the caller-supplied root.  This keeps
    # copied-root verification self-contained and prevents a stale global
    # checkout from satisfying the audit's reciprocal receipts.
    for binding, report in zip(REPORT_BINDINGS, reports, strict=True):
        report_path = safe_repo_file(repo_root, binding["path"], f"audit {binding['slot']} report")
        check_sha_record(report_path, {"bytes": binding["bytes"], "sha256": binding["sha256"]}, f"audit {binding['slot']} report")
        loaded = aggregate.load_report(report_path)
        require(loaded == report, f"audit {binding['slot']} report content drift")
        require(loaded["run_id"] == binding["run_id"] and loaded["nonce"] == binding["nonce"], f"audit {binding['slot']} identity drift")
    aggregate_path = safe_repo_file(repo_root, AGGREGATE_BINDING["path"], "audit aggregate")
    check_sha_record(aggregate_path, {"bytes": AGGREGATE_BINDING["bytes"], "sha256": AGGREGATE_BINDING["sha256"]}, "audit aggregate")
    aggregate_value = aggregate._duplicate_safe_json(aggregate_path.read_bytes())
    require(
        aggregate_value["schema"] == AGGREGATE_SCHEMA
        and aggregate_value["status"] == STATUS
        and aggregate_value["blockers"] == BLOCKERS,
        "audit aggregate content drift",
    )
    result = audit["result"]
    require(isinstance(result, dict) and set(result) == {"status", "matched", "acceptance", "blockers", "port_order", "dfe_publication", "no_s_parameter_fit", "channel_policy"}, "audit result schema drift")
    require(result["status"] == STATUS and result["blockers"] == BLOCKERS and result["port_order"] == "not_observed" and result["dfe_publication"] == "candidate_not_published" and result["channel_policy"] == "one_final_fd_to_td_impulse", "audit result claim drift")
    require_bool(result["matched"], False, "audit matched")
    require_bool(result["acceptance"], False, "audit acceptance")
    require_bool(result["no_s_parameter_fit"], True, "audit no_s_parameter_fit")
    require(audit["non_claims"] == NON_CLAIMS, "audit non-claim drift")
    markers = audit_path.read_text(encoding="utf-8")
    require(f"# HARNESS_ANCHOR: {HARNESS_COMMIT}|{HARNESS_TREE}" in markers, "audit harness anchor marker missing")
    for binding in REPORT_BINDINGS:
        marker = "# REPORT_ANCHOR: " + "|".join(
            (binding["slot"], binding["path"], str(binding["bytes"]), binding["sha256"], binding["run_id"], binding["nonce"])
        )
        require(marker in markers, f"audit report anchor marker missing: {binding['slot']}")
    require(
        "# AGGREGATE_ANCHOR: "
        + "|".join((AGGREGATE_BINDING["path"], str(AGGREGATE_BINDING["bytes"]), AGGREGATE_BINDING["sha256"]))
        in markers,
        "audit aggregate anchor marker missing",
    )


def validate(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    repo_root: Path = ROOT,
    upstream_root: Path | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(strict=True)
    repo_root = repo_root.resolve(strict=True)
    expected_manifest = safe_repo_file(repo_root, MANIFEST_RELATIVE, "manifest")
    require(manifest_path == expected_manifest, "manifest path is not the fixed repository manifest")
    document = load_yaml(manifest_path, "manifest")
    require(
        set(document)
        == {"schema", "status", "scope", "claims", "non_claims", "harness", "candidate", "upstream", "fixtures", "toolchain", "runs", "aggregate", "observations", "audit", "verification_gate", "anchors"},
        "manifest top-level schema drift",
    )
    require(document["schema"] == MANIFEST_SCHEMA and document["status"] == STATUS, "manifest schema/status drift")
    scope = document["scope"]
    require(isinstance(scope, dict) and set(scope) == {"work_item", "evidence_kind", "result_kind", "candidate_runtime", "acceptance", "release_ready"}, "manifest scope schema drift")
    require_bool(scope["acceptance"], False, "manifest scope acceptance")
    require_bool(scope["release_ready"], False, "manifest scope release_ready")
    require(
        scope
        == {
            "work_item": "COM-v5-formal-replay",
            "evidence_kind": "two_fresh_clean_archive_replays",
            "result_kind": "bounded_scoped_observation",
            "candidate_runtime": "scoped_candidate_only",
            "acceptance": False,
            "release_ready": False,
        },
        "manifest scope overclaim or drift",
    )
    claims = document["claims"]
    require(isinstance(claims, dict) and set(claims) == {"candidate_runtime", "numeric_parity", "port_order", "dfe_publication", "s_parameter_fit", "channel"}, "manifest claims schema drift")
    require_bool(claims["numeric_parity"], False, "manifest claims numeric_parity")
    require_bool(claims["s_parameter_fit"], False, "manifest claims s_parameter_fit")
    require(
        claims
        == {
            "candidate_runtime": "clean_archive_uv_and_native_candidate",
            "numeric_parity": False,
            "port_order": "not_observed",
            "dfe_publication": "not_claimed",
            "s_parameter_fit": False,
            "channel": "one_final_fd_to_td_impulse",
        },
        "manifest claims drift",
    )
    require(document["non_claims"] == NON_CLAIMS, "manifest non-claim drift")
    anchors = document["anchors"]
    require(isinstance(anchors, dict) and set(anchors) == {"algorithm", "harness", "reports", "aggregate", "audit"}, "manifest anchor schema drift")
    expected_anchors = expected_anchor_bindings()
    require(anchors == expected_anchors, "manifest hard anchor graph drift")
    validate_harness(document, repo_root)
    validate_source(document, repo_root, upstream_root)
    validate_fixtures(document)
    validate_verification_gate(document, repo_root)
    require(aggregate is not None, "COM v5 aggregate helper is unavailable")

    toolchain = document["toolchain"]
    require(isinstance(toolchain, dict) and set(toolchain) == {"sha256", "roles", "path_policy"}, "toolchain binding schema drift")
    require(toolchain["sha256"] == "fb742e87d6c468cd45a9cb9bbc149af0ea9fe90780190c802c636252e77b7cbb", "toolchain digest drift")
    require(toolchain["roles"] == ["cargo", "rustc", "python", "uv"] and toolchain["path_policy"] == "path_redacted", "toolchain role/policy drift")

    run_bindings = document["runs"]
    require(isinstance(run_bindings, list) and len(run_bindings) == 2, "two formal runs are required")
    reports: list[dict[str, Any]] = []
    report_paths: list[Path] = []
    run_ids: set[str] = set()
    nonces: set[str] = set()
    for index, (binding, slot) in enumerate(zip(run_bindings, ("run1", "run2"), strict=True)):
        expected_path = f"docs/baselines/com-workbook-accm-replay-v5-{slot}.json"
        require(isinstance(binding, dict) and binding.get("path") == expected_path, f"{slot} path binding drift")
        expected_anchor = REPORT_BINDINGS[index]
        for key in ("slot", "path", "bytes", "sha256", "run_id", "nonce"):
            require(binding.get(key) == expected_anchor[key], f"{slot} hard anchor drift: {key}")
        report_path = safe_repo_file(repo_root, binding["path"], f"{slot} report")
        report = aggregate.load_report(report_path)
        validate_run_record(binding, slot, report_path, repo_root, report, toolchain["sha256"])
        require(report["run_id"] not in run_ids and report["nonce"] not in nonces and report["run_id"] != report["nonce"], "run identity/nonce is not fresh")
        run_ids.add(report["run_id"])
        nonces.add(report["nonce"])
        reports.append(report)
        report_paths.append(report_path)
    require(reports[0]["toolchain"] == reports[1]["toolchain"], "toolchain drift between replays")
    require(reports[0]["blockers"] == BLOCKERS and reports[1]["blockers"] == BLOCKERS, "blocker drift")
    validate_observations(document, reports)

    aggregate_binding = document["aggregate"]
    require(
        isinstance(aggregate_binding, dict)
        and aggregate_binding == AGGREGATE_BINDING,
        "aggregate binding schema/status drift",
    )
    aggregate_path = safe_repo_file(repo_root, aggregate_binding["path"], "aggregate")
    check_sha_record(aggregate_path, {"bytes": aggregate_binding["bytes"], "sha256": aggregate_binding["sha256"]}, "aggregate")
    aggregate_value = aggregate._duplicate_safe_json(aggregate_path.read_bytes())
    require(aggregate_value["schema"] == AGGREGATE_SCHEMA and aggregate_value["status"] == STATUS and aggregate_value["blockers"] == BLOCKERS, "aggregate result drift")
    with tempfile.TemporaryDirectory(prefix="com-v5-aggregate-verify-") as directory:
        regenerated_path = Path(directory) / aggregate_path.name
        regenerated = aggregate.aggregate(report_paths[0], report_paths[1], regenerated_path)
        require(regenerated == aggregate_value, "aggregate does not reproduce from bound reports")

    validate_audit(document, repo_root, reports)
    return {
        "schema": MANIFEST_SCHEMA,
        "status": STATUS,
        "formal_replays": 2,
        "candidate_commit": CANDIDATE_COMMIT,
        "upstream_commit": UPSTREAM_COMMIT,
        "blockers": BLOCKERS,
        "port_order": "not_observed",
        "dfe_publication": "candidate_not_published",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--upstream-root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.manifest, repo_root=args.repo_root, upstream_root=args.upstream_root), sort_keys=True))
    except (OSError, KeyError, TypeError, VerificationError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
