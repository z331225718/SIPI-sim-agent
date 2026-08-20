//! dB-domain tolerance pass/fail core (P3C-03d).
//!
//! A dedicated absolute-difference tolerance check in the dB domain,
//! binding the owner-decided 0.1 dB tolerance (A5, ref owner-decision
//! checklist). In the dB domain the tolerance is an absolute difference:
//! |candidate_db - reference_db| <= tolerance_db. It complements the
//! general P3C-03c metric-compare engine with a dB-specific rule and
//! records the owner tolerance decision as a product constant.

/// Stable scope policy of the P3C-03d dB-tolerance core.
pub const DB_TOLERANCE_POLICY_V1: &str = "sipi.p3c-03d.db-tolerance.v1.0p1db";

/// The owner-decided 0.1 dB tolerance (A5).
pub const OWNER_DB_TOLERANCE_V1: f64 = 0.1;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DbToleranceErrorV1 {
    NonFiniteReference,
    NonFiniteCandidate,
    InvalidTolerance,
}

/// Outcome of a dB-domain tolerance check.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DbToleranceResultV1 {
    difference_db: f64,
    tolerance_db: f64,
    passed: bool,
}

impl DbToleranceResultV1 {
    pub const fn difference_db(self) -> f64 {
        self.difference_db
    }

    pub const fn tolerance_db(self) -> f64 {
        self.tolerance_db
    }

    pub const fn passed(self) -> bool {
        self.passed
    }
}

/// Checks |candidate_db - reference_db| <= tolerance_db in the dB domain.
pub fn db_tolerance_check_v1(
    reference_db: f64,
    candidate_db: f64,
    tolerance_db: f64,
) -> Result<DbToleranceResultV1, DbToleranceErrorV1> {
    if !reference_db.is_finite() {
        return Err(DbToleranceErrorV1::NonFiniteReference);
    }
    if !candidate_db.is_finite() {
        return Err(DbToleranceErrorV1::NonFiniteCandidate);
    }
    if !tolerance_db.is_finite() || tolerance_db < 0.0 {
        return Err(DbToleranceErrorV1::InvalidTolerance);
    }
    let difference = (candidate_db - reference_db).abs();
    // A tiny relative epsilon keeps the boundary inclusive against floating-
    // point representation error at exact-boundary inputs (e.g. 1.1 - 1.0).
    let epsilon = tolerance_db.abs() * 1e-12 + 1e-12;
    Ok(DbToleranceResultV1 {
        difference_db: difference,
        tolerance_db,
        passed: difference <= tolerance_db + epsilon,
    })
}

/// Convenience: checks against the owner-decided 0.1 dB tolerance.
pub fn owner_db_tolerance_check_v1(
    reference_db: f64,
    candidate_db: f64,
) -> Result<DbToleranceResultV1, DbToleranceErrorV1> {
    db_tolerance_check_v1(reference_db, candidate_db, OWNER_DB_TOLERANCE_V1)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(DB_TOLERANCE_POLICY_V1, "sipi.p3c-03d.db-tolerance.v1.0p1db");
        assert!((OWNER_DB_TOLERANCE_V1 - 0.1).abs() < 1e-15);
    }

    #[test]
    fn within_half_dtenth_passes() {
        let r = db_tolerance_check_v1(53.426, 53.45, 0.1).expect("r");
        assert!(r.passed());
        assert!((r.difference_db() - 0.024).abs() < 1e-12);
    }

    #[test]
    fn over_dtenth_fails() {
        let r = db_tolerance_check_v1(53.426, 53.6, 0.1).expect("r");
        assert!(!r.passed());
    }

    #[test]
    fn owner_default_applied() {
        let ok = owner_db_tolerance_check_v1(10.0, 10.05).expect("ok");
        assert!(ok.passed());
        let bad = owner_db_tolerance_check_v1(10.0, 10.3).expect("bad");
        assert!(!bad.passed());
    }

    #[test]
    fn exact_boundary_passes() {
        let r = db_tolerance_check_v1(1.0, 1.1, 0.1).expect("r");
        assert!(r.passed()); // boundary inclusive
    }

    #[test]
    fn boundary_with_epsilon_passes() {
        // 1.1 - 1.0 = 0.10000000000000009 in f64; the epsilon keeps it inclusive.
        let r = db_tolerance_check_v1(1.0, 1.1, 0.1).expect("r");
        assert!(
            r.passed(),
            "boundary with float error should pass, got diff={}",
            r.difference_db()
        );
    }

    #[test]
    fn rejects_nonfinite() {
        assert_eq!(
            db_tolerance_check_v1(f64::NAN, 1.0, 0.1).err(),
            Some(DbToleranceErrorV1::NonFiniteReference)
        );
        assert_eq!(
            db_tolerance_check_v1(1.0, f64::INFINITY, 0.1).err(),
            Some(DbToleranceErrorV1::NonFiniteCandidate)
        );
        assert_eq!(
            db_tolerance_check_v1(1.0, 1.0, -0.1).err(),
            Some(DbToleranceErrorV1::InvalidTolerance)
        );
    }
}
