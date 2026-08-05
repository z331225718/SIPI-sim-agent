"""Conformance and mutation tests for the M1-02A strict adapter SPI."""
from __future__ import annotations

from copy import deepcopy
import unittest

from jsonschema import ValidationError

from verify_m1_backend_execution_envelopes import validate_backend_request, validate_backend_result


def run_request(mode="strict"):
    selection = {"mode": "strict", "instance": "pybert-python"}
    if mode == "auto":
        selection = {"mode": "auto", "candidates": ["pybert-rust", "pybert-python"], "fallback_on": ["EngineUnavailable", "UnsupportedCapability"]}
    if mode == "compare":
        selection = {"mode": "compare", "reference": "pybert-python", "candidate": "pybert-rust", "comparison_profile": "parity.v1"}
    return {"schema": "sipi.run-request.v1", "run_id": "run-1", "project_id": "project-1", "analysis_id": "analysis-1", "attempt_id": "attempt-1", "operation": "link.simulate.v1", "payload_schema": "pybert.simulation.v1", "payload": {"source": "fixture"}, "backend_selection": selection, "resource_limits": {}, "randomness": {}, "artifact_policy": {}, "extensions": {}}


def backend_request(parent, role="primary", instance="pybert-python"):
    return {"schema": "sipi.backend-execution-request.v1", "run_id": parent["run_id"], "analysis_id": parent["analysis_id"], "attempt_id": parent["attempt_id"], "backend_execution_id": "backend-1", "role": role, "engine_instance_id": instance, "bundle_hash": "sha256:bundle", "operation": parent["operation"], "payload_schema": parent["payload_schema"], "payload": deepcopy(parent["payload"]), "bound_inputs": {}, "resource_limits": {}, "artifact_policy": {}, "randomness": {}, "selection_hash": "sha256:selection"}


def backend_result(request):
    return {"schema": "sipi.backend-execution-result.v1", "run_id": request["run_id"], "analysis_id": request["analysis_id"], "attempt_id": request["attempt_id"], "backend_execution_id": request["backend_execution_id"], "role": request["role"], "engine_instance_id": request["engine_instance_id"], "bundle_hash": request["bundle_hash"], "operation": request["operation"], "payload_schema": request["payload_schema"], "status": "succeeded", "domain_result_schema": "pybert.simulation.v1", "artifacts": [{"schema": "sipi.artifact-ref.v1", "opaque": True}], "events": [{"schema": "sipi.run-event.v1", "opaque": True}], "warnings": [], "timings": {}, "resource_usage": {}, "error": None}


class BackendExecutionEnvelopeTests(unittest.TestCase):
    def test_strict_request_and_result_are_valid(self):
        parent = run_request()
        request = backend_request(parent)
        validate_backend_request(parent, request, expected_selection_hash="sha256:selection")
        validate_backend_result(request, backend_result(request))

    def test_request_rejects_orchestration_and_unknown_fields(self):
        parent = run_request()
        request = backend_request(parent)
        request["backend_selection"] = parent["backend_selection"]
        with self.assertRaises(ValidationError):
            validate_backend_request(parent, request, "sha256:selection")

    def test_request_requires_single_payload_transport(self):
        parent = run_request()
        request = backend_request(parent)
        request["payload_artifact"] = {"schema": "sipi.artifact-ref.v1"}
        with self.assertRaises(ValidationError):
            validate_backend_request(parent, request, "sha256:selection")

    def test_runtime_selection_must_match_role_and_instance(self):
        parent = run_request("compare")
        request = backend_request(parent, role="candidate", instance="pybert-python")
        with self.assertRaisesRegex(ValueError, "compare role/instance mismatch"):
            validate_backend_request(parent, request, "sha256:selection")

    def test_compare_rejects_primary_role_without_a_key_error(self):
        parent = run_request("compare")
        request = backend_request(parent, role="primary", instance="pybert-python")
        with self.assertRaisesRegex(ValueError, "compare adapter role"):
            validate_backend_request(parent, request, "sha256:selection")

    def test_request_must_echo_parent_and_selection_hash(self):
        parent = run_request()
        request = backend_request(parent)
        request["attempt_id"] = "attempt-2"
        with self.assertRaisesRegex(ValueError, "attempt_id mismatch"):
            validate_backend_request(parent, request, expected_selection_hash="sha256:selection")
        request = backend_request(parent)
        request["selection_hash"] = "sha256:garbage"
        with self.assertRaisesRegex(ValueError, "selection_hash mismatch"):
            validate_backend_request(parent, request, expected_selection_hash="sha256:selection")

    def test_result_must_echo_all_strict_execution_identity(self):
        parent = run_request()
        request = backend_request(parent)
        out = backend_result(request)
        out["bundle_hash"] = "sha256:other"
        with self.assertRaisesRegex(ValueError, "bundle_hash mismatch"):
            validate_backend_result(request, out)

    def test_result_rejects_runtime_orchestration_fields_for_all_consumers(self):
        parent = run_request()
        request = backend_request(parent)
        out = backend_result(request)
        out["fallback_trace"] = []
        with self.assertRaisesRegex(ValueError, "runtime orchestration fields"):
            validate_backend_result(request, out, producer=False)

    def test_output_is_tolerant_for_consumers_but_producer_is_closed(self):
        parent = run_request()
        request = backend_request(parent)
        out = backend_result(request)
        out["future_optional"] = {"compatible": True}
        validate_backend_result(request, out, producer=False)
        with self.assertRaisesRegex(ValueError, "unnamespaced fields"):
            validate_backend_result(request, out)

    def test_status_nullable_rules_reject_invalid_terminal_shapes(self):
        parent = run_request()
        request = backend_request(parent)
        out = backend_result(request)
        out["error"] = {"deferred": True}
        with self.assertRaisesRegex(ValueError, "cannot contain an error"):
            validate_backend_result(request, out)
        out = backend_result(request)
        out["status"] = "failed"
        out["error"] = None
        with self.assertRaisesRegex(ValueError, "requires an error object"):
            validate_backend_result(request, out)
        out = backend_result(request)
        out["status"] = "blocked"
        with self.assertRaises(ValidationError):
            validate_backend_result(request, out)

    def test_successful_result_requires_a_domain_transport(self):
        parent = run_request()
        request = backend_request(parent)
        out = backend_result(request)
        out["artifacts"] = []
        with self.assertRaisesRegex(ValueError, "inline result or artifact"):
            validate_backend_result(request, out)
        out["domain_result"] = {"kind": "small-result"}
        validate_backend_result(request, out)

    def test_inline_domain_result_requires_a_nonempty_schema(self):
        parent = run_request()
        request = backend_request(parent)
        out = backend_result(request)
        out["status"] = "failed"
        out["error"] = {"deferred": True}
        out["domain_result_schema"] = None
        out["domain_result"] = {"partial": True}
        with self.assertRaisesRegex(ValueError, "inline domain result requires"):
            validate_backend_result(request, out)

    def test_artifact_and_event_slots_require_platform_schema_tags(self):
        parent = run_request()
        request = backend_request(parent)
        out = backend_result(request)
        out["events"] = [{"schema": "legacy.event.v1"}]
        with self.assertRaises(ValidationError):
            validate_backend_result(request, out)


if __name__ == "__main__":
    unittest.main()
