//! AMI parameter tree path relation core (P4B-02b65).
//!
//! Classifies the relation between two canonical paths (`[root_name, ...]`)
//! of an `AmiParameterTreeV1`: identical, ancestor (one path is a proper
//! prefix of the other), descendant (the inverse), or disjoint. This is a
//! primitive for subtree operations and diff/compose relations. Fail-closed:
//! an empty path is strictly rejected.

/// Scope policy for the path relation core.
pub const PARAMETER_TREE_PATH_RELATION_POLICY_V1: &str =
    "sipi.p4b-02b65.parameter-tree-path-relation-v1.path-classification";

/// Fail-closed errors during path relation classification.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreePathRelationErrorV1 {
    /// Either path is empty.
    EmptyPath,
}

/// Relation of path `a` to path `b`.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ParameterTreePathRelationV1 {
    /// The two paths are equal.
    Identical,
    /// Path `a` is a proper prefix of path `b`.
    Ancestor,
    /// Path `b` is a proper prefix of path `a`.
    Descendant,
    /// Neither path is a prefix of the other.
    Disjoint,
}

/// Classify the relation of canonical path `a` to canonical path `b`.
///
/// Fails closed on an empty path.
pub fn classify_parameter_tree_path_relation_v1(
    a: &[String],
    b: &[String],
) -> Result<ParameterTreePathRelationV1, ParameterTreePathRelationErrorV1> {
    if a.is_empty() || b.is_empty() {
        return Err(ParameterTreePathRelationErrorV1::EmptyPath);
    }
    let common = a.iter().zip(b.iter()).take_while(|(x, y)| x == y).count();
    if common == a.len() && common == b.len() {
        return Ok(ParameterTreePathRelationV1::Identical);
    }
    if common == a.len() {
        return Ok(ParameterTreePathRelationV1::Ancestor);
    }
    if common == b.len() {
        return Ok(ParameterTreePathRelationV1::Descendant);
    }
    Ok(ParameterTreePathRelationV1::Disjoint)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn path(segments: &[&str]) -> Vec<String> {
        segments.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn identical_paths_are_identical() {
        let a = path(&["root", "sub", "deep"]);
        let b = path(&["root", "sub", "deep"]);
        assert_eq!(
            classify_parameter_tree_path_relation_v1(&a, &b).expect("relation"),
            ParameterTreePathRelationV1::Identical
        );
    }

    #[test]
    fn proper_prefix_is_ancestor() {
        let a = path(&["root", "sub"]);
        let b = path(&["root", "sub", "deep"]);
        assert_eq!(
            classify_parameter_tree_path_relation_v1(&a, &b).expect("relation"),
            ParameterTreePathRelationV1::Ancestor
        );
    }

    #[test]
    fn longer_path_is_descendant() {
        let a = path(&["root", "sub", "deep"]);
        let b = path(&["root", "sub"]);
        assert_eq!(
            classify_parameter_tree_path_relation_v1(&a, &b).expect("relation"),
            ParameterTreePathRelationV1::Descendant
        );
    }

    #[test]
    fn diverging_paths_are_disjoint() {
        let a = path(&["root", "a"]);
        let b = path(&["root", "b"]);
        assert_eq!(
            classify_parameter_tree_path_relation_v1(&a, &b).expect("relation"),
            ParameterTreePathRelationV1::Disjoint
        );
    }

    #[test]
    fn deep_diverging_paths_are_disjoint() {
        let a = path(&["root", "a", "x"]);
        let b = path(&["root", "b", "y"]);
        assert_eq!(
            classify_parameter_tree_path_relation_v1(&a, &b).expect("relation"),
            ParameterTreePathRelationV1::Disjoint
        );
    }

    #[test]
    fn empty_path_fails_closed() {
        let a = path(&[]);
        let b = path(&["root"]);
        let error = classify_parameter_tree_path_relation_v1(&a, &b).unwrap_err();
        assert_eq!(error, ParameterTreePathRelationErrorV1::EmptyPath);
    }
}
