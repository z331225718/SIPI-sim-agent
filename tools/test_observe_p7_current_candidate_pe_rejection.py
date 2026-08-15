"""Tests for the external-only P7 current-candidate PE diagnosis observer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_pe_diagnosis", ROOT / "tools" / "observe_p7_current_candidate_pe_rejection.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def image(*, machine: int = 0x8664, delay: bool = False, import_name: bytes = b"kernel32.dll\0") -> bytes:
    data = bytearray(0x800)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    coff, optional, section = 0x84, 0x98, 0x188
    struct.pack_into("<H", data, coff, machine)
    struct.pack_into("<H", data, coff + 2, 1)
    struct.pack_into("<H", data, coff + 16, 0xF0)
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<I", data, optional + 108, 16)
    struct.pack_into("<II", data, optional + 112 + 8, 0x1000, 40)
    if delay:
        struct.pack_into("<II", data, optional + 112 + 13 * 8, 0x1200, 32)
    struct.pack_into("<I", data, section + 8, 0x400)
    struct.pack_into("<I", data, section + 12, 0x1000)
    struct.pack_into("<I", data, section + 16, 0x400)
    struct.pack_into("<I", data, section + 20, 0x400)
    struct.pack_into("<I", data, 0x400 + 12, 0x1100)
    data[0x500:0x500 + len(import_name)] = import_name
    return bytes(data)


class P7PeDiagnosisTests(unittest.TestCase):
    def test_classifies_normal_import_against_fixed_policy(self) -> None:
        record = GATE.classify(image(import_name=b"bcryptprimitives.dll\0"), ["kernel32.dll"], ["python"])
        self.assertEqual(record["rejection_classification"], "normal_import_disallowed")
        self.assertEqual(record["disallowed_import_dlls"], ["bcryptprimitives.dll"])
        self.assertEqual(record["forbidden_token_import_dlls"], [])

    def test_classifies_other_layout_rejection_categories(self) -> None:
        self.assertEqual(GATE.classify(image(machine=0x14C), [], [])["rejection_classification"], "wrong_machine")
        self.assertEqual(GATE.classify(image(delay=True), [], [])["rejection_classification"], "delay_import_directory_present")
        self.assertEqual(GATE.classify(b"not-a-pe", [], [])["rejection_classification"], "invalid_pe")
        self.assertEqual(
            GATE.classify(image(import_name=b"bad/name.dll\0"), [], [])["rejection_classification"],
            "malformed_import_name",
        )

    def test_two_fresh_materializations_must_match_and_bind_identity(self) -> None:
        payload = image(import_name=b"bcryptprimitives.dll\0")
        policy = {
            "schema": "sipi.release-layout-policy.v1", "platform": "windows-x86_64",
            "expectedExecutable": "sipi.exe", "requiredFiles": ["sipi.exe"], "optionalFiles": [],
            "normalImportDllAllowlist": ["kernel32.dll"], "forbiddenImportDllTokens": ["python"], "smoke": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory)
            first, second, policy_path = external / "first.exe", external / "second.exe", external / "policy.json"
            first.write_bytes(payload)
            second.write_bytes(payload)
            policy_bytes = json.dumps(policy, sort_keys=True).encode()
            policy_path.write_bytes(policy_bytes)
            with patch.object(GATE, "EXPECTED_EXECUTABLE_BYTES", len(payload)), patch.object(GATE, "EXPECTED_EXECUTABLE_SHA256", GATE.sha256(payload)), patch.object(GATE, "EXPECTED_POLICY_SHA256", GATE.sha256(policy_bytes)):
                report = GATE.observe(first, second, policy_path)
            self.assertEqual(report["fresh_materializations"], 2)
            self.assertEqual(report["observation"]["rejection_classification"], "normal_import_disallowed")
            with self.assertRaisesRegex(GATE.ObservationError, "fresh_executable_sources_not_distinct"):
                with patch.object(GATE, "EXPECTED_EXECUTABLE_BYTES", len(payload)), patch.object(GATE, "EXPECTED_EXECUTABLE_SHA256", GATE.sha256(payload)), patch.object(GATE, "EXPECTED_POLICY_SHA256", GATE.sha256(policy_bytes)):
                    GATE.observe(first, first, policy_path)


if __name__ == "__main__":
    unittest.main()
