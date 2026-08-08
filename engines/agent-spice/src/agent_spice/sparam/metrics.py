from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from typing import Any

import numpy as np
import skrf as rf


@dataclass(frozen=True)
class FrequencyBand:
    name: str
    f_min_hz: float | None = None
    f_max_hz: float | None = None


DEFAULT_FREQUENCY_BANDS: tuple[FrequencyBand, ...] = (
    FrequencyBand("low_dc_to_1mhz", 0.0, 1.0e6),
    FrequencyBand("above_1mhz", 1.0e6, None),
    FrequencyBand("mid_1mhz_to_100mhz", 1.0e6, 100.0e6),
    FrequencyBand("high_100mhz_up", 100.0e6, None),
)


def compute_banded_network_metrics(
    frequencies_hz: Any,
    original_s: Any,
    fitted_s: Any,
    original_z: Any,
    fitted_z: Any,
    *,
    bands: list[FrequencyBand] | tuple[FrequencyBand, ...] = DEFAULT_FREQUENCY_BANDS,
) -> dict[str, Any]:
    frequencies = np.asarray(frequencies_hz, dtype=float)
    original_s_array = np.asarray(original_s, dtype=complex)
    fitted_s_array = np.asarray(fitted_s, dtype=complex)
    original_z_array = np.asarray(original_z, dtype=complex)
    fitted_z_array = np.asarray(fitted_z, dtype=complex)

    if original_s_array.shape != fitted_s_array.shape:
        raise ValueError("original_s and fitted_s must have the same shape")
    if original_z_array.shape != fitted_z_array.shape:
        raise ValueError("original_z and fitted_z must have the same shape")
    if original_s_array.shape[0] != len(frequencies):
        raise ValueError("S-parameter frequency dimension must match frequencies_hz")
    if original_z_array.shape[0] != len(frequencies):
        raise ValueError("Z-parameter frequency dimension must match frequencies_hz")

    results: dict[str, Any] = {"bands": {}}
    for band in [*bands, FrequencyBand("full", None, None)]:
        mask = _band_mask(frequencies, band)
        results["bands"][band.name] = _metrics_for_mask(
            frequencies,
            original_s_array,
            fitted_s_array,
            original_z_array,
            fitted_z_array,
            mask,
            band,
        )
    return results


def run_touchstone_banded_comparison(
    raw_path: Any,
    models: dict[str, Any],
    *,
    output: Any,
    csv: Any | None = None,
    html: Any | None = None,
) -> dict[str, Any]:
    raw_network = rf.Network(str(raw_path))
    payload: dict[str, Any] = {
        "raw": str(raw_path),
        "frequency_points": int(len(raw_network.f)),
        "ports": int(raw_network.nports),
        "bands": [_band_to_dict(band) for band in DEFAULT_FREQUENCY_BANDS] + [_band_to_dict(FrequencyBand("full"))],
        "models": {},
    }
    for label, model_path in models.items():
        fitted_network = _align_network_to_raw(rf.Network(str(model_path)), raw_network)
        metrics = compute_banded_network_metrics(
            raw_network.f,
            raw_network.s,
            fitted_network.s,
            raw_network.z,
            fitted_network.z,
        )
        payload["models"][label] = {
            "path": str(model_path),
            "bands": metrics["bands"],
        }

    output_path = _as_path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if csv is not None:
        _write_banded_metrics_csv(payload, _as_path(csv))
    if html is not None:
        _write_banded_metrics_html(payload, _as_path(html))
    return payload


def _band_mask(frequencies: np.ndarray, band: FrequencyBand) -> np.ndarray:
    mask = np.ones(frequencies.shape, dtype=bool)
    if band.f_min_hz is not None:
        mask &= frequencies >= band.f_min_hz
    if band.f_max_hz is not None:
        mask &= frequencies < band.f_max_hz
    return mask


def _band_to_dict(band: FrequencyBand) -> dict[str, Any]:
    return {"name": band.name, "f_min_hz": band.f_min_hz, "f_max_hz": band.f_max_hz}


def _as_path(path: Any):
    from pathlib import Path

    return path if isinstance(path, Path) else Path(path)


def _align_network_to_raw(network: Any, raw_network: Any) -> Any:
    if network.nports != raw_network.nports:
        raise ValueError(f"Port count mismatch: raw={raw_network.nports}, fitted={network.nports}")
    if len(network.f) == len(raw_network.f) and np.allclose(network.f, raw_network.f, rtol=1e-9, atol=1e-3):
        return network
    return network.interpolate(raw_network.f, unit="hz")


