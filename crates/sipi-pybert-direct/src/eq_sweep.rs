#![forbid(unsafe_code)]

//! Constrained receiver/transmitter equalization parameter grid sweep and auto-tuning engine.
//!
//! This module evaluates a grid of CTLE peaking gain boost values and TX FFE tap
//! combinations under physical constraints (such as maximum normalized tap energy
//! sum: |c_pre| + |c_main| + |c_post| <= 1.0). It reuses the precomputed channel
//! impulse response across the sweep for fast execution, extracts eye opening and
//! RLM for each candidate, and ranks the configurations to find the optimum.
use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::{
    CtleConfigV1, FfeConfigV1, Hertz, ModulationV1, SimulationInputV1, simulate_native_v1,
};

#[derive(Debug, Error, PartialEq)]
pub enum EqSweepError {
    #[error("invalid sweep configuration: {0}")]
    InvalidConfig(String),
    #[error("sweep evaluation failed: {0}")]
    EvaluationFailed(String),
}

/// Configuration for equalization parameter sweep and optimization.
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct EqSweepConfigV1 {
    /// List of CTLE peaking gain boost values in dB to evaluate
    #[serde(default = "default_ctle_gains")]
    pub ctle_peaking_gain_db: Vec<f64>,
    /// List of TX FFE precursor tap weights (c_-1)
    #[serde(default = "default_tx_ffe_pre")]
    pub tx_ffe_precursor: Vec<f64>,
    /// List of TX FFE postcursor tap weights (c_+1)
    #[serde(default = "default_tx_ffe_post")]
    pub tx_ffe_postcursor: Vec<f64>,
    /// Maximum allowed sum of absolute tap weights: |c_pre| + |c_main| + |c_post| <= max
    #[serde(default = "default_max_tap_sum")]
    pub max_normalized_tap_sum: f64,
    /// Metric to maximize for ranking (defaults to "eye_height_worst_v")
    #[serde(default = "default_ranking_metric")]
    pub ranking_metric: String,
}

fn default_ctle_gains() -> Vec<f64> {
    vec![0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
}

fn default_tx_ffe_pre() -> Vec<f64> {
    vec![-0.15, -0.10, -0.05, 0.0]
}

fn default_tx_ffe_post() -> Vec<f64> {
    vec![-0.20, -0.10, 0.0]
}

fn default_max_tap_sum() -> f64 {
    1.0
}

fn default_ranking_metric() -> String {
    "eye_height_worst_v".into()
}

impl Default for EqSweepConfigV1 {
    fn default() -> Self {
        Self {
            ctle_peaking_gain_db: default_ctle_gains(),
            tx_ffe_precursor: default_tx_ffe_pre(),
            tx_ffe_postcursor: default_tx_ffe_post(),
            max_normalized_tap_sum: default_max_tap_sum(),
            ranking_metric: default_ranking_metric(),
        }
    }
}

/// Evaluation result for an individual equalization candidate.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EqCandidateResult {
    pub candidate_id: usize,
    pub ctle_boost_db: f64,
    pub tx_ffe_pre: f64,
    pub tx_ffe_main: f64,
    pub tx_ffe_post: f64,
    pub is_valid: bool,
    pub eye_height_worst_v: f64,
    pub eye_width_worst_ps: f64,
    pub rlm: Option<f64>,
    pub rank: usize,
}

/// Comprehensive report of the parameter sweep.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EqSweepReport {
    pub total_candidates: usize,
    pub valid_candidates: usize,
    pub optimal_candidate_id: usize,
    pub optimal_ctle_boost_db: f64,
    pub optimal_tx_ffe_weights: [f64; 3],
    pub optimal_eye_height_v: f64,
    pub optimal_eye_width_ps: f64,
    pub candidates: Vec<EqCandidateResult>,
}

/// Validate whether an FFE tap combination satisfies the physical energy/sum constraint.
pub fn is_ffe_tap_combination_valid(pre: f64, main: f64, post: f64, max_sum: f64) -> bool {
    let sum = pre.abs() + main.abs() + post.abs();
    sum <= max_sum + 1.0e-9 && main > 0.0 && main > pre.abs() + post.abs()
}

/// Compute the main cursor weight given pre and postcursor such that |c_pre| + c_main + |c_post| = 1.0
pub fn derive_main_cursor(pre: f64, post: f64) -> f64 {
    (1.0 - pre.abs() - post.abs()).max(0.0)
}

/// Rank candidates according to the requested metric in descending order.
pub fn rank_candidates(candidates: &mut [EqCandidateResult], metric: &str) {
    let is_rlm = metric.contains("rlm");
    candidates.sort_by(|a, b| {
        if !a.is_valid && b.is_valid {
            std::cmp::Ordering::Greater
        } else if a.is_valid && !b.is_valid {
            std::cmp::Ordering::Less
        } else if is_rlm {
            let rlm_a = a.rlm.unwrap_or(0.0);
            let rlm_b = b.rlm.unwrap_or(0.0);
            rlm_b.partial_cmp(&rlm_a).unwrap_or(std::cmp::Ordering::Equal)
        } else {
            b.eye_height_worst_v
                .partial_cmp(&a.eye_height_worst_v)
                .unwrap_or(std::cmp::Ordering::Equal)
        }
    });

    for (rank_idx, candidate) in candidates.iter_mut().enumerate() {
        candidate.rank = rank_idx + 1;
    }
}

