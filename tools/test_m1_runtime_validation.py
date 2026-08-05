from copy import deepcopy
import unittest

from verify_m1_runtime_validation import validate_capabilities, validate_event, validate_platform_error, validate_resource_slice, validate_validation_report


LIMITS = {"enforcement": "required", "wall_time_s": 5.0, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None}
ENFORCEMENT = {"wall_time_s": "hard", "cpu_time_s": "unsupported", "memory_bytes": "unsupported", "process_count": "unsupported", "artifact_bytes": "unsupported"}


def error(category="Timeout", resource="wall_time_s"):
    return {"category": category, "message": "fixture", "resource": resource, "cause": None, "details": {}}


def event(scope="project", sequence=0, elapsed=0):
    ids = {"project": (None, None, None), "analysis": ("a", None, None), "attempt": ("a", "t", None), "backend_execution": ("a", "t", "b")}[scope]
    return {"schema": "sipi.run-event.v1", "run_id": "r", "sequence": sequence, "scope": scope, "stage": "fixture", "elapsed_s": elapsed, "analysis_id": ids[0], "attempt_id": ids[1], "backend_execution_id": ids[2], "extensions": {}}


class RuntimeValidationTests(unittest.TestCase):
    def test_event_scopes_and_order(self):
        previous = {"r": (0, 1)}
        validate_event(event("backend_execution", 1, 1), previous)
        with self.assertRaisesRegex(ValueError, "order regression"):
            validate_event(event("project", 0, 1), previous)

    def test_resource_slice_and_enforcement_fail_closed(self):
        validate_resource_slice(LIMITS, deepcopy(LIMITS), ENFORCEMENT)
        child = deepcopy(LIMITS); child["wall_time_s"] = 6
        with self.assertRaisesRegex(ValueError, "exceeds"):
            validate_resource_slice(LIMITS, child, ENFORCEMENT)
        bad = deepcopy(ENFORCEMENT); bad["wall_time_s"] = "monitor"
        with self.assertRaisesRegex(ValueError, "UnsupportedCapability"):
            validate_resource_slice(LIMITS, deepcopy(LIMITS), bad)

    def test_error_resource_mapping(self):
        validate_platform_error(error())
        with self.assertRaisesRegex(ValueError, "Timeout"):
            validate_platform_error(error("Timeout", "memory_bytes"))
        with self.assertRaisesRegex(ValueError, "ResourceLimit"):
            validate_platform_error(error("ResourceLimit", "wall_time_s"))

    def test_capability_key_is_unique(self):
        item = {"operation": "link.simulate.v1", "payload_schema": "pybert.simulation.v1", "domain_result_schemas": ["pybert.output.v1"], "behavior_profile": "default", "role": "reference", "execution_mode": "process", "resource_enforcement": ENFORCEMENT, "external_model_capabilities": {}, "maximum_scale": {"vendor.max": 1}}
        value = {"schema": "sipi.engine-capabilities.v1", "producer": "fixture", "version": "1", "build": "x", "engine_instance_id": "pybert-python", "bundle_hash": "sha256:x", "platform": {"os": "windows", "architecture": "x86_64"}, "capabilities": [item], "extensions": {}}
        validate_capabilities(value)
        value["capabilities"].append(deepcopy(item))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_capabilities(value)


if __name__ == "__main__": unittest.main()
