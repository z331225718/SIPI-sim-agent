from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any
import xml.etree.ElementTree as ET

import numpy as np


DEFAULT_IDEM_BIN_DIR = Path(r"C:\Program Files\CST Studio Suite 2026\AMD64")


@dataclass(frozen=True)
class IdemFittingOptions:
    order: int
    threads: int = 1
    target: float = 1e-3
    initial_iterations: int = 3
    postadding_iterations: int = 1
    final_iterations: int = 1
    enhance_poles_placement: bool = False
    enforce_dc: bool = False
    enforce_asymptotic_passivity: bool = True
    asymptotic_passivity_margin: float = 1e-3
    asymptotic_relocate_poles: bool = False
    split_type: str = "none"
    p4poles_type: str = "all"
    p4poles_n_largest: str = "INF"
    p4res_type: str = "all"
    bandwidth: float | None = None


@dataclass(frozen=True)
class IdemAdaptiveFittingOptions:
    initial_iterations: int = 3
    postadding_iterations: int = 1
    final_iterations: int = 1
    enhance_poles_placement: bool = False
    stagnation_alpha: float = 0.05
    stagnation_back_steps: int = 3
    skimming_tolerance: float = 1e-3
    final_skimming_tolerance: float = 1e-3
    guaranteed_accuracy: float = 0.1
    split_type: str = "none"
    p4poles_type: str = "all"
    p4poles_n_largest: str = "INF"
    p4res_type: str = "all"
    enforce_dc: bool = True
    enforce_asymptotic_passivity: bool = True
    asymptotic_passivity_margin: float = 1e-3
    asymptotic_relocate_poles: bool = False
    reject_poles: bool = False
    reject_poles_max_relative_frequency: float = math.inf
    relative_frequency_weight_alpha: float | None = None
    relative_frequency_weight_threshold: float = 1e-10
    absolute_frequency_weight_points: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        _validate_nonnegative_int("initial_iterations", self.initial_iterations)
        _validate_positive_int("postadding_iterations", self.postadding_iterations)
        _validate_positive_int("final_iterations", self.final_iterations)
        _validate_bool("enhance_poles_placement", self.enhance_poles_placement)
        _validate_positive_finite("stagnation_alpha", self.stagnation_alpha)
        _validate_positive_int("stagnation_back_steps", self.stagnation_back_steps)
        _validate_positive_finite("skimming_tolerance", self.skimming_tolerance)
        _validate_positive_finite("final_skimming_tolerance", self.final_skimming_tolerance)
        _validate_positive_finite("guaranteed_accuracy", self.guaranteed_accuracy)
        _validate_choice("split_type", self.split_type, {"none", "column", "row", "all"})
        _validate_choice("p4poles_type", self.p4poles_type, {"all", "eye"})
        object.__setattr__(
            self,
            "p4poles_n_largest",
            _normalize_positive_integer_or_inf("p4poles_n_largest", self.p4poles_n_largest),
        )
        _validate_choice("p4res_type", self.p4res_type, {"all", "eye"})
        _validate_bool("enforce_dc", self.enforce_dc)
        _validate_bool("enforce_asymptotic_passivity", self.enforce_asymptotic_passivity)
        _validate_unit_interval_positive("asymptotic_passivity_margin", self.asymptotic_passivity_margin)
        _validate_bool("asymptotic_relocate_poles", self.asymptotic_relocate_poles)
        _validate_bool("reject_poles", self.reject_poles)
        object.__setattr__(
            self,
            "reject_poles_max_relative_frequency",
            _normalize_positive_float_or_inf(
                "reject_poles_max_relative_frequency",
                self.reject_poles_max_relative_frequency,
            ),
        )
        if self.relative_frequency_weight_alpha is not None:
            _validate_nonnegative_finite("relative_frequency_weight_alpha", self.relative_frequency_weight_alpha)
        _validate_positive_finite("relative_frequency_weight_threshold", self.relative_frequency_weight_threshold)
        normalized_points = _normalize_absolute_frequency_weight_points(self.absolute_frequency_weight_points)
        object.__setattr__(self, "absolute_frequency_weight_points", normalized_points)
        if self.relative_frequency_weight_alpha is not None and normalized_points:
            raise ValueError("relative and absolute frequency weights are mutually exclusive")


@dataclass(frozen=True)
class IdemAdaptiveRuntimeContract:
    order_min: int
    order_step: int
    order_max: int
    target: float
    bandwidth_hz: float
    threads: int
    requested_order_step: int | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_positive_int("order_min", self.order_min)
        _validate_positive_int("order_step", self.order_step)
        _validate_positive_int("order_max", self.order_max)
        if self.order_step < 2:
            raise ValueError("order_step must be >= 2 for the IdEM runtime parser envelope")
        if self.order_min > self.order_max:
            raise ValueError("order_min must be <= order_max")
        _validate_positive_finite("target", self.target)
        _validate_positive_finite("bandwidth_hz", self.bandwidth_hz)
        _validate_positive_int("threads", self.threads)
        if self.requested_order_step is None:
            object.__setattr__(self, "requested_order_step", self.order_step)
        else:
            _validate_positive_int("requested_order_step", self.requested_order_step)
        if isinstance(self.warnings, str):
            raise ValueError("warnings must be a sequence of strings")
        warnings = tuple(self.warnings)
        if not all(isinstance(item, str) for item in warnings):
            raise ValueError("warnings must be a sequence of strings")
        object.__setattr__(self, "warnings", warnings)

    @property
    def effective_order_step(self) -> int:
        return self.order_step

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_min": self.order_min,
            "order_step": self.order_step,
            "order_max": self.order_max,
            "target": float(self.target),
            "bandwidth_hz": float(self.bandwidth_hz),
            "threads": self.threads,
            "requested_order_step": self.requested_order_step,
            "effective_order_step": self.effective_order_step,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class IdemCommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    peak_memory_mb: float | None
    telemetry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["telemetry"] is None:
            del payload["telemetry"]
        return payload


class CommandIdleStallError(TimeoutError):
    """Raised when a command is killed after the idle-progress watchdog fires."""

    def __init__(self, command_result: IdemCommandResult):
        telemetry = command_result.telemetry or {}
        idle_limit = telemetry.get("idle_limit")
        message = f"Command stalled after {idle_limit} idle seconds: {' '.join(command_result.command)}"
        super().__init__(message)
        self.command_result = command_result
        self.telemetry = telemetry


@dataclass(frozen=True)
class PoleRelocationStep:
    iteration: int
    poles_rad_per_s: np.ndarray
    denominator_residues: np.ndarray | None
    selected_response_indices: tuple[int, ...]
    rank: int | None
    condition_number: float | None


def render_fitting_options_xml(options: IdemFittingOptions) -> str:
    if options.bandwidth is None:
        raise ValueError("bandwidth must be set when rendering IdEM fitting XML")
    bandwidth_value = f"{options.bandwidth:.16g}"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<fittingTask version="1.0" xmlns="OptionsFittingSchema.xsd">
  <options>
    <threads>{options.threads}</threads>
    <bandwidth mode="absolute">{bandwidth_value}</bandwidth>
    <order>
      <type>fixed</type>
      <value>{options.order}</value>
    </order>
    <iterations>
      <initial>{options.initial_iterations}</initial>
      <postadding>{options.postadding_iterations}</postadding>
      <final>{options.final_iterations}</final>
      <enhancePolesPlacement>{_xml_bool(options.enhance_poles_placement)}</enhancePolesPlacement>
    </iterations>
    <errorControl>
      <stagnation>
        <alpha>0.05</alpha>
        <nBackSteps>3</nBackSteps>
      </stagnation>
      <skimming>
        <relativeTolerance>0.001</relativeTolerance>
        <finalRelativeTolerance>0.001</finalRelativeTolerance>
      </skimming>
      <accuracy>
        <target>{options.target:.16g}</target>
        <guaranteed>0.1</guaranteed>
      </accuracy>
    </errorControl>
    <splitting>
      <splits>
        <type>{_escape_xml_text(options.split_type)}</type>
      </splits>
      <p4poles>
        <type>{_escape_xml_text(options.p4poles_type)}</type>
        <nLargest>{_escape_xml_text(options.p4poles_n_largest)}</nLargest>
      </p4poles>
      <p4res>
        <type>{_escape_xml_text(options.p4res_type)}</type>
      </p4res>
    </splitting>
    <outOfBand>
      <enforceDC>{_xml_bool(options.enforce_dc)}</enforceDC>
      <frequencyProportionalTerm>false</frequencyProportionalTerm>
      <enforceAsymptoticPassivity enabled="{_xml_bool(options.enforce_asymptotic_passivity)}">
        <passivityMargin>{options.asymptotic_passivity_margin:.16g}</passivityMargin>
        <relocatePoles>{_xml_bool(options.asymptotic_relocate_poles)}</relocatePoles>
      </enforceAsymptoticPassivity>
      <rejectPoles enabled="false"/>
    </outOfBand>
  </options>
