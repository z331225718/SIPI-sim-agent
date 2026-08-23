"""Run the pinned PyBERT Python backend as an external BackendRunResult oracle.

This helper is intentionally a Python-only boundary.  It does not import the
candidate crate and it never calls ``sim-rust``/``sim-auto``/``sim-compare``.
The output is the result-adapter payload consumed by the Rust compare leaf:
metadata, diagnostics, metrics, and typed, shaped numeric arrays.  AMI/IBIS
and other host-owned model failures are allowed to fail in the caller; they are
not replaced by a Rust result.
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


def _dtype(value: np.ndarray) -> str | None:
    kind = value.dtype.kind
    if kind == "b":
        return "bool"
    if kind in "iu":
        return "int64"
    if kind == "f":
        return "float64"
    return None


def _typed_array(value: Any) -> dict[str, Any] | None:
    """Return the JSON typed-array form accepted by ``workflows.rs``.

    The adapter currently emits numeric NumPy arrays.  Preserve their logical
    dtype and all dimensions, including the two-dimensional eye matrices;
    silently dropping an array would turn an incomplete oracle into a false
    compare.  Object/complex/string values are outside the portable numeric
    contract and are reported as a producer error instead of being coerced.
    """
    try:
        array = np.asarray(value)
    except (TypeError, ValueError):
        return None
    dtype = _dtype(array)
    if dtype is None:
        return None
    if array.dtype.kind == "f" and not np.isfinite(array).all():
        raise ValueError("Python result adapter emitted a non-finite array")
    contiguous = np.ascontiguousarray(array)
    return {
        "shape": list(contiguous.shape),
        "data": contiguous.reshape(-1).tolist(),
        "dtype": dtype,
    }


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

    arrays: dict[str, dict[str, Any]] = {}
    dtypes: dict[str, str] = {}
    skipped: dict[str, str] = {}
    for name, value in sorted(adapter_arrays.items()):
        typed = _typed_array(value)
        if typed is None:
            skipped[str(name)] = "non_numeric_adapter_value"
            continue
        arrays[str(name)] = typed
        dtypes[str(name)] = typed["dtype"]

    # BackendRunResult has no mandatory metrics member.  Keep an explicit
    # object in the envelope so the consumer can distinguish an empty metric
    # map from a missing result-adapter field.
    metrics = metadata.get("metrics", {}) if isinstance(metadata, dict) else {}
    if not isinstance(metrics, dict):
        metrics = {}
    document = {
        "schema": "pybert.backend-run-result.v1",
        "backend": "python",
        "source_command": "PythonSimulationBackend",
        "run_id": config.stem,
        "metadata": _jsonable(metadata),
        "diagnostics": _jsonable(result.diagnostics),
        "metrics": _jsonable(metrics),
        "arrays": arrays,
        "array_dtypes": dtypes,
        "skipped_non_numeric_arrays": skipped,
        "result_adapter": {
            "schema": "pybert.engine.result_adapter.v1",
            "array_count": len(arrays),
            "two_dimensional_arrays": sorted(name for name, item in arrays.items() if len(item["shape"]) == 2),
            "dtype_counts": {
                dtype: sum(1 for value in dtypes.values() if value == dtype)
                for dtype in ("bool", "int64", "float64")
            },
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
