"""Time the pinned Agent-Spice Python RFM evaluator on the shared input."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np


def median(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def checksum(values: np.ndarray) -> dict[str, object]:
    flattened = np.asarray(values).reshape(-1)
    first = complex(flattened[0])
    return {
        "sum_real": float(np.real(flattened).sum()),
        "sum_imag": float(np.imag(flattened).sum()),
        "sum_abs_squared": float(np.abs(flattened).dot(np.abs(flattened))),
        "first_re": float(first.real),
        "first_im": float(first.imag),
        "first_re_bits": f"{np.asarray(first.real, dtype=np.float64).view(np.uint64):016x}",
        "first_im_bits": f"{np.asarray(first.imag, dtype=np.float64).view(np.uint64):016x}",
        "response_count": int(values.shape[1] * values.shape[2]),
        "frequency_count": int(values.shape[0]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rfm", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frequency-count", type=int, default=262_144)
    parser.add_argument("--fmax-hz", type=float, default=200.0e9)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=7)
    arguments = parser.parse_args()
    if not (1 <= arguments.frequency_count <= 2_000_000):
        parser.error("frequency-count is outside the bounded range")
    if not np.isfinite(arguments.fmax_hz) or arguments.fmax_hz <= 0:
        parser.error("fmax-hz must be finite and positive")
    if not (0 <= arguments.warmups <= 100 and 1 <= arguments.repetitions <= 100):
        parser.error("warmups/repetitions are outside the bounded range")
    source = arguments.rfm.resolve()
    if not source.is_file():
        parser.error("RFM input does not exist")
    from agent_spice.sparam.rfm import parse_cadence_rfm

    model = parse_cadence_rfm(source)
    if arguments.frequency_count == 1:
        frequencies = np.array([0.0], dtype=np.float64)
    else:
        frequencies = np.linspace(
            0.0, arguments.fmax_hz, arguments.frequency_count, dtype=np.float64
        )
    for _ in range(arguments.warmups):
        warmup_values = model.evaluate_s(frequencies)
    durations_ns: list[int] = []
    values = None
    for _ in range(arguments.repetitions):
        started = time.perf_counter_ns()
        values = model.evaluate_s(frequencies)
        durations_ns.append(time.perf_counter_ns() - started)
    assert values is not None
    payload = {
        "schema": "sipi.as-performance-rfm-kernel.v1",
        "status": "observed",
        "engine": "upstream-python",
        "timing_scope": "evaluate_s_only_after_single_parse",
        "timing_clock": "time.perf_counter_ns",
        "input": {
            "file_name": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "bytes": source.stat().st_size,
            "nports": model.nports,
            "stored_poles": int(model.poles.size),
            "effective_order": model.effective_order,
        },
        "workload": {
            "frequency_count": arguments.frequency_count,
            "fmax_hz": arguments.fmax_hz,
            "response_count": model.nports * model.nports,
            "warmup_count": arguments.warmups,
            "repetition_count": arguments.repetitions,
        },
        "durations_ns": durations_ns,
        "median_ns": median(durations_ns),
        "checksum": checksum(values),
        "warmup_completed": arguments.warmups == 0 or warmup_values is not None,
        "limitations": [
            "kernel-only timing; RFM parse, process launch, filesystem and JSON serialization are excluded",
            "same mathematical pole/residue evaluator is compared; this is not a MATLAB SPICE solver comparison",
            "no performance acceptance threshold is asserted by this observation",
        ],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
