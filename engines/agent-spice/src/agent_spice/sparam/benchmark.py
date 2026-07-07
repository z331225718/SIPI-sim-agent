from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
import csv
import json
from pathlib import Path
import re
import time
import tracemalloc
from typing import Any

import yaml

from agent_spice.sparam.fitting import SParamFitConfig, fit_touchstone_to_spice
from agent_spice.sparam.io import load_touchstone_metadata


@dataclass(frozen=True)
class SParamBenchmarkCase:
    id: str
    touchstone_path: Path
    description: str = ""
    tags: list[str] = field(default_factory=list)
    fit_config: SParamFitConfig = field(default_factory=SParamFitConfig)


def _safe_case_id(case_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", case_id).strip("_") or "case"


def _resolve_case_path(manifest_path: Path, base_dir: str | Path, touchstone: str | Path) -> Path:
    touchstone_path = Path(touchstone)
    if touchstone_path.is_absolute():
        return touchstone_path
    base_path = Path(base_dir)
    if not base_path.is_absolute():
        base_path = manifest_path.parent / base_path
    return (base_path / touchstone_path).resolve()


def _fit_config_from_mapping(case_id: str, raw_config: dict[str, Any] | None) -> SParamFitConfig:
    if not raw_config:
        return SParamFitConfig()
    field_names = {config_field.name for config_field in fields(SParamFitConfig)}
    normalized = {str(key).replace("-", "_"): value for key, value in raw_config.items()}
    unsupported = sorted(key for key in normalized if key not in field_names)
    if unsupported:
        joined = ", ".join(unsupported)
        raise ValueError(f"Unsupported fit config keys for benchmark case '{case_id}': {joined}")
    return SParamFitConfig(**normalized)


def load_benchmark_cases(manifest_path: Path) -> list[SParamBenchmarkCase]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    base_dir = payload.get("base_dir", ".")
    cases = []
    for raw_case in payload.get("cases", []):
        case_id = str(raw_case["id"])
        cases.append(
            SParamBenchmarkCase(
                id=case_id,
                touchstone_path=_resolve_case_path(manifest_path, base_dir, raw_case["touchstone"]),
                description=str(raw_case.get("description", "")),
                tags=[str(tag) for tag in raw_case.get("tags", [])],
                fit_config=_fit_config_from_mapping(case_id, raw_case.get("fit")),
            )
        )
    return cases


def _selected_cases(cases: list[SParamBenchmarkCase], case_ids: set[str] | None) -> list[SParamBenchmarkCase]:
    if not case_ids:
        return cases
    selected = [case for case in cases if case.id in case_ids]
    missing = sorted(case_ids - {case.id for case in selected})
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Benchmark case id not found: {joined}")
    return selected


def run_benchmark_case(
    case: SParamBenchmarkCase,
    output_root: Path,
    run_fit: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case_id": case.id,
        "description": case.description,
        "tags": case.tags,
        "mode": "fit" if run_fit else "metadata",
        "touchstone_path": str(case.touchstone_path),
        "fit_config": asdict(case.fit_config),
    }
    if not case.touchstone_path.exists():
        result.update(
            {
                "status": "skipped",
                "reason": "touchstone file not found",
                "exists": False,
            }
        )
        return result

    result["exists"] = True
    result["file_size_bytes"] = case.touchstone_path.stat().st_size
    started = time.perf_counter()
    tracemalloc.start()
    try:
        metadata = load_touchstone_metadata(case.touchstone_path)
        result.update(
            {
                "ports": metadata.ports,
                "frequency_points": metadata.frequency_points,
                "reference_impedance": metadata.reference_impedance,
            }
        )
        if run_fit:
            case_output = output_root / _safe_case_id(case.id)
            spice_path = case_output / "model.sp"
            report_path = case_output / "fit_report.json"
            html_report_path = case_output / "fit_report.html"
            log_path = case_output / "fit.log"
            fit_result = fit_touchstone_to_spice(
                case.touchstone_path,
                spice_path,
                config=case.fit_config,
                report_path=report_path,
                html_report_path=html_report_path,
                log_path=log_path,
            )
            quality = fit_result.quality_report.to_dict()
            result.update(
                {
                    "artifacts": {
                        "spice_path": str(spice_path),
                        "json_report_path": str(report_path),
                        "html_report_path": str(html_report_path),
                        "log_path": str(log_path),
                    },
                    "spice_size_bytes": spice_path.stat().st_size if spice_path.exists() else None,
                    "fit_frequency_points": getattr(fit_result, "fit_frequency_points", None),
                    "fit_frequency_range_hz": getattr(fit_result, "fit_frequency_range_hz", None),
                    "comparison_frequency_points": getattr(fit_result, "comparison_frequency_points", None),
                    "quality_frequency_points": getattr(fit_result, "quality_frequency_points", None),
                    "rms_error": getattr(fit_result, "rms_error", None),
                    "comparison_rms_error": getattr(fit_result, "comparison_rms_error", None),
                    "z_comparison_rms_error": getattr(fit_result, "z_comparison_rms_error", None),
                    "z_log_magnitude_rms_error": getattr(fit_result, "z_log_magnitude_rms_error", None),
                    "quality_status": quality["status"],
                    "allowed_for": quality["allowed_for"],
                    "blocking_reasons": quality["blocking_reasons"],
                    "warnings": quality["warnings"],
                    "quality_diagnostics": quality["diagnostics"],
                }
            )
        result["status"] = "completed"
    except Exception as exc:
        result.update(
            {
                "status": "failed",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )
    finally:
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result["elapsed_seconds"] = time.perf_counter() - started
        result["peak_memory_mb"] = peak_bytes / 1024 / 1024
        result["current_memory_mb"] = current_bytes / 1024 / 1024
    return result


def run_sparam_benchmarks(
    manifest_path: Path,
    output_root: Path,
    *,
    run_fit: bool = False,
    case_ids: set[str] | None = None,
    order_sweep: list[int] | None = None,
) -> list[dict[str, Any]]:
    if order_sweep is not None and not run_fit:
        raise ValueError("order_sweep requires run_fit=True")
    cases = _selected_cases(load_benchmark_cases(manifest_path), case_ids)
    if order_sweep is None:
        return [run_benchmark_case(case, output_root, run_fit=run_fit) for case in cases]
    results: list[dict[str, Any]] = []
    for case in cases:
        results.extend(run_order_sweep(case, output_root, order_sweep))
    return results


def run_order_sweep(
    case: SParamBenchmarkCase,
    output_root: Path,
    orders: list[int],
) -> list[dict[str, Any]]:
    if not orders:
        raise ValueError("orders must contain at least one model order")
    results: list[dict[str, Any]] = []
    for order in orders:
        if order < 1:
            raise ValueError("model order values must be >= 1")
        sweep_case = replace(
            case,
            id=f"{case.id}_order{order}",
            fit_config=replace(case.fit_config, model_order_max=order),
        )
        result = run_benchmark_case(sweep_case, output_root, run_fit=True)
        result["case_id"] = f"{case.id}/order{order}"
        result["base_case_id"] = case.id
        result["sweep_model_order_max"] = order
        results.append(result)
    return results


def write_benchmark_jsonl(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, sort_keys=True) + "\n")


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def write_benchmark_csv(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "base_case_id",
        "status",
        "mode",
        "reason",
        "error_type",
        "error",
        "touchstone_path",
        "file_size_bytes",
        "ports",
        "frequency_points",
        "fit_frequency_points",
        "fit_frequency_range_hz",
        "comparison_frequency_points",
        "quality_frequency_points",
        "elapsed_seconds",
        "peak_memory_mb",
        "spice_size_bytes",
        "rms_error",
        "comparison_rms_error",
        "z_comparison_rms_error",
        "z_log_magnitude_rms_error",
        "sweep_model_order_max",
        "quality_status",
        "allowed_for",
        "blocking_reasons",
        "warnings",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({field: _csv_value(result.get(field)) for field in fieldnames})


def write_benchmark_reports(results: list[dict[str, Any]], jsonl_path: Path, csv_path: Path | None) -> None:
    write_benchmark_jsonl(results, jsonl_path)
    if csv_path is not None:
        write_benchmark_csv(results, csv_path)
