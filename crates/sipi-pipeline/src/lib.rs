#![forbid(unsafe_code)]

//! A non-executing, statically typed plan DAG.
//!
//! A plan carries only node identities, edge topology, and in-process Rust
//! `TypeId` checks. It never stores values or runs callbacks.

use std::{
    any::TypeId,
    collections::{BTreeMap, BTreeSet, VecDeque},
    error::Error,
    fmt,
    marker::PhantomData,
};

use sha2::{Digest, Sha256};
use sipi_contracts::{
    PROJECT_PLAN_SCHEMA, WireProjectEdgeSourceV1, WireProjectPlanV1, WireProjectPortRefV1,
};

mod tran_to_link;

pub use tran_to_link::{
    CausalFirConsumerConfigV1, TRAN_RC_PULSE_LAUNCH_CONTRACT_V1, TranRcPulseLaunchArtifactV1,
    TranToLinkEdgeError, build_direct_launch_plan_v1, derive_fixed_tran_launch_v1,
    run_fixed_tran_to_causal_fir_v1,
};

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct NodeId(String);

impl NodeId {
    pub fn try_new(value: impl Into<String>) -> Result<Self, PipelineError> {
        let value = value.into();
        let bytes = value.as_bytes();
        if value.is_empty()
            || value.len() > 128
            || !bytes[0].is_ascii_lowercase() && !bytes[0].is_ascii_digit()
            || !bytes.iter().all(|byte| {
                byte.is_ascii_lowercase()
                    || byte.is_ascii_digit()
                    || matches!(byte, b'.' | b'_' | b'-')
            })
        {
            Err(PipelineError::InvalidNodeId)
        } else {
            Ok(Self(value))
        }
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Output<T: 'static> {
    producer: usize,
    type_id: TypeId,
    marker: PhantomData<fn() -> T>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PipelineError {
    InvalidNodeId,
    DuplicateNodeId,
    InvalidNodeShape,
    MissingProducer,
    DuplicateInput,
    TypeMismatch,
    CycleDetected,
    NoSource,
    NoSink,
    UnreachableNode,
    DeadEndNode,
}

impl PipelineError {
    pub const fn code(&self) -> &'static str {
        match self {
            Self::InvalidNodeId => "invalid_node_id",
            Self::DuplicateNodeId => "duplicate_node_id",
            Self::InvalidNodeShape => "invalid_node_shape",
            Self::MissingProducer => "missing_producer",
            Self::DuplicateInput => "duplicate_input",
            Self::TypeMismatch => "type_mismatch",
            Self::CycleDetected => "cycle_detected",
            Self::NoSource => "no_source",
            Self::NoSink => "no_sink",
            Self::UnreachableNode => "unreachable_node",
            Self::DeadEndNode => "dead_end_node",
        }
    }
}

pub struct PipelineBuilder {
    nodes: Vec<DraftNode>,
}

pub struct PipelinePlan {
    topological_order: Vec<NodeId>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum NodeRole {
    Source,
    Stage,
    Join2,
    Sink,
}

struct DraftNode {
    id: NodeId,
    role: NodeRole,
    inputs: Vec<Input>,
    output: Option<TypeId>,
}

#[derive(Clone, Copy)]
struct Input {
    producer: usize,
    type_id: TypeId,
}

impl Default for PipelineBuilder {
    fn default() -> Self {
        Self::new()
    }
}

impl PipelineBuilder {
    pub fn new() -> Self {
        Self { nodes: Vec::new() }
    }

    pub fn source<T: 'static>(&mut self, id: NodeId) -> Result<Output<T>, PipelineError> {
        self.add_node(id, NodeRole::Source, Vec::new(), Some(TypeId::of::<T>()))
    }

    pub fn stage<I: 'static, O: 'static>(
        &mut self,
        id: NodeId,
        input: Output<I>,
    ) -> Result<Output<O>, PipelineError> {
        self.add_node(
            id,
            NodeRole::Stage,
            vec![Input {
                producer: input.producer,
                type_id: input.type_id,
            }],
            Some(TypeId::of::<O>()),
        )
    }

    pub fn join2<A: 'static, B: 'static, O: 'static>(
        &mut self,
        id: NodeId,
        first: Output<A>,
        second: Output<B>,
    ) -> Result<Output<O>, PipelineError> {
        self.add_node(
            id,
            NodeRole::Join2,
            vec![
                Input {
                    producer: first.producer,
                    type_id: first.type_id,
                },
                Input {
                    producer: second.producer,
                    type_id: second.type_id,
                },
            ],
            Some(TypeId::of::<O>()),
        )
    }

    pub fn sink<T: 'static>(&mut self, id: NodeId, input: Output<T>) -> Result<(), PipelineError> {
        self.add_node::<()>(
            id,
            NodeRole::Sink,
            vec![Input {
                producer: input.producer,
                type_id: input.type_id,
            }],
            None,
        )
        .map(|_| ())
    }

    pub fn build(self) -> Result<PipelinePlan, PipelineError> {
        validate_nodes(&self.nodes)?;
        let topological_order = topological_order(&self.nodes)?;
        validate_reachability(&self.nodes)?;
        Ok(PipelinePlan { topological_order })
    }

    fn add_node<T: 'static>(
        &mut self,
        id: NodeId,
        role: NodeRole,
        inputs: Vec<Input>,
        output: Option<TypeId>,
    ) -> Result<Output<T>, PipelineError> {
        if self.nodes.iter().any(|node| node.id == id) {
            return Err(PipelineError::DuplicateNodeId);
        }
        let mut producers = BTreeSet::new();
        if inputs.iter().any(|input| !producers.insert(input.producer)) {
            return Err(PipelineError::DuplicateInput);
        }
        let producer = self.nodes.len();
        self.nodes.push(DraftNode {
            id,
            role,
            inputs,
            output,
        });
        Ok(Output {
            producer,
            type_id: TypeId::of::<T>(),
            marker: PhantomData,
        })
    }
}

