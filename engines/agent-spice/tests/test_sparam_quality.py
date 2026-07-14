import numpy as np

from agent_spice.sparam.quality import SCHEMA_VERSION, build_quality_report


class QualityNetwork:
    nports = 2

    def __init__(self, freqs=None, s=None, z0=None):
        self.f = np.array([0.0, 1e6, 2e6] if freqs is None else freqs, dtype=float)
        self.s = np.array(
            [
                [[0.01 + 0.0j, 0.2 + 0.0j], [0.2 + 0.0j, 0.01 + 0.0j]],
                [[0.01 + 0.0j, 0.2 + 0.0j], [0.2 + 0.0j, 0.01 + 0.0j]],
                [[0.01 + 0.0j, 0.2 + 0.0j], [0.2 + 0.0j, 0.01 + 0.0j]],
            ]
            if s is None
            else s
        )
        self.z0 = np.array([[50 + 0j, 50 + 0j], [50 + 0j, 50 + 0j], [50 + 0j, 50 + 0j]] if z0 is None else z0)


def test_build_quality_report_marks_clean_explore_case_pass():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.01,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=True,
        poles=np.array([-1e6 + 0j, -2e6 + 1e6j]),
    )

    payload = report.to_dict()
    assert SCHEMA_VERSION == "0.2"
    assert payload["status"] == "PASS"
    assert payload["allowed_for"] == "tran_candidate"
    assert payload["blocking_reasons"] == []
    assert {diagnostic["id"] for diagnostic in payload["diagnostics"]} >= {
        "frequency_monotonic",
        "dc_coverage",
        "comparison_rms_error",
        "passivity_after_enforce",
        "pole_stability",
    }


def test_build_quality_report_blocks_nonpassive_asymptotic_feedthrough_outside_checked_band():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.01,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=True,
        poles=np.array([-1e6 + 0j]),
        passivity_check_f_max=2e6,
        constant_matrix_sigma=1.0,
    )

    payload = report.to_dict()
    asymptotic = next(item for item in payload["diagnostics"] if item["id"] == "asymptotic_passivity")
    assert payload["status"] == "FAIL"
    assert payload["allowed_for"] == "report_only"
    assert "asymptotic_passivity" in payload["blocking_reasons"]
    assert asymptotic["status"] == "FAIL"
    assert asymptotic["metric"] == 1.0


def test_build_quality_report_warns_for_preview_subset_and_missing_dc():
    report = build_quality_report(
        network=QualityNetwork(freqs=[1e6, 2e6, 3e6]),
        frequency_points=3,
        fit_frequency_points=2,
        comparison_rms_error=0.01,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=True,
        poles=np.array([-1e6 + 0j]),
    )

    payload = report.to_dict()
    assert payload["status"] == "WARN"
    assert payload["allowed_for"] == "report_only"
    assert "dc_coverage" in payload["warnings"]
    assert "fit_frequency_subset" in payload["warnings"]


def test_build_quality_report_requires_dc_when_requested():
    report = build_quality_report(
        network=QualityNetwork(freqs=[1e6, 2e6, 3e6]),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.01,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=True,
        poles=np.array([-1e6 + 0j]),
        require_dc=True,
    )

    payload = report.to_dict()
    assert payload["status"] == "FAIL"
    assert "dc_coverage" in payload["blocking_reasons"]


def test_build_quality_report_signoff_blocks_unknown_metrics():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=None,
        passive_after_enforce=None,
        passivity_violations_after=None,
        enforce_passivity=True,
        poles=None,
        profile="signoff",
    )

    payload = report.to_dict()
    assert payload["status"] == "FAIL"
    assert {"comparison_rms_error", "passivity_after_enforce", "pole_stability"} <= set(payload["blocking_reasons"])


def test_build_quality_report_signoff_blocks_error_threshold_and_skipped_passivity():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.2,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=False,
        poles=np.array([-1e6 + 0j]),
        profile="signoff",
        comparison_rms_limit=0.05,
    )

    payload = report.to_dict()
    assert payload["status"] == "FAIL"
    assert "comparison_rms_error" in payload["blocking_reasons"]
    assert "passivity_enforcement" not in payload["blocking_reasons"]


