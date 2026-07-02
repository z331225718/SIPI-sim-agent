from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
import inspect
import json
import logging
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
import skrf as rf
from skrf.vectorFitting import VectorFitting

from agent_spice.sparam.quality import SCHEMA_VERSION, QualityReport, build_quality_report


@dataclass(frozen=True)
class SParamFitConfig:
    mode: str = "auto"
    n_poles_real: int = 2
    n_poles_cmplx: int = 2
    init_pole_spacing: str = "lin"
    fit_constant: bool = True
    fit_proportional: bool = False
    enforce_dc: bool = True
    n_poles_init_real: int = 3
    n_poles_init_cmplx: int = 3
    n_poles_add: int = 3
    iters_start: int = 3
    iters_inter: int = 3
    iters_final: int = 5
    model_order_max: int = 100
    target_error: float = 0.01
    alpha: float = 0.03
    gamma: float = 0.03
    nu_samples: float = 1.0
    max_iterations: int | None = None
    parameter_type: str = "s"
    enforce_passivity: bool = True
    passivity_samples: int = 200
    passivity_f_max: float | None = None
    preserve_dc: bool = True
    subckt_name: str = "s_equivalent"
    create_reference_pins: bool = False
    fit_frequency_stride: int = 1
    fit_max_frequency_points: int | None = None
    fit_f_min: float | None = None
    fit_f_max: float | None = None
    quality_profile: str = "explore"
    max_comparison_rms_error: float = 0.05
    max_passivity_epsilon: float = 1e-6
    require_dc: bool = False


@dataclass(frozen=True)
class SParamFitResult:
    touchstone_path: Path
    spice_path: Path
    report_path: Path | None
    html_report_path: Path | None
    log_path: Path | None
    ports: int
    frequency_points: int
    frequency_range_hz: list[float] | None
    fit_frequency_points: int
    fit_frequency_range_hz: list[float] | None
    fit_frequency_selection: dict[str, Any]
    reference_impedance: list[float]
    config: SParamFitConfig
    rms_error: float | None
    comparison_rms_error: float | None
    passive_before_enforce: bool | None
    passive_after_enforce: bool | None
    passivity_violations_before: list[list[float]] | None
    passivity_violations_after: list[list[float]] | None
    quality_report: QualityReport

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Path):
            return self.spice_path == other
        if isinstance(other, SParamFitResult):
            return self.to_dict() == other.to_dict()
        return NotImplemented

    def to_dict(self) -> dict[str, Any]:
        quality = _quality_summary(self)
        return {
            "schema_version": SCHEMA_VERSION,
            "touchstone_path": str(self.touchstone_path),
            "spice_path": str(self.spice_path),
            "report_path": None if self.report_path is None else str(self.report_path),
            "html_report_path": None if self.html_report_path is None else str(self.html_report_path),
            "log_path": None if self.log_path is None else str(self.log_path),
            "ports": self.ports,
            "frequency_points": self.frequency_points,
            "frequency_range_hz": self.frequency_range_hz,
            "fit_frequency_points": self.fit_frequency_points,
            "fit_frequency_range_hz": self.fit_frequency_range_hz,
            "fit_frequency_selection": self.fit_frequency_selection,
            "reference_impedance": self.reference_impedance,
            "config": asdict(self.config),
            "quality": quality,
            "diagnostics": quality["diagnostics"],
            "rms_error": self.rms_error,
            "rms_error_scope": "fit_frequency_points",
            "comparison_rms_error": self.comparison_rms_error,
            "comparison_rms_error_scope": "original_frequency_points",
            "passive_before_enforce": self.passive_before_enforce,
            "passive_after_enforce": self.passive_after_enforce,
            "passivity_violations_before": self.passivity_violations_before,
            "passivity_violations_after": self.passivity_violations_after,
        }


def _reference_impedance(network: Any) -> list[float]:
    if len(network.z0) == 0:
        return []
    return [float(value.real) for value in network.z0[0]]


