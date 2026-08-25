"""Strict additive verifier for the v9 upstream integration ledger."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/baselines/upstream-integration-ledger.v9.yaml"
SCHEMA = "sipi.upstream-integration-ledger.v9"
COMMIT = "a8a97139686088b3340e5a8ff4dc47af0829b5ec"
TREE = "be7b2b25c8cbd705b3c0eb4778b5097762653296"
ARCHIVE = "95b7374b1c45538f8b0836c6ec4a576d330d9e43dcd1188e53c963d799df098d"
ARCHIVE_BYTES = 51722240
V8_PATH = "docs/baselines/upstream-integration-ledger.v8.yaml"
V8_SHA = "ce292d1eea19d38628b3e63360d9e269d080ab8533a63b9a46a092f9f8eed69d"
PLAN_PATH = "PLAN.md"
EXPECTED_PLAN_SHA = "ac52dcc1f6ea05393d73af8a6de80ff0399b47be75f5b419907547b7939f4462"
PLAN_MARKER = "2026-08-25 v9 upstream-first 治理快照"
PLAN_EXACT_SNIPPET = (
    "AS-03 current observation 绑定 commit `5a6608e0` 的 formal gate，约\n"
    "`1e-17` mismatch/open；PB-03 绑定 commit `c93746e9` 的 formal observation；COM workbook→ACCM\n"
    "绑定 commit `a8a97139` 的 formal evidence，状态为 `numeric_observation`、`matched=false`、\n"
    "`acceptance=false`。"
)
EXPECTED_AUDIT_SHA = "e26d5393f0e07b3dd4c60f0a054e55016c7f054b86537e64941b376147cbe863"
EXPECTED_VERIFIER_SHA = "ff7cc3722fd07fbf57c7531f440c91e129ffc1b3ec93daac414973be96f273cd"
EXPECTED_MUTATION_SHA = "fb77ef8dc6d68b4680ef1ec9da151e1581c42aa44359121f5b0324a1df183112"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ROWS = (
    ("AS-01", "agent_spice", "fit-sparam"), ("AS-02", "agent_spice", "fit-sparam-cascade"),
    ("AS-03", "agent_spice", "fit-yparam"), ("AS-04", "agent_spice", "tune-yparam-tran"),
    ("AS-05", "agent_spice", "run-hspice"), ("AS-06", "agent_spice", "run-rfm"),
    ("PB-01", "pybert", "sim"), ("PB-02", "pybert", "sim-native"),
    ("PB-03", "pybert", "sim-rust"), ("PB-04", "pybert", "sim-auto"),
    ("PB-05", "pybert", "sim-compare"), ("COM-01", "agent_com", "config-validate"),
    ("COM-02", "agent_com", "run"), ("COM-03", "agent_com", "compare"),
    ("COM-04", "agent_com", "load_config-run_com-write_artifacts"),
)
POLICY = {
    "AS-01": ("direct_rust_port", "portable", "scoped_numeric_mismatch_open", "open_no_release"),
    "AS-02": ("direct_rust_port", "portable", "scoped_numeric_mismatch_open", "open_no_release"),
    "AS-03": ("direct_rust_port", "portable", "scoped_numeric_mismatch_open", "open_no_release"),
    "AS-04": ("direct_rust_port", "external_solver_required", "external_blocker_observed", "open_no_release"),
    "AS-05": ("direct_rust_port", "external_solver_required", "external_solver_not_verified", "open_no_release"),
    "AS-06": ("direct_rust_port", "external_solver_required", "external_blocker_observed", "open_no_release"),
    "PB-01": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-02": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-03": ("direct_rust_port", "portable", "scoped_observation", "scoped_only_no_release"),
    "PB-04": ("retained_external_runtime", "external_asset_required", "external_vendor_numeric_parity_unverified", "open_no_release"),
    "PB-05": ("retained_external_runtime", "external_asset_required", "external_vendor_numeric_parity_unverified", "open_no_release"),
    "COM-01": ("direct_rust_port", "unavailable", "historical_only", "open_no_release"),
    "COM-02": ("direct_rust_port", "external_asset_required", "numeric_observation", "open_no_release"),
    "COM-03": ("direct_rust_port", "unavailable", "historical_only", "open_no_release"),
    "COM-04": ("direct_rust_port", "external_asset_required", "numeric_observation", "open_no_release"),
}
ALLOWED_VALUES = {
    "integration_disposition": ["direct_rust_port", "retained_external_runtime", "external_asset", "oracle_only", "excluded_fail_closed"],
    "runtime_availability": ["portable", "external_solver_required", "external_asset_required", "unavailable"],
    "parity_evidence": ["scoped_numeric_mismatch_open", "scoped_observation", "numeric_observation", "external_blocker_observed", "external_solver_not_verified", "external_vendor_numeric_parity_unverified", "upstream_only_timeout", "historical_only"],
    "release_state": ["open_no_release", "scoped_only_no_release", "excluded_no_release"],
}
AUTHORITY = {
    "agent_spice": {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "license": "MIT", "license_blob_sha1": "55aac2e4f8c36a978d315efb02815972579b8293", "license_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"},
    "pybert": {"commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe", "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24", "license": "BSD-3-Clause", "license_blob_sha1": "64d198ba43675ede5fbdef1ec918a63954951640", "license_sha256": "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c"},
    "agent_com": {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "license": "MIT", "license_blob_sha1": "55aac2e4f8c36a978d315efb02815972579b8293", "license_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"},
}
CURRENT = {
    "AS-03": {
        "manifest": ("docs/baselines/as-03-fit-yparam-numeric-bound-current-6b8dacb4.v1.yaml", "b68af5d1d59a11d057461a4a27054b6a77a1d21e4fa86e1d4cae31b865c3c0b7"),
        "report_01": ("docs/baselines/as-03-numeric-bound-current-6b8dacb4-run-01.json", "bca4296f296fe89740f2e526f1a301f688a55699af0a1f889e781e1ce3ae9df3"),
        "report_02": ("docs/baselines/as-03-numeric-bound-current-6b8dacb4-run-02.json", "f598d5f9ed284f0e8eac79b39eb7d71c7d61e44462e6087b5560d06bfc895b80"),
        "aggregate": ("docs/baselines/as-03-numeric-bound-current-6b8dacb4-aggregate.json", "49f78eff9f04bf522fb0b2a32119952e2529a6b4ef0a605e7945b852e03260a8"),
        "audit": ("docs/baselines/audits/2026-08-24-as-03-numeric-bound-current-6b8dacb4.md", "087c4149b8dcf3b8cf6c592d6332940c47b9b7f50a15452be5a7340c27fa24c7"),
        "verifier": ("tools/verify_as_03_numeric_bound_current_6b8dacb4.py", "526de14882453e7c0cc78a933e03415ce68a84527bf6c8c47a00255bb9f7fd50"),
        "mutation_tests": ("tools/test_verify_as_03_numeric_bound_current_6b8dacb4.py", "8f284eea40ebc208ec4db73beb467fbbc7a8edafae04445bb7784795967359df"),
    },
    "AS-04": ("docs/baselines/as-04-tune-yparam-tran-source-map.v1.yaml", "23fb2c2f124d71dd7f229ee814c4ebf686227a6a48ec579c575977051974ec62"),
    "AS-05": ("docs/baselines/as-05-ngspice-scoped-observation-v2.manifest.json", "47656c53fda3d39a29b3577945471dbfd21e68dc2f167ad43bfab72aeacb9a55"),
    "AS-06": ("docs/baselines/as-06-xspice-rfm-build-preflight-v2.manifest.json", "76deecf2344cade701f7ea2598d09c796016bfdd6bf1bf24f20857ec5425c3bd"),
    "PB-04": ("crates/sipi-pybert-direct/SOURCE-MAP-PB-AMI-MATERIALIZER.md", "29e846a7655ed1144a8771074d4bc313ecdc350b51a89a0d9e95a3434201007a"),
    "PB-05": ("crates/sipi-pybert-direct/SOURCE-MAP-PB-AMI-MATERIALIZER.md", "29e846a7655ed1144a8771074d4bc313ecdc350b51a89a0d9e95a3434201007a"),
    "PB-01": ("docs/baselines/pb-01-03-branch-inventory-ab1fc.v1.yaml", "169957926c1798e4c9d5b8628afca477c6b9a7d2779bab931e383d95bca6e2f3"),
    "PB-02": {
        "manifest": ("docs/baselines/pb-02-direct-43c12-current.v2.yaml", "ac5a36baa22649e01da769985b5a3fe1561b31b9005663ea32b0cad524077ad6"),
        "run_01": ("docs/baselines/pb-02-direct-43c12-current-run-01.json", "9906e4801dc462242ad064db3899cc98ea74f9eb81d24ad210859c3d8647034c"),
        "run_02": ("docs/baselines/pb-02-direct-43c12-current-run-02.json", "6956f44c3a25c211e32f3bd32e882d9cb5e01aec5713c215d130b8db8268fd4e"),
        "aggregate": ("docs/baselines/pb-02-direct-43c12-current-aggregate.json", "30253d5ec770ea69187d9211dcc5bb6700447c6eb052d7ac8b5155dc3b763c15"),
    },
    "PB-03": {
        "manifest": ("docs/baselines/pb-03-direct-ed7b12d2-current.v1.yaml", "9f672c2fa520e50ef4ac31095a2eb5d3b241022e24999bcd5f329668e50d7358"),
        "aggregate": ("docs/baselines/pb-03-direct-ed7b12d2-aggregate.json", "c5f54a591c9ab5037545468e4872e4906a2388686ae4d99497bd193edc1c1d64"),
        "audit": ("docs/baselines/audits/2026-08-24-pb-03-ed7b12d2-current.json", "16b0eeed749897bdfcf7b9bfce2e5fd8376435a86706e28e77e72add94f30c0c"),
        "report_01": ("docs/baselines/pb-03-direct-ed7b12d2-run-01.json", "5113f55c4c0644e46611db3edad423804cd106864e6616cb383ee69a222aed8f"),
        "report_02": ("docs/baselines/pb-03-direct-ed7b12d2-run-02.json", "b4bd16f3680828c45a1ec177111c1c62aa137926be09f3f732408017441775ca"),
        "verifier": ("tools/verify_pb_03_direct_ed7b12d2_current.py", "51835340224e1bd2e0239b858f03175d91b2896a33b9c557a4afbb17284aca33"),
        "mutation_tests": ("tools/test_verify_pb_03_direct_ed7b12d2_current.py", "534745510773b201126d07e1c290b58fc1480107b225a603fd98c8470cfa9471"),
    },
    "COM-02": {
        "manifest": ("docs/baselines/com-workbook-accm-replay-v4.manifest.yaml", "68e4fdc5c9d644d146b541eadd1753b5ff2a886576024a2f9f5f522e6aa95467"),
        "audit": ("docs/baselines/com-workbook-accm-replay-v4.audit.yaml", "47163ec41a37209de7c2168c6f9baf7628cd59160582858f750bd08c8887ad2c"),
        "report_01": ("docs/baselines/com-workbook-accm-replay-run1.json", "ce2c4545d8455718005d584874b655a544e36e086d8a33788561e3956f72e38f"),
        "report_02": ("docs/baselines/com-workbook-accm-replay-run2.json", "09514f59f49ec4d03d02f0e4634bc989aa1034225e86e427de99fe3cfbd58af6"),
        "aggregate": ("docs/baselines/com-workbook-accm-replay-aggregate.json", "805ebf00656a24057cff4ae389369f23eb78faf2b571deb25f1df8ba9c9143a4"),
        "verifier": ("tools/verify_com_workbook_accm_formal_evidence_v1.py", "e2cb58ff3883b78a801d8f3a2ec4b3a385e976db3c0651091d30142acbdff15b"),
        "mutation_tests": ("tools/test_verify_com_workbook_accm_formal_evidence_v1.py", "0b5a27c9e65a0234031937a6356619506fb22dabd4adfc2bd3e65a5d09a90cd7"),
    },
    "COM-04": {
        "manifest": ("docs/baselines/com-workbook-accm-replay-v4.manifest.yaml", "68e4fdc5c9d644d146b541eadd1753b5ff2a886576024a2f9f5f522e6aa95467"),
        "audit": ("docs/baselines/com-workbook-accm-replay-v4.audit.yaml", "47163ec41a37209de7c2168c6f9baf7628cd59160582858f750bd08c8887ad2c"),
        "report_01": ("docs/baselines/com-workbook-accm-replay-run1.json", "ce2c4545d8455718005d584874b655a544e36e086d8a33788561e3956f72e38f"),
        "report_02": ("docs/baselines/com-workbook-accm-replay-run2.json", "09514f59f49ec4d03d02f0e4634bc989aa1034225e86e427de99fe3cfbd58af6"),
        "aggregate": ("docs/baselines/com-workbook-accm-replay-aggregate.json", "805ebf00656a24057cff4ae389369f23eb78faf2b571deb25f1df8ba9c9143a4"),
        "verifier": ("tools/verify_com_workbook_accm_formal_evidence_v1.py", "e2cb58ff3883b78a801d8f3a2ec4b3a385e976db3c0651091d30142acbdff15b"),
        "mutation_tests": ("tools/test_verify_com_workbook_accm_formal_evidence_v1.py", "0b5a27c9e65a0234031937a6356619506fb22dabd4adfc2bd3e65a5d09a90cd7"),
    },
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
    "as03_source_map": ("docs/baselines/as-03-fit-yparam-source-map.v1.yaml", "8b8b2a822690dcda4e2d711aaa0425bcb03bbecca697ef0ac712ec444526e815"),
    "as03_notice": ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-03.md", "0d8cdee1b93f8e8ea51df76653233fea5c8a8e3d5f32b15d276c23c0686b908a"),
    "as04_source_map": CURRENT["AS-04"],
    "as06_preflight": CURRENT["AS-06"],
    "as04_notice": ("crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-04.md", "e0bcaad72b2fbcfebcca8a18560fee168c0215935f60bbfa8fdf36c41ef22875"),
    "pb_branch_inventory": CURRENT["PB-01"],
    "pb_ami_source_map": CURRENT["PB-04"],
    "pb_pyami_notice": ("crates/sipi-pybert-direct/NOTICE-PYAMI-LICENSE-BOUNDARY.md", "319865189948b21164849b6be38ba369d5d4c427dcb63baaa018597a15b8f505"),
    "com_source_map": ("crates/sipi-agent-com-direct/SOURCE-MAP-COM-02.md", "cebc323f76819c7f949b066f38b8ab64c7951d087f7d7925e041151c17336b06"),
    "pb02_manifest": CURRENT["PB-02"]["manifest"],
    "pb02_run_01": CURRENT["PB-02"]["run_01"],
    "pb02_run_02": CURRENT["PB-02"]["run_02"],
    "pb02_aggregate": CURRENT["PB-02"]["aggregate"],
}
MIN_NONCLAIMS = {
    "AS-01": {"no_global_parity", "no_release", "no_product_capability_promotion"},
    "AS-02": {"no_global_parity", "no_release", "no_product_capability_promotion"},
    "AS-03": {"v2_global_mismatch_open", "v3_fixed_fixture_scoped", "no_si_sparam_fit", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_release"},
    "AS-04": {"no_solver_result", "relative_paths_only", "hspice_external", "no_numeric_parity", "external_solver_not_verified", "no_global_parity", "no_product_capability_promotion", "no_release"},
    "AS-05": {"workflow_observed_only", "attested_external_ngspice_consumption_only", "external_solver_not_verified", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"},
    "AS-06": {"workflow_observed_only", "source_asset_missing", "docker_info_failed", "build_not_attempted", "workflow_not_run", "no_solver_result", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"},
    "PB-01": {"environment_local_scoped", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_release"},
    "PB-02": {"environment_local_scoped", "single_fixed_fixture_numeric_observation", "no_global_parity", "no_branch_completion", "no_bit_repro_build", "no_pure_python_legacy", "no_promotion", "no_release"},
    "PB-03": {"environment_local_scoped", "fixed_subset_payload_parity_only", "no_whole_payload_parity", "no_independent_implementation", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_release"},
    "PB-04": {"mock_dll_receipt_only", "bounded_example_rx_control_semantics_only", "no_vendor_dll_numeric_parity", "no_external_asset", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"},
    "PB-05": {"mock_dll_receipt_only", "bounded_example_rx_control_semantics_only", "no_vendor_dll_numeric_parity", "no_external_asset", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"},
    "COM-01": {"historical_only", "no_current_parity", "no_full_entrypoint_parity", "no_dc_accm", "no_sparam_fit", "impulse_only", "no_release"},
    "COM-02": {"internal_staged_dc_accm_leaf_only", "no_public_accm_e2e", "no_upstream_dc_accm_numeric_parity", "no_canonical_accm_fields", "no_candidate_parity", "no_full_entrypoint_parity", "scoped_synthetic_package_e2e_only", "no_upstream_package_numeric_parity", "no_clean_upstream_numeric_replay", "no_sparam_fit", "impulse_only", "no_release"},
    "COM-03": {"historical_only", "no_current_parity", "no_full_entrypoint_parity", "no_dc_accm", "no_sparam_fit", "impulse_only", "no_release"},
    "COM-04": {"internal_staged_dc_accm_leaf_only", "no_public_accm_e2e", "no_upstream_dc_accm_numeric_parity", "no_canonical_accm_fields", "no_candidate_parity", "no_full_entrypoint_parity", "scoped_synthetic_package_e2e_only", "no_upstream_package_numeric_parity", "no_clean_upstream_numeric_replay", "no_sparam_fit", "impulse_only", "no_release"},
}
EXPECTED_NONCLAIMS = {
    "AS-01": ["no_global_parity", "no_release", "no_product_capability_promotion"],
    "AS-02": ["no_global_parity", "no_release", "no_product_capability_promotion"],
    "AS-03": ["v2_global_mismatch_open", "v3_fixed_fixture_scoped", "no_si_sparam_fit", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_release"],
    "AS-04": ["no_solver_result", "relative_paths_only", "hspice_external", "no_numeric_parity", "external_solver_not_verified", "no_global_parity", "no_product_capability_promotion", "no_release"],
    "AS-05": ["workflow_observed_only", "attested_external_ngspice_consumption_only", "external_solver_not_verified", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"],
    "AS-06": ["workflow_observed_only", "source_asset_missing", "docker_info_failed", "build_not_attempted", "workflow_not_run", "no_solver_result", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"],
    "PB-01": ["environment_local_scoped", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_release"],
    "PB-02": ["environment_local_scoped", "single_fixed_fixture_numeric_observation", "no_global_parity", "no_branch_completion", "no_bit_repro_build", "no_pure_python_legacy", "no_promotion", "no_release"],
    "PB-03": ["environment_local_scoped", "fixed_subset_payload_parity_only", "no_whole_payload_parity", "no_independent_implementation", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_release"],
    "PB-04": ["mock_dll_receipt_only", "bounded_example_rx_control_semantics_only", "no_vendor_dll_numeric_parity", "no_external_asset", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"],
    "PB-05": ["mock_dll_receipt_only", "bounded_example_rx_control_semantics_only", "no_vendor_dll_numeric_parity", "no_external_asset", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "no_release"],
    "COM-01": ["historical_only", "no_current_parity", "no_full_entrypoint_parity", "no_dc_accm", "no_sparam_fit", "impulse_only", "no_release"],
    "COM-02": ["internal_staged_dc_accm_leaf_only", "no_public_accm_e2e", "no_upstream_dc_accm_numeric_parity", "no_canonical_accm_fields", "no_candidate_parity", "no_full_entrypoint_parity", "scoped_synthetic_package_e2e_only", "no_upstream_package_numeric_parity", "no_clean_upstream_numeric_replay", "no_sparam_fit", "impulse_only", "no_release"],
    "COM-03": ["historical_only", "no_current_parity", "no_full_entrypoint_parity", "no_dc_accm", "no_sparam_fit", "impulse_only", "no_release"],
    "COM-04": ["internal_staged_dc_accm_leaf_only", "no_public_accm_e2e", "no_upstream_dc_accm_numeric_parity", "no_canonical_accm_fields", "no_candidate_parity", "no_full_entrypoint_parity", "scoped_synthetic_package_e2e_only", "no_upstream_package_numeric_parity", "no_clean_upstream_numeric_replay", "no_sparam_fit", "impulse_only", "no_release"],
}
ALLOWED_NONCLAIMS = set().union(*MIN_NONCLAIMS.values())


class LedgerError(RuntimeError):
    pass


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise LedgerError(reason)


def _sha(path: Path) -> str:
    data = path.read_bytes()
    if path.resolve() == (ROOT / "tools/verify_upstream_integration_ledger_v9.py").resolve():
        data = re.sub(rb'EXPECTED_VERIFIER_SHA = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA = "<self>"', data, count=1)
        data = re.sub(rb'EXPECTED_MUTATION_SHA = "[0-9a-f]{64}"', b'EXPECTED_MUTATION_SHA = "<mutation>"', data, count=1)
    if path.resolve() == (ROOT / "tools/test_verify_upstream_integration_ledger_v9.py").resolve():
        data = re.sub(rb'EXPECTED_VERIFIER_SHA256 = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA256 = "<verifier>"', data, count=1)
    return hashlib.sha256(data).hexdigest()


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in tuple(env):
        if key.startswith("GIT_CONFIG_") or key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}:
            env.pop(key, None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _safe(path: object) -> bool:
    return (
        isinstance(path, str)
        and bool(path)
        and not path.startswith(("/", "\\"))
        and not path.startswith("//")
        and not re.match(r"^[A-Za-z]:", path)
        and "\\" not in path
        and ".." not in path.split("/")
    )


def _bind(item: Any, reason: str) -> None:
    _require(isinstance(item, dict) and set(item) == {"path", "sha256"}, reason + "_keys")
    _require(_safe(item["path"]) and HEX64.fullmatch(str(item["sha256"])), reason + "_shape")
    target = ROOT / item["path"]
    _require(target.is_file(), reason + "_missing")
    _require(_sha(target) == item["sha256"], reason + "_hash")


def _load(path: Path = LEDGER) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def _validate(document: dict[str, Any]) -> dict[str, Any]:
    expected_top = {"schema", "status", "successor", "candidate", "policy", "allowed_values", "source_authority", "current_sources", "rows", "summary", "plan", "audit", "harness"}
    _require(isinstance(document, dict) and set(document) == expected_top, "top_keys")
    _require(document["schema"] == SCHEMA and document["status"] == "current_clean_candidate_open_no_release", "identity")
    _require(document["successor"] == {"predecessor": V8_PATH, "predecessor_sha256": V8_SHA, "reason": "additive v9 current-candidate active-evidence rebinding; v1-v8 remain immutable historical ledgers"}, "successor")
    _require(_sha(ROOT / V8_PATH) == V8_SHA, "predecessor_hash")
    expected_candidate = {"commit": COMMIT, "tree": TREE, "archive_sha256": ARCHIVE, "archive_bytes": ARCHIVE_BYTES, "materialization": "clean_git_archive", "autocrlf": True, "worktree_overlay": False}
    candidate = document["candidate"]
    _require(isinstance(candidate, dict) and set(candidate) == set(expected_candidate), "candidate_shape")
    _require(type(candidate["archive_bytes"]) is int and type(candidate["autocrlf"]) is bool and type(candidate["worktree_overlay"]) is bool, "candidate_types")
    _require(candidate == expected_candidate, "candidate")
    git_env = _git_env()
    _require(subprocess.run(["git", "-c", "core.autocrlf=true", "show", "-s", "--format=%T", COMMIT], cwd=ROOT, env=git_env, capture_output=True, text=True, check=True).stdout.strip() == TREE, "candidate_tree")
    archive = subprocess.run(["git", "-c", "core.autocrlf=true", "archive", "--format=tar", COMMIT], cwd=ROOT, env=git_env, capture_output=True, check=True).stdout
    _require(len(archive) == ARCHIVE_BYTES and hashlib.sha256(archive).hexdigest() == ARCHIVE, "candidate_archive")
    expected_policy = {"new_domain_features_allowed": False, "direct_rust_port_requires_named_upstream_behavior": True, "external_runtime_is_not_parity": True, "scoped_observation_is_not_global_parity": True, "release_promotion_requires_branch_complete_evidence": True}
    _require(isinstance(document["policy"], dict) and set(document["policy"]) == set(expected_policy), "policy_shape")
    _require(all(type(value) is bool for value in document["policy"].values()), "policy_types")
    _require(document["policy"] == expected_policy, "policy")
    _require(document["allowed_values"] == ALLOWED_VALUES, "allowed_values")
    authorities = document["source_authority"]
    _require(isinstance(authorities, dict) and set(authorities) == {"agent_spice", "pybert", "agent_com"}, "source_authority")
    for authority in authorities.values():
        _require(isinstance(authority, dict) and set(authority) == {"commit", "tree", "license", "license_blob_sha1", "license_sha256"}, "source_authority_shape")
    _require(authorities == AUTHORITY, "source_authority_values")
    sources = document["current_sources"]
    _require(isinstance(sources, dict) and set(sources) == set(SOURCE_BINDINGS), "sources_keys")
    for name, expected in SOURCE_BINDINGS.items():
        _require(sources[name] == {"path": expected[0], "sha256": expected[1]}, "source:" + name)
        _bind(sources[name], "source:" + name)
    for row, identity in zip(document["rows"], ROWS):
        row_id, repo, entry = identity
        _require(isinstance(row, dict), "row_shape:" + row_id)
        keys = {"id", "repo", "public_entrypoint", "integration_disposition", "runtime_availability", "parity_evidence", "release_state", "evidence", "non_claims"} | ({"current_observation"} if row_id in CURRENT else set())
        _require(set(row) == keys and (row["id"], row["repo"], row["public_entrypoint"]) == identity, "row_identity:" + row_id)
        _require(tuple(row[k] for k in ("integration_disposition", "runtime_availability", "parity_evidence", "release_state")) == POLICY[row_id], "row_policy:" + row_id)
        _require(row["evidence"] == {"path": EVIDENCE[row_id][0], "sha256": EVIDENCE[row_id][1]}, "evidence_exact:" + row_id)
        _bind(row["evidence"], "evidence:" + row_id)
        _require(row["non_claims"] == EXPECTED_NONCLAIMS[row_id], "nonclaims:" + row_id)
        if row_id in CURRENT:
            if isinstance(CURRENT[row_id], dict):
                expected = {name: {"path": value[0], "sha256": value[1]} for name, value in CURRENT[row_id].items()}
                _require(row["current_observation"] == expected, "current_observation:" + row_id)
                for name, item in expected.items():
                    _bind(item, "current_observation:" + row_id + ":" + name)
            else:
                expected = {"path": CURRENT[row_id][0], "sha256": CURRENT[row_id][1]}
                _require(row["current_observation"] == expected, "current_observation:" + row_id)
                _bind(row["current_observation"], "current_observation:" + row_id)
    _require(len(document["rows"]) == 15, "row_count")
    expected_summary = {"rows": 15, "direct_rust_port": 13, "retained_external_runtime": 2, "external_asset": 0, "oracle_only": 0, "excluded_fail_closed": 0, "release_ready": 0}
    _require(isinstance(document["summary"], dict) and set(document["summary"]) == set(expected_summary), "summary_shape")
    _require(all(type(value) is int for value in document["summary"].values()), "summary_types")
    _require(document["summary"] == expected_summary, "summary")
    _require(document["plan"] == {"path": PLAN_PATH, "sha256": document["plan"]["sha256"]}, "plan_shape")
    _require(document["plan"]["sha256"] == EXPECTED_PLAN_SHA, "plan_anchor")
    _bind(document["plan"], "plan")
    plan_text = (ROOT / PLAN_PATH).read_text(encoding="utf-8")
    _require(PLAN_MARKER in plan_text and PLAN_EXACT_SNIPPET in plan_text, "plan_marker")
    _require(document["audit"] == {"path": "docs/baselines/audits/2026-08-25-upstream-integration-ledger-v9.md", "sha256": document["audit"]["sha256"]}, "audit_shape")
    _require(document["audit"]["sha256"] == EXPECTED_AUDIT_SHA, "audit_anchor")
    _bind(document["audit"], "audit")
    audit_text = (ROOT / document["audit"]["path"]).read_text(encoding="utf-8")
    for marker in (SCHEMA, COMMIT, TREE, ARCHIVE, "15 rows", "release-ready=0", "AS-04", "PB-01/PB-02/PB-03 remain scoped observations", "fixed-subset payload parity", "COM", "no_public_accm_e2e", "v8 immutable predecessor", "No promotion"):
        _require(marker in audit_text, "audit_marker:" + marker)
    harness = document["harness"]
    _require(isinstance(harness, dict) and set(harness) == {"verifier", "mutation_tests"}, "harness_shape")
    _bind(harness["verifier"], "harness_verifier")
    _bind(harness["mutation_tests"], "harness_mutations")
    _require(harness["verifier"]["path"] == "tools/verify_upstream_integration_ledger_v9.py" and harness["mutation_tests"]["path"] == "tools/test_verify_upstream_integration_ledger_v9.py", "harness_paths")
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
