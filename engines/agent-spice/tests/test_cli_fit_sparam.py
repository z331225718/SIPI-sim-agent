from pathlib import Path
from types import SimpleNamespace

import pytest


class FakeQualityReport:
    def __init__(self, status="PASS", blocking_reasons=None, warnings=None):
        self.status = status
        self.blocking_reasons = [] if blocking_reasons is None else blocking_reasons
        self.warnings = [] if warnings is None else warnings


class FakeFitResult:
    def __init__(self, quality_report):
        self.quality_report = quality_report


@pytest.fixture(autouse=True)
def bridge_legacy_single_fit_tests(monkeypatch, request):
    import agent_spice.cli as cli

    original_apply = cli._apply_sparam_auto_preset

    def apply_with_legacy_test_target(args, argv):
        original_apply(args, argv)
        if (
            request.node.name != "test_fit_sparam_cli_requires_rms_target"
            and getattr(args, "rms_target", None) is None
            and args.auto_target_mean_rms_error is None
        ):
            args.rms_target = 0.001

    def target_bridge(touchstone_path, output_path, *, target, config, report_path, html_report_path, log_path):
        fit = getattr(cli, "fit_touchstone_to_spice", None)
        if fit is None:
            raise AssertionError("test must patch fit_touchstone_to_spice_target or legacy fit_touchstone_to_spice")
        fit_result = fit(
            touchstone_path,
            output_path,
            config=config,
            report_path=report_path,
            html_report_path=html_report_path,
            log_path=log_path,
        )
        return SimpleNamespace(
            target_met=True,
            selected_trial=SimpleNamespace(payload=fit_result),
        )

    monkeypatch.setattr(cli, "_apply_sparam_auto_preset", apply_with_legacy_test_target)
    monkeypatch.setattr(cli, "fit_touchstone_to_spice_target", target_bridge)


