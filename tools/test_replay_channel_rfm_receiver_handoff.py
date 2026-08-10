"""Unit tests for the external-only RFM receiver handoff gate."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_channel_rfm_receiver_handoff as handoff  # noqa: E402


def manifest(waveform: Path, bits: Path) -> dict:
    return {
        "schema": "sipi.channel.rfm-observer-sidecars.v1",
        "response": {
            "schema": "agent-spice.rfm-response.v1",
            "fft_size": 1024,
            "frequency_bins": 513,
            "sample_interval_seconds": 1.0e-12,
            "input_ports": [1],
            "output_ports": [2],
            "producer_executable_sha256": handoff.ENGINE_SHA256,
            "producer_rfm_sha256": handoff.RFM["content_sha256"],
        },
        "current_sha256": "0" * 64,
        "waveform_sha256": hashlib.sha256(waveform.read_bytes()).hexdigest(),
        "reference_bits_sha256": hashlib.sha256(bits.read_bytes()).hexdigest(),
    }


class ObserverSidecarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="sipi-rfm-handoff-test-")
        self.root = Path(self.temporary.name)
        self.waveform = self.root / "waveform.f64le"
        self.bits = self.root / "bits.bin"
        self.waveform.write_bytes(b"\0" * handoff.WAVEFORM_BYTES)
        self.bits.write_bytes(bytes(1 if index % 2 == 0 else 0 for index in range(128)))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_validated_sidecars_are_bounded_and_hash_pinned(self) -> None:
        result = handoff._validate_observer_sidecars(
            directory=self.root,
            waveform_path=self.waveform,
            bits_path=self.bits,
            metadata=manifest(self.waveform, self.bits),
        )
        self.assertEqual(result["reference_bits_sha256"], handoff.BITS_SHA256)

    def test_wrong_length_hash_metadata_and_path_escape_are_rejected(self) -> None:
        bad = manifest(self.waveform, self.bits)
        bad["unexpected"] = True
        with self.assertRaises(ValueError):
            handoff._validate_observer_sidecars(
                directory=self.root, waveform_path=self.waveform, bits_path=self.bits, metadata=bad
            )
        self.waveform.write_bytes(b"\0" * 8)
        with self.assertRaises(ValueError):
            handoff._validate_observer_sidecars(
                directory=self.root,
                waveform_path=self.waveform,
                bits_path=self.bits,
                metadata=manifest(self.waveform, self.bits),
            )
        outside = Path(tempfile.gettempdir()) / "sipi-rfm-outside-sidecar.bin"
        outside.write_bytes(b"\0" * handoff.WAVEFORM_BYTES)
        try:
            with self.assertRaises(ValueError):
                handoff._validate_observer_sidecars(
                    directory=self.root,
                    waveform_path=outside,
                    bits_path=self.bits,
                    metadata=manifest(outside, self.bits),
                )
        finally:
            outside.unlink(missing_ok=True)

    def test_observer_program_does_not_import_a_retained_receiver(self) -> None:
        self.assertIn("current_driven_voltage_response", handoff.OBSERVER_PROGRAM)
        self.assertNotIn("compare_current_driven_receivers", handoff.OBSERVER_PROGRAM)
        self.assertNotIn("RustSimulationBackend", handoff.OBSERVER_PROGRAM)

    def test_policy_is_the_hash_pinned_handoff_contract(self) -> None:
        policy = handoff._load_policy()
        self.assertEqual(policy["profile_id"], handoff.PROFILE)
        self.assertEqual(policy["required_replays"], 2)


if __name__ == "__main__":
    unittest.main()
