//! Deterministic maximum-likelihood sequence estimation for finite ISI states.

use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum IsiDecodeError {
    #[error(
        "ISI decoder requires at least two symbol levels, one state symbol, and finite positive sigma"
    )]
    InvalidConfiguration,
    #[error("pulse response must contain at least the configured state-symbol count")]
    PulseTooShort,
    #[error("observations must be finite and contain at least one trellis depth")]
    InvalidObservations,
    #[error("state count exceeds the configured resource limit")]
    StateLimitExceeded,
}

#[derive(Debug, Clone, PartialEq)]
pub struct IsiDecodeConfig {
    pub levels: usize,
    pub state_symbols: usize,
    pub sigma: f64,
    pub max_states: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct IsiDecodeResult {
    pub state_path: Vec<usize>,
    pub symbols: Vec<f64>,
}

/// TI DN504-style rate-1/2 convolutional encoder used by the PAM4 FEC mode.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FecEncoder {
    state: [i32; 3],
}

impl FecEncoder {
    pub fn new(initial_state: [i32; 3]) -> Self {
        Self {
            state: initial_state.map(|value| value.rem_euclid(2)),
        }
    }

    pub fn state(&self) -> [i32; 3] {
        self.state
    }

    pub fn step(&mut self, input: i32) -> (i32, i32) {
        let input = i32::from(input != 0);
        let [first, second, third] = self.state;
        let output = (
            (input + first + second + third).rem_euclid(2),
            (input + second + third).rem_euclid(2),
        );
        self.state = [input, first, second];
        output
    }