def test_build_quality_report_signoff_can_use_z_domain_threshold_as_primary_fit_gate():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.2,
        z_comparison_rms_error=0.01,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=True,
        poles=np.array([-1e6 + 0j]),
        profile="signoff",
        comparison_rms_limit=0.05,
        z_comparison_rms_limit=0.05,
        z_required_for_signoff=True,
    )

    payload = report.to_dict()
    assert payload["status"] == "PASS"
    comparison = next(diagnostic for diagnostic in payload["diagnostics"] if diagnostic["id"] == "comparison_rms_error")
    assert comparison["status"] == "PASS"
    assert comparison["severity"] == "warning"
    assert "comparison_rms_error" not in payload["blocking_reasons"]
    assert "z_comparison_rms_error" not in payload["blocking_reasons"]


def test_build_quality_report_signoff_can_use_z_log_magnitude_threshold_as_primary_fit_gate():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.2,
        z_comparison_rms_error=1e6,
        z_log_magnitude_rms_error=0.02,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=True,
        poles=np.array([-1e6 + 0j]),
        profile="signoff",
        comparison_rms_limit=0.05,
        z_log_magnitude_rms_limit=0.05,
        z_required_for_signoff=True,
    )

    payload = report.to_dict()
    assert payload["status"] == "PASS"
    assert "comparison_rms_error" not in payload["blocking_reasons"]
    assert "z_log_magnitude_rms_error" not in payload["blocking_reasons"]
    diagnostic = next(
        diagnostic for diagnostic in payload["diagnostics"] if diagnostic["id"] == "z_log_magnitude_rms_error"
    )
    assert diagnostic["status"] == "PASS"
    assert diagnostic["metric"] == 0.02
    assert diagnostic["threshold"] == 0.05


def test_build_quality_report_signoff_blocks_missing_required_z_domain_metric():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.01,
        z_comparison_rms_error=None,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=True,
        poles=np.array([-1e6 + 0j]),
        profile="signoff",
        z_comparison_rms_limit=0.05,
        z_required_for_signoff=True,
    )

    payload = report.to_dict()
    assert payload["status"] == "FAIL"
    assert "z_comparison_rms_error" in payload["blocking_reasons"]


def test_build_quality_report_signoff_blocks_z_domain_metric_over_limit():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.01,
        z_comparison_rms_error=0.2,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=True,
        poles=np.array([-1e6 + 0j]),
        profile="signoff",
        z_comparison_rms_limit=0.05,
        z_required_for_signoff=True,
    )

    payload = report.to_dict()
    assert payload["status"] == "FAIL"
    assert "z_comparison_rms_error" in payload["blocking_reasons"]


def test_build_quality_report_can_pass_band_limited_passivity_check():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.01,
        passive_after_enforce=False,
        passivity_violations_after=[[2.1e9, 2.2e9]],
        enforce_passivity=False,
        poles=np.array([-1e6 + 0j]),
        profile="signoff",
        passivity_check_f_max=2.0e9,
    )

    payload = report.to_dict()
    assert payload["status"] == "PASS"
    assert payload["allowed_for"] == "ac_only"
    assert payload["blocking_reasons"] == []
    assert payload["warnings"] == []


def test_build_quality_report_band_limited_check_fails_intersecting_violation():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.01,
        passive_after_enforce=False,
        passivity_violations_after=[[1.9e9, 2.1e9]],
        enforce_passivity=False,
        poles=np.array([-1e6 + 0j]),
        profile="signoff",
        passivity_check_f_max=2.0e9,
    )

    payload = report.to_dict()
    assert payload["status"] == "FAIL"
    assert "passivity_violation_bands_after" in payload["blocking_reasons"]


def test_build_quality_report_fails_non_monotonic_and_remaining_passivity():
    report = build_quality_report(
        network=QualityNetwork(freqs=[0.0, 2e6, 1e6]),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=None,
        passive_after_enforce=False,
        passivity_violations_after=[[1e6, 2e6]],
        enforce_passivity=True,
        poles=np.array([1e6 + 0j]),
    )

    payload = report.to_dict()
    assert payload["status"] == "FAIL"
    assert {"frequency_monotonic", "passivity_after_enforce", "passivity_violation_bands_after", "pole_stability"} <= set(
        payload["blocking_reasons"]
    )
