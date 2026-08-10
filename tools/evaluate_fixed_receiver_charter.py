"""Independent, oracle-only evaluator for the approved fixed receiver charter."""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path


WAVEFORM_SAMPLES = 1024
REFERENCE_BITS = 128
SAMPLES_PER_UI = 8
TRAINING_SYMBOLS = 32
MEASUREMENT_SYMBOLS = 96
TAP_COUNT = 5
MINIMUM_AMPLITUDE_VOLTS = 1.0e-6
MINIMUM_PHASE_MARGIN = 0.01
TRAINING_STEP = 0.25
SCHEMA = "sipi.receiver-charter-evaluator.v1"


class CharterRejection(ValueError):
    """A fail-closed rejection under the approved charter."""


def _load_waveform(path: Path) -> list[float]:
    raw = path.read_bytes()
    if len(raw) != WAVEFORM_SAMPLES * 8:
        raise CharterRejection("waveform sidecar length is invalid")
    values = list(struct.iter_unpack("<d", raw))
    waveform = [value[0] for value in values]
    if not all(math.isfinite(value) for value in waveform):
        raise CharterRejection("waveform sidecar contains non-finite values")
    return waveform


def _load_bits(path: Path) -> list[bool]:
    raw = path.read_bytes()
    if len(raw) != REFERENCE_BITS or any(bit not in (0, 1) for bit in raw):
        raise CharterRejection("reference-bit sidecar is invalid")
    bits = [bit == 1 for bit in raw]
    if not any(bits[:TRAINING_SYMBOLS]) or all(bits[:TRAINING_SYMBOLS]):
        raise CharterRejection("training symbols must contain both classes")
    return bits


def _checked(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise CharterRejection(f"non-finite receiver intermediate: {label}")
    return value


def _symbols(bits: list[bool]) -> list[float]:
    return [1.0 if bit else -1.0 for bit in bits]


def _calibrate(waveform: list[float], bits: list[bool]) -> tuple[int, float, float]:
    candidates: list[tuple[int, float, float, float]] = []
    for phase in range(SAMPLES_PER_UI):
        one = [waveform[phase + SAMPLES_PER_UI * index] for index in range(TRAINING_SYMBOLS) if bits[index]]
        zero = [waveform[phase + SAMPLES_PER_UI * index] for index in range(TRAINING_SYMBOLS) if not bits[index]]
        if not one or not zero:
            raise CharterRejection("training symbols must contain both classes")
        mean_one = _checked(sum(one) / len(one), "mean one")
        mean_zero = _checked(sum(zero) / len(zero), "mean zero")
        center = _checked((mean_one + mean_zero) / 2.0, "center")
        amplitude = _checked((mean_one - mean_zero) / 2.0, "amplitude")
        candidates.append((phase, center, amplitude, abs(mean_one - mean_zero)))
    ordered = sorted(candidates, key=lambda candidate: candidate[3], reverse=True)
    phase, center, amplitude, best_score = ordered[0]
    second_score = ordered[1][3]
    if (
        best_score == 0.0
        or best_score == second_score
        or _checked((best_score - second_score) / best_score, "phase margin") < MINIMUM_PHASE_MARGIN
    ):
        raise CharterRejection("cdr_ambiguous")
    if abs(amplitude) < MINIMUM_AMPLITUDE_VOLTS:
        raise CharterRejection("amplitude_too_small")
    return phase, center, amplitude


def _dot(taps: list[float], feedback: list[float]) -> float:
    return _checked(sum(tap * symbol for tap, symbol in zip(taps, feedback, strict=True)), "dfe dot")


def _training_feedback(symbols: list[float], index: int) -> list[float]:
    return [symbols[index - delay] if index >= delay else 0.0 for delay in range(1, TAP_COUNT + 1)]


def evaluate(waveform: list[float], bits: list[bool]) -> dict:
    if len(waveform) != WAVEFORM_SAMPLES or not all(math.isfinite(value) for value in waveform):
        raise CharterRejection("waveform must be finite f64[1024]")
    if len(bits) != REFERENCE_BITS:
        raise CharterRejection("reference bits must contain 128 symbols")
    phase, center, amplitude = _calibrate(waveform, bits)
    normalized = [_checked((waveform[phase + SAMPLES_PER_UI * index] - center) / amplitude, "normalization") for index in range(REFERENCE_BITS)]
    symbols = _symbols(bits)
    taps = [0.0] * TAP_COUNT
    for index in range(TRAINING_SYMBOLS):
        feedback = _training_feedback(symbols, index)
        z = _checked(normalized[index] - _dot(taps, feedback), "training decision")
        error = _checked(symbols[index] - z, "training error")
        taps = [_checked(tap - TRAINING_STEP * error * prior, "tap update") for tap, prior in zip(taps, feedback, strict=True)]
    decisions: list[str] = []
    errors = 0
    for index in range(TRAINING_SYMBOLS, REFERENCE_BITS):
        feedback: list[float] = []
        for delay in range(1, TAP_COUNT + 1):
            prior = index - delay
            feedback.append(symbols[prior] if prior < TRAINING_SYMBOLS else {"+": 1.0, "-": -1.0, "0": 0.0}[decisions[prior - TRAINING_SYMBOLS]])
        z = _checked(normalized[index] - _dot(taps, feedback), "measurement decision")
        decision = "+" if z > 0.0 else "-" if z < 0.0 else "0"
        if decision == "0" or (decision == "+") != bits[index]:
            errors += 1
        decisions.append(decision)
    return {
        "schema": SCHEMA,
        "status": "accepted",
        "phase": phase,
        "locked": True,
        "centerVolts": center,
        "amplitudeVolts": amplitude,
        "frozenTaps": taps,
        "decisions": "".join(decisions),
        "errorCount": errors,
        "berNumerator": errors,
        "berDenominator": MEASUREMENT_SYMBOLS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--waveform", type=Path, required=True)
    parser.add_argument("--bits", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.result.exists():
            raise CharterRejection("result path must not already exist")
        result = evaluate(_load_waveform(args.waveform), _load_bits(args.bits))
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, CharterRejection) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": "accepted"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
