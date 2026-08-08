"""Small, deterministic primitives for Native performance measurement."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import time
from typing import Iterator


BLAS_THREAD_ENVIRONMENT = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def blas_thread_environment(threads: int, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a child-process environment with an explicit BLAS thread budget."""
    if not isinstance(threads, int) or isinstance(threads, bool) or threads < 1:
        raise ValueError("threads must be a positive integer")
    environment = dict(base or {})
    for name in BLAS_THREAD_ENVIRONMENT:
        environment[name] = str(threads)
    return environment


@dataclass
class PhaseProfile:
    name: str
    wall_seconds: float = 0.0
    cpu_seconds: float | None = None

    @property
    def cpu_utilization_percent(self) -> float | None:
        if self.cpu_seconds is None or self.wall_seconds <= 0.0:
            return None
        return 100.0 * self.cpu_seconds / self.wall_seconds


@contextmanager
def phase_profile(name: str, cpu_seconds: Callable[[], float] | None = None) -> Iterator[PhaseProfile]:
    """Measure one phase without coupling production fitting to psutil."""
    profile = PhaseProfile(name=name)
    started_wall = time.perf_counter()
    started_cpu = None if cpu_seconds is None else cpu_seconds()
    try:
        yield profile
    finally:
        profile.wall_seconds = time.perf_counter() - started_wall
        if started_cpu is not None and cpu_seconds is not None:
            profile.cpu_seconds = max(0.0, cpu_seconds() - started_cpu)
