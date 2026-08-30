//! Crosstalk noise integration (port of `equalization/search.py`
//! `_crosstalk_noise` / `_td_source_crosstalk_noise`).
//!
//! Ported from agent-com (MIT source, P5-04p source map): the
//! frequency-domain FEXT/NEXT power integration with sinc-squared
//! weights and the TDMODE implicit-expansion outer-product path with
//! column-major linear consumption. The candidate evaluation and
//! search loop remain separate scopes.

use sipi_types::Complex64;

use crate::equalizer_frontend_v1::complex_mul;
use crate::receiver_noise_v1::complex_add;
use crate::receiver_noise_v1::{NoiseErrorV1, rx_ffe_frequency_response_v1};

/// Explicit scope policy of the crosstalk noise stage.
pub const CROSSTALK_NOISE_POLICY_V1: &str = "sipi.p5-04p.crosstalk-noise-v1.fext-next-integration";

/// Bound the TD source outer product before any downstream allocation or
/// indexed expansion. The limit is deliberately below the generic TD work
/// budget because this stage represents one response by one COM frequency
/// axis for every admitted channel.
pub const MAX_TD_CROSSTALK_CHANNELS_V1: usize = 64;
pub const MAX_TD_CROSSTALK_MATRIX_ELEMENTS_V1: usize = 8_388_608;
pub const MAX_TD_CROSSTALK_MATRIX_BYTES_V1: usize =
    MAX_TD_CROSSTALK_MATRIX_ELEMENTS_V1 * std::mem::size_of::<f64>();

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum XtalkErrorV1 {
    FrequencyTooShort,
    RxFfePairing,
    AxisMismatch,
    Oversize,
    UnsupportedRole,
    TdRxffeUncertified,
    EmptyTdResponse,
    InvalidControls,
}

impl From<NoiseErrorV1> for XtalkErrorV1 {
    fn from(_: NoiseErrorV1) -> Self {
        XtalkErrorV1::InvalidControls
    }
}

/// The crosstalk parameter surface.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct XtalkParamsV1 {
    pub fb: f64,
    pub f2: f64,
    pub sigma_x: f64,
}

/// One crosstalk channel: role (FEXT/NEXT), response, amplitude.
pub type XtalkChannelV1 = (String, Vec<Complex64>, f64);

/// Invocation-local data that is invariant over the TX-FFE grid for one
/// CTLE/high-pass candidate.  It deliberately owns all inputs it reuses, so
/// no state can escape a single search invocation or be shared across runs.
#[derive(Clone, Debug)]
pub(crate) struct PreparedCrosstalkNoiseV1 {
    frequency_hz: Vec<f64>,
    fb_hz: f64,
    f2_hz: f64,
    sigma_x: f64,
    sinc: Vec<f64>,
    rx_magnitude: Vec<f64>,
    fext_channel_power: Vec<(Vec<f64>, f64)>,
    next_power: f64,
    index_f2: usize,
}

fn magnitude(value: Complex64) -> f64 {
    value.real().hypot(value.imaginary())
}

