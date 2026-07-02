from pathlib import Path


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
