"""Run the fixed external ADS off-grid one-UI differential-pulse observation.

This external-only helper owns one diagnostic topology.  It does not expose a
general netlist or product channel interface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
from pathlib import Path
from typing import Any

import run_p3c_external_ads_prbs9_reference as ads


REPO_ROOT = Path(__file__).resolve().parents[1]
UI_SECONDS = ads.UI_SECONDS
DT_SECONDS = ads.SAMPLE_INTERVAL_SECONDS
TOTAL_SAMPLES = ads.TOTAL_SAMPLES
ADS_INCLUSIVE_SAMPLES = TOTAL_SAMPLES + 1
EDGE_SECONDS = 1.0e-16
PULSE_START_INDEX = 511 * 32 + 1
PULSE_END_INDEX = PULSE_START_INDEX + 32
PULSE_START_SECONDS = 511 * UI_SECONDS + DT_SECONDS / 2.0
PULSE_END_SECONDS = PULSE_START_SECONDS + UI_SECONDS
PULSE_FALL_END_SECONDS = PULSE_END_SECONDS + EDGE_SECONDS
FMAX_HZ = 40_000_000_000.0
DELTA_F_HZ = 39_062_500.0
FORBIDDEN = ("prbssrc", "ami", "ibis", ".dll", "getwave", "ctspcie")


class FixedPulseError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_external(path: Path, kind: str, *, exists: bool = True) -> Path:
    resolved = path.resolve(strict=exists)
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return resolved
    raise FixedPulseError(f"{kind}_must_be_external")


def source_identity(source: Path) -> tuple[int, str]:
    value = source.stat().st_size, sha256_file(source)
    if value != (1_834_156, "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"):
        raise FixedPulseError("selected_s4p_identity_mismatch")
    return value


def _pwl(voltage: float) -> str:
    return (
        "pwl(time, "
        f"0 sec,0 V, {PULSE_START_SECONDS:.17g} sec,0 V, "
        f"{PULSE_START_SECONDS + EDGE_SECONDS:.17g} sec,{voltage:.17g} V, "
        f"{PULSE_END_SECONDS:.17g} sec,{voltage:.17g} V, "
        f"{PULSE_FALL_END_SECONDS:.17g} sec,0 V, "
        f"{TOTAL_SAMPLES * DT_SECONDS:.17g} sec,0 V)"
    )


def build_netlist() -> str:
    stop = f"{TOTAL_SAMPLES * DT_SECONDS:.17g} sec"
    step = f"{DT_SECONDS:.17g} sec"
    return "\n".join(
        [
            f"V_Source:SOURCE_P srcp 0 Type=\"VtPWL\" V_Tran={_pwl(0.5)}",
            f"V_Source:SOURCE_M srcm 0 Type=\"VtPWL\" V_Tran={_pwl(-0.5)}",
            "R:TX_PLUS_SERIES srcp txp R=50 Ohm",
            "R:TX_MINUS_SERIES srcm txm R=50 Ohm",
            'SnP:CHANNEL txp rxp txm rxm File="channel_gen5_highloss.s4p" NumPorts=4',
            "R:RX_PLUS_LOAD rxp 0 R=50 Ohm",
            "R:RX_MINUS_LOAD rxm 0 R=50 Ohm",
            (
                f"Tran:TRAN StartTime=0 sec StopTime={stop} MaxTimeStep={step} LimitStepForTL=no "
                "TimeStepControl=0 TruncTol=7.0 ChargeTol=1.0e-14 IntegMethod=0 MaxGearOrder=2 Mu=0.5 "
                "MaxOrder=4 Freq[1]=1.0 GHz Order[1]=3 HB_Window=no HB_Sol=no "
                f"ImpLFEOn=yes ImpApprox=no ImpMaxFreq={FMAX_HZ:.17g} Hz ImpDeltaFreq={DELTA_F_HZ:.17g} Hz "
                "ShortTL_Delay=1.0 psec ImpMode=1 UseInitCond=no LoadGminDC=no CheckKCL=yes "
                "CheckOnlyDeltaV=yes OverloadAlert=no DeviceBypass=no MaxIters=10 MaxItersDC=200 "
                "DevOpPtLevel=0 StatusLevel=2 OutputAllPoints=yes NoiseScale=1 ImpEnforcePassivity=yes "
                'OutputPlan="P3C_OUTPUT"'
            ),
            'OutputPlan:P3C_OUTPUT Type="Output" UseNodeNestLevel=yes NodeNestLevel=2 UseEquationNestLevel=yes EquationNestLevel=2 UseSavedEquationNestLevel=yes SavedEquationNestLevel=2 UseDeviceCurrentNestLevel=no DeviceCurrentNestLevel=0 DeviceCurrentDeviceType="All" DeviceCurrentSymSyntax=yes UseCurrentNestLevel=yes CurrentNestLevel=999 UseDeviceVoltageNestLevel=no DeviceVoltageNestLevel=0 DeviceVoltageDeviceType="All"',
            'Options:unknown TopDesignName="sipi_p3c_fixed_pulse_operator"',
            "",
        ]
    )


def assert_fixed_netlist(netlist: str) -> None:
    lowered = netlist.lower()
    if any(token in lowered for token in FORBIDDEN):
        raise FixedPulseError("forbidden_runtime_token")
    required = (
        "V_Source:SOURCE_P", "V_Source:SOURCE_M", "R:TX_PLUS_SERIES", "R:TX_MINUS_SERIES",
        "SnP:CHANNEL", "R:RX_PLUS_LOAD", "R:RX_MINUS_LOAD", "Tran:TRAN",
        "ImpMaxFreq=40000000000 Hz", "ImpDeltaFreq=39062500 Hz", "ImpMode=1",
        "ImpEnforcePassivity=yes", "OutputAllPoints=yes",
    )
    if any(token not in netlist for token in required):
        raise FixedPulseError("fixed_netlist_surface_mismatch")
    if netlist.count("R=50 Ohm") != 4 or netlist.count("V_Source:") != 2:
        raise FixedPulseError("fixed_topology_mismatch")


def parse_dataset(path: Path) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    if not ads.DSDUMP.is_file():
        raise FixedPulseError("ads_dsdump_not_found")
    result = ads.subprocess.run([str(ads.DSDUMP), str(path)], check=False, capture_output=True, text=True, encoding="utf-8", errors="strict")
    if result.returncode:
        raise FixedPulseError("ads_dataset_dump_rejected")
    lines = iter(result.stdout.splitlines())
    names: list[str] = []
    count: int | None = None
    expected_names = ["srcp", "srcm", "txp", "txm", "rxp", "rxm", "SOURCE_M.i", "SOURCE_P.i", "tranorder"]
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('* Dependent number of variables:'):
            continue
        if any(stripped.startswith(f'{index}: "{name}"') for index, name in enumerate(expected_names)):
            names.append(stripped.split('"')[1])
        if stripped.startswith('* Number of points:'):
            count = int(stripped.split(':', 1)[1].strip())
            break
    if names != expected_names or count != ADS_INCLUSIVE_SAMPLES:
        raise FixedPulseError("ads_dataset_shape_rejected")
    columns = ([], [], [], [], [])
    for index in range(count):
        row = next(lines, None)
        if row is None or not row.startswith(f"{index}:"):
            raise FixedPulseError("ads_dataset_point_order_rejected")
        values = [next(lines, None) for _ in range(9)]
        if any(value is None for value in values):
            raise FixedPulseError("ads_dataset_point_truncated")
        time = float(row.split(':', 1)[1].strip())
        _srcp, _srcm, txp, txm, rxp, rxm, _source_m_i, _source_p_i, _ = (float(value) for value in values)
        expected = index * DT_SECONDS
        if not all(math.isfinite(value) for value in (time, txp, txm, rxp, rxm)) or abs(time - expected) > 8 * math.ulp(max(abs(time), abs(expected))):
            raise FixedPulseError("ads_dataset_grid_or_finite_rejected")
        for column, value in zip(columns, (time, txp, txm, rxp, rxm), strict=True):
            column.append(value)
    return columns


def canonical_payload(columns: tuple[list[float], list[float], list[float], list[float], list[float]]) -> bytes:
    time, txp, txm, rxp, rxm = columns
    payload = bytearray()
    for index in range(TOTAL_SAMPLES):
        payload.extend(struct.pack("<ddd", time[index], txp[index] - txm[index], rxp[index] - rxm[index]))
    return bytes(payload)


def materialize_run(source: Path, destination: Path, *, invoke_ads: bool) -> dict[str, Any]:
    if destination.exists():
        raise FixedPulseError("run_directory_must_not_exist")
    destination.mkdir(parents=True)
    data = destination / "data"; data.mkdir()
    copied = data / "channel_gen5_highloss.s4p"
    before = source_identity(source)
    shutil.copyfile(source, copied)
    if source_identity(source) != before or (copied.stat().st_size, sha256_file(copied)) != before:
        raise FixedPulseError("selected_s4p_copy_drift")
    netlist = build_netlist(); assert_fixed_netlist(netlist)
    netlist_path = destination / "p3c_fixed_pulse_operator.ckt"
    netlist_path.write_text(netlist, encoding="ascii", newline="\n")
    manifest: dict[str, Any] = {
        "schema": "sipi.p3c-external-ads-fixed-pulse-operator-run.v1",
        "runtime_invoked": False,
        "source": {"byte_length": before[0], "sha256": before[1]},
        "pulse": {"open_circuit_differential_volts": 1.0, "edge_seconds": EDGE_SECONDS, "start_seconds": PULSE_START_SECONDS, "width_seconds": UI_SECONDS, "start_index": PULSE_START_INDEX, "end_index_exclusive": PULSE_END_INDEX},
        "controller": {"imp_max_freq_hz": FMAX_HZ, "imp_delta_freq_hz": DELTA_F_HZ, "imp_mode": 1, "passivity_enforced": True},
        "generated": {"netlist_sha256": sha256_file(netlist_path), "netlist_byte_length": netlist_path.stat().st_size},
    }
    if invoke_ads:
        ads.run_ads(netlist_path, destination, data)
        columns = parse_dataset(destination / "p3c_prbs9.ds")
        payload = canonical_payload(columns)
        payload_path = destination / "canonical_pulse_operator_le_f64.bin"; payload_path.write_bytes(payload)
        manifest["runtime_invoked"] = True
        manifest["waveform"] = {"ads_inclusive_samples": ADS_INCLUSIVE_SAMPLES, "half_open_samples": TOTAL_SAMPLES, "payload_sha256": hashlib.sha256(payload).hexdigest(), "payload_byte_length": len(payload), "tx_common_mode_sha256": hashlib.sha256(b"".join(struct.pack("<d", (a + b) / 2.0) for a, b in zip(columns[1][:-1], columns[2][:-1], strict=True))).hexdigest(), "rx_common_mode_sha256": hashlib.sha256(b"".join(struct.pack("<d", (a + b) / 2.0) for a, b in zip(columns[3][:-1], columns[4][:-1], strict=True))).hexdigest()}
    (destination / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="ascii", newline="\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s4p", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not ads.valid_run_id(args.run_id):
            raise FixedPulseError("run_id_invalid")
        source = require_external(args.s4p, "s4p")
        root = require_external(args.output_root, "output_root")
        result = materialize_run(source, root / args.run_id, invoke_ads=args.run)
    except (OSError, ValueError, FixedPulseError, ads.ExternalReferenceError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True)); return 2
    print(json.dumps({"status": "ads_run_completed" if args.run else "generated", "netlist_sha256": result["generated"]["netlist_sha256"]}, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