pub(crate) fn prepare_crosstalk_noise_v1(
    frequency: &[f64],
    h_ctf: &[Complex64],
    channels: &[XtalkChannelV1],
    parameters: &XtalkParamsV1,
    rx_ffe_taps: Option<&[f64]>,
    rx_ffe_precursor_count: Option<usize>,
) -> Result<Option<PreparedCrosstalkNoiseV1>, XtalkErrorV1> {
    if channels.is_empty() {
        return Ok(None);
    }
    validate_crosstalk_inputs_v1(frequency, h_ctf, channels, parameters)?;
    let index_f2 = frequency.partition_point(|value| *value <= parameters.fb);
    if index_f2 == 0 {
        return Ok(None);
    }
    if frequency.len() < 11 {
        return Err(XtalkErrorV1::FrequencyTooShort);
    }
    let h_rx_ffe = receiver_response_v1(
        frequency,
        rx_ffe_taps,
        rx_ffe_precursor_count,
        parameters.fb,
    )?;
    let sinc = frequency
        .iter()
        .map(|value| sinc_v1(*value, parameters.fb))
        .collect::<Vec<_>>();
    let rx_magnitude = h_rx_ffe.into_iter().map(magnitude).collect::<Vec<_>>();
    let scale = 2.0 * (frequency[10] - frequency[9]) / parameters.f2;
    let mut fext_channel_power = Vec::new();
    let mut next_power = 0.0;
    for (role, response, amplitude) in channels {
        let channel_power = response
            .iter()
            .zip(h_ctf)
            .map(|(response, h_ctf)| {
                let product = complex_mul(*response, *h_ctf);
                let magnitude = magnitude(product);
                magnitude * magnitude
            })
            .collect::<Vec<_>>();
        match role.as_str() {
            "FEXT" => fext_channel_power.push((channel_power, *amplitude)),
            "NEXT" => {
                let mut sum = 0.0;
                for index in 0..index_f2 {
                    let weight = sinc[index] * sinc[index] * rx_magnitude[index];
                    sum += weight * channel_power[index];
                }
                next_power += scale * amplitude * amplitude * sum;
            }
            _ => return Err(XtalkErrorV1::UnsupportedRole),
        }
    }
    Ok(Some(PreparedCrosstalkNoiseV1 {
        frequency_hz: frequency.to_vec(),
        fb_hz: parameters.fb,
        f2_hz: parameters.f2,
        sigma_x: parameters.sigma_x,
        sinc,
        rx_magnitude,
        fext_channel_power,
        next_power,
        index_f2,
    }))
}

impl PreparedCrosstalkNoiseV1 {
    pub(crate) fn evaluate(&self, taps: &[f64]) -> Result<f64, XtalkErrorV1> {
        let tx_magnitude = tx_filter_magnitude_v1(&self.frequency_hz, taps, self.fb_hz);
        self.evaluate_with_tx_magnitude(&tx_magnitude)
    }

    /// Reuses a caller-owned TX response that was prepared once for a stable
    /// TX-FFE grid.  The response is independent of CTLE/high-pass and of
    /// package-case noise, while this object retains the pair-local channel
    /// side of the integral.
    pub(crate) fn evaluate_with_tx_magnitude(
        &self,
        tx_magnitude: &[f64],
    ) -> Result<f64, XtalkErrorV1> {
        if tx_magnitude.len() != self.frequency_hz.len()
            || tx_magnitude
                .iter()
                .any(|value| !value.is_finite() || *value < 0.0)
        {
            return Err(XtalkErrorV1::AxisMismatch);
        }
        let scale = 2.0 * (self.frequency_hz[10] - self.frequency_hz[9]) / self.f2_hz;
        let mut fext_power = 0.0;
        for (channel_power, amplitude) in &self.fext_channel_power {
            let mut sum = 0.0;
            for index in 0..self.index_f2 {
                let weight = self.sinc[index]
                    * self.sinc[index]
                    * tx_magnitude[index]
                    * self.rx_magnitude[index];
                sum += weight * channel_power[index];
            }
            fext_power += scale * amplitude * amplitude * sum;
        }
        Ok((fext_power + self.next_power).sqrt() * self.sigma_x)
    }
}

fn validate_crosstalk_inputs_v1(
    frequency: &[f64],
    h_ctf: &[Complex64],
    channels: &[XtalkChannelV1],
    parameters: &XtalkParamsV1,
) -> Result<(), XtalkErrorV1> {
    if !parameters.fb.is_finite()
        || parameters.fb <= 0.0
        || !parameters.f2.is_finite()
        || parameters.f2 <= 0.0
        || !parameters.sigma_x.is_finite()
        || parameters.sigma_x < 0.0
    {
        return Err(XtalkErrorV1::InvalidControls);
    }
    if channels.len() > MAX_TD_CROSSTALK_CHANNELS_V1 {
        return Err(XtalkErrorV1::Oversize);
    }
    if frequency.len() != h_ctf.len()
        || channels
            .iter()
            .any(|(_, response, _)| response.len() != frequency.len())
    {
        return Err(XtalkErrorV1::AxisMismatch);
    }
    Ok(())
}

fn sinc_v1(frequency_hz: f64, fb_hz: f64) -> f64 {
    let angle = std::f64::consts::PI * frequency_hz / fb_hz;
    if angle == 0.0 {
        1.0
    } else {
        angle.sin() / angle
    }
}

