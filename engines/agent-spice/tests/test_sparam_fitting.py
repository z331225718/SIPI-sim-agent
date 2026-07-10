import json
import logging
from pathlib import Path
import re
from types import SimpleNamespace

import numpy as np
import pytest

from agent_spice.sparam.fitting import SParamFitConfig, fit_touchstone_to_spice, fit_touchstone_to_spice_auto_order
from agent_spice.sparam.target_fit import SParamFitTarget


def test_passivity_advanced_perturbations_are_experimental_opt_in():
    config = SParamFitConfig()

    assert config.passivity_perturb_constant is False
    assert config.passivity_perturb_poles is False
    assert config.passivity_constant_only_candidates is False
    assert config.passivity_global_damping_fallback is False
    assert config.passivity_global_damping_mode == "uniform"
    assert config.passivity_global_damping_selective_min_frequency == 5e8
    assert config.passivity_global_damping_safety_margin == 1e-5
    assert config.passivity_spectral_projection_fallback is False
    assert config.passivity_spectral_projection_max_delta_norm is None
    assert config.passivity_spectral_projection_max_response_delta_rms is None
    assert config.passivity_spectral_projection_max_sigma_regression == 0.0
    assert config.passivity_spectral_projection_iterations == 1
    assert config.passivity_spectral_projection_reweight_iterations == 0
    assert config.passivity_spectral_projection_max_reference_rms_increase is None
    assert config.passivity_spectral_projection_max_reference_rms_total_increase is None
    assert config.passivity_spectral_projection_max_reference_rms_per_sigma_improvement is None
    assert config.passivity_spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement is None
    assert config.passivity_spectral_projection_late_current_clip_start_iteration == 0
    assert config.passivity_spectral_projection_max_reference_band_sigma_regression is None
    assert config.passivity_spectral_projection_reference_band_holdout_start_iteration == 0
    assert config.passivity_spectral_projection_include_all_reference_violations is False
    assert config.passivity_spectral_projection_weight_mode == "none"
    assert config.passivity_spectral_projection_weight_exponent == 1.0
    assert config.passivity_spectral_projection_active_mode_candidate is False
    assert config.passivity_spectral_projection_active_mode_start_iteration == 0
    assert config.passivity_spectral_projection_non_active_stop_iteration is None
    assert config.passivity_spectral_projection_active_mode_max_responses == 0
    assert config.passivity_spectral_projection_active_mode_singular_modes == 1
    assert config.passivity_spectral_projection_active_mode_band_singular_modes == 1
    assert config.passivity_spectral_projection_active_mode_band_singular_mode_sample_count == 1
    assert config.passivity_spectral_projection_active_mode_solver == "min_norm"
    assert config.passivity_spectral_projection_active_mode_target_margin == 0.0
    assert config.passivity_spectral_projection_active_mode_target_margin_start_iteration == 0
    assert config.passivity_spectral_projection_active_mode_reference_max_points == 0
    assert config.passivity_spectral_projection_active_mode_frequency_selection == "top"
    assert config.passivity_spectral_projection_active_mode_reference_weight == 0.0
    assert config.passivity_spectral_projection_active_mode_reference_weight_mode == "none"
    assert config.passivity_spectral_projection_active_mode_reference_weight_candidates == ()
    assert config.passivity_spectral_projection_active_mode_global_reference_points == 0
    assert config.passivity_spectral_projection_active_mode_max_reference_rms_total_increase is None
    assert config.passivity_spectral_projection_active_mode_extra_scales == ()
    assert config.passivity_spectral_projection_active_mode_extra_scales_min_sigma == 0.0
    assert config.passivity_spectral_projection_current_clip_candidate is False
    assert config.passivity_spectral_projection_current_clip_reference_weight == 0.0
    assert config.passivity_spectral_projection_candidate_reference_max_points == 0
    assert config.passivity_spectral_projection_frequency_selection == "top"
    assert config.passivity_spectral_projection_band_sample_count == 8
    assert config.passivity_spectral_projection_reference_rms_scope == "projection"
    assert config.passivity_spectral_projection_reference_rms_chunk_size == 0
    assert config.passivity_spectral_projection_candidate_selection_metric == "passivity"
    assert config.passivity_spectral_projection_post_damping_selection_start_iteration == 0
    assert config.passivity_spectral_projection_post_damping_max_sigma_regression is None
    assert config.passivity_spectral_projection_mode_screen_candidates == 0
    assert config.passivity_spectral_projection_mode_screen_modes == 2
    assert config.native_effective_order_max is None
    assert config.native_effective_complex_pole_count is None
    assert config.native_effective_order_selection == "frequency_rank"
    assert config.native_effective_order_passivity_weight == 1.0
    assert config.native_post_relocation_effective_order_max is None
    assert config.high_frequency_complex_pair_anchor_bands_hz == ()
    assert config.high_frequency_complex_pair_anchor_strength == 0.0
    assert config.high_frequency_complex_pair_anchor_damping == 0.03
    assert config.native_high_frequency_complex_pair_frequency_gate is False
    assert config.native_high_frequency_residual_injection is False
    assert config.native_high_frequency_residual_injection_lower_fraction == 0.68
    assert config.native_high_frequency_residual_injection_damping == 0.03
    assert config.native_high_frequency_relocation_weight is False
    assert config.native_high_frequency_relocation_weight_lower_fraction == 0.68
    assert config.native_high_frequency_relocation_weight_gain == 2.0
    assert config.native_out_of_band_pole_regularization_weight == 0.0
    assert config.native_out_of_band_pole_regularization_start_fraction == 1.0
    assert config.native_dynamic_edge_c_res_regularization is False
    assert config.native_dynamic_edge_c_res_regularization_base_weight == 0.0
    assert config.native_dynamic_edge_c_res_regularization_start_fraction == 1.0
    assert config.native_dynamic_edge_c_res_regularization_growth_threshold == 1.5
    assert config.native_topology_sweep is False
    assert config.passivity_enforce_rms_target is None


