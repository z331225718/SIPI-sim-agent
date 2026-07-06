from __future__ import annotations

import time
import warnings
from typing import Any

import numpy as np

from .skrf_streaming import streaming_pole_relocation


class NativeVectorFitting:
    _pole_relocation = staticmethod(streaming_pole_relocation)

    def __init__(self, network: Any):
        self.network = network
        self.poles = None
        self.residues = None
        self.proportional_coeff = None
        self.constant_coeff = None
        self.max_iterations = 100
        self.max_tol = 1e-6
        self.wall_clock_time = 0.0
        self.d_res_history = []
        self.delta_max_history = []
        self.history_cond_A = []
        self.history_rank_deficiency = []

    @staticmethod
    def get_model_order(poles: np.ndarray) -> int:
        return int(np.sum((np.asarray(poles).imag != 0) + 1))

    @staticmethod
    def _init_poles(freqs: np.ndarray, n_poles_real: int, n_poles_cmplx: int, init_pole_spacing: str):
        fmin = np.amin(freqs)
        fmax = np.amax(freqs)
        if fmin == 0.0:
            fmin = freqs[1] / 1000
        spacing = init_pole_spacing.lower()
        if spacing == "log":
            pole_freqs_real = np.geomspace(fmin, fmax, n_poles_real)
            pole_freqs_cmplx = np.geomspace(fmin, fmax, n_poles_cmplx)
        elif spacing in {"lin", "linear"}:
            pole_freqs_real = np.linspace(fmin, fmax, n_poles_real)
            pole_freqs_cmplx = np.linspace(fmin, fmax, n_poles_cmplx)
        elif spacing == "custom":
            return None
        else:
            warnings.warn("Invalid initial pole spacing; using linear spacing.", UserWarning, stacklevel=2)
            pole_freqs_real = np.linspace(fmin, fmax, n_poles_real)
            pole_freqs_cmplx = np.linspace(fmin, fmax, n_poles_cmplx)

        poles = np.zeros(n_poles_real + n_poles_cmplx, dtype=complex)
        for i, freq in enumerate(pole_freqs_real):
            omega = 2 * np.pi * freq
            poles[i] = -1 * omega
        offset = len(pole_freqs_real)
        for i, freq in enumerate(pole_freqs_cmplx):
            omega = 2 * np.pi * freq
            poles[offset + i] = (-0.01 + 1j) * omega
        return poles

    def vector_fit(
        self,
        n_poles_real: int = 2,
        n_poles_cmplx: int = 2,
        init_pole_spacing: str = "lin",
        parameter_type: str = "s",
        fit_constant: bool = True,
        fit_proportional: bool = False,
        enforce_dc: bool = True,
    ) -> None:
        started = time.perf_counter()
        norm = np.average(self.network.f)
        freqs_norm = np.array(self.network.f) / norm
        poles = self._init_poles(freqs_norm, n_poles_real, n_poles_cmplx, init_pole_spacing)
        if poles is None:
            if self.poles is None or len(self.poles) == 0:
                raise ValueError("Initial poles must be provided when init_pole_spacing='custom'")
            poles = self.poles / norm

        if parameter_type.lower() != "s":
            raise ValueError("NativeVectorFitting currently supports only S-parameter fitting")
        nw_responses = self.network.s
        freq_responses = np.array(
            [nw_responses[:, i, j] for i in range(self.network.nports) for j in range(self.network.nports)]
        )
        weights_responses = np.linalg.norm(freq_responses, axis=1)

        max_singular = 1.0
        self.d_res_history = []
        self.delta_max_history = []
        self.history_cond_A = []
        self.history_rank_deficiency = []

        iterations = self.max_iterations
        while iterations > 0:
            poles, d_res, cond, rank_deficiency, _residuals, singular_vals = self._pole_relocation(
                poles,
                freqs_norm,
                freq_responses,
                weights_responses,
                fit_constant,
                fit_proportional,
            )
            self.history_cond_A.append(cond)
            self.history_rank_deficiency.append(rank_deficiency)
            self.d_res_history.append(d_res)
            new_max_singular = np.amax(singular_vals)
            delta_max = np.abs(1 - new_max_singular / max_singular)
            self.delta_max_history.append(delta_max)
            max_singular = new_max_singular
            iterations -= 1

        residues, constant_coeff, proportional_coeff, _residuals, _rank, _singular_vals = self._fit_residues(
            poles,
            freqs_norm,
            freq_responses,
            fit_constant,
            fit_proportional,
            enforce_dc,
        )
        self.poles = poles * norm
        self.residues = np.array(residues) * norm
        self.constant_coeff = np.array(constant_coeff)
        self.proportional_coeff = np.array(proportional_coeff) / norm
        self.wall_clock_time = time.perf_counter() - started

    auto_fit = vector_fit

    @staticmethod
    def _fit_residues(poles, freqs, freq_responses, fit_constant, fit_proportional, enforce_dc):
        n_responses, n_freqs = np.shape(freq_responses)
        s = 2j * np.pi * freqs
        n_cols = NativeVectorFitting.get_model_order(poles)
        idx_constant = []
        idx_proportional = []
        if fit_constant:
            idx_constant = [n_cols]
            n_cols += 1
        if fit_proportional:
            idx_proportional = [n_cols]
            n_cols += 1

        real_mask = poles.imag == 0
        idx_poles_real = np.nonzero(real_mask)[0]
        idx_poles_complex = np.nonzero(~real_mask)[0]
        idx_res_real = []
        idx_res_complex_re = []
        idx_res_complex_im = []
        response_column = 0
        for pole in poles:
            if pole.imag == 0:
                idx_res_real.append(response_column)
                response_column += 1
            else:
                idx_res_complex_re.append(response_column)
                idx_res_complex_im.append(response_column + 1)
                response_column += 2
        idx_res_real = np.asarray(idx_res_real)
        idx_res_complex_re = np.asarray(idx_res_complex_re)
        idx_res_complex_im = idx_res_complex_re + 1

        a_matrix = np.empty((n_freqs, n_cols), dtype=complex)
        coeff_real = 1 / (s[:, None] - poles[None, idx_poles_real])
        coeff_complex_re = (
            1 / (s[:, None] - poles[None, idx_poles_complex])
            + 1 / (s[:, None] - np.conj(poles[None, idx_poles_complex]))
        )
        coeff_complex_im = (
            1j / (s[:, None] - poles[None, idx_poles_complex])
            - 1j / (s[:, None] - np.conj(poles[None, idx_poles_complex]))
        )
        a_matrix[:, idx_res_real] = coeff_real
        a_matrix[:, idx_res_complex_re] = coeff_complex_re
        a_matrix[:, idx_res_complex_im] = coeff_complex_im
        a_matrix[:, idx_constant] = 1
        a_matrix[:, idx_proportional] = s[:, None]
        scaling = 1 / np.linalg.norm(a_matrix, axis=0)
        a_matrix = scaling * a_matrix

        if enforce_dc and freqs[0] == 0.0:
            mask_idx_constrained = np.zeros(n_cols, dtype=bool)
            if fit_constant:
                mask_idx_constrained[idx_constant] = True
            else:
                mask_idx_constrained[0] = True
            a22 = a_matrix[1:, ~mask_idx_constrained]
            b2 = freq_responses[:, 1:]
            a22_ri = np.vstack((a22.real, a22.imag))
            b22_ri = np.hstack((b2.real, b2.imag))
            x2, residuals, rank, singular_vals = np.linalg.lstsq(a22_ri, b22_ri.T, rcond=None)
            b1 = freq_responses[:, 0]
            a11 = a_matrix[0, mask_idx_constrained]
            a12 = a_matrix[0, ~mask_idx_constrained]
            x1 = np.real(1 / a11 * (b1 - np.dot(a12, x2)))
            x = np.empty((n_cols, n_responses))
            x[mask_idx_constrained, :] = x1
            x[~mask_idx_constrained, :] = x2
        else:
            a_ri = np.vstack((a_matrix.real, a_matrix.imag))
            b_ri = np.hstack((freq_responses.real, freq_responses.imag))
            x, residuals, rank, singular_vals = np.linalg.lstsq(a_ri, b_ri.T, rcond=None)

        x = scaling[:, None] * x
        residues = np.empty((len(freq_responses), len(poles)), dtype=complex)
        residues[:, idx_poles_real] = np.transpose(x[idx_res_real])
        residues[:, idx_poles_complex] = np.transpose(x[idx_res_complex_re] + 1j * x[idx_res_complex_im])
        constant_coeff = x[idx_constant][0] if fit_constant else np.zeros(n_responses)
        proportional_coeff = x[idx_proportional][0] if fit_proportional else np.zeros(n_responses)
        return residues, constant_coeff, proportional_coeff, residuals, rank, singular_vals

    def get_model_response(self, i: int, j: int, freqs: Any = None) -> np.ndarray:
        if freqs is None:
            freqs = self.network.f
        s = 2j * np.pi * np.array(freqs)
        n_ports = int(np.sqrt(len(self.constant_coeff)))
        response_index = i * n_ports + j
        residues = self.residues[response_index]
        response = self.proportional_coeff[response_index] * s + self.constant_coeff[response_index]
        for pole_index, pole in enumerate(self.poles):
            if np.imag(pole) == 0.0:
                response += residues[pole_index] / (s - pole)
            else:
                response += residues[pole_index] / (s - pole) + np.conj(residues[pole_index]) / (s - np.conj(pole))
        return response

    def get_rms_error(self, parameter_type: str = "s") -> float:
        total = 0.0
        for row in range(self.network.nports):
            for column in range(self.network.nports):
                original = self.network.s[:, row, column]
                fitted = self.get_model_response(row, column, self.network.f)
                total += float(np.mean(np.square(np.abs(original - fitted))))
        return float(np.sqrt(total))

    def is_passive(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def passivity_test(self, *args: Any, **kwargs: Any) -> list:
        return []

    def passivity_enforce(self, *args: Any, **kwargs: Any) -> None:
        return None

    def write_spice_subcircuit_s(
        self,
        file: str,
        fitted_model_name: str = "s_equivalent",
        create_reference_pins: bool = False,
    ) -> None:
        with open(file, "w", encoding="utf-8") as handle:
            handle.write("* EQUIVALENT CIRCUIT FOR NATIVE VECTOR FITTED S-MATRIX\n")
            handle.write("* Created using agent-spice native vector fitting\n")
            handle.write("*\n")

            if create_reference_pins:
                input_nodes = " ".join(f"p{i + 1} p{i + 1}_ref" for i in range(self.network.nports))
            else:
                input_nodes = " ".join(f"p{i + 1}" for i in range(self.network.nports))
            handle.write(f".SUBCKT {fitted_model_name} {input_nodes}\n")

            build_e = bool(np.any(self.proportional_coeff))
            for row in range(self.network.nports):
                handle.write("*\n")
                handle.write(f"* Port network for port {row + 1}\n")
                node_ref_i = f"p{row + 1}_ref" if create_reference_pins else "0"
                z0_i = float(np.real(self.network.z0[0, row]))
                gain_vccs_a_i = 1 / (2 * np.sqrt(z0_i))
                gain_cccs_a_i = np.sqrt(z0_i) / 2
                gain_b_i = 2 / np.sqrt(z0_i)

                handle.write(f"V{row + 1} p{row + 1} s{row + 1} 0\n")
                handle.write(f"R{row + 1} s{row + 1} {node_ref_i} {z0_i}\n")

                for column in range(self.network.nports):
                    node_ref_j = f"p{column + 1}_ref" if create_reference_pins else "0"
                    z0_j = float(np.real(self.network.z0[0, column]))
                    response_index = row * self.network.nports + column
                    gain_vccs_a_j = 1 / (2 * np.sqrt(z0_j))
                    gain_cccs_a_j = np.sqrt(z0_j) / 2

                    d_value = self.constant_coeff[response_index]
                    e_value = self.proportional_coeff[response_index]
                    if d_value != 0.0:
                        g_ij = gain_b_i * d_value * gain_vccs_a_j
                        f_ij = gain_b_i * d_value * gain_cccs_a_j
                        handle.write(
                            f"Gd{row + 1}_{column + 1} {node_ref_i} s{row + 1} "
                            f"p{column + 1} {node_ref_j} {g_ij}\n"
                        )
                        handle.write(f"Fd{row + 1}_{column + 1} {node_ref_i} s{row + 1} V{column + 1} {f_ij}\n")

                    if build_e and e_value != 0.0:
                        g_ij = gain_b_i * e_value
                        handle.write(f"Ge{row + 1}_{column + 1} {node_ref_i} s{row + 1} e{column + 1} 0 {g_ij}\n")

                    for pole_index, pole in enumerate(self.poles):
                        residue = self.residues[response_index, pole_index]
                        g_re = gain_b_i * np.real(residue)
                        g_im = gain_b_i * np.imag(residue)
                        if np.imag(pole) == 0.0:
                            xkj = f"x{pole_index + 1}_a{column + 1}"
                            handle.write(f"Gr{pole_index + 1}_{row + 1}_{column + 1} {node_ref_i} s{row + 1} {xkj} 0 {g_re}\n")
                        else:
                            xk_re_j = f"x{pole_index + 1}_re_a{column + 1}"
                            xk_im_j = f"x{pole_index + 1}_im_a{column + 1}"
                            handle.write(
                                f"Gr{pole_index + 1}_re_{row + 1}_{column + 1} "
                                f"{node_ref_i} s{row + 1} {xk_re_j} 0 {g_re}\n"
                            )
                            handle.write(
                                f"Gr{pole_index + 1}_im_{row + 1}_{column + 1} "
                                f"{node_ref_i} s{row + 1} {xk_im_j} 0 {g_im}\n"
                            )

                handle.write("*\n")
                handle.write(f"* State networks driven by port {row + 1}\n")
                for pole_index, pole in enumerate(self.poles):
                    pole_re = np.real(pole)
                    pole_im = np.imag(pole)
                    if pole_im == 0.0:
                        xki = f"x{pole_index + 1}_a{row + 1}"
                        handle.write(f"Cx{pole_index + 1}_a{row + 1} {xki} 0 1.0\n")
                        handle.write(
                            f"Gx{pole_index + 1}_a{row + 1} 0 {xki} "
                            f"p{row + 1} {node_ref_i} {gain_vccs_a_i}\n"
                        )
                        handle.write(f"Fx{pole_index + 1}_a{row + 1} 0 {xki} V{row + 1} {gain_cccs_a_i}\n")
                        handle.write(f"Rp{pole_index + 1}_a{row + 1} 0 {xki} {-1 / pole_re}\n")
                    else:
                        xk_re_i = f"x{pole_index + 1}_re_a{row + 1}"
                        xk_im_i = f"x{pole_index + 1}_im_a{row + 1}"
                        handle.write(f"Cx{pole_index + 1}_re_a{row + 1} {xk_re_i} 0 1.0\n")
                        handle.write(
                            f"Gx{pole_index + 1}_re_a{row + 1} 0 {xk_re_i} "
                            f"p{row + 1} {node_ref_i} {2 * gain_vccs_a_i}\n"
                        )
                        handle.write(f"Fx{pole_index + 1}_re_a{row + 1} 0 {xk_re_i} V{row + 1} {2 * gain_cccs_a_i}\n")
                        handle.write(f"Rp{pole_index + 1}_re_re_a{row + 1} 0 {xk_re_i} {-1 / pole_re}\n")
                        handle.write(f"Gp{pole_index + 1}_re_im_a{row + 1} 0 {xk_re_i} {xk_im_i} 0 {pole_im}\n")
                        handle.write(f"Cx{pole_index + 1}_im_a{row + 1} {xk_im_i} 0 1.0\n")
                        handle.write(f"Gp{pole_index + 1}_im_re_a{row + 1} 0 {xk_im_i} {xk_re_i} 0 {-1 * pole_im}\n")
                        handle.write(f"Rp{pole_index + 1}_im_im_a{row + 1} 0 {xk_im_i} {-1 / pole_re}\n")

                if build_e:
                    handle.write("*\n")
                    handle.write(f"* Network with derivative of input a_{row + 1} for proportional term\n")
                    handle.write(f"Le{row + 1} e{row + 1} 0 1.0\n")
                    handle.write(f"Ge{row + 1} 0 e{row + 1} p{row + 1} {node_ref_i} {gain_vccs_a_i}\n")
                    handle.write(f"Fe{row + 1} 0 e{row + 1} V{row + 1} {gain_cccs_a_i}\n")

            handle.write(f".ENDS {fitted_model_name}\n")
