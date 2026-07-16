from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from agent_spice.sparam.artifacts import evaluate_fitted_y, write_spice_subcircuit_y
from agent_spice.sparam.native_vf import NativeVectorFitting
from agent_spice.sparam.yparam import (
    YParamFitConfig,
    convert_y_to_s_strict,
    fit_touchstone_to_y_spice,
    fit_touchstone_to_y_spice_auto_order,
)


def _write_y_touchstone(path: Path, frequencies: np.ndarray, y: np.ndarray) -> Path:
    import skrf as rf

    network = rf.Network(frequency=rf.Frequency.from_f(frequencies, unit="hz"), y=y, z0=50, name=path.stem)
    network.write_touchstone(str(path.with_suffix("")))
    return path


def test_native_vector_fit_uses_y_matrix_and_reports_y_rms() -> None:
    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    y = 0.02 + 2j * np.pi * frequencies[:, None, None] * 1.0e-9
    network = SimpleNamespace(f=frequencies, nports=1, y=y, s=np.zeros_like(y))
    fit = NativeVectorFitting(network)

    fit.vector_fit(n_poles_real=1, n_poles_cmplx=1, parameter_type="y", fit_proportional=True)

    assert fit.get_rms_error("y") < 1e-8
    assert fit.get_rms_error("s") > 1e-4


