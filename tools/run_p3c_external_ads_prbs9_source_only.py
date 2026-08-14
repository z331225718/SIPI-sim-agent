"""Run the approved ADS PRBS9 source-only matched-load observation."""

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
PERIOD_SHA256 = "4437fb3beb2fa1ca99b4177673c53fc20089ac9cf68b1adaa1e0fad14d742127"
SEED = 0x1A5
UI_SECONDS = 3.125e-11
SAMPLES_PER_UI = 32
SAMPLE_INTERVAL_SECONDS = UI_SECONDS / SAMPLES_PER_UI
PERIOD_BITS = 511
PERIODS = 3
TOTAL_SAMPLES = PERIOD_BITS * PERIODS * SAMPLES_PER_UI
ADS_INCLUSIVE_SAMPLES = TOTAL_SAMPLES + 1
EDGE_SECONDS = 1.0e-16
FORBIDDEN_TOKENS = ("snp", "channel", "rxp", "rxm", "ami", "ibis", ".dll", "getwave", "ctspcie")
RUN_ID = re.compile(r"[A-Za-z0-9_-]+")


class SourceOnlyError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_external_path(path: Path, *, kind: str) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return resolved
    raise SourceOnlyError(f"{kind}_must_not_be_inside_repository")


def prbs9_period() -> str:
    state = SEED
    bits: list[str] = []
    seen: set[int] = set()
    for _ in range(PERIOD_BITS):
        if state == 0 or state in seen:
            raise SourceOnlyError("prbs9_cycle_invalid")
        seen.add(state)
        bits.append(str((state >> 8) & 1))
        feedback = ((state >> 8) ^ (state >> 4)) & 1
        state = ((state << 1) & 0x1FF) | feedback
    period = "".join(bits)
    if state != SEED or len(seen) != PERIOD_BITS or sha256_bytes(period.encode("ascii")) != PERIOD_SHA256:
        raise SourceOnlyError("prbs9_contract_mismatch")
    return period


def build_netlist(sequence: str) -> str:
    if len(sequence) != PERIOD_BITS * PERIODS:
        raise SourceOnlyError("stimulus_length_invalid")
    stop = f"{PERIOD_BITS * PERIODS * UI_SECONDS:.17g} sec"
    step = f"{SAMPLE_INTERVAL_SECONDS:.17g} sec"
    edge = f"{EDGE_SECONDS:.17g} sec"
    return "\n".join(
        [
            (
                'PRBSsrc:TXP txp 0 0 0 Mode=2 RegisterLength=9 Taps="10001110" Seed="10101010" '
                f'BitSequence="{sequence}" Trigger=0 VtriggerThreshold=0.5 V TriggerEdge=0 '
                'Vlow=-0.5 V Vhigh=0.5 V Rout=50 Ohm PAMencoding=0 PAMlevels=2 '
                'EnableDeEmphasis=0 DeEmphasisMode=0 DeEmphasis=0.0 DeEmphasisTaps=1 '
                f'EmphasisSpan=0.0 EdgeShape=0 BitRate=32 GHz RiseTime={edge} FallTime={edge} '
                'TransitReference=0.0 Delay=0 sec EnableRJ=0 RJrms=0 sec RJbw=1 THz '
                'EnablePJ=0 PJwave[1]=0 PJamp[1]=0 sec PJfreq[1]=100 MHz'
            ),
            (
                'PRBSsrc:TXM txm 0 0 0 Mode=2 RegisterLength=9 Taps="10001110" Seed="10101010" '
                f'BitSequence="{sequence}" Trigger=0 VtriggerThreshold=0.5 V TriggerEdge=0 '
                'Vlow=0.5 V Vhigh=-0.5 V Rout=50 Ohm PAMencoding=0 PAMlevels=2 '
                'EnableDeEmphasis=0 DeEmphasisMode=0 DeEmphasis=0.0 DeEmphasisTaps=1 '
                f'EmphasisSpan=0.0 EdgeShape=0 BitRate=32 GHz RiseTime={edge} FallTime={edge} '
                'TransitReference=0.0 Delay=0 sec EnableRJ=0 RJrms=0 sec RJbw=1 THz '
                'EnablePJ=0 PJwave[1]=0 PJamp[1]=0 sec PJfreq[1]=100 MHz'
            ),
            'R:TX_PLUS_MATCH txp 0 R=50 Ohm',
            'R:TX_MINUS_MATCH txm 0 R=50 Ohm',
            (
                f'Tran:TRAN StartTime=0 sec StopTime={stop} MaxTimeStep={step} LimitStepForTL=no '
                'TimeStepControl=0 TruncTol=7.0 ChargeTol=1.0e-14 IntegMethod=0 MaxGearOrder=2 Mu=0.5 '
                'MaxOrder=4 Freq[1]=1.0 GHz Order[1]=3 HB_Window=no HB_Sol=no '
                'ShortTL_Delay=1.0 psec ImpMode=1 UseInitCond=no LoadGminDC=no CheckKCL=yes '
                'CheckOnlyDeltaV=yes OverloadAlert=no DeviceBypass=no MaxIters=10 MaxItersDC=200 '
                'DevOpPtLevel=0 StatusLevel=2 OutputAllPoints=yes NoiseScale=1 '
                'OutputPlan="P3C_SOURCE_ONLY_OUTPUT"'
            ),
            'OutputPlan:P3C_SOURCE_ONLY_OUTPUT Type="Output" UseNodeNestLevel=yes NodeNestLevel=2 '
            'UseEquationNestLevel=yes EquationNestLevel=2 UseSavedEquationNestLevel=yes '
            'SavedEquationNestLevel=2 UseDeviceCurrentNestLevel=no DeviceCurrentNestLevel=0 '
            'DeviceCurrentDeviceType="All" DeviceCurrentSymSyntax=yes UseCurrentNestLevel=yes '
            'CurrentNestLevel=999 UseDeviceVoltageNestLevel=no DeviceVoltageNestLevel=0 '
            'DeviceVoltageDeviceType="All"',
            'Options:unknown TopDesignName="sipi_p3c_prbs9_source_only_matched_load"',
            "",
        ]
    )


