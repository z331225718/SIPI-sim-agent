"""Pytest configuration: opt-in external oracle lanes.

Lanes marked ``@pytest.mark.oracle("ngspice")`` run by default (gated only by
tool availability); ``"hspice"`` and ``"csharp"`` are opt-in via
``--run-oracle=<lane>`` (or ``--run-oracle=all``).
"""
from __future__ import annotations

import pytest

# Lanes that require explicit opt-in. ngspice is opt-in because the project
# uses its own agent-spice-sim engine (ngspice is a locally-downloaded OSS
# tool, not a project dependency); HSPICE is commercial; .NET is heavy.
_OPT_IN_LANES = frozenset({"hspice", "csharp", "ngspice"})


def pytest_addoption(parser):
    parser.addoption(
        "--run-oracle",
        action="append",
        default=[],
        metavar="LANE",
        help="enable an opt-in external oracle lane: ngspice | hspice | csharp | all",
    )


def pytest_collection_modifyitems(config, items):
    enabled = set(config.getoption("--run-oracle"))
    for item in items:
        mark = item.get_closest_marker("oracle")
        if mark is None:
            continue
        lane = mark.args[0]
        if lane not in _OPT_IN_LANES:
            continue
        if "all" not in enabled and lane not in enabled:
            item.add_marker(
                pytest.mark.skip(reason=f"oracle lane '{lane}' is opt-in (--run-oracle={lane})")
            )
