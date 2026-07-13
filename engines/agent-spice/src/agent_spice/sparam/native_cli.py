"""Fresh-process launcher for a reproducible Native BLAS thread budget."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from agent_spice.sparam.performance import BLAS_THREAD_ENVIRONMENT, blas_thread_environment


def _positive_threads(value: str) -> int:
    try:
        threads = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if threads < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return threads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-spice-native",
        description="Run agent-spice in a fresh process with an explicit BLAS thread budget.",
    )
    parser.add_argument(
        "--blas-threads",
        type=_positive_threads,
        default=1,
        help="OpenBLAS/MKL/OMP/NumExpr threads for the child (default: 1).",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="agent-spice command and arguments")
    args = parser.parse_args(argv)
    if not args.command:
        parser.error("provide an agent-spice command, for example: fit-sparam case.s16p")
    environment = blas_thread_environment(args.blas_threads, os.environ)
    completed = subprocess.run(
        [sys.executable, "-m", "agent_spice.cli", *args.command],
        env=environment,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