def _frequency_range(network: Any) -> list[float] | None:
    if len(network.f) == 0:
        return None
    return [float(network.f[0]), float(network.f[-1])]


def _frequency_selection_summary(config: SParamFitConfig) -> dict[str, Any]:
    return {
        "stride": config.fit_frequency_stride,
        "max_points": config.fit_max_frequency_points,
        "f_min": config.fit_f_min,
        "f_max": config.fit_f_max,
    }


def _selected_z0(network: Any, indices: np.ndarray) -> Any:
    z0 = np.asarray(network.z0)
    if z0.ndim < 2:
        return network.z0
    return z0[indices, :]


def _select_fit_network(network: Any, config: SParamFitConfig) -> Any:
    if config.fit_frequency_stride < 1:
        raise ValueError("fit_frequency_stride must be >= 1")
    if config.fit_max_frequency_points is not None and config.fit_max_frequency_points < 1:
        raise ValueError("fit_max_frequency_points must be >= 1")

    indices = np.arange(len(network.f))
    if config.fit_f_min is not None:
        indices = indices[network.f[indices] >= config.fit_f_min]
    if config.fit_f_max is not None:
        indices = indices[network.f[indices] <= config.fit_f_max]
    if len(indices) == 0:
        raise ValueError("Frequency selection produced no samples for vector fitting")

    if config.fit_frequency_stride > 1:
        indices = indices[:: config.fit_frequency_stride]

    if config.fit_max_frequency_points is not None and len(indices) > config.fit_max_frequency_points:
        sampled_positions = np.linspace(0, len(indices) - 1, config.fit_max_frequency_points, dtype=int)
        indices = indices[np.unique(sampled_positions)]
    if len(indices) < 2:
        raise ValueError("Frequency selection must contain at least 2 samples for vector fitting")

    if len(indices) == len(network.f) and np.array_equal(indices, np.arange(len(network.f))):
        return network

    return rf.Network(
        frequency=network.frequency[indices],
        s=network.s[indices, :, :],
        z0=_selected_z0(network, indices),
        name=f"{getattr(network, 'name', 'network')}_fit_subset",
    )


def _safe_bool(method, **kwargs) -> bool | None:
    try:
        return bool(_call_with_supported_kwargs(method, **kwargs))
    except Exception:
        return None