impl PipelinePlan {
    pub fn topological_order(&self) -> &[NodeId] {
        &self.topological_order
    }
}

fn validate_nodes(nodes: &[DraftNode]) -> Result<(), PipelineError> {
    let mut sources = 0;
    let mut sinks = 0;
    for (index, node) in nodes.iter().enumerate() {
        let valid_shape = match node.role {
            NodeRole::Source => {
                sources += 1;
                node.inputs.is_empty() && node.output.is_some()
            }
            NodeRole::Stage => node.inputs.len() == 1 && node.output.is_some(),
            NodeRole::Join2 => node.inputs.len() == 2 && node.output.is_some(),
            NodeRole::Sink => {
                sinks += 1;
                node.inputs.len() == 1 && node.output.is_none()
            }
        };
        if !valid_shape {
            return Err(PipelineError::InvalidNodeShape);
        }
        let mut producers = BTreeSet::new();
        for input in &node.inputs {
            if input.producer >= nodes.len() {
                return Err(PipelineError::MissingProducer);
            }
            if input.producer == index || !producers.insert(input.producer) {
                return Err(PipelineError::DuplicateInput);
            }
            let producer_type = nodes[input.producer]
                .output
                .ok_or(PipelineError::MissingProducer)?;
            if producer_type != input.type_id {
                return Err(PipelineError::TypeMismatch);
            }
        }
    }
    if sources == 0 {
        return Err(PipelineError::NoSource);
    }
    if sinks == 0 {
        return Err(PipelineError::NoSink);
    }
    Ok(())
}

fn topological_order(nodes: &[DraftNode]) -> Result<Vec<NodeId>, PipelineError> {
    let mut incoming = nodes
        .iter()
        .map(|node| node.inputs.len())
        .collect::<Vec<_>>();
    let mut outgoing = vec![Vec::new(); nodes.len()];
    for (consumer, node) in nodes.iter().enumerate() {
        for input in &node.inputs {
            outgoing[input.producer].push(consumer);
        }
    }
    let mut ready = BTreeSet::new();
    for (index, count) in incoming.iter().enumerate() {
        if *count == 0 {
            ready.insert((nodes[index].id.clone(), index));
        }
    }
    let mut result = Vec::with_capacity(nodes.len());
    while let Some((id, index)) = ready.pop_first() {
        result.push(id);
        for consumer in &outgoing[index] {
            incoming[*consumer] -= 1;
            if incoming[*consumer] == 0 {
                ready.insert((nodes[*consumer].id.clone(), *consumer));
            }
        }
    }
    if result.len() == nodes.len() {
        Ok(result)
    } else {
        Err(PipelineError::CycleDetected)
    }
}

fn validate_reachability(nodes: &[DraftNode]) -> Result<(), PipelineError> {
    let mut outgoing = vec![Vec::new(); nodes.len()];
    let mut incoming = vec![Vec::new(); nodes.len()];
    for (consumer, node) in nodes.iter().enumerate() {
        for input in &node.inputs {
            outgoing[input.producer].push(consumer);
            incoming[consumer].push(input.producer);
        }
    }
    let sources = nodes
        .iter()
        .enumerate()
        .filter_map(|(index, node)| (node.role == NodeRole::Source).then_some(index))
        .collect::<Vec<_>>();
    let sinks = nodes
        .iter()
        .enumerate()
        .filter_map(|(index, node)| (node.role == NodeRole::Sink).then_some(index))
        .collect::<Vec<_>>();
    if !reachable(&sources, &outgoing)
        .iter()
        .all(|reachable| *reachable)
    {
        return Err(PipelineError::UnreachableNode);
    }
    if !reachable(&sinks, &incoming)
        .iter()
        .all(|reachable| *reachable)
    {
        return Err(PipelineError::DeadEndNode);
    }
    Ok(())
}

fn reachable(starts: &[usize], adjacency: &[Vec<usize>]) -> Vec<bool> {
    let mut visited = vec![false; adjacency.len()];
    let mut queue = VecDeque::new();
    for start in starts {
        visited[*start] = true;
        queue.push_back(*start);
    }
    while let Some(index) = queue.pop_front() {
        for neighbor in &adjacency[index] {
            if !visited[*neighbor] {
                visited[*neighbor] = true;
                queue.push_back(*neighbor);
            }
        }
    }
    visited
}

