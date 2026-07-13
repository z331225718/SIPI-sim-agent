from __future__ import annotations

import sys

import pytest

from agent_spice.sparam import native_cli


def test_native_cli_starts_fit_in_fresh_process_with_explicit_blas_budget(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(command, *, env, check):
        captured["command"] = command
        captured["environment"] = env
        captured["check"] = check
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(native_cli.subprocess, "run", fake_run)

    assert native_cli.main(["--blas-threads", "1", "fit-sparam", "case.s16p", "--passivity", "enforce"]) == 0
    assert captured["command"] == [sys.executable, "-m", "agent_spice.cli", "fit-sparam", "case.s16p", "--passivity", "enforce"]
    assert {captured["environment"][name] for name in native_cli.BLAS_THREAD_ENVIRONMENT} == {"1"}
    assert captured["check"] is False


def test_native_cli_rejects_non_positive_blas_thread_budget():
    with pytest.raises(SystemExit, match="2"):
        native_cli.main(["--blas-threads", "0", "fit-sparam", "case.s2p"])
