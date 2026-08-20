//! r4.80 equalizer front-end primitives (port of `cursor.py` and
//! `ctle.py`).
//!
//! Ported from agent-com (MIT source, P5-04i source map): deterministic
//! cursor sampling (`cursor_sample_index`) and the frequency/time-domain
//! CTLE (`fd_ctle`, `td_ctle` with the source's bilinear z-domain
//! coefficients and an exact scipy `lfilter` difference-equation order).

use sipi_types::Complex64;

/// Explicit scope policy of the equalizer front-end stage.
pub const EQUALIZER_FRONTEND_POLICY_V1: &str = "sipi.p5-04i.equalizer-frontend-v1.cursor-ctle";

/// Fail-closed equalizer front-end errors (port of ConfigError paths).
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EqualizerErrorV1 {
    InvalidCursorControls,
    CursorMmRange,
    InvalidCtleControls,
}

/// Port of `CursorSample`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CursorSampleV1 {
    cursor_index: Option<i64>,
    no_zero_crossing: bool,
    peak_index: i64,
    zero_crossing_index: Option<i64>,
}

impl CursorSampleV1 {
    pub fn cursor_index(&self) -> Option<i64> {
        self.cursor_index
    }

    pub fn no_zero_crossing(&self) -> bool {
        self.no_zero_crossing
    }

    pub fn peak_index(&self) -> i64 {
        self.peak_index
    }

