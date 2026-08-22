//! Deterministic PRBS generation compatible with PyBERT's legacy LFSR.

use thiserror::Error;

#[derive(Debug, Error, PartialEq, Eq)]
pub enum PatternError {
    #[error("unsupported PRBS order; supported orders are 7, 9, 11, 13, 15, 19, 20, 23, and 31")]
    UnsupportedOrder,
    #[error("PRBS seed must be non-zero and fit the selected LFSR order")]
    InvalidSeed,
    #[error("symbol modulation must be NRZ (0), DuoBinary (1), or PAM4 (2)")]
    InvalidModulation,
    #[error("bit values must be zero or one and amplitude must be finite")]
    InvalidSymbolInput,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SymbolModulation {
    Nrz,
    DuoBinary,
    Pam4,
}

impl TryFrom<u8> for SymbolModulation {
    type Error = PatternError;

    fn try_from(value: u8) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::Nrz),
            1 => Ok(Self::DuoBinary),
            2 => Ok(Self::Pam4),
            _ => Err(PatternError::InvalidModulation),
        }
    }
}

/// Generate a fixed-length PRBS using the same Fibonacci LFSR update as
/// `pybert.utility.math.lfsr_bits`. A zero seed is rejected here because the
/// product adapter must turn its legacy "random seed" option into an explicit
/// persisted seed before handing work to the deterministic Rust core.
pub fn generate_prbs_bits(
    order: u8,
    seed: u64,
    bit_count: usize,
) -> Result<Vec<i32>, PatternError> {
    let taps = taps_for_order(order).ok_or(PatternError::UnsupportedOrder)?;
    let mask = (1_u64 << order) - 1;
    if seed == 0 || seed & !mask != 0 {
        return Err(PatternError::InvalidSeed);
    }
    let mut state = seed;
    let mut bits = Vec::with_capacity(bit_count);
    for _ in 0..bit_count {
        let feedback = taps.iter().fold(false, |value, &tap| {
            value ^ (state & (1_u64 << (tap - 1)) != 0)
        });
        state = (state << 1) & mask;
        if feedback {
            state |= 1;
        }
        bits.push((state & 1) as i32);
    }
    Ok(bits)
}

/// Convert validated binary data to the legacy PyBERT NRZ, duo-binary, or
/// Gray-coded PAM-4 voltage symbols. FEC encoding stays a separate stage.
pub fn modulate_bits(
    bits: &[i32],
    modulation: SymbolModulation,
    amplitude_v: f64,
) -> Result<Vec<f64>, PatternError> {
    if !amplitude_v.is_finite() || bits.iter().any(|&bit| bit != 0 && bit != 1) {
        return Err(PatternError::InvalidSymbolInput);
    }
    let normalized: Vec<f64> = match modulation {
        SymbolModulation::Nrz => bits.iter().map(|&bit| 2.0 * bit as f64 - 1.0).collect(),
        SymbolModulation::DuoBinary => {
            let mut previous = 0;
            bits.iter()
                .map(|&bit| {
                    previous ^= bit;
                    2.0 * previous as f64 - 1.0
                })
                .collect()
        }
        SymbolModulation::Pam4 => bits
            .chunks_exact(2)
            .map(|pair| match pair {
                [0, 0] => -1.0,
                [0, 1] => -1.0 / 3.0,
                [1, 1] => 1.0 / 3.0,
                [1, 0] => 1.0,
                _ => unreachable!("input bits have been validated"),
            })
            .collect(),
    };
    Ok(normalized
        .into_iter()
        .map(|symbol| symbol * amplitude_v)
        .collect())
}

fn taps_for_order(order: u8) -> Option<&'static [u8]> {
    match order {
        7 => Some(&[7, 6]),
        9 => Some(&[9, 5]),
        11 => Some(&[11, 9]),
        13 => Some(&[13, 12, 2, 1]),
        15 => Some(&[15, 14]),
        19 => Some(&[19, 18]),
        20 => Some(&[20, 3]),
        23 => Some(&[23, 18]),
        31 => Some(&[31, 28]),
        _ => None,
    }
}
