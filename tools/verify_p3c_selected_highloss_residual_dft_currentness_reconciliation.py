"""Verify that the selected residual-DFT record is historical after source drift."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/p3c-selected-highloss-residual-dft-currentness-reconciliation.v1.yaml"
HISTORICAL = ROOT / "docs/baselines/p3c-selected-highloss-residual-dft-v2-current-head-observation-evidence.v1.yaml"
HISTORICAL_VERIFIER = ROOT / "tools/verify_p3c_selected_highloss_residual_dft_v2_current_head_observation_evidence.py"
SCHEMA = "sipi.p3c-selected-highloss-residual-dft-currentness-reconciliation.v1"
HISTORICAL_SHA256 = "ed463c99d4beadfb6409b9146b7a5d3c669e609a42a77dc213bb64b02a1b1328"
VERIFIER_SHA256 = "c4b2dc8ec7b0cbe996e34c7f05fbf55b86fc05776ca87c59376036195e1abc13"
EXPECTED_OUTPUT = "p3c_selected_highloss_residual_dft_current_head_evidence_failed:source_drift"


class ReconciliationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReconciliationError("document_not_mapping")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(document: dict[str, Any] | None = None, *, execute: bool = True) -> dict[str, Any]:
    document = _load(DOCUMENT) if document is None else document
    if set(document) != {
        "schema", "status", "historical_record", "historical_verifier", "state",
        "non_claims", "audit_ref",
    } or document.get("schema") != SCHEMA:
        raise ReconciliationError("document_shape_invalid")
    if document.get("status") != "historical_observation_source_drifted_current_replay_missing":
        raise ReconciliationError("status_invalid")
    if document.get("historical_record") != {
        "path": "docs/baselines/p3c-selected-highloss-residual-dft-v2-current-head-observation-evidence.v1.yaml",
        "byte_length": 7045,
        "sha256": HISTORICAL_SHA256,
        "clean_archive_commit": "97b0f271abcb7df02a3a9b259c4dafee86f3a783",
    } or HISTORICAL.stat().st_size != 7045 or _sha256(HISTORICAL) != HISTORICAL_SHA256:
        raise ReconciliationError("historical_record_binding_invalid")
    if document.get("historical_verifier") != {
        "path": "tools/verify_p3c_selected_highloss_residual_dft_v2_current_head_observation_evidence.py",
        "sha256": VERIFIER_SHA256,
        "expected_exit_code": 1,
        "expected_output": EXPECTED_OUTPUT,
    } or _sha256(HISTORICAL_VERIFIER) != VERIFIER_SHA256:
        raise ReconciliationError("historical_verifier_binding_invalid")
    expected_state = {
        "historical_observation_preserved": True,
        "current_product_inventory_matches": False,
        "current_external_replay_available": False,
        "current_candidate_baseline_reproduced": False,
        "current_residual_spectral_distribution_observed": False,
        "current_parseval_integrity_verified": False,
        "selected_highloss_waveform_only_profile_accepted": False,
        "acceptance_ready": False,
        "release_ledger_promoted": False,
    }
    if document.get("state") != expected_state:
        raise ReconciliationError("state_promotion_or_drift")
    if set(document.get("non_claims", [])) != {
        "historical_nrmse_and_band_summaries_are_not_current_candidate_evidence",
        "source_drift_does_not_invalidate_the_historical_observation",
        "no_replay_alignment_fit_tolerance_or_policy_change_performed",
        "no_receiver_profile_or_release_admission",
    }:
        raise ReconciliationError("non_claims_invalid")
    audit_ref = document.get("audit_ref")
    if audit_ref != "docs/baselines/audits/2026-08-21-p3c-residual-dft-currentness-reconciliation.md" or not (ROOT / audit_ref).is_file():
        raise ReconciliationError("audit_ref_invalid")
    if execute:
        result = subprocess.run(
            [sys.executable, "-B", str(HISTORICAL_VERIFIER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if result.returncode != 1 or output != EXPECTED_OUTPUT:
            raise ReconciliationError("historical_source_drift_result_invalid")
    return {"schema": SCHEMA, "valid": True, "historical": True, "current_replay": False}


def main() -> int:
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ReconciliationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
