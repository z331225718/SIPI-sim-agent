"""Verify that drifted selected-S4P observations remain historical and fail closed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-selected-s4p-historical-observation-source-drift.v1.yaml"
SCHEMA = "sipi.p3c-selected-s4p-historical-observation-source-drift.v1"


class VerificationError(ValueError):
    pass


def _run(relative: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", relative],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("historical_source_drift_schema_invalid")
    if document.get("status") != "historical_observations_source_drifted_current_truncation_chain_evidence_only":
        raise VerificationError("historical_source_drift_status_invalid")
    records = document.get("historical_records")
    expected_records = {
        "selected-static-custody-v2": "static_custody_evidence_product_source_drift",
        "selected-uniform-spectrum-v1": "uniform_spectrum_product_source_drift",
        "selected-raw-periodic-v1": "raw_periodic_product_source_drift",
        "selected-bounded-causality-v1": "causality_product_source_drift",
    }
    if not isinstance(records, list) or len(records) != 4:
        raise VerificationError("historical_source_drift_records_invalid")
    ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"id", "evidence", "verifier", "expected_error"} or not all(isinstance(record.get(key), str) and record[key] for key in record):
            raise VerificationError("historical_source_drift_record_shape_invalid")
        if record["id"] in ids or record["expected_error"] != expected_records.get(record["id"]) or not (ROOT / record["evidence"]).is_file() or not (ROOT / record["verifier"]).is_file():
            raise VerificationError("historical_source_drift_record_identity_invalid")
        ids.add(record["id"])
    successor = document.get("current_successor")
    expected_successor = {"evidence", "verifier", "required_status", "required_result"}
    if not isinstance(successor, dict) or set(successor) != expected_successor or successor.get("required_status") != "external_selected_s4p_truncation_observed_causal_fir_and_candidate_route_pending" or successor.get("required_result") != {"valid": True, "truncation_observed": True, "release_admitted": False} or not all(isinstance(successor.get(key), str) and successor[key] for key in ("evidence", "verifier")) or not (ROOT / successor["evidence"]).is_file() or not (ROOT / successor["verifier"]).is_file():
        raise VerificationError("historical_source_drift_successor_invalid")
    gates = document.get("gates")
    expected_gates = {"historical_records_rewritten": False, "historical_records_current": False, "current_selected_truncation_chain_observed": True, "causal_impulse_admitted": False, "delay_extraction_implemented": False, "passivity_repair_implemented": False, "linear_convolution_implemented": False, "candidate_waveform_generated": False, "external_reference_binding_evaluated": False, "candidate_metric_acceptance_evaluated": False, "accepted_receiver": False, "release_ledger_promoted": False}
    if gates != expected_gates:
        raise VerificationError("historical_source_drift_gate_relaxed")
    claims = document.get("non_claims")
    if not isinstance(claims, list) or len(claims) != 2:
        raise VerificationError("historical_source_drift_nonclaim_invalid")
    return {"valid": True, "historical_record_count": len(records), "release_admitted": False}


def verify_runtime(document: dict[str, object]) -> None:
    records = document["historical_records"]
    assert isinstance(records, list)
    for record in records:
        assert isinstance(record, dict)
        completed = _run(record["verifier"])
        if completed.returncode != 1 or completed.stdout or completed.stderr.strip().split(":")[-1] != record["expected_error"]:
            raise VerificationError("historical_source_drift_not_precisely_fail_closed")
    successor = document["current_successor"]
    assert isinstance(successor, dict)
    completed = _run(successor["verifier"])
    if completed.returncode != 0 or completed.stderr or completed.stdout.strip() != "{'valid': True, 'truncation_observed': True, 'release_admitted': False}":
        raise VerificationError("historical_source_drift_successor_not_current")


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_runtime(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_s4p_historical_source_drift_failed:{error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
