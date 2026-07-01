import json
from pathlib import Path

import pytest

from agent_spice.cli import main, run_hspice


def test_run_hspice_writes_cases_without_executing(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(".probe tran v(vdd)\n.tran 1p 1n\n.end\n", encoding="utf-8")

    exit_code = run_hspice(
        deck_path=deck,
        backend_name="ngspice",
        output_root=tmp_path / "runs",
        execute=False,
    )

    case_deck = tmp_path / "runs" / "legacy" / "legacy__base" / "case.cir"
    report = tmp_path / "runs" / "legacy" / "legacy__base" / "compat_report.json"
    assert exit_code == 0
    assert ".print tran v(vdd)" in case_deck.read_text(encoding="utf-8")
    assert report.exists()


def test_run_hspice_expands_alter_cases(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(
        ".param cdecap=1u\n"
        ".tran 1p 1n\n"
        ".alter high_decap\n"
        ".param cdecap=2u\n"
        ".alter low_decap\n"
        ".param cdecap=500n\n"
        ".end\n",
        encoding="utf-8",
    )

    exit_code = run_hspice(deck, backend_name="xyce", output_root=tmp_path / "runs", execute=False)

    assert exit_code == 0
    assert (tmp_path / "runs" / "legacy" / "legacy__base" / "case.cir").exists()
    assert (tmp_path / "runs" / "legacy" / "legacy__alter_001_high_decap" / "case.cir").exists()
    assert (tmp_path / "runs" / "legacy" / "legacy__alter_002_low_decap" / "case.cir").exists()


def test_run_hspice_executes_xyce_xdm_and_writes_two_stage_artifacts(tmp_path: Path, monkeypatch):
    from agent_spice.backend.base import BackendResult
    from agent_spice.backend.xyce import XyceXdmRunResult

    deck = tmp_path / "legacy.sp"
    deck.write_text(".probe tran v(vdd)\n.tran 1p 1n\n.end\n", encoding="utf-8")
    recorded: dict[str, Path] = {}

    def fake_run(self, hspice_path: Path, xyce_path: Path, cwd: Path):
        recorded["hspice_path"] = hspice_path
        recorded["xyce_path"] = xyce_path
        recorded["cwd"] = cwd
        xyce_path.write_text(".end\n", encoding="utf-8")
        (cwd / "xdm.stdout.log").write_text("xdm ok", encoding="utf-8")
        (cwd / "xdm.stderr.log").write_text("", encoding="utf-8")
        (cwd / "xyce.stdout.log").write_text("xyce ok", encoding="utf-8")
        (cwd / "xyce.stderr.log").write_text("", encoding="utf-8")
        return XyceXdmRunResult(
            xdm=BackendResult(0, "xdm ok", ""),
            xyce=BackendResult(0, "xyce ok", ""),
        )

    monkeypatch.setattr("agent_spice.backend.xyce.XyceBackend.run_hspice_via_xdm", fake_run)

    exit_code = run_hspice(deck, backend_name="xyce-xdm", output_root=tmp_path / "runs", execute=True)

    run_dir = tmp_path / "runs" / "legacy" / "legacy__base"
    assert exit_code == 0
    assert recorded["hspice_path"] == run_dir / "case.sp"
    assert recorded["xyce_path"] == run_dir / "case.cir"
    assert recorded["cwd"] == run_dir
    assert ".probe tran v(vdd)" in (run_dir / "case.sp").read_text(encoding="utf-8")
    assert (run_dir / "case.cir").read_text(encoding="utf-8") == ".end\n"
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["backend"] == "xyce-xdm"
    assert summary["ok"] is True
    assert summary["stages"]["xdm"]["returncode"] == 0
    assert summary["stages"]["xyce"]["returncode"] == 0


def test_run_hspice_report_includes_deck_and_case_metadata(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(".probe tran v(vdd)\n.tran 1p 1n\n.end\n", encoding="utf-8")

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path / "runs", execute=False)

    report = json.loads((tmp_path / "runs" / "legacy" / "legacy__base" / "compat_report.json").read_text())
    assert exit_code == 0
    assert report["deck"]["id"] == "legacy"
    assert report["deck"]["source"] == "legacy.sp"
    assert len(report["deck"]["sha256"]) == 64
    assert report["case"] == {"name": "legacy__base", "kind": "base", "alter_label": None}


def test_run_hspice_report_marks_alter_cases(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(
        ".param cdecap=1u\n"
        ".alter high_decap\n"
        ".param cdecap=2u\n"
        ".end\n",
        encoding="utf-8",
    )

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path / "runs", execute=False)

    report = json.loads(
        (tmp_path / "runs" / "legacy" / "legacy__alter_001_high_decap" / "compat_report.json").read_text()
    )
    assert exit_code == 0
    assert report["case"] == {
        "name": "legacy__alter_001_high_decap",
        "kind": "alter",
        "alter_label": "high_decap",
    }


def test_run_hspice_returns_xdm_failure_code_for_xyce_xdm(tmp_path: Path, monkeypatch):
    from agent_spice.backend.base import BackendResult
    from agent_spice.backend.xyce import XyceXdmRunResult

    deck = tmp_path / "legacy.sp"
    deck.write_text(".end\n", encoding="utf-8")

    def fake_run(self, hspice_path: Path, xyce_path: Path, cwd: Path):
        (cwd / "xdm.stdout.log").write_text("", encoding="utf-8")
        (cwd / "xdm.stderr.log").write_text("xdm failed", encoding="utf-8")
        return XyceXdmRunResult(
            xdm=BackendResult(7, "", "xdm failed"),
            xyce=None,
        )

    monkeypatch.setattr("agent_spice.backend.xyce.XyceBackend.run_hspice_via_xdm", fake_run)

    exit_code = run_hspice(deck, backend_name="xyce-xdm", output_root=tmp_path / "runs", execute=True)

    summary = json.loads(
        (tmp_path / "runs" / "legacy" / "legacy__base" / "run_summary.json").read_text(encoding="utf-8")
    )
    assert exit_code == 7
    assert summary["ok"] is False
    assert summary["returncode"] == 7
    assert summary["stages"]["xdm"]["returncode"] == 7
    assert summary["stages"]["xyce"] is None


def test_run_hspice_returns_xyce_failure_code_for_xyce_xdm(tmp_path: Path, monkeypatch):
    from agent_spice.backend.base import BackendResult
    from agent_spice.backend.xyce import XyceXdmRunResult

    deck = tmp_path / "legacy.sp"
    deck.write_text(".end\n", encoding="utf-8")

    def fake_run(self, hspice_path: Path, xyce_path: Path, cwd: Path):
        xyce_path.write_text(".end\n", encoding="utf-8")
        (cwd / "xdm.stdout.log").write_text("xdm ok", encoding="utf-8")
        (cwd / "xdm.stderr.log").write_text("", encoding="utf-8")
        (cwd / "xyce.stdout.log").write_text("", encoding="utf-8")
        (cwd / "xyce.stderr.log").write_text("xyce failed", encoding="utf-8")
        return XyceXdmRunResult(
            xdm=BackendResult(0, "xdm ok", ""),
            xyce=BackendResult(9, "", "xyce failed"),
        )

    monkeypatch.setattr("agent_spice.backend.xyce.XyceBackend.run_hspice_via_xdm", fake_run)

    exit_code = run_hspice(deck, backend_name="xyce-xdm", output_root=tmp_path / "runs", execute=True)

    summary = json.loads(
        (tmp_path / "runs" / "legacy" / "legacy__base" / "run_summary.json").read_text(encoding="utf-8")
    )
    assert exit_code == 9
    assert summary["ok"] is False
    assert summary["returncode"] == 9
    assert summary["stages"]["xdm"]["returncode"] == 0
    assert summary["stages"]["xyce"]["returncode"] == 9


def test_main_dispatches_run_hspice(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(".end\n", encoding="utf-8")

    exit_code = main(["run-hspice", str(deck), "--backend", "ngspice", "--output-root", str(tmp_path / "runs")])

    assert exit_code == 0
    assert (tmp_path / "runs" / "legacy" / "legacy__base" / "case.cir").exists()


def test_main_accepts_xyce_xdm_backend_without_execution(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(".end\n", encoding="utf-8")

    exit_code = main(["run-hspice", str(deck), "--backend", "xyce-xdm", "--output-root", str(tmp_path / "runs")])

    assert exit_code == 0
    run_dir = tmp_path / "runs" / "legacy" / "legacy__base"
    assert (run_dir / "case.sp").read_text(encoding="utf-8") == ".end\n"
    assert (run_dir / "case.cir").exists()


def test_main_rejects_missing_command():
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2
