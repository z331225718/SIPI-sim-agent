from pathlib import Path

import pytest
import yaml

from agent_spice.cli import run_hspice


CORPUS_ROOT = Path("tests/fixtures/hspice/corpus")


def corpus_cases() -> list[Path]:
    return sorted(path for path in CORPUS_ROOT.iterdir() if (path / "case.yaml").exists())


@pytest.mark.parametrize("case_dir", corpus_cases(), ids=lambda path: path.name)
def test_hspice_corpus_matches_golden_reports_and_decks(case_dir: Path, tmp_path: Path):
    meta = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))
    deck = case_dir / meta["top"]
    backend = "ngspice"

    exit_code = run_hspice(deck, backend_name=backend, output_root=tmp_path / "runs", execute=False)

    assert exit_code == 0
    for case_name in meta["expected_cases"]:
        generated_dir = tmp_path / "runs" / meta["id"] / case_name
        golden_dir = case_dir / "golden" / backend / case_name
        assert (generated_dir / "compat_report.json").read_text(encoding="utf-8") == (
            golden_dir / "compat_report.json"
        ).read_text(encoding="utf-8")
        golden_deck = golden_dir / "case.cir"
        if golden_deck.exists():
            assert (generated_dir / "case.cir").read_text(encoding="utf-8") == golden_deck.read_text(
                encoding="utf-8"
            )
