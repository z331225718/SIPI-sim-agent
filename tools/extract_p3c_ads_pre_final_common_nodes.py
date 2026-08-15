"""Read only exact common-node ADS spectrum values through the ADS dataset API."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import keysight.ads.dataset as ads_dataset


MEMBERS = tuple((row, column) for row in range(1, 5) for column in range(1, 5))


class ExtractError(RuntimeError):
    pass


def bits(value: float) -> bytes:
    return struct.pack(">d", value)


def digest(domain: bytes, values: list[complex]) -> str:
    payload = bytearray(domain)
    payload.extend(len(values).to_bytes(8, "big"))
    for value in values:
        payload.extend(bits(value.real)); payload.extend(bits(value.imag))
    return hashlib.sha256(payload).hexdigest()


def l2_and_max(
    values: list[complex],
    *,
    matrix_layout: bool,
) -> dict[str, object]:
    terms = [value.real * value.real + value.imag * value.imag for value in values]
    if not all(math.isfinite(term) for term in terms):
        raise ExtractError("common_node_delta_numeric_rejected")
    total = math.fsum(terms)
    if not math.isfinite(total):
        raise ExtractError("common_node_delta_numeric_rejected")
    maximum = max(range(len(values)), key=lambda index: abs(values[index]))
    summary: dict[str, object] = {
        "l2_squared_bits": bits(total).hex(),
        "max_abs_bits": bits(abs(values[maximum])).hex(),
    }
    if matrix_layout:
        member, common_index = divmod(maximum, 1024)
        row, column = MEMBERS[member]
        summary.update(
            {
                "max_row": row,
                "max_column": column,
                "max_common_index": common_index,
            }
        )
    else:
        summary["max_common_index"] = maximum
    return summary


def read_block(dataset: object, kind: str, row: int, column: int) -> tuple[tuple[float, ...], tuple[complex, ...]]:
    name = f"TRAN.CHANNEL.CMP1_{kind}({row};{column})"
    try:
        frame = dataset[name].to_dataframe()
        axis = tuple(float(value) for value in frame.index.to_numpy())
        values = tuple(complex(value) for value in frame["freqResp"].to_numpy())
    except Exception as error:
        raise ExtractError("common_node_dataset_api_shape_rejected") from error
    if len(axis) < 2 or len(axis) != len(values) or not all(math.isfinite(value) for value in axis):
        raise ExtractError("common_node_dataset_axis_rejected")
    if any(right <= left for left, right in zip(axis, axis[1:])) or not all(math.isfinite(value.real) and math.isfinite(value.imag) for value in values):
        raise ExtractError("common_node_dataset_value_rejected")
    return axis, values


def write_s0_hdiff_payload(path: Path, axis: tuple[float, ...], values: list[complex]) -> dict[str, object]:
    if len(axis) != 1024 or len(values) != 1024:
        raise ExtractError("s0_hdiff_payload_shape_rejected")
    payload = bytearray(b"sipi.p3c.ads-s0-hdiff-payload.v1\0")
    payload.extend(len(axis).to_bytes(8, "big"))
    for frequency, value in zip(axis, values, strict=True):
        payload.extend(bits(frequency))
        payload.extend(bits(value.real))
        payload.extend(bits(value.imag))
    path.write_bytes(payload)
    return {"byte_length": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def write_or_hdiff_payload(path: Path, axis: tuple[float, ...], values: list[complex]) -> dict[str, object]:
    if len(axis) < 2 or len(axis) != len(values):
        raise ExtractError("or_hdiff_payload_shape_rejected")
    payload = bytearray(b"sipi.p3c.ads-or-hdiff-payload.v1\0")
    payload.extend(len(axis).to_bytes(8, "big"))
    for frequency, value in zip(axis, values, strict=True):
        payload.extend(bits(frequency))
        payload.extend(bits(value.real))
        payload.extend(bits(value.imag))
    path.write_bytes(payload)
    return {"byte_length": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def extract_or(dataset_path: Path, payload_path: Path) -> dict[str, object]:
    with ads_dataset.open_dataset_for_reading(dataset_path) as dataset:
        blocks = {(row, column): read_block(dataset, "OR", row, column) for row, column in MEMBERS}
    axes = [blocks[(row, column)][0] for row, column in MEMBERS]
    if any(tuple(map(bits, axis)) != tuple(map(bits, axes[0])) for axis in axes[1:]):
        raise ExtractError("or_member_axis_mismatch")
    hdiff = [
        (blocks[(2, 1)][1][index] - blocks[(2, 3)][1][index] - blocks[(4, 1)][1][index] + blocks[(4, 3)][1][index]) / 4.0
        for index in range(len(axes[0]))
    ]
    return {
        "or_node_count": len(axes[0]),
        "axis_sha256": hashlib.sha256(b"sipi.p3c.ads-or.axis.v1\0" + b"".join(bits(value) for value in axes[0])).hexdigest(),
        "selected_hdiff_sha256": digest(b"sipi.p3c.ads-or.hdiff.v1\0", hdiff),
        "or_hdiff_payload": write_or_hdiff_payload(payload_path, axes[0], hdiff),
    }


def write_or_s0_hdiff_payload(
    path: Path,
    axis: tuple[float, ...],
    original: list[complex],
    s0: list[complex],
) -> dict[str, object]:
    if len(axis) != 1024 or len(original) != len(axis) or len(s0) != len(axis):
        raise ExtractError("or_s0_hdiff_payload_shape_rejected")
    payload = bytearray(b"sipi.p3c.ads-or-s0-hdiff-payload.v1\0")
    payload.extend(len(axis).to_bytes(8, "big"))
    for frequency, original_value, s0_value in zip(axis, original, s0, strict=True):
        payload.extend(bits(frequency))
        payload.extend(bits(original_value.real)); payload.extend(bits(original_value.imag))
        payload.extend(bits(s0_value.real)); payload.extend(bits(s0_value.imag))
    path.write_bytes(payload)
    return {"byte_length": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def extract_or_s0_common(dataset_path: Path, payload_path: Path) -> dict[str, object]:
    """Export only the exact OR[4k]/S0[k] selected Hdiff pairs."""
    with ads_dataset.open_dataset_for_reading(dataset_path) as dataset:
        blocks = {
            (kind, row, column): read_block(dataset, kind, row, column)
            for kind in ("OR", "S0") for row, column in MEMBERS
        }
    or_axes = [blocks[("OR", row, column)][0] for row, column in MEMBERS]
    s0_axes = [blocks[("S0", row, column)][0] for row, column in MEMBERS]
    if any(tuple(map(bits, axis)) != tuple(map(bits, or_axes[0])) for axis in or_axes[1:]) or any(tuple(map(bits, axis)) != tuple(map(bits, s0_axes[0])) for axis in s0_axes[1:]):
        raise ExtractError("or_s0_member_axis_mismatch")
    if len(or_axes[0]) != 4096 or len(s0_axes[0]) != 1024:
        raise ExtractError("or_s0_axis_count_rejected")
    if any(bits(or_axes[0][4 * index]) != bits(s0_axes[0][index]) for index in range(1024)):
        raise ExtractError("or_s0_mapping_not_exact_four_to_one")

    def reduce(kind: str, index: int) -> complex:
        return (
            blocks[(kind, 2, 1)][1][index]
            - blocks[(kind, 2, 3)][1][index]
            - blocks[(kind, 4, 1)][1][index]
            + blocks[(kind, 4, 3)][1][index]
        ) / 4.0

    original = [reduce("OR", 4 * index) for index in range(1024)]
    s0 = [reduce("S0", index) for index in range(1024)]
    transition = [after - before for before, after in zip(original, s0, strict=True)]
    return {
        "common_node_count": 1024,
        "mapping": "or_index_equals_4_times_s0_index",
        "axis_sha256": hashlib.sha256(b"sipi.p3c.ads-or-s0.axis.v1\0" + b"".join(bits(value) for value in s0_axes[0])).hexdigest(),
        "original_hdiff_sha256": digest(b"sipi.p3c.ads-or-s0.original.v1\0", original),
        "s0_hdiff_sha256": digest(b"sipi.p3c.ads-or-s0.s0.v1\0", s0),
        "documented_surface_transition": {
            "sha256": digest(b"sipi.p3c.ads-or-s0.transition.v1\0", transition),
            **l2_and_max(transition, matrix_layout=False),
        },
        "or_s0_hdiff_payload": write_or_s0_hdiff_payload(payload_path, s0_axes[0], original, s0),
    }


def extract(dataset_path: Path, s0_hdiff_payload: Path | None = None) -> dict[str, object]:
    with ads_dataset.open_dataset_for_reading(dataset_path) as dataset:
        blocks = {(kind, row, column): read_block(dataset, kind, row, column) for kind in ("S0", "FFT_IMP") for row, column in MEMBERS}
    s0_axes = [blocks[("S0", row, column)][0] for row, column in MEMBERS]
    fft_axes = [blocks[("FFT_IMP", row, column)][0] for row, column in MEMBERS]
    if any(tuple(map(bits, axis)) != tuple(map(bits, s0_axes[0])) for axis in s0_axes[1:]) or any(tuple(map(bits, axis)) != tuple(map(bits, fft_axes[0])) for axis in fft_axes[1:]):
        raise ExtractError("common_node_member_axis_mismatch")
    positions: dict[bytes, list[int]] = {}
    for index, frequency in enumerate(fft_axes[0]): positions.setdefault(bits(frequency), []).append(index)
    mapping: list[int] = []
    for index, frequency in enumerate(s0_axes[0]):
        matches = positions.get(bits(frequency), [])
        if len(matches) != 1:
            raise ExtractError("common_node_missing_or_duplicate")
        mapping.append(matches[0])
    if any(value != 4 * index for index, value in enumerate(mapping)):
        raise ExtractError("common_node_mapping_not_exact_four_to_one")
    s0_values: list[complex] = []; final_values: list[complex] = []; delta_values: list[complex] = []
    h_s0: list[complex] = []; h_final: list[complex] = []
    for row, column in MEMBERS:
        s0, final = blocks[("S0", row, column)][1], blocks[("FFT_IMP", row, column)][1]
        matched = [final[index] for index in mapping]
        s0_values.extend(s0); final_values.extend(matched); delta_values.extend(value - source for value, source in zip(matched, s0, strict=True))
    for index in range(len(mapping)):
        def h(kind: str) -> complex:
            return (blocks[(kind, 2, 1)][1][mapping[index] if kind == "FFT_IMP" else index] - blocks[(kind, 2, 3)][1][mapping[index] if kind == "FFT_IMP" else index] - blocks[(kind, 4, 1)][1][mapping[index] if kind == "FFT_IMP" else index] + blocks[(kind, 4, 3)][1][mapping[index] if kind == "FFT_IMP" else index]) / 4.0
        h_s0.append(h("S0")); h_final.append(h("FFT_IMP"))
    h_delta = [value - source for value, source in zip(h_final, h_s0, strict=True)]
    result = {
        "common_node_count": len(mapping), "mapping": "fft_imp_index_equals_4_times_s0_index",
        "full_matrix": {
            "s0_sha256": digest(b"sipi.p3c.ads-common-node.full.s0.v1\0", s0_values),
            "fft_imp_sha256": digest(b"sipi.p3c.ads-common-node.full.final.v1\0", final_values),
            "delta_sha256": digest(b"sipi.p3c.ads-common-node.full.delta.v1\0", delta_values),
            **l2_and_max(delta_values, matrix_layout=True),
        },
        "selected_hdiff": {
            "s0_sha256": digest(b"sipi.p3c.ads-common-node.hdiff.s0.v1\0", h_s0),
            "fft_imp_sha256": digest(b"sipi.p3c.ads-common-node.hdiff.final.v1\0", h_final),
            "delta_sha256": digest(b"sipi.p3c.ads-common-node.hdiff.delta.v1\0", h_delta),
            **l2_and_max(h_delta, matrix_layout=False),
        },
    }
    if s0_hdiff_payload is not None:
        result["s0_hdiff_payload"] = write_s0_hdiff_payload(s0_hdiff_payload, s0_axes[0], h_s0)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--dataset", type=Path, required=True); group = parser.add_mutually_exclusive_group(); group.add_argument("--s0-hdiff-payload", type=Path); group.add_argument("--or-hdiff-payload", type=Path); group.add_argument("--or-s0-hdiff-payload", type=Path); args = parser.parse_args()
    try:
        result = extract_or_s0_common(args.dataset, args.or_s0_hdiff_payload) if args.or_s0_hdiff_payload is not None else extract_or(args.dataset, args.or_hdiff_payload) if args.or_hdiff_payload is not None else extract(args.dataset, args.s0_hdiff_payload)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError, ExtractError) as error: print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True)); return 2
    return 0


if __name__ == "__main__": raise SystemExit(main())
