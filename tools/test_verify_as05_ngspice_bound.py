"""Mutation tests for the exact AS-05 ngspice scoped-observation gate."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_as05_ngspice_bound as runner  # noqa: E402
import verify_as05_ngspice_bound as verifier  # noqa: E402

COMMIT = "a" * 40
TREE = "b" * 40
ARCHIVE = "c" * 64
UPSTREAM_ARCHIVE = "d" * 64
SOLVER = "e" * 64


def identity(role: str, digest: str) -> dict:
    return {"role": role, "basename": f"{role}.exe", "path_redacted": True, "file_sha256": digest, "file_bytes": 1, "version_exit_code": 0, "version_output_sha256": "f" * 64, "version_output_bytes": 1, "timeout_seconds": 10, "max_output_bytes": 65536}


def case(case_id: str, kind: str, waveform: bool) -> dict:
    artifacts = [{"path": "case", "bytes": 1, "sha256": "1" * 64}, {"path": "stdout.log", "bytes": 1, "sha256": "2" * 64}, {"path": "stderr.log", "bytes": 1, "sha256": "3" * 64}]
    if waveform:
        artifacts.append({"path": "waveform.csv", "bytes": 1, "sha256": "4" * 64})
    measurements = [{"name": "m_rms", "value": 0.5}]
    requested = {"probes": ["V(OUT)"], "measures": [{"analysis": "tran", "name": "M_RMS", "operation": "find", "target": "V(OUT)", "raw": ".MEASURE TRAN M_RMS FIND V(OUT) AT=0"}]} if waveform else {"probes": [], "measures": [{"analysis": "tran", "name": "M_ONLY", "operation": "find", "target": "V(OUT)", "raw": ".MEASURE TRAN M_ONLY FIND V(OUT) AT=0"}]}
    if not waveform:
        measurements = [{"name": "m_only", "value": 0.5}]
    fixture = next(item for item in runner.FIXTURES if item[0] == case_id)
    consumed_input = {"path": f"fixtures/{case_id}.sp", "bytes": len(fixture[2].encode("ascii")), "sha256": hashlib.sha256(fixture[2].encode("ascii")).hexdigest()}
    return {"id": case_id, "kind": kind, "returncode": 0, "consumed_input": consumed_input, "cli": {"stdout_bytes": 1, "stdout_sha256": "5" * 64, "stderr_bytes": 1, "stderr_sha256": "6" * 64}, "summary": {"path": f"{case_id}/run_summary.json", "bytes": 1, "sha256": "7" * 64, "ok": True, "backend": "ngspice", "external_runtime_sha256": SOLVER, "output_contract": {"normalizer": {"upstream_path": "src/agent_spice/hspice/measure.py::normalize_outputs", "upstream_sha256": verifier.MEASURE_SOURCE_SHA256}, "requested": requested, "returned": {"waveform_rows": 1 if waveform else 0, "measurements": measurements}, "result_kind": "ngspice_print_table_observation", "verification": "external_solver_not_verified", "caller_input_attestation": "caller_input_unattested"}, "measurements": measurements, "waveform_rows": 1 if waveform else 0, "artifacts": artifacts}, "run_report": {"path": f"{case_id}/run_report.json", "bytes": 1, "sha256": "8" * 64, "status": "compatible", "backend": "ngspice", "execute": True}, "waveform": {"present": waveform, "path": "waveform.csv" if waveform else None, "bytes": 1 if waveform else 0, "sha256": "4" * 64 if waveform else None}}


def valid_document() -> dict:
    fixtures = [{"id": item[0], "kind": item[1], "generated_by_runner": runner.FIXTURE_GENERATOR, "path": f"fixtures/{item[0]}.sp", "bytes": len(item[2].encode("ascii")), "sha256": hashlib.sha256(item[2].encode("ascii")).hexdigest()} for item in runner.FIXTURES]
    solver = identity("ngspice", SOLVER) | {"caller_sha256": SOLVER, "pre_file_sha256": SOLVER, "post_file_sha256": SOLVER, "pre_file_bytes": 1, "post_file_bytes": 1, "pre_basename": "ngspice.exe", "post_basename": "ngspice.exe"}
    return {"schema": "sipi.as-05-ngspice-scoped-observation.v2-prep", "status": "scoped_external_runtime_observation_open", "scope": {"external_solver_not_verified": True, "numeric_parity": False, "parity_claim": False, "as05_row_closed": False, "release": False, "environment_injection_not_fully_excluded": True}, "run_id": "run-01", "fresh_run_nonce": "0" * 64, "candidate": {"commit": COMMIT, "tree": TREE, "archive_sha256": ARCHIVE}, "upstream": {"commit": runner.UPSTREAM_COMMIT, "tree": runner.UPSTREAM_TREE, "archive_sha256": UPSTREAM_ARCHIVE}, "runner": {"path": "tools/run_as05_ngspice_bound.py", "sha256": "1" * 64}, "toolchain": {role: identity(role, "2" * 64) for role in ("git", "cargo", "rustc", "python")}, "build": {"exit_code": 0, "stdout_bytes": 1, "stdout_sha256": "3" * 64, "stderr_bytes": 1, "stderr_sha256": "4" * 64, "binary_path_redacted": True, "binary_bytes": 1, "binary_sha256": "5" * 64, "offline": True, "locked": True, "target_dir_redacted": True, "rustc_env_identity": "2" * 64, "wrapper_policy": "RUSTC_WRAPPER_RUSTC_WORKSPACE_WRAPPER_CARGO_BUILD_RUSTC_WRAPPER_cleared"}, "solver": solver, "fixtures": fixtures, "cases": [case("uppercase_tran", "uppercase_tran_v1", True), case("measure_only", "measure_only_v1", False)], "path_policy": "path_free_report_create_new_scoped_external_observation_no_parity_no_release"}


class VerifyAs05NgspiceBoundTests(unittest.TestCase):
    def check(self, document: dict, valid: bool = False) -> None:
        payload = json.dumps(document, indent=2, sort_keys=True).encode() + b"\n"
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as report:
            report.write(payload)
            report_path = Path(report.name)
        try:
            result = verifier.verify(document, candidate_commit=COMMIT, candidate_tree=TREE, candidate_archive_sha256=ARCHIVE, upstream_archive_sha256=UPSTREAM_ARCHIVE, solver_sha256=SOLVER, expected_runner_sha256="1" * 64, expected_report_sha256=hashlib.sha256(payload).hexdigest(), report_path=report_path)
        finally:
            report_path.unlink()
        self.assertEqual(result["valid"], valid, result)

    def test_exact_shape(self) -> None:
        self.check(valid_document(), True)

    def test_extra_top_level_claim_rejected(self) -> None:
        document = valid_document()
        document["parity_claim"] = True
        self.check(document)

    def test_runner_sha_drift_rejected(self) -> None:
        document = valid_document()
        document["runner"]["sha256"] = "0" * 64
        self.check(document)

    def test_release_path_policy_rejected(self) -> None:
        document = valid_document()
        document["path_policy"] = "release_allowed"
        self.check(document)

    def test_version_output_budget_rejected(self) -> None:
        document = valid_document()
        document["toolchain"]["git"]["version_output_bytes"] = 65537
        document["solver"]["version_output_bytes"] = 65537
        self.check(document)

    def test_bounded_file_budget_rejected(self) -> None:
        document = valid_document()
        document["toolchain"]["git"]["file_bytes"] = 268435457
        document["solver"]["file_bytes"] = 268435457
        document["solver"]["pre_file_bytes"] = 268435457
        document["solver"]["post_file_bytes"] = 268435457
        document["build"]["binary_bytes"] = 268435457
        self.check(document)

    def test_extra_nested_tool_key_rejected(self) -> None:
        document = valid_document()
        document["toolchain"]["cargo"]["resolved_path"] = "C:/tmp/cargo.exe"
        self.check(document)

    def test_upstream_archive_drift_rejected(self) -> None:
        document = valid_document()
        document["upstream"]["archive_sha256"] = "0" * 64
        self.check(document)

    def test_solver_pre_post_drift_rejected(self) -> None:
        document = valid_document()
        document["solver"]["post_file_sha256"] = "0" * 64
        self.check(document)

    def test_case_order_drift_rejected(self) -> None:
        document = valid_document()
        document["cases"].reverse()
        self.check(document)

    def test_artifact_set_drift_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["artifacts"].pop()
        self.check(document)

    def test_report_path_leak_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["path"] = r"C:\tmp\run_summary.json"
        self.check(document)

    def test_drive_relative_path_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["path"] = "C:tmp/run_summary.json"
        self.check(document)

    def test_nonfinite_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["measurements"] = [math.nan]
        self.check(document)

    def test_output_contract_extra_key_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["output_contract"]["promotion"] = False
        self.check(document)

    def test_solver_basename_path_rejected(self) -> None:
        document = valid_document()
        document["solver"]["basename"] = "C:/ngspice.exe"
        self.check(document)

    def test_version_failure_rejected(self) -> None:
        document = valid_document()
        document["toolchain"]["python"]["version_exit_code"] = 1
        self.check(document)

    def test_case_kind_drift_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["kind"] = "measure_only_v1"
        self.check(document)

    def test_cli_negative_bytes_and_bad_hash_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["cli"]["stdout_bytes"] = -1
        document["cases"][0]["cli"]["stderr_sha256"] = "bad"
        self.check(document)

    def test_summary_negative_bytes_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["bytes"] = -1
        self.check(document)

    def test_waveform_artifact_hash_drift_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["artifacts"][-1]["sha256"] = "0" * 64
        self.check(document)

    def test_zero_log_bytes_are_allowed(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["artifacts"][1]["bytes"] = 0
        document["cases"][0]["summary"]["artifacts"][2]["bytes"] = 0
        self.check(document, True)

    def test_non_dict_contract_rejected_without_exception(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["output_contract"] = []
        self.check(document)

    def test_non_list_artifacts_rejected_without_exception(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["artifacts"] = {}
        self.check(document)

    def test_non_dict_artifact_rejected_without_exception(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["artifacts"][0] = "artifact"
        self.check(document)

    def test_wrong_measurement_name_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["measurements"][0]["name"] = "m_only"
        document["cases"][0]["summary"]["output_contract"]["returned"]["measurements"][0]["name"] = "m_only"
        self.check(document)

    def test_consumed_input_drift_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["consumed_input"]["sha256"] = "0" * 64
        self.check(document)

    def test_binary_identity_drift_rejected(self) -> None:
        document = valid_document()
        document["build"]["binary_sha256"] = "bad"
        self.check(document)

    def test_measure_only_nonzero_rows_rejected(self) -> None:
        document = valid_document()
        document["cases"][1]["summary"]["waveform_rows"] = 1
        document["cases"][1]["summary"]["output_contract"]["returned"]["waveform_rows"] = 1
        self.check(document)

    def test_measurement_extra_key_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["summary"]["measurements"][0]["extra"] = 99
        document["cases"][0]["summary"]["output_contract"]["returned"]["measurements"][0]["extra"] = 99
        self.check(document)

    def test_binary_negative_bytes_rejected(self) -> None:
        document = valid_document()
        document["build"]["binary_bytes"] = -1
        self.check(document)

    def test_build_stdout_hash_drift_rejected(self) -> None:
        document = valid_document()
        document["build"]["stdout_sha256"] = "bad"
        self.check(document)

    def test_shared_cli_output_budget_rejected(self) -> None:
        document = valid_document()
        document["cases"][0]["cli"]["stdout_bytes"] = 40000
        document["cases"][0]["cli"]["stderr_bytes"] = 30000
        self.check(document)

    def test_shared_build_output_budget_rejected(self) -> None:
        document = valid_document()
        document["build"]["stdout_bytes"] = 70000000
        document["build"]["stderr_bytes"] = 70000000
        self.check(document)

    def test_tool_timeout_drift_rejected(self) -> None:
        document = valid_document()
        document["toolchain"]["git"]["timeout_seconds"] = 11
        self.check(document)

    def test_bool_numeric_fields_rejected(self) -> None:
        document = valid_document()
        document["toolchain"]["git"]["file_bytes"] = True
        document["solver"]["pre_file_bytes"] = True
        document["build"]["stdout_bytes"] = True
        document["cases"][0]["summary"]["measurements"][0]["value"] = True
        document["cases"][0]["summary"]["waveform_rows"] = True
        document["cases"][0]["summary"]["artifacts"][0]["bytes"] = True
        document["cases"][0]["summary"]["output_contract"]["returned"]["waveform_rows"] = True
        self.check(document)

    def test_non_dict_case_rejected(self) -> None:
        document = valid_document()
        document["cases"][0] = "not-a-case"
        self.check(document)

    def test_missing_cases_rejected_without_exception(self) -> None:
        document = valid_document()
        del document["cases"]
        self.check(document)

    def test_non_list_fixture_values_rejected_without_exception(self) -> None:
        for value in (None, 7, "fixtures"):
            document = valid_document()
            document["fixtures"] = value
            self.check(document)

    def test_non_list_cases_rejected_without_exception(self) -> None:
        document = valid_document()
        document["cases"] = {"uppercase_tran": case("uppercase_tran", "uppercase_tran_v1", True)}
        self.check(document)


if __name__ == "__main__":
    unittest.main()