def test_fit_sparam_cli_passes_explicit_report_path(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        calls.append((touchstone_path, output_path, config, report_path, html_report_path, log_path))
        output_path.write_text(".subckt s_equivalent 1 2\n.ends s_equivalent\n", encoding="utf-8")
        report_path.write_text("{}\n", encoding="utf-8")
        html_report_path.write_text("<html></html>\n", encoding="utf-8")
        log_path.write_text("ok\n", encoding="utf-8")
        return output_path

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--report",
            str(tmp_path / "fit_report.json"),
            "--html-report",
            str(tmp_path / "fit_report.html"),
            "--log",
            str(tmp_path / "fit.log"),
            "--mode",
            "manual",
            "--n-poles-real",
            "4",
            "--n-poles-cmplx",
            "5",
            "--init-pole-spacing",
            "log",
            "--subckt-name",
            "pkg_model",
            "--n-poles-add",
            "1",
            "--fit-max-iterations",
            "8",
            "--passivity-samples",
            "15",
            "--passivity-f-max",
            "3000000000",
            "--fit-frequency-stride",
            "2",
            "--fit-max-frequency-points",
            "128",
            "--fit-f-min",
            "1000000",
            "--fit-f-max",
            "5000000000",
            "--high-frequency-complex-pairs",
            "2",
            "--high-frequency-complex-pair-damping",
            "0.05",
            "--high-frequency-complex-pair-lower-fraction",
            "0.7",
            "--native-high-frequency-complex-pair-frequency-gate",
            "--native-high-frequency-residual-injection",
            "--native-high-frequency-residual-injection-lower-fraction",
            "0.72",
            "--native-high-frequency-residual-injection-damping",
            "0.06",
            "--high-frequency-complex-pair-anchor-bands",
            "1.3e9:1.45e9,1.8e9:2.0e9",
            "--high-frequency-complex-pair-anchor-strength",
            "0.1",
            "--high-frequency-complex-pair-anchor-damping",
            "0.04",
            "--native-effective-order-max",
            "10",
            "--native-effective-complex-pole-count",
            "2",
            "--native-effective-order-selection",
            "contribution_score",
            "--native-effective-order-passivity-weight",
            "2.5",
            "--native-post-relocation-effective-order-max",
            "8",
            "--no-fit-dc",
            "--native-high-frequency-relocation-weight",
            "--native-high-frequency-relocation-weight-lower-fraction",
            "0.73",
            "--native-high-frequency-relocation-weight-gain",
            "2.75",
            "--native-out-of-band-pole-regularization-weight",
            "0.125",
            "--native-out-of-band-pole-regularization-start-fraction",
            "1.05",
            "--native-dynamic-edge-c-res-regularization",
            "--native-dynamic-edge-c-res-regularization-base-weight",
            "0.025",
            "--native-dynamic-edge-c-res-regularization-start-fraction",
            "1.0",
            "--native-dynamic-edge-c-res-regularization-growth-threshold",
            "1.2",
            "--quality-profile",
            "signoff",
            "--max-comparison-rms-error",
            "0.02",
            "--max-passivity-epsilon",
            "0.0000015",
            "--require-dc",
        ]
    )

    assert exit_code == 0
    assert calls[0][0] == tmp_path / "line.s2p"
    assert calls[0][1] == tmp_path / "model.sp"
    assert calls[0][3] == tmp_path / "fit_report.json"
    assert calls[0][4] == tmp_path / "fit_report.html"
    assert calls[0][5] == tmp_path / "fit.log"
    assert calls[0][2].mode == "manual"
    assert calls[0][2].n_poles_real == 4
    assert calls[0][2].n_poles_cmplx == 5
    assert calls[0][2].init_pole_spacing == "log"
    assert calls[0][2].subckt_name == "pkg_model"
    assert calls[0][2].n_poles_add == 1
    assert calls[0][2].max_iterations == 8
    assert calls[0][2].passivity_samples == 15
    assert calls[0][2].passivity_f_max == 3e9
    assert calls[0][2].fit_frequency_stride == 2
    assert calls[0][2].fit_max_frequency_points == 128
    assert calls[0][2].fit_f_min == 1e6
    assert calls[0][2].fit_f_max == 5e9
    assert calls[0][2].high_frequency_complex_pair_count == 2
    assert calls[0][2].high_frequency_complex_pair_damping == 0.05
    assert calls[0][2].high_frequency_complex_pair_lower_fraction == 0.7
    assert calls[0][2].native_high_frequency_complex_pair_frequency_gate is True
    assert calls[0][2].native_high_frequency_residual_injection is True
    assert calls[0][2].native_high_frequency_residual_injection_lower_fraction == 0.72
    assert calls[0][2].native_high_frequency_residual_injection_damping == 0.06
    assert calls[0][2].high_frequency_complex_pair_anchor_bands_hz == ((1.3e9, 1.45e9), (1.8e9, 2.0e9))
    assert calls[0][2].high_frequency_complex_pair_anchor_strength == 0.1
    assert calls[0][2].high_frequency_complex_pair_anchor_damping == 0.04
    assert calls[0][2].native_effective_order_max == 10
    assert calls[0][2].native_effective_complex_pole_count == 2
    assert calls[0][2].native_effective_order_selection == "contribution_score"
    assert calls[0][2].native_effective_order_passivity_weight == 2.5
    assert calls[0][2].native_post_relocation_effective_order_max == 8
    assert calls[0][2].enforce_dc is False
    assert calls[0][2].native_high_frequency_relocation_weight is True
    assert calls[0][2].native_high_frequency_relocation_weight_lower_fraction == 0.73
    assert calls[0][2].native_high_frequency_relocation_weight_gain == 2.75
    assert calls[0][2].native_out_of_band_pole_regularization_weight == 0.125
    assert calls[0][2].native_out_of_band_pole_regularization_start_fraction == 1.05
    assert calls[0][2].native_dynamic_edge_c_res_regularization is True
    assert calls[0][2].native_dynamic_edge_c_res_regularization_base_weight == 0.025
    assert calls[0][2].native_dynamic_edge_c_res_regularization_start_fraction == 1.0
    assert calls[0][2].native_dynamic_edge_c_res_regularization_growth_threshold == 1.2
    assert calls[0][2].quality_profile == "signoff"
    assert calls[0][2].max_comparison_rms_error == 0.02
    assert calls[0][2].max_passivity_epsilon == 1.5e-6
    assert calls[0][2].require_dc is True