/// Product-owned project declaration schema. This planner never executes a
/// node, opens an artifact, or starts a worker.
pub const PROJECT_PLAN_V1_SCHEMA: &str = PROJECT_PLAN_SCHEMA;
pub const TRAN_RC_PULSE_KIND_V1: &str = "tran.rc_pulse";
pub const LINK_CAUSAL_FIR_KIND_V1: &str = "link.causal_fir";
pub const TRAN_RC_PULSE_REQUEST_CONTRACT_V1: &str = "sipi.tran.rc-pulse-request.v1";
pub const TRAN_RC_PULSE_RESULT_CONTRACT_V1: &str = "sipi.tran.rc-pulse-result.v1";
pub const LINK_CAUSAL_FIR_REQUEST_CONTRACT_V1: &str = "sipi.link.causal-fir-request.v1";
pub const LINK_CAUSAL_FIR_RESULT_CONTRACT_V1: &str = "sipi.link.causal-fir-result.v1";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ProjectPlanError {
    ContractBoundary,
    DuplicateInput,
    DuplicateNode,
    DuplicateEdge,
    UnknownNodeKind,
    UnknownInput,
    UnknownPort,
    ContractMismatch,
    InputAlreadyBound,
    MissingNodeInput,
    InvalidRequestedOutput,
    DuplicateRequestedOutput,
    CycleDetected,
    UnconnectedNode,
    InvalidSeed,
}

impl ProjectPlanError {
    pub const fn code(&self) -> &'static str {
        match self {
            Self::ContractBoundary => "project_contract_boundary",
            Self::DuplicateInput => "duplicate_project_input",
            Self::DuplicateNode => "duplicate_project_node",
            Self::DuplicateEdge => "duplicate_project_edge",
            Self::UnknownNodeKind => "unknown_project_node_kind",
            Self::UnknownInput => "unknown_project_input",
            Self::UnknownPort => "unknown_project_port",
            Self::ContractMismatch => "project_contract_mismatch",
            Self::InputAlreadyBound => "project_input_already_bound",
            Self::MissingNodeInput => "missing_project_node_input",
            Self::InvalidRequestedOutput => "invalid_requested_output",
            Self::DuplicateRequestedOutput => "duplicate_requested_output",
            Self::CycleDetected => "project_cycle_detected",
            Self::UnconnectedNode => "project_unconnected_node",
            Self::InvalidSeed => "invalid_project_seed",
        }
    }
}

impl fmt::Display for ProjectPlanError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl Error for ProjectPlanError {}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProjectResourcePolicyV1 {
    timeout_millis: u64,
    max_work_units: u64,
    max_accounted_bytes: u64,
}

impl ProjectResourcePolicyV1 {
    pub const fn timeout_millis(&self) -> u64 {
        self.timeout_millis
    }

    pub const fn max_work_units(&self) -> u64 {
        self.max_work_units
    }

