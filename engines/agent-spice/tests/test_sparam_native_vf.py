import numpy as np

from agent_spice.sparam.fitting import _LightweightSNetwork
from agent_spice.sparam.native_vf import NativeVectorFitting


def test_native_vector_fitting_writes_s_parameter_spice_subcircuit(tmp_path):
    network = _LightweightSNetwork(
        f=np.array([1.0e6, 2.0e6]),
        s=np.zeros((2, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    vector_fit = NativeVectorFitting(network)
    vector_fit.poles = np.array([-1.0e7 + 0.0j, -2.0e7 + 3.0e7j])
    vector_fit.residues = np.array([[0.2 + 0.0j, 0.1 + 0.05j]])
    vector_fit.constant_coeff = np.array([0.01])
    vector_fit.proportional_coeff = np.array([0.0])
    output = tmp_path / "native.sp"

    vector_fit.write_spice_subcircuit_s(str(output), fitted_model_name="native_s")

    content = output.read_text(encoding="utf-8")
    assert "placeholder" not in content.lower()
    assert ".SUBCKT native_s p1" in content
    assert "V1 p1 s1 0" in content
    assert "R1 s1 0 50.0" in content
    assert "Gd1_1" in content
    assert "Gr1_1_1" in content
    assert "Cx1_a1" in content
    assert "Gr2_re_1_1" in content
    assert "Cx2_re_a1" in content
    assert ".ENDS native_s" in content


def test_native_spice_exporter_matches_skrf_element_vocabulary(tmp_path):
    network = _LightweightSNetwork(
        f=np.array([1.0e6, 2.0e6]),
        s=np.zeros((2, 1, 1), dtype=complex),
        z0=np.array([[50.0], [50.0]], dtype=complex),
        name="one_port",
    )
    vector_fit = NativeVectorFitting(network)
    vector_fit.poles = np.array([-1.0e7 + 0.0j, -2.0e7 + 3.0e7j])
    vector_fit.residues = np.array([[0.2 + 0.0j, 0.1 + 0.05j]])
    vector_fit.constant_coeff = np.array([0.01])
    vector_fit.proportional_coeff = np.array([0.001])
    output = tmp_path / "native_with_e.sp"

    vector_fit.write_spice_subcircuit_s(str(output), fitted_model_name="native_s")

    lines = output.read_text(encoding="utf-8").splitlines()
    prefixes = {line.split()[0] for line in lines if line and not line.startswith("*") and not line.startswith(".")}
    expected = {
        "V1",
        "R1",
        "Gd1_1",
        "Fd1_1",
        "Ge1_1",
        "Gr1_1_1",
        "Gr2_re_1_1",
        "Gr2_im_1_1",
        "Cx1_a1",
        "Gx1_a1",
        "Fx1_a1",
        "Rp1_a1",
        "Cx2_re_a1",
        "Gx2_re_a1",
        "Fx2_re_a1",
        "Rp2_re_re_a1",
        "Gp2_re_im_a1",
        "Cx2_im_a1",
        "Gp2_im_re_a1",
        "Rp2_im_im_a1",
        "Le1",
        "Ge1",
        "Fe1",
    }
    assert expected <= prefixes
