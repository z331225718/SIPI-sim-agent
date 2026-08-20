//! AMI parameter profile assembly core (P4B-02b44).
//!
//! Assembles a strict parameter profile from a tree list, a defaults map, and a
//! reserved-name set in one fail-closed pass:
//!   1. extract typed parameters from every tree and merge by name
//!      (P4B-02b42, reused verbatim);
//!   2. fill names missing from the merged map with typed defaults
//!      (each default must be an AMI form `[type, value]` validated per
//!      P4B-02b1 `AmiParameterValueV1::try_new`); names already present are
//!      skipped;
//!   3. reject any assembled parameter name in the reserved set
//!      (P4B-02b43 semantics applied strictly).
//!
//! Fail-closed at every step; an empty defaults map is allowed (no filling).

use std::collections::{BTreeMap, BTreeSet};

use crate::{
    AmiParameterTreeV1, AmiParameterTypeV1, AmiParameterValueErrorV1, AmiParameterValueV1,
    ParameterTreeMultiFormErrorV1, extract_typed_parameter_forms_multi_v1,
};

/// Scope policy for the parameter profile assembly core.
pub const PARAMETER_PROFILE_ASSEMBLY_POLICY_V1: &str =
    "sipi.p4b-02b44.parameter-profile-assembly-v1.strict-profile-assembly";

/// Fail-closed errors during parameter profile assembly.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterProfileAssemblyErrorV1 {
    /// The multi-tree extraction stage (P4B-02b42) failed.
    Extraction(ParameterTreeMultiFormErrorV1),
    /// A default does not carry exactly `[type, value]` tokens.
    DefaultNotTypedForm { name: String, token_count: usize },
    /// A default's value violates its declared type rule.
    InvalidDefaultValue {
        name: String,
        error: AmiParameterValueErrorV1,
    },
    /// An assembled parameter name is in the reserved set.
    ReservedNameUsed(String),
    /// The reserved-name set is empty; strict assembly cannot proceed.
    EmptyReservedSet,
}

/// Outcome of a successful profile assembly pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileAssemblyV1 {
    leaves_consumed: usize,
    defaults_applied: usize,
    defaults_skipped: usize,
    parameters: BTreeMap<String, AmiParameterValueV1>,
}

impl ParameterProfileAssemblyV1 {
    pub fn leaves_consumed(&self) -> usize {
        self.leaves_consumed
    }

    pub fn defaults_applied(&self) -> usize {
        self.defaults_applied
    }

    pub fn defaults_skipped(&self) -> usize {
        self.defaults_skipped
    }

    pub fn parameters(&self) -> &BTreeMap<String, AmiParameterValueV1> {
        &self.parameters
    }
}

