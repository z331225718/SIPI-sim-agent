import json
from argparse import Namespace
from pathlib import Path

from agent_spice.cli import _apply_modal_auto_preset, main


def test_fit_modal_z_cli_writes_json_and_html_reports(tmp_path: Path):
    report = tmp_path / "modal_report.json"
    html = tmp_path / "modal_report.html"

    exit_code = main(
        [
            "fit-modal-z",
            "tests/fixtures/sparam/simple_through.s2p",
            "--report",
            str(report),
            "--html-report",
            str(html),
            "--mode-count",
            "1",
            "--basis-anchor-ports",
            "1",
            "--basis-frequency-sample-count",
            "3",
            "--basis-frequency-sampling",
            "linear",
            "--scalar-fit-order",
            "4",
            "--frequency-sample-head-count",
            "2",
            "--decomposition",
            "svd",
            "--reduced-fit-method",
            "vector",
            "--peak-pole-frequency-head-count",
            "2",
            "--peak-pole-entry-count",
            "1",
            "--peak-pole-full-pair-count",
            "2",
            "--peak-pole-complete-order",
            "--vector-target-error",
            "0.001",
            "--vector-iters-final",
            "3",
            "--relative-weight-power",
            "0.6",
            "--relative-weight-mode",
            "full-projected",
            "--relative-weight-iterations",
            "2",
            "--relative-weight-update",
            "max",
            "--target-error-weight-power",
            "1.5",
            "--target-error-weight-max",
            "6",
            "--target-error-pair-count",
            "2",
            "--residual-pair-count",
            "2",
            "--residual-fit-order",
            "4",
            "--residual-pole-damping",
            "0.2",
            "--residual-weight-power",
            "0.5",
            "--residual-gain",
            "0.75",
            "--residual-mirror-pairs",
        ]
    )

    assert exit_code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["mode"] == "modal_z"
    assert payload["ports"] == 2
    assert payload["mode_count"] == 1
    assert payload["config"]["basis_anchor_ports"] == [1]
    assert payload["basis_anchor_ports"] == [1]
    assert payload["config"]["basis_frequency_sample_count"] == 3
    assert payload["config"]["basis_frequency_sampling"] == "linear"
    assert payload["config"]["frequency_sample_head_count"] == 2
    assert payload["reduced_fit_method"] == "vector"
    assert payload["config"]["vector_target_error"] == 0.001
    assert payload["config"]["vector_iters_final"] == 3
    assert payload["config"]["peak_pole_frequency_head_count"] == 2
    assert payload["config"]["peak_pole_entry_count"] == 1
    assert payload["config"]["peak_pole_full_pair_count"] == 2
    assert payload["config"]["peak_pole_complete_order"] is True
    assert payload["config"]["relative_weight_power"] == 0.6
    assert payload["config"]["relative_weight_mode"] == "full-projected"
    assert payload["config"]["relative_weight_iterations"] == 2
    assert payload["config"]["relative_weight_update"] == "max"
    assert payload["config"]["target_error_weight_power"] == 1.5
    assert payload["config"]["target_error_weight_max"] == 6
    assert payload["config"]["target_error_pair_count"] == 2
    assert payload["config"]["residual_pair_count"] == 2
    assert payload["config"]["residual_fit_order"] == 4
    assert payload["config"]["residual_pole_damping"] == 0.2
    assert payload["config"]["residual_weight_power"] == 0.5
    assert payload["config"]["residual_gain"] == 0.75
    assert payload["config"]["residual_mirror_pairs"] is True
    assert "residual_correction_pair_count" in payload
    assert payload["s_rms_error"] >= 0.0
    assert payload["s_rms_error_scope"] == "original_frequency_points"
    assert payload["z_log_magnitude_rms_error"] >= 0.0
    assert payload["basis_projection_z_log_magnitude_rms_error"] >= 0.0
    assert "selected_pole_count" in payload
    html_text = html.read_text(encoding="utf-8")
    assert "Modal Z-Fit Report" in html_text
    assert "Original vs Fitted Z Magnitude" in html_text
    assert "<svg" in html_text


