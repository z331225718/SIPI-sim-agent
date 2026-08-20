//! R4.80 fixed and floating DFE tap primitives (port of
//! `equalization/dfe.py`).
//!
//! Ported from agent-com (MIT source, P5-04k source map): tail-RSS
//! bound rewriting, elementwise clipping, floating bank location search
//! (`findbankloc` with zero-based indices), and DFE bank application
//! with the source's floor-based magnitude quantization.

/// Explicit scope policy of the DFE bank stage.
pub const DFE_POLICY_V1: &str = "sipi.p5-04k.dfe-v1.tail-rss-bank";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DfeErrorV1 {
    InvalidTailRssBounds,
    InvalidTailStartIndex,
    InvalidClipThresholds,
    InvalidBankSearchControls,
    BanksExceedWaveform,
    CandidateBankRange,
    InvalidBankWaveform,
    BankZeroCursor,
    InvalidBankCoefficientControls,
}

/// Port of `TailRssBounds`.
#[derive(Clone, Debug, PartialEq)]
pub struct TailRssBoundsV1 {
    tail_rss: f64,
    maximum: Vec<f64>,
    minimum: Vec<f64>,
}

impl TailRssBoundsV1 {
    pub fn tail_rss(&self) -> f64 {
        self.tail_rss
    }

    pub fn maximum(&self) -> &[f64] {
        &self.maximum
    }

    pub fn minimum(&self) -> &[f64] {
        &self.minimum
    }
}

/// Port of `DfeBankResult`.
#[derive(Clone, Debug, PartialEq)]
pub struct DfeBankResultV1 {
    residual: Vec<f64>,
    reference: Vec<f64>,
    coefficients: Vec<f64>,
}

impl DfeBankResultV1 {
    pub fn residual(&self) -> &[f64] {
        &self.residual
    }

    pub fn reference(&self) -> &[f64] {
        &self.reference
    }

    pub fn coefficients(&self) -> &[f64] {
        &self.coefficients
    }
}

/// Port of `apply_tail_rss_bounds` (zero-based tail start; None = source zero).
pub fn apply_tail_rss_bounds_v1(
    dfe_taps: &[f64],
    maximum: &[f64],
    minimum: &[f64],
    tail_start_index: Option<usize>,
    rss_max: f64,
) -> Result<TailRssBoundsV1, DfeErrorV1> {
    let taps: Vec<f64> = dfe_taps.to_vec();
    let mut upper: Vec<f64> = maximum.to_vec();
    let mut lower: Vec<f64> = minimum.to_vec();
    if upper.len() != taps.len()
        || lower.len() != taps.len()
        || lower.iter().zip(upper.iter()).any(|(low, high)| low > high)
        || rss_max < 0.0
    {
        return Err(DfeErrorV1::InvalidTailRssBounds);
    }
    let Some(tail_start) = tail_start_index else {
        return Ok(TailRssBoundsV1 {
            tail_rss: 0.0,
            maximum: upper,
            minimum: lower,
        });
    };
    if tail_start >= taps.len() {
        return Err(DfeErrorV1::InvalidTailStartIndex);
    }
    let tail = &taps[tail_start..];
    let rss = tail.iter().map(|value| value * value).sum::<f64>().sqrt();
    if rss != 0.0 && rss >= rss_max {
        let magnitude: Vec<f64> = tail
            .iter()
            .map(|value| rss_max.min(rss) * value.abs() / rss)
            .collect();
        for (index, value) in magnitude.iter().enumerate() {
            upper[tail_start + index] = *value;
            lower[tail_start + index] = -*value;
        }
    }
    Ok(TailRssBoundsV1 {
        tail_rss: rss,
        maximum: upper,
        minimum: lower,
    })
}

/// Port of `clip_dfe` (flat surface; row/column orientation is
/// equivalent in the product API).
pub fn clip_dfe_v1(values: &[f64], maximum: &[f64], minimum: &[f64]) -> Result<Vec<f64>, DfeErrorV1> {
    let taps: Vec<f64> = values.to_vec();
    let upper: Vec<f64> = maximum.to_vec();
    let lower: Vec<f64> = minimum.to_vec();
    if upper.len() != taps.len() || lower.len() != taps.len() || lower.iter().zip(upper.iter()).any(|(low, high)| low > high) {
        return Err(DfeErrorV1::InvalidClipThresholds);
    }
    Ok(taps
        .iter()
        .zip(upper.iter())
        .zip(lower.iter())
        .map(|((value, high), low)| (*high).min((*low).max(*value)))
        .collect())
}

