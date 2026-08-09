#![forbid(unsafe_code)]

//! Cooperative run control for future SIPI domain workers.
//!
//! This crate does not spawn or stop threads or processes. Cancellation,
//! deadlines, and resource budgets are observed only at explicit checkpoints.

use std::{
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU8, AtomicU64, Ordering},
    },
    time::{Duration, Instant},
};

use sha2::{Digest, Sha256};

const RUNNING: u8 = 1;
const SUCCEEDED: u8 = 2;
const FAILED: u8 = 3;
const CANCELLED: u8 = 4;
const TIMED_OUT: u8 = 5;
const RESOURCE_EXCEEDED: u8 = 6;
const ABORTED: u8 = 7;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RuntimeFailure {
    InvalidId,
    InvalidPolicy,
    InvalidCacheField,
    Cancelled,
    DeadlineExceeded,
    ResourceExceeded,
    TaskFailed,
    StateViolation,
    Aborted,
}

impl RuntimeFailure {
    pub const fn code(&self) -> &'static str {
        match self {
            Self::InvalidId => "invalid_id",
            Self::InvalidPolicy => "invalid_policy",
            Self::InvalidCacheField => "invalid_cache_field",
            Self::Cancelled => "cancelled",
            Self::DeadlineExceeded => "deadline_exceeded",
            Self::ResourceExceeded => "resource_exceeded",
            Self::TaskFailed => "task_failed",
            Self::StateViolation => "state_violation",
            Self::Aborted => "aborted",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunId(String);

impl RunId {
    pub fn try_new(value: impl Into<String>) -> Result<Self, RuntimeFailure> {
        let value = value.into();
        if value.is_empty()
            || value.len() > 128
            || !value
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
        {
            Err(RuntimeFailure::InvalidId)
        } else {
            Ok(Self(value))
        }
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunPolicy {
    timeout: Duration,
    max_work_units: u64,
    max_accounted_bytes: u64,
}

impl RunPolicy {
    pub fn try_new(
        timeout: Duration,
        max_work_units: u64,
        max_accounted_bytes: u64,
    ) -> Result<Self, RuntimeFailure> {
        if timeout.is_zero() || max_work_units == 0 || max_accounted_bytes == 0 {
            return Err(RuntimeFailure::InvalidPolicy);
        }
        Ok(Self {
            timeout,
            max_work_units,
            max_accounted_bytes,
        })
    }

    pub const fn timeout(&self) -> Duration {
        self.timeout
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ResourceCost {
    pub work_units: u64,
    pub accounted_bytes: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CancelReason {
    Requested,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RunState {
    Created,
    Running,
    Succeeded,
    Failed,
    Cancelled,
    TimedOut,
    ResourceExceeded,
    Aborted,
}

impl RunState {
    const fn from_raw(value: u8) -> Self {
        match value {
            RUNNING => Self::Running,
            SUCCEEDED => Self::Succeeded,
            FAILED => Self::Failed,
            CANCELLED => Self::Cancelled,
            TIMED_OUT => Self::TimedOut,
            RESOURCE_EXCEEDED => Self::ResourceExceeded,
            ABORTED => Self::Aborted,
            _ => Self::Created,
        }
    }

    const fn as_raw(self) -> u8 {
        match self {
            Self::Created => 0,
            Self::Running => RUNNING,
            Self::Succeeded => SUCCEEDED,
            Self::Failed => FAILED,
            Self::Cancelled => CANCELLED,
            Self::TimedOut => TIMED_OUT,
            Self::ResourceExceeded => RESOURCE_EXCEEDED,
            Self::Aborted => ABORTED,
        }
    }

    const fn failure(self) -> RuntimeFailure {
        match self {
            Self::Cancelled => RuntimeFailure::Cancelled,
            Self::TimedOut => RuntimeFailure::DeadlineExceeded,
            Self::ResourceExceeded => RuntimeFailure::ResourceExceeded,
            Self::Failed => RuntimeFailure::TaskFailed,
            Self::Aborted => RuntimeFailure::Aborted,
            Self::Created | Self::Running | Self::Succeeded => RuntimeFailure::StateViolation,
        }
    }
}

pub struct Runtime;

#[derive(Clone)]
pub struct RunController {
    shared: Arc<Shared>,
}

#[derive(Clone)]
pub struct RunContext {
    shared: Arc<Shared>,
}

struct Shared {
    id: RunId,
    deadline: Instant,
    max_work_units: u64,
    max_accounted_bytes: u64,
    state: AtomicU8,
    cancelled: AtomicBool,
    work_units: AtomicU64,
    accounted_bytes: AtomicU64,
}

impl Runtime {
    pub fn start(
        id: RunId,
        policy: RunPolicy,
    ) -> Result<(RunController, RunContext), RuntimeFailure> {
        Self::start_at(id, policy, Instant::now())
    }

    pub fn execute<T, E>(
        context: &RunContext,
        operation: impl FnOnce(&RunContext) -> Result<T, E>,
    ) -> Result<T, RuntimeFailure> {
        context.checkpoint()?;
        let mut abort_guard = AbortGuard {
            context,
            completed: false,
        };
        let result = operation(context);
        context.checkpoint()?;
        let outcome = match result {
            Ok(value) => {
                context.succeed()?;
                Ok(value)
            }
            Err(_) => Err(context.finish(RunState::Failed)),
        };
        abort_guard.completed = true;
        outcome
    }

    fn start_at(
        id: RunId,
        policy: RunPolicy,
        now: Instant,
    ) -> Result<(RunController, RunContext), RuntimeFailure> {
        let deadline = now
            .checked_add(policy.timeout)
            .ok_or(RuntimeFailure::InvalidPolicy)?;
        let shared = Arc::new(Shared {
            id,
            deadline,
            max_work_units: policy.max_work_units,
            max_accounted_bytes: policy.max_accounted_bytes,
            state: AtomicU8::new(RUNNING),
            cancelled: AtomicBool::new(false),
            work_units: AtomicU64::new(0),
            accounted_bytes: AtomicU64::new(0),
        });
        Ok((
            RunController {
                shared: Arc::clone(&shared),
            },
            RunContext { shared },
        ))
    }
}

struct AbortGuard<'a> {
    context: &'a RunContext,
    completed: bool,
}

impl Drop for AbortGuard<'_> {
    fn drop(&mut self) {
        if !self.completed && std::thread::panicking() {
            let _ = self.context.finish(RunState::Aborted);
        }
    }
}

impl RunController {
    pub fn cancel(&self, _reason: CancelReason) {
        if self.state() == RunState::Running {
            self.shared.cancelled.store(true, Ordering::Release);
        }
    }

    pub fn state(&self) -> RunState {
        RunState::from_raw(self.shared.state.load(Ordering::Acquire))
    }

    pub fn run_id(&self) -> &RunId {
        &self.shared.id
    }
}

impl RunContext {
    pub fn checkpoint(&self) -> Result<(), RuntimeFailure> {
        if self.shared.cancelled.load(Ordering::Acquire) {
            return Err(self.finish(RunState::Cancelled));
        }
        if Instant::now() >= self.shared.deadline {
            return Err(self.finish(RunState::TimedOut));
        }
        match self.state() {
            RunState::Running => Ok(()),
            state => Err(state.failure()),
        }
    }

    pub fn consume(&self, cost: ResourceCost) -> Result<(), RuntimeFailure> {
        self.checkpoint()?;
        self.reserve(
            &self.shared.work_units,
            cost.work_units,
            self.shared.max_work_units,
        )?;
        self.reserve(
            &self.shared.accounted_bytes,
            cost.accounted_bytes,
            self.shared.max_accounted_bytes,
        )?;
        self.checkpoint()
    }

    pub fn state(&self) -> RunState {
        RunState::from_raw(self.shared.state.load(Ordering::Acquire))
    }

    fn reserve(
        &self,
        counter: &AtomicU64,
        amount: u64,
        maximum: u64,
    ) -> Result<(), RuntimeFailure> {
        if amount == 0 {
            return Ok(());
        }
        let update = counter.fetch_update(Ordering::AcqRel, Ordering::Acquire, |current| {
            current.checked_add(amount).filter(|next| *next <= maximum)
        });
        if update.is_err() {
            Err(self.finish(RunState::ResourceExceeded))
        } else {
            Ok(())
        }
    }

    fn succeed(&self) -> Result<(), RuntimeFailure> {
        if self
            .shared
            .state
            .compare_exchange(RUNNING, SUCCEEDED, Ordering::AcqRel, Ordering::Acquire)
            .is_ok()
        {
            Ok(())
        } else {
            Err(self.state().failure())
        }
    }

    fn finish(&self, target: RunState) -> RuntimeFailure {
        let _ = self.shared.state.compare_exchange(
            RUNNING,
            target.as_raw(),
            Ordering::AcqRel,
            Ordering::Acquire,
        );
        self.state().failure()
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CacheKey(String);

impl CacheKey {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

pub struct CacheKeyBuilder {
    preimage: Vec<u8>,
}

impl CacheKeyBuilder {
    pub fn new() -> Self {
        let mut preimage = Vec::new();
        append_component(&mut preimage, b"schema", b"sipi.runtime.cache-key.v1");
        Self { preimage }
    }

    pub fn add_bytes(&mut self, label: &str, value: &[u8]) -> Result<&mut Self, RuntimeFailure> {
        validate_cache_label(label)?;
        append_component(&mut self.preimage, b"bytes", label.as_bytes());
        append_component(&mut self.preimage, b"value", value);
        Ok(self)
    }

    pub fn add_u64(&mut self, label: &str, value: u64) -> Result<&mut Self, RuntimeFailure> {
        validate_cache_label(label)?;
        append_component(&mut self.preimage, b"u64", label.as_bytes());
        append_component(&mut self.preimage, b"value", &value.to_be_bytes());
        Ok(self)
    }

    pub fn add_sha256(&mut self, label: &str, digest: &str) -> Result<&mut Self, RuntimeFailure> {
        validate_cache_label(label)?;
        if digest.len() != 64
            || !digest
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(RuntimeFailure::InvalidCacheField);
        }
        append_component(&mut self.preimage, b"sha256", label.as_bytes());
        append_component(&mut self.preimage, b"value", digest.as_bytes());
        Ok(self)
    }

    pub fn finish(self) -> CacheKey {
        CacheKey(format!("{:x}", Sha256::digest(self.preimage)))
    }
}

impl Default for CacheKeyBuilder {
    fn default() -> Self {
        Self::new()
    }
}

fn validate_cache_label(value: &str) -> Result<(), RuntimeFailure> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    {
        Err(RuntimeFailure::InvalidCacheField)
    } else {
        Ok(())
    }
}

fn append_component(output: &mut Vec<u8>, kind: &[u8], value: &[u8]) {
    output.extend_from_slice(&(kind.len() as u64).to_be_bytes());
    output.extend_from_slice(kind);
    output.extend_from_slice(&(value.len() as u64).to_be_bytes());
    output.extend_from_slice(value);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn policy() -> RunPolicy {
        RunPolicy::try_new(Duration::from_secs(1), 2, 4).unwrap()
    }

    fn context() -> (RunController, RunContext) {
        Runtime::start(RunId::try_new("run-1").unwrap(), policy()).unwrap()
    }

    #[test]
    fn cancellation_is_cooperative_and_terminal() {
        let (controller, context) = context();
        controller.cancel(CancelReason::Requested);
        let result = Runtime::execute(&context, |_| -> Result<(), ()> { panic!("must not run") });
        assert_eq!(result, Err(RuntimeFailure::Cancelled));
        assert_eq!(controller.state(), RunState::Cancelled);
    }

    #[test]
    fn deadline_and_resource_boundaries_fail_closed() {
        let started = Instant::now().checked_sub(Duration::from_secs(2)).unwrap();
        let (_, timed_out) =
            Runtime::start_at(RunId::try_new("late").unwrap(), policy(), started).unwrap();
        assert_eq!(
            timed_out.checkpoint(),
            Err(RuntimeFailure::DeadlineExceeded)
        );

        let (controller, context) = context();
        context
            .consume(ResourceCost {
                work_units: 2,
                accounted_bytes: 4,
            })
            .unwrap();
        assert_eq!(
            context.consume(ResourceCost {
                work_units: 1,
                accounted_bytes: 0,
            }),
            Err(RuntimeFailure::ResourceExceeded)
        );
        assert_eq!(controller.state(), RunState::ResourceExceeded);
    }

    #[test]
    fn task_failure_is_structured_and_terminal() {
        let (controller, context) = context();
        assert_eq!(
            Runtime::execute(&context, |_| -> Result<(), ()> { Err(()) }),
            Err(RuntimeFailure::TaskFailed)
        );
        assert_eq!(controller.state(), RunState::Failed);
        assert_eq!(RuntimeFailure::TaskFailed.code(), "task_failed");
    }

    #[test]
    fn cache_key_is_ordered_and_length_delimited() {
        let mut first = CacheKeyBuilder::new();
        first.add_bytes("a", b"bc").unwrap();
        let mut second = CacheKeyBuilder::new();
        second.add_bytes("ab", b"c").unwrap();
        assert_ne!(first.finish(), second.finish());

        let mut stable = CacheKeyBuilder::new();
        stable.add_u64("count", 7).unwrap();
        let expected = stable.finish();
        let mut repeated = CacheKeyBuilder::new();
        repeated.add_u64("count", 7).unwrap();
        assert_eq!(expected, repeated.finish());
        assert!(
            CacheKeyBuilder::new()
                .add_sha256("hash", "not-a-hash")
                .is_err()
        );
    }

    #[test]
    fn identifiers_and_policies_reject_invalid_values() {
        assert!(RunId::try_new("bad/path").is_err());
        assert!(RunPolicy::try_new(Duration::ZERO, 1, 1).is_err());
        assert!(RunPolicy::try_new(Duration::from_secs(1), 0, 1).is_err());
    }

    #[test]
    fn unwind_marks_the_run_aborted_without_catching_the_panic() {
        let (controller, context) = context();
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _ = Runtime::execute(&context, |_| -> Result<(), ()> { panic!("test panic") });
        }));
        assert!(result.is_err());
        assert_eq!(controller.state(), RunState::Aborted);
    }
}
