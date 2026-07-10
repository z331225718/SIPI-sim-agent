from __future__ import annotations

from typing import Any

import numpy as np


def _get_model_order(poles: np.ndarray) -> int:
    pole_array = np.asarray(poles)
    return int(np.count_nonzero(pole_array.imag == 0.0) + 2 * np.count_nonzero(pole_array.imag != 0.0))


def streaming_pole_relocation(
    poles: np.ndarray,
    freqs: np.ndarray,
    freq_responses: np.ndarray,
    weights_responses: np.ndarray,
    fit_constant: bool,
    fit_proportional: bool,
    *,
    frequency_relocation_weights: np.ndarray | None = None,
    return_diagnostics: bool = False,
    out_of_band_pole_regularization_weight: float = 0.0,
    out_of_band_pole_regularization_start_fraction: float = 1.0,
    pole_regularization_weights: np.ndarray | None = None,
) -> tuple[Any, ...]:
    return _streaming_pole_relocation_impl(
        poles,
        freqs,
        freq_responses,
        weights_responses,
        fit_constant,
        fit_proportional,
        low_memory=False,
        frequency_relocation_weights=frequency_relocation_weights,
        return_diagnostics=return_diagnostics,
        out_of_band_pole_regularization_weight=out_of_band_pole_regularization_weight,
        out_of_band_pole_regularization_start_fraction=out_of_band_pole_regularization_start_fraction,
        pole_regularization_weights=pole_regularization_weights,
    )


def streaming_reciprocal_pole_relocation(
    poles: np.ndarray,
    freqs: np.ndarray,
    freq_responses: np.ndarray,
    weights_responses: np.ndarray,
    fit_constant: bool,
    fit_proportional: bool,
    *,
    frequency_relocation_weights: np.ndarray | None = None,
    return_diagnostics: bool = False,
    out_of_band_pole_regularization_weight: float = 0.0,
    out_of_band_pole_regularization_start_fraction: float = 1.0,
    pole_regularization_weights: np.ndarray | None = None,
) -> tuple[Any, ...]:
    compressed_responses, compressed_weights, multiplicities = _compress_reciprocal_responses(
        freq_responses,
        weights_responses,
    )
    return _streaming_pole_relocation_impl(
        poles,
        freqs,
        compressed_responses,
        compressed_weights,
        fit_constant,
        fit_proportional,
        low_memory=False,
        response_multiplicities=multiplicities,
        frequency_relocation_weights=frequency_relocation_weights,
        return_diagnostics=return_diagnostics,
        out_of_band_pole_regularization_weight=out_of_band_pole_regularization_weight,
        out_of_band_pole_regularization_start_fraction=out_of_band_pole_regularization_start_fraction,
        pole_regularization_weights=pole_regularization_weights,
    )


