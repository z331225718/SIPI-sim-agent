"""P4B-07b external-only ctypes ABI observer (raw output parity).

Loads a hash-pinned authorized AMI DLL via ctypes with the same fixed
probe inputs as the clean-room Rust host (identity-like matrix, 1 ps
sample interval, 31.25 ps bit time, alternating +/-1 waveform, -1.0 clock
sentinel) and reports hash-only raw outputs (sha256 over f64 little-
endian bytes). This observer is external-custody parity tooling, not
product code; it asserts nothing about AMI semantics or compatibility.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import struct
from pathlib import Path


def sha256_f64(values) -> str:
    payload = b"".join(struct.pack("<d", float(value)) for value in values)
    return hashlib.sha256(payload).hexdigest()


def fixed_matrix(rows: int, aggressors: int) -> list[float]:
    columns = aggressors + 1
    return [1.0 if index % columns == 0 else 0.0 for index in range(rows * columns)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--ami", type=Path, required=True)
    parser.add_argument("--mode", choices=["init", "single", "multi"], required=True)
    parser.add_argument("--wave-length", type=int)
    parser.add_argument("--clock-capacity", type=int)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--aggressors", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    library = ctypes.CDLL(str(args.dll))
    init = library.AMI_Init
    init.restype = ctypes.c_long
    init.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_long,
        ctypes.c_long,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    close = library.AMI_Close
    close.restype = ctypes.c_long
    close.argtypes = [ctypes.c_void_p]
    getwave = None
    try:
        getwave = library.AMI_GetWave
        getwave.restype = ctypes.c_long
        getwave.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_long,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
        ]
    except AttributeError:
        pass

    matrix = fixed_matrix(args.rows, args.aggressors)
    matrix_arr = (ctypes.c_double * len(matrix))(*matrix)
    ami_bytes = args.ami.read_bytes()
    params = ctypes.create_string_buffer(ami_bytes)
    params_out = ctypes.c_void_p()
    handle = ctypes.c_void_p()
    message = ctypes.c_void_p()
    init_status = init(
        matrix_arr,
        args.rows,
        args.aggressors,
        1.0e-12,
        31.25e-12,
        params,
        ctypes.byref(params_out),
        ctypes.byref(handle),
        ctypes.byref(message),
    )
    if init_status != 1:
        close(handle)
        Path(args.report).write_text(
            json.dumps({"init_status": init_status, "error": "init_failed"}), encoding="utf-8")
        return 0
    if args.mode == "init":
        close_status = close(handle)
        Path(args.report).write_text(
            json.dumps({"init_status": init_status, "close_status": close_status, "mode": "init_only"}), encoding="utf-8")
        return 0
    if getwave is None:
        close(handle)
        Path(args.report).write_text(
            json.dumps({"init_status": init_status, "error": "getwave_unavailable"}), encoding="utf-8")
        return 0
    probes = []
    count = 3 if args.mode == "multi" else 1
    for _ in range(count):
        waveform = [1.0 if index % 2 == 0 else -1.0 for index in range(args.wave_length)]
        wave_arr = (ctypes.c_double * len(waveform))(*waveform)
        clocks = (ctypes.c_double * args.clock_capacity)(*([-1.0] * args.clock_capacity))
        wave_params_out = ctypes.c_void_p()
        status = getwave(wave_arr, len(waveform), clocks, ctypes.byref(wave_params_out), handle)
        if status != 1:
            probes.append({"status": status, "error": "getwave_failed"})
            continue
        wave_values = list(wave_arr[: len(waveform)])
        clock_values = list(clocks[: args.clock_capacity])
        count_clocks = clock_values.index(-1.0) if -1.0 in clock_values else len(clock_values)
        probes.append({
            "status": status,
            "output_waveform_hash": sha256_f64(wave_values),
            "output_waveform_len": len(wave_values),
            "clocks_hash": sha256_f64(clock_values[:count_clocks]),
            "clocks_len": count_clocks,
        })
    close_status = close(handle)
    Path(args.report).write_text(
        json.dumps({"init_status": init_status, "probe_count": count, "probes": probes, "close_status": close_status}),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
