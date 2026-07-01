from pathlib import Path

from agent_spice.cli import run_hspice


def test_simple_pi_fixture_converts(tmp_path: Path):
    deck = Path("tests/fixtures/hspice/simple_pi.sp")

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path, execute=False)

    case_deck = tmp_path / "simple_pi" / "simple_pi__base" / "case.cir"
    assert exit_code == 0
    assert case_deck.exists()
    assert ".print tran v(load)" in case_deck.read_text(encoding="utf-8")


def test_alter_fixture_creates_three_cases(tmp_path: Path):
    deck = Path("tests/fixtures/hspice/alter_pi.sp")

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path, execute=False)

    assert exit_code == 0
    assert (tmp_path / "alter_pi" / "alter_pi__base" / "case.cir").exists()
    assert (tmp_path / "alter_pi" / "alter_pi__alter_001_high_decap" / "case.cir").exists()
    assert (tmp_path / "alter_pi" / "alter_pi__alter_002_low_decap" / "case.cir").exists()
