"""Verify the blocked ADS PRBSsrc source-only observation charter."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-ads-prbssrc-source-only-matched-load-charter.v1.yaml"
SCHEMA = "sipi.p3c-ads-prbssrc-source-only-matched-load-charter.v1"


class VerificationError(ValueError):
    pass


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("schema_invalid")
    if document.get("status") != "specified_pending_owner_topology_and_fixed_thevenin_mapping_confirmation":
        raise VerificationError("status_invalid")
    if document.get("authority") != {"actor": "user", "decision_ref": "user-continuation-2026-08-14", "scope": "external_ads_source_only_observation_charter_not_runtime_or_policy_change"}:
        raise VerificationError("authority_invalid")
    topology = document.get("topology")
    if not isinstance(topology, dict) or topology.get("components_exact") != ["PRBSsrc:TXP", "PRBSsrc:TXM", "R:TX_PLUS_MATCH", "R:TX_MINUS_MATCH", "Tran:TRAN"]:
        raise VerificationError("topology_invalid")
    if topology.get("forbidden_component_tokens") != ["SnP", "channel", "rxp", "rxm", "ami", "ibis", ".dll", "getwave", "ctspcie"] or topology.get("observation") != "V(txp)-V(txm)":
        raise VerificationError("topology_boundary")
    sources = topology.get("sources")
    if not isinstance(sources, dict) or sources.get("txp") != {"node": "txp", "vlow_volts": -0.5, "vhigh_volts": 0.5, "rout_ohms": 50.0} or sources.get("txm") != {"node": "txm", "vlow_volts": 0.5, "vhigh_volts": -0.5, "rout_ohms": 50.0}:
        raise VerificationError("source_levels")
    loads = topology.get("loads")
    expected_loads = {"tx_plus_match": {"node": "txp", "reference_node": "global_ground_0", "resistance_ohms": 50.0}, "tx_minus_match": {"node": "txm", "reference_node": "global_ground_0", "resistance_ohms": 50.0}}
    if loads != expected_loads:
        raise VerificationError("load_topology")
    mapping = document.get("fixed_diagnostic_mapping")
    if not isinstance(mapping, dict) or mapping.get("expected_ads_loaded_differential") != "0.5_times_product_projection" or mapping.get("gain_fit") != "prohibited":
        raise VerificationError("mapping_invalid")
    if any(mapping.get(key) != "prohibited" for key in ("alignment", "resampling", "delay_or_phase_shift", "dc_removal", "polarity_flip")):
        raise VerificationError("transform_gate")
    confirmation = document.get("owner_confirmation")
    if confirmation != {"topology_confirmed": False, "thevenin_half_scale_mapping_confirmed": False, "diagnostic_partition_confirmation": False, "external_ads_runner_authorized": False}:
        raise VerificationError("owner_confirmation_gate")
    expected_false = {"external_ads_source_only_matched_load_observed", "ads_prbssrc_strobe_semantics_observed", "right_continuous_projection_strict_diagnostic_evaluated", "product_source_policy_changed", "product_source_policy_admitted", "source_explains_full_channel_residual", "candidate_waveform_accepted", "causalization_policy_changed", "accepted_receiver", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != expected_false or any(admission[key] is not False for key in expected_false):
        raise VerificationError("admission_gate")
    if any(token in str(document).lower() for token in ("file://", "http://", "https://", "c:\\", "waveform: [", "samples: [")):
        raise VerificationError("evidence_leak")
    return {"valid": True, "owner_confirmation_pending": True, "external_runner_authorized": False, "release_admitted": False}


def main() -> int:
    try:
        result = verify_document(yaml.safe_load(PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_ads_prbssrc_source_only_matched_load_charter_failed:{error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
