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
    assert (case_deck.parent / "case.source.sp").read_text(encoding="utf-8") == ".probe tran v(vdd)\n.tran 1p 1n\n.end\n"


def test_run_hspice_native_preserves_hspice_syntax_without_conversion(
    tmp_path: Path,
) -> None:
    deps = tmp_path / "models"
    deps.mkdir()
    (deps / "pdn.inc").write_text("Rload out 0 1k\n", encoding="utf-8")
    deck = tmp_path / "native.sp"
    source = (
        "native HSPICE deck\n"
        ".inc 'models/pdn.inc'\n"
        "V1 out 0 1\n"
        ".option post=2 nomod\n"
        ".probe tran v(out)\n"
        ".tran 1p 10p\n"
        ".end\n"
    )
    deck.write_text(source, encoding="utf-8")

    exit_code = run_hspice(
        deck,
        backend_name="native",
        output_root=tmp_path / "runs",
        execute=False,
    )

    run_dir = tmp_path / "runs" / "native" / "native__base"
    report = json.loads((run_dir / "compat_report.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert (run_dir / "case.cir").read_text(encoding="utf-8") == source
    assert (run_dir / "models" / "pdn.inc").read_text(encoding="utf-8") == "Rload out 0 1k\n"
    assert report["summary"] == {
        "status": "compatible",
        "rewrites": 0,
        "drops": 0,
        "unsupported": 0,
    }


def test_run_hspice_stages_relative_include_for_generated_case(tmp_path: Path):
    deps = tmp_path / "deps"
    deps.mkdir()
    (deps / "model.inc").write_text("C1 load 0 1u\n", encoding="utf-8")
    deck = tmp_path / "legacy.sp"
    deck.write_text(".include 'deps/model.inc'\nV1 load 0 1\n.tran 1p 1n\n.end\n", encoding="utf-8")

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path / "runs", execute=False)

    run_dir = tmp_path / "runs" / "legacy" / "legacy__base"
    assert exit_code == 0
    assert (run_dir / "deps" / "model.inc").read_text(encoding="utf-8") == "C1 load 0 1u\n"


def test_run_hspice_converts_current_pwl_repeat_in_included_netlist(tmp_path: Path):
    deps = tmp_path / "deps"
    deps.mkdir()
    (deps / "current.inc").write_text(
        "Icursig vdd 0 pwl(\n+ 0ps 1 3500ps 2 6000ps 3\n+ R=3500ps )\n",
        encoding="utf-8",
    )
    deck = tmp_path / "legacy.sp"
    deck.write_text(".include 'deps/current.inc'\nR1 vdd 0 1\n.tran 1p 8n\n.end\n", encoding="utf-8")

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path / "runs", execute=False)

    staged = tmp_path / "runs" / "legacy" / "legacy__base" / "deps" / "current.inc"
    assert exit_code == 0
    assert "Bcursig vdd 0 I = pwl(" in staged.read_text(encoding="utf-8")
    assert "R=3500ps" not in staged.read_text(encoding="utf-8")


def test_run_hspice_writes_ngspice_summary_on_backend_failure(tmp_path: Path, monkeypatch):
    from agent_spice.backend.base import BackendResult

    deck = tmp_path / "legacy.sp"
    deck.write_text(".end\n", encoding="utf-8")
    monkeypatch.setattr("agent_spice.cli._run_backend", lambda *args: BackendResult(2, "", "parse failed"))

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path / "runs", execute=True)

    summary = json.loads((tmp_path / "runs" / "legacy" / "legacy__base" / "run_summary.json").read_text())
    assert exit_code == 2
    assert summary["ok"] is False
    assert summary["error"] == "parse failed"
    assert summary["waveform"] == {"path": "waveform.csv", "format": "csv", "exists": False, "rows": 0}


def test_run_hspice_executes_project_owned_native_backend(tmp_path: Path, monkeypatch):
    from agent_spice.backend.base import BackendResult

    deck = tmp_path / "linear.sp"
    deck.write_text(
        "linear native run\nV1 in 0 1\nR1 in out 1k\nR2 out 0 1k\n.op\n.print op v(out)\n.end\n",
        encoding="utf-8",
    )
    engine = tmp_path / "agent-spice-sim.exe"
    engine.write_bytes(b"placeholder")

    def fake_run(self, deck_path: Path, cwd: Path):
        assert self.engine_path == engine.resolve()
        assert deck_path == cwd / "case.cir"
        self.output_json_path.write_text(
            '{"points": [], "measurements": [{"analysis": "op", "name": "vout", "value": 0.5}]}\n',
            encoding="utf-8",
        )
        self.waveform_csv_path.write_text("analysis,x\nop,0\n", encoding="utf-8")
        return BackendResult(0, '{"ok":true,"waveformRows":1}\n', "")

    monkeypatch.setattr("agent_spice.backend.native.NativeEngineBackend.run", fake_run)
    exit_code = run_hspice(
        deck,
        backend_name="native",
        output_root=tmp_path / "runs",
        execute=True,
        native_engine=engine,
    )

    run_dir = tmp_path / "runs" / "linear" / "linear__base"
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert summary["backend"] == "native"
    assert summary["waveform"]["rows"] == 1
    assert summary["native_result"] == {"path": "native_result.json", "exists": True}
    assert summary["measurements"] == [
        {"analysis": "op", "name": "vout", "value": 0.5}
    ]


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


def test_main_defaults_run_hspice_to_native_without_execution(tmp_path: Path):
    deck = tmp_path / "linear.sp"
    deck.write_text("linear\nV1 out 0 1\n.op\n.end\n", encoding="utf-8")

    exit_code = main(
        ["run-hspice", str(deck), "--output-root", str(tmp_path / "runs")]
    )

    report = json.loads(
        (
            tmp_path
            / "runs"
            / "linear"
            / "linear__base"
            / "compat_report.json"
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert report["backend"] == "native"


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
