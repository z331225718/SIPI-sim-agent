from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from agent_spice.sparam import idem
from agent_spice.sparam.idem import (
    evaluate_local_idem_like_model,
    evaluate_local_idem_like_state_space,
    export_local_idem_like_touchstone,
    export_local_idem_like_state_space,
    IdemCommandResult,
    IdemFittingOptions,
    fit_matrix_with_idem_real_basis,
    fit_s_with_fixed_poles,
    initial_common_poles,
    relocate_common_poles,
    render_fitting_options_xml,
    run_local_idem_like_fit,
)


def _write_s2p(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# GHz S RI R 50",
                "0.001 0 0 1 0 1 0 0 0",
                "5.0 0 0 1 0 1 0 0 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_render_fitting_options_xml_sets_initial_iteration_knob():
    xml_text = render_fitting_options_xml(
        IdemFittingOptions(order=32, initial_iterations=1, threads=2, target=1e-4, bandwidth=2.0e9)
    )
    root = ET.fromstring(xml_text)
    namespace = {"f": "OptionsFittingSchema.xsd"}

    assert root.findtext(".//f:order/f:value", namespaces=namespace) == "32"
    assert root.findtext(".//f:iterations/f:initial", namespaces=namespace) == "1"
    assert root.findtext(".//f:threads", namespaces=namespace) == "2"
    assert root.findtext(".//f:accuracy/f:target", namespaces=namespace) == "0.0001"
    assert root.findtext(".//f:bandwidth", namespaces=namespace) == "2000000000"


def test_run_idem_initial_iteration_probe_writes_xml_per_trial(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    _write_s2p(touchstone)
    commands = []

    def fake_run(touchstone_path, model_path, *, options_xml_path=None, idem_bin_dir=None, timeout_seconds=None):
        commands.append((touchstone_path, model_path, options_xml_path))
        model_path.write_text("fake model", encoding="utf-8")
        return IdemCommandResult(
            command=["idemmp_fitting.exe"],
            returncode=1,
            stdout="End of model build\n",
            stderr="",
            elapsed_seconds=0.1,
            peak_memory_mb=12.5,
        )

    monkeypatch.setattr(idem, "run_idem_fitting", fake_run)
    monkeypatch.setattr(
        idem,
        "inspect_idem_model",
        lambda path: {"order": 32, "total_pole_count": 32, "error_history": [0.2], "orders_history": [32]},
    )

    results = idem.run_idem_initial_iteration_probe(touchstone, tmp_path / "runs", order=32, initial_iterations=[0, 3])

    assert [result["initial_iterations"] for result in results] == [0, 3]
    assert [result["status"] for result in results] == ["completed", "completed"]
    assert len(commands) == 2
    xml_text = commands[1][2].read_text(encoding="utf-8")
    assert "<initial>3</initial>" in xml_text
    assert "<bandwidth mode=\"absolute\">5000000000</bandwidth>" in xml_text


def test_decode_idem_split_poles_expands_real_state_space_pairs():
    dtype = [("nr", "<i4"), ("nc", "<i4"), ("p", "O")]
    row = np.array([(1, 2, np.array([-1.0, -2.0, 3.0, -4.0, 5.0]))], dtype=dtype)[0]

    poles = idem._decode_idem_split_poles(row)

    assert poles.tolist() == [
        complex(-1.0, 0.0),
        complex(-2.0, 3.0),
        complex(-2.0, -3.0),
        complex(-4.0, 5.0),
        complex(-4.0, -5.0),
    ]


def test_s_mean_rms_error_matches_idem_port_pair_mean_definition():
    original = np.zeros((2, 3, 3), dtype=complex)
    fitted = np.ones((2, 3, 3), dtype=complex)

    assert np.isclose(idem._s_rms_error(original, fitted), 3.0)
    assert np.isclose(idem._s_mean_rms_error(original, fitted), 1.0)


def test_fit_s_with_fixed_poles_recovers_known_response():
    freqs = np.array([1e6, 2e6, 5e6, 10e6, 20e6], dtype=float)
    poles = np.array([-1e8, -2e8], dtype=complex)
    s = 2j * np.pi * freqs
    values = 0.2 + 3e7 / (s - poles[0]) - 2e7j / (s - poles[1])
    samples = values.reshape(len(freqs), 1, 1)

    result = fit_s_with_fixed_poles(freqs, samples, poles)

    assert result["rank"] == 3
    assert result["condition_number"] > 0.0
    assert np.max(np.abs(result["fitted_s"] - samples)) < 1e-12


def test_fit_matrix_with_idem_real_basis_recovers_conjugate_pair_response():
    freqs = np.array([1e6, 2e6, 5e6, 10e6, 20e6], dtype=float)
    pole_block = {
        "poles_rad_per_s": [-1e8, -2e8, 3e8],
        "real_pole_count": 1,
        "complex_pair_count": 1,
    }
    s = 2j * np.pi * freqs
    pole = -2e8 + 3e8j
    conjugate = -2e8 - 3e8j
    values = 0.2 + 3e7 / (s + 1e8)
    values += 2e7 * (1 / (s - pole) + 1 / (s - conjugate))
    values += -1e7 * 1j * (1 / (s - pole) - 1 / (s - conjugate))
    samples = values.reshape(len(freqs), 1, 1)

    result = fit_matrix_with_idem_real_basis(freqs, samples, pole_block)

    assert result["rank"] == 4
    assert result["condition_number"] > 0.0
    assert np.max(np.abs(result["fitted_values"] - samples)) < 1e-12


def test_pole_block_from_complex_poles_encodes_conjugate_pairs():
    poles = np.array([-1e8 + 0j, -2e8 + 3e8j, -2e8 - 3e8j])

    block = idem._pole_block_from_complex_poles(poles)

    assert block["real_pole_count"] == 1
    assert block["complex_pair_count"] == 1
    assert block["poles_rad_per_s"] == [-1e8, -2e8, 3e8]
    assert block["decoded_poles_rad_per_s"] == [[-1e8, 0.0], [-2e8, 3e8], [-2e8, -3e8]]


def test_pole_block_from_complex_poles_pairs_nearby_opposite_imaginary_poles():
    poles = np.array([-2.0e8 + 3.0e8j, -2.2e8 - 3.1e8j, -5.0e8 + 8.0e8j, -5.1e8 - 8.2e8j])

    block = idem._pole_block_from_complex_poles(poles)

    assert block["real_pole_count"] == 0
    assert block["complex_pair_count"] == 2
    assert len(block["poles_rad_per_s"]) == 4


def test_initial_common_poles_uses_stable_conjugate_pairs():
    poles = initial_common_poles([0.0, 1e6, 10e6], order=4, damping=0.05, spacing="log")

    assert len(poles) == 4
    assert np.all(poles.real < 0.0)
    assert any(pole.imag > 0.0 for pole in poles)
    assert any(pole.imag < 0.0 for pole in poles)


def test_initial_common_poles_can_skip_near_dc_frequency():
    poles = initial_common_poles([0.1, 1e6, 10e6], order=2, damping=0.05, spacing="lin", f_min=1e6)

    assert np.isclose(abs(poles[0].imag) / (2 * np.pi), 1e6)


def test_relocate_common_poles_moves_toward_scalar_response_pole():
    freqs = np.linspace(1e6, 30e6, 80)
    true_pole = -2.0e7 + 2j * np.pi * 8.0e6
    true_conjugate = true_pole.conjugate()
    s = 2j * np.pi * freqs
    values = 0.1 + 1.5e7 / (s - true_pole) + 1.5e7 / (s - true_conjugate)
    samples = values.reshape(len(freqs), 1, 1)
    initial = initial_common_poles(freqs, order=2, damping=0.05, spacing="lin")

    step = relocate_common_poles(freqs, samples, initial, max_responses=None)

    assert len(step.poles_rad_per_s) == 2
    assert np.all(step.poles_rad_per_s.real < 0.0)
    assert step.rank is not None and step.rank > 0
    initial_distance = np.min(np.abs(initial - true_pole))
    relocated_distance = np.min(np.abs(step.poles_rad_per_s - true_pole))
    assert relocated_distance < initial_distance


def test_relocate_common_poles_can_select_diagonal_responses():
    freqs = np.linspace(1e6, 10e6, 16)
    samples = np.zeros((len(freqs), 2, 2), dtype=complex)
    samples[:, 0, 0] = 1.0
    samples[:, 1, 1] = 2.0
    samples[:, 0, 1] = 100.0
    initial = initial_common_poles(freqs, order=2)

    step = relocate_common_poles(freqs, samples, initial, response_selection="diagonal", max_responses=2)

    assert step.selected_response_indices == (0, 3)


def test_relocate_common_poles_can_force_conjugate_pairs():
    freqs = np.linspace(1e6, 10e6, 24)
    samples = np.zeros((len(freqs), 1, 1), dtype=complex)
    samples[:, 0, 0] = 1.0 / (2j * np.pi * freqs - complex(-2e6, 3e7))
    initial = initial_common_poles(freqs, order=4)

    step = relocate_common_poles(freqs, samples, initial, max_responses=None, pole_pairing="conjugate")
    positive = sorted(pole.imag for pole in step.poles_rad_per_s if pole.imag > 0.0)
    negative = sorted(-pole.imag for pole in step.poles_rad_per_s if pole.imag < 0.0)

    assert len(step.poles_rad_per_s) == 4
    assert len(positive) == len(negative) == 2
    assert np.allclose(positive, negative)


def test_adaptive_z_selection_keeps_worst_z_pairs():
    values = np.zeros((3, 2, 2), dtype=complex)
    values[:, 0, 0] = 1.0
    values[:, 0, 1] = 100.0
    values[:, 1, 0] = 50.0
    values[:, 1, 1] = 2.0
    original_z = np.ones((3, 2, 2), dtype=complex)
    fitted_z = original_z.copy()
    fitted_z[:, 1, 1] *= 100.0

    selected = idem._select_adaptive_z_response_indices(values, original_z, fitted_z, 2, worst_pair_count=1)

    assert 3 in selected
    assert len(selected) == 2


def test_run_local_idem_like_fit_selects_best_iteration(tmp_path: Path):
    touchstone = tmp_path / "line.s2p"
    _write_s2p(touchstone)

    result = run_local_idem_like_fit(
        touchstone,
        order=1,
        iterations=1,
        fit_max_frequency_points=2,
        max_pole_responses=2,
        residue_basis="complex",
    )

    assert result["probe"] == "local_idem_like_fit"
    assert result["recipe"]["order"] == 1
    assert len(result["iterations"]) == 2
    assert result["best"]["iteration"] in {0, 1}


def test_run_local_idem_like_fit_backfills_s_mean_for_selection(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    _write_s2p(touchstone)

    def fake_probe(*args, **kwargs):
        return [
            {"iteration": 0, "s_rms_error": 30.0, "ports": 30, "z_log_magnitude_rms_error": 0.1},
            {"iteration": 1, "s_rms_error": 3.0, "ports": 30, "z_log_magnitude_rms_error": 0.2},
        ]

    monkeypatch.setattr(idem, "run_local_pole_relocation_probe", fake_probe)

    result = run_local_idem_like_fit(
        touchstone,
        selection_metric="s_mean_rms_error",
    )

    assert result["iterations"][0]["s_mean_rms_error"] == 1.0
    assert result["iterations"][1]["s_mean_rms_error"] == 0.1
    assert result["best"]["iteration"] == 1


def test_local_idem_like_model_round_trips_metrics(tmp_path: Path):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "line_model.npz"
    _write_s2p(touchstone)

    result = run_local_idem_like_fit(
        touchstone,
        order=1,
        iterations=1,
        fit_max_frequency_points=2,
        max_pole_responses=2,
        residue_basis="complex",
        model_output_path=model,
    )
    replay = evaluate_local_idem_like_model(model, touchstone)

    assert model.exists()
    assert replay["basis"] == "complex"
    assert replay["pole_count"] == 1
    assert np.isclose(replay["z_log_magnitude_rms_error"], result["best"]["z_log_magnitude_rms_error"])


def test_export_local_idem_like_touchstone_writes_readable_network(tmp_path: Path):
    import skrf as rf

    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "line_model.npz"
    output = tmp_path / "line_fit.s2p"
    _write_s2p(touchstone)
    run_local_idem_like_fit(
        touchstone,
        order=1,
        iterations=1,
        fit_max_frequency_points=2,
        max_pole_responses=2,
        residue_basis="complex",
        model_output_path=model,
    )

    result = export_local_idem_like_touchstone(model, output, reference_touchstone_path=touchstone)
    exported = rf.Network(str(output))

    assert Path(result["output_path"]) == output
    assert exported.nports == 2
    assert len(exported.f) == 2


def test_export_local_idem_like_state_space_replays_model(tmp_path: Path):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "line_model.npz"
    state_space = tmp_path / "line_statespace.npz"
    _write_s2p(touchstone)
    run_local_idem_like_fit(
        touchstone,
        order=1,
        iterations=1,
        fit_max_frequency_points=2,
        max_pole_responses=2,
        residue_basis="complex",
        model_output_path=model,
    )

    export = export_local_idem_like_state_space(model, state_space)
    replay_model = evaluate_local_idem_like_model(model, touchstone)
    replay_state = evaluate_local_idem_like_state_space(state_space, touchstone)

    assert export["states"] == 2
    assert state_space.exists()
    assert np.isclose(replay_state["z_log_magnitude_rms_error"], replay_model["z_log_magnitude_rms_error"])
