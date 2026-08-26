"""Strict additive verifier for the v12 upstream integration ledger."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/baselines/upstream-integration-ledger.v12.yaml"
SCHEMA = "sipi.upstream-integration-ledger.v12"
STATUS = "current_clean_candidate_open_no_release"
COMMIT = "a6db3dafb1c52309bdc701db31bae47e4d340cbb"
TREE = "2bfb65fdd44d350786180835c6eb5f9fc4fb757d"
ARCHIVE = "3f385f2f323b3b78095b1ec884697eb1dc086b4df3b5bba9b390026acbfc8890"
ARCHIVE_BYTES = 52992000
PREDECESSOR_PATH = "docs/baselines/upstream-integration-ledger.v11.yaml"
PREDECESSOR_SHA = "2a8fc445a0627f0bec1218a8fdabfdf2fac7a6f92b895f53cd863736c334cb4d"
PLAN_PATH = "PLAN.md"
PLAN_MARKER = "2026-08-27 v12 upstream-first successor"
EXPECTED_PLAN_SHA = "70ce505e5fc0b53cd76710018da6e9a3b9c3bd8ec28e32abe3384160119e4178"
AUDIT_PATH = "docs/baselines/audits/2026-08-27-upstream-integration-ledger-v12.md"
EXPECTED_AUDIT_SHA = "66959725a0affb3a41d3a83e2fbeee84b9c2c9cd055ca4fe639bc5883d2e4ae2"
MUTATION_TEST_PATH = "tools/test_verify_upstream_integration_ledger_v12.py"
EXPECTED_VERIFIER_SHA = "664994d931836056796b64dcaafd5bdf8bd45f35786361cc6c890b0da7408123"
EXPECTED_MUTATION_SHA = "7aa2ad9e1cc0ce7a3077b43d0fd6e289f96470a3ba4584de05b6f6570a31950d"
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
    "COM-02": ("direct_rust_port", "external_asset_required", "scoped_numeric_mismatch_open", "open_no_release"),
    "COM-03": ("direct_rust_port", "unavailable", "historical_only", "open_no_release"),
    "COM-04": ("direct_rust_port", "external_asset_required", "scoped_numeric_mismatch_open", "open_no_release"),
}

EVIDENCE = {
    "AS-01": ("docs/baselines/as-01-fit-sparam-bound-clean-archive-v3.yaml", "7b1e82ea428f0fe6f5a9fd39157ad3251c416e97929f82de7129c7098dcb01b8"),
    "AS-02": ("docs/baselines/as-02-fit-sparam-cascade-numeric-bound-v3.yaml", "65b2ef5908a3920a18a209c56e5f73be50db5ac6ae2aeeb37a43b775cde843ee"),
    "AS-03": ("docs/baselines/as-03-fit-yparam-numeric-bound-current-6b8dacb4.v1.yaml", "b68af5d1d59a11d057461a4a27054b6a77a1d21e4fa86e1d4cae31b865c3c0b7"),
    "AS-04": ("docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml", "3e42e662be21b1814f0b37fb915a66441d0af2bcc0ab7ddd1ca77d1fac4883c8"),
    "AS-05": ("docs/baselines/as-05-run-hspice-rust-control-direct-port.v2.yaml", "6ba0b596ba96b1cf41fb556027f25c60852917b90cf78c6ccce77c10f3856015"),
    "AS-06": ("docs/baselines/as-06-run-rfm-direct-port.v2.yaml", "b1b52a43dc8de03b98461b9af20629edfed5167df88fbc80135703df89deda90"),
    "PB-01": ("docs/baselines/pb-01-03-current-scoped-replay-bc882d2e.v1.yaml", "32763b2bc0f4f14dc3c291ca91fa9cb0b260ad9606cc48d556e69f3811b7966e"),
    "PB-02": ("docs/baselines/pb-01-03-current-scoped-replay-bc882d2e.v1.yaml", "32763b2bc0f4f14dc3c291ca91fa9cb0b260ad9606cc48d556e69f3811b7966e"),
    "PB-03": ("docs/baselines/pb-01-03-current-scoped-replay-bc882d2e.v1.yaml", "32763b2bc0f4f14dc3c291ca91fa9cb0b260ad9606cc48d556e69f3811b7966e"),
    "PB-04": ("docs/baselines/pb-04-direct-port.current-bound.v1.yaml", "b13a8d42946d5685344f8e03c78dff3d8c40c51e1f57f52a093b69571742f8b1"),
    "PB-05": ("docs/baselines/pb-05-direct-port.current-bound.v1.yaml", "3876ae5a1e827d80ccfc08fdbb72a3b3bb743130d2efcccc2533de7c8439a39d"),
    "COM-01": ("docs/baselines/com-01-direct-replay-bound.v2.yaml", "a5581ddfd6284a5345845c276915933f8529f6300cddc14c09fa2a534589db32"),
    "COM-02": ("docs/baselines/com-workbook-accm-replay-v5.manifest.yaml", "6ac1bd5cec34e960c992876fe35471b7019178b1af9db88cdaffe8f612cc7bd9"),
    "COM-03": ("docs/baselines/com-03-direct-port-bound.v2.yaml", "13792b8be122d247cf3cb41a3361caec9fad1cb15c8f3633624d1d98da17a4ac"),
    "COM-04": ("docs/baselines/com-workbook-accm-replay-v5.manifest.yaml", "6ac1bd5cec34e960c992876fe35471b7019178b1af9db88cdaffe8f612cc7bd9"),
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

AUTHORITY = {
    "agent_spice": {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "license": "MIT", "license_blob_sha1": "55aac2e4f8c36a978d315efb02815972579b8293", "license_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"},
    "pybert": {"commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe", "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24", "license": "BSD-3-Clause", "license_blob_sha1": "64d198ba43675ede5fbdef1ec918a63954951640", "license_sha256": "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c"},
    "agent_com": {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "license": "MIT", "license_blob_sha1": "55aac2e4f8c36a978d315efb02815972579b8293", "license_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"},
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
    "pb_current_scoped_replays": "c43852176ad21cc13e6376734e0b1e0be12d0025",
    "com_formal_replay_v5": "a6db3dafb1c52309bdc701db31bae47e4d340cbb",
}

AS05_OBSERVATION = {
    "staging_source_map": {"path": SOURCE_BINDINGS["as05_source_map"][0], "sha256": SOURCE_BINDINGS["as05_source_map"][1]},
    "staging_notice": {"path": SOURCE_BINDINGS["as05_staging_notice"][0], "sha256": SOURCE_BINDINGS["as05_staging_notice"][1]},
    "external_observation": {"path": SOURCE_BINDINGS["as05_external_observation"][0], "sha256": SOURCE_BINDINGS["as05_external_observation"][1]},
    "existing_run_hspice_staging": "retained",
    "existing_implementation": "retained_without_rollback",
    "owner_decision": "owner_excluded_not_required",
    "xyce_xdm_extension": "no_xyce_xdm_extension",
}

PB_MANIFEST = {"path": "docs/baselines/pb-01-03-current-scoped-replay-bc882d2e.v1.yaml", "sha256": "32763b2bc0f4f14dc3c291ca91fa9cb0b260ad9606cc48d556e69f3811b7966e"}
PB_AUDIT = {"path": "docs/baselines/audits/2026-08-26-pb-01-03-current-scoped-replay-bc882d2e.md", "sha256": "ae0a25f90f5dd310af8fb62f8624d7979a7ea2b33636b18dccbe8af068283cce"}

PB_OBSERVATIONS = {
    "PB-01": {"formal_manifest": PB_MANIFEST, "audit": PB_AUDIT, "selected_array_count": 12, "default_dictionary_schema": "sipi.pybert_data.v1", "default_dictionary_item_count": 23, "comparison_status": "passed_scoped", "release_ready": False},
    "PB-02": {"formal_manifest": PB_MANIFEST, "audit": PB_AUDIT, "exact_npz_member_count": 11, "comparison_status": "passed_scoped", "release_ready": False},
    "PB-03": {"formal_manifest": PB_MANIFEST, "audit": PB_AUDIT, "stable_subset_member_count": 44, "candidate_total_member_count": 113, "oracle_total_member_count": 150, "whole_payload_parity": False, "comparison_status": "passed_scoped_subset_only", "release_ready": False},
}

COM_MANIFEST = {"path": "docs/baselines/com-workbook-accm-replay-v5.manifest.yaml", "sha256": "6ac1bd5cec34e960c992876fe35471b7019178b1af9db88cdaffe8f612cc7bd9"}
COM_AUDIT = {"path": "docs/baselines/audits/2026-08-27-com-workbook-accm-replay-v5.md", "sha256": "1937951fc001f82511ea6f7b42ca3c2880b068e0a34ac3776bdde3e8596df4ab"}
COM_GATE = {
    "status": "scoped_mismatch_observed",
    "blockers": ["candidate_dfe_taps_not_published"],
    "port_order": "not_observed",
    "dfe_publication": "candidate_not_published",
    "fresh_replay_count": 2,
    "numeric_parity": False,
    "global_parity": False,
    "release_ready": False,
    "no_s_parameter_fit": True,
    "channel_policy": "one_final_fd_to_td_impulse",
}
COM_REPORTS = [
    {"path": "docs/baselines/com-workbook-accm-replay-v5-run1.json", "sha256": "fc14c562020883d0706bfaa16c3d970cb9834bcbf971f9e57b260021a8ca1a64"},
    {"path": "docs/baselines/com-workbook-accm-replay-v5-run2.json", "sha256": "ef732c7b063a72e422aa5f68325df1d029da056b2eb092502e7a7c7eb26fda01"},
]
COM_AGGREGATE = {"path": "docs/baselines/com-workbook-accm-replay-v5-aggregate.json", "sha256": "6ec879783ef1ef2310b72c4bbc19e590b84c727055e374af0f59913a8fdb2242"}
COM_OBSERVATION = {"formal_manifest": COM_MANIFEST, "formal_audit": COM_AUDIT, "formal_gate": COM_GATE, "reports": COM_REPORTS, "aggregate": COM_AGGREGATE, "status": "scoped_mismatch_observed", "release_ready": False, "no_s_parameter_fit": True, "channel_policy": "one_final_fd_to_td_impulse", "non_release_claim": True}

UPDATED_NONCLAIMS = {
    "AS-05": ["portable_staging_only", "external_solver_retained", "trusted_non_concurrent_roots", "external_solver_not_verified", "no_solver_result", "no_numeric_parity", "no_global_parity", "no_product_capability_promotion", "no_migration_row_close", "owner_excluded_not_required", "no_xyce_xdm_extension", "no_xyce_xdm_claim", "no_release"],
    "PB-01": ["scoped_only", "default_dictionary_only", "class_pickle_bounded_compatibility_only", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_release"],
    "PB-02": ["scoped_only", "logical_npz_members_only", "no_zip_wrapper_parity", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_release"],
    "PB-03": ["scoped_only", "stable_subset_only", "no_whole_payload_parity", "no_independent_implementation", "no_global_parity", "no_branch_completion", "no_product_capability_promotion", "no_release"],
    "COM-02": ["candidate_dfe_taps_not_published", "port_order_not_observed", "dfe_not_published", "no_numeric_parity", "no_global_parity", "no_release", "no_s_parameter_fit", "impulse_only", "one_final_fd_to_td_impulse", "no_row_close"],
    "COM-04": ["candidate_dfe_taps_not_published", "port_order_not_observed", "dfe_not_published", "no_numeric_parity", "no_global_parity", "no_release", "no_s_parameter_fit", "impulse_only", "one_final_fd_to_td_impulse", "no_row_close"],
}


class LedgerError(RuntimeError):
    pass


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise LedgerError(reason)


def _exact_equal(actual: Any, expected: Any, reason: str) -> None:
    """Compare fixed evidence structures without Python bool/int coercion."""
    _require(type(actual) is type(expected), reason + "_type")
    if isinstance(expected, dict):
        _require(set(actual) == set(expected), reason + "_keys")
        for key in expected:
            _exact_equal(actual[key], expected[key], reason + ":" + str(key))
    elif isinstance(expected, list):
        _require(len(actual) == len(expected), reason + "_length")
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            _exact_equal(actual_item, expected_item, reason + ":" + str(index))
    else:
        _require(actual == expected, reason + "_value")


def _sha(path: Path, root: Path = ROOT) -> str:
    data = path.read_bytes()
    verifier = (root / "tools/verify_upstream_integration_ledger_v12.py").resolve()
    mutations = (root / MUTATION_TEST_PATH).resolve()
    if path.resolve() == verifier:
        data = re.sub(rb'EXPECTED_VERIFIER_SHA = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA = "<self>"', data, count=1)
        data = re.sub(rb'EXPECTED_MUTATION_SHA = "[0-9a-f]{64}"', b'EXPECTED_MUTATION_SHA = "<mutation>"', data, count=1)
    if path.resolve() == mutations:
        data = re.sub(rb'EXPECTED_VERIFIER_SHA256 = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA256 = "<verifier>"', data, count=1)
    return hashlib.sha256(data).hexdigest()


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


def _safe(path: object, root: Path = ROOT) -> bool:
    if not isinstance(path, str) or not path:
        return False
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path) or "\\" in path:
        return False
    if ".." in path.split("/") or "temp" in path.lower():
        return False
    try:
        resolved_root = root.resolve(strict=True)
        target = (root / path).resolve(strict=True)
        target.relative_to(resolved_root)
        lexical = root / path
        current = root
        for component in lexical.relative_to(root).parts:
            current = current / component
            info = current.lstat()
            if current.is_symlink() or _is_reparse(info):
                return False
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode):
            return False
        nlink = getattr(info, "st_nlink", None)
        return nlink == 1
    except (OSError, RuntimeError, ValueError):
        return False


def _is_reparse(info: os.stat_result) -> bool:
    """Detect Windows reparse points while remaining false on POSIX files."""
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & flag)


def _bind(item: Any, reason: str, root: Path = ROOT) -> None:
    _require(type(item) is dict and set(item) == {"path", "sha256"}, reason + "_keys")
    _require(type(item.get("path")) is str and type(item.get("sha256")) is str and HEX64.fullmatch(item["sha256"]) is not None, reason + "_shape")
    _require(_safe(item["path"], root), reason + "_unsafe_path")
    target = root / item["path"]
    _require(target.is_file(), reason + "_missing")
    _require(_sha(target, root) == item["sha256"], reason + "_hash")


def _bind_tree(value: Any, reason: str, root: Path = ROOT) -> None:
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            _bind(value, reason, root)
            return
        for key, child in value.items():
            _bind_tree(child, reason + ":" + str(key), root)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _bind_tree(child, reason + ":" + str(index), root)


def _contains_temp(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_temp(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_temp(child) for child in value)
    return isinstance(value, str) and "temp" in value.lower()


def _declared_test_verifier_sha(root: Path = ROOT) -> str:
    text = (root / MUTATION_TEST_PATH).read_text(encoding="utf-8")
    match = re.search(r'^EXPECTED_VERIFIER_SHA256 = "([0-9a-f]{64})"$', text, re.MULTILINE)
    _require(match is not None, "mutation_verifier_anchor_shape")
    return match.group(1)


def _validate(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    expected_top = {"schema", "status", "successor", "candidate", "policy", "allowed_values", "source_authority", "change_commits", "current_sources", "rows", "summary", "plan", "audit", "harness"}
    _require(set(document) == expected_top, "top_keys")
    _exact_equal(document.get("schema"), SCHEMA, "schema")
    _exact_equal(document.get("status"), STATUS, "status")
    expected_successor = {"predecessor": PREDECESSOR_PATH, "predecessor_sha256": PREDECESSOR_SHA, "reason": "additive v12 successor; v1-v11 remain immutable historical ledgers"}
    _exact_equal(document.get("successor"), expected_successor, "successor")
    _bind({"path": PREDECESSOR_PATH, "sha256": PREDECESSOR_SHA}, "predecessor", root)
    expected_candidate = {"commit": COMMIT, "tree": TREE, "archive_sha256": ARCHIVE, "archive_bytes": ARCHIVE_BYTES, "materialization": "clean_git_archive", "autocrlf": True, "worktree_overlay": False}
    _exact_equal(document.get("candidate"), expected_candidate, "candidate")
    env = _git_env()
    tree = subprocess.run(["git", "-c", "core.autocrlf=true", "show", "-s", "--format=%T", COMMIT], cwd=root, env=env, capture_output=True, text=True, check=True).stdout.strip()
    _require(tree == TREE, "candidate_tree")
    archive = subprocess.run(["git", "-c", "core.autocrlf=true", "archive", "--format=tar", COMMIT], cwd=root, env=env, capture_output=True, check=True).stdout
    _require(len(archive) == ARCHIVE_BYTES and hashlib.sha256(archive).hexdigest() == ARCHIVE, "candidate_archive")
    expected_policy = {"new_domain_features_allowed": False, "direct_rust_port_requires_named_upstream_behavior": True, "external_runtime_is_not_parity": True, "scoped_observation_is_not_global_parity": True, "release_promotion_requires_branch_complete_evidence": True, "s_parameter_fit": "forbidden", "channel_policy": "one_final_fd_to_td_impulse"}
    _exact_equal(document.get("policy"), expected_policy, "policy")
    expected_allowed = {"integration_disposition": ["direct_rust_port", "retained_external_runtime", "external_asset", "oracle_only", "excluded_fail_closed"], "runtime_availability": ["portable", "external_solver_required", "external_asset_required", "unavailable"], "parity_evidence": ["scoped_numeric_mismatch_open", "scoped_observation", "numeric_observation", "external_blocker_observed", "external_solver_not_verified", "external_vendor_numeric_parity_unverified", "upstream_only_timeout", "historical_only"], "release_state": ["open_no_release", "scoped_only_no_release", "excluded_no_release"]}
    _exact_equal(document.get("allowed_values"), expected_allowed, "allowed_values")
    _exact_equal(document.get("source_authority"), AUTHORITY, "source_authority")
    _exact_equal(document.get("change_commits"), CHANGE_COMMITS, "change_commits")
    _require(all(type(v) is str and HEX40.fullmatch(v) for v in CHANGE_COMMITS.values()), "change_commit_shape")
    sources = document["current_sources"]
    _require(isinstance(sources, dict) and set(sources) == set(SOURCE_BINDINGS), "sources_keys")
    for name, (path, sha) in SOURCE_BINDINGS.items():
        _exact_equal(sources.get(name), {"path": path, "sha256": sha}, "source_exact:" + name)
        _bind(sources[name], "source:" + name, root)

    predecessor = _load(root / PREDECESSOR_PATH)
    previous_rows = {row["id"]: row for row in predecessor["rows"]}
    _require(len(document["rows"]) == 15 and len(previous_rows) == 15, "row_count")
    for row, identity in zip(document["rows"], ROWS):
        row_id, repo, entry = identity
        _require(isinstance(row, dict), "row_shape:" + row_id)
        _exact_equal(row.get("id"), row_id, "row_identity:" + row_id + ":id")
        _exact_equal(row.get("repo"), repo, "row_identity:" + row_id + ":repo")
        _exact_equal(row.get("public_entrypoint"), entry, "row_identity:" + row_id + ":entry")
        _exact_equal([row.get(key) for key in ("integration_disposition", "runtime_availability", "parity_evidence", "release_state")], list(POLICY[row_id]), "row_policy:" + row_id)
        _exact_equal(row.get("evidence"), {"path": EVIDENCE[row_id][0], "sha256": EVIDENCE[row_id][1]}, "evidence_exact:" + row_id)
        _bind(row["evidence"], "evidence:" + row_id, root)
        if row_id not in UPDATED_NONCLAIMS:
            _exact_equal(row, previous_rows[row_id], "row_preserved:" + row_id)
            continue
        _exact_equal(row.get("non_claims"), UPDATED_NONCLAIMS[row_id], "nonclaims:" + row_id)
        expected_observation: Any
        if row_id == "AS-05":
            expected_observation = AS05_OBSERVATION
        elif row_id in PB_OBSERVATIONS:
            expected_observation = PB_OBSERVATIONS[row_id]
        else:
            expected_observation = COM_OBSERVATION
        _exact_equal(row.get("current_observation"), expected_observation, "observation_exact:" + row_id)
        _bind_tree(row["current_observation"], "observation:" + row_id, root)
        _require(not _contains_temp(row["current_observation"]), "observation_temp:" + row_id)

    expected_summary = {"rows": 15, "direct_rust_port": 10, "retained_external_runtime": 3, "external_asset": 0, "oracle_only": 0, "excluded_fail_closed": 2, "release_ready": 0}
    _exact_equal(document.get("summary"), expected_summary, "summary")
    _exact_equal(document.get("plan"), {"path": PLAN_PATH, "sha256": EXPECTED_PLAN_SHA}, "plan_shape")
    _bind(document["plan"], "plan", root)
    plan_text = (root / PLAN_PATH).read_text(encoding="utf-8")
    for marker in (PLAN_MARKER, "upstream-integration-ledger.v12", "15/15", "release-ready=0", "AS-05", "owner_excluded_not_required", "no_xyce_xdm_extension", "PB-01", "12 selected", "23-key", "PB-02", "11 logical NPZ", "PB-03", "44 stable", "113", "150", "whole_payload_parity=false", "COM-02", "scoped_mismatch_observed", "candidate_dfe_taps_not_published", "not_observed", "candidate_not_published", "one-final FD-to-TD impulse", "not row close"):
        _require(marker in plan_text, "plan_marker:" + marker)
    _exact_equal(document.get("audit"), {"path": AUDIT_PATH, "sha256": EXPECTED_AUDIT_SHA}, "audit_shape")
    _bind(document["audit"], "audit", root)
    audit_text = (root / AUDIT_PATH).read_text(encoding="utf-8")
    for marker in (PLAN_MARKER, SCHEMA, COMMIT, TREE, ARCHIVE, "15 rows", "release-ready=0", "owner_excluded_not_required", "no_xyce_xdm_extension", "PB-01", "12 selected arrays", "23-key", "PB-02", "11 logical NPZ", "PB-03", "44-member", "113 candidate", "150 upstream", "whole_payload_parity=false", "COM-02", "COM-04", "scoped_mismatch_observed", "candidate_dfe_taps_not_published", "Port order is `not_observed`", "candidate_not_published", "two replays", "not numeric", "global parity", "one final", "No row is closed"):
        _require(marker in audit_text, "audit_marker:" + marker)
    expected_harness = {"verifier": {"path": "tools/verify_upstream_integration_ledger_v12.py", "sha256": EXPECTED_VERIFIER_SHA}, "mutation_tests": {"path": MUTATION_TEST_PATH, "sha256": EXPECTED_MUTATION_SHA}}
    _exact_equal(document.get("harness"), expected_harness, "harness_shape")
    _bind(document["harness"]["verifier"], "harness_verifier", root)
    _bind(document["harness"]["mutation_tests"], "harness_mutations", root)
    _require(_declared_test_verifier_sha(root) == EXPECTED_VERIFIER_SHA, "mutation_verifier_anchor")
    _require(EXPECTED_VERIFIER_SHA == _sha(root / "tools/verify_upstream_integration_ledger_v12.py", root), "verifier_self_anchor")
    _require(EXPECTED_MUTATION_SHA == _sha(root / MUTATION_TEST_PATH, root), "mutation_self_anchor")
    return {"valid": True, "rows": 15, "release_ready": 0}


def validate(document: dict[str, Any], repo_root: Path = ROOT) -> dict[str, Any]:
    try:
        return _validate(document, repo_root)
    except LedgerError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        raise LedgerError("malformed:" + type(exc).__name__) from None


if __name__ == "__main__":
    print(validate(_load()))
