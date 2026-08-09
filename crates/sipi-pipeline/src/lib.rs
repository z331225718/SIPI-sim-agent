#![forbid(unsafe_code)]

//! A non-executing, statically typed plan DAG.
//!
//! A plan carries only node identities, edge topology, and in-process Rust
//! `TypeId` checks. It never stores values or runs callbacks.

use std::{
    any::TypeId,
    collections::{BTreeSet, VecDeque},
    marker::PhantomData,
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
}