def test_fit_modal_z_cli_can_auto_select_bounded_order(tmp_path: Path):
    report = tmp_path / "modal_auto_report.json"
    html = tmp_path / "modal_auto_report.html"

    exit_code = main(
        [
            "fit-modal-z",
            "tests/fixtures/sparam/simple_through.s2p",
            "--report",
            str(report),
            "--html-report",
            str(html),
            "--mode-count",
            "1",
            "--scalar-fit-order",
            "4",
            "--decomposition",
            "svd",
            "--auto-order-candidates",
            "2,4",
            "--auto-order-max-z-log-rms-error",
            "0.1",
        ]
    )

    assert exit_code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["config"]["auto_order_candidates"] == [2, 4]
    assert payload["auto_order_trials"]
    assert payload["scalar_fit_order"] in {2, 4}
    assert "selected_pole_count" in payload["auto_order_trials"][0]
    html_text = html.read_text(encoding="utf-8")
    assert "Auto-Order Trials" in html_text
    assert "Selected Poles" in html_text


def test_fit_modal_z_cli_writes_quality_gate_and_can_pass(tmp_path: Path):
    report = tmp_path / "modal_quality_pass_report.json"
    html = tmp_path / "modal_quality_pass_report.html"

    exit_code = main(
        [
            "fit-modal-z",
            "tests/fixtures/sparam/simple_through.s2p",
            "--report",
            str(report),
            "--html-report",
            str(html),
            "--mode-count",
            "1",
            "--scalar-fit-order",
            "4",
            "--decomposition",
            "svd",
            "--fail-on-quality",
            "--max-s-rms-error",
            "10",
            "--max-z-log-rms-error",
            "10",
            "--max-diag-z-log-rms-error",
            "10",
            "--max-basis-projection-z-log-rms-error",
            "10",
            "--max-scalar-fit-order",
            "4",
        ]
    )

    assert exit_code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["quality"]["status"] == "PASS"
    assert [check["metric"] for check in payload["quality"]["checks"]] == [
        "s_rms_error",
        "z_log_magnitude_rms_error",
        "diagonal_z_log_magnitude_rms_error",
        "basis_projection_z_log_magnitude_rms_error",
        "scalar_fit_order",
    ]
    assert "Quality Gate" in html.read_text(encoding="utf-8")


