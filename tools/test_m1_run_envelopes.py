"""Conformance and mutation tests for the M1-02 run-envelope boundary."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from verify_m1_run_envelopes import validate_request, validate_result


def request(mode="strict"):
    base = {
        "schema": "sipi.run-request.v1",
        "run_id": "run-1",
        "project_id": "project-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "operation": "link.simulate.v1",
        "payload_schema": "pybert.simulation.v1",
        "payload": {"source": "fixture"},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "randomness": {},
        "artifact_policy": {},
        "extensions": {},
    }
    if mode == "strict":
        base["backend_selection"] = {
            "mode": "strict",
            "instance": "pybert-python",
            "allow_experimental": False,
            "allow_internal": False,
        }
    elif mode == "auto":
        base["backend_selection"] = {
            "mode": "auto",
            "candidates": ["pybert-rust", "pybert-python"],
            "fallback_on": ["EngineUnavailable", "UnsupportedCapability"],
        }
    else:
        base["backend_selection"] = {
            "mode": "compare",
            "reference": "pybert-python",
            "candidate": "pybert-rust",
            "comparison_profile": "pybert-native-parity-v1",
            "allow_experimental": False,
            "allow_internal": False,
        }
    return base


def execution(role, instance, suffix):
    return {
        "backend_execution_id": f"backend-{suffix}",
        "role": role,
        "engine_instance_id": instance,
        "bundle_hash": f"sha256:bundle-{suffix}",
        "status": "succeeded",
        "domain_result_schema": "pybert.simulation.v1",
        "artifacts": [{"schema": "sipi.artifact-ref.v1", "content_schema": "pybert.output.v1", "relative_path": f"backends/backend-{suffix}/artifacts/result.json", "mime_type": "application/json", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "byte_length": 1, "producer": "fixture.adapter", "role": "domain_result", "extensions": {}}],
        "error": None,
    }


def result(req, executions):
    return {
        "schema": "sipi.run-result.v1",
        "run_id": req["run_id"],
        "analysis_id": req["analysis_id"],
        "attempt_id": req["attempt_id"],
        "operation": req["operation"],
        "payload_schema": req["payload_schema"],
        "status": "succeeded",
        "selection_requested": deepcopy(req["backend_selection"]),
        "backend_executions": executions,
        "fallback_trace": [],
        "comparison": {},
        "metrics_summary": {},
        "artifacts": [],
        "events": [],
        "provenance": {"producers": [{"id": "fixture.platform", "kind": "platform", "name": "fixture", "version": "1", "commit": None, "build_profile": None, "dirty": False, "bundle_hash": None, "parent_ids": []}, {"id": "fixture.adapter", "kind": "adapter", "name": "fixture", "version": "1", "commit": None, "build_profile": None, "dirty": False, "bundle_hash": None, "parent_ids": ["fixture.platform"]}, {"id": "fixture.engine", "kind": "engine", "name": "fixture", "version": "1", "commit": None, "build_profile": None, "dirty": False, "bundle_hash": None, "parent_ids": ["fixture.adapter"]}, {"id": "fixture.algorithm", "kind": "algorithm", "name": "fixture", "version": "1", "commit": None, "build_profile": None, "dirty": False, "bundle_hash": None, "parent_ids": ["fixture.engine"]}], "request": {"schema": "pybert.simulation.v1", "behavior_profile": "fixture", "inputs": [], "resolved_config_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}, "environment": {"python": None, "rust": None, "os": "windows", "cpu": "fixture", "blas": None, "thread_count": 1, "dependency_locks": []}, "randomness": {"seed": None, "array_sources": []}, "policies": {"fallback": [], "conditioning": [], "repairs": [], "truncations": [], "approximations": []}, "extensions": {}},
        "timings": {},
        "resource_usage": {"actual_enforcement": {"wall_time_s": "monitor", "cpu_time_s": "unsupported", "memory_bytes": "unsupported", "process_count": "unsupported", "artifact_bytes": "unsupported"}},
        "error": None,
        "warnings": [],
        "extensions": {},
    }


class RunEnvelopeTests(unittest.TestCase):
    def test_strict_envelope_is_valid(self):
        req = request()
        validate_request(req)
        validate_result(req, result(req, [execution("primary", "pybert-python", "1")]))

    def test_auto_records_only_preflight_rejections(self):
        req = request("auto")
        out = result(req, [execution("primary", "pybert-python", "1")])
        out["fallback_trace"] = [{"instance": "pybert-rust", "reason": "EngineUnavailable"}]
        validate_request(req)
        validate_result(req, out)

    def test_compare_has_exactly_two_resolved_roles(self):
        req = request("compare")
        out = result(req, [execution("reference", "pybert-python", "1"), execution("candidate", "pybert-rust", "2")])
        out["comparison"] = {"profile": "pybert-native-parity-v1"}
        validate_request(req)
        validate_result(req, out)

    def test_compare_rejects_same_instance(self):
        req = request("compare")
        req["backend_selection"]["candidate"] = "pybert-python"
        with self.assertRaises(ValueError):
            validate_request(req)

    def test_auto_rejects_opt_in_fields(self):
        req = request("auto")
        req["backend_selection"]["allow_experimental"] = True
        with self.assertRaises(ValidationError):
            validate_request(req)

    def test_request_requires_deferred_policy_slots(self):
        req = request()
        del req["resource_limits"]
        with self.assertRaises(ValidationError):
            validate_request(req)

    def test_internal_opt_in_requires_authorization_context(self):
        req = request()
        req["backend_selection"]["allow_internal"] = True
        with self.assertRaisesRegex(ValueError, "authorized internal policy"):
            validate_request(req)
        validate_request(req, allow_internal=True)
        out = result(req, [execution("primary", "pybert-python", "1")])
        with self.assertRaisesRegex(ValueError, "authorized internal policy"):
            validate_result(req, out)
        validate_result(req, out, allow_internal=True)

    def test_auto_accepts_the_fixed_reason_set_in_either_order(self):
        req = request("auto")
        req["backend_selection"]["fallback_on"].reverse()
        validate_request(req)

    def test_result_ids_and_payload_schema_must_match_request(self):
        req = request()
        out = result(req, [execution("primary", "pybert-python", "1")])
        out["payload_schema"] = "other.v1"
        with self.assertRaisesRegex(ValueError, "payload_schema mismatch"):
            validate_result(req, out)

    def test_auto_execution_must_follow_ordered_preflight_trace(self):
        req = request("auto")
        out = result(req, [execution("primary", "pybert-rust", "1")])
        out["fallback_trace"] = [{"instance": "pybert-rust", "reason": "EngineUnavailable"}]
        with self.assertRaisesRegex(ValueError, "does not follow"):
            validate_result(req, out)

    def test_compare_role_and_instance_mutations_are_rejected(self):
        req = request("compare")
        out = result(req, [execution("reference", "pybert-python", "1"), execution("candidate", "pybert-rust", "2")])
        out["comparison"] = {"profile": "pybert-native-parity-v1"}
        out["backend_executions"][1]["engine_instance_id"] = "pybert-other"
        with self.assertRaisesRegex(ValueError, "compare candidate instance mismatch"):
            validate_result(req, out)

    def test_compare_requires_matching_nonempty_evidence(self):
        req = request("compare")
        out = result(req, [execution("reference", "pybert-python", "1"), execution("candidate", "pybert-rust", "2")])
        with self.assertRaisesRegex(ValueError, "matching comparison evidence"):
            validate_result(req, out)
        out["comparison"] = {"profile": "other-profile"}
        with self.assertRaisesRegex(ValueError, "matching comparison evidence"):
            validate_result(req, out)

    def test_non_compare_rejects_spurious_comparison(self):
        req = request()
        out = result(req, [execution("primary", "pybert-python", "1")])
        out["comparison"] = {"profile": "not-applicable"}
        with self.assertRaisesRegex(ValueError, "comparison outside compare mode"):
            validate_result(req, out)

    def test_producer_rejects_flattened_domain_fields_but_consumer_tolerates_them(self):
        req = request()
        out = result(req, [execution("primary", "pybert-python", "1")])
        out["ber"] = 1e-12
        validate_result(req, out, producer=False)
        with self.assertRaisesRegex(ValueError, "run result has unnamespaced fields"):
            validate_result(req, out, producer=True)

    def test_consumer_tolerates_nested_optional_fields_but_producer_does_not(self):
        req = request()
        out = result(req, [execution("primary", "pybert-python", "1")])
        out["backend_executions"][0]["future_optional"] = {"compatible": True}
        validate_result(req, out, producer=False)
        with self.assertRaisesRegex(ValueError, "backend execution has unnamespaced fields"):
            validate_result(req, out)

    def test_producer_rejects_unnamespaced_summary_metrics(self):
        req = request()
        out = result(req, [execution("primary", "pybert-python", "1")])
        out["metrics_summary"] = {"ber": 1e-12}
        with self.assertRaisesRegex(ValueError, "metrics_summary has unnamespaced keys"):
            validate_result(req, out)

    def test_result_requires_exactly_one_event_representation(self):
        req = request()
        out = result(req, [execution("primary", "pybert-python", "1")])
        out["event_log_artifact"] = {"schema": "sipi.artifact-ref.v1"}
        with self.assertRaises(ValidationError):
            validate_result(req, out)

    def test_extensions_must_be_namespaced(self):
        req = request()
        req["extensions"] = {"experimental": {"enabled": True}}
        with self.assertRaises(ValidationError):
            validate_request(req)

    def test_backend_execution_id_cannot_escape_its_execution_summary(self):
        req = request()
        out = result(req, [execution("primary", "pybert-python", "1")])
        out["backend_execution_id"] = "backend-1"
        with self.assertRaisesRegex(ValueError, "belongs to backend_executions"):
            validate_result(req, out, producer=False)


if __name__ == "__main__":
    unittest.main()
