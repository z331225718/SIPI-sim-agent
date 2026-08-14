"""Strictly inspect whether ADS pre- and final-spectrum grids are comparable.

This external-only P3C helper reuses the fixed 04aw ADS pulse bench without
changing its topology or controller.  It reads only the structured spectrum
surfaces explicitly authorized by the owner.  No interpolation, resampling,
or frequency-domain repair is permitted: unequal grids are the terminal,
hash-only observation outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SURFACE_PATH = ROOT / "tools" / "run_p3c_external_ads_fixed_pulse_passivity_surface.py"
SPEC = importlib.util.spec_from_file_location("p3c_passivity_surface", SURFACE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("passivity_surface_import_unavailable")
SURFACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SURFACE)

VECTORSET_NAME = re.compile(r'^\* Vectorset name: "([^"\\]+)"$')
POINT_COUNT = re.compile(r"^\* Number of points: (\d+)$")
AXIS_ROW = re.compile(r"^(\d+): (.+)$")
COMPLEX_VALUE = re.compile(r"^\([^,]+, [^)]+\)$")
SELECTED_NAME = re.compile(r"^TRAN\.CHANNEL\.CMP1_(S0|FFT_IMP)\(([1-4]);([1-4])\)$")
EXPECTED_MEMBERS = tuple((row, column) for row in range(1, 5) for column in range(1, 5))


class PreFinalSpectrumError(RuntimeError):
    pass


def _f64_bits(value: float) -> int:
    import struct

    return int.from_bytes(struct.pack(">d", value), "big")


def _axis_digest(axis: tuple[float, ...], domain: bytes) -> str:
    payload = bytearray(domain)
    payload.extend(len(axis).to_bytes(8, "big"))
    for value in axis:
        payload.extend(_f64_bits(value).to_bytes(8, "big"))
    return hashlib.sha256(payload).hexdigest()


def _axis_bits_equal(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return len(left) == len(right) and all(
        _f64_bits(left_value) == _f64_bits(right_value)
        for left_value, right_value in zip(left, right, strict=True)
    )


def _axis_summary(axis: tuple[float, ...], domain: bytes) -> dict[str, Any]:
    if len(axis) < 2:
        raise PreFinalSpectrumError("spectrum_axis_too_short")
    if not all(math.isfinite(value) for value in axis):
        raise PreFinalSpectrumError("spectrum_axis_nonfinite")
    if any(right <= left for left, right in zip(axis, axis[1:])):
        raise PreFinalSpectrumError("spectrum_axis_not_strictly_increasing")
    return {
        "point_count": len(axis),
        "first_frequency_bits": f"{_f64_bits(axis[0]):016x}",
        "last_frequency_bits": f"{_f64_bits(axis[-1]):016x}",
        "first_step_bits": f"{_f64_bits(axis[1] - axis[0]):016x}",
        "axis_sha256": _axis_digest(axis, domain),
    }


def _selected_axes(dataset: Path) -> dict[tuple[str, int, int], tuple[float, ...]]:
    if not SURFACE.PULSE.ads.DSDUMP.is_file():
        raise PreFinalSpectrumError("ads_dsdump_not_found")
    result = SURFACE.PULSE.ads.subprocess.run(
        [str(SURFACE.PULSE.ads.DSDUMP), str(dataset)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if result.returncode:
        raise PreFinalSpectrumError("ads_dataset_dump_rejected")
    lines = result.stdout.splitlines()
    records: dict[tuple[str, int, int], tuple[float, ...]] = {}
    index = 0
    while index < len(lines):
        match = VECTORSET_NAME.match(lines[index].strip())
        if match is None:
            index += 1
            continue
        selected = SELECTED_NAME.match(match.group(1))
        index += 1
        if selected is None:
            continue
        kind, row_text, column_text = selected.groups()
        key = kind, int(row_text), int(column_text)
        if key in records:
            raise PreFinalSpectrumError("spectrum_member_duplicate")
        header_start = index
        while index < len(lines) and POINT_COUNT.match(lines[index].strip()) is None:
            if VECTORSET_NAME.match(lines[index].strip()) is not None:
                raise PreFinalSpectrumError("spectrum_points_missing")
            index += 1
        if index == len(lines):
            raise PreFinalSpectrumError("spectrum_points_missing")
        header = "\n".join(line.strip() for line in lines[header_start:index])
        if '0: "freq" 0 r' not in header or '0: "freqResp" 0 c' not in header:
            raise PreFinalSpectrumError("spectrum_variable_surface_mismatch")
        count = int(POINT_COUNT.match(lines[index].strip()).group(1))
        index += 1
        axis: list[float] = []
        for expected_index in range(count):
            if index + 1 >= len(lines):
                raise PreFinalSpectrumError("spectrum_points_truncated")
            axis_match = AXIS_ROW.match(lines[index].strip())
            if axis_match is None or int(axis_match.group(1)) != expected_index:
                raise PreFinalSpectrumError("spectrum_axis_index_mismatch")
            try:
                frequency = float(axis_match.group(2))
            except ValueError as error:
                raise PreFinalSpectrumError("spectrum_axis_parse_rejected") from error
            if not math.isfinite(frequency):
                raise PreFinalSpectrumError("spectrum_axis_nonfinite")
            if not COMPLEX_VALUE.match(lines[index + 1].strip()):
                raise PreFinalSpectrumError("spectrum_complex_surface_mismatch")
            axis.append(frequency)
            index += 2
        records[key] = tuple(axis)
    required = {(kind, row, column) for kind in ("S0", "FFT_IMP") for row, column in EXPECTED_MEMBERS}
    if set(records) != required:
        raise PreFinalSpectrumError("spectrum_member_set_mismatch")
    return records


def compare_pre_to_final_axes(dataset: Path) -> dict[str, Any]:
    records = _selected_axes(dataset)
    summaries: dict[str, dict[str, Any]] = {}
    canonical: dict[str, tuple[float, ...]] = {}
    for kind in ("S0", "FFT_IMP"):
        axes = [records[(kind, row, column)] for row, column in EXPECTED_MEMBERS]
        if any(not _axis_bits_equal(axis, axes[0]) for axis in axes[1:]):
            raise PreFinalSpectrumError("spectrum_member_axis_mismatch")
        canonical[kind] = axes[0]
        summaries[kind.lower()] = _axis_summary(
            axes[0],
            f"sipi.p3c.ads-pre-final-spectrum.{kind.lower()}.axis.v1\x00".encode("ascii"),
        )
    if not _axis_bits_equal(canonical["S0"], canonical["FFT_IMP"]):
        outcome = "pre_final_axis_not_identical"
    else:
        # This narrow slice stops at the exact-grid admission.  A later scope
        # may compare complex payloads only after this condition is observed.
        outcome = "pre_final_axis_identical_payload_delta_not_in_scope"
    return {
        "matrix_dimension": 4,
        "members_per_surface": len(EXPECTED_MEMBERS),
        "s0": summaries["s0"],
        "fft_imp": summaries["fft_imp"],
        "outcome": outcome,
    }


def materialize_probe(source: Path, destination: Path, *, invoke_ads: bool) -> dict[str, Any]:
    result = SURFACE.materialize_probe(source, destination, invoke_ads=invoke_ads)
    if invoke_ads:
        comparison = compare_pre_to_final_axes(destination / "p3c_prbs9.ds")
        result["pre_final_axis_comparison"] = comparison
    (destination / "manifest.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="ascii",
        newline="\n",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s4p", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not SURFACE.PULSE.ads.valid_run_id(args.run_id):
            raise PreFinalSpectrumError("run_id_invalid")
        source = SURFACE.PULSE.require_external(args.s4p, "s4p")
        root = SURFACE.PULSE.require_external(args.output_root, "output_root")
        result = materialize_probe(source, root / args.run_id, invoke_ads=args.run)
    except (OSError, ValueError, PreFinalSpectrumError, SURFACE.PassivitySurfaceError, SURFACE.PULSE.FixedPulseError, SURFACE.PULSE.ads.ExternalReferenceError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "ads_run_completed" if args.run else "generated", "pre_final_axis_comparison": result.get("pre_final_axis_comparison")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