fn sliding_energy(values: &[f64], width: usize) -> Vec<f64> {
    // np.convolve(values^2, ones(width), 'valid')
    let squares: Vec<f64> = values.iter().map(|value| value * value).collect();
    let count = squares.len().saturating_sub(width).saturating_add(1);
    (0..count)
        .map(|index| squares[index..index + width].iter().sum())
        .collect()
}

fn preceding_overlap(start: usize, width: usize) -> Vec<usize> {
    let low = start.saturating_sub(width - 1);
    (low..start).collect()
}

fn invalidate_preceding_overlap(energy: &mut [f64], start: usize, width: usize, invalid: f64) {
    for index in preceding_overlap(start, width) {
        if index < energy.len() {
            energy[index] = invalid;
        }
    }
}

fn stable_order_descending(energy: &[f64]) -> Vec<usize> {
    let mut order: Vec<usize> = (0..energy.len()).collect();
    order.sort_by(|a, b| energy[*b].partial_cmp(&energy[*a]).unwrap_or(std::cmp::Ordering::Equal));
    order
}

/// Port of `find_dfe_bank_locations` (zero-based waveform indices).
pub fn find_dfe_bank_locations_v1(
    hisi: &[f64],
    start_index: usize,
    end_index: usize,
    taps_per_bank: usize,
    cursor: f64,
    coefficient_limit: f64,
    bank_count: usize,
) -> Result<Vec<i64>, DfeErrorV1> {
    let values: Vec<f64> = hisi.to_vec();
    if end_index < start_index
        || end_index >= values.len()
        || taps_per_bank < 1
        || end_index - start_index + 1 < taps_per_bank
        || coefficient_limit < 0.0
    {
        return Err(DfeErrorV1::InvalidBankSearchControls);
    }
    if bank_count == 0 {
        return Ok(Vec::new());
    }
    let window: Vec<f64> = values[start_index..=end_index].iter().map(|value| value.abs()).collect();
    let mut reduced: Vec<f64> = window
        .iter()
        .map(|value| (0.0_f64).max(value - coefficient_limit * cursor))
        .collect();
    if cursor < 0.0 {
        reduced = vec![0.0; reduced.len()];
    }
    let mut energy: Vec<f64> = sliding_energy(&window, taps_per_bank)
        .iter()
        .zip(sliding_energy(&reduced, taps_per_bank).iter())
        .map(|(left, right)| left - right)
        .collect();
    if bank_count * taps_per_bank > window.len() {
        return Err(DfeErrorV1::BanksExceedWaveform);
    }
    let invalid = f64::NEG_INFINITY;
    let mut selected = vec![-1i64; bank_count * taps_per_bank];
    let ordered_len = (bank_count - 1) * taps_per_bank + 1;
    let mut next_bank: Option<usize> = None;
    for bank in 0..bank_count {
        let order = stable_order_descending(&energy);
        if bank == 0 {
            let prefix = &order[..ordered_len.min(order.len())];
            let mut sorted = prefix.to_vec();
            sorted.sort_unstable();
            let expected: Vec<usize> = (0..ordered_len).collect();
            if sorted == expected {
                return Ok((0..bank_count * taps_per_bank)
                    .map(|index| (index as i64) + start_index as i64)
                    .collect());
            }
        }
        if let Some(bank_start) = next_bank.take() {
            let candidate: Vec<usize> = (bank_start..bank_start + taps_per_bank).collect();
            for (offset, index) in candidate.iter().enumerate() {
                selected[bank * taps_per_bank + offset] = *index as i64;
            }
            let invalid_indices: Vec<usize> = candidate.iter().copied().filter(|index| *index < energy.len()).collect();
            for index in invalid_indices {
                energy[index] = invalid;
            }
            invalidate_preceding_overlap(&mut energy, candidate[0], taps_per_bank, invalid);
            continue;
        }
        let candidate: Vec<usize> = (order[0]..order[0] + taps_per_bank).collect();
        if *candidate.last().expect("candidate") >= window.len() {
            return Err(DfeErrorV1::CandidateBankRange);
        }
        if bank == bank_count - 1 {
            for (offset, index) in candidate.iter().enumerate() {
                selected[bank * taps_per_bank + offset] = *index as i64;
            }
            break;
        }
        let mut loops = 0usize;
        let mut bad: Vec<usize> = Vec::new();
        let mut candidate = candidate;
        loop {
            if loops > energy.len() {
                break;
            }
            bad = preceding_overlap(candidate[0], taps_per_bank);
            if !bad.is_empty() {
                bad.retain(|index| !selected.contains(&(*index as i64)));
            }
            let good = candidate[0].saturating_sub(taps_per_bank);
            if !bad.is_empty() {
                let order = stable_order_descending(&energy);
                // Python: iterate order; break at good or at first value not in check.
                let check: Vec<usize> = {
                    let mut combined = bad.clone();
                    combined.extend_from_slice(&candidate);
                    combined
                };
                let mut found_good = false;
                let mut position = 0usize;
                for (index, value) in order.iter().enumerate() {
                    if *value == good {
                        found_good = true;
                        position = index;
                        break;
                    }
                    if !check.contains(value) {
                        position = index;
                        break;
                    }
                }
                let bad_positions: Vec<usize> = bad
                    .iter()
                    .map(|value| order.iter().position(|entry| entry == value).expect("position"))
                    .collect();
                if !found_good && bad_positions.iter().min().copied().unwrap_or(usize::MAX) < position {
                    if candidate[0] < energy.len() {
                        energy[candidate[0]] = invalid;
                    }
                    candidate = (order[1]..order[1] + taps_per_bank).collect();
                    if *candidate.last().expect("candidate") >= window.len() {
                        return Err(DfeErrorV1::CandidateBankRange);
                    }
                    loops += 1;
                    continue;
                }
                if found_good {
                    next_bank = Some(good);
                }
            }
            break;
        }
        let invalid_indices: Vec<usize> = candidate.iter().copied().filter(|index| *index < energy.len()).collect();
        for index in invalid_indices {
            energy[index] = invalid;
        }
        for (offset, index) in candidate.iter().enumerate() {
            selected[bank * taps_per_bank + offset] = *index as i64;
        }
        if !bad.is_empty() {
            for index in bad {
                if index < energy.len() {
                    energy[index] = invalid;
                }
            }
        }
    }
    let mut result: Vec<i64> = selected.iter().map(|value| value + start_index as i64).collect();
    result.sort_unstable();
    Ok(result)
}

