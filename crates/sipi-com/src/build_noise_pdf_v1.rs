//! r4.80 Gaussian and dual-Dirac noise PDF build (port of
//! `build_r480_noise_pdf`, the non-MMSE Create_Noise_PDF path).
//!
//! Ported from agent-com `src/agent_com/noise/discrete_pdf.py` (MIT
//! source, P5-04h source map). Combines the ported normal_pdf /
//! sampled_signal_pdf / combine_r480_noise_pdf stages with the r4.80
//! Q-factor `sqrt(2) * erfcinv(2 * spec_ber)`.

use crate::combined_noise_pdf_v1::{CombinedNoisePdfV1, combine_r480_noise_pdf_v1};
use crate::discrete_pdf_v1::{DiscretePdfV1, PdfErrorV1, normal_pdf_v1};
use crate::erf_v1::erfcinv_v1;
use crate::sampled_signal_pdf_v1::sampled_signal_pdf_v1;

/// Explicit scope policy of the noise-PDF build stage.
pub const BUILD_NOISE_PDF_POLICY_V1: &str = "sipi.p5-04h.build-noise-pdf-v1.gaussian-dual-dirac";

/// The r4.80 noise PDF result surface (port of `R480NoisePdf`).
#[derive(Clone, Debug, PartialEq)]
pub struct R480NoisePdfV1 {
    result: CombinedNoisePdfV1,
    sigma_tx_v: f64,
    sigma_rj_v: f64,
    sigma_gaussian_v: f64,
    ber_q: f64,
    gaussian_pdf: DiscretePdfV1,
    jitter_pdf: DiscretePdfV1,
}

impl R480NoisePdfV1 {
    pub fn result(&self) -> &CombinedNoisePdfV1 {
        &self.result
    }

    pub fn sigma_tx_v(&self) -> f64 {
        self.sigma_tx_v
    }

    pub fn sigma_rj_v(&self) -> f64 {
        self.sigma_rj_v
    }

    pub fn sigma_gaussian_v(&self) -> f64 {
        self.sigma_gaussian_v
    }

    pub fn ber_q(&self) -> f64 {
        self.ber_q
    }

    pub fn gaussian_pdf(&self) -> &DiscretePdfV1 {
        &self.gaussian_pdf
    }

    pub fn jitter_pdf(&self) -> &DiscretePdfV1 {
        &self.jitter_pdf
    }
}

