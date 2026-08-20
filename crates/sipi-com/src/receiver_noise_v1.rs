//! Receiver noise integration (port of `signal/filters.py` and
//! `equalization/search.py` `_rx_ffe_frequency_response` /
//! `_receiver_noise`).
//!
//! Ported from agent-com (MIT source, P5-04o source map): the
//! Bessel-Thomson / Butterworth / raised-cosine frequency filters,
//! the RxFFE frequency response, and the eta_0 plus AC_CM_RMS
//! receiver-noise integration. The crosstalk-noise integration and
//! the search loop remain separate scopes.

use sipi_types::Complex64;

use crate::equalizer_frontend_v1::{complex_div, complex_mul};
use crate::search_support_v1::{CtleParamsV1, SearchErrorV1, ctle_frequency_response_v1};

/// Explicit scope policy of the receiver noise stage.
pub const RECEIVER_NOISE_POLICY_V1: &str = "sipi.p5-04o.receiver-noise-v1.filters-eta0-accm";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum NoiseErrorV1 {
    InvalidFilterControls,
    InvalidFrequencyAxis,
    FrequencyTooShort,
    AccmChannelMismatch,
    AccmFrequencyRange,
    AccmRequiresChannel,
    SearchErrorVariant,
}

impl From<SearchErrorV1> for NoiseErrorV1 {
    fn from(_: SearchErrorV1) -> Self {
        NoiseErrorV1::SearchErrorVariant
    }
}

pub(crate) fn complex_add(a: Complex64, b: Complex64) -> Complex64 {
    Complex64::try_new(a.real() + b.real(), a.imaginary() + b.imaginary()).expect("complex")
}

fn polyval_complex(coefficients: &[f64], z: Complex64) -> Complex64 {
    let mut result = Complex64::try_new(0.0, 0.0).expect("complex");
    for coefficient in coefficients {
        result = complex_add(
            complex_mul(result, z),
            Complex64::try_new(*coefficient, 0.0).expect("complex"),
        );
    }
    result
}

fn factorial(value: usize) -> f64 {
    (1..=value).fold(1.0_f64, |acc, item| acc * item as f64)
}

fn frequency_axis(frequency_hz: &[f64]) -> Result<Vec<f64>, NoiseErrorV1> {
    let values: Vec<f64> = frequency_hz.to_vec();
    if values.is_empty() || values.iter().any(|value| *value < 0.0) {
        return Err(NoiseErrorV1::InvalidFrequencyAxis);
    }
    Ok(values)
}

/// Port of `bessel_thomson_filter` (r4.80 lines 907-914).
pub fn bessel_thomson_filter_v1(
    frequency_hz: &[f64],
    order: usize,
    cutoff_multiplier: f64,
    baud_hz: f64,
    enabled: bool,
) -> Result<Vec<Complex64>, NoiseErrorV1> {
    let frequency = frequency_axis(frequency_hz)?;
    if !enabled {
        return Ok(vec![
            Complex64::try_new(1.0, 0.0).expect("complex");
            frequency.len()
        ]);
    }
    if cutoff_multiplier <= 0.0 || baud_hz <= 0.0 {
        return Err(NoiseErrorV1::InvalidFilterControls);
    }
    let mut coefficients = Vec::with_capacity(order + 1);
    for index in 0..=order {
        let numerator = factorial(2 * order - index);
        let denominator =
            2.0_f64.powi((order - index) as i32) * factorial(index) * factorial(order - index);
        coefficients.push(numerator / denominator);
    }
    let reversed: Vec<f64> = coefficients.iter().rev().copied().collect();
    Ok(frequency
        .iter()
        .map(|value| {
            let z =
                Complex64::try_new(0.0, *value / (cutoff_multiplier * baud_hz)).expect("complex");
            let denominator = polyval_complex(&reversed, z);
            complex_div(
                Complex64::try_new(coefficients[0], 0.0).expect("complex"),
                denominator,
            )
        })
        .collect())
}