def _call_with_supported_kwargs(method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(*args, **kwargs)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return method(*args, **kwargs)
    supported_kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return method(*args, **supported_kwargs)


class _ProgressLog:
    def __init__(self, path: Path | None):
        self.path = path
        self.handler: logging.Handler | None = None
        self.loggers: list[logging.Logger] = []
        self.old_levels: dict[logging.Logger, int] = {}
        self.progress_logger = logging.getLogger("agent_spice.sparam.fitting")

    def __enter__(self) -> "_ProgressLog":
        if self.path is None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handler = logging.FileHandler(self.path, mode="w", encoding="utf-8")
        self.handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        self.loggers = [
            self.progress_logger,
            logging.getLogger("skrf.vectorFitting"),
        ]
        for logger in self.loggers:
            self.old_levels[logger] = logger.level
            logger.addHandler(self.handler)
            logger.setLevel(logging.INFO)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc is not None:
            self.exception("fit-sparam failed")
        if self.handler is None:
            return
        for logger in self.loggers:
            logger.removeHandler(self.handler)
            logger.setLevel(self.old_levels[logger])
        self.handler.close()

    def info(self, message: str) -> None:
        if self.handler is None:
            return
        self.progress_logger.info(message)
        self.handler.flush()

    def exception(self, message: str) -> None:
        if self.handler is None:
            return
        self.progress_logger.exception(message)
        self.handler.flush()


def _safe_passivity_violations(vector_fit: VectorFitting, parameter_type: str) -> list[list[float]] | None:
    try:
        violations = _call_with_supported_kwargs(vector_fit.passivity_test, parameter_type=parameter_type)
    except Exception:
        return None
    if violations is None:
        return None
    if hasattr(violations, "tolist"):
        violations = violations.tolist()
    if violations == []:
        return []
    if violations and not isinstance(violations[0], (list, tuple)):
        violations = [violations]
    return [[float(value) for value in band] for band in violations]


def _safe_rms_error(vector_fit: VectorFitting, parameter_type: str) -> float | None:
    try:
        return float(_call_with_supported_kwargs(vector_fit.get_rms_error, parameter_type=parameter_type))
    except Exception:
        return None


def _model_response_at_frequencies(
    vector_fit: VectorFitting,
    row: int,
    column: int,
    freqs: Any,
) -> list[complex] | None:
    if not hasattr(vector_fit, "get_model_response"):
        return None
    method = vector_fit.get_model_response
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        try:
            fitted = method(row, column, freqs=freqs)
        except Exception:
            return None
    else:
        parameters = list(signature.parameters.values())
        supports_freqs_keyword = "freqs" in signature.parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters
        )
        supports_third_positional = any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters)
        supports_third_positional = supports_third_positional or sum(
            parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            for parameter in parameters
        ) >= 3
        try:
            if supports_freqs_keyword:
                fitted = method(row, column, freqs=freqs)
            elif supports_third_positional:
                fitted = method(row, column, freqs)
            else:
                return None
        except Exception:
            return None
    try:
        fitted_values = [complex(value) for value in fitted]
    except Exception:
        return None
    if len(fitted_values) != len(freqs):
        return None
    return fitted_values


def _comparison_rms_error(network: Any, vector_fit: VectorFitting, parameter_type: str) -> float | None:
    network_values = getattr(network, parameter_type.lower(), None)
    if network_values is None or not hasattr(network, "f") or not hasattr(network, "nports"):
        return None
    try:
        network_array = np.asarray(network_values)
        error_mean_squared = 0.0
        for row in range(network.nports):
            for column in range(network.nports):
                fitted = _model_response_at_frequencies(vector_fit, row, column, network.f)
                if fitted is None:
                    return None
                original = network_array[:, row, column].astype(complex)
                error_mean_squared += float(np.mean(np.square(np.abs(original - np.asarray(fitted)))))
        return float(math.sqrt(error_mean_squared))
    except Exception:
        return None


def _quality_summary(result: SParamFitResult) -> dict[str, Any]:
    if result.passive_after_enforce is True:
        passivity = "passive"
    elif result.passive_after_enforce is False:
        passivity = "violations remain"
    else:
        passivity = "unknown"
    payload = result.quality_report.to_dict()
    payload.update(
        {
            "rms_error": result.rms_error,
            "rms_error_scope": "fit_frequency_points",
            "comparison_rms_error": result.comparison_rms_error,
            "comparison_rms_error_scope": "original_frequency_points",
            "passivity": passivity,
            "passivity_enforcement_enabled": result.config.enforce_passivity,
            "violation_bands_after": len(result.passivity_violations_after or []),
        }
    )
    return payload


def _format_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6g}"


