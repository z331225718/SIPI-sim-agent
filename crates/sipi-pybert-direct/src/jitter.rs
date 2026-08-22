//! Threshold-crossing extraction used by the deterministic jitter pipeline.

use rustfft::{FftPlanner, num_complex::Complex};
use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum CrossingError {
    #[error("time and signal arrays must have the same non-zero length")]
    LengthMismatch,
    #[error("time and signal arrays must contain only finite values")]
    NonFiniteInput,
    #[error("minimum initial deviation must be finite and non-negative")]
    InvalidInitialDeviation,
    #[error("no signal sample reached the minimum initial deviation")]
    InitialDeviationNotDetected,
    #[error("minimum delay must be before the final detected crossing")]
    InvalidMinimumDelay,
    #[error("modulation must be NRZ (0), DuoBinary (1), or PAM4 (2)")]
    InvalidModulation,
    #[error("UI must be finite and greater than zero")]
    InvalidUi,
    #[error("ideal and actual crossing arrays must be non-empty and finite")]
    InvalidCrossingTrack,
    #[error("pattern length must be positive and fit at least once in the TIE span")]
    InvalidPatternLength,
    #[error("the ideal crossing track has no usable even crossing count per pattern")]
    InvalidPatternCrossings,
    #[error("spectral jitter analysis requires at least 101 aligned finite TIE samples")]
    InsufficientSpectralSamples,
    #[error(
        "dual-Dirac analysis requires at least three bins, a positive smoothing width, and finite non-empty TIE values"
    )]
    InvalidDualDiracInput,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CrossingConfig {
    pub min_delay_s: f64,
    pub rising_first: bool,
    pub min_initial_deviation: f64,
    pub threshold_v: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TieTrackResult {
    pub jitter_s: Vec<f64>,
    pub ideal_times_s: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DataDependentJitterResult {
    pub isi_s: f64,
    pub dcd_s: f64,
    pub data_independent_tie_s: Vec<f64>,
    pub pattern_count: usize,
    pub crossings_per_pattern: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpectralJitterResult {
    pub periodic_jitter_s: f64,
    pub random_jitter_s: f64,
    pub total_spectrum: Vec<f64>,
    pub data_independent_spectrum: Vec<f64>,
    pub frequencies_hz: Vec<f64>,
    pub periodic_threshold: Vec<f64>,
}

/// Histogram-based dual-Dirac decomposition of a TIE track.
#[derive(Debug, Clone, PartialEq)]
pub struct DualDiracJitterResult {
    pub periodic_jitter_s: f64,
    pub random_jitter_s: f64,
    pub total_histogram: Vec<f64>,
    pub data_independent_histogram: Vec<f64>,
    pub bin_centers_s: Vec<f64>,
    pub positive_mean_s: f64,
    pub negative_mean_s: f64,
}

impl Default for CrossingConfig {
    fn default() -> Self {
        Self {
            min_delay_s: 0.0,
            rising_first: true,
            min_initial_deviation: 0.1,
            threshold_v: 0.0,
        }
    }
}

/// Mirror PyBERT's zero-safe sign convention and linear crossing interpolation.
pub fn find_crossing_times(
    times_s: &[f64],
    signal_v: &[f64],
    config: CrossingConfig,
) -> Result<Vec<f64>, CrossingError> {
    if times_s.is_empty() || times_s.len() != signal_v.len() {
        return Err(CrossingError::LengthMismatch);
    }
    if times_s
        .iter()
        .chain(signal_v)
        .chain(
            [
                config.min_delay_s,
                config.min_initial_deviation,
                config.threshold_v,
            ]
            .iter(),
        )
        .any(|value| !value.is_finite())
    {
        return Err(CrossingError::NonFiniteInput);
    }
    if config.min_initial_deviation < 0.0 {
        return Err(CrossingError::InvalidInitialDeviation);
    }
    let max_magnitude = signal_v
        .iter()
        .fold(0.0_f64, |value, sample| value.max(sample.abs()));
    let minimum_magnitude = config.min_initial_deviation * max_magnitude;
    let start = signal_v
        .iter()
        .position(|sample| sample.abs() >= minimum_magnitude)
        .ok_or(CrossingError::InitialDeviationNotDetected)?;
    let adjusted = signal_v[start..]
        .iter()
        .map(|sample| sample - config.threshold_v)
        .collect::<Vec<_>>();
    let mut crossings = Vec::new();
    let mut crossing_indices = Vec::new();
    for index in 0..adjusted.len().saturating_sub(1) {
        let left_sign = if adjusted[index] < 0.0 { -1 } else { 1 };
        let right_sign = if adjusted[index + 1] < 0.0 { -1 } else { 1 };
        if left_sign != right_sign {
            let left_time = times_s[start + index];
            let right_time = times_s[start + index + 1];
            crossings.push(
                left_time
                    + (right_time - left_time) * adjusted[index]
                        / (adjusted[index] - adjusted[index + 1]),
            );
            crossing_indices.push(index);
        }
    }
    if crossings.is_empty() {
        return Ok(crossings);
    }
    let mut first = 0;
    if config.min_delay_s != 0.0 {
        if config.min_delay_s >= *crossings.last().expect("non-empty crossings") {
            return Err(CrossingError::InvalidMinimumDelay);
        }
        first = crossings.partition_point(|crossing| *crossing < config.min_delay_s);
    }
    if config.rising_first && first < crossings.len() {
        let crossing_index = crossing_indices[first];
        if adjusted[crossing_index] > 0.0 && adjusted[crossing_index + 1] < 0.0 {
            first += 1;
        }
    }
    Ok(crossings.split_off(first))
}

/// Extract crossings at the modulation-specific decision thresholds.
pub fn find_crossings(
    times_s: &[f64],
    signal_v: &[f64],
    amplitude_v: f64,
    min_delay_s: f64,
    rising_first: bool,
    min_initial_deviation: f64,
    modulation: u8,
) -> Result<Vec<f64>, CrossingError> {
    if !amplitude_v.is_finite() {
        return Err(CrossingError::NonFiniteInput);
    }
    let thresholds: &[f64] = match modulation {
        0 | 2 => &[0.0],
        1 => &[-0.5, 0.5],
        _ => return Err(CrossingError::InvalidModulation),
    };
    let mut crossings = Vec::new();
    for &threshold_scale in thresholds {
        crossings.extend(find_crossing_times(
            times_s,
            signal_v,
            CrossingConfig {
                min_delay_s,
                rising_first,
                min_initial_deviation,
                threshold_v: threshold_scale * amplitude_v,
            },
        )?);
    }
    crossings.sort_by(f64::total_cmp);
    Ok(crossings)
}

/// Match actual crossings to ideal edge windows and build PyBERT's TIE track.
///
/// Missing edges deliberately receive the legacy alternating +/-3UI/4 pair,
/// with the following ideal edge reserved so the returned TIE and time arrays
/// stay aligned. Higher-level ISI/DCD and dual-Dirac decomposition consumes
/// this stable intermediate representation.
pub fn assemble_tie_track(
    ui_s: f64,
    ideal_crossings_s: &[f64],
    actual_crossings_s: &[f64],
    zero_mean: bool,
) -> Result<TieTrackResult, CrossingError> {
    if !ui_s.is_finite() || ui_s <= 0.0 {
        return Err(CrossingError::InvalidUi);
    }
    if ideal_crossings_s.is_empty()
        || actual_crossings_s.is_empty()
        || ideal_crossings_s
            .iter()
            .chain(actual_crossings_s)
            .any(|value| !value.is_finite())
    {
        return Err(CrossingError::InvalidCrossingTrack);
    }
    let mut actual_index = 0;
    let mut jitter_s = Vec::new();
    let mut ideal_times_s = Vec::new();
    let mut skip_next_ideal_crossing = false;
    for &ideal_crossing in ideal_crossings_s {
        if skip_next_ideal_crossing {
            ideal_times_s.push(ideal_crossing);
            skip_next_ideal_crossing = false;
            continue;
        }
        let min_time = ideal_crossing - ui_s / 2.0;
        let max_time = ideal_crossing + ui_s / 2.0;
        while actual_index < actual_crossings_s.len() && actual_crossings_s[actual_index] < min_time
        {
            actual_index += 1;
        }
        if actual_index == actual_crossings_s.len() {
            break;
        }
        if actual_crossings_s[actual_index] > max_time {
            jitter_s.extend([3.0 * ui_s / 4.0, -3.0 * ui_s / 4.0]);
            skip_next_ideal_crossing = true;
        } else {
            let mut candidate_index = actual_index;
            let mut sum = 0.0;
            let mut count = 0_usize;
            while candidate_index < actual_crossings_s.len()
                && actual_crossings_s[candidate_index] <= max_time
            {
                sum += actual_crossings_s[candidate_index];
                count += 1;
                candidate_index += 1;
            }
            jitter_s.push(sum / count as f64 - ideal_crossing);
        }
        ideal_times_s.push(ideal_crossing);
    }
    if zero_mean && !jitter_s.is_empty() {
        let mean = jitter_s.iter().sum::<f64>() / jitter_s.len() as f64;
        jitter_s.iter_mut().for_each(|jitter| *jitter -= mean);
    }
    Ok(TieTrackResult {
        jitter_s,
        ideal_times_s,
    })
}

/// Separate data-dependent ISI/DCD from a uniformly repeating TIE pattern.
///
/// This is the deterministic middle section of ``calc_jitter``. FFT spectral
/// classification and dual-Dirac tail fitting intentionally remain separate
/// consumers of its `data_independent_tie_s` output.
pub fn calculate_data_dependent_jitter(
    ui_s: f64,
    nui: usize,
    pattern_len: usize,
    ideal_crossings_s: &[f64],
    jitter_s: &[f64],
    zero_mean: bool,
) -> Result<DataDependentJitterResult, CrossingError> {
    if !ui_s.is_finite() || ui_s <= 0.0 {
        return Err(CrossingError::InvalidUi);
    }
    if pattern_len == 0 || nui / pattern_len == 0 {
        return Err(CrossingError::InvalidPatternLength);
    }
    if ideal_crossings_s.is_empty()
        || jitter_s.is_empty()
        || ideal_crossings_s
            .iter()
            .chain(jitter_s)
            .any(|value| !value.is_finite())
    {
        return Err(CrossingError::InvalidCrossingTrack);
    }
    let first_after_pattern = ideal_crossings_s
        .iter()
        .position(|crossing| *crossing > pattern_len as f64 * ui_s);
    let (pattern_count, mut crossings_per_pattern) = match first_after_pattern {
        Some(index) => (nui / pattern_len, index),
        None => (1, ideal_crossings_s.len()),
    };
    if crossings_per_pattern % 2 == 1 {
        crossings_per_pattern -= 1;
    }
    if crossings_per_pattern == 0 {
        return Err(CrossingError::InvalidPatternCrossings);
    }
    let edges_per_polarity = crossings_per_pattern / 2;
    let padded_polarity_len = pattern_count * edges_per_polarity;
    let mut rising = jitter_s.iter().step_by(2).copied().collect::<Vec<_>>();
    let mut falling = jitter_s
        .iter()
        .skip(1)
        .step_by(2)
        .copied()
        .collect::<Vec<_>>();
    rising.resize(padded_polarity_len, 0.0);
    falling.resize(padded_polarity_len, 0.0);
    rising.truncate(padded_polarity_len);
    falling.truncate(padded_polarity_len);
    let rising_average = pattern_average(&rising, pattern_count, edges_per_polarity);
    let falling_average = pattern_average(&falling, pattern_count, edges_per_polarity);
    let isi_s = peak_to_peak(&rising_average)
        .max(peak_to_peak(&falling_average))
        .min(ui_s);
    let dcd_s = (mean(&rising_average) - mean(&falling_average)).abs();

    let mut padded_jitter = jitter_s.to_vec();
    padded_jitter.resize(pattern_count * crossings_per_pattern, 0.0);
    padded_jitter.truncate(pattern_count * crossings_per_pattern);
    let one_pattern_average = pattern_average(&padded_jitter, pattern_count, crossings_per_pattern);
    // Preserve PyBERT's historical zero-pad behavior here. Although a
    // repeated pattern might look more natural, `resize_zero_pad()` only
    // places the averaged pattern at the beginning of the observed TIE span.
    let mut tie_average = one_pattern_average;
    tie_average.resize(jitter_s.len(), 0.0);
    let mut data_independent_tie_s = jitter_s
        .iter()
        .enumerate()
        .map(|(index, jitter)| jitter - tie_average[index])
        .collect::<Vec<_>>();
    if zero_mean {
        let average = mean(&data_independent_tie_s);
        data_independent_tie_s
            .iter_mut()
            .for_each(|jitter| *jitter -= average);
    }
    Ok(DataDependentJitterResult {
        isi_s,
        dcd_s,
        data_independent_tie_s,
        pattern_count,
        crossings_per_pattern,
    })
}

fn pattern_average(values: &[f64], pattern_count: usize, pattern_width: usize) -> Vec<f64> {
    (0..pattern_width)
        .map(|column| {
            (0..pattern_count)
                .map(|row| values[row * pattern_width + column])
                .sum::<f64>()
                / pattern_count as f64
        })
        .collect()
}

fn mean(values: &[f64]) -> f64 {
    values.iter().sum::<f64>() / values.len() as f64
}

fn peak_to_peak(values: &[f64]) -> f64 {
    let minimum = values.iter().copied().fold(f64::INFINITY, f64::min);
    let maximum = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    maximum - minimum
}

/// Calculate the FFT display vectors and periodic/random split of a TIE track.
///
/// The moving-average width, threshold comparison, interpolation/extrapolation
/// and inverse-FFT normalization match the corresponding portion of PyBERT's
/// `calc_jitter`; dual-Dirac histogram fitting remains a separate stage.
pub fn calculate_spectral_jitter(
    ui_s: f64,
    nui: usize,
    tie_times_s: &[f64],
    jitter_s: &[f64],
    data_independent_tie_s: &[f64],
    relative_threshold: f64,
) -> Result<SpectralJitterResult, CrossingError> {
    if !ui_s.is_finite() || ui_s <= 0.0 {
        return Err(CrossingError::InvalidUi);
    }
    if nui < 101
        || tie_times_s.len() < 2
        || tie_times_s.len() != jitter_s.len()
        || jitter_s.len() != data_independent_tie_s.len()
        || tie_times_s
            .iter()
            .chain(jitter_s)
            .chain(data_independent_tie_s)
            .chain([relative_threshold].iter())
            .any(|value| !value.is_finite())
    {
        return Err(CrossingError::InsufficientSpectralSamples);
    }
    let sample_times_s = (0..nui)
        .map(|index| index as f64 * ui_s)
        .collect::<Vec<_>>();
    let total_samples = interpolate_linear_extrapolate(tie_times_s, jitter_s, &sample_times_s)?;
    let independent_samples =
        interpolate_linear_extrapolate(tie_times_s, data_independent_tie_s, &sample_times_s)?;
    let total_fft = forward_fft(&total_samples);
    let independent_fft = forward_fft(&independent_samples);
    let magnitudes = independent_fft
        .iter()
        .map(|value| value.norm())
        .collect::<Vec<_>>();
    let moving_mean = moving_average_protect_edges(&magnitudes, 100)?;
    let variance_input = magnitudes
        .iter()
        .zip(&moving_mean)
        .map(|(value, average)| (value - average).powi(2))
        .collect::<Vec<_>>();
    let moving_sigma = moving_average_protect_edges(&variance_input, 100)?
        .into_iter()
        .map(f64::sqrt)
        .collect::<Vec<_>>();
    let periodic_threshold = moving_mean
        .iter()
        .zip(&moving_sigma)
        .map(|(average, sigma)| average + relative_threshold * sigma)
        .collect::<Vec<_>>();
    let periodic_fft = independent_fft
        .iter()
        .zip(&magnitudes)
        .zip(&periodic_threshold)
        .map(|((&value, &magnitude), &threshold)| {
            if magnitude > threshold {
                value
            } else {
                Complex::new(0.0, 0.0)
            }
        })
        .collect::<Vec<_>>();
    let random_fft = independent_fft
        .iter()
        .zip(&magnitudes)
        .zip(&periodic_threshold)
        .map(|((&value, &magnitude), &threshold)| {
            if magnitude > threshold {
                Complex::new(0.0, 0.0)
            } else {
                value
            }
        })
        .collect::<Vec<_>>();
    let periodic_tie = inverse_fft_real(&periodic_fft);
    let random_tie = inverse_fft_real(&random_fft);
    let random_mean = mean(&random_tie);
    let random_jitter_s = (random_tie
        .iter()
        .map(|value| (value - random_mean).powi(2))
        .sum::<f64>()
        / random_tie.len() as f64)
        .sqrt();
    let half_len = nui / 2;
    let frequency_step_hz = 1.0 / (ui_s * nui as f64);
    Ok(SpectralJitterResult {
        periodic_jitter_s: peak_to_peak(&periodic_tie),
        random_jitter_s,
        total_spectrum: total_fft[..half_len]
            .iter()
            .map(|value| value.norm())
            .collect(),
        data_independent_spectrum: magnitudes[..half_len].to_vec(),
        frequencies_hz: (0..half_len)
            .map(|index| index as f64 * frequency_step_hz)
            .collect(),
        periodic_threshold: periodic_threshold[..half_len].to_vec(),
    })
}

/// Match PyBERT's dual-Dirac histogram diagnostics and legacy tail-fit output.
///
/// The reference uses a `[1, 1]` Gaussian fit seed while its public contract
/// is seconds. At SI-scale bin centers that Gaussian underflows, so successful
/// SciPy tail fits retain the seed and are converted to 1 ps. Preserve that v1
/// compatibility behavior explicitly; a corrected estimator needs a new API.
pub fn calculate_dual_dirac_jitter(
    ui_s: f64,
    jitter_s: &[f64],
    data_independent_tie_s: &[f64],
    num_bins: usize,
    smooth_width: usize,
) -> Result<DualDiracJitterResult, CrossingError> {
    if !ui_s.is_finite()
        || ui_s <= 0.0
        || num_bins < 3
        || smooth_width == 0
        || jitter_s.is_empty()
        || jitter_s.len() != data_independent_tie_s.len()
        || jitter_s
            .iter()
            .chain(data_independent_tie_s)
            .any(|value| !value.is_finite())
    {
        return Err(CrossingError::InvalidDualDiracInput);
    }

    let (independent_histogram, bin_centers_s) =
        pybert_histogram(data_independent_tie_s, ui_s, num_bins)?;
    let (total_histogram, _) = pybert_histogram(jitter_s, ui_s, num_bins)?;
    let data_independent_histogram =
        moving_average_protect_edges(&independent_histogram, smooth_width)?;
    let total_histogram = moving_average_protect_edges(&total_histogram, smooth_width)?;
    let center_index = (num_bins - 1) / 2;
    let peak_indices = local_peak_indices(&total_histogram, center_index);
    let negative_peak = peak_indices
        .iter()
        .copied()
        .filter(|&index| index < center_index)
        .max_by(|&left, &right| total_histogram[left].total_cmp(&total_histogram[right]))
        .unwrap_or(center_index);
    let positive_peak = peak_indices
        .iter()
        .copied()
        .filter(|&index| index > center_index)
        .max_by(|&left, &right| total_histogram[left].total_cmp(&total_histogram[right]))
        .unwrap_or(center_index);
    let has_both_tails = total_histogram[positive_peak..]
        .iter()
        .any(|&value| value < total_histogram[positive_peak] / 2.0)
        && total_histogram[..negative_peak]
            .iter()
            .any(|&value| value < total_histogram[negative_peak] / 2.0);

    let (positive_mean_s, positive_sigma_s, negative_mean_s, negative_sigma_s) = if has_both_tails {
        (1.0e-12, 1.0e-12, 1.0e-12, 1.0e-12)
    } else {
        (0.0, 0.0, 0.0, 0.0)
    };
    Ok(DualDiracJitterResult {
        periodic_jitter_s: bin_centers_s[positive_peak] - bin_centers_s[negative_peak],
        random_jitter_s: (positive_sigma_s + negative_sigma_s) / 2.0,
        total_histogram,
        data_independent_histogram,
        bin_centers_s,
        positive_mean_s,
        negative_mean_s,
    })
}

fn pybert_histogram(
    values: &[f64],
    ui_s: f64,
    num_bins: usize,
) -> Result<(Vec<f64>, Vec<f64>), CrossingError> {
    let step = ui_s / (num_bins - 2) as f64;
    let mut edges = Vec::with_capacity(num_bins + 1);
    edges.push(-ui_s);
    edges.extend((0..num_bins - 1).map(|index| -ui_s / 2.0 + index as f64 * step));
    edges.push(ui_s);
    let mut counts = vec![0_usize; num_bins];
    for &value in values {
        if value < edges[0] || value > *edges.last().expect("non-empty histogram edges") {
            continue;
        }
        let upper = edges.partition_point(|edge| *edge <= value);
        let index = upper.saturating_sub(1).min(num_bins - 1);
        counts[index] += 1;
    }
    let count_sum = counts.iter().sum::<usize>();
    if count_sum == 0 {
        return Err(CrossingError::InvalidDualDiracInput);
    }
    let histogram = counts
        .into_iter()
        .enumerate()
        .map(|(index, count)| {
            let mass = count as f64 / count_sum as f64;
            mass / (edges[index + 1] - edges[index])
        })
        .collect();
    let mut centers = Vec::with_capacity(num_bins);
    centers.push(-ui_s / 2.0);
    centers.extend((1..num_bins - 1).map(|index| (edges[index] + edges[index + 1]) / 2.0));
    centers.push(ui_s / 2.0);
    Ok((histogram, centers))
}

fn local_peak_indices(values: &[f64], center_index: usize) -> Vec<usize> {
    if values.len() < 3 {
        return Vec::new();
    }
    let differences = values
        .windows(2)
        .map(|pair| pair[1] - pair[0])
        .collect::<Vec<_>>();
    differences
        .windows(2)
        .enumerate()
        .filter_map(|(index, pair)| {
            let peak_index = index + 1;
            ((pair[1].signum() - pair[0].signum()) < 0.0 && peak_index.abs_diff(center_index) > 1)
                .then_some(peak_index)
        })
        .collect()
}

fn interpolate_linear_extrapolate(
    source_times_s: &[f64],
    source_values: &[f64],
    target_times_s: &[f64],
) -> Result<Vec<f64>, CrossingError> {
    if source_times_s.windows(2).any(|pair| pair[1] <= pair[0]) {
        return Err(CrossingError::InvalidCrossingTrack);
    }
    Ok(target_times_s
        .iter()
        .map(|&target| {
            let upper = source_times_s.partition_point(|time| *time < target);
            let left = upper.saturating_sub(1).min(source_times_s.len() - 2);
            let right = left + 1;
            let fraction =
                (target - source_times_s[left]) / (source_times_s[right] - source_times_s[left]);
            source_values[left] + fraction * (source_values[right] - source_values[left])
        })
        .collect())
}

fn forward_fft(values: &[f64]) -> Vec<Complex<f64>> {
    let mut spectrum = values
        .iter()
        .map(|&value| Complex::new(value, 0.0))
        .collect::<Vec<_>>();
    FftPlanner::<f64>::new()
        .plan_fft_forward(spectrum.len())
        .process(&mut spectrum);
    spectrum
}

fn inverse_fft_real(values: &[Complex<f64>]) -> Vec<f64> {
    let mut samples = values.to_vec();
    let sample_count = samples.len();
    FftPlanner::<f64>::new()
        .plan_fft_inverse(sample_count)
        .process(&mut samples);
    samples
        .into_iter()
        .map(|value| value.re / sample_count as f64)
        .collect()
}

fn moving_average_protect_edges(values: &[f64], width: usize) -> Result<Vec<f64>, CrossingError> {
    if values.len() < width + 1 {
        return Err(CrossingError::InsufficientSpectralSamples);
    }
    let half_width = width.div_ceil(2);
    let triangle = (0..(2 * half_width - 1))
        .map(|index| {
            let distance = index.abs_diff(half_width - 1);
            (half_width - distance) as f64 / (half_width * half_width) as f64
        })
        .collect::<Vec<_>>();
    let interior = &values[1..values.len() - 1];
    let mut smoothed = Vec::with_capacity(values.len());
    smoothed.push(values[0]);
    for index in 0..interior.len() {
        let mut total = 0.0;
        for (kernel_index, &weight) in triangle.iter().enumerate() {
            let source = index as isize + kernel_index as isize - (half_width - 1) as isize;
            if (0..interior.len() as isize).contains(&source) {
                total += interior[source as usize] * weight;
            }
        }
        smoothed.push(total);
    }
    smoothed.push(*values.last().expect("validated minimum length"));
    Ok(smoothed)
}