    pub const fn max_accounted_bytes(&self) -> u64 {
        self.max_accounted_bytes
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PlannedProjectNodeV1 {
    id: String,
    kind: String,
}

impl PlannedProjectNodeV1 {
    pub fn id(&self) -> &str {
        &self.id
    }

    pub fn kind(&self) -> &str {
        &self.kind
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequestedProjectOutputV1 {
    node_id: String,
    port: String,
    contract: String,
}

impl RequestedProjectOutputV1 {
    pub fn node_id(&self) -> &str {
        &self.node_id
    }

    pub fn port(&self) -> &str {
        &self.port
    }

    pub fn contract(&self) -> &str {
        &self.contract
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ProjectPlanDigestV1([u8; 32]);

impl ProjectPlanDigestV1 {
    pub const fn bytes(&self) -> &[u8; 32] {
        &self.0
    }

    pub fn hex(&self) -> String {
        let mut value = String::with_capacity(self.0.len() * 2);
        for byte in self.0 {
            use std::fmt::Write as _;
            let _ = write!(value, "{byte:02x}");
        }
        value
    }
}

/// A validated, declarative project. It carries no executable callback or
/// artifact location, so it cannot be mistaken for a scheduler.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ValidatedProjectPlanV1 {
    project_id: String,
    seed: [u8; 32],
    resource_policy: ProjectResourcePolicyV1,
    topological_order: Vec<PlannedProjectNodeV1>,
    requested_outputs: Vec<RequestedProjectOutputV1>,
    digest: ProjectPlanDigestV1,
}

impl ValidatedProjectPlanV1 {
    pub fn project_id(&self) -> &str {
        &self.project_id
    }

    pub const fn seed(&self) -> &[u8; 32] {
        &self.seed
    }

    pub const fn resource_policy(&self) -> &ProjectResourcePolicyV1 {
        &self.resource_policy
    }

    pub fn topological_order(&self) -> &[PlannedProjectNodeV1] {
        &self.topological_order
    }

    pub fn requested_outputs(&self) -> &[RequestedProjectOutputV1] {
        &self.requested_outputs
    }

    pub const fn digest(&self) -> ProjectPlanDigestV1 {
        self.digest
    }
}

pub struct ProjectPlannerV1;

impl ProjectPlannerV1 {
    pub fn validate(plan: WireProjectPlanV1) -> Result<ValidatedProjectPlanV1, ProjectPlanError> {
        plan_with_catalog(plan, &production_catalog())
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct PortContract {
    port: &'static str,
    contract: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct NodeSignature {
    inputs: Vec<PortContract>,
    outputs: Vec<PortContract>,
}

fn production_catalog() -> BTreeMap<&'static str, NodeSignature> {
    BTreeMap::from([
        (
            TRAN_RC_PULSE_KIND_V1,
            NodeSignature {
                inputs: vec![PortContract {
                    port: "request",
                    contract: TRAN_RC_PULSE_REQUEST_CONTRACT_V1,
                }],
                outputs: vec![PortContract {
                    port: "result",
                    contract: TRAN_RC_PULSE_RESULT_CONTRACT_V1,
                }],
            },
        ),
        (
            LINK_CAUSAL_FIR_KIND_V1,
            NodeSignature {
                inputs: vec![PortContract {
                    port: "request",
                    contract: LINK_CAUSAL_FIR_REQUEST_CONTRACT_V1,
                }],
                outputs: vec![PortContract {
                    port: "result",
                    contract: LINK_CAUSAL_FIR_RESULT_CONTRACT_V1,
                }],
            },
        ),
    ])
}

fn plan_with_catalog(
    plan: WireProjectPlanV1,
    catalog: &BTreeMap<&'static str, NodeSignature>,
) -> Result<ValidatedProjectPlanV1, ProjectPlanError> {
    plan.validate_boundary()
        .map_err(|_| ProjectPlanError::ContractBoundary)?;
    let seed = decode_seed(&plan.seed_hex)?;

    let mut inputs = BTreeMap::new();
    for input in &plan.inputs {
        if !project_token(&input.id) || !project_token(&input.contract) {
            return Err(ProjectPlanError::ContractBoundary);
        }
        if inputs
            .insert(input.id.as_str(), input.contract.as_str())
            .is_some()
        {
            return Err(ProjectPlanError::DuplicateInput);
        }
    }

    let mut nodes = BTreeMap::new();
    for node in &plan.nodes {
        if !project_token(&node.id) || !project_token(&node.kind) {
            return Err(ProjectPlanError::ContractBoundary);
        }
        let Some(signature) = catalog.get(node.kind.as_str()) else {
            return Err(ProjectPlanError::UnknownNodeKind);
        };
        if nodes.insert(node.id.as_str(), signature).is_some() {
            return Err(ProjectPlanError::DuplicateNode);
        }
    }

    let mut bindings = BTreeSet::new();
    let mut edge_keys = BTreeSet::new();
    let mut outgoing = BTreeMap::<&str, BTreeSet<&str>>::new();
    let mut incoming = BTreeMap::<&str, BTreeSet<&str>>::new();
    for node_id in nodes.keys() {
        outgoing.insert(node_id, BTreeSet::new());
        incoming.insert(node_id, BTreeSet::new());
    }

    for edge in &plan.edges {
        let edge_key = canonical_edge_key(edge);
        if !edge_keys.insert(edge_key) {
            return Err(ProjectPlanError::DuplicateEdge);
        }
        let target = resolve_input(&nodes, &edge.to, &edge.contract)?;
        let binding = (edge.to.node_id.as_str(), edge.to.port.as_str());
        if !bindings.insert(binding) {
            return Err(ProjectPlanError::InputAlreadyBound);
        }
        match &edge.from {
            WireProjectEdgeSourceV1::ProjectInput { input_id } => {
                if !project_token(input_id) {
                    return Err(ProjectPlanError::ContractBoundary);
                }
                let Some(source_contract) = inputs.get(input_id.as_str()) else {
                    return Err(ProjectPlanError::UnknownInput);
                };
                if *source_contract != target {
                    return Err(ProjectPlanError::ContractMismatch);
                }
            }
            WireProjectEdgeSourceV1::NodeOutput { node_id, port } => {
                if !project_token(node_id) || !project_token(port) {
                    return Err(ProjectPlanError::ContractBoundary);
                }
                let Some(source_signature) = nodes.get(node_id.as_str()) else {
                    return Err(ProjectPlanError::UnknownPort);
                };
                let Some(source_contract) = port_contract(&source_signature.outputs, port) else {
                    return Err(ProjectPlanError::UnknownPort);
                };
                if source_contract != target {
                    return Err(ProjectPlanError::ContractMismatch);
                }
                outgoing
                    .get_mut(node_id.as_str())
                    .expect("all node ids initialized")
                    .insert(edge.to.node_id.as_str());
                incoming
                    .get_mut(edge.to.node_id.as_str())
                    .expect("all node ids initialized")
                    .insert(node_id.as_str());
            }
        }
    }

    for (node_id, signature) in &nodes {
        for input in &signature.inputs {
            if !bindings.contains(&(*node_id, input.port)) {
                return Err(ProjectPlanError::MissingNodeInput);
            }
        }
    }

    let mut requested = BTreeSet::new();
    for output in &plan.requested_outputs {
        let Some(signature) = nodes.get(output.node_id.as_str()) else {
            return Err(ProjectPlanError::InvalidRequestedOutput);
        };
        let Some(contract) = port_contract(&signature.outputs, &output.port) else {
            return Err(ProjectPlanError::InvalidRequestedOutput);
        };
        if contract != output.contract || !project_token(&output.contract) {
            return Err(ProjectPlanError::ContractMismatch);
        }
        if !requested.insert((output.node_id.as_str(), output.port.as_str())) {
            return Err(ProjectPlanError::DuplicateRequestedOutput);
        }
    }

    let order = topological_project_order(&incoming, &outgoing)?;
    let reverse_reachable = project_reachable(
        &requested
            .iter()
            .map(|(node_id, _)| *node_id)
            .collect::<Vec<_>>(),
        &incoming,
    );
    if nodes
        .keys()
        .any(|node_id| !reverse_reachable.contains(node_id))
    {
        return Err(ProjectPlanError::UnconnectedNode);
    }

    let topological_order = order
        .iter()
        .map(|id| PlannedProjectNodeV1 {
            id: (*id).to_owned(),
            kind: plan
                .nodes
                .iter()
                .find(|node| node.id == *id)
                .expect("validated node id")
                .kind
                .clone(),
        })
        .collect();
    let requested_outputs = plan
        .requested_outputs
        .iter()
        .map(|output| RequestedProjectOutputV1 {
            node_id: output.node_id.clone(),
            port: output.port.clone(),
            contract: output.contract.clone(),
        })
        .collect::<Vec<_>>();
    let resource_policy = ProjectResourcePolicyV1 {
        timeout_millis: plan.resource_policy.timeout_millis,
        max_work_units: plan.resource_policy.max_work_units,
        max_accounted_bytes: plan.resource_policy.max_accounted_bytes,
    };
    let digest = project_digest(&plan, &order);
    Ok(ValidatedProjectPlanV1 {
        project_id: plan.project_id,
        seed,
        resource_policy,
        topological_order,
        requested_outputs,
        digest,
    })
}

fn resolve_input<'a>(
    nodes: &BTreeMap<&'a str, &'a NodeSignature>,
    target: &'a WireProjectPortRefV1,
    edge_contract: &'a str,
) -> Result<&'a str, ProjectPlanError> {
    if !project_token(&target.node_id)
        || !project_token(&target.port)
        || !project_token(edge_contract)
    {
        return Err(ProjectPlanError::ContractBoundary);
    }
    let Some(signature) = nodes.get(target.node_id.as_str()) else {
        return Err(ProjectPlanError::UnknownPort);
    };
    let Some(contract) = port_contract(&signature.inputs, &target.port) else {
        return Err(ProjectPlanError::UnknownPort);
    };
    if contract != edge_contract {
        return Err(ProjectPlanError::ContractMismatch);
    }
    Ok(contract)
}

fn port_contract<'a>(ports: &'a [PortContract], name: &str) -> Option<&'a str> {
    ports
        .iter()
        .find(|port| port.port == name)
        .map(|port| port.contract)
}

fn topological_project_order<'a>(
    incoming: &BTreeMap<&'a str, BTreeSet<&'a str>>,
    outgoing: &BTreeMap<&'a str, BTreeSet<&'a str>>,
) -> Result<Vec<&'a str>, ProjectPlanError> {
    let mut degrees = incoming
        .iter()
        .map(|(node, sources)| (*node, sources.len()))
        .collect::<BTreeMap<_, _>>();
    let mut ready = degrees
        .iter()
        .filter_map(|(node, degree)| (*degree == 0).then_some(*node))
        .collect::<BTreeSet<_>>();
    let mut order = Vec::with_capacity(degrees.len());
    while let Some(node) = ready.pop_first() {
        order.push(node);
        for target in &outgoing[node] {
            let degree = degrees
                .get_mut(target)
                .expect("outgoing target is a project node");
            *degree -= 1;
            if *degree == 0 {
                ready.insert(target);
            }
        }
    }
    if order.len() == degrees.len() {
        Ok(order)
    } else {
        Err(ProjectPlanError::CycleDetected)
    }
}

fn project_reachable<'a>(
    starts: &[&'a str],
    adjacency: &BTreeMap<&'a str, BTreeSet<&'a str>>,
) -> BTreeSet<&'a str> {
    let mut visited = BTreeSet::new();
    let mut queue = VecDeque::new();
    for start in starts {
        visited.insert(*start);
        queue.push_back(*start);
    }
    while let Some(node) = queue.pop_front() {
        for neighbor in &adjacency[node] {
            if visited.insert(*neighbor) {
                queue.push_back(*neighbor);
            }
        }
    }
    visited
}

