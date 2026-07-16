from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
from typing import TYPE_CHECKING, Any

from agent_spice.deck.builder import write_case_artifacts
from agent_spice.hspice.alter import split_alter_cases
from agent_spice.hspice.audit import audit_deck
from agent_spice.hspice.converter import convert_hspice_deck
from agent_spice.hspice.results import parse_ngspice_measurements, write_ngspice_waveform_csv
from agent_spice.project import prepare_run_directory
from agent_spice.sparam.fitting import SParamFitConfig, fit_touchstone_to_spice_target
from agent_spice.sparam.target_fit import SParamFitTarget
from agent_spice.sparam.io import load_touchstone_metadata
from agent_spice.sparam.artifacts import evaluate_fitted_s, write_cadence_rfm, write_cadence_rfm_wrapper, write_fitted_touchstone
from agent_spice.sparam.rational_lft import exact_y_to_s_rational
from agent_spice.sparam.y_pr import enforce_y_positive_real_kyp
from agent_spice.sparam.yparam import (
    YParamFitConfig,
    append_yparam_progress,
    fit_touchstone_to_y_spice_auto_order,
)
from agent_spice.sparam.y_tran_tuning import YTranTuneConfig, parse_float_csv, tune_y_rfm_for_tran


SPARAM_IDEM_FAST_CANDIDATES_LARGE_PORT = "9,10,12,14,17,20"
SPARAM_IDEM_FAST_TARGET_MEAN_RMS = 0.002
SPARAM_IDEM_FAST_PASSIVITY_PROFILE_LARGE_PORT = {
    "passivity_samples": 64,
    "passivity_max_iterations": 0,
    "passivity_perturb_constant": False,
    "passivity_global_damping_fallback": True,
    "passivity_global_damping_safety_margin": 1e-7,
    "passivity_spectral_projection_fallback": False,
    "passivity_spectral_projection_iterations": 0,
}
SPARAM_IDEM_FAST_PASSIVITY_OPTION_FLAGS = {
    "passivity_samples": "--passivity-samples",
    "passivity_max_iterations": "--passivity-max-iterations",
    "passivity_active_variables": "--passivity-active-variables",
    "passivity_f_max": "--passivity-f-max",
}


