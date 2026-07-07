from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, Any

from agent_spice.deck.builder import write_case_artifacts
from agent_spice.hspice.alter import split_alter_cases
from agent_spice.hspice.converter import convert_hspice_deck
from agent_spice.project import prepare_run_directory
from agent_spice.sparam.fitting import SParamFitConfig, fit_touchstone_to_spice, fit_touchstone_to_spice_auto_order


SPARAM_IDEM_FAST_CANDIDATES_LARGE_PORT = "9,10,12,14,17,20"
SPARAM_IDEM_FAST_TARGET_MEAN_RMS = 0.002


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
        return _argument_was_explicit(argv, opt)

    ports = 2
    match = re.search(r"\.s(\d+)p", str(getattr(args, "touchstone", "")).lower())
    if match:
        ports = int(match.group(1))

    if args.auto_preset != "idem-fast":
        raise ValueError(f"Unsupported S-parameter auto preset '{args.auto_preset}'")

    candidates = SPARAM_IDEM_FAST_CANDIDATES_LARGE_PORT if ports >= 60 else None
    target = SPARAM_IDEM_FAST_TARGET_MEAN_RMS if ports >= 60 else None
    if not is_explicit("--mode"):
        args.mode = "manual"
    if not is_explicit("--n-poles-real"):
        args.n_poles_real = 0 if ports >= 60 else 4
    if not is_explicit("--n-poles-cmplx"):
        args.n_poles_cmplx = 2 if ports >= 60 else (30 if ports >= 30 else 18)
    if not is_explicit("--init-pole-spacing"):
        args.init_pole_spacing = "log" if ports >= 60 else "lin"
    if not is_explicit("--fit-max-iterations"):
        args.fit_max_iterations = 14 if ports >= 60 else (6 if ports >= 30 else 5)
    if not is_explicit("--fit-max-frequency-points"):
        args.fit_max_frequency_points = 256
    if not is_explicit("--relocation-backend"):
        args.relocation_backend = "streaming-reciprocal" if ports >= 30 else "streaming"
    if not is_explicit("--vector-fit-backend"):
        args.vector_fit_backend = "native" if ports >= 30 else "skrf"
    if not is_explicit("--use-lightweight-network"):
        args.use_lightweight_network = True
    if ports >= 60 and not is_explicit("--high-frequency-complex-pairs"):
        args.high_frequency_complex_pairs = 2
    if ports >= 60 and not is_explicit("--high-frequency-complex-pair-damping"):
        args.high_frequency_complex_pair_damping = 0.03
    if ports >= 60 and not is_explicit("--high-frequency-complex-pair-lower-fraction"):
        args.high_frequency_complex_pair_lower_fraction = 0.68
    if candidates is not None and not is_explicit("--auto-model-order-candidates"):
        args.auto_model_order_candidates = candidates
    if target is not None and not is_explicit("--auto-target-mean-rms-error"):
        args.auto_target_mean_rms_error = target
    if not is_explicit("--skip-passivity-enforce") and not is_explicit("--enforce-passivity"):
        args.skip_passivity_enforce = True
    if not is_explicit("--skip-passivity-check") and not is_explicit("--check-passivity"):
        args.skip_passivity_check = True