fn decode_seed(value: &str) -> Result<[u8; 32], ProjectPlanError> {
    let mut seed = [0_u8; 32];
    if value.len() != 64 {
        return Err(ProjectPlanError::InvalidSeed);
    }
    for (index, pair) in value.as_bytes().chunks_exact(2).enumerate() {
        let high = hex_nibble(pair[0]).ok_or(ProjectPlanError::InvalidSeed)?;
        let low = hex_nibble(pair[1]).ok_or(ProjectPlanError::InvalidSeed)?;
        seed[index] = (high << 4) | low;
    }
    Ok(seed)
}

fn hex_nibble(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        _ => None,
    }
}

fn project_token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'_' | b'-')
        })
}

fn canonical_edge_key(edge: &sipi_contracts::WireProjectEdgeV1) -> String {
    match &edge.from {
        WireProjectEdgeSourceV1::ProjectInput { input_id } => format!(
            "input:{input_id}:{}:{}:{}",
            edge.to.node_id, edge.to.port, edge.contract
        ),
        WireProjectEdgeSourceV1::NodeOutput { node_id, port } => format!(
            "node:{node_id}:{port}:{}:{}:{}",
            edge.to.node_id, edge.to.port, edge.contract
        ),
    }
}

fn project_digest(plan: &WireProjectPlanV1, order: &[&str]) -> ProjectPlanDigestV1 {
    let mut hasher = Sha256::new();
    hash_field(&mut hasher, "schema", &plan.schema);
    hash_field(&mut hasher, "project_id", &plan.project_id);
    hash_field(&mut hasher, "seed_hex", &plan.seed_hex);
    for (label, value) in [
        ("timeout_millis", plan.resource_policy.timeout_millis),
        ("max_work_units", plan.resource_policy.max_work_units),
        (
            "max_accounted_bytes",
            plan.resource_policy.max_accounted_bytes,
        ),
    ] {
        hash_field(&mut hasher, label, &value.to_string());
    }
    let mut inputs = plan.inputs.iter().collect::<Vec<_>>();
    inputs.sort_by_key(|input| (&input.id, &input.contract));
    for input in inputs {
        hash_field(&mut hasher, "input_id", &input.id);
        hash_field(&mut hasher, "input_contract", &input.contract);
    }
    for node_id in order {
        hash_field(&mut hasher, "node_id", node_id);
        let kind = plan
            .nodes
            .iter()
            .find(|node| node.id == *node_id)
            .expect("validated node id")
            .kind
            .as_str();
        hash_field(&mut hasher, "node_kind", kind);
    }
    let mut edges = plan.edges.iter().collect::<Vec<_>>();
    edges.sort_by_key(|edge| canonical_edge_key(edge));
    for edge in edges {
        hash_field(&mut hasher, "edge", &canonical_edge_key(edge));
    }
    let mut outputs = plan.requested_outputs.iter().collect::<Vec<_>>();
    outputs.sort_by_key(|output| (&output.node_id, &output.port, &output.contract));
    for output in outputs {
        hash_field(&mut hasher, "output_node", &output.node_id);
        hash_field(&mut hasher, "output_port", &output.port);
        hash_field(&mut hasher, "output_contract", &output.contract);
    }
    ProjectPlanDigestV1(hasher.finalize().into())
}

