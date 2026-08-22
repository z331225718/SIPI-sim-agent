//! Composable native link stages with no dependency on the Python object model.

use thiserror::Error;

use crate::{
    CdrConfig, DfeConfig, DfeModulation, DfeRunError, DfeRunOptions, DfeRunResult,
    EqualizationError, PatternError, SignalError, SymbolModulation, causal_convolve_truncated,
    ffe_impulse_response, generate_prbs_bits, modulate_bits, run_dfe,
};

#[derive(Debug, Error, PartialEq)]
pub enum LinearLinkError {
    #[error("symbols and channel impulse response must be non-empty and finite")]
    InvalidInput,
    #[error("requested waveform exceeds the configured output limit")]
    OutputLimitExceeded,
    #[error(transparent)]
    Equalization(#[from] EqualizationError),
    #[error(transparent)]
    Signal(#[from] SignalError),
    #[error(transparent)]
    Dfe(#[from] DfeRunError),
    #[error(transparent)]
    Pattern(#[from] PatternError),
}

#[derive(Debug, Clone, PartialEq)]
pub struct LinearDfeLinkResult {
    pub linear: LinearLinkResult,
    pub dfe: DfeRunResult,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LinearDfeLinkConfig {
    pub samples_per_ui: usize,
    pub sample_interval_s: f64,
    pub max_output_samples: usize,
    pub dfe: DfeConfig,
    pub cdr: CdrConfig,
    pub options: DfeRunOptions,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PrbsLinearDfeLinkConfig {
    pub prbs_order: u8,
    pub seed: u64,
    pub bit_count: usize,
    pub amplitude_v: f64,
    pub link: LinearDfeLinkConfig,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PrbsLinearDfeLinkResult {
    pub bits: Vec<i32>,
    pub symbols: Vec<f64>,
    pub link: LinearDfeLinkResult,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LinearLinkResult {
    pub tx_impulse: Vec<f64>,
    pub tx_channel_impulse: Vec<f64>,
    pub tx_waveform: Vec<f64>,
    pub rx_input: Vec<f64>,
    pub rx_output: Vec<f64>,
}

/// Execute PyBERT's native-TX linear path: symbol hold, sample-spaced FFE,
/// channel convolution, and truncated RX input waveform.
pub fn run_linear_link(
    symbols: &[f64],
    channel_impulse: &[f64],
    ffe_weights: &[f64],
    samples_per_ui: usize,
    max_output_samples: usize,
) -> Result<LinearLinkResult, LinearLinkError> {
    run_linear_link_with_rx_filter(
        symbols,
        channel_impulse,
        ffe_weights,
        &[1.0],
        samples_per_ui,
        max_output_samples,
    )
}

/// Continue the native-TX linear path through a host-supplied RX impulse
/// response. This supports native CTLE once its frequency response has been
/// transformed to a sampled impulse response, without involving Python state.
pub fn run_linear_link_with_rx_filter(
    symbols: &[f64],
    channel_impulse: &[f64],
    ffe_weights: &[f64],
    rx_filter_impulse: &[f64],
    samples_per_ui: usize,
    max_output_samples: usize,
) -> Result<LinearLinkResult, LinearLinkError> {
    if symbols.is_empty()
        || channel_impulse.is_empty()
        || symbols
            .iter()
            .chain(channel_impulse)
            .chain(rx_filter_impulse)
            .any(|value| !value.is_finite())
    {
        return Err(LinearLinkError::InvalidInput);
    }
    let waveform_len = symbols
        .len()
        .checked_mul(samples_per_ui)
        .ok_or(LinearLinkError::OutputLimitExceeded)?;
    if samples_per_ui == 0 || waveform_len > max_output_samples {
        return Err(LinearLinkError::OutputLimitExceeded);
    }
    let weights = if ffe_weights.is_empty() {
        &[1.0][..]
    } else {
        ffe_weights
    };
    let tx_impulse = ffe_impulse_response(weights, samples_per_ui, channel_impulse.len())?;
    let tx_channel_impulse =
        causal_convolve_truncated(&tx_impulse, channel_impulse, channel_impulse.len())?;
    let tx_waveform = symbols
        .iter()
        .flat_map(|symbol| std::iter::repeat_n(*symbol, samples_per_ui))
        .collect::<Vec<_>>();
    let rx_input = causal_convolve_truncated(&tx_waveform, &tx_channel_impulse, waveform_len)?;
    let rx_output = causal_convolve_truncated(&rx_input, rx_filter_impulse, waveform_len)?;
    Ok(LinearLinkResult {
        tx_impulse,
        tx_channel_impulse,
        tx_waveform,
        rx_input,
        rx_output,
    })
}

/// Compose the migrated linear path with native DFE/CDR. Time samples are
/// constructed only from the explicitly supplied SI sample interval.
pub fn run_linear_dfe_link(
    symbols: &[f64],
    channel_impulse: &[f64],
    ffe_weights: &[f64],
    rx_filter_impulse: &[f64],
    config: LinearDfeLinkConfig,
) -> Result<LinearDfeLinkResult, LinearLinkError> {
    if !config.sample_interval_s.is_finite() || config.sample_interval_s <= 0.0 {
        return Err(LinearLinkError::InvalidInput);
    }
    let linear = run_linear_link_with_rx_filter(
        symbols,
        channel_impulse,
        ffe_weights,
        rx_filter_impulse,
        config.samples_per_ui,
        config.max_output_samples,
    )?;
    let sample_times = (0..linear.rx_output.len())
        .map(|index| index as f64 * config.sample_interval_s)
        .collect::<Vec<_>>();
    let dfe = run_dfe(
        &sample_times,
        &linear.rx_output,
        config.dfe,
        config.cdr,
        config.options,
    )?;
    Ok(LinearDfeLinkResult { linear, dfe })
}

/// Run the native PRBS generator, matching symbol mapper, and sampled link as
/// one deterministic path. FEC encoding intentionally remains an explicit
/// separate stage because it changes the PAM-4 bit pairing contract.
pub fn run_prbs_linear_dfe_link(
    channel_impulse: &[f64],
    ffe_weights: &[f64],
    rx_filter_impulse: &[f64],
    config: PrbsLinearDfeLinkConfig,
) -> Result<PrbsLinearDfeLinkResult, LinearLinkError> {
    let bits = generate_prbs_bits(config.prbs_order, config.seed, config.bit_count)?;
    let symbol_modulation = match config.link.dfe.modulation {
        DfeModulation::Nrz => SymbolModulation::Nrz,
        DfeModulation::DuoBinary => SymbolModulation::DuoBinary,
        DfeModulation::Pam4 => SymbolModulation::Pam4,
    };
    let symbols = modulate_bits(&bits, symbol_modulation, config.amplitude_v)?;
    let link = run_linear_dfe_link(
        &symbols,
        channel_impulse,
        ffe_weights,
        rx_filter_impulse,
        config.link,
    )?;
    Ok(PrbsLinearDfeLinkResult {
        bits,
        symbols,
        link,
    })
}
