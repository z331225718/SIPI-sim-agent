"""Verify the P3B-02 owner decision against the current bypass-only surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/baselines/p3b-02-named-fir-prerequisite.v2.yaml"
SCHEMA = "sipi.p3b-02.named-fir-prerequisite.v2"
PREDECESSOR = ROOT / "docs/baselines/p3b-02-equalizer-semantics-gap.v1.yaml"
PREDECESSOR_SHA256 = "636f7d9d8b7ae65a5c987173b93e07166ef55a21ac549191290e84b885afbc4b"
OWNER_DECISION = ROOT / "docs/baselines/owner-decision-reconciliation.v2.yaml"
OWNER_DECISION_SHA256 = "4e9109e3adde405f3c6529bd6d09f27828a0cc56959eeb024b5600865bbba1f0"
WIRE_SCHEMA = ROOT / "crates/sipi-contracts/schemas/sipi.link-plan.v1.schema.json"
CONTRACT_SOURCE = ROOT / "crates/sipi-contracts/src/lib.rs"
SINGLETON_GATE = ROOT / "tools/verify_p3b_02_link_kernel_singleton.py"
FIR_SOURCE = ROOT / "crates/sipi-link/src/rx_named_fir_v1.rs"
FIR_SOURCE_SHA256 = "30d87038569cc5277c994f4309e1702ba274cb1c56df699bcf14cf468b949e9e"


class GapEvidenceError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = yaml.safe_load(raw) if yaml is not None else json.loads(raw)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise GapEvidenceError("record_invalid") from error
    if not isinstance(value, dict):
        raise GapEvidenceError("record_invalid")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise GapEvidenceError("owner_decision_missing") from error


def _expected_owner_decision() -> dict[str, Any]:
    return {
        "id": "P3B-02",
        "answer": "A",
        "receiver_chain": ["RX CTLE", "RX FFE"],
        "stage_order": "RX CTLE->RX FFE",
        "stage_selection": "explicit_optional_per_simulation",
        "bypass": "explicit_per_stage",
        "auto_tuning": "prohibited",
        "silent_default": "prohibited",
        "v1_boundary": "bypass_only_unchanged",
        "future_extension": "additive_profile_only",
    }


def _expected_missing_semantics() -> dict[str, list[str]]:
    return {
        "ctle": [
            "transfer_function_representation_and_units",
            "normalization_reference_and_frequency_or_time_domain_boundary",
            "state_initialization_and_update_semantics",
            "bounds_numeric_policy_and_failure_taxonomy",
        ],
        "ffe": [
            "tap_order_and_cursor_convention",
            "tap_units_sign_and_initial_state",
            "sample_or_ui_domain_and_boundary_handling",
            "bounds_numeric_policy_and_failure_taxonomy",
        ],
        "shared": [
            "stage_output_binding_and_timebase_contract",
            "independent_reference_and_compare_tolerance",
            "runtime_provenance_and_publication_boundary",
        ],
    }


def _stage_kinds(schema: dict[str, Any], stage_name: str) -> list[str]:
    try:
        choices = schema["$defs"][stage_name]["oneOf"]
        return [choice["properties"]["kind"]["const"] for choice in choices]
    except (KeyError, IndexError, TypeError) as error:
        raise GapEvidenceError(f"wire_{stage_name}_shape_invalid") from error


def _enum_variants(source: str, enum_name: str) -> list[str]:
    match = re.search(
        rf"pub\s+enum\s+{re.escape(enum_name)}\s*\{{(?P<body>.*?)\}}",
        source,
        re.DOTALL,
    )
    if match is None:
        raise GapEvidenceError(f"rust_{enum_name}_missing")
    return re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*,", match.group("body"), re.MULTILINE)


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema",
        "status",
        "predecessor",
        "authority",
        "owner_decision",
        "current_surface",
        "missing_semantics",
        "decision",
        "admission",
        "non_claims",
    }
    if set(document) != required or document["schema"] != SCHEMA:
        raise GapEvidenceError("record_shape_invalid")
    if document["status"] != "blocked_missing_transfer_profile_semantics":
        raise GapEvidenceError("record_status_invalid")
    if document["predecessor"] != {
        "path": "docs/baselines/p3b-02-equalizer-semantics-gap.v1.yaml",
        "sha256": PREDECESSOR_SHA256,
        "unchanged": True,
    }:
        raise GapEvidenceError("predecessor_binding_invalid")

    authority = document["authority"]
    if authority != {
        "actor": "project",
        "decision_ref": "docs/baselines/owner-decision-reconciliation.v2.yaml",
        "decision_sha256": OWNER_DECISION_SHA256,
        "scope": "owner-decision-boundary-to-current-bypass-only-link-surface",
    }:
        raise GapEvidenceError("authority_invalid")
    if document["owner_decision"] != _expected_owner_decision():
        raise GapEvidenceError("owner_decision_invalid")

    surface = document["current_surface"]
    if surface != {
        "wire_schema": {
            "path": "crates/sipi-contracts/schemas/sipi.link-plan.v1.schema.json",
            "ctle_kinds": ["bypass"],
            "ffe_kinds": ["bypass"],
        },
        "rust_contract": {
            "path": "crates/sipi-contracts/src/lib.rs",
            "ctle_variants": ["Bypass"],
            "ffe_variants": ["Bypass"],
        },
        "singleton_gate": "tools/verify_p3b_02_link_kernel_singleton.py",
        "runtime_admission": {
            "named_fir_prerequisite": {
                "path": "crates/sipi-link/src/rx_named_fir_v1.rs",
                "source_sha256": FIR_SOURCE_SHA256,
                "policy": "sipi.p3b-02.rx-named-fir-prerequisite-v1",
                "stage_order": "ctle_named_slot->ffe_named_slot",
                "choices": ["bypass", "explicit_causal_fir"],
                "semantics": "finite_sample_spaced_taps_tap0_zero_prehistory_full_linear",
            },
            "ctle_runtime": False,
            "ffe_runtime": False,
            "profile_acceptance": False,
        },
    }:
        raise GapEvidenceError("current_surface_invalid")

    if document["missing_semantics"] != _expected_missing_semantics():
        raise GapEvidenceError("missing_semantics_invalid")
    if document["decision"] != {
        "selected_profile": "none",
        "implementation_status": "named_fir_prerequisite_only_no_product_equalizer_profile",
        "reason": [
            "owner decision fixes chain and selection policy but not executable CTLE or FFE equations",
            "current link-plan schema and Rust contract admit bypass only",
            "named FIR slots prove explicit ordering and bounded composition without claiming CTLE or FFE transfer semantics",
        ],
    }:
        raise GapEvidenceError("decision_invalid")
    if document["admission"] != {
        "product_equalizer_implemented": False,
        "external_source_promoted": False,
        "acceptance_promoted": False,
        "release_promoted": False,
    }:
        raise GapEvidenceError("admission_invalid")
    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or len(non_claims) != 5 or any(not isinstance(item, str) for item in non_claims):
        raise GapEvidenceError("non_claims_invalid")
    return {"valid": True, "status": document["status"], "missing_groups": len(document["missing_semantics"])}


def verify(root: Path = ROOT) -> dict[str, Any]:
    document = _load(root / RECORD.relative_to(ROOT))
    result = validate_document(document)
    if _sha256(root / PREDECESSOR.relative_to(ROOT)) != PREDECESSOR_SHA256:
        raise GapEvidenceError("predecessor_hash_drift")
    owner_path = root / OWNER_DECISION.relative_to(ROOT)
    if _sha256(owner_path) != OWNER_DECISION_SHA256:
        raise GapEvidenceError("owner_decision_source_drift")
    try:
        schema = json.loads((root / WIRE_SCHEMA.relative_to(ROOT)).read_text(encoding="utf-8"))
        contract = (root / CONTRACT_SOURCE.relative_to(ROOT)).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GapEvidenceError("live_surface_missing") from error
    if _stage_kinds(schema, "WireCtleStageV1") != ["bypass"]:
        raise GapEvidenceError("wire_ctle_non_bypass_admitted")
    if _stage_kinds(schema, "WireFfeStageV1") != ["bypass"]:
        raise GapEvidenceError("wire_ffe_non_bypass_admitted")
    if _enum_variants(contract, "WireCtleStageV1") != ["Bypass"]:
        raise GapEvidenceError("rust_wire_ctle_non_bypass_admitted")
    if _enum_variants(contract, "WireFfeStageV1") != ["Bypass"]:
        raise GapEvidenceError("rust_wire_ffe_non_bypass_admitted")
    if not (root / SINGLETON_GATE.relative_to(ROOT)).is_file():
        raise GapEvidenceError("singleton_gate_missing")
    fir_source = root / FIR_SOURCE.relative_to(ROOT)
    if _sha256(fir_source) != FIR_SOURCE_SHA256:
        raise GapEvidenceError("named_fir_source_drift")
    try:
        fir_text = fir_source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise GapEvidenceError("named_fir_source_missing") from error
    for marker in (
        "RxNamedFirStageV1",
        "ExplicitCausalFir",
        "convolve_causal_fir_v1",
        "ctle_named_slot",
        "ffe_named_slot",
    ):
        if marker not in fir_text:
            raise GapEvidenceError("named_fir_marker_missing")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps({"schema": SCHEMA, **verify(args.root)}, sort_keys=True))
        return 0
    except (GapEvidenceError, OSError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