def test_fit_yparam_writes_y_report_and_checks_positive_real_rc(tmp_path: Path) -> None:
    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7, 2.0e7, 5.0e7])
    y = 0.02 + 2j * np.pi * frequencies[:, None, None] * 1.0e-9
    touchstone = _write_y_touchstone(tmp_path / "rc.s1p", frequencies, y)
    report = tmp_path / "rc.y.json"

    result = fit_touchstone_to_y_spice(
        touchstone,
        tmp_path / "rc.y.sp",
        config=YParamFitConfig(n_poles_real=1, n_poles_cmplx=1, max_iterations=8, max_y_rms_siemens=1e-6),
        report_path=report,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert result.target_met is True
    assert result.y_rms_siemens < 1e-6
    assert payload["parameter_type"] == "y"
    assert payload["response_unit"] == "siemens"
    assert payload["passivity"]["min_eigenvalue"] > 0.0
    assert payload["passivity"]["constant_hermitian_min_eigenvalue"] > 0.0
    assert payload["fit_proportional"] is True
    assert payload["s_to_y_conversion"]["matrix"] == "I+S"
    assert payload["z_log_magnitude_rms_error"] < 1e-8
    assert payload["fitted_y_condition_max"] is not None
    assert "Fy1_1" in (tmp_path / "rc.y.sp").read_text(encoding="ascii")


def test_fit_yparam_flushes_progress_log_while_vector_fit_runs(tmp_path: Path, monkeypatch) -> None:
    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    touchstone = _write_y_touchstone(
        tmp_path / "progress.s1p",
        frequencies,
        np.full((4, 1, 1), 0.02 + 0j),
    )
    log_path = tmp_path / "progress.y.log"
    original_vector_fit = NativeVectorFitting.vector_fit
    observed_during_fit: dict[str, bool] = {}

    def inspect_log_then_fit(self, *args, **kwargs):
        log_text = log_path.read_text(encoding="utf-8")
        observed_during_fit["created"] = log_path.is_file()
        observed_during_fit["loading"] = "loading Touchstone" in log_text
        observed_during_fit["started"] = "starting vector fit" in log_text
        return original_vector_fit(self, *args, **kwargs)

    monkeypatch.setattr(NativeVectorFitting, "vector_fit", inspect_log_then_fit)

    fit_touchstone_to_y_spice(
        touchstone,
        tmp_path / "progress.y.sp",
        config=YParamFitConfig(n_poles_real=1, n_poles_cmplx=1, max_iterations=3),
        log_path=log_path,
    )

    assert observed_during_fit == {"created": True, "loading": True, "started": True}
    log_text = log_path.read_text(encoding="utf-8")
    assert "vector-fit iteration=1/3" in log_text
    assert "Y error evaluated" in log_text
    assert "sampled Y positive-real check finished" in log_text
    assert "writing Y-domain SPICE subcircuit" in log_text
    assert "fit-yparam completed" in log_text


def test_fit_yparam_preserves_progress_log_when_vector_fit_fails(tmp_path: Path, monkeypatch) -> None:
    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    touchstone = _write_y_touchstone(
        tmp_path / "failure.s1p",
        frequencies,
        np.full((4, 1, 1), 0.02 + 0j),
    )
    log_path = tmp_path / "failure.y.log"

    def fail_vector_fit(self, *args, **kwargs):
        assert "starting vector fit" in log_path.read_text(encoding="utf-8")
        raise RuntimeError("intentional vector-fit failure")

    monkeypatch.setattr(NativeVectorFitting, "vector_fit", fail_vector_fit)

    with pytest.raises(RuntimeError, match="intentional vector-fit failure"):
        fit_touchstone_to_y_spice(
            touchstone,
            tmp_path / "failure.y.sp",
            config=YParamFitConfig(n_poles_real=1, n_poles_cmplx=1, max_iterations=3),
            log_path=log_path,
        )

    log_text = log_path.read_text(encoding="utf-8")
    assert "fit-yparam failed" in log_text
    assert "intentional vector-fit failure" in log_text


def test_fit_yparam_auto_order_increases_until_target_passes(tmp_path: Path, monkeypatch) -> None:
    import agent_spice.sparam.yparam as yparam_module

    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    touchstone = _write_y_touchstone(
        tmp_path / "auto.s1p",
        frequencies,
        np.full((4, 1, 1), 0.02 + 0j),
    )
    report_path = tmp_path / "auto.y.json"
    log_path = tmp_path / "auto.y.log"
    attempted_orders: list[int] = []
    original_impl = yparam_module._fit_touchstone_to_y_spice_impl

    def controlled_target(*args, **kwargs):
        result = original_impl(*args, **kwargs)
        order = result.config.n_poles_real + 2 * result.config.n_poles_cmplx
        attempted_orders.append(order)
        return replace(result, target_met=order >= 5)

    monkeypatch.setattr(yparam_module, "_fit_touchstone_to_y_spice_impl", controlled_target)

    result = fit_touchstone_to_y_spice_auto_order(
        touchstone,
        tmp_path / "auto.y.sp",
        config=YParamFitConfig(
            n_poles_real=1,
            n_poles_cmplx=1,
            max_iterations=3,
            passivity="off",
        ),
        max_order=9,
        order_step=2,
        report_path=report_path,
        log_path=log_path,
    )

    assert attempted_orders == [3, 5]
    assert result.target_met is True
    assert (tmp_path / "auto.y.sp").is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["order_search"]["selected_order"] == 5
    assert [trial["requested_order"] for trial in payload["order_search"]["trials"]] == [3, 5]
    log_text = log_path.read_text(encoding="utf-8")
    assert "Y order trial started: requested_order=3" in log_text
    assert "Y order trial started: requested_order=5" in log_text
    assert "Y order trial started: requested_order=7" not in log_text


def test_fit_yparam_can_export_y_derived_s_touchstone(tmp_path: Path) -> None:
    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7, 2.0e7, 5.0e7])
    y = 0.02 + 2j * np.pi * frequencies[:, None, None] * 1.0e-9
    touchstone = _write_y_touchstone(tmp_path / "rc.s1p", frequencies, y)
    derived_s = tmp_path / "rc.y-derived.s1p"
    report = tmp_path / "rc.y.json"

    fit_touchstone_to_y_spice(
        touchstone,
        tmp_path / "rc.y.sp",
        config=YParamFitConfig(n_poles_real=1, n_poles_cmplx=1, max_iterations=8),
        report_path=report,
        derived_s_touchstone_path=derived_s,
    )

    import skrf as rf

    exported = rf.Network(str(derived_s))
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert derived_s.is_file()
    np.testing.assert_allclose(exported.s, rf.Network(str(touchstone)).s, rtol=1e-6, atol=1e-8)
    assert payload["y_derived_s"]["rms_error_against_input"] < 1e-8
    assert payload["y_derived_s"]["condition_max"] > 0.0


def test_fit_yparam_can_disable_proportional_term(tmp_path: Path) -> None:
    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    touchstone = _write_y_touchstone(tmp_path / "conductance.s1p", frequencies, np.full((4, 1, 1), 0.02 + 0j))

    result = fit_touchstone_to_y_spice(
        touchstone,
        tmp_path / "conductance.y.sp",
        config=YParamFitConfig(n_poles_real=1, n_poles_cmplx=1, max_iterations=8, fit_proportional=False),
    )

    assert result.to_dict()["fit_proportional"] is False


def test_convert_y_to_s_rejects_ill_conditioned_mapping() -> None:
    with pytest.raises(ValueError, match="ill-conditioned"):
        convert_y_to_s_strict(np.array([[[-0.02 + 0j]]]), 50.0, condition_limit=1e6)


