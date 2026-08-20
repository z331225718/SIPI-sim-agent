//! CDR lock semantics core (P3B-04b).
//!
//! Deterministic clock/data recovery lock state machine with hysteresis over a
//! sequence of timing error samples (units are caller-supplied, e.g. UI or
//! seconds): an error magnitude at or below the lock threshold is a good
//! sample, at or above the unlock threshold is a bad sample, and strictly
//! between the thresholds is neutral. The machine starts unlocked and acquires
//! lock after `lock_count` consecutive good samples; while locked it loses
//! lock after `unlock_count` consecutive bad samples. Neutral samples reset
//! both counters. `reset` restarts acquisition from the unlocked state;
//! `cancel` freezes the machine (observations are ignored) until `reset`.
//! This addresses the P3B-04 missing semantic
//! `cdr_clock_source_acquisition_lock_reset_and_cancel` as a clean-room
//! mechanism (no clock source, no BER, no tolerance profile).

/// Scope policy for the CDR lock semantics core.
pub const CDR_LOCK_POLICY_V1: &str = "sipi.p3b-04b.cdr-lock.v1.acquisition-hysteresis";

/// Fail-closed errors during CDR lock tracking.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CdrLockErrorV1 {
    /// The lock threshold is not positive.
    InvalidLockThreshold,
    /// The unlock threshold is not positive or is below the lock threshold.
    InvalidUnlockThreshold,
    /// A lock/unlock count is zero.
    InvalidCount,
    /// The sample sequence is empty.
    EmptySequence,
    /// A timing error sample is not finite.
    NonFiniteError,
}

/// CDR lock state.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CdrLockStateV1 {
    Locked,
    Unlocked,
}

/// Classification of one timing error sample against the thresholds.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CdrSampleClassificationV1 {
    Good,
    Neutral,
    Bad,
}

/// Configuration of the CDR lock machine.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CdrLockConfigV1 {
    lock_threshold: f64,
    unlock_threshold: f64,
    lock_count: usize,
    unlock_count: usize,
}

impl CdrLockConfigV1 {
    pub fn try_new(
        lock_threshold: f64,
        unlock_threshold: f64,
        lock_count: usize,
        unlock_count: usize,
    ) -> Result<Self, CdrLockErrorV1> {
        if !lock_threshold.is_finite() || lock_threshold <= 0.0 {
            return Err(CdrLockErrorV1::InvalidLockThreshold);
        }
        if !unlock_threshold.is_finite() || unlock_threshold < lock_threshold {
            return Err(CdrLockErrorV1::InvalidUnlockThreshold);
        }
        if lock_count == 0 || unlock_count == 0 {
            return Err(CdrLockErrorV1::InvalidCount);
        }
        Ok(Self {
            lock_threshold,
            unlock_threshold,
            lock_count,
            unlock_count,
        })
    }

    pub const fn lock_threshold(&self) -> f64 {
        self.lock_threshold
    }

    pub const fn unlock_threshold(&self) -> f64 {
        self.unlock_threshold
    }

    pub const fn lock_count(&self) -> usize {
        self.lock_count
    }

    pub const fn unlock_count(&self) -> usize {
        self.unlock_count
    }
}

/// One per-sample tracking record.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CdrLockSampleRecordV1 {
    sample_index: usize,
    error: f64,
    classification: CdrSampleClassificationV1,
    state_after: CdrLockStateV1,
}

impl CdrLockSampleRecordV1 {
    pub const fn new(
        sample_index: usize,
        error: f64,
        classification: CdrSampleClassificationV1,
        state_after: CdrLockStateV1,
    ) -> Self {
        Self {
            sample_index,
            error,
            classification,
            state_after,
        }
    }

    pub const fn sample_index(&self) -> usize {
        self.sample_index
    }

    pub const fn error(&self) -> f64 {
        self.error
    }

    pub const fn classification(&self) -> CdrSampleClassificationV1 {
        self.classification
    }

    pub const fn state_after(&self) -> CdrLockStateV1 {
        self.state_after
    }
}

/// Outcome of a batch CDR lock tracking pass.
#[derive(Clone, Debug, PartialEq)]
pub struct CdrLockTrackingV1 {
    final_state: CdrLockStateV1,
    lock_transitions: usize,
    unlock_transitions: usize,
    samples: Vec<CdrLockSampleRecordV1>,
}

impl CdrLockTrackingV1 {
    pub fn final_state(&self) -> CdrLockStateV1 {
        self.final_state
    }