    pub fn encode(&mut self, bits: &[i32]) -> Vec<(i32, i32)> {
        bits.iter().map(|&bit| self.step(bit)).collect()
    }
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum FecDecodeError {
    #[error("FEC decoder requires a trellis depth of at least two")]
    InvalidTrellisDepth,
    #[error("FEC decoder requires at least one observation per trellis column")]
    TooFewObservations,
    #[error("FEC observations must contain binary pairs")]
    InvalidObservation,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FecDecodeResult {
    pub state_path: Vec<usize>,
    pub bits: Vec<i32>,
}

/// Decode the TI DN504-style rate-1/2 convolutional code with a fixed-depth
/// Viterbi trellis. State ordering and strict tie breaking match
/// ``pybert.models.fec.FEC_Decoder`` exactly.
pub fn decode_fec(
    observations: &[(i32, i32)],
    trellis_depth: usize,
) -> Result<FecDecodeResult, FecDecodeError> {
    const STATE_COUNT: usize = 16;
    if trellis_depth < 2 {
        return Err(FecDecodeError::InvalidTrellisDepth);
    }
    if observations.len() < trellis_depth {
        return Err(FecDecodeError::TooFewObservations);
    }
    if observations
        .iter()
        .any(|&(first, second)| !(0..=1).contains(&first) || !(0..=1).contains(&second))
    {
        return Err(FecDecodeError::InvalidObservation);
    }

    let mut trellis = vec![
        vec![
            TrellisNode {
                probability: 1.0 / STATE_COUNT as f64,
                previous: 0,
            };
            STATE_COUNT
        ];
        trellis_depth
    ];
    let mut first_column = (0..STATE_COUNT)
        .map(|state| fec_emission_probability(state, observations[0]))
        .collect::<Vec<_>>();
    normalize_or_uniform(&mut first_column);
    trellis[trellis_depth - 1] = first_column
        .into_iter()
        .enumerate()
        .map(|(state, probability)| TrellisNode {
            probability,
            previous: state,
        })
        .collect();

    for &observation in &observations[1..trellis_depth] {
        step_fec_trellis(&mut trellis, observation);
    }
    let mut state_path = Vec::with_capacity(observations.len());
    for &observation in &observations[trellis_depth..] {
        step_fec_trellis(&mut trellis, observation);
        state_path.push(backtrack_path(&trellis)[0]);
    }
    let final_path = backtrack_path(&trellis);
    state_path.extend_from_slice(&final_path[1..]);
    state_path.push(max_probability_state(
        trellis.last().expect("trellis depth was validated"),
    ));
    let bits = state_path
        .iter()
        .map(|&state| ((state >> 3) & 1) as i32)
        .collect();
    Ok(FecDecodeResult { state_path, bits })
}

#[derive(Debug, Clone, Copy)]
struct TrellisNode {
    probability: f64,
    previous: usize,
}

pub fn decode_isi(
    observations: &[f64],
    pulse_response_samples: &[f64],
    config: IsiDecodeConfig,
) -> Result<IsiDecodeResult, IsiDecodeError> {
    if config.levels < 2
        || config.state_symbols == 0
        || !config.sigma.is_finite()
        || config.sigma <= 0.0
        || config.max_states == 0
    {
        return Err(IsiDecodeError::InvalidConfiguration);
    }
    if pulse_response_samples.len() < config.state_symbols
        || pulse_response_samples
            .iter()
            .any(|value| !value.is_finite())
    {
        return Err(IsiDecodeError::PulseTooShort);
    }
    if observations.len() < config.state_symbols
        || observations.iter().any(|value| !value.is_finite())
    {
        return Err(IsiDecodeError::InvalidObservations);
    }
    let state_count = config
        .levels
        .checked_pow(config.state_symbols as u32)
        .filter(|&count| count <= config.max_states)
        .ok_or(IsiDecodeError::StateLimitExceeded)?;
    let prefix_scale = config.levels.pow((config.state_symbols - 1) as u32);
    let expected = (0..state_count)
        .map(|state| expected_sample(state, pulse_response_samples, &config))
        .collect::<Vec<_>>();
    let mut trellis = vec![
        vec![
            TrellisNode {
                probability: 1.0 / state_count as f64,
                previous: 0,
            };
            state_count
        ];
        config.state_symbols
    ];

    let mut first_column = expected
        .iter()
        .map(|&value| emission_probability(observations[0] - value, config.sigma))
        .collect::<Vec<_>>();
    normalize_or_uniform(&mut first_column);
    trellis[config.state_symbols - 1] = first_column
        .into_iter()
        .enumerate()
        .map(|(state, probability)| TrellisNode {
            probability,
            previous: state,
        })
        .collect();

    for &observation in &observations[1..config.state_symbols] {
        step_trellis(
            &mut trellis,
            observation,
            &expected,
            config.levels,
            prefix_scale,
            config.sigma,
        );
    }
    let mut path = Vec::with_capacity(observations.len());
    for &observation in &observations[config.state_symbols..] {
        step_trellis(
            &mut trellis,
            observation,
            &expected,
            config.levels,
            prefix_scale,
            config.sigma,
        );
        path.push(backtrack_path(&trellis)[0]);
    }
    let final_path = backtrack_path(&trellis);
    path.extend_from_slice(&final_path[1..]);
    path.push(max_probability_state(
        trellis.last().expect("non-empty trellis"),
    ));
    let symbols = path
        .iter()
        .map(|&state| symbol_value(state % config.levels, config.levels))
        .collect();
    Ok(IsiDecodeResult {
        state_path: path,
        symbols,
    })
}

fn step_trellis(
    trellis: &mut [Vec<TrellisNode>],
    observation: f64,
    expected: &[f64],
    levels: usize,
    prefix_scale: usize,
    sigma: f64,
) {
    let previous_column = trellis.last().expect("non-empty trellis").clone();
    trellis.rotate_left(1);
    let mut new_column = Vec::with_capacity(expected.len());
    for (state, &expected_value) in expected.iter().enumerate() {
        let suffix = state / levels;
        let emission = emission_probability(observation - expected_value, sigma);
        let mut probability = 0.0;
        let mut previous = state;
        for leading_symbol in 0..levels {
            let candidate = leading_symbol * prefix_scale + suffix;
            let candidate_probability =
                previous_column[candidate].probability * (1.0 / levels as f64) * emission;
            if candidate_probability > probability {
                probability = candidate_probability;
                previous = candidate;
            }
        }
        new_column.push(TrellisNode {
            probability,
            previous,
        });
    }
    let mut probabilities = new_column
        .iter()
        .map(|node| node.probability)
        .collect::<Vec<_>>();
    normalize_or_uniform(&mut probabilities);
    for (node, probability) in new_column.iter_mut().zip(probabilities) {
        node.probability = probability;
    }
    *trellis.last_mut().expect("non-empty trellis") = new_column;
}

fn step_fec_trellis(trellis: &mut [Vec<TrellisNode>], observation: (i32, i32)) {
    const STATE_COUNT: usize = 16;
    let previous_column = trellis.last().expect("trellis depth was validated").clone();
    trellis.rotate_left(1);
    let mut new_column = Vec::with_capacity(STATE_COUNT);
    for state in 0..STATE_COUNT {
        let emission = fec_emission_probability(state, observation);
        let mut probability = 0.0;
        let mut previous = state;
        for tail in 0..=1 {
            let candidate = ((state & 0b0111) << 1) | tail;
            let candidate_probability = previous_column[candidate].probability * 0.5 * emission;
            if candidate_probability > probability {
                probability = candidate_probability;
                previous = candidate;
            }
        }
        new_column.push(TrellisNode {
            probability,
            previous,
        });
    }
    let mut probabilities = new_column
        .iter()
        .map(|node| node.probability)
        .collect::<Vec<_>>();
    normalize_or_uniform(&mut probabilities);
    for (node, probability) in new_column.iter_mut().zip(probabilities) {
        node.probability = probability;
    }
    *trellis.last_mut().expect("trellis depth was validated") = new_column;
}

fn backtrack_path(trellis: &[Vec<TrellisNode>]) -> Vec<usize> {
    let depth = trellis.len();
    let mut previous = trellis[depth - 1][max_probability_state(&trellis[depth - 1])].previous;
    let mut path = vec![previous];
    for column in (0..depth - 1).rev() {
        previous = trellis[column][previous].previous;
        path.push(previous);
    }
    path.reverse();
    path
}

fn max_probability_state(column: &[TrellisNode]) -> usize {
    column
        .iter()
        .enumerate()
        .fold((0, f64::NEG_INFINITY), |best, (state, node)| {
            if node.probability > best.1 {
                (state, node.probability)
            } else {
                best
            }
        })
        .0
}

fn normalize_or_uniform(probabilities: &mut [f64]) {
    let total = probabilities.iter().sum::<f64>();
    if total > 0.0 && total.is_finite() {
        probabilities.iter_mut().for_each(|value| *value /= total);
    } else {
        probabilities.fill(1.0 / probabilities.len() as f64);
    }
}

fn expected_sample(state: usize, pulse: &[f64], config: &IsiDecodeConfig) -> f64 {
    (0..config.state_symbols)
        .map(|index| {
            let digit = (state / config.levels.pow(index as u32)) % config.levels;
            pulse[index] * symbol_value(digit, config.levels)
        })
        .sum()
}

fn symbol_value(digit: usize, levels: usize) -> f64 {
    -1.0 + digit as f64 * 2.0 / (levels - 1) as f64
}

fn emission_probability(delta: f64, sigma: f64) -> f64 {
    const GRID_POINTS: usize = 4_000;
    if !(-2.0..=2.0).contains(&delta) {
        return 0.0;
    }
    let position = (delta + 2.0) * (GRID_POINTS - 1) as f64 / 4.0;
    let lower = position.floor() as usize;
    let density = |grid_index: usize| {
        let voltage = -2.0 + grid_index as f64 * 4.0 / (GRID_POINTS - 1) as f64;
        1.0e-3 * (-(voltage * voltage) / (2.0 * sigma * sigma)).exp()
            / (std::f64::consts::TAU * sigma * sigma).sqrt()
    };
    if lower >= GRID_POINTS - 1 {
        density(GRID_POINTS - 1)
    } else {
        let fraction = position - lower as f64;
        density(lower) * (1.0 - fraction) + density(lower + 1) * fraction
    }
}

fn fec_emission_probability(state: usize, observation: (i32, i32)) -> f64 {
    const STATE_COUNT: f64 = 16.0;
    let bits = [
        ((state >> 3) & 1) as i32,
        ((state >> 2) & 1) as i32,
        ((state >> 1) & 1) as i32,
        (state & 1) as i32,
    ];
    let expected = (
        (bits[0] + bits[1] + bits[2] + bits[3]).rem_euclid(2),
        (bits[0] + bits[2] + bits[3]).rem_euclid(2),
    );
    (2 - (observation.0 - expected.0).abs() - (observation.1 - expected.1).abs()) as f64
        / STATE_COUNT
}