def assert_netlist_isolated(netlist: str) -> None:
    lower = netlist.lower()
    if any(token in lower for token in FORBIDDEN_TOKENS):
        raise SourceOnlyError("netlist_runtime_boundary_violation")
    for required in ("PRBSsrc:TXP", "PRBSsrc:TXM", "R:TX_PLUS_MATCH", "R:TX_MINUS_MATCH", "Tran:TRAN"):
        if required not in netlist:
            raise SourceOnlyError("netlist_topology_incomplete")
    if "Rout=50 Ohm" not in netlist or netlist.count("R=50 Ohm") != 2:
        raise SourceOnlyError("netlist_termination_mismatch")


def run_ads(netlist_path: Path, destination: Path, data_dir: Path) -> None:
    if not ADS_PYTHON.is_file():
        raise SourceOnlyError("ads_python_not_found")
    code = (
        "import os; from keysight.edatoolbox import ads; "
        "ads.CircuitSimulator(hpeesof_dir=os.environ['SIPI_ADS_ROOT']).run_netlist("
        "open(os.environ['SIPI_NETLIST'], encoding='ascii').read(), "
        "output_dir=os.environ['SIPI_OUTPUT_DIR'], working_dir=os.environ['SIPI_OUTPUT_DIR'], "
        "netlist_file=os.environ['SIPI_NETLIST'], output_file=os.environ['SIPI_LOG'], "
        "rel_data_dir=os.environ['SIPI_DATA_DIR'], dataset_name='p3c_prbs9_source_only')"
    )
    environment = os.environ.copy()
    environment.update(
        {
            "SIPI_ADS_ROOT": str(ADS_ROOT),
            "SIPI_NETLIST": str(netlist_path),
            "SIPI_OUTPUT_DIR": str(destination),
            "SIPI_LOG": str(destination / "hpeesofsim.out"),
            "SIPI_DATA_DIR": str(data_dir),
        }
    )
    result = subprocess.run(
        [str(ADS_PYTHON), "-c", code], check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=environment,
    )
    (destination / "ads_python.out").write_text(result.stdout + result.stderr, encoding="utf-8", newline="\n")
    if result.returncode != 0:
        raise SourceOnlyError("ads_runtime_rejected")


def parse_dsdump(dataset_path: Path) -> list[tuple[float, float, float]]:
    if not DSDUMP.is_file():
        raise SourceOnlyError("ads_dsdump_not_found")
    result = subprocess.run([str(DSDUMP), str(dataset_path)], check=False, capture_output=True, text=True, encoding="utf-8", errors="strict")
    if result.returncode != 0:
        raise SourceOnlyError("ads_dataset_dump_rejected")
    lines = iter(result.stdout.splitlines())
    names: list[str] = []
    point_count: int | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('0: "txp"') or stripped.startswith('1: "txm"') or stripped.startswith('2: "tranorder"'):
            names.append(stripped.split('"')[1])
        if stripped.startswith("* Number of points:"):
            point_count = int(stripped.split(":", 1)[1].strip())
            break
    if names != ["txp", "txm", "tranorder"] or point_count != ADS_INCLUSIVE_SAMPLES:
        raise SourceOnlyError("ads_dataset_shape_rejected")
    values: list[tuple[float, float, float]] = []
    for index in range(point_count):
        point_line = next(lines, None)
        if point_line is None or not point_line.startswith(f"{index}:"):
            raise SourceOnlyError("ads_dataset_point_order_rejected")
        time = float(point_line.split(":", 1)[1].strip())
        raw = [next(lines, None) for _ in range(3)]
        if any(value is None for value in raw):
            raise SourceOnlyError("ads_dataset_point_truncated")
        txp, txm, _order = (float(value) for value in raw)
        expected_time = index * SAMPLE_INTERVAL_SECONDS
        if not math.isfinite(time) or abs(time - expected_time) > 8 * math.ulp(max(abs(time), abs(expected_time))):
            raise SourceOnlyError("ads_dataset_time_grid_rejected")
        if not all(math.isfinite(value) for value in (txp, txm)):
            raise SourceOnlyError("ads_dataset_nonfinite_rejected")
        values.append((time, txp - txm, 0.5 * (txp + txm)))
    return values


