from __future__ import annotations

import json
from pathlib import Path

from scripts import sparam_mft_pole_trajectory
from scripts.sparam_mft_pole_trajectory import classify_collapse


def test_collapse_classifier_distinguishes_avoided_reproduced_and_mitigated() -> None:
    avoided = classify_collapse([[1.5e9], [1.8e9], [1.9e9]], f_max_hz=2.0e9)
    reproduced = classify_collapse([[1.5e9], [2.2e9], [1.4e9]], f_max_hz=2.0e9)
    mitigated = classify_collapse([[1.5e9], [2.2e9], [2.1e9]], f_max_hz=2.0e9)

    assert avoided["classification"] == "avoided"
    assert reproduced["classification"] == "reproduced"
    assert reproduced["collapse_iteration"] == 2
    assert mitigated["classification"] == "mitigated"


def test_probe_command_writes_json_artifact(monkeypatch, tmp_path: Path) -> None:
    report = {"classification": {"classification": "avoided"}, "trajectory": []}
    monkeypatch.setattr(sparam_mft_pole_trajectory, "probe_mft_pole_trajectory", lambda *args, **kwargs: report)
    output = tmp_path / "trajectory.json"

    assert sparam_mft_pole_trajectory.main(["--touchstone", "Test16.s91p", "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == report