fn receiver_response_v1(
    frequency: &[f64],
    rx_ffe_taps: Option<&[f64]>,
    rx_ffe_precursor_count: Option<usize>,
    fb_hz: f64,
) -> Result<Vec<Complex64>, XtalkErrorV1> {
    match (rx_ffe_taps, rx_ffe_precursor_count) {
        (None, None) => Ok(vec![
            Complex64::try_new(1.0, 0.0).expect("complex");
            frequency.len()
        ]),
        (Some(taps), Some(precursor_count)) => {
            rx_ffe_frequency_response_v1(frequency, taps, precursor_count, fb_hz)
                .map_err(Into::into)
        }
        _ => Err(XtalkErrorV1::RxFfePairing),
    }
}

pub(crate) fn tx_filter_magnitude_v1(frequency: &[f64], taps: &[f64], fb_hz: f64) -> Vec<f64> {
    let main_index = argmax_first(taps);
    frequency
        .iter()
        .map(|value| {
            let mut filter = Complex64::try_new(0.0, 0.0).expect("complex");
            for (index, coefficient) in taps.iter().enumerate() {
                if *coefficient == 0.0 {
                    continue;
                }
                let shift = index as i64 - main_index as i64;
                let angle = -2.0 * std::f64::consts::PI * shift as f64 * value / fb_hz;
                let term = Complex64::try_new(angle.cos(), angle.sin()).expect("complex");
                filter = complex_add(
                    filter,
                    Complex64::try_new(*coefficient * term.real(), *coefficient * term.imaginary())
                        .expect("complex"),
                );
            }
            magnitude(filter)
        })
        .collect()
}

/// Port of `_crosstalk_noise` (frequency-domain integration).
pub fn crosstalk_noise_v1(
    frequency: &[f64],
    h_ctf: &[Complex64],
    taps: &[f64],
    channels: &[XtalkChannelV1],
    parameters: &XtalkParamsV1,
    td_source_outer_product: bool,
    rx_ffe_taps: Option<&[f64]>,
    rx_ffe_precursor_count: Option<usize>,
) -> Result<f64, XtalkErrorV1> {
    if channels.is_empty() {
        return Ok(0.0);
    }
    if !parameters.fb.is_finite()
        || parameters.fb <= 0.0
        || !parameters.f2.is_finite()
        || parameters.f2 <= 0.0
        || !parameters.sigma_x.is_finite()
        || parameters.sigma_x < 0.0
    {
        return Err(XtalkErrorV1::InvalidControls);
    }
    if channels.len() > MAX_TD_CROSSTALK_CHANNELS_V1 {
        return Err(XtalkErrorV1::Oversize);
    }
    if frequency.len() != h_ctf.len() {
        return Err(XtalkErrorV1::AxisMismatch);
    }
    let index_f2 = frequency.partition_point(|value| *value <= parameters.fb);
    if index_f2 == 0 {
        return Ok(0.0);
    }
    let main_index = argmax_first(taps);
    let mut tx_filter = vec![Complex64::try_new(0.0, 0.0).expect("complex"); frequency.len()];
    for (index, coefficient) in taps.iter().enumerate() {
        if *coefficient == 0.0 {
            continue;
        }
        let shift = index as i64 - main_index as i64;
        for (point, value) in frequency.iter().enumerate() {
            let angle = -2.0 * std::f64::consts::PI * shift as f64 * value / parameters.fb;
            let term = Complex64::try_new(angle.cos(), angle.sin()).expect("complex");
            tx_filter[point] = complex_add(
                tx_filter[point],
                Complex64::try_new(*coefficient * term.real(), *coefficient * term.imaginary())
                    .expect("complex"),
            );
        }
    }
    let sinc: Vec<f64> = frequency
        .iter()
        .map(|value| {
            let angle = std::f64::consts::PI * value / parameters.fb;
            if angle == 0.0 {
                1.0
            } else {
                angle.sin() / angle
            }
        })
        .collect();
    if frequency.len() < 11 {
        return Err(XtalkErrorV1::FrequencyTooShort);
    }
    match (rx_ffe_taps, rx_ffe_precursor_count) {
        (None, None) => {}
        (Some(_), Some(_)) => {}
        _ => return Err(XtalkErrorV1::RxFfePairing),
    }
    let h_rx_ffe: Vec<Complex64> = match rx_ffe_taps {
        Some(taps_rx) => rx_ffe_frequency_response_v1(
            frequency,
            taps_rx,
            rx_ffe_precursor_count.expect("count"),
            parameters.fb,
        )?,
        None => vec![Complex64::try_new(1.0, 0.0).expect("complex"); frequency.len()],
    };
    let delta_f = frequency[10] - frequency[9];
    if td_source_outer_product {
        if rx_ffe_taps.is_some() {
            return Err(XtalkErrorV1::TdRxffeUncertified);
        }
        return td_source_crosstalk_noise_v1(
            frequency, h_ctf, &tx_filter, &sinc, channels, parameters,
        );
    }
    let mut fext_power = 0.0_f64;
    let mut next_power = 0.0_f64;
    for (role, response, amplitude) in channels {
        if response.len() != frequency.len() {
            return Err(XtalkErrorV1::AxisMismatch);
        }
        let mut channel_power = vec![0.0_f64; frequency.len()];
        for index in 0..frequency.len() {
            let product = complex_mul(response[index], h_ctf[index]);
            channel_power[index] = magnitude(product) * magnitude(product);
        }
        match role.as_str() {
            "FEXT" => {
                let mut sum = 0.0_f64;
                for index in 0..index_f2 {
                    let weight = sinc[index]
                        * sinc[index]
                        * magnitude(tx_filter[index])
                        * magnitude(h_rx_ffe[index]);
                    sum += weight * channel_power[index];
                }
                fext_power += 2.0 * delta_f / parameters.f2 * amplitude * amplitude * sum;
            }
            "NEXT" => {
                let mut sum = 0.0_f64;
                for index in 0..index_f2 {
                    let weight = sinc[index] * sinc[index] * magnitude(h_rx_ffe[index]);
                    sum += weight * channel_power[index];
                }
                next_power += 2.0 * delta_f / parameters.f2 * amplitude * amplitude * sum;
            }
            other => return Err(XtalkErrorV1::UnsupportedRole.with_role(other)),
        }
    }
    Ok((fext_power + next_power).sqrt() * parameters.sigma_x)
}