def test_fit_sparam_cli_defaults_report_next_to_output(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        calls.append((touchstone_path, output_path, config, report_path, html_report_path, log_path))
        output_path.write_text(".subckt s_equivalent 1 2\n.ends s_equivalent\n", encoding="utf-8")
        report_path.write_text("{}\n", encoding="utf-8")
        html_report_path.write_text("<html></html>\n", encoding="utf-8")
        return output_path

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(["fit-sparam", str(tmp_path / "line.s2p"), "--output", str(tmp_path / "model.sp")])

    assert exit_code == 0
    assert calls[0][3] == tmp_path / "fit_report.json"
    assert calls[0][4] == tmp_path / "fit_report.html"
    assert calls[0][5] is None
    assert calls[0][2].enforce_dc is True
    assert calls[0][2].enforce_passivity is False


def test_fit_sparam_cli_can_enable_passivity_enforcement(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        calls.append((touchstone_path, output_path, config, report_path, html_report_path, log_path))
        return output_path

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--enforce-passivity",
        ]
    )

    assert exit_code == 0
    assert calls[0][2].enforce_passivity is True
    assert calls[0][2].check_passivity is True


def test_fit_sparam_cli_enforce_passivity_always_keeps_truthful_check(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        calls.append(config)
        return output_path

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--enforce-passivity",
            "--skip-passivity-check",
        ]
    )

    assert exit_code == 0
    assert calls[0].enforce_passivity is True
    assert calls[0].check_passivity is True