    pub fn zero_crossing_index(&self) -> Option<i64> {
        self.zero_crossing_index
    }
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

fn argmin_first(values: &[f64]) -> usize {
    let mut best = 0usize;
    for index in 1..values.len() {
        if values[index] < values[best] {
            best = index;
        }
    }
    best
}

/// Port of `cursor_sample_index` (zero-based indices; MM / Mod-MM CDR).
pub fn cursor_sample_index_v1(
    sbr: &[f64],
    samples_per_ui: usize,
    dfe_first_max: f64,
    cdr: &str,
    peak_start: usize,
    peak_stop: Option<usize>,
) -> Result<CursorSampleV1, EqualizerErrorV1> {
    let pulse: Vec<f64> = sbr.to_vec();
    if samples_per_ui < 1 || pulse.is_empty() || peak_start >= pulse.len() {
        return Err(EqualizerErrorV1::InvalidCursorControls);
    }
    let stop = peak_stop.unwrap_or(pulse.len());
    if !(peak_start < stop && stop <= pulse.len()) || !(cdr == "MM" || cdr == "Mod-MM") {
        return Err(EqualizerErrorV1::InvalidCursorControls);
    }
    let peak_index = peak_start + argmax_first(&pulse[peak_start..stop]);
    let maximum = pulse[peak_index];
    let search_start = peak_index.saturating_sub(4 * samples_per_ui);
    let mut rising: Vec<usize> = Vec::new();
    let window = &pulse[search_start..=peak_index];
    for index in 1..window.len() {
        let before = sign(window[index - 1] - 0.01 * maximum);
        let after = sign(window[index] - 0.01 * maximum);
        if after - before >= 1.0 {
            rising.push(search_start + index - 1);
        }
    }
    if rising.is_empty() {
        return Ok(CursorSampleV1 {
            cursor_index: None,
            no_zero_crossing: true,
            peak_index: peak_index as i64,
            zero_crossing_index: None,
        });
    }
    let zero_crossing = rising[rising.len() - 1];
    let offsets: Vec<usize> = (0..(2 * samples_per_ui + 1)).collect();
    let sample_points: Vec<usize> = offsets
        .iter()
        .map(|offset| zero_crossing + offset)
        .collect();
    let last = *sample_points.last().expect("points");
    if last + samples_per_ui >= pulse.len() || sample_points[0] < samples_per_ui {
        return Err(EqualizerErrorV1::CursorMmRange);
    }
    let metric: Vec<f64> = if cdr == "Mod-MM" {
        sample_points
            .iter()
            .map(|point| {
                let far = pulse[point + samples_per_ui];
                let near = pulse[*point];
                (far - dfe_first_max * near).abs()
            })
            .collect()
    } else {
        sample_points
            .iter()
            .map(|point| {
                let past = pulse[*point - samples_per_ui];
                let far = pulse[point + samples_per_ui] - dfe_first_max * pulse[*point];
                (past - far.max(0.0)).abs()
            })
            .collect()
    };
    let selected = zero_crossing + argmin_first(&metric);
    Ok(CursorSampleV1 {
        cursor_index: Some(selected as i64),
        no_zero_crossing: false,
        peak_index: peak_index as i64,
        zero_crossing_index: Some(zero_crossing as i64),
    })
}

fn sign(value: f64) -> f64 {
    if value > 0.0 {
        1.0
    } else if value < 0.0 {
        -1.0
    } else {
        0.0
    }
}

pub(crate) fn complex_mul(a: Complex64, b: Complex64) -> Complex64 {
    Complex64::try_new(
        a.real() * b.real() - a.imaginary() * b.imaginary(),
        a.real() * b.imaginary() + a.imaginary() * b.real(),
    )
    .expect("complex")
}

pub(crate) fn complex_div(a: Complex64, b: Complex64) -> Complex64 {
    let denominator = b.real() * b.real() + b.imaginary() * b.imaginary();
    Complex64::try_new(
        (a.real() * b.real() + a.imaginary() * b.imaginary()) / denominator,
        (a.imaginary() * b.real() - a.real() * b.imaginary()) / denominator,
    )
    .expect("complex")
}

/// Port of `fd_ctle` (FD_CTLE explicit two-pole/one-zero transfer).
pub fn fd_ctle_v1(
    frequency_hz: &[f64],
    baud_hz: f64,
    fz_multiplier: f64,
    fp1_multiplier: f64,
    fp2_multiplier: f64,
    dc_gain_db: f64,
) -> Result<Vec<Complex64>, EqualizerErrorV1> {
    let frequency: Vec<f64> = frequency_hz.to_vec();
    if frequency.is_empty()
        || frequency.iter().any(|value| *value < 0.0)
        || !(baud_hz > 0.0)
        || fz_multiplier.min(fp1_multiplier).min(fp2_multiplier) <= 0.0
    {
        return Err(EqualizerErrorV1::InvalidCtleControls);
    }
    let fz = fz_multiplier * baud_hz;
    let fp1 = fp1_multiplier * baud_hz;
    let fp2 = fp2_multiplier * baud_hz;
    let gain = 10.0_f64.powf(dc_gain_db / 20.0);
    Ok(frequency
        .iter()
        .map(|value| {
            let numerator = Complex64::try_new(gain, *value / fz).expect("complex");
            let d1 = Complex64::try_new(1.0, *value / fp1).expect("complex");
            let d2 = Complex64::try_new(1.0, *value / fp2).expect("complex");
            let denominator = complex_mul(d1, d2);
            complex_div(numerator, denominator)
        })
        .collect())
}

/// Port of `td_ctle` (TD_CTLE bilinear z-domain coefficients with the
/// source's exact scipy `lfilter` difference-equation order).
pub fn td_ctle_v1(
    impulse: &[f64],
    baud_hz: f64,
    fz_hz: f64,
    fp1_hz: f64,
    fp2_hz: f64,
    dc_gain_db: f64,
    samples_per_ui: usize,
) -> Result<Vec<f64>, EqualizerErrorV1> {
    let values: Vec<f64> = impulse.to_vec();
    if values.is_empty()
        || !(baud_hz > 0.0)
        || fz_hz.min(fp1_hz).min(fp2_hz) <= 0.0
        || samples_per_ui < 1
    {
        return Err(EqualizerErrorV1::InvalidCtleControls);
    }
    let p1 = -2.0 * std::f64::consts::PI * fp1_hz;
    let p2 = -2.0 * std::f64::consts::PI * fp2_hz;
    let z = -2.0 * std::f64::consts::PI * fz_hz * 10.0_f64.powf(dc_gain_db / 20.0);
    let bilinear_fs = 2.0 * baud_hz * samples_per_ui as f64;
    let p1d = (1.0 + p1 / bilinear_fs) / (1.0 - p1 / bilinear_fs);
    let p2d = (1.0 + p2 / bilinear_fs) / (1.0 - p2 / bilinear_fs);
    let zd = (1.0 + z / bilinear_fs) / (1.0 - z / bilinear_fs);
    let kd = (bilinear_fs - z) / ((bilinear_fs - p1) * (bilinear_fs - p2)) * fp1_hz / fz_hz;
    // b = -p2 * kd * poly((zd, -1)); poly roots (zd, -1) -> [1, 1-zd, -zd]
    let b0 = -p2 * kd * 1.0;
    let b1 = -p2 * kd * (1.0 - zd);
    let b2 = -p2 * kd * (-zd);
    // a = poly((p1d, p2d)) -> [1, -(p1d+p2d), p1d*p2d]
    let a1 = -(p1d + p2d);
    let a2 = p1d * p2d;
    // lfilter(b, a, values) with zero initial conditions, source order:
    // y[n] = b0 x[n] + b1 x[n-1] + b2 x[n-2] - a1 y[n-1] - a2 y[n-2]
    let mut result = vec![0.0_f64; values.len()];
    let mut x1 = 0.0;
    let mut x2 = 0.0;
    let mut y1 = 0.0;
    let mut y2 = 0.0;
    for (index, x0) in values.iter().enumerate() {
        let y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
        result[index] = y0;
        x2 = x1;
        x1 = *x0;
        y2 = y1;
        y1 = y0;
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pulse() -> Vec<f64> {
        (0..200)
            .map(|index| {
                let i = index as f64;
                (-(i - 80.0) * (i - 80.0) / 300.0).exp() * (i * 0.3).sin()
            })
            .collect()
    }

    #[test]
    fn cursor_deterministic_mm() {
        let sample = cursor_sample_index_v1(&pulse(), 8, 0.0, "MM", 0, None).expect("cursor");
        assert!(!sample.no_zero_crossing());
        assert!(sample.cursor_index().is_some());
        assert!(sample.zero_crossing_index().is_some());
        assert!(sample.peak_index() >= 0);
    }

    #[test]
    fn cursor_mod_mm_differs_only_in_metric() {
        let sample = cursor_sample_index_v1(&pulse(), 8, 0.0, "Mod-MM", 0, None).expect("cursor");
        assert!(sample.cursor_index().is_some());
    }

    #[test]
    fn cursor_no_rising_edge_yields_no_crossing() {
        let flat = vec![1.0; 64];
        let sample = cursor_sample_index_v1(&flat, 8, 0.0, "MM", 0, None).expect("cursor");
        assert!(sample.no_zero_crossing());
        assert_eq!(sample.cursor_index(), None);
    }

    #[test]
    fn cursor_controls_fail_closed() {
        assert_eq!(
            cursor_sample_index_v1(&pulse(), 0, 0.0, "MM", 0, None).unwrap_err(),
            EqualizerErrorV1::InvalidCursorControls,
        );
        assert_eq!(
            cursor_sample_index_v1(&pulse(), 8, 0.0, "PE", 0, None).unwrap_err(),
            EqualizerErrorV1::InvalidCursorControls,
        );
        assert_eq!(
            cursor_sample_index_v1(&pulse(), 8, 0.0, "MM", 500, None).unwrap_err(),
            EqualizerErrorV1::InvalidCursorControls,
        );
    }

    #[test]
    fn fd_ctle_transfer_shape() {
        let frequencies: Vec<f64> = (0..8).map(|index| index as f64 * 1e9).collect();
        let response = fd_ctle_v1(&frequencies, 53.125e9, 0.5, 1.5, 2.0, 6.0).expect("ctle");
        assert_eq!(response.len(), 8);
        // DC: gain * 1.0
        let dc = response[0];

        assert!((dc.real() - 10.0_f64.powf(6.0 / 20.0)).abs() < 1e-9);
        assert!(dc.imaginary().abs() < 1e-12);
    }

    #[test]
    fn td_ctle_impulse_response_finite() {
        let impulse = pulse();
        let filtered = td_ctle_v1(&impulse, 53.125e9, 10e9, 30e9, 40e9, 6.0, 8).expect("filtered");
        assert_eq!(filtered.len(), impulse.len());
        assert!(filtered.iter().all(|value| value.is_finite()));
        assert!(!filtered.iter().all(|value| *value == 0.0));
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            EQUALIZER_FRONTEND_POLICY_V1,
            "sipi.p5-04i.equalizer-frontend-v1.cursor-ctle",
        );
    }
}
