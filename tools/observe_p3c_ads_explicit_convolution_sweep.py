"""External-only ADS sweep for explicit P3C convolution grid candidates.

This tool compares ADS's existing adaptive oracle with a small, fixed set of
explicit `ImpMaxFreq`/`ImpDeltaFreq` declarations.  It never runs product code
and retains only a canonical hash-only report outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import struct
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools" / "run_p3c_external_ads_prbs9_reference.py"
SOURCE_NAME = "channel_gen5_highloss.s4p"
SOURCE_LENGTH = 1834156
SOURCE_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"
FMAX_HZ = 40_000_000_000.0
# ADS begins its adaptive impulse search from a short response and doubles it.
# This finite profile samples the useful smaller orders before the longer guards.
GRID_LENGTHS = (512, 1024, 2048, 4096, 8192, 16384)
WAVEFORM_NRMSE_LIMIT = 0.01


class SweepError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_external(path: Path, *, kind: str) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise SweepError(f"{kind}_must_be_outside_repository")


def load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("p3c_ads_sweep_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise SweepError("runner_load_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def delta_frequency_hz(grid_length: int) -> float:
    if grid_length not in GRID_LENGTHS or grid_length % 2:
        raise SweepError("grid_length_not_allowlisted")
    return FMAX_HZ / (grid_length // 2)


def build_explicit_netlist(runner: Any, *, grid_length: int) -> str:
    delta_hz = delta_frequency_hz(grid_length)
    netlist = runner.build_netlist(runner.prbs9_period() * runner.PERIODS, edge_rise_fall_seconds=1.0e-16)
    original = 'ImpLFEOn=yes ImpApprox=no '
    replacement = (
        "ImpLFEOn=yes ImpApprox=no "
        f"ImpMaxFreq={FMAX_HZ:.17g} Hz ImpDeltaFreq={delta_hz:.17g} Hz "
    )
    if original not in netlist or netlist.count(original) != 1:
        raise SweepError("transient_controller_surface_unexpected")
    netlist = netlist.replace(original, replacement)
    runner.assert_netlist_isolated(netlist)
    required = (
        f"ImpMaxFreq={FMAX_HZ:.17g} Hz",
        f"ImpDeltaFreq={delta_hz:.17g} Hz",
        "ImpMode=1",
        "ImpEnforcePassivity=yes",
        "RiseTime=9.9999999999999998e-17 sec",
        "FallTime=9.9999999999999998e-17 sec",
    )
    if any(token not in netlist for token in required):
        raise SweepError("explicit_netlist_binding_invalid")
    return netlist


def materialize_and_run(runner: Any, *, source: Path, destination: Path, netlist: str) -> dict[str, object]:
    if destination.exists():
        raise SweepError("run_directory_must_not_exist")
    destination.mkdir(parents=True)
    data_dir = destination / "data"
    data_dir.mkdir()
    copied = data_dir / SOURCE_NAME
    shutil.copyfile(source, copied)
    if copied.stat().st_size != SOURCE_LENGTH or sha256_file(copied) != SOURCE_SHA256:
        raise SweepError("source_copy_drift")
    netlist_path = destination / "p3c_prbs9_explicit_convolution.ckt"
    netlist_path.write_text(netlist, encoding="ascii", newline="\n")
    runner.run_ads(netlist_path, destination, data_dir)
    raw_observation = runner.extract_waveform_observation(destination)
    waveform_identity = {
        field: raw_observation[field]
        for field in (
            "ads_output_samples_inclusive",
            "canonical_half_open_samples",
            "canonical_payload_byte_length",
            "canonical_payload_format",
            "canonical_payload_sha256",
            "third_period_payload_byte_length",
            "third_period_payload_sha256",
            "time_grid",
        )
    }
    return {
        "netlist_sha256": sha256_file(netlist_path),
        "waveform": waveform_identity,
        "payload": (destination / "canonical_waveform_le_f64.bin").read_bytes(),
    }


def third_period_rx(payload: bytes, runner: Any) -> list[float]:
    expected = runner.TOTAL_SAMPLES * 24
    if len(payload) != expected:
        raise SweepError("canonical_payload_length_invalid")
    values = [
        struct.unpack_from("<d", payload, index * 24 + 16)[0]
        for index in range(runner.COMPARE_START, runner.COMPARE_START + runner.COMPARE_SAMPLES)
    ]
    if not all(math.isfinite(value) for value in values):
        raise SweepError("canonical_payload_nonfinite")
    return values


def relative_nrmse(reference: list[float], candidate: list[float]) -> float:
    if len(reference) != len(candidate) or not reference:
        raise SweepError("waveform_shape_invalid")
    ref_scale = max(abs(value) for value in reference)
    error_scale = max(abs(candidate[index] - value) for index, value in enumerate(reference))
    if ref_scale == 0.0 or not math.isfinite(ref_scale) or not math.isfinite(error_scale):
        raise SweepError("waveform_norm_invalid")
    reference_sum = math.fsum((value / ref_scale) ** 2 for value in reference)
    error_sum = math.fsum(((candidate[index] - value) / error_scale) ** 2 for index, value in enumerate(reference)) if error_scale else 0.0
    if reference_sum == 0.0:
        raise SweepError("waveform_norm_invalid")
    value = 0.0 if error_scale == 0.0 else (error_scale / ref_scale) * math.sqrt(error_sum / reference_sum)
    if not math.isfinite(value):
        raise SweepError("waveform_nrmse_nonfinite")
    return value


def observe(*, s4p: Path, output_root: Path) -> dict[str, object]:
    source = require_external(s4p, kind="s4p")
    if source.name != SOURCE_NAME or source.stat().st_size != SOURCE_LENGTH or sha256_file(source) != SOURCE_SHA256:
        raise SweepError("selected_s4p_identity_mismatch")
    root = require_external(output_root.parent, kind="output_root_parent") / output_root.name
    if root.exists():
        raise SweepError("output_root_must_not_exist")
    runner = load_runner()
    runner.check_s4p_header(source)
    root.mkdir(parents=True)
    adaptive = materialize_and_run(
        runner,
        source=source,
        destination=root / "adaptive",
        netlist=runner.build_netlist(runner.prbs9_period() * runner.PERIODS, edge_rise_fall_seconds=1.0e-16),
    )
    reference = third_period_rx(adaptive.pop("payload"), runner)
    candidates: list[dict[str, object]] = []
    for grid_length in GRID_LENGTHS:
        result = materialize_and_run(
            runner,
            source=source,
            destination=root / f"explicit_n{grid_length}",
            netlist=build_explicit_netlist(runner, grid_length=grid_length),
        )
        candidate = third_period_rx(result.pop("payload"), runner)
        nrmse = relative_nrmse(reference, candidate)
        candidates.append(
            {
                "grid_length": grid_length,
                "delta_frequency_hz": delta_frequency_hz(grid_length),
                "time_step_seconds": 1.0 / (2.0 * FMAX_HZ),
                "impulse_duration_seconds": grid_length / (2.0 * FMAX_HZ),
                "netlist_sha256": result["netlist_sha256"],
                "waveform": result["waveform"],
                "third_period_nrmse_to_adaptive_oracle": nrmse,
                "within_waveform_limit": nrmse <= WAVEFORM_NRMSE_LIMIT,
            }
        )
    qualifying = [item for item in candidates if item["within_waveform_limit"]]
    return {
        "schema": "sipi.p3c-ads-explicit-convolution-sweep-observation.v1",
        "custody": "external_only_hash_only",
        "runtime_invoked": True,
        "product_runtime_invoked": False,
        "p4b_ami_runtime_invoked": False,
        "source": {"logical_name": SOURCE_NAME, "byte_length": SOURCE_LENGTH, "sha256": SOURCE_SHA256},
        "runner_sha256": sha256_file(RUNNER_PATH),
        "adaptive": {"netlist_sha256": adaptive["netlist_sha256"], "waveform": adaptive["waveform"]},
        "explicit_policy": {
            "fmax_hz": FMAX_HZ,
            "source_edge_seconds": 1.0e-16,
            "imp_mode": 1,
            "imp_approx": False,
            "imp_enforce_passivity": True,
            "grid_lengths": list(GRID_LENGTHS),
        },
        "candidates": candidates,
        "selection": {
            "selection_rule": "minimum_nrmse_among_explicit_candidates_within_frozen_waveform_limit",
            "qualifying_grid_lengths": [item["grid_length"] for item in qualifying],
            "selected_grid_length": min(qualifying, key=lambda item: (item["third_period_nrmse_to_adaptive_oracle"], item["grid_length"]))["grid_length"] if qualifying else None,
            "product_policy_selected": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s4p", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = observe(s4p=args.s4p, output_root=args.output_root)
        report_path = require_external(args.report.parent, kind="report_root") / args.report.name
        if report_path.exists():
            raise SweepError("report_must_not_exist")
        payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("ascii")
        report_path.write_bytes(payload)
        print(json.dumps({"status": "observed", "report_byte_length": len(payload), "report_content_sha256": sha256_bytes(payload)}, sort_keys=True))
    except SweepError as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    except (OSError, UnicodeDecodeError, ValueError):
        print(json.dumps({"status": "rejected", "reason": "external_sweep_io_rejected"}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