def fit_sparam_cascade(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from agent_spice.sparam.cascade import fit_sparam_cascade as implementation

    return implementation(*args, **kwargs)


def _cascade_fit_config(**kwargs: Any) -> Any:
    from agent_spice.sparam.cascade import CascadeFitConfig

    return CascadeFitConfig(**kwargs)

_EXPERT_TUNING_OPTION_FLAGS = {
    "init_pole_spacing": ("--pole-spacing", "--init-pole-spacing"),
    "fit_max_iterations": ("--fit-iterations", "--fit-max-iterations"),
    "high_frequency_complex_pairs": ("--hf-complex-pairs", "--high-frequency-complex-pairs"),
    "high_frequency_complex_pair_damping": ("--hf-pair-damping", "--high-frequency-complex-pair-damping"),
    "high_frequency_complex_pair_lower_fraction": (
        "--hf-pair-start-fraction",
        "--high-frequency-complex-pair-lower-fraction",
    ),
    "passivity_max_iterations": ("--passivity-max-iterations",),
    "passivity_samples": ("--passivity-samples",),
    "passivity_active_variables": ("--passivity-active-variables",),
}


def _load_expert_tuning_profile(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read tuning profile {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid tuning profile JSON {path}: {exc.msg}") from exc
    if not isinstance(payload, dict) or set(payload) != {"version", "overrides"}:
        raise ValueError("tuning profile must contain exactly 'version' and 'overrides'")
    if payload["version"] != 1 or isinstance(payload["version"], bool):
        raise ValueError("tuning profile version must be 1")
    overrides = payload["overrides"]
    if not isinstance(overrides, dict):
        raise ValueError("tuning profile overrides must be an object")
    unknown = sorted(set(overrides) - set(_EXPERT_TUNING_OPTION_FLAGS))
    if unknown:
        raise ValueError(f"Unsupported tuning profile override(s): {', '.join(unknown)}")

    validated: dict[str, Any] = {}
    for name, value in overrides.items():
        if name == "init_pole_spacing":
            if value not in {"lin", "log", "resonance"}:
                raise ValueError("init_pole_spacing must be lin, log, or resonance")
        elif name in {"fit_max_iterations", "high_frequency_complex_pairs", "passivity_samples", "passivity_active_variables"}:
            minimum = 0 if name == "high_frequency_complex_pairs" else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        elif name == "passivity_max_iterations":
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("passivity_max_iterations must be an integer >= 0")
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
            if not 0.0 < float(value) <= 1.0:
                raise ValueError(f"{name} must be in (0, 1]")
        validated[name] = value
    return validated


def _apply_expert_tuning_overrides(args: Any, argv: list[str]) -> dict[str, Any] | None:
    direct = {
        name: getattr(args, name)
        for name, flags in _EXPERT_TUNING_OPTION_FLAGS.items()
        if any(_argument_was_explicit(argv, flag) for flag in flags)
    }
    profile_values: dict[str, Any] = {}
    if args.tuning_profile is not None:
        profile_values = _load_expert_tuning_profile(args.tuning_profile)
        for name, value in profile_values.items():
            if name not in direct:
                setattr(args, name, value)
    if not direct and not profile_values:
        return None
    return {
        "profile_path": None if args.tuning_profile is None else str(args.tuning_profile),
        "values": {**profile_values, **direct},
    }


if TYPE_CHECKING:
    from agent_spice.backend.xyce import XyceXdmRunResult


def _run_backend(backend_name: str, deck_path: Path, run_dir: Path):
    if backend_name == "ngspice":
        from agent_spice.backend.ngspice import NgspiceBackend

        return NgspiceBackend().run(deck_path, cwd=run_dir)
    if backend_name == "xyce":
        from agent_spice.backend.xyce import XyceBackend

        return XyceBackend().run(deck_path, cwd=run_dir)
    raise ValueError(f"Unsupported backend '{backend_name}'")


def _write_xyce_xdm_summary(run_dir: Path, result: "XyceXdmRunResult") -> None:
    summary = {
        "backend": "xyce-xdm",
        "ok": result.ok,
        "returncode": result.returncode,
        "stages": {
            "xdm": {
                "ok": result.xdm.ok,
                "returncode": result.xdm.returncode,
                "stdout": "xdm.stdout.log",
                "stderr": "xdm.stderr.log",
            },
            "xyce": None
            if result.xyce is None
            else {
                "ok": result.xyce.ok,
                "returncode": result.xyce.returncode,
                "stdout": "xyce.stdout.log",
                "stderr": "xyce.stderr.log",
            },
        },
    }
    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_backend_summary(run_dir: Path, backend_name: str, result: Any) -> None:
    waveform = run_dir / "waveform.csv"
    summary: dict[str, Any] = {
        "schema_version": 1,
        "backend": backend_name,
        "ok": result.ok,
        "returncode": result.returncode,
        "logs": {"stdout": "stdout.log", "stderr": "stderr.log"},
        "waveform": None,
        "measurements": [],
        "error": None if result.ok else result.stderr.strip() or result.stdout.strip() or "backend failed without output",
    }
    if backend_name == "ngspice":
        waveform_rows = write_ngspice_waveform_csv(result.stdout, waveform)
        summary["waveform"] = {
            "path": "waveform.csv",
            "format": "csv",
            "exists": waveform.exists(),
            "rows": waveform_rows,
        }
        summary["measurements"] = parse_ngspice_measurements(result.stdout)
    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stage_local_dependencies(source_root: Path, run_dir: Path, text: str, report: Any, backend_name: str) -> None:
    """Stage relative dependencies, converting each included netlist for ngspice."""
    source_root = source_root.resolve()
    run_root = run_dir.resolve()
    root_audit = audit_deck(text)
    pending = [(source_root, path, True) for path in (*root_audit.includes, *(item[0] for item in root_audit.libraries))]
    seen: set[Path] = set()
    while pending:
        parent, reference, report_missing = pending.pop()
        ref_path = Path(reference)
        if ref_path.is_absolute():
            report.add_unsupported(reference, "absolute_include_path_not_staged")
            continue
        source = (parent / ref_path).resolve()
        if source in seen:
            continue
        seen.add(source)
        try:
            relative = source.relative_to(source_root)
        except ValueError:
            report.add_unsupported(reference, "include_outside_source_directory")
            continue
        target = (run_root / relative).resolve()
        if not target.is_relative_to(run_root):
            report.add_unsupported(reference, "include_path_escapes_run_directory")
            continue
        if not source.is_file():
            if report_missing:
                report.add_unsupported(reference, "include_not_found")
            continue
        source_text = source.read_text(encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        if backend_name == "ngspice":
            conversion = convert_hspice_deck(source_text, backend=backend_name)
            target.write_text(conversion.deck_text, encoding="utf-8")
            report.actions.extend(conversion.report.actions)
            report.unsupported.extend(conversion.report.unsupported)
        else:
            target.write_text(source_text, encoding="utf-8")
        nested = audit_deck(source_text)
        pending.extend((source.parent, nested_ref, False) for nested_ref in nested.includes)
        pending.extend((source.parent, nested_ref, False) for nested_ref, _ in nested.libraries)


def _stable_source_path(deck_path: Path) -> str:
    if not deck_path.is_absolute():
        return deck_path.as_posix()
    try:
        return deck_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return deck_path.name


def _case_metadata(deck_id: str, case_name: str) -> tuple[str, str | None]:
    suffix = case_name.removeprefix(f"{deck_id}__")
    if suffix == "base":
        return "base", None
    match = re.fullmatch(r"alter_\d{3}(?:_(?P<label>.+))?", suffix)
    if match:
        return "alter", match.group("label")
    return "case", suffix or None


_HSPICE_S_ELEMENT = re.compile(r"(?ims)^\s*(S\S+)\s+([^\n]+(?:\n\s*\+[^\n]+)*)")
_TSTONE_FILE = re.compile(r"\bTSTONEFILE\s*=\s*(['\"]?)([^\s'\"]+)\1", re.IGNORECASE)


def _compile_touchstone_s_elements(text: str, source_dir: Path, run_dir: Path, report: Any) -> tuple[str, list[str]]:
    """Replace HSPICE S-elements with fitted ngspice subcircuits for TRAN."""
    messages: list[str] = []

    def replace(match: re.Match[str]) -> str:
        instance, raw_body = match.group(1), match.group(2)
        tstone = _TSTONE_FILE.search(raw_body)
        if tstone is None:
            return match.group(0)
        path = (source_dir / tstone.group(2)).resolve()
        if not path.is_file():
            report.add_unsupported(match.group(0).splitlines()[0], "touchstone_file_not_found")
            return match.group(0)
        metadata = load_touchstone_metadata(path)
        tokens = raw_body.replace("\n", " ").replace("+", " ").split()
        nodes = [token for token in tokens if "=" not in token][: metadata.ports + 1]
        if len(nodes) != metadata.ports + 1 or nodes[-1] != "0":
            report.add_unsupported(match.group(0).splitlines()[0], "touchstone_s_element_requires_common_ground_reference")
            return match.group(0)
        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", instance)
        subckt_name = f"auto_sparam_{safe_name}"
        output_dir = run_dir / "sparam"
        output_dir.mkdir(parents=True, exist_ok=True)
        spice_path = output_dir / f"{safe_name}.sp"
        fit_log = output_dir / f"{safe_name}.fit.log"
        target = SParamFitTarget(mean_rms=0.001, passivity="enforce", max_order=100)
        result = fit_touchstone_to_spice_target(
            path, spice_path, target=target,
            config=SParamFitConfig(mode="auto", model_order_max=100, target_error=0.001, subckt_name=subckt_name),
            report_path=output_dir / f"{safe_name}.fit_report.json",
            html_report_path=output_dir / f"{safe_name}.fit_report.html",
            log_path=fit_log,
            fitted_touchstone_path=output_dir / f"{safe_name}_fitted{path.suffix.lower()}",
        )
        best = getattr(result, "best_trial", None)
        actual_rms = None if best is None else best.final_mean_rms
        status = "FIT_PASS" if result.target_met else "FIT_FALLBACK_BEST_RMS"
        messages.append(f"S-PARAM AUTO-FIT {status} instance={instance} file={path.name} target_rms=0.001 actual_rms={actual_rms} output={spice_path.name}")
        report.add_action("rewrite_touchstone_s_element", instance, f"{status}; subckt={subckt_name}; rms={actual_rms}")
        return f".include '{spice_path.as_posix()}'\nX{instance[1:]} {' '.join(nodes[:-1])} {subckt_name}"

    return _HSPICE_S_ELEMENT.sub(replace, text), messages


def _quality_gate_failure(result: Any, allow_warnings: bool) -> str | None:
    quality_report = getattr(result, "quality_report", None)
    if quality_report is None:
        return "quality gate unavailable: fit result did not include a quality report"
    status = getattr(quality_report, "status", None)
    if status == "PASS":
        return None
    if status == "WARN" and allow_warnings:
        return None

    blocking_reasons = list(getattr(quality_report, "blocking_reasons", []) or [])
    warnings = list(getattr(quality_report, "warnings", []) or [])
    reasons = blocking_reasons if status == "FAIL" else warnings
    if not reasons:
        reasons = blocking_reasons + warnings
    reason_text = ", ".join(reasons) if reasons else str(status or "unknown")
    return f"quality gate failed: status={status or 'unknown'}, reasons={reason_text}"


def run_touchstone_banded_comparison(*args: Any, **kwargs: Any) -> Any:
    from agent_spice.sparam.metrics import run_touchstone_banded_comparison as impl

    return impl(*args, **kwargs)


def run_sparam_benchmarks(*args: Any, **kwargs: Any) -> Any:
    from agent_spice.sparam.benchmark import run_sparam_benchmarks as impl

    return impl(*args, **kwargs)


def _idem_tool(name: str) -> Any:
    from agent_spice.sparam import idem

    return getattr(idem, name)


def run_idem_initial_iteration_probe(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("run_idem_initial_iteration_probe")(*args, **kwargs)


def run_idem_fixed_pole_residue_probe(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("run_idem_fixed_pole_residue_probe")(*args, **kwargs)


def run_idem_residue_sweep(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("run_idem_residue_sweep")(*args, **kwargs)


def run_idem_passivity(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("run_idem_passivity")(*args, **kwargs)


def run_local_pole_relocation_probe(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("run_local_pole_relocation_probe")(*args, **kwargs)


def run_local_pole_relocation_sweep(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("run_local_pole_relocation_sweep")(*args, **kwargs)


def run_local_idem_like_fit(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("run_local_idem_like_fit")(*args, **kwargs)


def evaluate_local_idem_like_model(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("evaluate_local_idem_like_model")(*args, **kwargs)


def refine_local_idem_like_model(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("refine_local_idem_like_model")(*args, **kwargs)


def export_local_idem_like_touchstone(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("export_local_idem_like_touchstone")(*args, **kwargs)


def export_local_idem_like_state_space(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("export_local_idem_like_state_space")(*args, **kwargs)


def evaluate_local_idem_like_state_space(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("evaluate_local_idem_like_state_space")(*args, **kwargs)


def write_json_report(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("write_json_report")(*args, **kwargs)


def write_jsonl_report(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("write_jsonl_report")(*args, **kwargs)


def write_probe_csv(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("write_probe_csv")(*args, **kwargs)


def write_probe_jsonl(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("write_probe_jsonl")(*args, **kwargs)


def write_relocation_csv(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("write_relocation_csv")(*args, **kwargs)


def write_residue_sweep_csv(*args: Any, **kwargs: Any) -> Any:
    return _idem_tool("write_residue_sweep_csv")(*args, **kwargs)


def _parse_int_list(value: str) -> list[int]:
    try:
        items = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError(f"Expected comma-separated integers, got '{value}'") from exc
    if not items:
        raise ValueError("Expected at least one integer")
    return items


def _parse_float_list(value: str) -> list[float]:
    try:
        items = [float(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError(f"Expected comma-separated numbers, got '{value}'") from exc
    if not items:
        raise ValueError("Expected at least one number")
    return items


def _parse_choice_list(value: str, allowed: set[str], name: str) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise ValueError(f"Expected at least one {name}")
    unsupported = sorted(set(items) - allowed)
    if unsupported:
        raise ValueError(f"Unsupported {name}: {', '.join(unsupported)}")
    return items


def _add_hidden_argument(parser: argparse.ArgumentParser, *flags: str, **kwargs: Any) -> None:
    kwargs.setdefault("help", argparse.SUPPRESS)
    parser.add_argument(*flags, **kwargs)


def _expand_model_paths(models: list[Path] | None, model_globs: list[str] | None) -> list[Path]:
    paths = list(models or [])
    for pattern in model_globs or []:
        matches = sorted(Path.cwd().glob(pattern))
        if not matches:
            raise ValueError(f"Model glob matched no files: {pattern}")
        paths.extend(matches)
    unique: list[Path] = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    if not unique:
        raise ValueError("At least one --model or --model-glob is required")
    return unique


def _argument_was_explicit(argv: list[str], option: str) -> bool:
    return option in argv or any(item.startswith(f"{option}=") for item in argv)


def _apply_idem_like_recipe(args: Any, argv: list[str]) -> None:
    if getattr(args, "recipe", "default") != "idem-compact":
        return
    defaults = {
        "--order": ("order", 32),
        "--iterations": ("iterations", 2),
        "--pole-spacing": ("pole_spacing", "log"),
        "--pole-f-min": ("pole_f_min", 1.0e7),
        "--pole-pairing": ("pole_pairing", "conjugate"),
        "--residue-basis": ("residue_basis", "real-state"),
        "--fit-max-frequency-points": ("fit_max_frequency_points", 128),
        "--max-pole-responses": ("max_pole_responses", 128),
    }
    for option, (attribute, value) in defaults.items():
        if not _argument_was_explicit(argv, option):
            setattr(args, attribute, value)


def _parse_labeled_paths(values: list[str] | None, option_name: str) -> dict[str, Path]:
    labeled_paths: dict[str, Path] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"expected {option_name} LABEL=PATH, got '{value}'")
        label, path = value.split("=", 1)
        label = label.strip()
        path = path.strip()
        if not label or not path:
            raise ValueError(f"expected {option_name} LABEL=PATH, got '{value}'")
        if label in labeled_paths:
            raise ValueError(f"duplicate model label '{label}'")
        labeled_paths[label] = Path(path)
    if not labeled_paths:
        raise ValueError(f"at least one {option_name} LABEL=PATH is required")
    return labeled_paths


def _parse_tuple_int(val: Any) -> tuple[int, ...] | None:
    if val is None:
        return None
    if isinstance(val, tuple):
        return val
    if isinstance(val, list):
        return tuple(val)
    if isinstance(val, int):
        return (val,)
    val_str = str(val).strip()
    if not val_str:
        return ()
    return tuple(int(x) for x in val_str.split(","))


def _parse_tuple_float(val: Any) -> tuple[float, ...] | None:
    if val is None:
        return None
    if isinstance(val, tuple):
        return val
    if isinstance(val, list):
        return tuple(val)
    if isinstance(val, (int, float)):
        return (float(val),)
    val_str = str(val).strip()
    if not val_str:
        return ()
    return tuple(float(x) for x in val_str.split(","))


def _parse_frequency_bands(value: Any) -> tuple[tuple[float, float], ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    text = str(value).strip()
    if not text:
        return ()
    bands: list[tuple[float, float]] = []
    for item in text.split(","):
        part = item.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Expected frequency band LO:HI, got '{part}'")
        lo_text, hi_text = part.split(":", 1)
        try:
            lo = float(lo_text.strip())
            hi = float(hi_text.strip())
        except ValueError as exc:
            raise ValueError(f"Expected numeric frequency band, got '{part}'") from exc
        if not lo < hi:
            raise ValueError(f"Expected frequency band LO < HI, got '{part}'")
        bands.append((lo, hi))
    return tuple(bands)


def _parse_priority_bands(values: Any) -> tuple[tuple[float, float, float, float], ...]:
    if values is None:
        return ()
    items = values if isinstance(values, (list, tuple)) else [values]
    bands: list[tuple[float, float, float, float]] = []
    for raw_item in items:
        parts = [part.strip() for part in str(raw_item).split(":")]
        if len(parts) not in {3, 4}:
            raise ValueError(
                f"Expected priority band F_MIN:F_MAX:RMS_TARGET[:WEIGHT], got '{raw_item}'"
            )
        try:
            f_min = float(parts[0])
            f_max = float(parts[1])
            rms_target = float(parts[2])
            weight = 1.0 if len(parts) == 3 else float(parts[3])
        except ValueError as exc:
            raise ValueError(f"Expected numeric priority band, got '{raw_item}'") from exc
        if not all(math.isfinite(value) for value in (f_min, f_max, rms_target, weight)):
            raise ValueError(f"Priority band values must be finite, got '{raw_item}'")
        if f_min < 0.0 or f_min >= f_max:
            raise ValueError(f"Priority band must satisfy 0 <= F_MIN < F_MAX, got '{raw_item}'")
        if rms_target <= 0.0:
            raise ValueError(f"Priority band RMS target must be > 0, got '{raw_item}'")
        if weight <= 0.0:
            raise ValueError(f"Priority band weight must be > 0, got '{raw_item}'")
        bands.append((f_min, f_max, rms_target, weight))
    return tuple(bands)


def check_modal_quality(result: Any, args: Any) -> dict[str, Any]:
    checks = []
    blocking_reasons = []

    # s_rms_error
    s_val = result.s_rms_error
    s_max = getattr(args, "max_s_rms_error", None)
    s_passed = True
    if s_max is not None and s_val is not None and s_val > s_max:
        s_passed = False
        blocking_reasons.append(f"s_rms_error={s_val:.6f} exceeds max {s_max}")
    checks.append({"metric": "s_rms_error", "value": s_val, "max": s_max, "passed": s_passed})

    # z_log_magnitude_rms_error
    z_val = result.z_log_magnitude_rms_error
    z_max = getattr(args, "max_z_log_rms_error", None)
    z_passed = True
    if z_max is not None and z_val > z_max:
        z_passed = False
        blocking_reasons.append(f"z_log_magnitude_rms_error={z_val:.6f} exceeds max {z_max}")
    checks.append({"metric": "z_log_magnitude_rms_error", "value": z_val, "max": z_max, "passed": z_passed})

    # diagonal_z_log_magnitude_rms_error
    d_val = result.diagonal_z_log_magnitude_rms_error
    d_max = getattr(args, "max_diag_z_log_rms_error", None)
    d_passed = True
    if d_max is not None and d_val > d_max:
        d_passed = False
        blocking_reasons.append(f"diagonal_z_log_magnitude_rms_error={d_val:.6f} exceeds max {d_max}")
    checks.append({"metric": "diagonal_z_log_magnitude_rms_error", "value": d_val, "max": d_max, "passed": d_passed})

    # basis_projection_z_log_magnitude_rms_error
    p_val = result.basis_projection_z_log_magnitude_rms_error
    p_max = getattr(args, "max_basis_projection_z_log_rms_error", None)
    p_passed = True
    if p_max is not None and p_val > p_max:
        p_passed = False
        blocking_reasons.append(f"basis_projection_z_log_magnitude_rms_error={p_val:.6f} exceeds max {p_max}")
    checks.append({"metric": "basis_projection_z_log_magnitude_rms_error", "value": p_val, "max": p_max, "passed": p_passed})

    # scalar_fit_order
    o_val = result.scalar_fit_order
    o_max = getattr(args, "max_scalar_fit_order", None)
    o_passed = True
    if o_max is not None and o_val > o_max:
        o_passed = False
        blocking_reasons.append(f"scalar_fit_order={o_val} exceeds max {o_max}")
    checks.append({"metric": "scalar_fit_order", "value": o_val, "max": o_max, "passed": o_passed})

    status = "FAIL" if blocking_reasons else "PASS"
    return {
        "status": status,
        "checks": checks,
        "blocking_reasons": blocking_reasons,
    }



def _apply_modal_auto_preset(args: Any, argv: list[str]) -> None:
    if not getattr(args, "auto_preset", None):
        return

    def is_explicit(opt: str) -> bool:
        return opt in argv

    ports = 2
    if getattr(args, "touchstone", None):
        import re
        match = re.search(r"\.s(\d+)p", str(args.touchstone).lower())
        if match:
            ports = int(match.group(1))
        else:
            try:
                from agent_spice.sparam.io import load_touchstone_metadata
                meta = load_touchstone_metadata(args.touchstone)
                ports = meta.ports
            except Exception:
                pass

    preset = args.auto_preset

    if preset == "compact":
        if ports >= 30:
            if not is_explicit("--mode-count"):
                args.mode_count = 28
            if not is_explicit("--basis-frequency-sample-count"):
                args.basis_frequency_sample_count = 21
            if not is_explicit("--scalar-fit-order"):
                args.scalar_fit_order = 44
            if not is_explicit("--frequency-sample-count"):
                args.frequency_sample_count = 256
            if not is_explicit("--frequency-sample-head-count"):
                args.frequency_sample_head_count = 3
            if not is_explicit("--shared-pole-trace-count"):
                args.shared_pole_trace_count = 2
            if not is_explicit("--auto-order-candidates"):
                args.auto_order_candidates = "32,36,40,44"
            if not is_explicit("--auto-order-max-z-log-rms-error"):
                args.auto_order_max_z_log_rms_error = 0.49
            if not is_explicit("--auto-order-max-diag-z-log-rms-error"):
                args.auto_order_max_diag_z_log_rms_error = 0.14
            if not is_explicit("--max-z-log-rms-error"):
                args.max_z_log_rms_error = 0.49
            if not is_explicit("--max-diag-z-log-rms-error"):
                args.max_diag_z_log_rms_error = 0.14
            if not is_explicit("--max-scalar-fit-order"):
                args.max_scalar_fit_order = 44
            if hasattr(args, "auto_basis_mode_counts"):
                delattr(args, "auto_basis_mode_counts")
            if hasattr(args, "auto_pole_dampings"):
                delattr(args, "auto_pole_dampings")
        else:
            mode_c = 18 if ports >= 10 else 1
            if not is_explicit("--mode-count"):
                args.mode_count = mode_c
            if not is_explicit("--auto-basis-mode-counts"):
                args.auto_basis_mode_counts = f"{mode_c-1},{mode_c}" if mode_c > 1 else "1"
            if not is_explicit("--auto-basis-anchor-port-counts"):
                args.auto_basis_anchor_port_counts = "3" if mode_c > 1 else "1"
            if not is_explicit("--auto-basis-anchor-candidate-count"):
                args.auto_basis_anchor_candidate_count = 5 if mode_c > 1 else 2
            if not is_explicit("--auto-basis-anchor-combo-count"):
                args.auto_basis_anchor_combo_count = 4 if mode_c > 1 else 1
            if not is_explicit("--auto-order-candidates"):
                args.auto_order_candidates = "128,160,192,224"
            if not is_explicit("--auto-order-max-z-log-rms-error"):
                args.auto_order_max_z_log_rms_error = 0.38
            if not is_explicit("--auto-basis-diagonal-weight"):
                args.auto_basis_diagonal_weight = 0.25 if mode_c > 1 else 0.0
            if not is_explicit("--max-z-log-rms-error"):
                args.max_z_log_rms_error = 0.38
            if not is_explicit("--max-diag-z-log-rms-error"):
                args.max_diag_z_log_rms_error = 0.05
            if not is_explicit("--max-scalar-fit-order"):
                args.max_scalar_fit_order = 224

    elif preset == "high-accuracy":
        if ports >= 30:
            if not is_explicit("--mode-count"):
                args.mode_count = 28
            if not is_explicit("--basis-frequency-sample-count"):
                args.basis_frequency_sample_count = 21
            if not is_explicit("--scalar-fit-order"):
                args.scalar_fit_order = 56
            if not is_explicit("--frequency-sample-count"):
                args.frequency_sample_count = 256
            if not is_explicit("--frequency-sample-head-count"):
                args.frequency_sample_head_count = 3
            if not is_explicit("--shared-pole-trace-count"):
                args.shared_pole_trace_count = 2
            if not is_explicit("--auto-order-candidates"):
                args.auto_order_candidates = "44,48,52,56"
            if not is_explicit("--auto-order-max-z-log-rms-error"):
                args.auto_order_max_z_log_rms_error = 0.445
            if not is_explicit("--auto-order-max-diag-z-log-rms-error"):
                args.auto_order_max_diag_z_log_rms_error = 0.12
            if not is_explicit("--max-z-log-rms-error"):
                args.max_z_log_rms_error = 0.445
            if not is_explicit("--max-diag-z-log-rms-error"):
                args.max_diag_z_log_rms_error = 0.12
            if not is_explicit("--max-scalar-fit-order"):
                args.max_scalar_fit_order = 56
            if hasattr(args, "auto_basis_mode_counts"):
                delattr(args, "auto_basis_mode_counts")
            if hasattr(args, "auto_pole_dampings"):
                delattr(args, "auto_pole_dampings")
        else:
            mode_c = 18 if ports >= 10 else 1
            if not is_explicit("--mode-count"):
                args.mode_count = mode_c
            if not is_explicit("--auto-basis-mode-counts"):
                args.auto_basis_mode_counts = f"{mode_c-1},{mode_c}" if mode_c > 1 else "1"
            if not is_explicit("--auto-basis-anchor-port-counts"):
                args.auto_basis_anchor_port_counts = "3" if mode_c > 1 else "1"
            if not is_explicit("--auto-basis-anchor-candidate-count"):
                args.auto_basis_anchor_candidate_count = 5 if mode_c > 1 else 2
            if not is_explicit("--auto-basis-anchor-combo-count"):
                args.auto_basis_anchor_combo_count = 4 if mode_c > 1 else 1
            if not is_explicit("--auto-order-candidates"):
                args.auto_order_candidates = "160,192,224"
            if not is_explicit("--auto-order-max-z-log-rms-error"):
                args.auto_order_max_z_log_rms_error = 0.34
            if not is_explicit("--auto-basis-diagonal-weight"):
                args.auto_basis_diagonal_weight = 0.25 if mode_c > 1 else 0.0
            if not is_explicit("--max-z-log-rms-error"):
                args.max_z_log_rms_error = 0.34
            if not is_explicit("--max-diag-z-log-rms-error"):
                args.max_diag_z_log_rms_error = 0.05
            if not is_explicit("--max-scalar-fit-order"):
                args.max_scalar_fit_order = 224

    if is_explicit("--mode-count") and not is_explicit("--auto-basis-mode-counts"):
        args.auto_basis_mode_counts = str(args.mode_count)


def _apply_sparam_auto_preset(args: Any, argv: list[str]) -> None:
    if not getattr(args, "auto_preset", None):
        return

    def is_explicit(opt: str) -> bool:
        for flags in _EXPERT_TUNING_OPTION_FLAGS.values():
            if opt in flags:
                return any(_argument_was_explicit(argv, flag) for flag in flags)
        return _argument_was_explicit(argv, opt)

    ports = 2
    match = re.search(r"\.s(\d+)p", str(getattr(args, "touchstone", "")).lower())
    if match:
        ports = int(match.group(1))

    if args.auto_preset != "idem-fast":
        raise ValueError(f"Unsupported S-parameter auto preset '{args.auto_preset}'")

    candidates = None
    target = None
    if not is_explicit("--mode"):
        args.mode = "manual"
    if not is_explicit("--n-poles-real"):
        args.n_poles_real = 4
    if not is_explicit("--n-poles-cmplx"):
        args.n_poles_cmplx = 2 if ports >= 60 else (30 if ports >= 30 else 18)
    if not is_explicit("--init-pole-spacing"):
        args.init_pole_spacing = "lin"
    if not is_explicit("--fit-max-iterations"):
        args.fit_max_iterations = 14 if ports >= 60 else (6 if ports >= 30 else 5)
    if not is_explicit("--fit-max-frequency-points"):
        args.fit_max_frequency_points = None if ports >= 60 else 256
    if not is_explicit("--use-lightweight-network"):
        args.use_lightweight_network = True
    if ports >= 60 and not is_explicit("--high-frequency-complex-pairs"):
        args.high_frequency_complex_pairs = 2
    if ports >= 60 and not is_explicit("--high-frequency-complex-pair-damping"):
        args.high_frequency_complex_pair_damping = 0.03
    if ports >= 60 and not is_explicit("--high-frequency-complex-pair-lower-fraction"):
        args.high_frequency_complex_pair_lower_fraction = 0.68
    if ports >= 60 and not (
        is_explicit("--no-fit-dc") or is_explicit("--fit-enforce-dc")
    ):
        args.no_fit_dc = True
    if ports >= 60 and not is_explicit("--native-post-relocation-effective-order-max"):
        args.native_post_relocation_effective_order_max = 8
    if candidates is not None and not is_explicit("--auto-model-order-candidates"):
        args.auto_model_order_candidates = candidates
    if target is not None and not is_explicit("--auto-target-mean-rms-error"):
        args.auto_target_mean_rms_error = target
    if not is_explicit("--skip-passivity-enforce") and not is_explicit("--enforce-passivity"):
        args.skip_passivity_enforce = True
    if not is_explicit("--skip-passivity-check") and not is_explicit("--check-passivity"):
        args.skip_passivity_check = bool(args.skip_passivity_enforce)
    if ports >= 60 and not args.skip_passivity_enforce:
        for attr, value in SPARAM_IDEM_FAST_PASSIVITY_PROFILE_LARGE_PORT.items():
            option = SPARAM_IDEM_FAST_PASSIVITY_OPTION_FLAGS.get(attr)
            if option is not None and is_explicit(option):
                continue
            setattr(args, attr, value)


def _sparam_cli_advanced_passivity_kwargs(args: Any) -> dict[str, Any]:
    names = (
        "passivity_perturb_constant",
        "passivity_perturb_poles",
        "passivity_constant_only_candidates",
        "passivity_global_damping_fallback",
        "passivity_global_damping_mode",
        "passivity_global_damping_selective_min_frequency",
        "passivity_global_damping_safety_margin",
        "passivity_spectral_projection_fallback",
        "passivity_spectral_projection_max_delta_norm",
        "passivity_spectral_projection_max_response_delta_rms",
        "passivity_spectral_projection_max_sigma_regression",
        "passivity_spectral_projection_iterations",
        "passivity_spectral_projection_reweight_iterations",
        "passivity_spectral_projection_max_reference_rms_increase",
        "passivity_spectral_projection_max_reference_rms_total_increase",
        "passivity_spectral_projection_max_reference_rms_per_sigma_improvement",
        "passivity_spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement",
        "passivity_spectral_projection_late_current_clip_start_iteration",
        "passivity_spectral_projection_max_reference_band_sigma_regression",
        "passivity_spectral_projection_reference_band_holdout_start_iteration",
        "passivity_spectral_projection_include_all_reference_violations",
        "passivity_spectral_projection_weight_mode",
        "passivity_spectral_projection_weight_exponent",
        "passivity_spectral_projection_active_mode_candidate",
        "passivity_spectral_projection_active_mode_start_iteration",
        "passivity_spectral_projection_non_active_stop_iteration",
        "passivity_spectral_projection_active_mode_max_responses",
        "passivity_spectral_projection_active_mode_singular_modes",
        "passivity_spectral_projection_active_mode_band_singular_modes",
        "passivity_spectral_projection_active_mode_band_singular_mode_sample_count",
        "passivity_spectral_projection_active_mode_solver",
        "passivity_spectral_projection_active_mode_target_margin",
        "passivity_spectral_projection_active_mode_target_margin_start_iteration",
        "passivity_spectral_projection_active_mode_reference_max_points",
        "passivity_spectral_projection_active_mode_frequency_selection",
        "passivity_spectral_projection_active_mode_reference_weight",
        "passivity_spectral_projection_active_mode_reference_weight_mode",
        "passivity_spectral_projection_active_mode_reference_weight_candidates",
        "passivity_spectral_projection_active_mode_global_reference_points",
        "passivity_spectral_projection_active_mode_max_reference_rms_total_increase",
        "passivity_spectral_projection_active_mode_extra_scales",
        "passivity_spectral_projection_active_mode_extra_scales_min_sigma",
        "passivity_spectral_projection_current_clip_candidate",
        "passivity_spectral_projection_current_clip_reference_weight",
        "passivity_spectral_projection_candidate_reference_max_points",
        "passivity_spectral_projection_frequency_selection",
        "passivity_spectral_projection_band_sample_count",
        "passivity_spectral_projection_reference_rms_scope",
        "passivity_spectral_projection_reference_rms_chunk_size",
        "passivity_spectral_projection_candidate_selection_metric",
        "passivity_spectral_projection_post_damping_selection_start_iteration",
        "passivity_spectral_projection_post_damping_max_sigma_regression",
        "passivity_spectral_projection_mode_screen_candidates",
        "passivity_spectral_projection_mode_screen_modes",
        "passivity_constant_weight",
        "passivity_pole_weight",
    )
    fields = SParamFitConfig.__dataclass_fields__
    return {
        name: getattr(args, name, fields[name].default)
        for name in names
    }


def run_hspice(deck_path: Path, backend_name: str, output_root: Path, execute: bool = False) -> int:
    source = deck_path.read_text(encoding="utf-8")
    deck_id = deck_path.stem
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    source_path = _stable_source_path(deck_path)
    cases = split_alter_cases(source, stem=deck_path.stem)
    for case in cases:
        case_kind, alter_label = _case_metadata(deck_id, case.name)
        run_dir = prepare_run_directory(output_root, project_name=deck_id, case_name=case.name)
        prepared_text, preflight_messages = (
            _compile_touchstone_s_elements(case.text, deck_path.parent, run_dir, convert_hspice_deck(case.text, backend=backend_name).report)
            if backend_name == "ngspice" else (case.text, [])
        )
        conversion = convert_hspice_deck(prepared_text, backend=backend_name)
        for message in preflight_messages:
            conversion.report.add_action("auto_fit_touchstone", message)
        conversion.report.set_deck(deck_id=deck_id, source=source_path, sha256=source_hash)
        conversion.report.set_case(name=case.name, kind=case_kind, alter_label=alter_label)
        _stage_local_dependencies(deck_path.parent, run_dir, prepared_text, conversion.report, backend_name)
        conversion.report.finalize_summary()
        artifacts = write_case_artifacts(run_dir, conversion.deck_text, conversion.report, source_text=case.text)
        if preflight_messages:
            (run_dir / "preflight.log").write_text("\n".join(preflight_messages) + "\n", encoding="utf-8")
        hspice_case_path = run_dir / "case.sp"
        if backend_name == "xyce-xdm":
            hspice_case_path.write_text(case.text, encoding="utf-8")
        if execute:
            if backend_name == "xyce-xdm":
                from agent_spice.backend.xyce import XyceBackend

                result = XyceBackend().run_hspice_via_xdm(hspice_case_path, artifacts.deck_path, cwd=run_dir)
                _write_xyce_xdm_summary(run_dir, result)
                if not result.ok:
                    return result.returncode
                continue
            result = _run_backend(backend_name, artifacts.deck_path, run_dir)
            (run_dir / "stdout.log").write_text("\n".join(preflight_messages) + ("\n" if preflight_messages else "") + result.stdout, encoding="utf-8")
            (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
            _write_backend_summary(run_dir, backend_name, result)
            if not result.ok:
                return result.returncode
    return 0


def run_rfm(
    deck_path: Path,
    rfm_path: Path,
    output_root: Path,
    subcircuit_name: str,
    *,
    execute: bool = False,
    ngspice_executable: str = "ngspice",
    code_model: Path | None = None,
) -> int:
    """Prepare and optionally execute an RFM without vector fitting or macro expansion."""

    from agent_spice.sparam.rfm import RfmParseError
    from agent_spice.sparam.rfm_ngspice import (
        RfmNgspiceError,
        execute_rfm_run,
        prepare_rfm_run,
    )

    try:
        artifacts = prepare_rfm_run(
            deck_path,
            rfm_path,
            output_root=output_root,
            subcircuit_name=subcircuit_name,
        )
        if not execute:
            print(f"run-rfm status=PREPARED output={artifacts.run_dir}")
            return 0
        result = execute_rfm_run(
            artifacts,
            ngspice_executable=ngspice_executable,
            code_model=code_model,
        )
    except (OSError, ValueError, RfmParseError, RfmNgspiceError) as exc:
        print(f"run-rfm status=FAIL reason={exc}", file=sys.stderr)
        return 1
    status = "PASS" if result.ok else "FAIL"
    print(f"run-rfm status={status} returncode={result.returncode} output={artifacts.run_dir}")
    return 0 if result.ok else result.returncode or 1


def main(argv: list[str] | None = None) -> int:
    effective_argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="agent-spice")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run-hspice")
    run_parser.add_argument("deck", type=Path)
    run_parser.add_argument("--backend", choices=["ngspice", "xyce", "xyce-xdm"], default="ngspice")
    run_parser.add_argument("--output-root", type=Path, default=Path("runs"))
    run_parser.add_argument("--execute", action="store_true")

    rfm_parser = subparsers.add_parser(
        "run-rfm",
        description=(
            "Run a Cadence/HSPICE RFM directly through the Agent-Spice XSPICE N-port device; "
            "no vector fitting or expanded SPICE macro-model is used."
        ),
    )
    rfm_parser.add_argument("deck", type=Path, help="Circuit deck instantiating the generated subcircuit.")
    rfm_parser.add_argument("--rfm", type=Path, required=True, help="Input VERSION 200600 S-matrix RFM.")
    rfm_parser.add_argument("--subckt-name", default="rfm_direct")
    rfm_parser.add_argument("--output-root", type=Path, default=Path("runs"))
    rfm_parser.add_argument("--ngspice", default="ngspice", help="ngspice executable or absolute path.")
    rfm_parser.add_argument(
        "--code-model",
        type=Path,
        help="Override bundled rfm.cm (or set AGENT_SPICE_RFM_CODE_MODEL).",
    )
    rfm_parser.add_argument("--execute", action="store_true")

    fit_parser = subparsers.add_parser(
        "fit-sparam",
        description="Fit a Touchstone S-parameter file with the IdEM-fast baseline.",
    )
    fit_parser.add_argument("touchstone", type=Path, help="Input .sNp Touchstone file.")
    fit_parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Output SPICE subcircuit path; defaults to <input>_fitted.sp next to the input. "
            "On a target-search FAIL, exports the lowest-RMS candidate but returns FAIL."
        ),
    )
    fit_parser.add_argument("--report", type=Path, help="Override the default JSON fit report path.")
    fit_parser.add_argument("--html-report", type=Path, help="Override the default HTML fit report path.")
    fit_parser.add_argument(
        "--fitted-touchstone",
        type=Path,
        help="Override the default fitted .sNp Touchstone export path.",
    )
    fit_parser.add_argument("--rfm", type=Path, help="Override the default Cadence Broadband SPICE RFM export path.")
    fit_parser.add_argument("--rfm-wrapper", type=Path, help="Override the default SPICE wrapper path for the RFM.")
    fit_parser.add_argument(
        "--report-top-rms",
        type=int,
        default=5,
        help="Number of worst RMS S-parameter elements to plot in the HTML report (default: 5).",
    )
    fit_parser.add_argument("--log", type=Path, help="Progress log path; defaults next to the JSON report as <input>.log.")
    fit_parser.add_argument(
        "--rms-target",
        type=float,
        help=(
            "Blocking full-band mean S-RMS target. Required without --priority-band. When omitted "
            "with priority bands, full-band RMS is post-checked but does not block delivery."
        ),
    )
    fit_parser.add_argument(
        "--priority-band",
        action="append",
        metavar="F_MIN:F_MAX:RMS_TARGET[:WEIGHT]",
        help=(
            "Prioritize a frequency band during pole relocation and residue fitting; repeat for multiple bands. "
            "Each band must include its own RMS target; optional WEIGHT defaults to 1."
        ),
    )
    fit_parser.add_argument(
        "--outside-band-weight",
        type=float,
        default=0.1,
        help="Least-squares weight outside --priority-band ranges (default: 0.1; must be > 0).",
    )
    fit_parser.add_argument(
        "--passivity",
        choices=["off", "check", "enforce"],
        default=None,
        help="Passivity policy; defaults to check.",
    )
    fit_parser.add_argument(
        "--max-order",
        type=int,
        help="Maximum effective common-pole order; defaults to 100.",
    )
    fit_parser.add_argument(
        "--min-order",
        type=int,
        default=1,
        help="Validated lower bound for target-order search; skips lower orders (default: 1).",
    )
    fit_parser.add_argument(
        "--max-order-step",
        type=int,
        default=8,
        help="Largest adaptive order-search step when RMS is far above target (default: 8).",
    )
    fit_parser.add_argument("--auto-preset", choices=["idem-fast"], default="idem-fast", help=argparse.SUPPRESS)
    fit_parser.add_argument(
        "--auto-model-order-candidates",
        help=argparse.SUPPRESS,
    )
    fit_parser.add_argument(
        "--auto-target-mean-rms-error",
        type=float,
        help=argparse.SUPPRESS,
    )
    fit_parser.add_argument("--quality-profile", choices=["explore", "signoff"], default="explore", help="Report quality profile.")
    fit_parser.add_argument("--fail-on-quality", action="store_true", help="Return non-zero when the quality report blocks.")
    fit_parser.add_argument("--allow-quality-warnings", action="store_true", help="Allow WARN quality status with --fail-on-quality.")
    fit_parser.add_argument("--enforce-passivity", dest="skip_passivity_enforce", action="store_false", help=argparse.SUPPRESS)
    fit_parser.add_argument("--check-passivity", dest="skip_passivity_check", action="store_false", help=argparse.SUPPRESS)
    fit_parser.add_argument("--subckt-name", default="s_equivalent", help="SPICE subcircuit name.")
    expert_tuning = fit_parser.add_argument_group(
        "Expert tuning",
        "Optional Native algorithm overrides for difficult cases; every applied value is recorded in the report.",
    )
    expert_tuning.add_argument(
        "--tuning-profile",
        type=Path,
        help="Strict JSON profile with version=1 and an overrides object; CLI options take precedence.",
    )
    expert_tuning.add_argument(
        "--pole-spacing", "--init-pole-spacing", dest="init_pole_spacing",
        choices=["lin", "log", "resonance"], default="log",
        help="Initial pole spacing (default: log).",
    )
    expert_tuning.add_argument(
        "--fit-iterations", "--fit-max-iterations", dest="fit_max_iterations", type=int, default=14,
        help="Maximum Native vector-fitting iterations (default: 14).",
    )
    expert_tuning.add_argument(
        "--hf-complex-pairs", "--high-frequency-complex-pairs", dest="high_frequency_complex_pairs", type=int, default=2,
        help="Additional high-frequency complex pole pairs (default: 2).",
    )
    expert_tuning.add_argument(
        "--hf-pair-damping", "--high-frequency-complex-pair-damping", dest="high_frequency_complex_pair_damping", type=float, default=0.03,
        help="High-frequency complex-pair damping ratio (default: 0.03).",
    )
    expert_tuning.add_argument(
        "--hf-pair-start-fraction", "--high-frequency-complex-pair-lower-fraction", dest="high_frequency_complex_pair_lower_fraction", type=float, default=0.68,
        help="Lowest normalized frequency for high-frequency pairs (default: 0.68).",
    )
    expert_tuning.add_argument("--passivity-max-iterations", type=int, default=3, help="Maximum passivity-enforcement iterations (default: 3).")
    expert_tuning.add_argument("--passivity-samples", type=int, default=8, help="Maximum passivity violation samples per enforcement iteration (default: 8).")
    expert_tuning.add_argument("--passivity-active-variables", type=int, default=3072, help="Maximum active variables for passivity enforcement (default: 3072).")
    _add_hidden_argument(fit_parser, "--mode", choices=["auto", "manual"], default="manual")
    _add_hidden_argument(fit_parser, "--n-poles-real", type=int, default=0)
    _add_hidden_argument(fit_parser, "--n-poles-cmplx", type=int, default=2)
    _add_hidden_argument(fit_parser, "--n-poles-init-real", type=int, default=3)
    _add_hidden_argument(fit_parser, "--n-poles-init-cmplx", type=int, default=3)
    _add_hidden_argument(fit_parser, "--n-poles-add", type=int, default=3)
    _add_hidden_argument(fit_parser, "--iters-start", type=int, default=3)
    _add_hidden_argument(fit_parser, "--iters-inter", type=int, default=3)
    _add_hidden_argument(fit_parser, "--iters-final", type=int, default=5)
    _add_hidden_argument(fit_parser, "--model-order-max", type=int, default=100)
    _add_hidden_argument(fit_parser, "--target-error", type=float, default=0.01)
    _add_hidden_argument(fit_parser, "--alpha", type=float, default=0.03)
    _add_hidden_argument(fit_parser, "--gamma", type=float, default=0.03)
    _add_hidden_argument(fit_parser, "--nu-samples", type=float, default=1.0)
    _add_hidden_argument(fit_parser, "--passivity-f-max", type=float)
    _add_hidden_argument(fit_parser, "--no-fit-dc", action="store_true")
    _add_hidden_argument(fit_parser, "--fit-enforce-dc", dest="no_fit_dc", action="store_false")
    _add_hidden_argument(fit_parser, "--no-preserve-dc", action="store_true")
    _add_hidden_argument(fit_parser, "--fit-frequency-stride", type=int, default=1)
    _add_hidden_argument(fit_parser, "--fit-max-frequency-points", type=int, default=256)
    _add_hidden_argument(fit_parser, "--fit-f-min", type=float)
    _add_hidden_argument(fit_parser, "--fit-f-max", type=float)
    _add_hidden_argument(fit_parser, "--native-high-frequency-complex-pair-frequency-gate", action="store_true")
    _add_hidden_argument(fit_parser, "--native-high-frequency-residual-injection", action="store_true")
    _add_hidden_argument(fit_parser, "--native-high-frequency-residual-injection-lower-fraction", type=float, default=0.68)
    _add_hidden_argument(fit_parser, "--native-high-frequency-residual-injection-damping", type=float, default=0.03)
    _add_hidden_argument(fit_parser, "--high-frequency-complex-pair-anchor-bands", default="")
    _add_hidden_argument(fit_parser, "--high-frequency-complex-pair-anchor-strength", type=float, default=0.0)
    _add_hidden_argument(fit_parser, "--high-frequency-complex-pair-anchor-damping", type=float, default=0.03)
    _add_hidden_argument(fit_parser, "--native-effective-order-max", type=int)
    _add_hidden_argument(fit_parser, "--native-effective-complex-pole-count", type=int)
    _add_hidden_argument(
        fit_parser,
        "--native-effective-order-selection",
        choices=["frequency_rank", "contribution_score"],
        default="frequency_rank",
    )
    _add_hidden_argument(fit_parser, "--native-effective-order-passivity-weight", type=float, default=1.0)
    _add_hidden_argument(fit_parser, "--native-post-relocation-effective-order-max", type=int)
    _add_hidden_argument(fit_parser, "--native-high-frequency-relocation-weight", action="store_true")
    _add_hidden_argument(fit_parser, "--native-high-frequency-relocation-weight-lower-fraction", type=float, default=0.68)
    _add_hidden_argument(fit_parser, "--native-high-frequency-relocation-weight-gain", type=float, default=2.0)
    _add_hidden_argument(fit_parser, "--native-out-of-band-pole-regularization-weight", type=float, default=0.0)
    _add_hidden_argument(fit_parser, "--native-out-of-band-pole-regularization-start-fraction", type=float, default=1.0)
    _add_hidden_argument(fit_parser, "--native-dynamic-edge-c-res-regularization", action="store_true")
    _add_hidden_argument(fit_parser, "--native-dynamic-edge-c-res-regularization-base-weight", type=float, default=0.0)
    _add_hidden_argument(fit_parser, "--native-dynamic-edge-c-res-regularization-start-fraction", type=float, default=1.0)
    _add_hidden_argument(fit_parser, "--native-dynamic-edge-c-res-regularization-growth-threshold", type=float, default=1.5)
    _add_hidden_argument(fit_parser, "--use-lightweight-network", action="store_true", default=True)
    _add_hidden_argument(fit_parser, "--skip-passivity-enforce", dest="skip_passivity_enforce", action="store_true", default=True)
    _add_hidden_argument(fit_parser, "--skip-passivity-check", dest="skip_passivity_check", action="store_true", default=True)
    _add_hidden_argument(fit_parser, "--max-comparison-rms-error", type=float, default=0.05)
    _add_hidden_argument(fit_parser, "--max-passivity-epsilon", type=float, default=1e-6)
    _add_hidden_argument(fit_parser, "--require-dc", action="store_true")

    cascade_fit_parser = subparsers.add_parser(
        "fit-sparam-cascade",
        description=(
            "Fit and enforce an ordered chain of 2-port Touchstone blocks, then verify cascade "
            "RMS and passivity."
        ),
    )
    cascade_fit_parser.add_argument("manifest", type=Path, help="Version 1 cascade JSON manifest.")
    cascade_fit_parser.add_argument("--output-root", type=Path, help="Output directory for block and cascade artifacts.")
    cascade_fit_parser.add_argument("--report", type=Path, help="Cascade JSON report path.")
    cascade_fit_parser.add_argument(
        "--rms-target",
        type=float,
        help=(
            "Default blocking per-block full-band mean S-RMS target. Required without "
            "--priority-band; omission selects priority-band-only fit/enforcement."
        ),
    )
    cascade_fit_parser.add_argument("--max-order", type=int, default=100)
    cascade_fit_parser.add_argument("--min-order", type=int, default=1)
    cascade_fit_parser.add_argument("--max-order-step", type=int, default=8)
    cascade_fit_parser.add_argument("--passivity-epsilon", type=float, default=1e-6)
    cascade_fit_parser.add_argument("--cascade-passivity-epsilon", type=float, default=1e-8)
    cascade_fit_parser.add_argument(
        "--cascade-rms-target",
        type=float,
        help=(
            "Optional blocking mean S-RMS target for the final cascaded model, evaluated over "
            "the reported cascade evaluation scope."
        ),
    )
    cascade_fit_parser.add_argument(
        "--cascade-refit-iterations",
        type=int,
        default=8,
        help=(
            "Maximum targeted block refits used to meet --cascade-rms-target after the initial "
            "independent fits (default: 8; 0 disables automatic refit)."
        ),
    )
    cascade_fit_parser.add_argument("--cascade-samples", type=int, default=1001)
    cascade_fit_parser.add_argument("--reference-impedance", type=float, default=50.0, metavar="OHM")
    cascade_fit_parser.add_argument("--adjustment-iterations", type=int, default=12)
    cascade_fit_parser.add_argument("--minimum-scale", type=float, default=0.8)
    cascade_fit_parser.add_argument(
        "--priority-band",
        action="append",
        metavar="F_MIN:F_MAX:RMS_TARGET[:WEIGHT]",
        help="Per-block priority band and RMS target; repeat for multiple bands.",
    )
    cascade_fit_parser.add_argument("--outside-band-weight", type=float, default=0.1)

    y_fit_parser = subparsers.add_parser(
        "fit-yparam",
        description="Fit Touchstone-derived Y parameters and write a common-ground Norton/MNA subcircuit.",
    )
    y_fit_parser.add_argument("touchstone", type=Path, help="Input .sNp Touchstone file.")
    y_fit_parser.add_argument("--output", type=Path, help="Output Y-domain SPICE subcircuit path.")
    y_fit_parser.add_argument(
        "--derived-s-touchstone",
        type=Path,
        help="Optional sampled S Touchstone obtained from the fitted Y rational model; feed it to fit-sparam for S-domain delivery/enforcement.",
    )
    y_fit_parser.add_argument("--report", type=Path, help="JSON report path.")
    y_fit_parser.add_argument("--html-report", type=Path, help="Optional HTML report path.")
    y_fit_parser.add_argument("--log", type=Path, help="Progress log path.")
    y_fit_parser.add_argument("--subckt-name", default="y_equivalent", help="SPICE subcircuit name.")
    y_fit_parser.add_argument("--n-poles-real", type=int, default=1, help="Initial real pole count (default: 1).")
    y_fit_parser.add_argument("--n-poles-cmplx", type=int, default=3, help="Initial complex-pair count (default: 3).")
    y_fit_parser.add_argument(
        "--max-order",
        type=int,
        default=40,
        help="Maximum effective common-pole order for Y target search (default: 40).",
    )
    y_fit_parser.add_argument(
        "--order-step",
        type=int,
        default=2,
        help="Effective-order increment between Y fit attempts (default: 2).",
    )
    y_fit_parser.add_argument("--pole-spacing", choices=["lin", "log"], default="log")
    y_fit_parser.add_argument("--fit-iterations", type=int, default=20)
    y_fit_parser.add_argument(
        "--no-fit-proportional",
        action="store_true",
        help="Disable the Y proportional term. Required by the current exact rational Y-to-S/RFM path.",
    )
    y_fit_parser.add_argument(
        "--max-y-rms-siemens",
        type=float,
        help="Maximum full-matrix mean Y RMS error in Siemens.",
    )
    y_fit_parser.add_argument("--passivity", choices=["off", "check"], default="check", help="Y positive-real check policy; enforcement is intentionally unavailable.")
    y_fit_parser.add_argument("--passivity-epsilon", type=float, default=1e-9)
    y_fit_parser.add_argument("--conversion-condition-limit", type=float, default=1e12)
    y_fit_parser.add_argument("--exact-s-rfm", type=Path, help="Run KYP Y enforcement and write the exact-LFT S RFM delivery artifact.")
    y_fit_parser.add_argument("--exact-s-touchstone", type=Path, help="Write the exact-LFT S Touchstone used to audit the RFM.")
    y_fit_parser.add_argument("--exact-s-rfm-wrapper", type=Path, help="Optional HSPICE wrapper for --exact-s-rfm.")
    y_fit_parser.add_argument("--kyp-max-states", type=int, default=128, help="Maximum dense KYP state count (default: 128).")
    y_fit_parser.add_argument("--kyp-margin", type=float, default=1e-8, help="KYP positive-real margin (default: 1e-8).")
    y_fit_parser.add_argument("--kyp-max-relative-correction", type=float, default=0.05, help="Maximum accepted KYP correction relative to the Y model (default: 0.05).")
    y_fit_parser.add_argument("--kyp-solver", default="CLARABEL", help="CVXPY PSD-cone solver for KYP enforcement (default: CLARABEL).")

    y_tran_tune_parser = subparsers.add_parser(
        "tune-yparam-tran",
        description="Tune declared low-frequency residues of an existing Y-derived S RFM against an explicit HSPICE transient signoff deck.",
    )
    y_tran_tune_parser.add_argument("touchstone", type=Path, help="Input .sNp used to retain in-band static accuracy.")
    y_tran_tune_parser.add_argument("input_rfm", type=Path, help="Existing Y-derived S RFM to tune.")
    y_tran_tune_parser.add_argument("deck", type=Path, help="HSPICE signoff deck containing the input RFM filename exactly once.")
    y_tran_tune_parser.add_argument("--output-rfm", type=Path, required=True, help="Frozen best RFM output path.")
    y_tran_tune_parser.add_argument("--report", type=Path, help="JSON search report; defaults next to --output-rfm.")
    y_tran_tune_parser.add_argument("--work-dir", type=Path, help="Trial artifacts directory; defaults beside the signoff deck.")
    y_tran_tune_parser.add_argument("--rfm-token", required=True, help="Exact input-RFM filename token to replace once in the signoff deck.")
    y_tran_tune_parser.add_argument("--rms-measure", required=True, help="HSPICE .measure name used as the optimization objective.")
    y_tran_tune_parser.add_argument("--peak-measure", help="Optional HSPICE .measure name recorded for the selected candidate.")
    y_tran_tune_parser.add_argument("--residual-poles", required=True, help="Strictly increasing real-pole damping list in rad/s, comma-separated.")
    y_tran_tune_parser.add_argument("--band-boundaries", required=True, help="Strictly increasing residual-band boundaries in rad/s, comma-separated.")
    y_tran_tune_parser.add_argument("--hspice-bin", default="hspice", help="HSPICE executable or command (default: hspice).")
    y_tran_tune_parser.add_argument("--license-file", help="Optional HSPICE license endpoint assigned to SNPSLMD_LICENSE_FILE and LM_LICENSE_FILE.")
    y_tran_tune_parser.add_argument("--max-evaluations", type=int, default=150, help="Maximum HSPICE candidates (default: 150).")
    y_tran_tune_parser.add_argument("--max-static-rms-growth", type=float, default=0.003, help="Largest allowed in-band S-RMS growth fraction (default: 0.003).")
    y_tran_tune_parser.add_argument("--max-sigma", type=float, default=0.999, help="Largest allowed sampled in-band singular value (default: 0.999).")

    idem_probe_parser = subparsers.add_parser("probe-idem-init")
    idem_probe_parser.add_argument("touchstone", type=Path)
    idem_probe_parser.add_argument("--output-root", type=Path, default=Path("runs-sparam/idem-init-probe"))
    idem_probe_parser.add_argument("--report", type=Path, default=Path("runs-sparam/idem-init-probe/report.jsonl"))
    idem_probe_parser.add_argument("--csv", type=Path)
    idem_probe_parser.add_argument("--order", type=int, required=True)
    idem_probe_parser.add_argument("--initial-iters", default="0,1,2,3")
    idem_probe_parser.add_argument("--idem-bin", type=Path)
    idem_probe_parser.add_argument("--n-threads", type=int, default=1)
    idem_probe_parser.add_argument("--target", type=float, default=1e-3)
    idem_probe_parser.add_argument("--no-asymptotic-passivity", action="store_true")
    idem_probe_parser.add_argument("--asymptotic-relocate-poles", action="store_true")
    idem_probe_parser.add_argument("--enhance-poles-placement", action="store_true")
    idem_probe_parser.add_argument("--timeout-seconds", type=float)

    idem_residue_parser = subparsers.add_parser("probe-idem-residue")
    idem_residue_parser.add_argument("touchstone", type=Path)
    idem_residue_parser.add_argument("--model", type=Path, required=True)
    idem_residue_parser.add_argument("--report", type=Path, required=True)
    idem_residue_parser.add_argument("--parameter-type", choices=["s", "z"], default="s")
    idem_residue_parser.add_argument("--basis", choices=["complex", "idem-real"], default="complex")
    idem_residue_parser.add_argument("--relative-weight-power", type=float, default=0.0)
    idem_residue_parser.add_argument("--fit-max-frequency-points", type=int)
    idem_residue_parser.add_argument("--rcond", type=float)

    idem_passivity_parser = subparsers.add_parser("probe-idem-passivity")
    idem_passivity_parser.add_argument("model", type=Path)
    idem_passivity_parser.add_argument("--output-model", type=Path, required=True)
    idem_passivity_parser.add_argument("--report", type=Path, required=True)
    idem_passivity_parser.add_argument("--idem-bin", type=Path)
    idem_passivity_parser.add_argument("--n-threads", type=int, default=8)
    idem_passivity_parser.add_argument("--ham-solver", type=int, choices=[1, 2, 3])
    idem_passivity_parser.add_argument("--preserve-dc", action="store_true")
    idem_passivity_parser.add_argument("--only-check", type=int, choices=[1, 2])
    idem_passivity_parser.add_argument("--xml", type=Path)
    idem_passivity_parser.add_argument("--timeout-seconds", type=float)

    idem_sweep_parser = subparsers.add_parser("probe-idem-residue-sweep")
    idem_sweep_parser.add_argument("touchstone", type=Path)
    idem_sweep_parser.add_argument("--model", type=Path, action="append")
    idem_sweep_parser.add_argument("--model-glob", action="append")
    idem_sweep_parser.add_argument("--report", type=Path, required=True)
    idem_sweep_parser.add_argument("--csv", type=Path)
    idem_sweep_parser.add_argument("--parameter-types", default="s,z")
    idem_sweep_parser.add_argument("--bases", default="complex,idem-real")
    idem_sweep_parser.add_argument("--relative-weight-powers", default="0,0.5,1")
    idem_sweep_parser.add_argument("--fit-max-frequency-points", type=int)
    idem_sweep_parser.add_argument("--rcond", type=float)

    idem_relocate_parser = subparsers.add_parser("probe-idem-relocate")
    idem_relocate_parser.add_argument("touchstone", type=Path)
    idem_relocate_parser.add_argument("--report", type=Path, required=True)
    idem_relocate_parser.add_argument("--csv", type=Path)
    idem_relocate_parser.add_argument("--order", type=int, required=True)
    idem_relocate_parser.add_argument("--iterations", type=int, default=3)
    idem_relocate_parser.add_argument("--parameter-type", choices=["s", "z"], default="s")
    idem_relocate_parser.add_argument("--pole-damping", type=float, default=0.05)
    idem_relocate_parser.add_argument("--pole-spacing", choices=["lin", "log"], default="lin")
    idem_relocate_parser.add_argument("--pole-f-min", type=float)
    idem_relocate_parser.add_argument(
        "--response-selection",
        choices=["energy", "diagonal", "offdiagonal", "mixed", "adaptive-z"],
        default="energy",
    )
    idem_relocate_parser.add_argument("--adaptive-worst-pair-count", type=int, default=16)
    idem_relocate_parser.add_argument("--residue-basis", choices=["complex", "real-state"], default="complex")
    idem_relocate_parser.add_argument("--fit-max-frequency-points", type=int)
    idem_relocate_parser.add_argument("--max-pole-responses", type=int, default=64)
    idem_relocate_parser.add_argument("--relative-weight-power", type=float, default=0.0)
    idem_relocate_parser.add_argument("--pole-pairing", choices=["none", "conjugate"], default="none")
    idem_relocate_parser.add_argument("--relocation-basis", choices=["complex", "real-state"], default="complex")
    idem_relocate_parser.add_argument("--relocation-normalization", choices=["none", "frequency"], default="none")
    idem_relocate_parser.add_argument("--relocation-numerator", choices=["complex", "real"], default="complex")
    idem_relocate_parser.add_argument("--rcond", type=float)

    idem_relocate_sweep_parser = subparsers.add_parser("probe-idem-relocate-sweep")
    idem_relocate_sweep_parser.add_argument("touchstone", type=Path)
    idem_relocate_sweep_parser.add_argument("--report", type=Path, required=True)
    idem_relocate_sweep_parser.add_argument("--csv", type=Path)
    idem_relocate_sweep_parser.add_argument("--order", type=int, required=True)
    idem_relocate_sweep_parser.add_argument("--iterations", type=int, default=3)
    idem_relocate_sweep_parser.add_argument("--parameter-type", choices=["s", "z"], default="s")
    idem_relocate_sweep_parser.add_argument("--pole-damping", type=float, default=0.05)
    idem_relocate_sweep_parser.add_argument("--pole-spacing", choices=["lin", "log"], default="lin")
    idem_relocate_sweep_parser.add_argument("--pole-f-min", type=float)
    idem_relocate_sweep_parser.add_argument("--response-selections", default="energy,diagonal,mixed,adaptive-z")
    idem_relocate_sweep_parser.add_argument("--max-pole-responses-list", default="32,64")
    idem_relocate_sweep_parser.add_argument("--relative-weight-powers", default="0,0.5,1")
    idem_relocate_sweep_parser.add_argument("--adaptive-worst-pair-count", type=int, default=16)
    idem_relocate_sweep_parser.add_argument("--residue-bases", default="complex")
    idem_relocate_sweep_parser.add_argument("--fit-max-frequency-points", type=int)
    idem_relocate_sweep_parser.add_argument("--pole-pairings", default="none")
    idem_relocate_sweep_parser.add_argument("--relocation-bases", default="complex")
    idem_relocate_sweep_parser.add_argument("--relocation-normalizations", default="none")
    idem_relocate_sweep_parser.add_argument("--relocation-numerators", default="complex")
    idem_relocate_sweep_parser.add_argument("--rcond", type=float)

    idem_like_parser = subparsers.add_parser("fit-idem-like")
    idem_like_parser.add_argument("touchstone", type=Path)
    idem_like_parser.add_argument("--report", type=Path, required=True)
    idem_like_parser.add_argument("--csv", type=Path)
    idem_like_parser.add_argument("--model-output", type=Path)
    idem_like_parser.add_argument("--recipe", choices=["default", "idem-compact"], default="default")
    idem_like_parser.add_argument("--order", type=int, default=32)
    idem_like_parser.add_argument("--iterations", type=int, default=4)
    idem_like_parser.add_argument("--parameter-type", choices=["s", "z"], default="s")
    idem_like_parser.add_argument("--pole-damping", type=float, default=0.05)
    idem_like_parser.add_argument("--pole-spacing", choices=["lin", "log"], default="lin")
    idem_like_parser.add_argument("--pole-f-min", type=float)
    idem_like_parser.add_argument(
        "--response-selection",
        choices=["energy", "diagonal", "offdiagonal", "mixed", "adaptive-z"],
        default="energy",
    )
    idem_like_parser.add_argument("--adaptive-worst-pair-count", type=int, default=16)
    idem_like_parser.add_argument("--residue-basis", choices=["complex", "real-state"], default="real-state")
    idem_like_parser.add_argument("--fit-max-frequency-points", type=int, default=256)
    idem_like_parser.add_argument("--max-pole-responses", type=int, default=64)
    idem_like_parser.add_argument("--relative-weight-power", type=float, default=0.0)
    idem_like_parser.add_argument("--pole-pairing", choices=["none", "conjugate"], default="none")
    idem_like_parser.add_argument("--relocation-basis", choices=["complex", "real-state"], default="complex")
    idem_like_parser.add_argument("--relocation-normalization", choices=["none", "frequency"], default="none")
    idem_like_parser.add_argument("--relocation-numerator", choices=["complex", "real"], default="complex")
    idem_like_parser.add_argument("--selection-metric", choices=[
        "z_log_magnitude_rms_error",
        "diagonal_z_log_magnitude_rms_error",
        "s_mean_rms_error",
        "s_relative_rms_error",
    ], default="z_log_magnitude_rms_error")
    idem_like_parser.add_argument("--rcond", type=float)

    idem_like_eval_parser = subparsers.add_parser("eval-idem-like-model")
    idem_like_eval_parser.add_argument("model", type=Path)
    idem_like_eval_parser.add_argument("touchstone", type=Path)
    idem_like_eval_parser.add_argument("--report", type=Path)

    idem_like_refine_parser = subparsers.add_parser("refine-idem-like")
    idem_like_refine_parser.add_argument("model", type=Path)
    idem_like_refine_parser.add_argument("touchstone", type=Path)
    idem_like_refine_parser.add_argument("--output", type=Path, required=True)
    idem_like_refine_parser.add_argument("--report", type=Path, required=True)
    idem_like_refine_parser.add_argument("--iterations", type=int, default=1)
    idem_like_refine_parser.add_argument("--candidate-pair-count", type=int, default=6)
    idem_like_refine_parser.add_argument("--relative-step", type=float, default=0.02)
    idem_like_refine_parser.add_argument("--fit-max-frequency-points", type=int, default=128)
    idem_like_refine_parser.add_argument(
        "--selection-metric",
        choices=[
            "z_log_magnitude_rms_error",
            "diagonal_z_log_magnitude_rms_error",
            "s_mean_rms_error",
            "s_relative_rms_error",
        ],
        default="z_log_magnitude_rms_error",
    )
    idem_like_refine_parser.add_argument("--rcond", type=float)

    idem_like_export_ts_parser = subparsers.add_parser("export-idem-like-touchstone")
    idem_like_export_ts_parser.add_argument("model", type=Path)
    idem_like_export_ts_parser.add_argument("output", type=Path)
    idem_like_export_ts_parser.add_argument("--reference", type=Path, required=True)
    idem_like_export_ts_parser.add_argument("--report", type=Path)

    idem_like_export_ss_parser = subparsers.add_parser("export-idem-like-statespace")
    idem_like_export_ss_parser.add_argument("model", type=Path)
    idem_like_export_ss_parser.add_argument("output", type=Path)
    idem_like_export_ss_parser.add_argument("--report", type=Path)

    idem_like_eval_ss_parser = subparsers.add_parser("eval-idem-like-statespace")
    idem_like_eval_ss_parser.add_argument("statespace", type=Path)
    idem_like_eval_ss_parser.add_argument("touchstone", type=Path)
    idem_like_eval_ss_parser.add_argument("--report", type=Path)

    modal_parser = subparsers.add_parser("fit-modal-z")
    modal_parser.add_argument("touchstone", type=Path)
    modal_parser.add_argument("--report", type=Path)
    modal_parser.add_argument("--html-report", type=Path)
    modal_parser.add_argument("--auto-preset", choices=["compact", "high-accuracy"])
    modal_parser.add_argument("--mode-count", type=int, default=8)
    modal_parser.add_argument("--basis-anchor-ports")
    modal_parser.add_argument("--basis-frequency-sample-count", type=int, default=9)
    modal_parser.add_argument("--basis-frequency-sampling", default="linear")
    modal_parser.add_argument("--decomposition", default="hermitian")
    modal_parser.add_argument("--scalar-fit-order", type=int, default=12)
    modal_parser.add_argument("--frequency-sample-count", type=int)
    modal_parser.add_argument("--frequency-sample-head-count", type=int, default=0)
    modal_parser.add_argument("--pole-damping", type=float, default=0.05)
    modal_parser.add_argument("--peak-pole-frequency-head-count", type=int, default=0)
    modal_parser.add_argument("--peak-pole-entry-count", type=int, default=0)
    modal_parser.add_argument("--peak-pole-full-pair-count", type=int, default=0)
    modal_parser.add_argument("--peak-pole-complete-order", action="store_true")
    modal_parser.add_argument("--reduced-fit-method", default="fixed")
    modal_parser.add_argument("--vector-target-error", type=float, default=0.01)
    modal_parser.add_argument("--vector-iters-final", type=int, default=2)
    modal_parser.add_argument("--shared-pole-trace-count", type=int, default=3)
    modal_parser.add_argument("--relative-weight-power", type=float, default=1.0)
    modal_parser.add_argument("--relative-weight-mode", default="trace")
    modal_parser.add_argument("--relative-weight-iterations", type=int, default=1)
    modal_parser.add_argument("--relative-weight-update", default="original")
    modal_parser.add_argument("--target-error-weight-power", type=float, default=0.0)
    modal_parser.add_argument("--target-error-weight-max", type=float, default=8.0)
    modal_parser.add_argument("--target-error-pair-count", type=int, default=0)
    modal_parser.add_argument("--residual-pair-count", type=int, default=0)
    modal_parser.add_argument("--residual-fit-order", type=int, default=12)
    modal_parser.add_argument("--residual-pole-damping", type=float)
    modal_parser.add_argument("--residual-weight-power", type=float, default=0.0)
    modal_parser.add_argument("--residual-gain", type=float, default=1.0)
    modal_parser.add_argument("--residual-mirror-pairs", action="store_true")
    modal_parser.add_argument("--auto-order-candidates")
    modal_parser.add_argument("--auto-basis-mode-counts")
    modal_parser.add_argument("--auto-basis-sample-counts")
    modal_parser.add_argument("--auto-basis-anchor-port-counts")
    modal_parser.add_argument("--auto-basis-anchor-candidate-count", type=int)
    modal_parser.add_argument("--auto-basis-anchor-combo-count", type=int, default=1)
    modal_parser.add_argument("--auto-pole-dampings")
    modal_parser.add_argument("--auto-shared-pole-trace-counts")
    modal_parser.add_argument("--auto-peak-pole-entry-counts")
    modal_parser.add_argument("--auto-basis-diagonal-weight", type=float, default=0.0)
    modal_parser.add_argument("--auto-order-max-z-log-rms-error", type=float)
    modal_parser.add_argument("--auto-order-max-diagonal-z-log-rms-error", type=float)
    modal_parser.add_argument("--fail-on-quality", action="store_true")
    modal_parser.add_argument("--max-s-rms-error", type=float)
    modal_parser.add_argument("--max-z-log-rms-error", type=float)
    modal_parser.add_argument("--max-diag-z-log-rms-error", type=float)
    modal_parser.add_argument("--max-basis-projection-z-log-rms-error", type=float)
    modal_parser.add_argument("--max-scalar-fit-order", type=int)

    benchmark_parser = subparsers.add_parser("benchmark-sparam")
    benchmark_parser.add_argument("--manifest", type=Path, required=True)
    benchmark_parser.add_argument("--output", type=Path)
    benchmark_parser.add_argument("--csv", type=Path)
    benchmark_parser.add_argument("--output-root", type=Path)
    benchmark_parser.add_argument("--run-fit", action="store_true")
    benchmark_parser.add_argument("--case", action="append")
    benchmark_parser.add_argument("--order-sweep")

    preflight_parser = subparsers.add_parser("preflight-sparam-corpus")
    preflight_parser.add_argument("--manifest", type=Path, required=True)
    preflight_parser.add_argument("--report", type=Path, required=True)

    band_parser = subparsers.add_parser("compare-sparam-bands")
    band_parser.add_argument("raw", type=Path)
    band_parser.add_argument("--model", action="append", required=True, help="Model Touchstone as LABEL=PATH")
    band_parser.add_argument("--output", type=Path, required=True)
    band_parser.add_argument("--csv", type=Path)
    band_parser.add_argument("--html", type=Path)

    args = parser.parse_args(effective_argv)
    if args.command == "run-hspice":
        return run_hspice(args.deck, args.backend, args.output_root, args.execute)
    if args.command == "run-rfm":
        return run_rfm(
            args.deck,
            args.rfm,
            args.output_root,
            args.subckt_name,
            execute=args.execute,
            ngspice_executable=args.ngspice,
            code_model=args.code_model,
        )
    if args.command == "fit-sparam-cascade":
        output_root = args.output_root or args.manifest.with_name(f"{args.manifest.stem}_fit")
        try:
            priority_bands = _parse_priority_bands(args.priority_band)
            gate_full_band_rms = args.rms_target is not None
            rms_target = (
                args.rms_target
                if gate_full_band_rms
                else min((band[2] for band in priority_bands), default=None)
            )
            if rms_target is None:
                raise ValueError("--rms-target is required without --priority-band")
            payload = fit_sparam_cascade(
                args.manifest,
                output_root,
                config=_cascade_fit_config(
                    rms_target=rms_target,
                    max_order=args.max_order,
                    min_order=args.min_order,
                    max_order_step=args.max_order_step,
                    passivity_epsilon=args.passivity_epsilon,
                    cascade_rms_target=args.cascade_rms_target,
                    cascade_refit_max_iterations=args.cascade_refit_iterations,
                    cascade_passivity_epsilon=args.cascade_passivity_epsilon,
                    cascade_samples=args.cascade_samples,
                    reference_impedance_ohm=args.reference_impedance,
                    adjustment_iterations=args.adjustment_iterations,
                    minimum_scale=args.minimum_scale,
                    priority_bands_hz=priority_bands,
                    outside_band_weight=args.outside_band_weight,
                    gate_full_band_rms=gate_full_band_rms,
                    priority_band_fit_only=bool(priority_bands and not gate_full_band_rms),
                ),
                report_path=args.report,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"fit-sparam-cascade status=FAIL reason={exc}", file=sys.stderr)
            return 1
        status = payload.get("status", "FAIL")
        print(f"fit-sparam-cascade status={status} output={output_root}")
        return 0 if status == "PASS" else 1
    if args.command == "fit-sparam":
        try:
            _apply_sparam_auto_preset(args, effective_argv)
            tuning_overrides = _apply_expert_tuning_overrides(args, effective_argv)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        explicit_passivity = _argument_was_explicit(effective_argv, "--passivity")
        legacy_enforce = _argument_was_explicit(effective_argv, "--enforce-passivity")
        legacy_check = _argument_was_explicit(effective_argv, "--check-passivity")
        legacy_skip_check = _argument_was_explicit(effective_argv, "--skip-passivity-check")
        legacy_skip_enforce = _argument_was_explicit(effective_argv, "--skip-passivity-enforce")
        if explicit_passivity and (legacy_enforce or legacy_check or legacy_skip_check or legacy_skip_enforce):
            print("error: --passivity cannot be combined with legacy passivity flags", file=sys.stderr)
            return 1
        if explicit_passivity:
            passivity_policy = args.passivity
        elif legacy_enforce:
            passivity_policy = "enforce"
        elif legacy_skip_check:
            passivity_policy = "off"
        else:
            passivity_policy = "check"
        args.skip_passivity_enforce = passivity_policy != "enforce"
        args.skip_passivity_check = passivity_policy == "off"

        ports = 2
        port_match = re.search(r"\.s(\d+)p$", str(args.touchstone).lower())
        if port_match:
            ports = int(port_match.group(1))
        if ports >= 60 and passivity_policy == "enforce":
            for attr, value in SPARAM_IDEM_FAST_PASSIVITY_PROFILE_LARGE_PORT.items():
                option = SPARAM_IDEM_FAST_PASSIVITY_OPTION_FLAGS.get(attr)
                if option is not None and _argument_was_explicit(effective_argv, option):
                    continue
                setattr(args, attr, value)

        max_order = args.max_order
        if max_order is None and args.auto_model_order_candidates:
            compatibility_orders = _parse_int_list(args.auto_model_order_candidates)
            max_order = max(compatibility_orders) if compatibility_orders else None
        if max_order is None:
            max_order = 100
        try:
            priority_bands = _parse_priority_bands(args.priority_band)
            gate_full_band_rms = not priority_bands or args.rms_target is not None
            rms_target = args.rms_target
            if rms_target is None:
                rms_target = (
                    min((band[2] for band in priority_bands), default=None)
                    if priority_bands
                    else args.auto_target_mean_rms_error
                )
            if rms_target is None:
                raise ValueError("--rms-target is required without --priority-band")
            target = SParamFitTarget(
                mean_rms=rms_target,
                passivity=passivity_policy,
                max_order=max_order,
                min_order=args.min_order,
                max_order_step=args.max_order_step,
                passivity_epsilon=args.max_passivity_epsilon,
                gate_full_band_rms=gate_full_band_rms,
                priority_bands_hz=tuple(
                    (band[0], band[1], band[2]) for band in priority_bands
                ),
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        config = SParamFitConfig(
            mode=args.mode,
            n_poles_real=args.n_poles_real,
            n_poles_cmplx=args.n_poles_cmplx,
            init_pole_spacing=args.init_pole_spacing,
            n_poles_init_real=args.n_poles_init_real,
            n_poles_init_cmplx=args.n_poles_init_cmplx,
            n_poles_add=args.n_poles_add,
            iters_start=args.iters_start,
            iters_inter=args.iters_inter,
            iters_final=args.iters_final,
            model_order_max=args.model_order_max,
            target_error=args.target_error,
            alpha=args.alpha,
            gamma=args.gamma,
            nu_samples=args.nu_samples,
            max_iterations=args.fit_max_iterations,
            enforce_dc=not args.no_fit_dc,
            check_passivity=passivity_policy != "off",
            enforce_passivity=passivity_policy == "enforce",
            passivity_samples=args.passivity_samples,
            passivity_max_iterations=args.passivity_max_iterations,
            passivity_active_variables=args.passivity_active_variables,
            passivity_f_max=args.passivity_f_max,
            preserve_dc=not args.no_preserve_dc,
            fit_frequency_stride=args.fit_frequency_stride,
            fit_max_frequency_points=args.fit_max_frequency_points,
            fit_f_min=args.fit_f_min,
            fit_f_max=args.fit_f_max,
            priority_bands_hz=priority_bands,
            outside_band_weight=args.outside_band_weight,
            priority_band_fit_only=bool(priority_bands and not gate_full_band_rms),
            use_lightweight_network=args.use_lightweight_network,
            high_frequency_complex_pair_count=args.high_frequency_complex_pairs,
            high_frequency_complex_pair_damping=args.high_frequency_complex_pair_damping,
            high_frequency_complex_pair_lower_fraction=args.high_frequency_complex_pair_lower_fraction,
            native_high_frequency_complex_pair_frequency_gate=args.native_high_frequency_complex_pair_frequency_gate,
            native_high_frequency_residual_injection=args.native_high_frequency_residual_injection,
            native_high_frequency_residual_injection_lower_fraction=(
                args.native_high_frequency_residual_injection_lower_fraction
            ),
            native_high_frequency_residual_injection_damping=args.native_high_frequency_residual_injection_damping,
            high_frequency_complex_pair_anchor_bands_hz=_parse_frequency_bands(
                args.high_frequency_complex_pair_anchor_bands
            ),
            high_frequency_complex_pair_anchor_strength=args.high_frequency_complex_pair_anchor_strength,
            high_frequency_complex_pair_anchor_damping=args.high_frequency_complex_pair_anchor_damping,
            native_effective_order_max=args.native_effective_order_max,
            native_effective_complex_pole_count=args.native_effective_complex_pole_count,
            native_effective_order_selection=args.native_effective_order_selection,
            native_effective_order_passivity_weight=args.native_effective_order_passivity_weight,
            native_post_relocation_effective_order_max=args.native_post_relocation_effective_order_max,
            native_high_frequency_relocation_weight=args.native_high_frequency_relocation_weight,
            native_high_frequency_relocation_weight_lower_fraction=(
                args.native_high_frequency_relocation_weight_lower_fraction
            ),
            native_high_frequency_relocation_weight_gain=args.native_high_frequency_relocation_weight_gain,
            native_out_of_band_pole_regularization_weight=args.native_out_of_band_pole_regularization_weight,
            native_out_of_band_pole_regularization_start_fraction=(
                args.native_out_of_band_pole_regularization_start_fraction
            ),
            native_dynamic_edge_c_res_regularization=args.native_dynamic_edge_c_res_regularization,
            native_dynamic_edge_c_res_regularization_base_weight=(
                args.native_dynamic_edge_c_res_regularization_base_weight
            ),
            native_dynamic_edge_c_res_regularization_start_fraction=(
                args.native_dynamic_edge_c_res_regularization_start_fraction
            ),
            native_dynamic_edge_c_res_regularization_growth_threshold=(
                args.native_dynamic_edge_c_res_regularization_growth_threshold
            ),
            quality_profile=args.quality_profile,
            max_comparison_rms_error=args.max_comparison_rms_error,
            max_passivity_epsilon=args.max_passivity_epsilon,
            require_dc=args.require_dc,
            subckt_name=args.subckt_name,
            **_sparam_cli_advanced_passivity_kwargs(args),
        )

        output_was_defaulted = args.output is None
        if output_was_defaulted:
            args.output = args.touchstone.with_name(f"{args.touchstone.stem}_fitted.sp")
        report_path = args.report or (
            args.output.with_name(f"{args.output.stem}_report.json")
            if output_was_defaulted
            else args.output.parent / "fit_report.json"
        )
        html_report_path = args.html_report or (
            args.output.with_name(f"{args.output.stem}_report.html")
            if output_was_defaulted
            else args.output.parent / "fit_report.html"
        )
        log_path = args.log or (report_path.parent / f"{args.touchstone.stem}.log")
        if args.report_top_rms < 0:
            print("error: --report-top-rms must be >= 0", file=sys.stderr)
            return 1
        fitted_touchstone_path = args.fitted_touchstone or args.output.with_suffix(args.touchstone.suffix.lower())
        rfm_path = args.rfm or args.output.with_suffix(".rfm")
        rfm_wrapper_path = args.rfm_wrapper or rfm_path.with_name(f"{rfm_path.stem}_rfm_wrapper.sp")
        try:
            target_fit_kwargs = {
                "target": target,
                "config": config,
                "report_path": report_path,
                "html_report_path": html_report_path,
                "log_path": log_path,
                "fitted_touchstone_path": fitted_touchstone_path,
                "rfm_path": rfm_path,
                "rfm_wrapper_path": rfm_wrapper_path,
                "report_top_rms": args.report_top_rms,
                "max_order_step": args.max_order_step,
            }
            if tuning_overrides is not None:
                target_fit_kwargs["tuning_overrides"] = tuning_overrides
            result = fit_touchstone_to_spice_target(
                args.touchstone,
                args.output,
                **target_fit_kwargs,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not result.target_met:
            best_trial = getattr(result, "best_trial", None)
            details = ""
            if best_trial is not None:
                details = (
                    f" best_order={best_trial.requested_order}"
                    f" best_rms={best_trial.final_mean_rms:.12g}"
                    f" output={args.output}"
                )
            print(
                "fit-sparam status=FAIL reason=target_not_met_before_max_order" + details,
                file=sys.stderr,
            )
            return 1
        if args.fail_on_quality:
            selected_result = None if result.selected_trial is None else result.selected_trial.payload
            failure = None if selected_result is None else _quality_gate_failure(
                selected_result,
                allow_warnings=args.allow_quality_warnings,
            )
            if failure is not None:
                print(f"error: {failure}", file=sys.stderr)
                return 1
        selected_trial = result.selected_trial
        selected_order = None if selected_trial is None else getattr(selected_trial, "requested_order", None)
        print(f"fit-sparam status=PASS selected_order={selected_order} output={args.output}")
        return 0
    if args.command == "tune-yparam-tran":
        try:
            payload = tune_y_rfm_for_tran(
                YTranTuneConfig(
                    touchstone=args.touchstone,
                    input_rfm=args.input_rfm,
                    deck=args.deck,
                    output_rfm=args.output_rfm,
                    rfm_token=args.rfm_token,
                    rms_measure=args.rms_measure,
                    peak_measure=args.peak_measure,
                    residual_damping=parse_float_csv(args.residual_poles, label="residual_poles"),
                    band_boundaries=parse_float_csv(args.band_boundaries, label="band_boundaries"),
                    report=args.report,
                    work_dir=args.work_dir,
                    hspice_bin=args.hspice_bin,
                    license_file=args.license_file,
                    max_evaluations=args.max_evaluations,
                    max_static_rms_growth=args.max_static_rms_growth,
                    max_sigma=args.max_sigma,
                )
            )
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        best = payload["best"]
        print(
            f"tune-yparam-tran status=PASS rms={float(best['tran_rms']):.12g} "
            f"output={args.output_rfm}"
        )
        return 0
    if args.command == "fit-yparam":
        output = args.output or args.touchstone.with_name(f"{args.touchstone.stem}_fitted.y.sp")
        report_path = args.report or output.with_suffix(".json")
        html_report_path = args.html_report or output.with_suffix(".html")
        log_path = args.log or output.with_suffix(".log")
        exact_trial_deliveries: dict[int, tuple[Any, Any, Any]] = {}
        exact_gate_failures: list[str] = []

        def validate_exact_y_to_s_trial(trial_result):
            trial_order = trial_result.fitted_model.get_model_order(
                trial_result.fitted_model.poles
            )
            append_yparam_progress(
                log_path,
                "starting exact Y delivery gate: "
                f"order={trial_order}, solver={args.kyp_solver}, "
                f"max_states={args.kyp_max_states}, margin={args.kyp_margin:.12g}, "
                f"max_relative_correction={args.kyp_max_relative_correction:.12g}",
            )
            try:
                enforced_y, certificate = enforce_y_positive_real_kyp(
                    trial_result.fitted_model,
                    margin=args.kyp_margin,
                    max_states=args.kyp_max_states,
                    max_relative_correction=args.kyp_max_relative_correction,
                    solver=args.kyp_solver,
                )
                exact_s = exact_y_to_s_rational(
                    enforced_y,
                    float(trial_result.reference_impedance[0]),
                )
            except (RuntimeError, ValueError) as exc:
                reason = f"exact_y_to_s_gate_failed: {exc}"
                exact_gate_failures.append(reason)
                append_yparam_progress(
                    log_path,
                    f"exact Y delivery gate failed: order={trial_order}, error={exc}",
                )
                return False, reason
            exact_trial_deliveries[id(trial_result.fitted_model)] = (
                enforced_y,
                certificate,
                exact_s,
            )
            append_yparam_progress(
                log_path,
                "exact Y delivery gate passed: "
                f"order={trial_order}, status={certificate.status}, "
                f"state_count={certificate.state_count}, "
                f"correction_frobenius_norm={certificate.correction_frobenius_norm:.12g}",
            )
            return True, None

        try:
            if args.exact_s_rfm is not None and not args.no_fit_proportional:
                raise ValueError(
                    "--exact-s-rfm requires --no-fit-proportional; descriptor Y-to-S is not implemented"
                )
            result = fit_touchstone_to_y_spice_auto_order(
                args.touchstone,
                output,
                config=YParamFitConfig(
                    n_poles_real=args.n_poles_real,
                    n_poles_cmplx=args.n_poles_cmplx,
                    init_pole_spacing=args.pole_spacing,
                    max_iterations=args.fit_iterations,
                    max_y_rms_siemens=args.max_y_rms_siemens,
                    passivity=args.passivity,
                    passivity_epsilon=args.passivity_epsilon,
                    conversion_condition_limit=args.conversion_condition_limit,
                    fit_proportional=not args.no_fit_proportional,
                    subckt_name=args.subckt_name,
                ),
                max_order=args.max_order,
                order_step=args.order_step,
                report_path=report_path,
                html_report_path=html_report_path,
                log_path=log_path,
                derived_s_touchstone_path=args.derived_s_touchstone,
                trial_acceptance=(
                    validate_exact_y_to_s_trial
                    if args.exact_s_rfm is not None
                    else None
                ),
            )
            if args.exact_s_rfm is not None and result.target_met:
                delivery = exact_trial_deliveries.get(id(result.fitted_model))
                if delivery is None:
                    raise ValueError("selected Y model is missing its exact-delivery gate result")
                _, certificate, exact_s = delivery
                z0 = float(result.reference_impedance[0])
                append_yparam_progress(
                    log_path,
                    f"writing exact S RFM: {args.exact_s_rfm}",
                )
                write_cadence_rfm(exact_s, args.exact_s_rfm, z0)
                exact_touchstone = args.exact_s_touchstone or args.exact_s_rfm.with_suffix(args.touchstone.suffix.lower())
                append_yparam_progress(log_path, f"writing exact S Touchstone: {exact_touchstone}")
                write_fitted_touchstone(exact_touchstone, result.fitted_model.network.f, evaluate_fitted_s(exact_s, result.fitted_model.network.f), result.fitted_model.network.z0)
                if args.exact_s_rfm_wrapper is not None:
                    append_yparam_progress(
                        log_path,
                        f"writing exact S RFM wrapper: {args.exact_s_rfm_wrapper}",
                    )
                    write_cadence_rfm_wrapper(
                        args.exact_s_rfm_wrapper,
                        args.exact_s_rfm,
                        nports=result.ports,
                        subcircuit_name=f"{args.subckt_name}_exact_s",
                    )
                payload = json.loads(report_path.read_text(encoding="utf-8"))
                payload["passivity"]["enforcement"] = "KYP continuous-frequency certificate"
                payload["passivity"]["kyp_certificate"] = certificate.__dict__
                payload["exact_y_to_s"] = {
                    "method": "state-space rational LFT; no sampled S refit",
                    "matrix": "S=(I-z0Y)(I+z0Y)^-1",
                    "rfm_path": str(args.exact_s_rfm),
                    "touchstone_path": str(exact_touchstone),
                    "stored_pole_count": int(len(exact_s.poles)),
                }
                report_path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
                append_yparam_progress(
                    log_path,
                    f"exact Y-to-S delivery completed: rfm={args.exact_s_rfm}, touchstone={exact_touchstone}",
                )
        except ValueError as exc:
            append_yparam_progress(log_path, f"fit-yparam command failed: {exc}")
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not result.target_met:
            reason = "y_rms_target_not_met"
            if exact_gate_failures:
                reason = "exact_y_to_s_gate_failed"
            elif args.passivity == "check" and result.passivity_violation_count:
                reason = "y_not_positive_real"
            selected_order = result.fitted_model.get_model_order(result.fitted_model.poles)
            print(
                f"fit-yparam status=FAIL reason={reason} rms_siemens={result.y_rms_siemens:.12g} "
                f"mean_rms_siemens={result.y_mean_rms_siemens:.12g} order={selected_order} output={output}",
                file=sys.stderr,
            )
            return 1
        z_log = result.z_log_metrics["z_log_magnitude_rms_error"]
        z_log_text = "unavailable" if z_log is None else f"{z_log:.12g}"
        selected_order = result.fitted_model.get_model_order(result.fitted_model.poles)
        print(
            f"fit-yparam status=PASS rms_siemens={result.y_rms_siemens:.12g} "
            f"mean_rms_siemens={result.y_mean_rms_siemens:.12g} z_log_rms={z_log_text} "
            f"order={selected_order} output={output}"
        )
        return 0
    if args.command == "probe-idem-init":
        try:
            initial_iterations = _parse_int_list(args.initial_iters)
            results = run_idem_initial_iteration_probe(
                args.touchstone,
                args.output_root,
                order=args.order,
                initial_iterations=initial_iterations,
                idem_bin_dir=args.idem_bin,
                threads=args.n_threads,
                target=args.target,
                enforce_asymptotic_passivity=not args.no_asymptotic_passivity,
                asymptotic_relocate_poles=args.asymptotic_relocate_poles,
                enhance_poles_placement=args.enhance_poles_placement,
                timeout_seconds=args.timeout_seconds,
            )
            write_probe_jsonl(results, args.report)
            if args.csv is not None:
                write_probe_csv(results, args.csv)
        except (ValueError, RuntimeError, TimeoutError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for result in results:
            command = result["command"]
            model = result["model"]
            error_history = model.get("error_history") or []
            rms = error_history[-1] if error_history else None
            quality = f" rms={rms:.6g}" if isinstance(rms, (int, float)) else ""
            print(
                f"init={result['initial_iterations']}: {result['status']}"
                f" order={model.get('order')}"
                f" poles={model.get('total_pole_count')}"
                f" elapsed={command.get('elapsed_seconds'):.3f}s"
                f"{quality}"
            )
        return 0
    if args.command == "probe-idem-residue":
        try:
            result = run_idem_fixed_pole_residue_probe(
                args.touchstone,
                args.model,
                parameter_type=args.parameter_type,
                basis=args.basis,
                relative_weight_power=args.relative_weight_power,
                fit_max_frequency_points=args.fit_max_frequency_points,
                rcond=args.rcond,
            )
            write_json_report(result, args.report)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            f"fixed-pole residues: parameter={result['parameter_type']} basis={result['basis']} "
            f"poles={result['pole_count']} "
            f"fit_points={result['fit_frequency_points']} "
            f"cond={result['condition_number']:.6g} "
            f"s_rel_rms={result['s_relative_rms_error']:.6g} "
            f"z_log_rms={result['z_log_magnitude_rms_error']:.6g}"
        )
        return 0
    if args.command == "probe-idem-passivity":
        try:
            result = run_idem_passivity(
                args.model,
                args.output_model,
                idem_bin_dir=args.idem_bin,
                threads=args.n_threads,
                ham_solver=args.ham_solver,
                preserve_dc=args.preserve_dc,
                only_check=args.only_check,
                options_xml_path=args.xml,
                timeout_seconds=args.timeout_seconds,
            )
            write_json_report(result, args.report)
        except (ValueError, RuntimeError, TimeoutError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        passivity = result.get("passivity") or {}
        command = result.get("command") or {}
        max_values = passivity.get("max_singular_values") or []
        peak = max_values[0] if max_values else None
        peak_text = ""
        if peak is not None:
            peak_text = f" first_peak={peak.get('value'):.6g}@{peak.get('frequency_hz'):.6g}Hz"
        print(
            f"idem passivity: {result['status']} passive={passivity.get('passive')} "
            f"soc={passivity.get('soc_iterations')} ham={passivity.get('ham_iterations')} "
            f"elapsed={command.get('elapsed_seconds'):.3f}s"
            f"{peak_text}"
        )
        return 0
    if args.command == "probe-idem-residue-sweep":
        try:
            model_paths = _expand_model_paths(args.model, args.model_glob)
            parameter_types = _parse_choice_list(args.parameter_types, {"s", "z"}, "parameter type")
            bases = _parse_choice_list(args.bases, {"complex", "idem-real"}, "basis")
            relative_weight_powers = _parse_float_list(args.relative_weight_powers)
            results = run_idem_residue_sweep(
                args.touchstone,
                model_paths,
                parameter_types=parameter_types,
                bases=bases,
                relative_weight_powers=relative_weight_powers,
                fit_max_frequency_points=args.fit_max_frequency_points,
                rcond=args.rcond,
            )
            write_jsonl_report(results, args.report)
            if args.csv is not None:
                write_residue_sweep_csv(results, args.csv)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        best = results[0]
        print(
            f"best z_log_rms={best['z_log_magnitude_rms_error']:.6g} "
            f"model={best.get('model_label')} "
            f"basis={best['basis']} "
            f"parameter={best['parameter_type']} "
            f"weight={best['relative_weight_power']} "
            f"s_rel_rms={best['s_relative_rms_error']:.6g} "
            f"cond={best['condition_number']:.6g}"
        )
        for result in results[: min(5, len(results))]:
            print(
                f"ranked z_log={result['z_log_magnitude_rms_error']:.6g} "
                f"diag_z_log={result['diagonal_z_log_magnitude_rms_error']:.6g} "
                f"model={result.get('model_label')} "
                f"basis={result['basis']} "
                f"parameter={result['parameter_type']} "
                f"weight={result['relative_weight_power']}"
            )
        return 0
    if args.command == "probe-idem-relocate":
        try:
            results = run_local_pole_relocation_probe(
                args.touchstone,
                order=args.order,
                iterations=args.iterations,
                parameter_type=args.parameter_type,
                pole_damping=args.pole_damping,
                pole_spacing=args.pole_spacing,
                pole_f_min=args.pole_f_min,
                response_selection=args.response_selection,
                adaptive_worst_pair_count=args.adaptive_worst_pair_count,
                residue_basis=args.residue_basis,
                fit_max_frequency_points=args.fit_max_frequency_points,
                max_pole_responses=args.max_pole_responses,
                relative_weight_power=args.relative_weight_power,
                pole_pairing=args.pole_pairing,
                relocation_basis=args.relocation_basis,
                relocation_normalization=args.relocation_normalization,
                relocation_numerator=args.relocation_numerator,
                rcond=args.rcond,
            )
            write_jsonl_report(results, args.report)
            if args.csv is not None:
                write_relocation_csv(results, args.csv)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for result in results:
            print(
                f"relocate iter={result['iteration']} "
                f"poles={result['order']} "
                f"fit_points={result['fit_frequency_points']} "
                f"responses={result['selected_response_count']} "
                f"selection={result['response_selection']} "
                f"pairing={result['pole_pairing']} "
                f"reloc_basis={result['relocation_basis']} "
                f"norm={result['relocation_normalization']} "
                f"num={result['relocation_numerator']} "
                f"basis={result['basis']} "
                f"reloc_cond={result.get('relocation_condition_number')} "
                f"residue_cond={result['condition_number']:.6g} "
                f"s_rel_rms={result['s_relative_rms_error']:.6g} "
                f"z_log_rms={result['z_log_magnitude_rms_error']:.6g}"
            )
        return 0
    if args.command == "probe-idem-relocate-sweep":
        try:
            response_selections = _parse_choice_list(
                args.response_selections,
                {"energy", "diagonal", "offdiagonal", "mixed", "adaptive-z"},
                "response selection",
            )
            max_response_values = _parse_int_list(args.max_pole_responses_list)
            relative_weight_powers = _parse_float_list(args.relative_weight_powers)
            residue_bases = _parse_choice_list(args.residue_bases, {"complex", "real-state"}, "residue basis")
            pole_pairings = _parse_choice_list(args.pole_pairings, {"none", "conjugate"}, "pole pairing")
            relocation_bases = _parse_choice_list(
                args.relocation_bases,
                {"complex", "real-state"},
                "relocation basis",
            )
            relocation_normalizations = _parse_choice_list(
                args.relocation_normalizations,
                {"none", "frequency"},
                "relocation normalization",
            )
            relocation_numerators = _parse_choice_list(
                args.relocation_numerators,
                {"complex", "real"},
                "relocation numerator",
            )
            results = run_local_pole_relocation_sweep(
                args.touchstone,
                order=args.order,
                iterations=args.iterations,
                parameter_type=args.parameter_type,
                pole_damping=args.pole_damping,
                pole_spacing=args.pole_spacing,
                pole_f_min=args.pole_f_min,
                response_selections=response_selections,
                max_pole_responses_values=max_response_values,
                relative_weight_powers=relative_weight_powers,
                adaptive_worst_pair_count=args.adaptive_worst_pair_count,
                residue_bases=residue_bases,
                fit_max_frequency_points=args.fit_max_frequency_points,
                pole_pairings=pole_pairings,
                relocation_bases=relocation_bases,
                relocation_normalizations=relocation_normalizations,
                relocation_numerators=relocation_numerators,
                rcond=args.rcond,
            )
            write_jsonl_report(results, args.report)
            if args.csv is not None:
                write_relocation_csv(results, args.csv)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        best = results[0]
        print(
            f"best z_log_rms={best['z_log_magnitude_rms_error']:.6g} "
            f"iter={best['iteration']} "
            f"label={best.get('sweep_label')} "
            f"selection={best['response_selection']} "
            f"pairing={best['pole_pairing']} "
            f"reloc_basis={best['relocation_basis']} "
            f"norm={best['relocation_normalization']} "
            f"num={best['relocation_numerator']} "
            f"basis={best['basis']} "
            f"responses={best['selected_response_count']} "
            f"s_rel_rms={best['s_relative_rms_error']:.6g} "
            f"residue_cond={best['condition_number']:.6g}"
        )
        for result in results[: min(5, len(results))]:
            print(
                f"ranked z_log={result['z_log_magnitude_rms_error']:.6g} "
                f"iter={result['iteration']} "
                f"label={result.get('sweep_label')} "
                f"selection={result['response_selection']} "
                f"pairing={result['pole_pairing']} "
                f"reloc_basis={result['relocation_basis']} "
                f"norm={result['relocation_normalization']} "
                f"num={result['relocation_numerator']} "
                f"basis={result['basis']} "
                f"responses={result['selected_response_count']} "
                f"weight={result['relative_weight_power']}"
            )
        return 0
    if args.command == "fit-idem-like":
        _apply_idem_like_recipe(args, argv if argv is not None else sys.argv[1:])
        try:
            result = run_local_idem_like_fit(
                args.touchstone,
                order=args.order,
                iterations=args.iterations,
                parameter_type=args.parameter_type,
                pole_damping=args.pole_damping,
                pole_spacing=args.pole_spacing,
                pole_f_min=args.pole_f_min,
                response_selection=args.response_selection,
                adaptive_worst_pair_count=args.adaptive_worst_pair_count,
                residue_basis=args.residue_basis,
                fit_max_frequency_points=args.fit_max_frequency_points,
                max_pole_responses=args.max_pole_responses,
                relative_weight_power=args.relative_weight_power,
                pole_pairing=args.pole_pairing,
                relocation_basis=args.relocation_basis,
                relocation_normalization=args.relocation_normalization,
                relocation_numerator=args.relocation_numerator,
                rcond=args.rcond,
                selection_metric=args.selection_metric,
                model_output_path=args.model_output,
            )
            result.setdefault("recipe", {})["cli_recipe"] = args.recipe
            write_json_report(result, args.report)
            if args.csv is not None:
                write_relocation_csv(result["iterations"], args.csv)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        best = result["best"]
        print(
            f"fit-idem-like best iter={best['iteration']} "
            f"basis={best['basis']} "
            f"selection={best['response_selection']} "
            f"pairing={best['pole_pairing']} "
            f"reloc_basis={best['relocation_basis']} "
            f"norm={best['relocation_normalization']} "
            f"num={best['relocation_numerator']} "
            f"responses={best['selected_response_count']} "
            f"z_log_rms={best['z_log_magnitude_rms_error']:.6g} "
            f"diag_z_log_rms={best['diagonal_z_log_magnitude_rms_error']:.6g} "
            f"s_mean_rms={best.get('s_mean_rms_error', float('nan')):.6g} "
            f"s_rel_rms={best['s_relative_rms_error']:.6g} "
            f"residue_cond={best['condition_number']:.6g}"
        )
        return 0
    if args.command == "eval-idem-like-model":
        try:
            result = evaluate_local_idem_like_model(args.model, args.touchstone)
            if args.report is not None:
                write_json_report(result, args.report)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            f"eval-idem-like-model basis={result['basis']} "
            f"poles={result['pole_count']} "
            f"z_log_rms={result['z_log_magnitude_rms_error']:.6g} "
            f"diag_z_log_rms={result['diagonal_z_log_magnitude_rms_error']:.6g} "
            f"s_mean_rms={result.get('s_mean_rms_error', float('nan')):.6g} "
            f"s_rel_rms={result['s_relative_rms_error']:.6g}"
        )
        return 0
    if args.command == "refine-idem-like":
        try:
            result = refine_local_idem_like_model(
                args.model,
                args.touchstone,
                args.output,
                iterations=args.iterations,
                candidate_pair_count=args.candidate_pair_count,
                relative_step=args.relative_step,
                fit_max_frequency_points=args.fit_max_frequency_points,
                selection_metric=args.selection_metric,
                rcond=args.rcond,
            )
            write_json_report(result, args.report)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        initial = result["initial"]
        best = result["best"]
        print(
            f"refine-idem-like output={result['output_path']} "
            f"z_log_rms={initial['z_log_magnitude_rms_error']:.6g}->{best['z_log_magnitude_rms_error']:.6g} "
            f"diag_z_log_rms={initial['diagonal_z_log_magnitude_rms_error']:.6g}->"
            f"{best['diagonal_z_log_magnitude_rms_error']:.6g} "
            f"s_mean_rms={initial.get('s_mean_rms_error', float('nan')):.6g}->"
            f"{best.get('s_mean_rms_error', float('nan')):.6g} "
            f"s_rel_rms={initial['s_relative_rms_error']:.6g}->{best['s_relative_rms_error']:.6g}"
        )
        return 0
    if args.command == "export-idem-like-touchstone":
        try:
            result = export_local_idem_like_touchstone(
                args.model,
                args.output,
                reference_touchstone_path=args.reference,
            )
            if args.report is not None:
                write_json_report(result, args.report)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            f"export-idem-like-touchstone output={result['output_path']} "
            f"ports={result['ports']} "
            f"points={result['frequency_points']}"
        )
        return 0
    if args.command == "export-idem-like-statespace":
        try:
            result = export_local_idem_like_state_space(args.model, args.output)
            if args.report is not None:
                write_json_report(result, args.report)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            f"export-idem-like-statespace output={result['output_path']} "
            f"basis={result['basis']} "
            f"ports={result['ports']} "
            f"states={result['states']}"
        )
        return 0
    if args.command == "eval-idem-like-statespace":
        try:
            result = evaluate_local_idem_like_state_space(args.statespace, args.touchstone)
            if args.report is not None:
                write_json_report(result, args.report)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            f"eval-idem-like-statespace basis={result['basis']} "
            f"states={result['states']} "
            f"z_log_rms={result['z_log_magnitude_rms_error']:.6g} "
            f"diag_z_log_rms={result['diagonal_z_log_magnitude_rms_error']:.6g} "
            f"s_mean_rms={result.get('s_mean_rms_error', float('nan')):.6g} "
            f"s_rel_rms={result['s_relative_rms_error']:.6g}"
        )
        return 0
    if args.command == "compare-sparam-bands":
        try:
            models = _parse_labeled_paths(args.model, "--model")
            run_touchstone_banded_comparison(
                args.raw,
                models,
                output=args.output,
                csv=args.csv,
                html=args.html,
            )
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"compare-sparam-bands models={len(models)} output={args.output}")
        return 0
    if args.command == "fit-modal-z":
        from agent_spice.sparam.modal import ModalZFitConfig

        _apply_modal_auto_preset(args, effective_argv)

        # Build config
        cfg = ModalZFitConfig(
            auto_preset=args.auto_preset,
            mode_count=args.mode_count,
            basis_anchor_ports=_parse_tuple_int(getattr(args, "basis_anchor_ports", None)) or (),
            basis_frequency_sample_count=args.basis_frequency_sample_count,
            basis_frequency_sampling=args.basis_frequency_sampling,
            decomposition=args.decomposition,
            scalar_fit_order=args.scalar_fit_order,
            frequency_sample_count=getattr(args, "frequency_sample_count", None),
            frequency_sample_head_count=args.frequency_sample_head_count,
            pole_damping=getattr(args, "pole_damping", 0.05),
            peak_pole_frequency_head_count=args.peak_pole_frequency_head_count,
            peak_pole_entry_count=args.peak_pole_entry_count,
            peak_pole_full_pair_count=args.peak_pole_full_pair_count,
            peak_pole_complete_order=args.peak_pole_complete_order,
            reduced_fit_method=args.reduced_fit_method,
            vector_target_error=args.vector_target_error,
            vector_iters_final=args.vector_iters_final,
            shared_pole_trace_count=getattr(args, "shared_pole_trace_count", 3),
            relative_weight_power=args.relative_weight_power,
            relative_weight_mode=args.relative_weight_mode,
            relative_weight_iterations=args.relative_weight_iterations,
            relative_weight_update=args.relative_weight_update,
            target_error_weight_power=args.target_error_weight_power,
            target_error_weight_max=args.target_error_weight_max,
            target_error_pair_count=args.target_error_pair_count,
            residual_pair_count=args.residual_pair_count,
            residual_fit_order=args.residual_fit_order,
            residual_pole_damping=getattr(args, "residual_pole_damping", None),
            residual_weight_power=args.residual_weight_power,
            residual_gain=args.residual_gain,
            residual_mirror_pairs=args.residual_mirror_pairs,
            auto_order_candidates=_parse_tuple_int(getattr(args, "auto_order_candidates", None)),
            auto_basis_mode_counts=_parse_tuple_int(getattr(args, "auto_basis_mode_counts", None)),
            auto_basis_sample_counts=_parse_tuple_int(getattr(args, "auto_basis_sample_counts", None)),
            auto_basis_anchor_port_counts=_parse_tuple_int(getattr(args, "auto_basis_anchor_port_counts", None)),
            auto_basis_anchor_candidate_count=getattr(args, "auto_basis_anchor_candidate_count", None),
            auto_basis_anchor_combo_count=args.auto_basis_anchor_combo_count,
            auto_pole_dampings=_parse_tuple_float(getattr(args, "auto_pole_dampings", None)),
            auto_shared_pole_trace_counts=_parse_tuple_int(getattr(args, "auto_shared_pole_trace_counts", None)),
            auto_peak_pole_entry_counts=_parse_tuple_int(getattr(args, "auto_peak_pole_entry_counts", None)),
            auto_basis_diagonal_weight=args.auto_basis_diagonal_weight,
            auto_order_max_z_log_magnitude_rms_error=getattr(args, "auto_order_max_z_log_rms_error", None),
            auto_order_max_diagonal_z_log_magnitude_rms_error=getattr(args, "auto_order_max_diagonal_z_log_rms_error", None),
        )

        # Run Touchstone fit
        from agent_spice.sparam.modal import fit_modal_z_touchstone
        result = fit_modal_z_touchstone(args.touchstone, cfg)

        # Check quality
        quality_info = check_modal_quality(result, args)

        # Write reports
        from agent_spice.sparam.modal_report import write_modal_z_json_report, write_modal_z_html_report

        if getattr(args, "report", None):
            write_modal_z_json_report(
                result,
                args.report,
                args.touchstone,
                cfg,
                quality=quality_info,
            )
        if getattr(args, "html_report", None):
            write_modal_z_html_report(
                result,
                args.html_report,
                args.touchstone,
                cfg,
                quality=quality_info,
            )

        if args.fail_on_quality and quality_info["status"] == "FAIL":
            print(f"error: modal-z quality gate failed: {quality_info['blocking_reasons']}", file=sys.stderr)
            return 1
        return 0
    if args.command == "preflight-sparam-corpus":
        from agent_spice.sparam.corpus_preflight import preflight_promotion_corpus

        try:
            report = preflight_promotion_corpus(args.manifest, args.report)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"PASS: {report.case_count} corpus inputs validated; report={args.report}")
        return 0
    if args.command == "benchmark-sparam":
        if args.order_sweep and not args.run_fit:
            print("error: --order-sweep requires --run-fit", file=sys.stderr)
            return 1

        from agent_spice.sparam.benchmark import load_benchmark_cases, write_benchmark_reports
        try:
            cases = load_benchmark_cases(args.manifest)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        known_ids = {c.id for c in cases}
        if args.case:
            for cid in args.case:
                if cid not in known_ids:
                    print(f"error: Benchmark case id not found: {cid}", file=sys.stderr)
                    return 1

        case_ids = set(args.case) if args.case else None
        order_sweep = _parse_int_list(args.order_sweep) if args.order_sweep else None

        output_root = args.output_root or Path("runs-sparam/benchmark")

        results = run_sparam_benchmarks(
            manifest_path=args.manifest,
            output_root=output_root,
            run_fit=args.run_fit,
            case_ids=case_ids,
            order_sweep=order_sweep,
        )

        if args.output:
            write_benchmark_reports(results, args.output, args.csv)

        for r in results:
            cid = r["case_id"]
            status = r["status"]
            q_status = r.get("quality_status")
            q_str = f" {q_status}" if q_status else ""
            print(f"{cid}: {status}{q_str}")

        return 0
    raise ValueError(f"Unsupported command '{args.command}'")



if __name__ == "__main__":
    raise SystemExit(main())
