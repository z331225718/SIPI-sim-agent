//! Deterministic PRBS9 TX-injection waveform core (P3B-05d).
//!
//! Maps PRBS9 bits (P3B-05c) to a DC-balanced time-domain injection waveform
//! at the owner-decided TX injection point (A4: PRBS9, TX, time model). Each
//! bit emits samples_per_ui samples of +amplitude (bit 1) or -amplitude
//! (bit 0), producing a length bit_count * samples_per_ui waveform. This is the
//! deterministic injection basis; the full time-warp jitter model and
//! observables/tolerance remain out of scope.

use super::prbs9_v1::{Prbs9V1, PRBS9_OWNER_SEED_BITS};

/// Stable scope policy of the P3B-05d injection waveform core.
pub const PRBS9_INJECT_POLICY_V1: &str = "sipi.p3b-05d.prbs9-inject.v1.tx-waveform";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum InjectWaveformErrorV1 {
    ZeroSamplesPerUi,
    ZeroBitCount,
    NonFiniteAmplitude,
}

/// Builds a deterministic PRBS9 injection waveform (DC-balanced +/- amplitude).
pub fn prbs9_inject_waveform_v1(
    seed_bits: u16,
    bit_count: usize,
    samples_per_ui: usize,
    amplitude_v: f64,
) -> Result<Vec<f64>, InjectWaveformErrorV1> {
    if samples_per_ui == 0 { return Err(InjectWaveformErrorV1::ZeroSamplesPerUi); }
    if bit_count == 0 { return Err(InjectWaveformErrorV1::ZeroBitCount); }
    if !amplitude_v.is_finite() { return Err(InjectWaveformErrorV1::NonFiniteAmplitude); }
    let mut generator = Prbs9V1::new(seed_bits);
    let mut waveform = Vec::with_capacity(bit_count * samples_per_ui);
    for _ in 0..bit_count {
        let bit = generator.next_bit();
        let value = if bit == 1 { amplitude_v } else { -amplitude_v };
        waveform.extend(std::iter::repeat(value).take(samples_per_ui));
    }
    Ok(waveform)
}

/// Convenience: builds the waveform with the owner-decided default seed.
pub fn owner_default_inject_waveform_v1(
    bit_count: usize, samples_per_ui: usize, amplitude_v: f64,
) -> Result<Vec<f64>, InjectWaveformErrorV1> {
    prbs9_inject_waveform_v1(PRBS9_OWNER_SEED_BITS, bit_count, samples_per_ui, amplitude_v)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::prbs9_v1::Prbs9V1;

    #[test]
    fn policy_fixed() {
        assert_eq!(PRBS9_INJECT_POLICY_V1, "sipi.p3b-05d.prbs9-inject.v1.tx-waveform");
    }

    #[test]
    fn waveform_length_and_first_marks() {
        let w = prbs9_inject_waveform_v1(0x001, 4, 2, 1.0).expect("w");
        assert_eq!(w.len(), 8);
        let mut g = Prbs9V1::new(0x001);
        assert_eq!(g.next_bit(), 0);
        assert_eq!(g.next_bit(), 0);
        assert_eq!(&w[0..2], &[-1.0, -1.0]);
        assert_eq!(&w[2..4], &[-1.0, -1.0]);
    }

    #[test]
    fn owner_default_seed_used() {
        let w = owner_default_inject_waveform_v1(1, 1, 1.0).expect("w");
        assert_eq!(w, vec![-1.0]);
    }

    #[test]
    fn rejects_zero_spu() {
        assert_eq!(prbs9_inject_waveform_v1(1, 4, 0, 1.0).err(), Some(InjectWaveformErrorV1::ZeroSamplesPerUi));
    }

    #[test]
    fn rejects_zero_bits() {
        assert_eq!(prbs9_inject_waveform_v1(1, 0, 1, 1.0).err(), Some(InjectWaveformErrorV1::ZeroBitCount));
    }
}