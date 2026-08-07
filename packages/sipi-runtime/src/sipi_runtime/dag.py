"""Local analysis DAG planning (M3-03).

``plan_dag`` turns a resolved project into a deterministic execution plan:
topological order with long-chain cycle detection, ``effective_required``
closure over required nodes, and a content-addressed cache identity per node.
Execution-layer IDs (run/analysis/attempt/backend) and lineage are never part
of a cache key; only canonical payload, input/upstream artifact hashes, the
complete resolved selection, actual instance bundle hashes, schema/profile,
resources and randomness participate.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .registry import EngineRegistry
from .resolution import ResolvedAnalysis, ResolvedProject
from .selection import resolve_selection


class DagCycleError(ValueError):
    """Raised when the analysis graph contains a dependency cycle."""


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class DagNode:
    analysis_id: str
    operation: str
    payload_schema: str
    payload_sha256: str
    depends_on: tuple[str, ...]
    required: bool
    effective_required: bool
    selection: Mapping[str, Any]
    selection_hash: str
    execution_modes: tuple[str, ...]
    cache_key: str


@dataclass(frozen=True)
class DagPlan:
    project_hash: str
    order: tuple[str, ...]
    nodes: tuple[DagNode, ...]

    @property
    def by_id(self) -> Mapping[str, DagNode]:
        return MappingProxyType({node.analysis_id: node for node in self.nodes})


def cache_identity(
    analysis: ResolvedAnalysis,
    *,
    selection_hash: str,
    bundle_hashes: tuple[str, ...],
    bound_input_hashes: Mapping[str, str] | None = None,
    resource_policy: Mapping[str, Any] | None = None,
    randomness: Mapping[str, Any] | None = None,
) -> str:
    """Content-addressed cache identity excluding all execution IDs/lineage."""
    inputs: dict[str, Any] = {}
    for binding in analysis.inputs:
        upstream_hash = bound_input_hashes.get(binding.name) if bound_input_hashes is not None else None
        inputs[binding.name] = {
            "from_analysis": binding.from_analysis,
            "artifact_role": binding.artifact_role,
            "expected_schema": binding.expected_schema,
            "content_sha256": upstream_hash,
        }
    content = {
        "operation": analysis.operation,
        "payload_schema": analysis.payload_schema,
        "payload_sha256": analysis.payload_sha256,
        "backend_selection": dict(analysis.backend_selection),
        "selection_hash": selection_hash,
        "bundle_hashes": tuple(sorted(bundle_hashes)),
        "inputs": inputs,
        "resource_policy": dict(resource_policy or {}),
        "randomness": dict(randomness or {}),
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return _sha256(canonical)


def _topological_order(analyses: Mapping[str, ResolvedAnalysis]) -> tuple[str, ...]:
    indegree = {analysis_id: len(analysis.depends_on) for analysis_id, analysis in analyses.items()}
    dependents: dict[str, list[str]] = {analysis_id: [] for analysis_id in analyses}
    for analysis_id, analysis in analyses.items():
        for dependency in analysis.depends_on:
            dependents[dependency].append(analysis_id)
    queue = deque(analysis_id for analysis_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while queue:
        analysis_id = queue.popleft()
        order.append(analysis_id)
        for dependent in dependents[analysis_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(order) != len(analyses):
        remaining = sorted(analysis_id for analysis_id, degree in indegree.items() if degree > 0)
        raise DagCycleError(f"analysis DAG contains a cycle involving: {remaining}")
    return tuple(order)


def _effective_required_closure(analyses: Mapping[str, ResolvedAnalysis]) -> set[str]:
    effective: set[str] = set()

    def mark(analysis_id: str) -> None:
        if analysis_id in effective:
            return
        effective.add(analysis_id)
        for dependency in analyses[analysis_id].depends_on:
            mark(dependency)

    for analysis_id, analysis in analyses.items():
        if analysis.required:
            mark(analysis_id)
    return effective


def plan_dag(resolved: ResolvedProject, registry: EngineRegistry) -> DagPlan:
    """Build a deterministic DAG plan with pinned selections and cache keys."""
    analyses = {analysis.analysis_id: analysis for analysis in resolved.analyses}
    order = _topological_order(analyses)
    effective_required = _effective_required_closure(analyses)
    nodes: list[DagNode] = []
    for analysis_id in order:
        analysis = analyses[analysis_id]
        trace = resolve_selection(analysis.backend_selection, registry)
        bundle_hashes = tuple(backend.engine_entry["bundle"]["sha256"] for backend in trace.resolved)
        execution_modes = tuple(
            f"{backend.role}:{backend.instance_id}:sha256:{backend.engine_entry['bundle']['sha256']}"
            for backend in trace.resolved
        )
        cache_key = cache_identity(
            analysis,
            selection_hash=trace.selection_hash,
            bundle_hashes=bundle_hashes,
        )
        nodes.append(
            DagNode(
                analysis_id=analysis.analysis_id,
                operation=analysis.operation,
                payload_schema=analysis.payload_schema,
                payload_sha256=analysis.payload_sha256,
                depends_on=analysis.depends_on,
                required=analysis.required,
                effective_required=analysis_id in effective_required,
                selection=analysis.backend_selection,
                selection_hash=trace.selection_hash,
                execution_modes=execution_modes,
                cache_key=cache_key,
            )
        )
    return DagPlan(project_hash=resolved.project_hash, order=order, nodes=tuple(nodes))
