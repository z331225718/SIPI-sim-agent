//! Portable bounded MMSE/KKT solve and strict-best candidate reduction.
//!
//! This is the matrix core of `equalization/mmse.py`.  The full Python
//! orchestration supplies PSDs and channel candidates; the direct API accepts
//! those already-materialized real matrices so no S-parameter fit or hidden
//! numerical dependency is introduced at the Rust boundary.

pub const MMSE_POLICY_V1: &str = "sipi.com.equalization.mmse-v1.kkt-bounded-search";
pub const MAX_MMSE_CANDIDATES_V1: usize = 16_384;
pub const MAX_MMSE_MATRIX_DIM_V1: usize = 512;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MmseErrorV1 {
    InvalidMatrix,
    InvalidControls,
    SingularSolve,
    NonFinite,
    EmptySearch,
    CandidateLimit,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MmseResultV1 {
    pub sigma_e: f64,
    pub fom_db: f64,
    pub rx_ffe: Vec<f64>,
    pub dfe: Vec<f64>,
    pub dfe_limited: Vec<f64>,
    pub condition_number: f64,
    /// Optional waveform materialized by the source search orchestration.
    /// The KKT leaf does not invent one when the caller only supplies a
    /// matrix, so empty vectors mean that no waveform was available at the
    /// boundary rather than a status-only result.
    pub pre_rx_sbr: Vec<f64>,
    pub equalized_sbr: Vec<f64>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MmseCandidateSpecV1 {
    pub h_matrix: Vec<Vec<f64>>,
    pub noise_correlation: Vec<Vec<f64>>,
    pub decision_index: usize,
    pub dfe_tap_count: usize,
    pub sigma_x2: f64,
    pub levels: u32,
    pub r_lm: f64,
    pub rx_min: Vec<f64>,
    pub rx_max: Vec<f64>,
    pub dfe_min: Vec<f64>,
    pub dfe_max: Vec<f64>,
    pub rx_cursor_offset: usize,
    pub ctle_index: i64,
    pub high_pass_index: i64,
    pub pre_rx_sbr: Vec<f64>,
    pub equalized_sbr: Vec<f64>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MmseSearchResultV1 {
    pub candidate_index: usize,
    pub result: MmseResultV1,
    pub ctle_index: i64,
    pub high_pass_index: i64,
}

fn finite_matrix(matrix: &[Vec<f64>]) -> bool {
    !matrix.is_empty()
        && matrix
            .iter()
            .all(|row| !row.is_empty() && row.iter().all(|v| v.is_finite()))
}

fn shape(matrix: &[Vec<f64>]) -> Option<(usize, usize)> {
    if !finite_matrix(matrix) {
        return None;
    }
    let width = matrix[0].len();
    if matrix.iter().any(|row| row.len() != width) {
        return None;
    }
    Some((matrix.len(), width))
}

fn mat_mul_transpose_left(h: &[Vec<f64>]) -> Vec<Vec<f64>> {
    let n = h[0].len();
    let mut out = vec![vec![0.0; n]; n];
    for row in h {
        for i in 0..n {
            for j in 0..n {
                out[i][j] += row[i] * row[j];
            }
        }
    }
    out
}

fn lu_solve(matrix: &[Vec<f64>], rhs: &[f64]) -> Result<Vec<f64>, MmseErrorV1> {
    let n = matrix.len();
    if n == 0 || rhs.len() != n || matrix.iter().any(|row| row.len() != n) {
        return Err(MmseErrorV1::InvalidMatrix);
    }
    let mut a = matrix.to_vec();
    let mut b = rhs.to_vec();
    for column in 0..n {
        let mut pivot = column;
        for row in column + 1..n {
            if a[row][column].abs() > a[pivot][column].abs() {
                pivot = row;
            }
        }
        if !a[pivot][column].is_finite() || a[pivot][column].abs() <= f64::EPSILON {
            return Err(MmseErrorV1::SingularSolve);
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
    if b.iter().all(|value| value.is_finite()) {
        Ok(b)
    } else {
        Err(MmseErrorV1::NonFinite)
    }
}

fn dot(left: &[f64], right: &[f64]) -> f64 {
    left.iter().zip(right).map(|(a, b)| a * b).sum()
}

fn mat_vec(matrix: &[Vec<f64>], vector: &[f64]) -> Vec<f64> {
    matrix.iter().map(|row| dot(row, vector)).collect()
}

fn clamp(value: f64, low: f64, high: f64) -> f64 {
    value.max(low).min(high)
}

fn condition_estimate(matrix: &[Vec<f64>]) -> f64 {
    // NumPy's default `cond(A)` is the 2-norm.  Compute the singular values
    // as the eigenvalues of A^T A with a bounded Jacobi eigensolver.  This is
    // dependency-free and, unlike an infinity-norm or inverse-power proxy,
    // has the same norm definition as the upstream reference.
    let n = matrix.len();
    if n == 0 || matrix.iter().any(|row| row.len() != n) {
        return f64::INFINITY;
    }
    let mut gram = vec![vec![0.0; n]; n];
    for row in matrix {
        for i in 0..n {
            for j in 0..=i {
                gram[i][j] += row[i] * row[j];
            }
        }
    }
    for i in 0..n {
        for j in 0..i {
            gram[j][i] = gram[i][j];
        }
    }
    if gram.iter().flatten().any(|value| !value.is_finite()) {
        return f64::INFINITY;
    }
    for _ in 0..(8 * n).clamp(32, 512) {
        let mut p = 0;
        let mut q = 0;
        let mut largest = 0.0;
        for i in 0..n {
            for j in i + 1..n {
                if gram[i][j].abs() > largest {
                    largest = gram[i][j].abs();
                    p = i;
                    q = j;
                }
            }
        }
        if largest <= f64::EPSILON {
            break;
        }
        let tau = (gram[q][q] - gram[p][p]) / (2.0 * gram[p][q]);
        let t = if tau >= 0.0 {
            1.0 / (tau + (1.0 + tau * tau).sqrt())
        } else {
            -1.0 / (-tau + (1.0 + tau * tau).sqrt())
        };
        let c = 1.0 / (1.0 + t * t).sqrt();
        let s = t * c;
        let app = gram[p][p];
        let aqq = gram[q][q];
        let apq = gram[p][q];
        gram[p][p] = c * c * app - 2.0 * s * c * apq + s * s * aqq;
        gram[q][q] = s * s * app + 2.0 * s * c * apq + c * c * aqq;
        gram[p][q] = 0.0;
        gram[q][p] = 0.0;
        for k in 0..n {
            if k == p || k == q {
                continue;
            }
            let akp = gram[k][p];
            let akq = gram[k][q];
            gram[k][p] = c * akp - s * akq;
            gram[p][k] = gram[k][p];
            gram[k][q] = s * akp + c * akq;
            gram[q][k] = gram[k][q];
        }
    }
    let mut eigenvalues = gram
        .iter()
        .enumerate()
        .map(|(i, row)| row[i])
        .collect::<Vec<_>>();
    if eigenvalues
        .iter()
        .any(|value| !value.is_finite() || *value < -1.0e-10)
    {
        return f64::INFINITY;
    }
    eigenvalues
        .iter_mut()
        .for_each(|value| *value = value.max(0.0));
    eigenvalues.sort_by(f64::total_cmp);
    let smallest = eigenvalues[0];
    let largest = *eigenvalues.last().expect("non-empty eigenvalues");
    if smallest <= f64::EPSILON {
        f64::INFINITY
    } else {
        (largest / smallest).sqrt()
    }
}

fn validate_bounds(minimum: &[f64], maximum: &[f64], expected: usize) -> Result<(), MmseErrorV1> {
    if minimum.len() != expected
        || maximum.len() != expected
        || minimum
            .iter()
            .zip(maximum)
            .any(|(low, high)| !low.is_finite() || !high.is_finite() || low > high)
    {
        return Err(MmseErrorV1::InvalidControls);
    }
    Ok(())
}

/// Port of the fixed-tap `constrained_mmse` KKT solve.
#[allow(clippy::too_many_arguments)]
pub fn constrained_mmse_v1(
    h_matrix: &[Vec<f64>],
    noise_correlation: &[Vec<f64>],
    decision_index: usize,
    dfe_tap_count: usize,
    sigma_x2: f64,
    levels: u32,
    r_lm: f64,
    rx_min: &[f64],
    rx_max: &[f64],
    dfe_min: &[f64],
    dfe_max: &[f64],
    rx_cursor_offset: usize,
) -> Result<MmseResultV1, MmseErrorV1> {
    let (rows, columns) = shape(h_matrix).ok_or(MmseErrorV1::InvalidMatrix)?;
    let (noise_rows, noise_columns) = shape(noise_correlation).ok_or(MmseErrorV1::InvalidMatrix)?;
    if rows > MAX_MMSE_MATRIX_DIM_V1
        || columns != noise_rows
        || noise_rows != noise_columns
        || columns > MAX_MMSE_MATRIX_DIM_V1
        || decision_index + dfe_tap_count >= rows
        || sigma_x2 <= 0.0
        || !sigma_x2.is_finite()
        || levels < 2
        || !r_lm.is_finite()
        || r_lm <= 0.0
        || rx_cursor_offset >= columns
    {
        return Err(MmseErrorV1::InvalidControls);
    }
    validate_bounds(rx_min, rx_max, columns)?;
    validate_bounds(dfe_min, dfe_max, dfe_tap_count)?;
    let mut r = mat_mul_transpose_left(h_matrix);
    for i in 0..columns {
        for j in 0..columns {
            r[i][j] += noise_correlation[i][j] / sigma_x2;
        }
    }
    let h0 = h_matrix[decision_index].clone();
    let hb = (0..dfe_tap_count)
        .map(|row| h_matrix[decision_index + row + 1].clone())
        .collect::<Vec<_>>();
    let kkt_size = columns + dfe_tap_count + 1;
    let mut kkt = vec![vec![0.0; kkt_size]; kkt_size];
    for i in 0..columns {
        for j in 0..columns {
            kkt[i][j] = r[i][j];
        }
    }
    for row in 0..dfe_tap_count {
        for column in 0..columns {
            kkt[column][columns + row] = -hb[row][column];
            kkt[columns + row][column] = -hb[row][column];
        }
        kkt[columns + row][columns + row] = 1.0;
    }
    for column in 0..columns {
        kkt[column][columns + dfe_tap_count] = -h0[column];
        kkt[columns + dfe_tap_count][column] = h0[column];
    }
    let mut rhs = vec![0.0; kkt_size];
    rhs[..columns].copy_from_slice(&h0);
    rhs[kkt_size - 1] = 1.0;
    let condition_number = condition_estimate(&kkt);
    let solution = lu_solve(&kkt, &rhs)?;
    let mut w = solution[..columns].to_vec();
    let b = solution[columns..columns + dfe_tap_count].to_vec();
    let mut limited_b = b.clone();
    for i in 0..dfe_tap_count {
        limited_b[i] = clamp(b[i], dfe_min[i], dfe_max[i]);
    }
    if b != limited_b {
        let replay_size = columns + 1;
        let mut replay = vec![vec![0.0; replay_size]; replay_size];
        for i in 0..columns {
            for j in 0..columns {
                replay[i][j] = r[i][j];
            }
            replay[i][columns] = -h0[i];
            replay[columns][i] = h0[i];
        }
        let mut replay_rhs = vec![0.0; replay_size];
        for i in 0..columns {
            replay_rhs[i] = h0[i]
                + (0..dfe_tap_count)
                    .map(|row| hb[row][i] * limited_b[row])
                    .sum::<f64>();
        }
        replay_rhs[columns] = 1.0;
        w = lu_solve(&replay, &replay_rhs)?[..columns].to_vec();
    }
    let cursor = w[rx_cursor_offset];
    if !cursor.is_finite() || cursor.abs() <= f64::EPSILON {
        return Err(MmseErrorV1::SingularSolve);
    }
    let mut limited_w = w.clone();
    for i in 0..columns {
        limited_w[i] = clamp(w[i], rx_min[i] * cursor, rx_max[i] * cursor);
    }
    if limited_w != w {
        let normalization = dot(&h0, &limited_w);
        if normalization.abs() <= f64::EPSILON || !normalization.is_finite() {
            return Err(MmseErrorV1::SingularSolve);
        }
        for value in &mut limited_w {
            *value /= normalization;
        }
        w = limited_w;
        for row in 0..dfe_tap_count {
            limited_b[row] = clamp(dot(&hb[row], &w), dfe_min[row], dfe_max[row]);
        }
    }
    let rw = mat_vec(&r, &w);
    let mut error_term = dot(&w, &rw) + 1.0 + dot(&limited_b, &limited_b) - 2.0 * dot(&w, &h0);
    for row in 0..dfe_tap_count {
        error_term -= 2.0 * dot(&w, &hb[row]) * limited_b[row];
    }
    if !error_term.is_finite() {
        return Err(MmseErrorV1::NonFinite);
    }
    let sigma_e = (sigma_x2 * error_term.max(0.0)).sqrt();
    let fom_db = if sigma_e == 0.0 {
        f64::INFINITY
    } else {
        20.0 * (r_lm / ((levels as f64 - 1.0) * sigma_e)).log10()
    };
    if !fom_db.is_finite() && !fom_db.is_infinite() {
        return Err(MmseErrorV1::NonFinite);
    }
    Ok(MmseResultV1 {
        sigma_e,
        fom_db,
        rx_ffe: w,
        dfe: limited_b.clone(),
        dfe_limited: limited_b,
        condition_number,
        pre_rx_sbr: Vec::new(),
        equalized_sbr: Vec::new(),
    })
}

/// Evaluate source-order candidates with strict `>` reduction.
pub fn search_mmse_candidates_v1(
    candidates: &[MmseCandidateSpecV1],
) -> Result<MmseSearchResultV1, MmseErrorV1> {
    if candidates.is_empty() {
        return Err(MmseErrorV1::EmptySearch);
    }
    if candidates.len() > MAX_MMSE_CANDIDATES_V1 {
        return Err(MmseErrorV1::CandidateLimit);
    }
    let mut best: Option<MmseSearchResultV1> = None;
    for (candidate_index, candidate) in candidates.iter().enumerate() {
        let mut result = constrained_mmse_v1(
            &candidate.h_matrix,
            &candidate.noise_correlation,
            candidate.decision_index,
            candidate.dfe_tap_count,
            candidate.sigma_x2,
            candidate.levels,
            candidate.r_lm,
            &candidate.rx_min,
            &candidate.rx_max,
            &candidate.dfe_min,
            &candidate.dfe_max,
            candidate.rx_cursor_offset,
        )?;
        if candidate.pre_rx_sbr.iter().any(|value| !value.is_finite())
            || candidate
                .equalized_sbr
                .iter()
                .any(|value| !value.is_finite())
            || candidate.pre_rx_sbr.len() > MAX_MMSE_MATRIX_DIM_V1 * MAX_MMSE_MATRIX_DIM_V1
            || candidate.equalized_sbr.len() > MAX_MMSE_MATRIX_DIM_V1 * MAX_MMSE_MATRIX_DIM_V1
        {
            return Err(MmseErrorV1::NonFinite);
        }
        result.pre_rx_sbr = candidate.pre_rx_sbr.clone();
        result.equalized_sbr = candidate.equalized_sbr.clone();
        if best
            .as_ref()
            .is_none_or(|previous| result.fom_db > previous.result.fom_db)
        {
            best = Some(MmseSearchResultV1 {
                candidate_index,
                result,
                ctle_index: candidate.ctle_index,
                high_pass_index: candidate.high_pass_index,
            });
        }
    }
    best.ok_or(MmseErrorV1::EmptySearch)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spec(scale: f64) -> MmseCandidateSpecV1 {
        MmseCandidateSpecV1 {
            h_matrix: vec![vec![1.0, 0.1], vec![0.2, 1.0], vec![0.1, 0.3]],
            noise_correlation: vec![vec![0.01 * scale, 0.0], vec![0.0, 0.01 * scale]],
            decision_index: 0,
            dfe_tap_count: 1,
            sigma_x2: 1.0,
            levels: 4,
            r_lm: 50.0,
            rx_min: vec![-2.0, -2.0],
            rx_max: vec![2.0, 2.0],
            dfe_min: vec![-0.5],
            dfe_max: vec![0.5],
            rx_cursor_offset: 0,
            ctle_index: scale as i64,
            high_pass_index: 0,
            pre_rx_sbr: Vec::new(),
            equalized_sbr: Vec::new(),
        }
    }

    #[test]
    fn kkt_solution_is_normalized_and_finite() {
        let result = constrained_mmse_v1(
            &spec(1.0).h_matrix,
            &spec(1.0).noise_correlation,
            0,
            1,
            1.0,
            4,
            50.0,
            &[-2.0, -2.0],
            &[2.0, 2.0],
            &[-0.5],
            &[0.5],
            0,
        )
        .expect("mmse");
        assert!(result.fom_db.is_finite());
        assert!(result.rx_ffe.iter().all(|v| v.is_finite()));
    }

    #[test]
    fn search_keeps_first_strict_best() {
        let result = search_mmse_candidates_v1(&[spec(1.0), spec(1.0)]).expect("search");
        assert_eq!(result.candidate_index, 0);
    }
}
