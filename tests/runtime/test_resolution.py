from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_contracts import ContractViolation, parse_project
from sipi_runtime import ResolvedAnalysis, ResolvedProject, resolve_project


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


def write_root(directory: Path, payload_bytes: bytes = b'{"sample": 2}'):
    (directory / "engine.lock").write_text("{}", encoding="utf-8")
    (directory / "requests").mkdir(exist_ok=True)
    (directory / "requests" / "link-input.json").write_bytes(payload_bytes)


class ResolutionTests(unittest.TestCase):
    def test_inline_payload_is_hashed_and_selection_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_root(root)
            model = parse_project(project())
            resolved = resolve_project(model, root)
            self.assertIsInstance(resolved, ResolvedProject)
            first = resolved.analyses[0]
            self.assertIsInstance(first, ResolvedAnalysis)
            self.assertEqual(first.selection_source, "analysis")
            self.assertEqual(first.backend_selection, {"mode": "strict", "instance": "agent-spice-process"})
            self.assertEqual(first.payload_sha256, hashlib.sha256(b'{"fft_size":32768,"rfm":"models/channel.rfm"}').hexdigest())
            self.assertIsNone(first.payload_artifact)
            self.assertEqual(resolved.project_hash, resolve_project(model, root).project_hash)

    def test_runtime_default_selection_is_applied_when_analysis_omits_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_root(root)
            raw = project()
            del raw["analyses"][0]["backend_selection"]
            raw["runtime"]["backend_defaults"] = {"circuit.solve.v1": {"mode": "strict", "instance": "agent-spice-process"}}
            resolved = resolve_project(parse_project(raw), root)
            first = resolved.analyses[0]
            self.assertEqual(first.selection_source, "runtime_default")
            self.assertEqual(first.backend_selection, {"mode": "strict", "instance": "agent-spice-process"})

    def test_payload_artifact_is_resolved_and_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_root(root, b'{"seed": 7}')
            resolved = resolve_project(parse_project(project()), root)
            link = resolved.analyses[1]
            ref = link.payload_artifact
            self.assertIsNotNone(ref)
            expected = hashlib.sha256(b'{"seed": 7}').hexdigest()
            self.assertEqual(ref["sha256"], expected)
            self.assertEqual(ref["byte_length"], 11)
            self.assertEqual(ref["producer"], "link-eye")
            self.assertEqual(ref["role"], "payload")
            self.assertEqual(link.payload_sha256, expected)
            self.assertEqual(len(link.inputs), 1)
            binding = link.inputs[0]
            self.assertEqual(binding.from_analysis, "channel-response")
            self.assertEqual(binding.artifact_role, "channel-response")
            self.assertEqual(binding.expected_schema, "agent-spice.rfm-response.v1")

    def test_missing_payload_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "engine.lock").write_text("{}", encoding="utf-8")
            with self.assertRaises(ContractViolation):
                resolve_project(parse_project(project()), root)

    def test_missing_engine_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_root(root)
            (root / "engine.lock").unlink()
            with self.assertRaises(ContractViolation):
                resolve_project(parse_project(project()), root)

    def test_engine_lock_ref_hashes_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_root(root)
            resolved = resolve_project(parse_project(project()), root)
            self.assertEqual(resolved.engine_lock["content_schema"], "sipi.engine-lock.v1")
            self.assertEqual(resolved.engine_lock["sha256"], hashlib.sha256(b"{}").hexdigest())

    def test_project_hash_changes_with_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_root(root, b'{"seed": 1}')
            first = resolve_project(parse_project(project()), root).project_hash
            write_root(root, b'{"seed": 2}')
            second = resolve_project(parse_project(project()), root).project_hash
            self.assertNotEqual(first, second)

    def test_failure_policy_defaults_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_root(root)
            resolved = resolve_project(parse_project(project()), root)
            self.assertEqual(resolved.failure_policy, "block-dependents, continue-independent")
            wire = resolved.to_wire()
            self.assertEqual(wire["project"], "pcie-link-study")
            self.assertEqual(len(wire["analyses"]), 2)

    def test_project_hash_covers_content_excluding_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_root(root)
            resolved = resolve_project(parse_project(project()), root)
            wire = resolved.to_wire()
            wire.pop("project_hash")
            canonical = json.dumps(wire, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            self.assertEqual(resolved.project_hash, hashlib.sha256(canonical).hexdigest())


if __name__ == "__main__":
    unittest.main()
