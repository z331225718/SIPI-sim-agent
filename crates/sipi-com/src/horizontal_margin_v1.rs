//! Bathtub horizontal time-margin core (P3C-02g).
//!
//! Computes the receiver horizontal timing margins from a bathtub eye
//! opening width (from P3C-02f) and the nominal sampling-point offset
//! within that opening. Interprets the eye center as mid-width and
//! computes the left and right margins (distance from the sampling point
//! to each bathtub edge). A non-positive margin is flagged, consistent
//! with a receiver that cannot sample reliably at the target BER.

use crate::bathtub_v1::{BathtubErrorV1, BathtubSampleV1, bathtub_opening_width_v1};

/// Composes the bathtub opening at a target BER (P3C-02f) with a
/// sampling-point offset to yield horizontal margins end to end.
pub fn margins_from_bathtub_v1(
    samples: &[BathtubSampleV1],
    target_ber: f64,
    sample_offset_from_left_edge_ui: f64,
) -> Result<HorizontalMarginsV1, HorizontalMarginErrorV1> {
    let width = bathtub_opening_width_v1(samples, target_ber).map_err(|e| match e {
        BathtubErrorV1::NoOpening => HorizontalMarginErrorV1::NonPositiveEyeWidth,
        _ => HorizontalMarginErrorV1::NonFinite,
    })?;
    compute_horizontal_margins_v1(width, sample_offset_from_left_edge_ui)
}
/// Stable scope policy of the P3C-02g horizontal margin core.
pub const HORIZONTAL_MARGIN_POLICY_V1: &str = "sipi.p3c-02g.horizontal-margin.v1.timing";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum HorizontalMarginErrorV1 {
    NonPositiveEyeWidth,
    SampleOutsideEye,
    NonFinite,
}

/// One signal-integrity horizontal timing state at the target BER.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct HorizontalMarginsV1 {
    eye_width_ui: f64,
    left_margin_ui: f64,
    right_margin_ui: f64,
}

impl HorizontalMarginsV1 {
    pub const fn eye_width_ui(self) -> f64 {
        self.eye_width_ui
    }

    pub const fn left_margin_ui(self) -> f64 {
        self.left_margin_ui
    }

    pub const fn right_margin_ui(self) -> f64 {
        self.right_margin_ui
    }

    /// The smaller of the two margins (the RX timing constraint).
    pub fn min_margin_ui(self) -> f64 {
        self.left_margin_ui.min(self.right_margin_ui)
    }
}

/// Computes the horizontal margins from an eye opening width (UI) and the
/// sampling-point offset (UI) relative to the eye opening's left edge.
///
/// `eye_width_ui` is the bathtub opening width at the target BER (P3C-02f).
/// `sample_offset_from_left_edge_ui` is where the receiver samples,
/// measured from the left bathtub edge. Returns the margins to the left
/// and right edges; a sampling point at or outside an edge is an error.
pub fn compute_horizontal_margins_v1(
    eye_width_ui: f64,
    sample_offset_from_left_edge_ui: f64,
) -> Result<HorizontalMarginsV1, HorizontalMarginErrorV1> {
    if !eye_width_ui.is_finite() || !sample_offset_from_left_edge_ui.is_finite() {
        return Err(HorizontalMarginErrorV1::NonFinite);
    }
    if eye_width_ui <= 0.0 {
        return Err(HorizontalMarginErrorV1::NonPositiveEyeWidth);
    }
    if sample_offset_from_left_edge_ui < 0.0 || sample_offset_from_left_edge_ui > eye_width_ui {
        return Err(HorizontalMarginErrorV1::SampleOutsideEye);
    }
    let left_margin = sample_offset_from_left_edge_ui;
    let right_margin = eye_width_ui - sample_offset_from_left_edge_ui;
    Ok(HorizontalMarginsV1 {
        eye_width_ui,
        left_margin_ui: left_margin,
        right_margin_ui: right_margin,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            HORIZONTAL_MARGIN_POLICY_V1,
            "sipi.p3c-02g.horizontal-margin.v1.timing"
        );
    }

    #[test]
    fn centered_sampling_balanced_margins() {
        let m = compute_horizontal_margins_v1(0.8, 0.4).expect("m");
        assert!((m.left_margin_ui() - 0.4).abs() < 1e-12);
        assert!((m.right_margin_ui() - 0.4).abs() < 1e-12);
        assert!((m.min_margin_ui() - 0.4).abs() < 1e-12);
    }

    #[test]
    fn off_center_gives_asymmetric_margins() {
        let m = compute_horizontal_margins_v1(1.0, 0.25).expect("m");
        assert!((m.left_margin_ui() - 0.25).abs() < 1e-12);
        assert!((m.right_margin_ui() - 0.75).abs() < 1e-12);
        assert!((m.min_margin_ui() - 0.25).abs() < 1e-12);
    }

    #[test]
    fn rejects_nonpositive_eye() {
        assert_eq!(
            compute_horizontal_margins_v1(0.0, 0.0).err(),
            Some(HorizontalMarginErrorV1::NonPositiveEyeWidth)
        );
    }

    #[test]
    fn rejects_sample_outside_eye() {
        assert_eq!(
            compute_horizontal_margins_v1(0.8, 0.9).err(),
            Some(HorizontalMarginErrorV1::SampleOutsideEye)
        );
        assert_eq!(
            compute_horizontal_margins_v1(0.8, -0.1).err(),
            Some(HorizontalMarginErrorV1::SampleOutsideEye)
        );
    }

    #[test]
    fn rejects_nonfinite() {
        assert_eq!(
            compute_horizontal_margins_v1(f64::NAN, 0.0).err(),
            Some(HorizontalMarginErrorV1::NonFinite)
        );
    }
}