class FakeVectorFitting:
    instances: list["FakeVectorFitting"] = []
    rms_errors: list[float] = []

    def __init__(self, network):
        self.network = network
        self.calls: list[str] = []
        self.auto_fit_kwargs = {}
        self.vector_fit_kwargs = {}
        self.poles = [-1.0 + 0.0j, -2.0 + 3.0j, -4.0 + 0.0j]
        self.constant_coeff = [0.25 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j, 0.5 + 0.0j]
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

    def vector_fit_topology_sweep(self, **kwargs):
        self.calls.append("vector_fit_topology_sweep")
        self.vector_fit_topology_sweep_kwargs = kwargs
        self.topology_sweep_diagnostics = [{"selected": True, "combined_score": 0.25}]
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
        if self.rms_errors:
            return self.rms_errors.pop(0)
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


class FakeNetworkWithExpensiveInternalPassivity(FakeNetwork):
    def is_passive(self):
        raise AssertionError("internal passivity check should be bypassed")


class FakeVectorFittingWithInternalPassivityCheck(FakeVectorFitting):
    def vector_fit(self, **kwargs):
        self.calls.append("vector_fit")
        self.vector_fit_kwargs = kwargs
        self.network.is_passive()
        return None


class FakeVectorFittingWithRelocationBackend(FakeVectorFitting):
    _pole_relocation = staticmethod(lambda: "original")

    def vector_fit(self, **kwargs):
        self.calls.append("vector_fit")
        self.vector_fit_kwargs = kwargs
        self.seen_relocation_backend = self.__class__._pole_relocation
        return None


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


def test_fit_touchstone_to_spice_reports_elapsed_and_mean_rms(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    FakeVectorFitting.rms_errors = [0.2]
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    report = tmp_path / "fit_report.json"

    result = fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        tmp_path / "model.sp",
        config=SParamFitConfig(enforce_passivity=False),
        report_path=report,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert result.comparison_mean_rms_error == pytest.approx(result.comparison_rms_error / 2)
    assert payload["comparison_mean_rms_error"] == pytest.approx(result.comparison_rms_error / 2)
    assert payload["elapsed_seconds"] >= 0.0
    assert payload["peak_memory_mb"] is None or payload["peak_memory_mb"] > 0.0
    assert payload["stored_pole_count"] == 3
    assert payload["real_pole_count"] == 2
    assert payload["complex_pair_count"] == 1
    assert payload["expanded_model_order"] == 4
    assert payload["constant_matrix_sigma"] == pytest.approx(0.5)


def test_fit_skips_enforcement_when_pre_rms_is_above_target(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    report = tmp_path / "fit_report.json"

    result = fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        tmp_path / "model.sp",
        config=SParamFitConfig(
            enforce_passivity=True,
            check_passivity=True,
            passivity_enforce_rms_target=1e-12,
        ),
        report_path=report,
    )

    instance = FakeVectorFitting.instances[0]
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert "passivity_enforce" not in instance.calls
    assert result.passivity_enforcement_skip_reason == "pre_rms_above_target"
    assert result.pre_enforcement_mean_rms_error == pytest.approx(result.comparison_mean_rms_error)
    assert result.fit_seconds >= 0.0
    assert result.check_seconds >= 0.0
    assert result.enforce_seconds == 0.0
    assert payload["passivity_enforcement_skip_reason"] == "pre_rms_above_target"


def test_fit_touchstone_to_spice_can_skip_passivity_checks(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)

    result = fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        tmp_path / "model.sp",
        config=SParamFitConfig(enforce_passivity=False, check_passivity=False),
    )

    instance = FakeVectorFitting.instances[0]
    assert "is_passive" not in instance.calls
    assert "passivity_test" not in instance.calls
    assert result.passive_before_enforce is None
    assert result.passive_after_enforce is None


