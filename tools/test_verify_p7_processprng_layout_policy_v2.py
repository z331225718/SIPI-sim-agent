"""Mutation tests for the P7 ProcessPrng-only layout policy revision."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_processprng_policy", ROOT / "tools" / "verify_p7_processprng_layout_policy_v2.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class P7ProcessPrngLayoutPolicyTests(unittest.TestCase):
    def document(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "p7-processprng-layout-policy.v2.yaml").read_text(encoding="utf-8"))

    def test_document_is_valid(self) -> None:
        self.assertTrue(GATE.validate(self.document())["valid"])

    def test_policy_boundary_and_promotion_mutations_are_rejected(self) -> None:
        for path, value, reason in (
            (("selected_platform_boundary", "minimum_supported_desktop"), "windows_8", "platform_boundary_invalid"),
            (("policy", "normal_import_dll_allowlist"), ["kernel32.dll", "bcryptprimitives.dll", "other.dll"], "policy_definition_invalid"),
            (("policy", "delta_from_v1"), {"added_normal_import_dll": "other.dll", "removed_normal_import_dlls": []}, "policy_definition_invalid"),
            (("gates", "static_dependency_closure_evaluated"), True, "gate_state_invalid"),
            (("gates", "composition_invoked"), True, "gate_state_invalid"),
            (("gates", "promotion_status"), "eligible", "gate_state_invalid"),
            (("non_claims",), ["bogus"], "non_claims_invalid"),
        ):
            with self.subTest(path=path):
                document = self.document()
                target = document
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(GATE.PolicyError):
                    GATE.validate(document)

    def test_external_layout_report_is_exactly_bound(self) -> None:
        document = self.document()
        report = {
            "schema": "sipi.release-layout-report.v1", "status": "layout_conformant",
            "policySha256": GATE.sha256(GATE.canonical_policy()),
            "inventorySha256": "6be163cde5ba9b3906e7982ce657b234f2b19294638b053c191e5db08ef45812",
            "executableSha256": "a3059d052df54c0f3ebbd727bd2f71760ff33f73af82e1e2f29c0ec35b8c882d",
            "executableBytes": 3908608, "machine": "amd64",
            "normalImports": GATE.POLICY["normalImportDllAllowlist"], "delayImportDirectoryPresent": False,
            "smoke": [
                {"args": ["version", "--json"], "exitCode": 0, "stdoutSha256": "fd5ca3a9c17338be055b18c37d5ede95d88e929172d2cade97888504e9d68663", "stderrSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
                {"args": ["capabilities", "--json"], "exitCode": 0, "stdoutSha256": "46fb24ae991ccb424190bd290c37463b78ed2d436adcb4d2e8a69e8936ea47b8", "stderrSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
                {"args": ["doctor", "--json"], "exitCode": 0, "stdoutSha256": "eac21c81bd526242e0ade57a1d5d4c449e9d59c970ef46c656929f0fb8284a49", "stderrSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
                {"args": ["schema", "list", "--json"], "exitCode": 0, "stdoutSha256": "c3e6e6cf3f54948005bb2a6798ae27bc61594d400196f795753e605dc08b634b", "stderrSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
            ],
            "limitations": ["provisional product boundary; this is not release readiness", "no hostile-filesystem containment claim", "no arbitrary-command child-process or dynamic-load claim"],
        }
        raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        document["external_layout_observation"]["sha256"] = GATE.sha256(raw)
        document["external_layout_observation"]["byte_length"] = len(raw)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_bytes(raw)
            self.assertTrue(GATE.validate(document, path)["layout_report_bound"])
            tampered = copy.deepcopy(report)
            tampered["normalImports"].append("other.dll")
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(GATE.PolicyError, "external_layout_report_identity_drift"):
                GATE.validate(document, path)


if __name__ == "__main__":
    unittest.main()
