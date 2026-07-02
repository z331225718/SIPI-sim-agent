from pathlib import Path


class FakeQualityReport:
    def __init__(self, status="PASS", blocking_reasons=None, warnings=None):
        self.status = status
        self.blocking_reasons = [] if blocking_reasons is None else blocking_reasons
        self.warnings = [] if warnings is None else warnings


class FakeFitResult:
    def __init__(self, quality_report):
        self.quality_report = quality_report


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
    assert calls[0][2].subckt_name == "pkg_model"
    assert calls[0][2].n_poles_add == 1
    assert calls[0][2].max_iterations == 8
    assert calls[0][2].passivity_samples == 15
    assert calls[0][2].passivity_f_max == 3e9
    assert calls[0][2].fit_frequency_stride == 2
    assert calls[0][2].fit_max_frequency_points == 128
    assert calls[0][2].fit_f_min == 1e6
    assert calls[0][2].fit_f_max == 5e9
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
    assert calls[0][2].enforce_passivity is True


def test_fit_sparam_cli_can_skip_passivity_enforcement(tmp_path: Path, monkeypatch):
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
            "--skip-passivity-enforce",
        ]
    )

    assert exit_code == 0
    assert calls[0][2].enforce_passivity is False


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