def test_native_fit_uses_low_memory_passivity_engine_without_idem_exporter(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting
    import agent_spice.sparam.passivity as passivity

    FakeVectorFitting.instances.clear()
    calls: list[tuple[str, object, int | None, float | None, int | None, int | None, dict]] = []

    def fake_create_vector_fitting(network, config):
        return FakeVectorFitting(network)

    def fake_check(vector_fit, *, nports, epsilon, f_max=None):
        calls.append(("check", vector_fit, None, f_max, None, None, {}))
        if len([name for name, *_rest in calls if name == "check"]) == 1:
            return passivity.PassivitySampleReport(
                max_sigma=1.1,
                max_sigma_frequency_hz=1e6,
                violation_bands_hz=[[1e6, 2e6]],
                frequency_points=1,
                chunk_size=1,
            )
        return passivity.PassivitySampleReport(
            max_sigma=1.0,
            max_sigma_frequency_hz=1e6,
            violation_bands_hz=[],
            frequency_points=1,
            chunk_size=1,
        )

    def fake_enforce(
        vector_fit,
        *,
        nports,
        epsilon,
        max_iterations,
        f_max,
        max_violation_samples,
        max_active_variables,
        **kwargs,
    ):
        calls.append(("enforce", vector_fit, max_violation_samples, f_max, max_iterations, max_active_variables, kwargs))
        vector_fit.enforced = True
        vector_fit.passivity_enforcement_diagnostics = [{"active_budget": 123, "accepted": True}]

    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "_create_vector_fitting", fake_create_vector_fitting)
    monkeypatch.setattr(passivity, "check_vector_fit_passivity_hamiltonian", fake_check)
    monkeypatch.setattr(passivity, "enforce_passivity_hamiltonian", fake_enforce)

    result = fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        tmp_path / "model.sp",
        config=SParamFitConfig(
            mode="manual",
            vector_fit_backend="native",
            exporter="skrf",
            check_passivity=True,
            enforce_passivity=True,
            max_iterations=7,
            passivity_samples=17,
            passivity_active_variables=123,
        ),
    )

    assert [name for name, *_rest in calls] == ["check", "enforce", "check"]
    assert calls[1][2] == 17
    assert [call[3] for call in calls] == [2e6, 2e6, 2e6]
    assert calls[1][4] == 1
    assert calls[1][5] == 123
    assert calls[1][6]["spectral_projection_include_all_reference_violations"] is False
    assert calls[1][6]["spectral_projection_weight_mode"] == "none"
    assert calls[1][6]["spectral_projection_weight_exponent"] == 1.0
    assert calls[1][6]["spectral_projection_max_reference_rms_total_increase"] is None
    assert calls[1][6]["spectral_projection_active_mode_candidate"] is False
    assert calls[1][6]["spectral_projection_active_mode_max_responses"] == 0
    assert calls[1][6]["spectral_projection_candidate_reference_max_points"] == 0
    assert calls[1][6]["spectral_projection_frequency_selection"] == "top"
    assert calls[1][6]["spectral_projection_band_sample_count"] == 8
    assert calls[1][6]["spectral_projection_reference_rms_scope"] == "projection"
    assert calls[1][6]["spectral_projection_reference_rms_chunk_size"] == 0
    assert calls[1][6]["spectral_projection_mode_screen_candidates"] == 0
    assert calls[1][6]["spectral_projection_mode_screen_modes"] == 2
    assert "passivity_enforce" not in FakeVectorFitting.instances[0].calls
    assert result.passive_before_enforce is False
    assert result.passive_after_enforce is True
    assert result.passivity_violations_before == [[1e6, 2e6]]
    assert result.passivity_violations_after == []
    assert result.passivity_max_sigma_before == pytest.approx(1.1)
    assert result.passivity_max_sigma_after == pytest.approx(1.0)
    assert result.passivity_enforcement_diagnostics == [{"active_budget": 123, "accepted": True}]