def run_hspice(deck_path: Path, backend_name: str, output_root: Path, execute: bool = False) -> int:
    source = deck_path.read_text(encoding="utf-8")
    deck_id = deck_path.stem
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    source_path = _stable_source_path(deck_path)
    cases = split_alter_cases(source, stem=deck_path.stem)
    for case in cases:
        conversion = convert_hspice_deck(case.text, backend=backend_name)
        case_kind, alter_label = _case_metadata(deck_id, case.name)
        conversion.report.set_deck(deck_id=deck_id, source=source_path, sha256=source_hash)
        conversion.report.set_case(name=case.name, kind=case_kind, alter_label=alter_label)
        run_dir = prepare_run_directory(output_root, project_name=deck_id, case_name=case.name)
        artifacts = write_case_artifacts(run_dir, conversion.deck_text, conversion.report)
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
            (run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
            (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
            if not result.ok:
                return result.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    effective_argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="agent-spice")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run-hspice")
    run_parser.add_argument("deck", type=Path)
    run_parser.add_argument("--backend", choices=["ngspice", "xyce", "xyce-xdm"], default="ngspice")
    run_parser.add_argument("--output-root", type=Path, default=Path("runs"))
    run_parser.add_argument("--execute", action="store_true")

    fit_parser = subparsers.add_parser(
        "fit-sparam",
        description="Fit a Touchstone S-parameter file with the IdEM-fast baseline.",
    )
    fit_parser.add_argument("touchstone", type=Path, help="Input .sNp Touchstone file.")
    fit_parser.add_argument("--output", type=Path, required=True, help="Output SPICE subcircuit path.")
    fit_parser.add_argument("--report", type=Path, help="JSON fit report path; defaults next to --output.")
    fit_parser.add_argument("--html-report", type=Path, help="HTML fit report path; defaults next to --output.")
    fit_parser.add_argument("--log", type=Path, help="Progress log path.")
    fit_parser.add_argument("--auto-preset", choices=["idem-fast"], default="idem-fast", help=argparse.SUPPRESS)
    fit_parser.add_argument(
        "--auto-model-order-candidates",
        help="Comma-separated order candidates for auto-order search; large-port default is 9,10,12,14,17,20.",
    )
    fit_parser.add_argument(
        "--auto-target-mean-rms-error",
        type=float,
        help="Mean RMS stop target for auto-order search; large-port default is 0.002.",
    )
    fit_parser.add_argument("--quality-profile", choices=["explore", "signoff"], default="explore", help="Report quality profile.")
    fit_parser.add_argument("--fail-on-quality", action="store_true", help="Return non-zero when the quality report blocks.")
    fit_parser.add_argument("--allow-quality-warnings", action="store_true", help="Allow WARN quality status with --fail-on-quality.")
    fit_parser.add_argument("--enforce-passivity", dest="skip_passivity_enforce", action="store_false", help="Run passivity enforcement after fitting.")
    fit_parser.add_argument("--check-passivity", dest="skip_passivity_check", action="store_false", help="Run passivity checks before/after enforcement.")
    fit_parser.add_argument("--subckt-name", default="s_equivalent", help="SPICE subcircuit name.")
    fit_parser.add_argument("--exporter", choices=["idem", "skrf"], default="skrf", help="SPICE exporter format.")
    _add_hidden_argument(fit_parser, "--mode", choices=["auto", "manual"], default="manual")
    _add_hidden_argument(fit_parser, "--n-poles-real", type=int, default=0)
    _add_hidden_argument(fit_parser, "--n-poles-cmplx", type=int, default=2)
    _add_hidden_argument(fit_parser, "--init-pole-spacing", choices=["lin", "log"], default="log")
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
    _add_hidden_argument(fit_parser, "--fit-max-iterations", type=int, default=14)
    _add_hidden_argument(fit_parser, "--passivity-samples", type=int, default=8)
    _add_hidden_argument(fit_parser, "--passivity-max-iterations", type=int, default=1)
    _add_hidden_argument(fit_parser, "--passivity-active-variables", type=int, default=512)
    _add_hidden_argument(fit_parser, "--passivity-f-max", type=float)
    _add_hidden_argument(fit_parser, "--no-preserve-dc", action="store_true")
    _add_hidden_argument(fit_parser, "--fit-frequency-stride", type=int, default=1)
    _add_hidden_argument(fit_parser, "--fit-max-frequency-points", type=int, default=256)
    _add_hidden_argument(fit_parser, "--fit-f-min", type=float)
    _add_hidden_argument(fit_parser, "--fit-f-max", type=float)
    _add_hidden_argument(
        fit_parser,
        "--relocation-backend",
        choices=["skrf", "streaming", "streaming-lowmem", "streaming-reciprocal"],
        default="streaming-reciprocal",
    )
    _add_hidden_argument(fit_parser, "--vector-fit-backend", choices=["skrf", "native"], default="native")
    _add_hidden_argument(fit_parser, "--high-frequency-complex-pairs", type=int, default=2)
    _add_hidden_argument(fit_parser, "--high-frequency-complex-pair-damping", type=float, default=0.03)
    _add_hidden_argument(fit_parser, "--high-frequency-complex-pair-lower-fraction", type=float, default=0.68)
    _add_hidden_argument(fit_parser, "--use-lightweight-network", action="store_true", default=True)
    _add_hidden_argument(fit_parser, "--skip-passivity-enforce", dest="skip_passivity_enforce", action="store_true", default=True)
    _add_hidden_argument(fit_parser, "--skip-passivity-check", dest="skip_passivity_check", action="store_true", default=True)
    _add_hidden_argument(fit_parser, "--max-comparison-rms-error", type=float, default=0.05)
    _add_hidden_argument(fit_parser, "--max-passivity-epsilon", type=float, default=1e-6)
    _add_hidden_argument(fit_parser, "--require-dc", action="store_true")

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

    band_parser = subparsers.add_parser("compare-sparam-bands")
    band_parser.add_argument("raw", type=Path)
    band_parser.add_argument("--model", action="append", required=True, help="Model Touchstone as LABEL=PATH")
    band_parser.add_argument("--output", type=Path, required=True)
    band_parser.add_argument("--csv", type=Path)
    band_parser.add_argument("--html", type=Path)

    args = parser.parse_args(effective_argv)
    if args.command == "run-hspice":
        return run_hspice(args.deck, args.backend, args.output_root, args.execute)
    if args.command == "fit-sparam":
        try:
            _apply_sparam_auto_preset(args, effective_argv)
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
            check_passivity=not args.skip_passivity_check,
            enforce_passivity=not args.skip_passivity_enforce,
            passivity_samples=args.passivity_samples,
            passivity_max_iterations=args.passivity_max_iterations,
            passivity_active_variables=args.passivity_active_variables,
            passivity_f_max=args.passivity_f_max,
            preserve_dc=not args.no_preserve_dc,
            fit_frequency_stride=args.fit_frequency_stride,
            fit_max_frequency_points=args.fit_max_frequency_points,
            fit_f_min=args.fit_f_min,
            fit_f_max=args.fit_f_max,
            relocation_backend=args.relocation_backend,
            use_lightweight_network=args.use_lightweight_network,
            vector_fit_backend=args.vector_fit_backend,
            high_frequency_complex_pair_count=args.high_frequency_complex_pairs,
            high_frequency_complex_pair_damping=args.high_frequency_complex_pair_damping,
            high_frequency_complex_pair_lower_fraction=args.high_frequency_complex_pair_lower_fraction,
            quality_profile=args.quality_profile,
            max_comparison_rms_error=args.max_comparison_rms_error,
            max_passivity_epsilon=args.max_passivity_epsilon,
            require_dc=args.require_dc,
            subckt_name=args.subckt_name,
            exporter=args.exporter,
        )

        report_path = args.report or (args.output.parent / "fit_report.json")
        html_report_path = args.html_report or (args.output.parent / "fit_report.html")
        try:
            if args.auto_model_order_candidates:
                if args.auto_target_mean_rms_error is None:
                    raise ValueError("--auto-target-mean-rms-error is required with --auto-model-order-candidates")
                result = fit_touchstone_to_spice_auto_order(
                    args.touchstone,
                    args.output,
                    config=config,
                    order_candidates=_parse_int_list(args.auto_model_order_candidates),
                    target_mean_rms_error=args.auto_target_mean_rms_error,
                    report_path=report_path,
                    html_report_path=html_report_path,
                    log_path=args.log,
                )
            else:
                result = fit_touchstone_to_spice(
                    args.touchstone,
                    args.output,
                    config=config,
                    report_path=report_path,
                    html_report_path=html_report_path,
                    log_path=args.log,
                )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.fail_on_quality:
            failure = _quality_gate_failure(result, allow_warnings=args.allow_quality_warnings)
            if failure is not None:
                print(f"error: {failure}", file=sys.stderr)
                return 1
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
