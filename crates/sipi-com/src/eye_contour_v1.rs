//! Statistical eye contour core (P3C-02i).
//!
//! Computes the Q-threshold contour of a statistical eye grid: for each time
//! column (strictly ascending time offsets in UI) with per-voltage-row
//! Q-factors (strictly ascending voltage levels), locates the lower and upper
//! voltage crossings where Q crosses the target Q (linear interpolation in Q
//! between adjacent voltage rows; clamped at the grid edges). This is the
//! boundary of the statistical eye at the target BER-equivalent Q, the
//! statistical eye contour mechanism. Fail-closed: empty grids, column/row
//! count mismatches, non-ascending time or voltage, non-finite or non-positive
//! Q, a non-positive target Q, and any column without a Q >= target span are
//! strictly rejected.

/// Scope policy for the statistical eye contour core.
pub const EYE_CONTOUR_POLICY_V1: &str =
    "sipi.p3c-02i.statistical-eye-contour.v1.q-threshold-contour";

/// Fail-closed errors during statistical eye contour computation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum EyeContourErrorV1 {
    /// The grid has no columns or no voltage rows.
    EmptyGrid,
    /// The Q grid column count does not match the time offsets.
    ColumnCountMismatch { columns: usize, time: usize },
    /// A Q grid row length does not match the voltage levels.
    RowCountMismatch { column: usize, rows: usize, voltage: usize },
    /// Time offsets are not strictly ascending.
    TimeNotAscending,
    /// Voltage levels are not strictly ascending.
    VoltageNotAscending,
    /// A Q-factor is not finite or not positive.
    InvalidQ,
    /// The target Q is not positive.
    InvalidTargetQ,
    /// A column has no span with Q >= target.
    NoContourAtColumn { column: usize },
}

/// A statistical eye grid: Q-factor per (time column, voltage row).
#[derive(Clone, Debug, PartialEq)]
pub struct EyeGridV1 {
    time_offsets_ui: Vec<f64>,
    voltage_levels: Vec<f64>,
    q_grid: Vec<Vec<f64>>,
}

impl EyeGridV1 {
    pub fn new(
        time_offsets_ui: Vec<f64>,
        voltage_levels: Vec<f64>,
        q_grid: Vec<Vec<f64>>,
    ) -> Self {
        Self {
            time_offsets_ui,
            voltage_levels,
            q_grid,
        }
    }

    pub fn time_offsets_ui(&self) -> &[f64] {
        &self.time_offsets_ui
    }

    pub fn voltage_levels(&self) -> &[f64] {
        &self.voltage_levels
    }

    pub fn q_grid(&self) -> &[Vec<f64>] {
        &self.q_grid
    }
}

/// The contour at one time column.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TimeColumnContourV1 {
    time_offset_ui: f64,
    lower_voltage: f64,
    upper_voltage: f64,
}

impl TimeColumnContourV1 {
    pub const fn new(time_offset_ui: f64, lower_voltage: f64, upper_voltage: f64) -> Self {
        Self {
            time_offset_ui,
            lower_voltage,
            upper_voltage,
        }
    }

    pub const fn time_offset_ui(self) -> f64 {
        self.time_offset_ui
    }

    pub const fn lower_voltage(self) -> f64 {
        self.lower_voltage
    }

    pub const fn upper_voltage(self) -> f64 {
        self.upper_voltage
    }
}

/// The statistical eye contour at the target Q.
#[derive(Clone, Debug, PartialEq)]
pub struct EyeContourV1 {
    target_q: f64,
    columns: Vec<TimeColumnContourV1>,
}

impl EyeContourV1 {
    pub fn target_q(&self) -> f64 {
        self.target_q
    }

    pub fn columns(&self) -> &[TimeColumnContourV1] {
        &self.columns
    }
}

/// Compute the Q-threshold contour of a statistical eye grid.
///
/// For each time column, the lower crossing is the voltage where Q rises to
/// the target (linear interpolation in Q between adjacent voltage rows, clamped
/// at the leftmost row already at/above target); the upper crossing is the
/// voltage where Q falls back below the target (clamped at the rightmost row).
pub fn statistical_eye_contour_v1(
    grid: &EyeGridV1,
    target_q: f64,
) -> Result<EyeContourV1, EyeContourErrorV1> {
    let time = grid.time_offsets_ui();
    let voltage = grid.voltage_levels();
    let q_grid = grid.q_grid();
    if time.is_empty() || voltage.is_empty() {
        return Err(EyeContourErrorV1::EmptyGrid);
    }
    if q_grid.len() != time.len() {
        return Err(EyeContourErrorV1::ColumnCountMismatch {
            columns: q_grid.len(),
            time: time.len(),
        });
    }
    for (column, row_values) in q_grid.iter().enumerate() {
        if row_values.len() != voltage.len() {
            return Err(EyeContourErrorV1::RowCountMismatch {
                column,
                rows: row_values.len(),
                voltage: voltage.len(),
            });
        }
    }
    if !(target_q > 0.0) {
        return Err(EyeContourErrorV1::InvalidTargetQ);
    }
    for pair in time.windows(2) {
        if pair[0] >= pair[1] {
            return Err(EyeContourErrorV1::TimeNotAscending);
        }
    }
    for pair in voltage.windows(2) {
        if pair[0] >= pair[1] {
            return Err(EyeContourErrorV1::VoltageNotAscending);
        }
    }
    for column in q_grid {
        for &q in column {
            if !q.is_finite() || q <= 0.0 {
                return Err(EyeContourErrorV1::InvalidQ);
            }
        }
    }

    let mut columns = Vec::with_capacity(time.len());
    for (column_index, column) in q_grid.iter().enumerate() {
        // Find the contiguous span of rows with Q >= target.
        let above: Vec<bool> = column.iter().map(|&q| q >= target_q).collect();
        let Some(first) = above.iter().position(|b| *b) else {
            return Err(EyeContourErrorV1::NoContourAtColumn {
                column: column_index,
            });
        };
        let last = above.iter().rposition(|b| *b).expect("first implies last");

        let lower = if first == 0 {
            voltage[0]
        } else {
            interpolate_crossing(
                voltage[first - 1],
                column[first - 1],
                voltage[first],
                column[first],
                target_q,
            )
        };
        let upper = if last == voltage.len() - 1 {
            voltage[last]
        } else {
            interpolate_crossing(
                voltage[last],
                column[last],
                voltage[last + 1],
                column[last + 1],
                target_q,
            )
        };
        columns.push(TimeColumnContourV1::new(time[column_index], lower, upper));
    }
    Ok(EyeContourV1 { target_q, columns })
}