fn argmax_first(values: &[f64]) -> usize {
    let mut best = 0usize;
    for index in 1..values.len() {
        if values[index] > values[best] {
            best = index;
        }
    }
    best
}

/// Port of `_td_source_crosstalk_noise` (TDMODE outer-product path).
pub fn td_source_crosstalk_noise_v1(
    frequency: &[f64],
    h_ctf: &[Complex64],
    tx_filter: &[Complex64],
    sinc: &[f64],
    channels: &[XtalkChannelV1],
    parameters: &XtalkParamsV1,
) -> Result<f64, XtalkErrorV1> {
    if !parameters.fb.is_finite()
        || parameters.fb <= 0.0
        || !parameters.f2.is_finite()
        || parameters.f2 <= 0.0
        || !parameters.sigma_x.is_finite()
        || parameters.sigma_x < 0.0
    {
        return Err(XtalkErrorV1::InvalidControls);
    }
    if frequency.len() < 11 {
        return Err(XtalkErrorV1::FrequencyTooShort);
    }
    if frequency.len() != h_ctf.len()
        || frequency.len() != tx_filter.len()
        || frequency.len() != sinc.len()
    {
        return Err(XtalkErrorV1::AxisMismatch);
    }
    if channels.is_empty() || channels.len() > MAX_TD_CROSSTALK_CHANNELS_V1 {
        return if channels.is_empty() {
            Ok(0.0)
        } else {
            Err(XtalkErrorV1::Oversize)
        };
    }
    let first_above = frequency.iter().position(|value| *value > parameters.fb);
    let count = match first_above {
        None => frequency.len(),
        Some(index) => index + 1,
    };
    if count == 0 {
        return Ok(0.0);
    }
    let response_row_count = channels
        .first()
        .map(|(_, response, _)| response.len())
        .unwrap_or(0);
    if response_row_count == 0 {
        return Err(XtalkErrorV1::EmptyTdResponse);
    }
    checked_td_outer_product_budget_v1(response_row_count, h_ctf.len())?;
    for (_, response, _) in channels {
        if response.len() != response_row_count {
            return Err(XtalkErrorV1::AxisMismatch);
        }
    }
    let weight_fext: Vec<f64> = (0..count)
        .map(|index| sinc[index] * sinc[index] * magnitude(tx_filter[index]))
        .collect();
    let weight_next: Vec<f64> = (0..count).map(|index| sinc[index] * sinc[index]).collect();
    let mut fext_sum = 0.0_f64;
    let mut next_sum = 0.0_f64;
    let mut fext_amplitude = 0.0_f64;
    let mut next_amplitude = 0.0_f64;
    // The upstream reshapes the outer product in Fortran order and consumes
    // only the first `count` entries. Stream those entries directly so the
    // public result is unchanged without allocating the full matrix. The
    // accumulation order is intentionally element-major: channels of one
    // role are combined before the weight is applied, matching NumPy's
    // matrix sum followed by the weighted reduction.
    for index in 0..count {
        let mut fext_element = 0.0_f64;
        let mut next_element = 0.0_f64;
        for (role, response, amplitude) in channels {
            let row = index % response_row_count;
            let column = index / response_row_count;
            let product = complex_mul(response[row], h_ctf[column]);
            let magnitude_squared = magnitude(product) * magnitude(product);
            match role.as_str() {
                "FEXT" => {
                    fext_element += magnitude_squared;
                    fext_amplitude = *amplitude;
                }
                "NEXT" => {
                    next_element += magnitude_squared;
                    next_amplitude = *amplitude;
                }
                other => return Err(XtalkErrorV1::UnsupportedRole.with_role(other)),
            }
        }
        if fext_element != 0.0 {
            fext_sum += weight_fext[index] * fext_element;
        }
        if next_element != 0.0 {
            next_sum += weight_next[index] * next_element;
        }
    }
    let delta_f = frequency[10] - frequency[9];
    let fext_power = 2.0 * delta_f / parameters.f2 * fext_amplitude * fext_amplitude * fext_sum;
    let next_power = 2.0 * delta_f / parameters.f2 * next_amplitude * next_amplitude * next_sum;
    Ok((fext_power + next_power).sqrt() * parameters.sigma_x)
}

