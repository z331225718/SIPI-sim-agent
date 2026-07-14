from pathlib import Path
import json
import re
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from agent_spice.sparam.artifacts import evaluate_fitted_y, write_spice_subcircuit_y
from agent_spice.sparam.native_vf import NativeVectorFitting
from agent_spice.sparam.yparam import YParamFitConfig, fit_touchstone_to_y_spice


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
        "--max-y-rms-siemens", "1e-6",
    ])

    assert exit_code == 0
    assert (tmp_path / "line_fitted.y.sp").is_file()
    assert (tmp_path / "line_fitted.y.json").is_file()
    assert (tmp_path / "line_fitted.y.html").is_file()


def test_fit_yparam_cli_fails_positive_real_check(tmp_path: Path) -> None:
    from agent_spice import cli

    frequencies = np.array([1.0e6, 2.0e6, 5.0e6, 1.0e7])
    touchstone = _write_y_touchstone(tmp_path / "negative_cli.s1p", frequencies, np.full((4, 1, 1), -0.01 + 0j))

    assert cli.main(["fit-yparam", str(touchstone), "--n-poles-real", "1", "--n-poles-cmplx", "1", "--fit-iterations", "8"]) == 1


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