def _write_banded_metrics_csv(payload: dict[str, Any], path: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model",
                "band",
                "frequency_point_count",
                "frequency_range_hz",
                "s_mean_rms_error",
                "s_relative_rms_error",
                "diagonal_z_log_magnitude_rms_error",
            ],
        )
        writer.writeheader()
        for label, model in payload["models"].items():
            for band_name, metrics in model["bands"].items():
                writer.writerow(
                    {
                        "model": label,
                        "band": band_name,
                        "frequency_point_count": metrics["frequency_point_count"],
                        "frequency_range_hz": json.dumps(metrics["frequency_range_hz"]),
                        "s_mean_rms_error": metrics["s_mean_rms_error"],
                        "s_relative_rms_error": metrics["s_relative_rms_error"],
                        "diagonal_z_log_magnitude_rms_error": metrics["diagonal_z_log_magnitude_rms_error"],
                    }
                )


def _write_banded_metrics_html(payload: dict[str, Any], path: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, model in payload["models"].items():
        for band_name, metrics in model["bands"].items():
            rows.append(
                "<tr>"
                f"<td>{_escape(label)}</td>"
                f"<td>{_escape(band_name)}</td>"
                f"<td>{metrics['frequency_point_count']}</td>"
                f"<td>{_format_metric(metrics['s_mean_rms_error'])}</td>"
                f"<td>{_format_metric(metrics['s_relative_rms_error'])}</td>"
                f"<td>{_format_metric(metrics['diagonal_z_log_magnitude_rms_error'])}</td>"
                "</tr>"
            )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>S-parameter Banded Metrics</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; color: #17202a; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #d7dde3; padding: 8px 10px; text-align: right; }}
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
th {{ background: #eef2f7; }}
code {{ background: #f4f6f8; padding: 2px 4px; }}
</style>
</head>
<body>
<h1>S-parameter Banded Metrics</h1>
<p>Raw: <code>{_escape(payload['raw'])}</code>; ports={payload['ports']}; points={payload['frequency_points']}.</p>
<table>
<thead>
<tr><th>Model</th><th>Band</th><th>Points</th><th>S mean RMS</th><th>S relative RMS</th><th>Diag Z log RMS</th></tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def _format_metric(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.8g}"


def _escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _metrics_for_mask(
    frequencies: np.ndarray,
    original_s: np.ndarray,
    fitted_s: np.ndarray,
    original_z: np.ndarray,
    fitted_z: np.ndarray,
    mask: np.ndarray,
    band: FrequencyBand,
) -> dict[str, Any]:
    selected_freqs = frequencies[mask]
    payload: dict[str, Any] = {
        "name": band.name,
        "f_min_hz": band.f_min_hz,
        "f_max_hz": band.f_max_hz,
        "frequency_point_count": int(mask.sum()),
        "frequency_range_hz": None
        if len(selected_freqs) == 0
        else [float(selected_freqs[0]), float(selected_freqs[-1])],
        "s_mean_rms_error": None,
        "s_relative_rms_error": None,
        "diagonal_z_log_magnitude_rms_error": None,
    }
    if not mask.any():
        return payload

    original_s_band = original_s[mask]
    fitted_s_band = fitted_s[mask]
    s_error = fitted_s_band - original_s_band
    payload["s_mean_rms_error"] = float(np.sqrt(np.mean(np.abs(s_error) ** 2)))

    original_norm = float(np.linalg.norm(original_s_band.reshape(-1)))
    payload["s_relative_rms_error"] = (
        None if original_norm == 0.0 else float(np.linalg.norm(s_error.reshape(-1)) / original_norm)
    )
    payload["diagonal_z_log_magnitude_rms_error"] = _diagonal_z_log_magnitude_rms_error(
        original_z[mask],
        fitted_z[mask],
    )
    return payload


def _diagonal_z_log_magnitude_rms_error(original_z: np.ndarray, fitted_z: np.ndarray) -> float | None:
    if original_z.ndim != 3 or fitted_z.ndim != 3:
        raise ValueError("Z arrays must have shape (frequency, port, port)")
    port_count = min(original_z.shape[1], original_z.shape[2])
    diffs = []
    for port in range(port_count):
        original_mag = np.abs(original_z[:, port, port])
        fitted_mag = np.abs(fitted_z[:, port, port])
        mask = np.isfinite(original_mag) & np.isfinite(fitted_mag) & (original_mag > 0.0) & (fitted_mag > 0.0)
        if mask.any():
            diffs.append(np.log10(fitted_mag[mask]) - np.log10(original_mag[mask]))
    if not diffs:
        return None
    return float(np.sqrt(np.mean(np.concatenate(diffs) ** 2)))
