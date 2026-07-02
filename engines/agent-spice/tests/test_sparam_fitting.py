import json
import logging
from pathlib import Path
import re

import pytest

from agent_spice.sparam.fitting import SParamFitConfig, fit_touchstone_to_spice


class FakeVectorFitting:
    instances: list["FakeVectorFitting"] = []

    def __init__(self, network):
        self.network = network
        self.calls: list[str] = []
        self.auto_fit_kwargs = {}
        self.vector_fit_kwargs = {}
        self.max_iterations = 100
        self.enforced = False
        self.model_response_freq_lengths: list[int] = []
        self.instances.append(self)

    def auto_fit(self, **kwargs):
        self.calls.append("auto_fit")
        self.auto_fit_kwargs = kwargs
        logging.getLogger("skrf.vectorFitting").info("fake vector fitting internal progress")
        return None

    def vector_fit(self, **kwargs):
        self.calls.append("vector_fit")
        self.vector_fit_kwargs = kwargs
        return None

    def is_passive(self, parameter_type="s"):
        self.calls.append("is_passive")
        return self.enforced

    def passivity_test(self, parameter_type="s"):
        self.calls.append("passivity_test")
        if self.enforced:
            return []
        return [[1e6, 2e6]]

    def passivity_enforce(self, **kwargs):
        self.calls.append("passivity_enforce")
        self.passivity_enforce_kwargs = kwargs
        self.enforced = True
        return None

    def get_rms_error(self, parameter_type="s"):
        self.calls.append("get_rms_error")
        return 0.125

    def get_model_response(self, i, j, freqs=None):
        self.calls.append("get_model_response")
        freqs = self.network.f if freqs is None else freqs
        self.model_response_freq_lengths.append(len(freqs))
        base_values = [0.10 + 0.01j, 0.20 + 0.02j]
        return [base_values[index % len(base_values)] for index in range(len(freqs))]

    def write_spice_subcircuit_s(self, filename, **kwargs):
        self.calls.append("write_spice_subcircuit_s")
        self.write_spice_kwargs = kwargs
        Path(filename).write_text(".subckt fitted 1 2\n.ends fitted\n", encoding="utf-8")


class FakeNetwork:
    nports = 2
    f = [1e6, 2e6]
    s = [
        [[0.11 + 0.01j, 0.78 - 0.02j], [0.77 - 0.02j, 0.12 + 0.01j]],
        [[0.20 + 0.02j, 0.70 - 0.10j], [0.69 - 0.10j, 0.21 + 0.02j]],
    ]
    z0 = [
        [50 + 0j, 50 + 0j],
        [50 + 0j, 50 + 0j],
    ]

    def __init__(self, path):
        self.path = path


class LegacyVectorFitting:
    instances: list["LegacyVectorFitting"] = []

    def __init__(self, network):
        self.network = network
        self.auto_fit_kwargs = {}
        self.instances.append(self)

    def auto_fit(
        self,
        n_poles_init_real=3,
        n_poles_init_cmplx=3,
        n_poles_add=3,
        model_order_max=100,
        target_error=0.01,
        parameter_type="s",
    ):
        self.auto_fit_kwargs = {
            "n_poles_init_real": n_poles_init_real,
            "n_poles_init_cmplx": n_poles_init_cmplx,
            "n_poles_add": n_poles_add,
            "model_order_max": model_order_max,
            "target_error": target_error,
            "parameter_type": parameter_type,
        }
        return None

    def is_passive(self):
        return True

    def passivity_test(self):
        return []

    def passivity_enforce(self, n_samples=200):
        self.passivity_samples = n_samples
        return None

    def get_rms_error(self):
        return 0.25

    def write_spice_subcircuit_s(self, filename):
        Path(filename).write_text(".subckt legacy 1 2\n.ends legacy\n", encoding="utf-8")


