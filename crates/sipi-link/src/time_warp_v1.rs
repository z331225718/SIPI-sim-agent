//! Deterministic per-sample fractional time-warp shift core (P3B-05e).
//!
//! Applies a caller-supplied per-sample shift vector (in sample units) to a
//! sampled waveform by linear interpolation on the same sample grid. For
//! output sample n, the source position is p = n + shift[n]; the output is
//! the linear interpolation of the two nearest input samples (identical to
//! the input sample when p is integral). This is the deterministic time-warp
//! basis on top of the P3B-05d injection waveform: a bounded, reproducible
//! fractional-sample relocation with no noise, statistics, observables, or
//! tolerance semantics.
//!
//! Fail-closed rules: empty input, length mismatch between samples and
//! shifts, a non-finite sample or shift, or an output position whose
//! interpolation stencil would leave the input domain ([0, len-1]) are all
//! hard errors. There is no zero-padding, wraparound, or extrapolation
//! guess. The shift vector itself is supplied by the caller: the jitter/
//! time-warp model that generates shifts, the units model, observables, and
//! tolerance remain owner-decided and are NOT implemented here (the P3B-05a
//! wire-request rejection surface stays in force).

/// Stable scope policy of the P3B-05e time-warp shift core.
pub const TIME_WARP_POLICY_V1: &str = "sipi.p3b-05e.time-warp-shift.v1.linear-per-sample";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TimeWarpErrorV1 {
    EmptyWaveform,
    LengthMismatch,
    NonFiniteSample,
    NonFiniteShift,
    OutOfDomain { index: usize },
}

/// Applies a per-sample fractional shift via linear interpolation.
pub fn time_warp_shift_v1(
    samples: &[f64],
    shift_samples: &[f64],
) -> Result<Vec<f64>, TimeWarpErrorV1> {
    if samples.is_empty() {
        return Err(TimeWarpErrorV1::EmptyWaveform);
    }
    if samples.len() != shift_samples.len() {
        return Err(TimeWarpErrorV1::LengthMismatch);
    }
    if samples.iter().any(|value| !value.is_finite()) {
        return Err(TimeWarpErrorV1::NonFiniteSample);
    }
    if shift_samples.iter().any(|value| !value.is_finite()) {
        return Err(TimeWarpErrorV1::NonFiniteShift);
    }
    let last = (samples.len() - 1) as f64;
    let mut out = Vec::with_capacity(samples.len());
    for (n, &shift) in shift_samples.iter().enumerate() {
        let position = n as f64 + shift;
        if position < 0.0 || position > last {
            return Err(TimeWarpErrorV1::OutOfDomain { index: n });
        }
        let lo = position.floor() as usize;
        let hi = position.ceil() as usize;
        let frac = position - lo as f64;
        let value = if hi == lo {
            samples[lo]
        } else {
            samples[lo] * (1.0 - frac) + samples[hi] * frac
        };
        out.push(value);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(TIME_WARP_POLICY_V1, "sipi.p3b-05e.time-warp-shift.v1.linear-per-sample");
    }

    #[test]
    fn zero_shift_is_identity() {
        let samples = vec![1.0, -1.0, 1.0, -1.0];
        let shifts = vec![0.0, 0.0, 0.0, 0.0];
        assert_eq!(time_warp_shift_v1(&samples, &shifts).unwrap(), samples);
    }

    #[test]
    fn half_sample_shift_interpolates_midpoint() {
        let samples = vec![0.0, 2.0, 4.0];
        let shifts = vec![0.5, 0.5, 0.0];
        assert_eq!(time_warp_shift_v1(&samples, &shifts).unwrap(), vec![1.0, 3.0, 4.0]);
    }

    #[test]
    fn positive_quarter_shift_interpolates() {
        let samples = vec![0.0, 2.0, 4.0, 8.0];
        let shifts = vec![0.25, 0.25, 0.25, 0.0];
        // n=0 p=0.25 -> 0*0.75+2*0.25=0.5; n=1 p=1.25 -> 2*.75+4*.25=2.5;
        // n=2 p=2.25 -> 4*.75+8*.25=5.0; n=3 p=3.0 -> 8.0
        assert_eq!(time_warp_shift_v1(&samples, &shifts).unwrap(), vec![0.5, 2.5, 5.0, 8.0]);
    }

    #[test]
    fn out_of_domain_forward_and_backward_are_errors() {
        let samples = vec![1.0, 2.0, 3.0];
        assert_eq!(
            time_warp_shift_v1(&samples, &[0.0, 0.0, 0.5]).err(),
            Some(TimeWarpErrorV1::OutOfDomain { index: 2 })
        );
        assert_eq!(
            time_warp_shift_v1(&samples, &[-0.5, 0.0, 0.0]).err(),
            Some(TimeWarpErrorV1::OutOfDomain { index: 0 })
        );
    }

    #[test]
    fn rejects_empty_and_length_mismatch() {
        assert_eq!(time_warp_shift_v1(&[], &[]).err(), Some(TimeWarpErrorV1::EmptyWaveform));
        assert_eq!(
            time_warp_shift_v1(&[1.0], &[0.0, 0.0]).err(),
            Some(TimeWarpErrorV1::LengthMismatch)
        );
    }

    #[test]
    fn rejects_non_finite_inputs() {
        assert_eq!(
            time_warp_shift_v1(&[1.0, f64::NAN], &[0.0, 0.0]).err(),
            Some(TimeWarpErrorV1::NonFiniteSample)
        );
        assert_eq!(
            time_warp_shift_v1(&[1.0, 2.0], &[0.0, f64::INFINITY]).err(),
            Some(TimeWarpErrorV1::NonFiniteShift)
        );
    }
}