def test_fit_yparam_reports_non_positive_real_negative_conductance(tmp_path: Path) -> None:
    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    touchstone = _write_y_touchstone(tmp_path / "negative.s1p", frequencies, np.full((4, 1, 1), -0.01 + 0j))

    result = fit_touchstone_to_y_spice(
        touchstone,
        tmp_path / "negative.y.sp",
        config=YParamFitConfig(n_poles_real=1, n_poles_cmplx=1, max_iterations=8),
    )

    assert result.passivity_min_eigenvalue is not None
    assert result.passivity_min_eigenvalue < 0.0
    assert result.passivity_violation_count and result.passivity_violation_count > 0
    assert result.target_met is False


def test_fit_yparam_rejects_ill_conditioned_s_to_y_conversion(tmp_path: Path) -> None:
    import skrf as rf

    frequencies = np.array([1.0e6, 2.0e6])
    network = rf.Network(frequency=rf.Frequency.from_f(frequencies, unit="hz"), s=np.full((2, 1, 1), -1.0 + 0j), z0=50)
    touchstone = tmp_path / "singular.s1p"
    network.write_touchstone(str(touchstone.with_suffix("")))

    with pytest.raises(ValueError, match="ill-conditioned"):
        fit_touchstone_to_y_spice(touchstone, tmp_path / "singular.y.sp")


def test_fit_yparam_cli_writes_default_y_artifacts(tmp_path: Path) -> None:
    from agent_spice import cli

    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    touchstone = _write_y_touchstone(tmp_path / "line.s1p", frequencies, np.full((4, 1, 1), 0.02 + 0j))

    exit_code = cli.main([
        "fit-yparam", str(touchstone), "--n-poles-real", "1", "--n-poles-cmplx", "1", "--fit-iterations", "8",
        "--max-y-rms-siemens", "1e-6", "--derived-s-touchstone", str(tmp_path / "line.y-derived.s1p"),
    ])

    assert exit_code == 0
    assert (tmp_path / "line_fitted.y.sp").is_file()
    assert (tmp_path / "line_fitted.y.json").is_file()
    assert (tmp_path / "line_fitted.y.html").is_file()
    assert "fit-yparam completed" in (tmp_path / "line_fitted.y.log").read_text(encoding="utf-8")
    assert (tmp_path / "line.y-derived.s1p").is_file()
    payload = json.loads((tmp_path / "line_fitted.y.json").read_text(encoding="utf-8"))
    assert payload["order_search"]["target_met"] is True
    assert len(payload["order_search"]["trials"]) == 1


def test_fit_yparam_cli_fails_positive_real_check(tmp_path: Path) -> None:
    from agent_spice import cli

    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    touchstone = _write_y_touchstone(tmp_path / "negative_cli.s1p", frequencies, np.full((4, 1, 1), -0.01 + 0j))

    report_path = tmp_path / "negative_cli.y.json"
    assert cli.main([
        "fit-yparam", str(touchstone), "--n-poles-real", "1", "--n-poles-cmplx", "1",
        "--fit-iterations", "8", "--max-order", "7", "--order-step", "2",
        "--report", str(report_path),
    ]) == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["order_search"]["target_met"] is False
    assert [trial["requested_order"] for trial in payload["order_search"]["trials"]] == [3, 5, 7]


def test_fit_yparam_cli_exports_kyp_enforced_exact_s_rfm(tmp_path: Path) -> None:
    from agent_spice import cli

    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    touchstone = _write_y_touchstone(tmp_path / "passive.s1p", frequencies, np.full((4, 1, 1), 0.02 + 0j))
    rfm = tmp_path / "passive.exact.rfm"
    report = tmp_path / "passive.y.json"
    log_path = tmp_path / "passive.y.log"

    assert cli.main([
        "fit-yparam", str(touchstone), "--output", str(tmp_path / "passive.y.sp"), "--report", str(report),
        "--log", str(log_path),
        "--n-poles-real", "1", "--n-poles-cmplx", "1", "--fit-iterations", "8", "--no-fit-proportional",
        "--exact-s-rfm", str(rfm),
    ]) == 0

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert rfm.is_file()
    assert payload["passivity"]["enforcement"] == "KYP continuous-frequency certificate"
    assert payload["exact_y_to_s"]["method"] == "state-space rational LFT; no sampled S refit"
    log_text = log_path.read_text(encoding="utf-8")
    assert "starting KYP Y positive-real enforcement" in log_text
    assert "KYP Y positive-real enforcement finished" in log_text
    assert "exact Y-to-S delivery completed" in log_text