def test_fit_touchstone_to_spice_writes_report_with_auto_fit_summary(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    output = tmp_path / "model.sp"
    report = tmp_path / "fit_report.json"

    result = fit_touchstone_to_spice(tmp_path / "line.s2p", output, report_path=report)

    assert result.spice_path == output
    assert result.report_path == report
    assert result.rms_error == 0.125
    assert result.passive_before_enforce is False
    assert result.passive_after_enforce is True
    assert result.passivity_violations_before == [[1000000.0, 2000000.0]]
    assert result.passivity_violations_after == []
    assert len(FakeVectorFitting.instances) == 1
    assert "auto_fit" in FakeVectorFitting.instances[0].calls
    assert "passivity_enforce" in FakeVectorFitting.instances[0].calls
    assert "write_spice_subcircuit_s" in FakeVectorFitting.instances[0].calls
    assert ".subckt fitted" in output.read_text(encoding="utf-8")

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["touchstone_path"] == str(tmp_path / "line.s2p")
    assert payload["schema_version"] == "0.2"
    assert payload["spice_path"] == str(output)
    assert payload["report_path"] == str(report)
    assert payload["ports"] == 2
    assert payload["frequency_points"] == 2
    assert payload["fit_frequency_points"] == 2
    assert payload["reference_impedance"] == [50.0, 50.0]
    assert payload["config"]["mode"] == "auto"
    assert payload["rms_error"] == 0.125
    assert payload["rms_error_scope"] == "fit_frequency_points"
    assert payload["comparison_rms_error"] is not None
    assert payload["comparison_rms_error_scope"] == "original_frequency_points"
    assert payload["quality"]["status"] == "WARN"
    assert payload["quality"]["allowed_for"] == "report_only"
    assert payload["quality"]["passivity"] == "passive"
    assert {diagnostic["id"] for diagnostic in payload["diagnostics"]} >= {
        "dc_coverage",
        "comparison_rms_error",
        "passivity_after_enforce",
    }


def test_fit_touchstone_to_spice_writes_readable_html_report_with_comparison_plot(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    output = tmp_path / "model.sp"
    report = tmp_path / "fit_report.json"
    html_report = tmp_path / "fit_report.html"

    result = fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        output,
        report_path=report,
        html_report_path=html_report,
    )

    assert result.html_report_path == html_report
    html = html_report.read_text(encoding="utf-8")
    assert "<h1>S-Parameter Fit Report</h1>" in html
    assert "Original vs Fitted" in html
    assert "Fit Sample Selection" in html
    assert "Fit Frequency Points" in html
    assert "Fit-Sample RMS Error" in html
    assert "Original-Point RMS Error" in html
    assert "Quality Gate" in html
    assert "dc_coverage" in html
    assert "RMS Error" in html
    assert "0.125" in html
    assert "S11" in html
    assert "S21" in html
    assert re.search(r"<svg[^>]*>.*</svg>", html, flags=re.DOTALL)
    assert "get_model_response" in FakeVectorFitting.instances[0].calls


def test_fit_touchstone_to_spice_writes_progress_log_and_uses_tuning_options(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    output = tmp_path / "model.sp"
    log_path = tmp_path / "fit.log"
    config = SParamFitConfig(
        n_poles_add=1,
        model_order_max=12,
        target_error=0.2,
        iters_start=1,
        iters_inter=1,
        iters_final=2,
        alpha=0.2,
        gamma=0.4,
        nu_samples=0.5,
        max_iterations=7,
        passivity_samples=17,
        passivity_f_max=2.5e9,
        preserve_dc=False,
    )

    result = fit_touchstone_to_spice(tmp_path / "line.s2p", output, config=config, log_path=log_path)

    instance = FakeVectorFitting.instances[0]
    assert result.log_path == log_path
    assert instance.max_iterations == 7
    assert instance.auto_fit_kwargs["n_poles_add"] == 1
    assert instance.auto_fit_kwargs["iters_start"] == 1
    assert instance.auto_fit_kwargs["iters_inter"] == 1
    assert instance.auto_fit_kwargs["iters_final"] == 2
    assert instance.auto_fit_kwargs["alpha"] == 0.2
    assert instance.auto_fit_kwargs["gamma"] == 0.4
    assert instance.auto_fit_kwargs["nu_samples"] == 0.5
    assert instance.passivity_enforce_kwargs["n_samples"] == 17
    assert instance.passivity_enforce_kwargs["f_max"] == 2.5e9
    assert instance.passivity_enforce_kwargs["preserve_dc"] is False
    log_text = log_path.read_text(encoding="utf-8")
    assert "loading Touchstone" in log_text
    assert "starting vector fit" in log_text
    assert "fake vector fitting internal progress" in log_text
    assert "writing SPICE subcircuit" in log_text
    assert "fit-sparam completed" in log_text


def test_fit_touchstone_to_spice_can_fit_frequency_subset(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    fixture = Path("tests/fixtures/sparam/simple_through.s2p")
    output = tmp_path / "subset.sp"
    report = tmp_path / "fit_report.json"
    html_report = tmp_path / "fit_report.html"

    result = fit_touchstone_to_spice(
        fixture,
        output,
        config=SParamFitConfig(fit_frequency_stride=2, fit_max_frequency_points=2),
        report_path=report,
        html_report_path=html_report,
    )

    fit_network = FakeVectorFitting.instances[0].network
    assert result.frequency_points == 5
    assert result.fit_frequency_points == 2
    assert 5 in FakeVectorFitting.instances[0].model_response_freq_lengths
    assert list(fit_network.f) == [1e6, 5e9]
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["frequency_points"] == 5
    assert payload["fit_frequency_points"] == 2
    assert payload["comparison_rms_error"] is not None
    assert payload["fit_frequency_selection"]["stride"] == 2
    assert payload["fit_frequency_selection"]["max_points"] == 2
    html = html_report.read_text(encoding="utf-8")
    assert "Fit Sample Selection" in html
    assert "Fit frequency points</td><td>2" in html


def test_fit_touchstone_to_spice_rejects_single_frequency_subset(tmp_path: Path):
    fixture = Path("tests/fixtures/sparam/simple_through.s2p")

    with pytest.raises(ValueError, match="at least 2 samples"):
        fit_touchstone_to_spice(
            fixture,
            tmp_path / "subset.sp",
            config=SParamFitConfig(fit_max_frequency_points=1),
        )


def test_manual_fit_uses_vector_fit_parameters(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    config = SParamFitConfig(mode="manual", n_poles_real=4, n_poles_cmplx=5)

    fit_touchstone_to_spice(tmp_path / "line.s2p", tmp_path / "model.sp", config=config)

    instance = FakeVectorFitting.instances[0]
    assert "vector_fit" in instance.calls
    assert "auto_fit" not in instance.calls
    assert instance.vector_fit_kwargs["n_poles_real"] == 4
    assert instance.vector_fit_kwargs["n_poles_cmplx"] == 5


def test_legacy_path_comparison_still_works(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    output = tmp_path / "model.sp"

    result = fit_touchstone_to_spice(tmp_path / "line.s2p", output)

    assert result == output


def test_fit_touchstone_to_spice_supports_legacy_vector_fitting_signature(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    LegacyVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", LegacyVectorFitting)
    output = tmp_path / "legacy.sp"

    result = fit_touchstone_to_spice(tmp_path / "line.s2p", output)

    assert result.spice_path == output
    assert ".subckt legacy" in output.read_text(encoding="utf-8")
    assert LegacyVectorFitting.instances[0].auto_fit_kwargs["parameter_type"] == "s"
    assert result.passive_before_enforce is True


def test_fit_touchstone_to_spice_smoke_with_fixture(tmp_path: Path):
    fixture = Path("tests/fixtures/sparam/simple_through.s2p")
    output = tmp_path / "simple_through.sp"
    report = tmp_path / "fit_report.json"
    html_report = tmp_path / "fit_report.html"

    result = fit_touchstone_to_spice(
        fixture,
        output,
        config=SParamFitConfig(model_order_max=20, target_error=0.05),
        report_path=report,
        html_report_path=html_report,
    )

    assert result.spice_path == output
    assert ".subckt" in output.read_text(encoding="utf-8").lower()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ports"] == 2
    assert payload["frequency_points"] > 0
    assert payload["spice_path"] == str(output)
    assert "<svg" in html_report.read_text(encoding="utf-8")
