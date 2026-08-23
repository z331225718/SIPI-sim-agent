//! Portable receiver-noise calibration primitives from `calibration.py`.
//!
//! The controller is intentionally independent of the COM run boundary: the
//! caller owns case evaluation and supplies the resulting COM values.  This
//! keeps the source's worst-case outer-loop semantics visible and makes the
//! numerical leaf useful to both COM-02 and COM-04.

use sipi_types::Complex64;

pub const CALIBRATION_POLICY_V1: &str = "sipi.com.calibration-v1.r480-receiver-noise-controller";
/// Bounded default matching the upstream controller's public iteration budget.
pub const MAX_CALIBRATION_ITERATIONS_V1: usize = 512;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CalibrationNoiseResultV1 {
    pub sigma_ne_v: f64,
    pub sigma_hp_v: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct CalibrationIterationV1 {
    pub sigma_bn_v: f64,
    pub step_v: f64,
    pub case_com_db: Vec<f64>,
    pub minimum_com_db: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct CalibrationResultV1 {
    pub sigma_bn_v: f64,
    pub final_step_v: f64,
    pub iterations: Vec<CalibrationIterationV1>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CalibrationErrorV1 {
    InvalidInput,
    FrequencyDoesNotReachHalfBaud,
    Evaluator,
    IterationLimit,
}

fn finite_complex(value: Complex64) -> bool {
    value.real().is_finite() && value.imaginary().is_finite()
}

fn magnitude(value: Complex64) -> f64 {
    value.real().hypot(value.imaginary())
}

fn mul(a: Complex64, b: Complex64) -> Complex64 {
    Complex64::try_new(
        a.real() * b.real() - a.imaginary() * b.imaginary(),
        a.real() * b.imaginary() + a.imaginary() * b.real(),
    )
    .expect("finite complex product")
}

fn div(a: Complex64, b: Complex64) -> Option<Complex64> {
    let denominator = b.real() * b.real() + b.imaginary() * b.imaginary();
    if denominator == 0.0 || !denominator.is_finite() {
        return None;
    }
    Some(
        Complex64::try_new(
            (a.real() * b.real() + a.imaginary() * b.imaginary()) / denominator,
            (a.imaginary() * b.real() - a.real() * b.imaginary()) / denominator,
        )
        .expect("finite complex quotient"),
    )
}

fn polyval(coefficients: &[f64], value: Complex64) -> Complex64 {
    let mut result = Complex64::try_new(0.0, 0.0).expect("complex zero");
    for coefficient in coefficients {
        result = mul(result, value);
        result = Complex64::try_new(result.real() + coefficient, result.imaginary())
            .expect("finite polynomial value");
    }
    result
}

/// Port of `get_sigma_noise` used by the upstream calibration path.
pub fn calculate_r480_calibration_noise_v1(
    frequency_hz: &[f64],
    calibration_sdd21: &[Complex64],
    ctle_transfer: &[Complex64],
    fb_hz: f64,
    f_r: f64,
    f_hp_hz: f64,
    sigma_bn_v: f64,
) -> Result<CalibrationNoiseResultV1, CalibrationErrorV1> {
    if frequency_hz.is_empty()
        || frequency_hz.len() != calibration_sdd21.len()
        || frequency_hz.len() != ctle_transfer.len()
        || !frequency_hz.iter().all(|v| v.is_finite())
        || !calibration_sdd21.iter().copied().all(finite_complex)
        || !ctle_transfer.iter().copied().all(finite_complex)
        || !frequency_hz.windows(2).all(|w| w[1] >= w[0])
        || !fb_hz.is_finite()
        || !f_r.is_finite()
        || !f_hp_hz.is_finite()
        || !sigma_bn_v.is_finite()
        || fb_hz <= 0.0
        || f_r <= 0.0
    {
        return Err(CalibrationErrorV1::InvalidInput);
    }
    let end = frequency_hz
        .iter()
        .position(|frequency| *frequency >= fb_hz / 2.0)
        .map(|index| index + 1)
        .ok_or(CalibrationErrorV1::FrequencyDoesNotReachHalfBaud)?;
    let h_hp = |frequency: f64| {
        if f_hp_hz == 0.0 {
            Complex64::try_new(1.0, 0.0).expect("complex one")
        } else {
            let z = Complex64::try_new(0.0, frequency / f_hp_hz).expect("finite highpass z");
            let numerator = Complex64::try_new(0.0, -z.imaginary()).expect("-j z");
            let denominator =
                Complex64::try_new(1.0 + z.real(), z.imaginary()).expect("highpass denominator");
            div(numerator, denominator).expect("highpass denominator is nonzero")
        }
    };
    let mut noise_power = 0.0;
    let mut highpass_power = 0.0;
    for index in 0..end {
        let frequency = frequency_hz[index];
        let z = Complex64::try_new(0.0, frequency / (f_r * fb_hz)).expect("finite receiver z");
        let h_r = div(
            Complex64::try_new(1.0, 0.0).expect("complex one"),
            polyval(&[1.0, 2.613126, 3.414214, 2.613126, 1.0], z),
        )
        .ok_or(CalibrationErrorV1::InvalidInput)?;
        let hp = h_hp(frequency);
        let h_np = mul(
            mul(mul(calibration_sdd21[index], ctle_transfer[index]), h_r),
            hp,
        );
        noise_power += magnitude(h_np).powi(2);
        highpass_power += magnitude(hp).powi(2);
    }
    let sigma_ne_v = sigma_bn_v * (noise_power / end as f64).sqrt();
    let sigma_hp_v = sigma_bn_v * highpass_power / end as f64;
    if !sigma_ne_v.is_finite() || !sigma_hp_v.is_finite() {
        return Err(CalibrationErrorV1::InvalidInput);
    }
    Ok(CalibrationNoiseResultV1 {
        sigma_ne_v,
        sigma_hp_v,
    })
}

/// Port of `calibrate_receiver_noise`; the minimum case COM controls every
/// sign flip and half-step, including the source's initial low-result exit.
pub fn calibrate_receiver_noise_v1<F>(
    mut evaluate_cases: F,
    pass_threshold_db: f64,
    initial_step_v: f64,
) -> Result<CalibrationResultV1, CalibrationErrorV1>
where
    F: FnMut(f64) -> Result<Vec<f64>, CalibrationErrorV1>,
{
    if !pass_threshold_db.is_finite() || !initial_step_v.is_finite() || initial_step_v == 0.0 {
        return Err(CalibrationErrorV1::InvalidInput);
    }
    let mut sigma = 0.0;
    let mut step = initial_step_v;
    let mut low_com_found = false;
    let mut history = Vec::new();
    for _ in 0..MAX_CALIBRATION_ITERATIONS_V1 {
        let case_com_db = evaluate_cases(sigma)?;
        if case_com_db.is_empty() || !case_com_db.iter().all(|value| value.is_finite()) {
            return Err(CalibrationErrorV1::Evaluator);
        }
        let minimum_com_db = case_com_db.iter().copied().fold(f64::INFINITY, f64::min);
        history.push(CalibrationIterationV1 {
            sigma_bn_v: sigma,
            step_v: step,
            case_com_db,
            minimum_com_db,
        });
        if (minimum_com_db - pass_threshold_db).abs() < 0.1
            || (sigma == 0.0 && minimum_com_db < pass_threshold_db)
        {
            return Ok(CalibrationResultV1 {
                sigma_bn_v: sigma,
                final_step_v: step,
                iterations: history,
            });
        }
        if minimum_com_db > pass_threshold_db {
            if low_com_found {
                step = if step > 0.0 { step / 2.0 } else { -step / 2.0 };
            }
        } else {
            low_com_found = true;
            step = if step > 0.0 { -step / 2.0 } else { step / 2.0 };
        }
        sigma += step;
        if !sigma.is_finite() || !step.is_finite() {
            return Err(CalibrationErrorV1::InvalidInput);
        }
    }
    Err(CalibrationErrorV1::IterationLimit)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(real: f64, imag: f64) -> Complex64 {
        Complex64::try_new(real, imag).expect("complex")
    }

    #[test]
    fn calibration_noise_matches_constant_channel() {
        let result = calculate_r480_calibration_noise_v1(
            &[0.0, 1.0, 2.0, 3.0],
            &[c(1.0, 0.0); 4],
            &[c(1.0, 0.0); 4],
            4.0,
            1.0,
            0.0,
            2.0,
        )
        .expect("noise");
        assert!(result.sigma_ne_v > 0.0);
        assert_eq!(result.sigma_hp_v, 2.0);
    }

    #[test]
    fn controller_reproduces_source_sign_flip() {
        let result = calibrate_receiver_noise_v1(|sigma| Ok(vec![3.0 - sigma]), 2.0, 2.0)
            .expect("controller");
        assert!(result.iterations.len() >= 2);
        assert!(result.sigma_bn_v > 0.0);
        assert!((result.minimum_com_db() - 2.0).abs() < 0.1);
    }

    impl CalibrationResultV1 {
        fn minimum_com_db(&self) -> f64 {
            self.iterations.last().expect("iteration").minimum_com_db
        }
    }
}
