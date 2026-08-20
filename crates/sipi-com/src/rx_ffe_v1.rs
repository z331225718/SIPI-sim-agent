//! R4.80 receiver FFE filtering primitive (port of
//! `equalization/rx_ffe.py`, fixed-tap branch).
//!
//! Ported from agent-com (MIT source, P5-04l source map): UI-spaced
//! circular-shift FIR application and the fixed-tap force solve
//! (partial-pivot LU, unity-cursor normalization, floor-magnitude tap
//! quantization). The floating-RxFFE bank branch remains a separate
//! sub-slice.

/// Explicit scope policy of the RX FFE stage.
pub const RX_FFE_POLICY_V1: &str = "sipi.p5-04l.rx-ffe-v1.apply-force-fixed";

/// Explicit scope policy of the floating RxFFE sub-slice.
pub const FLOATING_RX_FFE_POLICY_V1: &str =
    "sipi.p5-04m.rx-ffe-v1.floating-bank-force";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RxFfeErrorV1 {
    InvalidWaveformOrTaps,
    PrecursorNotCursor,
    InvalidControls,
    SingularSolve,
    ZeroCursorNormalization,
    InvalidFloatingControls,
    InvalidBankControls,
    BankRange,
}

/// Port of `ForcedRxFfeResult`.
#[derive(Clone, Debug, PartialEq)]
pub struct ForcedRxFfeResultV1 {
    taps: Vec<f64>,
    filtered: Option<Vec<f64>>,
    matrix: Vec<Vec<f64>>,
}

impl ForcedRxFfeResultV1 {
    pub fn taps(&self) -> &[f64] {
        &self.taps
    }

    pub fn filtered(&self) -> Option<&[f64]> {
        self.filtered.as_deref()
    }

    pub fn matrix(&self) -> &[Vec<f64>] {
        &self.matrix
    }
}

/// Port of `FFE`: sum UI-spaced circular shifts, including wraparound.
pub fn apply_rx_ffe_v1(
    taps: &[f64],
    precursor_count: usize,
    samples_per_ui: usize,
    waveform: &[f64],
) -> Result<Vec<f64>, RxFfeErrorV1> {
    let coefficients: Vec<f64> = taps.to_vec();
    let values: Vec<f64> = waveform.to_vec();
    if coefficients.is_empty() || values.is_empty() || samples_per_ui < 1 {
        return Err(RxFfeErrorV1::InvalidWaveformOrTaps);
    }
    if precursor_count >= coefficients.len() {
        return Err(RxFfeErrorV1::PrecursorNotCursor);
    }
    let size = values.len();
    let mut output = vec![0.0_f64; size];
    for (index, coefficient) in coefficients.iter().enumerate() {
        if *coefficient == 0.0 {
            continue;
        }
        let shift = (index as i64 - precursor_count as i64) * samples_per_ui as i64;
        for position in 0..size {
            // np.roll(values, shift)[i] = values[(i - shift) mod size]
            let source = ((position as i64 - shift).rem_euclid(size as i64)) as usize;
            output[position] += coefficient * values[source];
        }
    }
    Ok(output)
}

/// Partial-pivot LU solve (A x = b) matching np.linalg.solve's
/// non-singular path; a zero pivot after pivoting is singular.
fn lu_solve(matrix: &[Vec<f64>], rhs: &[f64]) -> Result<Vec<f64>, ()> {
    let n = matrix.len();
    let mut a: Vec<Vec<f64>> = matrix.to_vec();
    let mut b: Vec<f64> = rhs.to_vec();
    for column in 0..n {
        let mut pivot = column;
        for row in column + 1..n {
            if a[row][column].abs() > a[pivot][column].abs() {
                pivot = row;
            }
        }
        if a[pivot][column] == 0.0 {
            return Err(());
        }
        a.swap(column, pivot);
        b.swap(column, pivot);
        for row in column + 1..n {
            let factor = a[row][column] / a[column][column];
            a[row][column] = factor;
            for entry in column + 1..n {
                a[row][entry] -= factor * a[column][entry];
            }
        }
    }
    for row in 1..n {
        for column in 0..row {
            b[row] -= a[row][column] * b[column];
        }
    }
    for row in (0..n).rev() {
        for column in row + 1..n {
            b[row] -= a[row][column] * b[column];
        }
        b[row] /= a[row][row];
    }
    Ok(b)
}

