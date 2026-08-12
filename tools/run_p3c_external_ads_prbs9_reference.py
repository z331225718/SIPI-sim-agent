"""Generate a custody-external ADS PRBS9 ideal-load channel reference.

This tool is deliberately not a product runtime.  It accepts one externally
held Touchstone input, creates a new isolated ADS working directory, and
records only hashes and structural facts in its external manifest.  It never
accepts IBIS, AMI, or DLL inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ADS_ROOT = Path(r"C:\Program Files\Keysight\ADS2026_Update1")
ADS_PYTHON = ADS_ROOT / "tools" / "python" / "python.exe"
DSDUMP = ADS_ROOT / "bin" / "dsdump.exe"
CONTRACT_PATH = REPO_ROOT / "docs" / "baselines" / "p3c-prbs9-waveform-jitter-contract.v1.yaml"
PERIOD_SHA256 = "4437fb3beb2fa1ca99b4177673c53fc20089ac9cf68b1adaa1e0fad14d742127"
SEED = 0x1A5
UI_SECONDS = 3.125e-11
SAMPLES_PER_UI = 32
SAMPLE_INTERVAL_SECONDS = UI_SECONDS / SAMPLES_PER_UI
PERIOD_BITS = 511
PERIODS = 3
TOTAL_SAMPLES = PERIOD_BITS * PERIODS * SAMPLES_PER_UI
COMPARE_START = PERIOD_BITS * 2 * SAMPLES_PER_UI
COMPARE_SAMPLES = PERIOD_BITS * SAMPLES_PER_UI
FORBIDDEN_TOKENS = ("ami", "ibis", ".dll", "getwave", "ctspcie")
RUN_ID = re.compile(r"[A-Za-z0-9_-]+")


class ExternalReferenceError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prbs9_period() -> str:
    state = SEED
    bits: list[str] = []
    seen: set[int] = set()
    for _ in range(PERIOD_BITS):
        if state == 0 or state in seen:
            raise ExternalReferenceError("prbs9_cycle_invalid")
        seen.add(state)
        bits.append(str((state >> 8) & 1))
        feedback = ((state >> 8) ^ (state >> 4)) & 1
        state = ((state << 1) & 0x1FF) | feedback
    period = "".join(bits)
    if state != SEED or len(seen) != PERIOD_BITS or sha256_file_bytes(period.encode("ascii")) != PERIOD_SHA256:
        raise ExternalReferenceError("prbs9_contract_mismatch")
    return period


def sha256_file_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_external_path(path: Path, *, kind: str) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return resolved
    raise ExternalReferenceError(f"{kind}_must_not_be_inside_repository")


def valid_run_id(value: str) -> bool:
    return RUN_ID.fullmatch(value) is not None


def check_s4p_header(source: Path) -> None:
    head = source.read_text(encoding="ascii", errors="strict").splitlines()[:16]
    if not any(line.strip().lower() == "# hz s ri r 50" for line in head):
        raise ExternalReferenceError("s4p_header_not_exact_hz_s_ri_r50")
    required = ("Port1   <-- P -->  Port2", "Port3   <-- M -->  Port4")
    if not all(any(fragment in line for line in head) for fragment in required):
        raise ExternalReferenceError("s4p_authoritative_port_map_missing")


def build_netlist(bit_sequence: str, *, edge_rise_fall_seconds: float = 0.0) -> str:
    """Use ADS PRBSsrc explicit bits so ADS cannot choose an LFSR convention."""
    if len(bit_sequence) != PERIOD_BITS * PERIODS:
        raise ExternalReferenceError("stimulus_length_invalid")
    if edge_rise_fall_seconds not in (0.0, 1.0e-16):
        raise ExternalReferenceError("source_edge_not_authorized")
    stop = f"{PERIOD_BITS * PERIODS * UI_SECONDS:.17g} sec"
    step = f"{SAMPLE_INTERVAL_SECONDS:.17g} sec"
    edge = f"{edge_rise_fall_seconds:.17g} sec"
    return "\n".join(
        [
            (
                'PRBSsrc:TXP txp 0 0 0 Mode=2 RegisterLength=9 Taps="10001110" Seed="10101010" '
                f'BitSequence="{bit_sequence}" Trigger=0 VtriggerThreshold=0.5 V TriggerEdge=0 '
                'Vlow=-0.5 V Vhigh=0.5 V Rout=50 Ohm PAMencoding=0 PAMlevels=2 '
                'EnableDeEmphasis=0 DeEmphasisMode=0 DeEmphasis=0.0 DeEmphasisTaps=1 '
                f'EmphasisSpan=0.0 EdgeShape=0 BitRate=32 GHz RiseTime={edge} FallTime={edge} '
                'TransitReference=0.0 Delay=0 sec EnableRJ=0 RJrms=0 sec RJbw=1 THz '
                'EnablePJ=0 PJwave[1]=0 PJamp[1]=0 sec PJfreq[1]=100 MHz'
            ),
            (
                'PRBSsrc:TXM txm 0 0 0 Mode=2 RegisterLength=9 Taps="10001110" Seed="10101010" '
                f'BitSequence="{bit_sequence}" Trigger=0 VtriggerThreshold=0.5 V TriggerEdge=0 '
                'Vlow=0.5 V Vhigh=-0.5 V Rout=50 Ohm PAMencoding=0 PAMlevels=2 '
                'EnableDeEmphasis=0 DeEmphasisMode=0 DeEmphasis=0.0 DeEmphasisTaps=1 '
                f'EmphasisSpan=0.0 EdgeShape=0 BitRate=32 GHz RiseTime={edge} FallTime={edge} '
                'TransitReference=0.0 Delay=0 sec EnableRJ=0 RJrms=0 sec RJbw=1 THz '
                'EnablePJ=0 PJwave[1]=0 PJamp[1]=0 sec PJfreq[1]=100 MHz'
            ),
            'SnP:CHANNEL txp rxp txm rxm File="channel_gen5_highloss.s4p" NumPorts=4',
            'R:RX_PLUS_LOAD rxp 0 R=50 Ohm',
            'R:RX_MINUS_LOAD rxm 0 R=50 Ohm',
            (
                f'Tran:TRAN StartTime=0 sec StopTime={stop} MaxTimeStep={step} LimitStepForTL=no '
                'TimeStepControl=0 TruncTol=7.0 ChargeTol=1.0e-14 IntegMethod=0 MaxGearOrder=2 Mu=0.5 '
                'MaxOrder=4 Freq[1]=1.0 GHz Order[1]=3 HB_Window=no HB_Sol=no ImpLFEOn=yes ImpApprox=no '
                'ShortTL_Delay=1.0 psec ImpMode=1 UseInitCond=no LoadGminDC=no CheckKCL=yes '
                'CheckOnlyDeltaV=yes OverloadAlert=no DeviceBypass=no MaxIters=10 MaxItersDC=200 '
                'DevOpPtLevel=0 StatusLevel=2 OutputAllPoints=yes NoiseScale=1 ImpEnforcePassivity=yes '
                'OutputPlan="P3C_OUTPUT"'
            ),
            'OutputPlan:P3C_OUTPUT Type="Output" UseNodeNestLevel=yes NodeNestLevel=2 UseEquationNestLevel=yes '
            'EquationNestLevel=2 UseSavedEquationNestLevel=yes SavedEquationNestLevel=2 UseDeviceCurrentNestLevel=no '
            'DeviceCurrentNestLevel=0 DeviceCurrentDeviceType="All" DeviceCurrentSymSyntax=yes UseCurrentNestLevel=yes '
            'CurrentNestLevel=999 UseDeviceVoltageNestLevel=no DeviceVoltageNestLevel=0 DeviceVoltageDeviceType="All"',
            'Options:unknown TopDesignName="sipi_p3c_prbs9_ideal_load"',
            "",
        ]
    )


def assert_netlist_isolated(netlist: str) -> None:
    lower = netlist.lower()
    if any(token in lower for token in FORBIDDEN_TOKENS):
        raise ExternalReferenceError("netlist_external_runtime_boundary_violation")
    for required in ("PRBSsrc:TXP", "PRBSsrc:TXM", "SnP:CHANNEL", "R:RX_PLUS_LOAD", "R:RX_MINUS_LOAD", "Tran:TRAN"):
        if required not in netlist:
            raise ExternalReferenceError("netlist_topology_incomplete")


def materialize_run(source: Path, destination: Path, *, dry_run: bool, edge_rise_fall_seconds: float = 0.0) -> dict[str, Any]:
    if destination.exists():
        raise ExternalReferenceError("run_directory_must_not_exist")
    destination.mkdir(parents=True)
    data_dir = destination / "data"
    data_dir.mkdir()
    copied = data_dir / "channel_gen5_highloss.s4p"
    shutil.copyfile(source, copied)
    if source.stat().st_size != copied.stat().st_size or sha256_file(source) != sha256_file(copied):
        raise ExternalReferenceError("s4p_copy_source_drift")
    sequence = prbs9_period() * PERIODS
    netlist = build_netlist(sequence, edge_rise_fall_seconds=edge_rise_fall_seconds)
    assert_netlist_isolated(netlist)
    netlist_path = destination / "p3c_prbs9_ideal_load.ckt"
    netlist_path.write_text(netlist, encoding="ascii", newline="\n")
    manifest: dict[str, Any] = {
        "schema": "sipi.p3c-external-ads-prbs9-reference-run.v1",
        "custody": "external_only",
        "runtime_invoked": False,
        "ads_oracle_only": True,
        "product_runtime": False,
        "p4b_ami_runtime": False,
        "source": {"logical_name": "channel_gen5_highloss.s4p", "byte_length": copied.stat().st_size, "sha256": sha256_file(copied)},
        "port_map": {"port_1": "tx_plus", "port_2": "rx_plus", "port_3": "tx_minus", "port_4": "rx_minus"},
        "stimulus": {"seed_hex": "0x1a5", "period_sha256": PERIOD_SHA256, "period_bits": PERIOD_BITS, "periods": PERIODS, "serialized_three_period_sha256": sha256_file_bytes(sequence.encode("ascii"))},
        "timebase": {"ui_seconds": UI_SECONDS, "samples_per_ui": SAMPLES_PER_UI, "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS, "sample_count_expected": TOTAL_SAMPLES, "third_period_start_index": COMPARE_START, "third_period_sample_count": COMPARE_SAMPLES},
        "topology": {"tx": "two_complementary_ideal_prbssrc_sources_with_internal_50_ohm_rout", "channel": "four_port_touchstone", "rx": "two_50_ohm_to_global_ground_loads", "reference_node": "global_ground_0", "observation": "V(rxp)-V(rxm)", "rise_time_seconds": edge_rise_fall_seconds, "fall_time_seconds": edge_rise_fall_seconds},
        "generated": {"netlist_sha256": sha256_file(netlist_path), "netlist_byte_length": netlist_path.stat().st_size},
    }
    if not dry_run:
        run_ads(netlist_path, destination, data_dir)
        manifest["runtime_invoked"] = True
        manifest["waveform_observation"] = extract_waveform_observation(destination)
    (destination / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="ascii", newline="\n")
    return manifest


def run_ads(netlist_path: Path, destination: Path, data_dir: Path) -> None:
    if not ADS_PYTHON.is_file():
        raise ExternalReferenceError("ads_python_not_found")
    code = (
        "import os; from keysight.edatoolbox import ads; "
        "ads.CircuitSimulator(hpeesof_dir=os.environ['SIPI_ADS_ROOT']).run_netlist("
        "open(os.environ['SIPI_NETLIST'], encoding='ascii').read(), "
        "output_dir=os.environ['SIPI_OUTPUT_DIR'], working_dir=os.environ['SIPI_OUTPUT_DIR'], "
        "netlist_file=os.environ['SIPI_NETLIST'], output_file=os.environ['SIPI_LOG'], "
        "rel_data_dir=os.environ['SIPI_DATA_DIR'], dataset_name='p3c_prbs9')"
    )
    environment = os.environ.copy()
    environment.update({"SIPI_ADS_ROOT": str(ADS_ROOT), "SIPI_NETLIST": str(netlist_path), "SIPI_OUTPUT_DIR": str(destination), "SIPI_LOG": str(destination / "hpeesofsim.out"), "SIPI_DATA_DIR": str(data_dir)})
    result = subprocess.run([str(ADS_PYTHON), "-c", code], check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment)
    (destination / "ads_python.out").write_text(result.stdout + result.stderr, encoding="utf-8", newline="\n")
    if result.returncode != 0:
        raise ExternalReferenceError("ads_runtime_rejected")


def parse_dsdump(dataset_path: Path) -> list[tuple[float, float, float]]:
    if not DSDUMP.is_file():
        raise ExternalReferenceError("ads_dsdump_not_found")
    result = subprocess.run([str(DSDUMP), str(dataset_path)], check=False, capture_output=True, text=True, encoding="utf-8", errors="strict")
    if result.returncode != 0:
        raise ExternalReferenceError("ads_dataset_dump_rejected")
    lines = iter(result.stdout.splitlines())
    names: list[str] = []
    point_count: int | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('* Dependent number of variables:'):
            continue
        if stripped.startswith('0: "txp"') or stripped.startswith('1: "txm"') or stripped.startswith('2: "rxp"') or stripped.startswith('3: "rxm"') or stripped.startswith('4: "tranorder"'):
            names.append(stripped.split('"')[1])
        if stripped.startswith('* Number of points:'):
            point_count = int(stripped.split(':', 1)[1].strip())
            break
    if names != ["txp", "txm", "rxp", "rxm", "tranorder"] or point_count != TOTAL_SAMPLES + 1:
        raise ExternalReferenceError("ads_dataset_shape_rejected")
    values: list[tuple[float, float, float]] = []
    for index in range(point_count):
        point_line = next(lines, None)
        if point_line is None or not point_line.startswith(f"{index}:"):
            raise ExternalReferenceError("ads_dataset_point_order_rejected")
        time = float(point_line.split(':', 1)[1].strip())
        raw = [next(lines, None) for _ in range(5)]
        if any(value is None for value in raw):
            raise ExternalReferenceError("ads_dataset_point_truncated")
        txp, txm, rxp, rxm, _order = (float(value) for value in raw)
        expected_time = index * SAMPLE_INTERVAL_SECONDS
        if not math.isfinite(time) or abs(time - expected_time) > 8 * math.ulp(max(abs(time), abs(expected_time))):
            raise ExternalReferenceError("ads_dataset_time_grid_rejected")
        if not all(math.isfinite(value) for value in (txp, txm, rxp, rxm)):
            raise ExternalReferenceError("ads_dataset_nonfinite_rejected")
        values.append((time, txp - txm, rxp - rxm))
    return values


def canonical_waveform_payload(values: list[tuple[float, float, float]]) -> bytes:
    # ADS emits an inclusive endpoint; P3C's contract requires the half-open grid.
    if len(values) != TOTAL_SAMPLES + 1:
        raise ExternalReferenceError("ads_dataset_shape_rejected")
    payload = bytearray()
    for index, (time, tx_differential, rx_differential) in enumerate(values[:-1]):
        expected_time = index * SAMPLE_INTERVAL_SECONDS
        if abs(time - expected_time) > 8 * math.ulp(max(abs(time), abs(expected_time))):
            raise ExternalReferenceError("ads_dataset_time_grid_rejected")
        payload.extend(struct.pack("<ddd", time, tx_differential, rx_differential))
    return bytes(payload)


def extract_waveform_observation(destination: Path) -> dict[str, Any]:
    values = parse_dsdump(destination / "p3c_prbs9.ds")
    payload = canonical_waveform_payload(values)
    waveform_path = destination / "canonical_waveform_le_f64.bin"
    waveform_path.write_bytes(payload)
    third = payload[COMPARE_START * 24 : (COMPARE_START + COMPARE_SAMPLES) * 24]
    return {
        "dataset_logical_name": "p3c_prbs9.ds",
        "dataset_byte_length": (destination / "p3c_prbs9.ds").stat().st_size,
        "dataset_sha256": sha256_file(destination / "p3c_prbs9.ds"),
        "time_grid": "fixed_uniform_inclusive_ads_output_then_contractually_excluded_endpoint",
        "ads_output_samples_inclusive": TOTAL_SAMPLES + 1,
        "canonical_half_open_samples": TOTAL_SAMPLES,
        "canonical_payload_format": "little_endian_f64_time_tx_differential_rx_differential",
        "canonical_payload_sha256": sha256_file_bytes(payload),
        "canonical_payload_byte_length": len(payload),
        "third_period_payload_sha256": sha256_file_bytes(third),
        "third_period_payload_byte_length": len(third),
        "source_edge_floor_seconds": 1e-16,
        "source_edge_floor_observed": True,
        "reference_contract_match": False,
        "reference_contract_mismatch_reason": "ads_prbssrc_clamps_requested_zero_rise_and_fall_to_100_asec",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s4p", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--edge-rise-fall-seconds", type=float, default=0.0)
    parser.add_argument("--run", action="store_true", help="Invoke ADS after static generation checks.")
    arguments = parser.parse_args(argv)
    try:
        source = require_external_path(arguments.s4p, kind="s4p")
        check_s4p_header(source)
        output_root = require_external_path(arguments.output_root, kind="output_root")
        if not valid_run_id(arguments.run_id):
            raise ExternalReferenceError("run_id_invalid")
        result = materialize_run(source, output_root / arguments.run_id, dry_run=not arguments.run, edge_rise_fall_seconds=arguments.edge_rise_fall_seconds)
    except (OSError, ValueError, ExternalReferenceError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "generated" if not arguments.run else "ads_run_completed", "run_id": arguments.run_id, "netlist_sha256": result["generated"]["netlist_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
