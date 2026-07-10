import numpy as np
import pytest

from agent_spice.sparam.fitting import _LightweightSNetwork
from agent_spice.sparam.native_vf import NativeVectorFitting, PoleCandidateScore


def test_native_vector_fitting_writes_s_parameter_spice_subcircuit(tmp_path):
    network = _LightweightSNetwork(
        f=np.array([1.0e6, 2.0e6]),
        s=np.zeros((2, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    vector_fit = NativeVectorFitting(network)
    vector_fit.poles = np.array([-1.0e7 + 0.0j, -2.0e7 + 3.0e7j])
    vector_fit.residues = np.array([[0.2 + 0.0j, 0.1 + 0.05j]])
    vector_fit.constant_coeff = np.array([0.01])
    vector_fit.proportional_coeff = np.array([0.0])
    output = tmp_path / "native.sp"

    vector_fit.write_spice_subcircuit_s(str(output), fitted_model_name="native_s")

    content = output.read_text(encoding="utf-8")
    assert "placeholder" not in content.lower()
    assert ".SUBCKT native_s p1" in content
    assert "V1 p1 s1 0" in content
    assert "R1 s1 0 50.0" in content
    assert "Gd1_1" in content
    assert "Gr1_1_1" in content
    assert "Cx1_a1" in content
    assert "Gr2_re_1_1" in content
    assert "Cx2_re_a1" in content
    assert ".ENDS native_s" in content


def test_native_spice_exporter_matches_skrf_element_vocabulary(tmp_path):
    network = _LightweightSNetwork(
        f=np.array([1.0e6, 2.0e6]),
        s=np.zeros((2, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    vector_fit = NativeVectorFitting(network)
    vector_fit.poles = np.array([-1.0e7 + 0.0j, -2.0e7 + 3.0e7j])
    vector_fit.residues = np.array([[0.2 + 0.0j, 0.1 + 0.05j]])
    vector_fit.constant_coeff = np.array([0.01])
    vector_fit.proportional_coeff = np.array([0.001])
    output = tmp_path / "native_with_e.sp"

    vector_fit.write_spice_subcircuit_s(str(output), fitted_model_name="native_s")

    lines = output.read_text(encoding="utf-8").splitlines()
    prefixes = {line.split()[0] for line in lines if line and not line.startswith("*") and not line.startswith(".")}
    expected = {
        "V1",
        "R1",
        "Gd1_1",
        "Fd1_1",
        "Ge1_1",
        "Gr1_1_1",
        "Gr2_re_1_1",
        "Gr2_im_1_1",
        "Cx1_a1",
        "Gx1_a1",
        "Fx1_a1",
        "Rp1_a1",
        "Cx2_re_a1",
        "Gx2_re_a1",
        "Fx2_re_a1",
        "Rp2_re_re_a1",
        "Gp2_re_im_a1",
        "Cx2_im_a1",
        "Gp2_im_re_a1",
        "Rp2_im_im_a1",
        "Le1",
        "Ge1",
        "Fe1",
    }
    assert expected <= prefixes


def test_native_residue_fit_handles_all_real_poles():
    poles = np.array([-1.0e6 + 0.0j, -2.0e6 + 0.0j])
    freqs = np.array([0.0, 1.0, 2.0, 3.0])
    responses = np.array([[1.0 + 0.0j, 0.9 + 0.1j, 0.8 + 0.2j, 0.7 + 0.3j]])

    residues, constant_coeff, proportional_coeff, *_ = NativeVectorFitting._fit_residues(
        poles,
        freqs,
        responses,
        True,
        False,
        True,
    )

    assert residues.shape == (1, 2)
    assert constant_coeff.shape == (1,)
    assert proportional_coeff.shape == (1,)


def test_native_high_frequency_complex_pair_repair_converts_largest_real_pole():
    poles = np.array([-1.0 + 0.0j, -10.0 + 0.0j, -2.0 + 3.0 * np.pi * 1j])
    repaired = NativeVectorFitting._ensure_high_frequency_complex_pairs(
        poles,
        np.array([0.0, 1.0, 2.0]),
        pair_count=2,
        damping=0.05,
        lower_fraction=0.5,
    )

    assert repaired[0] == poles[0]
    assert repaired[2] == poles[2]
    assert repaired[1].imag > 0.0
    assert repaired[1].real < 0.0


def test_high_frequency_repair_replaces_low_frequency_complex_pair():
    freqs_hz = np.array([0.0, 1.0e9, 2.0e9])
    low_pair = complex(-0.03 * 2.0 * np.pi * 5.3e4, 2.0 * np.pi * 5.3e4)
    mid_pair = complex(-0.03 * 2.0 * np.pi * 1.386e9, 2.0 * np.pi * 1.386e9)
    poles = np.array([-2.0e9 + 0.0j, low_pair, mid_pair])

    repaired = NativeVectorFitting._ensure_high_frequency_complex_pairs(
        poles,
        freqs_hz,
        pair_count=2,
        damping=0.03,
        lower_fraction=0.68,
    )

    complex_freqs = sorted(abs(pole.imag) / (2.0 * np.pi) for pole in repaired if abs(pole.imag) > 0.0)
    assert len(complex_freqs) == 2
    assert complex_freqs[0] == pytest.approx(1.386e9)
    assert complex_freqs[1] == pytest.approx(2.0e9)
    assert not any(freq < 0.68 * 2.0e9 for freq in complex_freqs)


def test_high_frequency_repair_keeps_valid_high_frequency_pairs():
    freqs_hz = np.array([0.0, 1.0e9, 2.0e9])
    mid_pair = complex(-0.03 * 2.0 * np.pi * 1.386e9, 2.0 * np.pi * 1.386e9)
    edge_pair = complex(-0.03 * 2.0 * np.pi * 2.0e9, 2.0 * np.pi * 2.0e9)
    poles = np.array([-2.0e9 + 0.0j, mid_pair, edge_pair])

    repaired = NativeVectorFitting._ensure_high_frequency_complex_pairs(
        poles,
        freqs_hz,
        pair_count=2,
        damping=0.03,
        lower_fraction=0.68,
    )

    assert np.allclose(repaired, poles)


def test_high_frequency_repair_demotes_surplus_low_frequency_complex_pair():
    freqs_hz = np.array([0.0, 1.0e9, 2.0e9])
    low_pair = complex(-0.03 * 2.0 * np.pi * 5.3e4, 2.0 * np.pi * 5.3e4)
    mid_pair = complex(-0.03 * 2.0 * np.pi * 1.386e9, 2.0 * np.pi * 1.386e9)
    edge_pair = complex(-0.03 * 2.0 * np.pi * 2.0e9, 2.0 * np.pi * 2.0e9)
    poles = np.array([-2.0e9 + 0.0j, low_pair, mid_pair, edge_pair])

    repaired = NativeVectorFitting._ensure_high_frequency_complex_pairs(
        poles,
        freqs_hz,
        pair_count=2,
        damping=0.03,
        lower_fraction=0.68,
    )

    complex_freqs = sorted(abs(pole.imag) / (2.0 * np.pi) for pole in repaired if abs(pole.imag) > 0.0)
    assert len(complex_freqs) == 2
    assert complex_freqs == pytest.approx([1.386e9, 2.0e9])
    assert repaired[1].imag == 0.0
    assert repaired[1].real < 0.0


def test_missing_high_frequency_anchors_prefers_uncovered_edge_slot():
    anchors = np.array([1.36e9, 2.0e9])
    missing = NativeVectorFitting._missing_high_frequency_anchors(
        valid_frequencies_hz=[1.386e9],
        anchors_hz=anchors,
        missing_count=1,
    )

    assert missing == pytest.approx([2.0e9])


def test_edge_residual_seed_frequency_uses_largest_high_frequency_residual():
    freqs_hz = np.array([0.0, 0.5e9, 1.4e9, 1.8e9, 2.0e9])
    raw = np.zeros((1, len(freqs_hz)), dtype=complex)
    fitted = np.zeros((1, len(freqs_hz)), dtype=complex)
    raw[0, 2] = 0.1 + 0.0j
    raw[0, 3] = 0.7 + 0.0j
    raw[0, 4] = 0.2 + 0.0j

    seed = NativeVectorFitting._edge_residual_seed_frequency(
        freqs_hz,
        raw,
        fitted,
        lower_fraction=0.68,
    )

    assert seed == pytest.approx(1.8e9)


def test_soft_anchor_high_frequency_complex_pairs_blends_into_anchor_bands():
    freqs_hz = np.linspace(0.0, 2.0e9, 11)
    poles = np.array([-2.0e9 + 0.2j * 2.0 * np.pi * 9.0e8, -4.0e9 + 0.0j])

    anchored = NativeVectorFitting._soft_anchor_high_frequency_complex_pairs(
        poles,
        freqs_hz=freqs_hz,
        anchor_bands_hz=((1.3e9, 1.45e9), (1.8e9, 2.0e9)),
        damping=0.03,
        strength=1.0,
    )

    complex_freqs = sorted(abs(pole.imag) / (2.0 * np.pi) for pole in anchored if abs(pole.imag) > 0.0)
    assert any(1.3e9 <= freq <= 1.45e9 for freq in complex_freqs)
    assert any(1.8e9 <= freq <= 2.0e9 for freq in complex_freqs)


def test_native_vector_fit_soft_anchor_uses_hz_units(monkeypatch):
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e9, 2.0e9]),
        s=np.zeros((3, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    relocated = np.array([-1.0 + 1.0j])

    def fake_relocation(*_args, **_kwargs):
        return relocated, 0.0, 1.0, 0, None, np.ones(1)

    monkeypatch.setattr(NativeVectorFitting, "_pole_relocation", staticmethod(fake_relocation))
    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = 1
    vector_fit.high_frequency_complex_pair_anchor_bands_hz = ((1.8e9, 2.0e9),)
    vector_fit.high_frequency_complex_pair_anchor_strength = 1.0

    vector_fit.vector_fit(n_poles_real=0, n_poles_cmplx=1)

    anchored_freq = abs(vector_fit.poles[0].imag) / (2.0 * np.pi)
    assert anchored_freq == pytest.approx(1.9e9)


def test_relocation_history_records_complex_pair_frequencies(monkeypatch):
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e9, 2.0e9]),
        s=np.zeros((3, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0], [50.0]], dtype=complex),
        name="one_port",
    )

    def fake_relocation(*_args, **_kwargs):
        return np.array([-1.0 + 0.0j, -2.0 + 2.0j]), 0.0, 1.0, 0, None, np.ones(1)

    monkeypatch.setattr(NativeVectorFitting, "_pole_relocation", staticmethod(fake_relocation))

    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = 1
    vector_fit.vector_fit(n_poles_real=1, n_poles_cmplx=1, init_pole_spacing="lin", fit_constant=True, fit_proportional=False)

    assert len(vector_fit.pole_relocation_history) == 1
    row = vector_fit.pole_relocation_history[0]
    assert row["iteration"] == 0
    assert row["complex_pair_frequencies_hz"] == pytest.approx([1.0e9 / np.pi])
    assert row["real_pole_count"] == 1


def test_high_frequency_relocation_weight_passes_sample_weights(monkeypatch):
    captured = {}
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e9, 2.0e9]),
        s=np.zeros((3, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0], [50.0]], dtype=complex),
        name="one_port",
    )

    def fake_relocation(*_args, **kwargs):
        captured["weights"] = kwargs["frequency_relocation_weights"]
        return np.array([-1.0 + 0.0j, -2.0 + 2.0j]), 0.0, 1.0, 0, None, np.ones(1)

    monkeypatch.setattr(NativeVectorFitting, "_pole_relocation", staticmethod(fake_relocation))

    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = 1
    vector_fit.high_frequency_relocation_weight_enabled = True
    vector_fit.high_frequency_relocation_weight_lower_fraction = 0.68
    vector_fit.high_frequency_relocation_weight_gain = 3.0
    vector_fit.vector_fit(n_poles_real=1, n_poles_cmplx=1, init_pole_spacing="lin", fit_constant=True, fit_proportional=False)

    assert captured["weights"].tolist() == [1.0, 1.0, 3.0]


