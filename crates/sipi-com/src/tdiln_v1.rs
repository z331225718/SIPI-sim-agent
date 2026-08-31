// SPDX-License-Identifier: MIT
// Direct-port source: Agent-COM `metrics/tdiln.py` at the pinned commit/tree
// recorded in `SOURCE-MAP-COM-02.md`.
//
//! Time-domain insertion-loss noise report (`get_ILN_cmp_td`).
//!
//! This is an auxiliary metric/report path from upstream Agent-COM.  It uses
//! a small complex weighted least-squares insertion-loss model as the report
//! definition requires, but that fit is never used by the channel resolver or
//! the normal S-parameter-to-impulse path.

use rustfft::num_complex::Complex;
use sipi_types::Complex64;

use crate::{
    DiscretePdfV1, FdToTdErrorV1, FdToTdOptionsV1, NoiseErrorV1, PdfErrorV1,
    bessel_thomson_filter_v1, rectangular_pulse_response_fd_v1, s21_to_impulse_dc_v1,
    sampled_signal_pdf_v1,
};

pub const TDILN_POLICY_V1: &str = "sipi.com.metrics.tdiln-v1.complex-il-fit-filtered-impulse-pdf";
const TDILN_SPARSE_PAM_BACKEND_V1: bool = true;

#[derive(Clone, Debug, PartialEq)]
pub struct TdIlnResultV1 {
    pub fit: Vec<Complex64>,
    pub iln_db: Vec<f64>,
    pub reference_pulse: Vec<f64>,
    pub fitted_pulse: Vec<f64>,
    pub iln_pulse: Vec<f64>,
    pub time_s: Vec<f64>,
    pub pdf: DiscretePdfV1,
    pub selected_phase: usize,
    pub fom_v: f64,
    pub fom_pdf_v: f64,
    pub snr_isi_fom_db: f64,
    pub snr_isi_fom_pdf_db: f64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TdIlnErrorV1 {
    InvalidInput(&'static str),
    LengthMismatch,
    EmptyRange,
    ZeroTransfer,
    SingularFit,
    NonFiniteCalculation,
    Noise(NoiseErrorV1),
    FdToTd(FdToTdErrorV1),
    Pdf(PdfErrorV1),
}

impl From<NoiseErrorV1> for TdIlnErrorV1 {
    fn from(value: NoiseErrorV1) -> Self {
        Self::Noise(value)
    }
}

impl From<FdToTdErrorV1> for TdIlnErrorV1 {
    fn from(value: FdToTdErrorV1) -> Self {
        Self::FdToTd(value)
    }
}

impl From<PdfErrorV1> for TdIlnErrorV1 {
    fn from(value: PdfErrorV1) -> Self {
        Self::Pdf(value)
    }
}

#[allow(clippy::too_many_arguments)]
pub fn r480_tdiln_v1(
    sdd21: &[Complex64],
    frequency_hz: &[f64],
    f1_hz: f64,
    f2_hz: f64,
    baud_hz: f64,
    samples_per_ui: usize,
    sample_dt_s: f64,
    levels: u32,
    spec_ber: f64,
    bin_size: f64,
    bessel_order: usize,
    bessel_cutoff_multiplier: f64,
    transmitter_transition_time_ns: f64,
    enforce_causality: bool,
    ec_pulse_tolerance: f64,
    ec_relative_tolerance: f64,
    ec_difference_tolerance: f64,
) -> Result<TdIlnResultV1, TdIlnErrorV1> {
    r480_tdiln_with_pdf_backend_v1(
        sdd21,
        frequency_hz,
        f1_hz,
        f2_hz,
        baud_hz,
        samples_per_ui,
        sample_dt_s,
        levels,
        spec_ber,
        bin_size,
        bessel_order,
        bessel_cutoff_multiplier,
        transmitter_transition_time_ns,
        enforce_causality,
        ec_pulse_tolerance,
        ec_relative_tolerance,
        ec_difference_tolerance,
        TDILN_SPARSE_PAM_BACKEND_V1,
    )
}

#[allow(clippy::too_many_arguments)]
fn r480_tdiln_with_pdf_backend_v1(
    sdd21: &[Complex64],
    frequency_hz: &[f64],
    f1_hz: f64,
    f2_hz: f64,
    baud_hz: f64,
    samples_per_ui: usize,
    sample_dt_s: f64,
    levels: u32,
    spec_ber: f64,
    bin_size: f64,
    bessel_order: usize,
    bessel_cutoff_multiplier: f64,
    transmitter_transition_time_ns: f64,
    enforce_causality: bool,
    ec_pulse_tolerance: f64,
    ec_relative_tolerance: f64,
    ec_difference_tolerance: f64,
    sparse_pam: bool,
) -> Result<TdIlnResultV1, TdIlnErrorV1> {
    validate_frequency_v1(frequency_hz)?;
    if sdd21.len() != frequency_hz.len() {
        return Err(TdIlnErrorV1::LengthMismatch);
    }
    if !(f1_hz >= 0.0 && f2_hz > f1_hz)
        || !(baud_hz > 0.0)
        || samples_per_ui == 0
        || !(sample_dt_s > 0.0)
        || levels < 2
        || !(0.0 < spec_ber && spec_ber <= 1.0)
        || !(bin_size > 0.0)
        || !transmitter_transition_time_ns.is_finite()
        || transmitter_transition_time_ns < 0.0
    {
        return Err(TdIlnErrorV1::InvalidInput("invalid TDILN controls"));
    }
    let start = upper_bound_v1(frequency_hz, f1_hz).saturating_sub(1);
    let stop = lower_bound_v1(frequency_hz, f2_hz).min(frequency_hz.len() - 1);
    if stop <= start {
        return Err(TdIlnErrorV1::EmptyRange);
    }
    let axis = &frequency_hz[start..=stop];
    let values = &sdd21[start..=stop];
    if values
        .iter()
        .any(|value| value.real() == 0.0 && value.imaginary() == 0.0)
    {
        return Err(TdIlnErrorV1::ZeroTransfer);
    }
    let fit = complex_insertion_loss_fit_v1(values, axis)?;
    let iln_db = values
        .iter()
        .zip(&fit)
        .map(|(value, fitted)| {
            20.0 * value.real().hypot(value.imaginary()).log10()
                - 20.0 * fitted.real().hypot(fitted.imaginary()).log10()
        })
        .collect::<Vec<_>>();
    let filter =
        bessel_thomson_filter_v1(axis, bessel_order, bessel_cutoff_multiplier, baud_hz, true)?;
    let conditioning = filter
        .iter()
        .zip(axis)
        .map(|(filter, frequency)| {
            let gaussian = -((std::f64::consts::PI * *frequency / 1.0e9
                * transmitter_transition_time_ns
                / 1.6832)
                .powi(2));
            complex_scale_v1(*filter, gaussian.exp())
        })
        .collect::<Vec<_>>();
    let reference_values = values
        .iter()
        .zip(&conditioning)
        .map(|(value, filter)| complex_mul_v1(*value, *filter))
        .collect::<Vec<_>>();
    let fitted_values = fit
        .iter()
        .zip(&conditioning)
        .map(|(value, filter)| complex_mul_v1(*value, *filter))
        .collect::<Vec<_>>();
    let impulse_options = FdToTdOptionsV1 {
        sample_dt_s,
        magnitude_policy: "trend_to_DC".to_owned(),
        phase_policy: "interp_to_DC".to_owned(),
        enforce_causality,
        ec_pulse_tolerance,
        ec_relative_tolerance,
        ec_difference_tolerance,
        truncation_threshold: 1.0e-7,
        debug: false,
        max_iterations: 10_000,
    };
    let reference = s21_to_impulse_dc_v1(&reference_values, axis, &impulse_options)?;
    let fitted = s21_to_impulse_dc_v1(&fitted_values, axis, &impulse_options)?;
    let reference_pulse = rectangular_pulse_response_fd_v1(&reference.voltage, samples_per_ui)?;
    let fitted_pulse = rectangular_pulse_response_fd_v1(&fitted.voltage, samples_per_ui)?;
    let peak = argmax_first_v1(&reference_pulse);
    let end = reference_pulse.len().min(fitted_pulse.len());
    if peak >= end {
        return Err(TdIlnErrorV1::InvalidInput(
            "TDILN peak is outside fitted pulse",
        ));
    }
    let iln_pulse = fitted_pulse[peak..end]
        .iter()
        .zip(&reference_pulse[peak..end])
        .map(|(fitted, reference)| fitted - reference)
        .collect::<Vec<_>>();
    let time_s = fitted.time_s[peak..end].to_vec();
    if iln_pulse.len() < samples_per_ui || fitted_pulse[peak] <= 0.0 {
        return Err(TdIlnErrorV1::InvalidInput("invalid TDILN pulse support"));
    }
    let fom_v = (0..samples_per_ui)
        .map(|phase| strided_norm_v1(&iln_pulse, phase, samples_per_ui))
        .fold(0.0, f64::max);
    let mut selected_phase = 0usize;
    let mut selected_pdf = None;
    let mut rms_fom = f64::NEG_INFINITY;
    for phase in 0..samples_per_ui {
        let samples = iln_pulse[phase..]
            .iter()
            .step_by(samples_per_ui)
            .copied()
            .collect::<Vec<_>>();
        // Each PAM component has at most `levels` nonzero masses.  The
        // sparse backend preserves the same binning and source-order
        // normalization while avoiding dense spans of zero-probability bins.
        let pdf = sampled_signal_pdf_v1(&samples, levels, bin_size, sparse_pam)?;
        let rms = (pdf
            .probability()
            .iter()
            .enumerate()
            .map(|(index, probability)| probability * pdf.x(index).powi(2))
            .sum::<f64>()
            .sqrt())
            * 2.0_f64.sqrt();
        if rms > rms_fom {
            rms_fom = rms;
            selected_phase = phase;
            selected_pdf = Some(pdf);
        }
    }
    let pdf = selected_pdf.ok_or(TdIlnErrorV1::InvalidInput("no TDILN phase PDF"))?;
    let fom_pdf_v = -pdf.first_quantile(spec_ber)?;
    if !(fom_v > 0.0 && fom_pdf_v > 0.0) {
        return Err(TdIlnErrorV1::InvalidInput("TDILN FOM must be positive"));
    }
    let cursor = fitted_pulse[peak];
    Ok(TdIlnResultV1 {
        fit,
        iln_db,
        reference_pulse,
        fitted_pulse,
        iln_pulse,
        time_s,
        pdf,
        selected_phase,
        fom_v,
        fom_pdf_v,
        snr_isi_fom_db: db_scalar_v1(cursor / fom_v),
        snr_isi_fom_pdf_db: db_scalar_v1(cursor / fom_pdf_v),
    })
}

fn validate_frequency_v1(frequency: &[f64]) -> Result<(), TdIlnErrorV1> {
    if frequency.len() < 3
        || frequency
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
        || frequency.windows(2).any(|pair| pair[1] <= pair[0])
    {
        return Err(TdIlnErrorV1::InvalidInput(
            "frequency axis must be increasing with at least three samples",
        ));
    }
    Ok(())
}

fn upper_bound_v1(values: &[f64], target: f64) -> usize {
    values.partition_point(|value| *value <= target)
}

fn lower_bound_v1(values: &[f64], target: f64) -> usize {
    values.partition_point(|value| *value < target)
}

fn complex_insertion_loss_fit_v1(
    values: &[Complex64],
    frequencies: &[f64],
) -> Result<Vec<Complex64>, TdIlnErrorV1> {
    let mut matrix = Vec::with_capacity(values.len());
    let mut target = Vec::with_capacity(values.len());
    let mut phase_previous = None;
    let mut unwrapped = Vec::with_capacity(values.len());
    for value in values {
        let phase = value.imaginary().atan2(value.real());
        let mut phase = phase;
        if let Some(previous) = phase_previous {
            let mut delta = phase - previous;
            while delta > std::f64::consts::PI {
                phase -= std::f64::consts::TAU;
                delta -= std::f64::consts::TAU;
            }
            while delta <= -std::f64::consts::PI {
                phase += std::f64::consts::TAU;
                delta += std::f64::consts::TAU;
            }
        }
        phase_previous = Some(phase);
        unwrapped.push(phase);
    }
    // The Python source forms the basis with Hz.  Scaling the frequency
    // coordinate before the 4x4 solve is algebraically identical, while
    // avoiding a normal matrix whose entries span roughly 42 orders of
    // magnitude for ordinary COM grids.
    const FREQUENCY_SCALE_HZ: f64 = 1.0e9;
    for ((value, frequency), phase) in values.iter().zip(frequencies).zip(&unwrapped) {
        let normalized_frequency = *frequency / FREQUENCY_SCALE_HZ;
        let f_sqrt = normalized_frequency.sqrt();
        let value_complex = to_complex_v1(*value);
        matrix.push([
            value_complex,
            value_complex * f_sqrt,
            value_complex * normalized_frequency,
            value_complex * normalized_frequency.powi(2),
        ]);
        let log_value = Complex::new(value_complex.norm().ln(), *phase);
        target.push(value_complex * log_value);
    }
    let mut normal = [[Complex::new(0.0, 0.0); 4]; 4];
    let mut rhs = [Complex::new(0.0, 0.0); 4];
    for row in 0..4 {
        for column in 0..4 {
            normal[row][column] = matrix
                .iter()
                .map(|item| item[row].conj() * item[column])
                .sum();
        }
        rhs[row] = matrix
            .iter()
            .zip(&target)
            .map(|(item, target)| item[row].conj() * *target)
            .sum();
    }
    let alpha = solve_complex_4x4_v1(normal, rhs)?;
    frequencies
        .iter()
        .map(|frequency| {
            let normalized_frequency = *frequency / FREQUENCY_SCALE_HZ;
            let z = alpha[0]
                + alpha[1] * normalized_frequency.sqrt()
                + alpha[2] * normalized_frequency
                + alpha[3] * normalized_frequency.powi(2);
            let value = z.exp();
            Complex64::try_new(value.re, value.im).map_err(|_| TdIlnErrorV1::NonFiniteCalculation)
        })
        .collect()
}

fn solve_complex_4x4_v1(
    mut matrix: [[Complex<f64>; 4]; 4],
    mut rhs: [Complex<f64>; 4],
) -> Result<[Complex<f64>; 4], TdIlnErrorV1> {
    for column in 0..4 {
        let pivot = (column..4)
            .max_by(|left, right| {
                matrix[*left][column]
                    .norm()
                    .total_cmp(&matrix[*right][column].norm())
            })
            .ok_or(TdIlnErrorV1::SingularFit)?;
        if matrix[pivot][column].norm() <= f64::EPSILON {
            return Err(TdIlnErrorV1::SingularFit);
        }
        if pivot != column {
            matrix.swap(pivot, column);
            rhs.swap(pivot, column);
        }
        for row in column + 1..4 {
            let factor = matrix[row][column] / matrix[column][column];
            matrix[row][column] = Complex::new(0.0, 0.0);
            for entry in column + 1..4 {
                matrix[row][entry] -= factor * matrix[column][entry];
            }
            rhs[row] -= factor * rhs[column];
        }
    }
    let mut result = [Complex::new(0.0, 0.0); 4];
    for row in (0..4).rev() {
        let mut value = rhs[row];
        for column in row + 1..4 {
            value -= matrix[row][column] * result[column];
        }
        if matrix[row][row].norm() <= f64::EPSILON {
            return Err(TdIlnErrorV1::SingularFit);
        }
        result[row] = value / matrix[row][row];
    }
    if result
        .iter()
        .any(|value| !value.re.is_finite() || !value.im.is_finite())
    {
        return Err(TdIlnErrorV1::NonFiniteCalculation);
    }
    Ok(result)
}

fn to_complex_v1(value: Complex64) -> Complex<f64> {
    Complex::new(value.real(), value.imaginary())
}

fn complex_mul_v1(left: Complex64, right: Complex64) -> Complex64 {
    Complex64::try_new(
        left.real() * right.real() - left.imaginary() * right.imaginary(),
        left.real() * right.imaginary() + left.imaginary() * right.real(),
    )
    .expect("finite complex multiplication")
}

fn complex_scale_v1(value: Complex64, scale: f64) -> Complex64 {
    Complex64::try_new(value.real() * scale, value.imaginary() * scale)
        .expect("finite complex scaling")
}

fn argmax_first_v1(values: &[f64]) -> usize {
    let mut best = 0;
    for index in 1..values.len() {
        if values[index] > values[best] {
            best = index;
        }
    }
    best
}

fn strided_norm_v1(values: &[f64], start: usize, step: usize) -> f64 {
    values
        .iter()
        .skip(start)
        .step_by(step)
        .map(|value| value * value)
        .sum::<f64>()
        .sqrt()
}

fn db_scalar_v1(value: f64) -> f64 {
    20.0 * value.log10()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn source() -> (Vec<Complex64>, Vec<f64>) {
        let frequency = (0..64)
            .map(|index| index as f64 * 1.0e9)
            .collect::<Vec<_>>();
        let transfer = frequency
            .iter()
            .map(|value| {
                let magnitude = (-(value / 8.0e10)).exp() * (1.0 + 0.2 * (value / 5.0e9).sin());
                let phase = -value / 2.0e10;
                Complex64::try_new(magnitude * phase.cos(), magnitude * phase.sin()).unwrap()
            })
            .collect::<Vec<_>>();
        (transfer, frequency)
    }

    #[test]
    fn tdiln_produces_fit_waveform_and_semantic_pdf() {
        let (transfer, frequency) = source();
        let result = r480_tdiln_v1(
            &transfer, &frequency, 0.0, 50.0e9, 25.0e9, 4, 1.0e-12, 4, 1.0e-4, 0.01, 4, 1.0, 0.0,
            false, 0.05, 0.006, 1.0e-4,
        )
        .expect("TDILN");
        assert_eq!(result.fit.len(), result.iln_db.len());
        assert_eq!(result.iln_pulse.len(), result.time_s.len());
        assert!(!result.pdf.probability().is_empty());
        assert!(result.fom_v > 0.0);
    }

    #[test]
    fn sparse_pdf_backend_preserves_tdiln_receipts() {
        let (transfer, frequency) = source();
        let direct = r480_tdiln_with_pdf_backend_v1(
            &transfer, &frequency, 0.0, 50.0e9, 25.0e9, 4, 1.0e-12, 4, 1.0e-4, 0.01, 4, 1.0, 0.0,
            false, 0.05, 0.006, 1.0e-4, false,
        )
        .expect("direct TDILN");
        let sparse = r480_tdiln_v1(
            &transfer, &frequency, 0.0, 50.0e9, 25.0e9, 4, 1.0e-12, 4, 1.0e-4, 0.01, 4, 1.0, 0.0,
            false, 0.05, 0.006, 1.0e-4,
        )
        .expect("sparse TDILN");
        assert_eq!(direct.selected_phase, sparse.selected_phase);
        assert_eq!(direct.pdf.min_bin(), sparse.pdf.min_bin());
        assert_eq!(
            direct.pdf.probability().len(),
            sparse.pdf.probability().len()
        );
        for (left, right) in direct
            .pdf
            .probability()
            .iter()
            .zip(sparse.pdf.probability())
        {
            assert!(
                (left - right).abs() < 1.0e-12,
                "PDF drift: {left} vs {right}"
            );
        }
        for (left, right) in [
            (direct.fom_v, sparse.fom_v),
            (direct.fom_pdf_v, sparse.fom_pdf_v),
            (direct.snr_isi_fom_db, sparse.snr_isi_fom_db),
            (direct.snr_isi_fom_pdf_db, sparse.snr_isi_fom_pdf_db),
        ] {
            assert!(
                (left - right).abs() < 1.0e-12,
                "TDILN scalar drift: {left} vs {right}"
            );
        }
    }

    #[test]
    fn tdiln_rejects_zero_transfer_and_singular_controls() {
        let (mut transfer, frequency) = source();
        transfer[3] = Complex64::try_new(0.0, 0.0).unwrap();
        assert_eq!(
            r480_tdiln_v1(
                &transfer, &frequency, 0.0, 50.0e9, 25.0e9, 4, 1.0e-12, 4, 1.0e-4, 0.01, 4, 1.0,
                0.0, false, 0.05, 0.006, 1.0e-4,
            )
            .unwrap_err(),
            TdIlnErrorV1::ZeroTransfer
        );
    }
}