fn checked_td_outer_product_budget_v1(rows: usize, columns: usize) -> Result<(), XtalkErrorV1> {
    let elements = rows.checked_mul(columns).ok_or(XtalkErrorV1::Oversize)?;
    let bytes = elements
        .checked_mul(std::mem::size_of::<f64>())
        .ok_or(XtalkErrorV1::Oversize)?;
    if elements > MAX_TD_CROSSTALK_MATRIX_ELEMENTS_V1 || bytes > MAX_TD_CROSSTALK_MATRIX_BYTES_V1 {
        return Err(XtalkErrorV1::Oversize);
    }
    Ok(())
}

/// Error with the unsupported role name attached for diagnostics.
trait WithRole {
    fn with_role(self, role: &str) -> Self;
}

impl WithRole for XtalkErrorV1 {
    fn with_role(self, _role: &str) -> Self {
        XtalkErrorV1::UnsupportedRole
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn complex(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).expect("complex")
    }

    #[test]
    fn empty_channels_zero() {
        let frequency: Vec<f64> = (0..32).map(|index| index as f64 * 1e9).collect();
        let h_ctf: Vec<Complex64> = (0..32)
            .map(|index| complex(1.0, index as f64 * 1e-3))
            .collect();
        let parameters = XtalkParamsV1 {
            fb: 26.5625e9,
            f2: 26.5625e9,
            sigma_x: 0.03,
        };
        let noise = crosstalk_noise_v1(
            &frequency,
            &h_ctf,
            &[1.0],
            &[],
            &parameters,
            false,
            None,
            None,
        )
        .expect("noise");
        assert_eq!(noise, 0.0);
    }

