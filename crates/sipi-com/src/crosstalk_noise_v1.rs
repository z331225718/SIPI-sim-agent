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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum XtalkErrorV1 {
    FrequencyTooShort,
    RxFfePairing,
    AxisMismatch,
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

fn magnitude(value: Complex64) -> f64 {
    value.real().hypot(value.imaginary())
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
    let first_above = frequency.iter().position(|value| *value > parameters.fb);
    let count = match first_above {
        None => frequency.len(),
        Some(index) => index + 1,
    };
    if count == 0 {
        return Ok(0.0);
    }
    let weight_fext: Vec<f64> = (0..count)
        .map(|index| sinc[index] * sinc[index] * magnitude(tx_filter[index]))
        .collect();
    let weight_next: Vec<f64> = (0..count).map(|index| sinc[index] * sinc[index]).collect();
    let mut fext_matrix: Option<Vec<f64>> = None;
    let mut next_matrix: Option<Vec<f64>> = None;
    let mut fext_amplitude = 0.0_f64;
    let mut next_amplitude = 0.0_f64;
    let response_row_count = channels
        .first()
        .map(|(_, response, _)| response.len())
        .unwrap_or(0);
    for (role, response, amplitude) in channels {
        if response.is_empty() {
            return Err(XtalkErrorV1::EmptyTdResponse);
        }
        // Outer product: values[:, None] * h_ctf[None, :]
        let rows = response.len();
        let columns = h_ctf.len();
        let mut power = Vec::with_capacity(rows * columns);
        for row in 0..rows {
            for column in 0..columns {
                let product = complex_mul(response[row], h_ctf[column]);
                let magnitude_squared = magnitude(product) * magnitude(product);
                power.push(magnitude_squared);
            }
        }
        match role.as_str() {
            "FEXT" => {
                fext_matrix = Some(match fext_matrix {
                    Some(acc) => acc.iter().zip(power.iter()).map(|(a, b)| a + b).collect(),
                    None => power,
                });
                fext_amplitude = *amplitude;
            }
            "NEXT" => {
                next_matrix = Some(match next_matrix {
                    Some(acc) => acc.iter().zip(power.iter()).map(|(a, b)| a + b).collect(),
                    None => power,
                });
                next_amplitude = *amplitude;
            }
            other => return Err(XtalkErrorV1::UnsupportedRole.with_role(other)),
        }
    }
    let delta_f = frequency[10] - frequency[9];
    let mut fext_power = 0.0_f64;
    if let Some(matrix) = fext_matrix {
        // reshape(-1, order='F')[:count]: column-major flatten, first
        // count entries; element index -> (row = index % rows, column = index / rows).
        let rows = response_row_count;
        let columns = h_ctf.len();
        let mut sum = 0.0_f64;
        for index in 0..count {
            let row = index % rows;
            let column = index / rows;
            let value = matrix[row * columns + column];
            sum += weight_fext[index] * value;
        }
        fext_power = 2.0 * delta_f / parameters.f2 * fext_amplitude * fext_amplitude * sum;
    }
    let mut next_power = 0.0_f64;
    if let Some(matrix) = next_matrix {
        let rows = response_row_count;
        let columns = h_ctf.len();
        let mut sum = 0.0_f64;
        for index in 0..count {
            let row = index % rows;
            let column = index / rows;
            let value = matrix[row * columns + column];
            sum += weight_next[index] * value;
        }
        next_power = 2.0 * delta_f / parameters.f2 * next_amplitude * next_amplitude * sum;
    }
    Ok((fext_power + next_power).sqrt() * parameters.sigma_x)
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
        assert!(noise.is_finite() && noise > 0.0);
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
