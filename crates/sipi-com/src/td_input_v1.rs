//! Portable r4.80 TDMODE pulse-input preparation and frequency fill-in.

use rustfft::{FftPlanner, num_complex::Complex};
use sipi_types::Complex64;

pub const TD_INPUT_POLICY_V1: &str = "sipi.com.td-input-v1.r480-tmode";

/// Input and work budgets keep the upstream sampled convolution and FFT
/// bounded before any proportional allocation or quadratic loop starts.
pub const MAX_TD_INPUT_SAMPLES_V1: usize = 262_144;
pub const MAX_TD_FREQUENCY_POINTS_V1: usize = 1_048_576;
pub const MAX_TD_WORK_ELEMENTS_V1: usize = 67_108_864;

#[derive(Clone, Debug, PartialEq)]
pub struct TdPulseInputV1 {
    pub time_s: Vec<f64>,
    pub pulse: Vec<f64>,
    pub impulse: Vec<f64>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct TdFrequencyFillinV1 {
    pub frequency_hz: Vec<f64>,
    pub noise_frequency_hz: Vec<f64>,
    pub insertion_loss: Vec<Complex64>,
    /// Synthetic differential SDD matrix, row-major [S11, S12, S21, S22].
    pub sdd: Vec<[Complex64; 4]>,
    pub final_voltage_v: f64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TdInputErrorV1 {
    InvalidSamplesPerUi,
    InvalidTimeAxis,
    InvalidControls,
    FrequencySpanTooShort,
    PulseWindowTooShort,
    ZeroFinalVoltage,
    NonFinite,
    InvalidPulseInvariant,
    OversizeInput,
    WorkBudgetExceeded,
}

/// Port `read_PR_files`' CSV branch, including its three-UI zero prefix and
/// sampled step-to-impulse conversion.
pub fn td_pulse_input_v1(
    time_s: &[f64],
    voltage_v: &[f64],
    samples_per_ui: usize,
) -> Result<TdPulseInputV1, TdInputErrorV1> {
    if samples_per_ui == 0 || time_s.len() < 2 || time_s.len() != voltage_v.len() {
        return Err(TdInputErrorV1::InvalidSamplesPerUi);
    }
    if time_s.len() > MAX_TD_INPUT_SAMPLES_V1 {
        return Err(TdInputErrorV1::OversizeInput);
    }
    if !time_s
        .iter()
        .chain(voltage_v)
        .all(|value| value.is_finite())
        || !time_s.windows(2).all(|pair| pair[1] > pair[0])
    {
        return Err(TdInputErrorV1::InvalidTimeAxis);
    }
    let step = time_s[1] - time_s[0];
    let prefix = 3usize
        .checked_mul(samples_per_ui)
        .ok_or(TdInputErrorV1::InvalidSamplesPerUi)?;
    let total_len = prefix
        .checked_add(time_s.len())
        .ok_or(TdInputErrorV1::OversizeInput)?;
    if total_len > MAX_TD_INPUT_SAMPLES_V1 {
        return Err(TdInputErrorV1::OversizeInput);
    }
    let work = total_len
        .checked_mul(total_len)
        .ok_or(TdInputErrorV1::WorkBudgetExceeded)?;
    if work > MAX_TD_WORK_ELEMENTS_V1 {
        return Err(TdInputErrorV1::WorkBudgetExceeded);
    }
    let mut pulse = vec![0.0; prefix];
    pulse.extend_from_slice(voltage_v);
    let mut expanded_time = (0..prefix)
        .map(|index| index as f64 * step)
        .collect::<Vec<_>>();
    let offset = prefix as f64 * step;
    expanded_time.extend(time_s.iter().map(|value| value + offset));
    if !expanded_time.iter().all(|value| value.is_finite())
        || !expanded_time.windows(2).all(|pair| pair[1] > pair[0])
    {
        return Err(TdInputErrorV1::InvalidTimeAxis);
    }
    let train_len = (pulse.len() / samples_per_ui) * samples_per_ui;
    let mut step_response = vec![0.0; pulse.len()];
    for index in 0..pulse.len() {
        let mut sum = 0.0;
        let upper = index.min(train_len.saturating_sub(1));
        for tap in (0..=upper).step_by(samples_per_ui) {
            sum += pulse[index - tap];
        }
        if !sum.is_finite() {
            return Err(TdInputErrorV1::NonFinite);
        }
        step_response[index] = sum;
    }
    let mut impulse = vec![0.0; pulse.len()];
    for index in 0..pulse.len() {
        impulse[index] = if index == 0 {
            step_response[1]
        } else {
            step_response[index] - step_response[index - 1]
        };
    }
    if !impulse.iter().all(|value| value.is_finite()) {
        return Err(TdInputErrorV1::NonFinite);
    }
    let result = TdPulseInputV1 {
        time_s: expanded_time,
        pulse,
        impulse,
    };
    validate_td_pulse_input_v1(&result, samples_per_ui)?;
    Ok(result)
}

/// Validate the exact typed invariant consumed by the TD FD leaf.
pub fn validate_td_pulse_input_v1(
    channel: &TdPulseInputV1,
    samples_per_ui: usize,
) -> Result<(), TdInputErrorV1> {
    if samples_per_ui == 0
        || channel.time_s.len() < 2
        || channel.time_s.len() != channel.pulse.len()
        || channel.pulse.len() != channel.impulse.len()
    {
        return Err(TdInputErrorV1::InvalidPulseInvariant);
    }
    let sample_count = channel.time_s.len();
    if sample_count > MAX_TD_INPUT_SAMPLES_V1 {
        return Err(TdInputErrorV1::OversizeInput);
    }
    let work = sample_count
        .checked_mul(sample_count)
        .ok_or(TdInputErrorV1::WorkBudgetExceeded)?;
    if work > MAX_TD_WORK_ELEMENTS_V1 {
        return Err(TdInputErrorV1::WorkBudgetExceeded);
    }
    if !channel
        .time_s
        .iter()
        .chain(channel.pulse.iter())
        .chain(channel.impulse.iter())
        .all(|value| value.is_finite())
        || !channel.time_s.windows(2).all(|pair| pair[1] > pair[0])
    {
        return Err(TdInputErrorV1::InvalidPulseInvariant);
    }
    let mut step_response = vec![0.0; sample_count];
    let train_len = (sample_count / samples_per_ui) * samples_per_ui;
    for index in 0..sample_count {
        let upper = index.min(train_len.saturating_sub(1));
        let mut sum = 0.0;
        for tap in (0..=upper).step_by(samples_per_ui) {
            sum += channel.pulse[index - tap];
        }
        if !sum.is_finite() {
            return Err(TdInputErrorV1::NonFinite);
        }
        step_response[index] = sum;
    }
    for index in 0..sample_count {
        let expected = if index == 0 {
            step_response[1]
        } else {
            step_response[index] - step_response[index - 1]
        };
        if !expected.is_finite() || channel.impulse[index] != expected {
            return Err(TdInputErrorV1::InvalidPulseInvariant);
        }
    }
    Ok(())
}

/// Port `TD_FD_fillin` for the fields consumed by the normal COM pipeline.
pub fn td_fd_fillin_v1(
    channel: &TdPulseInputV1,
    baud_hz: f64,
    samples_per_ui: usize,
    bessel_order: usize,
    bessel_cutoff_multiplier: f64,
    bessel_enabled: bool,
    butterworth_cutoff_multiplier: f64,
    butterworth_enabled: bool,
) -> Result<TdFrequencyFillinV1, TdInputErrorV1> {
    if baud_hz <= 0.0 || !baud_hz.is_finite() || samples_per_ui == 0 || channel.time_s.len() < 2 {
        return Err(TdInputErrorV1::InvalidControls);
    }
    validate_td_pulse_input_v1(channel, samples_per_ui)?;
    let step = channel.time_s[1] - channel.time_s[0];
    let span = *channel
        .time_s
        .last()
        .ok_or(TdInputErrorV1::InvalidTimeAxis)?;
    if !(step > 0.0 && span > 0.0) {
        return Err(TdInputErrorV1::InvalidTimeAxis);
    }
    let frequency_step = 1.0 / span;
    let frequency_limit = 1.0 / step + 0.5 / span;
    if !frequency_step.is_finite() || !frequency_limit.is_finite() {
        return Err(TdInputErrorV1::InvalidTimeAxis);
    }
    let mut frequency_hz = Vec::new();
    let mut value = 0.0;
    while value <= frequency_limit {
        if frequency_hz.len() == MAX_TD_FREQUENCY_POINTS_V1 {
            return Err(TdInputErrorV1::OversizeInput);
        }
        frequency_hz.push(value);
        value += frequency_step;
        if !value.is_finite() {
            return Err(TdInputErrorV1::InvalidTimeAxis);
        }
    }
    let mut spectrum = channel
        .pulse
        .iter()
        .map(|value| Complex::new(*value, 0.0))
        .collect::<Vec<_>>();
    let mut planner = FftPlanner::<f64>::new();
    planner
        .plan_fft_forward(spectrum.len())
        .process(&mut spectrum);
    let spectrum_len = channel.pulse.len() / 2;
    if frequency_hz.len() < spectrum_len {
        return Err(TdInputErrorV1::FrequencySpanTooShort);
    }
    let limit = frequency_hz
        .iter()
        .position(|value| *value >= 0.75 * baud_hz)
        .map(|index| index + 1)
        .ok_or(TdInputErrorV1::FrequencySpanTooShort)?;
    if limit > spectrum_len || limit == 0 {
        return Err(TdInputErrorV1::FrequencySpanTooShort);
    }
    let axis = &frequency_hz[..limit];
    let bessel = crate::bessel_thomson_filter_v1(
        axis,
        bessel_order,
        bessel_cutoff_multiplier,
        baud_hz,
        bessel_enabled,
    )
    .map_err(|_| TdInputErrorV1::InvalidControls)?;
    let butterworth = crate::butterworth_filter_v1(
        axis,
        butterworth_cutoff_multiplier,
        baud_hz,
        butterworth_enabled,
    )
    .map_err(|_| TdInputErrorV1::InvalidControls)?;
    let train_len = 200usize
        .checked_mul(samples_per_ui)
        .ok_or(TdInputErrorV1::InvalidSamplesPerUi)?;
    if train_len > channel.pulse.len() {
        return Err(TdInputErrorV1::PulseWindowTooShort);
    }
    let mut train = vec![0.0; train_len];
    for index in (0..train_len).step_by(samples_per_ui) {
        train[index] = 1.0;
    }
    let mut final_voltage = 0.0;
    for index in 0..train_len {
        final_voltage += train[index] * channel.pulse[train_len - 1 - index];
    }
    if !final_voltage.is_finite() || final_voltage == 0.0 {
        return Err(TdInputErrorV1::ZeroFinalVoltage);
    }
    let insertion_loss = axis
        .iter()
        .enumerate()
        .map(|(index, frequency)| {
            let x = std::f64::consts::PI * *frequency / baud_hz;
            let prr = if x == 0.0 { 1.0 } else { x.sin() / x };
            let denominator = 2.0 * samples_per_ui as f64 * prr;
            let value = Complex64::try_new(spectrum[index].re, spectrum[index].im)
                .map_err(|_| TdInputErrorV1::NonFinite)?;
            let value = complex_div_v1(
                value,
                Complex64::try_new(denominator, 0.0).map_err(|_| TdInputErrorV1::NonFinite)?,
            )
            .map_err(|_| TdInputErrorV1::NonFinite)?;
            let value =
                complex_div_v1(value, bessel[index]).map_err(|_| TdInputErrorV1::NonFinite)?;
            let value =
                complex_div_v1(value, butterworth[index]).map_err(|_| TdInputErrorV1::NonFinite)?;
            Complex64::try_new(
                value.real() / final_voltage,
                value.imaginary() / final_voltage,
            )
            .map_err(|_| TdInputErrorV1::NonFinite)
        })
        .collect::<Result<Vec<_>, _>>()?;
    let zero = Complex64::try_new(0.0, 0.0).map_err(|_| TdInputErrorV1::NonFinite)?;
    let sdd = insertion_loss
        .iter()
        .map(|value| [zero, *value, *value, zero])
        .collect();
    Ok(TdFrequencyFillinV1 {
        frequency_hz: axis.to_vec(),
        noise_frequency_hz: frequency_hz,
        insertion_loss,
        sdd,
        final_voltage_v: final_voltage,
    })
}

fn complex_div_v1(left: Complex64, right: Complex64) -> Result<Complex64, TdInputErrorV1> {
    let denominator = right.real() * right.real() + right.imaginary() * right.imaginary();
    if !denominator.is_finite() || denominator == 0.0 {
        return Err(TdInputErrorV1::NonFinite);
    }
    Complex64::try_new(
        (left.real() * right.real() + left.imaginary() * right.imaginary()) / denominator,
        (left.imaginary() * right.real() - left.real() * right.imaginary()) / denominator,
    )
    .map_err(|_| TdInputErrorV1::NonFinite)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn td_input_matches_prefix_and_sampled_impulse_contract() {
        let input =
            td_pulse_input_v1(&[0.0, 1.0e-12, 2.0e-12], &[0.1, 0.2, 0.3], 2).expect("TD input");
        assert_eq!(
            input.pulse,
            vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.2, 0.3]
        );
        assert_eq!(
            input.impulse,
            vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.1, 0.2]
        );
        assert_eq!(
            input.time_s,
            (0..9)
                .map(|index| index as f64 * 1.0e-12)
                .collect::<Vec<_>>()
        );
        validate_td_pulse_input_v1(&input, 2).expect("typed invariant");
    }

