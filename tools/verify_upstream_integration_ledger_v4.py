"""Verify the additive orthogonal upstream integration ledger v4."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/baselines/upstream-integration-ledger.v4.yaml"
SCHEMA = "sipi.upstream-integration-ledger.v4"
COMMIT = "e1a9ca876c57bdf196974ae7b640e5ae73b6f18c"
TREE = "ab34cc91ff482fa7494f0b3c36842345ad46e519"
ARCHIVE = "d4c576ddf6ded979896c47dca8142aed7c57555ac1977edc924088e7bf939311"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_ROWS = {
    "AS-01": ("agent_spice", "fit-sparam"),
    "AS-02": ("agent_spice", "fit-sparam-cascade"),
    "AS-03": ("agent_spice", "fit-yparam"),
    "AS-04": ("agent_spice", "tune-yparam-tran"),
    "AS-05": ("agent_spice", "run-hspice"),
    "AS-06": ("agent_spice", "run-rfm"),
    "PB-01": ("pybert", "sim"),
    "PB-02": ("pybert", "sim-native"),
    "PB-03": ("pybert", "sim-rust"),
    "PB-04": ("pybert", "sim-auto"),
    "PB-05": ("pybert", "sim-compare"),
    "COM-01": ("agent_com", "config-validate"),
    "COM-02": ("agent_com", "run"),
    "COM-03": ("agent_com", "compare"),
    "COM-04": ("agent_com", "load_config-run_com-write_artifacts"),
}
AUTHORITIES = {
    "agent_spice": {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "license": "MIT"},
    "pybert": {"commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe", "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24", "license": "BSD-3-Clause"},
    "agent_com": {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "license": "MIT"},
}
ROW_POLICIES = {
    "AS-01": ("direct_rust_port", "portable", "scoped_numeric_mismatch_open", "open_no_release"),
    "AS-02": ("direct_rust_port", "portable", "scoped_numeric_mismatch_open", "open_no_release"),
    "AS-03": ("direct_rust_port", "portable", "scoped_numeric_mismatch_open", "open_no_release"),
    "AS-04": ("direct_rust_port", "external_solver_required", "external_blocker_observed", "open_no_release"),
    "AS-05": ("direct_rust_port", "external_solver_required", "external_blocker_observed", "open_no_release"),
    "AS-06": ("direct_rust_port", "external_solver_required", "external_blocker_observed", "open_no_release"),
    "PB-01": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-02": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-03": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-04": ("retained_external_runtime", "external_asset_required", "external_blocker_observed", "open_no_release"),
    "PB-05": ("retained_external_runtime", "external_asset_required", "external_blocker_observed", "open_no_release"),
    "COM-01": ("direct_rust_port", "unavailable", "historical_only", "open_no_release"),
    "COM-02": ("direct_rust_port", "external_asset_required", "upstream_only_timeout", "open_no_release"),
    "COM-03": ("direct_rust_port", "unavailable", "historical_only", "open_no_release"),
    "COM-04": ("direct_rust_port", "external_asset_required", "upstream_only_timeout", "open_no_release"),
}
SUPPLEMENTAL = {
    "pb-02-metallic-grid": {
        "path": "docs/baselines/pb-02-metallic-grid.v1.yaml",
        "sha256": "a2c26a3e24a558c0b7a3d268cb125135639d62c8cc461ba9d677d342c1184b3f",
        "schema": "sipi.pb-02-metallic-grid.v1",
        "scope": "scoped_numeric_checkpoint_only",
    },
    "com-td-crosstalk-stage-replay": {
        "path": "docs/baselines/com-td-crosstalk-stage-replay-v1.manifest.json",
        "sha256": "4c94f367e23aeb8622d68c8b07d569a3e1c719e69b4c3907854f4deb7d8563e4",
        "schema": "sipi.com.td-crosstalk-stage-replay.v1",
        "scope": "environment_local_scoped_observation_only",
    },
}
DISPOSITIONS = {"direct_rust_port", "retained_external_runtime", "external_asset", "oracle_only", "excluded_fail_closed"}
RUNTIMES = {"portable", "external_solver_required", "external_asset_required", "unavailable"}
EVIDENCE = {"scoped_numeric_mismatch_open", "scoped_observation", "external_blocker_observed", "upstream_only_timeout", "historical_only"}
RELEASES = {"open_no_release", "scoped_only_no_release", "excluded_no_release"}
TOP_KEYS = {"schema", "status", "successor", "candidate", "policy", "allowed_values", "source_authority", "provenance_documents", "harness", "audit", "supplemental_evidence", "rows", "summary"}
SUCCESSOR = {"predecessor": "docs/baselines/upstream-rust-parity-ledger.v3.yaml", "reason": "additive orthogonal disposition/runtime/evidence/release view; historical ledgers retained"}
POLICY = {
    "new_domain_features_allowed": False,
    "direct_rust_port_requires_named_upstream_behavior": True,
    "external_runtime_is_not_parity": True,
    "scoped_observation_is_not_global_parity": True,
    "release_promotion_requires_branch_complete_evidence": True,
}
ALLOWED_VALUES = {
    "integration_disposition": ["direct_rust_port", "retained_external_runtime", "external_asset", "oracle_only", "excluded_fail_closed"],
    "runtime_availability": ["portable", "external_solver_required", "external_asset_required", "unavailable"],
    "parity_evidence": ["scoped_numeric_mismatch_open", "scoped_observation", "external_blocker_observed", "upstream_only_timeout", "historical_only"],
    "release_state": ["open_no_release", "scoped_only_no_release", "excluded_no_release"],
}
CANDIDATE = {"commit": COMMIT, "tree": TREE, "archive_sha256": ARCHIVE, "archive_bytes": 42854400, "materialization": "clean_git_archive", "worktree_overlay": False}
SOURCE_AUTHORITIES = {
    "agent_spice": {"commit": AUTHORITIES["agent_spice"]["commit"], "tree": AUTHORITIES["agent_spice"]["tree"], "license": "MIT", "license_blob_sha1": "55aac2e4f8c36a978d315efb02815972579b8293", "license_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"},
    "pybert": {"commit": AUTHORITIES["pybert"]["commit"], "tree": AUTHORITIES["pybert"]["tree"], "license": "BSD-3-Clause", "license_blob_sha1": "64d198ba43675ede5fbdef1ec918a63954951640", "license_sha256": "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1"},
    "agent_com": {"commit": AUTHORITIES["agent_com"]["commit"], "tree": AUTHORITIES["agent_com"]["tree"], "license": "MIT", "license_blob_sha1": "55aac2e4f8c36a978d315efb02815972579b8293", "license_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"},
}
PROVENANCE = [
    ("docs/baselines/upstream-migration-inventory.v1.yaml", "1d1a3fc2e43be26884554ca8a1d94217ade6142c0e1ae92a686eaba9b6ca5a86"),
    ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-MIT.md", "a46b7e9dbe697f40922ae5d8c77087e16b8b7a21bd84c11435e9bc6dc646c48c"),
    ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-01.txt", "d43d8a5e91aa303434466ede2fcf4237860eae53148732f6cb87dc8de0b88dbc"),
    ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-05.txt", "04e5b257de1cdd4fc9012c12cc2095933e304c4790203c412961c5103ec8d711"),
    ("docs/baselines/as-05-run-hspice-output-source-map.v1.yaml", "dd35889243e8f5fe5618c436b410eb4b4d83afbc8bd088b6320c76ed88ff6e38"),
    ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-06.txt", "abe80cb534c637e9169a8703db8ffc6c51f6d66f1eec8aae8cfd6be5052c7880"),
    ("docs/baselines/as-06-run-rfm-source-map.v1.yaml", "df8bf873f3c39491c6efd4434e60119f98b198d115a9bff94e37dcaac385ffb1"),
    ("crates/sipi-pybert-direct/NOTICE-PYBERT-LICENSE-BOUNDARY.md", "77c20eb0cc8411b7826666e6673b7c388ce508fd80029e0d302a116fa5d237e6"),
    ("crates/sipi-agent-com-direct/NOTICE-AGENT-COM-MIT.md", "04344354a492e4afa55a71fe6fd39047f8ee52f78370ea0ea4fb243d9104817f"),
]
HARNESS = {"verifier": {"path": "tools/verify_upstream_integration_ledger_v4.py"}, "mutation_tests": {"path": "tools/test_verify_upstream_integration_ledger_v4.py", "sha256": "f7aee11cb73fe81ed8d3d062e520b34b012c10f86b21450905cb892951d16ebb"}}
AUDIT = {"path": "docs/baselines/audits/2026-08-24-upstream-integration-ledger-v4.md", "sha256": "7729b2af1f977805b071c0a4a24e0aba87141ef6d4c8dc73f20d30a4cb53b6fa"}
ROW_KEYS = {"id", "repo", "public_entrypoint", "integration_disposition", "runtime_availability", "parity_evidence", "release_state", "evidence", "non_claims"}
FILE_BINDING_KEYS = {"path", "sha256"}
ROW_ORDER = tuple(EXPECTED_ROWS)
ROW_DETAILS = {
    "AS-01": ("agent_spice", "fit-sparam", ROW_POLICIES["AS-01"], "docs/baselines/as-01-fit-sparam-bound-clean-archive-v3.yaml", "7b1e82ea428f0fe6f5a9fd39157ad3251c416e97929f82de7129c7098dcb01b8", ("no_global_parity", "no_release", "no_product_capability_promotion")),
    "AS-02": ("agent_spice", "fit-sparam-cascade", ROW_POLICIES["AS-02"], "docs/baselines/as-02-fit-sparam-cascade-numeric-bound-v3.yaml", "65b2ef5908a3920a18a209c56e5f73be50db5ac6ae2aeeb37a43b775cde843ee", ("no_global_parity", "no_release", "no_product_capability_promotion")),
    "AS-03": ("agent_spice", "fit-yparam", ROW_POLICIES["AS-03"], "docs/baselines/as-03-fit-yparam-numeric-bound-v2.yaml", "0ce8d64e0fa3dd8ec31a9073b0127782826106c641261984afc5932b50f669aa", ("no_global_parity", "no_release", "no_product_capability_promotion")),
    "AS-04": ("agent_spice", "tune-yparam-tran", ROW_POLICIES["AS-04"], "docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml", "3e42e662be21b1814f0b37fb915a66441d0af2bcc0ab7ddd1ca77d1fac4883c8", ("no_solver_result", "no_global_parity", "no_release")),
    "AS-05": ("agent_spice", "run-hspice", ROW_POLICIES["AS-05"], "docs/baselines/as-05-run-hspice-rust-control-direct-port.v2.yaml", "6ba0b596ba96b1cf41fb556027f25c60852917b90cf78c6ccce77c10f3856015", ("workflow_observed_only", "no_solver_result", "no_global_parity", "no_release")),
    "AS-06": ("agent_spice", "run-rfm", ROW_POLICIES["AS-06"], "docs/baselines/as-06-run-rfm-direct-port.v2.yaml", "b1b52a43dc8de03b98461b9af20629edfed5167df88fbc80135703df89deda90", ("workflow_observed_only", "no_solver_result", "no_global_parity", "no_release")),
    "PB-01": ("pybert", "sim", ROW_POLICIES["PB-01"], "docs/baselines/pb-01-legacy-leaf-current-d3154093.v1.yaml", "40f1721b20f1affcaa381270b760e4e9fa4896f8a8674b1c8a408d78de6f9312", ("no_global_parity", "no_branch_completion", "no_release")),
    "PB-02": ("pybert", "sim-native", ROW_POLICIES["PB-02"], "docs/baselines/pb-02-direct-current-d3154093.v1.yaml", "00ae4121f3136c9ba993b1a5a666635f260b9952acb213517796e638f40aa0d4", ("no_global_parity", "no_branch_completion", "no_release")),
    "PB-03": ("pybert", "sim-rust", ROW_POLICIES["PB-03"], "docs/baselines/pb-03-legacy-branch-coverage-d3154093.v1.yaml", "5f6203e7ffc718bae7501546d3021d08088bf90b8e051571c093ee0f87de9a92", ("no_candidate_parity", "no_global_parity", "no_release")),
    "PB-04": ("pybert", "sim-auto", ROW_POLICIES["PB-04"], "docs/baselines/pb-04-direct-port.current-bound.v1.yaml", "b13a8d42946d5685344f8e03c78dff3d8c40c51e1f57f52a093b69571742f8b1", ("no_external_asset", "no_global_parity", "no_release")),
    "PB-05": ("pybert", "sim-compare", ROW_POLICIES["PB-05"], "docs/baselines/pb-05-direct-port.current-bound.v1.yaml", "3876ae5a1e827d80ccfc08fdbb72a3b3bb743130d2efcccc2533de7c8439a39d", ("no_external_asset", "no_global_parity", "no_release")),
    "COM-01": ("agent_com", "config-validate", ROW_POLICIES["COM-01"], "docs/baselines/com-01-direct-replay-bound.v2.yaml", "a5581ddfd6284a5345845c276915933f8529f6300cddc14c09fa2a534589db32", ("historical_only", "no_current_parity", "no_release")),
    "COM-02": ("agent_com", "run", ROW_POLICIES["COM-02"], "docs/baselines/com-upstream-runtime-oracle.v2.yaml", "05af738f6c32ea4f96021050ddc43c67cc8f4d1a6fb976fc366c79c6629e30a2", ("no_candidate_parity", "no_full_entrypoint_parity", "no_release")),
    "COM-03": ("agent_com", "compare", ROW_POLICIES["COM-03"], "docs/baselines/com-03-direct-port-bound.v2.yaml", "13792b8be122d247cf3cb41a3361caec9fad1cb15c8f3633624d1d98da17a4ac", ("historical_only", "no_current_parity", "no_release")),
    "COM-04": ("agent_com", "load_config-run_com-write_artifacts", ROW_POLICIES["COM-04"], "docs/baselines/com-upstream-runtime-oracle.v2.yaml", "05af738f6c32ea4f96021050ddc43c67cc8f4d1a6fb976fc366c79c6629e30a2", ("no_candidate_parity", "no_full_entrypoint_parity", "no_release")),
}
SUMMARY = {"rows": 15, "direct_rust_port": 13, "retained_external_runtime": 2, "external_asset": 0, "oracle_only": 0, "excluded_fail_closed": 0, "release_ready": 0}


class LedgerError(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise LedgerError(reason)


def _load(path: Path = LEDGER) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise LedgerError(f"document_invalid:{path}") from error
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hex(value: object, pattern: re.Pattern[str], reason: str) -> None:
    _require(isinstance(value, str) and pattern.fullmatch(value) is not None, reason)


def _safe_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\\" not in value and not value.startswith("/") and ".." not in value.split("/")


def _file_binding(item: Any, reason: str) -> None:
    _require(isinstance(item, dict), f"{reason}_shape")
    path = item.get("path")
    _require(_safe_path(path), f"{reason}_path")
    _hex(item.get("sha256"), HEX64, f"{reason}_hash_shape")
    target = ROOT / path
    _require(target.is_file(), f"{reason}_missing")
    _require(_sha(target) == item["sha256"], f"{reason}_hash_drift")


def _validate_supplemental(document: dict[str, Any]) -> None:
    items = document.get("supplemental_evidence")
    _require(isinstance(items, list) and len(items) == len(SUPPLEMENTAL), "supplemental_count")
    seen: set[str] = set()
    for item in items:
        _require(isinstance(item, dict), "supplemental_shape")
        _require(set(item) == {"id", "path", "sha256", "scope", "parity_promotion", "release_promotion"}, f"supplemental_keys:{item.get('id')}")
        item_id = item.get("id")
        _require(item_id in SUPPLEMENTAL and item_id not in seen, f"supplemental_id:{item_id}")
        seen.add(item_id)
        expected = SUPPLEMENTAL[item_id]
        _require(item.get("path") == expected["path"], f"supplemental_path:{item_id}")
        _require(item.get("sha256") == expected["sha256"], f"supplemental_sha:{item_id}")
        _require(item.get("scope") == expected["scope"], f"supplemental_scope:{item_id}")
        _require(item.get("parity_promotion") is False and item.get("release_promotion") is False, f"supplemental_promotion:{item_id}")
        _file_binding(item, f"supplemental:{item_id}")
        target = ROOT / expected["path"]
        try:
            payload = yaml.safe_load(target.read_text(encoding="utf-8")) if target.suffix in {".yaml", ".yml"} else json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
            raise LedgerError(f"supplemental_document_invalid:{item_id}") from error
        _require(isinstance(payload, dict) and payload.get("schema") == expected["schema"], f"supplemental_schema:{item_id}")
        if item_id == "pb-02-metallic-grid":
            claims = payload.get("claims")
            _require(isinstance(claims, dict) and claims.get("global_payload_parity") is False and claims.get("promotion") is False, "supplemental_scope:pb-02-metallic-grid_claims")
        else:
            candidate = payload.get("candidate")
            _require(isinstance(candidate, dict) and candidate.get("commit") == COMMIT and candidate.get("tree") == TREE and candidate.get("archive_sha256") == ARCHIVE, "supplemental_scope:com-td-crosstalk-stage-replay_candidate")
    _require(seen == set(SUPPLEMENTAL), "supplemental_set")


def _git(*args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=False)
    _require(result.returncode == 0, f"git_failed:{args[-1]}")
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def validate(document: dict[str, Any]) -> dict[str, Any]:
    _require(set(document) == TOP_KEYS, "top_keys")
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "current_clean_candidate_open_no_release", "status_promoted")
    _require(document.get("successor") == SUCCESSOR, "successor_drift")
    _require(document.get("policy") == POLICY, "policy_drift")
    _require(document.get("allowed_values") == ALLOWED_VALUES, "allowed_values_drift")
    candidate = document.get("candidate")
    _require(isinstance(candidate, dict), "candidate_missing")
    _require(set(candidate) == set(CANDIDATE), "candidate_keys")
    for key, expected_value in CANDIDATE.items():
        _require(candidate.get(key) == expected_value, f"candidate_{key}_drift")
    _require(candidate.get("commit") == COMMIT, "candidate_commit_drift")
    _require(candidate.get("tree") == TREE, "candidate_tree_drift")
    _require(candidate.get("archive_sha256") == ARCHIVE, "candidate_archive_drift")
    _hex(candidate.get("commit"), HEX40, "candidate_commit_shape")
    _hex(candidate.get("tree"), HEX40, "candidate_tree_shape")
    _hex(candidate.get("archive_sha256"), HEX64, "candidate_archive_shape")
    _require(_git("show", "-s", "--format=%T", COMMIT) == TREE, "candidate_git_tree_drift")
    _require(hashlib.sha256(_git("archive", "--format=tar", COMMIT, binary=True)).hexdigest() == ARCHIVE, "candidate_git_archive_drift")

    authorities = document.get("source_authority")
    _require(isinstance(authorities, dict) and set(authorities) == set(SOURCE_AUTHORITIES), "source_authority_set")
    for name, expected in SOURCE_AUTHORITIES.items():
        value = authorities[name]
        _require(isinstance(value, dict) and set(value) == set(expected), f"source_authority_keys:{name}")
        for key, expected_value in expected.items():
            _require(value.get(key) == expected_value, f"source_authority_drift:{name}:{key}")
        _hex(value.get("commit"), HEX40, f"source_authority_commit:{name}")
        _hex(value.get("tree"), HEX40, f"source_authority_tree:{name}")
        _hex(value.get("license_blob_sha1"), HEX40, f"source_authority_license_sha1:{name}")
        _hex(value.get("license_sha256"), HEX64, f"source_authority_license_sha256:{name}")

    provenance = document.get("provenance_documents")
    _require(isinstance(provenance, list) and len(provenance) == len(PROVENANCE) and [x.get("path") for x in provenance] == [x[0] for x in PROVENANCE], "provenance_exact")
    for index, item in enumerate(provenance):
        _require(isinstance(item, dict) and set(item) == FILE_BINDING_KEYS, f"provenance_keys:{index}")
        _file_binding(item, f"provenance:{index}")
    _require([(x.get("path"), x.get("sha256")) for x in provenance] == PROVENANCE, "provenance_exact")
    harness = document.get("harness")
    _require(set(harness) == set(HARNESS) and harness.get("verifier", {}).get("path") == HARNESS["verifier"]["path"] and harness.get("mutation_tests") == HARNESS["mutation_tests"], "harness_exact")
    _require(set(harness["verifier"]) == FILE_BINDING_KEYS, "harness_verifier_keys")
    _require(set(harness["mutation_tests"]) == FILE_BINDING_KEYS, "harness_mutation_keys")
    _file_binding(harness.get("verifier"), "harness_verifier")
    _file_binding(harness.get("mutation_tests"), "harness_mutations")
    audit = document.get("audit")
    _require(isinstance(audit, dict) and set(audit) == set(AUDIT) and audit.get("path") == AUDIT["path"], "audit_exact")
    _file_binding(audit, "audit")
    audit_text = (ROOT / AUDIT["path"]).read_text(encoding="utf-8")
    for marker in (SCHEMA, "current_clean_candidate_open_no_release", COMMIT, TREE, ARCHIVE, "15 rows", "0 release-ready", "does not promote"):
        _require(marker in audit_text, f"audit_semantics:{marker}")
    _validate_supplemental(document)

    rows = document.get("rows")
    _require(isinstance(rows, list) and len(rows) == len(EXPECTED_ROWS), "row_count")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        _require(isinstance(row, dict), "row_shape")
        _require(set(row) == ROW_KEYS, f"row_keys:{row.get('id')}")
        row_id = row.get("id")
        _require(isinstance(row_id, str) and row_id in EXPECTED_ROWS and row_id not in seen, f"row_set:{row_id}")
        _require(row_id == ROW_ORDER[index], f"row_order:{row_id}")
        seen.add(row_id)
        repo, entry, policy, evidence_path, evidence_sha, non_claims = ROW_DETAILS[row_id]
        _require((row.get("repo"), row.get("public_entrypoint")) == (repo, entry), f"row_identity:{row_id}")
        _require(row.get("integration_disposition") in DISPOSITIONS, f"disposition:{row_id}")
        _require(row.get("runtime_availability") in RUNTIMES, f"runtime:{row_id}")
        _require(row.get("parity_evidence") in EVIDENCE, f"evidence:{row_id}")
        _require(row.get("release_state") in RELEASES, f"release:{row_id}")
        _require(tuple(row.get(key) for key in ("integration_disposition", "runtime_availability", "parity_evidence", "release_state")) == ROW_POLICIES[row_id], f"row_policy:{row_id}")
        _require(row.get("release_state") != "excluded_no_release" or row.get("integration_disposition") == "excluded_fail_closed", f"excluded_state:{row_id}")
        _file_binding(row.get("evidence"), f"row_evidence:{row_id}")
        _require(row.get("evidence") == {"path": evidence_path, "sha256": evidence_sha}, f"row_evidence_binding:{row_id}")
        _require(tuple(row.get("non_claims", [])) == non_claims, f"row_non_claims:{row_id}")
    _require(seen == set(EXPECTED_ROWS), "row_set_incomplete")
    summary = document.get("summary")
    counts = {name: sum(row["integration_disposition"] == name for row in rows) for name in DISPOSITIONS}
    calculated_summary = {"rows": len(rows), **counts, "release_ready": 0}
    _require(summary == SUMMARY == calculated_summary, "summary_drift")
    return {"valid": True, "rows": len(rows), "release_ready": 0}


def main() -> int:
    result = validate(_load())
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
