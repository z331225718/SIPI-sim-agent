//! Combined R480 noise PDF composition (port of `combine_r480_noise_pdf`).
//!
//! Ported from agent-com `src/agent_com/noise/discrete_pdf.py` (MIT
//! source, P5-04e source map). Orders the Create_Noise_PDF combination
//! through Eq. 93A-45 using the ported convolution and quantile core.

use crate::discrete_pdf_v1::{DiscretePdfV1, PdfErrorV1, convolve_v1};

/// The combined noise PDF result surface.
#[derive(Clone, Debug, PartialEq)]
pub struct CombinedNoisePdfV1 {
    combined: DiscretePdfV1,
    cdf: Vec<f64>,
    cci: DiscretePdfV1,
    isi_and_crosstalk: DiscretePdfV1,
    gaussian_and_jitter: DiscretePdfV1,
    peak_interference_v: f64,
}

impl CombinedNoisePdfV1 {
    pub fn combined(&self) -> &DiscretePdfV1 {
        &self.combined
    }

    pub fn cdf(&self) -> &[f64] {
        &self.cdf
    }

    pub fn peak_interference_v(&self) -> f64 {
        self.peak_interference_v
    }
}

/// Port the ordered Create_Noise_PDF combination through Eq. 93A-45.
pub fn combine_r480_noise_pdf_v1(
    sci_pdf: &DiscretePdfV1,
    fext_pdfs: &[DiscretePdfV1],
    next_pdfs: &[DiscretePdfV1],
    gaussian_pdf: &DiscretePdfV1,
    dual_dirac_pdf: &DiscretePdfV1,
    spec_ber: f64,
) -> Result<CombinedNoisePdfV1, PdfErrorV1> {
    if !(0.0 < spec_ber && spec_ber <= 1.0) {
        return Err(PdfErrorV1::InvalidQuantile);
    }
    let bin_size = sci_pdf.bin_size();
    for pdf in fext_pdfs
        .iter()
        .chain(next_pdfs.iter())
        .chain([gaussian_pdf, dual_dirac_pdf])
    {
        if pdf.bin_size() != bin_size {
            return Err(PdfErrorV1::ConvolveBinMismatch);
        }
    }
    let mut fext = DiscretePdfV1::try_new(bin_size, 0, vec![1.0])?;
    for pdf in fext_pdfs {
        fext = convolve_v1(&fext, pdf)?;
    }
    let mut next_pdf = DiscretePdfV1::try_new(bin_size, 0, vec![1.0])?;
    for pdf in next_pdfs {
        next_pdf = convolve_v1(&next_pdf, pdf)?;
    }
    let cci = convolve_v1(&fext, &next_pdf)?;
    let isi_and_crosstalk = convolve_v1(sci_pdf, &cci)?;
    let gaussian_and_jitter = convolve_v1(gaussian_pdf, dual_dirac_pdf)?;
    let combined = convolve_v1(&isi_and_crosstalk, &gaussian_and_jitter)?;
    let cdf = combined.cdf();
    let peak_interference_v = isi_and_crosstalk.first_quantile(spec_ber)?.abs();
    Ok(CombinedNoisePdfV1 {
        combined,
        cdf,
        cci,
        isi_and_crosstalk,
        gaussian_and_jitter,
        peak_interference_v,
    })
}

/// Explicit scope policy of the combined noise PDF stage.
pub const COMBINED_NOISE_PDF_POLICY_V1: &str = "sipi.p5-04e.combined-noise-pdf-v1.eq-93a-45-order";

#[cfg(test)]
mod tests {
    use super::*;
    use crate::discrete_pdf_v1::normal_pdf_v1;

    #[test]
    fn all_delta_inputs_yield_delta_output() {
        let delta = DiscretePdfV1::try_new(1e-4, 0, vec![1.0]).expect("delta");
        let result =
            combine_r480_noise_pdf_v1(&delta, &[], &[], &delta, &delta, 1e-4).expect("combined");
        assert_eq!(result.combined().probability().len(), 1);
        assert!((result.combined().probability()[0] - 1.0).abs() < 1e-12);
        assert!((result.peak_interference_v() - 0.0).abs() < 1e-12);
    }

    #[test]
    fn gaussian_input_produces_combined_pdf() {
        let gaussian = normal_pdf_v1(0.01, 3.0, 1e-4).expect("gaussian");
        let result = combine_r480_noise_pdf_v1(&gaussian, &[], &[], &gaussian, &gaussian, 1e-4)
            .expect("combined");
        assert!(result.combined().probability().len() > gaussian.probability().len());
        let cdf = result.cdf();
        assert!((cdf[cdf.len() - 1] - 1.0).abs() < 1e-9);
    }

    #[test]
    fn rejects_bin_size_mismatch() {
        let a = DiscretePdfV1::try_new(1e-4, 0, vec![1.0]).expect("a");
        let b = DiscretePdfV1::try_new(1e-3, 0, vec![1.0]).expect("b");
        assert_eq!(
            combine_r480_noise_pdf_v1(&a, std::slice::from_ref(&b), &[], &a, &a, 1e-4),
            Err(PdfErrorV1::ConvolveBinMismatch)
        );
    }

    #[test]
    fn rejects_invalid_spec_ber() {
        let delta = DiscretePdfV1::try_new(1e-4, 0, vec![1.0]).expect("delta");
        assert_eq!(
            combine_r480_noise_pdf_v1(&delta, &[], &[], &delta, &delta, 0.0),
            Err(PdfErrorV1::InvalidQuantile)
        );
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            COMBINED_NOISE_PDF_POLICY_V1,
            "sipi.p5-04e.combined-noise-pdf-v1.eq-93a-45-order",
        );
    }
}
