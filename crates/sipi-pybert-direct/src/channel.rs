//! Frequency-domain transmission-line channel primitives.
//!
//! These are deliberately limited to the legacy analytic metallic-line model
//! and its source/load termination algebra. Touchstone parsing and circuit I/O
//! remain host-owned boundaries.

use num_complex::Complex64;
use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum ChannelError {
    #[error("metallic transmission-line parameters are invalid")]
    InvalidMetallicParameters,
    #[error("termination parameters are invalid")]
    InvalidTerminationParameters,
    #[error("angular-frequency samples must be finite, non-negative, and non-empty")]
    InvalidAngularFrequencies,
    #[error("unloaded transfer function and characteristic impedance must have matching lengths")]
    LengthMismatch,
}

/// Howard Johnson metallic transmission-line model parameters in SI units.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct MetallicLineConfig {
    pub skin_effect_resistance_ohm_per_m: f64,
    pub crossover_angular_frequency_rad_per_s: f64,
    pub dc_resistance_ohm_per_m: f64,
    pub characteristic_impedance_ohm: f64,
    pub propagation_velocity_m_per_s: f64,
    pub loss_tangent: f64,
}

/// Driver/load parasitics used by the legacy fully loaded transfer equation.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct TerminationConfig {
    pub source_resistance_ohm: f64,
    pub source_capacitance_f: f64,
    pub load_resistance_ohm: f64,
    pub load_capacitance_f: f64,
}

/// Calculate propagation constant and characteristic impedance for each bin.
///
/// This preserves the Python reference's special DC handling: the first zero
/// angular-frequency sample is evaluated at `1e-12 rad/s`, then its reported
/// characteristic impedance is restored to the configured nominal value.
pub fn calculate_metallic_line(
    config: MetallicLineConfig,
    angular_frequencies_rad_per_s: &[f64],
) -> Result<(Vec<Complex64>, Vec<Complex64>), ChannelError> {
    validate_metallic_config(config)?;
    if !valid_angular_frequencies(angular_frequencies_rad_per_s) {
        return Err(ChannelError::InvalidAngularFrequencies);
    }

    let inductance_h_per_m =
        config.characteristic_impedance_ohm / config.propagation_velocity_m_per_s;
    let capacitance_f_per_m =
        1.0 / (config.characteristic_impedance_ohm * config.propagation_velocity_m_per_s);
    let exponent = -2.0 * config.loss_tangent / std::f64::consts::PI;
    let mut gamma = Vec::with_capacity(angular_frequencies_rad_per_s.len());
    let mut characteristic_impedance = Vec::with_capacity(angular_frequencies_rad_per_s.len());

    for (index, &frequency) in angular_frequencies_rad_per_s.iter().enumerate() {
        let evaluated_frequency = if index == 0 && frequency == 0.0 {
            1.0e-12
        } else {
            frequency
        };
        // A later zero would cause the legacy complex power to diverge; reject
        // it rather than returning a non-finite value into the typed pipeline.
        if evaluated_frequency == 0.0 {
            return Err(ChannelError::InvalidAngularFrequencies);
        }
        let jw = Complex64::new(0.0, evaluated_frequency);
        let ac_resistance = config.skin_effect_resistance_ohm_per_m
            * (Complex64::new(
                0.0,
                2.0 * evaluated_frequency / config.crossover_angular_frequency_rad_per_s,
            ))
            .sqrt();
        let resistance = (Complex64::new(
            config.dc_resistance_ohm_per_m * config.dc_resistance_ohm_per_m,
            0.0,
        ) + ac_resistance * ac_resistance)
            .sqrt();
        let capacitance = capacitance_f_per_m
            * (jw / config.crossover_angular_frequency_rad_per_s).powf(exponent);
        let series_impedance = jw * inductance_h_per_m + resistance;
        let shunt_admittance = jw * capacitance;
        gamma.push((series_impedance * shunt_admittance).sqrt());
        characteristic_impedance.push((series_impedance / shunt_admittance).sqrt());
    }
    if angular_frequencies_rad_per_s[0] == 0.0 {
        characteristic_impedance[0] = Complex64::new(config.characteristic_impedance_ohm, 0.0);
    }
    Ok((gamma, characteristic_impedance))
}

