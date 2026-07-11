from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from agent_spice.cli import main
from agent_spice.sparam.corpus_preflight import preflight_promotion_corpus


def _write_touchstone(
    path: Path,
    ports: int,
    *,
    frequencies: tuple[float, ...] = (1.0e6, 2.0e6),
    value: str = "0",
) -> None:
    rows = ["# Hz S RI R 50"]
    for frequency in frequencies:
        rows.append(f"{frequency} " + f"{value} 0 " * (ports * ports))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_manifest(path: Path, cases: list[dict[str, object]]) -> None:
    path.write_text(yaml.safe_dump({"base_dir": ".", "cases": cases}, sort_keys=False), encoding="utf-8")


def _case(case_id: str, touchstone: str) -> dict[str, object]:
    return {
        "id": case_id,
        "touchstone": touchstone,
        "fit": {"mode": "auto", "target_error": 0.001, "enforce_passivity": True},
    }


def test_preflight_writes_atomic_report_for_valid_unique_cases(tmp_path: Path) -> None:
    inputs = []
    for ports in (19, 30, 60, 91, 163, 166):
        path = tmp_path / f"case.s{ports}p"
        _write_touchstone(path, ports)
        inputs.append(_case(f"case_{ports}", path.name))
    manifest = tmp_path / "promotion.yaml"
    report = tmp_path / "report" / "preflight.json"
    _write_manifest(manifest, inputs)

    result = preflight_promotion_corpus(manifest, report)

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert result.case_count == 6
    assert payload["status"] == "PASS"
    assert [case["ports"] for case in payload["cases"]] == [19, 30, 60, 91, 163, 166]
    assert all(len(case["sha256"]) == 64 for case in payload["cases"])
    assert not list(report.parent.glob("*.tmp"))


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda cases, root: cases.__setitem__(1, _case("case_30", "case.s19p")), "duplicate input SHA-256"),
        (lambda cases, root: cases.__setitem__(0, _case("case_19", "missing.s19p")), "Touchstone file not found"),
        (lambda cases, root: cases.__setitem__(0, _case("case_19", "case.s2p")), "Touchstone data rows are incomplete"),
    ],
)
def test_preflight_rejects_invalid_input_identity(tmp_path: Path, mutator, message: str) -> None:
    _write_touchstone(tmp_path / "case.s19p", 19)
    _write_touchstone(tmp_path / "case.s30p", 30)
    _write_touchstone(tmp_path / "case.s2p", 19)
    cases = [_case("case_19", "case.s19p"), _case("case_30", "case.s30p")]
    mutator(cases, tmp_path)
    manifest = tmp_path / "promotion.yaml"
    _write_manifest(manifest, cases)

    with pytest.raises(ValueError, match=message):
        preflight_promotion_corpus(manifest, tmp_path / "preflight.json")


@pytest.mark.parametrize(
    ("frequencies", "value", "message"),
    [
        ((1.0e6, 1.0e6), "0", "strictly increasing"),
        ((2.0e6, 1.0e6), "0", "strictly increasing"),
        ((1.0e6, 2.0e6), "nan", "non-finite S-parameter"),
    ],
)
def test_preflight_rejects_invalid_touchstone_samples(tmp_path: Path, frequencies, value: str, message: str) -> None:
    _write_touchstone(tmp_path / "case.s2p", 2, frequencies=frequencies, value=value)
    manifest = tmp_path / "promotion.yaml"
    _write_manifest(manifest, [_case("case", "case.s2p")])

    with pytest.raises(ValueError, match=message):
        preflight_promotion_corpus(manifest, tmp_path / "preflight.json")


def test_cli_preflight_writes_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_touchstone(tmp_path / "case.s2p", 2)
    manifest = tmp_path / "promotion.yaml"
    report = tmp_path / "preflight.json"
    _write_manifest(manifest, [_case("case", "case.s2p")])

    assert main(["preflight-sparam-corpus", "--manifest", str(manifest), "--report", str(report)]) == 0
    assert "PASS" in capsys.readouterr().out
    assert report.is_file()