def test_fit_sparam_cli_reports_value_error_without_traceback(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        raise ValueError("Frequency selection must contain at least 2 samples for vector fitting")

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(["fit-sparam", str(tmp_path / "line.s2p"), "--output", str(tmp_path / "model.sp")])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error: Frequency selection must contain at least 2 samples for vector fitting" in captured.err
    assert "Traceback" not in captured.err


def test_fit_sparam_cli_fail_on_quality_rejects_warnings(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        return FakeFitResult(FakeQualityReport(status="WARN", warnings=["dc_coverage"]))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--fail-on-quality",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "quality gate failed: status=WARN" in captured.err
    assert "dc_coverage" in captured.err


def test_fit_sparam_cli_fail_on_quality_can_allow_warnings(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        return FakeFitResult(FakeQualityReport(status="WARN", warnings=["dc_coverage"]))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--fail-on-quality",
            "--allow-quality-warnings",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "quality gate failed" not in captured.err


def test_fit_sparam_cli_fail_on_quality_rejects_blocking_failures(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        return FakeFitResult(FakeQualityReport(status="FAIL", blocking_reasons=["passivity_after_enforce"]))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--fail-on-quality",
            "--allow-quality-warnings",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "quality gate failed: status=FAIL" in captured.err
    assert "passivity_after_enforce" in captured.err


def test_fit_sparam_cli_supports_idem_exporter(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    exporter_value = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        exporter_value.append(config.exporter)
        return FakeFitResult(FakeQualityReport(status="PASS"))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--exporter",
            "idem",
        ]
    )

    assert exit_code == 0
    assert exporter_value == ["idem"]


def test_fit_sparam_cli_rejects_retired_auto_preset_for_30p():
    from argparse import Namespace

    import agent_spice.cli as cli

    args = Namespace(
        auto_preset="compact",
        touchstone=Path("model.s30p"),
        auto_model_order_candidates=None,
        auto_target_mean_rms_error=None,
        skip_passivity_enforce=False,
        skip_passivity_check=False,
    )

    try:
        cli._apply_sparam_auto_preset(args, ["fit-sparam", "model.s30p", "--auto-preset", "compact"])
    except ValueError as exc:
        assert "Unsupported S-parameter auto preset 'compact'" in str(exc)
    else:
        raise AssertionError("compact preset should be retired from fit-sparam")


def test_fit_sparam_cli_help_is_idem_fast_focused(capsys):
    import agent_spice.cli as cli

    try:
        cli.main(["fit-sparam", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("--help should exit through argparse")

    captured = capsys.readouterr()
    assert "IdEM-fast baseline" in captured.out
    assert "--rms-target" in captured.out
    assert "--passivity {off,check,enforce}" in captured.out
    assert "--max-order" in captured.out
    assert "--enforce-passivity" not in captured.out
    assert "--n-poles-real" not in captured.out
    assert "compact" not in captured.out
    assert "high-accuracy" not in captured.out


def test_fit_sparam_cli_can_apply_idem_fast_preset_for_30p():
    from argparse import Namespace

    import agent_spice.cli as cli

    args = Namespace(
        auto_preset="idem-fast",
        touchstone=Path("model.s30p"),
        mode="auto",
        n_poles_real=2,
        n_poles_cmplx=2,
        init_pole_spacing="lin",
        fit_max_iterations=None,
        fit_max_frequency_points=None,
        relocation_backend="skrf",
        vector_fit_backend="skrf",
        use_lightweight_network=False,
        high_frequency_complex_pairs=0,
        high_frequency_complex_pair_damping=0.03,
        high_frequency_complex_pair_lower_fraction=0.68,
        auto_model_order_candidates=None,
        auto_target_mean_rms_error=None,
        skip_passivity_enforce=False,
        skip_passivity_check=False,
    )

    cli._apply_sparam_auto_preset(args, ["fit-sparam", "model.s30p", "--auto-preset", "idem-fast"])

    assert args.mode == "manual"
    assert args.n_poles_real == 4
    assert args.n_poles_cmplx == 30
    assert args.init_pole_spacing == "lin"
    assert args.fit_max_iterations == 6
    assert args.fit_max_frequency_points == 256
    assert args.relocation_backend == "streaming-reciprocal"
    assert args.vector_fit_backend == "native"
    assert args.use_lightweight_network is True
    assert args.high_frequency_complex_pairs == 0
    assert args.auto_model_order_candidates is None
    assert args.auto_target_mean_rms_error is None
    assert args.skip_passivity_enforce is True
    assert args.skip_passivity_check is True


def test_fit_sparam_cli_applies_idem_fast_low_order_auto_for_large_ports():
    from argparse import Namespace

    import agent_spice.cli as cli

    args = Namespace(
        auto_preset="idem-fast",
        touchstone=Path("model.s91p"),
        mode="auto",
        n_poles_real=2,
        n_poles_cmplx=2,
        init_pole_spacing="lin",
        fit_max_iterations=None,
        fit_max_frequency_points=None,
        relocation_backend="skrf",
        vector_fit_backend="skrf",
        use_lightweight_network=False,
        high_frequency_complex_pairs=0,
        high_frequency_complex_pair_damping=0.01,
        high_frequency_complex_pair_lower_fraction=0.5,
        auto_model_order_candidates=None,
        auto_target_mean_rms_error=None,
        skip_passivity_enforce=False,
        skip_passivity_check=False,
        no_fit_dc=False,
        native_post_relocation_effective_order_max=None,
    )

    cli._apply_sparam_auto_preset(args, ["fit-sparam", "model.s91p", "--auto-preset", "idem-fast"])

    assert args.mode == "manual"
    assert args.n_poles_real == 4
    assert args.n_poles_cmplx == 2
    assert args.init_pole_spacing == "lin"
    assert args.fit_max_iterations == 14
    assert args.fit_max_frequency_points is None
    assert args.relocation_backend == "streaming-reciprocal"
    assert args.vector_fit_backend == "native"
    assert args.use_lightweight_network is True
    assert args.high_frequency_complex_pairs == 2
    assert args.high_frequency_complex_pair_damping == 0.03
    assert args.high_frequency_complex_pair_lower_fraction == 0.68
    assert args.auto_model_order_candidates is None
    assert args.auto_target_mean_rms_error is None
    assert args.no_fit_dc is True
    assert args.native_post_relocation_effective_order_max == 8


def test_fit_sparam_cli_uses_auto_order_runner(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_target(touchstone_path, output_path, *, target, config, report_path, html_report_path, log_path):
        calls.append((target, config))
        return SimpleNamespace(target_met=True, selected_trial=SimpleNamespace(payload=None))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice_target", fake_target)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s30p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--auto-model-order-candidates",
            "40,60",
            "--auto-target-mean-rms-error",
            "0.002",
        ]
    )

    assert exit_code == 0
    assert calls[0][0].mean_rms == pytest.approx(0.002)
    assert calls[0][0].max_order == 60


def test_fit_sparam_cli_defaults_to_full_grid_no_dc_order8_for_large_ports(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, **_kwargs):
        calls.append((touchstone_path, output_path, config))
        return FakeFitResult(FakeQualityReport(status="PASS"))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(["fit-sparam", str(tmp_path / "line.s91p"), "--output", str(tmp_path / "model.sp")])

    assert exit_code == 0
    assert calls[0][2].mode == "manual"
    assert calls[0][2].n_poles_real == 4
    assert calls[0][2].n_poles_cmplx == 2
    assert calls[0][2].init_pole_spacing == "lin"
    assert calls[0][2].fit_max_frequency_points is None
    assert calls[0][2].enforce_dc is False
    assert calls[0][2].native_post_relocation_effective_order_max == 8
    assert calls[0][2].vector_fit_backend == "native"
    assert calls[0][2].high_frequency_complex_pair_count == 2
    assert calls[0][2].passivity_samples == 8
    assert calls[0][2].passivity_max_iterations == 1
    assert calls[0][2].passivity_active_variables == 3072
    assert calls[0][2].enforce_passivity is False
    assert calls[0][2].check_passivity is True


def test_fit_sparam_cli_idem_fast_preset_uses_single_manual_fit(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    fit_calls = []
    auto_calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        fit_calls.append(config)
        return FakeFitResult(FakeQualityReport(status="PASS"))

    def fake_auto(*args, **kwargs):
        auto_calls.append((args, kwargs))
        return FakeFitResult(FakeQualityReport(status="PASS"))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)
    monkeypatch.setattr(cli, "fit_touchstone_to_spice_auto_order", fake_auto, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s30p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--auto-preset",
            "idem-fast",
        ]
    )

    assert exit_code == 0
    assert len(fit_calls) == 1
    assert auto_calls == []
    assert fit_calls[0].mode == "manual"
    assert fit_calls[0].n_poles_real == 4
    assert fit_calls[0].n_poles_cmplx == 30
    assert fit_calls[0].max_iterations == 6
    assert fit_calls[0].fit_max_frequency_points == 256
    assert fit_calls[0].relocation_backend == "streaming-reciprocal"
    assert fit_calls[0].vector_fit_backend == "native"
    assert fit_calls[0].use_lightweight_network is True
    assert fit_calls[0].check_passivity is True
    assert fit_calls[0].enforce_passivity is False


def test_fit_sparam_cli_idem_fast_large_port_enforce_uses_passivity_profile(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    fit_calls = []
    auto_calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        fit_calls.append(config)
        return FakeFitResult(FakeQualityReport(status="PASS"))

    def fake_auto(*args, **kwargs):
        auto_calls.append((args, kwargs))
        return FakeFitResult(FakeQualityReport(status="PASS"))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)
    monkeypatch.setattr(cli, "fit_touchstone_to_spice_auto_order", fake_auto, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s91p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--auto-preset",
            "idem-fast",
            "--enforce-passivity",
        ]
    )

    assert exit_code == 0
    assert len(fit_calls) == 1
    assert auto_calls == []
    config = fit_calls[0]
    assert config.n_poles_real == 4
    assert config.n_poles_cmplx == 2
    assert config.init_pole_spacing == "lin"
    assert config.fit_max_frequency_points is None
    assert config.enforce_dc is False
    assert config.native_post_relocation_effective_order_max == 8
    assert config.enforce_passivity is True
    assert config.check_passivity is True
    assert config.passivity_samples == 64
    assert config.passivity_max_iterations == 0
    assert config.passivity_perturb_constant is False
    assert config.passivity_global_damping_fallback is True
    assert config.passivity_global_damping_safety_margin == 1e-7
    assert config.passivity_spectral_projection_fallback is False
    assert config.passivity_spectral_projection_iterations == 0


def test_fit_sparam_cli_auto_preset_respects_explicit_options_when_argv_is_none(tmp_path: Path, monkeypatch):
    import sys

    import agent_spice.cli as cli

    fit_calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        fit_calls.append(config)
        return FakeFitResult(FakeQualityReport(status="PASS"))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent-spice",
            "fit-sparam",
            str(tmp_path / "line.s30p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--auto-preset",
            "idem-fast",
            "--fit-max-frequency-points",
            "320",
        ],
    )

    exit_code = cli.main()

    assert exit_code == 0
    assert fit_calls[0].fit_max_frequency_points == 320


def test_fit_sparam_cli_auto_preset_respects_explicit_vector_fit_backend(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    fit_calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        fit_calls.append(config)
        return FakeFitResult(FakeQualityReport(status="PASS"))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s30p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--auto-preset",
            "idem-fast",
            "--vector-fit-backend",
            "skrf",
        ]
    )

    assert exit_code == 0
    assert fit_calls[0].vector_fit_backend == "skrf"


