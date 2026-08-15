"""Verify that drifted selected sensitivity observations remain historical."""
from __future__ import annotations
import hashlib
import subprocess
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-selected-sensitivity-historical-source-drift.v1.yaml"
SCHEMA = "sipi.p3c.selected-sensitivity-historical-source-drift.v1"
EXPECTED = {
    "selected-oob-zero-extension-v1": ("docs/baselines/p3c-selected-oob-zero-extension-sensitivity-observation-evidence.v1.yaml", "0d0b48f31938a42fa3b96b6123cbff61dfcccb586d456ea2db626754d89e8923", "tools/verify_p3c_selected_oob_zero_extension_sensitivity_observation_evidence.py", "oob_product_source_drift"),
    "selected-truncation-sensitivity-v1": ("docs/baselines/p3c-selected-truncation-waveform-sensitivity-observation-evidence.v1.yaml", "4f33480a5fe50cb1828e9c60506d9edb5a97efa9ff4026ae43c5c5cf4dbbaaec", "tools/verify_p3c_selected_truncation_waveform_sensitivity_observation_evidence.py", "truncation_sensitivity_product_source_drift"),
}
GATES = {"historical_records_rewritten": False, "historical_records_current": False, "current_oob_sensitivity_available": False, "current_truncation_sensitivity_available": False, "candidate_waveform_generated": False, "candidate_metric_acceptance_evaluated": False, "causal_impulse_admitted": False, "passivity_repair_implemented": False, "accepted_receiver": False, "release_ledger_promoted": False}

class VerificationError(ValueError): pass

def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "historical_oob_and_truncation_sensitivity_observations_source_drifted": raise VerificationError("sensitivity_historical_schema_invalid")
    records = document.get("historical_records")
    if not isinstance(records, list) or len(records) != 2 or document.get("gates") != GATES: raise VerificationError("sensitivity_historical_gate_invalid")
    for record in records:
        if not isinstance(record, dict) or set(record) != {"id", "evidence", "evidence_sha256", "verifier", "expected_error"}: raise VerificationError("sensitivity_historical_record_invalid")
        expected = EXPECTED.get(record["id"])
        if expected is None or tuple(record[key] for key in ("evidence", "evidence_sha256", "verifier", "expected_error")) != expected: raise VerificationError("sensitivity_historical_identity_invalid")
        if hashlib.sha256((ROOT / record["evidence"]).read_bytes()).hexdigest() != record["evidence_sha256"]: raise VerificationError("sensitivity_historical_hash_invalid")
    if not isinstance(document.get("non_claims"), list) or len(document["non_claims"]) != 2: raise VerificationError("sensitivity_historical_nonclaim_invalid")
    return {"valid": True, "historical_record_count": 2, "current_evidence_available": False}

def verify_runtime(document: dict[str, object]) -> None:
    for record in document["historical_records"]:
        result = subprocess.run([sys.executable, "-B", record["verifier"]], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 1 or result.stderr or result.stdout.strip().split(":")[-1] != record["expected_error"]: raise VerificationError("sensitivity_historical_not_precisely_drifted")

if __name__ == "__main__":
    document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8")); result = verify_document(document); verify_runtime(document); print(result)