/// Port of `build_r480_noise_pdf` (non-MMSE Create_Noise_PDF path).
#[allow(clippy::too_many_arguments)]
pub fn build_r480_noise_pdf_v1(
    sci_pdf: &DiscretePdfV1,
    fext_pdfs: &[DiscretePdfV1],
    next_pdfs: &[DiscretePdfV1],
    levels: u32,
    available_signal_v: f64,
    r_lm_ohm: f64,
    tx_snr_db: f64,
    sigma_x: f64,
    sigma_rj_s: f64,
    jitter_response: &[f64],
    sigma_n_v: f64,
    amplitude_dd_v: f64,
    spec_ber: f64,
    noise_crest_factor: f64,
    sigma_ne_v: f64,
    bbn_q_factor: Option<f64>,
    sigma_tx_override_v: Option<f64>,
    sigma_rj_override_v: Option<f64>,
) -> Result<R480NoisePdfV1, PdfErrorV1> {
    if levels < 2
        || !(available_signal_v > 0.0)
        || !(r_lm_ohm > 0.0)
        || tx_snr_db < 0.0
        || sigma_x < 0.0
        || sigma_rj_s < 0.0
        || sigma_n_v < 0.0
        || amplitude_dd_v < 0.0
        || sigma_ne_v < 0.0
        || sigma_tx_override_v.is_some_and(|value| value < 0.0)
        || sigma_rj_override_v.is_some_and(|value| value < 0.0)
    {
        return Err(PdfErrorV1::InvalidNoisePdfControls);
    }
    let h_j: Vec<f64> = jitter_response.to_vec();
    if h_j.is_empty() {
        return Err(PdfErrorV1::InvalidNoisePdfControls);
    }
    let sigma_tx = match sigma_tx_override_v {
        Some(value) => value,
        None => {
            (levels - 1) as f64 * available_signal_v / r_lm_ohm * 10.0_f64.powf(-tx_snr_db / 20.0)
        }
    };
    let norm_h_j = h_j.iter().map(|value| value * value).sum::<f64>().sqrt();
    let sigma_rj = match sigma_rj_override_v {
        Some(value) => value,
        None => sigma_rj_s * sigma_x * norm_h_j,
    };
    let sigma_gaussian = (sigma_rj * sigma_rj + sigma_n_v * sigma_n_v + sigma_tx * sigma_tx).sqrt();
    let ber_q = if noise_crest_factor != 0.0 {
        noise_crest_factor
    } else {
        std::f64::consts::SQRT_2 * erfcinv_v1(2.0 * spec_ber)
    };
    let ne_q = match bbn_q_factor {
        Some(value) => value,
        None => ber_q,
    };
    let bin_size = sci_pdf.bin_size();
    let gaussian_first = normal_pdf_v1(sigma_gaussian, ber_q, bin_size)?;
    let gaussian_second = normal_pdf_v1(sigma_ne_v, ne_q, bin_size)?;
    let gaussian = crate::discrete_pdf_v1::convolve_v1(&gaussian_first, &gaussian_second)?;
    let dual_dirac_values: Vec<f64> = h_j.iter().map(|value| amplitude_dd_v * value).collect();
    let dual_dirac = sampled_signal_pdf_v1(&dual_dirac_values, levels, bin_size, false)?;
    let result = combine_r480_noise_pdf_v1(
        sci_pdf,
        fext_pdfs,
        next_pdfs,
        &gaussian,
        &dual_dirac,
        spec_ber,
    )?;
    Ok(R480NoisePdfV1 {
        result,
        sigma_tx_v: sigma_tx,
        sigma_rj_v: sigma_rj,
        sigma_gaussian_v: sigma_gaussian,
        ber_q,
        gaussian_pdf: gaussian,
        jitter_pdf: dual_dirac,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::discrete_pdf_v1::normal_pdf_v1;

    fn base_pdf() -> DiscretePdfV1 {
        normal_pdf_v1(0.001, 3.0, 1e-4).expect("pdf")
    }

    #[test]
    fn builds_noise_pdf_surface() {
        let sci = base_pdf();
        let fext = normal_pdf_v1(0.002, 3.0, 1e-4).expect("pdf");
        let next = normal_pdf_v1(0.0015, 3.0, 1e-4).expect("pdf");
        let h_j = vec![0.3, 0.5, 0.2];
        let built = build_r480_noise_pdf_v1(
            &sci,
            &[fext],
            &[next],
            4,
            0.6,
            50.0,
            30.0,
            0.03,
            1e-4,
            &h_j,
            0.01,
            0.4,
            1e-4,
            0.0,
            0.0,
            None,
            None,
            None,
        )
        .expect("built");
        assert!(built.sigma_tx_v() > 0.0);
        assert!(built.sigma_rj_v() > 0.0);
        assert!(built.sigma_gaussian_v() > 0.0);
        assert!(built.ber_q() > 3.0 && built.ber_q() < 4.0);
        let total: f64 = built.result().combined().probability().iter().sum();
        assert!((total - 1.0).abs() < 1e-10);
    }

    #[test]
    fn controls_fail_closed() {
        let sci = base_pdf();
        let h_j = vec![0.5];
        for (levels, available) in [(1u32, 0.6), (4, 0.0)] {
            let result = build_r480_noise_pdf_v1(
                &sci,
                &[],
                &[],
                levels,
                available,
                50.0,
                30.0,
                0.03,
                1e-4,
                &h_j,
                0.01,
                0.4,
                1e-4,
                0.0,
                0.0,
                None,
                None,
                None,
            );
            assert_eq!(result.unwrap_err(), PdfErrorV1::InvalidNoisePdfControls);
        }
        assert_eq!(
            build_r480_noise_pdf_v1(
                &sci,
                &[],
                &[],
                4,
                0.6,
                50.0,
                30.0,
                0.03,
                1e-4,
                &[],
                0.01,
                0.4,
                1e-4,
                0.0,
                0.0,
                None,
                None,
                None,
            )
            .unwrap_err(),
            PdfErrorV1::InvalidNoisePdfControls,
        );
    }

    #[test]
    fn noise_crest_factor_and_overrides() {
        let sci = base_pdf();
        let h_j = vec![0.3, 0.5, 0.2];
        let built = build_r480_noise_pdf_v1(
            &sci,
            &[],
            &[],
            4,
            0.6,
            50.0,
            30.0,
            0.03,
            1e-4,
            &h_j,
            0.01,
            0.4,
            1e-4,
            3.8,
            0.0,
            Some(2.5),
            Some(0.002),
            Some(0.001),
        )
        .expect("built");
        assert!((built.ber_q() - 3.8).abs() < 1e-15);
        assert!((built.sigma_tx_v() - 0.002).abs() < 1e-15);
        assert!((built.sigma_rj_v() - 0.001).abs() < 1e-15);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            BUILD_NOISE_PDF_POLICY_V1,
            "sipi.p5-04h.build-noise-pdf-v1.gaussian-dual-dirac",
        );
    }
}