fn floor_quantize(values: &[f64], step: f64) -> Vec<f64> {
    values
        .iter()
        .map(|value| {
            let sign = if *value > 0.0 { 1.0 } else if *value < 0.0 { -1.0 } else { 0.0 };
            (value / step).abs().floor() * sign * step
        })
        .collect()
}

/// Port of `force_rx_ffe` (fixed-tap branch; Wiener path excluded).
#[allow(clippy::too_many_arguments)]
pub fn force_rx_ffe_v1(
    waveform: &[f64],
    cursor_index: usize,
    precursor_count: usize,
    postcursor_count: usize,
    samples_per_ui: usize,
    dfe_first_max: f64,
    unity_cursor: bool,
    tap_step: f64,
    return_filtered: bool,
) -> Result<ForcedRxFfeResultV1, RxFfeErrorV1> {
    let values: Vec<f64> = waveform.to_vec();
    if values.is_empty()
        || cursor_index >= values.len()
        || samples_per_ui < 1
        || dfe_first_max < 0.0
        || tap_step < 0.0
    {
        return Err(RxFfeErrorV1::InvalidControls);
    }
    let count = precursor_count + postcursor_count + 1;
    let mut matrix = vec![vec![0.0_f64; count]; count];
    for output_tap in 0..count {
        for input_tap in 0..count {
            let index = cursor_index as i64 + (output_tap as i64 - input_tap as i64) * samples_per_ui as i64;
            if 0 <= index && index < values.len() as i64 {
                matrix[output_tap][input_tap] = values[index as usize];
            }
        }
    }
    let mut forcing = vec![0.0_f64; count];
    forcing[precursor_count] = values[cursor_index];
    if dfe_first_max != 0.0 && postcursor_count > 0 {
        let postcursor_index = cursor_index + samples_per_ui;
        let postcursor = if postcursor_index < values.len() {
            values[postcursor_index]
        } else {
            0.0
        };
        let sign = if postcursor > 0.0 { 1.0 } else if postcursor < 0.0 { -1.0 } else { 0.0 };
        forcing[precursor_count + 1] =
            (dfe_first_max * forcing[precursor_count]).min(postcursor.abs()) * sign;
    }
    let mut taps = lu_solve(&matrix, &forcing).map_err(|_| RxFfeErrorV1::SingularSolve)?;
    if unity_cursor {
        if taps[precursor_count] == 0.0 {
            return Err(RxFfeErrorV1::ZeroCursorNormalization);
        }
        let cursor = taps[precursor_count];
        for value in taps.iter_mut() {
            *value /= cursor;
        }
    }
    if tap_step != 0.0 {
        taps = floor_quantize(&taps, tap_step);
    }
    let filtered = if return_filtered {
        Some(apply_rx_ffe_v1(&taps, precursor_count, samples_per_ui, &values)?)
    } else {
        None
    };
    Ok(ForcedRxFfeResultV1 {
        taps,
        filtered,
        matrix,
    })
}

