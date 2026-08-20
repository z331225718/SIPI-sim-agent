//! High-precision erf / erfc / erfinv / erfcinv (P5-04h prerequisite).
//!
//! Self-implemented double-precision special functions following the
//! standard numerical recipes (Abramowitz & Stegun 7.1 series and
//! continued fraction 7.1.14, Newton iteration for the inverse), with
//! no third-party code copied. Used by the r4.80 noise-PDF Q-factor
//! (erfcinv(2 * spec_ber)).

/// erf(x) to ~1e-15 relative.
pub fn erf_v1(x: f64) -> f64 {
    if x == 0.0 {
        return 0.0;
    }
    let sign = if x < 0.0 { -1.0 } else { 1.0 };
    let ax = x.abs();
    if ax <= 2.0 {
        // Series: erf(x) = 2/sqrt(pi) * sum_n (-1)^n x^(2n+1) / (n! (2n+1))
        let mut term = ax; // x^(2n+1)/n! for n = 0
        let mut sum = 0.0_f64;
        let mut n = 0usize;
        loop {
            sum += term / (2 * n + 1) as f64;
            term *= -ax * ax / (n + 1) as f64;
            if term.abs() < 1e-18 * sum.abs() {
                break;
            }
            n += 1;
        }
        sign * (2.0 / std::f64::consts::PI.sqrt()) * sum
    } else {
        sign * (1.0 - erfc_v1(ax))
    }
}

/// erfc(x) for x >= 0 to ~1e-15 relative (A&S 7.1.14 continued fraction).
fn erfc_v1(x: f64) -> f64 {
    if x < 0.0 {
        return 1.0 - erf_v1(x);
    }
    // Continued fraction: erfc(x) = exp(-x^2)/(sqrt(pi)) * 1/(x + a1/(x + a2/(x + ...)))
    // with a = 1/2, 1, 3/2, 2, 5/2, ...  Evaluate backwards from the tail.
    let max_terms = 40usize;
    let mut fraction = 0.0_f64;
    for index in (1..=max_terms).rev() {
        let a = index as f64 / 2.0;
        fraction = a / (x + fraction);
    }
    let value = (-x * x).exp() / std::f64::consts::PI.sqrt() / (x + fraction);
    // The continued fraction can undershoot slightly for moderate x;
    // clamp into [0, 2].
    value.clamp(0.0, 2.0)
}

/// erfinv(p) for p in [-1, 1] via an initial estimate and Newton
/// iteration on erf (quadratic convergence).
pub fn erfinv_v1(p: f64) -> f64 {
    if !(-1.0..=1.0).contains(&p) {
        return f64::NAN;
    }
    if p == 0.0 {
        return 0.0;
    }
    if p == 1.0 {
        return f64::INFINITY;
    }
    if p == -1.0 {
        return f64::NEG_INFINITY;
    }
    let sign = if p < 0.0 { -1.0 } else { 1.0 };
    let a = p.abs();
    let scale = 2.0 / std::f64::consts::PI.sqrt();
    let mut x = if a <= 0.5 {
        // Inverse series: erfinv(z) ~ sqrt(pi)/2 (z + pi z^3 / 12 + 7 pi^2 z^5 / 480)
        let z2 = a * a;
        let pi = std::f64::consts::PI;
        std::f64::consts::PI.sqrt() / 2.0
            * a
            * (1.0 + pi * z2 / 12.0 + 7.0 * pi * pi * z2 * z2 / 480.0)
    } else {
        // erfc tail estimate: q = 1 - a ~ exp(-x^2) / (x sqrt(pi));
        // dropping the slow -ln(x) term gives x0 = sqrt(-ln(q sqrt(pi)))
        // which is already inside Newton's quadratic basin.
        let q = 1.0 - a;
        let inner = (q * std::f64::consts::PI.sqrt()).ln();
        (-inner).sqrt().max(0.0)
    };
    if a <= 0.5 {
        // Newton on erf: x -= (erf(x) - a) / (2/sqrt(pi) * exp(-x^2))
        for _ in 0..8 {
            let error = erf_v1(x) - a;
            let derivative = scale * (-x * x).exp();
            let step = error / derivative;
            x -= step;
            if step.abs() <= 1e-17 * x.abs().max(1.0) {
                break;
            }
        }
    } else {
        // Tail side: iterate directly on erfc(x) - q to avoid the
        // catastrophic 1 - erfc(x) cancellation at large x.
        let q = 1.0 - a;
        for _ in 0..10 {
            let error = erfc_v1(x) - q;
            let derivative = -scale * (-x * x).exp();
            let step = error / derivative;
            x -= step;
            if step.abs() <= 1e-17 * x.abs().max(1.0) {
                break;
            }
        }
    }
    sign * x
}

/// erfc(x) general (any sign), ~1e-15.
pub fn erfc_v1_general(x: f64) -> f64 {
    if x >= 0.0 {
        erfc_v1(x)
    } else {
        2.0 - erfc_v1(-x)
    }
}

/// erfcinv(q) for q in (0, 2), iterating directly on erfc to avoid
/// the 1 - q representation loss for tiny q.
pub fn erfcinv_v1(q: f64) -> f64 {
    if !(0.0 < q && q < 2.0) {
        return f64::NAN;
    }
    if q > 1.0 {
        return -erfcinv_v1(2.0 - q);
    }
    if q <= 0.5 {
        // erfc tail: q ~ exp(-x^2) / (x sqrt(pi))
        let mut x = (-(q * std::f64::consts::PI.sqrt()).ln()).sqrt().max(0.0);
        let scale = 2.0 / std::f64::consts::PI.sqrt();
        for _ in 0..12 {
            let error = erfc_v1(x) - q;
            let derivative = -scale * (-x * x).exp();
            let step = error / derivative;
            x -= step;
            if step.abs() <= 1e-17 * x.abs().max(1.0) {
                break;
            }
        }
        x
    } else {
        erfinv_v1(1.0 - q)
    }
}

/// Explicit scope policy of the special-function core.
pub const ERF_POLICY_V1: &str = "sipi.p5-04h.erf-v1.as7-series-newton";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn erf_known_values() {
        assert_eq!(erf_v1(0.0), 0.0);
        assert!((erf_v1(1.0) - 0.8427007929497149).abs() < 1e-15);
        assert!((erf_v1(-1.0) + 0.8427007929497149).abs() < 1e-15);
        assert!((erf_v1(0.5) - 0.5204998778130465).abs() < 1e-15);
    }

    #[test]
    fn erfinv_known_values() {
        assert!((erfinv_v1(0.0) - 0.0).abs() < 1e-17);
        assert!((erfinv_v1(0.5) - 0.4769362762044699).abs() < 1e-14);
        assert!((erfinv_v1(-0.5) + 0.4769362762044699).abs() < 1e-14);
        // scipy.special.erfinv(0.9998) = 2.6297417762102926
        assert!((erfinv_v1(0.9998) - 2.6297417762102926).abs() < 1e-12);
    }

    #[test]
    fn erfcinv_small_q() {
        // scipy.special.erfcinv(2e-4) = 2.629741776210273
        let value = erfcinv_v1(2e-4);
        assert!((value - 2.629741776210273).abs() < 1e-12);
        // scipy.special.erfcinv(2e-12) = 4.974131215017515
        let value_12 = erfcinv_v1(2e-12);
        assert!((value_12 - 4.974131215017515).abs() < 1e-10);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(ERF_POLICY_V1, "sipi.p5-04h.erf-v1.as7-series-newton");
    }
}