/// Port of `butterworth_filter` (fourth-order, r4.80 lines 1015-1020).
pub fn butterworth_filter_v1(
    frequency_hz: &[f64],
    cutoff_multiplier: f64,
    baud_hz: f64,
    enabled: bool,
) -> Result<Vec<Complex64>, NoiseErrorV1> {
    let frequency = frequency_axis(frequency_hz)?;
    if !enabled {
        return Ok(vec![
            Complex64::try_new(1.0, 0.0).expect("complex");
            frequency.len()
        ]);
    }
    if cutoff_multiplier <= 0.0 || baud_hz <= 0.0 {
        return Err(NoiseErrorV1::InvalidFilterControls);
    }
    let coefficients = [1.0, 2.613126, 3.414214, 2.613126, 1.0];
    Ok(frequency
        .iter()
        .map(|value| {
            let z =
                Complex64::try_new(0.0, *value / (cutoff_multiplier * baud_hz)).expect("complex");
            let denominator = polyval_complex(&coefficients, z);
            complex_div(Complex64::try_new(1.0, 0.0).expect("complex"), denominator)
        })
        .collect())
}

/// Port of `tukey_window` (r4.80 lines 3087-3101).
pub fn tukey_window_v1(
    frequency_hz: &[f64],
    start_hz: f64,
    end_hz: f64,
) -> Result<Vec<f64>, NoiseErrorV1> {
    let frequency = frequency_axis(frequency_hz)?;
    if !(end_hz > start_hz) {
        return Err(NoiseErrorV1::InvalidFilterControls);
    }
    let period = 2.0 * (end_hz - start_hz);
    Ok(frequency
        .iter()
        .map(|value| {
            if *value < start_hz {
                1.0
            } else if *value <= end_hz {
                0.5 * (2.0 * std::f64::consts::PI * (*value - end_hz) / period
                    - std::f64::consts::PI)
                    .cos()
                    + 0.5
            } else {
                0.0
            }
        })
        .collect())
}

/// Port of `raised_cosine_filter`.
pub fn raised_cosine_filter_v1(
    frequency_hz: &[f64],
    start_hz: f64,
    end_hz: f64,
    enabled: bool,
) -> Result<Vec<f64>, NoiseErrorV1> {
    if !enabled {
        return Ok(vec![1.0; frequency_hz.len()]);
    }
    tukey_window_v1(frequency_hz, start_hz, end_hz)
}

/// Port of `_rx_ffe_frequency_response` (sum of UI-spaced phasors).
pub fn rx_ffe_frequency_response_v1(
    frequency_hz: &[f64],
    taps: &[f64],
    precursor_count: usize,
    baud_hz: f64,
) -> Result<Vec<Complex64>, NoiseErrorV1> {
    let frequency = frequency_axis(frequency_hz)?;
    if taps.is_empty() || baud_hz <= 0.0 {
        return Err(NoiseErrorV1::InvalidFilterControls);
    }
    if precursor_count >= taps.len() {
        return Err(NoiseErrorV1::InvalidFilterControls);
    }
    // Source offsets are arange(size) - precursor_count (a global phase
    // versus the conventional cursor-centered form; magnitude-squared
    // integrations are identical).
    let mut result = vec![Complex64::try_new(0.0, 0.0).expect("complex"); frequency.len()];
    for (index, coefficient) in taps.iter().enumerate() {
        if *coefficient == 0.0 {
            continue;
        }
        let shift = index as i64 - precursor_count as i64;
        for (point, value) in frequency.iter().enumerate() {
            let angle = -2.0 * std::f64::consts::PI * shift as f64 * value / baud_hz;
            let term = Complex64::try_new(angle.cos(), angle.sin()).expect("complex");
            result[point] = complex_add(
                result[point],
                Complex64::try_new(*coefficient * term.real(), *coefficient * term.imaginary())
                    .expect("complex"),
            );
        }
    }
    Ok(result)
}

/// The receiver-noise options surface.
#[derive(Clone, Debug, PartialEq)]
pub struct ReceiverNoiseOptionsV1 {
    pub bessel_thomson: bool,
    pub butterworth: bool,
    pub raised_cosine: bool,
    pub use_eta0_psd: bool,
    pub wc_portz: bool,
    pub pkg_len_select: Vec<i64>,
}

