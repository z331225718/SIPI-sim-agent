#![forbid(unsafe_code)]

//! PAM4 modulation three-eye statistical analysis, level extraction,
//! IEEE 802.3ck Level Separation Mismatch Ratio (RLM), and SER-to-BER mapping.

use thiserror::Error;

#[derive(Debug, Error, PartialEq)]
pub enum Pam4EyeError {
    #[error("waveform must not be empty and samples per UI must be greater than zero")]
    InvalidInput,
    #[error("sample interval must be finite and positive")]
    InvalidSampleInterval,
    #[error("waveform contains non-finite values")]
    NonFiniteWaveform,
}

/// The four physical voltage levels of a PAM4 signal.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Pam4Levels {
    pub v0: f64,
    pub v1: f64,
    pub v2: f64,
    pub v3: f64,
}

/// The three decision thresholds separating the four PAM4 levels.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Pam4Thresholds {
    pub lower: f64,
    pub mid: f64,
    pub upper: f64,
}

/// Three-eye statistical metrics for a PAM4 link.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Pam4EyeMetrics {
    pub levels: Pam4Levels,
    pub thresholds: Pam4Thresholds,
    pub eye_height_lower_v: f64,
    pub eye_height_mid_v: f64,
    pub eye_height_upper_v: f64,
    pub eye_height_worst_v: f64,
    pub inner_eye_height_lower_v: f64,
    pub inner_eye_height_mid_v: f64,
    pub inner_eye_height_upper_v: f64,
    pub inner_eye_height_worst_v: f64,
    pub eye_width_lower_ps: f64,
    pub eye_width_mid_ps: f64,
    pub eye_width_upper_ps: f64,
    pub eye_width_worst_ps: f64,
    pub rlm: f64,
    pub ser: f64,
    pub ber: f64,
    pub symbol_count: usize,
}

