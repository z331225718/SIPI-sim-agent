//! The one project-scoped execution route currently admitted by P6.
//!
//! This module intentionally does not generalize the declarative planner into
//! an executor. It admits one composite node whose semantics are the already
//! verified fixed TRAN-to-causal-FIR edge, then performs exactly one attempt.

use std::{error::Error, fmt, time::Duration};

use sha2::{Digest, Sha256};
use sipi_contracts::{WireProjectEdgeSourceV1, WireProjectPlanV1, WireProjectPortRefV1};
use sipi_link::ReceivedVoltageSamplesV1;
use sipi_runtime::{RunContext, RunId, RuntimeFailure};
use sipi_tran::RcPulseTransientV1;

use crate::{
    CausalFirConsumerConfigV1, CompletedEdgeAttemptV1, EdgeDigestV1,
    FIXED_TRAN_CAUSAL_FIR_PROJECT_BINDING_CONTRACT_V1, FIXED_TRAN_CAUSAL_FIR_PROJECT_KIND_V1,
    FIXED_TRAN_CAUSAL_FIR_PROJECT_SCHEMA_V1, LINK_CAUSAL_FIR_RESULT_CONTRACT_V1,
    ProjectPlanDigestV1, ProjectPlannerV1, TranRcPulseToCausalFirEdgeRecordV1,
    ValidatedProjectPlanV1, run_fixed_tran_to_causal_fir_with_context_v1,
};

/// In-memory values bound to the sole executable project node.
///
/// The request type has no variable fields: it always denotes
/// `tran-rc-pulse-v1`. The consumer policy remains caller-provided and is
/// bound by a digest before the project may execute.
#[derive(Clone, Debug, PartialEq)]
pub struct FixedTranCausalFirProjectBindingV1 {
    request: RcPulseTransientV1,
    consumer: CausalFirConsumerConfigV1,
}

impl FixedTranCausalFirProjectBindingV1 {
    pub const fn new(request: RcPulseTransientV1, consumer: CausalFirConsumerConfigV1) -> Self {
        Self { request, consumer }
    }

    pub const fn request(&self) -> RcPulseTransientV1 {
        self.request
    }

    pub fn consumer(&self) -> &CausalFirConsumerConfigV1 {
        &self.consumer
    }
}

/// A plan admitted for exactly one fixed composite topology.
#[derive(Clone, Debug, PartialEq)]
pub struct FixedTranCausalFirProjectAdmissionV1 {
    plan: ValidatedProjectPlanV1,
    binding: FixedTranCausalFirProjectBindingV1,
    binding_digest: EdgeDigestV1,
}

impl FixedTranCausalFirProjectAdmissionV1 {
    pub fn plan(&self) -> &ValidatedProjectPlanV1 {
        &self.plan
    }

    pub fn binding(&self) -> &FixedTranCausalFirProjectBindingV1 {
        &self.binding
    }

    pub const fn binding_digest(&self) -> EdgeDigestV1 {
        self.binding_digest
    }
}

/// A successful first and only project attempt.
#[derive(Clone, Debug, PartialEq)]
pub struct CompletedFixedTranCausalFirProjectAttemptV1 {
    schema: &'static str,
    project_digest: ProjectPlanDigestV1,
    binding_digest: EdgeDigestV1,
    attempt_index: u64,
    edge_attempt: CompletedEdgeAttemptV1,
}

impl CompletedFixedTranCausalFirProjectAttemptV1 {
    pub const fn schema(&self) -> &'static str {
        self.schema
    }

    pub const fn project_digest(&self) -> ProjectPlanDigestV1 {
        self.project_digest
    }

    pub const fn binding_digest(&self) -> EdgeDigestV1 {
        self.binding_digest
    }

    pub const fn attempt_index(&self) -> u64 {
        self.attempt_index
    }

    pub fn edge_record(&self) -> &TranRcPulseToCausalFirEdgeRecordV1 {
        self.edge_attempt.record()
    }

    pub fn received(&self) -> &ReceivedVoltageSamplesV1 {
        self.edge_attempt.received()
    }
}

/// Admission and execution failures for the fixed project route.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum FixedTranCausalFirProjectError {
    Plan(crate::ProjectPlanError),
    UnsupportedTopology,
    InvalidRunId,
    RunIdMismatch,
    RuntimePolicyMismatch,
    Runtime(RuntimeFailure),
}

impl FixedTranCausalFirProjectError {
    pub const fn code(&self) -> &'static str {
        match self {
            Self::Plan(error) => error.code(),
            Self::UnsupportedTopology => "unsupported_fixed_project_topology",
            Self::InvalidRunId => "invalid_project_run_id",
            Self::RunIdMismatch => "project_run_id_mismatch",
            Self::RuntimePolicyMismatch => "project_runtime_policy_mismatch",
            Self::Runtime(error) => error.code(),
        }
    }
}

