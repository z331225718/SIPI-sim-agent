"""Verify the additive P5-06k required COM compare contract-gap record."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06k-required-com-compare-contract-gap.v1.yaml"
AUDIT_PATH = "docs/baselines/audits/2026-08-21-p5-06k-required-com-compare-contract-gap.md"
AUDIT_SHA256 = "28c6e4f4d6502cebfe46603afc83be674e2b4c4af466c655c5a2be98226359a4"
COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
TREE = "7094ab6e84989b218730c52432c70da10261f8ea"

EXPECTED_METRICS = [
    {"id": "com_db", "unit": "dB", "comparison_level": "scalar", "source_aliases": ["COM_dB"], "status": "alias_observed_value_observed_tolerance_missing"},
    {"id": "erl_db", "unit": "dB", "comparison_level": "scalar", "source_aliases": ["ERL"], "status": "alias_observed_value_observed_tolerance_missing"},
    {"id": "td_iln_db", "unit": "dB", "comparison_level": "scalar", "source_aliases": ["TD_ILN"], "status": "legacy_alias_only_value_and_tolerance_missing"},
]
OBSERVED_METRICS = [
    "COM_dB",
    "CTLE_DC_gain_dB",
    "ERL",
    "ERL11",
    "ERL22",
    "FOM",
    "ICN_mV",
    "IL_dB_channel_only_at_Fnq",
    "Peak_ISI_XTK_and_Noise_interference_at_BER_mV",
    "VEC_dB",
    "VEO_mV",
    "fitted_IL_dB_at_Fnq",
    "g_DC_HP",
    "itick",
]
CHECKPOINT_KEYS = [
    "DFE_taps",
    "TXLE_taps",
    "itick",
    "sgm_Ani__isi_xt_noise",
    "sigma_N",
    "tail_RSS",
]
REQUIRED_INPUT_KEYS = [
    "normalized_input_digest",
    "channel_role_manifest_digest",
    "parameter_set_digest",
]
REQUIRED_STAGES = [
    "selected_channel_evidence",
    "equalizer_selection_evidence",
    "pdf_axes_and_density",
]
REFERENCE_HASHES = {
    "docs/baselines/com-r480-acceptance.v1.yaml": "e90fca0d14968a04e09df90cd8bd4fcc7f749abfa07ad2b4b29dc297351ef03b",
    "docs/baselines/p5-06-oracle-metric-surface.v1.yaml": "677ed155b9851352f3fe128212eb4b60a22be9ed03fd7afd763a3de0736a3036",
    "docs/baselines/p5-06-matlab-oracle-first-run-evidence.v1.yaml": "4e2f6bb1d55376f3b317acaa75008a4603f910c184c619c130ee786a90453d24",
    "docs/baselines/p5-06i-external-result-custody.v1.yaml": "1226111d891cad2f353b290a2cedfec1d6e6c75eae0318be82e4c991f2c1801f",
    "docs/baselines/p5-r480-reference-custody-preflight.v1.yaml": "9819bd5b01120808f0b38191a2b9dbbf2925c9b6e19e59a9e13caa1ed1f4730b",
    "docs/baselines/p5-06-pinned-source-external-matlab-oracle-candidate-run.v1.yaml": "294984a6ef9f8ad756435dd133afc953866537326f623858c90890f7de3e43d4",
}
OBJECT_FACTS = [
    {
        "id": "capability_selection_schema",
        "path": "schemas/r480-capability-envelope-v1.yaml",
        "git_blob": "69aeffa675341733277ccaf19a8e878cb716a315",
        "content_sha256": "9b3329e25559e595187ae1a0530785d5a8dbbdc02a035eeb44326aa91ee34b73",
        "byte_length": 9636,
        "proves": ["profile_rule_ids_and_fingerprints", "input_kind_and_channel_role_sets"],
        "does_not_prove": ["compare_metric_bundle", "checkpoint_alignment_policy", "metric_or_checkpoint_tolerances"],
    },
    {
        "id": "stable_case_metric_and_checkpoint_extractor",
        "path": "tools/matlab_oracle/com_oracle_case_metrics.m",
        "git_blob": "9d13c8c9468a31ff9c06e2985bb6d03efc6428b6",
        "content_sha256": "93fb174b26256b485a86e56ed765858eec7f5f28371df56e182c3a5e8d77a794",
        "byte_length": 3401,
        "proves": ["observed_output_metric_key_surface", "observed_internal_checkpoint_field_surface", "case_index_is_retained_in_extracted_records"],
        "does_not_prove": ["required_td_iln_compare_value", "cross_implementation_alignment", "acceptance_tolerance"],
    },
    {
        "id": "legacy_output_schema",
        "path": "schemas/legacy-output-r480.json",
        "git_blob": "7980dcffb5a88557b8cb2e8107fae06355c91169",
        "content_sha256": "aa74317a43a7152c7ed3937a04093e6c84d5583652ca4d9af2ac0fed98ad9ea6",
        "byte_length": 2121,
        "proves": ["legacy_td_iln_field_name_TD_ILN", "legacy_td_iln_fom_field_name_FOM_TDILN", "legacy_com_and_erl_field_names"],
        "does_not_prove": ["td_iln_db_value_in_current_observed_matrix", "td_iln_comparison_tolerance", "metric_alias_policy"],
    },
    {
        "id": "matlab_repeatability_runner",
        "path": "tools/run_matlab_oracle.py",
        "git_blob": "36d4fa55f6eaf9ecdd72ba2cebfbc1b01908e8bc",
        "content_sha256": "db63ed42375ac990cb53d9926f603e050b652b0706c079f2e4456a5d97d87d42",
        "byte_length": 30851,
        "proves": ["repeated_run_case_count_and_case_order_checks", "repeated_run_scalar_metric_absolute_tolerance_1e-12", "network_observation_checks"],
        "does_not_prove": ["product_to_oracle_acceptance_tolerance", "full_compare_matrix_alignment"],
    },
    {
        "id": "network_checkpoint_tests",
        "path": "tests/test_network_matlab_checkpoint.py",
        "git_blob": "00f85011a7df88fe25fe9228e30f1605068dd583",
        "content_sha256": "ff7757b1303eb32dcd5fc893cff7d2d9969f5610eee7c6648b8fcc8179b02906",
        "byte_length": 2473,
        "proves": ["raw_and_mixed_network_checkpoint_comparison_shape", "network_rtol_1e-12_atol_1e-14_test_values"],
        "does_not_prove": ["final_com_erl_td_iln_tolerance", "product_oracle_acceptance"],
    },
    {
        "id": "isolated_mlse_checkpoint_test",
        "path": "tests/test_mlse.py",
        "git_blob": "6628e3bbcf563fe57ea08e7af41553aa8b6c92aa",
        "content_sha256": "b9ca3a6edc6a498a73b22a61a7dd35f5a995d5c8c8cb14c7854584d294d98a71",
        "byte_length": 4568,
        "proves": ["vertical_mlse_checkpoint_field_comparison_shape", "isolated_mlse_abs_2e-12_test_value"],
        "does_not_prove": ["full_com_compare_checkpoint_tolerance", "final_metric_tolerance"],
    },
]


def _fail(message: str) -> None:
    raise AssertionError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expect(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _git(source_root: Path, *arguments: str, text: bool = False) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(source_root), *arguments],
            check=False,
            capture_output=True,
        )
    except OSError as error:
        _fail(f"git unavailable: {error}")
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        _fail(f"git object lookup failed: {detail or completed.returncode}")
    return completed.stdout.decode("utf-8").strip() if text else completed.stdout


def _verify_source_git_objects(document: dict[str, Any], source_root: Path) -> None:
    """Check the recorded Agent-COM objects without reading the worktree."""
    source = document["canonical_agent_com"]
    commit = source["commit"]
    tree = source["tree"]
    actual_commit = str(_git(source_root, "rev-parse", f"{commit}^{{commit}}", text=True))
    _expect(actual_commit == commit, "canonical commit object mismatch")
    actual_tree = str(_git(source_root, "rev-parse", f"{commit}^{{tree}}", text=True))
    _expect(actual_tree == tree, "canonical tree object mismatch")
    for fact in source["object_facts"]:
        path = fact["path"]
        actual_blob = str(_git(source_root, "rev-parse", f"{commit}:{path}", text=True))
        _expect(actual_blob == fact["git_blob"], f"blob OID mismatch: {path}")
        _expect(str(_git(source_root, "cat-file", "-t", actual_blob, text=True)) == "blob", f"not a blob: {path}")
        raw = bytes(_git(source_root, "cat-file", "blob", actual_blob))
        _expect(len(raw) == fact["byte_length"], f"byte length mismatch: {path}")
        _expect(hashlib.sha256(raw).hexdigest() == fact["content_sha256"], f"content SHA-256 mismatch: {path}")


def validate(
    document: dict[str, Any],
    *,
    verify_references: bool = True,
    source_root: Path | None = None,
) -> dict[str, Any]:
    _expect(document.get("schema") == "sipi.p5-06k.required-com-compare-contract-gap.v1", "schema mismatch")
    _expect(document.get("status") == "required_com_compare_contract_gap_observed_not_closed", "status must remain open")

    scope = document.get("scope")
    _expect(isinstance(scope, dict), "scope must be a mapping")
    for key, expected in {
        "work_item": "P5-06k",
        "source_basis": "canonical_agent_com_git_objects_and_existing_external_records_only",
        "canonical_commit": COMMIT,
        "matlab_invoked": False,
        "product_rust_changed": False,
        "historical_evidence_changed": False,
        "compare_executed": False,
        "acceptance_or_release_promoted": False,
    }.items():
        _expect(scope.get(key) == expected, f"scope.{key} mismatch")

    source = document.get("canonical_agent_com")
    _expect(isinstance(source, dict), "canonical source must be a mapping")
    _expect(source.get("commit") == COMMIT and source.get("tree") == TREE, "canonical source identity mismatch")
    _expect(source.get("object_format") == "sha1", "canonical source object format mismatch")
    _expect(source.get("object_facts") == OBJECT_FACTS, "canonical object facts mismatch")
    if source_root is not None:
        _verify_source_git_objects(document, Path(source_root))

    contract = document.get("required_compare_contract")
    _expect(isinstance(contract, dict), "required compare contract missing")
    input_identity = contract.get("input_identity")
    _expect(input_identity.get("required_keys") == REQUIRED_INPUT_KEYS, "required input identity mismatch")
    _expect(input_identity.get("status") == "missing_clean_replayable_binding", "input provenance must remain open")
    stages = contract.get("stage_observables")
    _expect(stages.get("required_keys") == REQUIRED_STAGES, "required stage observables mismatch")
    _expect(stages.get("status") == "missing_compare_alignment_contract", "stage alignment must remain open")

    metrics = contract.get("metric_bundle")
    _expect(metrics.get("required") == EXPECTED_METRICS, "required metric bundle mismatch")
    _expect(metrics.get("observed_external_surface") == OBSERVED_METRICS, "observed metric surface mismatch")
    c4 = metrics.get("observed_c4_surface")
    _expect(c4.get("ids") == ["COM_dB", "ICN_mV", "ERL"], "C4 metric surface was changed")
    _expect(c4.get("relative_tolerance") == 0.01 and c4.get("scope") == "c4_metric_profile_only", "C4 policy scope mismatch")
    _expect(c4.get("cannot_substitute_for") == ["td_iln_db"], "TD-ILN substitution guard missing")

    checkpoints = contract.get("checkpoint_contract")
    _expect(checkpoints.get("observed_required_matrix_keys") == CHECKPOINT_KEYS, "checkpoint key surface mismatch")
    _expect(checkpoints.get("observed_case_count") == 2, "checkpoint case count mismatch")
    _expect(checkpoints.get("observed_case_checkpoint_digests") is True, "checkpoint digest observation missing")
    _expect(checkpoints.get("status") == "checkpoint_alignment_and_tolerance_missing", "checkpoint gap must remain open")

    alignment = contract.get("alignment_policy")
    _expect(alignment.get("status") == "missing", "alignment policy must remain missing")
    _expect(alignment.get("observed_facts", {}).get("observed_network_roles") == ["THRU", "FEXT1", "NEXT1"], "network role observation mismatch")
    _expect(alignment.get("observed_facts", {}).get("observed_port_order") == [1, 3, 2, 4], "port order observation mismatch")
    tolerance = contract.get("tolerance_policy")
    _expect(tolerance.get("status") == "missing_for_required_com_compare", "required tolerance must remain missing")
    observed_tolerances = tolerance.get("observed_non_acceptance_tolerances")
    _expect(isinstance(observed_tolerances, list) and len(observed_tolerances) == 4, "observed tolerance inventory mismatch")
    _expect(observed_tolerances[-1].get("scope") == ["COM_dB", "ICN_mV", "ERL"], "C4 tolerance scope was broadened")

    gaps = document.get("provenance_gaps")
    _expect(gaps.get("status") == "unresolved", "provenance gaps must remain unresolved")
    _expect("exact_authoritative_reference_artifact_payload" in gaps.get("clean_oracle", []), "oracle payload gap missing")
    _expect("normalized_input_digest_bound_to_the_required_matrix" in gaps.get("clean_input", []), "input digest gap missing")

    _expect(document.get("audit") == {"path": AUDIT_PATH, "sha256": AUDIT_SHA256}, "audit binding mismatch")

    if verify_references:
        audit_path = ROOT / AUDIT_PATH
        _expect(audit_path.is_file(), "audit missing")
        _expect(_sha256(audit_path) == AUDIT_SHA256, "audit hash mismatch")
        for relative, expected_hash in REFERENCE_HASHES.items():
            path = ROOT / relative
            _expect(path.is_file(), f"reference missing: {relative}")
            _expect(_sha256(path) == expected_hash, f"reference hash mismatch: {relative}")
        references = {item.get("path"): item.get("sha256") for item in document.get("references", [])}
        _expect(references == REFERENCE_HASHES, "reference inventory mismatch")

    non_claims = set(document.get("non_claims", []))
    for required in {
        "not_a_matlab_run",
        "not_a_product_oracle",
        "not_a_product_vs_oracle_compare",
        "not_acceptance_evidence",
        "not_release_evidence",
        "not_a_td_iln_value_or_tolerance_selection",
        "not_a_c4_to_required_metric_alias_promotion",
    }:
        _expect(required in non_claims, f"non-claim missing: {required}")
    return {
        "schema": document["schema"],
        "valid": True,
        "required_metrics": len(EXPECTED_METRICS),
        "observed_checkpoint_keys": len(CHECKPOINT_KEYS),
        "required_metric_tolerance_status": tolerance["status"],
        "alignment_status": alignment["status"],
        "provenance_status": gaps["status"],
        "source_git_object_checked": source_root is not None,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, help="optional external Agent-COM Git checkout")
    arguments = parser.parse_args()
    try:
        document = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))
        result = validate(document, source_root=arguments.source_root)
    except (AssertionError, OSError, UnicodeError, yaml.YAMLError) as error:
        print(json.dumps({"schema": "sipi.p5-06k.required-com-compare-contract-gap.v1", "valid": False, "source_git_object_checked": False, "reason": str(error)}, sort_keys=True))
        raise SystemExit(2) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