/// Port of `_receiver_noise`: eta_0 plus optional AC_CM_RMS components.
pub fn receiver_noise_v1(
    frequency_hz: &[f64],
    ctle_index: usize,
    high_pass_index: usize,
    high_pass_gain_db: f64,
    parameters: &ReceiverNoiseParamsV1,
    options: &ReceiverNoiseOptionsV1,
    ac_common_mode_transfers: &[Vec<Complex64>],
    package_case_index: usize,
    rx_ffe_taps: Option<&[f64]>,
    rx_ffe_precursor_count: Option<usize>,
    include_accm: bool,
) -> Result<f64, NoiseErrorV1> {
    let frequency = frequency_axis(frequency_hz)?;
    let baud_hz = parameters.fb;
    let h_r_bt = bessel_thomson_filter_v1(
        &frequency,
        parameters.btorder,
        parameters.fb_bt_cutoff,
        baud_hz,
        options.bessel_thomson,
    )?;
    let h_r_bw = butterworth_filter_v1(
        &frequency,
        parameters.fb_bw_cutoff,
        baud_hz,
        options.butterworth,
    )?;
    let h_r_rc = raised_cosine_filter_v1(
        &frequency,
        parameters.rc_start,
        parameters.rc_end,
        options.raised_cosine,
    )?;
    let h_r: Vec<Complex64> = frequency
        .iter()
        .enumerate()
        .map(|(index, _)| {
            complex_mul(
                complex_mul(h_r_bt[index], h_r_bw[index]),
                Complex64::try_new(h_r_rc[index], 0.0).expect("complex"),
            )
        })
        .collect();
    let ctle_params = CtleParamsV1 {
        ctle_gdc_values: parameters.ctle_gdc_values.clone(),
        ctle_fz: parameters.ctle_fz.clone(),
        ctle_fp1: parameters.ctle_fp1.clone(),
        ctle_fp2: parameters.ctle_fp2.clone(),
        ctle_type: parameters.ctle_type.clone(),
        f_hp: parameters.f_hp.clone(),
        f_hp_z: parameters.f_hp_z.clone(),
        f_hp_p: parameters.f_hp_p.clone(),
    };
    let h_ctf = ctle_frequency_response_v1(
        &frequency,
        ctle_index,
        high_pass_index,
        high_pass_gain_db,
        &ctle_params,
    )?;
    match (rx_ffe_taps, rx_ffe_precursor_count) {
        (None, None) => {}
        (Some(_), Some(_)) => {}
        _ => return Err(NoiseErrorV1::InvalidFilterControls),
    }
    let h_rx_ffe: Vec<Complex64> = match rx_ffe_taps {
        Some(taps) => rx_ffe_frequency_response_v1(
            &frequency,
            taps,
            rx_ffe_precursor_count.expect("count"),
            baud_hz,
        )?,
        None => vec![Complex64::try_new(1.0, 0.0).expect("complex"); frequency.len()],
    };
    let h_system_noise =
        crate::search_support_v1::system_noise_response_v1(&frequency, options.use_eta0_psd);
    let mut sum = 0.0_f64;
    for index in 1..frequency.len() {
        let magnitude = h_system_noise[index]
            * magnitude(h_r[index])
            * magnitude(h_ctf[index])
            * magnitude(h_rx_ffe[index]);
        sum += magnitude * magnitude * (frequency[index] - frequency[index - 1]) / 1e9;
    }
    let eta0 = (parameters.eta_0 * sum).sqrt();
    let ac_rms = crate::search_support_v1::selected_accm_rms_v1(
        &parameters.ac_cm_rms,
        &options.pkg_len_select,
        package_case_index,
    )?;
    if !include_accm || ac_rms == 0.0 {
        return Ok(eta0);
    }
    if ac_common_mode_transfers.is_empty() {
        return Err(NoiseErrorV1::AccmRequiresChannel);
    }
    // np.searchsorted(frequency, value, side='right')
    let end = frequency.partition_point(|value| *value <= parameters.accm_max_freq);
    if end < 2 {
        return Err(NoiseErrorV1::AccmFrequencyRange);
    }
    let integration_frequency = &frequency[..end];
    let mut components = Vec::new();
    for transfer in ac_common_mode_transfers {
        if transfer.len() != frequency.len() {
            return Err(NoiseErrorV1::AccmChannelMismatch);
        }
        let mut accm_sum = 0.0_f64;
        for index in 1..end {
            let factor = h_system_noise[index]
                * magnitude(h_r[index])
                * magnitude(h_ctf[index])
                * magnitude(h_rx_ffe[index]);
            let dc = magnitude(transfer[index]);
            accm_sum += factor
                * dc
                * factor
                * dc
                * (integration_frequency[index] - integration_frequency[index - 1]);
        }
        let value = 2.0 * ac_rms * ac_rms * accm_sum;
        components.push((value / integration_frequency[end - 1]).sqrt());
    }
    let total = eta0 * eta0 + components.iter().map(|value| value * value).sum::<f64>();
    Ok(total.sqrt())
}

