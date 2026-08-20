//! Deterministic r4.80 TX FFE grid construction and reduction (port of
//! `equalization/tx_ffe.py`).
//!
//! Ported from agent-com (MIT source, P5-04j source map): full grid
//! matrix (first column varies slowest), dynamic tx_ffe grid build with
//! cursor = 1 - sum(|taps|) filtering, strict first-maximum candidate
//! reductions, and the final FOM tracker coordinate selection with
//! C-order unravel semantics.

use std::collections::BTreeMap;

/// Explicit scope policy of the TX FFE grid stage.
pub const TX_FFE_POLICY_V1: &str = "sipi.p5-04j.tx-ffe-v1.grid-build-reduce";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TxFfeErrorV1 {
    InvalidGridShape,
    GridColumnEmpty,
    TapNumberGap,
    CandidateEmpty,
    CandidateNonFiniteScore,
    FomTrackerEmpty,
    FomMaskMisaligned,
    FomNonFinite,
}

/// Port of `TxFfeGrid`.
#[derive(Clone, Debug, PartialEq)]
pub struct TxFfeGridV1 {
    noncursor_taps: Vec<Vec<f64>>,
    cursor: Vec<f64>,
    taps: Vec<Vec<f64>>,
    source_indices: Vec<Vec<i64>>,
    precursor_count: usize,
}

impl TxFfeGridV1 {
    pub fn try_new(
        noncursor_taps: Vec<Vec<f64>>,
        cursor: Vec<f64>,
        taps: Vec<Vec<f64>>,
        source_indices: Vec<Vec<i64>>,
        precursor_count: usize,
    ) -> Result<Self, TxFfeErrorV1> {
        let rows = noncursor_taps.len();
        let columns = noncursor_taps.first().map(|row| row.len()).unwrap_or(0);
        if cursor.len() != rows
            || taps.len() != rows
            || source_indices.len() != rows
            || taps.iter().any(|row| row.len() != columns + 1)
            || source_indices.iter().any(|row| row.len() != columns)
            || noncursor_taps.iter().any(|row| row.len() != columns)
        {
            return Err(TxFfeErrorV1::InvalidGridShape);
        }
        Ok(Self {
            noncursor_taps,
            cursor,
            taps,
            source_indices,
            precursor_count,
        })
    }

    pub fn cursor(&self) -> &[f64] {
        &self.cursor
    }

    pub fn taps(&self) -> &[Vec<f64>] {
        &self.taps
    }

    pub fn source_indices(&self) -> &[Vec<i64>] {
        &self.source_indices
    }

    pub fn precursor_count(&self) -> usize {
        self.precursor_count
    }
}

/// Port of `CandidateSelection`.
#[derive(Clone, Debug, PartialEq)]
pub struct CandidateSelectionV1<T: Clone> {
    index: usize,
    score: f64,
    candidate: T,
}

impl<T: Clone> CandidateSelectionV1<T> {
    pub fn index(&self) -> usize {
        self.index
    }

    pub fn score(&self) -> f64 {
        self.score
    }

    pub fn candidate(&self) -> &T {
        &self.candidate
    }
}

/// Port of `FomSelection` (zero-based indices).
#[derive(Clone, Debug, PartialEq)]
pub struct FomSelectionV1 {
    indices: Vec<usize>,
    score: f64,
}

impl FomSelectionV1 {
    pub fn indices(&self) -> &[usize] {
        &self.indices
    }

    pub fn score(&self) -> f64 {
        self.score
    }
}

/// Port of `Full_Grid_Matrix`: the first column varies slowest.
pub fn full_grid_matrix_v1(columns: &[Vec<f64>]) -> Result<Vec<Vec<f64>>, TxFfeErrorV1> {
    if columns.is_empty() {
        return Ok(vec![Vec::new()]);
    }
    for column in columns {
        if column.is_empty() {
            return Err(TxFfeErrorV1::GridColumnEmpty);
        }
    }
    let mut rows = vec![Vec::new()];
    for column in columns {
        let mut next = Vec::with_capacity(rows.len() * column.len());
        for row in &rows {
            for value in column {
                let mut extended = row.clone();
                extended.push(*value);
                next.push(extended);
            }
        }
        rows = next;
    }
    Ok(rows)
}