def _format_hz(value: float | None) -> str:
    if value is None:
        return "n/a"
    units = [(1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")]
    for scale, suffix in units:
        if abs(value) >= scale:
            return f"{value / scale:.6g} {suffix}"
    return f"{value:.6g} Hz"


def _format_bool(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _format_cell(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _network_s_value(network: Any, point_index: int, row: int, column: int) -> complex:
    try:
        return complex(network.s[point_index, row, column])
    except TypeError:
        return complex(network.s[point_index][row][column])


def _to_db(value: complex) -> float:
    magnitude = max(abs(value), 1e-300)
    return 20.0 * math.log10(magnitude)


def _comparison_traces(network: Any, vector_fit: VectorFitting, max_traces: int = 16) -> list[dict[str, Any]]:
    if not hasattr(network, "s") or not hasattr(vector_fit, "get_model_response"):
        return []
    traces: list[dict[str, Any]] = []
    freqs = [float(value) for value in network.f]
    for row in range(network.nports):
        for column in range(network.nports):
            if len(traces) >= max_traces:
                return traces
            try:
                fitted = _model_response_at_frequencies(vector_fit, row, column, network.f)
                if fitted is None:
                    continue
                original_db = [_to_db(_network_s_value(network, idx, row, column)) for idx in range(len(freqs))]
                fitted_db = [_to_db(value) for value in fitted]
            except Exception:
                continue
            traces.append(
                {
                    "label": f"S{row + 1}{column + 1}",
                    "frequencies_hz": freqs,
                    "original_db": original_db,
                    "fitted_db": fitted_db,
                }
            )
    return traces


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
    freqs = trace["frequencies_hz"]
    values = trace["original_db"] + trace["fitted_db"]
    y_min = min(values)
    y_max = max(values)
    if math.isclose(y_min, y_max):
        y_min -= 1.0
        y_max += 1.0
    padding = max((y_max - y_min) * 0.08, 0.5)
    y_min -= padding
    y_max += padding
    positive_freqs = [max(freq, 1e-300) for freq in freqs]
    x_min = math.log10(min(positive_freqs))
    x_max = math.log10(max(positive_freqs))
    if math.isclose(x_min, x_max):
        x_max += 1.0

    def map_points(series: list[float]) -> list[tuple[float, float]]:
        points = []
        for freq, value in zip(positive_freqs, series):
            x = left + ((math.log10(freq) - x_min) / (x_max - x_min)) * plot_width
            y = top + ((y_max - value) / (y_max - y_min)) * plot_height
            points.append((x, y))
        return points

    original_points = _svg_polyline(map_points(trace["original_db"]))
    fitted_points = _svg_polyline(map_points(trace["fitted_db"]))
    x_start = _format_hz(min(freqs))
    x_end = _format_hz(max(freqs))
    y_top = _format_float(y_max)
    y_bottom = _format_float(y_min)
    label = escape(trace["label"])
    return f"""
<section class="chart">
  <h3>{label} Original vs Fitted</h3>
  <svg viewBox="0 0 {width} {height}" role="img" aria-label="{label} original vs fitted magnitude">
    <rect x="0" y="0" width="{width}" height="{height}" class="plot-bg" />
    <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" class="axis" />
    <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" class="axis" />
    <text x="12" y="{top + 4}" class="tick">{y_top} dB</text>
    <text x="12" y="{height - bottom}" class="tick">{y_bottom} dB</text>
    <text x="{left}" y="{height - 18}" class="tick">{escape(x_start)}</text>
    <text x="{width - right - 92}" y="{height - 18}" class="tick">{escape(x_end)}</text>
    <polyline points="{original_points}" class="line original" />
    <polyline points="{fitted_points}" class="line fitted" />
  </svg>
  <div class="legend"><span class="swatch original"></span>Original Touchstone <span class="swatch fitted"></span>Fitted model</div>
</section>
"""


def _render_html_report(result: SParamFitResult, traces: list[dict[str, Any]]) -> str:
    quality = _quality_summary(result)
    freq_start = None if result.frequency_range_hz is None else result.frequency_range_hz[0]
    freq_end = None if result.frequency_range_hz is None else result.frequency_range_hz[1]
    fit_freq_start = None if result.fit_frequency_range_hz is None else result.fit_frequency_range_hz[0]
    fit_freq_end = None if result.fit_frequency_range_hz is None else result.fit_frequency_range_hz[1]
    selection_rows = "".join(
        f"<tr><td>{escape(key)}</td><td>{escape(_format_cell(value))}</td></tr>"
        for key, value in result.fit_frequency_selection.items()
    )
    violation_rows = "\n".join(
        f"<tr><td>{_format_hz(band[0])}</td><td>{_format_hz(band[1])}</td></tr>"
        for band in (result.passivity_violations_after or [])
    )
    if not violation_rows:
        violation_rows = "<tr><td colspan=\"2\">No violation bands reported after enforcement.</td></tr>"
    diagnostic_rows = "\n".join(
        "<tr>"
        f"<td>{escape(_format_cell(diagnostic['id']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['status']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['severity']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['metric']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['threshold']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['message']))}</td>"
        f"<td>{escape(_format_cell(diagnostic['recommendation']))}</td>"
        "</tr>"
        for diagnostic in quality["diagnostics"]
    )
    if not diagnostic_rows:
        diagnostic_rows = "<tr><td colspan=\"7\">No quality diagnostics reported.</td></tr>"
    trace_sections = "\n".join(_render_trace_chart(trace) for trace in traces)
    if not trace_sections:
        trace_sections = "<p class=\"muted\">Comparison plot unavailable for this scikit-rf version or input.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>S-Parameter Fit Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #17202a; background: #f7f9fb; }}
    h1, h2, h3 {{ color: #102a43; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
    .card {{ background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 14px; }}
    .label {{ color: #627d98; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .value {{ font-size: 20px; font-weight: 650; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; margin: 12px 0 24px; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #d9e2ec; }}
    th {{ background: #eef2f7; }}
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
    .muted {{ color: #627d98; }}
  </style>
</head>
<body>
  <h1>S-Parameter Fit Report</h1>
  <div class="cards">
    <div class="card"><div class="label">Ports</div><div class="value">{result.ports}</div></div>
    <div class="card"><div class="label">Frequency Points</div><div class="value">{result.frequency_points}</div></div>
    <div class="card"><div class="label">Fit Frequency Points</div><div class="value">{result.fit_frequency_points}</div></div>
    <div class="card"><div class="label">Fit-Sample RMS Error</div><div class="value">{_format_float(result.rms_error)}</div></div>
    <div class="card"><div class="label">Original-Point RMS Error</div><div class="value">{_format_float(result.comparison_rms_error)}</div></div>
    <div class="card"><div class="label">Quality</div><div class="value">{escape(str(quality["status"]))}</div></div>
    <div class="card"><div class="label">Passivity</div><div class="value">{escape(str(quality["passivity"]))}</div></div>
  </div>

  <h2>Quality Gate</h2>
  <table>
    <tr><th>Item</th><th>Value</th></tr>
    <tr><td>Profile</td><td>{escape(str(quality["profile"]))}</td></tr>
    <tr><td>Status</td><td>{escape(str(quality["status"]))}</td></tr>
    <tr><td>Allowed for</td><td>{escape(str(quality["allowed_for"]))}</td></tr>
    <tr><td>Blocking reasons</td><td>{escape(', '.join(quality["blocking_reasons"]))}</td></tr>
    <tr><td>Warnings</td><td>{escape(', '.join(quality["warnings"]))}</td></tr>
  </table>
  <table>
    <tr><th>Diagnostic</th><th>Status</th><th>Severity</th><th>Metric</th><th>Threshold</th><th>Message</th><th>Recommendation</th></tr>
    {diagnostic_rows}
  </table>

  <h2>Input And Output</h2>
  <table>
    <tr><th>Item</th><th>Value</th></tr>
    <tr><td>Touchstone</td><td>{escape(str(result.touchstone_path))}</td></tr>
    <tr><td>SPICE subcircuit</td><td>{escape(str(result.spice_path))}</td></tr>
    <tr><td>JSON report</td><td>{escape(str(result.report_path))}</td></tr>
    <tr><td>Frequency span</td><td>{_format_hz(freq_start)} to {_format_hz(freq_end)}</td></tr>
    <tr><td>Reference impedance</td><td>{escape(', '.join(_format_float(value) for value in result.reference_impedance))}</td></tr>
  </table>

  <h2>Fit Sample Selection</h2>
  <table>
    <tr><th>Item</th><th>Value</th></tr>
    <tr><td>Original frequency points</td><td>{result.frequency_points}</td></tr>
    <tr><td>Fit frequency points</td><td>{result.fit_frequency_points}</td></tr>
    <tr><td>Original frequency span</td><td>{_format_hz(freq_start)} to {_format_hz(freq_end)}</td></tr>
    <tr><td>Fit frequency span</td><td>{_format_hz(fit_freq_start)} to {_format_hz(fit_freq_end)}</td></tr>
    <tr><td>Fit-sample RMS error</td><td>{_format_float(result.rms_error)}</td></tr>
    <tr><td>Original-point comparison RMS error</td><td>{_format_float(result.comparison_rms_error)}</td></tr>
    {selection_rows}
  </table>

  <h2>Fit Configuration</h2>
  <table>
    <tr><th>Field</th><th>Value</th></tr>
    {''.join(f'<tr><td>{escape(key)}</td><td>{escape(_format_cell(value))}</td></tr>' for key, value in asdict(result.config).items())}
  </table>

  <h2>Passivity</h2>
  <table>
    <tr><th>Check</th><th>Value</th></tr>
    <tr><td>Passive before enforcement</td><td>{_format_bool(result.passive_before_enforce)}</td></tr>
    <tr><td>Passive after enforcement</td><td>{_format_bool(result.passive_after_enforce)}</td></tr>
    <tr><td>Enforcement enabled</td><td>{_format_bool(result.config.enforce_passivity)}</td></tr>
  </table>
  <table>
    <tr><th>Violation band start</th><th>Violation band end</th></tr>
    {violation_rows}
  </table>

  <h2>Original vs Fitted</h2>
  {trace_sections}
</body>
</html>
"""


def _fit_model(vector_fit: VectorFitting, config: SParamFitConfig) -> None:
    if config.max_iterations is not None and hasattr(vector_fit, "max_iterations"):
        vector_fit.max_iterations = config.max_iterations
    if config.mode == "auto":
        _call_with_supported_kwargs(
            vector_fit.auto_fit,
            n_poles_init_real=config.n_poles_init_real,
            n_poles_init_cmplx=config.n_poles_init_cmplx,
            n_poles_add=config.n_poles_add,
            model_order_max=config.model_order_max,
            iters_start=config.iters_start,
            iters_inter=config.iters_inter,
            iters_final=config.iters_final,
            target_error=config.target_error,
            alpha=config.alpha,
            gamma=config.gamma,
            nu_samples=config.nu_samples,
            parameter_type=config.parameter_type,
            enforce_dc=config.enforce_dc,
        )
        return
    if config.mode == "manual":
        _call_with_supported_kwargs(
            vector_fit.vector_fit,
            n_poles_real=config.n_poles_real,
            n_poles_cmplx=config.n_poles_cmplx,
            init_pole_spacing=config.init_pole_spacing,
            parameter_type=config.parameter_type,
            fit_constant=config.fit_constant,
            fit_proportional=config.fit_proportional,
            enforce_dc=config.enforce_dc,
        )
        return
    raise ValueError(f"Unsupported S-parameter fit mode '{config.mode}'")


def fit_touchstone_to_spice(
    touchstone_path: Path,
    output_path: Path,
    config: SParamFitConfig | None = None,
    report_path: Path | None = None,
    html_report_path: Path | None = None,
    log_path: Path | None = None,
) -> SParamFitResult:
    config = config or SParamFitConfig()
    with _ProgressLog(log_path) as progress:
        progress.info(f"loading Touchstone: {touchstone_path}")
        network = rf.Network(str(touchstone_path))
        progress.info(
            f"loaded Touchstone: ports={network.nports}, frequency_points={len(network.f)}, "
            f"frequency_range={_frequency_range(network)}"
        )
        fit_network = _select_fit_network(network, config)
        if fit_network is network:
            progress.info("using all frequency points for vector fit")
        else:
            progress.info(
                f"using frequency subset for vector fit: {len(fit_network.f)} of {len(network.f)} points, "
                f"range={_frequency_range(fit_network)}, selection={_frequency_selection_summary(config)}"
            )
        vector_fit = VectorFitting(fit_network)
        progress.info(f"starting vector fit: mode={config.mode}, parameter_type={config.parameter_type}")
        _fit_model(vector_fit, config)
        progress.info("vector fit finished")
        progress.info("checking passivity before enforcement")
        passive_before = _safe_bool(vector_fit.is_passive, parameter_type=config.parameter_type)
        violations_before = _safe_passivity_violations(vector_fit, config.parameter_type)
        if config.enforce_passivity:
            progress.info(
                f"starting passivity enforcement: n_samples={config.passivity_samples}, "
                f"f_max={config.passivity_f_max}, preserve_dc={config.preserve_dc}"
            )
            _call_with_supported_kwargs(
                vector_fit.passivity_enforce,
                n_samples=config.passivity_samples,
                f_max=config.passivity_f_max,
                parameter_type=config.parameter_type,
                preserve_dc=config.preserve_dc,
            )
            progress.info("passivity enforcement finished")
        else:
            progress.info("passivity enforcement skipped")
        passive_after = _safe_bool(vector_fit.is_passive, parameter_type=config.parameter_type)
        violations_after = _safe_passivity_violations(vector_fit, config.parameter_type)
        rms_error = _safe_rms_error(vector_fit, config.parameter_type)
        comparison_rms_error = _comparison_rms_error(network, vector_fit, config.parameter_type)
        quality_report = build_quality_report(
            network=network,
            frequency_points=len(network.f),
            fit_frequency_points=len(fit_network.f),
            comparison_rms_error=comparison_rms_error,
            passive_after_enforce=passive_after,
            passivity_violations_after=violations_after,
            enforce_passivity=config.enforce_passivity,
            poles=getattr(vector_fit, "poles", None),
            profile=config.quality_profile,
            comparison_rms_limit=config.max_comparison_rms_error,
            passivity_epsilon=config.max_passivity_epsilon,
            require_dc=config.require_dc,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        progress.info(f"writing SPICE subcircuit: {output_path}")
        _call_with_supported_kwargs(
            vector_fit.write_spice_subcircuit_s,
            str(output_path),
            fitted_model_name=config.subckt_name,
            create_reference_pins=config.create_reference_pins,
        )
        result = SParamFitResult(
            touchstone_path=touchstone_path,
            spice_path=output_path,
            report_path=report_path,
            html_report_path=html_report_path,
            log_path=log_path,
            ports=network.nports,
            frequency_points=len(network.f),
            frequency_range_hz=_frequency_range(network),
            fit_frequency_points=len(fit_network.f),
            fit_frequency_range_hz=_frequency_range(fit_network),
            fit_frequency_selection=_frequency_selection_summary(config),
            reference_impedance=_reference_impedance(network),
            config=config,
            rms_error=rms_error,
            comparison_rms_error=comparison_rms_error,
            passive_before_enforce=passive_before,
            passive_after_enforce=passive_after,
            passivity_violations_before=violations_before,
            passivity_violations_after=violations_after,
            quality_report=quality_report,
        )
        if report_path is not None:
            progress.info(f"writing JSON report: {report_path}")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if html_report_path is not None:
            progress.info(f"writing HTML report: {html_report_path}")
            html_report_path.parent.mkdir(parents=True, exist_ok=True)
            html_report_path.write_text(
                _render_html_report(result, _comparison_traces(network, vector_fit)),
                encoding="utf-8",
            )
        progress.info("fit-sparam completed")
        return result
