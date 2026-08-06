from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_contracts import parse_backend_execution_result
from sipi_runtime import ComparisonError, ComparisonProfile, Metric, compare_results


def backend_result(role: str, domain: dict, *, operation: str = "link.simulate.v1", status: str = "succeeded") -> object:
    value = {
        "schema": "sipi.backend-execution-result.v1",
        "run_id": "run-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "backend_execution_id": f"attempt-1-{role}",
        "role": role,
        "engine_instance_id": "pybert-" + role,
        "bundle_hash": "sha256:" + "a" * 64,
        "operation": operation,
        "payload_schema": "pybert.simulation.v1",
        "status": status,
        "domain_result_schema": "pybert.native-cli-result.v1",
        "domain_result": domain,
        "artifacts": [],
        "events": [],
        "warnings": [],
        "timings": {},
        "resource_usage": {"actual_enforcement": {"wall_time_s": "unsupported", "cpu_time_s": "unsupported", "memory_bytes": "unsupported", "process_count": "unsupported", "artifact_bytes": "unsupported"}},
        "error": None,
    }
    if status != "succeeded":
        value["error"] = {"category": "NumericFailure", "message": "fixture failure", "resource": None, "cause": None, "details": {}}
    return parse_backend_execution_result(value)


class ComparisonTests(unittest.TestCase):
    def test_matching_within_tolerance(self) -> None:
        reference = backend_result("reference", {"cases": [{"metrics": {"com": 3.0}}]})
        candidate = backend_result("candidate", {"cases": [{"metrics": {"com": 3.001}}]})
        report = compare_results(reference, candidate, ComparisonProfile("default", (Metric("cases[0].metrics.com", atol=0.01),)))
        self.assertTrue(report.matched)
        self.assertEqual(report.checked_count, 1)
        self.assertEqual(report.mismatches, ())

    def test_mismatch_beyond_tolerance(self) -> None:
        reference = backend_result("reference", {"com": 1.0})
        candidate = backend_result("candidate", {"com": 2.0})
        report = compare_results(reference, candidate, ComparisonProfile("default", (Metric("com", atol=0.1),)))
        self.assertFalse(report.matched)
        self.assertEqual(len(report.mismatches), 1)
        self.assertEqual(report.mismatches[0].path, "com")
        self.assertEqual(report.mismatches[0].reference, 1.0)
        self.assertEqual(report.mismatches[0].candidate, 2.0)

    def test_relative_tolerance_is_applied(self) -> None:
        reference = backend_result("reference", {"value": 100.0})
        candidate = backend_result("candidate", {"value": 100.5})
        profile = ComparisonProfile("default", (Metric("value", rtol=0.01),))
        self.assertTrue(compare_results(reference, candidate, profile).matched)
        profile_strict = ComparisonProfile("default", (Metric("value", rtol=0.001),))
        self.assertFalse(compare_results(reference, candidate, profile_strict).matched)

    def test_missing_path_is_error(self) -> None:
        reference = backend_result("reference", {"value": 1.0})
        candidate = backend_result("candidate", {"other": 1.0})
        report = compare_results(reference, candidate, ComparisonProfile("default", (Metric("value"),)))
        self.assertFalse(report.matched)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.checked_count, 0)

    def test_identity_mismatch_is_error(self) -> None:
        reference = backend_result("reference", {"value": 1.0}, operation="link.simulate.v1")
        candidate = backend_result("candidate", {"value": 1.0}, operation="com.r480.run.v1")
        report = compare_results(reference, candidate, ComparisonProfile("default", (Metric("value"),)))
        self.assertFalse(report.matched)
        self.assertIn("operations/payloads differ", report.errors[0])

    def test_same_role_is_error(self) -> None:
        reference = backend_result("candidate", {"value": 1.0})
        candidate = backend_result("candidate", {"value": 1.0})
        report = compare_results(reference, candidate, ComparisonProfile("default", (Metric("value"),)))
        self.assertFalse(report.matched)
        self.assertIn("roles must differ", report.errors[0])

    def test_failed_result_is_error(self) -> None:
        reference = backend_result("reference", {"value": 1.0}, status="failed")
        candidate = backend_result("candidate", {"value": 1.0})
        report = compare_results(reference, candidate, ComparisonProfile("default", (Metric("value"),)))
        self.assertFalse(report.matched)
        self.assertIn("succeeded", report.errors[0])

    def test_path_resolution_supports_nested_arrays(self) -> None:
        reference = backend_result("reference", {"cases": [{"metrics": {"ber": 1e-6}}]})
        candidate = backend_result("candidate", {"cases": [{"metrics": {"ber": 1.1e-6}}]})
        report = compare_results(reference, candidate, ComparisonProfile("default", (Metric("cases[0].metrics.ber", rtol=0.2),)))
        self.assertTrue(report.matched)

    def test_invalid_path_is_reported_as_error(self) -> None:
        report = compare_results(
            backend_result("reference", {"value": 1.0}),
            backend_result("candidate", {"value": 1.0}),
            ComparisonProfile("default", (Metric("cases[x].value"),)),
        )
        self.assertFalse(report.matched)
        self.assertIn("invalid path index", report.errors[0])


if __name__ == "__main__":
    unittest.main()
