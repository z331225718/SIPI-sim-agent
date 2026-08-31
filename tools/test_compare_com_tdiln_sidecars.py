from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from tools.compare_com_tdiln_sidecars import compare_sidecars


def write_case(root: Path, case: int, vectors: dict[str, list[float]], applicable: bool = True) -> None:
    directory = root / f"case-{case}"
    directory.mkdir(parents=True)
    manifest: dict[str, object] = {"schema": "sipi.com.tdiln-array-sidecar.v1", "diagnostic_only": True, "tdiln_applicable": applicable, "case_index": case}
    if applicable:
        entries = {}
        for name, values in vectors.items():
            raw = struct.pack(f"<{len(values)}d", *values)
            (directory / f"{name}.f64le").write_bytes(raw)
            entries[name] = {"file": f"{name}.f64le", "dtype": "f64le", "shape": [len(values)], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        manifest["vectors"] = entries
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class SidecarComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.values = {name: [0.0, 0.25, -0.5] for name in ("time_s", "iln_pulse", "reference_pulse", "fitted_pulse", "pdf_axis", "pdf_probability")}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_matching_sidecars_pass(self) -> None:
        write_case(self.root / "matlab", 0, self.values)
        write_case(self.root / "rust", 0, self.values)
        report = compare_sidecars(self.root / "matlab", self.root / "rust", 1)
        self.assertEqual(report["status"], "passed_diagnostic")

    def test_exact_time_axis_rejects_one_bit_drift(self) -> None:
        write_case(self.root / "matlab", 0, self.values)
        drift = {name: list(values) for name, values in self.values.items()}
        drift["time_s"][1] = 0.25000000000000006
        write_case(self.root / "rust", 0, drift)
        self.assertEqual(compare_sidecars(self.root / "matlab", self.root / "rust", 1)["status"], "blocked")

    def test_waveform_drift_rejects(self) -> None:
        write_case(self.root / "matlab", 0, self.values)
        drift = {name: list(values) for name, values in self.values.items()}
        drift["iln_pulse"][2] = 1.0
        write_case(self.root / "rust", 0, drift)
        self.assertEqual(compare_sidecars(self.root / "matlab", self.root / "rust", 1)["status"], "blocked")

    def test_source_absence_requires_rust_inapplicable_manifest(self) -> None:
        write_case(self.root / "rust", 0, {}, applicable=False)
        self.assertEqual(compare_sidecars(self.root / "matlab", self.root / "rust", 1)["status"], "passed_diagnostic")

    def test_known_inapplicable_case_requires_both_sidecars_to_be_absent(self) -> None:
        report = compare_sidecars(
            self.root / "matlab",
            self.root / "rust",
            1,
            expected_applicability=(False,),
        )
        self.assertEqual(report["status"], "passed_diagnostic")
        write_case(self.root / "rust", 0, {}, applicable=False)
        self.assertEqual(
            compare_sidecars(
                self.root / "matlab",
                self.root / "rust",
                1,
                expected_applicability=(False,),
            )["status"],
            "blocked",
        )

    def test_rust_payload_hash_drift_rejects(self) -> None:
        write_case(self.root / "matlab", 0, self.values)
        write_case(self.root / "rust", 0, self.values)
        payload = self.root / "rust" / "case-0" / "iln_pulse.f64le"
        payload.write_bytes(payload.read_bytes()[:-1] + b"x")
        with self.assertRaises(ValueError):
            compare_sidecars(self.root / "matlab", self.root / "rust", 1)


if __name__ == "__main__":
    unittest.main()
