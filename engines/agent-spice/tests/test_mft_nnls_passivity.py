from __future__ import annotations

import numpy as np
import pytest

from agent_spice.sparam.mft_nnls.model import evaluate
from agent_spice.sparam.mft_nnls.passivity import (
    assess_s_passivity,
    assess_y_passivity,
    select_violation_extrema,
)
from agent_spice.sparam.mft_nnls.types import PoleResidueModel


def _scalar_model(*, residue: complex = 0.0j, constant: complex = 0.0j, proportional: complex = 0.0j) -> PoleResidueModel:
    return PoleResidueModel(
        poles=np.array([-1.0 + 0.0j]),
        residues=np.array([[[residue]]]),
        constant=np.array([[constant]]),
        proportional=np.array([[proportional]]),
    )


def test_s_half_size_assessment_finds_exact_scalar_crossover_band() -> None:
    model = _scalar_model(residue=2.0)

    assessment = assess_s_passivity(model, f_max=1.0)

    assert assessment.band_source == "half_size"
    assert len(assessment.bands) == 1
    assert assessment.bands[0].start_hz == pytest.approx(0.0)
    assert assessment.bands[0].end_hz == pytest.approx(np.sqrt(3.0) / (2.0 * np.pi), rel=1.0e-8)
    assert assessment.max_value > 1.0


def test_y_half_size_assessment_finds_negative_real_part_band() -> None:
    model = _scalar_model(residue=-2.0, constant=1.0)

    assessment = assess_y_passivity(model, f_max=1.0)

    assert assessment.band_source == "half_size"
    assert len(assessment.bands) == 1
    assert assessment.bands[0].start_hz == pytest.approx(0.0)
    assert assessment.bands[0].end_hz == pytest.approx(1.0 / (2.0 * np.pi), rel=1.0e-8)
    assert assessment.min_value < 0.0


def test_proportional_model_uses_bounded_sweep_fallback_and_records_source() -> None:
    model = _scalar_model(constant=0.5, proportional=1.0e-2)

    assessment = assess_s_passivity(model, f_max=100.0)

    assert assessment.band_source == "sweep"
    assert assessment.bands
    assert all(band.band_source == "sweep" for band in assessment.bands)


def test_passive_scalar_models_have_no_violation_bands() -> None:
    s_model = _scalar_model(constant=0.5)
    y_model = _scalar_model(constant=0.5)

    assert assess_s_passivity(s_model, f_max=1.0).bands == ()
    assert assess_y_passivity(y_model, f_max=1.0).bands == ()


def test_negative_y_feedthrough_is_an_asymptotic_violation() -> None:
    model = _scalar_model(constant=-0.1)

    assessment = assess_y_passivity(model, f_max=1.0)

    assert assessment.bands == (assessment.bands[0],)
    assert assessment.bands[0].start_hz == pytest.approx(0.0)
    assert assessment.bands[0].end_hz == pytest.approx(1.0)


def test_s_feedthrough_above_unity_is_an_asymptotic_violation() -> None:
    model = _scalar_model(constant=1.2)

    assessment = assess_s_passivity(model, f_max=1.0)

    assert assessment.bands == (assessment.bands[0],)
    assert assessment.bands[0].start_hz == pytest.approx(0.0)
    assert assessment.bands[0].end_hz == pytest.approx(1.0)


def test_extrema_reports_mode_vectors_and_model_value() -> None:
    model = _scalar_model(residue=2.0)
    assessment = assess_s_passivity(model, f_max=1.0)

    extrema = select_violation_extrema(model, assessment, local=True)

    assert len(extrema) == 1
    assert extrema[0].frequency_hz == pytest.approx(0.0)
    assert extrema[0].value > 1.0
    assert np.linalg.norm(extrema[0].left_vector) == pytest.approx(1.0)
    assert np.linalg.norm(extrema[0].right_vector) == pytest.approx(1.0)
    assert abs(evaluate(model, np.array([0.0j]))[0, 0, 0]) == pytest.approx(extrema[0].value)


@pytest.mark.parametrize(
    ("parameter_type", "model", "assess", "fixture_key"),
    [
        ("S", _scalar_model(residue=2.0), assess_s_passivity, "passivity_s_bands_hz"),
        ("Y", _scalar_model(residue=-2.0, constant=1.0), assess_y_passivity, "passivity_y_bands_hz"),
    ],
)
def test_sweep_band_boundaries_match_matlab_fixture(parameter_type, model, assess, fixture_key) -> None:
    with np.load("tests/fixtures/mft_nnls/ex4_s_small.npz") as fixture:
        assessment = assess(model, f_max=1.0, force_sweep=True)
        expected = fixture[fixture_key].reshape(-1, 2)

    actual = np.asarray([[band.start_hz, band.end_hz] for band in assessment.bands])
    assert assessment.parameter_type == parameter_type
    assert actual == pytest.approx(expected, rel=0.0, abs=1.0e-12)
