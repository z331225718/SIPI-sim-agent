from __future__ import annotations

from dataclasses import dataclass
import time
import warnings
from typing import Any

import numpy as np

from .pole_relocation import streaming_pole_relocation


@dataclass(frozen=True)
class PoleCandidateScore:
    poles: np.ndarray
    rms_error: float
    max_sigma: float
    passivity_excess: float
    score: float


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
        self.high_frequency_complex_pair_count = 0
        self.high_frequency_complex_pair_damping = 0.03
        self.high_frequency_complex_pair_lower_fraction = 0.68
        self.high_frequency_complex_pair_frequency_gate_enabled = False
        self.high_frequency_residual_injection_enabled = False
        self.high_frequency_residual_injection_lower_fraction = 0.68
        self.high_frequency_residual_injection_damping = 0.03
        self.high_frequency_complex_pair_anchor_bands_hz = ()
        self.high_frequency_complex_pair_anchor_strength = 0.0
        self.high_frequency_complex_pair_anchor_damping = 0.03
        self.effective_order_max = None
        self.effective_complex_pole_count = None
        self.effective_order_selection = "frequency_rank"
        self.effective_order_passivity_weight = 1.0
        self.post_relocation_effective_order_max = None
        self.high_frequency_relocation_weight_enabled = False
        self.high_frequency_relocation_weight_lower_fraction = 0.68
        self.high_frequency_relocation_weight_gain = 2.0
        self.out_of_band_pole_regularization_weight = 0.0
        self.out_of_band_pole_regularization_start_fraction = 1.0
        self.dynamic_edge_c_res_regularization_enabled = False
        self.dynamic_edge_c_res_regularization_base_weight = 0.0
        self.dynamic_edge_c_res_regularization_start_fraction = 1.0
        self.dynamic_edge_c_res_regularization_growth_threshold = 1.5
        self.topology_sweep_diagnostics = []
        self.high_frequency_repair_diagnostics = []
        self.high_frequency_residual_injection_diagnostics = []
        self.pole_relocation_history = []
        self.post_relocation_order_diagnostics = []
        self.relocation_frontier_enabled = False
        self.relocation_frontier_passivity_weight = 1.0
        self.relocation_frontier_max_candidates = 0
        self.relocation_frontier_diagnostics = []

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

    @staticmethod
    def _ensure_high_frequency_complex_pairs(
        poles: np.ndarray,
        freqs: np.ndarray,
        pair_count: int,
        damping: float,
        lower_fraction: float,
        frequency_gate: bool = True,
    ) -> np.ndarray:
        if pair_count <= 0:
            return poles
        pole_array = np.asarray(poles, dtype=complex).copy()
        if not frequency_gate:
            complex_mask = np.abs(pole_array.imag) > 0.0
            existing_pairs = int(np.count_nonzero(complex_mask))
            missing_pairs = pair_count - existing_pairs
            if missing_pairs <= 0:
                return pole_array

            real_indices = np.nonzero(~complex_mask)[0]
            if len(real_indices) == 0:
                return pole_array

            fmax = float(np.max(freqs))
            lower = max(0.0, min(float(lower_fraction), 1.0))
            anchors = np.linspace(lower * fmax, fmax, pair_count)
            replacement_anchors = anchors[-missing_pairs:]
            replacement_indices = sorted(real_indices, key=lambda idx: abs(pole_array[idx]), reverse=True)[:missing_pairs]
            for idx, anchor in zip(replacement_indices, replacement_anchors):
                omega = 2.0 * np.pi * anchor
                pole_array[idx] = complex(-abs(damping) * omega, omega)
            return pole_array

        valid_pairs, invalid_pairs = NativeVectorFitting._high_frequency_complex_pair_frequencies(
            pole_array,
            freqs,
            lower_fraction,
        )
        missing_pairs = pair_count - len(valid_pairs)
        if missing_pairs <= 0:
            for idx, _ in invalid_pairs:
                pole_array[idx] = NativeVectorFitting._demote_complex_pair_to_real(pole_array[idx])
            return pole_array

        fmax = float(np.max(freqs))
        lower = max(0.0, min(float(lower_fraction), 1.0))
        anchors = np.linspace(lower * fmax, fmax, pair_count)
        replacement_anchors = NativeVectorFitting._missing_high_frequency_anchors(
            [frequency for _, frequency in valid_pairs],
            anchors,
            missing_pairs,
        )
        if not replacement_anchors:
            return pole_array

        complex_mask = np.abs(pole_array.imag) > 0.0
        real_indices = list(np.nonzero(~complex_mask)[0])
        invalid_complex_indices = [idx for idx, _ in sorted(invalid_pairs, key=lambda item: item[1])]
        real_replacement_indices = sorted(real_indices, key=lambda idx: abs(pole_array[idx]), reverse=True)
        replacement_indices = (invalid_complex_indices + real_replacement_indices)[: len(replacement_anchors)]
        if len(replacement_indices) < len(replacement_anchors):
            return pole_array

        for idx, anchor in zip(replacement_indices, replacement_anchors):
            omega = 2.0 * np.pi * anchor
            pole_array[idx] = complex(-abs(damping) * omega, omega)
        replaced = set(replacement_indices)
        for idx, _ in invalid_pairs:
            if idx not in replaced:
                pole_array[idx] = NativeVectorFitting._demote_complex_pair_to_real(pole_array[idx])
        return pole_array

    @staticmethod
    def _demote_complex_pair_to_real(pole: complex) -> complex:
        magnitude = max(float(abs(pole)), np.finfo(float).tiny)
        return complex(-magnitude, 0.0)

    @staticmethod
    def _high_frequency_complex_pair_frequencies(
        poles: np.ndarray,
        freqs: np.ndarray,
        lower_fraction: float,
    ) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
        pole_array = np.asarray(poles, dtype=complex)
        fmax = float(np.max(freqs))
        lower = max(0.0, min(float(lower_fraction), 1.0))
        min_frequency = lower * fmax
        valid: list[tuple[int, float]] = []
        invalid: list[tuple[int, float]] = []
        for idx, pole in enumerate(pole_array):
            if abs(pole.imag) == 0.0:
                continue
            pole_frequency = abs(float(pole.imag)) / (2.0 * np.pi)
            target = valid if pole_frequency >= min_frequency else invalid
            target.append((idx, pole_frequency))
        return valid, invalid

    @staticmethod
    def _missing_high_frequency_anchors(
        valid_frequencies_hz: list[float],
        anchors_hz: np.ndarray,
        missing_count: int,
    ) -> list[float]:
        if missing_count <= 0:
            return []
        remaining = [float(anchor) for anchor in np.asarray(anchors_hz, dtype=float)]
        for valid_frequency in valid_frequencies_hz:
            if not remaining:
                break
            closest = min(range(len(remaining)), key=lambda idx: abs(remaining[idx] - valid_frequency))
            remaining.pop(closest)
        return remaining[-missing_count:]

    @staticmethod
    def _edge_residual_seed_frequency(
        freqs_hz: np.ndarray,
        raw_responses: np.ndarray,
        fitted_responses: np.ndarray,
        lower_fraction: float,
    ) -> float:
        freq_array = np.asarray(freqs_hz, dtype=float)
        residual = np.asarray(raw_responses, dtype=complex) - np.asarray(fitted_responses, dtype=complex)
        residual_power = np.abs(residual) ** 2 if residual.ndim == 1 else np.sum(np.abs(residual) ** 2, axis=0)
        lower = max(0.0, min(float(lower_fraction), 1.0))
        mask = freq_array >= lower * float(np.max(freq_array))
        if not np.any(mask):
            return float(freq_array[-1])
        high_indices = np.nonzero(mask)[0]
        chosen = high_indices[int(np.argmax(residual_power[high_indices]))]
        return float(freq_array[chosen])

    @staticmethod
    def _soft_anchor_high_frequency_complex_pairs(
        poles: np.ndarray,
        *,
        freqs_hz: np.ndarray,
        anchor_bands_hz: tuple[tuple[float, float], ...],
        damping: float,
        strength: float,
    ) -> np.ndarray:
        pole_array = np.asarray(poles, dtype=complex).copy()
        if not anchor_bands_hz or strength <= 0.0:
            return pole_array
        blend = min(max(float(strength), 0.0), 1.0)
        used: set[int] = set()
        for lo_hz, hi_hz in anchor_bands_hz:
            target_hz = 0.5 * (float(lo_hz) + float(hi_hz))
            target_omega = 2.0 * np.pi * target_hz
            target = complex(-abs(float(damping)) * target_omega, target_omega)
            unused_complex = [
                idx
                for idx, pole in enumerate(pole_array)
                if idx not in used and abs(pole.imag) > 0.0
            ]
            unused_real = [
                idx
                for idx, pole in enumerate(pole_array)
                if idx not in used and abs(pole.imag) == 0.0
            ]
            candidates = unused_complex or unused_real
            if not candidates:
                break
            chosen = min(
                candidates,
                key=lambda idx: abs(
                    (
                        abs(float(pole_array[idx].imag))
                        if abs(pole_array[idx].imag) > 0.0
                        else abs(float(pole_array[idx].real))
                    )
                    / (2.0 * np.pi)
                    - target_hz
                ),
            )
            pole_array[chosen] = (1.0 - blend) * pole_array[chosen] + blend * target
            used.add(chosen)
        return pole_array

    @staticmethod
    def _limit_effective_order(
        poles: np.ndarray,
        max_order: int,
        *,
        preferred_complex_count: int = 0,
    ) -> np.ndarray:
        pole_array = np.asarray(poles, dtype=complex)
        if max_order <= 0 or NativeVectorFitting.get_model_order(pole_array) <= max_order:
            return pole_array

        complex_indices = [idx for idx, pole in enumerate(pole_array) if abs(pole.imag) > 0.0]
        real_indices = [idx for idx, pole in enumerate(pole_array) if abs(pole.imag) == 0.0]
        selected: list[int] = []
        budget = int(max_order)

        complex_target = min(max(0, int(preferred_complex_count)), len(complex_indices), budget // 2)
        complex_by_frequency = sorted(complex_indices, key=lambda idx: abs(pole_array[idx].imag), reverse=True)
        for idx in complex_by_frequency[:complex_target]:
            selected.append(idx)
            budget -= 2

        real_by_frequency = sorted(real_indices, key=lambda idx: abs(pole_array[idx].real))
        for idx in real_by_frequency:
            if budget < 1:
                break
            selected.append(idx)
            budget -= 1

        selected_set = set(selected)
        for idx in complex_by_frequency:
            if budget < 2:
                break
            if idx in selected_set:
                continue
            selected.append(idx)
            selected_set.add(idx)
            budget -= 2

        if not selected:
            return pole_array[:1]
        return pole_array[sorted(selected)]

    @staticmethod
    def _trim_low_frequency_real_poles(
        poles: np.ndarray,
        max_order: int,
        preferred_complex_count: int | None = None,
    ) -> np.ndarray:
        pole_array = np.asarray(poles, dtype=complex)
        if max_order <= 0 or NativeVectorFitting.get_model_order(pole_array) <= max_order:
            return pole_array

        complex_indices = sorted(
            (idx for idx, pole in enumerate(pole_array) if abs(pole.imag) > 0.0),
            key=lambda idx: abs(pole_array[idx].imag),
            reverse=True,
        )
        real_indices = sorted(
            (idx for idx, pole in enumerate(pole_array) if abs(pole.imag) == 0.0),
            key=lambda idx: abs(pole_array[idx].real),
            reverse=True,
        )
        complex_limit = max_order // 2
        if preferred_complex_count is not None:
            complex_limit = min(complex_limit, max(0, int(preferred_complex_count)))
        selected_complex = complex_indices[:complex_limit]
        remaining = max_order - 2 * len(selected_complex)
        selected = set(selected_complex)
        selected.update(real_indices[: max(0, remaining)])
        if not selected:
            return pole_array[:1]
        return pole_array[[idx for idx in range(len(pole_array)) if idx in selected]]

    @staticmethod
    def score_pole_candidate(
        poles: np.ndarray,
        freqs: np.ndarray,
        freq_responses: np.ndarray,
        *,
        nports: int,
        fit_constant: bool,
        fit_proportional: bool,
        enforce_dc: bool,
        passivity_weight: float = 1.0,
    ) -> PoleCandidateScore:
        pole_array = np.asarray(poles, dtype=complex)
        freq_array = np.asarray(freqs, dtype=float)
        response_array = np.asarray(freq_responses, dtype=complex)
        residues, constant_coeff, proportional_coeff, *_ = NativeVectorFitting._fit_residues(
            pole_array,
            freq_array,
            response_array,
            fit_constant,
            fit_proportional,
            enforce_dc,
        )
        fitted = NativeVectorFitting._evaluate_residue_model(
            pole_array,
            residues,
            constant_coeff,
            proportional_coeff,
            freq_array,
        )
        rms_error = float(np.sqrt(np.mean(np.abs(fitted - response_array) ** 2)))
        max_sigma = NativeVectorFitting._max_sigma_from_responses(fitted, nports)
        passivity_excess = max(0.0, max_sigma - 1.0)
        combined = rms_error + float(passivity_weight) * passivity_excess
        return PoleCandidateScore(
            poles=pole_array.copy(),
            rms_error=rms_error,
            max_sigma=max_sigma,
            passivity_excess=passivity_excess,
            score=float(combined),
        )

    @staticmethod
    def _select_poles_by_contribution_score(
        poles: np.ndarray,
        freqs: np.ndarray,
        freq_responses: np.ndarray,
        *,
        nports: int,
        max_order: int,
        fit_constant: bool,
        fit_proportional: bool,
        enforce_dc: bool,
        passivity_weight: float,
    ) -> np.ndarray:
        selected = np.asarray(poles, dtype=complex).copy()
        while NativeVectorFitting.get_model_order(selected) > int(max_order) and len(selected) > 1:
            candidates = []
            for remove_index in range(len(selected)):
                candidate = np.delete(selected, remove_index)
                score = NativeVectorFitting.score_pole_candidate(
                    candidate,
                    freqs,
                    freq_responses,
                    nports=nports,
                    fit_constant=fit_constant,
                    fit_proportional=fit_proportional,
                    enforce_dc=enforce_dc,
                    passivity_weight=passivity_weight,
                )
                candidates.append((float(score.score), remove_index, candidate))
            if not candidates:
                break
            candidates.sort(key=lambda item: (item[0], item[1]))
            selected = candidates[0][2]
        return selected

    @staticmethod
    def _evaluate_residue_model(
        poles: np.ndarray,
        residues: np.ndarray,
        constant_coeff: np.ndarray,
        proportional_coeff: np.ndarray,
        freqs: np.ndarray,
    ) -> np.ndarray:
        s = 2j * np.pi * np.asarray(freqs, dtype=float)
        fitted = np.tile(np.asarray(constant_coeff, dtype=complex)[:, None], (1, len(s)))
        if len(proportional_coeff):
            fitted += np.asarray(proportional_coeff, dtype=complex)[:, None] * s[None, :]
        for pole_index, pole in enumerate(np.asarray(poles, dtype=complex)):
            residue = residues[:, pole_index]
            if np.imag(pole) == 0.0:
                fitted += residue[:, None] / (s[None, :] - pole)
            else:
                fitted += residue[:, None] / (s[None, :] - pole) + np.conj(residue)[:, None] / (s[None, :] - np.conj(pole))
        return fitted

    @staticmethod
    def _max_sigma_from_responses(freq_responses: np.ndarray, nports: int) -> float:
        response_array = np.asarray(freq_responses, dtype=complex)
        max_sigma = 0.0
        for freq_index in range(response_array.shape[1]):
            matrix = response_array[:, freq_index].reshape((nports, nports))
            max_sigma = max(max_sigma, float(np.max(np.linalg.svd(matrix, compute_uv=False))))
        return max_sigma

    @staticmethod
    def _resonance_seed_frequencies(freqs: np.ndarray, freq_responses: np.ndarray, count: int) -> np.ndarray:
        freq_array = np.asarray(freqs, dtype=float)
        response_array = np.asarray(freq_responses, dtype=complex)
        if count <= 0 or freq_array.size == 0:
            return np.array([], dtype=float)
        energy = np.linalg.norm(response_array, axis=0)
        peak_indices: list[int] = []
        if len(energy) == 1:
            peak_indices = [0]
        else:
            if energy[0] >= energy[1]:
                peak_indices.append(0)
            for idx in range(1, len(energy) - 1):
                if energy[idx] >= energy[idx - 1] and energy[idx] >= energy[idx + 1]:
                    peak_indices.append(idx)
            if energy[-1] >= energy[-2]:
                peak_indices.append(len(energy) - 1)
        if not peak_indices:
            peak_indices = list(np.argsort(energy)[::-1][:count])
        selected = sorted(peak_indices, key=lambda idx: energy[idx], reverse=True)[:count]
        if len(selected) < count:
            selected_set = set(selected)
            for idx in np.argsort(energy)[::-1]:
                if int(idx) in selected_set:
                    continue
                selected.append(int(idx))
                selected_set.add(int(idx))
                if len(selected) >= count:
                    break
        return np.sort(freq_array[np.asarray(selected[:count], dtype=int)])

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

        if parameter_type.lower() != "s":
            raise ValueError("NativeVectorFitting currently supports only S-parameter fitting")
        nw_responses = self.network.s
        freq_responses = np.array(
            [nw_responses[:, i, j] for i in range(self.network.nports) for j in range(self.network.nports)]
        )
        if init_pole_spacing.lower() == "resonance":
            positive_freqs = np.asarray(self.network.f, dtype=float)
            positive_freqs = positive_freqs[positive_freqs > 0.0]
            real_freqs = (
                np.geomspace(max(float(np.min(positive_freqs)), 1.0), float(np.max(self.network.f)), int(n_poles_real))
                if int(n_poles_real) > 0 and positive_freqs.size
                else np.array([], dtype=float)
            )
            resonance_freqs = self._resonance_seed_frequencies(
                np.asarray(self.network.f, dtype=float),
                freq_responses,
                count=int(n_poles_cmplx),
            )
            poles = np.concatenate(
                [
                    -2.0 * np.pi * real_freqs / norm,
                    (-0.03 + 1j) * 2.0 * np.pi * resonance_freqs / norm,
                ]
            )
        else:
            poles = self._init_poles(freqs_norm, n_poles_real, n_poles_cmplx, init_pole_spacing)
        if poles is None:
            if self.poles is None or len(self.poles) == 0:
                raise ValueError("Initial poles must be provided when init_pole_spacing='custom'")
            poles = self.poles / norm
        weights_responses = np.linalg.norm(freq_responses, axis=1)

        max_singular = 1.0
        self.d_res_history = []
        self.delta_max_history = []
        self.history_cond_A = []
        self.history_rank_deficiency = []
        self.high_frequency_repair_diagnostics = []
        self.high_frequency_residual_injection_diagnostics = []
        self.pole_relocation_history = []
        self.post_relocation_order_diagnostics = []
        self.relocation_frontier_diagnostics = []
        relocation_frontier_checkpoints: list[tuple[int, np.ndarray]] = []

        iterations = self.max_iterations
        iteration = 0
        previous_input_complex_rows: list[tuple[float, float]] = []
        while iterations > 0:
            frequency_relocation_weights = None
            if self.high_frequency_relocation_weight_enabled:
                frequency_relocation_weights = np.ones_like(freqs_norm, dtype=float)
                high_mask = np.asarray(self.network.f, dtype=float) >= (
                    self.high_frequency_relocation_weight_lower_fraction * float(np.max(self.network.f))
                )
                frequency_relocation_weights[high_mask] = float(self.high_frequency_relocation_weight_gain)
            pole_regularization_weights = self._dynamic_edge_c_res_regularization_weights(
                poles,
                norm,
                previous_input_complex_rows,
            )
            relocation_result = self._pole_relocation(
                poles,
                freqs_norm,
                freq_responses,
                weights_responses,
                fit_constant,
                fit_proportional,
                frequency_relocation_weights=frequency_relocation_weights,
                return_diagnostics=True,
                out_of_band_pole_regularization_weight=float(self.out_of_band_pole_regularization_weight),
                out_of_band_pole_regularization_start_fraction=float(
                    self.out_of_band_pole_regularization_start_fraction
                ),
                pole_regularization_weights=pole_regularization_weights,
            )
            relocation_diagnostics = {}
            if len(relocation_result) == 7:
                poles, d_res, cond, rank_deficiency, _residuals, singular_vals, relocation_diagnostics = relocation_result
            else:
                poles, d_res, cond, rank_deficiency, _residuals, singular_vals = relocation_result
            self.history_cond_A.append(cond)
            self.history_rank_deficiency.append(rank_deficiency)
            self.d_res_history.append(d_res)
            if self.high_frequency_complex_pair_anchor_bands_hz:
                poles = self._soft_anchor_high_frequency_complex_pairs(
                    poles * norm,
                    freqs_hz=np.asarray(self.network.f, dtype=float),
                    anchor_bands_hz=tuple(self.high_frequency_complex_pair_anchor_bands_hz),
                    damping=float(self.high_frequency_complex_pair_anchor_damping),
                    strength=float(self.high_frequency_complex_pair_anchor_strength),
                ) / norm
            repaired_poles = self._ensure_high_frequency_complex_pairs(
                poles,
                freqs_norm,
                self.high_frequency_complex_pair_count,
                self.high_frequency_complex_pair_damping,
                self.high_frequency_complex_pair_lower_fraction,
                frequency_gate=bool(self.high_frequency_complex_pair_frequency_gate_enabled),
            )
            if not self.high_frequency_complex_pair_frequency_gate_enabled:
                poles = repaired_poles
            elif np.allclose(repaired_poles, poles):
                poles = repaired_poles
            else:
                current_score = self.score_pole_candidate(
                    poles,
                    freqs_norm,
                    freq_responses,
                    nports=self.network.nports,
                    fit_constant=fit_constant,
                    fit_proportional=fit_proportional,
                    enforce_dc=enforce_dc,
                    passivity_weight=float(self.effective_order_passivity_weight),
                )
                repaired_score = self.score_pole_candidate(
                    repaired_poles,
                    freqs_norm,
                    freq_responses,
                    nports=self.network.nports,
                    fit_constant=fit_constant,
                    fit_proportional=fit_proportional,
                    enforce_dc=enforce_dc,
                    passivity_weight=float(self.effective_order_passivity_weight),
                )
                accepted = repaired_score.score <= current_score.score
                self.high_frequency_repair_diagnostics.append(
                    {
                        "accepted": bool(accepted),
                        "current_score": float(current_score.score),
                        "current_rms_error": float(current_score.rms_error),
                        "current_max_sigma": float(current_score.max_sigma),
                        "repaired_score": float(repaired_score.score),
                        "repaired_rms_error": float(repaired_score.rms_error),
                        "repaired_max_sigma": float(repaired_score.max_sigma),
                    }
                )
                poles = repaired_poles if accepted else poles
            complex_pair_frequencies = [
                abs(float(pole.imag)) * norm / (2.0 * np.pi)
                for pole in np.asarray(poles, dtype=complex)
                if abs(pole.imag) > 0.0
            ]
            input_poles = np.asarray(relocation_diagnostics.get("input_poles", []), dtype=complex)
            c_res_by_pole = np.asarray(relocation_diagnostics.get("c_res_by_pole", []), dtype=float)
            input_complex_rows = [
                (idx, abs(float(pole.imag)) * norm / (2.0 * np.pi))
                for idx, pole in enumerate(input_poles)
                if abs(pole.imag) > 0.0
            ]
            input_complex_c_res = [
                float(c_res_by_pole[idx]) if idx < len(c_res_by_pole) else 0.0
                for idx, _ in input_complex_rows
            ]
            self.pole_relocation_history.append(
                {
                    "iteration": int(iteration),
                    "d_res": [float(np.real(d_res)), float(np.imag(d_res))],
                    "d_res_abs": float(abs(d_res)),
                    "rank_deficiency": int(rank_deficiency),
                    "condition_number": float(cond),
                    "singular_value_min": float(np.min(singular_vals)) if len(singular_vals) else 0.0,
                    "singular_value_max": float(np.max(singular_vals)) if len(singular_vals) else 0.0,
                    "input_complex_pair_frequencies_hz": [float(freq) for _, freq in input_complex_rows],
                    "input_complex_pair_c_res_magnitudes": input_complex_c_res,
                    "pole_regularization_weights": [float(value) for value in pole_regularization_weights],
                    "complex_pair_frequencies_hz": sorted(complex_pair_frequencies),
                    "real_pole_count": int(np.count_nonzero(np.abs(np.asarray(poles).imag) == 0.0)),
                }
            )
            previous_input_complex_rows = [
                (float(freq), float(c_res))
                for (_, freq), c_res in zip(input_complex_rows, input_complex_c_res)
            ]
            if self.effective_order_max is not None:
                preferred_complex_count = (
                    int(self.effective_complex_pole_count)
                    if self.effective_complex_pole_count is not None
                    else max(int(n_poles_cmplx), int(self.high_frequency_complex_pair_count))
                )
                if self.effective_order_selection == "contribution_score":
                    poles = self._select_poles_by_contribution_score(
                        poles,
                        freqs_norm,
                        freq_responses,
                        nports=self.network.nports,
                        max_order=int(self.effective_order_max),
                        fit_constant=fit_constant,
                        fit_proportional=fit_proportional,
                        enforce_dc=enforce_dc,
                        passivity_weight=float(self.effective_order_passivity_weight),
                    )
                else:
                    poles = self._limit_effective_order(
                        poles,
                        int(self.effective_order_max),
                        preferred_complex_count=preferred_complex_count,
                    )
            if self.relocation_frontier_enabled:
                relocation_frontier_checkpoints.append((int(iteration), np.asarray(poles, dtype=complex).copy()))
            new_max_singular = np.amax(singular_vals)
            delta_max = np.abs(1 - new_max_singular / max_singular)
            self.delta_max_history.append(delta_max)
            max_singular = new_max_singular
            iterations -= 1
            iteration += 1

        if self.post_relocation_effective_order_max is not None:
            order_before = self.get_model_order(poles)
            trimmed_poles = self._trim_low_frequency_real_poles(
                poles,
                int(self.post_relocation_effective_order_max),
                preferred_complex_count=(
                    int(self.effective_complex_pole_count)
                    if self.effective_complex_pole_count is not None
                    else int(n_poles_cmplx)
                ),
            )
            poles = trimmed_poles
            self.post_relocation_order_diagnostics.append(
                {
                    "max_order": int(self.post_relocation_effective_order_max),
                    "order_before": int(order_before),
                    "order_after": int(self.get_model_order(poles)),
                    "stored_pole_count_after": int(len(poles)),
                    "complex_pair_count_after": int(np.count_nonzero(np.abs(np.asarray(poles).imag) > 0.0)),
                    "real_pole_count_after": int(np.count_nonzero(np.abs(np.asarray(poles).imag) == 0.0)),
                }
            )

        if self.relocation_frontier_enabled and relocation_frontier_checkpoints:
            max_candidates = int(self.relocation_frontier_max_candidates)
            checkpoints = relocation_frontier_checkpoints
            if max_candidates > 0:
                checkpoints = checkpoints[-max_candidates:]
            selected_index = 0
            selected_score: PoleCandidateScore | None = None
            for checkpoint_index, (checkpoint_iteration, checkpoint_poles) in enumerate(checkpoints):
                candidate_poles = checkpoint_poles
                if self.post_relocation_effective_order_max is not None:
                    candidate_poles = self._trim_low_frequency_real_poles(
                        checkpoint_poles,
                        int(self.post_relocation_effective_order_max),
                        preferred_complex_count=(
                            int(self.effective_complex_pole_count)
                            if self.effective_complex_pole_count is not None
                            else int(n_poles_cmplx)
                        ),
                    )
                score = self.score_pole_candidate(
                    candidate_poles,
                    freqs_norm,
                    freq_responses,
                    nports=self.network.nports,
                    fit_constant=fit_constant,
                    fit_proportional=fit_proportional,
                    enforce_dc=enforce_dc,
                    passivity_weight=float(self.relocation_frontier_passivity_weight),
                )
                if selected_score is None or score.score < selected_score.score:
                    selected_index = checkpoint_index
                    selected_score = score
                self.relocation_frontier_diagnostics.append(
                    {
                        "iteration": int(checkpoint_iteration),
                        "rms_error": float(score.rms_error),
                        "max_sigma": float(score.max_sigma),
                        "passivity_excess": float(score.passivity_excess),
                        "combined_score": float(score.score),
                        "effective_order": int(self.get_model_order(candidate_poles)),
                        "selected": False,
                    }
                )
            assert selected_score is not None
            selected_checkpoint_poles = checkpoints[selected_index][1]
            poles = (
                self._trim_low_frequency_real_poles(
                    selected_checkpoint_poles,
                    int(self.post_relocation_effective_order_max),
                    preferred_complex_count=(
                        int(self.effective_complex_pole_count)
                        if self.effective_complex_pole_count is not None
                        else int(n_poles_cmplx)
                    ),
                )
                if self.post_relocation_effective_order_max is not None
                else selected_checkpoint_poles.copy()
            )
            self.relocation_frontier_diagnostics[selected_index]["selected"] = True

        residues, constant_coeff, proportional_coeff, _residuals, _rank, _singular_vals = self._fit_residues(
            poles,
            freqs_norm,
            freq_responses,
            fit_constant,
            fit_proportional,
            enforce_dc,
        )
        if self.high_frequency_residual_injection_enabled:
            fitted_responses = self._evaluate_residue_model(
                poles,
                residues,
                constant_coeff,
                proportional_coeff,
                freqs_norm,
            )
            seed_frequency = self._edge_residual_seed_frequency(
                freqs_norm,
                freq_responses,
                fitted_responses,
                self.high_frequency_residual_injection_lower_fraction,
            )
            omega = 2.0 * np.pi * seed_frequency
            injected = complex(-abs(self.high_frequency_residual_injection_damping) * omega, omega)
            candidate_poles = np.asarray([*np.asarray(poles, dtype=complex), injected], dtype=complex)
            current_score = self.score_pole_candidate(
                poles,
                freqs_norm,
                freq_responses,
                nports=self.network.nports,
                fit_constant=fit_constant,
                fit_proportional=fit_proportional,
                enforce_dc=enforce_dc,
                passivity_weight=float(self.effective_order_passivity_weight),
            )
            candidate_score = self.score_pole_candidate(
                candidate_poles,
                freqs_norm,
                freq_responses,
                nports=self.network.nports,
                fit_constant=fit_constant,
                fit_proportional=fit_proportional,
                enforce_dc=enforce_dc,
                passivity_weight=float(self.effective_order_passivity_weight),
            )
            accepted = candidate_score.score <= current_score.score
            self.high_frequency_residual_injection_diagnostics.append(
                {
                    "accepted": bool(accepted),
                    "seed_frequency_hz": float(seed_frequency * norm),
                    "current_score": float(current_score.score),
                    "current_rms_error": float(current_score.rms_error),
                    "current_max_sigma": float(current_score.max_sigma),
                    "candidate_score": float(candidate_score.score),
                    "candidate_rms_error": float(candidate_score.rms_error),
                    "candidate_max_sigma": float(candidate_score.max_sigma),
                }
            )
            if accepted:
                poles = candidate_poles
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

    def _dynamic_edge_c_res_regularization_weights(
        self,
        poles: np.ndarray,
        norm: float,
        previous_input_complex_rows: list[tuple[float, float]],
    ) -> np.ndarray:
        pole_array = np.asarray(poles, dtype=complex)
        weights = np.zeros(len(pole_array), dtype=float)
        if not self.dynamic_edge_c_res_regularization_enabled:
            return weights
        base_weight = max(0.0, float(self.dynamic_edge_c_res_regularization_base_weight))
        if base_weight <= 0.0:
            return weights
        fmax = float(np.max(self.network.f))
        start_hz = max(0.0, float(self.dynamic_edge_c_res_regularization_start_fraction)) * fmax
        if not previous_input_complex_rows:
            return weights
        threshold = max(1.0, float(self.dynamic_edge_c_res_regularization_growth_threshold))
        for idx, pole in enumerate(pole_array):
            if abs(pole.imag) == 0.0:
                continue
            pole_frequency_hz = abs(float(pole.imag)) * norm / (2.0 * np.pi)
            if pole_frequency_hz <= start_hz:
                continue
            nearest_frequency, previous_c_res = min(
                previous_input_complex_rows,
                key=lambda item: abs(float(item[0]) - pole_frequency_hz),
            )
            if previous_c_res <= 0.0:
                continue
            growth_proxy = max(1.0, pole_frequency_hz / max(float(nearest_frequency), np.finfo(float).tiny))
            if growth_proxy < threshold:
                continue
            overrun = max(0.0, pole_frequency_hz / max(fmax, np.finfo(float).tiny) - 1.0)
            weights[idx] = base_weight * overrun * growth_proxy
        return weights

    auto_fit = vector_fit

    def vector_fit_topology_sweep(
        self,
        *,
        candidate_configs: list[dict[str, Any]],
        init_pole_spacing: str = "lin",
        parameter_type: str = "s",
        fit_constant: bool = True,
        fit_proportional: bool = False,
        enforce_dc: bool = True,
        passivity_weight: float = 1.0,
    ) -> None:
        if not candidate_configs:
            raise ValueError("candidate_configs must contain at least one topology")
        started = time.perf_counter()
        freq_responses = np.array(
            [self.network.s[:, i, j] for i in range(self.network.nports) for j in range(self.network.nports)]
        )
        best_fit: NativeVectorFitting | None = None
        best_score: PoleCandidateScore | None = None
        diagnostics: list[dict[str, Any]] = []

        for candidate in candidate_configs:
            candidate_fit = NativeVectorFitting(self.network)
            candidate_fit.max_iterations = self.max_iterations
            candidate_fit.max_tol = self.max_tol
            candidate_fit.high_frequency_complex_pair_count = int(candidate.get("high_frequency_complex_pair_count", 0))
            candidate_fit.high_frequency_complex_pair_damping = float(
                candidate.get("high_frequency_complex_pair_damping", self.high_frequency_complex_pair_damping)
            )
            candidate_fit.high_frequency_complex_pair_lower_fraction = float(
                candidate.get("high_frequency_complex_pair_lower_fraction", self.high_frequency_complex_pair_lower_fraction)
            )
            candidate_fit.effective_order_max = self.effective_order_max
            candidate_fit.effective_complex_pole_count = self.effective_complex_pole_count
            candidate_fit.vector_fit(
                n_poles_real=int(candidate["n_poles_real"]),
                n_poles_cmplx=int(candidate["n_poles_cmplx"]),
                init_pole_spacing=init_pole_spacing,
                parameter_type=parameter_type,
                fit_constant=fit_constant,
                fit_proportional=fit_proportional,
                enforce_dc=enforce_dc,
            )
            score = self.score_pole_candidate(
                candidate_fit.poles,
                np.asarray(self.network.f, dtype=float),
                freq_responses,
                nports=self.network.nports,
                fit_constant=fit_constant,
                fit_proportional=fit_proportional,
                enforce_dc=enforce_dc,
                passivity_weight=passivity_weight,
            )
            diagnostic = {
                **candidate,
                "rms_error": float(score.rms_error),
                "max_sigma": float(score.max_sigma),
                "passivity_excess": float(score.passivity_excess),
                "combined_score": float(score.score),
                "stored_pole_count": int(len(candidate_fit.poles)),
                "effective_order": int(self.get_model_order(candidate_fit.poles)),
                "selected": False,
            }
            diagnostics.append(diagnostic)
            if best_score is None or score.score < best_score.score:
                best_score = score
                best_fit = candidate_fit

        assert best_fit is not None
        for diagnostic in diagnostics:
            diagnostic["selected"] = bool(diagnostic["combined_score"] == float(best_score.score))
        self.poles = best_fit.poles
        self.residues = best_fit.residues
        self.constant_coeff = best_fit.constant_coeff
        self.proportional_coeff = best_fit.proportional_coeff
        self.d_res_history = best_fit.d_res_history
        self.delta_max_history = best_fit.delta_max_history
        self.history_cond_A = best_fit.history_cond_A
        self.history_rank_deficiency = best_fit.history_rank_deficiency
        self.topology_sweep_diagnostics = diagnostics
        self.wall_clock_time = time.perf_counter() - started

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
        idx_res_real = np.asarray(idx_res_real, dtype=int)
        idx_res_complex_re = np.asarray(idx_res_complex_re, dtype=int)
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