def test_dynamic_edge_c_res_regularization_weights_only_out_of_band_growth():
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e9, 2.0e9]),
        s=np.zeros((3, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    vector_fit = NativeVectorFitting(network)
    vector_fit.dynamic_edge_c_res_regularization_enabled = True
    vector_fit.dynamic_edge_c_res_regularization_base_weight = 0.1
    vector_fit.dynamic_edge_c_res_regularization_start_fraction = 1.0
    vector_fit.dynamic_edge_c_res_regularization_growth_threshold = 1.2
    poles = np.array([
        -1.0 + 0.0j,
        -0.03 * 2.0 * np.pi * 2.5 + 1j * 2.0 * np.pi * 2.5,
        -0.03 * 2.0 * np.pi * 1.4 + 1j * 2.0 * np.pi * 1.4,
    ])

    weights = vector_fit._dynamic_edge_c_res_regularization_weights(
        poles,
        norm=1.0e9,
        previous_input_complex_rows=[(2.0e9, 10.0), (1.4e9, 5.0)],
    )

    assert weights[0] == 0.0
    assert weights[1] > 0.0
    assert weights[2] == 0.0


def test_resonance_seed_frequencies_selects_local_and_edge_peaks():
    freqs = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    responses = np.array([[0.1, 0.2, 2.0, 0.3, 1.5]], dtype=complex)

    seeds = NativeVectorFitting._resonance_seed_frequencies(freqs, responses, count=2)

    assert list(seeds) == [2.0, 4.0]


def test_native_vector_fit_accepts_resonance_initial_spacing():
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e9, 2.0e9, 3.0e9, 4.0e9]),
        s=np.array([[[0.1]], [[0.2]], [[2.0]], [[0.3]], [[1.5]]], dtype=complex),
        z0=np.array([[50.0]] * 5, dtype=complex),
        name="one_port",
    )
    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = 0

    vector_fit.vector_fit(n_poles_real=1, n_poles_cmplx=2, init_pole_spacing="resonance")

    complex_freqs = sorted(abs(pole.imag) / (2.0 * np.pi) for pole in vector_fit.poles if abs(pole.imag) > 0)
    assert complex_freqs == pytest.approx([2.0e9, 4.0e9])