fn tap_numbers(values: &BTreeMap<String, Vec<f64>>, direction: &str) -> Vec<usize> {
    let mut numbers = Vec::new();
    for key in values.keys() {
        let prefix = format!("tx_ffe_{direction}");
        if let Some(rest) = key.strip_prefix(&prefix)
            && let Some(digits) = rest.strip_suffix("_values")
            && !digits.is_empty()
            && digits.chars().all(|c| c.is_ascii_digit())
            && let Ok(number) = digits.parse::<usize>()
        {
            numbers.push(number);
        }
    }
    numbers.sort_unstable();
    numbers
}

fn require_contiguous(numbers: &[usize], direction: &str) -> Result<(), TxFfeErrorV1> {
    if !numbers.is_empty() {
        let expected: Vec<usize> = (1..=*numbers.iter().max().expect("max")).collect();
        if numbers != expected.as_slice() {
            let _ = direction;
            return Err(TxFfeErrorV1::TapNumberGap);
        }
    }
    Ok(())
}

/// Port of `build_txffe_grid`.
pub fn build_txffe_grid_v1(
    values: &BTreeMap<String, Vec<f64>>,
    c0_min: f64,
    retain_invalid: bool,
) -> Result<TxFfeGridV1, TxFfeErrorV1> {
    let precursor_numbers = tap_numbers(values, "cm");
    let postcursor_numbers = tap_numbers(values, "cp");
    require_contiguous(&precursor_numbers, "cm")?;
    require_contiguous(&postcursor_numbers, "cp")?;
    let mut fields = Vec::new();
    for number in precursor_numbers.iter().rev() {
        fields.push(format!("tx_ffe_cm{number}_values"));
    }
    for number in &postcursor_numbers {
        fields.push(format!("tx_ffe_cp{number}_values"));
    }
    let columns: Vec<Vec<f64>> = fields
        .iter()
        .map(|field| values.get(field).cloned().unwrap_or_default())
        .collect();
    let mut grid = full_grid_matrix_v1(&columns)?;
    let mut indices: Vec<Vec<i64>> = {
        let index_columns: Vec<Vec<f64>> = columns
            .iter()
            .map(|column| {
                (1..=column.len() as i64)
                    .map(|index| index as f64)
                    .collect()
            })
            .collect();
        full_grid_matrix_v1(&index_columns)?
            .into_iter()
            .map(|row| row.into_iter().map(|value| value as i64).collect())
            .collect()
    };
    let mut cursor: Vec<f64> = grid
        .iter()
        .map(|row| 1.0 - row.iter().map(|value| value.abs()).sum::<f64>())
        .collect();
    if !retain_invalid {
        let mut kept_grid = Vec::new();
        let mut kept_indices = Vec::new();
        let mut kept_cursor = Vec::new();
        for (index, row) in grid.iter().enumerate() {
            if cursor[index] >= c0_min {
                kept_grid.push(row.clone());
                kept_indices.push(indices[index].clone());
                kept_cursor.push(cursor[index]);
            }
        }
        grid = kept_grid;
        indices = kept_indices;
        cursor = kept_cursor;
    }
    if grid.is_empty() {
        grid = Vec::new();
        indices = Vec::new();
        cursor = Vec::new();
    }
    // taps = [grid[:, :len(cm)], cursor[:, None], grid[:, len(cm):]]
    let taps: Vec<Vec<f64>> = grid
        .iter()
        .zip(cursor.iter())
        .map(|(row, cursor_value)| {
            let mut taps_row = row[..precursor_numbers.len()].to_vec();
            taps_row.push(*cursor_value);
            taps_row.extend_from_slice(&row[precursor_numbers.len()..]);
            taps_row
        })
        .collect();
    TxFfeGridV1::try_new(grid, cursor, taps, indices, precursor_numbers.len())
}

