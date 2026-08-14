"""Verify that the drifted 04ag waveform-only observation remains historical."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-external-ads-selected-highloss-waveform-only-historical-source-drift.v1.yaml"
SCHEMA = "sipi.p3c-external-ads-selected-highloss-waveform-only-historical-source-drift.v1"
HISTORICAL_EVIDENCE = "docs/baselines/p3c-external-ads-selected-highloss-waveform-only-observation-evidence.v3.yaml"
HISTORICAL_VERIFIER = "tools/verify_p3c_external_ads_selected_highloss_waveform_only_observation_evidence.py"
EXPECTED_ERROR = "waveform_only_product_source_drift"
HISTORICAL_SHA256 = "bbd3afa54e57aa64fbd48878074460cc5137073fcbfa9c76a4b29c9eda705a63"


class VerificationError(ValueError):
    pass


def verify_document(document: object) -> dict[str, object]:
    required = {"schema", "status", "authority", "historical_record", "current_state", "gates", "blockers", "non_claims"}
    if not isinstance(document, dict) or set(document) != required or document.get("schema") != SCHEMA:
        raise VerificationError("waveform_only_historical_drift_shape")
    if document.get("status") != "historical_waveform_only_observation_source_drifted_current_external_binding_unavailable":
        raise VerificationError("waveform_only_historical_drift_status")
    if document.get("authority") != {
        "actor": "project",
        "decision_ref": "historical-evidence-source-drift-preservation",
        "scope": "preserve_the_04ag_selected_highloss_waveform_only_observation_without_reclassification_or_gate_relaxation",
    }:
        raise VerificationError("waveform_only_historical_drift_authority")
    if document.get("historical_record") != {
        "id": "selected-highloss-waveform-only-v3",
        "evidence": HISTORICAL_EVIDENCE,
        "content_sha256": HISTORICAL_SHA256,
        "verifier": HISTORICAL_VERIFIER,
        "expected_error": EXPECTED_ERROR,
    }:
        raise VerificationError("waveform_only_historical_drift_record")
    if hashlib.sha256((ROOT / HISTORICAL_EVIDENCE).read_bytes()).hexdigest() != HISTORICAL_SHA256:
        raise VerificationError("waveform_only_historical_evidence_rewritten")
    if document.get("current_state") != {
        "current_external_observation_available": False,
        "current_external_reference_binding_evaluated": False,
        "current_waveform_nrmse_evaluated": False,
        "current_selected_highloss_waveform_only_profile_accepted": False,
        "reconciliation_only": True,
    }:
        raise VerificationError("waveform_only_historical_drift_current_state")
    expected_gates = {
        "historical_record_rewritten": False,
        "historical_record_current": False,
        "selected_highloss_waveform_only_contract_ready": True,
        "current_external_reference_binding_evaluated": False,
        "current_waveform_nrmse_evaluated": False,
        "sampled_eye_evaluated": False,
        "crossing_tie_evaluated": False,
        "selected_highloss_waveform_only_profile_accepted": False,
        "accepted_receiver": False,
        "acceptance_ready": False,
        "promotion_eligible": False,
        "release_ledger_promoted": False,
    }
    if document.get("gates") != expected_gates:
        raise VerificationError("waveform_only_historical_drift_gate_relaxed")
    expected_blockers = {
        "waveform_only_product_source_drift",
        "current_external_waveform_only_observation_missing",
        "selected_waveform_nrmse_exceeds_fixed_one_percent_limit_historically",
        "accepted_receiver_stage_missing",
        "statistical_eye_contour_semantics_missing",
    }
    if not isinstance(document.get("blockers"), list) or set(document["blockers"]) != expected_blockers:
        raise VerificationError("waveform_only_historical_drift_blockers")
    claims = document.get("non_claims")
    if not isinstance(claims, list) or len(claims) != 3 or any(not isinstance(claim, str) or not claim for claim in claims):
        raise VerificationError("waveform_only_historical_drift_nonclaims")
    if any(token in str(document).lower() for token in ("\\\\", "file://", "http://", "https://", "samples: [", "waveform: [")):
        raise VerificationError("waveform_only_historical_drift_leak")
    return {"valid": True, "historical_observation_current": False, "current_external_binding_evaluated": False, "release_admitted": False}


def verify_runtime() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", HISTORICAL_VERIFIER],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    expected = f"external_ads_selected_highloss_waveform_only_observation_failed:{EXPECTED_ERROR}"
    if completed.returncode != 1 or completed.stderr or completed.stdout.strip() != expected:
        raise VerificationError("waveform_only_historical_drift_not_precisely_fail_closed")


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_runtime()
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"waveform_only_historical_source_drift_failed:{error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
