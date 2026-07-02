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
    assert {"comparison_rms_error", "passivity_enforcement"} <= set(payload["blocking_reasons"])


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