/// Port of `first_strict_best`: tie retains the first candidate.
pub fn first_strict_best_v1(scores: &[f64]) -> Result<usize, TxFfeErrorV1> {
    if scores.is_empty() || scores.iter().any(|value| value.is_nan()) {
        return Err(TxFfeErrorV1::CandidateEmpty);
    }
    let mut best_index = 0usize;
    let mut best_score = scores[0];
    for (index, score) in scores.iter().enumerate().skip(1) {
        if *score > best_score {
            best_index = index;
            best_score = *score;
        }
    }
    Ok(best_index)
}

/// Port of `select_strict_best` (no guard in the product API).
pub fn select_strict_best_v1<T: Clone, F, E>(
    candidates: &[T],
    score: F,
) -> Result<CandidateSelectionV1<T>, TxFfeErrorV1>
where
    F: Fn(&T) -> Result<f64, E>,
{
    if candidates.is_empty() {
        return Err(TxFfeErrorV1::CandidateEmpty);
    }
    let mut best: Option<(usize, f64, T)> = None;
    for (index, candidate) in candidates.iter().enumerate() {
        let value = score(candidate).map_err(|_| TxFfeErrorV1::CandidateNonFiniteScore)?;
        if !value.is_finite() {
            return Err(TxFfeErrorV1::CandidateNonFiniteScore);
        }
        if best
            .as_ref()
            .is_none_or(|(_, best_score, _)| value > *best_score)
        {
            best = Some((index, value, candidate.clone()));
        }
    }
    let (index, score, candidate) = best.expect("non-empty");
    Ok(CandidateSelectionV1 {
        index,
        score,
        candidate,
    })
}