    #[test]
    fn fext_next_integration() {
        let frequency: Vec<f64> = (0..32).map(|index| index as f64 * 1e9).collect();
        let h_ctf: Vec<Complex64> = frequency
            .iter()
            .map(|value| complex(1.0, value * 1e-11))
            .collect();
        let fext: Vec<Complex64> = frequency
            .iter()
            .map(|value| complex(0.5 * value.cos(), 0.0))
            .collect();
        let next: Vec<Complex64> = frequency
            .iter()
            .map(|value| complex(0.3 * value.sin(), 0.0))
            .collect();
        let parameters = XtalkParamsV1 {
            fb: 26.5625e9,
            f2: 26.5625e9,
            sigma_x: 0.03,
        };
        let channels = vec![
            ("FEXT".to_string(), fext, 0.5),
            ("NEXT".to_string(), next, 0.4),
        ];
        let noise = crosstalk_noise_v1(
            &frequency,
            &h_ctf,
            &[0.5, 1.0, -0.25],
            &channels,
            &parameters,
            false,
            None,
            None,
        )
        .expect("noise");
        assert!(noise.is_finite() && noise > 0.0);
    }

    #[test]
    fn prepared_noise_matches_legacy_bit_exactly() {
        let frequency: Vec<f64> = (0..32).map(|index| index as f64 * 1e9).collect();
        let h_ctf: Vec<Complex64> = frequency
            .iter()
            .map(|value| complex(1.0, value * 1e-11))
            .collect();
        let channels = vec![
            (
                "FEXT".to_string(),
                frequency
                    .iter()
                    .map(|value| complex(0.5 * value.cos(), 0.0))
                    .collect(),
                0.5,
            ),
            (
                "NEXT".to_string(),
                frequency
                    .iter()
                    .map(|value| complex(0.3 * value.sin(), 0.0))
                    .collect(),
                0.4,
            ),
        ];
        let parameters = XtalkParamsV1 {
            fb: 26.5625e9,
            f2: 26.5625e9,
            sigma_x: 0.03,
        };
        let taps = [0.5, 1.0, -0.25];
        let legacy = crosstalk_noise_v1(
            &frequency,
            &h_ctf,
            &taps,
            &channels,
            &parameters,
            false,
            None,
            None,
        )
        .expect("legacy");
        let prepared =
            prepare_crosstalk_noise_v1(&frequency, &h_ctf, &channels, &parameters, None, None)
                .expect("prepare")
                .expect("nonempty");
        let direct = prepared.evaluate(&taps).expect("prepared");
        let precomputed = prepared
            .evaluate_with_tx_magnitude(&tx_filter_magnitude_v1(&frequency, &taps, parameters.fb))
            .expect("precomputed");
        assert_eq!(direct.to_bits(), legacy.to_bits());
        assert_eq!(precomputed.to_bits(), legacy.to_bits());
    }

    #[test]
    fn td_outer_product_path() {
        let frequency: Vec<f64> = (0..32).map(|index| index as f64 * 1e9).collect();
        let h_ctf: Vec<Complex64> = frequency
            .iter()
            .map(|value| complex(1.0, value * 1e-11))
            .collect();
        let tx_filter: Vec<Complex64> = frequency
            .iter()
            .map(|value| complex(value.cos(), value.sin()))
            .collect();
        let sinc: Vec<f64> = frequency
            .iter()
            .map(|value| {
                let angle = std::f64::consts::PI * value / 26.5625e9;
                if angle == 0.0 {
                    1.0
                } else {
                    angle.sin() / angle
                }
            })
            .collect();
        let fext: Vec<Complex64> = frequency
            .iter()
            .map(|value| complex(0.4 * value.cos(), 0.1))
            .collect();
        let parameters = XtalkParamsV1 {
            fb: 26.5625e9,
            f2: 26.5625e9,
            sigma_x: 0.03,
        };
        let channels = vec![("FEXT".to_string(), fext, 0.5)];
        let noise = td_source_crosstalk_noise_v1(
            &frequency,
            &h_ctf,
            &tx_filter,
            &sinc,
            &channels,
            &parameters,
        )
        .expect("noise");
        // Checkpoint from the pinned Agent-COM search.py outer-product
        // formula (source map records blob 58f6e5e3...); this is more than a
        // shape/self-finiteness check and freezes the FEXT amplitude/axis
        // ordering used by the direct TDMODE consumer.
        assert!((noise - 0.004441284617118329).abs() < 1.0e-15);
    }