def canonical_source_payload(values: list[tuple[float, float, float]]) -> bytes:
    if len(values) != ADS_INCLUSIVE_SAMPLES:
        raise SourceOnlyError("ads_dataset_shape_rejected")
    payload = bytearray()
    for index, (time, differential, common_mode) in enumerate(values[:-1]):
        expected_time = index * SAMPLE_INTERVAL_SECONDS
        if abs(time - expected_time) > 8 * math.ulp(max(abs(time), abs(expected_time))):
            raise SourceOnlyError("ads_dataset_time_grid_rejected")
        payload.extend(struct.pack("<ddd", time, differential, common_mode))
    return bytes(payload)


def materialize_run(destination: Path, *, invoke_ads: bool) -> dict[str, Any]:
    if destination.exists():
        raise SourceOnlyError("run_directory_must_not_exist")
    destination.mkdir(parents=True)
    data_dir = destination / "data"
    data_dir.mkdir()
    sequence = prbs9_period() * PERIODS
    netlist = build_netlist(sequence)
    assert_netlist_isolated(netlist)
    netlist_path = destination / "p3c_prbs9_source_only.ckt"
    netlist_path.write_text(netlist, encoding="ascii", newline="\n")
    manifest: dict[str, Any] = {
        "schema": "sipi.p3c-external-ads-prbs9-source-only-run.v1",
        "custody": "external_only",
        "runtime_invoked": False,
        "product_runtime": False,
        "p4b_ami_runtime": False,
        "stimulus": {"seed_hex": "0x1a5", "period_sha256": PERIOD_SHA256, "period_bits": PERIOD_BITS, "periods": PERIODS, "serialized_three_period_sha256": sha256_bytes(sequence.encode("ascii"))},
        "timebase": {"sample_interval_seconds": SAMPLE_INTERVAL_SECONDS, "ads_output_samples_inclusive": ADS_INCLUSIVE_SAMPLES, "canonical_half_open_samples": TOTAL_SAMPLES},
        "topology": {"loads": "two_independent_50_ohm_to_global_ground", "observation": "V(txp)-V(txm)", "common_mode": "(V(txp)+V(txm))/2", "rise_time_seconds": EDGE_SECONDS, "fall_time_seconds": EDGE_SECONDS},
        "generated": {"netlist_sha256": sha256_file(netlist_path), "netlist_byte_length": netlist_path.stat().st_size},
    }
    if invoke_ads:
        run_ads(netlist_path, destination, data_dir)
        dataset = destination / "p3c_prbs9_source_only.ds"
        values = parse_dsdump(dataset)
        payload = canonical_source_payload(values)
        payload_path = destination / "canonical_source_le_f64.bin"
        payload_path.write_bytes(payload)
        manifest["runtime_invoked"] = True
        manifest["waveform_observation"] = {"dataset_logical_name": dataset.name, "dataset_sha256": sha256_file(dataset), "ads_output_samples_inclusive": ADS_INCLUSIVE_SAMPLES, "canonical_half_open_samples": TOTAL_SAMPLES, "canonical_payload_format": "little_endian_f64_time_loaded_differential_common_mode", "canonical_payload_sha256": sha256_bytes(payload), "canonical_payload_byte_length": len(payload)}
    (destination / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="ascii", newline="\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if RUN_ID.fullmatch(arguments.run_id) is None:
            raise SourceOnlyError("run_id_invalid")
        root = require_external_path(arguments.output_root, kind="output_root")
        result = materialize_run(root / arguments.run_id, invoke_ads=arguments.run)
    except (OSError, ValueError, SourceOnlyError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "generated" if not arguments.run else "ads_run_completed", "run_id": arguments.run_id, "netlist_sha256": result["generated"]["netlist_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
