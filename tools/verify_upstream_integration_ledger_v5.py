"""Verify the additive upstream integration ledger v5."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/baselines/upstream-integration-ledger.v5.yaml"
SCHEMA = "sipi.upstream-integration-ledger.v5"
COMMIT = "9aeb69173daefc59f77205280931896fed7bf9a8"
TREE = "815eda3c7ed2e692588f4f0161b0ff82831e40a7"
ARCHIVE = "e73ac6c8b7cfe816753c058620f7ce3d144b01f948c1be6942db3236f06788ee"
ARCHIVE_BYTES = 43458560
EXPECTED_AUDIT_SHA256 = "fa7e96b98279ed55cd25681a1f837a5e10ef28a59ef9162c41e85c8c0388a508"
EXPECTED_MUTATION_SHA256 = "994db9351646b5f9c9cad67c6285a3aaa5b1a4e65128b62ff22f9850db1294ec"
EXPECTED_VERIFIER_ANCHOR_SHA256 = "96030b5add4aa612cc8ea2b2747fd949170dbf299899c5031c2da263f6ad39d0"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_ROWS = (
    ("AS-01", "agent_spice", "fit-sparam"),
    ("AS-02", "agent_spice", "fit-sparam-cascade"),
    ("AS-03", "agent_spice", "fit-yparam"),
    ("AS-04", "agent_spice", "tune-yparam-tran"),
    ("AS-05", "agent_spice", "run-hspice"),
    ("AS-06", "agent_spice", "run-rfm"),
    ("PB-01", "pybert", "sim"),
    ("PB-02", "pybert", "sim-native"),
    ("PB-03", "pybert", "sim-rust"),
    ("PB-04", "pybert", "sim-auto"),
    ("PB-05", "pybert", "sim-compare"),
    ("COM-01", "agent_com", "config-validate"),
    ("COM-02", "agent_com", "run"),
    ("COM-03", "agent_com", "compare"),
    ("COM-04", "agent_com", "load_config-run_com-write_artifacts"),
)
POLICY = {
    "new_domain_features_allowed": False,
    "direct_rust_port_requires_named_upstream_behavior": True,
    "external_runtime_is_not_parity": True,
    "scoped_observation_is_not_global_parity": True,
    "release_promotion_requires_branch_complete_evidence": True,
}
ALLOWED = {
    "integration_disposition": ["direct_rust_port", "retained_external_runtime", "external_asset", "oracle_only", "excluded_fail_closed"],
    "runtime_availability": ["portable", "external_solver_required", "external_asset_required", "unavailable"],
    "parity_evidence": ["scoped_numeric_mismatch_open", "scoped_observation", "external_blocker_observed", "external_solver_not_verified", "external_vendor_numeric_parity_unverified", "upstream_only_timeout", "historical_only"],
    "release_state": ["open_no_release", "scoped_only_no_release", "excluded_no_release"],
}
AUTHORITIES = {
    "agent_spice": ("2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "b6bde97128030d6cea0d68b2f0a35d807be8c402", "MIT", "55aac2e4f8c36a978d315efb02815972579b8293", "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"),
    "pybert": ("5bf6d7ea0ace261891aaeb611ffc1c267e160afe", "5faef6bdb341d444ad65d82a11c0018b15805e24", "BSD-3-Clause", "64d198ba43675ede5fbdef1ec918a63954951640", "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c"),
    "agent_com": ("5272ffe74702cd585054d975559b06f8afae7b6e", "7094ab6e84989b218730c52432c70da10261f8ea", "MIT", "55aac2e4f8c36a978d315efb02815972579b8293", "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"),
}
PROVENANCE = {
    "docs/baselines/upstream-migration-inventory.v1.yaml": "1d1a3fc2e43be26884554ca8a1d94217ade6142c0e1ae92a686eaba9b6ca5a86",
    "crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-MIT.md": "a46b7e9dbe697f40922ae5d8c77087e16b8b7a21bd84c11435e9bc6dc646c48c",
    "crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-01.txt": "d43d8a5e91aa303434466ede2fcf4237860eae53148732f6cb87dc8de0b88dbc",
    "crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-05.txt": "04e5b257de1cdd4fc9012c12cc2095933e304c4790203c412961c5103ec8d711",
    "docs/baselines/as-05-run-hspice-output-source-map.v1.yaml": "dd35889243e8f5fe5618c436b410eb4b4d83afbc8bd088b6320c76ed88ff6e38",
    "crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-06.txt": "abe80cb534c637e9169a8703db8ffc6c51f6d66f1eec8aae8cfd6be5052c7880",
    "docs/baselines/as-06-run-rfm-source-map.v1.yaml": "df8bf873f3c39491c6efd4434e60119f98b198d115a9bff94e37dcaac385ffb1",
    "crates/sipi-pybert-direct/NOTICE-PYBERT-LICENSE-BOUNDARY.md": "77c20eb0cc8411b7826666e6673b7c388ce508fd80029e0d302a116fa5d237e6",
    "crates/sipi-agent-com-direct/NOTICE-AGENT-COM-MIT.md": "04344354a492e4afa55a71fe6fd39047f8ee52f78370ea0ea4fb243d9104817f",
}
EVIDENCE = {
    "AS-01": ("docs/baselines/as-01-fit-sparam-bound-clean-archive-v3.yaml", "7b1e82ea428f0fe6f5a9fd39157ad3251c416e97929f82de7129c7098dcb01b8"),
    "AS-02": ("docs/baselines/as-02-fit-sparam-cascade-numeric-bound-v3.yaml", "65b2ef5908a3920a18a209c56e5f73be50db5ac6ae2aeeb37a43b775cde843ee"),
    "AS-03": ("docs/baselines/as-03-fit-yparam-numeric-bound-v2.yaml", "0ce8d64e0fa3dd8ec31a9073b0127782826106c641261984afc5932b50f669aa"),
    "AS-04": ("docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml", "3e42e662be21b1814f0b37fb915a66441d0af2bcc0ab7ddd1ca77d1fac4883c8"),
    "AS-05": ("docs/baselines/as-05-run-hspice-rust-control-direct-port.v2.yaml", "6ba0b596ba96b1cf41fb556027f25c60852917b90cf78c6ccce77c10f3856015"),
    "AS-06": ("docs/baselines/as-06-run-rfm-direct-port.v2.yaml", "b1b52a43dc8de03b98461b9af20629edfed5167df88fbc80135703df89deda90"),
    "PB-01": ("docs/baselines/pb-01-legacy-leaf-current-d3154093.v1.yaml", "40f1721b20f1affcaa381270b760e4e9fa4896f8a8674b1c8a408d78de6f9312"),
    "PB-02": ("docs/baselines/pb-02-direct-current-d3154093.v1.yaml", "00ae4121f3136c9ba993b1a5a666635f260b9952acb213517796e638f40aa0d4"),
    "PB-03": ("docs/baselines/pb-03-legacy-branch-coverage-d3154093.v1.yaml", "5f6203e7ffc718bae7501546d3021d08088bf90b8e051571c093ee0f87de9a92"),
    "PB-04": ("docs/baselines/pb-04-direct-port.current-bound.v1.yaml", "b13a8d42946d5685344f8e03c78dff3d8c40c51e1f57f52a093b69571742f8b1"),
    "PB-05": ("docs/baselines/pb-05-direct-port.current-bound.v1.yaml", "3876ae5a1e827d80ccfc08fdbb72a3b3bb743130d2efcccc2533de7c8439a39d"),
    "COM-01": ("docs/baselines/com-01-direct-replay-bound.v2.yaml", "a5581ddfd6284a5345845c276915933f8529f6300cddc14c09fa2a534589db32"),
    "COM-02": ("docs/baselines/com-upstream-runtime-oracle.v2.yaml", "05af738f6c32ea4f96021050ddc43c67cc8f4d1a6fb976fc366c79c6629e30a2"),
    "COM-03": ("docs/baselines/com-03-direct-port-bound.v2.yaml", "13792b8be122d247cf3cb41a3361caec9fad1cb15c8f3633624d1d98da17a4ac"),
    "COM-04": ("docs/baselines/com-upstream-runtime-oracle.v2.yaml", "05af738f6c32ea4f96021050ddc43c67cc8f4d1a6fb976fc366c79c6629e30a2"),
}
POLICIES = {
    **{key: ("direct_rust_port", "portable", "scoped_numeric_mismatch_open", "open_no_release") for key in ("AS-01", "AS-02", "AS-03")},
    "AS-04": ("direct_rust_port", "external_solver_required", "external_blocker_observed", "open_no_release"),
    "AS-05": ("direct_rust_port", "external_solver_required", "external_solver_not_verified", "open_no_release"),
    "AS-06": ("direct_rust_port", "external_solver_required", "external_blocker_observed", "open_no_release"),
    **{key: ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release") for key in ("PB-01", "PB-02", "PB-03")},
    "PB-04": ("retained_external_runtime", "external_asset_required", "external_vendor_numeric_parity_unverified", "open_no_release"),
    "PB-05": ("retained_external_runtime", "external_asset_required", "external_vendor_numeric_parity_unverified", "open_no_release"),
    "COM-01": ("direct_rust_port", "unavailable", "historical_only", "open_no_release"),
    "COM-02": ("direct_rust_port", "external_asset_required", "upstream_only_timeout", "open_no_release"),
    "COM-03": ("direct_rust_port", "unavailable", "historical_only", "open_no_release"),
    "COM-04": ("direct_rust_port", "external_asset_required", "upstream_only_timeout", "open_no_release"),
}
NONCLAIMS = {
    "AS-01": ["no_global_parity", "no_release", "no_product_capability_promotion"],
    "AS-02": ["no_global_parity", "no_release", "no_product_capability_promotion"],
    "AS-03": ["no_global_parity", "no_release", "no_product_capability_promotion"],
    "AS-04": ["no_solver_result", "no_global_parity", "no_release"],
    "AS-05": ["workflow_observed_only", "attested_external_ngspice_consumption_only", "external_solver_not_verified", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"],
    "AS-06": ["workflow_observed_only", "no_solver_result", "no_global_parity", "no_release"],
    "PB-01": ["no_global_parity", "no_branch_completion", "no_release"],
    "PB-02": ["no_global_parity", "no_branch_completion", "no_release"],
    "PB-03": ["no_candidate_parity", "no_global_parity", "no_release"],
    "PB-04": ["mock_dll_receipt_only", "no_vendor_dll_numeric_parity", "no_external_asset", "no_global_parity", "no_release"],
    "PB-05": ["mock_dll_receipt_only", "no_vendor_dll_numeric_parity", "no_external_asset", "no_global_parity", "no_release"],
    "COM-01": ["historical_only", "no_current_parity", "no_release"],
    "COM-02": ["no_candidate_parity", "no_full_entrypoint_parity", "selector_only", "no_package_vtf_s4p_cascade", "no_sparam_fit", "impulse_only", "no_release"],
    "COM-03": ["historical_only", "no_current_parity", "no_release"],
    "COM-04": ["no_candidate_parity", "no_full_entrypoint_parity", "selector_only", "no_package_vtf_s4p_cascade", "no_sparam_fit", "impulse_only", "no_release"],
}
SUPPLEMENTALS = {
    "as05-attested-ngspice": ("docs/baselines/as-05-ngspice-scoped-observation-v2.manifest.json", "47656c53fda3d39a29b3577945471dbfd21e68dc2f167ad43bfab72aeacb9a55", "attested_external_ngspice_consumption_immutable_replay_only", tuple(NONCLAIMS["AS-05"][2:])),
    "pb-external-worker-mock": ("crates/sipi-pybert-direct/SOURCE-MAP-PB-EXTERNAL-HOST.md", "3f5cd91d1f4c44d9103744667f6eada513740dc40bcdc77192fa614d5dcdf894", "mock_dll_typed_receipt_only_vendor_asset_external"),
    "com-selector-vtf-gap": ("crates/sipi-agent-com-direct/SOURCE-MAP-COM-02.md", "b8d86ecc2098c5a4d318029cf0bdea66fcb0cfb7aa7f74165b3073d699a02899", "selector_direct_port_package_vtf_s4p_cascade_blocked"),
}
TOP_KEYS = {"schema", "status", "successor", "candidate", "policy", "allowed_values", "source_authority", "provenance_documents", "harness", "audit", "supplemental_evidence", "rows", "summary"}


class LedgerError(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise LedgerError(reason)


def _sha(path: Path) -> str:
    data = path.read_bytes()
    if path.resolve() == ROOT / "tools/verify_upstream_integration_ledger_v5.py":
        data = re.sub(rb'EXPECTED_VERIFIER_ANCHOR_SHA256 = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_ANCHOR_SHA256 = "<self-anchor>"', data, count=1)
    if path.resolve() == ROOT / "tools/test_verify_upstream_integration_ledger_v5.py":
        data = re.sub(rb'EXPECTED_VERIFIER_SHA256 = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA256 = "<verifier-anchor>"', data, count=1)
    return hashlib.sha256(data).hexdigest()


def _safe_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and not value.startswith("/") and "\\" not in value and ".." not in value.split("/")


def _binding(item: Any, reason: str) -> None:
    _require(isinstance(item, dict) and set(item) == {"path", "sha256"}, f"{reason}_keys")
    _require(_safe_path(item["path"]), f"{reason}_path")
    _require(isinstance(item["sha256"], str) and HEX64.fullmatch(item["sha256"]), f"{reason}_hash_shape")
    target = ROOT / item["path"]
    _require(target.is_file(), f"{reason}_missing")
    _require(_sha(target) == item["sha256"], f"{reason}_hash_drift")


def _load(path: Path = LEDGER) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def validate(document: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(document, dict), "document_not_mapping")
    _require(set(document) == TOP_KEYS, "top_keys")
    _require(document["schema"] == SCHEMA, "schema_invalid")
    _require(document["status"] == "current_clean_candidate_open_no_release", "status_promoted")
    _require(document["successor"] == {"predecessor": "docs/baselines/upstream-integration-ledger.v4.yaml", "reason": "additive v5 runtime-attestation/source disposition; v1-v4 historical ledgers retained"}, "successor_drift")
    _require(document["policy"] == POLICY, "policy_drift")
    _require(document["allowed_values"] == ALLOWED, "allowed_values_drift")
    candidate = document["candidate"]
    _require(isinstance(candidate, dict), "candidate_not_mapping")
    _require(set(candidate) == {"commit", "tree", "archive_sha256", "archive_bytes", "materialization", "worktree_overlay"}, "candidate_keys")
    expected_candidate = {"commit": COMMIT, "tree": TREE, "archive_sha256": ARCHIVE, "archive_bytes": ARCHIVE_BYTES, "materialization": "clean_git_archive", "worktree_overlay": False}
    _require(candidate == expected_candidate, "candidate_drift")
    _require(HEX40.fullmatch(COMMIT) and HEX40.fullmatch(TREE) and HEX64.fullmatch(ARCHIVE), "candidate_shape")
    _require(subprocess.run(["git", "show", "-s", "--format=%T", COMMIT], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip() == TREE, "candidate_git_tree_drift")
    archive = subprocess.run(["git", "archive", "--format=tar", COMMIT], cwd=ROOT, capture_output=True, check=True).stdout
    _require(len(archive) == ARCHIVE_BYTES and hashlib.sha256(archive).hexdigest() == ARCHIVE, "candidate_archive_drift")
    authorities = document["source_authority"]
    _require(isinstance(authorities, dict), "source_authority_not_mapping")
    _require(set(authorities) == set(AUTHORITIES), "source_authority_set")
    for name, (commit, tree, license_name, blob, sha) in AUTHORITIES.items():
        _require(authorities[name] == {"commit": commit, "tree": tree, "license": license_name, "license_blob_sha1": blob, "license_sha256": sha}, f"source_authority_drift:{name}")
    provenance = document["provenance_documents"]
    _require(isinstance(provenance, list) and len(provenance) == len(PROVENANCE), "provenance_count")
    for item, (path, sha) in zip(provenance, PROVENANCE.items()):
        _require(isinstance(item, dict), "provenance_item_not_mapping")
        _require(item == {"path": path, "sha256": sha}, "provenance_exact")
        _binding(item, f"provenance:{path}")
    harness = document["harness"]
    _require(isinstance(harness, dict), "harness_not_mapping")
    _require(set(harness) == {"verifier", "mutation_tests"}, "harness_keys")
    _binding(harness["verifier"], "harness_verifier")
    _binding(harness["mutation_tests"], "harness_mutations")
    _require(harness["verifier"]["path"] == "tools/verify_upstream_integration_ledger_v5.py", "harness_verifier_path")
    _require(harness["mutation_tests"]["path"] == "tools/test_verify_upstream_integration_ledger_v5.py", "harness_mutation_path")
    _require(harness["verifier"]["sha256"] == EXPECTED_VERIFIER_ANCHOR_SHA256, "verifier_anchor")
    _require(harness["mutation_tests"]["sha256"] == EXPECTED_MUTATION_SHA256, "mutation_anchor")
    audit = document["audit"]
    _require(isinstance(audit, dict), "audit_not_mapping")
    _require(set(audit) == {"path", "sha256"}, "audit_keys")
    _require(audit["path"] == "docs/baselines/audits/2026-08-24-upstream-integration-ledger-v5.md", "audit_keys")
    _require(audit["sha256"] == EXPECTED_AUDIT_SHA256, "audit_anchor")
    _binding(audit, "audit")
    audit_text = (ROOT / audit["path"]).read_text(encoding="utf-8")
    for marker in (SCHEMA, COMMIT, TREE, ARCHIVE, "15 rows", "release-ready=0", "AS-05", "as-05-ngspice-scoped-observation-v2.manifest.json", "PB", "COM", "No promotion"):
        _require(marker in audit_text, f"audit_marker:{marker}")
    supplements = document["supplemental_evidence"]
    _require(isinstance(supplements, list) and len(supplements) == len(SUPPLEMENTALS), "supplemental_count")
    for item in supplements:
        _require(isinstance(item, dict), "supplemental_item_not_mapping")
        _require(set(item) == {"id", "path", "sha256", "scope", "non_claims", "parity_promotion", "release_promotion"}, "supplemental_keys")
        expected = SUPPLEMENTALS.get(item.get("id"))
        _require(expected is not None, "supplemental_id")
        _require(item["path"] == expected[0] and item["sha256"] == expected[1] and item["scope"] == expected[2], f"supplemental_drift:{item['id']}")
        if len(expected) == 4:
            _require(item["non_claims"] == list(expected[3]), f"supplemental_non_claims:{item['id']}")
        else:
            _require(item["non_claims"] == [], f"supplemental_non_claims:{item['id']}")
        _require(item["parity_promotion"] is False and item["release_promotion"] is False, "supplemental_promotion")
        _binding({"path": item["path"], "sha256": item["sha256"]}, f"supplemental:{item['id']}")
    rows = document["rows"]
    _require(isinstance(rows, list) and len(rows) == 15, "row_count")
    for row, (row_id, repo, entry) in zip(rows, EXPECTED_ROWS):
        _require(isinstance(row, dict), f"row_not_mapping:{row_id}")
        expected_row_keys = {"id", "repo", "public_entrypoint", "integration_disposition", "runtime_availability", "parity_evidence", "release_state", "evidence", "non_claims"}
        if row_id == "AS-05":
            expected_row_keys.add("current_observation")
        _require(set(row) == expected_row_keys, f"row_keys:{row_id}")
        _require((row["id"], row["repo"], row["public_entrypoint"]) == (row_id, repo, entry), f"row_identity:{row_id}")
        _require(tuple(row[key] for key in ("integration_disposition", "runtime_availability", "parity_evidence", "release_state")) == POLICIES[row_id], f"row_policy:{row_id}")
        expected_evidence = {"path": EVIDENCE[row_id][0], "sha256": EVIDENCE[row_id][1]}
        _require(isinstance(row["evidence"], dict), f"row_evidence:{row_id}_not_mapping")
        _require(row["evidence"].get("path") == expected_evidence["path"], f"row_evidence:{row_id}_path")
        _require(row["evidence"].get("sha256") == expected_evidence["sha256"], f"row_evidence:{row_id}_hash_drift")
        _require(set(row["evidence"]) == {"path", "sha256"}, f"row_evidence:{row_id}")
        _binding(row["evidence"], f"row_evidence:{row_id}")
        if row_id == "AS-05":
            _require("current_observation" in row, "row_current_observation:AS-05_missing")
            _binding(row["current_observation"], "row_current_observation:AS-05")
            _require(row["current_observation"] == {"path": SUPPLEMENTALS["as05-attested-ngspice"][0], "sha256": SUPPLEMENTALS["as05-attested-ngspice"][1]}, "row_current_observation:AS-05_drift")
        _require(row["non_claims"] == NONCLAIMS[row_id], f"row_non_claims:{row_id}")
    summary = document["summary"]
    _require(summary == {"rows": 15, "direct_rust_port": 13, "retained_external_runtime": 2, "external_asset": 0, "oracle_only": 0, "excluded_fail_closed": 0, "release_ready": 0}, "summary_drift")
    return {"valid": True, "rows": 15, "release_ready": 0}


if __name__ == "__main__":
    print(validate(_load()))
