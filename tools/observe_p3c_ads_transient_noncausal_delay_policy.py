"""Observe only the ADS noncausal-delay policy surface for the fixed PWL bench."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
S4P_NAME = "channel_gen5_highloss.s4p"
S4P_LENGTH = 1_834_156
S4P_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"
DOC_NAME = "Troubleshooting_a_Transient-Convolution_Simulation.html"
DOC_LENGTH = 78_496
DOC_SHA256 = "621851d5d3bd754b898c27bccd641da3dae08954ef902f72b6609bd8f093a7e0"
FIXED_PWL_RUNNER = ROOT / "tools" / "run_p3c_external_ads_fixed_pulse_operator.py"
PRODUCT_CONTRACT = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-inline-causality-direct-port.v1.yaml"
REQUIRED_DOC_FRAGMENTS = (
    "Solving a Noncausal Impulse Response",
    "introducing a delay to force causality",
    "ImpNoncausalLength (default=32)",
    "timestep set by default ImpMaxFreq",
)


class ObservationError(ValueError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def require_external(path: Path, *, kind: str, exists: bool = True) -> Path:
    resolved = path.resolve(strict=exists)
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise ObservationError(f"{kind}_must_be_external")


def require_identity(path: Path, *, logical_name: str, length: int, digest: str, kind: str) -> None:
    if path.name != logical_name or path.stat().st_size != length or sha256_file(path) != digest:
        raise ObservationError(f"{kind}_identity_mismatch")


def load_fixed_pwl_runner() -> Any:
    spec = importlib.util.spec_from_file_location("p3c_fixed_pwl_runner", FIXED_PWL_RUNNER)
    if spec is None or spec.loader is None:
        raise ObservationError("fixed_pwl_runner_load_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def observe_documentation(document: bytes) -> None:
    try:
        text = document.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ObservationError("ads_documentation_encoding_rejected") from error
    if any(fragment not in text for fragment in REQUIRED_DOC_FRAGMENTS):
        raise ObservationError("ads_noncausal_delay_documentation_surface_missing")


def observe_fixed_pwl_netlist(netlist: str) -> None:
    required = (
        "ImpMaxFreq=40000000000 Hz",
        "ImpDeltaFreq=39062500 Hz",
        "ImpMode=1",
        "ImpEnforcePassivity=yes",
        "OutputAllPoints=yes",
    )
    if any(token not in netlist for token in required):
        raise ObservationError("fixed_pwl_netlist_policy_surface_mismatch")
    if "ImpNoncausalLength=" in netlist:
        raise ObservationError("fixed_pwl_netlist_noncausal_length_override_present")


def observe_product_contract(contract: bytes) -> None:
    required = (
        "delay_extraction_implemented: false",
        "caller_overrides: prohibited",
        "not delay extraction",
    )
    if any(fragment not in contract.decode("utf-8", errors="strict") for fragment in required):
        raise ObservationError("product_no_delay_contract_surface_missing")


def observe(*, s4p: Path, ads_document: Path) -> dict[str, object]:
    source = require_external(s4p, kind="s4p")
    require_identity(source, logical_name=S4P_NAME, length=S4P_LENGTH, digest=S4P_SHA256, kind="selected_s4p")
    document_path = require_external(ads_document, kind="ads_document")
    require_identity(document_path, logical_name=DOC_NAME, length=DOC_LENGTH, digest=DOC_SHA256, kind="ads_document")
    document = document_path.read_bytes()
    observe_documentation(document)

    runner = load_fixed_pwl_runner()
    netlist = runner.build_netlist()
    runner.assert_fixed_netlist(netlist)
    observe_fixed_pwl_netlist(netlist)
    contract = PRODUCT_CONTRACT.read_bytes()
    observe_product_contract(contract)
    require_identity(source, logical_name=S4P_NAME, length=S4P_LENGTH, digest=S4P_SHA256, kind="selected_s4p_after_observation")
    return {
        "schema": "sipi.p3c-ads-transient-noncausal-delay-policy-surface-observation.v1",
        "custody": "external_only_hash_only",
        "runtime_invoked": False,
        "source": {"logical_name": S4P_NAME, "byte_length": S4P_LENGTH, "sha256": S4P_SHA256},
        "ads_document": {"logical_name": DOC_NAME, "byte_length": DOC_LENGTH, "sha256": DOC_SHA256},
        "fixed_pwl_runner": {"logical_name": FIXED_PWL_RUNNER.name, "sha256": sha256_file(FIXED_PWL_RUNNER)},
        "generated_netlist": {
            "sha256": sha256_bytes(netlist.encode("ascii")),
            "imp_max_freq_hz": 40_000_000_000.0,
            "imp_delta_freq_hz": 39_062_500.0,
            "imp_mode": 1,
            "imp_noncausal_length": "not_declared",
        },
        "documented_policy": {
            "controller_introduces_delay_to_force_causality": True,
            "imp_noncausal_length_default": 32,
            "timestep_relation": "documentation_states_timestep_set_by_default_imp_max_freq",
        },
        "product_no_delay_contract": {"sha256": sha256_bytes(contract), "delay_extraction_implemented": False, "caller_delay_or_alignment_override": "prohibited"},
        "conclusion": {
            "ads_transient_noncausal_delay_policy_surface_documented": True,
            "selected_netlist_implicit_noncausal_length_surface_observed": True,
            "product_no_delay_contract_bound": True,
            "selected_run_delay_action_observed": False,
            "delay_seconds_derived": False,
            "candidate_waveform_accepted": False,
            "release_ledger_promoted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s4p", required=True, type=Path)
    parser.add_argument("--ads-document", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = observe(s4p=args.s4p, ads_document=args.ads_document)
        destination = require_external(args.report.parent, kind="report_root") / args.report.name
        if destination.exists():
            raise ObservationError("report_must_not_exist")
        payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("ascii")
        destination.write_bytes(payload)
        print(json.dumps({"status": "observed", "report_byte_length": len(payload), "report_content_sha256": sha256_bytes(payload)}, sort_keys=True))
    except ObservationError as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    except (OSError, ValueError):
        print(json.dumps({"status": "rejected", "reason": "external_observation_io_rejected"}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