def test_fit_sparam_cli_can_skip_passivity_check(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        calls.append(config)
        return FakeFitResult(FakeQualityReport(status="PASS"))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--skip-passivity-check",
        ]
    )

    assert exit_code == 0
    assert calls[0].check_passivity is False


def test_fit_sparam_cli_can_select_native_vector_fit_backend(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        calls.append(config)
        return FakeFitResult(FakeQualityReport(status="PASS"))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--vector-fit-backend",
            "native",
        ]
    )

    assert exit_code == 0
    assert calls[0].vector_fit_backend == "native"


def test_fit_sparam_cli_requires_rms_target(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    monkeypatch.setattr(
        cli,
        "fit_touchstone_to_spice_target",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("target fit must not run")),
        raising=False,
    )

    exit_code = cli.main(
        ["fit-sparam", str(tmp_path / "line.s2p"), "--output", str(tmp_path / "model.sp")]
    )

    assert exit_code == 1


def test_fit_sparam_cli_builds_explicit_target_and_enforce_policy(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_target_fit(touchstone_path, output_path, *, target, config, report_path, html_report_path, log_path):
        calls.append((target, config))
        return SimpleNamespace(target_met=True, selected_trial=SimpleNamespace(payload=None))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice_target", fake_target_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s91p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--rms-target",
            "0.001",
            "--passivity",
            "enforce",
            "--max-order",
            "32",
        ]
    )

    assert exit_code == 0
    target, config = calls[0]
    assert target.mean_rms == pytest.approx(0.001)
    assert target.passivity == "enforce"
    assert target.max_order == 32
    assert config.check_passivity is True
    assert config.enforce_passivity is True
    assert config.fit_max_frequency_points is None