fn hash_field(hasher: &mut Sha256, label: &str, value: &str) {
    hasher.update((label.len() as u64).to_be_bytes());
    hasher.update(label.as_bytes());
    hasher.update((value.len() as u64).to_be_bytes());
    hasher.update(value.as_bytes());
}

#[cfg(test)]
mod tests {
    use super::*;

    fn id(value: &str) -> NodeId {
        NodeId::try_new(value).unwrap()
    }

    #[test]
    fn validates_a_typed_fan_out_and_join_plan() {
        let mut builder = PipelineBuilder::new();
        let source = builder.source::<u8>(id("source")).unwrap();
        let left = builder.stage::<u8, u16>(id("left"), source).unwrap();
        let right = builder.stage::<u8, u32>(id("right"), source).unwrap();
        let joined = builder
            .join2::<u16, u32, u64>(id("joined"), left, right)
            .unwrap();
        builder.sink(id("sink"), joined).unwrap();
        let plan = builder.build().unwrap();
        assert_eq!(
            plan.topological_order()
                .iter()
                .map(NodeId::as_str)
                .collect::<Vec<_>>(),
            vec!["source", "left", "right", "joined", "sink"]
        );
    }

    #[test]
    fn ordering_is_independent_of_ready_node_insertion_order() {
        let mut builder = PipelineBuilder::new();
        let z = builder.source::<u8>(id("z")).unwrap();
        let a = builder.source::<u8>(id("a")).unwrap();
        builder.sink(id("z-sink"), z).unwrap();
        builder.sink(id("a-sink"), a).unwrap();
        let plan = builder.build().unwrap();
        assert_eq!(plan.topological_order()[0].as_str(), "a");
    }

    #[test]
    fn public_builder_rejects_duplicate_identifiers_and_inputs() {
        let mut builder = PipelineBuilder::new();
        let source = builder.source::<u8>(id("source")).unwrap();
        assert!(matches!(
            builder.source::<u16>(id("source")),
            Err(PipelineError::DuplicateNodeId)
        ));
        assert!(matches!(
            builder.join2::<u8, u8, u16>(id("join"), source, source),
            Err(PipelineError::DuplicateInput)
        ));
        assert!(NodeId::try_new("Bad").is_err());
    }

    #[test]
    fn validation_rejects_internal_cycles_and_missing_paths() {
        let mut cycle = PipelineBuilder::new();
        cycle.nodes.push(DraftNode {
            id: id("cycle"),
            role: NodeRole::Stage,
            inputs: vec![Input {
                producer: 0,
                type_id: TypeId::of::<u8>(),
            }],
            output: Some(TypeId::of::<u8>()),
        });
        assert!(matches!(cycle.build(), Err(PipelineError::DuplicateInput)));

        let mut no_sink = PipelineBuilder::new();
        no_sink.source::<u8>(id("source")).unwrap();
        assert!(matches!(no_sink.build(), Err(PipelineError::NoSink)));
    }

    #[test]
    fn validation_rejects_type_mismatch_in_defensive_path() {
        let mut builder = PipelineBuilder::new();
        builder.nodes.push(DraftNode {
            id: id("source"),
            role: NodeRole::Source,
            inputs: Vec::new(),
            output: Some(TypeId::of::<u8>()),
        });
        builder.nodes.push(DraftNode {
            id: id("sink"),
            role: NodeRole::Sink,
            inputs: vec![Input {
                producer: 0,
                type_id: TypeId::of::<u16>(),
            }],
            output: None,
        });
        assert!(matches!(builder.build(), Err(PipelineError::TypeMismatch)));
        assert_eq!(PipelineError::TypeMismatch.code(), "type_mismatch");
    }

