#!/usr/bin/env python3
"""Verify the fixed-fixture M5B S2P-to-Link handoff across both repositories.

This is an explicit cross-repository integration gate, not a root-suite test.
It keeps the legacy PyBERT S-parameter resolver as the sole numeric producer,
passes its DTO through SIPI's M4 admission, then invokes PyBERT's ``sim-native``
CLI.  The resulting report deliberately makes no claim that SIPI resolves or
independently verifies S-parameter conditioning, IFFT, or termination.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np


TARGET_ROOT = Path(__file__).resolve().parents[1]
for package in ("sipi-contracts", "sipi-adapters"):
    sys.path.insert(0, str(TARGET_ROOT / "packages" / package / "src"))

from sipi_adapters import PyBertResolvedChannelAdapter  # noqa: E402
from sipi_contracts import parse_backend_execution_request  # noqa: E402


SENTINEL = {
    "kind": "external_model",
    "value": {"kind": "sipi_resolved_channel", "capability": "adapter_injected_v1"},
}
RTOL = 2.0e-5
ATOL = 2.5e-7


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _network() -> dict[str, Any]:
    return {
        "schema": "sipi.network-tensor.v1",
        "parameter_kind": "S",
        "axis": {
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
        },
        "port_map": {
            "schema": "sipi.port-map.v1",
            "basis": "single_ended",
            "index_base": 0,
            "ports": [
                {"id": "p1", "external_index": 0, "kind": "signal", "polarity": 1, "extensions": {}},
                {"id": "p2", "external_index": 1, "kind": "signal", "polarity": -1, "extensions": {}},
            ],
            "extensions": {},
        },
        "data": {
            "schema": "sipi.artifact-ref.v1",
            "content_schema": "sipi.network-matrix.v1",
            "relative_path": "external/s2p-network-matrix.npy",
            "mime_type": "application/octet-stream",
            "sha256": "0" * 64,
            "byte_length": 128,
            "producer": "m5b-s2p-link-parity-fixture",
            "role": "data",
            "extensions": {},
        },
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


def _policy() -> dict[str, Any]:
    return {
        "schema": "sipi.channel-resolution-policy.v1",
        "reader_semantics": "scikit-rf s2p",
        "port_selection": [
            {"port_id": "p1", "role": "signal", "extensions": {}},
            {"port_id": "p2", "role": "signal", "extensions": {}},
        ],
        "termination": "match",
        "interpolation": {"kind": "none", "extensions": {}},
        "dc": {"method": "none", "extensions": {}},
        "causality": {"method": "none", "extensions": {}},
        "ifft": {"extensions": {}},
        "normalization": {"fft": "none", "extensions": {}},
        "output": {"signal_intent": "voltage", "current_to_voltage_sign": 1, "extensions": {}},
        "extensions": {},
    }


def _fixture_request(s2p_path: Path):
    from pybert_web.models import ChannelConfig, SimConfig, SimulateRequest, TxConfig

    return SimulateRequest(
        tx=TxConfig(pn_mag=0.0, rn=0.0, rj_ui=0.0, dj_ui=0.0, dcd_ui=0.0),
        channel=ChannelConfig(
            mode="sparam",
            sp_file=str(s2p_path),
            source_impedance=50.0,
            load_impedance=50.0,
            use_window=True,
            enforce_passivity=False,
            use_low_frequency_extrapolation=False,
        ),
        config=SimConfig(
            bit_rate=10.3125e9,
            nbits=1000,
            nspui=8,
            eye_bits=1000,
            pattern="prbs7",
            seed=17,
            f_max=40.0e9,
            f_step=10.0e6,
            statistical_time_points=32,
            statistical_ber_levels=[1.0e-5],
        ),
    )


def _backend_request(payload: dict[str, Any]):
    return parse_backend_execution_request(
        {
            "schema": "sipi.backend-execution-request.v1",
            "run_id": "m5b-s2p-link-parity",
            "analysis_id": "fixed-s2p-handoff",
            "attempt_id": "attempt-1",
            "backend_execution_id": "candidate-1",
            "role": "candidate",
            "engine_instance_id": "pybert-native-cross-repo",
            "bundle_hash": "sha256:cross-repository-integration-gate",
            "operation": "link.simulate.v1",
            "payload_schema": "sipi.pybert-resolved-channel-request.v1",
            "payload": payload,
            "bound_inputs": {},
            "resource_limits": {
                "enforcement": "monitor",
                "wall_time_s": None,
                "cpu_time_s": None,
                "memory_bytes": None,
                "process_count": None,
                "artifact_bytes": None,
            },
            "artifact_policy": {},
            "randomness": {},
            "selection_hash": "m5b-s2p-link-parity-fixed-fixture",
        }
    )


def _lineage_check(dto: dict[str, Any], resolved_input: dict[str, Any], legacy_impulse: np.ndarray) -> dict[str, Any]:
    dt = float(dto["sample_interval_s"])
    recovered = np.asarray(
        resolved_input["channel"]["value"]["impulseResponseVoltsPerSecond"], dtype=np.float64
    ) * dt
    # JSON's float division/multiplication round-trip can differ by an ULP;
    # this is a serialization check, not a second channel calculation.
    exact = bool(np.allclose(recovered, legacy_impulse, rtol=1.0e-15, atol=1.0e-24))
    return {
        "source_discrete_impulse_hash": dto["source_discrete_impulse_hash"],
        "external_impulse_hash": dto["impulse_hash"],
        "sample_interval_s": dt,
        "recovered_discrete_shape": list(recovered.shape),
        "legacy_discrete_shape": list(legacy_impulse.shape),
        "recovered_discrete_finite": bool(np.isfinite(recovered).all()),
        "legacy_discrete_finite": bool(np.isfinite(legacy_impulse).all()),
        "recovered_equals_legacy": exact,
        "max_abs_error": float(np.max(np.abs(recovered - legacy_impulse), initial=0.0)),
        "passed": exact,
    }


def _run_sim_native(pybert_root: Path, input_path: Path, output_dir: Path) -> None:
    environment = dict(os.environ)
    source_path = str(pybert_root / "src")
    environment["PYTHONPATH"] = source_path + os.pathsep + environment.get("PYTHONPATH", "")
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pybert.cli import cli; cli()",
            "sim-native",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=pybert_root,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            "sim-native failed with exit code "
            f"{completed.returncode}:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def _comparison(reference_arrays, candidate_arrays, reference_metrics, candidate_metrics) -> dict[str, Any]:
    from pybert.engine.compare import compare_backend_results
    from pybert.engine.api import BackendRunResult

    arrays = compare_backend_results(
        BackendRunResult(metadata={}, arrays=reference_arrays, diagnostics={}),
        BackendRunResult(metadata={}, arrays=candidate_arrays, diagnostics={}),
        rtol=RTOL,
        atol=ATOL,
    )
    metrics = compare_backend_results(
        BackendRunResult(metadata=reference_metrics, arrays={}, diagnostics={}),
        BackendRunResult(metadata=candidate_metrics, arrays={}, diagnostics={}),
        rtol=RTOL,
        atol=ATOL,
    )
    return {
        "schema": "sipi.m5b-link-array-and-metric-compare.v1",
        "passed": bool(arrays["passed"] and metrics["passed"]),
        "array_compare": arrays,
        "metric_compare": metrics,
    }


def _error_count_check(reference_owner: Any, native_metrics: dict[str, Any]) -> dict[str, Any]:
    reference = int(reference_owner.n_errs_dfe)
    candidate = native_metrics.get("ber_error_count")
    exact = isinstance(candidate, (int, float)) and not isinstance(candidate, bool) and int(candidate) == reference
    return {
        "reference": reference,
        "candidate": candidate,
        "comparison": "exact integer",
        "passed": exact,
    }


def verify(pybert_root: Path, s2p_path: Path, source_commit: str) -> dict[str, Any]:
    source_root = pybert_root.resolve()
    s2p_path = s2p_path.resolve()
    if not s2p_path.is_file() or not s2p_path.is_relative_to(source_root):
        raise ValueError("--s2p must be a tracked file under --pybert-root")
    sys.path.insert(0, str(source_root / "src"))

    from pybert import __version__ as pybert_version
    from pybert.engine.api import BackendRunResult
    from pybert.utility.sparam import export_external_channel_resolution
    from pybert_web.engine_adapter import adapt_native_result_for_web, to_simulation_input_v1
    from pybert_web.simulation import _build_pybert, _extract_results

    request = _fixture_request(s2p_path)
    reference_owner = _build_pybert(request)
    network = _network()
    policy = _policy()
    dto = export_external_channel_resolution(
        reference_owner,
        network=network,
        resolution_policy=policy,
        package_version=pybert_version,
        build_id=source_commit,
    )
    reference_owner.simulate(initial_run=True, update_plots=False, aborted_sim=lambda: False, on_stage=lambda _stage, _data: None)
    reference_metadata, _ = _extract_results(reference_owner)
    legacy_impulse = np.asarray(reference_owner.chnl_h, dtype=np.float64)

    simulation_input = to_simulation_input_v1(request, "m5b-s2p-link-parity")
    simulation_input["channel"] = SENTINEL
    simulation_input["externalModels"] = []
    simulation_input["legacyOptions"] = {}
    payload = {
        "schema": "sipi.pybert-resolved-channel-request.v1",
        "simulation_input": simulation_input,
        "network": network,
        "resolution_policy": policy,
        "external_resolution": dto,
    }
    resolved_input, provenance = PyBertResolvedChannelAdapter()._resolve_payload(_backend_request(payload))
    unit_recovery = _lineage_check(dto, resolved_input, legacy_impulse)

    with tempfile.TemporaryDirectory(prefix="m5b-s2p-link-") as temporary:
        workdir = Path(temporary)
        input_path = workdir / "resolved-input.json"
        output_dir = workdir / "native-output"
        input_path.write_text(json.dumps(resolved_input, sort_keys=True), encoding="utf-8")
        _run_sim_native(source_root, input_path, output_dir)
        native_meta = json.loads((output_dir / "meta.json").read_text(encoding="utf-8"))
        with np.load(output_dir / "arrays.npz", allow_pickle=False) as archive:
            native_arrays = {name: np.asarray(archive[name]) for name in archive.files}

    candidate_raw = BackendRunResult(
        metadata=dict(native_meta["backend_metadata"]),
        arrays=native_arrays,
        diagnostics={"backend": "rust", "fixture": "m5b-s2p-link-parity"},
    )
    candidate = adapt_native_result_for_web(
        candidate_raw,
        request,
        channel_intent="m4_external_sparam_handoff",
    )
    comparison = _comparison(
        {
            "parity_channel_impulse_v_per_v": legacy_impulse,
            "parity_channel_output_v": np.asarray(reference_owner.chnl_out, dtype=np.float64),
            "parity_rx_input_v": np.asarray(reference_owner.rx_in, dtype=np.float64),
            "parity_ctle_output_v": np.asarray(reference_owner.ctle_out, dtype=np.float64),
            "parity_dfe_output_v": np.asarray(reference_owner.dfe_out, dtype=np.float64),
            "parity_dfe_decisions": np.asarray(reference_owner.dfe_decisions, dtype=np.float64),
            "parity_dfe_clock_times_s": np.asarray(reference_owner.clock_times, dtype=np.float64),
        },
        {
            "parity_channel_impulse_v_per_v": np.asarray(native_arrays["channel_impulse_v_per_v"], dtype=np.float64),
            "parity_channel_output_v": np.asarray(native_arrays["channel_output_v"], dtype=np.float64),
            "parity_rx_input_v": np.asarray(native_arrays["rx_input_v"], dtype=np.float64),
            "parity_ctle_output_v": np.asarray(native_arrays["ctle_output_v"], dtype=np.float64),
            "parity_dfe_output_v": np.asarray(native_arrays["dfe_output_v"], dtype=np.float64),
            "parity_dfe_decisions": np.asarray(native_arrays["dfe_decisions"], dtype=np.float64),
            "parity_dfe_clock_times_s": np.asarray(native_arrays["dfe_clock_times_s"], dtype=np.float64),
        },
        {
            "ber": reference_metadata["ber"],
            "sampled_eye": reference_metadata["sampled_eye"],
            "jitter": reference_metadata["jitter"],
        },
        {
            "ber": candidate.metadata["ber"],
            "sampled_eye": candidate.metadata["sampled_eye"],
            "jitter": candidate.metadata["jitter"],
        },
    )
    native_metrics = native_meta["backend_metadata"]["metrics"]
    error_count = _error_count_check(reference_owner, native_metrics)
    resolution_report = provenance["channel_resolution_report"]
    return {
        "schema": "sipi.m5b-s2p-link-handoff-parity.v1",
        "passed": bool(unit_recovery["passed"] and comparison["passed"] and error_count["passed"]),
        "scope": "fixed S2P fixture: legacy Python external resolution -> DTO unit/lineage -> M4 identity/sign admission -> native Link",
        "non_claims": [
            "M4 does not calculate or independently verify S-parameter conditioning, IFFT, termination, or resampling.",
            "This is not ADS, AMI, S4P, or general S-parameter certified parity.",
        ],
        "fixture": {
            "source_relative_path": s2p_path.relative_to(source_root).as_posix(),
            "source_file_sha256": _file_sha256(s2p_path),
            "source_commit": source_commit,
            "request_hash": _canonical_sha256(request.model_dump(mode="json")),
        },
        "lineage": {
            "network_hash": dto["source_network_hash"],
            "policy_hash": dto["policy_hash"],
            "source_channel_file_sha256": dto["source_channel_file_sha256"],
            "legacy_channel_config_hash": dto["legacy_channel_config_hash"],
            "producer": dto["producer"],
            "unit_recovery": unit_recovery,
            "m4_channel_resolution_report": resolution_report,
            "resolved_simulation_input_hash": provenance["resolved_simulation_input_hash"],
            "effective_native_input_hash": _canonical_sha256(resolved_input),
        },
        "comparison": comparison,
        "error_count": error_count,
        "presentation_metric_observations": {
            "status": "not_compared",
            "reason": "M5B-03 validates Link arrays and shared BER/jitter metrics; legacy visual-eye and native statistical-eye widths are distinct product-presentation contracts owned by M5B-05.",
            "legacy_visual_eye_width_ps": reference_metadata["eye_width_ps"],
            "native_statistical_eye_width_ps": candidate.metadata["eye_width_ps"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pybert-root", type=Path, required=True)
    parser.add_argument("--s2p", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.pybert_root, args.s2p, args.source_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(args.output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
