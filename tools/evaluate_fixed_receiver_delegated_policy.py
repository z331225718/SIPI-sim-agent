"""Independent, oracle-only evaluator for the delegated receiver policy."""

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
SCHEMA = "sipi.receiver-delegated-policy-evaluator.v1"


class PolicyRejection(ValueError):
    """A fail-closed rejection under the delegated policy."""


def _finite(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise PolicyRejection(f"non-finite receiver intermediate: {label}")
    return value


def _load_waveform(path: Path) -> list[float]:
    raw = path.read_bytes()
    if len(raw) != WAVEFORM_SAMPLES * 8:
        raise PolicyRejection("waveform sidecar length is invalid")
    values = [item[0] for item in struct.iter_unpack("<d", raw)]
    if not all(math.isfinite(value) for value in values):
        raise PolicyRejection("waveform sidecar contains non-finite values")
    return values


def _load_bits(path: Path) -> list[bool]:
    raw = path.read_bytes()
    if len(raw) != REFERENCE_BITS or any(value not in (0, 1) for value in raw):
        raise PolicyRejection("reference-bit sidecar is invalid")
    bits = [value == 1 for value in raw]
    if not any(bits[:TRAINING_SYMBOLS]) or all(bits[:TRAINING_SYMBOLS]):
        raise PolicyRejection("training symbols must contain both classes")
    return bits


def _calibrate(waveform: list[float], bits: list[bool]) -> tuple[int, float, float, str, str]:
    candidates: list[tuple[int, float, float, float]] = []
    for phase in range(SAMPLES_PER_UI):
        one_total = 0.0
        zero_total = 0.0
        one_count = 0
        zero_count = 0
        for index in range(TRAINING_SYMBOLS):
            value = waveform[phase + SAMPLES_PER_UI * index]
            if bits[index]:
                one_total = _finite(one_total + value, "mean one sum")
                one_count += 1
            else:
                zero_total = _finite(zero_total + value, "mean zero sum")
                zero_count += 1
        if not one_count or not zero_count:
            raise PolicyRejection("training symbols must contain both classes")
        mean_one = _finite(one_total / one_count, "mean one")
        mean_zero = _finite(zero_total / zero_count, "mean zero")
        center = _finite((mean_one + mean_zero) / 2.0, "center")
        amplitude = _finite((mean_one - mean_zero) / 2.0, "amplitude")
        candidates.append((phase, center, amplitude, abs(mean_one - mean_zero)))

    ordered = sorted(candidates, key=lambda candidate: candidate[3], reverse=True)
    best = ordered[0]
    second = ordered[1]
    if best[3] <= 0.0 or not math.isfinite(best[3]):
        raise PolicyRejection("cdr_unqualified")
    margin = _finite((best[3] - second[3]) / best[3], "phase margin")
    if best[3] != second[3] and margin >= MINIMUM_PHASE_MARGIN:
        chosen = best
        selection = "unique_locked"
        lock_state = "locked"
    else:
        floor = _finite(best[3] / (1.0 + MINIMUM_PHASE_MARGIN), "contender floor")
        contenders = [candidate for candidate in candidates if candidate[3] >= floor]
        if not contenders:
            raise PolicyRejection("cdr_unqualified")
        chosen = min(contenders, key=lambda candidate: candidate[0])
        selection = "delegated_ambiguous_tie_break"
        lock_state = "policy_selected_not_locked"
    if abs(chosen[2]) < MINIMUM_AMPLITUDE_VOLTS:
        raise PolicyRejection("amplitude_too_small")
    return chosen[0], chosen[1], chosen[2], selection, lock_state


def _dot(taps: list[float], feedback: list[float]) -> float:
    total = 0.0
    for tap, prior in zip(taps, feedback, strict=True):
        total = _finite(total + _finite(tap * prior, "dfe product"), "dfe dot")
    return total


def evaluate(waveform: list[float], bits: list[bool]) -> dict:
    if len(waveform) != WAVEFORM_SAMPLES or not all(math.isfinite(value) for value in waveform):
        raise PolicyRejection("waveform must be finite f64[1024]")
    if len(bits) != REFERENCE_BITS:
        raise PolicyRejection("reference bits must contain 128 symbols")
    phase, center, amplitude, selection, lock_state = _calibrate(waveform, bits)
    symbols = [1.0 if bit else -1.0 for bit in bits]
    normalized = [
        _finite((waveform[phase + SAMPLES_PER_UI * index] - center) / amplitude, "normalization")
        for index in range(REFERENCE_BITS)
    ]
    taps = [0.0] * TAP_COUNT
    for index in range(TRAINING_SYMBOLS):
        feedback = [symbols[index - delay] if index >= delay else 0.0 for delay in range(1, TAP_COUNT + 1)]
        z = _finite(normalized[index] - _dot(taps, feedback), "training decision")
        error = _finite(symbols[index] - z, "training error")
        taps = [_finite(tap - TRAINING_STEP * error * prior, "tap update") for tap, prior in zip(taps, feedback, strict=True)]
    decisions: list[str] = []
    errors = 0
    for index in range(TRAINING_SYMBOLS, REFERENCE_BITS):
        feedback = []
        for delay in range(1, TAP_COUNT + 1):
            prior = index - delay
            feedback.append(symbols[prior] if prior < TRAINING_SYMBOLS else {"+": 1.0, "-": -1.0, "0": 0.0}[decisions[prior - TRAINING_SYMBOLS]])
        z = _finite(normalized[index] - _dot(taps, feedback), "measurement decision")
        decision = "+" if z > 0.0 else "-" if z < 0.0 else "0"
        if decision == "0" or (decision == "+") != bits[index]:
            errors += 1
        decisions.append(decision)
    return {
        "schema": SCHEMA,
        "status": "accepted",
        "phase": phase,
        "phaseSelection": selection,
        "cdrLockState": lock_state,
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
    if args.result.exists():
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": "result_path_exists"}))
        return 2
    try:
        result = evaluate(_load_waveform(args.waveform), _load_bits(args.bits))
    except PolicyRejection as error:
        result = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    except OSError:
        result = {"schema": SCHEMA, "status": "rejected", "reason": "sidecar_io_failure"}
    try:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": "result_write_failure"}))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": result["status"]}))
    return 0 if result["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