/// Port of `_r480_rxffe_floating_locations`: the RxFFE-specific
/// findbankloc with one-based candidate coordinates and the source's
/// adjacent-bank heuristic. Returns zero-based C-vector offsets.
fn rxffe_floating_locations_v1(
    values: &[f64],
    start_one_based: usize,
    end_one_based: usize,
    taps_per_bank: usize,
    cursor: f64,
    coefficient_limit: f64,
    bank_count: usize,
) -> Result<Vec<i64>, RxFfeErrorV1> {
    let source: Vec<f64> = values.to_vec();
    let length = end_one_based - start_one_based + 1;
    if start_one_based < 1
        || end_one_based < start_one_based
        || end_one_based > source.len()
        || taps_per_bank < 1
        || bank_count < 1
        || coefficient_limit < 0.0
        || length < taps_per_bank
        || bank_count * taps_per_bank > length
    {
        return Err(RxFfeErrorV1::InvalidBankControls);
    }
    let h0: Vec<f64> = source[start_one_based - 1..end_one_based]
        .iter()
        .map(|value| value.abs())
        .collect();
    let mut h1: Vec<f64> = h0
        .iter()
        .map(|value| (0.0_f64).max(value - coefficient_limit * cursor))
        .collect();
    if cursor < 0.0 {
        h1 = vec![0.0; h1.len()];
    }
    let window_count = length - taps_per_bank + 1;
    let mut h0n = vec![0.0_f64; window_count];
    let mut h1n = vec![0.0_f64; window_count];
    for offset in 0..taps_per_bank {
        for index in 0..window_count {
            let h0v = h0[offset + index];
            let h1v = h1[offset + index];
            h0n[index] += h0v * h0v;
            h1n[index] += h1v * h1v;
        }
    }
    let mut energy: Vec<f64> = h0n.iter().zip(h1n.iter()).map(|(a, b)| a - b).collect();
    let mut selected_relative = vec![0i64; taps_per_bank * bank_count];
    let ordered_set: Vec<i64> = (1..(bank_count - 1) * taps_per_bank + 2).map(|v| v as i64).collect();
    let mut next_bank: Option<usize> = None;
    let negative_infinity = f64::NEG_INFINITY;
    for bank in 1..=bank_count {
        let mut order: Vec<usize> = (0..energy.len()).collect();
        order.sort_by(|a, b| energy[*b].partial_cmp(&energy[*a]).unwrap_or(std::cmp::Ordering::Equal));
        let order_one: Vec<i64> = order.iter().map(|value| *value as i64 + 1).collect();
        if bank == 1 {
            let mut prefix: Vec<i64> = order_one.iter().take(ordered_set.len()).copied().collect();
            prefix.sort_unstable();
            if prefix == ordered_set {
                return Ok((1..=bank_count * taps_per_bank)
                    .map(|value| value as i64 + start_one_based as i64 - 2)
                    .collect());
            }
        }
        if let Some(next) = next_bank.take() {
            let new_bank: Vec<usize> = (next..next + taps_per_bank).collect();
            for (offset, value) in new_bank.iter().enumerate() {
                selected_relative[(bank - 1) * taps_per_bank + offset] = *value as i64;
            }
            for value in new_bank.iter() {
                // The source writes energy[new_bank - 1] without bounds
                // protection (unlike the DFE variant) and raises
                // IndexError; the product rejects the same inputs.
                if *value > energy.len() {
                    return Err(RxFfeErrorV1::BankRange);
                }
                energy[value - 1] = negative_infinity;
            }
            let bad_end = new_bank[0] - 1;
            if bad_end > 0 {
                let bad_start = new_bank[0] + 1 - taps_per_bank;
                let start = bad_start.max(1);
                for value in start..=bad_end {
                    energy[value - 1] = negative_infinity;
                }
            }
            continue;
        }
        let mut new_bank: Vec<usize> = (order_one[0] as usize..order_one[0] as usize + taps_per_bank).collect();
        if *new_bank.last().expect("new bank") > length {
            return Err(RxFfeErrorV1::BankRange);
        }
        if bank == bank_count {
            for (offset, value) in new_bank.iter().enumerate() {
                selected_relative[(bank - 1) * taps_per_bank + offset] = *value as i64;
            }
            break;
        }
        let mut first_time = true;
        let mut loops = 0usize;
        let mut bad: Vec<i64> = Vec::new();
        loop {
            if loops > energy.len() {
                break;
            }
            let bad_end = new_bank[0] as i64 - 1;
            bad = if bad_end <= 0 {
                Vec::new()
            } else {
                let bad_start = (new_bank[0] as i64 + 1 - taps_per_bank as i64).max(1);
                (bad_start..=bad_end).collect()
            };
            if !bad.is_empty() {
                bad.retain(|value| !selected_relative.contains(value));
            }
            let good = new_bank[0] as i64 - taps_per_bank as i64;
            if !bad.is_empty() {
                let order_current: Vec<i64> = if first_time {
                    order_one.clone()
                } else {
                    let mut reordered: Vec<usize> = (0..energy.len()).collect();
                    reordered.sort_by(|a, b| energy[*b].partial_cmp(&energy[*a]).unwrap_or(std::cmp::Ordering::Equal));
                    reordered.iter().map(|value| *value as i64 + 1).collect()
                };
                first_time = false;
                let mut check: Vec<i64> = bad.clone();
                check.extend(new_bank.iter().map(|value| *value as i64));
                let bad_positions: Vec<i64> = bad
                    .iter()
                    .map(|item| {
                        order_current.iter().position(|entry| entry == item).expect("in order") as i64 + 1
                    })
                    .collect();
                let mut found_good = false;
                let mut position = 0i64;
                for (index, item) in order_current.iter().enumerate() {
                    position = index as i64 + 1;
                    if *item == good {
                        found_good = true;
                        break;
                    }
                    if !check.contains(item) {
                        break;
                    }
                }
                if !found_good && bad_positions.iter().min().copied().unwrap_or(i64::MAX) < position {
                    if new_bank[0] > energy.len() {
                        return Err(RxFfeErrorV1::BankRange);
                    }
                    energy[new_bank[0] - 1] = negative_infinity;
                    new_bank = (order_current[1] as usize..order_current[1] as usize + taps_per_bank).collect();
                    if *new_bank.last().expect("new bank") > length {
                        return Err(RxFfeErrorV1::BankRange);
                    }
                    loops += 1;
                    continue;
                }
                if found_good {
                    next_bank = Some(good.max(1) as usize);
                }
            }
            loops += 1;
            break;
        }
        for value in new_bank.iter() {
            if *value > energy.len() {
                return Err(RxFfeErrorV1::BankRange);
            }
            energy[value - 1] = negative_infinity;
        }
        for (offset, value) in new_bank.iter().enumerate() {
            selected_relative[(bank - 1) * taps_per_bank + offset] = *value as i64;
        }
        if !bad.is_empty() {
            for value in bad {
                if value >= 1 && value <= energy.len() as i64 {
                    energy[value as usize - 1] = negative_infinity;
                }
            }
        }
    }
    Ok(selected_relative
        .iter()
        .map(|value| value + start_one_based as i64 - 2)
        .collect())
}