/// Port of `apply_dfe_bank` (zero-based start; floor-magnitude quantizer).
pub fn apply_dfe_bank_v1(
    hisi: &[f64],
    hisi_ref: &[f64],
    start_index: usize,
    tap_count: usize,
    cursor: f64,
    coefficient_limit: f64,
    quantization_step: f64,
) -> Result<DfeBankResultV1, DfeErrorV1> {
    let mut residual: Vec<f64> = hisi.to_vec();
    let mut reference: Vec<f64> = hisi_ref.to_vec();
    if residual.len() != reference.len() || start_index + tap_count > residual.len() || cursor == 0.0 {
        return Err(DfeErrorV1::InvalidBankWaveform);
    }
    if coefficient_limit < 0.0 || quantization_step < 0.0 {
        return Err(DfeErrorV1::InvalidBankCoefficientControls);
    }
    let values: Vec<f64> = residual[start_index..start_index + tap_count].to_vec();
    let quantized: Vec<f64> = if quantization_step != 0.0 {
        values
            .iter()
            .map(|value| {
                let sign = if *value > 0.0 { 1.0 } else if *value < 0.0 { -1.0 } else { 0.0 };
                ((value / cursor).abs() / quantization_step).floor() * quantization_step * sign * cursor
            })
            .collect()
    } else {
        values.clone()
    };
    let coefficients: Vec<f64> = quantized
        .iter()
        .map(|value| {
            let sign = if *value > 0.0 { 1.0 } else if *value < 0.0 { -1.0 } else { 0.0 };
            (value / cursor).abs().min(coefficient_limit) * sign
        })
        .collect();
    for (offset, coefficient) in coefficients.iter().enumerate() {
        residual[start_index + offset] -= cursor * coefficient;
        reference[start_index + offset] = 0.0;
    }
    Ok(DfeBankResultV1 {
        residual,
        reference,
        coefficients,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tail_rss_rewrites_bounds_when_exceeding() {
        let taps = vec![0.1, 0.2, 0.3, 0.4];
        let maximum = vec![0.5, 0.5, 0.5, 0.5];
        let minimum = vec![-0.5, -0.5, -0.5, -0.5];
        let bounds = apply_tail_rss_bounds_v1(&taps, &maximum, &minimum, Some(2), 0.25)
            .expect("bounds");
        // tail = [0.3, 0.4], rss = 0.5 >= 0.25 -> magnitude = 0.25 * |tail| / 0.5
        assert!((bounds.tail_rss() - 0.5).abs() < 1e-12);
        assert!((bounds.maximum()[2] - 0.15).abs() < 1e-12);
        assert!((bounds.maximum()[3] - 0.2).abs() < 1e-12);
        assert!((bounds.minimum()[3] + 0.2).abs() < 1e-12);
        let none = apply_tail_rss_bounds_v1(&taps, &maximum, &minimum, None, 0.25)
            .expect("bounds");
        assert_eq!(none.tail_rss(), 0.0);
        assert_eq!(none.maximum(), &maximum);
    }

    #[test]
    fn clip_elementwise() {
        let clipped = clip_dfe_v1(&[0.8, -0.8, 0.0], &[0.5, 0.5, 0.5], &[-0.2, -0.2, -0.2])
            .expect("clipped");
        assert_eq!(clipped, vec![0.5, -0.2, 0.0]);
        assert!(clip_dfe_v1(&[1.0], &[0.5], &[0.6]).is_err());
    }

    #[test]
    fn bank_locations_basic() {
        // Energy concentrated at the first bank positions.
        let hisi = vec![1.0, 1.0, 0.1, 0.1, 1.0, 1.0, 0.05, 0.05];
        let locations = find_dfe_bank_locations_v1(&hisi, 0, 7, 2, 1.0, 0.0, 2)
            .expect("locations");
        assert_eq!(locations.len(), 4);
        assert!(locations.iter().all(|index| *index >= 0));
    }

    #[test]
    fn bank_apply_quantized() {
        let hisi = vec![0.1, 0.05, 0.2];
        let hisi_ref = vec![0.0, 0.0, 0.0];
        let result = apply_dfe_bank_v1(&hisi, &hisi_ref, 0, 3, 0.1, 1.0, 0.5)
            .expect("bank");
        // quantized = floor(|v/0.1|/0.5)*0.5*sign*0.1
        assert_eq!(result.coefficients().len(), 3);
        assert_eq!(result.residual().len(), 3);
        assert_eq!(result.reference(), &[0.0, 0.0, 0.0]);
        assert!(apply_dfe_bank_v1(&hisi, &hisi_ref, 0, 3, 0.0, 1.0, 0.5).is_err());
        assert!(apply_dfe_bank_v1(&hisi, &hisi_ref, 2, 3, 0.1, 1.0, 0.5).is_err());
    }

    #[test]
    fn controls_fail_closed() {
        assert!(apply_tail_rss_bounds_v1(&[1.0], &[0.5], &[-0.5], Some(5), 0.1).is_err());
        assert!(apply_tail_rss_bounds_v1(&[1.0], &[0.5], &[-0.5], Some(0), -1.0).is_err());
        assert!(find_dfe_bank_locations_v1(&[1.0], 0, 0, 2, 1.0, 0.0, 1).is_err());
        assert!(find_dfe_bank_locations_v1(&[1.0; 4], 0, 3, 2, 1.0, 0.0, 3).is_err());
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(DFE_POLICY_V1, "sipi.p5-04k.dfe-v1.tail-rss-bank");
    }
}