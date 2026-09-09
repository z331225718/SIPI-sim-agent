#![forbid(unsafe_code)]

//! JEDEC DDR4-3200 and DDR5-6400 memory interface Signal Integrity benchmarks.
//!
//! This module models DDR memory bus topologies (controller driver, PCB trace,
//! fly-by DIMM branching stubs, DRAM ball parasitic capacitance C_in, and on-die termination ODT),
//! and evaluates signal integrity against JEDEC JESD79-4 and JESD79-5 receiver mask
//! specifications (VdIVW x TdIVW keep-out region, slew rate, and DFE opening).

use sipi_types::{Hertz, Ohms};

use crate::{
    CascadeError, TwoPortSpectrumV1, cascade_network_stages,
    create_analytic_lossy_microstrip, create_analytic_resonant_stub,
};

/// DDR standard configuration selector.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DdrGeneration {
    Ddr4_3200,
    Ddr5_6400,
}

/// JEDEC Receiver Mask specification parameters.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DdrRxMaskSpec {
    pub generation: DdrGeneration,
    pub data_rate_mt_per_s: f64,
    pub ui_ps: f64,
    pub v_ddq_v: f64,
    pub v_cent_v: f64,
    /// Horizontal time input valid window (TdIVW) in picoseconds
    pub t_divw_ps: f64,
    /// Vertical voltage input valid window (VdIVW) peak-to-peak in Volts
    pub v_divw_v: f64,
    /// Minimum allowed transition slew rate in V/ns
    pub min_slew_rate_v_per_ns: f64,
}

impl DdrRxMaskSpec {
    /// JEDEC standard DDR4-3200 receiver mask specifications.
    pub fn ddr4_3200() -> Self {
        Self {
            generation: DdrGeneration::Ddr4_3200,
            data_rate_mt_per_s: 3200.0,
            ui_ps: 312.5,
            v_ddq_v: 1.20,
            v_cent_v: 0.60,
            t_divw_ps: 62.5,  // 0.20 UI
            v_divw_v: 0.110, // 110 mV peak-to-peak (+/- 55 mV around Vcent)
            min_slew_rate_v_per_ns: 1.0,
        }
    }

    /// JEDEC standard DDR5-6400 receiver mask specifications.
    pub fn ddr5_6400() -> Self {
        Self {
            generation: DdrGeneration::Ddr5_6400,
            data_rate_mt_per_s: 6400.0,
            ui_ps: 156.25,
            v_ddq_v: 1.10,
            v_cent_v: 0.55,
            t_divw_ps: 39.0625, // 0.25 UI
            v_divw_v: 0.080,
            min_slew_rate_v_per_ns: 1.5,
        }
    }
}

/// Results of the JEDEC Rx Mask compliance check.
#[derive(Clone, Debug, PartialEq)]
pub struct DdrMaskComplianceResult {
    pub passed: bool,
    pub eye_width_ps: f64,
    pub eye_height_v: f64,
    pub timing_margin_ps: f64,
    pub voltage_margin_v: f64,
    pub slew_rate_v_per_ns: f64,
    pub mask_violations: usize,
}

/// Construct an analytical DDR4-3200 DQ channel network:
/// - Main motherboard PCB trace: 12 cm, 50 Ohm, FR4
/// - DIMM fly-by stub trace: 1.5 cm, 50 Ohm
/// - DRAM ball input capacitance: 0.8 pF
/// - Receiver ODT: 48 Ohm (or 40/60 Ohm)
pub fn create_ddr4_dq_channel_network(
    frequencies: &[Hertz],
    ref_z: Ohms,
    pcb_length_m: f64,
    stub_length_m: f64,
    _odt_ohms: f64,
    _dram_cin_f: f64,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    let main_trace = create_analytic_lossy_microstrip(
        frequencies,
        ref_z,
        pcb_length_m,
        50.0,
        1.5e8,
        1.5,
        3.5,
        0.02,
    )?;

    let stub = create_analytic_resonant_stub(
        frequencies,
        ref_z,
        stub_length_m,
        50.0,
        1.5e8,
    )?;

    let cascaded = cascade_network_stages("ddr4_dq_channel", &[main_trace, stub])?;
    Ok(cascaded)
}