def test_y_spice_export_ac_matches_conductance_and_capacitance(tmp_path: Path) -> None:
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice is not installed")
    model = SimpleNamespace(
        network=SimpleNamespace(nports=1),
        poles=np.array([], dtype=complex),
        residues=np.empty((1, 0), dtype=complex),
        constant_coeff=np.array([0.02 + 0j]),
        proportional_coeff=np.array([1.0e-9 + 0j]),
    )
    subckt = tmp_path / "rc.y.sp"
    write_spice_subcircuit_y(model, subckt, fitted_model_name="rc_y")
    deck = tmp_path / "verify.cir"
    deck.write_text(
        "Y exporter verification\n"
        f".include '{subckt.as_posix()}'\n"
        "Vac in 0 ac 1\nXy in rc_y\n.ac lin 1 1meg 1meg\n.print ac i(vac)\n.end\n",
        encoding="ascii",
    )
    completed = subprocess.run([ngspice, "-b", str(deck)], capture_output=True, text=True, check=True)
    match = re.search(r"1\.000000e\+06\s+([-+\deE.]+),\s*([-+\deE.]+)", completed.stdout)
    assert match is not None
    current = complex(float(match.group(1)), float(match.group(2)))
    np.testing.assert_allclose(current, -(0.02 + 2j * np.pi * 1.0e6 * 1.0e-9), rtol=1e-5, atol=1e-8)


@pytest.mark.parametrize(
    ("pole", "residue"),
    [(-1.0e7 + 0j, 2.0e5 + 0j), (-1.0e7 + 2.0e7j, 3.0e5 + 1.0e5j)],
)
def test_y_spice_export_ac_matches_real_and_complex_pole_responses(tmp_path: Path, pole: complex, residue: complex) -> None:
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice is not installed")
    model = SimpleNamespace(
        network=SimpleNamespace(nports=1), poles=np.array([pole]), residues=np.array([[residue]]),
        constant_coeff=np.array([0j]), proportional_coeff=np.array([0j]),
    )
    subckt = tmp_path / "pole.y.sp"
    write_spice_subcircuit_y(model, subckt, fitted_model_name="pole_y")
    deck = tmp_path / "pole.cir"
    deck.write_text(
        "Y pole exporter verification\n"
        f".include '{subckt.as_posix()}'\n"
        "Vac in 0 ac 1\nXy in pole_y\n.ac lin 1 1meg 1meg\n.print ac i(vac)\n.end\n",
        encoding="ascii",
    )
    completed = subprocess.run([ngspice, "-b", str(deck)], capture_output=True, text=True, check=True)
    match = re.search(r"1\.000000e\+06\s+([-+\deE.]+),\s*([-+\deE.]+)", completed.stdout)
    assert match is not None
    current = complex(float(match.group(1)), float(match.group(2)))
    expected = -evaluate_fitted_y(model, [1.0e6])[0, 0, 0]
    np.testing.assert_allclose(current, expected, rtol=1e-5, atol=1e-8)


def test_y_spice_export_preserves_two_port_cross_admittance_sign(tmp_path: Path) -> None:
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        pytest.skip("ngspice is not installed")
    model = SimpleNamespace(
        network=SimpleNamespace(nports=2), poles=np.array([], dtype=complex), residues=np.empty((4, 0), dtype=complex),
        constant_coeff=np.array([0.1, -0.02, -0.02, 0.1], dtype=complex), proportional_coeff=np.zeros(4, dtype=complex),
    )
    subckt = tmp_path / "two_port.y.sp"
    write_spice_subcircuit_y(model, subckt, fitted_model_name="two_y")
    deck = tmp_path / "two_port.cir"
    deck.write_text(
        "Y two port cross-admittance verification\n"
        f".include '{subckt.as_posix()}'\n"
        "V1 p1 0 0\nV2 p2 0 ac 1\nXy p1 p2 two_y\n.ac lin 1 1meg 1meg\n.print ac i(v1)\n.end\n",
        encoding="ascii",
    )
    completed = subprocess.run([ngspice, "-b", str(deck)], capture_output=True, text=True, check=True)
    match = re.search(r"1\.000000e\+06\s+([-+\deE.]+),\s*([-+\deE.]+)", completed.stdout)
    assert match is not None
    # I(V1) is current supplied by the source, the negative of current into port 1.
    np.testing.assert_allclose(complex(float(match.group(1)), float(match.group(2))), 0.02 + 0j, atol=1e-8)


def test_evaluate_fitted_y_uses_native_matrix_shape() -> None:
    model = SimpleNamespace(
        network=SimpleNamespace(nports=1),
        poles=np.array([-2.0 + 0j]),
        residues=np.array([[1.0 + 0j]]),
        constant_coeff=np.array([0.5 + 0j]),
        proportional_coeff=np.array([0.0 + 0j]),
    )
    np.testing.assert_allclose(evaluate_fitted_y(model, [0.0]), [[[1.0 + 0j]]])
