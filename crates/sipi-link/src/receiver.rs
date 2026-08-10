//! Product-owned, fixed data-aided receiver for the approved P3B profile.

use std::{error::Error, fmt};

use sipi_contracts::ReceiverInputV1;
use sipi_types::{FiniteF64, Volts};

const SYMBOL_COUNT: usize = 128;
const SAMPLES_PER_UI: usize = 8;
const TRAINING_SYMBOLS: usize = 32;
const MEASUREMENT_SYMBOLS: usize = SYMBOL_COUNT - TRAINING_SYMBOLS;
const TAP_COUNT: usize = 5;
const MINIMUM_AMPLITUDE_VOLTS: f64 = 1.0e-6;
const MINIMUM_PHASE_MARGIN: f64 = 0.01;
const TRAINING_STEP: f64 = 0.25;

/// Caller-supplied symbols for the one approved receiver profile.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ReferenceBitsV1 {
    bits: Box<[bool]>,
}

impl ReferenceBitsV1 {
    pub fn try_new(bits: Vec<bool>) -> Result<Self, ReceiverError> {
        if bits.len() != SYMBOL_COUNT {
            return Err(ReceiverError::InvalidReferenceBitCount);
        }
        if !bits[..TRAINING_SYMBOLS].contains(&true) || !bits[..TRAINING_SYMBOLS].contains(&false) {
            return Err(ReceiverError::InsufficientTrainingSymbols);
        }
        Ok(Self {
            bits: bits.into_boxed_slice(),
        })
    }

    pub fn bits(&self) -> &[bool] {
        &self.bits
    }
}

/// A measurement symbol is either a hard decision or an explicit erasure.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReceiverDecisionV1 {
    Positive,
    Negative,
    Erasure,
}

impl ReceiverDecisionV1 {
    fn symbol(self) -> Option<f64> {
        match self {
            Self::Positive => Some(1.0),
            Self::Negative => Some(-1.0),
            Self::Erasure => None,
        }
    }

    fn feedback_symbol(self) -> f64 {
        self.symbol().unwrap_or(0.0)
    }
}

/// Immutable observations emitted by the approved fixed receiver.
#[derive(Clone, Debug, PartialEq)]
pub struct ReceiverResultV1 {
    phase: usize,
    center: Volts,
    amplitude: Volts,
    frozen_taps: [FiniteF64; TAP_COUNT],
    decisions: Box<[ReceiverDecisionV1]>,
    error_count: usize,
}

impl ReceiverResultV1 {
    pub fn phase(&self) -> usize {
        self.phase
    }

    pub fn locked(&self) -> bool {
        true
    }

    pub fn center(&self) -> Volts {
        self.center
    }

    pub fn amplitude(&self) -> Volts {
        self.amplitude
    }

    pub fn frozen_taps(&self) -> &[FiniteF64; TAP_COUNT] {
        &self.frozen_taps
    }

    pub fn decisions(&self) -> &[ReceiverDecisionV1] {
        &self.decisions
    }

    pub fn error_count(&self) -> usize {
        self.error_count
    }

    pub fn ber_denominator(&self) -> usize {
        MEASUREMENT_SYMBOLS
    }

    pub fn ber(&self) -> f64 {
        self.error_count as f64 / MEASUREMENT_SYMBOLS as f64
    }
}

/// Fail-closed errors for the approved receiver profile.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReceiverError {
    InvalidReferenceBitCount,
    InsufficientTrainingSymbols,
    CdrAmbiguous,
    AmplitudeTooSmall,
    NumericOverflow,
}

impl fmt::Display for ReceiverError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "fixed receiver rejected input: {self:?}")
    }
}

impl Error for ReceiverError {}

#[derive(Clone, Copy)]
struct PhaseCalibration {
    phase: usize,
    center: f64,
    amplitude: f64,
    score: f64,
}

