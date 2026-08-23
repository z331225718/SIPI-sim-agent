"""Focused custody tests for the shared PB replay helpers."""

from __future__ import annotations

import sys
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pb_03_replay_common as common  # noqa: E402
import verify_pb_03_python_oracle_18_branch as verify_18  # noqa: E402
import verify_pb_03_python_oracle_matrix as verify_matrix  # noqa: E402
import verify_pb_04_05_python_external as verify_external  # noqa: E402


class ReplayCommonTests(unittest.TestCase):
    @staticmethod
    def _write_pe(path: Path, *, timestamp: int = 0x12345678, guid: bytes = b"0123456789abcdef", repro: bytes = b"repro") -> None:
        payload = bytearray(0x600)
        payload[:2] = b"MZ"
        struct.pack_into("<I", payload, 0x3C, 0x80)
        payload[0x80:0x84] = b"PE\0\0"
        coff = 0x84
        struct.pack_into("<HHIIIHH", payload, coff, 0x8664, 1, timestamp, 0, 0, 0xF0, 0x2022)
        optional = coff + 20
        struct.pack_into("<H", payload, optional, 0x20B)
        struct.pack_into("<I", payload, optional + 108, 16)
        debug_directory = optional + 112 + 6 * 8
        struct.pack_into("<II", payload, debug_directory, 0x1000, 56)
        section = optional + 0xF0
        payload[section : section + 8] = b".rdata\0\0"
        struct.pack_into("<IIII", payload, section + 8, 0x400, 0x1000, 0x400, 0x200)
        codeview = b"RSDS" + guid + struct.pack("<I", 1) + b"sipi_pybert_direct.pdb\0"
        payload[0x300 : 0x300 + len(codeview)] = codeview
        payload[0x380 : 0x380 + len(repro)] = repro
        struct.pack_into("<IIHHIIII", payload, 0x200, 0, timestamp, 1, 0, 2, len(codeview), 0x1100, 0x300)
        struct.pack_into("<IIHHIIII", payload, 0x21C, 0, timestamp + 1, 1, 0, 16, len(repro), 0x1180, 0x380)
        path.write_bytes(payload)

    def test_build_summary_has_closed_keys_and_binary_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "candidate.bin"
            self._write_pe(binary)
            summary = common.build_summary(
                {"exit_code": 0, "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64, "unexpected": True},
                binary,
            )
        self.assertEqual(set(summary), {"exit_code", "stdout_sha256", "stderr_sha256", "binary_sha256", "binary_custody"})
        self.assertEqual(len(summary["binary_sha256"]), 64)
        self.assertEqual(summary["binary_custody"]["schema"], "sipi.windows-pe-replay-custody.v1")
        self.assertEqual(summary["binary_custody"]["normalization"]["changed_byte_count"], 28)

    def test_normalized_fields_may_differ_but_unmasked_bytes_may_not(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first_path = Path(temporary) / "first.exe"
            second_path = Path(temporary) / "second.exe"
            self._write_pe(first_path)
            self._write_pe(second_path, timestamp=0x87654321, guid=b"fedcba9876543210")
            first = common.windows_pe_replay_custody(first_path)
            second = common.windows_pe_replay_custody(second_path)
            self.assertEqual(common.compare_windows_pe_custody(first, second), [])
            mutated = bytearray(second_path.read_bytes())
            mutated[0x450] ^= 0x01
            second_path.write_bytes(mutated)
            changed = common.windows_pe_replay_custody(second_path)
            self.assertIn("canonical PE digests differ across fresh runs", common.compare_windows_pe_custody(first, changed))

    def test_repro_payload_drift_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first_path = Path(temporary) / "first.exe"
            second_path = Path(temporary) / "second.exe"
            self._write_pe(first_path)
            self._write_pe(second_path, repro=b"changed")
            first = common.windows_pe_replay_custody(first_path)
            second = common.windows_pe_replay_custody(second_path)
            self.assertIn("IMAGE_DEBUG_TYPE_REPRO payload digests differ across fresh runs", common.compare_windows_pe_custody(first, second))

    def test_absent_repro_policy_is_not_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "candidate.exe"
            self._write_pe(binary)
            custody = common.windows_pe_replay_custody(binary)
            custody["repro_entry"] = {"present": False, "debug_directory_index": None, "bytes": 0, "raw_sha256": None}
            self.assertEqual(common.windows_pe_repro_policy(custody, custody), "not_present")

    def test_aggregate_non_claim_text_matches_canonical_gate(self) -> None:
        for name in ("aggregate_pb_03_python_oracle_matrix.py", "aggregate_pb_04_05_python_external.py"):
            text = (Path(__file__).with_name(name)).read_text(encoding="utf-8")
            self.assertIn("Raw PE digests may differ", text)
            self.assertIn("canonical digest, profile/normalization shape, or REPRO payload drift blocks", text)
            self.assertNotIn("differing binary digests block aggregation", text)

    def test_raw_custody_split_is_rejected_by_all_verifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "candidate.exe"
            self._write_pe(binary)
            build = common.build_summary({"exit_code": 0, "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64}, binary)
            build["binary_sha256"] = "f" * 64
            for verifier in (verify_18, verify_matrix, verify_external):
                errors: list[str] = []
                verifier.verify_build(build, errors, "split")
                self.assertTrue(any("raw binary/custody digest split" in error for error in errors), verifier.__name__)

    def test_malformed_debug_and_mutated_ranges_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "candidate.exe"
            self._write_pe(binary)
            custody = common.windows_pe_replay_custody(binary)
            pe32 = dict(custody)
            pe32["profile"] = "pe32"
            self.assertTrue(common.validate_windows_pe_replay_custody(pe32))
            mutated = dict(custody)
            mutated["normalization"] = dict(custody["normalization"])
            mutated["normalization"]["ranges"] = list(custody["normalization"]["ranges"]) + [dict(custody["normalization"]["ranges"][0])]
            self.assertTrue(common.validate_windows_pe_replay_custody(mutated))
            missing_raw = dict(custody)
            missing_raw["raw_sha256"] = None
            self.assertTrue(common.validate_windows_pe_replay_custody(missing_raw))
            forged_raw = dict(custody)
            forged_raw["raw_sha256"] = "f" * 63
            self.assertTrue(common.validate_windows_pe_replay_custody(forged_raw))
            malformed = bytearray(binary.read_bytes())
            malformed[0x200 + 12 : 0x200 + 16] = struct.pack("<I", 99)
            binary.write_bytes(malformed)
            with self.assertRaises(ValueError):
                common.windows_pe_replay_custody(binary)
            self._write_pe(binary)
            malformed = bytearray(binary.read_bytes())
            malformed[0x200 + 24 : 0x200 + 28] = struct.pack("<I", 0x100)
            binary.write_bytes(malformed)
            with self.assertRaises(ValueError):
                common.windows_pe_replay_custody(binary)
            self._write_pe(binary)
            malformed = bytearray(binary.read_bytes())
            malformed[0x200 + 24 : 0x200 + 28] = struct.pack("<I", 0x5F0)
            binary.write_bytes(malformed)
            with self.assertRaises(ValueError):
                common.windows_pe_replay_custody(binary)
            self._write_pe(binary)
            malformed = bytearray(binary.read_bytes())
            malformed[0x200 + 24 : 0x200 + 28] = struct.pack("<I", 0x310)
            binary.write_bytes(malformed)
            with self.assertRaises(ValueError):
                common.windows_pe_replay_custody(binary)
            self._write_pe(binary)
            malformed = bytearray(binary.read_bytes())
            malformed[0x200 + 20 : 0x200 + 24] = struct.pack("<I", 0x1001)
            binary.write_bytes(malformed)
            with self.assertRaises(ValueError):
                common.windows_pe_replay_custody(binary)
            self._write_pe(binary)
            malformed = bytearray(binary.read_bytes())
            struct.pack_into("<H", malformed, 0x84, 0x14C)
            binary.write_bytes(malformed)
            with self.assertRaises(ValueError):
                common.windows_pe_replay_custody(binary)
            self._write_pe(binary)
            malformed = bytearray(binary.read_bytes())
            struct.pack_into("<H", malformed, 0x84 + 18, 0x0000)
            binary.write_bytes(malformed)
            with self.assertRaises(ValueError):
                common.windows_pe_replay_custody(binary)
            self._write_pe(binary)
            malformed = bytearray(binary.read_bytes())
            malformed[0x200 + 12 : 0x200 + 16] = struct.pack("<I", 2)
            malformed[0x300:0x304] = b"BAD!"
            binary.write_bytes(malformed)
            with self.assertRaises(ValueError):
                common.windows_pe_replay_custody(binary)
            malformed[:2] = b"NO"
            binary.write_bytes(malformed)
            with self.assertRaises(ValueError):
                common.windows_pe_replay_custody(binary)

    def test_run_command_clears_wrappers_and_sets_rustc(self) -> None:
        executable = Path(sys.executable)
        with patch.object(common.subprocess, "run") as run:
            run.return_value = common.subprocess.CompletedProcess([], 0, b"", b"")
            common.run_command(
                ["cargo", "--version"],
                Path.cwd(),
                1,
                {"cargo": executable, "rustc": executable},
            )
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["RUSTC"], str(executable))
        self.assertNotIn("RUSTC_WRAPPER", environment)
        self.assertNotIn("RUSTC_WORKSPACE_WRAPPER", environment)


if __name__ == "__main__":
    unittest.main()
