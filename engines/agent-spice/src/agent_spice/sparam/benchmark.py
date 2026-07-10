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
from typing import Any, Callable, Iterator

import numpy as np
import yaml

from agent_spice.sparam.fitting import NATIVE_BASELINE_VERSION, SParamFitConfig, fit_touchstone_to_spice
from agent_spice.sparam.io import load_touchstone_metadata


_TOUCHSTONE_SUFFIX_RE = re.compile(r"\.s(?P<ports>\d+)p$", re.IGNORECASE)
_FREQUENCY_SCALES = {
    "HZ": 1.0,
    "KHZ": 1.0e3,
    "MHZ": 1.0e6,
    "GHZ": 1.0e9,
}


def native_baseline_fingerprint_options() -> dict[str, str]:
    return {"native_baseline_version": NATIVE_BASELINE_VERSION}


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


def source_file_identity(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        stat = resolved.stat()
        digest = _sha256_file(resolved)
    except OSError:
        return f"{resolved}|missing"
    return f"{resolved}|size={stat.st_size}|sha256={digest}"


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


def _iter_touchstone_s_ri_chunks(
    path: Path,
    *,
    ports: int,
    chunk_size: int,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    expected_values = 1 + (2 * ports * ports)
    frequency_scale: float | None = None
    data_format: str | None = None
    header_seen = False
    pending_values: list[float] = []
    chunk_frequencies: list[float] = []
    chunk_responses: list[np.ndarray] = []

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.split("!", 1)[0].strip()
            if not line:
                continue
            if line.startswith("["):
                raise ValueError("Touchstone 2.0 is not supported by the independent audit")
            if line.startswith("#"):
                tokens = line[1:].upper().split()
                if len(tokens) < 3 or tokens[1] != "S" or tokens[2] not in {"RI", "MA", "DB"}:
                    raise ValueError("Independent audit requires Touchstone S-parameter RI, MA, or DB data")
                frequency_scale = _FREQUENCY_SCALES.get(tokens[0])
                if frequency_scale is None:
                    raise ValueError(f"Unsupported Touchstone frequency unit: {tokens[0]}")
                data_format = tokens[2]
                header_seen = True
                continue
            if not header_seen:
                continue

            try:
                pending_values.extend(float(token) for token in line.split())
            except ValueError as exc:
                raise ValueError(f"Invalid numeric Touchstone data in {path}") from exc
            while len(pending_values) >= expected_values:
                point = pending_values[:expected_values]
                pending_values = pending_values[expected_values:]
                pairs = np.asarray(point[1:], dtype=float).reshape(-1, 2)
                if data_format == "RI":
                    values = pairs[:, 0] + 1j * pairs[:, 1]
                else:
                    magnitude = pairs[:, 0] if data_format == "MA" else np.power(10.0, pairs[:, 0] / 20.0)
                    values = magnitude * np.exp(1j * np.deg2rad(pairs[:, 1]))
                response = values.reshape(ports, ports)
                chunk_frequencies.append(point[0] * frequency_scale)
                chunk_responses.append(response)
                if len(chunk_frequencies) == chunk_size:
                    yield np.asarray(chunk_frequencies, dtype=float), np.asarray(chunk_responses)
                    chunk_frequencies = []
                    chunk_responses = []

    if pending_values:
        raise ValueError(f"Incomplete Touchstone data block in {path}")
    if chunk_frequencies:
        yield np.asarray(chunk_frequencies, dtype=float), np.asarray(chunk_responses)


def _invalid_audit(reason: str, **details: Any) -> dict[str, Any]:
    return {
        "status": "INVALID",
        "failure_reason": reason,
        "frequency_grid_match": False,
        "mean_rms": None,
        "sampled_max_sigma": None,
        **details,
    }


def audit_touchstone_model(
    original_path: Path,
    exported_path: Path,
    *,
    chunk_size: int = 32,
) -> dict[str, Any]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")

    try:
        original_metadata = load_touchstone_metadata(original_path)
        exported_metadata = load_touchstone_metadata(exported_path)
    except (OSError, ValueError) as exc:
        return _invalid_audit("touchstone_parse_error", error=str(exc))

    base_details = {
        "ports": original_metadata.ports,
        "frequency_points": original_metadata.frequency_points,
        "exported_ports": exported_metadata.ports,
        "exported_frequency_points": exported_metadata.frequency_points,
    }
    if exported_metadata.ports != original_metadata.ports:
        return _invalid_audit("port_count_mismatch", **base_details)
    if exported_metadata.frequency_points != original_metadata.frequency_points:
        return _invalid_audit("frequency_point_count_mismatch", **base_details)

    original_chunks = _iter_touchstone_s_ri_chunks(
        original_path,
        ports=original_metadata.ports,
        chunk_size=chunk_size,
    )
    exported_chunks = _iter_touchstone_s_ri_chunks(
        exported_path,
        ports=exported_metadata.ports,
        chunk_size=chunk_size,
    )
    squared_error_sum = 0.0
    scalar_count = 0
    sampled_max_sigma = 0.0
    audited_points = 0

    try:
        for original_chunk, exported_chunk in zip(original_chunks, exported_chunks, strict=True):
            original_frequencies, original_s = original_chunk
            exported_frequencies, exported_s = exported_chunk
            if not (
                np.all(np.isfinite(original_frequencies))
                and np.all(np.isfinite(exported_frequencies))
                and np.all(np.isfinite(original_s))
                and np.all(np.isfinite(exported_s))
            ):
                return _invalid_audit("non_finite_metric", **base_details)
            if not np.allclose(original_frequencies, exported_frequencies, rtol=1.0e-12, atol=0.0):
                return _invalid_audit("frequency_grid_mismatch", **base_details)
            error = exported_s - original_s
            squared_error_sum += float(np.sum(np.abs(error) ** 2))
            scalar_count += int(error.size)
            audited_points += len(original_frequencies)
            for matrix in exported_s:
                sigma = float(np.linalg.svd(matrix, compute_uv=False)[0])
                sampled_max_sigma = max(sampled_max_sigma, sigma)
    except (OSError, ValueError) as exc:
        return _invalid_audit("touchstone_parse_error", error=str(exc), **base_details)

    if audited_points != original_metadata.frequency_points or scalar_count == 0:
        return _invalid_audit("frequency_point_count_mismatch", **base_details)
    mean_rms = math.sqrt(squared_error_sum / scalar_count)
    if not math.isfinite(mean_rms) or not math.isfinite(sampled_max_sigma):
        return _invalid_audit("non_finite_metric", **base_details)
    return {
        "status": "PASS",
        "failure_reason": None,
        "frequency_grid_match": True,
        "ports": original_metadata.ports,
        "frequency_points": audited_points,
        "exported_ports": exported_metadata.ports,
        "exported_frequency_points": exported_metadata.frequency_points,
        "mean_rms": mean_rms,
        "sampled_max_sigma": sampled_max_sigma,
    }


def accuracy_agrees(
    reported: float | None,
    audited: float | None,
    target: float,
) -> bool:
    if (
        reported is None
        or audited is None
        or not math.isfinite(reported)
        or not math.isfinite(audited)
        or not math.isfinite(target)
        or target <= 0.0
    ):
        return False
    return abs(reported - audited) <= max(1.0e-9, 1.0e-5 * target)


def _finite_non_negative(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(converted) or converted < 0.0:
        return None
    return converted


def _summarize_tool_cell(
    cell: Any,
    contract: BenchmarkContract,
    *,
    input_sha256: Any,
    frequency_points: Any,
) -> dict[str, Any]:
    base = {
        "status": "INVALID",
        "target_met": False,
        "selected_order": None,
        "final_mean_rms": None,
        "final_max_sigma": None,
        "sampled_max_sigma": None,
        "total_search_seconds": None,
        "peak_memory_mb": None,
        "failure_reason": "missing_tool_result",
    }
    if not isinstance(cell, dict) or cell.get("status") != "completed":
        if isinstance(cell, dict):
            base["failure_reason"] = str(cell.get("status") or "invalid_tool_result")
        return base
    if cell.get("input_sha256") != input_sha256:
        base["failure_reason"] = "input_hash_mismatch"
        return base
    if cell.get("frequency_points") != frequency_points:
        base["failure_reason"] = "frequency_point_count_mismatch"
        return base
    search = cell.get("search")
    if not isinstance(search, dict):
        base["failure_reason"] = "missing_search_result"
        return base
    selected = search.get("selected_trial")
    if not isinstance(selected, dict):
        base.update(status="FAIL", failure_reason=str(search.get("stop_reason") or "target_not_met"))
        return base

    order = selected.get("effective_order")
    final_rms = _finite_non_negative(selected.get("final_mean_rms"))
    final_sigma = _finite_non_negative(selected.get("final_max_sigma"))
    sampled_sigma = _finite_non_negative(selected.get("sampled_max_sigma"))
    trials = search.get("trials")
    if (
        not isinstance(order, int)
        or order < 1
        or not isinstance(trials, list)
        or final_rms is None
        or final_sigma is None
        or sampled_sigma is None
    ):
        base["failure_reason"] = "invalid_selected_metrics"
        return base
    elapsed_values = [_finite_non_negative(trial.get("elapsed_seconds")) for trial in trials if isinstance(trial, dict)]
    memory_values = [_finite_non_negative(trial.get("peak_memory_mb")) for trial in trials if isinstance(trial, dict)]
    if len(elapsed_values) != len(trials) or len(memory_values) != len(trials):
        base["failure_reason"] = "invalid_search_resource_metrics"
        return base
    if any(value is None for value in elapsed_values + memory_values):
        base["failure_reason"] = "invalid_search_resource_metrics"
        return base
    target_met = bool(
        selected.get("target_met") is True
        and selected.get("status") == "PASS"
        and selected.get("authoritative_passive") is True
        and order <= contract.max_order
        and final_rms <= contract.rms_target
        and final_sigma <= 1.0 + contract.passivity_epsilon
        and sampled_sigma <= 1.0 + contract.passivity_epsilon
    )
    base.update(
        status="PASS" if target_met else "FAIL",
        target_met=target_met,
        selected_order=order,
        final_mean_rms=final_rms,
        final_max_sigma=final_sigma,
        sampled_max_sigma=sampled_sigma,
        total_search_seconds=sum(value for value in elapsed_values if value is not None),
        peak_memory_mb=max((value for value in memory_values if value is not None), default=0.0),
        failure_reason=None if target_met else str(selected.get("failure_reason") or "target_contract_failed"),
    )
    return base


def _positive_ratio(numerator: Any, denominator: Any) -> float | None:
    top = _finite_non_negative(numerator)
    bottom = _finite_non_negative(denominator)
    if top is None or bottom is None or bottom <= 0.0:
        return None
    return top / bottom


def build_corpus_summary(raw_summary: dict[str, Any]) -> dict[str, Any]:
    contract_payload = raw_summary.get("contract") or {}
    contract_fields = {field.name for field in fields(BenchmarkContract)}
    contract = BenchmarkContract(
        **{name: contract_payload[name] for name in contract_fields if name in contract_payload}
    )
    normalized_cases = []
    for raw_case in raw_summary.get("cases") or []:
        input_payload = raw_case.get("input") or {}
        provenance = {
            "input_sha256": input_payload.get("sha256"),
            "frequency_points": input_payload.get("frequency_points"),
        }
        native_metrics = _summarize_tool_cell(raw_case.get("native"), contract, **provenance)
        idem_metrics = _summarize_tool_cell(raw_case.get("idem"), contract, **provenance)
        valid = native_metrics["status"] == "PASS" and idem_metrics["status"] == "PASS"
        order_ratio = _positive_ratio(native_metrics["selected_order"], idem_metrics["selected_order"]) if valid else None
        time_ratio = _positive_ratio(native_metrics["total_search_seconds"], idem_metrics["total_search_seconds"]) if valid else None
        memory_ratio = _positive_ratio(native_metrics["peak_memory_mb"], idem_metrics["peak_memory_mb"]) if valid else None
        ratio_metrics_valid = all(value is not None for value in (order_ratio, time_ratio, memory_ratio))
        comparison_pass = bool(
            valid
            and ratio_metrics_valid
            and order_ratio <= 1.25
            and time_ratio <= 2.0
            and memory_ratio <= 1.5
        )
        comparison_status = "INVALID" if not valid or not ratio_metrics_valid else ("PASS" if comparison_pass else "FAIL")
        normalized_cases.append(
            {
                "input": input_payload,
                "native": raw_case.get("native"),
                "idem": raw_case.get("idem"),
                "native_metrics": native_metrics,
                "idem_metrics": idem_metrics,
                "comparison": {
                    "status": comparison_status,
                    "invalid_comparison": comparison_status == "INVALID",
                    "order_ratio": order_ratio,
                    "time_ratio": time_ratio,
                    "memory_ratio": memory_ratio,
                    "gates": {
                        "order_ratio_max": 1.25,
                        "time_ratio_max": 2.0,
                        "memory_ratio_max": 1.5,
                    },
                },
            }
        )
    normalized_cases.sort(
        key=lambda case: (
            int(case["input"].get("ports") or 0),
            str(case["input"].get("relative_path") or "").lower(),
        )
    )
    valid_cells = sum(case["comparison"]["status"] != "INVALID" for case in normalized_cases)
    passing_cells = sum(case["comparison"]["status"] == "PASS" for case in normalized_cases)
    return {
        "benchmark_contract_version": contract.contract_version,
        "contract": contract.to_dict(),
        "comparison_gates": {
            "order_ratio_max": 1.25,
            "time_ratio_max": 2.0,
            "memory_ratio_max": 1.5,
            "required_case_count": 6,
        },
        "case_count": len(normalized_cases),
        "valid_comparison_count": valid_cells,
        "passing_comparison_count": passing_cells,
        "overall_parity": len(normalized_cases) == 6 and passing_cells == 6,
        "cases": normalized_cases,
    }


def write_full_benchmark_csv(summary: dict[str, Any], path: Path) -> None:
    fieldnames = [
        "input_sha256",
        "native_status",
        "idem_status",
        "comparison_status",
        "input",
        "ports",
        "frequency_points",
        "native_order",
        "idem_order",
        "native_final_mean_rms",
        "idem_final_mean_rms",
        "native_final_max_sigma",
        "idem_final_max_sigma",
        "native_total_search_seconds",
        "idem_total_search_seconds",
        "native_peak_memory_mb",
        "idem_peak_memory_mb",
        "order_ratio",
        "time_ratio",
        "memory_ratio",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in summary.get("cases") or []:
            raw = case["input"]
            native = case["native_metrics"]
            idem = case["idem_metrics"]
            comparison = case["comparison"]
            writer.writerow(
                {
                    "input_sha256": raw.get("sha256"),
                    "native_status": native["status"],
                    "idem_status": idem["status"],
                    "comparison_status": comparison["status"],
                    "input": raw.get("relative_path"),
                    "ports": raw.get("ports"),
                    "frequency_points": raw.get("frequency_points"),
                    "native_order": native["selected_order"],
                    "idem_order": idem["selected_order"],
                    "native_final_mean_rms": native["final_mean_rms"],
                    "idem_final_mean_rms": idem["final_mean_rms"],
                    "native_final_max_sigma": native["final_max_sigma"],
                    "idem_final_max_sigma": idem["final_max_sigma"],
                    "native_total_search_seconds": native["total_search_seconds"],
                    "idem_total_search_seconds": idem["total_search_seconds"],
                    "native_peak_memory_mb": native["peak_memory_mb"],
                    "idem_peak_memory_mb": idem["peak_memory_mb"],
                    "order_ratio": comparison["order_ratio"],
                    "time_ratio": comparison["time_ratio"],
                    "memory_ratio": comparison["memory_ratio"],
                }
            )


def _markdown_metric(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.9g}"
    return str(value)


def render_benchmark_markdown(summary: dict[str, Any]) -> str:
    contract = summary["contract"]
    lines = [
        "<!-- GENERATED FROM summary.json; DO NOT EDIT -->",
        "# Native vs IdEM Full-Corpus S-Parameter Benchmark",
        "",
        "Canonical data: `runs-sparam/full-corpus-target-0p001/summary.json`",
        "",
        "## Contract",
        "",
        f"- Mean S-RMS target: `{contract['rms_target']}` on every original frequency and port pair.",
        f"- Passivity: enforced; authoritative check plus sampled `max_sigma <= {1.0 + contract['passivity_epsilon']}`.",
        f"- Maximum effective order: `{contract['max_order']}`; computational threads: `{contract['threads']}`.",
        "- Search: even orders from 4, then adjacent odd-order backfill after the first even pass.",
        "- Parity gates: Native/IdEM order `<= 1.25`, time `<= 2.0`, memory `<= 1.5`.",
        "",
        f"Native command: `python -m agent_spice.cli fit-sparam <INPUT> --rms-target {contract['rms_target']} --passivity enforce --max-order {contract['max_order']} --resume-target-search`",
        "",
        f"Benchmark command: `python scripts/sparam_full_corpus_benchmark.py --corpus-root user_input/spara --rms-target {contract['rms_target']} --passivity-epsilon {contract['passivity_epsilon']} --max-order {contract['max_order']} --threads {contract['threads']} --resume`",
        "",
        "IdEM enforcement/check options: `idemmp_passivity.exe -hamSolver 3 -DC 1 -nThreads <THREADS>` followed by `-onlyCheck 1`; accepted models are exported with `idemmp_export.exe -type 2` and independently audited.",
        "",
        "## Results",
        "",
        "| Input | SHA-256 | Native | IdEM | Native order | IdEM order | Native RMS | IdEM RMS | Native sigma | IdEM sigma | Native time (s) | IdEM time (s) | Native peak (MiB) | IdEM peak (MiB) | Order ratio | Time ratio | Memory ratio | Comparison |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for case in summary.get("cases") or []:
        raw = case["input"]
        native = case["native_metrics"]
        idem = case["idem_metrics"]
        comparison = case["comparison"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(raw.get("relative_path")),
                    str(raw.get("sha256")),
                    native["status"],
                    idem["status"],
                    _markdown_metric(native["selected_order"]),
                    _markdown_metric(idem["selected_order"]),
                    _markdown_metric(native["final_mean_rms"]),
                    _markdown_metric(idem["final_mean_rms"]),
                    _markdown_metric(native["final_max_sigma"]),
                    _markdown_metric(idem["final_max_sigma"]),
                    _markdown_metric(native["total_search_seconds"]),
                    _markdown_metric(idem["total_search_seconds"]),
                    _markdown_metric(native["peak_memory_mb"]),
                    _markdown_metric(idem["peak_memory_mb"]),
                    _markdown_metric(comparison["order_ratio"]),
                    _markdown_metric(comparison["time_ratio"]),
                    _markdown_metric(comparison["memory_ratio"]),
                    comparison["status"],
                ]
            )
            + " |"
        )
    overall = "PASS" if summary.get("overall_parity") else "FAIL"
    lines.extend(["", f"Overall six-case parity: **{overall}**.", ""])
    return "\n".join(lines)


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