/// Port of `select_fom_tracker`: strict first-maximum over C-order
/// flattened tracker axes with an optional validity mask.
pub fn select_fom_tracker_v1(
    values: &[f64],
    shape: &[usize],
    valid: Option<&[bool]>,
) -> Result<FomSelectionV1, TxFfeErrorV1> {
    let expected_size: usize = shape.iter().product();
    if shape.is_empty() || expected_size == 0 || values.len() != expected_size {
        return Err(TxFfeErrorV1::FomTrackerEmpty);
    }
    let mask: Vec<bool> = match valid {
        Some(mask) => {
            if mask.len() != expected_size {
                return Err(TxFfeErrorV1::FomMaskMisaligned);
            }
            mask.to_vec()
        }
        None => vec![true; expected_size],
    };
    if !mask.iter().any(|value| *value) {
        return Err(TxFfeErrorV1::FomMaskMisaligned);
    }
    for (index, value) in values.iter().enumerate() {
        if mask[index] && !value.is_finite() {
            return Err(TxFfeErrorV1::FomNonFinite);
        }
    }
    let ordered: Vec<f64> = (0..expected_size)
        .map(|index| {
            if mask[index] {
                values[index]
            } else {
                f64::NEG_INFINITY
            }
        })
        .collect();
    let mut best_index = 0usize;
    let mut best_score = ordered[0];
    for (index, &score) in ordered.iter().enumerate().skip(1) {
        if score > best_score {
            best_index = index;
            best_score = score;
        }
    }
    // C-order unravel: final axis fastest.
    let mut indices = vec![0usize; shape.len()];
    let mut remaining = best_index;
    for axis in (0..shape.len()).rev() {
        indices[axis] = remaining % shape[axis];
        remaining /= shape[axis];
    }
    Ok(FomSelectionV1 {
        indices,
        score: best_score,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn full_grid_first_column_slowest() {
        let columns = vec![vec![1.0, 2.0], vec![10.0, 20.0, 30.0]];
        let grid = full_grid_matrix_v1(&columns).expect("grid");
        assert_eq!(grid.len(), 6);
        assert_eq!(grid[0], vec![1.0, 10.0]);
        assert_eq!(grid[3], vec![2.0, 10.0]);
        assert_eq!(grid[5], vec![2.0, 30.0]);
        let empty = full_grid_matrix_v1(&[]).expect("empty");
        assert_eq!(empty, vec![Vec::<f64>::new()]);
        assert_eq!(
            full_grid_matrix_v1(&[vec![], vec![1.0]]).unwrap_err(),
            TxFfeErrorV1::GridColumnEmpty,
        );
    }

    #[test]
    fn grid_build_filters_invalid_cursor() {
        let mut values = BTreeMap::new();
        values.insert("tx_ffe_cm1_values".to_string(), vec![0.1, -0.2]);
        values.insert("tx_ffe_cp1_values".to_string(), vec![0.05]);
        let grid = build_txffe_grid_v1(&values, 0.0, false).expect("grid");
        // cursor = 1 - (|0.1| + |0.05|) = 0.85; 1 - (0.2+0.05) = 0.75
        assert_eq!(grid.taps().len(), 2);
        assert_eq!(grid.taps()[0], vec![0.1, 0.85, 0.05]);
        assert_eq!(grid.taps()[1], vec![-0.2, 0.75, 0.05]);
        assert_eq!(grid.precursor_count(), 1);
    }

    #[test]
    fn grid_build_retain_invalid() {
        let mut values = BTreeMap::new();
        values.insert("tx_ffe_cm1_values".to_string(), vec![0.9]);
        values.insert("tx_ffe_cp1_values".to_string(), vec![0.8]);
        let filtered = build_txffe_grid_v1(&values, 0.0, false).expect("filtered");
        // cursor = 1 - 1.7 = -0.7 < 0 -> dropped
        assert!(filtered.cursor().is_empty());
        let retained = build_txffe_grid_v1(&values, 0.0, true).expect("retained");
        assert_eq!(retained.cursor().len(), 1);
        assert!((retained.cursor()[0] - (-0.7)).abs() < 1e-12);
    }

    #[test]
    fn tap_gap_rejected() {
        let mut values = BTreeMap::new();
        values.insert("tx_ffe_cm2_values".to_string(), vec![0.1]);
        assert_eq!(
            build_txffe_grid_v1(&values, 0.0, false).unwrap_err(),
            TxFfeErrorV1::TapNumberGap,
        );
    }

    #[test]
    fn strict_first_maximum_ties() {
        assert_eq!(
            first_strict_best_v1(&[2.0, 5.0, 5.0, 3.0]).expect("best"),
            1
        );
        assert_eq!(first_strict_best_v1(&[1.0]).expect("best"), 0);
        assert!(first_strict_best_v1(&[f64::NAN]).is_err());
        assert!(first_strict_best_v1(&[]).is_err());
    }

    #[test]
    fn select_strict_best_candidates() {
        let candidates = vec![3.0_f64, 7.0, 7.0, 2.0];
        let selection =
            select_strict_best_v1::<_, _, ()>(&candidates, |value| Ok(*value)).expect("selection");
        assert_eq!(selection.index(), 1);
        assert_eq!(selection.score(), 7.0);
        assert_eq!(selection.candidate(), &7.0);
        assert!(select_strict_best_v1::<f64, _, ()>(&[], |_| Ok(1.0)).is_err());
        assert!(select_strict_best_v1::<_, _, ()>(&candidates, |_| Ok(f64::INFINITY)).is_err());
    }

    #[test]
    fn fom_tracker_selects_c_order() {
        // 2x3 C-order flat: [a00 a01 a02 a10 a11 a12]
        let values = vec![1.0, 5.0, 2.0, 4.0, 9.0, 3.0];
        let selection = select_fom_tracker_v1(&values, &[2, 3], None).expect("selection");
        assert_eq!(selection.indices(), &[1, 1]);
        assert_eq!(selection.score(), 9.0);
        // validity mask excludes the true maximum
        let mask = vec![true, true, true, true, false, true];
        let masked = select_fom_tracker_v1(&values, &[2, 3], Some(&mask)).expect("masked");
        assert_eq!(masked.indices(), &[0, 1]);
        assert_eq!(masked.score(), 5.0);
        assert!(select_fom_tracker_v1(&values, &[2, 3], Some(&[false; 6])).is_err());
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(TX_FFE_POLICY_V1, "sipi.p5-04j.tx-ffe-v1.grid-build-reduce");
    }
}
