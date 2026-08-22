use statrs::distribution::{ContinuousCDF, Normal};
use thiserror::Error;

use crate::{Seconds, Volts, linear_convolve};

#[derive(Debug, Clone, Copy)]
pub struct StatisticalEyeInputV1<'a> {
    /// UI pulse response before the Python reference implementation halves it
    /// for NRZ symbol levels.
    pub pulse_response: &'a [f64],
    pub ui: Seconds,
    pub nspui: usize,
    pub target_ber: f64,
    pub noise_sigma_v: Option<Volts>,
    pub horizontal_rj_ui: Option<f64>,
    pub horizontal_dj_ui: Option<f64>,
    pub tx_rj_ui: Option<f64>,
    pub tx_dj_ui: Option<f64>,
    pub tx_dcd_ui: Option<f64>,
    pub rx_rj_ui: Option<f64>,
    pub rx_dj_ui: Option<f64>,
    pub voltage_resolution: Option<Volts>,
    pub time_points: usize,
    pub max_distribution_states: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StatisticalEyeResultV1 {
    pub level0_v: f64,
    pub level1_v: f64,
    pub eye_height_v: f64,
    pub eye_width_ps: f64,
    pub height_at_ber_v: f64,
    pub width_at_ber_ps: f64,
    pub cursor_index: usize,
    pub decision_phase_offset_samples: isize,
    pub distribution_state_count: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StatisticalEyeContourV1 {
    pub ber: f64,
    pub height_v: f64,
    pub width_ps: f64,
    pub point_count: usize,
    pub x_ui: Vec<f64>,
    pub y_v: Vec<f64>,
}

#[derive(Debug, Error, PartialEq)]
pub enum StatisticalEyeError {
    #[error("pulse response must contain at least one finite sample")]
    InvalidPulse,
    #[error("UI must be finite and greater than zero")]
    InvalidUi,
    #[error("samples per UI must be greater than zero")]
    InvalidSamplesPerUi,
    #[error("target BER must be between 0 and 0.5")]
    InvalidTargetBer,
    #[error("voltage resolution must be finite and greater than zero")]
    InvalidVoltageResolution,
    #[error("vertical noise sigma must be finite and non-negative")]
    InvalidVerticalNoise,
    #[error("horizontal jitter values must be finite and non-negative")]
    InvalidHorizontalJitter,
    #[error("time points must be at least samples per UI")]
    InvalidTimePoints,
    #[error("maximum distribution states must be at least 8")]
    InvalidDistributionLimit,
    #[error("pulse response main cursor is zero")]
    ZeroMainCursor,
    #[error("ISI distribution exceeded maximum distribution states")]
    DistributionLimitExceeded,
    #[error("could not evaluate any statistical eye sampling phase")]
    NoSamplingPhase,
}

#[derive(Debug)]
struct Distribution {
    values: Vec<f64>,
    probabilities: Vec<f64>,
    cumulative_probabilities: Vec<f64>,
}

impl Distribution {
    fn new(values: Vec<f64>, probabilities: Vec<f64>) -> Self {
        let mut cumulative = 0.0;
        let cumulative_probabilities = probabilities
            .iter()
            .map(|probability| {
                cumulative += probability;
                cumulative
            })
            .collect();
        Self {
            values,
            probabilities,
            cumulative_probabilities,
        }
    }

    fn quantile(&self, probability: f64, sigma_v: f64) -> f64 {
        if sigma_v <= 0.0 {
            return discrete_quantile(&self.values, &self.probabilities, probability);
        }
        let normal = Normal::new(0.0, 1.0).expect("standard normal is valid");
        let tail = normal
            .inverse_cdf(probability)
            .abs()
            .max(normal.inverse_cdf(1.0 - probability).abs())
            .max(8.0);
        let mut lo = self.values[0] - (tail + 2.0) * sigma_v;
        let mut hi = self.values[self.values.len() - 1] + (tail + 2.0) * sigma_v;
        for _ in 0..90 {
            let mid = 0.5 * (lo + hi);
            if mixture_cdf(mid, self, sigma_v, &normal) < probability {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        0.5 * (lo + hi)
    }
}

pub fn calculate_statistical_eye(
    input: StatisticalEyeInputV1<'_>,
) -> Result<StatisticalEyeResultV1, StatisticalEyeError> {
    validate_input(input)?;

    let pulse = input
        .pulse_response
        .iter()
        .map(|sample| sample * 0.5)
        .collect::<Vec<_>>();
    let main_cursor_index = pulse
        .iter()
        .enumerate()
        .max_by(|(_, left), (_, right)| left.abs().total_cmp(&right.abs()))
        .map(|(index, _)| index)
        .expect("input validation guarantees a nonempty pulse");
    let raw_cursor = pulse[main_cursor_index];
    if raw_cursor == 0.0 {
        return Err(StatisticalEyeError::ZeroMainCursor);
    }
    let polarity = raw_cursor.signum();
    let normalized = pulse
        .iter()
        .map(|sample| sample * polarity)
        .collect::<Vec<_>>();
    let resolution = input.voltage_resolution.map_or_else(
        || normalized[main_cursor_index].abs().max(1.0) * 1.0e-5,
        |resolution| resolution.0,
    );
    let noise_sigma_v = input.noise_sigma_v.map_or(0.0, |noise| noise.0);

    let offsets = phase_offsets(input.nspui);
    let mut phase_results = Vec::with_capacity(offsets.len());
    for &offset in &offsets {
        let sample_index = main_cursor_index as isize + offset;
        if sample_index < 0 || sample_index as usize >= normalized.len() {
            phase_results.push(None);
            continue;
        }
        phase_results.push(phase_height(
            &normalized,
            input.nspui,
            sample_index as usize,
            resolution,
            input.target_ber,
            noise_sigma_v,
            input.max_distribution_states,
        )?);
    }

    let best_index = phase_results
        .iter()
        .enumerate()
        .filter_map(|(index, result)| result.map(|value| (index, value)))
        .max_by(|(left_index, left), (right_index, right)| {
            left.total_cmp(right)
                .then_with(|| offsets[*right_index].abs().cmp(&offsets[*left_index].abs()))
        })
        .map(|(index, _)| index)
        .ok_or(StatisticalEyeError::NoSamplingPhase)?;
    let decision_offset = offsets[best_index];
    let cursor_index = (main_cursor_index as isize + decision_offset) as usize;
    let (samples, cursor_position) = phase_samples(&normalized, input.nspui, cursor_index)
        .expect("selected phase was evaluated");
    let cursor_v = samples[cursor_position];
    let interferers = samples
        .iter()
        .enumerate()
        .filter_map(|(index, sample)| (index != cursor_position).then_some(*sample))
        .collect::<Vec<_>>();
    let distribution = distribution(&interferers, resolution, input.max_distribution_states)?;
    // Keep the deterministic opening independent of the quantized PDF grid
    // that serves the BER integration below.
    let eye_height = 2.0 * (cursor_v - interferers.iter().map(|tap| tap.abs()).sum::<f64>());
    let low_q = distribution.quantile(input.target_ber, noise_sigma_v);
    let high_q = distribution.quantile(1.0 - input.target_ber, noise_sigma_v);
    let mut height_at_ber = (cursor_v + low_q) - (-cursor_v + high_q);
    let width_ps = opening_width_ps(&offsets, &phase_results, input.ui, input.nspui, best_index);
    let mut width_at_ber_ps = width_ps;
    if input.has_horizontal_jitter() || input.has_tx_edge_jitter() {
        let contour = calculate_statistical_contours(input, &[input.target_ber])?
            .pop()
            .expect("one requested contour yields one result");
        height_at_ber = contour.height_v;
        width_at_ber_ps = contour.width_ps;
    }

    Ok(StatisticalEyeResultV1 {
        level0_v: -cursor_v,
        level1_v: cursor_v,
        eye_height_v: eye_height,
        eye_width_ps: width_ps,
        height_at_ber_v: height_at_ber,
        width_at_ber_ps,
        cursor_index,
        decision_phase_offset_samples: decision_offset,
        distribution_state_count: distribution.values.len(),
    })
}

/// Calculate receiver-sampling-jitter-aware NRZ contour scalars on a
/// fractional-phase BER surface. TX edge jitter remains Python-backed.
pub fn calculate_statistical_contours(
    input: StatisticalEyeInputV1<'_>,
    ber_values: &[f64],
) -> Result<Vec<StatisticalEyeContourV1>, StatisticalEyeError> {
    validate_input(input)?;
    if ber_values
        .iter()
        .any(|ber| !ber.is_finite() || !(0.0..0.5).contains(ber))
    {
        return Err(StatisticalEyeError::InvalidTargetBer);
    }

    let pulse = input
        .pulse_response
        .iter()
        .map(|sample| sample * 0.5)
        .collect::<Vec<_>>();
    let main_cursor_index = pulse
        .iter()
        .enumerate()
        .max_by(|(_, left), (_, right)| left.abs().total_cmp(&right.abs()))
        .map(|(index, _)| index)
        .expect("input validation guarantees a nonempty pulse");
    let raw_cursor = pulse[main_cursor_index];
    if raw_cursor == 0.0 {
        return Err(StatisticalEyeError::ZeroMainCursor);
    }
    let symbol_pulse = input
        .pulse_response
        .iter()
        .map(|sample| sample * raw_cursor.signum())
        .collect::<Vec<_>>();
    let normalized = symbol_pulse
        .iter()
        .map(|sample| sample * 0.5)
        .collect::<Vec<_>>();
    let edge_slopes = input
        .has_tx_edge_jitter()
        .then(|| recover_step_slope_per_ui(&symbol_pulse, input.nspui));
    let resolution = input.voltage_resolution.map_or_else(
        || normalized[main_cursor_index].abs().max(1.0) * 1.0e-5,
        |value| value.0,
    );
    let noise_sigma_v = input.noise_sigma_v.map_or(0.0, |noise| noise.0);
    let offsets = phase_offsets(input.nspui);
    let mut heights = Vec::with_capacity(offsets.len());
    for &offset in &offsets {
        let sample_index = main_cursor_index as isize + offset;
        heights.push(
            if sample_index < 0 || sample_index as usize >= normalized.len() {
                None
            } else {
                phase_height(
                    &normalized,
                    input.nspui,
                    sample_index as usize,
                    resolution,
                    input.target_ber,
                    noise_sigma_v,
                    input.max_distribution_states,
                )?
            },
        );
    }
    let best_index = heights
        .iter()
        .enumerate()
        .filter_map(|(index, result)| result.map(|value| (index, value)))
        .max_by(|(left_index, left), (right_index, right)| {
            left.total_cmp(right)
                .then_with(|| offsets[*right_index].abs().cmp(&offsets[*left_index].abs()))
        })
        .map(|(index, _)| index)
        .ok_or(StatisticalEyeError::NoSamplingPhase)?;
    let cursor_index = (main_cursor_index as isize + offsets[best_index]) as usize;

    let voltage_limit = voltage_limit(&normalized, input.nspui, cursor_index, &offsets);
    let voltage_limit =
        (voltage_limit + 2.0 * resolution).max(normalized[cursor_index].abs() * 1.25);
    let voltage_bins = ((2.0 * voltage_limit) / resolution).ceil() as usize;
    let voltage_axis = (0..=voltage_bins)
        .map(|index| (index as f64 - voltage_bins as f64 / 2.0) * resolution)
        .collect::<Vec<_>>();
    let mut ber_surface = vec![0.0; voltage_axis.len() * input.time_points];
    for time_index in 0..input.time_points {
        let offset_ui = time_index as f64 / input.time_points as f64 - 0.5;
        let Some((samples, cursor_position)) =
            fractional_phase_samples(&normalized, input.nspui, cursor_index, offset_ui)
        else {
            for value in ber_surface[time_index..]
                .iter_mut()
                .step_by(input.time_points)
            {
                *value = 0.5;
            }
            continue;
        };
        if let Some(edge_slopes) = &edge_slopes {
            let Some((symbol_samples, symbol_cursor_position)) =
                fractional_phase_samples(&symbol_pulse, input.nspui, cursor_index, offset_ui)
            else {
                return Err(StatisticalEyeError::NoSamplingPhase);
            };
            let Some((slope_samples, slope_cursor_position)) =
                fractional_phase_samples(edge_slopes, input.nspui, cursor_index, offset_ui)
            else {
                return Err(StatisticalEyeError::NoSamplingPhase);
            };
            if symbol_cursor_position != cursor_position || slope_cursor_position != cursor_position
            {
                return Err(StatisticalEyeError::NoSamplingPhase);
            }
            let high = gaussian_blurred_distribution(
                conditioned_tx_distribution(
                    &symbol_samples,
                    &slope_samples,
                    cursor_position,
                    1,
                    resolution,
                    input.max_distribution_states,
                    input.tx_rj_ui.unwrap_or(0.0),
                    input.tx_dj_ui.unwrap_or(0.0),
                    input.tx_dcd_ui.unwrap_or(0.0),
                )?,
                noise_sigma_v,
                resolution,
                input.max_distribution_states,
            )?;
            let low = gaussian_blurred_distribution(
                conditioned_tx_distribution(
                    &symbol_samples,
                    &slope_samples,
                    cursor_position,
                    -1,
                    resolution,
                    input.max_distribution_states,
                    input.tx_rj_ui.unwrap_or(0.0),
                    input.tx_dj_ui.unwrap_or(0.0),
                    input.tx_dcd_ui.unwrap_or(0.0),
                )?,
                noise_sigma_v,
                resolution,
                input.max_distribution_states,
            )?;
            for (voltage_index, &voltage) in voltage_axis.iter().enumerate() {
                let high_error = distribution_cdf(voltage, &high);
                let low_error = 1.0 - distribution_cdf(voltage, &low);
                ber_surface[voltage_index * input.time_points + time_index] =
                    high_error + low_error;
            }
        } else {
            let cursor_v = samples[cursor_position];
            let interferers = samples
                .iter()
                .enumerate()
                .filter_map(|(index, sample)| (index != cursor_position).then_some(*sample))
                .collect::<Vec<_>>();
            let distribution = gaussian_blurred_distribution(
                distribution(&interferers, resolution, input.max_distribution_states)?,
                noise_sigma_v,
                resolution,
                input.max_distribution_states,
            )?;
            for (voltage_index, &voltage) in voltage_axis.iter().enumerate() {
                let high_error = distribution_cdf(voltage - cursor_v, &distribution);
                let low_error = 1.0 - distribution_cdf(voltage + cursor_v, &distribution);
                ber_surface[voltage_index * input.time_points + time_index] =
                    high_error + low_error;
            }
        }
    }
    let kernel = periodic_jitter_kernel(input);
    if kernel.iter().filter(|value| **value > 0.0).count() > 1 {
        for row in ber_surface.chunks_exact_mut(input.time_points) {
            let blurred = periodic_convolve(row, &kernel);
            row.copy_from_slice(&blurred);
        }
    }
    for value in &mut ber_surface {
        *value = value.clamp(0.0, 1.0);
    }

    Ok(ber_values
        .iter()
        .map(|&ber| {
            contour_from_surface(
                ber,
                &voltage_axis,
                &ber_surface,
                input.time_points,
                input.ui,
            )
        })
        .collect())
}

fn validate_input(input: StatisticalEyeInputV1<'_>) -> Result<(), StatisticalEyeError> {
    if input.pulse_response.is_empty()
        || input
            .pulse_response
            .iter()
            .any(|sample| !sample.is_finite())
    {
        return Err(StatisticalEyeError::InvalidPulse);
    }
    if !input.ui.is_finite_positive() {
        return Err(StatisticalEyeError::InvalidUi);
    }
    if input.nspui == 0 {
        return Err(StatisticalEyeError::InvalidSamplesPerUi);
    }
    if !input.target_ber.is_finite() || !(0.0..0.5).contains(&input.target_ber) {
        return Err(StatisticalEyeError::InvalidTargetBer);
    }
    if input
        .voltage_resolution
        .is_some_and(|resolution| !resolution.is_finite_positive())
    {
        return Err(StatisticalEyeError::InvalidVoltageResolution);
    }
    if input
        .noise_sigma_v
        .is_some_and(|noise| !noise.0.is_finite() || noise.0 < 0.0)
    {
        return Err(StatisticalEyeError::InvalidVerticalNoise);
    }
    if [
        input.horizontal_rj_ui,
        input.horizontal_dj_ui,
        input.tx_rj_ui,
        input.tx_dj_ui,
        input.tx_dcd_ui,
        input.rx_rj_ui,
        input.rx_dj_ui,
    ]
    .into_iter()
    .flatten()
    .any(|value| !value.is_finite() || value < 0.0)
    {
        return Err(StatisticalEyeError::InvalidHorizontalJitter);
    }
    if input.time_points < input.nspui {
        return Err(StatisticalEyeError::InvalidTimePoints);
    }
    if input.max_distribution_states < 8 {
        return Err(StatisticalEyeError::InvalidDistributionLimit);
    }
    Ok(())
}

impl StatisticalEyeInputV1<'_> {
    fn has_horizontal_jitter(self) -> bool {
        [
            self.horizontal_rj_ui,
            self.horizontal_dj_ui,
            self.rx_rj_ui,
            self.rx_dj_ui,
        ]
        .into_iter()
        .flatten()
        .any(|value| value > 0.0)
    }

    fn has_tx_edge_jitter(self) -> bool {
        [self.tx_rj_ui, self.tx_dj_ui, self.tx_dcd_ui]
            .into_iter()
            .flatten()
            .any(|value| value > 0.0)
    }
}

fn voltage_limit(pulse: &[f64], nspui: usize, cursor_index: usize, offsets: &[isize]) -> f64 {
    offsets.iter().fold(0.0, |limit, &offset| {
        let sample_index = cursor_index as isize + offset;
        if sample_index < 0 || sample_index as usize >= pulse.len() {
            return limit;
        }
        let Some((samples, cursor_position)) = phase_samples(pulse, nspui, sample_index as usize)
        else {
            return limit;
        };
        let support = samples[cursor_position].abs()
            + samples
                .iter()
                .enumerate()
                .filter_map(|(index, sample)| (index != cursor_position).then_some(sample.abs()))
                .sum::<f64>();
        limit.max(support)
    })
}

fn fractional_phase_samples(
    pulse: &[f64],
    nspui: usize,
    cursor_index: usize,
    offset_ui: f64,
) -> Option<(Vec<f64>, usize)> {
    let sample_position = cursor_index as f64 + offset_ui * nspui as f64;
    let first_symbol = (-sample_position / nspui as f64).ceil() as isize;
    let last_symbol =
        ((pulse.len() as f64 - 1.0 - sample_position) / nspui as f64).floor() as isize;
    if first_symbol > last_symbol || !(first_symbol..=last_symbol).contains(&0) {
        return None;
    }
    let mut samples = Vec::with_capacity((last_symbol - first_symbol + 1) as usize);
    let mut cursor_position = None;
    for symbol in first_symbol..=last_symbol {
        let position = sample_position + symbol as f64 * nspui as f64;
        let lower = position.floor() as usize;
        let upper = (lower + 1).min(pulse.len() - 1);
        let fraction = position - lower as f64;
        samples.push(pulse[lower] * (1.0 - fraction) + pulse[upper] * fraction);
        if symbol == 0 {
            cursor_position = Some(samples.len() - 1);
        }
    }
    cursor_position.map(|position| (samples, position))
}

fn distribution_cdf(x: f64, distribution: &Distribution) -> f64 {
    let first = distribution.values[0];
    let last_index = distribution.values.len() - 1;
    if x < first {
        return 0.0;
    }
    if x >= distribution.values[last_index] {
        return 1.0;
    }
    let upper = distribution.values.partition_point(|value| *value < x);
    if upper == 0 {
        return distribution.cumulative_probabilities[0];
    }
    let lower = upper - 1;
    let lower_cdf = distribution.cumulative_probabilities[lower];
    let upper_cdf = distribution.cumulative_probabilities[upper];
    let fraction = (x - distribution.values[lower])
        / (distribution.values[upper] - distribution.values[lower]);
    lower_cdf + fraction * (upper_cdf - lower_cdf)
}

/// Match the reference BER-surface path: it discretizes vertical Gaussian
/// noise onto the voltage grid before interpolating each phase's CDF. The
/// scalar eye metric intentionally keeps its analytic mixture quantile path.
fn gaussian_blurred_distribution(
    distribution: Distribution,
    sigma_v: f64,
    resolution: f64,
    max_distribution_states: usize,
) -> Result<Distribution, StatisticalEyeError> {
    if sigma_v <= 0.0 {
        return Ok(distribution);
    }
    let sigma_bins = sigma_v / resolution;
    let padding = (8.0 * sigma_bins).ceil();
    if !padding.is_finite() || padding < 0.0 || padding > usize::MAX as f64 {
        return Err(StatisticalEyeError::DistributionLimitExceeded);
    }
    let padding = padding as usize;
    let expanded_length = distribution
        .probabilities
        .len()
        .checked_add(padding.saturating_mul(2))
        .ok_or(StatisticalEyeError::DistributionLimitExceeded)?;
    if expanded_length > max_distribution_states {
        return Err(StatisticalEyeError::DistributionLimitExceeded);
    }
    // SciPy gaussian_filter1d uses radius=round(truncate * sigma) with its
    // default truncate=8.0, then applies zero-padded correlation.
    let radius = (8.0 * sigma_bins + 0.5).floor() as usize;
    let mut kernel = (0..=radius.saturating_mul(2))
        .map(|index| {
            let offset = index as isize - radius as isize;
            (-0.5 * (offset as f64 / sigma_bins).powi(2)).exp()
        })
        .collect::<Vec<_>>();
    kernel = normalize_probability(kernel);

    let mut padded = vec![0.0; expanded_length];
    padded[padding..padding + distribution.probabilities.len()]
        .copy_from_slice(&distribution.probabilities);
    let probabilities = padded
        .iter()
        .enumerate()
        .map(|(index, _)| {
            kernel
                .iter()
                .enumerate()
                .filter_map(|(kernel_index, &weight)| {
                    let source = index as isize + kernel_index as isize - radius as isize;
                    if source >= 0 && source < padded.len() as isize {
                        Some(padded[source as usize] * weight)
                    } else {
                        None
                    }
                })
                .sum::<f64>()
        })
        .collect::<Vec<_>>();
    let probabilities = normalize_probability(probabilities);
    let first_value = distribution.values[0] - padding as f64 * resolution;
    let values = (0..expanded_length)
        .map(|index| first_value + index as f64 * resolution)
        .collect();
    Ok(Distribution::new(values, probabilities))
}

fn recover_step_slope_per_ui(pulse: &[f64], nspui: usize) -> Vec<f64> {
    let mut step = pulse.to_vec();
    for index in nspui..step.len() {
        step[index] += step[index - nspui];
    }
    let mut slopes = vec![0.0; step.len()];
    for (index, slope) in slopes.iter_mut().enumerate() {
        let derivative = match index {
            0 if step.len() > 1 => step[1] - step[0],
            index if index + 1 == step.len() && index > 0 => step[index] - step[index - 1],
            index => (step[index + 1] - step[index - 1]) * 0.5,
        };
        *slope = derivative * nspui as f64;
    }
    slopes
}

fn shift_probability(probabilities: &[f64], bins: f64) -> Vec<f64> {
    let lower = bins.floor() as isize;
    let fraction = bins - lower as f64;
    let mut shifted = vec![0.0; probabilities.len()];
    for (index, &value) in probabilities.iter().enumerate() {
        for (offset, weight) in [(lower, 1.0 - fraction), (lower + 1, fraction)] {
            let destination = index as isize + offset;
            if (0..shifted.len() as isize).contains(&destination) {
                shifted[destination as usize] += value * weight;
            }
        }
    }
    shifted
}

fn zero_padded_filter(
    probabilities: &[f64],
    kernel: &[f64],
    radius: usize,
) -> Result<Vec<f64>, StatisticalEyeError> {
    let filtered = linear_convolve(probabilities, kernel)
        .map_err(|_| StatisticalEyeError::DistributionLimitExceeded)?;
    Ok(filtered[radius..radius + probabilities.len()].to_vec())
}

fn filter_transition_probability(
    probabilities: &[f64],
    edge_slope_v_per_ui: f64,
    resolution: f64,
    tx_rj_ui: f64,
    tx_dj_ui: f64,
) -> Result<Vec<f64>, StatisticalEyeError> {
    let mut filtered = probabilities.to_vec();
    if tx_rj_ui > 0.0 {
        let sigma_bins = (edge_slope_v_per_ui * tx_rj_ui / resolution).abs();
        if sigma_bins > f64::EPSILON {
            let radius = (8.0 * sigma_bins + 0.5).floor() as usize;
            let kernel = normalize_probability(
                (0..=radius.saturating_mul(2))
                    .map(|index| {
                        let offset = index as isize - radius as isize;
                        (-0.5 * (offset as f64 / sigma_bins).powi(2)).exp()
                    })
                    .collect(),
            );
            filtered = zero_padded_filter(&filtered, &kernel, radius)?;
        }
    }
    if tx_dj_ui > 0.0 {
        let half_range_bins = (edge_slope_v_per_ui * tx_dj_ui / resolution).abs();
        let kernel_size = (2.0 * half_range_bins + 1.0).round().max(1.0) as usize;
        if kernel_size > 1 {
            let kernel = vec![1.0 / kernel_size as f64; kernel_size];
            filtered = zero_padded_filter(&filtered, &kernel, kernel_size / 2)?;
        }
    }
    Ok(filtered)
}

#[allow(clippy::too_many_arguments)]
fn conditioned_tx_distribution(
    samples: &[f64],
    edge_slopes_v_per_ui: &[f64],
    cursor_position: usize,
    cursor_sign: i8,
    resolution: f64,
    max_distribution_states: usize,
    tx_rj_ui: f64,
    tx_dj_ui: f64,
    tx_dcd_ui: f64,
) -> Result<Distribution, StatisticalEyeError> {
    if samples.len() != edge_slopes_v_per_ui.len()
        || cursor_position >= samples.len()
        || !matches!(cursor_sign, -1 | 1)
    {
        return Err(StatisticalEyeError::NoSamplingPhase);
    }
    let mut symbol_samples = samples.to_vec();
    let mut edge_slopes = edge_slopes_v_per_ui.to_vec();
    symbol_samples.reverse();
    edge_slopes.reverse();
    let cursor_position = symbol_samples.len() - 1 - cursor_position;

    let edge_energy = edge_slopes
        .iter()
        .map(|slope| slope * slope)
        .collect::<Vec<_>>();
    let total_edge_energy = edge_energy.iter().sum::<f64>();
    let mut first = cursor_position;
    let mut last = cursor_position;
    let mut captured_edge_energy = edge_energy[cursor_position];
    while total_edge_energy > 0.0
        && captured_edge_energy < 0.99999 * total_edge_energy
        && (first > 0 || last + 1 < edge_energy.len())
    {
        let left = if first > 0 {
            edge_energy[first - 1]
        } else {
            -1.0
        };
        let right = if last + 1 < edge_energy.len() {
            edge_energy[last + 1]
        } else {
            -1.0
        };
        if left >= right {
            first -= 1;
            captured_edge_energy += edge_energy[first];
        } else {
            last += 1;
            captured_edge_energy += edge_energy[last];
        }
    }
    let ideal_support_v = 0.5
        * symbol_samples
            .iter()
            .map(|sample| sample.abs())
            .sum::<f64>();
    let jitter_variance_ui2 = tx_rj_ui.powi(2) + tx_dj_ui.powi(2) / 3.0;
    let jitter_sigma_v = (0.5 * total_edge_energy * jitter_variance_ui2).sqrt();
    let dcd_support_v = tx_dcd_ui.abs()
        * edge_slopes[first..=last]
            .iter()
            .map(|slope| slope.abs())
            .sum::<f64>();
    let required_bins =
        (2.0 * (ideal_support_v + 8.0 * jitter_sigma_v + dcd_support_v) / resolution).ceil();
    if !required_bins.is_finite() || required_bins < 0.0 {
        return Err(StatisticalEyeError::DistributionLimitExceeded);
    }
    let mut state_count = 1024usize;
    while state_count < required_bins as usize {
        state_count = state_count
            .checked_mul(2)
            .ok_or(StatisticalEyeError::DistributionLimitExceeded)?;
    }
    if state_count > max_distribution_states {
        return Err(StatisticalEyeError::DistributionLimitExceeded);
    }
    let center = state_count / 2;
    let mut state = [vec![0.0; state_count], vec![0.0; state_count]];
    state[0][center] = 0.5;
    state[1][center] = 0.5;
    let conditioned_state = usize::from(cursor_sign > 0);
    for index in first..=last {
        let mut next = [vec![0.0; state_count], vec![0.0; state_count]];
        for current_state in 0..2 {
            if index == cursor_position && current_state != conditioned_state {
                continue;
            }
            let mut transition = filter_transition_probability(
                &state[1 - current_state],
                edge_slopes[index],
                resolution,
                tx_rj_ui,
                tx_dj_ui,
            )?;
            if tx_dcd_ui > 0.0 {
                let direction = if current_state == 1 { 1.0 } else { -1.0 };
                transition = shift_probability(
                    &transition,
                    -direction * edge_slopes[index] * tx_dcd_ui / resolution,
                );
            }
            let combined = state[current_state]
                .iter()
                .zip(&transition)
                .map(|(same, transition)| same + transition)
                .collect::<Vec<_>>();
            let level = if current_state == 1 { 0.5 } else { -0.5 };
            next[current_state] =
                shift_probability(&combined, level * symbol_samples[index] / resolution)
                    .into_iter()
                    .map(|value| value * 0.5)
                    .collect();
        }
        state = next;
    }
    let mut inside = state[0]
        .iter()
        .zip(&state[1])
        .map(|(low, high)| low + high)
        .collect::<Vec<_>>();
    let inside_sum = inside.iter().sum::<f64>();
    if !inside_sum.is_finite() || inside_sum <= 0.0 {
        return Err(StatisticalEyeError::DistributionLimitExceeded);
    }
    for probability in &mut inside {
        *probability /= inside_sum;
    }

    let outside_samples = symbol_samples[..first]
        .iter()
        .chain(&symbol_samples[last + 1..])
        .map(|sample| sample * 0.5)
        .collect::<Vec<_>>();
    let outside_distribution = distribution(&outside_samples, resolution, max_distribution_states)?;
    let mut outside = vec![0.0; state_count];
    for (&value, &probability) in outside_distribution
        .values
        .iter()
        .zip(&outside_distribution.probabilities)
    {
        let bin = (value / resolution).round() as isize;
        let destination = center as isize + bin;
        if (0..state_count as isize).contains(&destination) {
            outside[destination as usize] += probability;
        }
    }
    let outside_sum = outside.iter().sum::<f64>();
    if !outside_sum.is_finite() || outside_sum <= 0.0 {
        return Err(StatisticalEyeError::DistributionLimitExceeded);
    }
    for probability in &mut outside {
        *probability /= outside_sum;
    }
    let full = linear_convolve(&inside, &outside)
        .map_err(|_| StatisticalEyeError::DistributionLimitExceeded)?;
    let start = (full.len() - state_count) / 2;
    let probabilities = normalize_probability(full[start..start + state_count].to_vec());
    let values = (0..state_count)
        .map(|index| (index as isize - center as isize) as f64 * resolution)
        .collect();
    Ok(Distribution::new(values, probabilities))
}

fn periodic_jitter_kernel(input: StatisticalEyeInputV1<'_>) -> Vec<f64> {
    let count = input.time_points;
    let mut kernel = vec![0.0; count];
    kernel[0] = 1.0;
    let random_sigma = (input.horizontal_rj_ui.unwrap_or(0.0).powi(2)
        + input.rx_rj_ui.unwrap_or(0.0).powi(2))
    .sqrt();
    if random_sigma > 0.0 {
        let gaussian = (0..count)
            .map(|index| {
                let signed = if index <= count / 2 {
                    index as f64
                } else {
                    index as f64 - count as f64
                } / count as f64;
                (-0.5 * (signed / random_sigma).powi(2)).exp()
            })
            .collect::<Vec<_>>();
        kernel =
            normalize_probability(periodic_convolve(&kernel, &normalize_probability(gaussian)));
    }
    for half_range in [input.horizontal_dj_ui, input.rx_dj_ui]
        .into_iter()
        .flatten()
        .filter(|value| *value > 0.0)
    {
        let uniform = (0..count)
            .map(|index| {
                let signed = if index <= count / 2 {
                    index as f64
                } else {
                    index as f64 - count as f64
                } / count as f64;
                f64::from(signed.abs() <= half_range)
            })
            .collect::<Vec<_>>();
        kernel = normalize_probability(periodic_convolve(&kernel, &normalize_probability(uniform)));
    }
    kernel
}

fn periodic_convolve(left: &[f64], right: &[f64]) -> Vec<f64> {
    let mut output = vec![0.0; left.len()];
    for (left_index, &left_value) in left.iter().enumerate() {
        if left_value == 0.0 {
            continue;
        }
        for (right_index, &right_value) in right.iter().enumerate() {
            if right_value != 0.0 {
                output[(left_index + right_index) % left.len()] += left_value * right_value;
            }
        }
    }
    output
}

fn normalize_probability(mut values: Vec<f64>) -> Vec<f64> {
    let total = values.iter().sum::<f64>();
    if total > 0.0 && total.is_finite() {
        for value in &mut values {
            *value /= total;
        }
    }
    values
}

fn contour_from_surface(
    ber: f64,
    voltage_axis: &[f64],
    surface: &[f64],
    time_points: usize,
    ui: Seconds,
) -> StatisticalEyeContourV1 {
    let mut lower = vec![None; time_points];
    let mut upper = vec![None; time_points];
    for time_index in 0..time_points {
        let column = surface
            .chunks_exact(time_points)
            .map(|row| row[time_index])
            .collect::<Vec<_>>();
        let Some((minimum_index, &minimum)) = column
            .iter()
            .enumerate()
            .min_by(|(_, left), (_, right)| left.total_cmp(right))
        else {
            continue;
        };
        if minimum > ber {
            continue;
        }
        let mut lo_index = minimum_index;
        while lo_index > 0 && column[lo_index - 1] <= ber {
            lo_index -= 1;
        }
        let mut hi_index = minimum_index;
        while hi_index + 1 < column.len() && column[hi_index + 1] <= ber {
            hi_index += 1;
        }
        let lo = if lo_index > 0 && column[lo_index - 1] > ber {
            interpolate_threshold(
                ber,
                column[lo_index],
                column[lo_index - 1],
                voltage_axis[lo_index],
                voltage_axis[lo_index - 1],
            )
        } else {
            voltage_axis[lo_index]
        };
        let hi = if hi_index + 1 < column.len() && column[hi_index + 1] > ber {
            interpolate_threshold(
                ber,
                column[hi_index],
                column[hi_index + 1],
                voltage_axis[hi_index],
                voltage_axis[hi_index + 1],
            )
        } else {
            voltage_axis[hi_index]
        };
        if hi >= lo {
            lower[time_index] = Some(lo);
            upper[time_index] = Some(hi);
        }
    }

    let mut best_start = 0usize;
    let mut best_end = None;
    let mut start = None;
    for index in 0..=time_points {
        let valid = index < time_points && lower[index].is_some() && upper[index].is_some();
        match (start, valid) {
            (None, true) => start = Some(index),
            (Some(begin), false) => {
                let end = index - 1;
                if best_end.is_none_or(|best| end - begin > best - best_start) {
                    best_start = begin;
                    best_end = Some(end);
                }
                start = None;
            }
            _ => {}
        }
    }
    let Some(best_end) = best_end else {
        return StatisticalEyeContourV1 {
            ber,
            height_v: 0.0,
            width_ps: 0.0,
            point_count: 0,
            x_ui: vec![],
            y_v: vec![],
        };
    };
    let x_open = (best_start..=best_end)
        .map(|index| index as f64 / time_points as f64 - 0.5)
        .collect::<Vec<_>>();
    let lower_open = (best_start..=best_end)
        .map(|index| lower[index].expect("valid range"))
        .collect::<Vec<_>>();
    let upper_open = (best_start..=best_end)
        .map(|index| upper[index].expect("valid range"))
        .collect::<Vec<_>>();
    let mut x_ui = x_open.clone();
    x_ui.extend(x_open.iter().rev().copied());
    let mut y_v = upper_open;
    y_v.extend(lower_open.iter().rev().copied());
    let height_v = (best_start..=best_end)
        .map(|index| upper[index].expect("valid range") - lower[index].expect("valid range"))
        .fold(0.0, f64::max);
    StatisticalEyeContourV1 {
        ber,
        height_v,
        width_ps: (best_end - best_start) as f64 / time_points as f64 * ui.0 * 1.0e12,
        point_count: x_ui.len(),
        x_ui,
        y_v,
    }
}

fn interpolate_threshold(
    target: f64,
    inside: f64,
    outside: f64,
    inside_x: f64,
    outside_x: f64,
) -> f64 {
    if outside == inside {
        inside_x
    } else {
        inside_x + (target - inside) * (outside_x - inside_x) / (outside - inside)
    }
}

fn phase_offsets(nspui: usize) -> Vec<isize> {
    let start = -(nspui as isize / 2);
    (0..nspui).map(|index| start + index as isize).collect()
}

fn phase_samples(pulse: &[f64], nspui: usize, sample_index: usize) -> Option<(Vec<f64>, usize)> {
    let phase = sample_index % nspui;
    let samples = (phase..pulse.len())
        .step_by(nspui)
        .map(|index| pulse[index])
        .collect::<Vec<_>>();
    let cursor_position = (sample_index - phase) / nspui;
    (cursor_position < samples.len()).then_some((samples, cursor_position))
}

fn phase_height(
    pulse: &[f64],
    nspui: usize,
    sample_index: usize,
    resolution: f64,
    target_ber: f64,
    noise_sigma_v: f64,
    max_distribution_states: usize,
) -> Result<Option<f64>, StatisticalEyeError> {
    let Some((samples, cursor_position)) = phase_samples(pulse, nspui, sample_index) else {
        return Ok(None);
    };
    let cursor = samples[cursor_position];
    let interferers = samples
        .iter()
        .enumerate()
        .filter_map(|(index, sample)| (index != cursor_position).then_some(*sample))
        .collect::<Vec<_>>();
    let distribution = distribution(&interferers, resolution, max_distribution_states)?;
    let low_q = distribution.quantile(target_ber, noise_sigma_v);
    let high_q = distribution.quantile(1.0 - target_ber, noise_sigma_v);
    Ok(Some((cursor + low_q) - (-cursor + high_q)))
}

fn distribution(
    taps: &[f64],
    resolution: f64,
    max_distribution_states: usize,
) -> Result<Distribution, StatisticalEyeError> {
    let scaled = taps
        .iter()
        .map(|tap| tap.abs() / resolution)
        .filter(|shift| *shift > f64::EPSILON)
        .collect::<Vec<_>>();
    if scaled.is_empty() {
        return Ok(Distribution::new(vec![0.0], vec![1.0]));
    }

    let upper = scaled
        .iter()
        .map(|shift| shift.floor() as usize + usize::from(shift.fract() > 0.0))
        .collect::<Vec<_>>();
    let support = upper.iter().sum::<usize>();
    let state_count = support.saturating_mul(2).saturating_add(1);
    if state_count > max_distribution_states {
        return Err(StatisticalEyeError::DistributionLimitExceeded);
    }

    let mut probabilities = vec![1.0];
    let mut current_support = 0usize;
    for (shift, upper_shift) in scaled.iter().zip(upper) {
        let lower_shift = shift.floor() as usize;
        let fraction = shift - lower_shift as f64;
        let mut kernel = vec![0.0; upper_shift * 2 + 1];
        let midpoint = upper_shift;
        if lower_shift == 0 {
            kernel[midpoint] += 1.0 - fraction;
        } else {
            let mass = 0.5 * (1.0 - fraction);
            kernel[midpoint - lower_shift] += mass;
            kernel[midpoint + lower_shift] += mass;
        }
        if fraction > f64::EPSILON {
            kernel[0] += 0.5 * fraction;
            let last = kernel.len() - 1;
            kernel[last] += 0.5 * fraction;
        }
        probabilities = convolve(&probabilities, &kernel);
        current_support += upper_shift;
    }
    let sum = probabilities.iter().sum::<f64>();
    if !sum.is_finite() || sum <= 0.0 {
        return Err(StatisticalEyeError::DistributionLimitExceeded);
    }
    for probability in &mut probabilities {
        *probability /= sum;
    }
    let values = (-(current_support as isize)..=(current_support as isize))
        .map(|index| index as f64 * resolution)
        .collect();
    Ok(Distribution::new(values, probabilities))
}

fn discrete_quantile(values: &[f64], probabilities: &[f64], probability: f64) -> f64 {
    let mut cdf = 0.0;
    for (&value, &weight) in values.iter().zip(probabilities) {
        cdf += weight;
        if cdf >= probability {
            return value;
        }
    }
    *values.last().expect("distribution is nonempty")
}

fn mixture_cdf(x: f64, distribution: &Distribution, sigma_v: f64, normal: &Normal) -> f64 {
    distribution
        .values
        .iter()
        .zip(&distribution.probabilities)
        .map(|(&value, &weight)| weight * normal.cdf((x - value) / sigma_v))
        .sum()
}

fn convolve(left: &[f64], right: &[f64]) -> Vec<f64> {
    let mut output = vec![0.0; left.len() + right.len() - 1];
    for (left_index, left_value) in left.iter().enumerate() {
        for (right_index, right_value) in right.iter().enumerate() {
            output[left_index + right_index] += left_value * right_value;
        }
    }
    output
}

fn opening_width_ps(
    offsets: &[isize],
    heights: &[Option<f64>],
    ui: Seconds,
    nspui: usize,
    center_index: usize,
) -> f64 {
    if heights[center_index].is_none_or(|height| height <= 0.0) {
        return 0.0;
    }
    let mut left = center_index;
    while left > 0 && heights[left - 1].is_some_and(|height| height > 0.0) {
        left -= 1;
    }
    let mut right = center_index;
    while right + 1 < heights.len() && heights[right + 1].is_some_and(|height| height > 0.0) {
        right += 1;
    }

    let left_cross = if left == 0 {
        offsets[left] as f64
    } else {
        interpolate_zero(
            offsets[left - 1] as f64,
            offsets[left] as f64,
            heights[left - 1].unwrap_or(0.0),
            heights[left].unwrap_or(0.0),
        )
    };
    let right_cross = if right + 1 == heights.len() {
        offsets[right] as f64
    } else {
        interpolate_zero(
            offsets[right] as f64,
            offsets[right + 1] as f64,
            heights[right].unwrap_or(0.0),
            heights[right + 1].unwrap_or(0.0),
        )
    };
    ((right_cross - left_cross).max(0.0) * ui.0 / nspui as f64) * 1.0e12
}

fn interpolate_zero(x0: f64, x1: f64, y0: f64, y1: f64) -> f64 {
    if y1 == y0 {
        x0
    } else {
        x0 - y0 * (x1 - x0) / (y1 - y0)
    }
}
