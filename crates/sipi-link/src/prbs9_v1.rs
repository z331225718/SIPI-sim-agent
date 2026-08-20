//! Deterministic PRBS9 sequence core (P3B-05c).
//!
//! Implements the owner-decided seed/PRBS semantics (A4 decision, ref
//! docs/baselines/owner-decision-checklist.v1.md): PRBS9 profile with a
//! reproducible 9-bit LFSR generator. The generator is the standard
//! x^9+x^5+1 maximal-length polynomial (ITU-T O.150 / IEEE 802.3 PRBS9
//! family), seeded from the full 9-bit register value; the owner chose seed
//! 0b000000001 (0x001).
//!
//! Scope (fail-closed): this slice provides the deterministic sequence core
//! and its seed-replay guarantee. Injection position (TX), the time-warp
//! units model, observables, and tolerance are the remaining owner-decided
//! surface and are NOT implemented here; the P3B-05a wire-request rejection
//! surface remains in force unchanged.

/// Stable scope policy of the P3B-05c PRBS9 core.
pub const PRBS9_POLICY_V1: &str = "sipi.p3b-05c.prbs9-sequence.v1.deterministic-core";

/// Number of LFSR stages for PRBS9.
pub const PRBS9_STAGES: u32 = 9;

/// Default owner-selected seed: 0b000000001.
pub const PRBS9_OWNER_SEED_BITS: u16 = 0x001;

/// Output bit mask for the 9 independent data outputs of PRBS9.
const MASK: u16 = 0x1FF;

/// Deterministic PRBS9 generator (x^9+x^5+1 LFSR).
///
/// The register advances on a clock; the output bit is the MSB of the
/// register. Shift direction and tap follow the standard PRBS9 mapping
/// (register bit 8 is output; bits 8 and 4 are XORed into the new bit 0).
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Prbs9V1 {
    register: u16,
    emitted: u64,
}

impl Prbs9V1 {
    /// Create a generator with the seed exactly as supplied (full 9-bit
    /// value; only bits 0..8 are used, but the caller supplies the raw bits).
    pub fn new(seed_bits: u16) -> Self {
        Self {
            register: seed_bits & MASK,
            emitted: 0,
        }
    }

    /// Create a generator with the owner-decided default seed.
    pub fn owner_default() -> Self {
        Self::new(PRBS9_OWNER_SEED_BITS)
    }

    /// Step the LFSR once and return the output bit (0 or 1).
    pub fn next_bit(&mut self) -> u8 {
        let out = ((self.register >> (PRBS9_STAGES - 1)) & 1) as u8;
        let feedback = ((self.register >> 8) ^ (self.register >> 4)) & 1;
        self.register = ((self.register << 1) | feedback) & MASK;
        self.emitted += 1;
        out
    }

    /// Emit `count` bits as bytes (LSB-first packing; bit i of byte j is
    /// the (j*8+i)-th output).
    pub fn next_bytes(&mut self, count: usize) -> Vec<u8> {
        let mut out = Vec::with_capacity(count.div_ceil(8));
        let mut acc = 0u8;
        let mut acc_bits = 0usize;
        for _ in 0..count {
            let bit = self.next_bit();
            acc |= bit << acc_bits;
            acc_bits += 1;
            if acc_bits == 8 {
                out.push(acc);
                acc = 0;
                acc_bits = 0;
            }
        }
        if acc_bits > 0 {
            out.push(acc);
        }
        out
    }

    /// Current register state (for seed-replay / check-pointing).
    pub fn state(&self) -> u16 {
        self.register
    }

    /// Number of bits emitted so far.
    pub fn emitted_bits(&self) -> u64 {
        self.emitted
    }

    /// Restore a checkpointed register state (seed replay primitive).
    pub fn restore(&mut self, register: u16, emitted: u64) {
        self.register = register & MASK;
        self.emitted = emitted;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PRBS9_POLICY_V1,
            "sipi.p3b-05c.prbs9-sequence.v1.deterministic-core"
        );
    }

    #[test]
    fn first_outputs_match_lfsr() {
        // Manual LFSR trace for seed 0x001 (register bit 8..0).
        // init reg = 0b000000001. out = bit8 = 0. fb = bit8^bit4 = 0^0 = 0.
        // reg = (0x001 << 1) | 0 = 0x002. The seed 1 walks to the output
        // over 8 shifts, so first outputs are 0x0 ... 1.
        let mut g = Prbs9V1::new(0x001);
        let expected = [0, 0, 0, 0, 0, 0, 0, 0, 1];
        let got: Vec<u8> = (0..expected.len()).map(|_| g.next_bit()).collect();
        assert_eq!(got, expected.to_vec());
    }

    #[test]
    fn owner_default_seed() {
        assert_eq!(Prbs9V1::owner_default().state(), 0x001);
    }

    #[test]
    fn seed_replay_is_deterministic() {
        let mut a = Prbs9V1::owner_default();
        let mut b = Prbs9V1::owner_default();
        let av: Vec<u8> = (0..200).map(|_| a.next_bit()).collect();
        let bv: Vec<u8> = (0..200).map(|_| b.next_bit()).collect();
        assert_eq!(av, bv);
    }

    #[test]
    fn checkpoint_restore_matches() {
        let mut g = Prbs9V1::owner_default();
        for _ in 0..37 {
            g.next_bit();
        }
        let state = g.state();
        let emitted = g.emitted_bits();
        let mut g2 = Prbs9V1::owner_default();
        for _ in 0..37 {
            g2.next_bit();
        }
        assert_eq!(g2.state(), state);
        g2.restore(state, emitted);
        let next_a = g.next_bit();
        let next_b = g2.next_bit();
        assert_eq!(next_a, next_b);
        assert_eq!(g.state(), g2.state());
    }

    #[test]
    fn byte_packing_lsb_first() {
        let mut g = Prbs9V1::new(0x001);
        let b0 = g.next_bytes(8);
        assert_eq!(b0, vec![0x00]);
        let mut g2 = Prbs9V1::new(0x001);
        for _ in 0..8 {
            g2.next_bit();
        }
        let bits: Vec<u8> = (0..8).map(|_| g2.next_bit()).collect();
        let mut expected = 0u8;
        for (i, b) in bits.iter().enumerate() {
            expected |= b << i;
        }
        let mut g3 = Prbs9V1::new(0x001);
        let _ = g3.next_bytes(8);
        assert_eq!(g3.next_bytes(8), vec![expected]);
    }

    #[test]
    fn register_bounds_mask() {
        let mut g = Prbs9V1::new(0x1FF);
        for _ in 0..100 {
            g.next_bit();
            assert!(g.state() <= 0x1FF);
        }
    }
}