def test_native_fit_enforces_low_memory_passivity_when_checks_are_skipped(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting
    import agent_spice.sparam.passivity as passivity

    FakeVectorFitting.instances.clear()
    calls: list[tuple[str, object, int | None, float | None, int | None, int | None, dict]] = []

    def fake_create_vector_fitting(network, config):
        return FakeVectorFitting(network)

    def fake_check(*args, **kwargs):
        calls.append(("check", args[0], None, kwargs.get("f_max"), None, None, {}))
        return passivity.PassivitySampleReport(
            max_sigma=1.0,
            max_sigma_frequency_hz=1e6,
            violation_bands_hz=[],
            frequency_points=1,
            chunk_size=1,
        )

    def fake_enforce(
        vector_fit,
        *,
        nports,
        epsilon,
        max_iterations,
        f_max,
        max_violation_samples,
        max_active_variables,
        **kwargs,
    ):
        calls.append(("enforce", vector_fit, max_violation_samples, f_max, max_iterations, max_active_variables, kwargs))
        vector_fit.enforced = True

    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "_create_vector_fitting", fake_create_vector_fitting)
    monkeypatch.setattr(passivity, "check_vector_fit_passivity_hamiltonian", fake_check)
    monkeypatch.setattr(passivity, "enforce_passivity_hamiltonian", fake_enforce)

    result = fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        tmp_path / "model.sp",
        config=SParamFitConfig(
            mode="manual",
            vector_fit_backend="native",
            check_passivity=False,
            enforce_passivity=True,
            max_iterations=3,
            passivity_samples=19,
            passivity_active_variables=321,
            passivity_global_damping_mode="selective_pole",
            passivity_global_damping_selective_min_frequency=7.5e8,
            passivity_global_damping_safety_margin=2e-7,
            passivity_spectral_projection_include_all_reference_violations=True,
            passivity_spectral_projection_weight_mode="violation_excess",
            passivity_spectral_projection_weight_exponent=2.0,
            passivity_spectral_projection_max_sigma_regression=1e-4,
            passivity_spectral_projection_reweight_iterations=2,
            passivity_spectral_projection_max_reference_rms_total_increase=0.001,
            passivity_spectral_projection_max_reference_rms_per_sigma_improvement=0.25,
            passivity_spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement=0.05,
            passivity_spectral_projection_late_current_clip_start_iteration=7,
            passivity_spectral_projection_max_reference_band_sigma_regression=0.002,
            passivity_spectral_projection_reference_band_holdout_start_iteration=5,
            passivity_spectral_projection_active_mode_candidate=True,
            passivity_spectral_projection_active_mode_start_iteration=5,
            passivity_spectral_projection_non_active_stop_iteration=8,
            passivity_spectral_projection_active_mode_max_responses=128,
            passivity_spectral_projection_active_mode_singular_modes=3,
            passivity_spectral_projection_active_mode_band_singular_modes=4,
            passivity_spectral_projection_active_mode_band_singular_mode_sample_count=2,
            passivity_spectral_projection_active_mode_solver="minimax_slack",
            passivity_spectral_projection_active_mode_target_margin=0.002,
            passivity_spectral_projection_active_mode_target_margin_start_iteration=7,
            passivity_spectral_projection_active_mode_reference_max_points=96,
            passivity_spectral_projection_active_mode_frequency_selection="reference_bands",
            passivity_spectral_projection_active_mode_reference_weight=2.5,
            passivity_spectral_projection_active_mode_reference_weight_mode="reference_band_equalized",
            passivity_spectral_projection_active_mode_reference_weight_candidates=(0.03, 0.1),
            passivity_spectral_projection_active_mode_global_reference_points=128,
            passivity_spectral_projection_active_mode_max_reference_rms_total_increase=0.0009,
            passivity_spectral_projection_active_mode_extra_scales=(1.25, 1.5),
            passivity_spectral_projection_active_mode_extra_scales_min_sigma=1.001,
            passivity_spectral_projection_current_clip_candidate=True,
            passivity_spectral_projection_current_clip_reference_weight=0.5,
            passivity_spectral_projection_candidate_reference_max_points=64,
            passivity_spectral_projection_frequency_selection="reference_bands",
            passivity_spectral_projection_band_sample_count=4,
            passivity_spectral_projection_reference_rms_scope="candidate_validation",
            passivity_spectral_projection_reference_rms_chunk_size=128,
            passivity_spectral_projection_candidate_selection_metric="post_damping_reference_rms",
            passivity_spectral_projection_post_damping_selection_start_iteration=7,
            passivity_spectral_projection_post_damping_max_sigma_regression=3e-4,
            passivity_spectral_projection_mode_screen_candidates=2,
            passivity_spectral_projection_mode_screen_modes=3,
        ),
    )

    assert [name for name, *_rest in calls] == ["enforce"]
    assert calls[0][2] == 19
    assert calls[0][3] == 2e6
    assert calls[0][4] == 1
    assert calls[0][5] == 321
    assert calls[0][6]["global_damping_mode"] == "selective_pole"
    assert calls[0][6]["global_damping_selective_min_frequency"] == 7.5e8
    assert calls[0][6]["global_damping_safety_margin"] == 2e-7
    assert calls[0][6]["spectral_projection_include_all_reference_violations"] is True
    assert calls[0][6]["spectral_projection_weight_mode"] == "violation_excess"
    assert calls[0][6]["spectral_projection_weight_exponent"] == 2.0
    assert calls[0][6]["spectral_projection_max_sigma_regression"] == 1e-4
    assert calls[0][6]["spectral_projection_reweight_iterations"] == 2
    assert calls[0][6]["spectral_projection_max_reference_rms_total_increase"] == 0.001
    assert calls[0][6]["spectral_projection_max_reference_rms_per_sigma_improvement"] == 0.25
    assert calls[0][6]["spectral_projection_late_current_clip_max_reference_rms_per_sigma_improvement"] == 0.05
    assert calls[0][6]["spectral_projection_late_current_clip_start_iteration"] == 7
    assert calls[0][6]["spectral_projection_max_reference_band_sigma_regression"] == 0.002
    assert calls[0][6]["spectral_projection_reference_band_holdout_start_iteration"] == 5
    assert calls[0][6]["spectral_projection_active_mode_candidate"] is True
    assert calls[0][6]["spectral_projection_active_mode_start_iteration"] == 5
    assert calls[0][6]["spectral_projection_non_active_stop_iteration"] == 8
    assert calls[0][6]["spectral_projection_active_mode_max_responses"] == 128
    assert calls[0][6]["spectral_projection_active_mode_singular_modes"] == 3
    assert calls[0][6]["spectral_projection_active_mode_band_singular_modes"] == 4
    assert calls[0][6]["spectral_projection_active_mode_band_singular_mode_sample_count"] == 2
    assert calls[0][6]["spectral_projection_active_mode_solver"] == "minimax_slack"
    assert calls[0][6]["spectral_projection_active_mode_target_margin"] == 0.002
    assert calls[0][6]["spectral_projection_active_mode_target_margin_start_iteration"] == 7
    assert calls[0][6]["spectral_projection_active_mode_reference_max_points"] == 96
    assert calls[0][6]["spectral_projection_active_mode_frequency_selection"] == "reference_bands"
    assert calls[0][6]["spectral_projection_active_mode_reference_weight"] == 2.5
    assert calls[0][6]["spectral_projection_active_mode_reference_weight_mode"] == "reference_band_equalized"
    assert calls[0][6]["spectral_projection_active_mode_reference_weight_candidates"] == (0.03, 0.1)
    assert calls[0][6]["spectral_projection_active_mode_global_reference_points"] == 128
    assert calls[0][6]["spectral_projection_active_mode_max_reference_rms_total_increase"] == 0.0009
    assert calls[0][6]["spectral_projection_active_mode_extra_scales"] == (1.25, 1.5)
    assert calls[0][6]["spectral_projection_active_mode_extra_scales_min_sigma"] == 1.001
    assert calls[0][6]["spectral_projection_current_clip_candidate"] is True
    assert calls[0][6]["spectral_projection_current_clip_reference_weight"] == 0.5
    assert calls[0][6]["spectral_projection_candidate_reference_max_points"] == 64
    assert calls[0][6]["spectral_projection_frequency_selection"] == "reference_bands"
    assert calls[0][6]["spectral_projection_band_sample_count"] == 4
    assert calls[0][6]["spectral_projection_reference_rms_scope"] == "candidate_validation"
    assert calls[0][6]["spectral_projection_reference_rms_chunk_size"] == 128
    assert calls[0][6]["spectral_projection_candidate_selection_metric"] == "post_damping_reference_rms"
    assert calls[0][6]["spectral_projection_post_damping_selection_start_iteration"] == 7
    assert calls[0][6]["spectral_projection_post_damping_max_sigma_regression"] == 3e-4
    assert calls[0][6]["spectral_projection_mode_screen_candidates"] == 2
    assert calls[0][6]["spectral_projection_mode_screen_modes"] == 3
    assert "passivity_enforce" not in FakeVectorFitting.instances[0].calls
    assert result.passive_before_enforce is None
    assert result.passive_after_enforce is None