def test_native_effective_order_limit_preserves_high_complex_and_low_real_poles():
    poles = np.array([
        -1.0 + 0.0j,
        -2.0 + 0.0j,
        -100.0 + 0.0j,
        -200.0 + 0.0j,
        -0.1 + 10.0j,
        -0.1 + 20.0j,
        -0.1 + 30.0j,
    ])

    limited = NativeVectorFitting._limit_effective_order(
        poles,
        max_order=6,
        preferred_complex_count=2,
    )

    assert NativeVectorFitting.get_model_order(limited) <= 6
    assert np.count_nonzero(np.abs(limited.imag) > 0.0) == 2
    assert -1.0 + 0.0j in limited
    assert -2.0 + 0.0j in limited
    assert -0.1 + 30.0j in limited
    assert -0.1 + 20.0j in limited


def test_post_relocation_trim_keeps_high_real_poles_and_complex_pairs():
    poles = np.array(
        [
            -1.0 + 0.0j,
            -2.0 + 0.0j,
            -10.0 + 0.0j,
            -20.0 + 0.0j,
            -100.0 + 0.0j,
            -200.0 + 0.0j,
            -1000.0 + 0.0j,
            -0.1 + 10.0j,
            -0.1 + 20.0j,
        ]
    )

    trimmed = NativeVectorFitting._trim_low_frequency_real_poles(poles, max_order=8)

    assert NativeVectorFitting.get_model_order(trimmed) == 8
    assert set(trimmed) == {
        -20.0 + 0.0j,
        -100.0 + 0.0j,
        -200.0 + 0.0j,
        -1000.0 + 0.0j,
        -0.1 + 10.0j,
        -0.1 + 20.0j,
    }