/// Executes the sole approved data-aided, fixed-phase receiver behavior.
///
/// The input boundary is already strict about 1024 samples, zero origin, one
/// picosecond interval, eight samples per UI, and bypass frontend stages. This
/// function adds only the approved 128-bit reference and receiver semantics.
pub fn run_fixed_receiver_v1(
    input: &ReceiverInputV1,
    reference: &ReferenceBitsV1,
) -> Result<ReceiverResultV1, ReceiverError> {
    let calibration = select_phase(input, reference)?;
    if calibration.amplitude.abs() < MINIMUM_AMPLITUDE_VOLTS {
        return Err(ReceiverError::AmplitudeTooSmall);
    }
    let normalized = normalized_samples(input, calibration)?;
    let symbols = reference
        .bits()
        .iter()
        .map(|bit| if *bit { 1.0 } else { -1.0 })
        .collect::<Vec<_>>();
    let mut taps = [0.0; TAP_COUNT];

    for symbol_index in 0..TRAINING_SYMBOLS {
        let feedback = reference_feedback(&symbols, symbol_index);
        let z = checked_subtract(normalized[symbol_index], dot(&taps, &feedback)?)?;
        let error = checked_subtract(symbols[symbol_index], z)?;
        for (tap, prior_symbol) in taps.iter_mut().zip(feedback) {
            *tap = checked_subtract(*tap, checked_product(TRAINING_STEP * error, prior_symbol)?)?;
        }
    }

    let frozen_taps = [
        FiniteF64::try_new(taps[0], "fixed receiver tap")
            .map_err(|_| ReceiverError::NumericOverflow)?,
        FiniteF64::try_new(taps[1], "fixed receiver tap")
            .map_err(|_| ReceiverError::NumericOverflow)?,
        FiniteF64::try_new(taps[2], "fixed receiver tap")
            .map_err(|_| ReceiverError::NumericOverflow)?,
        FiniteF64::try_new(taps[3], "fixed receiver tap")
            .map_err(|_| ReceiverError::NumericOverflow)?,
        FiniteF64::try_new(taps[4], "fixed receiver tap")
            .map_err(|_| ReceiverError::NumericOverflow)?,
    ];
    let mut decisions = Vec::with_capacity(MEASUREMENT_SYMBOLS);
    let mut error_count = 0usize;
    for symbol_index in TRAINING_SYMBOLS..SYMBOL_COUNT {
        let feedback = measurement_feedback(&symbols, &decisions, symbol_index);
        let z = checked_subtract(normalized[symbol_index], dot(&taps, &feedback)?)?;
        let decision = if z > 0.0 {
            ReceiverDecisionV1::Positive
        } else if z < 0.0 {
            ReceiverDecisionV1::Negative
        } else {
            ReceiverDecisionV1::Erasure
        };
        if decision.symbol() != Some(symbols[symbol_index]) {
            error_count += 1;
        }
        decisions.push(decision);
    }

    Ok(ReceiverResultV1 {
        phase: calibration.phase,
        center: Volts::try_new(calibration.center).map_err(|_| ReceiverError::NumericOverflow)?,
        amplitude: Volts::try_new(calibration.amplitude)
            .map_err(|_| ReceiverError::NumericOverflow)?,
        frozen_taps,
        decisions: decisions.into_boxed_slice(),
        error_count,
    })
}

