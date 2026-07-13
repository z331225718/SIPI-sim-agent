from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_spice.hspice.manifest import CompatReport


@dataclass(frozen=True)
class CaseArtifacts:
    deck_path: Path
    compat_report_path: Path


def write_case_artifacts(
    run_dir: Path,
    deck_text: str,
    compat_report: CompatReport,
    source_text: str | None = None,
) -> CaseArtifacts:
    run_dir.mkdir(parents=True, exist_ok=True)
    deck_path = run_dir / "case.cir"
    report_path = run_dir / "compat_report.json"
    if source_text is not None:
        (run_dir / "case.source.sp").write_text(source_text, encoding="utf-8")
    deck_path.write_text(deck_text, encoding="utf-8")
    report_path.write_text(compat_report.to_json() + "\n", encoding="utf-8")
    return CaseArtifacts(deck_path=deck_path, compat_report_path=report_path)