def test_manual_fit_bypasses_skrf_internal_passivity_warning_check_when_checks_are_skipped(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFittingWithInternalPassivityCheck.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetworkWithExpensiveInternalPassivity)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFittingWithInternalPassivityCheck)

    result = fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        tmp_path / "model.sp",
        config=SParamFitConfig(mode="manual", enforce_passivity=False, check_passivity=False),
    )

    assert result.spice_path == tmp_path / "model.sp"


def test_fit_touchstone_to_spice_can_use_streaming_relocation_backend(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFittingWithRelocationBackend.instances.clear()
    original = FakeVectorFittingWithRelocationBackend._pole_relocation
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFittingWithRelocationBackend)

    result = fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        tmp_path / "model.sp",
        config=SParamFitConfig(
            mode="manual",
            enforce_passivity=False,
            check_passivity=False,
            relocation_backend="streaming",
        ),
    )

    instance = FakeVectorFittingWithRelocationBackend.instances[0]
    assert result.spice_path == tmp_path / "model.sp"
    assert instance.seen_relocation_backend is not original
    assert FakeVectorFittingWithRelocationBackend._pole_relocation is original


def test_fit_touchstone_to_spice_can_use_streaming_lowmem_relocation_backend(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting
    from agent_spice.sparam.skrf_streaming import streaming_lowmem_pole_relocation

    FakeVectorFittingWithRelocationBackend.instances.clear()
    original = FakeVectorFittingWithRelocationBackend._pole_relocation
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFittingWithRelocationBackend)

    fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        tmp_path / "model.sp",
        config=SParamFitConfig(
            mode="manual",
            enforce_passivity=False,
            check_passivity=False,
            relocation_backend="streaming-lowmem",
        ),
    )

    instance = FakeVectorFittingWithRelocationBackend.instances[0]
    assert instance.seen_relocation_backend is streaming_lowmem_pole_relocation
    assert FakeVectorFittingWithRelocationBackend._pole_relocation is original


