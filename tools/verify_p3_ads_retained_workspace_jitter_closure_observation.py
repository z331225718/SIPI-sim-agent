"""Verify retained ADS workspace bytes and the observed missing P3 fields."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/p3-ads-retained-workspace-jitter-closure-observation.v1.yaml"
SCHEMA = "sipi.p3-ads-retained-workspace-jitter-closure-observation.v1"
FILES = {
    "workspace.ads": ("9882100aae00151622e6d7a8afa04e43651e4f4cbcb83349f40df525c5b091b9", 1414),
    "netlist.log": ("676838f9bff5f92cd0e645da7db20b3adf3399cab015300d1d3b34e8098f3983", 7858),
    "EyeProbeSummary.xls": ("ea65986f08486c43d8af6e16b2d31fdcf32e9075755e8ba17e31faa29ad3af5f", 5632),
    "original.ds": ("d295530dc5aa28697e2b23a0d471a520613efc309a570a68964c538cb6f45d76", 348672),
    "nojitter.ds": ("17c5c6f633ad0c47d63d100277b78013519adb104fe469e10fad2dbb1cd4e8a4", 480768),
    "txonly.ds": ("88663636b344a43f378a269f61c191122dfc555f568bff4227a92aff3d715d9f", 464384),
    "rxonly.ds": ("697328a7c9ae06d1377e7d32393dee26fa8aa0b4246abc22347dada264ea7df5", 349696),
}
NETLIST_REQUIRED = (
    "ami_jitter_enable=1", "ami_rx_rj=rx_rj*ami_jitter_enable", "ami_rx_dj=rx_dj*ami_jitter_enable", "ami_tx_rj=tx_rj*ami_jitter_enable", "ami_tx_dj=tx_dj*ami_jitter_enable", "ami_tx_dcd=tx_dcd*ami_jitter_enable",
    "rx_rj=0", "rx_dj=0", "tx_rj=0", "tx_dj=0", "tx_dcd=0",
    "JitterName[1]=\"Tx_Sj\"", "JitterName[2]=\"Tx_Sj_Frequency\"", "JitterValue[1]=0.0", "JitterValue[2]=0.0",
    "JitterName[1]=\"Rx_Sj\"", "JitterName[2]=\"Rx_DCD\"", "JitterName[3]=\"Rx_Noise\"", "JitterValue[3]=0.0",
    "Save_JitterRMS=no", "Save_JitterPP=no", "Save_Bathtub=no", "Save_Waveform=no", "Save_Contour=yes",
    "TimePoints=400", "AmplitudeResolution=0.001 V", "Type=\"Statistical\"", "NumberTimePtPerUI=32",
    "wave_capture_delay", "wave_capture_cnt", "wave_capture_mode",
)


class EvidenceError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load() -> dict[str, Any]:
    try:
        value = yaml.safe_load(DOCUMENT.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise EvidenceError("document_invalid") from error
    if not isinstance(value, dict):
        raise EvidenceError("document_invalid")
    return value


def _verify_workspace(root: Path) -> None:
    for relative, (digest, size) in FILES.items():
        path = root / relative
        try:
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise EvidenceError("workspace_file_not_regular")
            data = path.read_bytes()
        except OSError as error:
            raise EvidenceError("workspace_file_unavailable") from error
        if len(data) != size or _sha256(data) != digest:
            raise EvidenceError(f"workspace_file_identity_invalid:{relative}")
    try:
        netlist = (root / "netlist.log").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise EvidenceError("workspace_netlist_unreadable") from error
    if any(token not in netlist for token in NETLIST_REQUIRED):
        raise EvidenceError("workspace_missing_observed_configuration")


def validate(document: dict[str, Any]) -> None:
    expected = {"schema", "kind", "captured_at_utc", "workspace", "observed_configuration", "missing_fields", "conclusion", "admission", "non_claims", "audit_ref"}
    if set(document) != expected or document.get("schema") != SCHEMA or document.get("kind") != "external_retained_ads_workspace_dependency_closure_not_product_admission":
        raise EvidenceError("document_identity_invalid")
    workspace = document.get("workspace")
    if not isinstance(workspace, dict) or set(workspace) != {"root_ref", "files"} or workspace["root_ref"] != "ads_retained_workspace":
        raise EvidenceError("workspace_shape_invalid")
    files = workspace["files"]
    if not isinstance(files, list) or {item.get("path") for item in files if isinstance(item, dict)} != set(FILES):
        raise EvidenceError("workspace_file_set_invalid")
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"} or FILES.get(item["path"]) != (item["sha256"], item["bytes"]):
            raise EvidenceError("workspace_file_binding_invalid")
    if document.get("observed_configuration") != {
        "channel": "statistical", "bitrate_gbps": 32, "samples_per_ui": 32, "ami_jitter_enable": 1,
        "jitter_values": "all_retained_tx_rx_jitter_dcd_noise_values_zero",
        "eye_probe": {"save_jitter_rms": False, "save_jitter_pp": False, "save_bathtub": False, "save_waveform": False, "save_contour": True, "time_points": 400, "amplitude_resolution_v": 0.001, "ber_contour": [1.0e-12, 1.0e-11, 1.0e-10, 1.0e-9, 1.0e-8, 1.0e-7, 1.0e-6, 1.0e-5, 1.0e-4, 1.0e-3]},
        "receiver": {"wave_capture_delay": 1000, "wave_capture_count": 2047, "wave_capture_mode": 2, "cdr_lock_semantics_observed": False},
        "equalizer": {"adaptive_mode": 3, "gain_db": 0, "lfeq": 0, "peak": 0, "product_stage_contract_observed": False},
    }:
        raise EvidenceError("observed_configuration_invalid")
    if document.get("missing_fields") != ["jitter_observable_definition_and_reference", "jitter_tolerance_and_acceptance_rule", "eye_folding_and_bin_semantics", "cdr_clock_source_acquisition_and_lock_contract", "product_equalizer_profile_and_stage_identity", "canonical_input_asset_and_external_runtime_dependency_closure"]:
        raise EvidenceError("missing_field_inventory_invalid")
    if document.get("conclusion") != {"highest_value_slice": "retained_workspace_dependency_closure_and_missing_field_audit", "product_algorithm_implemented": False, "strict_waveform_mismatch_explained": False, "status": "blocked_missing_product_semantics_and_runtime_identity"}:
        raise EvidenceError("conclusion_invalid")
    if document.get("admission") != {"external_workspace_promoted": False, "receiver_accepted": False, "candidate_waveform_accepted": False, "release_promoted": False}:
        raise EvidenceError("admission_invalid")
    if document.get("non_claims") != ["retained_ds_and_xls_bytes_are_not_product_input", "disabled_eye_outputs_are_not_observed_jitter_or_bathtub_results", "ADS_configuration_strings_do_not_define_product_or_legal_semantics", "no_alignment_gain_dc_polarity_tolerance_relaxation_or_oracle_fit_was_used", "no_release_or_external_runtime_authorization_is_claimed"]:
        raise EvidenceError("non_claims_invalid")
    audit_ref = document.get("audit_ref")
    if not isinstance(audit_ref, str) or not audit_ref.startswith("docs/baselines/audits/") or not (ROOT / audit_ref).is_file():
        raise EvidenceError("audit_reference_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path)
    args = parser.parse_args()
    try:
        document = _load()
        validate(document)
        if args.workspace_root is not None:
            _verify_workspace(args.workspace_root)
        print(json.dumps({"schema": SCHEMA, "valid": True, "external_workspace_verified": args.workspace_root is not None}, sort_keys=True))
        return 0
    except EvidenceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