def test_fit_modal_z_cli_fail_on_quality_returns_nonzero(tmp_path: Path, capsys):
    report = tmp_path / "modal_quality_fail_report.json"

    exit_code = main(
        [
            "fit-modal-z",
            "tests/fixtures/sparam/simple_through.s2p",
            "--report",
            str(report),
            "--mode-count",
            "1",
            "--scalar-fit-order",
            "4",
            "--decomposition",
            "svd",
            "--fail-on-quality",
            "--max-scalar-fit-order",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["quality"]["status"] == "FAIL"
    assert "scalar_fit_order=4 exceeds max 1" in payload["quality"]["blocking_reasons"]
    assert "modal-z quality gate failed" in captured.err


def test_fit_modal_z_cli_can_auto_sweep_basis_candidates(tmp_path: Path):
    report = tmp_path / "modal_auto_basis_report.json"
    html = tmp_path / "modal_auto_basis_report.html"

    exit_code = main(
        [
            "fit-modal-z",
            "tests/fixtures/sparam/simple_through.s2p",
            "--report",
            str(report),
            "--html-report",
            str(html),
            "--mode-count",
            "1",
            "--scalar-fit-order",
            "4",
            "--decomposition",
            "svd",
            "--auto-order-candidates",
            "2,4",
            "--auto-basis-mode-counts",
            "1,2",
            "--auto-basis-sample-counts",
            "2,3",
            "--auto-basis-anchor-port-counts",
            "0,1",
            "--auto-basis-anchor-candidate-count",
            "3",
            "--auto-basis-anchor-combo-count",
            "1",
            "--auto-pole-dampings",
            "0.05",
            "--auto-shared-pole-trace-counts",
            "1",
            "--auto-peak-pole-entry-counts",
            "0",
            "--auto-basis-diagonal-weight",
            "0.25",
        ]
    )

    assert exit_code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["config"]["auto_basis_mode_counts"] == [1, 2]
    assert payload["config"]["auto_basis_sample_counts"] == [2, 3]
    assert payload["config"]["auto_basis_anchor_port_counts"] == [0, 1]
    assert payload["config"]["auto_basis_anchor_candidate_count"] == 3
    assert payload["config"]["auto_basis_anchor_combo_count"] == 1
    assert payload["config"]["auto_pole_dampings"] == [0.05]
    assert payload["config"]["auto_shared_pole_trace_counts"] == [1]
    assert payload["config"]["auto_peak_pole_entry_counts"] == [0]
    assert payload["config"]["auto_basis_diagonal_weight"] == 0.25
    assert len(payload["auto_basis_trials"]) == 20
    assert any(trial["mode_count"] == 2 and trial["basis_anchor_ports"] == [1] for trial in payload["auto_basis_trials"])
    assert "basis_anchor_ports" in payload["auto_basis_trials"][0]
    assert "pole_damping" in payload["auto_basis_trials"][0]
    assert "shared_pole_trace_count" in payload["auto_basis_trials"][0]
    assert "peak_pole_entry_count" in payload["auto_basis_trials"][0]
    assert "selection_score" in payload["auto_basis_trials"][0]
    assert "Auto-Basis Trials" in html.read_text(encoding="utf-8")


def test_fit_modal_z_cli_can_apply_compact_auto_preset(tmp_path: Path):
    report = tmp_path / "modal_preset_report.json"
    html = tmp_path / "modal_preset_report.html"

    exit_code = main(
        [
            "fit-modal-z",
            "tests/fixtures/sparam/simple_through.s2p",
            "--report",
            str(report),
            "--html-report",
            str(html),
            "--auto-preset",
            "compact",
        ]
    )

    assert exit_code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["config"]["auto_preset"] == "compact"
    assert payload["config"]["mode_count"] == 1
    assert payload["config"]["auto_basis_mode_counts"] == [1]
    assert payload["config"]["auto_basis_anchor_port_counts"] == [1]
    assert payload["config"]["auto_basis_anchor_candidate_count"] == 2
    assert payload["config"]["auto_order_candidates"] == [128, 160, 192, 224]
    assert payload["config"]["auto_order_max_z_log_magnitude_rms_error"] == 0.38
    assert payload["auto_basis_trials"]


def test_fit_modal_z_cli_auto_preset_respects_explicit_mode_count(tmp_path: Path):
    report = tmp_path / "modal_preset_override_report.json"

    exit_code = main(
        [
            "fit-modal-z",
            "tests/fixtures/sparam/simple_through.s2p",
            "--report",
            str(report),
            "--auto-preset",
            "compact",
            "--mode-count",
            "2",
            "--auto-basis-anchor-port-counts",
            "1",
        ]
    )

    assert exit_code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["config"]["mode_count"] == 2
    assert payload["config"]["auto_basis_mode_counts"] == [2]


def test_fit_modal_z_cli_auto_preset_uses_low_order_auto_order_for_30p():
    args = Namespace(auto_preset="high-accuracy", touchstone=Path("model.s30p"), mode_count=8)

    _apply_modal_auto_preset(args, ["fit-modal-z", "model.s30p", "--auto-preset", "high-accuracy"])

    assert args.mode_count == 28
    assert args.basis_frequency_sample_count == 21
    assert args.scalar_fit_order == 56
    assert args.frequency_sample_count == 256
    assert args.frequency_sample_head_count == 3
    assert args.shared_pole_trace_count == 2
    assert args.auto_order_candidates == "44,48,52,56"
    assert args.auto_order_max_z_log_rms_error == 0.445
    assert args.auto_order_max_diag_z_log_rms_error == 0.12
    assert args.max_z_log_rms_error == 0.445
    assert args.max_diag_z_log_rms_error == 0.12
    assert args.max_scalar_fit_order == 56
    assert not hasattr(args, "auto_basis_mode_counts")
    assert not hasattr(args, "auto_pole_dampings")