fn select_phase(
    input: &ReceiverInputV1,
    reference: &ReferenceBitsV1,
) -> Result<PhaseCalibration, ReceiverError> {
    let mut candidates = Vec::with_capacity(SAMPLES_PER_UI);
    for phase in 0..SAMPLES_PER_UI {
        let mut one_sum = 0.0;
        let mut zero_sum = 0.0;
        let mut one_count = 0usize;
        let mut zero_count = 0usize;
        for symbol_index in 0..TRAINING_SYMBOLS {
            let sample = input.receive()[phase + SAMPLES_PER_UI * symbol_index].get();
            if reference.bits()[symbol_index] {
                one_sum = checked_add(one_sum, sample)?;
                one_count += 1;
            } else {
                zero_sum = checked_add(zero_sum, sample)?;
                zero_count += 1;
            }
        }
        let mean_one = checked_divide(one_sum, one_count as f64)?;
        let mean_zero = checked_divide(zero_sum, zero_count as f64)?;
        let difference = checked_subtract(mean_one, mean_zero)?;
        candidates.push(PhaseCalibration {
            phase,
            center: checked_divide(checked_add(mean_one, mean_zero)?, 2.0)?,
            amplitude: checked_divide(difference, 2.0)?,
            score: difference.abs(),
        });
    }
    let mut ordered = candidates;
    ordered.sort_by(|left, right| right.score.total_cmp(&left.score));
    let best = ordered[0];
    let second = ordered[1];
    if best.score == 0.0
        || !best.score.is_finite()
        || best.score == second.score
        || checked_divide(best.score - second.score, best.score)? < MINIMUM_PHASE_MARGIN
    {
        return Err(ReceiverError::CdrAmbiguous);
    }
    Ok(best)
}

fn normalized_samples(
    input: &ReceiverInputV1,
    calibration: PhaseCalibration,
) -> Result<Vec<f64>, ReceiverError> {
    (0..SYMBOL_COUNT)
        .map(|symbol_index| {
            checked_divide(
                checked_subtract(
                    input.receive()[calibration.phase + SAMPLES_PER_UI * symbol_index].get(),
                    calibration.center,
                )?,
                calibration.amplitude,
            )
        })
        .collect()
}

fn reference_feedback(symbols: &[f64], symbol_index: usize) -> [f64; TAP_COUNT] {
    std::array::from_fn(|tap_index| {
        let delay = tap_index + 1;
        symbol_index
            .checked_sub(delay)
            .map_or(0.0, |index| symbols[index])
    })
}

fn measurement_feedback(
    symbols: &[f64],
    decisions: &[ReceiverDecisionV1],
    symbol_index: usize,
) -> [f64; TAP_COUNT] {
    std::array::from_fn(|tap_index| {
        let past = symbol_index - (tap_index + 1);
        if past < TRAINING_SYMBOLS {
            symbols[past]
        } else {
            decisions[past - TRAINING_SYMBOLS].feedback_symbol()
        }
    })
}

fn dot(taps: &[f64; TAP_COUNT], symbols: &[f64; TAP_COUNT]) -> Result<f64, ReceiverError> {
    taps.iter()
        .zip(symbols)
        .try_fold(0.0, |sum, (tap, symbol)| {
            checked_add(sum, checked_product(*tap, *symbol)?)
        })
}

fn checked_add(left: f64, right: f64) -> Result<f64, ReceiverError> {
    let result = left + right;
    result
        .is_finite()
        .then_some(result)
        .ok_or(ReceiverError::NumericOverflow)
}

fn checked_subtract(left: f64, right: f64) -> Result<f64, ReceiverError> {
    let result = left - right;
    result
        .is_finite()
        .then_some(result)
        .ok_or(ReceiverError::NumericOverflow)
}

fn checked_product(left: f64, right: f64) -> Result<f64, ReceiverError> {
    let result = left * right;
    result
        .is_finite()
        .then_some(result)
        .ok_or(ReceiverError::NumericOverflow)
}

