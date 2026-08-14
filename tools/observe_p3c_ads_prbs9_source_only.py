"""Observe the approved ADS PRBS9 source-only matched-load strobe behavior."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import run_p3c_external_ads_prbs9_source_only as runner


REPO_ROOT = Path(__file__).resolve().parents[1]
THIRD_START = runner.TOTAL_SAMPLES - runner.PERIOD_BITS * runner.SAMPLES_PER_UI
PERIOD_SAMPLES = runner.PERIOD_BITS * runner.SAMPLES_PER_UI


class ObservationError(RuntimeError):
    pass


def _hex_bits(value: float) -> str:
    return f"{struct.unpack('>Q', struct.pack('>d', value))[0]:016x}"


def _digest(domain: bytes, values: Iterable[float]) -> str:
    payload = bytearray(domain)
    values = tuple(values)
    payload.extend(len(values).to_bytes(8, "big"))
    payload.extend(struct.pack(">Q", struct.unpack(">Q", struct.pack(">d", runner.SAMPLE_INTERVAL_SECONDS))[0]))
    for value in values:
        if not math.isfinite(value):
            raise ObservationError("nonfinite_digest_input")
        payload.extend(struct.pack(">Q", struct.unpack(">Q", struct.pack(">d", value))[0]))
    return hashlib.sha256(payload).hexdigest()


def projected_loaded_differential() -> list[float]:
    period = runner.prbs9_period()
    symbols = [-0.5 if bit == "0" else 0.5 for bit in period]
    return [symbols[(index // runner.SAMPLES_PER_UI) % runner.PERIOD_BITS] for index in range(runner.TOTAL_SAMPLES)]


def read_canonical_payload(path: Path) -> tuple[list[float], list[float], str]:
    payload = path.read_bytes()
    if len(payload) != runner.TOTAL_SAMPLES * 24:
        raise ObservationError("canonical_payload_length")
    differential: list[float] = []
    common_mode: list[float] = []
    for index in range(runner.TOTAL_SAMPLES):
        time, loaded, common = struct.unpack_from("<ddd", payload, index * 24)
        expected = index * runner.SAMPLE_INTERVAL_SECONDS
        if not all(math.isfinite(value) for value in (time, loaded, common)) or abs(time - expected) > 8 * math.ulp(max(abs(time), abs(expected))):
            raise ObservationError("canonical_payload_grid")
        differential.append(loaded)
        common_mode.append(common)
    return differential, common_mode, hashlib.sha256(payload).hexdigest()


def summary(expected: list[float], observed: list[float], common_mode: list[float], indexes: range) -> dict[str, object]:
    selected = list(indexes)
    if not selected:
        raise ObservationError("empty_diagnostic_partition")
    reference = [expected[index] for index in selected]
    actual = [observed[index] for index in selected]
    residual = [actual[index] - reference[index] for index in range(len(selected))]
    reference_energy = math.fsum(value * value for value in reference)
    if not math.isfinite(reference_energy) or reference_energy <= 0.0:
        raise ObservationError("zero_reference_energy")
    residual_energy = math.fsum(value * value for value in residual)
    if not math.isfinite(residual_energy):
        raise ObservationError("residual_overflow")
    max_index, max_residual = max(enumerate(residual), key=lambda item: (abs(item[1]), -item[0]))
    cm_values = [common_mode[index] for index in selected]
    cm_peak = max(abs(value) for value in cm_values)
    count = len(selected)
    return {
        "sample_count": count,
        "reference_rms_bits": _hex_bits(math.sqrt(reference_energy / count)),
        "ads_rms_bits": _hex_bits(math.sqrt(math.fsum(value * value for value in actual) / count)),
        "residual_rms_bits": _hex_bits(math.sqrt(residual_energy / count)),
        "signed_residual_mean_bits": _hex_bits(math.fsum(residual) / count),
        "nrmse_bits": _hex_bits(math.sqrt(residual_energy / reference_energy)),
        "residual_sha256": _digest(b"sipi.p3c.ads-source-only.residual.v1\0", residual),
        "max_absolute_residual_bits": _hex_bits(abs(max_residual)),
        "max_absolute_residual_first_index": selected[max_index],
        "common_mode_sha256": _digest(b"sipi.p3c.ads-source-only.common-mode.v1\0", cm_values),
        "common_mode_max_absolute_bits": _hex_bits(cm_peak),
    }


def run_once(root: Path, index: int) -> dict[str, object]:
    destination = root / f"run-{index}"
    manifest = runner.materialize_run(destination, invoke_ads=True)
    try:
        waveform = manifest.get("waveform_observation")
        generated = manifest.get("generated")
        if not isinstance(waveform, dict) or not isinstance(generated, dict) or manifest.get("runtime_invoked") is not True:
            raise ObservationError("runner_manifest_shape")
        observed, common_mode, payload_sha256 = read_canonical_payload(destination / "canonical_source_le_f64.bin")
        expected = projected_loaded_differential()
        if len(observed) != len(expected):
            raise ObservationError("projection_length")
        periods = [summary(expected, observed, common_mode, range(offset, offset + PERIOD_SAMPLES)) for offset in range(0, runner.TOTAL_SAMPLES, PERIOD_SAMPLES)]
        boundary = summary(expected, observed, common_mode, range(THIRD_START, runner.TOTAL_SAMPLES, runner.SAMPLES_PER_UI))
        interior = summary(expected, observed, common_mode, (index for index in range(THIRD_START, runner.TOTAL_SAMPLES) if index % runner.SAMPLES_PER_UI != 0))
        return {
            "netlist_sha256": generated.get("netlist_sha256"),
            "canonical_payload_sha256": payload_sha256,
            "period_summaries": periods,
            "third_period": summary(expected, observed, common_mode, range(THIRD_START, runner.TOTAL_SAMPLES)),
            "third_period_ui_boundary": boundary,
            "third_period_ui_interior": interior,
        }
    finally:
        if destination.exists():
            shutil.rmtree(destination)


def external_path(path: Path, *, kind: str, allow_missing: bool) -> Path:
    candidate = path.resolve(strict=not allow_missing)
    try:
        candidate.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return candidate
    raise ObservationError(f"{kind}_must_not_be_inside_repository")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        output_root = external_path(arguments.output_root, kind="output_root", allow_missing=False)
        report = external_path(arguments.report, kind="report", allow_missing=True)
        if report.exists() or not output_root.is_dir():
            raise ObservationError("external_output_path_invalid")
        work = Path(tempfile.mkdtemp(prefix="sipi-p3c-source-only-", dir=output_root))
        try:
            first = run_once(work, 1)
            second = run_once(work, 2)
            if first != second:
                raise ObservationError("fresh_runs_not_identical")
            report.write_text(json.dumps({"schema": "sipi.p3c.ads-prbssrc-source-only-observation.v1", "status": "observed", "fixed_mapping": "ads_loaded_differential_equals_0.5_times_product_projection", "ads_inclusive_samples": runner.ADS_INCLUSIVE_SAMPLES, "canonical_half_open_samples": runner.TOTAL_SAMPLES, "fresh_runs": [first, second], "cleanup_status": "complete"}, sort_keys=True, indent=2) + "\n", encoding="ascii", newline="\n")
        finally:
            if work.exists():
                shutil.rmtree(work)
    except (OSError, ValueError, ObservationError, runner.SourceOnlyError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "observed", "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
