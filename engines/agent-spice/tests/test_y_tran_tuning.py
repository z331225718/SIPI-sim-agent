from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest
import skrf as rf

from agent_spice.sparam.artifacts import write_cadence_rfm
from agent_spice.sparam.y_tran_tuning import (
    YTranTuneConfig,
    correction_pole_indices,
    parse_float_csv,
    parse_hspice_measure,
    tune_y_rfm_for_tran,
)


def _write_touchstone(path: Path) -> Path:
    network = rf.Network(
        frequency=rf.Frequency.from_f([1.0e6, 2.0e6], unit="hz"),
        s=np.zeros((2, 2, 2), dtype=complex),
        z0=50.0,
    )
    network.write_touchstone(str(path.with_suffix("")))
    return path


def _write_rfm(path: Path) -> Path:
    model = SimpleNamespace(
        nports=2,
        poles=np.array([-1.0 + 0j, -10.0 + 0j, -100.0 + 0j]),
        residues=np.full((4, 3), 1.0e-8 + 0j),
        constant_coeff=np.zeros(4, dtype=complex),
        proportional_coeff=np.zeros(4, dtype=complex),
    )
    write_cadence_rfm(model, path, 50.0)
    return path


def test_parse_float_csv_requires_sorted_positive_finite_values() -> None:
    assert parse_float_csv("1,2.5,3", label="poles") == (1.0, 2.5, 3.0)
    with pytest.raises(ValueError, match="strictly increasing"):
        parse_float_csv("2,1", label="poles")
    with pytest.raises(ValueError, match="positive finite"):
        parse_float_csv("1,0", label="poles")


def test_correction_pole_indices_requires_unique_real_poles() -> None:
    poles = np.array([-1.0 + 0j, -10.0 + 0j, -10.0 + 1j])
    np.testing.assert_array_equal(correction_pole_indices(poles, (1.0, 10.0)), [0, 1])
    with pytest.raises(ValueError, match="not uniquely present"):
        correction_pole_indices(poles, (5.0,))


def test_parse_hspice_measure_reads_engineering_suffix(tmp_path: Path) -> None:
    listing = tmp_path / "run.lis"
    listing.write_text("score= 1.25m\nscore= 42.0u\n", encoding="utf-8")
    assert parse_hspice_measure(listing, "score") == pytest.approx(42.0e-6)


def test_tune_y_rfm_for_tran_writes_frozen_best_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    touchstone = _write_touchstone(tmp_path / "raw.s2p")
    input_rfm = _write_rfm(tmp_path / "candidate.rfm")
    deck = tmp_path / "signoff.sp"
    deck.write_text("* test\n.model fit S n=2 rfmfile='candidate.rfm'\n.end\n", encoding="utf-8")

    def fake_hspice(command: list[str], *, cwd: Path, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        output_stem = cwd / command[command.index("-o") + 1]
        output_stem.with_suffix(".lis").write_text("rms= 0.5m\npeak= 0.75m\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("agent_spice.sparam.y_tran_tuning.subprocess.run", fake_hspice)
    output_rfm = tmp_path / "tuned.rfm"
    payload = tune_y_rfm_for_tran(
        YTranTuneConfig(
            touchstone=touchstone,
            input_rfm=input_rfm,
            deck=deck,
            output_rfm=output_rfm,
            rfm_token="candidate.rfm",
            rms_measure="rms",
            peak_measure="peak",
            residual_damping=(1.0, 10.0, 100.0),
            band_boundaries=(5.0,),
            max_evaluations=7,
        )
    )

    assert output_rfm.is_file()
    assert output_rfm.with_suffix(".json").is_file()
    assert payload["best"]["tran_rms"] == pytest.approx(0.5e-3)
    assert payload["best"]["tran_peak"] == pytest.approx(0.75e-3)