    #[test]
    fn td_frequency_fillin_requires_source_window_and_returns_complex_sdd() {
        let voltage = (0..400)
            .map(|index| if index > 100 { 1.0 } else { 0.0 })
            .collect::<Vec<_>>();
        let time = (0..400)
            .map(|index| index as f64 * 1.0e-12)
            .collect::<Vec<_>>();
        let input = td_pulse_input_v1(&time, &voltage, 2).expect("TD input");
        let fillin =
            td_fd_fillin_v1(&input, 1.0e9, 2, 2, 0.5, false, 0.6, false).expect("TD fill-in");
        assert!(!fillin.frequency_hz.is_empty());
        assert_eq!(fillin.frequency_hz.len(), fillin.insertion_loss.len());
        assert_eq!(fillin.sdd.len(), fillin.frequency_hz.len());
        assert!(
            fillin
                .sdd
                .iter()
                .all(|row| row[1] == row[2] && row[0].real() == 0.0 && row[3].real() == 0.0)
        );
        assert!(fillin.final_voltage_v.is_finite());
        assert_eq!(fillin.frequency_hz.len(), 2);
        assert_eq!(fillin.noise_frequency_hz.len(), 406);
        assert!((fillin.final_voltage_v - 147.0).abs() < 1.0e-12);
        assert!((fillin.insertion_loss[0].real() - 0.5085034013605442).abs() < 1.0e-12);
        assert!(fillin.insertion_loss[0].imaginary().abs() < 1.0e-12);
        assert!((fillin.insertion_loss[1].real() + 0.8605357080426795).abs() < 1.0e-12);
        assert!((fillin.insertion_loss[1].imaginary() - 0.9226525135553848).abs() < 1.0e-12);
    }

    #[test]
    fn td_input_rejects_typed_invariant_and_budget_mutations() {
        let malformed = TdPulseInputV1 {
            time_s: vec![0.0, 1.0, 2.0],
            pulse: vec![0.0, 1.0, 1.0],
            impulse: vec![0.0, 1.0, 0.0],
        };
        assert_eq!(
            validate_td_pulse_input_v1(&malformed, 1),
            Err(TdInputErrorV1::InvalidPulseInvariant)
        );
        let non_increasing = TdPulseInputV1 {
            time_s: vec![0.0, 1.0, 1.0],
            pulse: vec![0.0, 1.0, 1.0],
            impulse: vec![1.0, 1.0, 1.0],
        };
        assert_eq!(
            validate_td_pulse_input_v1(&non_increasing, 1),
            Err(TdInputErrorV1::InvalidPulseInvariant)
        );
        let oversized = vec![0.0; MAX_TD_INPUT_SAMPLES_V1 + 1];
        assert_eq!(
            td_pulse_input_v1(&oversized, &oversized, 1),
            Err(TdInputErrorV1::OversizeInput)
        );
    }
}