def test_fit_touchstone_to_spice_can_use_streaming_reciprocal_relocation_backend(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting
    from agent_spice.sparam.skrf_streaming import streaming_reciprocal_pole_relocation

    FakeVectorFittingWithRelocationBackend.instances.clear()
    original = FakeVectorFittingWithRelocationBackend._pole_relocation
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFittingWithRelocationBackend)

    fit_touchstone_to_spice(
        tmp_path / "line.s2p",
        tmp_path / "model.sp",
        config=SParamFitConfig(
            mode="manual",
            enforce_passivity=False,
            check_passivity=False,
            relocation_backend="streaming-reciprocal",
        ),
    )

    instance = FakeVectorFittingWithRelocationBackend.instances[0]
    assert instance.seen_relocation_backend is streaming_reciprocal_pole_relocation
    assert FakeVectorFittingWithRelocationBackend._pole_relocation is original


def test_fit_touchstone_to_spice_auto_order_stops_at_first_mean_rms_target(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None, html_report_path=None, log_path=None):
        calls.append(config.model_order_max)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"* order {config.model_order_max}\n", encoding="utf-8")
        mean = {40: 0.003, 60: 0.0019, 80: 0.0015}[config.model_order_max]
        return fitting.SParamFitResult(
            touchstone_path=touchstone_path,
            spice_path=output_path,
            report_path=report_path,
            html_report_path=html_report_path,
            log_path=log_path,
            ports=30,
            frequency_points=10,
            frequency_range_hz=[1.0, 2.0],
            fit_frequency_points=10,
            fit_frequency_range_hz=[1.0, 2.0],
            fit_frequency_selection={},
            reference_impedance=[50.0] * 30,
            config=config,
            rms_error=mean * 30,
            comparison_rms_error=mean * 30,
            passive_before_enforce=None,
            passive_after_enforce=None,
            passivity_violations_before=None,
            passivity_violations_after=None,
            quality_report=type(
                "Q",
                (),
                {
                    "status": "PASS",
                    "blocking_reasons": [],
                    "warnings": [],
                        "to_dict": lambda self: {
                            "status": "PASS",
                            "blocking_reasons": [],
                            "warnings": [],
                            "diagnostics": {},
                        },
                },
            )(),
            comparison_mean_rms_error=mean,
            elapsed_seconds=0.1,
            peak_memory_mb=12.0,
        )

    monkeypatch.setattr(fitting, "fit_touchstone_to_spice", fake_fit)
    report = tmp_path / "auto_report.json"

    result = fit_touchstone_to_spice_auto_order(
        tmp_path / "line.s30p",
        tmp_path / "model.sp",
        config=SParamFitConfig(enforce_passivity=False),
        order_candidates=[40, 60, 80],
        target_mean_rms_error=0.002,
        report_path=report,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert calls == [40, 60]
    assert result.auto_model_order_selected == 60
    assert payload["auto_model_order_selected"] == 60
    assert payload["auto_model_order_stop_reason"] == "target_met"
    assert [trial["order"] for trial in payload["auto_model_order_trials"]] == [40, 60]
    assert (tmp_path / "model.sp").read_text(encoding="utf-8") == "* order 60\n"


@pytest.mark.parametrize(
    ("order", "real_count", "complex_count"),
    [(4, 0, 2), (5, 1, 2), (6, 2, 2), (8, 4, 2), (10, 6, 2)],
)
def test_native_manual_auto_order_requests_exact_effective_order(order, real_count, complex_count):
    import agent_spice.sparam.fitting as fitting

    base = SParamFitConfig(
        mode="manual",
        vector_fit_backend="native",
        high_frequency_complex_pair_count=2,
        n_poles_real=0,
        n_poles_cmplx=2,
    )

    trial = fitting._native_manual_auto_order_config(base, order)

    assert (trial.n_poles_real, trial.n_poles_cmplx) == (real_count, complex_count)
    assert trial.native_post_relocation_effective_order_max == order
    assert trial.native_effective_complex_pole_count == complex_count


def _fake_target_fit_result(output_path: Path, order: int, *, target_met: bool):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"* order {order}\n", encoding="utf-8")
    result = SimpleNamespace(
        spice_path=output_path,
        expanded_model_order=order,
        fit_frequency_points=611,
        frequency_points=611,
        pre_enforcement_mean_rms_error=0.0008 if target_met else 0.002,
        comparison_mean_rms_error=0.0009 if target_met else 0.002,
        passivity_max_sigma_before=1.01,
        passivity_max_sigma_after=0.999 if target_met else 1.01,
        passive_after_enforce=target_met,
        fit_seconds=1.0,
        check_seconds=0.2,
        enforce_seconds=0.3,
        elapsed_seconds=1.5,
        peak_memory_mb=20.0,
        real_pole_count=max(0, order - 4),
        complex_pair_count=2,
        stored_pole_count=max(0, order - 4) + 2,
        passivity_enforcement_skip_reason=None,
    )
    result.to_dict = lambda: {
        "spice_path": str(output_path),
        "comparison_mean_rms_error": result.comparison_mean_rms_error,
        "expanded_model_order": order,
    }
    return result