    pub fn lock_transitions(&self) -> usize {
        self.lock_transitions
    }

    pub fn unlock_transitions(&self) -> usize {
        self.unlock_transitions
    }

    pub fn samples(&self) -> &[CdrLockSampleRecordV1] {
        &self.samples
    }
}

/// One live CDR lock tracker (reset/cancel capable).
#[derive(Clone, Debug)]
pub struct CdrLockTrackerV1 {
    config: CdrLockConfigV1,
    state: CdrLockStateV1,
    good_run: usize,
    bad_run: usize,
    lock_transitions: usize,
    unlock_transitions: usize,
    cancelled: bool,
}

impl CdrLockTrackerV1 {
    pub fn new(config: CdrLockConfigV1) -> Self {
        Self {
            config,
            state: CdrLockStateV1::Unlocked,
            good_run: 0,
            bad_run: 0,
            lock_transitions: 0,
            unlock_transitions: 0,
            cancelled: false,
        }
    }

    pub fn state(&self) -> CdrLockStateV1 {
        self.state
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled
    }

    pub fn lock_transitions(&self) -> usize {
        self.lock_transitions
    }

    pub fn unlock_transitions(&self) -> usize {
        self.unlock_transitions
    }

    /// Reset the machine: unlocked state, cleared counters, uncancelled.
    pub fn reset(&mut self) {
        self.state = CdrLockStateV1::Unlocked;
        self.good_run = 0;
        self.bad_run = 0;
        self.lock_transitions = 0;
        self.unlock_transitions = 0;
        self.cancelled = false;
    }

    /// Cancel the machine: observations are ignored until the next reset.
    pub fn cancel(&mut self) {
        self.cancelled = true;
    }

    /// Observe one timing error sample and advance the machine.
    pub fn observe(&mut self, error: f64) -> Result<CdrLockSampleRecordV1, CdrLockErrorV1> {
        if !error.is_finite() {
            return Err(CdrLockErrorV1::NonFiniteError);
        }
        if self.cancelled {
            return Ok(CdrLockSampleRecordV1::new(
                0,
                error,
                CdrSampleClassificationV1::Neutral,
                self.state,
            ));
        }
        let magnitude = error.abs();
        let classification = if magnitude <= self.config.lock_threshold() {
            CdrSampleClassificationV1::Good
        } else if magnitude >= self.config.unlock_threshold() {
            CdrSampleClassificationV1::Bad
        } else {
            CdrSampleClassificationV1::Neutral
        };
        match classification {
            CdrSampleClassificationV1::Good => {
                self.bad_run = 0;
                self.good_run += 1;
                if self.state == CdrLockStateV1::Unlocked
                    && self.good_run >= self.config.lock_count()
                {
                    self.state = CdrLockStateV1::Locked;
                    self.lock_transitions += 1;
                    self.good_run = 0;
                    self.bad_run = 0;
                }
            }
            CdrSampleClassificationV1::Bad => {
                self.good_run = 0;
                self.bad_run += 1;
                if self.state == CdrLockStateV1::Locked
                    && self.bad_run >= self.config.unlock_count()
                {
                    self.state = CdrLockStateV1::Unlocked;
                    self.unlock_transitions += 1;
                    self.good_run = 0;
                    self.bad_run = 0;
                }
            }
            CdrSampleClassificationV1::Neutral => {
                self.good_run = 0;
                self.bad_run = 0;
            }
        }
        Ok(CdrLockSampleRecordV1::new(
            0,
            error,
            classification,
            self.state,
        ))
    }
}

