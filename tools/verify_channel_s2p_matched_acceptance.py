"""Verify the observer-only numerical policy for the selected matched S2P profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.s2p-matched-acceptance.v1"
SHA1 = 40
SHA256 = 64


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _safe_path(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and not (len(value) >= 2 and value[0].isalpha() and value[1] == ":")
        and ".." not in value.split("/")
    )


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml_unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("acceptance_not_object")
    return value


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=text).stdout


def verify_document(document: object, source_root: Path) -> dict:
    blockers: list[str] = []
    if not _exact(document, {"schema", "selection", "source", "contract", "oracle", "acceptance", "non_claims"}) or document.get("schema") != SCHEMA:
        return {"valid": False, "acceptance_ready": False, "blockers": ["acceptance_schema_invalid"]}
    selection = document["selection"]
    if not _exact(selection, {"profile_id", "capability", "required", "status", "decision_ref"}) or selection.get("profile_id") != "channel-s2p-channel-16ghz-3db-v1" or selection.get("capability") != "channel" or selection.get("required") is not True or selection.get("status") != "user_selected" or not isinstance(selection.get("decision_ref"), str) or not selection["decision_ref"]:
        blockers.append("selection_invalid")
    source = document["source"]
    source_keys = {"canonical_origin", "commit", "tree", "object_format", "path", "git_blob", "content_sha256", "redistribution"}
    if not _exact(source, source_keys) or not _hex(source.get("commit"), SHA1) or not _hex(source.get("tree"), SHA1) or source.get("object_format") != "sha1" or not _safe_path(source.get("path")) or not _hex(source.get("git_blob"), SHA1) or not _hex(source.get("content_sha256"), SHA256) or source.get("redistribution") != "external_only":
        blockers.append("source_anchor_invalid")
    else:
        try:
            origin = str(_git(source_root, "remote", "get-url", "origin")).strip()
            tree = str(_git(source_root, "rev-parse", f"{source['commit']}^{{tree}}")).strip()
            blob = str(_git(source_root, "rev-parse", f"{source['commit']}:{source['path']}")).strip()
            payload = _git(source_root, "cat-file", "blob", blob, text=False)
            if origin != source["canonical_origin"] or tree != source["tree"] or blob != source["git_blob"] or hashlib.sha256(payload).hexdigest() != source["content_sha256"]:
                blockers.append("source_git_object_identity_mismatch")
        except (OSError, subprocess.CalledProcessError):
            blockers.append("source_git_object_unavailable")
    expected_contract = {"schema": "sipi.channel.s2p-matched.v1", "port_order": ["source_port_1", "receiver_port_2"], "reference_impedance_ohm": 50.0, "termination": "matched_explicit", "wave_definition": "real_z0_power_wave", "conditioning": "none", "resampling": "none", "window": "none", "trim": "none"}
    if document["contract"] != expected_contract:
        blockers.append("matched_contract_invalid")
    expected_oracle = {"mode": "external_git_object_standard_dft_only", "execution_status": "reproducibility_required", "product_fallback": "forbidden", "environment": {"platform": "windows-x86_64", "observer_implementation_identity": "required_at_comparison", "product_build": "independent_sipi_channel_release_f64", "working_directory": "external_clean_temp", "legacy_and_python_environment": "scrubbed"}, "historical_m5b_lane": "excluded_hidden_transform"}
    if document["oracle"] != expected_oracle:
        blockers.append("oracle_boundary_invalid")
    expected_acceptance = {"status": "specified_not_executed", "acceptance_ready": True, "result_status": "not_run", "observable": "discrete_voltage_gain_kernel_v_over_v", "probe": {"launched_voltage_samples_volts": [1.0, 0.0], "interpretation": "first_sample_one_volt_then_zero_periodic_dft_probe"}, "dft": {"fft_length": 400, "sample_interval_seconds": 2.5e-11, "forward_sign": "negative", "inverse_normalization": "one_over_n", "one_sided_completion": "hermitian"}, "alignment": "index_aligned_no_interpolation_no_shift", "kernel_compare": {"require_finite": True, "absolute_tolerance_v_per_v": 1.0e-9, "relative_tolerance": 1.0e-5}, "reproducibility": {"fresh_runs_required": 2, "require_exact_kernel_hash_match": True, "retained_report_fields": ["source_hash", "observer_identity", "environment_hash", "fft_length", "sample_interval_seconds", "kernel_hash", "max_abs_error", "max_rel_error", "worst_index", "conclusion"]}}
    if document["acceptance"] != expected_acceptance:
        blockers.append("acceptance_policy_invalid")
    if not isinstance(document["non_claims"], list) or not document["non_claims"] or not all(isinstance(item, str) and item for item in document["non_claims"]):
        blockers.append("non_claims_invalid")
    return {"valid": not blockers, "profile_id": "channel-s2p-channel-16ghz-3db-v1", "acceptance_ready": not blockers, "result_status": "not_run", "comparison_ready": False, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=ROOT / "docs" / "baselines" / "channel-s2p-matched-acceptance.v1.yaml")
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify_document(_load(args.contract), args.source_root)
    except (OSError, RuntimeError) as error:
        report = {"valid": False, "blockers": [str(error)]}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
