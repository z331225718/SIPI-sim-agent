"""Verify the P2-06 stage-compare coverage record against live evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p2-06.stage-compare-coverage.v1"
RECORD = ROOT / "docs" / "baselines" / "p2-06-stage-compare-coverage.v1.yaml"

REQUIRED_STAGES = frozenset({"parsed_circuit", "time_grid", "waveforms", "measurements"})
EXPECTED_CURRENT_EVIDENCE = {
    "archive_commit": "538b5dd08f734e5558b1179083c3d24a95aba02f",
    "oracle_commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5",
    "external_report_sha256": "854e34fd85bc5cef8018fb4387c6ecb8ecbb102dda9f14b872279bc0b05b84ce",
    "replay_count": 2,
}
CURRENT_EVIDENCE_AUDIT = "docs/baselines/audits/2026-08-15-p2-fixed-tran-current-evidence-rebinding-v4.md"


class StageCoverageError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if yaml is not None:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise StageCoverageError("invalid_coverage_document") from error
    else:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StageCoverageError("invalid_coverage_document") from error
    if not isinstance(value, dict):
        raise StageCoverageError("invalid_coverage_document")
    return value


def git_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    return completed.returncode == 0


def validate(record: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    required = {"schema", "status", "scope", "stages", "current_evidence", "historical_evidence", "non_claims"}
    if set(record) != required or record["schema"] != SCHEMA:
        raise StageCoverageError("coverage_schema_invalid")
    if record["status"] != "provisional":
        raise StageCoverageError("coverage_status_invalid")
    if record["scope"] != "current_product_surface_fixed_tran_rc_pulse":
        raise StageCoverageError("coverage_scope_invalid")

    stages = record["stages"]
    if set(stages) != REQUIRED_STAGES:
        raise StageCoverageError("coverage_stages_invalid")
    if stages["parsed_circuit"]["status"] != "not_applicable_current_surface":
        raise StageCoverageError("coverage_parsed_circuit_invalid")
    if stages["time_grid"]["status"] != "covered" or not stages["time_grid"].get("evidence"):
        raise StageCoverageError("coverage_time_grid_invalid")
    if stages["waveforms"]["status"] != "covered" or stages["waveforms"].get("observables") != ["time", "v(in)", "v(out)"]:
        raise StageCoverageError("coverage_waveforms_invalid")
    if stages["measurements"]["status"] != "not_implemented":
        raise StageCoverageError("coverage_measurements_invalid")

    current = record["current_evidence"]
    for key, expected in EXPECTED_CURRENT_EVIDENCE.items():
        if current.get(key) != expected:
            raise StageCoverageError(f"coverage_current_evidence_{key}_invalid")
    if not git_tracked(CURRENT_EVIDENCE_AUDIT) or not (root / CURRENT_EVIDENCE_AUDIT).is_file():
        raise StageCoverageError("coverage_current_evidence_audit_missing")

    historical = record["historical_evidence"]
    if not isinstance(historical, list) or not historical:
        raise StageCoverageError("coverage_historical_invalid")
    drift_seen = False
    for entry in historical:
        if entry.get("status") == "source_drift_historical":
            drift_seen = True
    if not drift_seen:
        raise StageCoverageError("coverage_historical_drift_missing")

    non_claims = record["non_claims"]
    if not isinstance(non_claims, list) or not non_claims or any(not isinstance(v, str) for v in non_claims):
        raise StageCoverageError("coverage_non_claims_invalid")

    return {"valid": True, "stages": len(REQUIRED_STAGES)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        record = load_json(RECORD)
        result = validate(record, ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except StageCoverageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