impl fmt::Display for FixedTranCausalFirProjectError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl Error for FixedTranCausalFirProjectError {}

/// Validates a declarative plan, then admits only the sole P6 composite node.
///
/// The generic planner is deliberately run first. This preserves its generic
/// boundary validation while the second phase refuses every topology except
/// the fixed composite route below.
pub fn validate_fixed_tran_causal_fir_project_v1(
    wire_plan: WireProjectPlanV1,
    binding: FixedTranCausalFirProjectBindingV1,
) -> Result<FixedTranCausalFirProjectAdmissionV1, FixedTranCausalFirProjectError> {
    let plan = ProjectPlannerV1::validate(wire_plan.clone())
        .map_err(FixedTranCausalFirProjectError::Plan)?;
    RunId::try_new(plan.project_id().to_owned())
        .map_err(|_| FixedTranCausalFirProjectError::InvalidRunId)?;
    validate_exact_fixed_topology(&wire_plan, &plan)?;
    Ok(FixedTranCausalFirProjectAdmissionV1 {
        plan,
        binding_digest: binding_digest(&binding),
        binding,
    })
}

/// Runs the admitted route exactly once with the caller's matching context.
///
/// The context is never replaced: its run id and cooperative budget must
/// exactly equal the declared project policy. Any failed inner attempt returns
/// no completed project attempt, edge record, or received waveform.
pub fn run_fixed_tran_causal_fir_project_attempt_v1(
    admission: &FixedTranCausalFirProjectAdmissionV1,
    context: &RunContext,
) -> Result<CompletedFixedTranCausalFirProjectAttemptV1, FixedTranCausalFirProjectError> {
    if context.run_id().as_str() != admission.plan.project_id() {
        return Err(FixedTranCausalFirProjectError::RunIdMismatch);
    }
    let runtime_policy = context.policy_snapshot();
    let project_policy = admission.plan.resource_policy();
    if runtime_policy.timeout() != Duration::from_millis(project_policy.timeout_millis())
        || runtime_policy.max_work_units() != project_policy.max_work_units()
        || runtime_policy.max_accounted_bytes() != project_policy.max_accounted_bytes()
    {
        return Err(FixedTranCausalFirProjectError::RuntimePolicyMismatch);
    }
    let edge_attempt = run_fixed_tran_to_causal_fir_with_context_v1(
        admission.binding.request(),
        admission.binding.consumer(),
        context,
    )
    .map_err(FixedTranCausalFirProjectError::Runtime)?;
    Ok(CompletedFixedTranCausalFirProjectAttemptV1 {
        schema: FIXED_TRAN_CAUSAL_FIR_PROJECT_SCHEMA_V1,
        project_digest: admission.plan.digest(),
        binding_digest: admission.binding_digest,
        attempt_index: 1,
        edge_attempt,
    })
}

fn validate_exact_fixed_topology(
    wire_plan: &WireProjectPlanV1,
    plan: &ValidatedProjectPlanV1,
) -> Result<(), FixedTranCausalFirProjectError> {
    let exact_input = wire_plan.inputs.len() == 1
        && wire_plan.inputs[0].id == "binding"
        && wire_plan.inputs[0].contract == FIXED_TRAN_CAUSAL_FIR_PROJECT_BINDING_CONTRACT_V1;
    let exact_node = wire_plan.nodes.len() == 1
        && wire_plan.nodes[0].id == "run"
        && wire_plan.nodes[0].kind == FIXED_TRAN_CAUSAL_FIR_PROJECT_KIND_V1;
    let exact_edge = wire_plan.edges.len() == 1
        && matches!(
            &wire_plan.edges[0].from,
            WireProjectEdgeSourceV1::ProjectInput { input_id } if input_id == "binding"
        )
        && wire_plan.edges[0].to
            == WireProjectPortRefV1 {
                node_id: "run".to_owned(),
                port: "binding".to_owned(),
            }
        && wire_plan.edges[0].contract == FIXED_TRAN_CAUSAL_FIR_PROJECT_BINDING_CONTRACT_V1;
    let exact_output = wire_plan.requested_outputs.len() == 1
        && wire_plan.requested_outputs[0].node_id == "run"
        && wire_plan.requested_outputs[0].port == "received"
        && wire_plan.requested_outputs[0].contract == LINK_CAUSAL_FIR_RESULT_CONTRACT_V1;
    let exact_planned_node = plan.topological_order().len() == 1
        && plan.topological_order()[0].id() == "run"
        && plan.topological_order()[0].kind() == FIXED_TRAN_CAUSAL_FIR_PROJECT_KIND_V1;
    if exact_input && exact_node && exact_edge && exact_output && exact_planned_node {
        Ok(())
    } else {
        Err(FixedTranCausalFirProjectError::UnsupportedTopology)
    }
}