/// Linear interpolation in Q between (v_low, q_low) and (v_high, q_high) to
/// find the voltage where Q equals the target.
fn interpolate_crossing(
    v_low: f64,
    q_low: f64,
    v_high: f64,
    q_high: f64,
    target_q: f64,
) -> f64 {
    v_low + (target_q - q_low) * (v_high - v_low) / (q_high - q_low)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn grid() -> EyeGridV1 {
        EyeGridV1::new(
            vec![0.0, 0.5, 1.0],
            vec![0.0, 0.25, 0.5, 0.75, 1.0],
            vec![
                vec![1.0, 5.0, 10.0, 5.0, 1.0],
                vec![1.0, 5.0, 10.0, 5.0, 1.0],
                vec![1.0, 5.0, 10.0, 5.0, 1.0],
            ],
        )
    }

    #[test]
    fn contour_crossings_are_exact_for_linear_segments() {
        let result = statistical_eye_contour_v1(&grid(), 5.0).expect("contour");
        assert_eq!(result.target_q(), 5.0);
        assert_eq!(result.columns().len(), 3);
        for column in result.columns() {
            assert_eq!(column.lower_voltage(), 0.25);
            assert_eq!(column.upper_voltage(), 0.75);
        }
    }

    #[test]
    fn edge_clamping_when_target_below_first_row() {
        let g = EyeGridV1::new(
            vec![0.0],
            vec![0.0, 0.5, 1.0],
            vec![vec![8.0, 10.0, 8.0]],
        );
        let result = statistical_eye_contour_v1(&g, 5.0).expect("contour");
        assert_eq!(result.columns()[0].lower_voltage(), 0.0);
        assert_eq!(result.columns()[0].upper_voltage(), 1.0);
    }

    #[test]
    fn no_contour_column_fails_closed() {
        let g = EyeGridV1::new(
            vec![0.0, 1.0],
            vec![0.0, 0.5, 1.0],
            vec![vec![8.0, 10.0, 8.0], vec![1.0, 2.0, 1.0]],
        );
        let error = statistical_eye_contour_v1(&g, 5.0).unwrap_err();
        assert_eq!(
            error,
            EyeContourErrorV1::NoContourAtColumn { column: 1 }
        );
    }

    #[test]
    fn empty_grid_fails_closed() {
        let g = EyeGridV1::new(vec![], vec![0.0], vec![]);
        let error = statistical_eye_contour_v1(&g, 5.0).unwrap_err();
        assert_eq!(error, EyeContourErrorV1::EmptyGrid);
    }

    #[test]
    fn column_count_mismatch_fails_closed() {
        let g = EyeGridV1::new(
            vec![0.0, 1.0],
            vec![0.0, 1.0],
            vec![vec![8.0, 10.0]],
        );
        let error = statistical_eye_contour_v1(&g, 5.0).unwrap_err();
        assert_eq!(
            error,
            EyeContourErrorV1::ColumnCountMismatch {
                columns: 1,
                time: 2,
            }
        );
    }

    #[test]
    fn row_count_mismatch_fails_closed() {
        let g = EyeGridV1::new(
            vec![0.0],
            vec![0.0, 1.0, 2.0],
            vec![vec![8.0, 10.0]],
        );
        let error = statistical_eye_contour_v1(&g, 5.0).unwrap_err();
        assert_eq!(
            error,
            EyeContourErrorV1::RowCountMismatch {
                column: 0,
                rows: 2,
                voltage: 3,
            }
        );
    }

    #[test]
    fn time_not_ascending_fails_closed() {
        let g = EyeGridV1::new(
            vec![0.0, 0.0],
            vec![0.0, 1.0],
            vec![vec![8.0, 10.0], vec![8.0, 10.0]],
        );
        let error = statistical_eye_contour_v1(&g, 5.0).unwrap_err();
        assert_eq!(error, EyeContourErrorV1::TimeNotAscending);
    }

    #[test]
    fn voltage_not_ascending_fails_closed() {
        let g = EyeGridV1::new(
            vec![0.0],
            vec![0.0, -1.0],
            vec![vec![8.0, 10.0]],
        );
        let error = statistical_eye_contour_v1(&g, 5.0).unwrap_err();
        assert_eq!(error, EyeContourErrorV1::VoltageNotAscending);
    }

    #[test]
    fn invalid_q_fails_closed() {
        let g = EyeGridV1::new(
            vec![0.0],
            vec![0.0, 1.0],
            vec![vec![0.0, 10.0]],
        );
        let error = statistical_eye_contour_v1(&g, 5.0).unwrap_err();
        assert_eq!(error, EyeContourErrorV1::InvalidQ);
    }

    #[test]
    fn invalid_target_q_fails_closed() {
        let error = statistical_eye_contour_v1(&grid(), 0.0).unwrap_err();
        assert_eq!(error, EyeContourErrorV1::InvalidTargetQ);
    }
}
