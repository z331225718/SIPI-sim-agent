//! AMI parameter tree JSON Serde serialization / deserialization core (P4B-02b19).
//!
//! Serializes typed `AmiParameterTreeV1` hierarchies (P4B-02b7) to JSON Value/string
//! (`serialize_parameter_trees_v1`) and deserializes JSON back into `AmiParameterTreeV1`
//! (`deserialize_parameter_trees_v1`).
//! Fail-closed: empty tree lists or malformed JSON tree structures are strictly rejected.

use serde_json::{Value, json};
use std::collections::BTreeMap;

use crate::parameter_trees_v1::{AmiParameterTreeNodeV1, AmiParameterTreeV1};

/// Scope policy for the parameter tree serde core.
pub const PARAMETER_TREE_SERDE_POLICY_V1: &str =
    "sipi.p4b-02b19.parameter-tree-serde-v1.tree-json-serde";

/// Fail-closed errors during AMI parameter tree JSON Serde operations.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeSerdeErrorV1 {
    EmptyTreeList,
    InvalidJsonStructure(String),
}

fn node_to_json(node: &AmiParameterTreeNodeV1) -> Value {
    match node {
        AmiParameterTreeNodeV1::Branch { name, children } => {
            let child_map: BTreeMap<String, Value> = children
                .iter()
                .map(|(k, v)| (k.clone(), node_to_json(v)))
                .collect();
            json!({
                "kind": "branch",
                "name": name,
                "children": child_map,
            })
        }
        AmiParameterTreeNodeV1::Leaf { name, value_tokens } => {
            json!({
                "kind": "leaf",
                "name": name,
                "value_tokens": value_tokens,
            })
        }
    }
}

fn json_to_node(val: &Value) -> Result<AmiParameterTreeNodeV1, ParameterTreeSerdeErrorV1> {
    let kind = val.get("kind").and_then(|v| v.as_str()).ok_or_else(|| {
        ParameterTreeSerdeErrorV1::InvalidJsonStructure("missing kind field".to_string())
    })?;
    let name = val.get("name").and_then(|v| v.as_str()).ok_or_else(|| {
        ParameterTreeSerdeErrorV1::InvalidJsonStructure("missing name field".to_string())
    })?;

    match kind {
        "branch" => {
            let children_obj =
                val.get("children")
                    .and_then(|v| v.as_object())
                    .ok_or_else(|| {
                        ParameterTreeSerdeErrorV1::InvalidJsonStructure(
                            "missing children map".to_string(),
                        )
                    })?;
            let mut children = BTreeMap::new();
            for (k, v) in children_obj {
                let child_node = json_to_node(v)?;
                children.insert(k.clone(), child_node);
            }
            Ok(AmiParameterTreeNodeV1::Branch {
                name: name.to_string(),
                children,
            })
        }
        "leaf" => {
            let tokens_arr = val
                .get("value_tokens")
                .and_then(|v| v.as_array())
                .ok_or_else(|| {
                    ParameterTreeSerdeErrorV1::InvalidJsonStructure(
                        "missing value_tokens list".to_string(),
                    )
                })?;
            let mut value_tokens = Vec::new();
            for t in tokens_arr {
                let s = t.as_str().ok_or_else(|| {
                    ParameterTreeSerdeErrorV1::InvalidJsonStructure("non-string token".to_string())
                })?;
                value_tokens.push(s.to_string());
            }
            Ok(AmiParameterTreeNodeV1::Leaf {
                name: name.to_string(),
                value_tokens,
            })
        }
        other => Err(ParameterTreeSerdeErrorV1::InvalidJsonStructure(format!(
            "unknown node kind: {other}"
        ))),
    }
}

/// Serialize a list of parameter trees to a JSON Value.
pub fn serialize_parameter_trees_v1(
    trees: &[AmiParameterTreeV1],
) -> Result<Value, ParameterTreeSerdeErrorV1> {
    if trees.is_empty() {
        return Err(ParameterTreeSerdeErrorV1::EmptyTreeList);
    }

    let tree_values: Vec<Value> = trees
        .iter()
        .map(|t| {
            json!({
                "root_name": t.root_name(),
                "root_node": node_to_json(t.root_node()),
            })
        })
        .collect();

    Ok(json!({
        "policy": PARAMETER_TREE_SERDE_POLICY_V1,
        "tree_count": trees.len(),
        "trees": tree_values,
    }))
}

/// Deserialize a JSON Value back into a list of parameter trees.
pub fn deserialize_parameter_trees_v1(
    val: &Value,
) -> Result<Vec<AmiParameterTreeV1>, ParameterTreeSerdeErrorV1> {
    let trees_arr = val.get("trees").and_then(|v| v.as_array()).ok_or_else(|| {
        ParameterTreeSerdeErrorV1::InvalidJsonStructure("missing trees list".to_string())
    })?;

    if trees_arr.is_empty() {
        return Err(ParameterTreeSerdeErrorV1::EmptyTreeList);
    }

    let mut trees = Vec::new();
    for t_val in trees_arr {
        let rname = t_val
            .get("root_name")
            .and_then(|v| v.as_str())
            .ok_or_else(|| {
                ParameterTreeSerdeErrorV1::InvalidJsonStructure(
                    "missing root_name field".to_string(),
                )
            })?;
        let rnode_val = t_val.get("root_node").ok_or_else(|| {
            ParameterTreeSerdeErrorV1::InvalidJsonStructure("missing root_node field".to_string())
        })?;
        let rnode = json_to_node(rnode_val)?;
        trees.push(AmiParameterTreeV1::new(rname, rnode));
    }

    Ok(trees)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parameter_trees_v1::build_parameter_trees_v1;
    use crate::{ParseLimitsV1, parse_ami_text_v1};

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(1024, 16, 64, 128).unwrap()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            PARAMETER_TREE_SERDE_POLICY_V1,
            "sipi.p4b-02b19.parameter-tree-serde-v1.tree-json-serde"
        );
    }

    #[test]
    fn serde_roundtrip_preserves_tree_hierarchy() {
        let doc = parse_ami_text_v1(
            b"(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            limits(),
        )
        .expect("parse");
        let trees = build_parameter_trees_v1(&doc).expect("build");

        let serialized = serialize_parameter_trees_v1(&trees).expect("serialize");
        let deserialized = deserialize_parameter_trees_v1(&serialized).expect("deserialize");

        assert_eq!(trees, deserialized);
    }

    #[test]
    fn rejects_empty_tree_list() {
        assert_eq!(
            serialize_parameter_trees_v1(&[]),
            Err(ParameterTreeSerdeErrorV1::EmptyTreeList)
        );
    }

    #[test]
    fn rejects_invalid_json_structure() {
        let bad_json = json!({ "trees": [{ "root_name": "root" }] });
        assert!(matches!(
            deserialize_parameter_trees_v1(&bad_json),
            Err(ParameterTreeSerdeErrorV1::InvalidJsonStructure(_))
        ));
    }
}