fn checked_divide(left: f64, right: f64) -> Result<f64, ReceiverError> {
    let result = left / right;
    result
        .is_finite()
        .then_some(result)
        .ok_or(ReceiverError::NumericOverflow)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_contracts::{RxStagesV1, UniformTimebaseV1};
    use sipi_types::Seconds;

    fn bits() -> ReferenceBitsV1 {
        ReferenceBitsV1::try_new((0..SYMBOL_COUNT).map(|index| index % 2 == 0).collect()).unwrap()
    }

    fn input(phase: usize, amplitude: f64, mutate: impl Fn(usize, f64) -> f64) -> ReceiverInputV1 {
        let reference = bits();
        let mut samples = vec![Volts::try_new(0.0).unwrap(); 1024];
        for symbol_index in 0..SYMBOL_COUNT {
            let symbol = if reference.bits()[symbol_index] {
                1.0
            } else {
                -1.0
            };
            samples[phase + SAMPLES_PER_UI * symbol_index] =
                Volts::try_new(mutate(symbol_index, amplitude * symbol)).unwrap();
        }
        ReceiverInputV1::try_new(
            UniformTimebaseV1::try_new(
                Seconds::try_new(0.0).unwrap(),
                Seconds::try_new(1.0e-12).unwrap(),
                1024,
            )
            .unwrap(),
            samples,
            8,
            RxStagesV1::bypass(),
        )
        .unwrap()
    }

    #[test]
    fn selects_a_unique_phase_and_produces_exact_clean_decisions() {
        let result = run_fixed_receiver_v1(&input(3, 1.0, |_, value| value), &bits()).unwrap();
        assert_eq!(result.phase(), 3);
        assert!(result.locked());
        assert_eq!(result.decisions().len(), MEASUREMENT_SYMBOLS);
        assert_eq!(result.error_count(), 0);
        assert_eq!(result.ber_denominator(), 96);
        assert_eq!(result.ber(), 0.0);
    }

    #[test]
    fn rejects_invalid_bits_ambiguous_phase_and_small_amplitude() {
        assert_eq!(
            ReferenceBitsV1::try_new(vec![true; 127]),
            Err(ReceiverError::InvalidReferenceBitCount)
        );
        assert_eq!(
            ReferenceBitsV1::try_new(vec![true; 128]),
            Err(ReceiverError::InsufficientTrainingSymbols)
        );
        let ambiguous = input(0, 1.0, |_, value| value);
        let mut samples = ambiguous.receive().to_vec();
        for index in 0..SYMBOL_COUNT {
            samples[1 + SAMPLES_PER_UI * index] = samples[SAMPLES_PER_UI * index];
        }
        let tied = ReceiverInputV1::try_new(ambiguous.timebase(), samples, 8, RxStagesV1::bypass())
            .unwrap();
        assert_eq!(
            run_fixed_receiver_v1(&tied, &bits()),
            Err(ReceiverError::CdrAmbiguous)
        );
        assert_eq!(
            run_fixed_receiver_v1(&input(2, 1.0e-7, |_, value| value), &bits()),
            Err(ReceiverError::AmplitudeTooSmall)
        );
    }

    #[test]
    fn erasure_counts_as_error_uses_zero_feedback_and_continues() {
        let symbols = bits()
            .bits()
            .iter()
            .map(|bit| if *bit { 1.0 } else { -1.0 })
            .collect::<Vec<_>>();
        let feedback = measurement_feedback(
            &symbols,
            &[ReceiverDecisionV1::Erasure],
            TRAINING_SYMBOLS + 1,
        );
        assert_eq!(feedback[0], 0.0);
        let result = run_fixed_receiver_v1(
            &input(4, 1.0, |index, value| {
                if index == TRAINING_SYMBOLS {
                    0.0
                } else {
                    value
                }
            }),
            &bits(),
        )
        .unwrap();
        assert_eq!(result.decisions()[0], ReceiverDecisionV1::Erasure);
        assert_eq!(result.decisions().len(), MEASUREMENT_SYMBOLS);
        assert_eq!(result.error_count(), 1);
        assert_eq!(result.decisions()[1], ReceiverDecisionV1::Negative);
    }

    #[test]
    fn repeated_runs_are_deterministic_and_training_taps_freeze() {
        let waveform = input(5, 1.0, |index, value| {
            if index < TRAINING_SYMBOLS {
                value
            } else {
                value * 0.75
            }
        });
        let first = run_fixed_receiver_v1(&waveform, &bits()).unwrap();
        let second = run_fixed_receiver_v1(&waveform, &bits()).unwrap();
        assert_eq!(first, second);
        assert!(first.frozen_taps().iter().all(|tap| tap.get().is_finite()));
    }
}
