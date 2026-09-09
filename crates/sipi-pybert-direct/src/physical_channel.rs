//! Explicit physical voltage boundary for the existing native link stages.
//! This is not the PB-02 power-wave normalization or legacy impulse trimming.

use std::path::Path;

use num_complex::Complex64;
use serde_json::json;

use crate::{
    ChannelInputV1, ChannelResponseV1, DirectRunError, DirectRunReport, MetallicLineChannelV1,
    MetallicLineConfig, ModulationV1, NativeSimulationError, PatternV1, SimulationInputV1,
    calculate_metallic_line, inverse_real_spectrum, simulate_native_v1,
    strict_simulation_input_json, write_simulation_artifacts_with_schema_and_backend,
};

pub const PHYSICAL_CHANNEL_POLICY_V1: &str = "physical-voltage-v1";

fn invalid(message: &str) -> DirectRunError {
    DirectRunError::Json(format!("physical channel: {message}"))
}

fn resource_limit() -> DirectRunError {
    NativeSimulationError::ResourceLimitExceeded.into()
}

fn integer_grid(value: f64) -> Result<usize, DirectRunError> {
    if !value.is_finite()
        || value < 1.0
        || value >= usize::MAX as f64
        || (value - value.round()).abs() > 1e-12 * value.max(1.0)
    {
        return Err(invalid(
            "frequency/time grid must have an integral sample count",
        ));
    }
    Ok(value.round() as usize)
}

fn finite(value: Complex64) -> bool {
    value.re.is_finite() && value.im.is_finite()
}

/// Vload / Vhalf_open. Source capacitance is on the line side of Rs; the
/// open-circuit source is 2 * Vhalf_open. All capacitances are differential
/// equivalent circuit values, not per-leg values silently divided by two.
fn voltage_transfer(
    line: &MetallicLineChannelV1,
    omega: &[f64],
) -> Result<Vec<Complex64>, DirectRunError> {
    let (gamma, zc) = calculate_metallic_line(
        MetallicLineConfig {
            skin_effect_resistance_ohm_per_m: line.skin_effect_resistance_ohm_per_m,
            crossover_angular_frequency_rad_per_s: line.crossover_angular_frequency_rad_per_s,
            dc_resistance_ohm_per_m: line.dc_resistance_ohm_per_m,
            characteristic_impedance_ohm: line.characteristic_impedance.0,
            propagation_velocity_m_per_s: line.propagation_velocity_m_per_s,
            loss_tangent: line.loss_tangent,
        },
        &omega[1..],
    )
    .map_err(NativeSimulationError::from)?;
    let mut values = Vec::with_capacity(omega.len());
    values.push(Complex64::new(
        2.0 * line.load_impedance.0
            / (line.source_impedance.0
                + line.dc_resistance_ohm_per_m * line.length_m
                + line.load_impedance.0),
        0.0,
    ));
    let one = Complex64::new(1.0, 0.0);
    for ((&w, propagation), z) in omega[1..].iter().zip(gamma).zip(zc) {
        let source_divisor =
            one + Complex64::new(0.0, w * line.source_impedance.0 * line.source_capacitance_f);
        let zs = line.source_impedance.0 / source_divisor;
        let zl = line.load_impedance.0
            / (one + Complex64::new(0.0, w * line.load_impedance.0 * line.load_capacitance_f));
        let p = (-propagation * line.length_m).exp();
        let source_reflection = (zs - z) / (zs + z);
        let load_reflection = (zl - z) / (zl + z);
        // Reflection form avoids cosh/sinh overflow on strongly attenuating lines.
        values.push(
            2.0 / source_divisor * (z / (zs + z)) * p * (one + load_reflection)
                / (one - source_reflection * load_reflection * p * p),
        );
    }
    if values.iter().any(|&value| !finite(value)) {
        return Err(invalid(
            "material/termination response is not representable as finite f64",
        ));
    }
    Ok(values)
}