    fn project_plan(nodes: Vec<sipi_contracts::WireProjectNodeV1>) -> WireProjectPlanV1 {
        WireProjectPlanV1 {
            schema: PROJECT_PLAN_V1_SCHEMA.to_owned(),
            project_id: "project-1".to_owned(),
            seed_hex: "00".repeat(32),
            resource_policy: sipi_contracts::WireProjectResourcePolicyV1 {
                timeout_millis: 1,
                max_work_units: 1,
                max_accounted_bytes: 1,
            },
            inputs: vec![sipi_contracts::WireProjectInputV1 {
                id: "request".to_owned(),
                contract: TRAN_RC_PULSE_REQUEST_CONTRACT_V1.to_owned(),
            }],
            nodes,
            edges: vec![sipi_contracts::WireProjectEdgeV1 {
                from: WireProjectEdgeSourceV1::ProjectInput {
                    input_id: "request".to_owned(),
                },
                to: WireProjectPortRefV1 {
                    node_id: "tran".to_owned(),
                    port: "request".to_owned(),
                },
                contract: TRAN_RC_PULSE_REQUEST_CONTRACT_V1.to_owned(),
            }],
            requested_outputs: vec![sipi_contracts::WireProjectOutputRefV1 {
                node_id: "tran".to_owned(),
                port: "result".to_owned(),
                contract: TRAN_RC_PULSE_RESULT_CONTRACT_V1.to_owned(),
            }],
        }
    }

    #[test]
    fn project_planner_accepts_a_single_supported_product_node() {
        let plan = project_plan(vec![sipi_contracts::WireProjectNodeV1 {
            id: "tran".to_owned(),
            kind: TRAN_RC_PULSE_KIND_V1.to_owned(),
        }]);
        let planned = ProjectPlannerV1::validate(plan.clone()).expect("project plan");
        assert_eq!(planned.project_id(), "project-1");
        assert_eq!(planned.seed(), &[0; 32]);
        assert_eq!(planned.topological_order()[0].kind(), TRAN_RC_PULSE_KIND_V1);
        assert_eq!(
            planned.requested_outputs()[0].contract(),
            TRAN_RC_PULSE_RESULT_CONTRACT_V1
        );
        assert_eq!(
            planned.digest(),
            ProjectPlannerV1::validate(plan)
                .expect("same plan")
                .digest()
        );
    }

    #[test]
    fn project_planner_rejects_unknown_kinds_contract_drift_and_duplicate_bindings() {
        let mut unknown = project_plan(vec![sipi_contracts::WireProjectNodeV1 {
            id: "tran".to_owned(),
            kind: "ami.vendor_runtime".to_owned(),
        }]);
        assert_eq!(
            ProjectPlannerV1::validate(unknown),
            Err(ProjectPlanError::UnknownNodeKind)
        );

        let mut mismatch = project_plan(vec![sipi_contracts::WireProjectNodeV1 {
            id: "tran".to_owned(),
            kind: TRAN_RC_PULSE_KIND_V1.to_owned(),
        }]);
        mismatch.edges[0].contract = LINK_CAUSAL_FIR_REQUEST_CONTRACT_V1.to_owned();
        assert_eq!(
            ProjectPlannerV1::validate(mismatch),
            Err(ProjectPlanError::ContractMismatch)
        );

        let mut duplicate = project_plan(vec![sipi_contracts::WireProjectNodeV1 {
            id: "tran".to_owned(),
            kind: TRAN_RC_PULSE_KIND_V1.to_owned(),
        }]);
        duplicate.edges.push(duplicate.edges[0].clone());
        assert_eq!(
            ProjectPlannerV1::validate(duplicate),
            Err(ProjectPlanError::DuplicateEdge)
        );
        unknown = project_plan(vec![sipi_contracts::WireProjectNodeV1 {
            id: "tran".to_owned(),
            kind: TRAN_RC_PULSE_KIND_V1.to_owned(),
        }]);
        unknown.requested_outputs.clear();
        assert_eq!(
            ProjectPlannerV1::validate(unknown),
            Err(ProjectPlanError::ContractBoundary)
        );
    }