fn binding_digest(binding: &FixedTranCausalFirProjectBindingV1) -> EdgeDigestV1 {
    let mut hasher = Sha256::new();
    hash_bytes(
        &mut hasher,
        b"sipi.project.fixed-tran-causal-fir.binding.v1\0",
    );
    hash_text(&mut hasher, binding.request.profile_id());
    hash_bytes(
        &mut hasher,
        binding_policy_digest(binding.consumer()).bytes(),
    );
    EdgeDigestV1::from_bytes(hasher.finalize().into())
}

fn binding_policy_digest(consumer: &CausalFirConsumerConfigV1) -> EdgeDigestV1 {
    let mut hasher = Sha256::new();
    hash_bytes(
        &mut hasher,
        b"sipi.project.fixed-tran-causal-fir.consumer.v1\0",
    );
    hash_f64(&mut hasher, consumer.channel().sample_interval().get());
    hash_u64(&mut hasher, consumer.channel().gain().len() as u64);
    for gain in consumer.channel().gain() {
        hash_f64(&mut hasher, gain.get());
    }
    hash_u64(
        &mut hasher,
        consumer.limits().max_output_samples().get() as u64,
    );
    hash_u64(
        &mut hasher,
        consumer.limits().max_multiply_accumulates().get() as u64,
    );
    EdgeDigestV1::from_bytes(hasher.finalize().into())
}

fn hash_text(hasher: &mut Sha256, value: &str) {
    hash_bytes(hasher, value.as_bytes());
}

fn hash_bytes(hasher: &mut Sha256, value: &[u8]) {
    hash_u64(hasher, value.len() as u64);
    hasher.update(value);
}

fn hash_u64(hasher: &mut Sha256, value: u64) {
    hasher.update(value.to_le_bytes());
}

