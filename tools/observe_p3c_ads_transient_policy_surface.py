"""Read-only, hash-only observation of the P3C ADS transient policy surface."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_p3c_external_ads_prbs9_reference.py"
SOURCE_NAME = "channel_gen5_highloss.s4p"
SOURCE_LENGTH = 1834156
SOURCE_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"
DOCS = {
    "transient_parameters": (
        "cktsimtrans/Transient_Simulation_Parameters.html",
        ("ImpEnforcePassivity", "Use Transient low freq extrapolation"),
    ),
    "transient_troubleshooting": (
        "cktsimtrans/Troubleshooting_a_Transient-Convolution_Simulation.html",
        ("Adaptive Impulse Response Calculation", "periodic extension"),
    ),
    "simulation_controllers": (
        "usrguide/Simulation_and_Optimization_Controllers.html",
        ("Adaptive Impulse Response Calculation", "doubling the maximum frequency"),
    ),
    "channel_convolution": (
        "cktsimchan/Differential_Channel_Simulator_-_Convolution.html",
        ("adaptive sampling frequency chosen by the Transient engine",),
    ),
}


class ObservationError(ValueError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def require_external(path: Path, *, kind: str) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise ObservationError(f"{kind}_must_be_outside_repository")


def load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("p3c_ads_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise ObservationError("runner_load_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def observe(*, s4p: Path, ads_doc_root: Path) -> dict[str, object]:
    source = require_external(s4p, kind="s4p")
    if source.name != SOURCE_NAME or source.stat().st_size != SOURCE_LENGTH or sha256_file(source) != SOURCE_SHA256:
        raise ObservationError("selected_s4p_identity_mismatch")
    documentation: dict[str, dict[str, object]] = {}
    docs_root = require_external(ads_doc_root, kind="ads_doc_root")
    for logical_name, (relative, required_fragments) in DOCS.items():
        path = docs_root / relative
        payload = path.read_bytes()
        text = payload.decode("utf-8", errors="strict")
        if any(fragment not in text for fragment in required_fragments):
            raise ObservationError(f"ads_documentation_surface_missing:{logical_name}")
        documentation[logical_name] = {
            "logical_name": Path(relative).name,
            "byte_length": len(payload),
            "sha256": sha256_bytes(payload),
        }

    runner = load_runner()
    netlist = runner.build_netlist(runner.prbs9_period() * runner.PERIODS, edge_rise_fall_seconds=1.0e-16)
    required = (
        "ImpLFEOn=yes", "ImpApprox=no", "ImpMode=1", "ImpEnforcePassivity=yes",
        "UseInitCond=no", "OutputAllPoints=yes", "MaxTimeStep=9.7656250000000006e-13 sec",
        "RiseTime=9.9999999999999998e-17 sec", "FallTime=9.9999999999999998e-17 sec",
    )
    if any(token not in netlist for token in required):
        raise ObservationError("generated_netlist_policy_surface_mismatch")
    snp_line = next((line for line in netlist.splitlines() if line.startswith("SnP:CHANNEL ")), None)
    if snp_line is None or "EnforcePassivity=" in snp_line:
        raise ObservationError("snp_component_passivity_surface_invalid")
    if any(token in netlist for token in ("ImpDeltaFreq=", "ImpMaxFreq=", "ImpMaxImpulseSamples=", "ImpTrunc")):
        raise ObservationError("unexpected_explicit_convolution_policy")
    return {
        "schema": "sipi.p3c-ads-transient-policy-surface-observation.v1",
        "custody": "external_only_hash_only",
        "runtime_invoked": False,
        "source": {"logical_name": SOURCE_NAME, "byte_length": SOURCE_LENGTH, "sha256": SOURCE_SHA256},
        "runner": {"logical_name": RUNNER.name, "sha256": sha256_file(RUNNER)},
        "documentation": documentation,
        "generated_netlist": {
            "source_edge_seconds": 1.0e-16,
            "max_time_step_seconds": 9.765625e-13,
            "output_points": "all_strobe_points",
            "low_frequency_extrapolation": "enabled_transient_engine_adaptive_start_frequency",
            "approximate_linear_models": "disabled",
            "convolution_mode": 1,
            "controller_passivity_enforcement": "enabled",
            "snp_component_passivity_override": "not_declared",
            "initial_conditions": "disabled",
        },
        "unresolved_product_policy": [
            "convolution_frequency_grid_and_delta_frequency_not_explicit",
            "maximum_frequency_not_explicit",
            "impulse_length_and_truncation_not_explicit",
            "frequency_interpolation_and_extrapolation_algorithm_not_selected",
            "causalization_and_passivity_handling_algorithm_not_selected",
            "linear_convolution_startup_history_and_output_strobe_algorithm_not_selected",
        ],
        "conclusion": {
            "ads_policy_surface_observed": True,
            "product_deterministic_time_domain_policy_observed": False,
            "candidate_waveform_generated": False,
            "external_reference_binding_evaluated": False,
            "product_runtime_invoked": False,
            "p4b_ami_runtime_invoked": False,
            "release_ledger_promoted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s4p", required=True, type=Path)
    parser.add_argument("--ads-doc-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = observe(s4p=args.s4p, ads_doc_root=args.ads_doc_root)
        destination = require_external(args.report.parent, kind="report_root") / args.report.name
        if destination.exists():
            raise ObservationError("report_must_not_exist")
        payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("ascii")
        destination.write_bytes(payload)
        print(json.dumps({"status": "observed", "report_byte_length": len(payload), "report_content_sha256": sha256_bytes(payload)}, sort_keys=True))
    except ObservationError as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    except UnicodeDecodeError:
        print(json.dumps({"status": "rejected", "reason": "ads_documentation_encoding_rejected"}, sort_keys=True))
        return 2
    except (OSError, ValueError):
        print(json.dumps({"status": "rejected", "reason": "external_observation_io_rejected"}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