pub fn run_channel_physical_json(
    bytes: &[u8],
    input_file: &Path,
    output_dir: &Path,
) -> Result<DirectRunReport, DirectRunError> {
    // Keep duplicate-field and unknown-field checks at this callable boundary,
    // not only in the outer SIPI argv adapter.
    let _: SimulationInputV1 =
        serde_json::from_slice(bytes).map_err(|error| DirectRunError::Json(error.to_string()))?;
    let input = strict_simulation_input_json(bytes)?;
    input.validate().map_err(NativeSimulationError::from)?;
    let ChannelInputV1::MetallicLine(line) = &input.channel else {
        return Err(invalid("this policy requires a metallic_line request"));
    };
    let dt = input.timebase.sample_interval.0;
    if line.sample_interval != input.timebase.sample_interval
        || !(0.0..std::f64::consts::FRAC_PI_2).contains(&line.loss_tangent)
    {
        return Err(invalid(
            "line sample interval or passive dielectric exponent is invalid",
        ));
    }
    let bits = match &input.pattern {
        PatternV1::Prbs { .. } => {
            usize::try_from(input.timebase.nbits).map_err(|_| resource_limit())?
        }
        PatternV1::ExplicitBits { bits, .. } => {
            if bits.is_empty() || bits.len() as u64 != input.timebase.nbits {
                return Err(invalid("explicit bits must match the declared timebase"));
            }
            bits.len()
        }
    };
    let encoded_bits =
        if input.rx.viterbi_enabled && input.rx.viterbi.as_ref().is_some_and(|v| v.fec) {
            bits.checked_mul(2).ok_or_else(resource_limit)?
        } else {
            bits
        };
    let symbols = if matches!(input.modulation, ModulationV1::Pam4) {
        encoded_bits / 2
    } else {
        encoded_bits
    };
    let sample_count = symbols
        .checked_mul(input.timebase.samples_per_ui as usize)
        .ok_or_else(resource_limit)?;
    let fft_size = match line.frequency_step_hz {
        Some(step) => integer_grid(1.0 / (step.0 * dt))?,
        None => sample_count,
    };
    if fft_size < 2
        || fft_size as u64 > input.limits.max_total_samples
        || sample_count as u64 > input.limits.max_total_samples
    {
        return Err(resource_limit());
    }
    // An explicit grid is an input key, not a value to round-trip through dt.
    let step = line
        .frequency_step_hz
        .map_or(1.0 / (fft_size as f64 * dt), |step| step.0);
    let last_bin = match line.frequency_max_hz {
        Some(maximum) => integer_grid(maximum.0 / step)?,
        None => fft_size / 2,
    };
    if last_bin == 0 || last_bin > fft_size / 2 {
        return Err(invalid(
            "declared material bandwidth exceeds the time-grid Nyquist frequency",
        ));
    }
    let impulse_samples = match line.impulse_length {
        Some(duration) => integer_grid(duration.0 / dt)?,
        None => fft_size,
    };
    if impulse_samples > fft_size {
        return Err(invalid(
            "impulse duration exceeds the transform period; decrease frequencyStepHz",
        ));
    }
    // Reserve the new stage's buffers/telemetry in addition to the existing
    // link-stage budget. This remains a conservative estimate, not an OS cap.
    let reserved = (fft_size as u64)
        .checked_mul(256)
        .ok_or_else(resource_limit)?;
    let remaining_memory = input
        .limits
        .max_memory_bytes
        .checked_sub(reserved)
        .filter(|&n| n > 0)
        .ok_or_else(resource_limit)?;
    let frequency = (0..=last_bin).map(|i| i as f64 * step).collect::<Vec<_>>();
    let omega = frequency
        .iter()
        .map(|f| std::f64::consts::TAU * f)
        .collect::<Vec<_>>();
    let physical = voltage_transfer(line, &omega)?;
    let mut loaded = physical.clone();
    if line.apply_raised_cosine_window {
        for (i, value) in loaded.iter_mut().enumerate() {
            let weight = if i == last_bin {
                0.0
            } else {
                0.5 * (1.0 + (std::f64::consts::PI * i as f64 / last_bin as f64).cos())
            };
            *value *= weight;
        }
    }
    let mut real = vec![0.0; fft_size / 2 + 1];
    let mut imag = real.clone();
    for (i, value) in loaded.iter().enumerate() {
        real[i] = value.re;
        imag[i] = value.im;
    }
    if fft_size.is_multiple_of(2) && imag[fft_size / 2].abs() > 1e-12 {
        return Err(invalid(
            "complex Nyquist endpoint needs an explicit window or a lower material bandwidth",
        ));
    }
    let mut impulse =
        inverse_real_spectrum(&real, &imag, fft_size).map_err(NativeSimulationError::from)?;
    let full_energy = impulse.iter().map(|v| v * v).sum::<f64>();
    let discarded_energy = impulse[impulse_samples..]
        .iter()
        .map(|v| v * v)
        .sum::<f64>();
    let end_quarter_energy = impulse[3 * fft_size / 4..]
        .iter()
        .map(|v| v * v)
        .sum::<f64>();
    if !full_energy.is_finite() || !discarded_energy.is_finite() {
        return Err(invalid("impulse energy is not representable as finite f64"));
    }
    impulse.truncate(impulse_samples);
    let peak = impulse
        .iter()
        .enumerate()
        .max_by(|a, b| a.1.abs().total_cmp(&b.1.abs()))
        .map_or(0, |(i, _)| i);
    let contract = json!({
        "policy": PHYSICAL_CHANNEL_POLICY_V1,
        "voltage": "Vload / Vhalf_open; open source is 2 * native TX; Cs is after Rs; all C values are differential-equivalent",
        "frequency_step_hz": step, "material_frequency_max_hz": frequency[last_bin],
        "fft_size": fft_size, "fft_period_s": fft_size as f64 * dt,
        "window": if line.apply_raised_cosine_window { "0.5*(1+cos(pi*f/fmax)); endpoint exactly zero" } else { "none" },
        "above_material_band": "zero-filled, not extrapolated",
        "impulse_origin_s": 0, "discarded_prefix_samples": 0,
        "impulse_tail_policy": "only an explicit impulseLength truncates the end; never peak-aligned",
        "retained_impulse_samples": impulse.len(),
        "discarded_tail_energy_fraction": if full_energy > 0.0 { discarded_energy / full_energy } else { 0.0 },
        "transform_end_quarter_energy_fraction": if full_energy > 0.0 { end_quarter_energy / full_energy } else { 0.0 },
        "nominal_line_delay_s": line.length_m / line.propagation_velocity_m_per_s,
        "kernel_peak_time_s": peak as f64 * dt,
        "td_contract": "finite-band periodic IFFT kernel; existing zero-prehistory sample-hold native link; no guarantee of continuous-time causality or ADS finite-edge parity",
        "acceptance": false
    });
    let mut prepared = crate::runner::upstream_native_input(input.clone());
    prepared.channel = ChannelInputV1::ImpulseResponse(ChannelResponseV1 {
        sample_interval: line.sample_interval,
        impulse_response_volts_per_second: impulse.iter().map(|v| v / dt).collect(),
        source_impedance: line.source_impedance,
        load_impedance: line.load_impedance,
    });
    prepared.limits.max_memory_bytes = remaining_memory;
    let mut output = crate::runner::native_cli_output(simulate_native_v1(&prepared)?);
    output
        .arrays
        .insert("physical_channel_frequency_hz".into(), frequency);
    for (prefix, values) in [
        ("physical_channel_voltage", &physical),
        ("physical_channel_windowed", &loaded),
    ] {
        output.arrays.insert(
            format!("{prefix}_re"),
            values.iter().map(|v| v.re).collect(),
        );
        output.arrays.insert(
            format!("{prefix}_im"),
            values.iter().map(|v| v.im).collect(),
        );
    }
    write_simulation_artifacts_with_schema_and_backend(
        crate::runner::upstream_native_input(input),
        input_file,
        output_dir,
        output,
        Some(json!({"physical_channel": contract})),
        "sipi.channel.physical-result.v1",
        "rust_channel_physical",
        None,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn line() -> MetallicLineChannelV1 {
        let input: SimulationInputV1 = serde_json::from_slice(include_bytes!(
            "../../../examples/channel-native/metallic-line.json"
        ))
        .unwrap();
        let ChannelInputV1::MetallicLine(mut line) = input.channel else {
            unreachable!()
        };
        line.skin_effect_resistance_ohm_per_m = 0.0;
        line.dc_resistance_ohm_per_m = 0.0;
        line.loss_tangent = 0.0;
        line.propagation_velocity_m_per_s = 200e6;
        line.source_capacitance_f = 0.0;
        line.load_capacitance_f = 0.0;
        line
    }

    #[test]
    fn actual_voltage_matches_lossless_abcd_with_both_rc_terminations() {
        let omega = [0.0, 1e-8, 2e8, 7e9, 5e10, 4e11];
        for (rs, rl, cs, cl) in [
            (100.0, 100.0, 0.0, 0.0),
            (35.0, 90.0, 0.0, 0.0),
            (35.0, 90.0, 0.2e-12, 0.0),
            (100.0, 100.0, 0.0, 0.2e-12),
            (35.0, 90.0, 0.15e-12, 0.3e-12),
        ] {
            let mut line = line();
            line.source_impedance.0 = rs;
            line.load_impedance.0 = rl;
            line.source_capacitance_f = cs;
            line.load_capacitance_f = cl;
            let actual = voltage_transfer(&line, &omega).unwrap();
            for (&w, h) in omega.iter().zip(actual) {
                let theta = w * line.length_m / line.propagation_velocity_m_per_s;
                let a = Complex64::new(theta.cos(), 0.0);
                let b = Complex64::new(0.0, line.characteristic_impedance.0 * theta.sin());
                let c = Complex64::new(0.0, theta.sin() / line.characteristic_impedance.0);
                let ys = Complex64::new(1.0 / rs, w * cs);
                let yl = Complex64::new(1.0 / rl, w * cl);
                let expected = (2.0 / rs) / (c + a * yl + ys * (a + b * yl));
                assert!((h - expected).norm() < 1e-12, "w={w}: {h} != {expected}");
            }
        }
    }

    #[test]
    fn zero_length_has_combined_shunt_capacitance_and_long_lossy_line_does_not_overflow() {
        let mut line = line();
        line.length_m = 0.0;
        line.source_capacitance_f = 0.2e-12;
        line.load_capacitance_f = 0.3e-12;
        let omega = [0.0, 1e10, 1e12];
        for (&w, h) in omega.iter().zip(voltage_transfer(&line, &omega).unwrap()) {
            let expected = 1.0 / Complex64::new(1.0, w * 50.0 * 0.5e-12);
            assert!((h - expected).norm() < 1e-12);
        }
        line.length_m = 1e6;
        line.dc_resistance_ohm_per_m = 20.0;
        line.loss_tangent = 0.02;
        let values = voltage_transfer(&line, &omega).unwrap();
        assert_eq!(values[0], Complex64::new(200.0 / 20_000_200.0, 0.0));
        assert!(values[1..].iter().all(|v| *v == Complex64::new(0.0, 0.0)));
    }
}