/// Port of `force_floating_rx_ffe` (floating RxFFE bank branch).
pub fn force_floating_rx_ffe_v1(
    waveform: &[f64],
    cursor_index: usize,
    precursor_count: usize,
    fixed_postcursor_count: usize,
    maximum_postcursor_count: usize,
    samples_per_ui: usize,
    dfe_first_max: f64,
    unity_cursor: bool,
    tap_step: f64,
    floating_start: usize,
    taps_per_bank: usize,
    bank_count: usize,
    coefficient_limit: f64,
    selection: &str,
    return_filtered: bool,
) -> Result<(ForcedRxFfeResultV1, Vec<i64>), RxFfeErrorV1> {
    let values: Vec<f64> = waveform.to_vec();
    if values.is_empty()
        || cursor_index >= values.len()
        || samples_per_ui < 1
        || dfe_first_max < 0.0
        || tap_step < 0.0
        || floating_start < 1
        || taps_per_bank < 1
        || bank_count < 1
        || coefficient_limit < 0.0
        || maximum_postcursor_count <= fixed_postcursor_count
    {
        return Err(RxFfeErrorV1::InvalidFloatingControls);
    }
    let count = precursor_count + maximum_postcursor_count + 1;
    let mut matrix = vec![vec![0.0_f64; count]; count];
    for output_tap in 0..count {
        for input_tap in 0..count {
            let index = cursor_index as i64 + (output_tap as i64 - input_tap as i64) * samples_per_ui as i64;
            if 0 <= index && index < values.len() as i64 {
                matrix[output_tap][input_tap] = values[index as usize];
            }
        }
    }
    let mut forcing = vec![0.0_f64; count];
    forcing[precursor_count] = values[cursor_index];
    if dfe_first_max != 0.0 {
        let postcursor_index = cursor_index + samples_per_ui;
        let postcursor = if postcursor_index < values.len() {
            values[postcursor_index]
        } else {
            0.0
        };
        let sign = if postcursor > 0.0 { 1.0 } else if postcursor < 0.0 { -1.0 } else { 0.0 };
        forcing[precursor_count + 1] =
            (dfe_first_max * forcing[precursor_count]).min(postcursor.abs()) * sign;
    }
    let raw = lu_solve(&matrix, &forcing).map_err(|_| RxFfeErrorV1::SingularSolve)?;
    let selector = selection.to_lowercase();
    let basis: Vec<f64> = if selector == "taps" {
        raw.clone()
    } else {
        (0..count).map(|row| matrix[row][precursor_count]).collect()
    };
    let selected = rxffe_floating_locations_v1(
        &basis,
        floating_start,
        maximum_postcursor_count,
        taps_per_bank,
        raw[precursor_count],
        coefficient_limit,
        bank_count,
    )?;
    let mut taps = raw.clone();
    if unity_cursor {
        if raw[precursor_count] == 0.0 {
            return Err(RxFfeErrorV1::ZeroCursorNormalization);
        }
        let cursor = raw[precursor_count];
        for value in taps.iter_mut() {
            *value /= cursor;
        }
    }
    if tap_step != 0.0 {
        taps = floor_quantize(&taps, tap_step);
    }
    let fixed_count = precursor_count + fixed_postcursor_count + 1;
    let mut retained = vec![0.0_f64; taps.len()];
    retained[..fixed_count].copy_from_slice(&taps[..fixed_count]);
    let tap_locations: Vec<usize> = selected
        .iter()
        .map(|value| precursor_count + *value as usize + 1)
        .collect();
    for location in &tap_locations {
        if *location >= retained.len() {
            return Err(RxFfeErrorV1::BankRange);
        }
    }
    for location in tap_locations {
        retained[location] = taps[location];
    }
    let filtered = if return_filtered {
        Some(apply_rx_ffe_v1(&retained, precursor_count, samples_per_ui, &values)?)
    } else {
        None
    };
    let locations_one_based: Vec<i64> = selected.iter().map(|value| value + 1).collect();
    Ok((
        ForcedRxFfeResultV1 {
            taps: retained,
            filtered,
            matrix,
        },
        locations_one_based,
    ))
}
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn apply_rx_ffe_circular_shifts() {
        let waveform = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0];
        let taps = vec![0.5, 1.0, -0.25];
        let filtered = apply_rx_ffe_v1(&taps, 1, 4, &waveform).expect("filtered");
        assert_eq!(filtered.len(), 8);
        // shift 0: +1.0 * w; shift -4: 0.5 * roll(+4); shift +4: -0.25 * roll(-4)
        let expected: Vec<f64> = (0..8)
            .map(|i| {
                1.0 * waveform[i]
                    + 0.5 * waveform[(i + 4) % 8]
                    + -0.25 * waveform[(i + 8 - 4) % 8]
            })
            .collect();
        for (a, b) in filtered.iter().zip(expected.iter()) {
            assert!((a - b).abs() < 1e-12);
        }
        assert!(apply_rx_ffe_v1(&taps, 3, 4, &waveform).is_err());
    }

    #[test]
    fn force_rx_ffe_solves_and_filters() {
        let waveform: Vec<f64> = (0..32)
            .map(|index| {
                let i = index as f64;
                (-(i - 16.0) * (i - 16.0) / 80.0).exp() * (i * 0.5).sin()
            })
            .collect();
        let result = force_rx_ffe_v1(&waveform, 16, 1, 2, 4, 0.0, false, 0.0, true)
            .expect("forced");
        assert_eq!(result.taps().len(), 4);
        assert!(result.filtered().is_some());
        // matrix @ taps == forcing
        let forcing0 = waveform[16];
        let residual: f64 = (0..4)
            .map(|row| {
                let dot: f64 = (0..4)
                    .map(|column| result.matrix()[row][column] * result.taps()[column])
                    .sum();
                (dot - if row == 1 { forcing0 } else { 0.0 }).abs()
            })
            .sum();
        assert!(residual < 1e-9);
    }

    #[test]
    fn force_unity_cursor_and_quantization() {
        let waveform: Vec<f64> = (0..32)
            .map(|index| {
                let i = index as f64;
                (-(i - 16.0) * (i - 16.0) / 80.0).exp()
            })
            .collect();
        let unity = force_rx_ffe_v1(&waveform, 16, 1, 1, 4, 0.0, true, 0.0, false)
            .expect("unity");
        assert!((unity.taps()[1] - 1.0).abs() < 1e-12);
        let quantized = force_rx_ffe_v1(&waveform, 16, 1, 1, 4, 0.0, true, 0.25, false)
            .expect("quantized");
        assert!(quantized.taps().iter().all(|value| (value / 0.25).fract().abs() < 1e-9));
    }

    #[test]
    fn singular_solve_fails_closed() {
        let waveform = vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        // All-zero matrix rows -> singular.
        assert_eq!(
            force_rx_ffe_v1(&waveform, 2, 1, 1, 2, 0.0, false, 0.0, false).unwrap_err(),
            RxFfeErrorV1::SingularSolve,
        );
    }

    #[test]
    fn controls_fail_closed() {
        let waveform = vec![1.0, 2.0, 3.0, 4.0];
        assert!(force_rx_ffe_v1(&waveform, 9, 1, 1, 2, 0.0, false, 0.0, false).is_err());
        assert!(force_rx_ffe_v1(&waveform, 0, 1, 1, 2, -1.0, false, 0.0, false).is_err());
    }

    #[test]
    fn floating_locations_basic() {
        let basis = vec![1.0, 0.9, 0.1, 0.05, 0.8, 0.85, 0.05, 0.02, 0.1, 0.08, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        let locations = rxffe_floating_locations_v1(&basis, 3, 12, 2, 1.0, 0.0, 2).expect("locations");
        assert_eq!(locations.len(), 4);
        assert!(locations.iter().all(|value| *value >= 0));
    }

    #[test]
    fn floating_force_retains_fixed_taps() {
        let waveform: Vec<f64> = (0..64)
            .map(|index| {
                let i = index as f64;
                (-(i - 32.0) * (i - 32.0) / 200.0).exp() * (i * 0.3).sin()
            })
            .collect();
        let (result, locations) = force_floating_rx_ffe_v1(
            &waveform, 32, 1, 1, 8, 4, 0.0, false, 0.0, 3, 2, 2, 0.5, "taps", true,
        )
        .expect("floating");
        assert_eq!(locations.len(), 4);
        assert_eq!(result.taps().len(), 10);
        assert!(result.filtered().is_some());
    }

    #[test]
    fn floating_controls_fail_closed() {
        let waveform = vec![1.0; 32];
        assert!(force_floating_rx_ffe_v1(
            &waveform, 4, 1, 1, 1, 4, 0.0, false, 0.0, 2, 2, 2, 0.5, "taps", true,
        )
        .is_err());
        assert!(force_floating_rx_ffe_v1(
            &waveform, 4, 1, 1, 8, 4, 0.0, false, 0.0, 0, 2, 2, 0.5, "taps", true,
        )
        .is_err());
    }
    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(RX_FFE_POLICY_V1, "sipi.p5-04l.rx-ffe-v1.apply-force-fixed");
        assert_eq!(FLOATING_RX_FFE_POLICY_V1, "sipi.p5-04m.rx-ffe-v1.floating-bank-force");
    }
}