/// Assemble a strict parameter profile from `trees`, `defaults`, `reserved`.
///
/// Steps (fail-closed): multi-tree typed-form extraction (P4B-02b42), typed
/// defaults fill for missing names, and reserved-name rejection. An empty
/// defaults map means no filling; an empty reserved set is a caller error.
pub fn assemble_parameter_profile_v1(
    trees: &[AmiParameterTreeV1],
    defaults: &BTreeMap<String, Vec<String>>,
    reserved: &BTreeSet<String>,
) -> Result<ParameterProfileAssemblyV1, ParameterProfileAssemblyErrorV1> {
    if reserved.is_empty() {
        return Err(ParameterProfileAssemblyErrorV1::EmptyReservedSet);
    }
    let extracted = extract_typed_parameter_forms_multi_v1(trees)
        .map_err(ParameterProfileAssemblyErrorV1::Extraction)?;
    let mut parameters = extracted.parameters().clone();
    let leaves_consumed = extracted.leaves_consumed();

    let mut defaults_applied = 0usize;
    let mut defaults_skipped = 0usize;
    for (name, tokens) in defaults {
        if parameters.contains_key(name) {
            defaults_skipped += 1;
            continue;
        }
        if tokens.len() != 2 {
            return Err(ParameterProfileAssemblyErrorV1::DefaultNotTypedForm {
                name: name.clone(),
                token_count: tokens.len(),
            });
        }
        let type_token = &tokens[0];
        let value_token = &tokens[1];
        if AmiParameterTypeV1::from_token(type_token).is_none() {
            return Err(ParameterProfileAssemblyErrorV1::InvalidDefaultValue {
                name: name.clone(),
                error: AmiParameterValueErrorV1::UnknownTypeToken,
            });
        }
        let parameter = AmiParameterValueV1::try_new(name, type_token, value_token)
            .map_err(|error| match error {
                AmiParameterValueErrorV1::EmptyName
                | AmiParameterValueErrorV1::UnknownTypeToken => {
                    unreachable!(
                        "structurally impossible: default names are map keys and the                          type token was just parsed"
                    )
                }
                other => ParameterProfileAssemblyErrorV1::InvalidDefaultValue {
                    name: name.clone(),
                    error: other,
                },
            })?;
        parameters.insert(name.clone(), parameter);
        defaults_applied += 1;
    }

    for name in parameters.keys() {
        if reserved.contains(name) {
            return Err(ParameterProfileAssemblyErrorV1::ReservedNameUsed(
                name.clone(),
            ));
        }
    }

    Ok(ParameterProfileAssemblyV1 {
        leaves_consumed,
        defaults_applied,
        defaults_skipped,
        parameters,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AmiParameterTreeNodeV1;

    fn leaf(name: &str, tokens: &[&str]) -> AmiParameterTreeNodeV1 {
        AmiParameterTreeNodeV1::Leaf {
            name: name.to_string(),
            value_tokens: tokens.iter().map(|s| s.to_string()).collect(),
        }
    }

    fn branch(name: &str, children: Vec<AmiParameterTreeNodeV1>) -> AmiParameterTreeNodeV1 {
        AmiParameterTreeNodeV1::Branch {
            name: name.to_string(),
            children: children
                .into_iter()
                .map(|c| (c.name().to_string(), c))
                .collect(),
        }
    }

    fn tree(node: AmiParameterTreeNodeV1) -> AmiParameterTreeV1 {
        AmiParameterTreeV1::new("root", node)
    }

    fn defaults_of(pairs: &[(&str, &[&str])]) -> BTreeMap<String, Vec<String>> {
        pairs
            .iter()
            .map(|(name, tokens)| {
                (
                    name.to_string(),
                    tokens.iter().map(|s| s.to_string()).collect(),
                )
            })
            .collect()
    }

    fn reserved_of(names: &[&str]) -> BTreeSet<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn assembles_full_profile() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let t2 = tree(branch("root", vec![leaf("enabled", &["Boolean", "True"])]));
        let result = assemble_parameter_profile_v1(
            &[t1, t2],
            &defaults_of(&[("steps", &["Integer", "7"])]),
            &reserved_of(&["Reserved_Parameters"]),
        )
        .expect("assembled");
        assert_eq!(result.leaves_consumed(), 2);
        assert_eq!(result.defaults_applied(), 1);
        assert_eq!(result.defaults_skipped(), 0);
        assert_eq!(result.parameters().len(), 3);
        let steps = result.parameters().get("steps").expect("steps");
        assert_eq!(steps.parameter_type(), AmiParameterTypeV1::Integer);
        assert_eq!(steps.value_token(), "7");
    }

    #[test]
    fn default_skipped_when_name_present() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let result = assemble_parameter_profile_v1(
            &[t1],
            &defaults_of(&[("gain", &["Float", "9.9"])]),
            &reserved_of(&["Reserved_Parameters"]),
        )
        .expect("assembled");
        assert_eq!(result.defaults_applied(), 0);
        assert_eq!(result.defaults_skipped(), 1);
        let gain = result.parameters().get("gain").expect("gain");
        assert_eq!(gain.value_token(), "0.5");
    }

    #[test]
    fn malformed_default_tokens_fail_closed() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let error = assemble_parameter_profile_v1(
            &[t1],
            &defaults_of(&[("steps", &["Integer"])]),
            &reserved_of(&["Reserved_Parameters"]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterProfileAssemblyErrorV1::DefaultNotTypedForm {
                name: "steps".to_string(),
                token_count: 1,
            }
        );
    }

    #[test]
    fn invalid_default_value_fails_closed() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let error = assemble_parameter_profile_v1(
            &[t1],
            &defaults_of(&[("steps", &["Integer", "x1"])]),
            &reserved_of(&["Reserved_Parameters"]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterProfileAssemblyErrorV1::InvalidDefaultValue {
                name: "steps".to_string(),
                error: AmiParameterValueErrorV1::InvalidInteger,
            }
        );
    }

    #[test]
    fn reserved_name_used_fails_closed() {
        let t1 = tree(branch(
            "root",
            vec![
                leaf("gain", &["Float", "0.5"]),
                leaf("Reserved_Parameters", &["Integer", "1"]),
            ],
        ));
        let error = assemble_parameter_profile_v1(
            &[t1],
            &defaults_of(&[]),
            &reserved_of(&["Reserved_Parameters"]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterProfileAssemblyErrorV1::ReservedNameUsed("Reserved_Parameters".to_string())
        );
    }

    #[test]
    fn empty_reserved_set_fails_closed() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let error =
            assemble_parameter_profile_v1(&[t1], &defaults_of(&[]), &reserved_of(&[])).unwrap_err();
        assert_eq!(error, ParameterProfileAssemblyErrorV1::EmptyReservedSet);
    }

    #[test]
    fn extraction_error_is_wrapped() {
        let t1 = tree(branch("root", vec![leaf("steps", &["Real", "7"])]));
        let error = assemble_parameter_profile_v1(
            &[t1],
            &defaults_of(&[]),
            &reserved_of(&["Reserved_Parameters"]),
        )
        .unwrap_err();
        assert_eq!(
            error,
            ParameterProfileAssemblyErrorV1::Extraction(ParameterTreeMultiFormErrorV1::TreeError(
                0,
                crate::ParameterTreeTypedFormErrorV1::UnknownTypeToken {
                    leaf: "steps".to_string(),
                    token: "Real".to_string(),
                }
            ))
        );
    }

    #[test]
    fn empty_defaults_map_is_allowed() {
        let t1 = tree(branch("root", vec![leaf("gain", &["Float", "0.5"])]));
        let result = assemble_parameter_profile_v1(
            &[t1],
            &defaults_of(&[]),
            &reserved_of(&["Reserved_Parameters"]),
        )
        .expect("assembled");
        assert_eq!(result.defaults_applied(), 0);
        assert_eq!(result.parameters().len(), 1);
    }
}
