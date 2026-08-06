"""Runtime-owned backend selection (M2-07 selection trace, M2-10 ownership).

The runtime is the only backend selector.  Adapters stay strict-only; this
module resolves a ``run-request`` backend selection into pinned engine
instances, records the fallback trace, enforces experimental/internal gates
and computes the canonical selection hash used by backend executions.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .registry import EngineRegistry, UnknownEngineInstance


class SelectionError(ValueError):
    """Raised when a selection cannot be resolved; carries a platform category."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message

    def as_platform_error(self) -> dict[str, Any]:
        return {"category": self.category, "message": self.message, "resource": None, "cause": None, "details": {}}


@dataclass(frozen=True)
class ResolvedBackend:
    role: str
    instance_id: str
    engine_entry: Mapping[str, Any]


@dataclass(frozen=True)
class SelectionTrace:
    mode: str
    requested: Mapping[str, Any]
    resolved: tuple[ResolvedBackend, ...]
    fallback_trace: tuple[str, ...]
    experimental: bool
    internal: bool
    selection_hash: str
    comparison_profile: str | None = None


def selection_hash(selection: Mapping[str, Any]) -> str:
    canonical = json.dumps(selection, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _check_instance(
    registry: EngineRegistry,
    instance_id: str,
    *,
    allow_internal: bool,
    mode: str,
) -> Mapping[str, Any]:
    try:
        entry = registry.lookup(instance_id)
    except UnknownEngineInstance as error:
        raise SelectionError("EngineUnavailable", f"unknown engine instance: {instance_id}") from error
    license_status = entry["license_provenance"]["distribution_status"]
    if license_status == "blocked_unknown":
        raise SelectionError("UnsupportedCapability", f"engine instance is license-blocked: {instance_id}")
    if entry.get("extensions", {}).get("sipi.internal") and not allow_internal:
        raise SelectionError("UnsupportedCapability", f"engine instance is internal-only: {instance_id}")
    return entry


def resolve_selection(
    selection: Mapping[str, Any],
    registry: EngineRegistry,
    *,
    allow_internal: bool = False,
) -> SelectionTrace:
    """Resolve one discriminated backend selection to pinned engine instances."""
    mode = selection["mode"]
    if selection.get("allow_experimental"):
        raise SelectionError("UnsupportedCapability", "experimental opt-in has no certified evidence in M2")
    if mode == "strict":
        instance = selection["instance"]
        entry = _check_instance(registry, instance, allow_internal=allow_internal, mode=mode)
        resolved = (ResolvedBackend("primary", instance, entry),)
        fallback: tuple[str, ...] = ()
        profile: str | None = None
    elif mode == "auto":
        fallback_list: list[str] = []
        resolved_list: list[ResolvedBackend] = []
        for candidate in selection["candidates"]:
            try:
                entry = _check_instance(registry, candidate, allow_internal=False, mode=mode)
            except SelectionError as error:
                if error.category in selection["fallback_on"]:
                    fallback_list.append(f"{candidate}:{error.message}")
                    continue
                raise
            resolved_list.append(ResolvedBackend("primary", candidate, entry))
            break
        if not resolved_list:
            raise SelectionError("EngineUnavailable", "no stable auto candidate is available")
        resolved = tuple(resolved_list)
        fallback = tuple(fallback_list)
        profile = None
    elif mode == "compare":
        reference = selection["reference"]
        candidate = selection["candidate"]
        if reference == candidate:
            raise SelectionError("EngineUnavailable", "compare requires distinct engine instances")
        reference_entry = _check_instance(registry, reference, allow_internal=allow_internal, mode=mode)
        candidate_entry = _check_instance(registry, candidate, allow_internal=allow_internal, mode=mode)
        resolved = (
            ResolvedBackend("reference", reference, reference_entry),
            ResolvedBackend("candidate", candidate, candidate_entry),
        )
        fallback = ()
        profile = selection["comparison_profile"]
    else:
        raise SelectionError("EngineUnavailable", f"unsupported selection mode: {mode!r}")
    return SelectionTrace(
        mode=mode,
        requested=dict(selection),
        resolved=resolved,
        fallback_trace=fallback,
        experimental=bool(selection.get("allow_experimental")),
        internal=bool(selection.get("allow_internal")),
        selection_hash=selection_hash(selection),
        comparison_profile=profile,
    )