/// Track `samples` through a fresh CDR lock machine (reset at start).
///
/// Returns the final state, transition counts, and per-sample records with
/// 1-based sample indices, or fails closed on the first violating condition.
pub fn track_cdr_lock_v1(
    config: CdrLockConfigV1,
    samples: &[f64],
) -> Result<CdrLockTrackingV1, CdrLockErrorV1> {
    if samples.is_empty() {
        return Err(CdrLockErrorV1::EmptySequence);
    }
    let mut tracker = CdrLockTrackerV1::new(config);
    let mut records = Vec::with_capacity(samples.len());
    for (index, &error) in samples.iter().enumerate() {
        let mut record = tracker.observe(error)?;
        record.sample_index = index + 1;
        records.push(record);
    }
    Ok(CdrLockTrackingV1 {
        final_state: tracker.state(),
        lock_transitions: tracker.lock_transitions(),
        unlock_transitions: tracker.unlock_transitions(),
        samples: records,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> CdrLockConfigV1 {
        CdrLockConfigV1::try_new(0.02, 0.10, 3, 2).expect("config")
    }

    #[test]
    fn acquires_lock_after_consecutive_good() {
        let samples = vec![0.01, 0.01, 0.01, 0.005, 0.005];
        let result = track_cdr_lock_v1(config(), &samples).expect("tracked");
        assert_eq!(result.final_state(), CdrLockStateV1::Locked);
        assert_eq!(result.lock_transitions(), 1);
        assert_eq!(result.unlock_transitions(), 0);
        assert_eq!(result.samples().len(), 5);
        // lock acquired at sample 3
        assert_eq!(result.samples()[2].state_after(), CdrLockStateV1::Locked);
        assert_eq!(result.samples()[0].state_after(), CdrLockStateV1::Unlocked);
    }

    #[test]
    fn neutral_samples_do_not_break_lock() {
        let samples = vec![0.01, 0.01, 0.01, 0.05, 0.05, 0.01];
        let result = track_cdr_lock_v1(config(), &samples).expect("tracked");
        assert_eq!(result.final_state(), CdrLockStateV1::Locked);
        assert_eq!(result.lock_transitions(), 1);
        assert_eq!(result.unlock_transitions(), 0);
        // neutral samples classified Neutral
        assert_eq!(
            result.samples()[3].classification(),
            CdrSampleClassificationV1::Neutral
        );
    }

    #[test]
    fn loses_lock_after_consecutive_bad_and_reacquires() {
        let samples = vec![
            0.01, 0.01, 0.01, // lock
            0.20, 0.20, // unlock
            0.01, 0.01, 0.01, // re-lock
        ];
        let result = track_cdr_lock_v1(config(), &samples).expect("tracked");
        assert_eq!(result.final_state(), CdrLockStateV1::Locked);
        assert_eq!(result.lock_transitions(), 2);
        assert_eq!(result.unlock_transitions(), 1);
    }

    #[test]
    fn reset_restarts_acquisition() {
        let mut tracker = CdrLockTrackerV1::new(config());
        tracker.observe(0.01).expect("ok");
        tracker.observe(0.01).expect("ok");
        assert_eq!(tracker.state(), CdrLockStateV1::Unlocked);
        tracker.reset();
        assert_eq!(tracker.state(), CdrLockStateV1::Unlocked);
        assert_eq!(tracker.lock_transitions(), 0);
    }

    #[test]
    fn cancel_freezes_the_machine() {
        let mut tracker = CdrLockTrackerV1::new(config());
        tracker.observe(0.01).expect("ok");
        tracker.observe(0.01).expect("ok");
        tracker.observe(0.01).expect("ok");
        assert_eq!(tracker.state(), CdrLockStateV1::Locked);
        tracker.cancel();
        let record = tracker.observe(0.30).expect("ok");
        // cancelled: observation ignored, state stays Locked
        assert_eq!(tracker.state(), CdrLockStateV1::Locked);
        assert_eq!(record.state_after(), CdrLockStateV1::Locked);
        assert!(tracker.is_cancelled());
        tracker.reset();
        assert!(!tracker.is_cancelled());
        assert_eq!(tracker.state(), CdrLockStateV1::Unlocked);
    }

    #[test]
    fn invalid_config_fails_closed() {
        assert_eq!(
            CdrLockConfigV1::try_new(0.0, 0.1, 3, 2).unwrap_err(),
            CdrLockErrorV1::InvalidLockThreshold
        );
        assert_eq!(
            CdrLockConfigV1::try_new(0.2, 0.1, 3, 2).unwrap_err(),
            CdrLockErrorV1::InvalidUnlockThreshold
        );
        assert_eq!(
            CdrLockConfigV1::try_new(0.02, 0.1, 0, 2).unwrap_err(),
            CdrLockErrorV1::InvalidCount
        );
        assert_eq!(
            CdrLockConfigV1::try_new(0.02, 0.1, 3, 0).unwrap_err(),
            CdrLockErrorV1::InvalidCount
        );
    }

    #[test]
    fn empty_sequence_fails_closed() {
        let error = track_cdr_lock_v1(config(), &[]).unwrap_err();
        assert_eq!(error, CdrLockErrorV1::EmptySequence);
    }

    #[test]
    fn non_finite_error_fails_closed() {
        let samples = vec![0.01, f64::NAN];
        let error = track_cdr_lock_v1(config(), &samples).unwrap_err();
        assert_eq!(error, CdrLockErrorV1::NonFiniteError);
    }
}
