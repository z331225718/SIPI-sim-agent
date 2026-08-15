"""Mutation tests for P7 BCryptPrimitives/ProcessPrng preflight evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_processprng_preflight", ROOT / "tools" / "verify_p7_bcryptprimitives_processprng_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class P7ProcessPrngPreflightTests(unittest.TestCase):
    def document(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "p7-bcryptprimitives-processprng-preflight.v1.yaml").read_text(encoding="utf-8"))

    def test_document_is_valid(self) -> None:
        result = GATE.validate(self.document())
        self.assertTrue(result["valid"])
        self.assertTrue(result["policy_revision_pending"])

    def test_import_authority_and_gate_mutations_are_rejected(self) -> None:
        for path, value, reason in (
            (("observation", "candidate_import_and_smoke", "bcryptprimitives_import"), {"import_kind": "ordinal", "symbols": ["ordinal:1"]}, "processprng_import_observation_invalid"),
            (("observation", "candidate_import_and_smoke", "delay_import_directory_present"), True, "processprng_import_observation_invalid"),
            (("observation", "authority", "frozen_facts", "rust_target_client_floor"), "windows_8", "authority_observation_invalid"),
            (("observation", "toolchain", "ownership_assessment"), "product_callsite_provenance", "toolchain_observation_invalid"),
            (("observation", "same_host_system_dll", "signature_status"), "unknown", "same_host_dll_observation_invalid"),
            (("gates", "allowlist_expanded"), True, "gate_state_invalid"),
            (("gates", "composition_invoked"), True, "gate_state_invalid"),
            (("non_claims",), ["bogus"], "non_claims_invalid"),
        ):
            with self.subTest(path=path):
                document = self.document()
                target = document
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaisesRegex(GATE.EvidenceError, reason):
                    GATE.validate(document)

    def test_external_report_is_exactly_bound(self) -> None:
        document = self.document()
        report = GATE.expected_report(document)
        raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        document["external_report"]["sha256"] = GATE.sha256(raw)
        document["external_report"]["byte_length"] = len(raw)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_bytes(raw)
            self.assertTrue(GATE.validate(document, path)["report_bound"])
            tampered = copy.deepcopy(report)
            tampered["candidate_import_and_smoke"]["bcryptprimitives_import"]["symbols"] = ["Other"]
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(GATE.EvidenceError, "external_report_identity_drift"):
                GATE.validate(document, path)


if __name__ == "__main__":
    unittest.main()
