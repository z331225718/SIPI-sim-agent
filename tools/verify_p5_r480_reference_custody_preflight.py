"""Verify the external-only P5 T13 R4.80 reference-custody preflight.

This gate only reads repository evidence records.  It never opens a recorded
external path, starts MATLAB, imports the product, or treats a product/Python
self-crosscheck as an oracle.  The result is deliberately blocked until the
recorded runner, input/default, warning, checkpoint, metric, tolerance, and
artifact custody facts form a replayable external bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "baselines" / "p5-r480-reference-custody-preflight.v1.yaml"
SCHEMA = "sipi.p5-13.com-r480-reference-custody-preflight.v1"

EXPECTED_HASH_BINDINGS = {
    "acceptance_contract": ("docs/baselines/com-r480-acceptance.v1.yaml", "e90fca0d14968a04e09df90cd8bd4fcc7f749abfa07ad2b4b29dc297351ef03b"),
    "availability_preflight": ("docs/baselines/com-r480-reference-availability-preflight.v1.yaml", "ca44d298350f1ab2c4d8f270450359290d4ec28868a6735508c7efe5b6b4a582"),
    "matlab_runner_preflight": ("docs/baselines/com-r480-matlab-runner-capability-preflight.v1.yaml", "00b0f84c64d97153a84cbd5130064b52a7b6b1666aa50d6d83e6217c06aaf20d"),
    "oracle_invocation_preflight": ("docs/baselines/com-r480-oracle-invocation-surface-preflight.v1.yaml", "57952d63868e54f32678ad0b7bd2b7a27287388631e2c3dd103e180057d72e99"),
    "git_object_preflight": ("docs/baselines/p5-agent-com-git-object-preflight.v1.yaml", "e787d0830c17561c5f8054eae681f7ee976da8d61201846cf40a1d1166d5809b"),
    "material_registry": ("docs/baselines/authorized-material-registry.v1.yaml", "e5c172bcb20d37aee933fefbbdfd0a816a82e9888f0ce6ed6a4d63f20e153b71"),
    "oracle_first_run": ("docs/baselines/p5-06-matlab-oracle-first-run-evidence.v1.yaml", "4e2f6bb1d55376f3b317acaa75008a4603f910c184c619c130ee786a90453d24"),
    "oracle_metric_surface": ("docs/baselines/p5-06-oracle-metric-surface.v1.yaml", "677ed155b9851352f3fe128212eb4b60a22be9ed03fd7afd763a3de0736a3036"),
    "normalized_input_surface": ("docs/baselines/p5-06-normalized-input-surface.v1.yaml", "886e2cdd52c90ed4e2dba59e162438a5dd14673fa160bb26225add75837f718f"),
    "oracle_metric_reference": ("docs/baselines/p5-06e-com-oracle-metric-reference.v1.yaml", "92a61cb9f7558e953d3ad1f35fd8c1bd0e482366ac6bb4f7d171d9a075ea5ef1"),
    "canonical_parameter_reference": ("docs/baselines/p5-r480-canonical-parameter-reference.v1.yaml", "489d70e7634e5daed0fe59f45bbb76a60904fd50045817e42715ce478c0d6a33"),
    "canonical_parameter_json": ("docs/baselines/p5-r480-canonical-parameter-json.v2.yaml", "7758452793602e2bf46b5b2a3267007785a7719d67c118a06e196ed46594b383"),
    "warning_observation": ("docs/baselines/p5-r480-warning-observation.v1.yaml", "862f1c930d1aff2463815273ba048dcb80edd52b8e80b56a4ec7eaa063f530b4"),
}

SOURCE_TARGET = {
    "canonical_origin": "https://github.com/z331225718/agent-com.git",
    "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
    "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
    "object_format": "sha1",
}
CAPABILITY_OBJECT = {
    "path": "schemas/r480-capability-envelope-v1.yaml",
    "git_blob": "69aeffa675341733277ccaf19a8e878cb716a315",
    "content_sha256": "9b3329e25559e595187ae1a0530785d5a8dbbdc02a035eeb44326aa91ee34b73",
    "byte_length": 9636,
}
RUNNER_OBJECT = {
    "path": "tools/run_matlab_oracle.py",
    "git_blob": "36d4fa55f6eaf9ecdd72ba2cebfbc1b01908e8bc",
    "content_sha256": "db63ed42375ac990cb53d9926f603e050b652b0706c079f2e4456a5d97d87d42",
    "byte_length": 30851,
}

EXPECTED_OUTPUT_KEYS = [
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
EXPECTED_CHECKPOINT_KEYS = ["DFE_taps", "TXLE_taps", "itick", "sgm_Ani__isi_xt_noise", "sigma_N", "tail_RSS"]
EXPECTED_BLOCKERS = [
    "capability_envelope_registry_copy_mismatch",
    "matlab_runner_startup_isolation_unproven",
    "oracle_invocation_authorization_missing",
    "replayable_external_custody_manifest_missing",
    "normalized_input_digest_missing",
    "caller_dependent_defaults_unresolved",
    "exact_run_warning_report_missing",
    "intermediate_checkpoint_tolerances_missing",
    "acceptance_metric_scope_incomplete",
    "full_metric_tolerance_and_alignment_policy_missing",
    "reference_artifact_payload_missing",
    "product_self_crosschecks_disqualified_as_oracle",
]


class CustodyError(RuntimeError):
    """Raised for malformed or drifted custody records."""


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CustodyError("document_not_mapping")
    return value


def _safe_repo_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or ":" in value:
        raise CustodyError("bound_path_not_repository_relative")
    path = root / value
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise CustodyError("bound_path_escapes_repository") from error
    return path


def _exact(value: object, expected: object) -> bool:
    return value == expected


def _material(materials: list[dict[str, Any]], material_id: str) -> dict[str, Any] | None:
    return next((item for item in materials if item.get("id") == material_id), None)


def _selected_materials(registry: dict[str, Any]) -> list[dict[str, Any]]:
    ids = {
        "com-r480-matlab-source",
        "com-r480-capability-envelope",
        "com-r480-config-120g-c2m",
        "com-synthetic-thru",
        "com-synthetic-fext",
        "com-synthetic-next",
        "com-synthetic-manifest",
        "com-r480-legacy-output",
        "matlab-r2024b",
    }
    return sorted((item for item in registry.get("materials", []) if item.get("id") in ids), key=lambda item: item["id"])


def _verify_hash_bindings(document: dict[str, Any], root: Path, blockers: list[str]) -> dict[str, dict[str, Any]]:
    bindings = document.get("hash_bindings")
    if not isinstance(bindings, dict) or set(bindings) != set(EXPECTED_HASH_BINDINGS):
        blockers.append("hash_binding_inventory_invalid")
        return {}
    docs: dict[str, dict[str, Any]] = {}
    for name, (expected_path, expected_hash) in EXPECTED_HASH_BINDINGS.items():
        binding = bindings.get(name)
        if not isinstance(binding, dict) or set(binding) != {"path", "sha256"} or binding.get("path") != expected_path or binding.get("sha256") != expected_hash:
            blockers.append(f"hash_binding_record_invalid:{name}")
            continue
        try:
            path = _safe_repo_path(root, expected_path)
            raw = path.read_bytes()
        except (CustodyError, OSError):
            blockers.append(f"hash_binding_file_unavailable:{name}")
            continue
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            blockers.append(f"hash_binding_file_drift:{name}")
            continue
        try:
            loaded = yaml.safe_load(raw.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError):
            blockers.append(f"hash_binding_yaml_invalid:{name}")
            continue
        if not isinstance(loaded, dict):
            blockers.append(f"hash_binding_yaml_not_mapping:{name}")
            continue
        docs[name] = loaded
    return docs


def _verify_source(document: dict[str, Any], docs: dict[str, dict[str, Any]], blockers: list[str]) -> None:
    source = document.get("external_source")
    if not isinstance(source, dict) or set(source) != {"git_target", "capability_object", "oracle_runner_object", "capability_registry_copy"}:
        blockers.append("external_source_shape_invalid")
        return
    if source["git_target"] != SOURCE_TARGET or source["capability_object"] != CAPABILITY_OBJECT or source["oracle_runner_object"] != RUNNER_OBJECT:
        blockers.append("external_source_object_identity_invalid")
    registry_copy = source["capability_registry_copy"]
    expected_registry_copy = {
        "material_id": "com-r480-capability-envelope",
        "content_sha256": "40f8020d178eda102d9032ce3691701ee8bc581a3c9cc5beaa894d1f326d51c7",
        "byte_length": 9985,
        "status": "conflicting_external_copy",
    }
    if registry_copy != expected_registry_copy:
        blockers.append("capability_registry_conflict_record_invalid")

    acceptance = docs.get("acceptance_contract", {})
    acceptance_source = acceptance.get("external_oracle", {}).get("source")
    expected_acceptance_source = {**SOURCE_TARGET, **{key: value for key, value in CAPABILITY_OBJECT.items() if key != "byte_length"}, "redistribution": "external_only"}
    if acceptance_source != expected_acceptance_source:
        blockers.append("acceptance_source_binding_mismatch")
    availability = docs.get("availability_preflight", {}).get("source")
    expected_availability_source = {**SOURCE_TARGET, **{key: value for key, value in CAPABILITY_OBJECT.items() if key != "byte_length"}, "materialization": "external_clean_temp_only"}
    if availability != expected_availability_source:
        blockers.append("availability_source_binding_mismatch")

    manifest = docs.get("git_object_preflight", {})
    if manifest.get("target") != SOURCE_TARGET:
        blockers.append("git_object_target_mismatch")
    entries = manifest.get("entries", [])
    for path, expected in ((CAPABILITY_OBJECT["path"], CAPABILITY_OBJECT), (RUNNER_OBJECT["path"], RUNNER_OBJECT)):
        entry = next((item for item in entries if item.get("path") == path), None)
        if entry is None or entry.get("git_oid") != expected["git_blob"] or entry.get("content_sha256") != expected["content_sha256"] or entry.get("byte_length") != expected["byte_length"]:
            blockers.append(f"git_object_entry_mismatch:{path}")

    registry = docs.get("material_registry", {})
    materials = registry.get("materials", [])
    registry_material = _material(materials, "com-r480-capability-envelope")
    if registry_material is None:
        blockers.append("registry_capability_material_missing")
    elif registry_material.get("sha256") != registry_copy["content_sha256"] or registry_material.get("byte_length") != registry_copy["byte_length"]:
        blockers.append("registry_capability_material_record_mismatch")
    if registry_copy.get("content_sha256") == CAPABILITY_OBJECT["content_sha256"] and registry_copy.get("byte_length") == CAPABILITY_OBJECT["byte_length"]:
        blockers.append("capability_registry_conflict_not_preserved")


def _verify_materials(document: dict[str, Any], docs: dict[str, dict[str, Any]], blockers: list[str]) -> None:
    section = document.get("external_materials")
    expected_registry = {"path": EXPECTED_HASH_BINDINGS["material_registry"][0], "sha256": EXPECTED_HASH_BINDINGS["material_registry"][1], "status": "authorized_external_only"}
    if not isinstance(section, dict) or set(section) != {"registry", "selected_digest", "selected"} or section.get("registry") != expected_registry:
        blockers.append("external_material_section_invalid")
        return
    registry = docs.get("material_registry", {})
    selected = _selected_materials(registry)
    if section.get("selected") != selected:
        blockers.append("external_material_identity_mismatch")
    if section.get("selected_digest") != "e5d621760825cdf3be8d22b5862efb92aae08e5164d8e459c3dff7fb00158b09" or _digest(selected) != section.get("selected_digest"):
        blockers.append("external_material_digest_mismatch")


def _verify_runner(document: dict[str, Any], docs: dict[str, dict[str, Any]], blockers: list[str]) -> None:
    runner = document.get("runner")
    if not isinstance(runner, dict) or set(runner) != {"capability_preflight", "invocation_surface", "historical_first_run"}:
        blockers.append("runner_section_shape_invalid")
        return
    capability = runner["capability_preflight"]
    expected_capability = {
        "path": EXPECTED_HASH_BINDINGS["matlab_runner_preflight"][0],
        "sha256": EXPECTED_HASH_BINDINGS["matlab_runner_preflight"][1],
        "status": "indeterminate_startup_isolation_unproven",
        "report": {"schema": "sipi.com.matlab-runner-probe-report.v1", "sha256": "f6b1fc48d2749b22c6d2cb4c0ff0b9edfa7131237a5f06ad2cbec1872aa2df16"},
        "executable": {"material_id": "matlab-r2024b", "sha256": "4b0fcf8112211ad1ae6ef5e51df0801d7afbe89c4daaac45473a46e1de16e633", "byte_length": 458288},
        "builtin_identity": {"release": "2024b", "version": "24.2.0.2712019 (R2024b)", "platform": "PCWIN64"},
        "isolation": {"cwd": "external_empty_temp", "matlabpath": "cleared", "matlab_prefdir": "external_temporary", "startup_isolation": "unproven"},
    }
    if capability != expected_capability:
        blockers.append("runner_capability_record_invalid")
    capability_doc = docs.get("matlab_runner_preflight", {})
    observation = capability_doc.get("runner_observation", {})
    if observation.get("status") != "indeterminate_startup_isolation_unproven" or observation.get("probe", {}).get("startup_isolation") != "unproven" or observation.get("result", {}).get("license_runtime_observation") != "unknown":
        blockers.append("runner_capability_observation_drift")
    invocation = runner["invocation_surface"]
    expected_invocation = {
        "path": EXPECTED_HASH_BINDINGS["oracle_invocation_preflight"][0],
        "sha256": EXPECTED_HASH_BINDINGS["oracle_invocation_preflight"][1],
        "status": "runner_interface_partially_observed",
        "report": {"schema": "sipi.com.r480.oracle-invocation-surface-report.v1", "sha256": "b4fd1ff3600463c2761cb30ff28f0ace258eada66be880ff0a74a06ccb66f44f"},
        "tool": RUNNER_OBJECT,
        "execution": {"authorized": False, "invoked": False, "status": "dynamic_invocation_not_authorized_or_not_safe"},
    }
    if invocation != expected_invocation:
        blockers.append("runner_invocation_record_invalid")
    invocation_doc = docs.get("oracle_invocation_preflight", {})
    if invocation_doc.get("execution") != expected_invocation["execution"] or invocation_doc.get("observation", {}).get("status") != "runner_interface_partially_observed":
        blockers.append("runner_invocation_observation_drift")
    historical = runner["historical_first_run"]
    expected_historical = {
        "evidence_path": EXPECTED_HASH_BINDINGS["oracle_first_run"][0],
        "evidence_sha256": EXPECTED_HASH_BINDINGS["oracle_first_run"][1],
        "status": "hash_bound_external_observation_not_replayable_custody",
        "materialization": "fresh_materialization_cleaned",
        "replay_manifest": "missing",
        "startup_isolation": "unproven",
    }
    if historical != expected_historical:
        blockers.append("historical_first_run_record_invalid")


def _verify_canonical(document: dict[str, Any], docs: dict[str, dict[str, Any]], blockers: list[str]) -> None:
    canonical = document.get("canonical_inputs")
    if not isinstance(canonical, dict) or set(canonical) != {"source_reference", "canonical_json_v2", "normalized_surface", "normalized_input_digest"}:
        blockers.append("canonical_input_section_shape_invalid")
        return
    source_doc = docs.get("canonical_parameter_reference", {})
    json_doc = docs.get("canonical_parameter_json", {})
    normalized_doc = docs.get("normalized_input_surface", {})
    source_expected = {"path": EXPECTED_HASH_BINDINGS["canonical_parameter_reference"][0], "sha256": EXPECTED_HASH_BINDINGS["canonical_parameter_reference"][1], "source_sha256": "642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad", "key_count": 214, "call_count": 229}
    json_expected = {"path": EXPECTED_HASH_BINDINGS["canonical_parameter_json"][0], "sha256": EXPECTED_HASH_BINDINGS["canonical_parameter_json"][1], "source_sha256": source_expected["source_sha256"], "key_count": 214, "statically_evaluated_calls": 3, "needs_oracle_calls": 20, "default_kind_counts": {"inf_literal": 1, "literal": 163, "needs_matlab_oracle": 20, "none": 20, "resolved_reference": 7, "statically_evaluated": 3, "string_literal": 15}}
    normalized_expected = {"path": EXPECTED_HASH_BINDINGS["normalized_input_surface"][0], "sha256": EXPECTED_HASH_BINDINGS["normalized_input_surface"][1], "config_material_id": "com-r480-config-120g-c2m", "config_sha256": "f2c4c92f9549e720fff2843df6dc861aca7a503d59b2208898c2b67fa6fc0fc9", "canonical_keys": 214, "keys_in_config": 82, "port_order": "[ 1 3 2 4 ]", "keys_digest": "53f3be62a8327ac87e77ab61382fc77d305d250eca047c9a453854cd4aec00d9"}
    if canonical["source_reference"] != source_expected or canonical["canonical_json_v2"] != json_expected or canonical["normalized_surface"] != normalized_expected or canonical["normalized_input_digest"] != {"status": "missing", "value": None}:
        blockers.append("canonical_input_record_invalid")
    if source_doc.get("source_sha256") != source_expected["source_sha256"] or source_doc.get("key_count") != 214 or source_doc.get("call_count") != 229:
        blockers.append("canonical_source_observation_drift")
    if json_doc.get("source_sha256") != source_expected["source_sha256"] or json_doc.get("key_count") != 214 or json_doc.get("statically_evaluated_calls") != 3 or json_doc.get("needs_oracle_calls") != 20:
        blockers.append("canonical_json_observation_drift")
    counts = Counter(default.get("kind") for entry in json_doc.get("keys", {}).values() for default in entry.get("defaults", []))
    if dict(sorted(counts.items())) != json_expected["default_kind_counts"]:
        blockers.append("canonical_default_kind_count_drift")
    if normalized_doc.get("config_sha256") != normalized_expected["config_sha256"] or normalized_doc.get("canonical_keys") != 214 or normalized_doc.get("keys_in_config") != 82 or normalized_doc.get("port_order_observed") != normalized_expected["port_order"] or _digest(normalized_doc.get("keys")) != normalized_expected["keys_digest"]:
        blockers.append("normalized_input_surface_drift")


def _verify_defaults_and_warnings(document: dict[str, Any], docs: dict[str, dict[str, Any]], blockers: list[str]) -> None:
    defaults = document.get("defaults")
    expected_defaults = {"status": "partial_static_observation_not_authoritative", "source_sha256": "642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad", "resolved_default_contract": "missing", "caller_dependent_defaults": 20, "external_default_payload": "not_recorded", "product_or_python_self_crosscheck": "excluded_as_oracle"}
    if defaults != expected_defaults:
        blockers.append("default_custody_record_invalid")
    warning = document.get("warnings")
    expected_warning = {
        "static_observation": {"path": EXPECTED_HASH_BINDINGS["warning_observation"][0], "sha256": EXPECTED_HASH_BINDINGS["warning_observation"][1], "source_sha256": "642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad", "warning_call_count": 25, "inventory_digest": "99acc4cb75d7f31e84d4e75f72a5f343e361ae87b72af815baf3d8a60f553078"},
        "exact_run_warning_report": {"status": "missing", "contract": "missing"},
    }
    if warning != expected_warning:
        blockers.append("warning_custody_record_invalid")
    warning_doc = docs.get("warning_observation", {})
    if warning_doc.get("source_sha256") != expected_warning["static_observation"]["source_sha256"] or warning_doc.get("warning_call_count") != 25 or _digest(warning_doc.get("warnings")) != expected_warning["static_observation"]["inventory_digest"]:
        blockers.append("warning_observation_drift")


def _summary(evidence: dict[str, Any], blockers: list[str]) -> dict[str, Any] | None:
    if evidence.get("status") != "matlab_oracle_first_run_succeeded_hash_bound":
        blockers.append("oracle_first_run_status_invalid")
    hashes = evidence.get("output_file_hashes")
    if hashes != {"matlab_oracle.mat": "dd47cb3dbe3f72e63b19c6331f4cbc504027f3b72b4a12bdc8503e9c993edbca", "summary.json": "151d8a03bbc4ef399a84dc97c6c4b6a87c22e3d12a1a0a611b07806c835b55ed"}:
        blockers.append("oracle_artifact_hashes_drift")
    try:
        summary = json.loads(evidence["summary_content"])
    except (KeyError, TypeError, json.JSONDecodeError):
        blockers.append("oracle_summary_invalid")
        return None
    if summary.get("matlab_release") != "2024b" or summary.get("matlab_version") != "24.2.0.2712019 (R2024b)" or summary.get("computer") != "PCWIN64" or summary.get("case_count") != 2 or summary.get("summary_case_index") != 1:
        blockers.append("oracle_summary_identity_drift")
    return summary


def _verify_checkpoints_and_metrics(document: dict[str, Any], docs: dict[str, dict[str, Any]], blockers: list[str]) -> None:
    evidence = docs.get("oracle_first_run", {})
    summary = _summary(evidence, blockers)
    if summary is None:
        return
    checkpoints = document.get("checkpoints")
    expected_checkpoints = {
        "evidence_path": EXPECTED_HASH_BINDINGS["oracle_first_run"][0],
        "summary_json_sha256": "151d8a03bbc4ef399a84dc97c6c4b6a87c22e3d12a1a0a611b07806c835b55ed",
        "case_count": 2,
        "keys": EXPECTED_CHECKPOINT_KEYS,
        "keys_digest": "8def09ef82da18e536e074c76abeedd34e616b19cd30580efdfd3cfd3a8ddb13",
        "network_metrics_digest": "c7c80a279f717fa0ca0b92f8fa6979d0a1608218af97edd83e1923a58927bfd5",
        "case_checkpoint_digests": {"case_1": "c52b3626d2a196808dc80daac938e8f14c23455c7f1c59a7a6add7dcec24c42d", "case_2": "9eef31a5815407357efb5a5e1dea8c9d6e1244cf1d1444c83edcdaf0597cf11c"},
        "payload_status": "summary_content_only",
        "per_checkpoint_tolerance": "missing",
    }
    if checkpoints != expected_checkpoints:
        blockers.append("checkpoint_custody_record_invalid")
    checkpoint_keys = sorted({key for case in summary.get("case_metrics", []) for key in case.get("internal_checkpoints", {})})
    case_checkpoint_digests = {
        f"case_{case.get('case_index')}": _digest(case.get("internal_checkpoints"))
        for case in summary.get("case_metrics", [])
    }
    if checkpoint_keys != EXPECTED_CHECKPOINT_KEYS or case_checkpoint_digests != {"case_1": "c52b3626d2a196808dc80daac938e8f14c23455c7f1c59a7a6add7dcec24c42d", "case_2": "9eef31a5815407357efb5a5e1dea8c9d6e1244cf1d1444c83edcdaf0597cf11c"} or _digest(summary.get("network_metrics")) != "c7c80a279f717fa0ca0b92f8fa6979d0a1608218af97edd83e1923a58927bfd5" or _digest([entry.get("internal_checkpoints") for entry in summary.get("case_metrics", [])]) != "f1790077615859092505b7aca48a5ff4aa34e765dded7736843b455763faed63":
        blockers.append("checkpoint_summary_digest_drift")
    metrics = document.get("metrics")
    expected_metrics_surface = {
        "path": EXPECTED_HASH_BINDINGS["oracle_metric_surface"][0],
        "sha256": EXPECTED_HASH_BINDINGS["oracle_metric_surface"][1],
        "case_count": 2,
        "network_roles": ["THRU", "FEXT1", "NEXT1"],
        "output_metric_keys": EXPECTED_OUTPUT_KEYS,
        "output_metric_keys_digest": "b685bf240f7d97b827e89a8025c869a4413227db2798c6e45c693c1628e32d94",
    }
    expected_c4 = {
        "path": EXPECTED_HASH_BINDINGS["oracle_metric_reference"][0],
        "sha256": EXPECTED_HASH_BINDINGS["oracle_metric_reference"][1],
        "summary_json_sha256": "151d8a03bbc4ef399a84dc97c6c4b6a87c22e3d12a1a0a611b07806c835b55ed",
        "aggregate_reference": {"COM_dB": 5.190191599808681, "ICN_mV": 4.601554213273623, "ERL": 16.742740133561476},
        "aggregate_reference_digest": "f7b30359cecf9958952caf7b7081c2e78e6057dd3336d84ae87e1d8dbda1bae7",
        "case_references": [{"case_index": 1, "COM_dB": 5.190191599808681, "ICN_mV": 4.601554213273623, "ERL": 16.742740133561476}, {"case_index": 2, "COM_dB": 4.877647775233487, "ICN_mV": 4.601554213273623, "ERL": 16.742740133561476}],
        "policy": "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct",
    }
    expected_metrics = {
        "surface": expected_metrics_surface,
        "summary_output_metrics_digest": "97669f35a820cf02176227e153805674be8b2b8a1e746e9ae5edf494a8ec6726",
        "case_output_metrics_digest": "cd995b124233c863e04032de7b7c7c70a1fb2d8aa1fc0c77da758d6a8607b529",
        "c4_reference": expected_c4,
        "acceptance_metric_scope": {"required_metric_ids": ["com_db", "erl_db", "td_iln_db"], "observed_c4_metric_ids": ["COM_dB", "ICN_mV", "ERL"], "status": "incomplete_scope_mismatch"},
    }
    if metrics != expected_metrics:
        blockers.append("metric_custody_record_invalid")
    surface_doc = docs.get("oracle_metric_surface", {})
    if surface_doc.get("case_count") != 2 or surface_doc.get("network_roles") != ["THRU", "FEXT1", "NEXT1"] or surface_doc.get("output_metric_keys") != EXPECTED_OUTPUT_KEYS or _digest(surface_doc.get("output_metric_keys")) != expected_metrics_surface["output_metric_keys_digest"]:
        blockers.append("metric_surface_drift")
    output_metrics = summary.get("output_metrics")
    cases = summary.get("case_metrics")
    if _digest(output_metrics) != expected_metrics["summary_output_metrics_digest"] or _digest([{"case_index": case.get("case_index"), "output_metrics": case.get("output_metrics")} for case in cases]) != expected_metrics["case_output_metrics_digest"]:
        blockers.append("metric_summary_digest_drift")
    reference = docs.get("oracle_metric_reference", {})
    if reference.get("summary_json_sha256") != expected_c4["summary_json_sha256"] or reference.get("aggregate_reference_digest") != expected_c4["aggregate_reference_digest"] or reference.get("aggregate_reference") != expected_c4["aggregate_reference"] or reference.get("case_references") != expected_c4["case_references"] or reference.get("c4_policy") != expected_c4["policy"]:
        blockers.append("c4_reference_drift")


def _verify_tolerance_artifacts_admission(document: dict[str, Any], docs: dict[str, dict[str, Any]], blockers: list[str]) -> None:
    expected_tolerance = {
        "status": "incomplete_for_t14",
        "observed_c4_policy": {"id": "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct", "relative_tolerance": 0.01, "metrics": ["COM_dB", "ICN_mV", "ERL"], "scope": "c4_metric_profile_only"},
        "full_matrix": {"metric_tolerances": "missing", "intermediate_checkpoint_tolerances": "missing", "warning_tolerances": "missing", "alignment_policy": "missing", "normalized_input_tolerance": "missing"},
    }
    if document.get("tolerance") != expected_tolerance:
        blockers.append("tolerance_record_invalid")
    expected_artifacts = {
        "first_run": {"evidence_path": EXPECTED_HASH_BINDINGS["oracle_first_run"][0], "evidence_sha256": EXPECTED_HASH_BINDINGS["oracle_first_run"][1], "matlab_oracle_mat_sha256": "dd47cb3dbe3f72e63b19c6331f4cbc504027f3b72b4a12bdc8503e9c993edbca", "summary_json_sha256": "151d8a03bbc4ef399a84dc97c6c4b6a87c22e3d12a1a0a611b07806c835b55ed", "stdout_tail_sha256": "d37597ec49c670a12060b78a68cf9cd5263a1df6d9268a351dbdb8b6e6c8be1b", "custody": "external_only", "payload_status": "summary_recorded_mat_payload_unavailable"},
        "runner_reports": {"matlab_probe_report_sha256": "f6b1fc48d2749b22c6d2cb4c0ff0b9edfa7131237a5f06ad2cbec1872aa2df16", "invocation_surface_report_sha256": "b4fd1ff3600463c2761cb30ff28f0ace258eada66be880ff0a74a06ccb66f44f"},
    }
    if document.get("artifacts") != expected_artifacts:
        blockers.append("artifact_custody_record_invalid")
    evidence = docs.get("oracle_first_run", {})
    if evidence.get("stdout_tail_hash") != expected_artifacts["first_run"]["stdout_tail_sha256"] or evidence.get("custody") != "fresh_materialization_cleaned":
        blockers.append("oracle_report_hash_or_custody_drift")
    expected_admission = {"t14_full_compare_matrix_admitted": False, "status": "blocked", "blockers": EXPECTED_BLOCKERS, "next_step": "T14_not_admitted_until_all_blockers_are_resolved_by_authorized_external_replay"}
    if document.get("admission") != expected_admission:
        blockers.append("admission_record_not_fail_closed")
    if document.get("scope") != {"oracle": "external_matlab_only", "product_self_comparison_as_oracle": "forbidden", "unauthorized_matlab_rerun": "forbidden", "unauthorized_external_asset_read": "forbidden", "product_runtime_dependency": "forbidden"}:
        blockers.append("scope_boundary_invalid")


def verify_document(document: object, root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    top_keys = {"schema", "ticket", "baseline_commit", "status", "profile", "scope", "hash_bindings", "external_source", "external_materials", "runner", "canonical_inputs", "defaults", "warnings", "checkpoints", "metrics", "tolerance", "artifacts", "admission", "non_claims"}
    if not isinstance(document, dict) or set(document) != top_keys:
        return {"valid": False, "t14_full_compare_matrix_admitted": False, "blockers": ["baseline_shape_invalid"]}
    if document.get("schema") != SCHEMA or document.get("ticket") != "T13" or document.get("baseline_commit") != "805ebb6b" or document.get("status") != "reference_custody_vertical_preflight_recorded_blocked":
        blockers.append("baseline_identity_invalid")
    profile = document.get("profile")
    if profile != {"id": "com-r480-envelope-v1", "acceptance_contract": {"path": EXPECTED_HASH_BINDINGS["acceptance_contract"][0], "sha256": EXPECTED_HASH_BINDINGS["acceptance_contract"][1]}}:
        blockers.append("profile_binding_invalid")
    docs = _verify_hash_bindings(document, root, blockers)
    _verify_source(document, docs, blockers)
    _verify_materials(document, docs, blockers)
    _verify_runner(document, docs, blockers)
    _verify_canonical(document, docs, blockers)
    _verify_defaults_and_warnings(document, docs, blockers)
    _verify_checkpoints_and_metrics(document, docs, blockers)
    _verify_tolerance_artifacts_admission(document, docs, blockers)
    claims = document.get("non_claims")
    if not isinstance(claims, list) or len(claims) != 4 or not all(isinstance(item, str) and item for item in claims):
        blockers.append("non_claims_invalid")
    return {"valid": not blockers, "ticket": "T13", "t14_full_compare_matrix_admitted": False, "status": "blocked", "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    args = parser.parse_args()
    try:
        document = _load_yaml(args.baseline)
        result = verify_document(document, ROOT)
    except (CustodyError, OSError, UnicodeError, yaml.YAMLError) as error:
        result = {"valid": False, "ticket": "T13", "t14_full_compare_matrix_admitted": False, "status": "blocked", "blockers": [str(error)]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
