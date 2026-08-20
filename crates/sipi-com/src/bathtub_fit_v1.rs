//! Bathtub curve fit core (P3C-02h).
//!
//! Fits a polynomial curve to a V-shaped BER-vs-time bathtub in the log10(BER)
//! domain: least-squares polynomial regression of degree 1..=3 over
//! (time_offset_ui, log10(ber)) samples, solved by Gaussian elimination with
//! partial pivoting (deterministic). Returns the fit coefficients plus the
//! maximum absolute residual at the sample points and an evaluation method.
//! Builds on the sample model of P3C-02f (BathtubSampleV1); the opening-width
//! estimator remains in 02f. Fail-closed: too few samples, non-ascending time,
//! invalid BER, invalid fit order, insufficient samples for the order, and a
//! numerically degenerate system are strictly rejected.

use crate::BathtubSampleV1;

/// Scope policy for the bathtub curve fit core.
pub const BATHTUB_FIT_POLICY_V1: &str = "sipi.p3c-02h.bathtub-curve-fit.v1.log-ber-poly-fit";

/// Maximum supported polynomial fit order.
pub const BATHTUB_FIT_MAX_ORDER: usize = 3;

/// Fail-closed errors during bathtub curve fitting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum BathtubFitErrorV1 {
    /// Fewer than three samples.
    TooFewSamples,
    /// Time offsets are not strictly ascending.
    TimeNotAscending,
    /// A BER sample is not finite or not in (0, 1).
    InvalidBer,
    /// Fit order is zero or above the maximum supported order.
    InvalidFitOrder,
    /// The sample count is below order + 1.
    InsufficientSamplesForOrder { order: usize, samples: usize },
    /// The least-squares system is numerically degenerate.
    NumericFailure,
}

/// One fitted bathtub curve (log10(BER) = c0 + c1*t + ... + cm*t^m).
#[derive(Clone, Debug, PartialEq)]
pub struct BathtubCurveFitV1 {
    fit_order: usize,
    coefficients: Vec<f64>,
    sample_count: usize,
    max_abs_residual: f64,
}

impl BathtubCurveFitV1 {
    pub fn fit_order(&self) -> usize {
        self.fit_order
    }

    pub fn coefficients(&self) -> &[f64] {
        &self.coefficients
    }

    pub fn sample_count(&self) -> usize {
        self.sample_count
    }

    pub fn max_abs_residual(&self) -> f64 {
        self.max_abs_residual
    }

    /// Evaluate the fitted log10(BER) at a time offset (UI).
    pub fn evaluate_log10_ber(&self, time_offset_ui: f64) -> f64 {
        let mut value = 0.0;
        for (index, coefficient) in self.coefficients.iter().enumerate() {
            value += coefficient * time_offset_ui.powi(index as i32);
        }
        value
    }
}

/// Solve a square linear system by Gaussian elimination with partial pivoting.
///
/// `augmented` is an n x (n + 1) matrix; the solution vector is returned.
/// Returns None when a pivot is zero (degenerate system).
fn gaussian_solve(augmented: &mut [Vec<f64>]) -> Option<Vec<f64>> {
    let n = augmented.len();
    for col in 0..n {
        // Partial pivoting: row with the largest absolute value in this column.
        let mut pivot_row = col;
        let mut pivot_value = augmented[col][col].abs();
        for row in (col + 1)..n {
            let candidate = augmented[row][col].abs();
            if candidate > pivot_value {
                pivot_value = candidate;
                pivot_row = row;
            }
        }
        if pivot_value == 0.0 {
            return None;
        }
        augmented.swap(col, pivot_row);
        for row in (col + 1)..n {
            let factor = augmented[row][col] / augmented[col][col];
            for entry in col..=n {
                augmented[row][entry] -= factor * augmented[col][entry];
            }
        }
    }
    let mut solution = vec![0.0; n];
    for row in (0..n).rev() {
        let mut sum = augmented[row][n];
        for entry in (row + 1)..n {
            sum -= augmented[row][entry] * solution[entry];
        }
        solution[row] = sum / augmented[row][row];
    }
    Some(solution)
}

