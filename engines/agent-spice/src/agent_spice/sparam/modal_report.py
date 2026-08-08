from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from agent_spice.sparam.modal import ModalZFitConfig, ModalZFitResult, pole_frequencies_hz


def _format_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6g}"


def _format_hz(value: float | None) -> str:
    if value is None:
        return "n/a"
    for scale, suffix in [(1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")]:
        if abs(value) >= scale:
            return f"{value / scale:.6g} {suffix}"
    return f"{value:.6g} Hz"


def _pole_rows(poles: np.ndarray | None) -> list[dict[str, float]]:
    if poles is None:
        return []
    rows: list[dict[str, float]] = []
    for pole in np.asarray(poles, dtype=complex).reshape(-1):
        frequency = abs(float(pole.imag)) / (2.0 * math.pi) if abs(pole.imag) > 0.0 else abs(float(pole.real)) / (2.0 * math.pi)
        rows.append({"real": float(pole.real), "imag": float(pole.imag), "frequency_hz": float(frequency)})
    return rows


def modal_report_to_dict(
    result: ModalZFitResult,
    touchstone_path: Path,
    config: ModalZFitConfig,
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_pole_frequencies = pole_frequencies_hz(result.selected_poles)
    payload = {
        "mode": "modal_z",
        "touchstone_path": str(touchstone_path),
        "config": asdict(config),
        "ports": result.ports,
        "frequency_points": result.frequency_points,
        "mode_count": result.mode_count,
        "basis_anchor_ports": list(result.basis_anchor_ports),
        "basis_frequency_sample_count": result.basis_frequency_sample_count,
        "scalar_fit_order": result.scalar_fit_order,
        "pole_damping": result.pole_damping,
        "shared_pole_trace_count": result.shared_pole_trace_count,
        "peak_pole_entry_count": result.peak_pole_entry_count,
        "decomposition": result.decomposition,
        "reduced_fit_method": result.reduced_fit_method,
        "s_rms_error": result.s_rms_error,
        "s_rms_error_scope": "original_frequency_points" if result.s_rms_error is not None else None,
        "z_log_magnitude_rms_error": result.z_log_magnitude_rms_error,
        "basis_projection_z_log_magnitude_rms_error": result.basis_projection_z_log_magnitude_rms_error,
        "diagonal_z_log_magnitude_rms_error": result.diagonal_z_log_magnitude_rms_error,
        "max_abs_z_error_ohm": result.max_abs_z_error_ohm,
        "worst_error_frequency_hz": result.worst_error_frequency_hz,
        "worst_error_port_pair": list(result.worst_error_port_pair),
        "selected_pole_count": 0 if result.selected_poles is None else int(len(result.selected_poles)),
        "selected_pole_frequencies_hz": list(selected_pole_frequencies),
        "selected_poles": _pole_rows(result.selected_poles),
        "residual_correction_pair_count": len(result.residual_correction_pairs),
        "residual_correction_pairs": [list(pair) for pair in result.residual_correction_pairs],
        "auto_order_trials": [
            {
                "scalar_fit_order": trial.scalar_fit_order,
                "z_log_magnitude_rms_error": trial.z_log_magnitude_rms_error,
                "basis_projection_z_log_magnitude_rms_error": trial.basis_projection_z_log_magnitude_rms_error,
                "diagonal_z_log_magnitude_rms_error": trial.diagonal_z_log_magnitude_rms_error,
                "worst_error_frequency_hz": trial.worst_error_frequency_hz,
                "worst_error_port_pair": list(trial.worst_error_port_pair),
                "selected_pole_count": trial.selected_pole_count,
                "selected_pole_frequencies_hz": list(trial.selected_pole_frequencies_hz),
            }
            for trial in result.auto_order_trials
        ],
        "auto_basis_trials": [
            {
                "mode_count": trial.mode_count,
                "basis_anchor_ports": list(trial.basis_anchor_ports),
                "basis_frequency_sample_count": trial.basis_frequency_sample_count,
                "scalar_fit_order": trial.scalar_fit_order,
                "pole_damping": trial.pole_damping,
                "shared_pole_trace_count": trial.shared_pole_trace_count,
                "peak_pole_entry_count": trial.peak_pole_entry_count,
                "selection_score": trial.selection_score,
                "z_log_magnitude_rms_error": trial.z_log_magnitude_rms_error,
                "basis_projection_z_log_magnitude_rms_error": trial.basis_projection_z_log_magnitude_rms_error,
                "diagonal_z_log_magnitude_rms_error": trial.diagonal_z_log_magnitude_rms_error,
                "worst_error_frequency_hz": trial.worst_error_frequency_hz,
                "worst_error_port_pair": list(trial.worst_error_port_pair),
                "selected_pole_count": trial.selected_pole_count,
                "residual_correction_pair_count": trial.residual_correction_pair_count,
            }
            for trial in result.auto_basis_trials
        ],
        "report_only": True,
        "notes": [
            "Prototype reduced-basis Z-domain rational fit.",
            "This report does not prove passivity and does not export a SPICE subcircuit.",
        ],
    }
    if quality is not None:
        payload["quality"] = quality
    return payload


def write_modal_z_json_report(
    result: ModalZFitResult,
    path: Path,
    touchstone_path: Path,
    config: ModalZFitConfig,
    quality: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = modal_report_to_dict(result, touchstone_path, config, quality=quality)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _svg_polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _render_trace_chart(trace: dict[str, Any]) -> str:
    width = 760
    height = 320
    left = 64
    right = 24
    top = 24
    bottom = 48
    plot_width = width - left - right
    plot_height = height - top - bottom
    freqs = [float(freq) for freq in trace["frequencies_hz"]]
    values = [float(value) for value in trace["original_values"] + trace["fitted_values"]]
    positive_values = [value for value in values if value > 0]
    y_floor = min(positive_values) if positive_values else 1e-300
    log_values = [max(value, y_floor) for value in values]
    y_min_log = math.log10(min(log_values))
    y_max_log = math.log10(max(log_values))
    if math.isclose(y_min_log, y_max_log):
        y_min_log -= 1.0
        y_max_log += 1.0
    padding = max((y_max_log - y_min_log) * 0.08, 0.05)
    y_min_log -= padding
    y_max_log += padding
    positive_freqs = [freq for freq in freqs if freq > 0]
    if not positive_freqs:
        return ""
    x_floor = min(positive_freqs)
    log_freqs = [max(freq, x_floor) for freq in freqs]
    x_min = math.log10(min(log_freqs))
    x_max = math.log10(max(log_freqs))
    if math.isclose(x_min, x_max):
        x_max += 1.0

    def map_points(series: list[float]) -> list[tuple[float, float]]:
        points = []
        for freq, value in zip(log_freqs, series):
            x = left + ((math.log10(freq) - x_min) / (x_max - x_min)) * plot_width
            y = top + ((y_max_log - math.log10(max(float(value), y_floor))) / (y_max_log - y_min_log)) * plot_height
            points.append((x, y))
        return points

    original_points = _svg_polyline(map_points(trace["original_values"]))
    fitted_points = _svg_polyline(map_points(trace["fitted_values"]))
    x_start = "DC" if min(freqs) <= 0 else _format_hz(min(freqs))
    x_end = _format_hz(max(freqs))
    y_top = _format_float(10**y_max_log)
    y_bottom = _format_float(10**y_min_log)
    label = escape(trace["label"])
    return f"""
<section class="chart">
  <h3>{label} Original vs Fitted |Z|</h3>
  <svg viewBox="0 0 {width} {height}" role="img" aria-label="{label} original vs fitted Z magnitude on log axes">
    <rect x="0" y="0" width="{width}" height="{height}" class="plot-bg" />
    <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" class="axis" />
    <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" class="axis" />
    <text x="12" y="{top + 4}" class="tick">{y_top} Ohm</text>
    <text x="12" y="{height - bottom}" class="tick">{y_bottom} Ohm</text>
    <text x="12" y="{top + 20}" class="tick">|Z| (Ohm), log</text>
    <text x="{left}" y="{height - 18}" class="tick">{escape(x_start)}</text>
    <text x="{width - right - 92}" y="{height - 18}" class="tick">{escape(x_end)}</text>
    <text x="{width - right - 120}" y="{height - 34}" class="tick">Frequency, log</text>
    <polyline points="{original_points}" class="line original" />
    <polyline points="{fitted_points}" class="line fitted" />
  </svg>
  <div class="legend"><span class="swatch original"></span>Original Touchstone <span class="swatch fitted"></span>Fitted modal-Z model</div>
</section>
"""


def _pair_log_rms(original: np.ndarray, fitted: np.ndarray) -> np.ndarray:
    original_mag = np.maximum(np.abs(original), 1e-300)
    fitted_mag = np.maximum(np.abs(fitted), 1e-300)
    delta = np.log10(fitted_mag / original_mag)
    return np.sqrt(np.nanmean(np.square(delta), axis=0))


def _modal_comparison_traces(result: ModalZFitResult, max_traces: int = 10) -> list[dict[str, Any]]:
    pair_errors = _pair_log_rms(result.original_z, result.fitted_z)
    ranked_pairs: list[tuple[float, int, int]] = []
    for row in range(result.ports):
        for column in range(result.ports):
            ranked_pairs.append((float(pair_errors[row, column]), row, column))
    worst_row, worst_column = result.worst_error_port_pair[0] - 1, result.worst_error_port_pair[1] - 1
    selected: list[tuple[int, int]] = [(worst_row, worst_column)]
    for _, row, column in sorted(ranked_pairs, reverse=True):
        pair = (row, column)
        if pair not in selected:
            selected.append(pair)
        if len(selected) >= max_traces:
            break

    freqs = [float(value) for value in result.frequencies_hz]
    traces: list[dict[str, Any]] = []
    for row, column in selected:
        traces.append(
            {
                "label": f"Z{row + 1}{column + 1}",
                "frequencies_hz": freqs,
                "original_values": [max(abs(value), 1e-300) for value in result.original_z[:, row, column]],
                "fitted_values": [max(abs(value), 1e-300) for value in result.fitted_z[:, row, column]],
            }
        )
    return traces


def write_modal_z_html_report(
    result: ModalZFitResult,
    path: Path,
    touchstone_path: Path,
    config: ModalZFitConfig,
    quality: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trace_sections = "\n".join(_render_trace_chart(trace) for trace in _modal_comparison_traces(result))
    if not trace_sections:
        trace_sections = "<p class=\"note\">Comparison plot unavailable for this input.</p>"
    rows = {
        "Auto preset": config.auto_preset,
        "Touchstone": str(touchstone_path),
        "Ports": result.ports,
        "Frequency points": result.frequency_points,
        "Mode count": result.mode_count,
        "Basis anchor ports": ", ".join(str(port) for port in result.basis_anchor_ports),
        "Scalar fit order": result.scalar_fit_order,
        "Decomposition": result.decomposition,
        "Reduced fit method": result.reduced_fit_method,
        "S RMS error": _format_float(result.s_rms_error),
        "Z log-magnitude RMS": f"{_format_float(result.z_log_magnitude_rms_error)} decades",
        "Basis projection Z log-magnitude RMS": f"{_format_float(result.basis_projection_z_log_magnitude_rms_error)} decades",
        "Diagonal Z log-magnitude RMS": f"{_format_float(result.diagonal_z_log_magnitude_rms_error)} decades",
        "Max absolute Z error": f"{_format_float(result.max_abs_z_error_ohm)} Ohm",
        "Worst frequency": _format_hz(result.worst_error_frequency_hz),
        "Worst port pair": f"Z{result.worst_error_port_pair[0]}{result.worst_error_port_pair[1]}",
        "Selected pole count": 0 if result.selected_poles is None else int(len(result.selected_poles)),
        "Selected pole frequencies": ", ".join(_format_hz(value) for value in pole_frequencies_hz(result.selected_poles)[:24]),
        "Frequency sample count": config.frequency_sample_count,
        "Frequency sample head count": config.frequency_sample_head_count,
        "Basis frequency sample count": config.basis_frequency_sample_count,
        "Basis frequency sampling": config.basis_frequency_sampling,
        "Pole damping": config.pole_damping,
        "Peak pole frequency head count": config.peak_pole_frequency_head_count,
        "Peak pole entry count": config.peak_pole_entry_count,
        "Peak pole full pair count": config.peak_pole_full_pair_count,
        "Peak pole complete order": config.peak_pole_complete_order,
        "Vector initial real poles": config.vector_n_poles_init_real,
        "Vector initial complex poles": config.vector_n_poles_init_cmplx,
        "Vector poles added per round": config.vector_n_poles_add,
        "Vector start iterations": config.vector_iters_start,
        "Vector intermediate iterations": config.vector_iters_inter,
        "Vector final iterations": config.vector_iters_final,
        "Vector target error": config.vector_target_error,
        "Shared pole trace count": config.shared_pole_trace_count,
        "Relative weight power": config.relative_weight_power,
        "Relative weight mode": config.relative_weight_mode,
        "Relative weight iterations": config.relative_weight_iterations,
        "Relative weight update": config.relative_weight_update,
        "Target error weight power": config.target_error_weight_power,
        "Target error weight max": config.target_error_weight_max,
        "Target error pair count": config.target_error_pair_count,
        "Residual pair count": config.residual_pair_count,
        "Residual fit order": config.residual_fit_order,
        "Residual pole damping": config.residual_pole_damping,
        "Residual weight power": config.residual_weight_power,
        "Residual gain": config.residual_gain,
        "Residual include diagonal": config.residual_include_diagonal,
        "Residual mirror pairs": config.residual_mirror_pairs,
        "Residual corrected pairs": ", ".join(f"Z{row}{column}" for row, column in result.residual_correction_pairs),
        "Auto-order candidates": config.auto_order_candidates,
        "Auto-basis mode counts": config.auto_basis_mode_counts,
        "Auto-basis sample counts": config.auto_basis_sample_counts,
        "Auto-basis anchor port counts": config.auto_basis_anchor_port_counts,
        "Auto-basis anchor candidate count": config.auto_basis_anchor_candidate_count,
        "Auto-basis anchor combo count": config.auto_basis_anchor_combo_count,
        "Auto pole dampings": config.auto_pole_dampings,
        "Auto shared pole trace counts": config.auto_shared_pole_trace_counts,
        "Auto peak pole entry counts": config.auto_peak_pole_entry_counts,
        "Auto basis diagonal weight": config.auto_basis_diagonal_weight,
        "Auto-order max Z log RMS": config.auto_order_max_z_log_magnitude_rms_error,
        "Auto-order max diagonal Z log RMS": config.auto_order_max_diagonal_z_log_magnitude_rms_error,
    }
    table_rows = "\n".join(
        f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>" for key, value in rows.items()
    )
    quality_section = ""
    if quality is not None:
        quality_rows = "\n".join(
            "<tr>"
            f"<td>{escape(str(check['metric']))}</td>"
            f"<td>{_format_float(check['value'])}</td>"
            f"<td>{_format_float(check['max'])}</td>"
            f"<td>{'PASS' if check['passed'] else 'FAIL'}</td>"
            "</tr>"
            for check in quality.get("checks", [])
        )
        if not quality_rows:
            quality_rows = '<tr><td colspan="4">No modal-Z quality thresholds configured.</td></tr>'
        reason_text = ", ".join(str(reason) for reason in quality.get("blocking_reasons", [])) or "none"
        quality_section = f"""
  <h2>Quality Gate</h2>
  <p>Status: <strong>{escape(str(quality.get("status", "unknown")))}</strong>; blocking reasons: {escape(reason_text)}</p>
  <table>
    <tr><th>Metric</th><th>Value</th><th>Max</th><th>Status</th></tr>
    {quality_rows}
  </table>
"""
    auto_order_section = ""
    if result.auto_order_trials:
        auto_rows = "\n".join(
            "<tr>"
            f"<td>{trial.scalar_fit_order}</td>"
            f"<td>{_format_float(trial.z_log_magnitude_rms_error)}</td>"
            f"<td>{_format_float(trial.diagonal_z_log_magnitude_rms_error)}</td>"
            f"<td>{_format_float(trial.basis_projection_z_log_magnitude_rms_error)}</td>"
            f"<td>{escape(_format_hz(trial.worst_error_frequency_hz))}</td>"
            f"<td>Z{trial.worst_error_port_pair[0]}{trial.worst_error_port_pair[1]}</td>"
            f"<td>{trial.selected_pole_count}</td>"
            "</tr>"
            for trial in result.auto_order_trials
        )
        auto_order_section = f"""
  <h2>Auto-Order Trials</h2>
  <table>
    <tr><th>Order</th><th>Z log RMS</th><th>Diagonal Z log RMS</th><th>Projection RMS</th><th>Worst frequency</th><th>Worst pair</th><th>Poles</th></tr>
    {auto_rows}
  </table>
"""
    auto_basis_section = ""
    if result.auto_basis_trials:
        basis_rows = "\n".join(
            "<tr>"
            f"<td>{trial.mode_count}</td>"
            f"<td>{escape(','.join(str(port) for port in trial.basis_anchor_ports))}</td>"
            f"<td>{trial.basis_frequency_sample_count}</td>"
            f"<td>{trial.scalar_fit_order}</td>"
            f"<td>{_format_float(trial.pole_damping)}</td>"
            f"<td>{trial.shared_pole_trace_count}</td>"
            f"<td>{trial.peak_pole_entry_count}</td>"
            f"<td>{_format_float(trial.selection_score)}</td>"
            f"<td>{_format_float(trial.z_log_magnitude_rms_error)}</td>"
            f"<td>{_format_float(trial.diagonal_z_log_magnitude_rms_error)}</td>"
            f"<td>{_format_float(trial.basis_projection_z_log_magnitude_rms_error)}</td>"
            f"<td>{escape(_format_hz(trial.worst_error_frequency_hz))}</td>"
            f"<td>Z{trial.worst_error_port_pair[0]}{trial.worst_error_port_pair[1]}</td>"
            f"<td>{trial.selected_pole_count}</td>"
            f"<td>{trial.residual_correction_pair_count}</td>"
            "</tr>"
            for trial in result.auto_basis_trials
        )
        auto_basis_section = f"""
  <h2>Auto-Basis Trials</h2>
  <table>
    <tr><th>Modes</th><th>Anchor ports</th><th>Basis samples</th><th>Order</th><th>Damping</th><th>Trace count</th><th>Peak entries</th><th>Score</th><th>Z log RMS</th><th>Diagonal Z log RMS</th><th>Projection RMS</th><th>Worst frequency</th><th>Worst pair</th><th>Poles</th><th>Residual pairs</th></tr>
    {basis_rows}
  </table>
"""
    pole_section = ""
    if result.selected_poles is not None:
        pole_table_rows = "\n".join(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{_format_float(row['real'])}</td>"
            f"<td>{_format_float(row['imag'])}</td>"
            f"<td>{escape(_format_hz(row['frequency_hz']))}</td>"
            "</tr>"
            for index, row in enumerate(_pole_rows(result.selected_poles), start=1)
        )
        pole_section = f"""
  <h2>Selected Poles</h2>
  <table>
    <tr><th>#</th><th>Real</th><th>Imag</th><th>Frequency</th></tr>
    {pole_table_rows}
  </table>
"""
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Modal Z-Fit Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #17202a; background: #f7f9fb; }}
    h1, h2, h3 {{ color: #102a43; }}
    table {{ width: 100%; border-collapse: collapse; background: white; margin: 12px 0 24px; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #d9e2ec; }}
    th {{ background: #eef2f7; }}
    .note {{ color: #52606d; }}
    .chart {{ background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 16px; margin: 14px 0; }}
    svg {{ width: 100%; max-width: 900px; height: auto; }}
    .plot-bg {{ fill: #fbfdff; }}
    .axis {{ stroke: #829ab1; stroke-width: 1.2; }}
    .tick {{ fill: #52606d; font-size: 12px; }}
    .line {{ fill: none; stroke-width: 2.4; }}
    .original {{ stroke: #1f77b4; }}
    .fitted {{ stroke: #d62728; stroke-dasharray: 6 4; }}
    .legend {{ color: #52606d; font-size: 13px; }}
    .swatch {{ display: inline-block; width: 22px; height: 3px; margin: 0 6px 3px 14px; vertical-align: middle; }}
    .swatch.original {{ background: #1f77b4; }}
    .swatch.fitted {{ background: repeating-linear-gradient(90deg, #d62728 0 8px, transparent 8px 13px); }}
  </style>
</head>
<body>
  <h1>Modal Z-Fit Report</h1>
  <p class="note">Report-only reduced-basis Z-domain rational fitting prototype. This artifact does not prove passivity or export SPICE.</p>
  <h2>Summary</h2>
  <table>
    <tr><th>Item</th><th>Value</th></tr>
    {table_rows}
  </table>
  {quality_section}
  {auto_order_section}
  {auto_basis_section}
  {pole_section}
  <h2>Original vs Fitted Z Magnitude</h2>
  {trace_sections}
</body>
</html>
""",
        encoding="utf-8",
    )
