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


def test_main_dispatches_run_hspice(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(".end\n", encoding="utf-8")

    exit_code = main(["run-hspice", str(deck), "--backend", "ngspice", "--output-root", str(tmp_path / "runs")])

    assert exit_code == 0
    assert (tmp_path / "runs" / "legacy" / "legacy__base" / "case.cir").exists()


def test_main_rejects_missing_command():
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2
