//! Deterministic warning-report aggregator (P5-02n).
//!
//! Aggregates the per-array deterministic warning flags produced by
//! warning_detector_v1 (P5-02m) into a single stable, deduplicated warning
//! report. Each input is a named warning slice carrying the two deterministic
//! flags delivered in P5-02m (anti-causal precursor and high-frequency
//! non-decay); the aggregator emits the union of active warning codes sorted
//! lexicographically, the per-code list of flagging slices (in input order),
//! and the total number of flagged slices. This is the deterministic subset
//! of the R480 warning contract; the owner-gated full contract (MLSE/DER/CDR)
//! remains out of scope.
//!
//! Fail-closed rules: an empty input set is a hard error, and every slice
//! must have a non-empty name.

/// Stable scope policy of the P5-02n warning-report aggregator.
pub const WARNING_REPORT_POLICY_V1: &str = "sipi.p5-02n.warning-report.v1.aggregate";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum WarningReportErrorV1 {
    EmptyReports,
    EmptySliceName,
}

/// The deterministic warning codes recognized by this aggregator.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub enum WarningCodeV1 {
    AntiCausal,
    HighFreqNonDecay,
}

impl WarningCodeV1 {
    pub const fn token(self) -> &'static str {
        match self {
            Self::AntiCausal => "anti_causal",
            Self::HighFreqNonDecay => "high_freq_non_decay",
        }
    }
}

/// One named deterministic warning slice produced by P5-02m.
#[derive(Clone, Debug, PartialEq)]
pub struct WarningSliceReportV1 {
    slice_name: String,
    anti_causal_flagged: bool,
    high_freq_non_decay_flagged: bool,
}

impl WarningSliceReportV1 {
    pub fn new(
        slice_name: impl Into<String>,
        anti_causal_flagged: bool,
        high_freq_non_decay_flagged: bool,
    ) -> Self {
        Self {
            slice_name: slice_name.into(),
            anti_causal_flagged,
            high_freq_non_decay_flagged,
        }
    }

    pub fn slice_name(&self) -> &str {
        &self.slice_name
    }

    pub const fn anti_causal_flagged(&self) -> bool {
        self.anti_causal_flagged
    }

    pub const fn high_freq_non_decay_flagged(&self) -> bool {
        self.high_freq_non_decay_flagged
    }
}

/// The aggregated deterministic warning report.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WarningReportV1 {
    active_codes: Vec<WarningCodeV1>,
    flagged_slices_total: usize,
    per_code_slices: Vec<(WarningCodeV1, Vec<String>)>,
}

impl WarningReportV1 {
    pub fn active_codes(&self) -> &[WarningCodeV1] {
        &self.active_codes
    }

    pub const fn flagged_slices_total(&self) -> usize {
        self.flagged_slices_total
    }

    /// The (code, flagging slice names in input order) pairs, sorted by code.
    pub fn per_code_slices(&self) -> &[(WarningCodeV1, Vec<String>)] {
        &self.per_code_slices
    }

    /// True if a given code is active anywhere in the report.
    pub fn has_code(&self, code: WarningCodeV1) -> bool {
        self.active_codes.contains(&code)
    }
}

/// Aggregates the deterministic warning slices into a single stable report.
pub fn aggregate_warning_report_v1(
    slices: &[WarningSliceReportV1],
) -> Result<WarningReportV1, WarningReportErrorV1> {
    if slices.is_empty() {
        return Err(WarningReportErrorV1::EmptyReports);
    }
    if slices.iter().any(|s| s.slice_name().is_empty()) {
        return Err(WarningReportErrorV1::EmptySliceName);
    }
    let all_codes = [WarningCodeV1::AntiCausal, WarningCodeV1::HighFreqNonDecay];
    let mut active = Vec::new();
    let mut per_code = Vec::new();
    for code in all_codes {
        let flagging: Vec<String> = slices
            .iter()
            .filter(|s| match code {
                WarningCodeV1::AntiCausal => s.anti_causal_flagged(),
                WarningCodeV1::HighFreqNonDecay => s.high_freq_non_decay_flagged(),
            })
            .map(|s| s.slice_name().to_string())
            .collect();
        if !flagging.is_empty() {
            active.push(code);
            per_code.push((code, flagging));
        }
    }
    let flagged_total = slices
        .iter()
        .filter(|s| s.anti_causal_flagged() || s.high_freq_non_decay_flagged())
        .count();
    Ok(WarningReportV1 {
        active_codes: active,
        flagged_slices_total: flagged_total,
        per_code_slices: per_code,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            WARNING_REPORT_POLICY_V1,
            "sipi.p5-02n.warning-report.v1.aggregate"
        );
    }

    #[test]
    fn aggregates_union_sorted_by_code() {
        let slices = vec![
            WarningSliceReportV1::new("pad", true, false),
            WarningSliceReportV1::new("die", false, true),
            WarningSliceReportV1::new("pk", true, true),
        ];
        let report = aggregate_warning_report_v1(&slices).expect("ok");
        assert_eq!(
            report.active_codes(),
            &[WarningCodeV1::AntiCausal, WarningCodeV1::HighFreqNonDecay]
        );
        assert_eq!(report.flagged_slices_total(), 3);
        assert_eq!(report.per_code_slices()[0].1, vec!["pad", "pk"]);
        assert_eq!(report.per_code_slices()[1].1, vec!["die", "pk"]);
        assert!(report.has_code(WarningCodeV1::AntiCausal));
        assert!(report.has_code(WarningCodeV1::HighFreqNonDecay));
    }

    #[test]
    fn no_active_codes_yields_empty_union() {
        let slices = vec![WarningSliceReportV1::new("pad", false, false)];
        let report = aggregate_warning_report_v1(&slices).expect("ok");
        assert!(report.active_codes().is_empty());
        assert_eq!(report.flagged_slices_total(), 0);
        assert_eq!(report.per_code_slices().len(), 0);
    }

    #[test]
    fn rejects_empty_reports() {
        assert_eq!(
            aggregate_warning_report_v1(&[]).err(),
            Some(WarningReportErrorV1::EmptyReports)
        );
    }

    #[test]
    fn rejects_empty_slice_name() {
        let slices = vec![WarningSliceReportV1::new("", true, false)];
        assert_eq!(
            aggregate_warning_report_v1(&slices).err(),
            Some(WarningReportErrorV1::EmptySliceName)
        );
    }

    #[test]
    fn single_code_only() {
        let slices = vec![
            WarningSliceReportV1::new("a", false, true),
            WarningSliceReportV1::new("b", false, true),
        ];
        let report = aggregate_warning_report_v1(&slices).expect("ok");
        assert_eq!(report.active_codes(), &[WarningCodeV1::HighFreqNonDecay]);
        assert_eq!(report.per_code_slices()[0].1, vec!["a", "b"]);
        assert!(!report.has_code(WarningCodeV1::AntiCausal));
    }

    #[test]
    fn deduplicates_slices_but_preserves_input_order_per_code() {
        let slices = vec![
            WarningSliceReportV1::new("x", true, false),
            WarningSliceReportV1::new("y", true, false),
            WarningSliceReportV1::new("z", true, false),
        ];
        let report = aggregate_warning_report_v1(&slices).expect("ok");
        assert_eq!(report.active_codes().len(), 1);
        assert_eq!(report.per_code_slices()[0].1, vec!["x", "y", "z"]);
    }
}