/// Calculate PAM4 three-eye heights, widths, RLM, SER, and BER from the received waveform.
pub fn calculate_pam4_eye_metrics(
    waveform: &[f64],
    samples_per_ui: usize,
    sample_interval_s: f64,
    tx_bits: &[i32],
    rx_bits: Option<&[i32]>,
) -> Result<Pam4EyeMetrics, Pam4EyeError> {
    if waveform.is_empty() || samples_per_ui == 0 {
        return Err(Pam4EyeError::InvalidInput);
    }
    if !sample_interval_s.is_finite() || sample_interval_s <= 0.0 {
        return Err(Pam4EyeError::InvalidSampleInterval);
    }
    if waveform.iter().any(|v| !v.is_finite()) {
        return Err(Pam4EyeError::NonFiniteWaveform);
    }

    let symbol_count = waveform.len() / samples_per_ui;
    if symbol_count == 0 {
        return Err(Pam4EyeError::InvalidInput);
    }

    // Map tx_bits (pairs of bits) to transmitted symbol level (0, 1, 2, 3)
    let tx_symbols: Vec<usize> = tx_bits
        .chunks_exact(2)
        .take(symbol_count)
        .map(|pair| match pair {
            [0, 0] => 0,
            [0, 1] => 1,
            [1, 1] => 2,
            [1, 0] => 3,
            _ => 0,
        })
        .collect();

    // Construct ideal symbol waveform to determine optimal sampling phase/delay
    let ideal_levels = [-1.0, -1.0 / 3.0, 1.0 / 3.0, 1.0];
    let mut ideal_wave = Vec::with_capacity(tx_symbols.len() * samples_per_ui);
    for &sym in &tx_symbols {
        let val = ideal_levels[sym.min(3)];
        ideal_wave.extend(std::iter::repeat_n(val, samples_per_ui));
    }

    let mean_ideal = ideal_wave.iter().sum::<f64>() / ideal_wave.len().max(1) as f64;
    let mean_wave = waveform.iter().sum::<f64>() / waveform.len().max(1) as f64;

    // Search for lag that maximizes cross-correlation
    let max_search_lag = (waveform.len() / 2).min(2048);
    let mut best_lag = samples_per_ui / 2;
    let mut max_corr = f64::NEG_INFINITY;

    for lag in 0..max_search_lag {
        let mut corr = 0.0_f64;
        let n_eval = (waveform.len() - lag).min(ideal_wave.len());
        if n_eval == 0 {
            break;
        }
        for i in 0..n_eval {
            corr += (waveform[i + lag] - mean_wave) * (ideal_wave[i] - mean_ideal);
        }
        if corr > max_corr {
            max_corr = corr;
            best_lag = lag;
        }
    }

    // Sample waveform at best_lag of each UI
    let mut samples_by_level: [Vec<f64>; 4] = [Vec::new(), Vec::new(), Vec::new(), Vec::new()];

    for (k, &sym) in tx_symbols.iter().enumerate() {
        let sample_idx = k * samples_per_ui + best_lag;
        if sample_idx < waveform.len() {
            samples_by_level[sym].push(waveform[sample_idx]);
        }
    }

    // Mean level calculation with fallback to global min/max if any level is sparse
    let mean_of = |samples: &[f64], fallback: f64| -> f64 {
        if samples.is_empty() {
            fallback
        } else {
            samples.iter().sum::<f64>() / samples.len() as f64
        }
    };

    let global_min = waveform.iter().copied().fold(f64::INFINITY, f64::min);
    let global_max = waveform.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let v_amp = (global_max - global_min).max(1e-6) / 2.0;
    let v_center = (global_max + global_min) / 2.0;

    let v0 = mean_of(&samples_by_level[0], v_center - v_amp);
    let v1 = mean_of(&samples_by_level[1], v_center - v_amp / 3.0);
    let v2 = mean_of(&samples_by_level[2], v_center + v_amp / 3.0);
    let v3 = mean_of(&samples_by_level[3], v_center + v_amp);

    let levels = Pam4Levels { v0, v1, v2, v3 };

    // Slicing thresholds
    let thresholds = Pam4Thresholds {
        lower: (v0 + v1) / 2.0,
        mid: (v1 + v2) / 2.0,
        upper: (v2 + v3) / 2.0,
    };

    // Calculate inner eye opening and statistical opening
    let level_min = |samples: &[f64], fallback: f64| -> f64 {
        samples.iter().copied().fold(fallback, f64::min)
    };
    let level_max = |samples: &[f64], fallback: f64| -> f64 {
        samples.iter().copied().fold(fallback, f64::max)
    };
    let level_sigma = |samples: &[f64], mean: f64| -> f64 {
        if samples.len() < 2 {
            0.0
        } else {
            let var = samples.iter().map(|&x| (x - mean).powi(2)).sum::<f64>() / (samples.len() - 1) as f64;
            var.sqrt()
        }
    };

    let s0 = level_sigma(&samples_by_level[0], v0);
    let s1 = level_sigma(&samples_by_level[1], v1);
    let s2 = level_sigma(&samples_by_level[2], v2);
    let s3 = level_sigma(&samples_by_level[3], v3);

    // IEEE 802.3ck PAM4 eye heights (mean level separations)
    let eh_lower = (v1 - v0).max(0.0);
    let eh_mid = (v2 - v1).max(0.0);
    let eh_upper = (v3 - v2).max(0.0);
    let eh_worst = eh_lower.min(eh_mid).min(eh_upper);

    // Inner deterministic eye openings at sampling phase
    let inner_lower = (level_min(&samples_by_level[1], v1) - level_max(&samples_by_level[0], v0)).max(0.0);
    let inner_mid = (level_min(&samples_by_level[2], v2) - level_max(&samples_by_level[1], v1)).max(0.0);
    let inner_upper = (level_min(&samples_by_level[3], v3) - level_max(&samples_by_level[2], v2)).max(0.0);
    let inner_worst = inner_lower.min(inner_mid).min(inner_upper);

    // Calculate eye widths by evaluating horizontal opening across phase offsets around best_lag
    let ui_ps = (samples_per_ui as f64 * sample_interval_s) * 1.0e12;
    let phase_base = if best_lag >= samples_per_ui / 2 {
        best_lag - samples_per_ui / 2
    } else {
        0
    };

    let calculate_eye_width = |thresh: f64, lower_lvl: usize, upper_lvl: usize| -> f64 {
        let mut open_phases = 0_usize;
        for offset in 0..samples_per_ui {
            let phase = phase_base + offset;
            let mut lower_max = f64::NEG_INFINITY;
            let mut upper_min = f64::INFINITY;

            for (k, &sym) in tx_symbols.iter().enumerate() {
                let idx = k * samples_per_ui + phase;
                if idx < waveform.len() {
                    let val = waveform[idx];
                    if sym == lower_lvl && val > lower_max {
                        lower_max = val;
                    } else if sym == upper_lvl && val < upper_min {
                        upper_min = val;
                    }
                }
            }

            if upper_min > lower_max && lower_max < thresh && upper_min > thresh {
                open_phases += 1;
            }
        }
        (open_phases as f64 / samples_per_ui as f64) * ui_ps
    };

    let ew_lower = calculate_eye_width(thresholds.lower, 0, 1);
    let ew_mid = calculate_eye_width(thresholds.mid, 1, 2);
    let ew_upper = calculate_eye_width(thresholds.upper, 2, 3);
    let ew_worst = ew_lower.min(ew_mid).min(ew_upper);

    // Calculate IEEE 802.3ck Level Separation Mismatch Ratio (RLM)
    let dv1 = v1 - v0;
    let dv2 = v2 - v1;
    let dv3 = v3 - v2;
    let v_total = v3 - v0;

    let rlm = if v_total > 1e-12 {
        let min_dv = dv1.min(dv2).min(dv3);
        ((3.0 * min_dv) / v_total).clamp(0.0, 1.0)
    } else {
        1.0
    };

    // Calculate SER and BER
    let (ser, ber) = if let Some(rx_bits) = rx_bits {
        let rx_symbols: Vec<usize> = rx_bits
            .chunks_exact(2)
            .take(tx_symbols.len())
            .map(|pair| match pair {
                [0, 0] => 0,
                [0, 1] => 1,
                [1, 1] => 2,
                [1, 0] => 3,
                _ => 0,
            })
            .collect();

        let mut sym_errors = 0_usize;
        let mut bit_errors = 0_usize;
        let evaluated_syms = tx_symbols.len().min(rx_symbols.len());

        for i in 0..evaluated_syms {
            if tx_symbols[i] != rx_symbols[i] {
                sym_errors += 1;
            }
        }

        let evaluated_bits = evaluated_syms * 2;
        for i in 0..evaluated_bits {
            if tx_bits[i] != rx_bits[i] {
                bit_errors += 1;
            }
        }

        let calculated_ser = if evaluated_syms > 0 {
            sym_errors as f64 / evaluated_syms as f64
        } else {
            0.0
        };

        let calculated_ber = if evaluated_bits > 0 {
            bit_errors as f64 / evaluated_bits as f64
        } else {
            0.0
        };

        (calculated_ser, calculated_ber)
    } else {
        (0.0, 0.0)
    };

    Ok(Pam4EyeMetrics {
        levels,
        thresholds,
        eye_height_lower_v: eh_lower,
        eye_height_mid_v: eh_mid,
        eye_height_upper_v: eh_upper,
        eye_height_worst_v: eh_worst,
        inner_eye_height_lower_v: inner_lower,
        inner_eye_height_mid_v: inner_mid,
        inner_eye_height_upper_v: inner_upper,
        inner_eye_height_worst_v: inner_worst,
        eye_width_lower_ps: ew_lower,
        eye_width_mid_ps: ew_mid,
        eye_width_upper_ps: ew_upper,
        eye_width_worst_ps: ew_worst,
        rlm,
        ser,
        ber,
        symbol_count,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ideal_pam4_noiseless_metrics() {
        let samples_per_ui = 16;
        let dt = 1.953125e-12; // 32 GBd -> UI = 31.25 ps
        let n_symbols = 128;
        let mut tx_bits = Vec::new();
        let mut waveform = Vec::new();

        for k in 0..n_symbols {
            let sym = k % 4;
            let (b0, b1) = match sym {
                0 => (0, 0),
                1 => (0, 1),
                2 => (1, 1),
                3 => (1, 0),
                _ => unreachable!(),
            };
            tx_bits.push(b0);
            tx_bits.push(b1);

            let v = match sym {
                0 => -0.6,
                1 => -0.2,
                2 => 0.2,
                3 => 0.6,
                _ => unreachable!(),
            };
            waveform.extend(std::iter::repeat_n(v, samples_per_ui));
        }

        let metrics = calculate_pam4_eye_metrics(
            &waveform,
            samples_per_ui,
            dt,
            &tx_bits,
            Some(&tx_bits),
        )
        .unwrap();

        assert!((metrics.levels.v0 - (-0.6)).abs() < 1e-12);
        assert!((metrics.levels.v1 - (-0.2)).abs() < 1e-12);
        assert!((metrics.levels.v2 - 0.2).abs() < 1e-12);
        assert!((metrics.levels.v3 - 0.6).abs() < 1e-12);

        assert!((metrics.thresholds.lower - (-0.4)).abs() < 1e-12);
        assert!((metrics.thresholds.mid - 0.0).abs() < 1e-12);
        assert!((metrics.thresholds.upper - 0.4).abs() < 1e-12);

        // Ideal RLM must be 1.0
        assert!((metrics.rlm - 1.0).abs() < 1e-12);

        // All three eye heights must be 0.4 V
        assert!((metrics.eye_height_lower_v - 0.4).abs() < 1e-12);
        assert!((metrics.eye_height_mid_v - 0.4).abs() < 1e-12);
        assert!((metrics.eye_height_upper_v - 0.4).abs() < 1e-12);
        assert!((metrics.eye_height_worst_v - 0.4).abs() < 1e-12);

        // Noiseless SER and BER must be zero
        assert_eq!(metrics.ser, 0.0);
        assert_eq!(metrics.ber, 0.0);
    }

    #[test]
    fn test_asymmetric_pam4_rlm() {
        let samples_per_ui = 16;
        let dt = 1.953125e-12;
        let n_symbols = 64;
        let mut tx_bits = Vec::new();
        let mut waveform = Vec::new();

        for k in 0..n_symbols {
            let sym = k % 4;
            let (b0, b1) = match sym {
                0 => (0, 0),
                1 => (0, 1),
                2 => (1, 1),
                3 => (1, 0),
                _ => unreachable!(),
            };
            tx_bits.push(b0);
            tx_bits.push(b1);

            // Compress level 1: v1 = -0.1 instead of -0.2
            let v = match sym {
                0 => -0.6,
                1 => -0.1,
                2 => 0.2,
                3 => 0.6,
                _ => unreachable!(),
            };
            waveform.extend(std::iter::repeat_n(v, samples_per_ui));
        }

        let metrics = calculate_pam4_eye_metrics(
            &waveform,
            samples_per_ui,
            dt,
            &tx_bits,
            Some(&tx_bits),
        )
        .unwrap();

        // Delta V:
        // dv1 = -0.1 - (-0.6) = 0.5
        // dv2 = 0.2 - (-0.1) = 0.3
        // dv3 = 0.6 - 0.2 = 0.4
        // min(dv) = 0.3
        // total = 0.6 - (-0.6) = 1.2
        // RLM = 3 * 0.3 / 1.2 = 0.9 / 1.2 = 0.75
        assert!((metrics.rlm - 0.75).abs() < 1e-12);
    }

    #[test]
    fn test_pam4_gray_ser_ber_ratio() {
        let samples_per_ui = 16;
        let dt = 1.953125e-12;
        let n_symbols = 100;
        let mut tx_bits = Vec::new();
        let mut rx_bits = Vec::new();
        let mut waveform = Vec::new();

        for k in 0..n_symbols {
            let sym = k % 4;
            let (b0, b1) = match sym {
                0 => (0, 0),
                1 => (0, 1),
                2 => (1, 1),
                3 => (1, 0),
                _ => unreachable!(),
            };
            tx_bits.push(b0);
            tx_bits.push(b1);

            // Create 10 adjacent symbol errors (e.g. sym 1 received as 2)
            if k < 10 && sym == 1 {
                rx_bits.push(1);
                rx_bits.push(1); // 2 in Gray
            } else {
                rx_bits.push(b0);
                rx_bits.push(b1);
            }
            waveform.extend(std::iter::repeat_n(0.0, samples_per_ui));
        }

        let metrics = calculate_pam4_eye_metrics(
            &waveform,
            samples_per_ui,
            dt,
            &tx_bits,
            Some(&rx_bits),
        )
        .unwrap();

        // 3 symbol errors out of 100 symbols (k=1, 5, 9 where sym==1)
        assert_eq!(metrics.ser, 0.03);
        // Each adjacent error was 1 bit error -> 3 bit errors out of 200 bits
        assert_eq!(metrics.ber, 0.015);
        // Ratio BER / SER is exactly 0.5
        assert!((metrics.ber - metrics.ser / 2.0).abs() < 1e-12);
    }
}