fn hash_f64(hasher: &mut Sha256, value: f64) {
    hasher.update(value.to_bits().to_le_bytes());
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    use sipi_contracts::{
        CausalFirChannelV1, WireProjectEdgeV1, WireProjectInputV1, WireProjectNodeV1,
        WireProjectOutputRefV1, WireProjectResourcePolicyV1,
    };
    use sipi_link::ConvolutionLimitsV1;
    use sipi_runtime::{CancelReason, RunPolicy, Runtime};
    use sipi_types::{FiniteF64, Seconds};

    fn binding() -> FixedTranCausalFirProjectBindingV1 {
        let channel = CausalFirChannelV1::try_new(
            Seconds::try_new(1.0e-6).expect("finite"),
            vec![FiniteF64::try_new(1.0, "gain").expect("finite")],
        )
        .expect("channel");
        FixedTranCausalFirProjectBindingV1::new(
            RcPulseTransientV1::fixed_profile(),
            CausalFirConsumerConfigV1::try_new(
                channel,
                ConvolutionLimitsV1::try_new(8, 16).expect("limits"),
            )
            .expect("consumer"),
        )
    }

    fn plan(policy: WireProjectResourcePolicyV1) -> WireProjectPlanV1 {
        WireProjectPlanV1 {
            schema: crate::PROJECT_PLAN_V1_SCHEMA.to_owned(),
            project_id: "fixed-project-1".to_owned(),
            seed_hex: "00".repeat(32),
            resource_policy: policy,
            inputs: vec![WireProjectInputV1 {
                id: "binding".to_owned(),
                contract: FIXED_TRAN_CAUSAL_FIR_PROJECT_BINDING_CONTRACT_V1.to_owned(),
            }],
            nodes: vec![WireProjectNodeV1 {
                id: "run".to_owned(),
                kind: FIXED_TRAN_CAUSAL_FIR_PROJECT_KIND_V1.to_owned(),
            }],
            edges: vec![WireProjectEdgeV1 {
                from: WireProjectEdgeSourceV1::ProjectInput {
                    input_id: "binding".to_owned(),
                },
                to: WireProjectPortRefV1 {
                    node_id: "run".to_owned(),
                    port: "binding".to_owned(),
                },
                contract: FIXED_TRAN_CAUSAL_FIR_PROJECT_BINDING_CONTRACT_V1.to_owned(),
            }],
            requested_outputs: vec![WireProjectOutputRefV1 {
                node_id: "run".to_owned(),
                port: "received".to_owned(),
                contract: LINK_CAUSAL_FIR_RESULT_CONTRACT_V1.to_owned(),
            }],
        }
    }

    fn policy() -> WireProjectResourcePolicyV1 {
        WireProjectResourcePolicyV1 {
            timeout_millis: 1000,
            max_work_units: 100,
            max_accounted_bytes: 2048,
        }
    }

    fn context(id: &str, policy: &WireProjectResourcePolicyV1) -> RunContext {
        Runtime::start(
            RunId::try_new(id).expect("run id"),
            RunPolicy::try_new(
                Duration::from_millis(policy.timeout_millis),
                policy.max_work_units,
                policy.max_accounted_bytes,
            )
            .expect("runtime policy"),
        )
        .expect("runtime")
        .1
    }

    #[test]
    fn admitted_project_matches_the_direct_edge_attempt() {
        let wire = plan(policy());
        let admission = validate_fixed_tran_causal_fir_project_v1(wire, binding()).expect("admit");
        let attempt = run_fixed_tran_causal_fir_project_attempt_v1(
            &admission,
            &context("fixed-project-1", &policy()),
        )
        .expect("attempt");
        assert_eq!(attempt.schema(), FIXED_TRAN_CAUSAL_FIR_PROJECT_SCHEMA_V1);
        assert_eq!(attempt.attempt_index(), 1);
        let (_, direct_context) = Runtime::start(
            RunId::try_new("direct-project").expect("id"),
            RunPolicy::try_new(Duration::from_secs(1), 100, 2048).expect("policy"),
        )
        .expect("runtime");
        let direct = run_fixed_tran_to_causal_fir_with_context_v1(
            RcPulseTransientV1::fixed_profile(),
            admission.binding().consumer(),
            &direct_context,
        )
        .expect("direct");
        assert_eq!(attempt.edge_record(), direct.record());
        assert_eq!(attempt.received(), direct.received());
    }

    #[test]
    fn admission_rejects_any_extra_project_shape() {
        let mut wire = plan(policy());
        wire.nodes.push(WireProjectNodeV1 {
            id: "extra".to_owned(),
            kind: FIXED_TRAN_CAUSAL_FIR_PROJECT_KIND_V1.to_owned(),
        });
        assert!(matches!(
            validate_fixed_tran_causal_fir_project_v1(wire, binding()),
            Err(FixedTranCausalFirProjectError::UnsupportedTopology)
                | Err(FixedTranCausalFirProjectError::Plan(_))
        ));
    }

    #[test]
    fn runtime_identity_and_policy_must_match_before_execution() {
        let wire = plan(policy());
        let admission = validate_fixed_tran_causal_fir_project_v1(wire, binding()).expect("admit");
        assert_eq!(
            run_fixed_tran_causal_fir_project_attempt_v1(
                &admission,
                &context("other-project", &policy()),
            ),
            Err(FixedTranCausalFirProjectError::RunIdMismatch)
        );
        let mismatch = WireProjectResourcePolicyV1 {
            timeout_millis: 1001,
            ..policy()
        };
        assert_eq!(
            run_fixed_tran_causal_fir_project_attempt_v1(
                &admission,
                &context("fixed-project-1", &mismatch),
            ),
            Err(FixedTranCausalFirProjectError::RuntimePolicyMismatch)
        );
    }

    #[test]
    fn cancellation_and_resource_exhaustion_have_no_completed_attempt() {
        let wire = plan(policy());
        let admission = validate_fixed_tran_causal_fir_project_v1(wire, binding()).expect("admit");
        let (controller, cancelled) = Runtime::start(
            RunId::try_new("fixed-project-1").expect("id"),
            RunPolicy::try_new(Duration::from_secs(1), 100, 2048).expect("policy"),
        )
        .expect("runtime");
        controller.cancel(CancelReason::Requested);
        assert_eq!(
            run_fixed_tran_causal_fir_project_attempt_v1(&admission, &cancelled),
            Err(FixedTranCausalFirProjectError::Runtime(
                RuntimeFailure::Cancelled
            ))
        );

        let limited = WireProjectResourcePolicyV1 {
            max_work_units: 1,
            ..policy()
        };
        let limited_admission =
            validate_fixed_tran_causal_fir_project_v1(plan(limited.clone()), binding())
                .expect("admit limited");
        assert_eq!(
            run_fixed_tran_causal_fir_project_attempt_v1(
                &limited_admission,
                &context("fixed-project-1", &limited),
            ),
            Err(FixedTranCausalFirProjectError::Runtime(
                RuntimeFailure::ResourceExceeded
            ))
        );
    }
}
