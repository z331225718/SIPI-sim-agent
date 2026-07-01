from pathlib import Path
import json

from agent_spice.deck.builder import write_case_artifacts
from agent_spice.hspice.manifest import CompatReport


def test_write_case_artifacts_creates_deck_and_report(tmp_path: Path):
    report = CompatReport(backend="ngspice")

    paths = write_case_artifacts(
        run_dir=tmp_path,
        deck_text=".tran 1p 1n\n.end\n",
        compat_report=report,
    )

    assert paths.deck_path.read_text(encoding="utf-8") == ".tran 1p 1n\n.end\n"
    assert paths.compat_report_path.exists()
    assert json.loads(paths.compat_report_path.read_text(encoding="utf-8"))["backend"] == "ngspice"