def _compress_reciprocal_responses(
    freq_responses: np.ndarray,
    weights_responses: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_responses = len(freq_responses)
    n_ports = int(round(np.sqrt(n_responses)))
    if n_ports * n_ports != n_responses:
        return freq_responses, weights_responses, np.ones(n_responses)
    selected_indices = []
    multiplicities = []
    for row in range(n_ports):
        for column in range(row, n_ports):
            selected_indices.append(row * n_ports + column)
            multiplicities.append(1.0 if row == column else 2.0)
    return (
        np.asarray(freq_responses)[selected_indices],
        np.asarray(weights_responses)[selected_indices],
        np.asarray(multiplicities, dtype=float),
    )


def _streaming_pole_relocation_impl(
    poles: np.ndarray,
    freqs: np.ndarray,
    freq_responses: np.ndarray,
    weights_responses: np.ndarray,
    fit_constant: bool,
    fit_proportional: bool,
    *,
    low_memory: bool,
    response_multiplicities: np.ndarray | None = None,
    frequency_relocation_weights: np.ndarray | None = None,
    return_diagnostics: bool = False,
    out_of_band_pole_regularization_weight: float = 0.0,
    out_of_band_pole_regularization_start_fraction: float = 1.0,
    pole_regularization_weights: np.ndarray | None = None,
) -> tuple[Any, ...]:
    n_responses, n_freqs = np.shape(freq_responses)
    if frequency_relocation_weights is None:
        frequency_weight = None
    else:
        frequency_weight = np.asarray(frequency_relocation_weights, dtype=float)
        if frequency_weight.shape != (n_freqs,):
            raise ValueError("frequency_relocation_weights must have one value per frequency sample")
    if response_multiplicities is None:
        response_multiplicities = np.ones(n_responses, dtype=float)
    else:
        response_multiplicities = np.asarray(response_multiplicities, dtype=float)
    n_samples = int(np.sum(response_multiplicities) * n_freqs)
    s = 2j * np.pi * freqs

    weighted_responses = weights_responses[:, None] * freq_responses
    weight_extra = np.sqrt(np.sum(response_multiplicities[:, None] * np.square(np.abs(weighted_responses)))) / n_samples
    weights_responses = np.sqrt(response_multiplicities * weights_responses)
    weight_extra = np.sqrt(weight_extra)

    n_cols_unused = _get_model_order(poles)
    n_cols_used = n_cols_unused + 1
    idx_constant = []
    idx_proportional = []
    if fit_constant:
        idx_constant = [n_cols_unused]
        n_cols_unused += 1
    if fit_proportional:
        idx_proportional = [n_cols_unused]
        n_cols_unused += 1

    real_mask = poles.imag == 0
    idx_poles_real = np.nonzero(real_mask)[0]
    idx_poles_complex = np.nonzero(~real_mask)[0]

    n_real = len(idx_poles_real)
    n_cmplx = len(idx_poles_complex)
    idx_res_real = np.arange(n_real)
    idx_res_complex_re = n_real + 2 * np.arange(n_cmplx)
    idx_res_complex_im = idx_res_complex_re + 1
    regularization_columns: list[tuple[int, float]] = []
    regularization_weight = max(0.0, float(out_of_band_pole_regularization_weight))
    pole_regularization = (
        np.zeros(len(poles), dtype=float)
        if pole_regularization_weights is None
        else np.asarray(pole_regularization_weights, dtype=float)
    )
    if pole_regularization.shape != (len(poles),):
        raise ValueError("pole_regularization_weights must have one value per stored pole")
    if regularization_weight > 0.0 and n_cmplx:
        start_fraction = max(0.0, float(out_of_band_pole_regularization_start_fraction))
        fmax = float(np.max(freqs))
        for pole_position, pole in enumerate(poles[idx_poles_complex]):
            pole_frequency = abs(float(pole.imag)) / (2.0 * np.pi)
            if pole_frequency > start_fraction * fmax:
                regularization_columns.extend([
                    (int(idx_res_complex_re[pole_position]), regularization_weight),
                    (int(idx_res_complex_im[pole_position]), regularization_weight),
                ])
    for pole_position, pole_index in enumerate(idx_poles_complex):
        local_weight = max(0.0, float(pole_regularization[pole_index]))
        if local_weight > 0.0:
            regularization_columns.extend([
                (int(idx_res_complex_re[pole_position]), local_weight),
                (int(idx_res_complex_im[pole_position]), local_weight),
            ])
    n_regularization_rows = len(regularization_columns)

    coeff_real = 1 / (s[:, None] - poles[None, idx_poles_real])
    coeff_complex_re = (
        1 / (s[:, None] - poles[None, idx_poles_complex])
        + 1 / (s[:, None] - np.conj(poles[None, idx_poles_complex]))
    )
    coeff_complex_im = (
        1j / (s[:, None] - poles[None, idx_poles_complex])
        - 1j / (s[:, None] - np.conj(poles[None, idx_poles_complex]))
    )

    dim_m = 2 * n_freqs
    dim_n = n_cols_unused + n_cols_used
    dim_k = min(dim_m, dim_n)
    if dim_k == dim_m:
        n_rows_r12 = n_freqs
        n_rows_r22 = n_freqs
    else:
        n_rows_r12 = n_cols_unused
        n_rows_r22 = n_cols_used

    dim0 = n_responses * n_rows_r22 + 1 + n_regularization_rows
    data_rows = n_responses * n_rows_r22
    a_fast = None if low_memory else np.empty((dim0, n_cols_used))
    r_aug = np.empty((0, n_cols_used + 1), dtype=float) if low_memory else None
    work = np.empty((n_freqs, dim_n), dtype=complex)
    work_ri = np.empty((dim_m, dim_n), dtype=float)
    column_norm_sq = np.zeros(n_cols_used, dtype=float) if low_memory else None

    for response_index in range(n_responses):
        response = freq_responses[response_index]
        work[:, idx_res_real] = coeff_real
        work[:, idx_res_complex_re] = coeff_complex_re
        work[:, idx_res_complex_im] = coeff_complex_im
        work[:, idx_constant] = 1
        work[:, idx_proportional] = s[:, None]
        work[:, n_cols_unused + idx_res_real] = -response[:, None] * coeff_real
        work[:, n_cols_unused + idx_res_complex_re] = -response[:, None] * coeff_complex_re
        work[:, n_cols_unused + idx_res_complex_im] = -response[:, None] * coeff_complex_im
        work[:, -1] = -response
        work_ri[:n_freqs, :] = work.real
        work_ri[n_freqs:, :] = work.imag
        if frequency_weight is not None:
            work_ri[:n_freqs, :] *= frequency_weight[:, None]
            work_ri[n_freqs:, :] *= frequency_weight[:, None]
        r_matrix = np.linalg.qr(work_ri, mode="r")
        r22 = weights_responses[response_index] * r_matrix[n_rows_r12:, n_cols_unused:]
        if low_memory:
            assert column_norm_sq is not None
            column_norm_sq += np.sum(np.square(r22), axis=0)
        else:
            assert a_fast is not None
            row_slice = slice(response_index * n_rows_r22, (response_index + 1) * n_rows_r22)
            a_fast[row_slice, :] = r22

    if low_memory:
        assert r_aug is not None
        assert column_norm_sq is not None
        extra_row = np.zeros(n_cols_used, dtype=float)
        extra_row[idx_res_real] = np.sum(coeff_real.real, axis=0)
        extra_row[idx_res_complex_re] = np.sum(coeff_complex_re.real, axis=0)
        extra_row[idx_res_complex_im] = np.sum(coeff_complex_im.real, axis=0)
        extra_row[-1] = n_freqs
        extra_row *= weight_extra
        b_extra = weight_extra * n_samples
        column_norm_sq += np.square(extra_row)
        if n_regularization_rows:
            for col, local_weight in regularization_columns:
                column_norm_sq[col] += max(0.0, float(local_weight))
        column_norms = np.sqrt(column_norm_sq)
        scaling = np.divide(1.0, column_norms, out=np.ones_like(column_norms), where=column_norms != 0.0)

        for response_index in range(n_responses):
            response = freq_responses[response_index]
            work[:, idx_res_real] = coeff_real
            work[:, idx_res_complex_re] = coeff_complex_re
            work[:, idx_res_complex_im] = coeff_complex_im
            work[:, idx_constant] = 1
            work[:, idx_proportional] = s[:, None]
            work[:, n_cols_unused + idx_res_real] = -response[:, None] * coeff_real
            work[:, n_cols_unused + idx_res_complex_re] = -response[:, None] * coeff_complex_re
            work[:, n_cols_unused + idx_res_complex_im] = -response[:, None] * coeff_complex_im
            work[:, -1] = -response
            work_ri[:n_freqs, :] = work.real
            work_ri[n_freqs:, :] = work.imag
            if frequency_weight is not None:
                work_ri[:n_freqs, :] *= frequency_weight[:, None]
                work_ri[n_freqs:, :] *= frequency_weight[:, None]
            r_matrix = np.linalg.qr(work_ri, mode="r")
            r22 = weights_responses[response_index] * r_matrix[n_rows_r12:, n_cols_unused:]
            r22 = scaling * r22
            previous_rows = r_aug.shape[0]
            qr_update_work = np.empty((previous_rows + n_rows_r22, n_cols_used + 1), dtype=float)
            qr_update_work[:previous_rows, :] = r_aug
            qr_update_work[previous_rows : previous_rows + n_rows_r22, :-1] = r22
            qr_update_work[previous_rows : previous_rows + n_rows_r22, -1] = 0.0
            r_aug = np.linalg.qr(qr_update_work[: previous_rows + n_rows_r22, :], mode="r")

        n_constraint_rows = 1 + n_regularization_rows
        qr_update_work = np.empty((r_aug.shape[0] + n_constraint_rows, n_cols_used + 1), dtype=float)
        qr_update_work[: r_aug.shape[0], :] = r_aug
        constraint_start = r_aug.shape[0]
        qr_update_work[constraint_start:, :] = 0.0
        qr_update_work[constraint_start, :-1] = scaling * extra_row
        qr_update_work[constraint_start, -1] = b_extra
        if n_regularization_rows:
            for offset, (col, local_weight) in enumerate(regularization_columns, start=1):
                reg_weight = np.sqrt(max(0.0, float(local_weight)))
                qr_update_work[constraint_start + offset, col] = scaling[col] * reg_weight
        r_aug = np.linalg.qr(qr_update_work, mode="r")

        r_matrix = r_aug[:n_cols_used, :n_cols_used]
        qtb = r_aug[:n_cols_used, -1]
        residual_tail = r_aug[n_cols_used:, -1]

        singular_vals = np.linalg.svd(r_matrix, compute_uv=False)
        cond = np.linalg.cond(r_matrix)
        full_rank = min(dim0, n_cols_used)
        y, _, _, _ = np.linalg.lstsq(r_matrix, qtb, rcond=None)
        x = scaling * y
        tolerance = np.finfo(float).eps * max(dim0, n_cols_used) * (singular_vals[0] if len(singular_vals) else 0.0)
        rank = int(np.count_nonzero(singular_vals > tolerance))
        residuals = np.array([float(np.sum(np.square(residual_tail)))])
    else:
        assert a_fast is not None
        extra_row_index = data_rows
        a_fast[extra_row_index, idx_res_real] = np.sum(coeff_real.real, axis=0)
        a_fast[extra_row_index, idx_res_complex_re] = np.sum(coeff_complex_re.real, axis=0)
        a_fast[extra_row_index, idx_res_complex_im] = np.sum(coeff_complex_im.real, axis=0)
        a_fast[extra_row_index, -1] = n_freqs
        a_fast[extra_row_index, :] = weight_extra * a_fast[extra_row_index, :]
        if n_regularization_rows:
            a_fast[extra_row_index + 1 :, :] = 0.0
            for offset, (col, local_weight) in enumerate(regularization_columns, start=1):
                reg_weight = np.sqrt(max(0.0, float(local_weight)))
                a_fast[extra_row_index + offset, col] = reg_weight

        scaling = 1 / np.linalg.norm(a_fast, axis=0)
        a_fast = scaling * a_fast

        b = np.zeros(dim0)
        b[extra_row_index] = weight_extra * n_samples

        cond = np.linalg.cond(a_fast)
        full_rank = min(dim0, n_cols_used)
        x, residuals, rank, singular_vals = np.linalg.lstsq(a_fast, b, rcond=None)
        x = scaling * x
    rank_deficiency = full_rank - rank

    c_res = x[:-1]
    d_res = x[-1]
    input_poles = np.asarray(poles, dtype=complex)
    c_res_by_pole = np.zeros(len(input_poles), dtype=float)
    for pole_position, pole_index in enumerate(idx_poles_real):
        c_res_by_pole[pole_index] = abs(float(c_res[idx_res_real[pole_position]]))
    for pole_position, pole_index in enumerate(idx_poles_complex):
        real_part = float(c_res[idx_res_complex_re[pole_position]])
        imag_part = float(c_res[idx_res_complex_im[pole_position]])
        c_res_by_pole[pole_index] = float(np.hypot(real_part, imag_part))
    tol_res = 1e-8
    if np.abs(d_res) < tol_res:
        d_res = tol_res * (d_res / np.abs(d_res))

    h_matrix = np.zeros((len(c_res), len(c_res)))
    poles_real = poles[np.nonzero(real_mask)]
    poles_cplx = poles[np.nonzero(~real_mask)]

    h_matrix[idx_res_real, idx_res_real] = poles_real.real
    h_matrix[idx_res_real] -= c_res / d_res
    h_matrix[idx_res_complex_re, idx_res_complex_re] = poles_cplx.real
    h_matrix[idx_res_complex_re, idx_res_complex_im] = poles_cplx.imag
    h_matrix[idx_res_complex_im, idx_res_complex_re] = -1 * poles_cplx.imag
    h_matrix[idx_res_complex_im, idx_res_complex_im] = poles_cplx.real
    h_matrix[idx_res_complex_re] -= 2 * c_res / d_res

    poles_new = np.linalg.eigvals(h_matrix)
    relocated = poles_new[np.nonzero(poles_new.imag >= 0)]
    relocated.real = -1 * np.abs(relocated.real)
    result = (relocated, d_res, cond, int(rank_deficiency), residuals, singular_vals)
    if not return_diagnostics:
        return result
    diagnostics = {
        "input_poles": input_poles.copy(),
        "c_res": np.asarray(c_res, dtype=complex).copy(),
        "c_res_by_pole": c_res_by_pole,
        "d_res": complex(d_res),
    }
    return (*result, diagnostics)
