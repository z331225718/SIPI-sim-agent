from pathlib import Path


def test_fit_sparam_cli_passes_explicit_report_path(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None):
        calls.append((touchstone_path, output_path, config, report_path))
        output_path.write_text(".subckt s_equivalent 1 2\n.ends s_equivalent\n", encoding="utf-8")
        report_path.write_text("{}\n", encoding="utf-8")
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
            "--mode",
            "manual",
            "--n-poles-real",
            "4",
            "--n-poles-cmplx",
            "5",
            "--subckt-name",
            "pkg_model",
        ]
    )

    assert exit_code == 0
    assert calls[0][0] == tmp_path / "line.s2p"
    assert calls[0][1] == tmp_path / "model.sp"
    assert calls[0][3] == tmp_path / "fit_report.json"
    assert calls[0][2].mode == "manual"
    assert calls[0][2].n_poles_real == 4
    assert calls[0][2].n_poles_cmplx == 5
    assert calls[0][2].subckt_name == "pkg_model"


def test_fit_sparam_cli_defaults_report_next_to_output(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None):
        calls.append((touchstone_path, output_path, config, report_path))
        output_path.write_text(".subckt s_equivalent 1 2\n.ends s_equivalent\n", encoding="utf-8")
        report_path.write_text("{}\n", encoding="utf-8")
        return output_path

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit, raising=False)

    exit_code = cli.main(["fit-sparam", str(tmp_path / "line.s2p"), "--output", str(tmp_path / "model.sp")])

    assert exit_code == 0
    assert calls[0][3] == tmp_path / "fit_report.json"
    assert calls[0][2].enforce_passivity is True


def test_fit_sparam_cli_can_skip_passivity_enforcement(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None):
        calls.append((touchstone_path, output_path, config, report_path))
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
