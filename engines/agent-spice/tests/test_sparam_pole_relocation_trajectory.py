import scripts.sparam_pole_relocation_trajectory as traj


def test_describe_relocation_history_reports_edge_drop():
    history = [
        {
            "iteration": 0,
            "complex_pair_frequencies_hz": [1.4e9, 2.0e9],
            "condition_number": 10.0,
            "d_res_abs": 1.0,
            "input_complex_pair_frequencies_hz": [1.4e9, 2.0e9],
            "input_complex_pair_c_res_magnitudes": [0.1, 0.2],
        },
        {
            "iteration": 1,
            "complex_pair_frequencies_hz": [1.386e9, 5.3e4],
            "condition_number": 20.0,
            "d_res_abs": 0.5,
            "input_complex_pair_frequencies_hz": [1.4e9, 2.0e9],
            "input_complex_pair_c_res_magnitudes": [0.3, 0.4],
        },
    ]

    summary = traj.describe_relocation_history(history)

    assert summary["iterations"] == 2
    assert summary["edge_frequency_by_iteration"] == [2.0e9, 1.386e9]
    assert summary["largest_negative_edge_step_hz"] == -614000000.0
    assert summary["collapse_iteration"] == 1
    assert summary["collapse_window"][1]["condition_number"] == 20.0
    assert summary["collapse_window"][1]["input_complex_pair_c_res_magnitudes"] == [0.3, 0.4]
