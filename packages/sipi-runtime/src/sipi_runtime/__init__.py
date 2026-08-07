from .registry import EngineLockLoadError, EngineRegistry, UnknownEngineInstance, load_engine_lock
from .lifecycle import CancellationToken, InMemoryEventSink, InMemoryLifecycle, InvalidTransition, LifecycleSnapshot
from .selection import ResolvedBackend, SelectionError, SelectionTrace, resolve_selection, selection_hash
from .execution import PlannedExecution, plan_backend_executions
from .comparison import ComparisonError, ComparisonProfile, ComparisonReport, Metric, MetricMismatch, compare_results
from .resolution import ResolvedAnalysis, ResolvedInputBinding, ResolvedProject, resolve_project
from .dag import DagCycleError, DagNode, DagPlan, cache_identity, plan_dag
from .supervisor_registry import (
    CasConflict,
    DuplicateAttempt,
    DuplicateNode,
    SubmissionKeyConflict,
    SupervisorRegistry,
    SupervisorRegistryError,
    TerminalTransition,
)
from .supervisor import Supervisor, SupervisorBusy, SupervisorLock
from .supervisor_ipc import SupervisorClient, SupervisorServer, SupervisorUnavailable, ipc_address, ipc_family
from .driver import DriverError, DriverOptions, ExecutionDriver
from .report import DEFAULT_COMPARISON_PROFILES, build_run_report
from .cache import CacheMiss, CachePathEscape, CacheRecord, CacheStore
from .process_tree import ChildIdentity, ProcessTreeError, child_identity, is_process_alive, matches_identity, spawn_managed, terminate_tree

__all__ = [
    "CancellationToken",
    "CacheMiss",
    "CachePathEscape",
    "CacheRecord",
    "CacheStore",
    "ChildIdentity",
    "CasConflict",
    "ComparisonError",
    "ComparisonProfile",
    "ComparisonReport",
    "DagCycleError",
    "DagNode",
    "DagPlan",
    "DEFAULT_COMPARISON_PROFILES",
    "DriverError",
    "DriverOptions",
    "DuplicateAttempt",
    "DuplicateNode",
    "EngineLockLoadError",
    "EngineRegistry",
    "ExecutionDriver",
    "InMemoryEventSink",
    "InMemoryLifecycle",
    "InvalidTransition",
    "LifecycleSnapshot",
    "Metric",
    "MetricMismatch",
    "PlannedExecution",
    "ProcessTreeError",
    "ResolvedAnalysis",
    "ResolvedBackend",
    "ResolvedInputBinding",
    "ResolvedProject",
    "SelectionError",
    "SelectionTrace",
    "SubmissionKeyConflict",
    "Supervisor",
    "SupervisorBusy",
    "SupervisorClient",
    "SupervisorLock",
    "SupervisorRegistry",
    "SupervisorServer",
    "SupervisorRegistryError",
    "SupervisorUnavailable",
    "TerminalTransition",
    "UnknownEngineInstance",
    "compare_results",
    "build_run_report",
    "cache_identity",
    "child_identity",
    "is_process_alive",
    "load_engine_lock",
    "plan_dag",
    "plan_backend_executions",
    "ipc_address",
    "ipc_family",
    "matches_identity",
    "resolve_project",
    "resolve_selection",
    "selection_hash",
    "spawn_managed",
    "terminate_tree",
]
