"""Unit tests for the observer-only matched-channel CLI harness."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("channel_cli_compare", ROOT / "tools" / "compare_channel_s2p_matched_cli.py")
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class ChannelCliComparatorTests(unittest.TestCase):
    source = b"# Hz S RI R 50.0\n0 0 0 1 0 1 0 0 0\n100000000 0 0 1 0 1 0 0 0\n"

    def response(self) -> bytes:
        result = {
            "schema": HARNESS.RESULT_SCHEMA,
            "input_byte_length": len(self.source),
            "input_sha256": hashlib.sha256(self.source).hexdigest(),
            "one_sided_sample_count": 201,
            "frequency_step_hz": 100_000_000.0,
            "reference_impedance_ohms": 50.0,
            "kernel_sample_count": 400,
            "sample_interval_seconds": 2.5e-11,
            "gain_v_per_v": [0.0] * 400,
            "evaluation_scope": "matched_s21_periodic_kernel_only",
            "external_profile_acceptance": "caller_input_unattested",
        }
        envelope = {
            "schema": "sipi.cli.response.v1",
            "protocol": 1,
            "command": "channel",
            "request_id": None,
            "status": "ok",
            "result": result,
            "diagnostic_count": 0,
        }
        return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"

    def test_request_is_single_canonical_json_document(self) -> None:
        request = HARNESS.build_request(self.source)
        self.assertEqual(json.loads(request), {
            "schema": HARNESS.REQUEST_SCHEMA,
            "source": {"encoding": "utf-8", "text": self.source.decode("utf-8")},
        })
        with self.assertRaises(HARNESS.CliComparatorError):
            HARNESS.build_request(b"\xff")

    def test_accepts_only_the_expected_success_shape(self) -> None:
        response, gain = HARNESS.parse_cli_response(self.response(), self.source, 2.5e-11)
        self.assertEqual(response["command"], "channel")
        self.assertEqual(len(gain), 400)
        self.assertEqual(gain[0], 0.0)

    def test_rejects_multiple_lines_duplicate_fields_and_unattested_drift(self) -> None:
        cases = [
            self.response() + b"{}\n",
            b'{"schema":"one","schema":"two"}\n',
        ]
        value = json.loads(self.response())
        value["result"]["external_profile_acceptance"] = "accepted"
        cases.append(json.dumps(value).encode("utf-8") + b"\n")
        for payload in cases:
            with self.subTest(payload=payload[:20]):
                with self.assertRaises(HARNESS.CliComparatorError):
                    HARNESS.parse_cli_response(payload, self.source, 2.5e-11)


if __name__ == "__main__":
    unittest.main()
