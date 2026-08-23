// SPDX-License-Identifier: MIT
// Direct-port source: Agent-COM `equalization/apply.py` at the pinned
// commit/tree recorded in `SOURCE-MAP-COM-02.md`.
//
//! R480 `Apply_EQ` channel equalization path.
//!
//! CTLE, rectangular pulse formation, TX FFE selection semantics, and RX FFE
//! filtering are all delegated to the already-portable COM primitives.  This
//! module only owns the source's channel-role ordering and CL93/CL120 branch
//! decisions.

use crate::{
    EqualizerErrorV1, RxFfeErrorV1, SearchLoopErrorV1, apply_rx_ffe_v1,
    rectangular_pulse_response_v1, td_ctle_v1,
};

pub const EQUALIZATION_APPLY_POLICY_V1: &str = "sipi.com.equalization.apply-r480-v1.ctle-tx-rx-ffe";

#[derive(Clone, Debug, PartialEq)]
pub struct EqualizedChannelsV1 {
    impulse_responses: Vec<Vec<f64>>,
    pulse_responses: Vec<Vec<f64>>,
}

impl EqualizedChannelsV1 {
    pub fn impulse_responses(&self) -> &[Vec<f64>] {
        &self.impulse_responses
    }

    pub fn pulse_responses(&self) -> &[Vec<f64>] {
        &self.pulse_responses
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum EqualizationApplyErrorV1 {
    EmptyOrMismatchedChannels,
    UnsupportedCtleType,
    MissingHighPassControls,
    MissingRxFfeControls,
    UnsupportedChannelType,
    Ctle(EqualizerErrorV1),
    RxFfe(RxFfeErrorV1),
    Pulse(SearchLoopErrorV1),
}

impl From<EqualizerErrorV1> for EqualizationApplyErrorV1 {
    fn from(value: EqualizerErrorV1) -> Self {
        Self::Ctle(value)
    }
}

impl From<RxFfeErrorV1> for EqualizationApplyErrorV1 {
    fn from(value: RxFfeErrorV1) -> Self {
        Self::RxFfe(value)
    }
}

impl From<SearchLoopErrorV1> for EqualizationApplyErrorV1 {
    fn from(value: SearchLoopErrorV1) -> Self {
        Self::Pulse(value)
    }
}

#[allow(clippy::too_many_arguments)]
pub fn apply_r480_equalization_v1(
    unequalized_impulses: &[Vec<f64>],
    channel_types: &[String],
    baud_hz: f64,
    samples_per_ui: usize,
    ctle_type: &str,
    ctle_fz_hz: f64,
    ctle_fp1_hz: f64,
    ctle_fp2_hz: f64,
    ctle_gain_db: f64,
    tx_ffe_taps: &[f64],
    tx_precursor_count: usize,
    high_pass_hz: Option<f64>,
    high_pass_gain_db: Option<f64>,
    high_pass_zero_hz: Option<f64>,
    high_pass_pole_hz: Option<f64>,
    rx_ffe_taps: Option<&[f64]>,
    rx_ffe_precursor_count: Option<usize>,
) -> Result<EqualizedChannelsV1, EqualizationApplyErrorV1> {
    if unequalized_impulses.is_empty() || unequalized_impulses.len() != channel_types.len() {
        return Err(EqualizationApplyErrorV1::EmptyOrMismatchedChannels);
    }
    if !matches!(ctle_type, "CL93" | "CL120d" | "CL120e") {
        return Err(EqualizationApplyErrorV1::UnsupportedCtleType);
    }
    if ctle_type == "CL120d" && (high_pass_hz.is_none() || high_pass_gain_db.is_none()) {
        return Err(EqualizationApplyErrorV1::MissingHighPassControls);
    }
    if ctle_type == "CL120e" && (high_pass_zero_hz.is_none() || high_pass_pole_hz.is_none()) {
        return Err(EqualizationApplyErrorV1::MissingHighPassControls);
    }
    if rx_ffe_taps.is_some() != rx_ffe_precursor_count.is_some() {
        return Err(EqualizationApplyErrorV1::MissingRxFfeControls);
    }
    let mut impulses = Vec::with_capacity(unequalized_impulses.len());
    let mut pulses = Vec::with_capacity(unequalized_impulses.len());
    for (waveform, channel_type) in unequalized_impulses.iter().zip(channel_types) {
        let kind = channel_type.to_ascii_uppercase();
        if !matches!(kind.as_str(), "THRU" | "FEXT" | "NEXT") {
            return Err(EqualizationApplyErrorV1::UnsupportedChannelType);
        }
        let mut equalized = td_ctle_v1(
            waveform,
            baud_hz,
            ctle_fz_hz,
            ctle_fp1_hz,
            ctle_fp2_hz,
            ctle_gain_db,
            samples_per_ui,
        )?;
        match ctle_type {
            "CL120d" => {
                equalized = td_ctle_v1(
                    &equalized,
                    baud_hz,
                    high_pass_hz.expect("validated high-pass frequency"),
                    high_pass_hz.expect("validated high-pass frequency"),
                    1.0e100,
                    high_pass_gain_db.expect("validated high-pass gain"),
                    samples_per_ui,
                )?;
            }
            "CL120e" => {
                equalized = td_ctle_v1(
                    &equalized,
                    baud_hz,
                    high_pass_zero_hz.expect("validated high-pass zero"),
                    high_pass_pole_hz.expect("validated high-pass pole"),
                    1.0e99,
                    0.0,
                    samples_per_ui,
                )?;
            }
            "CL93" => {}
            _ => unreachable!("CTLE type was validated"),
        }
        let mut pulse = rectangular_pulse_response_v1(&equalized, samples_per_ui)?;
        // R4.80 intentionally skips the TX FFE for NEXT channels.
        if matches!(kind.as_str(), "THRU" | "FEXT") {
            pulse = apply_rx_ffe_v1(tx_ffe_taps, tx_precursor_count, samples_per_ui, &pulse)?;
        }
        if let (Some(taps), Some(precursor)) = (rx_ffe_taps, rx_ffe_precursor_count) {
            pulse = apply_rx_ffe_v1(taps, precursor, samples_per_ui, &pulse)?;
        }
        impulses.push(equalized);
        pulses.push(pulse);
    }
    Ok(EqualizedChannelsV1 {
        impulse_responses: impulses,
        pulse_responses: pulses,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn impulse() -> Vec<f64> {
        (0..32)
            .map(|index| {
                let offset = index as f64 - 10.0;
                (-offset * offset / 12.0).exp()
            })
            .collect()
    }

    #[test]
    fn apply_eq_skips_tx_ffe_for_next_and_returns_aligned_waveforms() {
        let waveforms = vec![impulse(), impulse()];
        let types = vec!["THRU".to_owned(), "NEXT".to_owned()];
        let result = apply_r480_equalization_v1(
            &waveforms,
            &types,
            25.0e9,
            4,
            "CL93",
            0.5,
            1.0,
            2.0,
            0.0,
            &[1.0, 0.5],
            0,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        .expect("Apply_EQ");
        assert_eq!(result.impulse_responses().len(), 2);
        assert_eq!(result.pulse_responses().len(), 2);
        assert_eq!(
            result.impulse_responses()[0].len(),
            result.pulse_responses()[0].len()
        );
        assert_ne!(result.pulse_responses()[0], result.pulse_responses()[1]);
    }

    #[test]
    fn cl120_branches_fail_closed_without_controls() {
        let waveforms = vec![impulse()];
        let types = vec!["THRU".to_owned()];
        let error = apply_r480_equalization_v1(
            &waveforms,
            &types,
            25.0e9,
            4,
            "CL120d",
            0.5,
            1.0,
            2.0,
            0.0,
            &[1.0],
            0,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        .unwrap_err();
        assert_eq!(error, EqualizationApplyErrorV1::MissingHighPassControls);
    }
}