</fittingTask>
"""


def write_fitting_options_xml(options: IdemFittingOptions, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_fitting_options_xml(options), encoding="utf-8")
    return path


def render_adaptive_fitting_options_xml(
    options: IdemAdaptiveFittingOptions,
    *,
    order_min: int | None = None,
    order_step: int | None = None,
    order_max: int | None = None,
    target: float | None = None,
    bandwidth_hz: float | None = None,
    threads: int | None = None,
) -> str:
    return _render_adaptive_options_xml(options, runtime_contract=None)


def render_adaptive_runtime_parser_envelope_xml(
    options: IdemAdaptiveFittingOptions,
    runtime_contract: IdemAdaptiveRuntimeContract,
) -> str:
    return _render_adaptive_options_xml(options, runtime_contract=runtime_contract)


def _render_adaptive_options_xml(
    options: IdemAdaptiveFittingOptions,
    *,
    runtime_contract: IdemAdaptiveRuntimeContract | None,
) -> str:
    root = ET.Element("fittingTask", {"version": "1.0", "xmlns": "OptionsFittingSchema.xsd"})
    options_node = ET.SubElement(root, "options")
    if runtime_contract is not None:
        _append_xml_text(options_node, "threads", str(runtime_contract.threads))
        _append_xml_text(options_node, "bandwidth", _format_idem_float(runtime_contract.bandwidth_hz)).set(
            "mode",
            "absolute",
        )
        order = ET.SubElement(options_node, "order")
        _append_xml_text(order, "type", "custom")
        _append_xml_text(order, "min", str(runtime_contract.order_min))
        _append_xml_text(order, "increment", str(runtime_contract.order_step))
        _append_xml_text(order, "max", str(runtime_contract.order_max))

    iterations = ET.SubElement(options_node, "iterations")
    _append_xml_text(iterations, "initial", _format_idem_float(options.initial_iterations))
    _append_xml_text(iterations, "postadding", _format_idem_float(options.postadding_iterations))
    _append_xml_text(iterations, "final", _format_idem_float(options.final_iterations))
    _append_xml_text(iterations, "enhancePolesPlacement", _xml_bool(options.enhance_poles_placement))

    frequency_weights_enabled = options.relative_frequency_weight_alpha is not None or bool(
        options.absolute_frequency_weight_points
    )
    if frequency_weights_enabled:
        weights = ET.SubElement(options_node, "weights")
        frequency = ET.SubElement(weights, "frequency", {"enabled": "true"})
        if options.relative_frequency_weight_alpha is not None:
            relative = ET.SubElement(frequency, "relative")
            _append_xml_text(relative, "alpha", _format_idem_float(options.relative_frequency_weight_alpha))
            _append_xml_text(
                relative,
                "relativeThreshold",
                _format_idem_float(options.relative_frequency_weight_threshold),
            )
        else:
            absolute = ET.SubElement(frequency, "absolute")
            for frequency_hz, weight in options.absolute_frequency_weight_points:
                _append_xml_text(absolute, "point", f"{_format_idem_float(frequency_hz)} {_format_idem_float(weight)}")

    error_control = ET.SubElement(options_node, "errorControl")
    stagnation = ET.SubElement(error_control, "stagnation")
    _append_xml_text(stagnation, "alpha", _format_idem_float(options.stagnation_alpha))
    _append_xml_text(stagnation, "nBackSteps", _format_idem_float(options.stagnation_back_steps))
    skimming = ET.SubElement(error_control, "skimming")
    _append_xml_text(skimming, "relativeTolerance", _format_idem_float(options.skimming_tolerance))
    _append_xml_text(skimming, "finalRelativeTolerance", _format_idem_float(options.final_skimming_tolerance))
    accuracy = ET.SubElement(error_control, "accuracy")
    if runtime_contract is not None:
        _append_xml_text(accuracy, "target", _format_idem_float(runtime_contract.target))
    _append_xml_text(accuracy, "guaranteed", _format_idem_float(options.guaranteed_accuracy))

    splitting = ET.SubElement(options_node, "splitting")
    splits = ET.SubElement(splitting, "splits")
    _append_xml_text(splits, "type", options.split_type)
    p4poles = ET.SubElement(splitting, "p4poles")
    _append_xml_text(p4poles, "type", options.p4poles_type)
    _append_xml_text(p4poles, "nLargest", options.p4poles_n_largest)
    p4res = ET.SubElement(splitting, "p4res")
    _append_xml_text(p4res, "type", options.p4res_type)

    out_of_band = ET.SubElement(options_node, "outOfBand")
    _append_xml_text(out_of_band, "enforceDC", _xml_bool(options.enforce_dc))
    _append_xml_text(out_of_band, "frequencyProportionalTerm", "false")
    asymptotic = ET.SubElement(
        out_of_band,
        "enforceAsymptoticPassivity",
        {"enabled": _xml_bool(options.enforce_asymptotic_passivity)},
    )
    _append_xml_text(asymptotic, "passivityMargin", _format_idem_float(options.asymptotic_passivity_margin))
    _append_xml_text(asymptotic, "relocatePoles", _xml_bool(options.asymptotic_relocate_poles))
    reject_poles = ET.SubElement(out_of_band, "rejectPoles", {"enabled": _xml_bool(options.reject_poles)})
    if options.reject_poles:
        _append_xml_text(
            reject_poles,
            "maxRelativeFrequency",
            _format_idem_float(options.reject_poles_max_relative_frequency),
        )

    ET.indent(root, space="  ")
    return f"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n{ET.tostring(root, encoding='unicode')}\n"


def write_adaptive_fitting_options_xml(
    options: IdemAdaptiveFittingOptions,
    path: Path,
    *,
    order_min: int | None = None,
    order_step: int | None = None,
    order_max: int | None = None,
    target: float | None = None,
    bandwidth_hz: float | None = None,
    threads: int | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_adaptive_fitting_options_xml(options),
        encoding="utf-8",
    )
    return path


def write_adaptive_runtime_parser_envelope_xml(
    options: IdemAdaptiveFittingOptions,
    path: Path,
    runtime_contract: IdemAdaptiveRuntimeContract,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_adaptive_runtime_parser_envelope_xml(options, runtime_contract),
        encoding="utf-8",
    )
    return path


def run_idem_initial_iteration_probe(
    touchstone_path: Path,
    output_root: Path,
    *,
    order: int,
    initial_iterations: list[int],
    idem_bin_dir: Path | None = None,
    threads: int = 1,
    target: float = 1e-3,
    enforce_asymptotic_passivity: bool = True,
    asymptotic_relocate_poles: bool = False,
    enhance_poles_placement: bool = False,
    timeout_seconds: float | None = None,
) -> list[dict[str, Any]]:
    if order < 1:
        raise ValueError("order must be >= 1")
    if not initial_iterations:
        raise ValueError("initial_iterations must contain at least one value")

    output_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for initial_iter in initial_iterations:
        if initial_iter < 0:
            raise ValueError("initial iteration values must be >= 0")
        run_dir = output_root / f"order{order}_init{initial_iter}"
        run_dir.mkdir(parents=True, exist_ok=True)
        options = IdemFittingOptions(
            order=order,
            threads=threads,
            target=target,
            initial_iterations=initial_iter,
            bandwidth=_touchstone_bandwidth_hz(touchstone_path),
            enforce_asymptotic_passivity=enforce_asymptotic_passivity,
            asymptotic_relocate_poles=asymptotic_relocate_poles,
            enhance_poles_placement=enhance_poles_placement,
        )
        xml_path = write_fitting_options_xml(options, run_dir / "fitting_options.fopt.xml")
        model_path = run_dir / "model.mod.h5"
        command_result = run_idem_fitting(
            touchstone_path,
            model_path,
            options_xml_path=xml_path,
            idem_bin_dir=idem_bin_dir,
            timeout_seconds=timeout_seconds,
        )
        summary = inspect_idem_model(model_path) if model_path.exists() else {}
        completed = _idem_fit_completed(command_result, model_path)
        results.append(
            {
                "probe": "idem_initial_iterations",
                "touchstone_path": str(touchstone_path),
                "output_dir": str(run_dir),
                "model_path": str(model_path),
                "xml_path": str(xml_path),
                "order": order,
                "initial_iterations": initial_iter,
                "target": target,
                "threads": threads,
                "enforce_asymptotic_passivity": enforce_asymptotic_passivity,
                "asymptotic_relocate_poles": asymptotic_relocate_poles,
                "enhance_poles_placement": enhance_poles_placement,
                "status": "completed" if completed else "failed",
                "command": command_result.to_dict(),
                "model": summary,
            }
        )
    return results


def run_idem_fitting(
    touchstone_path: Path,
    model_path: Path,
    *,
    options_xml_path: Path | None = None,
    idem_bin_dir: Path | None = None,
    timeout_seconds: float | None = None,
) -> IdemCommandResult:
    idem_bin_dir = _resolve_idem_bin_dir(idem_bin_dir)
    exe_path = idem_bin_dir / "idemmp_fitting.exe"
    command = [str(exe_path), "-its", str(touchstone_path), "-o", str(model_path)]
    if options_xml_path is not None:
        command.extend(["-xml", str(options_xml_path)])
    return _run_command(command, timeout_seconds=timeout_seconds)


def run_idem_adaptive_fitting(
    touchstone_path: Path,
    model_path: Path,
    *,
    order_min: int,
    order_step: int,
    order_max: int,
    target: float,
    bandwidth_hz: float,
    threads: int,
    options_xml_path: Path,
    idem_bin_dir: Path | None = None,
    timeout_seconds: float | None = None,
    idle_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    touchstone_path = Path(touchstone_path)
    model_path = Path(model_path)
    options_xml_path = Path(options_xml_path)
    _validate_adaptive_fitting_inputs(
        touchstone_path,
        options_xml_path,
        order_min=order_min,
        order_step=order_step,
        order_max=order_max,
        target=target,
        bandwidth_hz=bandwidth_hz,
        threads=threads,
    )

    idem_bin_dir = _resolve_idem_bin_dir(idem_bin_dir)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.unlink(missing_ok=True)
    command = [
        str(idem_bin_dir / "idemmp_fitting.exe"),
        "-its",
        str(touchstone_path),
        "-o",
        str(model_path),
        "-tol",
        _format_idem_float(target),
        "-orderMin",
        str(order_min),
        "-orderStep",
        str(order_step),
        "-orderMax",
        str(order_max),
        "-bandwidth",
        _format_idem_float(bandwidth_hz),
        "-DC",
        "1",
        "-nThreads",
        str(threads),
        "-xml",
        str(options_xml_path),
    ]
    run_kwargs: dict[str, Any] = {"timeout_seconds": timeout_seconds}
    if idle_timeout_seconds is not None:
        run_kwargs["idle_timeout_seconds"] = idle_timeout_seconds
        run_kwargs["progress_paths"] = [model_path]
    command_result = _run_command(command, **run_kwargs)
    completed = _idem_adaptive_fit_completed(command_result, model_path)
    model: dict[str, Any] = {}
    error = None if completed else "IdEM adaptive fitting did not complete successfully"
    if completed:
        try:
            model = inspect_idem_model(model_path)
        except Exception as exc:
            completed = False
            error = f"IdEM adaptive fitting inspection failure: {type(exc).__name__}: {exc}"
    return {
        "probe": "idem_adaptive_fitting",
        "touchstone_path": str(touchstone_path),
        "model_path": str(model_path),
        "xml_path": str(options_xml_path),
        "order_min": order_min,
        "order_step": order_step,
        "order_max": order_max,
        "target": float(target),
        "bandwidth_hz": float(bandwidth_hz),
        "threads": threads,
        "status": "completed" if completed else "failed",
        "error": error,
        "command": command_result.to_dict(),
        "model": model,
    }


def parse_idem_accuracy_report(text: str) -> dict[str, Any]:
    def required(pattern: str, label: str) -> str:
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match is None:
            raise ValueError(f"IdEM accuracy report is missing {label}")
        return match.group(1)

    ports = int(required(r"^\s*\*\*\s*No\. of ports:\s*(\d+)\s*$", "No. of ports"))
    frequency_points = int(required(r"^\s*\*\*\s*No\. of samples:\s*(\d+)\s*$", "No. of samples"))
    max_error = float(required(r"^\s*\*\*\s*Max Err:\s*([-+0-9.eE]+)\s*$", "Max Err"))
    mean_rms = float(required(r"^\s*\*\*\s*RMS Err:\s*([-+0-9.eE]+)\s*$", "RMS Err"))
    if ports < 1 or frequency_points < 1:
        raise ValueError("IdEM accuracy report contains non-positive dimensions")
    if not math.isfinite(max_error) or max_error < 0.0:
        raise ValueError("IdEM accuracy report contains an invalid Max Err")
    if not math.isfinite(mean_rms) or mean_rms < 0.0:
        raise ValueError("IdEM accuracy report contains an invalid RMS Err")
    return {
        "ports": ports,
        "frequency_points": frequency_points,
        "max_error": max_error,
        "mean_rms": mean_rms,
    }


def run_idem_accuracy_check(
    touchstone_path: Path,
    model_path: Path,
    report_path: Path,
    *,
    idem_bin_dir: Path | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    idem_bin_dir = _resolve_idem_bin_dir(idem_bin_dir)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)
    command = [
        str(idem_bin_dir / "idemmp_checkaccuracy.exe"),
        "-its",
        str(touchstone_path),
        "-ih5m",
        str(model_path),
        "-r",
        str(report_path),
    ]
    command_result = _run_command(command, timeout_seconds=timeout_seconds)
    metrics = None
    error = None
    if report_path.is_file() and report_path.stat().st_size > 0:
        try:
            metrics = parse_idem_accuracy_report(report_path.read_text(encoding="utf-8", errors="replace"))
        except ValueError as exc:
            error = str(exc)
    else:
        error = "IdEM accuracy report was not created"
    return {
        "probe": "idem_accuracy_check",
        "touchstone_path": str(touchstone_path),
        "model_path": str(model_path),
        "report_path": str(report_path),
        "status": "completed" if metrics is not None else "failed",
        "metrics": metrics,
        "error": error,
        "command": command_result.to_dict(),
    }


def run_idem_touchstone_export(
    model_path: Path,
    output_path: Path,
    *,
    idem_bin_dir: Path | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    idem_bin_dir = _resolve_idem_bin_dir(idem_bin_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    command = [
        str(idem_bin_dir / "idemmp_export.exe"),
        "-ih5",
        str(model_path),
        "-o",
        str(output_path),
        "-type",
        "2",
    ]
    command_result = _run_command(command, timeout_seconds=timeout_seconds)
    artifact_exists = output_path.is_file() and output_path.stat().st_size > 0
    completed = artifact_exists and "Results" in command_result.stdout
    return {
        "probe": "idem_touchstone_export",
        "model_path": str(model_path),
        "output_path": str(output_path),
        "status": "completed" if completed else "failed",
        "error": None if completed else "IdEM Touchstone export did not create a valid artifact",
        "command": command_result.to_dict(),
    }


def parse_idem_passivity_stdout(stdout: str) -> dict[str, Any]:
    max_singular_values: list[dict[str, Any]] = []
    current_soc_iteration: int | None = None
    soc_iterations = 0
    ham_iterations = 0
    ham_imaginary_eigenvalues: list[int] = []
    passive: bool | None = None

    for line in stdout.splitlines():
        stripped = line.strip()
        soc_match = re.search(r"SOC Iteration no\.\s*(\d+)", stripped)
        if soc_match:
            current_soc_iteration = int(soc_match.group(1))
            soc_iterations = max(soc_iterations, current_soc_iteration)
            continue
        ham_match = re.search(r"HAM Iteration no\.\s*(\d+)", stripped)
        if ham_match:
            ham_iterations = max(ham_iterations, int(ham_match.group(1)))
            continue
        singular_match = re.search(
            r"Maximum Singular Value\s*:\s*([-+0-9.eE]+)\s*@\s*([-+0-9.eE]+)\s*Hz",
            stripped,
        )
        if singular_match:
            max_singular_values.append(
                {
                    "iteration": current_soc_iteration,
                    "value": float(singular_match.group(1)),
                    "frequency_hz": float(singular_match.group(2)),
                }
            )
            continue
        eigen_match = re.search(r"Found\s+(\d+)\s+imaginary eigenvalues", stripped)
        if eigen_match:
            ham_imaginary_eigenvalues.append(int(eigen_match.group(1)))
            continue
        passive_match = re.search(r"Passive:\s*(YES|NO)", stripped, flags=re.IGNORECASE)
        if passive_match:
            passive = passive_match.group(1).upper() == "YES"

    return {
        "passive": passive,
        "soc_iterations": soc_iterations,
        "ham_iterations": ham_iterations,
        "ham_imaginary_eigenvalues": ham_imaginary_eigenvalues,
        "max_singular_values": max_singular_values,
    }


def run_idem_passivity(
    model_path: Path,
    output_model_path: Path,
    *,
    idem_bin_dir: Path | None = None,
    threads: int = 8,
    ham_solver: int | None = None,
    preserve_dc: bool = False,
    only_check: int | None = None,
    options_xml_path: Path | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    idem_bin_dir = _resolve_idem_bin_dir(idem_bin_dir)
    command = [str(idem_bin_dir / "idemmp_passivity.exe"), "-ih5", str(model_path), "-o", str(output_model_path)]
    if only_check is not None:
        command.extend(["-onlyCheck", str(only_check)])
    if ham_solver is not None:
        command.extend(["-hamSolver", str(ham_solver)])
    if preserve_dc:
        command.extend(["-DC", "1"])
    command.extend(["-nThreads", str(threads)])
    if options_xml_path is not None:
        command.extend(["-xml", str(options_xml_path)])

    command_result = _run_command(command, timeout_seconds=timeout_seconds)
    passivity = parse_idem_passivity_stdout(command_result.stdout)
    completed = _idem_passivity_completed(command_result, output_model_path)
    model = inspect_idem_model(output_model_path) if output_model_path.exists() else {}
    return {
        "probe": "idem_passivity",
        "model_path": str(model_path),
        "output_model_path": str(output_model_path),
        "status": "completed" if completed else "failed",
        "threads": threads,
        "ham_solver": ham_solver,
        "preserve_dc": preserve_dc,
        "only_check": only_check,
        "xml_path": str(options_xml_path) if options_xml_path is not None else None,
        "command": command_result.to_dict(),
        "passivity": passivity,
        "model": model,
    }


def inspect_idem_model(model_path: Path) -> dict[str, Any]:
    try:
        import h5py
    except ImportError as exc:
        raise RuntimeError("h5py is required to inspect IdEM .mod.h5 files") from exc

    with h5py.File(model_path, "r") as handle:
        datasets: list[dict[str, Any]] = []
        pole_blocks: list[dict[str, Any]] = []
        error_history = _read_first_object_dataset(handle, "MOD/errorHistory")
        orders_history = _read_first_object_dataset(handle, "MOD/ordersHistory")
        fitting_options_xml = _read_text_dataset(handle, "MOD/fittingOptions")
        is_passive = _array_to_jsonable(handle["MOD/isPassive"][()]) if "MOD/isPassive" in handle else None

        def visit(name: str, obj: Any) -> None:
            if not hasattr(obj, "shape"):
                return
            datasets.append(
                {
                    "path": name,
                    "shape": list(obj.shape),
                    "dtype": str(obj.dtype),
                    "size": int(obj.size),
                }
            )

        handle.visititems(visit)
        if "MOD/Splits" in handle:
            splits = handle["MOD/Splits"]
            for split_index in range(len(splits)):
                split = splits[split_index]
                raw_poles = _field_to_float_list(split, "p")
                decoded_poles = _decode_idem_split_poles(split)
                pole_blocks.append(
                    {
                        "split_index": split_index,
                        "order": int(split["order"]) if "order" in split.dtype.names else len(decoded_poles),
                        "real_pole_count": _int_field(split, "nr"),
                        "complex_pair_count": _int_field(split, "nc"),
                        "poles_rad_per_s": raw_poles,
                        "pole_frequencies_hz": [_pole_to_hz(pole) for pole in raw_poles],
                        "decoded_poles_rad_per_s": _complex_array_to_jsonable(decoded_poles),
                        "decoded_pole_frequencies_hz": [_pole_to_hz(pole) for pole in decoded_poles],
                        "rms_error": _float_field(split, "err"),
                        "max_error": _float_field(split, "maxErr"),
                    }
                )

    return {
        "datasets": datasets,
        "pole_blocks": pole_blocks,
        "order": max((block["order"] for block in pole_blocks), default=None),
        "total_pole_count": sum(len(block["decoded_poles_rad_per_s"]) for block in pole_blocks),
        "error_history": _array_to_jsonable(error_history),
        "orders_history": _array_to_jsonable(orders_history),
        "fitting_options_xml": fitting_options_xml,
        "is_passive": is_passive,
    }


def run_idem_fixed_pole_residue_probe(
    touchstone_path: Path,
    model_path: Path,
    *,
    parameter_type: str = "s",
    basis: str = "complex",
    relative_weight_power: float = 0.0,
    fit_max_frequency_points: int | None = None,
    rcond: float | None = None,
) -> dict[str, Any]:
    if basis not in {"complex", "idem-real"}:
        raise ValueError("basis must be 'complex' or 'idem-real'")
    model = inspect_idem_model(model_path)
    pole_blocks = model.get("pole_blocks") or []
    if not pole_blocks:
        raise ValueError(f"No IdEM pole blocks found in {model_path}")
    if len(pole_blocks) > 1:
        raise ValueError("Fixed-pole residue probe currently supports one IdEM split")
    pole_block = pole_blocks[0]
    if basis == "idem-real":
        result = fit_touchstone_with_idem_real_basis(
            touchstone_path,
            pole_block,
            parameter_type=parameter_type,
            relative_weight_power=relative_weight_power,
            fit_max_frequency_points=fit_max_frequency_points,
            rcond=rcond,
        )
    else:
        poles = _jsonable_to_complex_array(pole_block["decoded_poles_rad_per_s"])
        result = fit_touchstone_with_fixed_poles(
            touchstone_path,
            poles,
            parameter_type=parameter_type,
            relative_weight_power=relative_weight_power,
            fit_max_frequency_points=fit_max_frequency_points,
            rcond=rcond,
        )
    result.update(
        {
            "probe": "idem_fixed_pole_residue",
            "touchstone_path": str(touchstone_path),
            "model_path": str(model_path),
            "basis": basis,
            "idem_model": {
                "order": model.get("order"),
                "total_pole_count": model.get("total_pole_count"),
                "error_history": model.get("error_history"),
                "orders_history": model.get("orders_history"),
                "split_rms_error": pole_blocks[0].get("rms_error"),
                "split_max_error": pole_blocks[0].get("max_error"),
            },
        }
    )
    return result


def run_idem_residue_sweep(
    touchstone_path: Path,
    model_paths: list[Path],
    *,
    parameter_types: list[str],
    bases: list[str],
    relative_weight_powers: list[float],
    fit_max_frequency_points: int | None = None,
    rcond: float | None = None,
) -> list[dict[str, Any]]:
    if not model_paths:
        raise ValueError("model_paths must contain at least one model")
    results: list[dict[str, Any]] = []
    for model_path in model_paths:
        for basis in bases:
            for parameter_type in parameter_types:
                for relative_weight_power in relative_weight_powers:
                    result = run_idem_fixed_pole_residue_probe(
                        touchstone_path,
                        model_path,
                        parameter_type=parameter_type,
                        basis=basis,
                        relative_weight_power=relative_weight_power,
                        fit_max_frequency_points=fit_max_frequency_points,
                        rcond=rcond,
                    )
                    result["model_label"] = _model_label(model_path)
                    results.append(result)
    return sorted(results, key=lambda item: item["z_log_magnitude_rms_error"])


def run_local_pole_relocation_probe(
    touchstone_path: Path,
    *,
    order: int,
    iterations: int = 3,
    parameter_type: str = "s",
    pole_damping: float = 0.05,
    pole_spacing: str = "lin",
    pole_f_min: float | None = None,
    response_selection: str = "energy",
    adaptive_worst_pair_count: int = 16,
    residue_basis: str = "complex",
    fit_max_frequency_points: int | None = None,
    max_pole_responses: int | None = 64,
    relative_weight_power: float = 0.0,
    pole_pairing: str = "none",
    relocation_basis: str = "complex",
    relocation_normalization: str = "none",
    relocation_numerator: str = "complex",
    rcond: float | None = None,
) -> list[dict[str, Any]]:
    import skrf as rf

    if order < 1:
        raise ValueError("order must be >= 1")
    if iterations < 0:
        raise ValueError("iterations must be >= 0")
    if parameter_type not in {"s", "z"}:
        raise ValueError("parameter_type must be 's' or 'z'")
    if pole_pairing not in {"none", "conjugate"}:
        raise ValueError("pole_pairing must be 'none' or 'conjugate'")
    if relocation_basis not in {"complex", "real-state"}:
        raise ValueError("relocation_basis must be 'complex' or 'real-state'")

    network = rf.Network(str(touchstone_path))
    fit_indices = _fit_indices(len(network.f), fit_max_frequency_points)
    samples = np.asarray(network.s if parameter_type == "s" else network.z, dtype=complex)
    poles = initial_common_poles(network.f, order, damping=pole_damping, spacing=pole_spacing, f_min=pole_f_min)
    initial_selection = "energy" if response_selection == "adaptive-z" else response_selection
    selected = _select_pole_response_indices(samples, max_pole_responses, mode=initial_selection)
    step = PoleRelocationStep(
        iteration=0,
        poles_rad_per_s=poles,
        denominator_residues=None,
        selected_response_indices=selected,
        rank=None,
        condition_number=None,
    )
    results: list[dict[str, Any]] = []
    for iteration in range(iterations + 1):
        if iteration > 0:
            step = relocate_common_poles(
                network.f,
                samples,
                step.poles_rad_per_s,
                iteration=iteration,
                fit_indices=fit_indices,
                max_responses=max_pole_responses,
                response_selection=response_selection,
                response_indices=selected,
                relative_weight_power=relative_weight_power,
                pole_pairing=pole_pairing,
                relocation_basis=relocation_basis,
                relocation_normalization=relocation_normalization,
                relocation_numerator=relocation_numerator,
                rcond=rcond,
            )
        evaluation = _evaluate_network_with_fixed_poles(
            network,
            step.poles_rad_per_s,
            parameter_type=parameter_type,
            residue_basis=residue_basis,
            relative_weight_power=0.0,
            fit_indices=fit_indices,
            rcond=rcond,
        )
        results.append(
            _pole_relocation_result_dict(
                touchstone_path,
                order,
                parameter_type,
                pole_damping,
                pole_spacing,
                pole_f_min,
                response_selection,
                relative_weight_power,
                pole_pairing,
                relocation_basis,
                relocation_normalization,
                relocation_numerator,
                fit_indices,
                step,
                evaluation,
            )
        )
        if response_selection == "adaptive-z":
            selected = _select_adaptive_z_response_indices(
                samples,
                evaluation["original_z"],
                evaluation["fitted_z"],
                max_pole_responses,
                worst_pair_count=adaptive_worst_pair_count,
            )
    return results


def run_local_pole_relocation_sweep(
    touchstone_path: Path,
    *,
    order: int,
    iterations: int,
    parameter_type: str,
    response_selections: list[str],
    max_pole_responses_values: list[int],
    relative_weight_powers: list[float],
    pole_damping: float = 0.05,
    pole_spacing: str = "lin",
    pole_f_min: float | None = None,
    adaptive_worst_pair_count: int = 16,
    residue_bases: list[str] | None = None,
    fit_max_frequency_points: int | None = None,
    pole_pairings: list[str] | None = None,
    relocation_bases: list[str] | None = None,
    relocation_normalizations: list[str] | None = None,
    relocation_numerators: list[str] | None = None,
    rcond: float | None = None,
) -> list[dict[str, Any]]:
    if not response_selections:
        raise ValueError("response_selections must contain at least one value")
    if not max_pole_responses_values:
        raise ValueError("max_pole_responses_values must contain at least one value")
    if not relative_weight_powers:
        raise ValueError("relative_weight_powers must contain at least one value")
    if residue_bases is None:
        residue_bases = ["complex"]
    if not residue_bases:
        raise ValueError("residue_bases must contain at least one value")
    if pole_pairings is None:
        pole_pairings = ["none"]
    if not pole_pairings:
        raise ValueError("pole_pairings must contain at least one value")
    if relocation_bases is None:
        relocation_bases = ["complex"]
    if not relocation_bases:
        raise ValueError("relocation_bases must contain at least one value")
    if relocation_normalizations is None:
        relocation_normalizations = ["none"]
    if not relocation_normalizations:
        raise ValueError("relocation_normalizations must contain at least one value")
    if relocation_numerators is None:
        relocation_numerators = ["complex"]
    if not relocation_numerators:
        raise ValueError("relocation_numerators must contain at least one value")
    results: list[dict[str, Any]] = []
    for selection in response_selections:
        for max_responses in max_pole_responses_values:
            for weight_power in relative_weight_powers:
                for residue_basis in residue_bases:
                    for pole_pairing in pole_pairings:
                        for relocation_basis in relocation_bases:
                            for relocation_normalization in relocation_normalizations:
                                for relocation_numerator in relocation_numerators:
                                    trial = run_local_pole_relocation_probe(
                                        touchstone_path,
                                        order=order,
                                        iterations=iterations,
                                        parameter_type=parameter_type,
                                        pole_damping=pole_damping,
                                        pole_spacing=pole_spacing,
                                        pole_f_min=pole_f_min,
                                        response_selection=selection,
                                        adaptive_worst_pair_count=adaptive_worst_pair_count,
                                        residue_basis=residue_basis,
                                        fit_max_frequency_points=fit_max_frequency_points,
                                        max_pole_responses=max_responses,
                                        relative_weight_power=weight_power,
                                        pole_pairing=pole_pairing,
                                        relocation_basis=relocation_basis,
                                        relocation_normalization=relocation_normalization,
                                        relocation_numerator=relocation_numerator,
                                        rcond=rcond,
                                    )
                                    for row in trial:
                                        row["sweep_label"] = (
                                            f"{selection}_n{max_responses}_w{weight_power:g}_"
                                            f"{residue_basis}_{pole_pairing}_{relocation_basis}_"
                                            f"{relocation_normalization}_{relocation_numerator}"
                                        )
                                        results.append(row)
    return sorted(results, key=lambda item: item["z_log_magnitude_rms_error"])


def run_local_idem_like_fit(
    touchstone_path: Path,
    *,
    order: int = 32,
    iterations: int = 4,
    parameter_type: str = "s",
    pole_damping: float = 0.05,
    pole_spacing: str = "lin",
    pole_f_min: float | None = None,
    response_selection: str = "energy",
    adaptive_worst_pair_count: int = 16,
    residue_basis: str = "real-state",
    fit_max_frequency_points: int | None = 256,
    max_pole_responses: int | None = 64,
    relative_weight_power: float = 0.0,
    pole_pairing: str = "none",
    relocation_basis: str = "complex",
    relocation_normalization: str = "none",
    relocation_numerator: str = "complex",
    rcond: float | None = None,
    selection_metric: str = "z_log_magnitude_rms_error",
    model_output_path: Path | None = None,
) -> dict[str, Any]:
    valid_metrics = {
        "z_log_magnitude_rms_error",
        "diagonal_z_log_magnitude_rms_error",
        "s_mean_rms_error",
        "s_relative_rms_error",
    }
    if selection_metric not in valid_metrics:
        raise ValueError(f"selection_metric must be one of: {', '.join(sorted(valid_metrics))}")
    iterations_result = run_local_pole_relocation_probe(
        touchstone_path,
        order=order,
        iterations=iterations,
        parameter_type=parameter_type,
        pole_damping=pole_damping,
        pole_spacing=pole_spacing,
        pole_f_min=pole_f_min,
        response_selection=response_selection,
        adaptive_worst_pair_count=adaptive_worst_pair_count,
        residue_basis=residue_basis,
        fit_max_frequency_points=fit_max_frequency_points,
        max_pole_responses=max_pole_responses,
        relative_weight_power=relative_weight_power,
        pole_pairing=pole_pairing,
        relocation_basis=relocation_basis,
        relocation_normalization=relocation_normalization,
        relocation_numerator=relocation_numerator,
        rcond=rcond,
    )
    _ensure_s_mean_rms_metrics(iterations_result)
    best = min(iterations_result, key=lambda item: item.get(selection_metric, math.inf))
    if model_output_path is not None:
        save_local_idem_like_model(
            touchstone_path,
            best,
            model_output_path,
            parameter_type=parameter_type,
            residue_basis=residue_basis,
            fit_max_frequency_points=fit_max_frequency_points,
            rcond=rcond,
        )
    return {
        "probe": "local_idem_like_fit",
        "touchstone_path": str(touchstone_path),
        "selection_metric": selection_metric,
        "recipe": {
            "order": order,
            "iterations": iterations,
            "parameter_type": parameter_type,
            "pole_damping": pole_damping,
            "pole_spacing": pole_spacing,
            "pole_f_min": pole_f_min,
            "response_selection": response_selection,
            "adaptive_worst_pair_count": adaptive_worst_pair_count,
            "residue_basis": residue_basis,
            "fit_max_frequency_points": fit_max_frequency_points,
            "max_pole_responses": max_pole_responses,
            "relative_weight_power": relative_weight_power,
            "pole_pairing": pole_pairing,
            "relocation_basis": relocation_basis,
            "relocation_normalization": relocation_normalization,
            "relocation_numerator": relocation_numerator,
            "rcond": rcond,
            "model_output_path": str(model_output_path) if model_output_path is not None else None,
        },
        "best": best,
        "iterations": iterations_result,
    }


def _ensure_s_mean_rms_metrics(results: list[dict[str, Any]]) -> None:
    for result in results:
        if result.get("s_mean_rms_error") is not None:
            continue
        s_rms = result.get("s_rms_error")
        ports = result.get("ports")
        if ports is None:
            response_count = len(result.get("selected_response_indices", ()))
            root = int(round(math.sqrt(response_count)))
            ports = root if root * root == response_count else None
        if isinstance(s_rms, (int, float)) and isinstance(ports, int | float) and ports:
            result["s_mean_rms_error"] = float(s_rms) / float(ports)


def save_local_idem_like_model(
    touchstone_path: Path,
    fit_iteration: dict[str, Any],
    output_path: Path,
    *,
    parameter_type: str,
    residue_basis: str,
    fit_max_frequency_points: int | None = None,
    rcond: float | None = None,
) -> None:
    import skrf as rf

    network = rf.Network(str(touchstone_path))
    fit_indices = _fit_indices(len(network.f), fit_max_frequency_points)
    poles = _jsonable_to_complex_array(fit_iteration["poles_rad_per_s"])
    model = _fit_network_model_coefficients(
        network,
        poles,
        parameter_type=parameter_type,
        residue_basis=residue_basis,
        fit_indices=fit_indices,
        rcond=rcond,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_local_idem_like_model_data(
        output_path,
        parameter_type=parameter_type,
        residue_basis=residue_basis,
        poles=poles,
        coefficients=np.asarray(model["coefficients"]),
        pole_block_raw=model["pole_block_raw"],
        pole_block_real_count=model["pole_block_real_count"],
        pole_block_complex_pair_count=model["pole_block_complex_pair_count"],
        frequencies_hz=np.asarray(network.f, dtype=float),
        z0=np.asarray(network.z0, dtype=complex),
    )


def _save_local_idem_like_model_data(
    output_path: Path,
    *,
    parameter_type: str,
    residue_basis: str,
    poles: Any,
    coefficients: Any,
    pole_block_raw: Any,
    pole_block_real_count: int,
    pole_block_complex_pair_count: int,
    frequencies_hz: Any,
    z0: Any,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        schema_version=np.array([1], dtype=np.int64),
        parameter_type=np.array(parameter_type),
        residue_basis=np.array(residue_basis),
        poles_rad_per_s=np.asarray(poles, dtype=complex),
        frequencies_hz=np.asarray(frequencies_hz, dtype=float),
        z0=np.asarray(z0, dtype=complex),
        coefficients=np.asarray(coefficients),
        pole_block_raw=np.asarray(pole_block_raw, dtype=float),
        pole_block_real_count=np.array([pole_block_real_count], dtype=np.int64),
        pole_block_complex_pair_count=np.array([pole_block_complex_pair_count], dtype=np.int64),
    )


def evaluate_local_idem_like_model(model_path: Path, touchstone_path: Path) -> dict[str, Any]:
    import skrf as rf

    network = rf.Network(str(touchstone_path))
    with np.load(model_path, allow_pickle=False) as data:
        parameter_type = str(data["parameter_type"].item())
        residue_basis = str(data["residue_basis"].item())
        poles = np.asarray(data["poles_rad_per_s"], dtype=complex)
        coefficients = np.asarray(data["coefficients"])
        pole_block = {
            "poles_rad_per_s": np.asarray(data["pole_block_raw"], dtype=float).tolist(),
            "real_pole_count": int(np.asarray(data["pole_block_real_count"])[0]),
            "complex_pair_count": int(np.asarray(data["pole_block_complex_pair_count"])[0]),
            "decoded_poles_rad_per_s": _complex_array_to_jsonable(poles),
        }
    fitted_target = evaluate_model_matrix(network.f, poles, coefficients, residue_basis=residue_basis, pole_block=pole_block)
    original_s = np.asarray(network.s, dtype=complex)
    original_z = np.asarray(network.z, dtype=complex)
    if parameter_type == "s":
        fitted_s = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, s=fitted_s, z0=network.z0)
        fitted_z = np.asarray(fitted_network.z, dtype=complex)
    elif parameter_type == "z":
        fitted_z = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, z=fitted_z, z0=network.z0)
        fitted_s = np.asarray(fitted_network.s, dtype=complex)
    else:
        raise ValueError(f"Unsupported model parameter_type: {parameter_type}")
    return {
        "probe": "local_idem_like_model_eval",
        "model_path": str(model_path),
        "touchstone_path": str(touchstone_path),
        "parameter_type": parameter_type,
        "basis": residue_basis,
        "ports": int(network.nports),
        "frequency_points": int(len(network.f)),
        "pole_count": int(len(poles)),
        "basis_term_count": int(coefficients.shape[0]),
        "s_rms_error": _s_rms_error(original_s, fitted_s),
        "s_mean_rms_error": _s_mean_rms_error(original_s, fitted_s),
        "s_relative_rms_error": _relative_rms_error(original_s, fitted_s),
        "z_log_magnitude_rms_error": _z_log_magnitude_rms_error(original_z, fitted_z),
        "diagonal_z_log_magnitude_rms_error": _z_log_magnitude_rms_error(
            np.diagonal(original_z, axis1=1, axis2=2),
            np.diagonal(fitted_z, axis1=1, axis2=2),
        ),
        "max_abs_z_error_ohm": float(np.max(np.abs(original_z - fitted_z))),
    }


def refine_local_idem_like_model(
    model_path: Path,
    touchstone_path: Path,
    output_path: Path,
    *,
    iterations: int = 1,
    candidate_pair_count: int = 6,
    relative_step: float = 0.02,
    fit_max_frequency_points: int | None = 128,
    selection_metric: str = "z_log_magnitude_rms_error",
    rcond: float | None = None,
) -> dict[str, Any]:
    import skrf as rf

    if iterations < 0:
        raise ValueError("iterations must be >= 0")
    if candidate_pair_count < 1:
        raise ValueError("candidate_pair_count must be >= 1")
    if relative_step <= 0.0:
        raise ValueError("relative_step must be > 0")
    valid_metrics = {
        "z_log_magnitude_rms_error",
        "diagonal_z_log_magnitude_rms_error",
        "s_mean_rms_error",
        "s_relative_rms_error",
    }
    if selection_metric not in valid_metrics:
        raise ValueError(f"selection_metric must be one of: {', '.join(sorted(valid_metrics))}")

    network = rf.Network(str(touchstone_path))
    model = _load_local_idem_like_model(model_path)
    parameter_type = str(model["parameter_type"])
    residue_basis = str(model["residue_basis"])
    if parameter_type not in {"s", "z"}:
        raise ValueError(f"Unsupported model parameter_type: {parameter_type}")
    fit_indices = _fit_indices(len(network.f), fit_max_frequency_points)

    current_poles = np.asarray(model["poles"], dtype=complex)
    current_coefficients = np.asarray(model["coefficients"])
    current_pole_block = model["pole_block"]
    current_metrics = _evaluate_model_against_network(
        network,
        current_poles,
        current_coefficients,
        parameter_type=parameter_type,
        residue_basis=residue_basis,
        pole_block=current_pole_block,
    )
    initial_metrics = dict(current_metrics)
    history = [
        {
            "iteration": 0,
            "accepted": True,
            "source": "input_model",
            **current_metrics,
        }
    ]

    best_fit_payload = {
        "coefficients": current_coefficients,
        "pole_block_raw": current_pole_block["poles_rad_per_s"],
        "pole_block_real_count": int(current_pole_block["real_pole_count"]),
        "pole_block_complex_pair_count": int(current_pole_block["complex_pair_count"]),
        "condition_number": None,
        "rank": None,
    }

    for iteration in range(1, iterations + 1):
        candidates = _joint_refinement_candidate_poles(
            current_poles,
            current_coefficients,
            residue_basis=residue_basis,
            candidate_pair_count=candidate_pair_count,
            relative_step=relative_step,
        )
        best_trial: dict[str, Any] | None = None
        for label, candidate_poles in candidates:
            fit_payload = _fit_network_model_coefficients(
                network,
                candidate_poles,
                parameter_type=parameter_type,
                residue_basis=residue_basis,
                fit_indices=fit_indices,
                rcond=rcond,
            )
            pole_block = {
                "poles_rad_per_s": fit_payload["pole_block_raw"],
                "real_pole_count": fit_payload["pole_block_real_count"],
                "complex_pair_count": fit_payload["pole_block_complex_pair_count"],
                "decoded_poles_rad_per_s": _complex_array_to_jsonable(candidate_poles),
            }
            metrics = _evaluate_model_against_network(
                network,
                candidate_poles,
                fit_payload["coefficients"],
                parameter_type=parameter_type,
                residue_basis=residue_basis,
                pole_block=pole_block,
            )
            trial = {
                "label": label,
                "poles": candidate_poles,
                "fit_payload": fit_payload,
                "pole_block": pole_block,
                **metrics,
                "condition_number": fit_payload["fit_result"]["condition_number"],
                "rank": fit_payload["fit_result"]["rank"],
            }
            if best_trial is None or _joint_refinement_trial_key(trial, selection_metric) < _joint_refinement_trial_key(
                best_trial,
                selection_metric,
            ):
                best_trial = trial

        if best_trial is None:
            history.append({"iteration": iteration, "accepted": False, "reason": "no_candidates", **current_metrics})
            break
        accepted = _joint_refinement_trial_key(best_trial, selection_metric) < _joint_refinement_trial_key(
            current_metrics,
            selection_metric,
        )
        history.append(
            {
                "iteration": iteration,
                "accepted": bool(accepted),
                "candidate_label": best_trial["label"],
                "candidate_count": len(candidates),
                "condition_number": best_trial["condition_number"],
                "rank": best_trial["rank"],
                **{key: best_trial[key] for key in _MODEL_METRIC_KEYS},
            }
        )
        if not accepted:
            break
        current_poles = np.asarray(best_trial["poles"], dtype=complex)
        current_coefficients = np.asarray(best_trial["fit_payload"]["coefficients"])
        current_pole_block = best_trial["pole_block"]
        current_metrics = {key: best_trial[key] for key in _MODEL_METRIC_KEYS}
        best_fit_payload = {
            "coefficients": current_coefficients,
            "pole_block_raw": current_pole_block["poles_rad_per_s"],
            "pole_block_real_count": int(current_pole_block["real_pole_count"]),
            "pole_block_complex_pair_count": int(current_pole_block["complex_pair_count"]),
            "condition_number": best_trial["condition_number"],
            "rank": best_trial["rank"],
        }

    _save_local_idem_like_model_data(
        output_path,
        parameter_type=parameter_type,
        residue_basis=residue_basis,
        poles=current_poles,
        coefficients=current_coefficients,
        pole_block_raw=best_fit_payload["pole_block_raw"],
        pole_block_real_count=best_fit_payload["pole_block_real_count"],
        pole_block_complex_pair_count=best_fit_payload["pole_block_complex_pair_count"],
        frequencies_hz=np.asarray(network.f, dtype=float),
        z0=np.asarray(network.z0, dtype=complex),
    )
    return {
        "probe": "local_idem_like_joint_refine",
        "model_path": str(model_path),
        "touchstone_path": str(touchstone_path),
        "output_path": str(output_path),
        "parameter_type": parameter_type,
        "basis": residue_basis,
        "selection_metric": selection_metric,
        "recipe": {
            "iterations": iterations,
            "candidate_pair_count": candidate_pair_count,
            "relative_step": relative_step,
            "fit_max_frequency_points": fit_max_frequency_points,
            "rcond": rcond,
        },
        "initial": initial_metrics,
        "best": current_metrics,
        "history": history,
    }


def export_local_idem_like_touchstone(
    model_path: Path,
    output_path: Path,
    *,
    reference_touchstone_path: Path,
) -> dict[str, Any]:
    import skrf as rf

    reference = rf.Network(str(reference_touchstone_path))
    fitted_s = _evaluate_model_s_parameters(model_path, reference)
    fitted_network = rf.Network(frequency=reference.frequency, s=fitted_s, z0=reference.z0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fitted_network.write_touchstone(str(output_path.with_suffix("")))
    actual_path = _touchstone_output_path(output_path, reference.nports)
    return {
        "probe": "local_idem_like_touchstone_export",
        "model_path": str(model_path),
        "reference_touchstone_path": str(reference_touchstone_path),
        "output_path": str(actual_path),
        "ports": int(reference.nports),
        "frequency_points": int(len(reference.f)),
        "frequency_range_hz": [float(reference.f[0]), float(reference.f[-1])] if len(reference.f) else None,
    }


def export_local_idem_like_state_space(model_path: Path, output_path: Path) -> dict[str, Any]:
    model = _load_local_idem_like_model(model_path)
    state_space = state_space_from_model_data(model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        schema_version=np.array([1], dtype=np.int64),
        parameter_type=np.array(model["parameter_type"]),
        residue_basis=np.array(model["residue_basis"]),
        poles_rad_per_s=model["poles"],
        A=state_space["A"],
        B=state_space["B"],
        C=state_space["C"],
        D=state_space["D"],
        z0=model["z0"],
    )
    return {
        "probe": "local_idem_like_state_space_export",
        "model_path": str(model_path),
        "output_path": str(output_path),
        "parameter_type": model["parameter_type"],
        "basis": model["residue_basis"],
        "ports": int(state_space["D"].shape[0]),
        "states": int(state_space["A"].shape[0]),
        "pole_count": int(len(model["poles"])),
    }


def evaluate_local_idem_like_state_space(state_space_path: Path, touchstone_path: Path) -> dict[str, Any]:
    import skrf as rf

    network = rf.Network(str(touchstone_path))
    with np.load(state_space_path, allow_pickle=False) as data:
        parameter_type = str(data["parameter_type"].item())
        residue_basis = str(data["residue_basis"].item())
        A = np.asarray(data["A"])
        B = np.asarray(data["B"])
        C = np.asarray(data["C"])
        D = np.asarray(data["D"])
        poles = np.asarray(data["poles_rad_per_s"], dtype=complex)
    fitted_target = evaluate_state_space_matrix(network.f, A, B, C, D)
    original_s = np.asarray(network.s, dtype=complex)
    original_z = np.asarray(network.z, dtype=complex)
    if parameter_type == "s":
        fitted_s = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, s=fitted_s, z0=network.z0)
        fitted_z = np.asarray(fitted_network.z, dtype=complex)
    elif parameter_type == "z":
        fitted_z = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, z=fitted_z, z0=network.z0)
        fitted_s = np.asarray(fitted_network.s, dtype=complex)
    else:
        raise ValueError(f"Unsupported state-space parameter_type: {parameter_type}")
    return {
        "probe": "local_idem_like_state_space_eval",
        "state_space_path": str(state_space_path),
        "touchstone_path": str(touchstone_path),
        "parameter_type": parameter_type,
        "basis": residue_basis,
        "ports": int(network.nports),
        "states": int(A.shape[0]),
        "pole_count": int(len(poles)),
        "s_rms_error": _s_rms_error(original_s, fitted_s),
        "s_mean_rms_error": _s_mean_rms_error(original_s, fitted_s),
        "s_relative_rms_error": _relative_rms_error(original_s, fitted_s),
        "z_log_magnitude_rms_error": _z_log_magnitude_rms_error(original_z, fitted_z),
        "diagonal_z_log_magnitude_rms_error": _z_log_magnitude_rms_error(
            np.diagonal(original_z, axis1=1, axis2=2),
            np.diagonal(fitted_z, axis1=1, axis2=2),
        ),
        "max_abs_z_error_ohm": float(np.max(np.abs(original_z - fitted_z))),
    }


def state_space_from_model_data(model: dict[str, Any]) -> dict[str, np.ndarray]:
    poles = np.asarray(model["poles"], dtype=complex)
    coefficients = np.asarray(model["coefficients"])
    residue_basis = str(model["residue_basis"])
    pole_block = model["pole_block"]
    response_count = coefficients.shape[1]
    nports = int(round(math.sqrt(response_count)))
    if nports * nports != response_count:
        raise ValueError("coefficient response count must be a square port matrix")
    if residue_basis == "complex":
        return _complex_basis_state_space(poles, coefficients, nports)
    if residue_basis == "real-state":
        return _real_state_basis_state_space(pole_block, coefficients, nports)
    raise ValueError("residue_basis must be 'complex' or 'real-state'")


def evaluate_state_space_matrix(freqs_hz: Any, A: Any, B: Any, C: Any, D: Any) -> np.ndarray:
    freqs = np.asarray(freqs_hz, dtype=float)
    a = np.asarray(A)
    b = np.asarray(B)
    c = np.asarray(C)
    d = np.asarray(D)
    nports = d.shape[0]
    if _is_port_block_state_space(a, b, nports):
        return _evaluate_port_block_state_space(freqs, a, b, c, d)
    identity = np.eye(a.shape[0], dtype=complex)
    fitted = np.empty((len(freqs), nports, nports), dtype=complex)
    for index, frequency in enumerate(freqs):
        s_value = 2j * math.pi * float(frequency)
        fitted[index] = d + c @ np.linalg.solve(s_value * identity - a, b)
    return fitted


def _is_port_block_state_space(a: np.ndarray, b: np.ndarray, nports: int) -> bool:
    if nports < 1 or a.ndim != 2 or b.ndim != 2 or a.shape[0] != a.shape[1] or b.shape[1] != nports:
        return False
    states = a.shape[0]
    if states == 0 or states % nports != 0:
        return False
    states_per_port = states // nports
    for port in range(nports):
        start = port * states_per_port
        end = start + states_per_port
        if np.any(np.abs(b[:start, port]) > 0.0) or np.any(np.abs(b[end:, port]) > 0.0):
            return False
        if np.any(np.abs(a[start:end, :start]) > 0.0) or np.any(np.abs(a[start:end, end:]) > 0.0):
            return False
    return True


def _evaluate_port_block_state_space(
    freqs: np.ndarray,
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    d: np.ndarray,
) -> np.ndarray:
    nports = d.shape[0]
    states_per_port = a.shape[0] // nports
    fitted = np.empty((len(freqs), nports, nports), dtype=complex)
    identity = np.eye(states_per_port, dtype=complex)
    for freq_index, frequency in enumerate(freqs):
        s_value = 2j * math.pi * float(frequency)
        response = d.astype(complex).copy()
        for input_port in range(nports):
            start = input_port * states_per_port
            end = start + states_per_port
            x = np.linalg.solve(s_value * identity - a[start:end, start:end], b[start:end, input_port])
            response[:, input_port] += c[:, start:end] @ x
        fitted[freq_index] = response
    return fitted


def _evaluate_model_s_parameters(model_path: Path, reference: Any) -> np.ndarray:
    import skrf as rf

    model = _load_local_idem_like_model(model_path)
    parameter_type = model["parameter_type"]
    poles = model["poles"]
    coefficients = model["coefficients"]
    residue_basis = model["residue_basis"]
    pole_block = model["pole_block"]
    fitted_target = evaluate_model_matrix(reference.f, poles, coefficients, residue_basis=residue_basis, pole_block=pole_block)
    if parameter_type == "s":
        return fitted_target
    if parameter_type == "z":
        fitted_network = rf.Network(frequency=reference.frequency, z=fitted_target, z0=reference.z0)
        return np.asarray(fitted_network.s, dtype=complex)
    raise ValueError(f"Unsupported model parameter_type: {parameter_type}")


def _load_local_idem_like_model(model_path: Path) -> dict[str, Any]:
    with np.load(model_path, allow_pickle=False) as data:
        parameter_type = str(data["parameter_type"].item())
        residue_basis = str(data["residue_basis"].item())
        poles = np.asarray(data["poles_rad_per_s"], dtype=complex)
        pole_block = {
            "poles_rad_per_s": np.asarray(data["pole_block_raw"], dtype=float).tolist(),
            "real_pole_count": int(np.asarray(data["pole_block_real_count"])[0]),
            "complex_pair_count": int(np.asarray(data["pole_block_complex_pair_count"])[0]),
            "decoded_poles_rad_per_s": _complex_array_to_jsonable(poles),
        }
        return {
            "parameter_type": parameter_type,
            "residue_basis": residue_basis,
            "poles": poles,
            "coefficients": np.asarray(data["coefficients"]),
            "z0": np.asarray(data["z0"], dtype=complex),
            "pole_block": pole_block,
        }


def _complex_basis_state_space(poles: np.ndarray, coefficients: np.ndarray, nports: int) -> dict[str, np.ndarray]:
    dynamic_terms = len(poles)
    states = nports * dynamic_terms
    dtype = np.result_type(poles, coefficients, complex)
    a = np.zeros((states, states), dtype=dtype)
    b = np.zeros((states, nports), dtype=dtype)
    c = np.zeros((nports, states), dtype=dtype)
    d = coefficients[-1, :].reshape(nports, nports).astype(dtype)
    for input_port in range(nports):
        state_offset = input_port * dynamic_terms
        for term_index, pole in enumerate(poles):
            state_index = state_offset + term_index
            a[state_index, state_index] = pole
            b[state_index, input_port] = 1.0
            for output_port in range(nports):
                response_index = output_port * nports + input_port
                c[output_port, state_index] = coefficients[term_index, response_index]
    return {"A": a, "B": b, "C": c, "D": d}


def _real_state_basis_state_space(
    pole_block: dict[str, Any],
    coefficients: np.ndarray,
    nports: int,
) -> dict[str, np.ndarray]:
    raw = np.asarray(pole_block["poles_rad_per_s"], dtype=float)
    real_count = int(pole_block.get("real_pole_count") or 0)
    pair_count = int(pole_block.get("complex_pair_count") or 0)
    states_per_input = real_count + 2 * pair_count
    states = nports * states_per_input
    a = np.zeros((states, states), dtype=float)
    b = np.zeros((states, nports), dtype=float)
    c = np.zeros((nports, states), dtype=float)
    d = coefficients[-1, :].reshape(nports, nports).astype(float)
    for input_port in range(nports):
        state_offset = input_port * states_per_input
        basis_index = 0
        local_state = 0
        for real_pole in raw[:real_count]:
            state_index = state_offset + local_state
            a[state_index, state_index] = float(real_pole)
            b[state_index, input_port] = 1.0
            for output_port in range(nports):
                response_index = output_port * nports + input_port
                c[output_port, state_index] = float(coefficients[basis_index, response_index])
            basis_index += 1
            local_state += 1
        offset = real_count
        for pair_index in range(pair_count):
            pair_offset = offset + 2 * pair_index
            sigma = float(raw[pair_offset])
            omega = abs(float(raw[pair_offset + 1]))
            state_1 = state_offset + local_state
            state_2 = state_offset + local_state + 1
            a[state_1, state_1] = sigma
            a[state_1, state_2] = omega
            a[state_2, state_1] = -omega
            a[state_2, state_2] = sigma
            b[state_1, input_port] = 1.0
            for output_port in range(nports):
                response_index = output_port * nports + input_port
                coeff_sum = float(coefficients[basis_index, response_index])
                coeff_diff = float(coefficients[basis_index + 1, response_index])
                c[output_port, state_1] = 2.0 * coeff_sum
                c[output_port, state_2] = 2.0 * coeff_diff
            basis_index += 2
            local_state += 2
    return {"A": a, "B": b, "C": c, "D": d}


def _touchstone_output_path(output_path: Path, nports: int) -> Path:
    expected_suffix = f".s{nports}p"
    if output_path.suffix.lower() == expected_suffix:
        return output_path
    return output_path.with_suffix(expected_suffix)


def evaluate_model_matrix(
    freqs_hz: Any,
    poles_rad_per_s: Any,
    coefficients: Any,
    *,
    residue_basis: str,
    pole_block: dict[str, Any] | None = None,
) -> np.ndarray:
    freqs = np.asarray(freqs_hz, dtype=float)
    coeffs = np.asarray(coefficients)
    if coeffs.ndim != 2:
        raise ValueError("coefficients must have shape (basis_terms, responses)")
    response_count = coeffs.shape[1]
    nports = int(round(math.sqrt(response_count)))
    if nports * nports != response_count:
        raise ValueError("coefficient response count must be a square port matrix")
    if residue_basis == "complex":
        design = _fixed_pole_design_matrix(freqs, np.asarray(poles_rad_per_s, dtype=complex))
    elif residue_basis == "real-state":
        if pole_block is None:
            pole_block = _pole_block_from_complex_poles(poles_rad_per_s)
        design = _idem_real_basis_design_matrix(freqs, pole_block)
    else:
        raise ValueError("residue_basis must be 'complex' or 'real-state'")
    if design.shape[1] != coeffs.shape[0]:
        raise ValueError("coefficient basis term count does not match model basis")
    return (design @ coeffs).reshape((len(freqs), nports, nports))


_MODEL_METRIC_KEYS = (
    "s_rms_error",
    "s_mean_rms_error",
    "s_relative_rms_error",
    "z_log_magnitude_rms_error",
    "diagonal_z_log_magnitude_rms_error",
    "max_abs_z_error_ohm",
)


def _evaluate_model_against_network(
    network: Any,
    poles: Any,
    coefficients: Any,
    *,
    parameter_type: str,
    residue_basis: str,
    pole_block: dict[str, Any],
) -> dict[str, float]:
    import skrf as rf

    fitted_target = evaluate_model_matrix(
        network.f,
        poles,
        coefficients,
        residue_basis=residue_basis,
        pole_block=pole_block,
    )
    original_s = np.asarray(network.s, dtype=complex)
    original_z = np.asarray(network.z, dtype=complex)
    if parameter_type == "s":
        fitted_s = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, s=fitted_s, z0=network.z0)
        fitted_z = np.asarray(fitted_network.z, dtype=complex)
    elif parameter_type == "z":
        fitted_z = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, z=fitted_z, z0=network.z0)
        fitted_s = np.asarray(fitted_network.s, dtype=complex)
    else:
        raise ValueError(f"Unsupported model parameter_type: {parameter_type}")
    return {
        "s_rms_error": _s_rms_error(original_s, fitted_s),
        "s_mean_rms_error": _s_mean_rms_error(original_s, fitted_s),
        "s_relative_rms_error": _relative_rms_error(original_s, fitted_s),
        "z_log_magnitude_rms_error": _z_log_magnitude_rms_error(original_z, fitted_z),
        "diagonal_z_log_magnitude_rms_error": _z_log_magnitude_rms_error(
            np.diagonal(original_z, axis1=1, axis2=2),
            np.diagonal(fitted_z, axis1=1, axis2=2),
        ),
        "max_abs_z_error_ohm": float(np.max(np.abs(original_z - fitted_z))),
    }


def _joint_refinement_trial_key(metrics: dict[str, Any], selection_metric: str) -> tuple[float, float, float]:
    return (
        float(metrics.get(selection_metric, math.inf)),
        float(metrics.get("z_log_magnitude_rms_error", math.inf)),
        float(metrics.get("s_relative_rms_error", math.inf)),
    )


def _joint_refinement_candidate_poles(
    poles: np.ndarray,
    coefficients: np.ndarray,
    *,
    residue_basis: str,
    candidate_pair_count: int,
    relative_step: float,
) -> list[tuple[str, np.ndarray]]:
    pole_block = _pole_block_from_complex_poles(poles)
    raw = list(float(value) for value in pole_block["poles_rad_per_s"])
    real_count = int(pole_block["real_pole_count"])
    pair_count = int(pole_block["complex_pair_count"])
    if pair_count == 0:
        return []
    scores = _joint_refinement_pair_scores(coefficients, residue_basis, real_count, pair_count)
    ranked_pairs = sorted(range(pair_count), key=lambda index: scores[index], reverse=True)[:candidate_pair_count]
    candidates: list[tuple[str, np.ndarray]] = []
    for pair_index in ranked_pairs:
        offset = real_count + 2 * pair_index
        sigma = float(raw[offset])
        omega = abs(float(raw[offset + 1]))
        sigma_step = max(abs(sigma) * relative_step, omega * relative_step * 0.05, 1.0)
        omega_step = max(omega * relative_step, 1.0)
        for label, new_sigma, new_omega in (
            (f"p{pair_index}_sigma_more_damped", sigma - sigma_step, omega),
            (f"p{pair_index}_sigma_less_damped", min(sigma + sigma_step, -1.0), omega),
            (f"p{pair_index}_omega_up", sigma, omega + omega_step),
            (f"p{pair_index}_omega_down", sigma, max(omega - omega_step, 1.0)),
        ):
            trial_raw = list(raw)
            trial_raw[offset] = float(new_sigma)
            trial_raw[offset + 1] = float(new_omega)
            candidates.append((label, _decoded_poles_from_real_state_raw(trial_raw, real_count, pair_count)))
    return candidates


def _joint_refinement_pair_scores(
    coefficients: np.ndarray,
    residue_basis: str,
    real_count: int,
    pair_count: int,
) -> list[float]:
    coeffs = np.asarray(coefficients)
    scores: list[float] = []
    for pair_index in range(pair_count):
        if residue_basis == "real-state":
            start = real_count + 2 * pair_index
            pair_coeffs = coeffs[start : start + 2, :]
        else:
            start = real_count + 2 * pair_index
            pair_coeffs = coeffs[start : start + 2, :]
        scores.append(float(np.linalg.norm(pair_coeffs)))
    return scores


def _decoded_poles_from_real_state_raw(raw_values: list[float], real_count: int, pair_count: int) -> np.ndarray:
    decoded: list[complex] = [complex(float(value), 0.0) for value in raw_values[:real_count]]
    offset = real_count
    for pair_index in range(pair_count):
        pair_offset = offset + 2 * pair_index
        sigma = float(raw_values[pair_offset])
        omega = abs(float(raw_values[pair_offset + 1]))
        decoded.append(complex(sigma, omega))
        decoded.append(complex(sigma, -omega))
    return _sort_poles_by_frequency(np.asarray(decoded, dtype=complex))


def initial_common_poles(
    freqs_hz: Any,
    order: int,
    *,
    damping: float = 0.05,
    spacing: str = "lin",
    f_min: float | None = None,
) -> np.ndarray:
    if order < 1:
        raise ValueError("order must be >= 1")
    if damping <= 0.0:
        raise ValueError("damping must be > 0")
    frequencies = np.asarray(freqs_hz, dtype=float)
    positive = np.sort(frequencies[np.isfinite(frequencies) & (frequencies > 0.0)])
    if positive.size == 0:
        raise ValueError("freqs_hz must contain at least one positive finite frequency")
    if f_min is not None:
        if f_min <= 0.0:
            raise ValueError("f_min must be > 0")
        in_band = positive[positive >= f_min]
        f_min_value = float(in_band[0]) if in_band.size else float(f_min)
    else:
        f_min_value = float(positive[0])
    f_max = float(positive[-1])
    pair_count = order // 2
    poles: list[complex] = []
    if order % 2:
        poles.append(complex(-2.0 * math.pi * f_min_value * damping, 0.0))
    if pair_count:
        if spacing == "lin":
            centers = np.linspace(f_min_value, f_max, pair_count)
        elif spacing == "log":
            centers = np.geomspace(f_min_value, f_max, pair_count)
        else:
            raise ValueError("spacing must be 'lin' or 'log'")
        for frequency in centers:
            omega = 2.0 * math.pi * float(frequency)
            sigma = -damping * omega
            poles.append(complex(sigma, omega))
            poles.append(complex(sigma, -omega))
    return _sort_poles_by_frequency(np.asarray(poles[:order], dtype=complex))


def relocate_common_poles(
    freqs_hz: Any,
    values: Any,
    poles_rad_per_s: Any,
    *,
    iteration: int = 1,
    fit_indices: Any = None,
    max_responses: int | None = 64,
    response_selection: str = "energy",
    response_indices: tuple[int, ...] | None = None,
    relative_weight_power: float = 0.0,
    pole_pairing: str = "none",
    relocation_basis: str = "complex",
    relocation_normalization: str = "none",
    relocation_numerator: str = "complex",
    rcond: float | None = None,
) -> PoleRelocationStep:
    frequencies = np.asarray(freqs_hz, dtype=float)
    samples = np.asarray(values, dtype=complex)
    poles = np.asarray(poles_rad_per_s, dtype=complex)
    if samples.ndim != 3 or samples.shape[1] != samples.shape[2]:
        raise ValueError("values must have shape (frequency_points, nports, nports)")
    if len(frequencies) != samples.shape[0]:
        raise ValueError("freqs_hz length must match values")
    if poles.ndim != 1 or len(poles) == 0:
        raise ValueError("poles_rad_per_s must be a non-empty 1D array")
    if relative_weight_power < 0.0:
        raise ValueError("relative_weight_power must be >= 0")
    if pole_pairing not in {"none", "conjugate"}:
        raise ValueError("pole_pairing must be 'none' or 'conjugate'")
    if relocation_basis not in {"complex", "real-state"}:
        raise ValueError("relocation_basis must be 'complex' or 'real-state'")
    if relocation_normalization not in {"none", "frequency"}:
        raise ValueError("relocation_normalization must be 'none' or 'frequency'")
    if relocation_numerator not in {"complex", "real"}:
        raise ValueError("relocation_numerator must be 'complex' or 'real'")
    if relocation_basis == "complex" and relocation_numerator != "complex":
        raise ValueError("real relocation numerator requires relocation_basis='real-state'")
    indices = np.arange(len(frequencies), dtype=int) if fit_indices is None else np.asarray(fit_indices, dtype=int)
    if len(indices) < len(poles) + 1:
        raise ValueError("pole relocation needs at least pole_count + 1 fit samples")
    relocation_scale = _relocation_scale_rad_per_s(frequencies[indices], relocation_normalization)
    solve_frequencies = frequencies / relocation_scale
    solve_poles = poles / relocation_scale

    flattened = samples.reshape(len(frequencies), -1)
    if response_indices is None:
        selected = _select_pole_response_indices(samples, max_responses, mode=response_selection)
    else:
        selected = _validate_response_indices(response_indices, samples.shape[1] * samples.shape[2])
    response_count = len(selected)
    if relocation_basis == "real-state":
        solve_poles = _force_conjugate_pole_pairs(solve_poles, len(solve_poles))
        pole_block = _pole_block_from_complex_poles(solve_poles)
        basis = _idem_real_basis_design_matrix(solve_frequencies[indices], pole_block)
        basis_no_constant = basis[:, :-1]
        pole_count = len(_jsonable_to_complex_array(pole_block["decoded_poles_rad_per_s"]))
        numerator_terms = basis.shape[1]
    else:
        basis_no_constant = _fixed_pole_design_matrix(solve_frequencies[indices], solve_poles)[:, :-1]
        pole_count = len(solve_poles)
        numerator_terms = pole_count + 1
    rows = len(indices) * response_count
    denominator_offset = response_count * numerator_terms
    if relocation_basis == "real-state":
        real_rows = 2 * rows
        numerator_unknowns = numerator_terms if relocation_numerator == "real" else 2 * numerator_terms
        cols = response_count * numerator_unknowns + (numerator_terms - 1)
        design = np.zeros((real_rows, cols), dtype=float)
        rhs = np.empty(real_rows, dtype=float)
        denominator_offset = response_count * numerator_unknowns
        row_offset = 0
        for local_response_index, response_index in enumerate(selected):
            response = flattened[indices, response_index]
            block_start = local_response_index * numerator_unknowns
            real_block = slice(2 * row_offset, 2 * (row_offset + len(indices)))
            if relocation_numerator == "real":
                design[real_block, block_start : block_start + numerator_terms] = np.vstack([basis.real, basis.imag])
            else:
                _fill_complex_unknown_real_system(design, real_block, block_start, basis)
            denom_block = -response[:, np.newaxis] * basis_no_constant
            design[real_block, denominator_offset:] = np.vstack([denom_block.real, denom_block.imag])
            rhs[real_block] = np.concatenate([response.real, response.imag])
            if relative_weight_power > 0.0:
                weights = _relative_response_weights(response, relative_weight_power)
                real_weights = np.concatenate([weights, weights])
                design[real_block, :] *= real_weights[:, np.newaxis]
                rhs[real_block] *= real_weights
            row_offset += len(indices)
        column_scale = np.linalg.norm(design, axis=0)
        column_scale[column_scale == 0.0] = 1.0
        scaled_design = design / column_scale[np.newaxis, :]
        scaled_coeffs, _, rank, singular_values = np.linalg.lstsq(scaled_design, rhs, rcond=rcond)
        coeffs = scaled_coeffs / column_scale
        denominator_coeffs = coeffs[denominator_offset:]
        companion_poles, denominator_residues = _real_basis_denominator_to_complex_residues(
            pole_block,
            denominator_coeffs,
        )
        companion = np.diag(companion_poles) - np.ones((pole_count, 1), dtype=complex) @ denominator_residues[
            np.newaxis, :
        ]
    else:
        cols = response_count * numerator_terms + pole_count
        design = np.zeros((rows, cols), dtype=complex)
        rhs = np.empty(rows, dtype=complex)
        row_offset = 0
        for local_response_index, response_index in enumerate(selected):
            response = flattened[indices, response_index]
            block_start = local_response_index * numerator_terms
            row_slice = slice(row_offset, row_offset + len(indices))
            design[row_slice, block_start : block_start + pole_count] = basis_no_constant
            design[row_slice, block_start + pole_count] = 1.0
            design[row_slice, denominator_offset:] = -response[:, np.newaxis] * basis_no_constant
            rhs[row_slice] = response
            if relative_weight_power > 0.0:
                weights = _relative_response_weights(response, relative_weight_power)
                design[row_slice, :] *= weights[:, np.newaxis]
                rhs[row_slice] *= weights
            row_offset += len(indices)
        column_scale = np.linalg.norm(design, axis=0)
        column_scale[column_scale == 0.0] = 1.0
        scaled_design = design / column_scale[np.newaxis, :]
        scaled_coeffs, _, rank, singular_values = np.linalg.lstsq(scaled_design, rhs, rcond=rcond)
        coeffs = scaled_coeffs / column_scale
        denominator_residues = coeffs[denominator_offset:]
        companion = np.diag(solve_poles) - np.ones((pole_count, 1), dtype=complex) @ denominator_residues[np.newaxis, :]
    relocated = (
        _stabilize_relocated_poles(np.linalg.eigvals(companion), pole_count, pole_pairing=pole_pairing)
        * relocation_scale
    )
    return PoleRelocationStep(
        iteration=iteration,
        poles_rad_per_s=relocated,
        denominator_residues=denominator_residues,
        selected_response_indices=selected,
        rank=int(rank),
        condition_number=_condition_number_from_singular_values(singular_values),
    )


def fit_touchstone_with_idem_real_basis(
    touchstone_path: Path,
    pole_block: dict[str, Any],
    *,
    parameter_type: str = "s",
    relative_weight_power: float = 0.0,
    fit_max_frequency_points: int | None = None,
    rcond: float | None = None,
) -> dict[str, Any]:
    import skrf as rf

    if parameter_type not in {"s", "z"}:
        raise ValueError("parameter_type must be 's' or 'z'")
    network = rf.Network(str(touchstone_path))
    fit_indices = _fit_indices(len(network.f), fit_max_frequency_points)
    original_z = np.asarray(network.z, dtype=complex)
    original_s = np.asarray(network.s, dtype=complex)
    target = original_s if parameter_type == "s" else original_z
    fit_result = fit_matrix_with_idem_real_basis(
        network.f,
        target,
        pole_block,
        fit_indices=fit_indices,
        relative_weight_power=relative_weight_power,
        rcond=rcond,
    )
    fitted_target = fit_result["fitted_values"]
    if parameter_type == "s":
        fitted_s = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, s=fitted_s, z0=network.z0)
        fitted_z = np.asarray(fitted_network.z, dtype=complex)
    else:
        fitted_z = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, z=fitted_z, z0=network.z0)
        fitted_s = np.asarray(fitted_network.s, dtype=complex)
    return {
        "basis": "idem-real",
        "parameter_type": parameter_type,
        "ports": int(network.nports),
        "frequency_points": int(len(network.f)),
        "fit_frequency_points": int(len(fit_indices)),
        "frequency_range_hz": [float(network.f[0]), float(network.f[-1])] if len(network.f) else None,
        "fit_frequency_range_hz": [float(network.f[fit_indices[0]]), float(network.f[fit_indices[-1]])]
        if len(fit_indices)
        else None,
        "pole_count": int(len(pole_block["decoded_poles_rad_per_s"])),
        "basis_term_count": int(fit_result["basis_term_count"]),
        "include_constant": True,
        "relative_weight_power": relative_weight_power,
        "rcond": rcond,
        "condition_number": fit_result["condition_number"],
        "rank": fit_result["rank"],
        "s_rms_error": _s_rms_error(original_s, fitted_s),
        "s_mean_rms_error": _s_mean_rms_error(original_s, fitted_s),
        "s_relative_rms_error": _relative_rms_error(original_s, fitted_s),
        "z_log_magnitude_rms_error": _z_log_magnitude_rms_error(original_z, fitted_z),
        "diagonal_z_log_magnitude_rms_error": _z_log_magnitude_rms_error(
            np.diagonal(original_z, axis1=1, axis2=2),
            np.diagonal(fitted_z, axis1=1, axis2=2),
        ),
        "max_abs_z_error_ohm": float(np.max(np.abs(original_z - fitted_z))),
    }


def fit_touchstone_with_fixed_poles(
    touchstone_path: Path,
    poles_rad_per_s: Any,
    *,
    parameter_type: str = "s",
    relative_weight_power: float = 0.0,
    fit_max_frequency_points: int | None = None,
    rcond: float | None = None,
) -> dict[str, Any]:
    import skrf as rf

    network = rf.Network(str(touchstone_path))
    fit_indices = _fit_indices(len(network.f), fit_max_frequency_points)
    result = _evaluate_network_with_fixed_poles(
        network,
        poles_rad_per_s,
        parameter_type=parameter_type,
        relative_weight_power=relative_weight_power,
        fit_indices=fit_indices,
        rcond=rcond,
    )
    return {key: value for key, value in result.items() if key not in {"original_s", "fitted_s", "original_z", "fitted_z"}}


def _evaluate_network_with_fixed_poles(
    network: Any,
    poles_rad_per_s: Any,
    *,
    parameter_type: str = "s",
    residue_basis: str = "complex",
    relative_weight_power: float = 0.0,
    fit_indices: Any = None,
    rcond: float | None = None,
) -> dict[str, Any]:
    import skrf as rf

    if parameter_type not in {"s", "z"}:
        raise ValueError("parameter_type must be 's' or 'z'")
    indices = np.arange(len(network.f), dtype=int) if fit_indices is None else np.asarray(fit_indices, dtype=int)
    original_z = np.asarray(network.z, dtype=complex)
    original_s = np.asarray(network.s, dtype=complex)
    if residue_basis not in {"complex", "real-state"}:
        raise ValueError("residue_basis must be 'complex' or 'real-state'")
    if parameter_type == "s":
        target = original_s
    else:
        target = original_z
    fit_model = _fit_model_coefficients(
        network.f,
        target,
        poles_rad_per_s,
        parameter_type=parameter_type,
        residue_basis=residue_basis,
        fit_indices=indices,
        relative_weight_power=relative_weight_power,
        rcond=rcond,
    )
    fit_result = fit_model["fit_result"]
    fitted_target = fit_result["fitted_values"]

    if parameter_type == "s":
        fitted_s = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, s=fitted_s, z0=network.z0)
        fitted_z = np.asarray(fitted_network.z, dtype=complex)
    else:
        fitted_z = fitted_target
        fitted_network = rf.Network(frequency=network.frequency, z=fitted_z, z0=network.z0)
        fitted_s = np.asarray(fitted_network.s, dtype=complex)
    return {
        "basis": residue_basis,
        "parameter_type": parameter_type,
        "ports": int(network.nports),
        "frequency_points": int(len(network.f)),
        "fit_frequency_points": int(len(indices)),
        "frequency_range_hz": [float(network.f[0]), float(network.f[-1])] if len(network.f) else None,
        "fit_frequency_range_hz": [float(network.f[indices[0]]), float(network.f[indices[-1]])]
        if len(indices)
        else None,
        "pole_count": int(len(np.asarray(poles_rad_per_s))),
        "basis_term_count": int(fit_result["basis_term_count"]),
        "include_constant": True,
        "relative_weight_power": relative_weight_power,
        "rcond": rcond,
        "condition_number": fit_result["condition_number"],
        "rank": fit_result["rank"],
        "s_rms_error": _s_rms_error(original_s, fitted_s),
        "s_mean_rms_error": _s_mean_rms_error(original_s, fitted_s),
        "s_relative_rms_error": _relative_rms_error(original_s, fitted_s),
        "z_log_magnitude_rms_error": _z_log_magnitude_rms_error(original_z, fitted_z),
        "diagonal_z_log_magnitude_rms_error": _z_log_magnitude_rms_error(
            np.diagonal(original_z, axis1=1, axis2=2),
            np.diagonal(fitted_z, axis1=1, axis2=2),
        ),
        "max_abs_z_error_ohm": float(np.max(np.abs(original_z - fitted_z))),
        "original_s": original_s,
        "fitted_s": fitted_s,
        "original_z": original_z,
        "fitted_z": fitted_z,
    }


def _fit_network_model_coefficients(
    network: Any,
    poles_rad_per_s: Any,
    *,
    parameter_type: str,
    residue_basis: str,
    fit_indices: Any = None,
    rcond: float | None = None,
) -> dict[str, Any]:
    target = np.asarray(network.s if parameter_type == "s" else network.z, dtype=complex)
    return _fit_model_coefficients(
        network.f,
        target,
        poles_rad_per_s,
        parameter_type=parameter_type,
        residue_basis=residue_basis,
        fit_indices=fit_indices,
        relative_weight_power=0.0,
        rcond=rcond,
    )


def _fit_model_coefficients(
    freqs_hz: Any,
    target: Any,
    poles_rad_per_s: Any,
    *,
    parameter_type: str,
    residue_basis: str,
    fit_indices: Any = None,
    relative_weight_power: float = 0.0,
    rcond: float | None = None,
) -> dict[str, Any]:
    if parameter_type not in {"s", "z"}:
        raise ValueError("parameter_type must be 's' or 'z'")
    if residue_basis == "complex":
        fit_result = fit_matrix_with_fixed_poles(
            freqs_hz,
            target,
            poles_rad_per_s,
            fit_indices=fit_indices,
            relative_weight_power=relative_weight_power,
            rcond=rcond,
        )
        pole_block = _pole_block_from_complex_poles(poles_rad_per_s)
    elif residue_basis == "real-state":
        pole_block = _pole_block_from_complex_poles(poles_rad_per_s)
        fit_result = fit_matrix_with_idem_real_basis(
            freqs_hz,
            target,
            pole_block,
            fit_indices=fit_indices,
            relative_weight_power=relative_weight_power,
            rcond=rcond,
        )
    else:
        raise ValueError("residue_basis must be 'complex' or 'real-state'")
    return {
        "fit_result": fit_result,
        "coefficients": fit_result["coefficients"],
        "pole_block_raw": pole_block["poles_rad_per_s"],
        "pole_block_real_count": int(pole_block["real_pole_count"]),
        "pole_block_complex_pair_count": int(pole_block["complex_pair_count"]),
    }


def fit_s_with_fixed_poles(
    freqs_hz: Any,
    s_parameters: Any,
    poles_rad_per_s: Any,
    *,
    fit_indices: Any = None,
    relative_weight_power: float = 0.0,
    rcond: float | None = None,
) -> dict[str, Any]:
    result = fit_matrix_with_fixed_poles(
        freqs_hz,
        s_parameters,
        poles_rad_per_s,
        fit_indices=fit_indices,
        relative_weight_power=relative_weight_power,
        rcond=rcond,
    )
    return {
        "fitted_s": result["fitted_values"],
        "coefficients": result["coefficients"],
        "rank": result["rank"],
        "condition_number": result["condition_number"],
    }


def fit_matrix_with_fixed_poles(
    freqs_hz: Any,
    values: Any,
    poles_rad_per_s: Any,
    *,
    fit_indices: Any = None,
    relative_weight_power: float = 0.0,
    rcond: float | None = None,
) -> dict[str, Any]:
    freqs = np.asarray(freqs_hz, dtype=float)
    original = np.asarray(values, dtype=complex)
    poles = np.asarray(poles_rad_per_s, dtype=complex)
    if original.ndim != 3 or original.shape[1] != original.shape[2]:
        raise ValueError("values must have shape (frequency_points, nports, nports)")
    if len(freqs) != original.shape[0]:
        raise ValueError("freqs_hz length must match values")
    if len(poles) == 0:
        raise ValueError("poles_rad_per_s must contain at least one pole")
    indices = np.arange(len(freqs)) if fit_indices is None else np.asarray(fit_indices, dtype=int)
    if len(indices) < len(poles) + 1:
        raise ValueError("fixed-pole solve needs at least pole_count + 1 fit samples")

    design_all = _fixed_pole_design_matrix(freqs, poles)
    design_fit = design_all[indices, :]
    rhs = original[indices, :, :].reshape(len(indices), -1)
    if relative_weight_power < 0.0:
        raise ValueError("relative_weight_power must be >= 0")
    if relative_weight_power > 0.0:
        n_terms = len(poles) + 1
        n_responses = rhs.shape[1]
        coeffs = np.empty((n_terms, n_responses), dtype=complex)
        ranks = []
        condition_numbers = []
        for response_index in range(n_responses):
            response_rhs = rhs[:, response_index]
            magnitude = np.abs(response_rhs)
            positive = magnitude[magnitude > 0.0]
            floor = 1e-300 if positive.size == 0 else max(float(np.percentile(positive, 5)) * 1e-3, 1e-300)
            weights = 1.0 / np.power(np.maximum(magnitude, floor), relative_weight_power)
            weighted_design = design_fit * weights[:, np.newaxis]
            weighted_rhs = response_rhs * weights
            column_scale = np.linalg.norm(weighted_design, axis=0)
            column_scale[column_scale == 0.0] = 1.0
            scaled_design = weighted_design / column_scale[np.newaxis, :]
            scaled_coeffs, _, response_rank, singular_values = np.linalg.lstsq(
                scaled_design,
                weighted_rhs,
                rcond=rcond,
            )
            coeffs[:, response_index] = scaled_coeffs / column_scale
            ranks.append(int(response_rank))
            condition_numbers.append(_condition_number_from_singular_values(singular_values))
        rank = min(ranks)
        condition_number = max(condition_numbers)
    else:
        column_scale = np.linalg.norm(design_fit, axis=0)
        column_scale[column_scale == 0.0] = 1.0
        scaled_design_fit = design_fit / column_scale[np.newaxis, :]
        scaled_coeffs, _, rank, singular_values = np.linalg.lstsq(scaled_design_fit, rhs, rcond=rcond)
        coeffs = scaled_coeffs / column_scale[:, np.newaxis]
        condition_number = _condition_number_from_singular_values(singular_values)
    fitted = (design_all @ coeffs).reshape(original.shape)
    return {
        "fitted_values": fitted,
        "coefficients": coeffs,
        "basis_term_count": int(len(poles) + 1),
        "rank": int(rank),
        "condition_number": condition_number,
    }


def fit_matrix_with_idem_real_basis(
    freqs_hz: Any,
    values: Any,
    pole_block: dict[str, Any],
    *,
    fit_indices: Any = None,
    relative_weight_power: float = 0.0,
    rcond: float | None = None,
) -> dict[str, Any]:
    freqs = np.asarray(freqs_hz, dtype=float)
    original = np.asarray(values, dtype=complex)
    if original.ndim != 3 or original.shape[1] != original.shape[2]:
        raise ValueError("values must have shape (frequency_points, nports, nports)")
    if len(freqs) != original.shape[0]:
        raise ValueError("freqs_hz length must match values")
    if relative_weight_power < 0.0:
        raise ValueError("relative_weight_power must be >= 0")
    indices = np.arange(len(freqs)) if fit_indices is None else np.asarray(fit_indices, dtype=int)
    design_all = _idem_real_basis_design_matrix(freqs, pole_block)
    if len(indices) < design_all.shape[1]:
        raise ValueError("real-basis solve needs at least basis_term_count fit samples")
    design_fit = design_all[indices, :]
    rhs = original[indices, :, :].reshape(len(indices), -1)
    fitted = np.empty((len(freqs), rhs.shape[1]), dtype=complex)
    ranks = []
    condition_numbers = []
    coefficients = np.empty((design_fit.shape[1], rhs.shape[1]), dtype=float)
    for response_index in range(rhs.shape[1]):
        response_rhs = rhs[:, response_index]
        weights = None
        if relative_weight_power > 0.0:
            magnitude = np.abs(response_rhs)
            positive = magnitude[magnitude > 0.0]
            floor = 1e-300 if positive.size == 0 else max(float(np.percentile(positive, 5)) * 1e-3, 1e-300)
            weights = 1.0 / np.power(np.maximum(magnitude, floor), relative_weight_power)
        coeffs, rank, singular_values = _solve_real_basis_response(
            design_fit,
            response_rhs,
            weights=weights,
            rcond=rcond,
        )
        coefficients[:, response_index] = coeffs
        fitted[:, response_index] = design_all @ coeffs
        ranks.append(rank)
        condition_numbers.append(_condition_number_from_singular_values(singular_values))
    return {
        "fitted_values": fitted.reshape(original.shape),
        "coefficients": coefficients,
        "basis_term_count": int(design_all.shape[1]),
        "rank": int(min(ranks)),
        "condition_number": float(max(condition_numbers)),
    }


def write_probe_jsonl(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, sort_keys=True) + "\n")


def write_probe_csv(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "probe",
        "touchstone_path",
        "status",
        "order",
        "initial_iterations",
        "target",
        "threads",
        "enforce_asymptotic_passivity",
        "asymptotic_relocate_poles",
        "enhance_poles_placement",
        "elapsed_seconds",
        "peak_memory_mb",
        "model_order",
        "total_pole_count",
        "last_rms_error",
        "last_order",
        "model_path",
        "xml_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            command = result.get("command", {})
            model = result.get("model", {})
            writer.writerow(
                {
                    "probe": result.get("probe"),
                    "touchstone_path": result.get("touchstone_path"),
                    "status": result.get("status"),
                    "order": result.get("order"),
                    "initial_iterations": result.get("initial_iterations"),
                    "target": result.get("target"),
                    "threads": result.get("threads"),
                    "enforce_asymptotic_passivity": result.get("enforce_asymptotic_passivity"),
                    "asymptotic_relocate_poles": result.get("asymptotic_relocate_poles"),
                    "enhance_poles_placement": result.get("enhance_poles_placement"),
                    "elapsed_seconds": command.get("elapsed_seconds"),
                    "peak_memory_mb": command.get("peak_memory_mb"),
                    "model_order": model.get("order"),
                    "total_pole_count": model.get("total_pole_count"),
                    "last_rms_error": _last_value(model.get("error_history")),
                    "last_order": _last_value(model.get("orders_history")),
                    "model_path": result.get("model_path"),
                    "xml_path": result.get("xml_path"),
                }
            )


def write_residue_sweep_csv(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model_label",
        "model_path",
        "basis",
        "parameter_type",
        "relative_weight_power",
        "rank",
        "condition_number",
        "s_relative_rms_error",
        "s_rms_error",
        "s_mean_rms_error",
        "z_log_magnitude_rms_error",
        "diagonal_z_log_magnitude_rms_error",
        "max_abs_z_error_ohm",
        "pole_count",
        "basis_term_count",
        "fit_frequency_points",
        "idem_split_rms_error",
        "idem_split_max_error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            idem_model = result.get("idem_model", {})
            writer.writerow(
                {
                    "model_label": result.get("model_label"),
                    "model_path": result.get("model_path"),
                    "basis": result.get("basis"),
                    "parameter_type": result.get("parameter_type"),
                    "relative_weight_power": result.get("relative_weight_power"),
                    "rank": result.get("rank"),
                    "condition_number": result.get("condition_number"),
                    "s_relative_rms_error": result.get("s_relative_rms_error"),
                    "s_rms_error": result.get("s_rms_error"),
                    "s_mean_rms_error": result.get("s_mean_rms_error"),
                    "z_log_magnitude_rms_error": result.get("z_log_magnitude_rms_error"),
                    "diagonal_z_log_magnitude_rms_error": result.get("diagonal_z_log_magnitude_rms_error"),
                    "max_abs_z_error_ohm": result.get("max_abs_z_error_ohm"),
                    "pole_count": result.get("pole_count"),
                    "basis_term_count": result.get("basis_term_count"),
                    "fit_frequency_points": result.get("fit_frequency_points"),
                    "idem_split_rms_error": idem_model.get("split_rms_error"),
                    "idem_split_max_error": idem_model.get("split_max_error"),
                }
            )


def write_relocation_csv(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "iteration",
        "sweep_label",
        "basis",
        "order",
        "parameter_type",
        "relative_weight_power",
        "pole_damping",
        "pole_spacing",
        "pole_f_min",
        "response_selection",
        "pole_pairing",
        "relocation_basis",
        "relocation_normalization",
        "relocation_numerator",
        "fit_frequency_points",
        "selected_response_count",
        "relocation_rank",
        "relocation_condition_number",
        "denominator_residue_norm",
        "rank",
        "condition_number",
        "s_mean_rms_error",
        "s_relative_rms_error",
        "z_log_magnitude_rms_error",
        "diagonal_z_log_magnitude_rms_error",
        "max_abs_z_error_ohm",
        "lowest_pole_frequency_hz",
        "highest_pole_frequency_hz",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            pole_frequencies = result.get("pole_frequencies_hz") or []
            sorted_frequencies = sorted(float(frequency) for frequency in pole_frequencies)
            row = {field: result.get(field) for field in fieldnames}
            row["lowest_pole_frequency_hz"] = sorted_frequencies[0] if sorted_frequencies else None
            row["highest_pole_frequency_hz"] = sorted_frequencies[-1] if sorted_frequencies else None
            writer.writerow(row)


def write_json_report(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl_report(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, sort_keys=True) + "\n")


def _run_command(
    command: list[str],
    timeout_seconds: float | None,
    idle_timeout_seconds: float | None = None,
    progress_paths: list[Path] | tuple[Path, ...] | None = None,
) -> IdemCommandResult:
    started = time.perf_counter()
    last_progress = started
    last_cpu_seconds: float | None = None
    peak_memory_mb: float | None = None
    termination_reason = "completed"
    elapsed: float | None = None
    try:
        import psutil
    except ImportError:
        psutil = None

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        psutil_process = psutil.Process(process.pid) if psutil is not None else None
    except Exception:
        psutil_process = None
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_counter = {"bytes": 0}
    stderr_counter = {"bytes": 0}
    reader_errors: list[BaseException] = []
    stdout_thread = _start_pipe_reader(getattr(process, "stdout", None), stdout_chunks, stdout_counter, reader_errors)
    stderr_thread = _start_pipe_reader(getattr(process, "stderr", None), stderr_chunks, stderr_counter, reader_errors)
    artifacts = [Path(path) for path in (progress_paths or [])]
    artifact_snapshot = _artifact_progress_snapshot(artifacts)
    last_output_bytes = 0
    cleanup: dict[str, Any] = {}
    child_pids: list[int] = []
    cpu_seconds: float | None = None
    try:
        while process.poll() is None:
            now = time.perf_counter()
            if timeout_seconds is not None and now - started > timeout_seconds:
                termination_reason = "timeout"
                cleanup = _kill_process_tree(process, psutil_process, psutil)
                _join_pipe_readers((stdout_thread, stderr_thread))
                raise TimeoutError(f"Command timed out after {timeout_seconds} seconds: {' '.join(command)}")
            cpu_seconds = _process_tree_cpu_seconds(psutil_process)
            if cpu_seconds is not None:
                if last_cpu_seconds is None or cpu_seconds > last_cpu_seconds + 1.0e-6:
                    last_progress = now
                last_cpu_seconds = cpu_seconds
            output_bytes = stdout_counter["bytes"] + stderr_counter["bytes"]
            if output_bytes > last_output_bytes:
                last_output_bytes = output_bytes
                last_progress = now
            next_artifact_snapshot = _artifact_progress_snapshot(artifacts)
            if _artifact_snapshot_changed(artifact_snapshot, next_artifact_snapshot):
                last_progress = now
            artifact_snapshot = next_artifact_snapshot
            child_pids = _process_tree_child_pids(psutil_process)
            if (
                idle_timeout_seconds is not None
                and now - last_progress > idle_timeout_seconds
            ):
                termination_reason = "idle_stall"
                cleanup = _kill_process_tree(process, psutil_process, psutil)
                _join_pipe_readers((stdout_thread, stderr_thread))
                elapsed = time.perf_counter() - started
                telemetry = _command_telemetry(
                    idle_limit=idle_timeout_seconds,
                    elapsed=elapsed,
                    last_progress_age=elapsed - (last_progress - started),
                    cpu_seconds=cpu_seconds,
                    stdout_bytes=stdout_counter["bytes"],
                    stderr_bytes=stderr_counter["bytes"],
                    artifacts=artifacts,
                    pid=process.pid,
                    child_pids=child_pids,
                    termination_reason=termination_reason,
                    cleanup=cleanup,
                )
                raise CommandIdleStallError(
                    IdemCommandResult(
                        command=command,
                        returncode=int(process.returncode or -9),
                        stdout="".join(stdout_chunks),
                        stderr="".join(stderr_chunks),
                        elapsed_seconds=elapsed,
                        peak_memory_mb=peak_memory_mb,
                        telemetry=telemetry,
                    )
                )
            peak_memory_mb = _sample_peak_memory_mb(psutil_process, peak_memory_mb)
            time.sleep(0.05)
        _join_pipe_readers((stdout_thread, stderr_thread))
        peak_memory_mb = _sample_peak_memory_mb(psutil_process, peak_memory_mb)
    except BaseException:
        if process.poll() is None and termination_reason == "completed":
            termination_reason = "interrupted"
            cleanup = _kill_process_tree(process, psutil_process, psutil)
            _join_pipe_readers((stdout_thread, stderr_thread))
        raise
    finally:
        if elapsed is None:
            elapsed = time.perf_counter() - started
        _close_process_pipes(process)
    if reader_errors:
        raise RuntimeError(f"command pipe reader failed: {type(reader_errors[0]).__name__}: {reader_errors[0]}")
    telemetry = _command_telemetry(
        idle_limit=idle_timeout_seconds,
        elapsed=elapsed,
        last_progress_age=elapsed - (last_progress - started),
        cpu_seconds=cpu_seconds,
        stdout_bytes=stdout_counter["bytes"],
        stderr_bytes=stderr_counter["bytes"],
        artifacts=artifacts,
        pid=process.pid,
        child_pids=child_pids,
        termination_reason=termination_reason,
        cleanup=cleanup,
    )
    return IdemCommandResult(
        command=command,
        returncode=int(process.returncode),
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
        elapsed_seconds=elapsed,
        peak_memory_mb=peak_memory_mb,
        telemetry=telemetry,
    )


def _start_pipe_reader(
    stream: Any,
    chunks: list[str],
    counter: dict[str, int],
    errors: list[BaseException],
) -> threading.Thread | None:
    if stream is None:
        return None

    def read_stream() -> None:
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                counter["bytes"] += len(chunk.encode("utf-8", errors="replace"))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=read_stream, name="idem-command-pipe-reader", daemon=True)
    thread.start()
    return thread


def _join_pipe_readers(threads: tuple[threading.Thread | None, ...]) -> None:
    for thread in threads:
        if thread is not None:
            thread.join(timeout=5.0)


def _close_process_pipes(process: subprocess.Popen[Any]) -> None:
    for stream in (getattr(process, "stdout", None), getattr(process, "stderr", None)):
        try:
            if stream is not None:
                stream.close()
        except Exception:
            pass


def _kill_process_tree(process: subprocess.Popen[Any], psutil_process: Any, psutil_module: Any = None) -> dict[str, Any]:
    cleanup: dict[str, Any] = {
        "owned_pids_before_kill": [],
        "owned_pids_alive_after_kill": [],
    }
    if psutil_process is not None and psutil_module is not None:
        try:
            known = _known_process_tree(psutil_process)
            known_by_pid = {int(item.pid): item for item in known}
            cleanup["owned_pids_before_kill"] = [item.pid for item in known]
            for proc in reversed(known[1:]):
                _psutil_terminate(proc)
            _psutil_terminate(psutil_process)
            _, alive = psutil_module.wait_procs(known, timeout=5.0)
            for proc in alive:
                _psutil_kill(proc)
            if alive:
                psutil_module.wait_procs(alive, timeout=5.0)
            try:
                if psutil_process.is_running():
                    new_processes = []
                    for proc in _known_process_tree(psutil_process):
                        pid = int(proc.pid)
                        if pid not in known_by_pid:
                            known_by_pid[pid] = proc
                            new_processes.append(proc)
                            cleanup["owned_pids_before_kill"].append(proc.pid)
                        _psutil_kill(proc)
                    if new_processes:
                        psutil_module.wait_procs(new_processes, timeout=5.0)
            except Exception:
                pass
            cleanup["owned_pids_alive_after_kill"] = [
                proc.pid for proc in known_by_pid.values() if _psutil_is_owned_process_alive(proc)
            ]
        except Exception:
            pass
    try:
        if process.poll() is None:
            process.terminate()
    except AttributeError:
        try:
            process.kill()
        except OSError:
            pass
    except Exception:
        pass
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=5.0)
        except Exception:
            pass
    except Exception:
        pass
    if process.pid not in cleanup["owned_pids_before_kill"]:
        cleanup["owned_pids_before_kill"].insert(0, process.pid)
    if process.poll() is None and process.pid not in cleanup["owned_pids_alive_after_kill"]:
        cleanup["owned_pids_alive_after_kill"].append(process.pid)
    return cleanup


def _known_process_tree(psutil_process: Any) -> list[Any]:
    known = [psutil_process]
    try:
        known.extend(psutil_process.children(recursive=True))
    except Exception:
        pass
    deduped: dict[int, Any] = {}
    for proc in known:
        try:
            deduped[int(proc.pid)] = proc
        except Exception:
            continue
    return list(deduped.values())


def _psutil_terminate(process: Any) -> None:
    try:
        process.terminate()
    except AttributeError:
        _psutil_kill(process)
    except Exception:
        pass


def _psutil_kill(process: Any) -> None:
    try:
        process.kill()
    except Exception:
        pass


def _psutil_is_owned_process_alive(process: Any) -> bool:
    try:
        if not process.is_running():
            return False
        status = process.status()
        return status != "zombie"
    except Exception:
        return False


def _process_tree_child_pids(process: Any) -> list[int]:
    if process is None:
        return []
    try:
        return [int(child.pid) for child in process.children(recursive=True)]
    except Exception:
        return []


def _artifact_progress_snapshot(paths: list[Path]) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            snapshot.append({"path": str(path), "exists": False, "size": None, "mtime": None})
            continue
        snapshot.append(
            {
                "path": str(path),
                "exists": True,
                "size": int(stat.st_size),
                "mtime": float(stat.st_mtime),
            }
        )
    return snapshot


def _artifact_snapshot_changed(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> bool:
    if len(before) != len(after):
        return True
    for left, right in zip(before, after):
        if (
            left.get("exists") != right.get("exists")
            or left.get("size") != right.get("size")
            or left.get("mtime") != right.get("mtime")
        ):
            return True
    return False


def _command_telemetry(
    *,
    idle_limit: float | None,
    elapsed: float,
    last_progress_age: float,
    cpu_seconds: float | None,
    stdout_bytes: int,
    stderr_bytes: int,
    artifacts: list[Path],
    pid: int,
    child_pids: list[int],
    termination_reason: str,
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    return {
        "idle_limit": None if idle_limit is None else float(idle_limit),
        "elapsed": float(elapsed),
        "last_progress_age": float(max(0.0, last_progress_age)),
        "cpu": {"process_tree_seconds": None if cpu_seconds is None else float(cpu_seconds)},
        "output_bytes": {
            "stdout": int(stdout_bytes),
            "stderr": int(stderr_bytes),
            "total": int(stdout_bytes + stderr_bytes),
        },
        "artifacts": _artifact_progress_snapshot(artifacts),
        "pid": int(pid),
        "child_pids": [int(child_pid) for child_pid in child_pids],
        "termination_reason": termination_reason,
        "owned_pids_before_kill": [int(item) for item in cleanup.get("owned_pids_before_kill", [])],
        "owned_pids_alive_after_kill": [int(item) for item in cleanup.get("owned_pids_alive_after_kill", [])],
    }


def _process_tree_cpu_seconds(process: Any) -> float | None:
    if process is None:
        return None
    total = 0.0
    try:
        cpu = process.cpu_times()
        total += float(getattr(cpu, "user", 0.0) or 0.0)
        total += float(getattr(cpu, "system", 0.0) or 0.0)
        total += float(getattr(cpu, "children_user", 0.0) or 0.0)
        total += float(getattr(cpu, "children_system", 0.0) or 0.0)
        children = process.children(recursive=True)
    except Exception:
        return None
    for child in children:
        try:
            cpu = child.cpu_times()
            total += float(getattr(cpu, "user", 0.0) or 0.0)
            total += float(getattr(cpu, "system", 0.0) or 0.0)
        except Exception:
            continue
    return total


def _sample_peak_memory_mb(process: Any, current_peak: float | None) -> float | None:
    if process is None:
        return current_peak
    try:
        rss = process.memory_info().rss
        for child in process.children(recursive=True):
            try:
                rss += child.memory_info().rss
            except Exception:
                continue
    except Exception:
        return current_peak
    sampled = rss / 1024 / 1024
    if current_peak is None:
        return sampled
    return max(current_peak, sampled)


def _resolve_idem_bin_dir(idem_bin_dir: Path | None) -> Path:
    if idem_bin_dir is not None:
        return idem_bin_dir
    env_value = os.environ.get("AGENT_SPICE_IDEM_BIN")
    return Path(env_value) if env_value else DEFAULT_IDEM_BIN_DIR


def _model_label(model_path: Path) -> str:
    parent = model_path.parent.name
    if parent:
        return parent
    return model_path.stem


def _idem_fit_completed(result: IdemCommandResult, model_path: Path) -> bool:
    if not model_path.exists():
        return False
    if "Error:" in result.stdout or "Error:" in result.stderr:
        return False
    return result.returncode == 0 or "End of model build" in result.stdout


def _idem_adaptive_fit_completed(result: IdemCommandResult, model_path: Path) -> bool:
    if not model_path.is_file() or model_path.stat().st_size <= 0:
        return False
    if "Error:" in result.stdout or "Error:" in result.stderr:
        return False
    return result.returncode == 0 or "End of model build" in result.stdout


def _idem_passivity_completed(result: IdemCommandResult, output_model_path: Path) -> bool:
    if "Passive:" in result.stdout:
        return True
    if output_model_path.exists() and "End of passivity check" in result.stdout:
        return True
    return result.returncode == 0 and output_model_path.exists()


def _touchstone_bandwidth_hz(path: Path) -> float:
    unit_scale = 1.0
    max_frequency: float | None = None
    scales = {
        "HZ": 1.0,
        "KHZ": 1e3,
        "MHZ": 1e6,
        "GHZ": 1e9,
    }
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("!"):
                continue
            if stripped.startswith("#"):
                tokens = stripped[1:].split()
                if tokens:
                    unit_scale = scales.get(tokens[0].upper(), unit_scale)
                continue
            data = stripped.split("!", 1)[0].strip()
            if not data:
                continue
            try:
                frequency = float(data.split()[0]) * unit_scale
            except (IndexError, ValueError):
                continue
            max_frequency = frequency if max_frequency is None else max(max_frequency, frequency)
    if max_frequency is None:
        raise ValueError(f"Could not determine Touchstone bandwidth from {path}")
    return max_frequency


def _read_first_object_dataset(handle: Any, path: str) -> Any:
    if path not in handle:
        return None
    dataset = handle[path]
    if len(dataset) == 0:
        return None
    return dataset[0]


def _read_text_dataset(handle: Any, path: str) -> str | None:
    value = _read_first_object_dataset(handle, path)
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _field_to_float_list(row: Any, field_name: str) -> list[float]:
    if row.dtype.names is None or field_name not in row.dtype.names:
        return []
    value = row[field_name]
    try:
        return [float(item) for item in value]
    except TypeError:
        return [float(value)]


def _float_field(row: Any, field_name: str) -> float | None:
    if row.dtype.names is None or field_name not in row.dtype.names:
        return None
    value = float(row[field_name])
    return value if math.isfinite(value) else None


def _int_field(row: Any, field_name: str) -> int | None:
    if row.dtype.names is None or field_name not in row.dtype.names:
        return None
    return int(row[field_name])


def _decode_idem_split_poles(row: Any) -> np.ndarray:
    raw = np.asarray(_field_to_float_list(row, "p"), dtype=float)
    nr = _int_field(row, "nr") or 0
    nc = _int_field(row, "nc") or 0
    decoded: list[complex] = [complex(value) for value in raw[:nr]]
    offset = nr
    for pair_index in range(nc):
        pair_offset = offset + 2 * pair_index
        if pair_offset + 1 >= len(raw):
            break
        sigma = float(raw[pair_offset])
        omega = abs(float(raw[pair_offset + 1]))
        decoded.append(complex(sigma, omega))
        decoded.append(complex(sigma, -omega))
    if len(decoded) < len(raw):
        decoded.extend(complex(value) for value in raw[len(decoded) :])
    return np.asarray(decoded, dtype=complex)


def _array_to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _complex_array_to_jsonable(values: Any) -> list[list[float]]:
    array = np.asarray(values, dtype=complex)
    return [[float(value.real), float(value.imag)] for value in array]


def _jsonable_to_complex_array(values: Any) -> np.ndarray:
    return np.asarray([complex(float(item[0]), float(item[1])) for item in values], dtype=complex)


def _pole_to_hz(pole_rad_per_s: float) -> float:
    return abs(complex(pole_rad_per_s)) / (2.0 * math.pi)


def _fit_indices(length: int, max_points: int | None) -> np.ndarray:
    if max_points is None or length <= max_points:
        return np.arange(length, dtype=int)
    if max_points < 1:
        raise ValueError("fit_max_frequency_points must be >= 1")
    return np.unique(np.linspace(0, length - 1, max_points, dtype=int))


def _pole_relocation_result_dict(
    touchstone_path: Path,
    order: int,
    parameter_type: str,
    pole_damping: float,
    pole_spacing: str,
    pole_f_min: float | None,
    response_selection: str,
    relative_weight_power: float,
    pole_pairing: str,
    relocation_basis: str,
    relocation_normalization: str,
    relocation_numerator: str,
    fit_indices: np.ndarray,
    step: PoleRelocationStep,
    residue_metrics: dict[str, Any],
) -> dict[str, Any]:
    metric_keys = {
        "basis",
        "basis_term_count",
        "condition_number",
        "rank",
        "s_rms_error",
        "s_mean_rms_error",
        "s_relative_rms_error",
        "z_log_magnitude_rms_error",
        "diagonal_z_log_magnitude_rms_error",
        "max_abs_z_error_ohm",
    }
    return {
        "probe": "local_common_pole_relocation",
        "touchstone_path": str(touchstone_path),
        "iteration": step.iteration,
        "order": order,
        "parameter_type": parameter_type,
        "relative_weight_power": relative_weight_power,
        "pole_damping": pole_damping,
        "pole_spacing": pole_spacing,
        "pole_f_min": pole_f_min,
        "response_selection": response_selection,
        "pole_pairing": pole_pairing,
        "relocation_basis": relocation_basis,
        "relocation_normalization": relocation_normalization,
        "relocation_numerator": relocation_numerator,
        "fit_frequency_points": int(len(fit_indices)),
        "selected_response_count": len(step.selected_response_indices),
        "selected_response_indices": list(step.selected_response_indices),
        "relocation_rank": step.rank,
        "relocation_condition_number": step.condition_number,
        "denominator_residue_norm": None
        if step.denominator_residues is None
        else float(np.linalg.norm(step.denominator_residues)),
        "poles_rad_per_s": _complex_array_to_jsonable(step.poles_rad_per_s),
        "pole_frequencies_hz": [_pole_to_hz(pole) for pole in step.poles_rad_per_s],
        "pole_real_parts_rad_per_s": [float(complex(pole).real) for pole in step.poles_rad_per_s],
        "pole_imag_parts_rad_per_s": [float(complex(pole).imag) for pole in step.poles_rad_per_s],
        **{key: value for key, value in residue_metrics.items() if key in metric_keys},
    }


def _select_pole_response_indices(
    values: np.ndarray,
    max_responses: int | None,
    *,
    mode: str = "energy",
) -> tuple[int, ...]:
    flattened = np.asarray(values, dtype=complex).reshape(values.shape[0], -1)
    response_count = flattened.shape[1]
    if values.ndim != 3 or values.shape[1] != values.shape[2]:
        raise ValueError("values must have shape (frequency_points, nports, nports)")
    if max_responses is None or max_responses >= response_count:
        max_responses = response_count
    if max_responses < 1:
        raise ValueError("max_responses must be >= 1")
    nports = values.shape[1]
    energy = np.sqrt(np.mean(np.square(np.abs(flattened)), axis=0))
    diagonal = tuple(port * nports + port for port in range(nports))
    offdiagonal = tuple(index for index in range(response_count) if index not in set(diagonal))
    if mode in {"energy", "adaptive-z"}:
        pool = tuple(range(response_count))
        ranked = _rank_response_indices_by_energy(energy, pool, max_responses)
    elif mode == "diagonal":
        ranked = _rank_response_indices_by_energy(energy, diagonal, max_responses)
    elif mode == "offdiagonal":
        ranked = _rank_response_indices_by_energy(energy, offdiagonal, max_responses)
    elif mode == "mixed":
        diag_budget = min(len(diagonal), max(1, max_responses // 2), max_responses)
        diagonal_ranked = _rank_response_indices_by_energy(energy, diagonal, diag_budget)
        remaining = max_responses - len(diagonal_ranked)
        rest_pool = tuple(index for index in range(response_count) if index not in set(diagonal_ranked))
        ranked = diagonal_ranked + _rank_response_indices_by_energy(energy, rest_pool, remaining)
    else:
        raise ValueError("mode must be 'energy', 'diagonal', 'offdiagonal', 'mixed', or 'adaptive-z'")
    return tuple(int(index) for index in sorted(ranked))


def _rank_response_indices_by_energy(energy: np.ndarray, pool: tuple[int, ...], limit: int) -> tuple[int, ...]:
    if limit <= 0 or not pool:
        return ()
    ranked = sorted(pool, key=lambda index: float(energy[index]), reverse=True)
    return tuple(int(index) for index in ranked[:limit])


def _select_adaptive_z_response_indices(
    values: np.ndarray,
    original_z: np.ndarray,
    fitted_z: np.ndarray,
    max_responses: int | None,
    *,
    worst_pair_count: int,
) -> tuple[int, ...]:
    if worst_pair_count < 0:
        raise ValueError("worst_pair_count must be >= 0")
    flattened = np.asarray(values, dtype=complex).reshape(values.shape[0], -1)
    response_count = flattened.shape[1]
    if max_responses is None or max_responses >= response_count:
        max_responses = response_count
    if max_responses < 1:
        raise ValueError("max_responses must be >= 1")
    energy = np.sqrt(np.mean(np.square(np.abs(flattened)), axis=0))
    worst = _worst_z_pair_indices(original_z, fitted_z, min(worst_pair_count, max_responses))
    remaining = max_responses - len(worst)
    rest = tuple(index for index in range(response_count) if index not in set(worst))
    return tuple(sorted(worst + _rank_response_indices_by_energy(energy, rest, remaining)))


def _worst_z_pair_indices(original_z: np.ndarray, fitted_z: np.ndarray, count: int) -> tuple[int, ...]:
    if count <= 0:
        return ()
    original = np.asarray(original_z, dtype=complex)
    fitted = np.asarray(fitted_z, dtype=complex)
    if original.shape != fitted.shape or original.ndim != 3 or original.shape[1] != original.shape[2]:
        raise ValueError("original_z and fitted_z must have matching shape (frequency_points, nports, nports)")
    original_mag = np.maximum(np.abs(original), 1e-300)
    fitted_mag = np.maximum(np.abs(fitted), 1e-300)
    delta = np.log10(fitted_mag / original_mag)
    with np.errstate(invalid="ignore"):
        pair_scores = np.sqrt(np.nanmean(np.square(delta), axis=0))
    ranked: list[tuple[float, int]] = []
    nports = original.shape[1]
    for row in range(nports):
        for column in range(nports):
            score = float(pair_scores[row, column])
            if math.isfinite(score):
                ranked.append((score, row * nports + column))
    return tuple(index for _, index in sorted(ranked, reverse=True)[:count])


def _validate_response_indices(indices: tuple[int, ...], response_count: int) -> tuple[int, ...]:
    if not indices:
        raise ValueError("response_indices must contain at least one index")
    unique = tuple(sorted(set(int(index) for index in indices)))
    invalid = [index for index in unique if index < 0 or index >= response_count]
    if invalid:
        raise ValueError(f"response index out of range: {invalid[0]}")
    return unique


def _fixed_pole_design_matrix(freqs_hz: np.ndarray, poles_rad_per_s: np.ndarray) -> np.ndarray:
    s = 2j * np.pi * freqs_hz
    pole_terms = 1.0 / (s[:, np.newaxis] - poles_rad_per_s[np.newaxis, :])
    return np.column_stack([pole_terms, np.ones(len(freqs_hz), dtype=complex)])


def _fill_complex_unknown_real_system(
    design: np.ndarray,
    row_slice: slice,
    column_start: int,
    basis: np.ndarray,
) -> None:
    term_count = basis.shape[1]
    real_columns = slice(column_start, column_start + term_count)
    imag_columns = slice(column_start + term_count, column_start + 2 * term_count)
    design[row_slice, real_columns] = np.vstack([basis.real, basis.imag])
    design[row_slice, imag_columns] = np.vstack([-basis.imag, basis.real])


def _relative_response_weights(response: np.ndarray, relative_weight_power: float) -> np.ndarray:
    magnitude = np.abs(response)
    positive = magnitude[magnitude > 0.0]
    floor = 1e-300 if positive.size == 0 else max(float(np.percentile(positive, 5)) * 1e-3, 1e-300)
    return 1.0 / np.power(np.maximum(magnitude, floor), relative_weight_power)


def _relocation_scale_rad_per_s(freqs_hz: np.ndarray, normalization: str) -> float:
    if normalization == "none":
        return 1.0
    if normalization != "frequency":
        raise ValueError("relocation_normalization must be 'none' or 'frequency'")
    frequencies = np.asarray(freqs_hz, dtype=float)
    positive = np.abs(frequencies[frequencies != 0.0])
    if positive.size == 0:
        return 1.0
    scale = 2.0 * math.pi * float(np.max(positive))
    return scale if math.isfinite(scale) and scale > 0.0 else 1.0


def _real_basis_denominator_to_complex_residues(
    pole_block: dict[str, Any],
    denominator_coeffs: Any,
) -> tuple[np.ndarray, np.ndarray]:
    raw = np.asarray(pole_block["poles_rad_per_s"], dtype=float)
    coeffs = np.asarray(denominator_coeffs, dtype=float)
    real_count = int(pole_block.get("real_pole_count") or 0)
    complex_pair_count = int(pole_block.get("complex_pair_count") or 0)
    poles: list[complex] = []
    residues: list[complex] = []
    coeff_index = 0
    for pole in raw[:real_count]:
        if coeff_index >= len(coeffs):
            break
        poles.append(complex(float(pole), 0.0))
        residues.append(complex(float(coeffs[coeff_index]), 0.0))
        coeff_index += 1
    offset = real_count
    for pair_index in range(complex_pair_count):
        if coeff_index + 1 >= len(coeffs):
            break
        pair_offset = offset + 2 * pair_index
        if pair_offset + 1 >= len(raw):
            break
        sigma = float(raw[pair_offset])
        omega = abs(float(raw[pair_offset + 1]))
        first = complex(sigma, omega)
        second = complex(sigma, -omega)
        coeff_sum = float(coeffs[coeff_index])
        coeff_diff = float(coeffs[coeff_index + 1])
        poles.extend([first, second])
        residues.extend([complex(coeff_sum, coeff_diff), complex(coeff_sum, -coeff_diff)])
        coeff_index += 2
    return np.asarray(poles, dtype=complex), np.asarray(residues, dtype=complex)


def _sort_poles_by_frequency(poles: np.ndarray) -> np.ndarray:
    return np.asarray(sorted((complex(pole) for pole in poles), key=lambda pole: (abs(pole), pole.imag)), dtype=complex)


def _stabilize_relocated_poles(
    poles: np.ndarray,
    expected_count: int,
    *,
    pole_pairing: str = "none",
) -> np.ndarray:
    if pole_pairing not in {"none", "conjugate"}:
        raise ValueError("pole_pairing must be 'none' or 'conjugate'")
    stable: list[complex] = []
    for pole in poles:
        value = complex(pole)
        if not (math.isfinite(value.real) and math.isfinite(value.imag)):
            continue
        real = value.real if value.real < 0.0 else -max(abs(value.real), 1e-12)
        stable.append(complex(real, value.imag))
    if len(stable) < expected_count:
        stable.extend(complex(-1.0 - index, 0.0) for index in range(expected_count - len(stable)))
    if pole_pairing == "conjugate":
        return _force_conjugate_pole_pairs(np.asarray(stable, dtype=complex), expected_count)
    return _sort_poles_by_frequency(np.asarray(stable[:expected_count], dtype=complex))


def _force_conjugate_pole_pairs(poles: np.ndarray, expected_count: int) -> np.ndarray:
    if expected_count < 1:
        return np.asarray([], dtype=complex)
    block = _pole_block_from_complex_poles(poles)
    raw = np.asarray(block["poles_rad_per_s"], dtype=float)
    real_count = int(block["real_pole_count"])
    pair_count = int(block["complex_pair_count"])
    real_poles = sorted((float(pole) for pole in raw[:real_count]), key=abs)
    pair_offset = real_count
    pairs: list[tuple[float, float, float]] = []
    for pair_index in range(pair_count):
        offset = pair_offset + 2 * pair_index
        if offset + 1 >= len(raw):
            break
        sigma = float(raw[offset])
        omega = abs(float(raw[offset + 1]))
        if omega == 0.0:
            real_poles.append(sigma)
        else:
            pairs.append((abs(complex(sigma, omega)), sigma, omega))
    pairs.sort(key=lambda item: item[0])

    target_pairs = expected_count // 2
    target_reals = expected_count % 2
    decoded: list[complex] = []
    if target_reals:
        if real_poles:
            decoded.append(complex(real_poles[0], 0.0))
        elif pairs:
            _, sigma, omega = pairs[0]
            decoded.append(complex(-max(abs(sigma), 0.05 * omega, 1.0), 0.0))
        else:
            decoded.append(complex(-1.0, 0.0))
    for _, sigma, omega in pairs[:target_pairs]:
        decoded.append(complex(sigma, omega))
        decoded.append(complex(sigma, -omega))
    while len(decoded) < expected_count:
        index = len(decoded)
        if expected_count - index >= 2:
            omega = float(index + 1)
            sigma = -max(1.0, 0.05 * omega)
            decoded.append(complex(sigma, omega))
            decoded.append(complex(sigma, -omega))
        else:
            decoded.append(complex(-1.0 - index, 0.0))
    return _sort_poles_by_frequency(np.asarray(decoded[:expected_count], dtype=complex))


def _pole_block_from_complex_poles(poles_rad_per_s: Any) -> dict[str, Any]:
    poles = _sort_poles_by_frequency(np.asarray(poles_rad_per_s, dtype=complex).reshape(-1))
    used: set[int] = set()
    real_poles: list[float] = []
    complex_pairs: list[tuple[float, float]] = []
    tolerance = 1e-7
    for index, pole in enumerate(poles):
        if index in used:
            continue
        scale = max(1.0, abs(pole))
        if abs(pole.imag) <= tolerance * scale:
            real_poles.append(float(pole.real))
            used.add(index)
            continue
        candidates = [
            (
                abs(abs(other.imag) - abs(pole.imag)) + 0.1 * abs(other.real - pole.real),
                other_index,
                other,
            )
            for other_index, other in enumerate(poles)
            if other_index not in used and other_index != index and other.imag * pole.imag < 0.0
        ]
        if candidates:
            _, other_index, other = min(candidates, key=lambda item: item[0])
        else:
            other_index, other = -1, pole.conjugate()
        if other_index >= 0:
            sigma = 0.5 * (pole.real + other.real)
            omega = 0.5 * (abs(pole.imag) + abs(other.imag))
            used.add(index)
            used.add(other_index)
        else:
            sigma = pole.real
            omega = abs(pole.imag)
            used.add(index)
        complex_pairs.append((float(sigma), float(omega)))
    raw: list[float] = list(real_poles)
    for sigma, omega in complex_pairs:
        raw.extend([sigma, omega])
    decoded: list[complex] = [complex(pole, 0.0) for pole in real_poles]
    for sigma, omega in complex_pairs:
        decoded.append(complex(sigma, omega))
        decoded.append(complex(sigma, -omega))
    return {
        "poles_rad_per_s": raw,
        "real_pole_count": len(real_poles),
        "complex_pair_count": len(complex_pairs),
        "decoded_poles_rad_per_s": _complex_array_to_jsonable(decoded),
    }


def _idem_real_basis_design_matrix(freqs_hz: np.ndarray, pole_block: dict[str, Any]) -> np.ndarray:
    raw = np.asarray(pole_block["poles_rad_per_s"], dtype=float)
    nr = int(pole_block.get("real_pole_count") or 0)
    nc = int(pole_block.get("complex_pair_count") or 0)
    s = 2j * np.pi * freqs_hz
    columns = []
    for pole in raw[:nr]:
        columns.append(1.0 / (s - pole))
    offset = nr
    for pair_index in range(nc):
        pair_offset = offset + 2 * pair_index
        if pair_offset + 1 >= len(raw):
            break
        sigma = float(raw[pair_offset])
        omega = abs(float(raw[pair_offset + 1]))
        pole = complex(sigma, omega)
        conjugate = complex(sigma, -omega)
        columns.append(1.0 / (s - pole) + 1.0 / (s - conjugate))
        columns.append(1j * (1.0 / (s - pole) - 1.0 / (s - conjugate)))
    columns.append(np.ones(len(freqs_hz), dtype=complex))
    return np.column_stack(columns)


def _solve_real_basis_response(
    design: np.ndarray,
    rhs: np.ndarray,
    *,
    weights: np.ndarray | None = None,
    rcond: float | None = None,
) -> tuple[np.ndarray, int, np.ndarray]:
    if weights is not None:
        design = design * weights[:, np.newaxis]
        rhs = rhs * weights
    real_design = np.vstack([design.real, design.imag])
    real_rhs = np.concatenate([rhs.real, rhs.imag])
    column_scale = np.linalg.norm(real_design, axis=0)
    column_scale[column_scale == 0.0] = 1.0
    scaled_design = real_design / column_scale[np.newaxis, :]
    scaled_coeffs, _, rank, singular_values = np.linalg.lstsq(scaled_design, real_rhs, rcond=rcond)
    return scaled_coeffs / column_scale, int(rank), singular_values


def _condition_number_from_singular_values(singular_values: np.ndarray) -> float:
    if len(singular_values) == 0 or singular_values[-1] == 0:
        return math.inf
    return float(singular_values[0] / singular_values[-1])


def _s_rms_error(original_s: np.ndarray, fitted_s: np.ndarray) -> float:
    error = original_s - fitted_s
    return float(math.sqrt(float(np.sum(np.mean(np.square(np.abs(error)), axis=0)))))


def _s_mean_rms_error(original_s: np.ndarray, fitted_s: np.ndarray) -> float:
    original = np.asarray(original_s, dtype=complex)
    fitted = np.asarray(fitted_s, dtype=complex)
    if original.shape != fitted.shape or original.ndim != 3 or original.shape[1] != original.shape[2]:
        raise ValueError("original_s and fitted_s must have matching shape (frequency_points, nports, nports)")
    return _s_rms_error(original, fitted) / float(original.shape[1])


def _relative_rms_error(original: np.ndarray, fitted: np.ndarray) -> float:
    denominator = float(np.sum(np.square(np.abs(original))))
    if denominator == 0.0:
        return math.inf
    numerator = float(np.sum(np.square(np.abs(original - fitted))))
    return float(math.sqrt(numerator / denominator))


def _z_log_magnitude_rms_error(original_z: Any, fitted_z: Any, floor: float = 1e-300) -> float:
    original = np.asarray(original_z, dtype=complex)
    fitted = np.asarray(fitted_z, dtype=complex)
    if original.shape != fitted.shape:
        raise ValueError("original_z and fitted_z must have the same shape")
    original_mag = np.maximum(np.abs(original), floor)
    fitted_mag = np.maximum(np.abs(fitted), floor)
    delta = np.log10(fitted_mag / original_mag)
    finite_delta = delta[np.isfinite(delta)]
    if finite_delta.size == 0:
        return math.inf
    return float(math.sqrt(float(np.mean(np.square(finite_delta)))))


def _last_value(values: Any) -> Any:
    if not values:
        return None
    if isinstance(values, list):
        return values[-1]
    return values


def _xml_bool(value: bool) -> str:
    return "true" if value else "false"


def _append_xml_text(parent: ET.Element, tag: str, text: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = text
    return element


def _format_idem_float(value: Any) -> str:
    if isinstance(value, str) and value.strip().upper() == "INF":
        return "INF"
    if isinstance(value, float) and math.isinf(value):
        return "INF"
    return f"{float(value):.16g}"


def _validate_bool(name: str, value: bool) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a bool")


def _validate_nonnegative_int(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _validate_positive_int(name: str, value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _validate_positive_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")


def _validate_nonnegative_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0.0:
        raise ValueError(f"{name} must be a non-negative finite number")


def _validate_unit_interval_positive(name: str, value: float) -> None:
    _validate_positive_finite(name, value)
    if float(value) > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


def _validate_choice(name: str, value: str, choices: set[str]) -> None:
    if not isinstance(value, str) or value not in choices:
        expected = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {expected}")


def _validate_adaptive_fitting_inputs(
    touchstone_path: Path,
    options_xml_path: Path,
    *,
    order_min: int,
    order_step: int,
    order_max: int,
    target: float,
    bandwidth_hz: float,
    threads: int,
) -> None:
    if not touchstone_path.is_file():
        raise FileNotFoundError(f"Touchstone input does not exist: {touchstone_path}")
    if not options_xml_path.is_file():
        raise FileNotFoundError(f"IdEM adaptive options XML does not exist: {options_xml_path}")
    _validate_positive_int("order_min", order_min)
    _validate_positive_int("order_step", order_step)
    _validate_positive_int("order_max", order_max)
    if order_min > order_max:
        raise ValueError("order_min must be <= order_max")
    _validate_positive_finite("target", target)
    _validate_positive_finite("bandwidth_hz", bandwidth_hz)
    _validate_positive_int("threads", threads)


def _normalize_positive_integer_or_inf(name: str, value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer or INF")
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.upper() == "INF":
            return "INF"
        if stripped.isdecimal() and int(stripped) >= 1:
            return str(int(stripped))
        raise ValueError(f"{name} must be a positive integer or INF")
    if isinstance(value, int) and value >= 1:
        return str(value)
    if isinstance(value, float) and math.isinf(value):
        return "INF"
    raise ValueError(f"{name} must be a positive integer or INF")


def _normalize_positive_float_or_inf(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive number or INF")
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.upper() == "INF":
            return math.inf
        try:
            value = float(stripped)
        except ValueError as exc:
            raise ValueError(f"{name} must be a positive number or INF") from exc
    numeric = float(value)
    if math.isinf(numeric) and numeric > 0.0:
        return math.inf
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name} must be a positive number or INF")
    return numeric


def _normalize_absolute_frequency_weight_points(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    if not points:
        return ()
    if len(points) < 2:
        raise ValueError("absolute_frequency_weight_points must contain at least two points")
    normalized: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, tuple) or len(point) != 2:
            raise ValueError("absolute_frequency_weight_points entries must be (frequency, weight)")
        if isinstance(point[0], bool) or isinstance(point[1], bool):
            raise ValueError("absolute frequency weight points must use numeric frequency and weight values")
        frequency_hz = float(point[0])
        weight = float(point[1])
        if not math.isfinite(frequency_hz) or frequency_hz < 0.0:
            raise ValueError("absolute frequency weight frequencies must be finite and non-negative")
        if not math.isfinite(weight) or weight <= 0.0:
            raise ValueError("absolute frequency weights must be positive finite numbers")
        normalized.append((frequency_hz, weight))
    return tuple(normalized)


def _escape_xml_text(value: str) -> str:
    element = ET.Element("value")
    element.text = value
    rendered = ET.tostring(element, encoding="unicode")
    return rendered.removeprefix("<value>").removesuffix("</value>")