/// Export sweep results to CSV format.
pub fn sweep_results_to_csv(candidates: &[EqCandidateResult]) -> String {
    let mut csv = String::from("rank,candidate_id,ctle_boost_db,tx_ffe_pre,tx_ffe_main,tx_ffe_post,eye_height_mv,eye_width_ps,rlm,valid\n");
    for c in candidates {
        let rlm_str = c.rlm.map(|r| format!("{r:.4}")).unwrap_or_else(|| "".into());
        csv.push_str(&format!(
            "{},{},{:.1},{:.3},{:.3},{:.3},{:.2},{:.2},{},{}\n",
            c.rank,
            c.candidate_id,
            c.ctle_boost_db,
            c.tx_ffe_pre,
            c.tx_ffe_main,
            c.tx_ffe_post,
            c.eye_height_worst_v * 1e3,
            c.eye_width_worst_ps,
            rlm_str,
            if c.is_valid { "valid" } else { "invalid" }
        ));
    }
    csv
}

/// Run the equalization parameter grid sweep over the provided base simulation input.
pub fn run_eq_sweep(
    base_input: &SimulationInputV1,
    config: &EqSweepConfigV1,
) -> Result<EqSweepReport, EqSweepError> {
    let mut candidates = Vec::new();
    let mut candidate_id = 0;

    let peaking_freq = base_input.timebase.data_rate.0 * 0.5; // Nyquist frequency

    for &boost in &config.ctle_peaking_gain_db {
        for &pre in &config.tx_ffe_precursor {
            for &post in &config.tx_ffe_postcursor {
                let main = derive_main_cursor(pre, post);
                let is_valid = is_ffe_tap_combination_valid(pre, main, post, config.max_normalized_tap_sum);

                if !is_valid {
                    candidates.push(EqCandidateResult {
                        candidate_id,
                        ctle_boost_db: boost,
                        tx_ffe_pre: pre,
                        tx_ffe_main: main,
                        tx_ffe_post: post,
                        is_valid: false,
                        eye_height_worst_v: 0.0,
                        eye_width_worst_ps: 0.0,
                        rlm: None,
                        rank: 0,
                    });
                    candidate_id += 1;
                    continue;
                }

                // Configure candidate input
                let mut sim_input = base_input.clone();
                sim_input.rx.native_ctle_enabled = boost > 0.0;
                sim_input.rx.ctle = (boost > 0.0).then_some(CtleConfigV1 {
                    bandwidth: Hertz(peaking_freq),
                    peak_frequency: Hertz(peaking_freq),
                    peak_magnitude_db: boost,
                    frequency_step_hz: None,
                    frequency_max_hz: None,
                    impulse_response_v_per_v: None,
                });

                sim_input.tx.ffe = FfeConfigV1 {
                    enabled: pre != 0.0 || post != 0.0,
                    weights: vec![pre, main, post],
                    cursor_position: 1,
                };

                let output = match simulate_native_v1(&sim_input) {
                    Ok(out) => out,
                    Err(e) => {
                        return Err(EqSweepError::EvaluationFailed(e.to_string()));
                    }
                };

                let is_pam4 = matches!(sim_input.modulation, ModulationV1::Pam4);
                let (eh, ew, rlm) = if is_pam4 {
                    (
                        output.metrics.get("pam4_eye_height_worst_v").copied().unwrap_or(0.0),
                        output.metrics.get("pam4_eye_width_worst_ps").copied().unwrap_or(0.0),
                        output.metrics.get("pam4_rlm").copied(),
                    )
                } else {
                    let eh = output
                        .metrics
                        .get("eye_height_v")
                        .copied()
                        .unwrap_or_else(|| {
                            if let (Some(rx_wave), Some(symbols)) = (
                                output.arrays.get("rx_output_v"),
                                output.arrays.get("symbols_v"),
                            ) {
                                let spui = sim_input.timebase.samples_per_ui as usize;
                                let mut best_lag = spui / 2;
                                let mut max_corr = f64::NEG_INFINITY;
                                let search_window = (rx_wave.len() / 2).min(1024);
                                for lag in 0..search_window {
                                    let mut corr = 0.0;
                                    let eval_len = (rx_wave.len() - lag).min(symbols.len() * spui);
                                    for idx in 0..eval_len {
                                        let sym_idx = idx / spui;
                                        corr += rx_wave[idx + lag] * symbols[sym_idx];
                                    }
                                    if corr > max_corr {
                                        max_corr = corr;
                                        best_lag = lag;
                                    }
                                }

                                let mut v0_sum = 0.0;
                                let mut v0_count = 0;
                                let mut v1_sum = 0.0;
                                let mut v1_count = 0;
                                for (k, &s) in symbols.iter().enumerate() {
                                    let idx = k * spui + best_lag;
                                    if idx < rx_wave.len() {
                                        if s > 0.0 {
                                            v1_sum += rx_wave[idx];
                                            v1_count += 1;
                                        } else {
                                            v0_sum += rx_wave[idx];
                                            v0_count += 1;
                                        }
                                    }
                                }
                                if v0_count > 0 && v1_count > 0 {
                                    (v1_sum / v1_count as f64 - v0_sum / v0_count as f64).max(0.0)
                                } else {
                                    0.0
                                }
                            } else {
                                0.0
                            }
                        });
                    let ew = output.metrics.get("eye_width_ps").copied().unwrap_or(0.0);
                    (eh, ew, None)
                };

                candidates.push(EqCandidateResult {
                    candidate_id,
                    ctle_boost_db: boost,
                    tx_ffe_pre: pre,
                    tx_ffe_main: main,
                    tx_ffe_post: post,
                    is_valid: true,
                    eye_height_worst_v: eh,
                    eye_width_worst_ps: ew,
                    rlm,
                    rank: 0,
                });
                candidate_id += 1;
            }
        }
    }

    rank_candidates(&mut candidates, &config.ranking_metric);

    let total_candidates = candidates.len();
    let valid_candidates = candidates.iter().filter(|c| c.is_valid).count();
    let best = candidates.first().cloned().unwrap_or(EqCandidateResult {
        candidate_id: 0,
        ctle_boost_db: 0.0,
        tx_ffe_pre: 0.0,
        tx_ffe_main: 1.0,
        tx_ffe_post: 0.0,
        is_valid: false,
        eye_height_worst_v: 0.0,
        eye_width_worst_ps: 0.0,
        rlm: None,
        rank: 1,
    });

    Ok(EqSweepReport {
        total_candidates,
        valid_candidates,
        optimal_candidate_id: best.candidate_id,
        optimal_ctle_boost_db: best.ctle_boost_db,
        optimal_tx_ffe_weights: [best.tx_ffe_pre, best.tx_ffe_main, best.tx_ffe_post],
        optimal_eye_height_v: best.eye_height_worst_v,
        optimal_eye_width_ps: best.eye_width_worst_ps,
        candidates,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tap_combination_constraint() {
        assert!(is_ffe_tap_combination_valid(-0.1, 0.8, -0.1, 1.0));
        assert!(is_ffe_tap_combination_valid(-0.05, 0.9, -0.05, 1.0));
        // Violates sum > 1.0
        assert!(!is_ffe_tap_combination_valid(-0.3, 0.6, -0.2, 1.0));
        // Violates main cursor dominance
        assert!(!is_ffe_tap_combination_valid(-0.4, 0.2, -0.4, 1.0));
    }

    #[test]
    fn test_candidate_ranking() {
        let mut candidates = vec![
            EqCandidateResult {
                candidate_id: 0,
                ctle_boost_db: 0.0,
                tx_ffe_pre: 0.0,
                tx_ffe_main: 1.0,
                tx_ffe_post: 0.0,
                is_valid: true,
                eye_height_worst_v: 0.05,
                eye_width_worst_ps: 10.0,
                rlm: Some(0.85),
                rank: 0,
            },
            EqCandidateResult {
                candidate_id: 1,
                ctle_boost_db: 6.0,
                tx_ffe_pre: -0.1,
                tx_ffe_main: 0.8,
                tx_ffe_post: -0.1,
                is_valid: true,
                eye_height_worst_v: 0.15,
                eye_width_worst_ps: 18.0,
                rlm: Some(0.95),
                rank: 0,
            },
            EqCandidateResult {
                candidate_id: 2,
                ctle_boost_db: 12.0,
                tx_ffe_pre: -0.2,
                tx_ffe_main: 0.6,
                tx_ffe_post: -0.2,
                is_valid: false,
                eye_height_worst_v: 0.0,
                eye_width_worst_ps: 0.0,
                rlm: None,
                rank: 0,
            },
        ];

        rank_candidates(&mut candidates, "eye_height_worst_v");
        assert_eq!(candidates[0].candidate_id, 1);
        assert_eq!(candidates[0].rank, 1);
        assert_eq!(candidates[1].candidate_id, 0);
        assert_eq!(candidates[1].rank, 2);
        assert_eq!(candidates[2].candidate_id, 2);
        assert_eq!(candidates[2].rank, 3);

        let csv = sweep_results_to_csv(&candidates);
        assert!(csv.contains("rank,candidate_id"));
        assert!(csv.contains("1,1,6.0,-0.100,0.800,-0.100,150.00,18.00,0.9500,valid"));
    }
}
