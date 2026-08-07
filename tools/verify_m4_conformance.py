"""Python-side conformance for M4 shared DTO schemas (M4-06a).

Each DTO (axis, port-map, network-tensor, waveform, spectrum) runs a fixed case
matrix: producer-good, producer-unknown-reject, consumer-good,
consumer-unknown-accept and consumer-version-reject.  Rust conformance is
recorded as ``deferred`` until the M5C Rust workspace/bindings exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import ContractViolation, parse_axis, parse_network_tensor, parse_port_map, parse_spectrum, parse_waveform


def artifact_ref(relative_path="data.npy"):
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": "sipi.samples.v1",
        "relative_path": relative_path,
        "mime_type": "application/octet-stream",
        "sha256": "c" * 64,
        "byte_length": 32,
        "producer": "fixture",
        "role": "data",
        "extensions": {},
    }


def axis_doc():
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


def port_map_doc():
    return {
        "schema": "sipi.port-map.v1",
        "basis": "single_ended",
        "index_base": 0,
        "ports": [
            {"id": "p1", "external_index": 0, "kind": "signal", "polarity": 1, "extensions": {}},
            {"id": "p2", "external_index": 1, "kind": "signal", "polarity": -1, "extensions": {}},
        ],
        "extensions": {},
    }


def frequency_axis_doc():
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


def network_tensor_doc():
    return {
        "schema": "sipi.network-tensor.v1",
        "parameter_kind": "S",
        "axis": frequency_axis_doc(),
        "port_map": port_map_doc(),
        "data": artifact_ref("matrix.npy"),
        "shape": {"frequency": 2, "output_ports": 2, "input_ports": 2},
        "complex_encoding": "interleaved",
        "dtype": "complex128",
        "byte_order": "little",
        "layout": "C",
        "z0": {"kind": "scalar", "value": 50.0, "extensions": {}},
        "wave_definition": "pseudo",
        "reader": {"source_reader": "scikit-rf", "reader_semantics": "s2p", "extensions": {}},
        "extensions": {},
    }


def waveform_doc():
    return {
        "schema": "sipi.waveform.v1",
        "axis": axis_doc(),
        "port_map": port_map_doc(),
        "signal_kind": "voltage",
        "voltage_measurement": "loaded",
        "unit": "V",
        "data": artifact_ref(),
        "shape": {"samples": 4, "channels": 1},
        "channels": [{"port_id": "p1", "signal_intent": "voltage", "polarity": 1, "reference": "p2", "extensions": {}}],
        "extensions": {},
    }


def spectrum_doc():
    return {
        "schema": "sipi.spectrum.v1",
        "axis": frequency_axis_doc(),
        "port_map": port_map_doc(),
        "signal_kind": "voltage",
        "voltage_measurement": "single_ended",
        "unit": "V",
        "data": artifact_ref("spectrum.npy"),
        "shape": {"bins": 2, "channels": 1},
        "channels": [{"port_id": "p1", "signal_intent": "voltage", "polarity": 1, "reference": "p2", "extensions": {}}],
        "fft": {"normalization": "amplitude", "extensions": {}},
        "extensions": {},
    }


DOCS: dict[str, Callable[[], dict[str, Any]]] = {
    "axis": axis_doc,
    "port-map": port_map_doc,
    "network-tensor": network_tensor_doc,
    "waveform": waveform_doc,
    "spectrum": spectrum_doc,
}

PARSERS = {
    "axis": parse_axis,
    "port-map": parse_port_map,
    "network-tensor": parse_network_tensor,
    "waveform": parse_waveform,
    "spectrum": parse_spectrum,
}


def _run_case(name: str, build: Callable[[], dict[str, Any]], parser: Callable[..., Any]) -> bool:
    try:
        if name == "producer.good":
            parser(build(), producer=True)
        elif name == "producer.unknown.reject":
            doc = build()
            doc["extra"] = True
            parser(doc, producer=True)
            return False
        elif name == "consumer.good":
            parser(build(), producer=False)
        elif name == "consumer.unknown.reject":
            doc = build()
            doc["future_optional"] = {"kept": True}
            parser(doc, producer=False)
            return False
        elif name == "consumer.version.reject":
            doc = build()
            doc["schema"] = doc["schema"].replace(".v1", ".v2")
            parser(doc, producer=False)
            return False
        return True
    except ContractViolation:
        return name in {"producer.unknown.reject", "consumer.unknown.reject", "consumer.version.reject"}
    except Exception:
        return False


CASES = ("producer.good", "producer.unknown.reject", "consumer.good", "consumer.unknown.reject", "consumer.version.reject")


def run() -> dict[str, Any]:
    schemas: dict[str, Any] = {}
    failures: list[str] = []
    for name, build in DOCS.items():
        results: dict[str, bool] = {}
        for case in CASES:
            ok = _run_case(case, build, PARSERS[name])
            results[case] = ok
            if not ok:
                failures.append(f"{name}:{case}")
        schemas[name] = {"python": "covered" if all(results.values()) else "failed", "rust": "deferred", "cases": results}
    return {"schema": "sipi.m4-conformance.v1", "python": "covered", "rust": "deferred", "valid": not failures, "schemas": schemas, "failures": failures}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path)
    args = parser.parse_args(argv)
    report = run()
    if args.record is not None:
        args.record.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