/// Fit a polynomial of degree `fit_order` (1..=3) to the bathtub samples in
/// the log10(BER) domain.
///
/// Samples must be strictly ascending in time offset with BER in (0, 1).
/// Returns the fit coefficients (constant first), the sample count, and the
/// maximum absolute residual at the sample points.
pub fn fit_bathtub_curve_v1(
    samples: &[BathtubSampleV1],
    fit_order: usize,
) -> Result<BathtubCurveFitV1, BathtubFitErrorV1> {
    if samples.len() < 3 {
        return Err(BathtubFitErrorV1::TooFewSamples);
    }
    if fit_order == 0 || fit_order > BATHTUB_FIT_MAX_ORDER {
        return Err(BathtubFitErrorV1::InvalidFitOrder);
    }
    if samples.len() < fit_order + 1 {
        return Err(BathtubFitErrorV1::InsufficientSamplesForOrder {
            order: fit_order,
            samples: samples.len(),
        });
    }
    for pair in samples.windows(2) {
        if pair[0].time_offset_ui() >= pair[1].time_offset_ui() {
            return Err(BathtubFitErrorV1::TimeNotAscending);
        }
        if !pair[0].ber().is_finite() || pair[0].ber() <= 0.0 || pair[0].ber() >= 1.0 {
            return Err(BathtubFitErrorV1::InvalidBer);
        }
    }
    let last_ber = samples[samples.len() - 1].ber();
    if !last_ber.is_finite() || last_ber <= 0.0 || last_ber >= 1.0 {
        return Err(BathtubFitErrorV1::InvalidBer);
    }

    // Normal equations: A^T A c = A^T y with rows [1, t, t^2, ..., t^m] and
    // y = log10(ber).
    let degree = fit_order;
    let mut gram = vec![vec![0.0; degree + 1]; degree + 1];
    let mut rhs = vec![0.0; degree + 1];
    for sample in samples {
        let t = sample.time_offset_ui();
        let y = sample.ber().log10();
        let mut powers = vec![1.0; degree + 1];
        for p in 1..=degree {
            powers[p] = powers[p - 1] * t;
        }
        for row in 0..=degree {
            for entry in 0..=degree {
                gram[row][entry] += powers[row] * powers[entry];
            }
            rhs[row] += powers[row] * y;
        }
    }
    let mut augmented: Vec<Vec<f64>> = Vec::with_capacity(degree + 1);
    for row in 0..=degree {
        let mut line = gram[row].clone();
        line.push(rhs[row]);
        augmented.push(line);
    }
    let coefficients = gaussian_solve(&mut augmented).ok_or(BathtubFitErrorV1::NumericFailure)?;
    if coefficients.iter().any(|c| !c.is_finite()) {
        return Err(BathtubFitErrorV1::NumericFailure);
    }

    let mut max_abs_residual = 0.0f64;
    for sample in samples {
        let t = sample.time_offset_ui();
        let y = sample.ber().log10();
        let fitted = coefficients
            .iter()
            .enumerate()
            .map(|(index, c)| c * t.powi(index as i32))
            .sum::<f64>();
        let residual = (y - fitted).abs();
        if residual > max_abs_residual {
            max_abs_residual = residual;
        }
    }

    Ok(BathtubCurveFitV1 {
        fit_order,
        coefficients,
        sample_count: samples.len(),
        max_abs_residual,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample(t: f64, ber: f64) -> BathtubSampleV1 {
        BathtubSampleV1::new(t, ber)
    }

    #[test]
    fn linear_fit_recovers_exact_line() {
        // log10(BER) = -2 - 3t
        let samples = vec![
            sample(0.0, 1e-2),
            sample(1.0, 1e-5),
            sample(2.0, 1e-8),
            sample(3.0, 1e-11),
        ];
        let fit = fit_bathtub_curve_v1(&samples, 1).expect("fit");
        assert_eq!(fit.fit_order(), 1);
        assert_eq!(fit.sample_count(), 4);
        let c = fit.coefficients();
        assert!((c[0] - (-2.0)).abs() < 1e-9, "c0 = {}", c[0]);
        assert!((c[1] - (-3.0)).abs() < 1e-9, "c1 = {}", c[1]);
        assert!(fit.max_abs_residual() < 1e-9);
    }

    #[test]
    fn quadratic_fit_recovers_exact_parabola() {
        // log10(BER) = t^2 - 4t + 1
        let samples = vec![
            sample(0.5, 10f64.powf(0.25 - 2.0 + 1.0)),
            sample(1.0, 10f64.powf(1.0 - 4.0 + 1.0)),
            sample(1.5, 10f64.powf(2.25 - 6.0 + 1.0)),
            sample(2.0, 10f64.powf(4.0 - 8.0 + 1.0)),
            sample(2.5, 10f64.powf(6.25 - 10.0 + 1.0)),
        ];
        let fit = fit_bathtub_curve_v1(&samples, 2).expect("fit");
        let c = fit.coefficients();
        assert!((c[0] - 1.0).abs() < 1e-9, "c0 = {}", c[0]);
        assert!((c[1] - (-4.0)).abs() < 1e-9, "c1 = {}", c[1]);
        assert!((c[2] - 1.0).abs() < 1e-9, "c2 = {}", c[2]);
        assert!(fit.max_abs_residual() < 1e-9);
    }

    #[test]
    fn evaluate_matches_fitted_values() {
        let samples = vec![sample(0.0, 1e-2), sample(1.0, 1e-5), sample(2.0, 1e-8)];
        let fit = fit_bathtub_curve_v1(&samples, 1).expect("fit");
        for s in &samples {
            let y = s.ber().log10();
            let fitted = fit.evaluate_log10_ber(s.time_offset_ui());
            assert!((fitted - y).abs() < 1e-9);
        }
    }

    #[test]
    fn too_few_samples_fails_closed() {
        let samples = vec![sample(0.0, 1e-2), sample(1.0, 1e-5)];
        let error = fit_bathtub_curve_v1(&samples, 1).unwrap_err();
        assert_eq!(error, BathtubFitErrorV1::TooFewSamples);
    }

    #[test]
    fn invalid_fit_order_fails_closed() {
        let samples = vec![sample(0.0, 1e-2), sample(1.0, 1e-5), sample(2.0, 1e-8)];
        let error = fit_bathtub_curve_v1(&samples, 0).unwrap_err();
        assert_eq!(error, BathtubFitErrorV1::InvalidFitOrder);
        let error = fit_bathtub_curve_v1(&samples, 4).unwrap_err();
        assert_eq!(error, BathtubFitErrorV1::InvalidFitOrder);
    }

    #[test]
    fn insufficient_samples_for_order_fails_closed() {
        let samples = vec![sample(0.0, 1e-2), sample(1.0, 1e-5), sample(2.0, 1e-8)];
        let error = fit_bathtub_curve_v1(&samples, 3).unwrap_err();
        assert_eq!(
            error,
            BathtubFitErrorV1::InsufficientSamplesForOrder {
                order: 3,
                samples: 3,
            }
        );
    }

    #[test]
    fn time_not_ascending_fails_closed() {
        let samples = vec![sample(0.0, 1e-2), sample(0.0, 1e-5), sample(2.0, 1e-8)];
        let error = fit_bathtub_curve_v1(&samples, 1).unwrap_err();
        assert_eq!(error, BathtubFitErrorV1::TimeNotAscending);
    }

    #[test]
    fn invalid_ber_fails_closed() {
        let samples = vec![sample(0.0, 0.0), sample(1.0, 1e-5), sample(2.0, 1e-8)];
        let error = fit_bathtub_curve_v1(&samples, 1).unwrap_err();
        assert_eq!(error, BathtubFitErrorV1::InvalidBer);
    }
}