    #[test]
    fn td_outer_product_accepts_the_channel_count_ceiling() {
        let frequency: Vec<f64> = (0..32).map(|index| index as f64 * 1e9).collect();
        let h_ctf = vec![complex(1.0, 0.0); frequency.len()];
        let tx_filter = vec![complex(1.0, 0.0); frequency.len()];
        let sinc = vec![1.0; frequency.len()];
        let response = vec![complex(0.25, 0.0); frequency.len()];
        let channels = (0..MAX_TD_CROSSTALK_CHANNELS_V1)
            .map(|index| {
                (
                    if index % 2 == 0 { "FEXT" } else { "NEXT" }.to_owned(),
                    response.clone(),
                    0.5,
                )
            })
            .collect::<Vec<_>>();
        let parameters = XtalkParamsV1 {
            fb: 26.5625e9,
            f2: 26.5625e9,
            sigma_x: 0.03,
        };
        let noise = td_source_crosstalk_noise_v1(
            &frequency,
            &h_ctf,
            &tx_filter,
            &sinc,
            &channels,
            &parameters,
        )
        .expect("64-channel outer product");
        assert!(noise.is_finite() && noise > 0.0);
    }

    #[test]
    fn td_outer_product_budget_rejects_overflow_channel_and_axis_mutations() {
        assert_eq!(
            checked_td_outer_product_budget_v1(usize::MAX, 2),
            Err(XtalkErrorV1::Oversize)
        );
        let too_many_channels = vec![
            ("FEXT".to_owned(), vec![complex(1.0, 0.0); 32], 0.5);
            MAX_TD_CROSSTALK_CHANNELS_V1 + 1
        ];
        let frequency: Vec<f64> = (0..32).map(|index| index as f64 * 1e9).collect();
        let axis = vec![complex(1.0, 0.0); frequency.len()];
        let parameters = XtalkParamsV1 {
            fb: 26.5625e9,
            f2: 26.5625e9,
            sigma_x: 0.03,
        };
        assert_eq!(
            td_source_crosstalk_noise_v1(
                &frequency,
                &axis,
                &axis,
                &vec![1.0; frequency.len()],
                &too_many_channels,
                &parameters,
            ),
            Err(XtalkErrorV1::Oversize)
        );

        let side = 2_897usize;
        let long_frequency: Vec<f64> = (0..side).map(|index| index as f64 * 1.0e6).collect();
        let long_axis = vec![complex(1.0, 0.0); side];
        let long_channel = vec![("FEXT".to_owned(), long_axis.clone(), 0.5)];
        assert_eq!(
            td_source_crosstalk_noise_v1(
                &long_frequency,
                &long_axis,
                &long_axis,
                &vec![1.0; side],
                &long_channel,
                &parameters,
            ),
            Err(XtalkErrorV1::Oversize)
        );
    }

    #[test]
    fn role_and_frequency_errors() {
        let frequency: Vec<f64> = (0..32).map(|index| index as f64 * 1e9).collect();
        let h_ctf: Vec<Complex64> = (0..32).map(|_index| complex(1.0, 0.0)).collect();
        let parameters = XtalkParamsV1 {
            fb: 26.5625e9,
            f2: 26.5625e9,
            sigma_x: 0.03,
        };
        let channels = vec![("XTLK".to_string(), h_ctf.clone(), 0.5)];
        assert!(
            crosstalk_noise_v1(
                &frequency,
                &h_ctf,
                &[1.0],
                &channels,
                &parameters,
                false,
                None,
                None
            )
            .is_err()
        );
        let short: Vec<f64> = (0..5).map(|index| index as f64 * 1e9).collect();
        assert!(
            crosstalk_noise_v1(
                &short,
                &h_ctf,
                &[1.0],
                &channels,
                &parameters,
                false,
                None,
                None
            )
            .is_err()
        );
        assert!(
            crosstalk_noise_v1(
                &frequency,
                &h_ctf,
                &[1.0],
                &channels,
                &parameters,
                false,
                Some(&[1.0]),
                None
            )
            .is_err()
        );
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            CROSSTALK_NOISE_POLICY_V1,
            "sipi.p5-04p.crosstalk-noise-v1.fext-next-integration",
        );
    }
}
