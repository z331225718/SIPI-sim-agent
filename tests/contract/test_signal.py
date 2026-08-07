from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import ContractViolation, SpectrumV1, WaveformV1, parse_spectrum, parse_waveform


def artifact_ref(relative_path="data.npy"):
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": "sipi.signal-samples.v1",
        "relative_path": relative_path,
        "mime_type": "application/octet-stream",
        "sha256": "c" * 64,
        "byte_length": 32,
        "producer": "fixture",
        "role": "data",
        "extensions": {},
    }


def port_map():
    return {
        "schema": "sipi.port-map.v1",
        "basis": "single_ended",
        "index_base": 0,
        "ports": [
            {"id": "p1", "external_index": 0, "kind": "signal", "polarity": 1, "extensions": {}},
            {"id": "gnd", "external_index": 1, "kind": "reference", "polarity": 1, "extensions": {}},
        ],
        "extensions": {},
    }


def time_axis():
    return {
        "schema": "sipi.axis.v1",
        "kind": "time",
        "unit": "s",
        "dtype": "float64",
        "length": 4,
        "monotonicity": "increasing",
        "uniform": True,
        "sample_location": "sample",
        "start": 0.0,
        "step": 0.1,
        "extensions": {},
    }


def frequency_axis():
    return {
        "schema": "sipi.axis.v1",
        "kind": "frequency",
        "unit": "Hz",
        "dtype": "float64",
        "length": 2,
        "monotonicity": "increasing",
        "uniform": True,
        "sample_location": "bin_center",
        "start": 1.0,
        "step": 1.0,
        "spectrum": {"sidedness": "single", "has_dc": False, "has_nyquist": False},
        "extensions": {},
    }


def channel(**changes):
    value = {"port_id": "p1", "signal_intent": "voltage", "polarity": 1, "reference": "gnd", "extensions": {}}
    value.update(changes)
    return value


def waveform(**changes):
    value = {
        "schema": "sipi.waveform.v1",
        "axis": time_axis(),
        "port_map": port_map(),
        "signal_kind": "voltage",
        "voltage_measurement": "loaded",
        "unit": "V",
        "data": artifact_ref(),
        "shape": {"samples": 4, "channels": 1},
        "channels": [channel()],
        "warmup_samples": 1,
        "trimming": {"leading_samples": 0, "trailing_samples": 1},
        "extensions": {},
    }
    value.update(changes)
    return value


def spectrum(**changes):
    value = {
        "schema": "sipi.spectrum.v1",
        "axis": frequency_axis(),
        "port_map": port_map(),
        "signal_kind": "voltage",
        "voltage_measurement": "single_ended",
        "unit": "V",
        "data": artifact_ref("spectrum.npy"),
        "shape": {"bins": 2, "channels": 1},
        "channels": [channel()],
        "fft": {"normalization": "amplitude", "window": "hann", "extensions": {}},
        "extensions": {},
    }
    value.update(changes)
    return value


class WaveformContractTests(unittest.TestCase):
    def test_good_waveform_parses_and_is_immutable(self):
        raw = waveform()
        model = parse_waveform(raw)
        self.assertIsInstance(model, WaveformV1)
        raw["shape"]["samples"] = 9
        self.assertEqual(model.to_wire()["shape"]["samples"], 4)

    def test_axis_and_shape_rules(self):
        with self.assertRaisesRegex(ContractViolation, "time"):
            parse_waveform(waveform(axis=frequency_axis()))
        with self.assertRaisesRegex(ContractViolation, "axis length"):
            parse_waveform(waveform(shape={"samples": 3, "channels": 1}))
        with self.assertRaisesRegex(ContractViolation, "channels"):
            parse_waveform(waveform(channels=[]))
        with self.assertRaisesRegex(ContractViolation, "channels length"):
            parse_waveform(waveform(shape={"samples": 4, "channels": 2}))

    def test_signal_kind_requirements(self):
        raw = waveform()
        del raw["voltage_measurement"]
        with self.assertRaisesRegex(ContractViolation, "voltage_measurement"):
            parse_waveform(raw)
        raw = waveform(signal_kind="current")
        with self.assertRaisesRegex(ContractViolation, "current_sign_convention"):
            parse_waveform(raw)

    def test_channel_rules(self):
        with self.assertRaisesRegex(ContractViolation, "undeclared port"):
            parse_waveform(waveform(channels=[channel(port_id="missing")]))
        with self.assertRaisesRegex(ContractViolation, "polarity"):
            parse_waveform(waveform(channels=[channel(polarity=-1)]))
        with self.assertRaisesRegex(ContractViolation, "itself"):
            parse_waveform(waveform(channels=[channel(reference="p1")]))
        with self.assertRaisesRegex(ContractViolation, "undeclared node"):
            parse_waveform(waveform(channels=[channel(reference="missing")]))

    def test_interval_rules(self):
        with self.assertRaisesRegex(ContractViolation, "within samples"):
            parse_waveform(waveform(effective_interval={"start_index": 3, "end_index": 5}))
        with self.assertRaisesRegex(ContractViolation, "must not exceed"):
            parse_waveform(waveform(warmup_samples=3, trimming={"leading_samples": 2, "trailing_samples": 1}))


class SpectrumContractTests(unittest.TestCase):
    def test_good_spectrum_parses(self):
        model = parse_spectrum(spectrum())
        self.assertIsInstance(model, SpectrumV1)

    def test_axis_and_shape_rules(self):
        with self.assertRaisesRegex(ContractViolation, "frequency"):
            parse_spectrum(spectrum(axis=time_axis()))
        with self.assertRaisesRegex(ContractViolation, "axis length"):
            parse_spectrum(spectrum(shape={"bins": 3, "channels": 1}))

    def test_fft_unknown_field_rejected(self):
        fft = spectrum()["fft"]
        fft["extra"] = True
        with self.assertRaises(ContractViolation):
            parse_spectrum(spectrum(fft=fft))


if __name__ == "__main__":
    unittest.main()
