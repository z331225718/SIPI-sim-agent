"""Run the pinned PyBERT Python backend and emit a bounded numeric oracle.

This helper deliberately does not invoke ``sim-rust`` or any native backend.
It executes ``PythonSimulationBackend`` and records only arrays produced by the
legacy result adapter (plus named raw stage outputs that the adapter consumes).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items() if not isinstance(item, (Path, bytes))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _array(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if array.dtype.kind != "f" or not np.isfinite(array).all():
        return None
    return np.ascontiguousarray(array)


def run(config: Path, output: Path) -> dict[str, Any]:
    from pybert.engine.python_backend import PythonSimulationBackend
    from pybert.engine.result_adapter import to_web_result
    from pybert.pybert import PyBERT
    from pybert_web.simulation import _extract_results

    pybert = PyBERT(run_simulation=False, gui=False)
    pybert.load_configuration(config)
    backend = PythonSimulationBackend(
        validate_request=lambda _request: None,
        build_pybert=lambda _request: pybert,
        extract_results=_extract_results,
        update_plots=False,
    )
    result = backend.run(pybert, aborted=lambda: False, on_stage=lambda _stage, _data: None)
    metadata, adapter_arrays = to_web_result(result)

    # These are source fields that are observable in the completed PyBERT run.
    # The candidate-side names are intentionally separate from the Python keys.
    source_fields: dict[str, tuple[str, Any]] = {
        "channel_impulse_v_per_v": ("parity_channel_impulse_v_per_v", adapter_arrays.get("parity_channel_impulse_v_per_v")),
        "channel_output_v": ("legacy_raw_channel_output_v", getattr(pybert, "chnl_out", None)),
        "rx_input_v": ("legacy_rx_input_v", getattr(pybert, "rx_in", None)),
        "ctle_output_v": ("parity_ctle_output_v", adapter_arrays.get("parity_ctle_output_v")),
        "rx_output_v": ("parity_rx_output_v", adapter_arrays.get("parity_rx_output_v")),
        "dfe_output_v": ("parity_dfe_output_v", adapter_arrays.get("parity_dfe_output_v")),
        "dfe_decisions": ("parity_dfe_decisions", adapter_arrays.get("parity_dfe_decisions")),
        "dfe_clock_times_s": ("parity_dfe_clock_times_s", adapter_arrays.get("parity_dfe_clock_times_s")),
        "random_noise_v": ("random_noise_v", adapter_arrays.get("random_noise_v")),
        "additive_noise_v": ("additive_noise_v", adapter_arrays.get("additive_noise_v")),
    }
    dfe_clocks = getattr(pybert, "clocks", None)
    dfe_locked = getattr(pybert, "lockeds", None)
    dfe_ui = getattr(pybert, "ui_ests", None)
    source_fields.update(
        {
            "dfe_clocks": ("legacy_clocks", dfe_clocks),
            "dfe_locked": ("legacy_lockeds", dfe_locked),
            "dfe_ui_estimates_s": ("legacy_ui_ests_ps", np.asarray(dfe_ui, dtype=np.float64) * 1.0e-12 if dfe_ui is not None else None),
        }
    )
    dbg = getattr(pybert, "dbg_dict_viterbi", None)
    if isinstance(dbg, dict):
        source_fields.update(
            {
                "viterbi_state_path": ("legacy_viterbi_path", dbg.get("path")),
                "viterbi_symbols_v": ("legacy_viterbi_symbols", dbg.get("symbols_viterbi")),
            }
        )

    arrays: dict[str, np.ndarray] = {}
    bindings: dict[str, dict[str, Any]] = {}
    for candidate_name, (source_name, value) in source_fields.items():
        array = _array(value)
        if array is None or array.size == 0:
            continue
        arrays[candidate_name] = array
        bindings[candidate_name] = {
            "source_field": source_name,
            "shape": list(array.shape),
            "dtype": "float64",
        }
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output / "arrays.npz", **arrays)
    selected_metadata = {
        key: metadata.get(key)
        for key in ("ber", "fom", "eye_width_ps", "eye_height_mv", "jitter", "effective_randomness", "eye_shape")
        if key in metadata
    }
    document = {
        "schema": "pybert.python-oracle-result.v1",
        "backend": "python",
        "source_command": "PythonSimulationBackend",
        "source_fields": bindings,
        "metadata": _jsonable(selected_metadata),
        "diagnostics": _jsonable(result.diagnostics),
        "arrays_file": "arrays.npz",
    }
    (output / "meta.json").write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.output_dir)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
