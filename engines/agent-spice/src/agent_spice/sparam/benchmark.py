from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import time
import tracemalloc
from typing import Any, Callable

import yaml

from agent_spice.sparam.fitting import SParamFitConfig, fit_touchstone_to_spice
from agent_spice.sparam.io import load_touchstone_metadata


_TOUCHSTONE_SUFFIX_RE = re.compile(r"\.s(?P<ports>\d+)p$", re.IGNORECASE)
_FREQUENCY_SCALES = {
    "HZ": 1.0,
    "KHZ": 1.0e3,
    "MHZ": 1.0e6,
    "GHZ": 1.0e9,
}


@dataclass(frozen=True)
class BenchmarkContract:
    contract_version: str = "sparam_full_corpus_v1"
    rms_target: float = 0.001
    passivity_epsilon: float = 1.0e-6
    max_order: int = 100
    threads: int = 8
    phase_timeout_seconds: float = 7200.0

    def __post_init__(self) -> None:
        if not self.contract_version:
            raise ValueError("contract_version must not be empty")
        if not math.isfinite(self.rms_target) or self.rms_target <= 0.0:
            raise ValueError("rms_target must be finite and positive")
        if not math.isfinite(self.passivity_epsilon) or self.passivity_epsilon < 0.0:
            raise ValueError("passivity_epsilon must be finite and non-negative")
        if self.max_order < 1:
            raise ValueError("max_order must be at least 1")
        if self.threads < 1:
            raise ValueError("threads must be at least 1")
        if not math.isfinite(self.phase_timeout_seconds) or self.phase_timeout_seconds <= 0.0:
            raise ValueError("phase_timeout_seconds must be finite and positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorpusEntry:
    path: Path
    relative_path: str
    sha256: str
    size_bytes: int
    ports: int
    frequency_points: int
    frequency_min_hz: float
    frequency_max_hz: float
    reference_impedance: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class ToolTrial:
    tool: str
    requested_order: int
    effective_order: int | None = None
    pre_mean_rms: float | None = None
    final_mean_rms: float | None = None
    authoritative_passive: bool | None = None
    final_max_sigma: float | None = None
    sampled_max_sigma: float | None = None
    fit_seconds: float = 0.0
    check_seconds: float = 0.0
    enforce_seconds: float = 0.0
    validation_seconds: float = 0.0
    elapsed_seconds: float = 0.0
    peak_memory_mb: float = 0.0
    target_met: bool = False
    status: str = "FAIL"
    failure_reason: str | None = None
    fingerprint: str = ""
    pre_max_sigma: float | None = None
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def meets_contract(self, contract: BenchmarkContract) -> bool:
        return bool(
            self.target_met
            and self.effective_order is not None
            and 1 <= self.effective_order <= contract.max_order
            and _is_finite_at_most(self.final_mean_rms, contract.rms_target)
            and self.authoritative_passive is True
            and _is_finite_at_most(
                self.final_max_sigma,
                1.0 + contract.passivity_epsilon,
            )
            and _is_finite_at_most(
                self.sampled_max_sigma,
                1.0 + contract.passivity_epsilon,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class ToolSearchResult:
    contract: BenchmarkContract
    trials: tuple[ToolTrial, ...]
    selected_trial: ToolTrial | None
    stop_reason: str

    @property
    def selected_order(self) -> int | None:
        if self.selected_trial is None:
            return None
        return self.selected_trial.effective_order

    @property
    def attempted_orders(self) -> tuple[int, ...]:
        return tuple(trial.requested_order for trial in self.trials)

    @property
    def target_met(self) -> bool:
        return self.selected_trial is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract.to_dict(),
            "trials": [trial.to_dict() for trial in self.trials],
            "selected_trial": None if self.selected_trial is None else self.selected_trial.to_dict(),
            "stop_reason": self.stop_reason,
        }


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _is_finite_at_most(value: float | None, upper_bound: float) -> bool:
    return value is not None and math.isfinite(value) and value <= upper_bound


def _touchstone_frequency_range_hz(path: Path, ports: int) -> tuple[float, float, int]:
    values_per_frequency = 1 + (2 * ports * ports)
    token_offset = 0
    frequencies: list[float] = []
    frequency_scale: float | None = None

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("!"):
                continue
            if stripped.startswith("["):
                raise ValueError(f"Touchstone 2.0 frequency scan is not supported: {path}")
            if stripped.startswith("#"):
                tokens = stripped[1:].split()
                if tokens:
                    frequency_scale = _FREQUENCY_SCALES.get(tokens[0].upper())
                continue

            data = stripped.split("!", 1)[0].strip()
            for token in data.split():
                if token_offset == 0:
                    try:
                        frequencies.append(float(token))
                    except ValueError as exc:
                        raise ValueError(f"Invalid Touchstone frequency token in {path}: {token}") from exc
                token_offset = (token_offset + 1) % values_per_frequency

    if frequency_scale is None:
        raise ValueError(f"Touchstone frequency unit is missing or unsupported: {path}")
    if not frequencies or token_offset != 0:
        raise ValueError(f"Touchstone data rows are incomplete: {path}")
    scaled = [frequency * frequency_scale for frequency in frequencies]
    if not all(math.isfinite(frequency) and frequency >= 0.0 for frequency in scaled):
        raise ValueError(f"Touchstone frequencies must be finite and non-negative: {path}")
    return min(scaled), max(scaled), len(scaled)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_touchstone_corpus(root: Path) -> tuple[CorpusEntry, ...]:
    root = root.resolve()
    entries: list[CorpusEntry] = []
    for path in root.iterdir():
        if not path.is_file():
            continue
        match = _TOUCHSTONE_SUFFIX_RE.search(path.name)
        if match is None:
            continue
        ports = int(match.group("ports"))
        metadata = load_touchstone_metadata(path)
        if metadata.ports != ports:
            raise ValueError(f"Touchstone suffix/metadata port mismatch: {path}")
        frequency_min_hz, frequency_max_hz, scanned_points = _touchstone_frequency_range_hz(
            path,
            ports,
        )
        if scanned_points != metadata.frequency_points:
            raise ValueError(f"Touchstone frequency count mismatch: {path}")
        entries.append(
            CorpusEntry(
                path=path.resolve(),
                relative_path=path.relative_to(root).as_posix(),
                sha256=_sha256_file(path),
                size_bytes=path.stat().st_size,
                ports=ports,
                frequency_points=metadata.frequency_points,
                frequency_min_hz=frequency_min_hz,
                frequency_max_hz=frequency_max_hz,
                reference_impedance=tuple(float(value) for value in metadata.reference_impedance),
            )
        )
    return tuple(sorted(entries, key=lambda entry: (entry.ports, entry.path.name.lower())))


def run_benchmark_order_search(
    contract: BenchmarkContract,
    evaluate_order: Callable[[int], ToolTrial],
) -> ToolSearchResult:
    cache: dict[int, ToolTrial] = {}
    evaluation_order: list[int] = []

    def evaluate(order: int) -> ToolTrial:
        if order not in cache:
            trial = evaluate_order(order)
            if trial.requested_order != order:
                raise ValueError("order evaluator returned a mismatched requested_order")
            cache[order] = trial
            evaluation_order.append(order)
        return cache[order]

    if contract.max_order < 4:
        coarse_orders = list(range(1, contract.max_order + 1))
    else:
        coarse_orders = list(range(4, contract.max_order + 1, 2))
        if contract.max_order % 2 == 1:
            coarse_orders.append(contract.max_order)

    previous_failed_order = 0 if contract.max_order < 4 else 2
    first_passing_order: int | None = None
    for order in coarse_orders:
        trial = evaluate(order)
        if trial.meets_contract(contract):
            first_passing_order = order
            break
        previous_failed_order = order

    if first_passing_order is None:
        return ToolSearchResult(
            contract=contract,
            trials=tuple(cache[order] for order in evaluation_order),
            selected_trial=None,
            stop_reason="target_not_met_before_max_order",
        )

    if contract.max_order >= 4:
        for order in range(previous_failed_order + 1, first_passing_order):
            evaluate(order)

    passing = [trial for trial in cache.values() if trial.meets_contract(contract)]
    selected = min(
        passing,
        key=lambda trial: (
            trial.effective_order if trial.effective_order is not None else math.inf,
            trial.requested_order,
        ),
    )
    return ToolSearchResult(
        contract=contract,
        trials=tuple(cache[order] for order in evaluation_order),
        selected_trial=selected,
        stop_reason="target_met",
    )


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    serialized = json.dumps(_json_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary_path.write_text(serialized, encoding="utf-8")
    temporary_path.replace(path)


def benchmark_fingerprint(
    *,
    input_sha256: str,
    contract: BenchmarkContract,
    tool: str,
    tool_identity: str,
    order: int,
    options: dict[str, Any],
) -> str:
    payload = {
        "input_sha256": input_sha256,
        "contract": contract.to_dict(),
        "tool": tool,
        "tool_identity": tool_identity,
        "order": order,
        "options": options,
    }
    canonical = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
