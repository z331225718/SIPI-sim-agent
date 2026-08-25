"""Strict additive verifier for the v11 upstream integration ledger."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/baselines/upstream-integration-ledger.v11.yaml"
SCHEMA = "sipi.upstream-integration-ledger.v11"
COMMIT = "e7e9882e5a7c3b058ee3e1cc7830da5ac60dd82d"
TREE = "6bf982dfecb226f656feaad5a31dc93820cd7893"
ARCHIVE = "4dce7e63ae169f5d1659549ac10433c3befa1f36641ce124719b1abb2de31336"
ARCHIVE_BYTES = 52152320
V10_PATH = "docs/baselines/upstream-integration-ledger.v10.yaml"
V10_SHA = "2e2b8b2b209380147df189f854d68fd7ead6d57ccbc53bdde61cc5f1b7176c17"
PLAN_PATH = "PLAN.md"
EXPECTED_PLAN_SHA = "336be1671a4801d8dfad07a3650179dfd69641f8caf54c5920db697b2efb2d5c"
AUDIT_PATH = "docs/baselines/audits/2026-08-25-upstream-integration-ledger-v11.md"
MUTATION_TEST_PATH = "tools/test_verify_upstream_integration_ledger_v11.py"
EXPECTED_AUDIT_SHA = "258a5b9ddf6902278210cbe253a391833355e145e089f8ce69d61f934a96d825"
EXPECTED_VERIFIER_SHA = "c0df17f3382a9bca0713af4679638055f271f8aad537f7f5731b5a192e9823a3"
EXPECTED_MUTATION_SHA = "0b0ff894ce778626d1ea9fe05772bd6cd20426d2a36e9a3bb0177c71dbd86139"
PLAN_MARKER = "2026-08-25 v11 upstream-first successor"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

ROWS = (
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
    "AS-01": ("excluded_fail_closed", "unavailable", "historical_only", "excluded_no_release"),
    "AS-02": ("excluded_fail_closed", "unavailable", "historical_only", "excluded_no_release"),
    "AS-03": ("retained_external_runtime", "external_solver_required", "scoped_observation", "open_no_release"),
    "AS-04": ("direct_rust_port", "external_solver_required", "external_blocker_observed", "open_no_release"),
    "AS-05": ("direct_rust_port", "external_solver_required", "external_solver_not_verified", "open_no_release"),
    "AS-06": ("direct_rust_port", "external_solver_required", "scoped_observation", "open_no_release"),
    "PB-01": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-02": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-03": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-04": ("retained_external_runtime", "external_asset_required", "external_vendor_numeric_parity_unverified", "open_no_release"),
    "PB-05": ("retained_external_runtime", "external_asset_required", "external_vendor_numeric_parity_unverified", "open_no_release"),
    "COM-01": ("direct_rust_port", "unavailable", "historical_only", "open_no_release"),
    "COM-02": ("direct_rust_port", "external_asset_required", "scoped_observation", "open_no_release"),
    "COM-03": ("direct_rust_port", "unavailable", "historical_only", "open_no_release"),
    "COM-04": ("direct_rust_port", "external_asset_required", "numeric_observation", "open_no_release"),
}

EXPECTED_NONCLAIMS = {
    "AS-01": ["owner_excluded_no_s_parameter_fit", "historical_only", "no_global_parity", "no_product_capability_promotion", "no_release"],
    "AS-02": ["owner_excluded_no_s_parameter_fit", "historical_only", "no_global_parity", "no_product_capability_promotion", "no_release"],
    "AS-03": ["owner_retained_y_parameter_reference_only", "no_si_s_parameter_fit", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_release"],
    "AS-04": ["no_solver_result", "relative_paths_only", "hspice_external", "no_numeric_parity", "external_solver_not_verified", "no_global_parity", "no_product_capability_promotion", "no_release"],
    "AS-05": ["portable_staging_only", "external_solver_retained", "trusted_non_concurrent_roots", "external_solver_not_verified", "no_solver_result", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"],
    "AS-06": ["attested_external_ngspice_rfm_execution_only", "external_solver_correctness_not_verified", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"],
    "PB-01": ["environment_local_scoped", "class_pickle_bounded_compatibility_only", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_release"],
    "PB-02": ["native_three_scenario_diagnostic_only", "upstream_flat_envelope_missing", "no_temp_report_formal_evidence", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_promotion", "no_release"],
    "PB-03": ["environment_local_scoped", "fixed_subset_payload_parity_only", "no_whole_payload_parity", "no_independent_implementation", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_release"],
    "PB-04": ["external_asset_branch_retained", "mock_dll_receipt_only", "bounded_example_rx_control_semantics_only", "no_vendor_dll_numeric_parity", "no_external_asset", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"],
    "PB-05": ["external_asset_branch_retained", "mock_dll_receipt_only", "bounded_example_rx_control_semantics_only", "no_vendor_dll_numeric_parity", "no_external_asset", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"],
    "COM-01": ["historical_only", "no_current_parity", "no_full_entrypoint_parity", "no_dc_accm", "no_sparam_fit", "impulse_only", "no_release"],
    "COM-02": ["unbound_manual_two_case_observation", "no_v4_formal_support", "no_public_accm_e2e", "no_upstream_dc_accm_numeric_parity", "no_canonical_accm_fields", "no_candidate_parity", "no_full_entrypoint_parity", "no_clean_upstream_numeric_replay", "no_sparam_fit", "impulse_only", "no_global_parity", "no_product_capability_promotion", "no_release"],
    "COM-03": ["historical_only", "no_current_parity", "no_full_entrypoint_parity", "no_dc_accm", "no_sparam_fit", "impulse_only", "no_release"],
    "COM-04": ["internal_staged_dc_accm_leaf_only", "no_public_accm_e2e", "no_upstream_dc_accm_numeric_parity", "no_canonical_accm_fields", "no_candidate_parity", "no_full_entrypoint_parity", "scoped_synthetic_package_e2e_only", "no_upstream_package_numeric_parity", "no_clean_upstream_numeric_replay", "no_sparam_fit", "impulse_only", "no_release"],
}

EXPECTED_OBSERVATION_SHA256_BY_ROW = {
    "AS-03": "efc6dcc5ec7f32b78bb79f231aaad7dca1e883e82e9c47b3653607b89c092c80",
    "AS-04": "8791b768cdd47ee33b671063891b61efdc52cd7897f82c74f381f0374cd3ed2e",
    "AS-05": "925615969220329de0125caf3c6d91f5660af314b377e420c0a0915182576ae0",
    "AS-06": "aa8344c91efeb7706da7b326fa26972ff858c0220d86910da8eae2f2848d83c0",
    "PB-01": "21bb0932ac5018225875724a2104ed542d06da67a06ef44252b0e0730fb36f0e",
    "PB-02": "18630cf41636d7dbbe3904c982121aba89c79ae77e1f6596c867cd84c0ebd5a3",
    "PB-03": "cde577529076464991f35e68933706be87459172385b8fdf75cfb919ff6a897f",
    "PB-04": "75ae34668901a9690c0195aaf27cd8ebd7098965cd90989f210b526895a1ec5c",
    "PB-05": "75ae34668901a9690c0195aaf27cd8ebd7098965cd90989f210b526895a1ec5c",
    "COM-02": "fd912d7db08362d9e901f9d8f380138b1d7107170df1b5194c430d245b402136",
    "COM-04": "082c09423cbbe0a86ed9d4e566212b7c88a781e8a8728c1eb30e76dbaf78e588",
}

EVIDENCE = {
    "AS-01": ("docs/baselines/as-01-fit-sparam-bound-clean-archive-v3.yaml", "7b1e82ea428f0fe6f5a9fd39157ad3251c416e97929f82de7129c7098dcb01b8"),
    "AS-02": ("docs/baselines/as-02-fit-sparam-cascade-numeric-bound-v3.yaml", "65b2ef5908a3920a18a209c56e5f73be50db5ac6ae2aeeb37a43b775cde843ee"),
    "AS-03": ("docs/baselines/as-03-fit-yparam-numeric-bound-current-6b8dacb4.v1.yaml", "b68af5d1d59a11d057461a4a27054b6a77a1d21e4fa86e1d4cae31b865c3c0b7"),
    "AS-04": ("docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml", "3e42e662be21b1814f0b37fb915a66441d0af2bcc0ab7ddd1ca77d1fac4883c8"),
    "AS-05": ("docs/baselines/as-05-run-hspice-rust-control-direct-port.v2.yaml", "6ba0b596ba96b1cf41fb556027f25c60852917b90cf78c6ccce77c10f3856015"),
    "AS-06": ("docs/baselines/as-06-run-rfm-direct-port.v2.yaml", "b1b52a43dc8de03b98461b9af20629edfed5167df88fbc80135703df89deda90"),
    "PB-01": ("docs/baselines/pb-01-legacy-leaf-current-d3154093.v1.yaml", "40f1721b20f1affcaa381270b760e4e9fa4896f8a8674b1c8a408d78de6f9312"),
    "PB-02": ("docs/baselines/pb-02-direct-current-d3154093.v1.yaml", "00ae4121f3136c9ba993b1a5a666635f260b9952acb213517796e638f40aa0d4"),
    "PB-03": ("docs/baselines/pb-03-direct-ed7b12d2-current.v1.yaml", "9f672c2fa520e50ef4ac31095a2eb5d3b241022e24999bcd5f329668e50d7358"),
    "PB-04": ("docs/baselines/pb-04-direct-port.current-bound.v1.yaml", "b13a8d42946d5685344f8e03c78dff3d8c40c51e1f57f52a093b69571742f8b1"),
    "PB-05": ("docs/baselines/pb-05-direct-port.current-bound.v1.yaml", "3876ae5a1e827d80ccfc08fdbb72a3b3bb743130d2efcccc2533de7c8439a39d"),
    "COM-01": ("docs/baselines/com-01-direct-replay-bound.v2.yaml", "a5581ddfd6284a5345845c276915933f8529f6300cddc14c09fa2a534589db32"),
    "COM-02": ("docs/baselines/com-workbook-accm-replay-v4.manifest.yaml", "68e4fdc5c9d644d146b541eadd1753b5ff2a886576024a2f9f5f522e6aa95467"),
    "COM-03": ("docs/baselines/com-03-direct-port-bound.v2.yaml", "13792b8be122d247cf3cb41a3361caec9fad1cb15c8f3633624d1d98da17a4ac"),
    "COM-04": ("docs/baselines/com-workbook-accm-replay-v4.manifest.yaml", "68e4fdc5c9d644d146b541eadd1753b5ff2a886576024a2f9f5f522e6aa95467"),
}

SOURCE_BINDINGS = {
    "as01_notice": ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-01.txt", "d43d8a5e91aa303434466ede2fcf4237860eae53148732f6cb87dc8de0b88dbc"),
    "as03_source_map": ("docs/baselines/as-03-fit-yparam-source-map.v1.yaml", "8b8b2a822690dcda4e2d711aaa0425bcb03bbecca697ef0ac712ec444526e815"),
    "as03_notice": ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-03.md", "0d8cdee1b93f8e8ea51df76653233fea5c8a8e3d5f32b15d276c23c0686b908a"),
    "as04_source_map": ("docs/baselines/as-04-tune-yparam-tran-source-map.v2.yaml", "c588f5c7dec7c843ceded6ac7dee43b8a9386c1e91838df7e3fa976f93d9cc73"),
    "as04_notice": ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-04-v2.md", "dca095b53d9436abf940a102cf5bf17d7d67cf95da9a58c53b267993df2042d9"),
    "as05_source_map": ("docs/baselines/as-05-run-hspice-staging-source-map.v1.yaml", "965fbd1ad692389a77ea91d0b6b9a052653d1c73c19d7b9c727429c3966d71e6"),
    "as05_staging_notice": ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-05-STAGING.txt", "07f0db2dd38162b4cc77c64944853930664509b27982f4d1f58a934930d62920"),
    "as05_external_observation": ("docs/baselines/as-05-ngspice-scoped-observation-v2.manifest.json", "47656c53fda3d39a29b3577945471dbfd21e68dc2f167ad43bfab72aeacb9a55"),
    "as06_source_map": ("docs/baselines/as-06-run-rfm-source-map.v3.yaml", "866950c2a9e7ebd366044a392fbe35a79a948927ed62192723a2ff87e9c70d6e"),
    "as06_notice": ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-06-v3.md", "ae1e01212153b4060637087eac4bc6fae3ffb3af385ffdcf15500d3d2d105053"),
    "pb_stage2_source_map": ("crates/sipi-pybert-direct/SOURCE-MAP-PB-STAGE2.md", "acc3ac30126dbd98aa4c474eda27bd27e05a39c42490b40c0fff0414810e9bba"),
    "pb_stage2_runner_source_map": ("crates/sipi-pybert-direct/SOURCE-MAP-PB-STAGE2-RUNNER.md", "a30e23e85f5dd0e6d3986ff812cdfa70e4286384968264a5c19af9a53ded837e"),
    "pb01_class_pickle_source_map": ("crates/sipi-pybert-direct/SOURCE-MAP-PB01-CLASS-PICKLE.md", "a0b8a1bf39bce5d9e78e2646bafe9c8d0f94ad7efd9f74e305113e15450647c9"),
    "pb01_class_pickle_notice": ("crates/sipi-pybert-direct/NOTICE-PYBERT-PB01-CLASS-PICKLE.md", "ea8949dc9267b18ef01a255120bd73d214a7f559dff883c57abb068d7d0d733b"),
    "pb_ami_source_map": ("crates/sipi-pybert-direct/SOURCE-MAP-PB-AMI-MATERIALIZER.md", "29e846a7655ed1144a8771074d4bc313ecdc350b51a89a0d9e95a3434201007a"),
    "pb_external_host_source_map": ("crates/sipi-pybert-direct/SOURCE-MAP-PB-EXTERNAL-HOST.md", "3f5cd91d1f4c44d9103744667f6eada513740dc40bcdc77192fa614d5dcdf894"),
    "pb_pybert_notice": ("crates/sipi-pybert-direct/NOTICE-PYBERT-LICENSE-BOUNDARY.md", "77c20eb0cc8411b7826666e6673b7c388ce508fd80029e0d302a116fa5d237e6"),
    "pb_pyami_notice": ("crates/sipi-pybert-direct/NOTICE-PYAMI-LICENSE-BOUNDARY.md", "319865189948b21164849b6be38ba369d5d4c427dcb63baaa018597a15b8f505"),
    "com_source_map": ("crates/sipi-agent-com-direct/SOURCE-MAP-COM-02.md", "59ccf47dd554b29f5e958742a238f5cad798d7161ff9ad2dc96914abf3785bf2"),
    "com_notice": ("crates/sipi-agent-com-direct/NOTICE-AGENT-COM-MIT.md", "04344354a492e4afa55a71fe6fd39047f8ee52f78370ea0ea4fb243d9104817f"),
    "com_td_source_map": ("crates/sipi-com/SOURCE-MAP-COM-TD-INPUT.md", "767046cd9bf475d184864efe70d8330c7fb2b6299fbd56049e626344ca51c082"),
    "com_td_notice": ("crates/sipi-com/NOTICE-AGENT-COM-TD-INPUT-MIT.md", "7b97c72c3e2f88adf0f27cf94a615a1f47c087f5768d7134165e90905c485c7f"),
    "com01_source_map": ("crates/sipi-agent-com-direct/SOURCE-MAP-COM-01.md", "2709d584c0c25f6ec95c50437bae1eddb372804fe85a54409bfe73d92c92715c"),
}

CHANGE_COMMITS = {
    "as05_staging": "01323d9c6c416fe1ae51cfbae8bdd28135c5b558",
    "pb_stage2_output": "6f52e53f99f66e12c4371392e6c82114d4ac6028",
    "pb_stage2_duo_semantics": "d55cce1be2b55143235e416ac20e4360564371ce",
    "as06_rfm": "859553899a9daaadd82362e64ee30686b692b95d",
    "com_workbook_order": "f50dc6b01e5ca4b135e2c9af7c2d36d8647aa3b8",
    "com_opaque_winner_metrics": "f628d7f0660667fe6a79b7a39ea5a3e3b4500a4e",
    "com_do_white_noise_boundary": "e4094ccb4d2fcac74a69ac669ef257713962dd1e",
    "as04_best_trial_custody": "ef648cd2afb1b866f0897d486cefebbce7baa314",
    "pb01_class_pickle_compatibility": "e7e9882e5a7c3b058ee3e1cc7830da5ac60dd82d",
}

AUTHORITY = {
    "agent_spice": {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "license": "MIT", "license_blob_sha1": "55aac2e4f8c36a978d315efb02815972579b8293", "license_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"},
    "pybert": {"commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe", "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24", "license": "BSD-3-Clause", "license_blob_sha1": "64d198ba43675ede5fbdef1ec918a63954951640", "license_sha256": "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c"},
    "agent_com": {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "license": "MIT", "license_blob_sha1": "55aac2e4f8c36a978d315efb02815972579b8293", "license_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"},
}


class LedgerError(RuntimeError):
    pass


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise LedgerError(reason)


def _sha(path: Path) -> str:
    data = path.read_bytes()
    if path.resolve() == (ROOT / "tools/verify_upstream_integration_ledger_v11.py").resolve():
        data = re.sub(rb'EXPECTED_VERIFIER_SHA = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA = "<self>"', data, count=1)
        data = re.sub(rb'EXPECTED_MUTATION_SHA = "[0-9a-f]{64}"', b'EXPECTED_MUTATION_SHA = "<mutation>"', data, count=1)
    if path.resolve() == (ROOT / "tools/test_verify_upstream_integration_ledger_v11.py").resolve():
        data = re.sub(rb'EXPECTED_VERIFIER_SHA256 = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA256 = "<verifier>"', data, count=1)
    return hashlib.sha256(data).hexdigest()


def _observation_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _declared_test_verifier_sha() -> str:
    text = (ROOT / MUTATION_TEST_PATH).read_text(encoding="utf-8")
    match = re.search(r'^EXPECTED_VERIFIER_SHA256 = "([0-9a-f]{64})"$', text, re.MULTILINE)
    _require(match is not None, "mutation_verifier_anchor_shape")
    return match.group(1)


def _safe(path: object) -> bool:
    return isinstance(path, str) and bool(path) and not path.startswith(("/", "\\")) and not path.startswith("//") and not re.match(r"^[A-Za-z]:", path) and "\\" not in path and ".." not in path.split("/") and "Temp" not in path and "temp" not in path


def _bind(item: Any, reason: str) -> None:
    _require(isinstance(item, dict) and set(item) == {"path", "sha256"}, reason + "_keys")
    _require(_safe(item.get("path")) and HEX64.fullmatch(str(item.get("sha256"))), reason + "_shape")
    target = ROOT / item["path"]
    _require(target.is_file(), reason + "_missing")
    _require(_sha(target) == item["sha256"], reason + "_hash")


def _bind_tree(value: Any, reason: str) -> None:
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            _bind(value, reason)
            return
        for key, child in value.items():
            _bind_tree(child, reason + ":" + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _bind_tree(child, reason + ":" + str(index))


def _contains_temp_value(value: Any) -> bool:
    """Reject temporary report locations without mistaking the boolean gate name for one."""
    if isinstance(value, dict):
        return any(_contains_temp_value(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_temp_value(child) for child in value)
    return isinstance(value, str) and "temp" in value.lower()


def _load(path: Path = LEDGER) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in tuple(env):
        if key.startswith("GIT_CONFIG_") or key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}:
            env.pop(key, None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _validate(document: dict[str, Any]) -> dict[str, Any]:
    expected_top = {"schema", "status", "successor", "candidate", "policy", "allowed_values", "source_authority", "change_commits", "current_sources", "rows", "summary", "plan", "audit", "harness"}
    _require(set(document) == expected_top, "top_keys")
    _require(document["schema"] == SCHEMA and document["status"] == "current_clean_candidate_open_no_release", "identity")
    _require(document["successor"] == {"predecessor": V10_PATH, "predecessor_sha256": V10_SHA, "reason": "additive v11 successor; v1-v10 remain immutable historical ledgers"}, "successor")
    _require(_sha(ROOT / V10_PATH) == V10_SHA, "predecessor_hash")
    expected_candidate = {"commit": COMMIT, "tree": TREE, "archive_sha256": ARCHIVE, "archive_bytes": ARCHIVE_BYTES, "materialization": "clean_git_archive", "autocrlf": True, "worktree_overlay": False}
    candidate = document["candidate"]
    _require(isinstance(candidate, dict) and candidate == expected_candidate, "candidate")
    _require(type(candidate["archive_bytes"]) is int and type(candidate["autocrlf"]) is bool and type(candidate["worktree_overlay"]) is bool, "candidate_types")
    git_env = _git_env()
    _require(subprocess.run(["git", "-c", "core.autocrlf=true", "show", "-s", "--format=%T", COMMIT], cwd=ROOT, env=git_env, capture_output=True, text=True, check=True).stdout.strip() == TREE, "candidate_tree")
    archive = subprocess.run(["git", "-c", "core.autocrlf=true", "archive", "--format=tar", COMMIT], cwd=ROOT, env=git_env, capture_output=True, check=True).stdout
    _require(len(archive) == ARCHIVE_BYTES and hashlib.sha256(archive).hexdigest() == ARCHIVE, "candidate_archive")
    expected_policy = {"new_domain_features_allowed": False, "direct_rust_port_requires_named_upstream_behavior": True, "external_runtime_is_not_parity": True, "scoped_observation_is_not_global_parity": True, "release_promotion_requires_branch_complete_evidence": True}
    _require(document["policy"] == expected_policy and all(type(v) is bool for v in document["policy"].values()), "policy")
    expected_allowed = {"integration_disposition": ["direct_rust_port", "retained_external_runtime", "external_asset", "oracle_only", "excluded_fail_closed"], "runtime_availability": ["portable", "external_solver_required", "external_asset_required", "unavailable"], "parity_evidence": ["scoped_numeric_mismatch_open", "scoped_observation", "numeric_observation", "external_blocker_observed", "external_solver_not_verified", "external_vendor_numeric_parity_unverified", "upstream_only_timeout", "historical_only"], "release_state": ["open_no_release", "scoped_only_no_release", "excluded_no_release"]}
    _require(document["allowed_values"] == expected_allowed, "allowed_values")
    _require(document["source_authority"] == AUTHORITY, "source_authority")
    _require(document["change_commits"] == CHANGE_COMMITS and all(HEX40.fullmatch(v) for v in CHANGE_COMMITS.values()), "change_commits")
    sources = document["current_sources"]
    _require(isinstance(sources, dict) and set(sources) == set(SOURCE_BINDINGS), "sources_keys")
    for name, expected in SOURCE_BINDINGS.items():
        _require(sources[name] == {"path": expected[0], "sha256": expected[1]}, "source:" + name)
        _bind(sources[name], "source:" + name)
    for row, identity in zip(document["rows"], ROWS):
        row_id, repo, entry = identity
        _require(isinstance(row, dict), "row_shape:" + row_id)
        _require((row.get("id"), row.get("repo"), row.get("public_entrypoint")) == identity, "row_identity:" + row_id)
        expected_keys = {"id", "repo", "public_entrypoint", "integration_disposition", "runtime_availability", "parity_evidence", "release_state", "evidence", "non_claims"}
        if row_id in {"AS-03", "AS-04", "AS-05", "AS-06", "PB-01", "PB-02", "PB-03", "PB-04", "PB-05", "COM-02", "COM-04"}:
            expected_keys.add("current_observation")
        _require(set(row) == expected_keys, "row_keys:" + row_id)
        _require(tuple(row[key] for key in ("integration_disposition", "runtime_availability", "parity_evidence", "release_state")) == POLICY[row_id], "row_policy:" + row_id)
        _require(row["evidence"] == {"path": EVIDENCE[row_id][0], "sha256": EVIDENCE[row_id][1]}, "evidence_exact:" + row_id)
        _bind(row["evidence"], "evidence:" + row_id)
        _require(row["non_claims"] == EXPECTED_NONCLAIMS[row_id], "nonclaims:" + row_id)
        if "current_observation" in row:
            _bind_tree(row["current_observation"], "current_observation:" + row_id)
            _require(not _contains_temp_value(row["current_observation"]), "current_observation_temp:" + row_id)
    _require(len(document["rows"]) == 15, "row_count")
    current_observation_ids = {row["id"] for row in document["rows"] if "current_observation" in row}
    _require(current_observation_ids == set(EXPECTED_OBSERVATION_SHA256_BY_ROW), "current_observation_rows")
    for row in document["rows"]:
        if "current_observation" in row:
            row_id = row["id"]
            _require(_observation_sha(row["current_observation"]) == EXPECTED_OBSERVATION_SHA256_BY_ROW[row_id], "current_observation_exact:" + row_id)
    by_id = {row["id"]: row for row in document["rows"]}
    _require(by_id["AS-05"]["current_observation"]["staging_source_map"] == {"path": SOURCE_BINDINGS["as05_source_map"][0], "sha256": SOURCE_BINDINGS["as05_source_map"][1]}, "AS-05:staging_source_map")
    _require(by_id["AS-05"]["current_observation"]["staging_notice"] == {"path": SOURCE_BINDINGS["as05_staging_notice"][0], "sha256": SOURCE_BINDINGS["as05_staging_notice"][1]}, "AS-05:staging_notice")
    _require(by_id["AS-05"]["current_observation"]["external_observation"] == {"path": SOURCE_BINDINGS["as05_external_observation"][0], "sha256": SOURCE_BINDINGS["as05_external_observation"][1]}, "AS-05:observation")
    as04_observation = by_id["AS-04"]["current_observation"]
    _require(as04_observation == {"source_map": {"path": SOURCE_BINDINGS["as04_source_map"][0], "sha256": SOURCE_BINDINGS["as04_source_map"][1]}, "notice": {"path": SOURCE_BINDINGS["as04_notice"][0], "sha256": SOURCE_BINDINGS["as04_notice"][1]}, "best_trial_frozen_artifact_custody": True, "external_solver": "hspice", "e2e": False, "numeric_parity": False}, "AS-04:scope")
    _require(by_id["AS-06"]["current_observation"] == {"source_map": {"path": SOURCE_BINDINGS["as06_source_map"][0], "sha256": SOURCE_BINDINGS["as06_source_map"][1]}, "notice": {"path": SOURCE_BINDINGS["as06_notice"][0], "sha256": SOURCE_BINDINGS["as06_notice"][1]}, "external_execution": "attested_ngspice_rfm_workflow", "native_caller_custody": True, "cli_output_protocol": True, "e2e": False, "numeric_parity": False}, "AS-06:scope_exact")
    _require(by_id["PB-01"]["current_observation"] == {"branch_inventory": {"path": "docs/baselines/pb-01-03-branch-inventory-ab1fc.v1.yaml", "sha256": "169957926c1798e4c9d5b8628afca477c6b9a7d2779bab931e383d95bca6e2f3"}, "source_map": {"path": "crates/sipi-pybert-direct/SOURCE-MAP-PB01.md", "sha256": "251ed57342908225f8fc71ef2c3e3a22ad04c50d8a6ee8488d7df70a5dcaa8a5"}, "class_pickle_source_map": {"path": SOURCE_BINDINGS["pb01_class_pickle_source_map"][0], "sha256": SOURCE_BINDINGS["pb01_class_pickle_source_map"][1]}, "class_pickle_notice": {"path": SOURCE_BINDINGS["pb01_class_pickle_notice"][0], "sha256": SOURCE_BINDINGS["pb01_class_pickle_notice"][1]}, "class_pickle_observation": "bounded_compatibility_observation", "upstream_python_load": True, "default_dict_unchanged": True}, "PB-01:class_pickle_scope")
    pb02_diagnostic = by_id["PB-02"]["current_observation"]["diagnostic"]
    _require(pb02_diagnostic == {"status": "scoped_mismatch", "scenarios": 3, "arrays": "exact", "metrics": "exact", "upstream_envelope": "flat_without_nested_output", "formal_evidence": False, "temp_report_bound": False, "global_parity": False}, "PB-02:diagnostic")
    com02_observation = by_id["COM-02"]["current_observation"]
    _require(com02_observation["commit"] == "f628d7f0660667fe6a79b7a39ea5a3e3b4500a4e" and com02_observation["trusted_workbook_port_order"] == "unbound_manual_two_case_observation" and com02_observation["opaque_winner_final_metrics"] == "unbound_manual_two_case_observation" and com02_observation["do_white_noise"] == "source_unimplemented_wiener_hopf_only_diagnostic" and com02_observation["formal_evidence"] is False and com02_observation["v4_formal_support"] is False and com02_observation["channel_policy"] == "impulse_only" and com02_observation["s_parameter_fit"] == "forbidden" and com02_observation["global_parity"] is False and com02_observation["release"] is False, "COM-02:scope")
    expected_summary = {"rows": 15, "direct_rust_port": 10, "retained_external_runtime": 3, "external_asset": 0, "oracle_only": 0, "excluded_fail_closed": 2, "release_ready": 0}
    _require(document["summary"] == expected_summary and all(type(v) is int for v in document["summary"].values()), "summary")
    _require(document["plan"] == {"path": PLAN_PATH, "sha256": document["plan"].get("sha256")} and document["plan"]["sha256"] == EXPECTED_PLAN_SHA, "plan")
    _bind(document["plan"], "plan")
    plan_text = (ROOT / PLAN_PATH).read_text(encoding="utf-8")
    _require(PLAN_MARKER in plan_text and "upstream-integration-ledger.v11" in plan_text and "15/15" in plan_text and "release-ready=0" in plan_text, "plan_marker")
    _require(document["audit"] == {"path": AUDIT_PATH, "sha256": document["audit"].get("sha256")} and document["audit"]["sha256"] == EXPECTED_AUDIT_SHA, "audit")
    _bind(document["audit"], "audit")
    audit_text = (ROOT / AUDIT_PATH).read_text(encoding="utf-8")
    for marker in (SCHEMA, COMMIT, TREE, ARCHIVE, "15 rows", "release-ready=0", "AS-01", "AS-04", "AS-05", "AS-06", "PB-01", "class-pickle", "PB-02", "flat", "Temp", "COM-01", "COM-02", "Do_White_Noise", "source-unimplemented", "Wiener-Hopf-only", "not formal evidence", "impulse-only", "No v10 file"):
        _require(marker in audit_text, "audit_marker:" + marker)
    harness = document["harness"]
    _require(isinstance(harness, dict) and set(harness) == {"verifier", "mutation_tests"}, "harness_shape")
    _require(harness["verifier"]["path"] == "tools/verify_upstream_integration_ledger_v11.py" and harness["mutation_tests"]["path"] == "tools/test_verify_upstream_integration_ledger_v11.py", "harness_paths")
    _bind(harness["verifier"], "harness_verifier")
    _bind(harness["mutation_tests"], "harness_mutations")
    _require(_declared_test_verifier_sha() == EXPECTED_VERIFIER_SHA, "mutation_verifier_anchor")
    _require(harness["verifier"]["sha256"] == EXPECTED_VERIFIER_SHA, "harness_verifier_anchor")
    _require(harness["mutation_tests"]["sha256"] == EXPECTED_MUTATION_SHA, "harness_mutation_anchor")
    return {"valid": True, "rows": 15, "release_ready": 0}


def validate(document: dict[str, Any]) -> dict[str, Any]:
    try:
        return _validate(document)
    except LedgerError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise LedgerError("malformed:" + type(exc).__name__) from None


if __name__ == "__main__":
    print(validate(_load()))