def test_target_fit_search_writes_only_selected_model(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    calls = []

    def fake_fit(touchstone_path, output_path, *, config, report_path, html_report_path, log_path):
        order = config.model_order_max
        calls.append(order)
        return _fake_target_fit_result(output_path, order, target_met=order >= 8)

    monkeypatch.setattr(fitting, "fit_touchstone_to_spice", fake_fit)
    output = tmp_path / "model.sp"
    report = tmp_path / "report.json"
    html = tmp_path / "report.html"

    result = fitting.fit_touchstone_to_spice_target(
        tmp_path / "line.s91p",
        output,
        target=SParamFitTarget(0.001, passivity="enforce", max_order=10),
        config=SParamFitConfig(mode="manual", vector_fit_backend="native", high_frequency_complex_pair_count=2),
        report_path=report,
        html_report_path=html,
    )

    assert calls == [4, 6, 8, 7]
    assert result.target_met is True
    assert result.selected_trial is not None
    assert result.selected_trial.requested_order == 8
    assert output.read_text(encoding="utf-8") == "* order 8\n"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["rms_target"] == pytest.approx(0.001)
    assert payload["passivity_policy"] == "enforce"
    assert payload["selected_effective_order"] == 8
    assert payload["benchmark_contract_version"] == "sparam_target_v1"
    assert payload["spice_path"] == str(output)
    assert payload["report_path"] == str(report)
    assert payload["html_report_path"] == str(html)
    assert html.exists()


def test_target_fit_failure_removes_requested_output_and_keeps_reports(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    def fake_fit(touchstone_path, output_path, *, config, report_path, html_report_path, log_path):
        return _fake_target_fit_result(output_path, config.model_order_max, target_met=False)

    monkeypatch.setattr(fitting, "fit_touchstone_to_spice", fake_fit)
    output = tmp_path / "model.sp"
    output.write_text("stale", encoding="utf-8")
    report = tmp_path / "report.json"
    html = tmp_path / "report.html"

    result = fitting.fit_touchstone_to_spice_target(
        tmp_path / "line.s91p",
        output,
        target=SParamFitTarget(0.001, passivity="check", max_order=6),
        config=SParamFitConfig(mode="manual", vector_fit_backend="native", high_frequency_complex_pair_count=2),
        report_path=report,
        html_report_path=html,
    )

    assert result.target_met is False
    assert result.stop_reason == "target_not_met_before_max_order"
    assert not output.exists()
    assert json.loads(report.read_text(encoding="utf-8"))["target_met"] is False
    assert html.exists()


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


def test_lightweight_s_network_preserves_lightweight_frequency_subset():
    from agent_spice.sparam.fitting import _LightweightSNetwork, _select_fit_network

    network = _LightweightSNetwork(
        f=np.array([0.0, 1.0e6, 2.0e6, 3.0e6, 4.0e6]),
        s=np.arange(5 * 2 * 2, dtype=float).reshape(5, 2, 2).astype(complex),
        z0=np.full((5, 2), 50.0),
        name="light",
    )

    selected = _select_fit_network(network, SParamFitConfig(fit_max_frequency_points=3))

    assert isinstance(selected, _LightweightSNetwork)
    assert selected.name == "light_fit_subset"
    assert selected.nports == 2
    assert selected.frequency is selected
    assert selected.f.tolist() == [0.0, 2.0e6, 4.0e6]
    np.testing.assert_allclose(selected.s, network.s[[0, 2, 4]])
    np.testing.assert_allclose(selected.z0, network.z0[[0, 2, 4]])


def test_lightweight_touchstone_loader_reads_hz_s_ri_fixture():
    from agent_spice.sparam.fitting import _load_touchstone_s_ri_lightweight

    network = _load_touchstone_s_ri_lightweight(Path("tests/fixtures/sparam/simple_through.s2p"))

    assert network.nports == 2
    assert network.f.tolist() == [1e6, 1e7, 1e8, 1e9, 5e9]
    np.testing.assert_allclose(network.z0, np.full((5, 2), 50.0))
    np.testing.assert_allclose(
        network.s[0],
        np.array(
            [
                [0.01 + 0.0j, 0.799999 - 0.000800j],
                [0.799999 - 0.000800j, 0.01 + 0.0j],
            ]
        ),
    )


def test_lightweight_touchstone_loader_reads_multiline_nport_block(tmp_path: Path):
    from agent_spice.sparam.fitting import _load_touchstone_s_ri_lightweight

    touchstone = tmp_path / "multi.s3p"
    touchstone.write_text(
        "\n".join(
            [
                "! multiline block",
                "# Hz S RI R 0.1",
                "1e6 1 0 2 0 3 0",
                "4 0 5 0 6 0",
                "7 0 8 0 9 0",
            ]
        ),
        encoding="utf-8",
    )

    network = _load_touchstone_s_ri_lightweight(touchstone)

    assert network.nports == 3
    assert network.f.tolist() == [1e6]
    np.testing.assert_allclose(network.z0, np.full((1, 3), 0.1))
    np.testing.assert_allclose(
        network.s[0],
        np.array(
            [
                [1, 2, 3],
                [4, 5, 6],
                [7, 8, 9],
            ],
            dtype=complex,
        ),
    )


def test_fit_touchstone_to_spice_lightweight_path_bypasses_skrf_network_loader(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)

    def fail_network(*args, **kwargs):
        raise AssertionError("lightweight path should not construct skrf.Network")

    monkeypatch.setattr(fitting.rf, "Network", fail_network)

    result = fit_touchstone_to_spice(
        Path("tests/fixtures/sparam/simple_through.s2p"),
        tmp_path / "model.sp",
        config=SParamFitConfig(
            mode="manual",
            check_passivity=False,
            enforce_passivity=False,
            use_lightweight_network=True,
        ),
    )

    assert result.spice_path == tmp_path / "model.sp"
    assert FakeVectorFitting.instances[0].network.nports == 2


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


def test_manual_fit_uses_topology_sweep_only_when_opted_in(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    report = tmp_path / "fit_report.json"
    config = SParamFitConfig(
        mode="manual",
        native_topology_sweep=True,
        n_poles_real=4,
        n_poles_cmplx=2,
        high_frequency_complex_pair_count=2,
    )

    result = fit_touchstone_to_spice(tmp_path / "line.s2p", tmp_path / "model.sp", config=config, report_path=report)

    instance = FakeVectorFitting.instances[0]
    assert "vector_fit_topology_sweep" in instance.calls
    assert "vector_fit" not in instance.calls
    assert instance.vector_fit_topology_sweep_kwargs["candidate_configs"][0]["n_poles_real"] == 4
    assert instance.vector_fit_topology_sweep_kwargs["candidate_configs"][0]["n_poles_cmplx"] == 2
    assert result.topology_sweep_diagnostics == [{"selected": True, "combined_score": 0.25}]
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["topology_sweep_diagnostics"] == [{"selected": True, "combined_score": 0.25}]


def test_create_native_vector_fitting_applies_high_frequency_complex_pair_options():
    import agent_spice.sparam.fitting as fitting

    config = SParamFitConfig(
        vector_fit_backend="native",
        high_frequency_complex_pair_count=2,
        high_frequency_complex_pair_damping=0.05,
        high_frequency_complex_pair_lower_fraction=0.7,
    )

    vector_fit = fitting._create_vector_fitting(FakeNetwork("line.s2p"), config)

    assert vector_fit.high_frequency_complex_pair_count == 2
    assert vector_fit.high_frequency_complex_pair_damping == 0.05
    assert vector_fit.high_frequency_complex_pair_lower_fraction == 0.7


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


def test_fit_touchstone_to_spice_with_idem_exporter(tmp_path: Path):
    fixture = Path("tests/fixtures/sparam/simple_through.s2p")
    output = tmp_path / "simple_through_idem.sp"
    report = tmp_path / "fit_report_idem.json"
    html_report = tmp_path / "fit_report_idem.html"

    result = fit_touchstone_to_spice(
        fixture,
        output,
        config=SParamFitConfig(
            model_order_max=20,
            target_error=0.05,
            exporter="idem",
            enforce_passivity=True,
        ),
        report_path=report,
        html_report_path=html_report,
    )

    assert result.spice_path == output
    content = output.read_text(encoding="utf-8")
    assert ".subckt s_equivalent" in content
    assert "** STATE-SPACE REALIZATION" in content
    assert "CS_" in content
    assert "RS_" in content
    assert "GS_" in content
