"""Verify the selected external-only IBIS input static acceptance charter."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p4a-ibis-input-typ-static-acceptance.v1.yaml"
SCHEMA = "sipi.p4a-ibis-input-typ-static-acceptance.v1"
ASSET_SHA256 = "46c53a49a31dea27769f0dddddadea72f03f1f956fb8e60aeaa24f83a7201b95"
SELECTOR_SHA256 = "0be75aff11736ab3fee529275984551c241433d189ba1a21bad1b0e0e70fd2ff"


def _exact(value: object, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("manifest_shape_invalid")
    return value


def _sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def validate(document: object) -> dict:
    root = _exact(document, {"schema", "status", "profile", "stimulus", "observable", "comparison", "non_claims"})
    if root["schema"] != SCHEMA or root["status"] != "required_pending_i_v_compare":
        raise ValueError("manifest_status_invalid")
    profile = _exact(root["profile"], {"id", "required_by", "boundary", "source", "terminal_binding", "corner", "model_scope", "package_scope", "vt_ramp_scope"})
    source = _exact(profile["source"], {"canonical_url", "content_sha256", "byte_length", "selector_utf8_sha256"})
    if profile["id"] != "ibis-org-sample1-input-typ-static-v2" or not isinstance(profile["required_by"], str) or not profile["required_by"] or profile["boundary"] != "external_oracle_only":
        raise ValueError("profile_selection_invalid")
    if source != {"canonical_url": "https://ibis.org/xml/sample1/sample1%28original%29.ibs", "content_sha256": ASSET_SHA256, "byte_length": 406532, "selector_utf8_sha256": SELECTOR_SHA256} or not _sha256(source["content_sha256"]) or not _sha256(source["selector_utf8_sha256"]):
        raise ValueError("external_identity_invalid")
    if profile["terminal_binding"] != {"kind": "single_ended", "signal": "sig", "reference": "ref", "reference_default": "forbidden"} or profile["corner"] != "typical" or profile["model_scope"] != "input_static_clamp" or profile["package_scope"] != "not_in_this_profile" or profile["vt_ramp_scope"] != "not_applicable_to_input_static_profile":
        raise ValueError("profile_scope_invalid")
    stimulus = _exact(root["stimulus"], {"kind", "voltage_v", "timebase"})
    if stimulus != {"kind": "static_voltage_sweep", "voltage_v": [-1.0, 0.0, 0.8, 2.0, 3.3, 4.0], "timebase": "none"}:
        raise ValueError("stimulus_invalid")
    observable = _exact(root["observable"], {"id", "current_direction", "components", "c_comp_contribution"})
    if observable != {"id": "sig_to_ref_shunt_current_a", "current_direction": "positive_into_sig", "components": ["gnd_clamp", "power_clamp"], "c_comp_contribution": "zero_at_dc"}:
        raise ValueError("observable_invalid")
    comparison = _exact(root["comparison"], {"alignment", "interpolation", "out_of_domain", "absolute_tolerance_a", "relative_tolerance", "environment"})
    if comparison != {"alignment": "index_exact", "interpolation": "linear_within_table_domain", "out_of_domain": "reject", "absolute_tolerance_a": 1.0e-12, "relative_tolerance": 1.0e-9, "environment": "windows_x86_64_external_observer"}:
        raise ValueError("comparison_invalid")
    if not isinstance(root["non_claims"], list) or len(root["non_claims"]) != 3 or not all(isinstance(item, str) and item for item in root["non_claims"]):
        raise ValueError("non_claims_invalid")
    return {"valid": True, "profile_id": profile["id"], "status": root["status"], "asset_sha256": source["content_sha256"], "charter_sha256": hashlib.sha256(json.dumps(root, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT)
    args = parser.parse_args()
    try:
        if yaml is None:
            raise RuntimeError("pyyaml is unavailable")
        result = validate(yaml.safe_load(args.manifest.read_text(encoding="utf-8")))
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
