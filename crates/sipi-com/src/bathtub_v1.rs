//! Bathtub opening-width estimator (P3C-02f).
//!
//! Given a V-shaped BER-vs-time bathtub (sorted time offsets with a
//! per-offset BER estimate), compute the horizontal opening width at a
//! target BER: the contiguous time span where BER <= target, measured as
//! right-crossing minus left-crossing offset. Uses the owner-decided
//! Q-factor method (P3C-02e) for the BER value domain; this slice only
//! locates the target-BER crossings. Eye folding/bins are owned by
//! P3C-02c; bathtub curve fitting and statistical contours remain out
//! of scope.

/// Stable scope policy of the P3C-02f bathtub opening core.
pub const BATHTUB_POLICY_V1: &str = "sipi.p3c-02f.bathtub-opening.v1.threshold";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum BathtubErrorV1 {
    TooFewSamples,
    TimeNotAscending,
    InvalidBer,
    TargetBerOutOfRange,
    NoOpening,
}

/// One BER estimate at a given time offset (UI).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct BathtubSampleV1 {
    time_offset_ui: f64,
    ber: f64,
}

impl BathtubSampleV1 {
    pub const fn new(time_offset_ui: f64, ber: f64) -> Self {
        Self {
            time_offset_ui,
            ber,
        }
    }

    pub const fn time_offset_ui(self) -> f64 {
        self.time_offset_ui
    }

    pub const fn ber(self) -> f64 {
        self.ber
    }
}

/// Computes the horizontal bathtub opening width (UI) at a target BER.
///
/// The samples must be strictly ascending in time offset and form a
/// V-shaped bathtub (low BER near center, high on the wings). The opening
/// is the contiguous span where BER <= target; its width is the right
/// crossing minus the left crossing (linear interpolation in log-BER
/// between adjacent samples). Returns an error if no such span exists.
pub fn bathtub_opening_width_v1(
    samples: &[BathtubSampleV1],
    target_ber: f64,
) -> Result<f64, BathtubErrorV1> {
    if samples.len() < 3 {
        return Err(BathtubErrorV1::TooFewSamples);
    }
    if !(0.0 < target_ber && target_ber < 1.0) {
        return Err(BathtubErrorV1::TargetBerOutOfRange);
    }
    for pair in samples.windows(2) {
        if pair[0].time_offset_ui() >= pair[1].time_offset_ui() {
            return Err(BathtubErrorV1::TimeNotAscending);
        }
        if !pair[0].ber().is_finite() || pair[0].ber() <= 0.0 || pair[0].ber() >= 1.0 {
            return Err(BathtubErrorV1::InvalidBer);
        }
    }
    let last_ber = samples[samples.len() - 1].ber();
    if !last_ber.is_finite() || last_ber <= 0.0 || last_ber >= 1.0 {
        return Err(BathtubErrorV1::InvalidBer);
    }

    // Locate the left crossing: first time the BER drops to <= target on
    // the ascending-left side; the right crossing is where BER rises back
    // above target. We walk forward and find the first and last sample
    // indices where ber <= target; interpolate at the two edges.
    let in_span: Vec<bool> = samples.iter().map(|s| s.ber() <= target_ber).collect();
    let first_in = in_span.iter().position(|b| *b);
    let Some(first_in) = first_in else {
        return Err(BathtubErrorV1::NoOpening);
    };
    let last_in = in_span.iter().rposition(|b| *b).unwrap();

    // Left crossing: between (first_in-1) and first_in if first_in > 0;
    // else at the leftmost sample already inside (clamp to its offset).
    let left = if first_in == 0 {
        samples[0].time_offset_ui()
    } else {
        interpolate_crossing(samples[first_in - 1], samples[first_in], target_ber)?
    };
    // Right crossing: between last_in and (last_in+1) if last_in < len-1;
    let right = if last_in == samples.len() - 1 {
        samples[last_in].time_offset_ui()
    } else {
        interpolate_crossing(samples[last_in], samples[last_in + 1], target_ber)?
    };

    let width = right - left;
    if width < 0.0 {
        return Err(BathtubErrorV1::NoOpening);
    }
    Ok(width)
}

/// Linear interpolation in log10(BER) between two adjacent samples to find
/// the time offset where BER equals the target.
fn interpolate_crossing(
    left: BathtubSampleV1,
    right: BathtubSampleV1,
    target_ber: f64,
) -> Result<f64, BathtubErrorV1> {
    let t = target_ber.clamp(1e-300, 1.0 - 1e-12);
    let lt = left.ber().max(1e-300).log10();
    let rt = right.ber().max(1e-300).log10();
    let tt = t.log10();
    if (rt - lt).abs() < 1e-300 {
        return Err(BathtubErrorV1::NoOpening);
    }
    let fraction = (tt - lt) / (rt - lt);
    let crossing =
        left.time_offset_ui() + fraction * (right.time_offset_ui() - left.time_offset_ui());
    Ok(crossing)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s(t: f64, ber: f64) -> BathtubSampleV1 {
        BathtubSampleV1::new(t, ber)
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            BATHTUB_POLICY_V1,
            "sipi.p3c-02f.bathtub-opening.v1.threshold"
        );
    }

    #[test]
    fn symmetric_bathtub_width() {
        // V-shape: BER 1e-3 at t=-0.5, 1e-9 at 0, 1e-3 at +0.5; target 1e-4.
        let samples = vec![s(-0.5, 1e-3), s(0.0, 1e-9), s(0.5, 1e-3)];
        let width = bathtub_opening_width_v1(&samples, 1e-4).expect("width");
        assert!(width > 0.6 && width < 0.9, "width={width}");
    }

    #[test]
    fn no_opening_when_all_above_target() {
        let samples = vec![s(-0.5, 1e-3), s(0.0, 1e-3), s(0.5, 1e-3)];
        let err = bathtub_opening_width_v1(&samples, 1e-6).expect_err("err");
        assert_eq!(err, BathtubErrorV1::NoOpening);
    }

    #[test]
    fn rejects_too_few_samples() {
        let err = bathtub_opening_width_v1(&[s(0.0, 1e-3), s(1.0, 1e-3)], 1e-4).expect_err("err");
        assert_eq!(err, BathtubErrorV1::TooFewSamples);
    }

    #[test]
    fn rejects_bad_target() {
        let samples = vec![s(-0.5, 1e-3), s(0.0, 1e-3), s(0.5, 1e-3)];
        assert_eq!(
            bathtub_opening_width_v1(&samples, 0.0).err(),
            Some(BathtubErrorV1::TargetBerOutOfRange)
        );
        assert_eq!(
            bathtub_opening_width_v1(&samples, 1.0).err(),
            Some(BathtubErrorV1::TargetBerOutOfRange)
        );
    }

    #[test]
    fn rejects_non_ascending_time() {
        let samples = vec![s(1.0, 1e-3), s(0.0, 1e-3), s(0.5, 1e-3)];
        assert_eq!(
            bathtub_opening_width_v1(&samples, 1e-4).err(),
            Some(BathtubErrorV1::TimeNotAscending)
        );
    }

    #[test]
    fn rejects_invalid_ber() {
        let samples = vec![s(-0.5, 0.0), s(0.0, 1e-3), s(0.5, 1e-3)];
        assert_eq!(
            bathtub_opening_width_v1(&samples, 1e-4).err(),
            Some(BathtubErrorV1::InvalidBer)
        );
    }
}