def test_post_relocation_trim_respects_requested_complex_pair_count():
    poles = np.array(
        [
            -1.0 + 0.0j,
            -10.0 + 0.0j,
            -100.0 + 0.0j,
            -1000.0 + 0.0j,
            -10000.0 + 0.0j,
            -100000.0 + 0.0j,
            -0.1 + 1.0j,
            -0.1 + 10.0j,
            -0.1 + 100.0j,
        ]
    )

    trimmed = NativeVectorFitting._trim_low_frequency_real_poles(
        poles,
        max_order=8,
        preferred_complex_count=2,
    )

    assert NativeVectorFitting.get_model_order(trimmed) == 8
    assert set(trimmed) == {
        -100.0 + 0.0j,
        -1000.0 + 0.0j,
        -10000.0 + 0.0j,
        -100000.0 + 0.0j,
        -0.1 + 10.0j,
        -0.1 + 100.0j,
    }


def test_post_relocation_trim_runs_only_after_relocation_converges(monkeypatch):
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e6, 2.0e6, 3.0e6]),
        s=np.zeros((4, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0], [50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    expanded_poles = np.array(
        [
            -1.0 + 0.0j,
            -2.0 + 0.0j,
            -10.0 + 0.0j,
            -20.0 + 0.0j,
            -100.0 + 0.0j,
            -0.1 + 1.0j,
            -0.1 + 2.0j,
        ]
    )
    relocation_input_orders = []

    def fake_relocation(poles, *_args, **_kwargs):
        relocation_input_orders.append(NativeVectorFitting.get_model_order(poles))
        return expanded_poles, 0.0, 1.0, 0, None, np.ones(1)

    monkeypatch.setattr(NativeVectorFitting, "_pole_relocation", staticmethod(fake_relocation))
    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = 2
    vector_fit.post_relocation_effective_order_max = 6

    vector_fit.vector_fit(n_poles_real=1, n_poles_cmplx=1, enforce_dc=False)

    assert relocation_input_orders[1] == NativeVectorFitting.get_model_order(expanded_poles)
    assert NativeVectorFitting.get_model_order(vector_fit.poles) == 6


def test_native_vector_fit_keeps_relocated_effective_order_by_default(monkeypatch):
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e6, 2.0e6, 3.0e6]),
        s=np.zeros((4, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0], [50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    expanded_poles = np.array([
        -1.0 + 0.0j,
        -2.0 + 0.0j,
        -3.0 + 0.0j,
        -4.0 + 0.0j,
        -0.1 + 1.0j,
        -0.1 + 2.0j,
    ])

    def fake_relocation(*_args, **_kwargs):
        return expanded_poles, 0.0, 1.0, 0, None, np.ones(1)

    monkeypatch.setattr(NativeVectorFitting, "_pole_relocation", staticmethod(fake_relocation))
    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = 1

    vector_fit.vector_fit(n_poles_real=1, n_poles_cmplx=1)

    assert NativeVectorFitting.get_model_order(vector_fit.poles) > 3


def test_native_vector_fit_can_limit_relocated_effective_order_when_opted_in(monkeypatch):
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e6, 2.0e6, 3.0e6]),
        s=np.zeros((4, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0], [50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    expanded_poles = np.array([
        -1.0 + 0.0j,
        -2.0 + 0.0j,
        -3.0 + 0.0j,
        -4.0 + 0.0j,
        -0.1 + 1.0j,
        -0.1 + 2.0j,
    ])

    def fake_relocation(*_args, **_kwargs):
        return expanded_poles, 0.0, 1.0, 0, None, np.ones(1)

    monkeypatch.setattr(NativeVectorFitting, "_pole_relocation", staticmethod(fake_relocation))
    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = 1
    vector_fit.effective_order_max = 3
    vector_fit.effective_complex_pole_count = 1

    vector_fit.vector_fit(n_poles_real=1, n_poles_cmplx=1)

    assert NativeVectorFitting.get_model_order(vector_fit.poles) <= 3


def test_native_vector_fit_rejects_worse_high_frequency_repair_candidate(monkeypatch):
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e9, 2.0e9]),
        s=np.zeros((3, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    low_pair = complex(-0.03 * 2.0 * np.pi * 5.3e4 / 1.0e9, 2.0 * np.pi * 5.3e4 / 1.0e9)
    mid_pair = complex(-0.03 * 2.0 * np.pi * 1.386, 2.0 * np.pi * 1.386)
    relocated = np.array([-2.0 + 0.0j, low_pair, mid_pair])

    def fake_relocation(*_args, **_kwargs):
        return relocated, 0.0, 1.0, 0, None, np.ones(1)

    def fake_score(poles, *_args, **_kwargs):
        has_edge_pair = any(abs(pole.imag) / (2.0 * np.pi) > 1.8 for pole in poles)
        score = 10.0 if has_edge_pair else 1.0
        return PoleCandidateScore(
            poles=np.asarray(poles),
            rms_error=score,
            max_sigma=1.0,
            passivity_excess=0.0,
            score=score,
        )

    monkeypatch.setattr(NativeVectorFitting, "_pole_relocation", staticmethod(fake_relocation))
    monkeypatch.setattr(NativeVectorFitting, "score_pole_candidate", staticmethod(fake_score))
    vector_fit = NativeVectorFitting(network)
    vector_fit.max_iterations = 1
    vector_fit.high_frequency_complex_pair_count = 2
    vector_fit.high_frequency_complex_pair_frequency_gate_enabled = True

    vector_fit.vector_fit(n_poles_real=1, n_poles_cmplx=2)

    complex_freqs = sorted(abs(pole.imag) / (2.0 * np.pi) for pole in vector_fit.poles if abs(pole.imag) > 0.0)
    assert complex_freqs[0] == pytest.approx(5.3e4)
    assert complex_freqs[1] == pytest.approx(1.386e9)
    assert vector_fit.high_frequency_repair_diagnostics[0]["accepted"] is False


def test_native_pole_candidate_score_prefers_lower_fit_error():
    freqs = np.array([0.0, 0.5, 1.0, 1.5])
    true_pole = np.array([-1.0 + 0.0j])
    s = 2j * np.pi * freqs
    responses = np.array([[0.2 + 1.0 / (s_val - true_pole[0]) for s_val in s]])

    good = NativeVectorFitting.score_pole_candidate(
        true_pole,
        freqs,
        responses,
        nports=1,
        fit_constant=True,
        fit_proportional=False,
        enforce_dc=True,
    )
    bad = NativeVectorFitting.score_pole_candidate(
        np.array([-50.0 + 0.0j]),
        freqs,
        responses,
        nports=1,
        fit_constant=True,
        fit_proportional=False,
        enforce_dc=True,
    )

    assert good.rms_error < bad.rms_error
    assert good.score < bad.score


def test_native_pole_candidate_score_penalizes_passivity_excess():
    freqs = np.array([0.0, 1.0, 2.0])
    responses = np.array([[1.2 + 0.0j, 1.2 + 0.0j, 1.2 + 0.0j]])

    score = NativeVectorFitting.score_pole_candidate(
        np.array([-1.0 + 0.0j]),
        freqs,
        responses,
        nports=1,
        fit_constant=True,
        fit_proportional=False,
        enforce_dc=True,
        passivity_weight=10.0,
    )

    assert score.max_sigma > 1.0
    assert score.passivity_excess == pytest.approx(score.max_sigma - 1.0)
    assert score.score > score.rms_error


def test_contribution_scored_selection_uses_candidate_score(monkeypatch):
    poles = np.array([-1.0, -2.0, -3.0])
    freqs = np.array([0.0, 1.0, 2.0, 3.0])
    responses = np.zeros((1, 4), dtype=complex)
    calls = []

    def fake_score(candidate_poles, *_args, **_kwargs):
        calls.append(tuple(candidate_poles))
        return PoleCandidateScore(
            poles=np.asarray(candidate_poles),
            rms_error=float(len(candidate_poles)),
            max_sigma=1.0,
            passivity_excess=0.0,
            score=0.0 if -2.0 not in candidate_poles else 10.0,
        )

    monkeypatch.setattr(NativeVectorFitting, "score_pole_candidate", staticmethod(fake_score))

    selected = NativeVectorFitting._select_poles_by_contribution_score(
        poles,
        freqs,
        responses,
        nports=1,
        max_order=2,
        fit_constant=True,
        fit_proportional=False,
        enforce_dc=True,
        passivity_weight=1.0,
    )

    assert -2.0 not in selected
    assert calls


def test_native_topology_sweep_selects_lowest_combined_score(monkeypatch):
    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e6, 2.0e6, 3.0e6]),
        s=np.zeros((4, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0], [50.0], [50.0]], dtype=complex),
        name="one_port",
    )

    def fake_vector_fit(self, *, n_poles_real=0, n_poles_cmplx=0, **_kwargs):
        self.poles = np.array([-(n_poles_real + 2 * n_poles_cmplx) + 0.0j])
        self.residues = np.array([[1.0 + 0.0j]])
        self.constant_coeff = np.array([0.0])
        self.proportional_coeff = np.array([0.0])

    def fake_score(poles, *_args, **_kwargs):
        order_marker = int(abs(float(np.real(poles[0]))))
        score = 0.1 if order_marker == 5 else 1.0
        return PoleCandidateScore(
            poles=np.asarray(poles),
            rms_error=score,
            max_sigma=1.0,
            passivity_excess=0.0,
            score=score,
        )

    monkeypatch.setattr(NativeVectorFitting, "vector_fit", fake_vector_fit)
    monkeypatch.setattr(NativeVectorFitting, "score_pole_candidate", staticmethod(fake_score))
    vector_fit = NativeVectorFitting(network)

    vector_fit.vector_fit_topology_sweep(
        candidate_configs=[
            {"n_poles_real": 1, "n_poles_cmplx": 1, "high_frequency_complex_pair_count": 1},
            {"n_poles_real": 1, "n_poles_cmplx": 2, "high_frequency_complex_pair_count": 2},
        ],
        init_pole_spacing="lin",
        parameter_type="s",
        fit_constant=True,
        fit_proportional=False,
        enforce_dc=True,
        passivity_weight=1.0,
    )

    assert vector_fit.poles.tolist() == [-(1 + 2 * 2) + 0.0j]
    assert vector_fit.topology_sweep_diagnostics[0]["selected"] is False
    assert vector_fit.topology_sweep_diagnostics[1]["selected"] is True
