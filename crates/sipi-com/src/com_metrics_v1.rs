//! Final COM/VEC/VEO scalar metrics from the combined discrete PDF.
//!
//! Ported from agent-com `src/agent_com/metrics/com.py` (MIT source,
//! P5-04c source map). The PDF arrays (support points and CDF) are
//! caller-supplied; discrete-PDF construction is a separate stage.

/// The COM scalar metrics envelope (matches the P5-03a output metric
/// subset COM_dB / VEC_dB / VEO_mV).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ComMetricsV1 {
    available_signal_v: f64,
    interference_noise_v: f64,
    threshold_der: f64,
    com_db: f64,
    vec_db: f64,
    veo_mv: f64,
    eye_opening_v: Option<f64>,
}

impl ComMetricsV1 {
    pub fn available_signal_v(self) -> f64 {
        self.available_signal_v
    }

    pub fn com_db(self) -> f64 {
        self.com_db
    }

    pub fn vec_db(self) -> f64 {
        self.vec_db
    }

    pub fn veo_mv(self) -> f64 {
        self.veo_mv
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ComMetricsErrorV1 {
    InvalidControls,
    BerRange,
    ThresholdRange,
    PdfMismatch,
    C2mEyeRequired,
}

fn db_ratio(numerator: f64, denominator: f64) -> f64 {
    if denominator == 0.0 {
        return f64::INFINITY;
    }
    if denominator < 0.0 {
        return f64::NAN;
    }
    20.0 * (numerator / denominator).log10()
}

/// Port the main r4.80 COM/VEC/VEO scalar calculations.
pub fn calculate_com_metrics_v1(
    available_signal_v: f64,
    pdf_x: &[f64],
    pdf_cdf: &[f64],
    spec_ber: f64,
    pass_threshold_db: f64,
    t_o_s: f64,
    eye_opening_v: Option<f64>,
) -> Result<ComMetricsV1, ComMetricsErrorV1> {
    if available_signal_v <= 0.0
        || !(0.0 < spec_ber && spec_ber < 1.0)
        || !pass_threshold_db.is_finite()
    {
        return Err(ComMetricsErrorV1::InvalidControls);
    }
    if pdf_x.len() != pdf_cdf.len() || pdf_x.is_empty() {
        return Err(ComMetricsErrorV1::PdfMismatch);
    }
    let interference_index = pdf_cdf
        .iter()
        .position(|value| *value > spec_ber)
        .ok_or(ComMetricsErrorV1::BerRange)?;
    let interference = pdf_x[interference_index].abs();
    let threshold = -available_signal_v / 10.0_f64.powf(pass_threshold_db / 20.0);
    let threshold_index = pdf_x
        .iter()
        .position(|value| *value > threshold)
        .ok_or(ComMetricsErrorV1::ThresholdRange)?;
    let threshold_der = pdf_cdf[threshold_index];
    if t_o_s != 0.0 {
        let eye = eye_opening_v.ok_or(ComMetricsErrorV1::C2mEyeRequired)?;
        let interference_c2m = 2.0 * available_signal_v - eye;
        let ratio = if eye == 0.0 {
            f64::NEG_INFINITY
        } else {
            2.0 * available_signal_v / eye
        };
        let vec_argument = ratio.max(f64::EPSILON);
        let com = db_ratio(2.0 * available_signal_v, interference_c2m);
        let vec = 20.0 * vec_argument.log10();
        let veo = 1000.0 * eye;
        return Ok(ComMetricsV1 {
            available_signal_v,
            interference_noise_v: interference_c2m,
            threshold_der,
            com_db: com,
            vec_db: vec,
            veo_mv: veo,
            eye_opening_v: Some(eye),
        });
    }
    let vec_argument = ((available_signal_v - interference) / available_signal_v).max(f64::EPSILON);
    let com = db_ratio(available_signal_v, interference);
    let vec = -20.0 * vec_argument.log10();
    let veo = 2000.0 * (available_signal_v - interference);
    Ok(ComMetricsV1 {
        available_signal_v,
        interference_noise_v: interference,
        threshold_der,
        com_db: com,
        vec_db: vec,
        veo_mv: veo,
        eye_opening_v: None,
    })
}

/// Explicit scope policy of the metrics stage.
pub const COM_METRICS_POLICY_V1: &str = "sipi.p5-04c.com-metrics-v1.scalar-cdf-metrics";

#[cfg(test)]
mod tests {
    use super::*;

    fn pdf() -> (Vec<f64>, Vec<f64>) {
        // Symmetric support with a monotone CDF.
        let x = vec![-1.0, -0.5, 0.0, 0.5, 1.0];
        let cdf = vec![0.05, 0.2, 0.5, 0.8, 0.95];
        (x, cdf)
    }

    #[test]
    fn computes_scalar_metrics() {
        let (x, cdf) = pdf();
        let metrics =
            calculate_com_metrics_v1(1.0, &x, &cdf, 1e-4, 3.0, 0.0, None).expect("metrics");
        // spec_ber=1e-4 < 0.05 -> first cdf > spec_ber is index 0, interference = 1.0
        assert!((metrics.available_signal_v() - 1.0).abs() < 1e-12);
        assert!((metrics.com_db() - 0.0).abs() < 1e-9);
        assert!((metrics.veo_mv() - 0.0).abs() < 1e-9);
    }

    #[test]
    fn rejects_invalid_controls() {
        let (x, cdf) = pdf();
        assert_eq!(
            calculate_com_metrics_v1(0.0, &x, &cdf, 1e-4, 3.0, 0.0, None),
            Err(ComMetricsErrorV1::InvalidControls)
        );
        assert_eq!(
            calculate_com_metrics_v1(1.0, &x, &cdf, 1.5, 3.0, 0.0, None),
            Err(ComMetricsErrorV1::InvalidControls)
        );
    }

    #[test]
    fn c2m_branch_requires_eye() {
        let (x, cdf) = pdf();
        assert_eq!(
            calculate_com_metrics_v1(1.0, &x, &cdf, 1e-4, 3.0, 1e-9, None),
            Err(ComMetricsErrorV1::C2mEyeRequired)
        );
    }

    #[test]
    fn c2m_branch_uses_eye_opening() {
        let (x, cdf) = pdf();
        let metrics =
            calculate_com_metrics_v1(1.0, &x, &cdf, 1e-4, 3.0, 1e-9, Some(0.5)).expect("metrics");
        assert!((metrics.veo_mv() - 500.0).abs() < 1e-9);
        // VEC = 20*log10(2A/eye) = 20*log10(4)
        assert!((metrics.vec_db() - 20.0 * 4.0_f64.log10()).abs() < 1e-9);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            COM_METRICS_POLICY_V1,
            "sipi.p5-04c.com-metrics-v1.scalar-cdf-metrics",
        );
    }
}