    #[test]
    fn project_planner_has_deterministic_fan_out_join_and_cycle_rejection() {
        let scalar = "sipi.test.scalar.v1";
        let catalog = BTreeMap::from([
            (
                "test.source",
                NodeSignature {
                    inputs: vec![PortContract {
                        port: "request",
                        contract: "sipi.test.request.v1",
                    }],
                    outputs: vec![PortContract {
                        port: "result",
                        contract: scalar,
                    }],
                },
            ),
            (
                "test.stage",
                NodeSignature {
                    inputs: vec![PortContract {
                        port: "input",
                        contract: scalar,
                    }],
                    outputs: vec![PortContract {
                        port: "result",
                        contract: scalar,
                    }],
                },
            ),
            (
                "test.join",
                NodeSignature {
                    inputs: vec![
                        PortContract {
                            port: "left",
                            contract: scalar,
                        },
                        PortContract {
                            port: "right",
                            contract: scalar,
                        },
                    ],
                    outputs: vec![PortContract {
                        port: "result",
                        contract: scalar,
                    }],
                },
            ),
        ]);
        let mut plan = WireProjectPlanV1 {
            schema: PROJECT_PLAN_V1_SCHEMA.to_owned(),
            project_id: "fan-out".to_owned(),
            seed_hex: "01".repeat(32),
            resource_policy: sipi_contracts::WireProjectResourcePolicyV1 {
                timeout_millis: 1,
                max_work_units: 1,
                max_accounted_bytes: 1,
            },
            inputs: vec![sipi_contracts::WireProjectInputV1 {
                id: "request".to_owned(),
                contract: "sipi.test.request.v1".to_owned(),
            }],
            nodes: vec![
                sipi_contracts::WireProjectNodeV1 {
                    id: "right".to_owned(),
                    kind: "test.stage".to_owned(),
                },
                sipi_contracts::WireProjectNodeV1 {
                    id: "join".to_owned(),
                    kind: "test.join".to_owned(),
                },
                sipi_contracts::WireProjectNodeV1 {
                    id: "source".to_owned(),
                    kind: "test.source".to_owned(),
                },
                sipi_contracts::WireProjectNodeV1 {
                    id: "left".to_owned(),
                    kind: "test.stage".to_owned(),
                },
            ],
            edges: vec![
                sipi_contracts::WireProjectEdgeV1 {
                    from: WireProjectEdgeSourceV1::ProjectInput {
                        input_id: "request".to_owned(),
                    },
                    to: WireProjectPortRefV1 {
                        node_id: "source".to_owned(),
                        port: "request".to_owned(),
                    },
                    contract: "sipi.test.request.v1".to_owned(),
                },
                sipi_contracts::WireProjectEdgeV1 {
                    from: WireProjectEdgeSourceV1::NodeOutput {
                        node_id: "source".to_owned(),
                        port: "result".to_owned(),
                    },
                    to: WireProjectPortRefV1 {
                        node_id: "left".to_owned(),
                        port: "input".to_owned(),
                    },
                    contract: scalar.to_owned(),
                },
                sipi_contracts::WireProjectEdgeV1 {
                    from: WireProjectEdgeSourceV1::NodeOutput {
                        node_id: "source".to_owned(),
                        port: "result".to_owned(),
                    },
                    to: WireProjectPortRefV1 {
                        node_id: "right".to_owned(),
                        port: "input".to_owned(),
                    },
                    contract: scalar.to_owned(),
                },
                sipi_contracts::WireProjectEdgeV1 {
                    from: WireProjectEdgeSourceV1::NodeOutput {
                        node_id: "left".to_owned(),
                        port: "result".to_owned(),
                    },
                    to: WireProjectPortRefV1 {
                        node_id: "join".to_owned(),
                        port: "left".to_owned(),
                    },
                    contract: scalar.to_owned(),
                },
                sipi_contracts::WireProjectEdgeV1 {
                    from: WireProjectEdgeSourceV1::NodeOutput {
                        node_id: "right".to_owned(),
                        port: "result".to_owned(),
                    },
                    to: WireProjectPortRefV1 {
                        node_id: "join".to_owned(),
                        port: "right".to_owned(),
                    },
                    contract: scalar.to_owned(),
                },
            ],
            requested_outputs: vec![sipi_contracts::WireProjectOutputRefV1 {
                node_id: "join".to_owned(),
                port: "result".to_owned(),
                contract: scalar.to_owned(),
            }],
        };
        let planned = plan_with_catalog(plan.clone(), &catalog).expect("fan-out join");
        assert_eq!(
            planned
                .topological_order()
                .iter()
                .map(PlannedProjectNodeV1::id)
                .collect::<Vec<_>>(),
            vec!["source", "left", "right", "join"]
        );
        let first = planned.digest();
        plan.nodes.reverse();
        plan.edges.reverse();
        assert_eq!(
            first,
            plan_with_catalog(plan, &catalog)
                .expect("reordered")
                .digest()
        );

        let cycle_catalog = BTreeMap::from([(
            "test.stage",
            NodeSignature {
                inputs: vec![PortContract {
                    port: "input",
                    contract: scalar,
                }],
                outputs: vec![PortContract {
                    port: "result",
                    contract: scalar,
                }],
            },
        )]);
        let cycle = WireProjectPlanV1 {
            schema: PROJECT_PLAN_V1_SCHEMA.to_owned(),
            project_id: "cycle".to_owned(),
            seed_hex: "02".repeat(32),
            resource_policy: sipi_contracts::WireProjectResourcePolicyV1 {
                timeout_millis: 1,
                max_work_units: 1,
                max_accounted_bytes: 1,
            },
            inputs: vec![],
            nodes: vec![
                sipi_contracts::WireProjectNodeV1 {
                    id: "a".to_owned(),
                    kind: "test.stage".to_owned(),
                },
                sipi_contracts::WireProjectNodeV1 {
                    id: "b".to_owned(),
                    kind: "test.stage".to_owned(),
                },
            ],
            edges: vec![
                sipi_contracts::WireProjectEdgeV1 {
                    from: WireProjectEdgeSourceV1::NodeOutput {
                        node_id: "a".to_owned(),
                        port: "result".to_owned(),
                    },
                    to: WireProjectPortRefV1 {
                        node_id: "b".to_owned(),
                        port: "input".to_owned(),
                    },
                    contract: scalar.to_owned(),
                },
                sipi_contracts::WireProjectEdgeV1 {
                    from: WireProjectEdgeSourceV1::NodeOutput {
                        node_id: "b".to_owned(),
                        port: "result".to_owned(),
                    },
                    to: WireProjectPortRefV1 {
                        node_id: "a".to_owned(),
                        port: "input".to_owned(),
                    },
                    contract: scalar.to_owned(),
                },
            ],
            requested_outputs: vec![sipi_contracts::WireProjectOutputRefV1 {
                node_id: "a".to_owned(),
                port: "result".to_owned(),
                contract: scalar.to_owned(),
            }],
        };
        assert_eq!(
            plan_with_catalog(cycle, &cycle_catalog),
            Err(ProjectPlanError::CycleDetected)
        );
    }
}