def test_fit_sparam_cli_defaults_to_check_and_large_port_max_order(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_target_fit(touchstone_path, output_path, *, target, config, report_path, html_report_path, log_path):
        calls.append((target, config))
        return SimpleNamespace(target_met=True, selected_trial=SimpleNamespace(payload=None))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice_target", fake_target_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s60p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--rms-target",
            "0.001",
        ]
    )

    assert exit_code == 0
    target, config = calls[0]
    assert target.passivity == "check"
    assert target.max_order == 24
    assert config.check_passivity is True
    assert config.enforce_passivity is False


def test_fit_sparam_cli_uses_native_backend_for_small_port_target_search(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_target_fit(touchstone_path, output_path, *, target, config, report_path, html_report_path, log_path):
        calls.append(config)
        return SimpleNamespace(target_met=True, selected_trial=SimpleNamespace(payload=None))

    monkeypatch.setattr(cli, "fit_touchstone_to_spice_target", fake_target_fit, raising=False)

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--rms-target",
            "0.1",
        ]
    )

    assert exit_code == 0
    assert calls[0].vector_fit_backend == "native"


def test_fit_sparam_cli_returns_failure_when_target_is_not_met(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    monkeypatch.setattr(
        cli,
        "fit_touchstone_to_spice_target",
        lambda *args, **kwargs: SimpleNamespace(target_met=False, selected_trial=None),
        raising=False,
    )

    exit_code = cli.main(
        [
            "fit-sparam",
            str(tmp_path / "line.s2p"),
            "--output",
            str(tmp_path / "model.sp"),
            "--rms-target",
            "0.001",
        ]
    )

    assert exit_code == 1