fn magnitude(value: Complex64) -> f64 {
    value.real().hypot(value.imaginary())
}

/// The receiver-noise parameter surface.
#[derive(Clone, Debug, PartialEq)]
pub struct ReceiverNoiseParamsV1 {
    pub fb: f64,
    pub btorder: usize,
    pub fb_bt_cutoff: f64,
    pub fb_bw_cutoff: f64,
    pub rc_start: f64,
    pub rc_end: f64,
    pub eta_0: f64,
    pub accm_max_freq: f64,
    pub ac_cm_rms: Vec<f64>,
    pub ctle_gdc_values: Vec<f64>,
    pub ctle_fz: Vec<f64>,
    pub ctle_fp1: Vec<f64>,
    pub ctle_fp2: Vec<f64>,
    pub ctle_type: String,
    pub f_hp: Vec<f64>,
    pub f_hp_z: Vec<f64>,
    pub f_hp_p: Vec<f64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bessel_known_response() {
        let frequency = vec![0.0, 10e9, 20e9];
        let response = bessel_thomson_filter_v1(&frequency, 3, 0.75, 53.125e9, true).expect("bt");
        assert_eq!(response.len(), 3);
        assert!((response[0].real() - 1.0).abs() < 1e-9);
        assert!(response[0].imaginary().abs() < 1e-12);
        assert!(magnitude(response[2]) < magnitude(response[0]));
        let disabled = bessel_thomson_filter_v1(&frequency, 3, 0.75, 53.125e9, false).expect("off");
        assert!(
            disabled
                .iter()
                .all(|value| (value.real() - 1.0).abs() < 1e-12)
        );
    }

    #[test]
    fn butterworth_and_rc() {
        let frequency = vec![0.0, 5e9, 12e9];
        let bw = butterworth_filter_v1(&frequency, 0.75, 53.125e9, true).expect("bw");
        assert!((bw[0].real() - 1.0).abs() < 1e-9);
        let rc = raised_cosine_filter_v1(&frequency, 8e9, 12e9, true).expect("rc");
        assert_eq!(rc[0], 1.0);
        // end frequency: 0.5 * cos(-pi) + 0.5 = 0
        assert!((rc[2] - 0.0).abs() < 1e-12);
        let rc_off = raised_cosine_filter_v1(&frequency, 8e9, 12e9, false).expect("off");
        assert!(rc_off.iter().all(|value| *value == 1.0));
    }

    #[test]
    fn rx_ffe_response_phasors() {
        let frequency = vec![0.0, 1e9];
        let response = rx_ffe_frequency_response_v1(&frequency, &[0.5, 1.0, -0.25], 1, 53.125e9)
            .expect("rxffe");
        assert_eq!(response.len(), 2);
        // DC: sum of taps = 1.25 (offsets cancel at f = 0)
        assert!((response[0].real() - 1.25).abs() < 1e-12);
        assert!(response[0].imaginary().abs() < 1e-12);
    }

    #[test]
    fn receiver_noise_eta0_only() {
        let frequency: Vec<f64> = (0..64).map(|index| index as f64 * 1e9).collect();
        let parameters = ReceiverNoiseParamsV1 {
            fb: 53.125e9,
            btorder: 3,
            fb_bt_cutoff: 0.75,
            fb_bw_cutoff: 0.75,
            rc_start: 8e9,
            rc_end: 12e9,
            eta_0: 1e-3,
            accm_max_freq: 30e9,
            ac_cm_rms: vec![0.1],
            ctle_gdc_values: vec![6.0],
            ctle_fz: vec![10e9],
            ctle_fp1: vec![30e9],
            ctle_fp2: vec![40e9],
            ctle_type: "CL120e".to_string(),
            f_hp: vec![0.0],
            f_hp_z: vec![5e9],
            f_hp_p: vec![1e9],
        };
        let options = ReceiverNoiseOptionsV1 {
            bessel_thomson: true,
            butterworth: true,
            raised_cosine: true,
            use_eta0_psd: true,
            wc_portz: false,
            pkg_len_select: vec![1],
        };
        let noise = receiver_noise_v1(
            &frequency,
            0,
            0,
            0.0,
            &parameters,
            &options,
            &[],
            0,
            None,
            None,
            false,
        )
        .expect("noise");
        assert!(noise.is_finite() && noise > 0.0);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            RECEIVER_NOISE_POLICY_V1,
            "sipi.p5-04o.receiver-noise-v1.filters-eta0-accm",
        );
    }
}