/// Apply the legacy source/load termination and reflection equation.
pub fn calculate_loaded_transfer(
    unloaded_transfer: &[Complex64],
    characteristic_impedance: &[Complex64],
    angular_frequencies_rad_per_s: &[f64],
    termination: TerminationConfig,
) -> Result<Vec<Complex64>, ChannelError> {
    validate_termination(termination)?;
    if unloaded_transfer.len() != characteristic_impedance.len()
        || unloaded_transfer.len() != angular_frequencies_rad_per_s.len()
    {
        return Err(ChannelError::LengthMismatch);
    }
    if !valid_angular_frequencies(angular_frequencies_rad_per_s) {
        return Err(ChannelError::InvalidAngularFrequencies);
    }
    let load_capacitance = if termination.load_capacitance_f == 0.0 {
        1.0e-18
    } else {
        termination.load_capacitance_f
    };
    Ok(unloaded_transfer
        .iter()
        .zip(characteristic_impedance)
        .zip(angular_frequencies_rad_per_s)
        .map(|((&transfer, &impedance), &frequency)| {
            let evaluated_frequency = if frequency == 0.0 { 1.0e-12 } else { frequency };
            let source_impedance = parallel_rc(
                termination.source_resistance_ohm,
                termination.source_capacitance_f,
                evaluated_frequency,
            );
            let load_impedance = parallel_rc(
                termination.load_resistance_ohm,
                load_capacitance,
                evaluated_frequency,
            );
            let source_parallel_line = parallel_rc(
                impedance,
                termination.source_capacitance_f,
                evaluated_frequency,
            );
            let admittance = source_parallel_line
                / (Complex64::new(termination.source_resistance_ohm, 0.0) + source_parallel_line);
            let load_reflection = (load_impedance - impedance) / (load_impedance + impedance);
            let source_reflection = (source_impedance - impedance) / (source_impedance + impedance);
            admittance * transfer * (Complex64::new(1.0, 0.0) + load_reflection)
                / (Complex64::new(1.0, 0.0)
                    - load_reflection * source_reflection * transfer * transfer)
        })
        .collect())
}

fn parallel_rc<R>(resistance: R, capacitance_f: f64, angular_frequency_rad_per_s: f64) -> Complex64
where
    R: Into<Complex64>,
{
    let resistance = resistance.into();
    resistance
        / (Complex64::new(1.0, 0.0)
            + Complex64::new(0.0, angular_frequency_rad_per_s) * resistance * capacitance_f / 2.0)
}

fn validate_metallic_config(config: MetallicLineConfig) -> Result<(), ChannelError> {
    if !config.skin_effect_resistance_ohm_per_m.is_finite()
        || config.skin_effect_resistance_ohm_per_m < 0.0
        || !config.crossover_angular_frequency_rad_per_s.is_finite()
        || config.crossover_angular_frequency_rad_per_s <= 0.0
        || !config.dc_resistance_ohm_per_m.is_finite()
        || config.dc_resistance_ohm_per_m < 0.0
        || !config.characteristic_impedance_ohm.is_finite()
        || config.characteristic_impedance_ohm <= 0.0
        || !config.propagation_velocity_m_per_s.is_finite()
        || config.propagation_velocity_m_per_s <= 0.0
        || !config.loss_tangent.is_finite()
    {
        return Err(ChannelError::InvalidMetallicParameters);
    }
    Ok(())
}

fn validate_termination(termination: TerminationConfig) -> Result<(), ChannelError> {
    if !termination.source_resistance_ohm.is_finite()
        || termination.source_resistance_ohm <= 0.0
        || !termination.source_capacitance_f.is_finite()
        || termination.source_capacitance_f < 0.0
        || !termination.load_resistance_ohm.is_finite()
        || termination.load_resistance_ohm <= 0.0
        || !termination.load_capacitance_f.is_finite()
        || termination.load_capacitance_f < 0.0
    {
        return Err(ChannelError::InvalidTerminationParameters);
    }
    Ok(())
}

fn valid_angular_frequencies(values: &[f64]) -> bool {
    !values.is_empty()
        && values.iter().enumerate().all(|(index, frequency)| {
            frequency.is_finite() && *frequency >= 0.0 && (index == 0 || *frequency > 0.0)
        })
}