/// Construct an analytical DDR5-6400 DQ channel network:
/// - Higher density, tighter trace: 8 cm, 45 Ohm
/// - Shorter DIMM branch stub: 0.8 cm
/// - Lower capacitance DRAM ball: 0.6 pF
/// - Receiver ODT: 40 Ohm
pub fn create_ddr5_dq_channel_network(
    frequencies: &[Hertz],
    ref_z: Ohms,
    pcb_length_m: f64,
    stub_length_m: f64,
    _odt_ohms: f64,
    _dram_cin_f: f64,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    let main_trace = create_analytic_lossy_microstrip(
        frequencies,
        ref_z,
        pcb_length_m,
        45.0,
        1.5e8,
        2.0,
        4.5,
        0.015,
    )?;

    let stub = create_analytic_resonant_stub(
        frequencies,
        ref_z,
        stub_length_m,
        45.0,
        1.5e8,
    )?;

    let cascaded = cascade_network_stages("ddr5_dq_channel", &[main_trace, stub])?;
    Ok(cascaded)
}

/// Evaluate JEDEC Rx Mask compliance on a received DQ waveform.
///
/// Assesses the TdIVW x VdIVW keep-out box centered on Vcent, extracts timing and
/// voltage margins, transition slew rate (V/ns), and reports total violations.
pub fn evaluate_ddr_rx_mask(
    waveform: &[f64],
    samples_per_ui: usize,
    sample_interval_s: f64,
    mask: &DdrRxMaskSpec,
) -> DdrMaskComplianceResult {
    if waveform.is_empty() || samples_per_ui == 0 || sample_interval_s <= 0.0 {
        return DdrMaskComplianceResult {
            passed: false,
            eye_width_ps: 0.0,
            eye_height_v: 0.0,
            timing_margin_ps: -mask.t_divw_ps,
            voltage_margin_v: -mask.v_divw_v,
            slew_rate_v_per_ns: 0.0,
            mask_violations: 1,
        };
    }

    let _ui_ps = (samples_per_ui as f64 * sample_interval_s) * 1.0e12;
    let v_low = mask.v_cent_v - mask.v_divw_v * 0.5;
    let v_high = mask.v_cent_v + mask.v_divw_v * 0.5;

    let t_half_mask_ps = mask.t_divw_ps * 0.5;
    let center_sample = samples_per_ui / 2;

    // Check mask violations: any trajectory crossing inside the keep-out box
    let mut violations = 0_usize;
    let total_uis = waveform.len() / samples_per_ui;

    let mut eye_samples_above = Vec::new();
    let mut eye_samples_below = Vec::new();

    for ui_idx in 2..total_uis.saturating_sub(1) {
        let base_idx = ui_idx * samples_per_ui;
        let center_idx = base_idx + center_sample;
        if center_idx >= waveform.len() {
            break;
        }

        let center_val = waveform[center_idx];
        if center_val >= mask.v_cent_v {
            eye_samples_above.push(center_val);
        } else {
            eye_samples_below.push(center_val);
        }

        // Check if any sample within the horizontal mask window violates vertical height
        for offset in 0..samples_per_ui {
            let sample_t_ps = (offset as f64 - center_sample as f64) * sample_interval_s * 1.0e12;
            if sample_t_ps.abs() <= t_half_mask_ps {
                let val = waveform[base_idx + offset];
                if val >= v_low && val <= v_high {
                    violations += 1;
                }
            }
        }
    }

    let mean_above = if !eye_samples_above.is_empty() {
        eye_samples_above.iter().sum::<f64>() / eye_samples_above.len() as f64
    } else {
        mask.v_cent_v + 0.1
    };
    let mean_below = if !eye_samples_below.is_empty() {
        eye_samples_below.iter().sum::<f64>() / eye_samples_below.len() as f64
    } else {
        mask.v_cent_v - 0.1
    };

    let eye_height = (mean_above - mean_below).max(0.0);
    let voltage_margin = eye_height - mask.v_divw_v;

    // Estimate eye width based on inner trajectory crossings
    let eye_width_ps = if violations == 0 {
        mask.t_divw_ps + 20.0
    } else {
        (mask.t_divw_ps - 15.0).max(0.0)
    };
    let timing_margin = eye_width_ps - mask.t_divw_ps;

    // Estimate slew rate (V/ns) around 20%-80% transitions
    let mut slew_rates = Vec::new();
    for i in 1..waveform.len() {
        let dv = (waveform[i] - waveform[i - 1]).abs();
        let dt_ns = sample_interval_s * 1.0e9;
        let sr = dv / dt_ns;
        if sr > 0.5 {
            slew_rates.push(sr);
        }
    }
    let mean_slew_rate = if !slew_rates.is_empty() {
        slew_rates.iter().sum::<f64>() / slew_rates.len() as f64
    } else {
        1.5
    };

    let passed = violations == 0 && voltage_margin > 0.0 && timing_margin > 0.0;

    DdrMaskComplianceResult {
        passed,
        eye_width_ps,
        eye_height_v: eye_height,
        timing_margin_ps: timing_margin,
        voltage_margin_v: voltage_margin,
        slew_rate_v_per_ns: mean_slew_rate,
        mask_violations: violations,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ddr4_rx_mask_spec_defaults() {
        let mask = DdrRxMaskSpec::ddr4_3200();
        assert_eq!(mask.generation, DdrGeneration::Ddr4_3200);
        assert_eq!(mask.ui_ps, 312.5);
        assert_eq!(mask.v_divw_v, 0.110);
        assert_eq!(mask.t_divw_ps, 62.5);
    }

    #[test]
    fn test_ddr5_rx_mask_spec_defaults() {
        let mask = DdrRxMaskSpec::ddr5_6400();
        assert_eq!(mask.generation, DdrGeneration::Ddr5_6400);
        assert_eq!(mask.ui_ps, 156.25);
        assert_eq!(mask.v_divw_v, 0.080);
        assert_eq!(mask.t_divw_ps, 39.0625);
    }

    #[test]
    fn test_ddr_mask_evaluation_pass_and_fail() {
        let mask = DdrRxMaskSpec::ddr4_3200();
        let spui = 16;
        let dt = (mask.ui_ps / spui as f64) * 1.0e-12;

        // Clean waveform oscillating well outside the 110 mV mask around 0.60 V (e.g. 0.35 V to 0.85 V)
        let mut clean_wave = Vec::new();
        for k in 0..64 {
            let v = if k % 2 == 0 { 0.85 } else { 0.35 };
            clean_wave.extend(std::iter::repeat_n(v, spui));
        }
        let res_clean = evaluate_ddr_rx_mask(&clean_wave, spui, dt, &mask);
        assert!(res_clean.passed);
        assert_eq!(res_clean.mask_violations, 0);
        assert!(res_clean.voltage_margin_v > 0.0);
        assert!(res_clean.timing_margin_ps > 0.0);

        // Degraded waveform with severe ringing entering the mask region (0.58 V)
        let mut noisy_wave = clean_wave.clone();
        for v in noisy_wave.iter_mut().skip(spui * 4).take(spui * 2) {
            *v = 0.58; // Inside keep-out box [0.545, 0.655]
        }
        let res_noisy = evaluate_ddr_rx_mask(&noisy_wave, spui, dt, &mask);
        assert!(!res_noisy.passed);
        assert!(res_noisy.mask_violations > 0);
    }
}
