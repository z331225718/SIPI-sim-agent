"""Profile-driven comparison of two backend results (M2-05 shell).

The platform does not rewrite engine goldens: it compares two backend domain
results using a profile of metric paths with absolute/relative tolerances.
Real engine-specific comparators can be exposed as profile-backed checks.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sipi_contracts import BackendExecutionResultV1


class ComparisonError(ValueError):
    """Raised when a comparison cannot be evaluated."""


@dataclass(frozen=True)
class Metric:
    path: str
    atol: float = 0.0
    rtol: float = 0.0


@dataclass(frozen=True)
class ComparisonProfile:
    name: str
    metrics: tuple[Metric, ...]


@dataclass(frozen=True)
class MetricMismatch:
    path: str
    reference: Any
    candidate: Any
    atol: float
    rtol: float


@dataclass(frozen=True)
class ComparisonReport:
    profile: str
    matched: bool
    checked_count: int
    mismatches: tuple[MetricMismatch, ...]
    errors: tuple[str, ...]


def _resolve_path(document: Any, path: str) -> Any:
    """Resolve ``cases[0].metrics.com`` style paths; ``[0]`` may lead."""
    current = document
    for segment in path.split("."):
        if segment.endswith("]") and "[" in segment:
            name, _, index_text = segment.partition("[")
            try:
                index = int(index_text[:-1])
            except ValueError as error:
                raise ComparisonError(f"invalid path index: {path}") from error
            if name:
                if not isinstance(current, Mapping) or name not in current:
                    raise ComparisonError(f"path not found: {path}")
                current = current[name]
            if not isinstance(current, (list, tuple)) or not 0 <= index < len(current):
                raise ComparisonError(f"path not found: {path}")
            current = current[index]
        else:
            if not isinstance(current, Mapping) or segment not in current:
                raise ComparisonError(f"path not found: {path}")
            current = current[segment]
    return current


def _close(reference: Any, candidate: Any, atol: float, rtol: float) -> bool:
    return abs(reference - candidate) <= atol + rtol * abs(reference)


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def compare_results(
    reference: BackendExecutionResultV1,
    candidate: BackendExecutionResultV1,
    profile: ComparisonProfile,
) -> ComparisonReport:
    errors: list[str] = []
    if reference["status"] != "succeeded" or candidate["status"] != "succeeded":
        return ComparisonReport(profile.name, matched=False, checked_count=0, mismatches=(), errors=("both results must be succeeded for comparison",))
    if reference["operation"] != candidate["operation"] or reference["payload_schema"] != candidate["payload_schema"]:
        return ComparisonReport(profile.name, matched=False, checked_count=0, mismatches=(), errors=("reference and candidate operations/payloads differ",))
    if reference["role"] == candidate["role"]:
        return ComparisonReport(profile.name, matched=False, checked_count=0, mismatches=(), errors=("reference and candidate roles must differ",))
    mismatches: list[MetricMismatch] = []
    for metric in profile.metrics:
        try:
            reference_value = _resolve_path(reference["domain_result"], metric.path)
            candidate_value = _resolve_path(candidate["domain_result"], metric.path)
        except ComparisonError as error:
            errors.append(str(error))
            continue
        if not (_is_finite_number(reference_value) and _is_finite_number(candidate_value)):
            errors.append(f"non-numeric value at {metric.path}")
            continue
        if not _close(reference_value, candidate_value, metric.atol, metric.rtol):
            mismatches.append(
                MetricMismatch(
                    path=metric.path,
                    reference=reference_value,
                    candidate=candidate_value,
                    atol=metric.atol,
                    rtol=metric.rtol,
                )
            )
    checked = len(profile.metrics) - len(errors)
    return ComparisonReport(
        profile=profile.name,
        matched=not mismatches and not errors,
        checked_count=checked,
        mismatches=tuple(mismatches),
        errors=tuple(errors),
    )
