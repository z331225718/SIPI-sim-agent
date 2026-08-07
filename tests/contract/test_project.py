from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import ContractViolation, ProjectV1, parse_project


def project(**changes):
    value = {
        "schema": "sipi.project.v1",
        "project": {"name": "pcie-link-study", "extensions": {}},
        "runtime": {"engine_lock": "engine.lock", "extensions": {}},
        "analyses": [
            {
                "id": "channel-response",
                "operation": "circuit.solve.v1",
                "backend_selection": {"mode": "strict", "instance": "agent-spice-process"},
                "payload_schema": "sipi.adapter.agent-spice.rfm-response-request.v1",
                "payload": {"rfm": "models/channel.rfm", "fft_size": 32768},
                "exports": [{"role": "channel-response", "schema": "agent-spice.rfm-response.v1"}],
            },
            {
                "id": "link-eye",
                "operation": "link.simulate.v1",
                "backend_selection": {"mode": "strict", "instance": "pybert-python"},
                "payload_schema": "pybert.simulation.v1",
                "payload_artifact": "requests/link-input.json",
                "depends_on": ["channel-response"],
                "inputs": {
                    "channel_response": {
                        "from_analysis": "channel-response",
                        "artifact_role": "channel-response",
                        "expected_schema": "agent-spice.rfm-response.v1",
                    }
                },
            },
        ],
        "extensions": {},
    }
    value.update(changes)
    return value


class ProjectContractTests(unittest.TestCase):
    def test_good_project_parses_and_is_immutable(self):
        raw = project()
        model = parse_project(raw)
        self.assertIsInstance(model, ProjectV1)
        raw["analyses"][0]["payload"]["fft_size"] = 1
        self.assertEqual(model.to_wire()["analyses"][0]["payload"]["fft_size"], 32768)
        with self.assertRaises(TypeError):
            model.wire["analyses"][0]["payload"]["fft_size"] = 2  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            model._data = {}  # type: ignore[misc]
        exported = model.to_wire()
        exported["analyses"][1]["payload_artifact"] = "tampered.json"
        self.assertEqual(model.to_wire()["analyses"][1]["payload_artifact"], "requests/link-input.json")

    def test_schema_identity_and_version_are_strict(self):
        with self.assertRaisesRegex(ContractViolation, "schema"):
            parse_project(project(schema="sipi.project.v2"))
        with self.assertRaisesRegex(ContractViolation, "schema"):
            parse_project({**project(), "future_optional": True})

    def test_analysis_ids_must_be_unique(self):
        raw = project()
        raw["analyses"][1]["id"] = "channel-response"
        with self.assertRaisesRegex(ContractViolation, "unique"):
            parse_project(raw)

    def test_dependencies_must_be_declared_and_not_self(self):
        raw = project()
        raw["analyses"][0]["depends_on"] = ["missing-analysis"]
        with self.assertRaisesRegex(ContractViolation, "undeclared"):
            parse_project(raw)
        raw = project()
        raw["analyses"][1]["depends_on"] = ["link-eye"]
        with self.assertRaisesRegex(ContractViolation, "itself"):
            parse_project(raw)

    def test_payload_and_payload_artifact_are_mutually_exclusive(self):
        raw = project()
        raw["analyses"][0]["payload_artifact"] = "requests/extra.json"
        with self.assertRaises(ContractViolation):
            parse_project(raw)
        raw = project()
        del raw["analyses"][0]["payload"]
        with self.assertRaises(ContractViolation):
            parse_project(raw)

    def test_paths_are_relative_and_cannot_escape(self):
        raw = project()
        raw["analyses"][1]["payload_artifact"] = "../outside.json"
        with self.assertRaises(ContractViolation):
            parse_project(raw)
        raw = project()
        raw["runtime"]["engine_lock"] = "C:/engine.lock"
        with self.assertRaises(ContractViolation):
            parse_project(raw)
        raw = project()
        raw["runtime"]["engine_lock"] = "engine.lock"
        parse_project(raw)

    def test_input_bindings_require_declared_producer_export(self):
        raw = project()
        raw["analyses"][1]["inputs"]["channel_response"]["from_analysis"] = "missing"
        with self.assertRaisesRegex(ContractViolation, "undeclared"):
            parse_project(raw)
        raw = project()
        raw["analyses"][1]["inputs"]["channel_response"]["artifact_role"] = "no-such-role"
        with self.assertRaisesRegex(ContractViolation, "no producer export role"):
            parse_project(raw)
        raw = project()
        raw["analyses"][1]["inputs"]["channel_response"]["from_analysis"] = "link-eye"
        with self.assertRaisesRegex(ContractViolation, "own output"):
            parse_project(raw)

    def test_export_roles_are_unique_per_analysis(self):
        raw = project()
        raw["analyses"][0]["exports"] = [
            {"role": "channel-response", "schema": "agent-spice.rfm-response.v1"},
            {"role": "channel-response", "schema": "agent-spice.rfm-response.v1"},
        ]
        with self.assertRaisesRegex(ContractViolation, "unique"):
            parse_project(raw)

    def test_backend_selection_requires_complete_discriminated_object(self):
        raw = project()
        raw["analyses"][0]["backend_selection"] = {"mode": "strict"}
        with self.assertRaises(ContractViolation):
            parse_project(raw)
        raw = project()
        raw["analyses"][0]["backend_selection"] = {"mode": "auto", "candidates": ["a", "b"], "fallback_on": ["EngineUnavailable", "UnsupportedCapability"]}
        parse_project(raw)

    def test_runtime_backend_defaults_require_full_selection_objects(self):
        raw = project()
        raw["runtime"]["backend_defaults"] = {"link.simulate.v1": {"mode": "auto"}}
        with self.assertRaises(ContractViolation):
            parse_project(raw)


if __name__ == "__main__":
    unittest.main()
