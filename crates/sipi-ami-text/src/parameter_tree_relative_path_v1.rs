//! AMI parameter tree relative path core (P4B-02b66).
//!
//! Derives the relative path of a canonical path with respect to one of its
//! ancestors: the suffix segments after the ancestor prefix. This is the
//! subtree-relative primitive (e.g. addressing inside an extracted subtree,
//! P4B-02b23). Fail-closed: an empty path, an ancestor that is not a proper
//! prefix of the path, and an equal path (empty suffix) are strictly rejected.

/// Scope policy for the relative path core.
pub const PARAMETER_TREE_RELATIVE_PATH_POLICY_V1: &str =
    "sipi.p4b-02b66.parameter-tree-relative-path-v1.suffix-derivation";

/// Fail-closed errors during relative path derivation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeRelativePathErrorV1 {
    /// Either path is empty.
    EmptyPath,
    /// The ancestor is not a proper prefix of the path.
    NotAncestor,
    /// The two paths are equal; the relative suffix is empty.
    EmptySuffix,
}

/// Derive the relative path of `path` with respect to `ancestor`.
///
/// Returns the suffix segments after the ancestor prefix. Fails closed on an
/// empty path, a non-ancestor, or equal paths.
pub fn relative_parameter_tree_path_v1(
    ancestor: &[String],
    path: &[String],
) -> Result<Vec<String>, ParameterTreeRelativePathErrorV1> {
    if ancestor.is_empty() || path.is_empty() {
        return Err(ParameterTreeRelativePathErrorV1::EmptyPath);
    }
    if ancestor.len() >= path.len() {
        if ancestor == path {
            return Err(ParameterTreeRelativePathErrorV1::EmptySuffix);
        }
        return Err(ParameterTreeRelativePathErrorV1::NotAncestor);
    }
    for (a, p) in ancestor.iter().zip(path.iter()) {
        if a != p {
            return Err(ParameterTreeRelativePathErrorV1::NotAncestor);
        }
    }
    Ok(path[ancestor.len()..].to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn path(segments: &[&str]) -> Vec<String> {
        segments.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn derives_simple_suffix() {
        let ancestor = path(&["root", "sub"]);
        let target = path(&["root", "sub", "deep"]);
        let relative = relative_parameter_tree_path_v1(&ancestor, &target).expect("relative");
        assert_eq!(relative, path(&["deep"]));
    }

    #[test]
    fn derives_multi_segment_suffix() {
        let ancestor = path(&["root"]);
        let target = path(&["root", "a", "b"]);
        let relative = relative_parameter_tree_path_v1(&ancestor, &target).expect("relative");
        assert_eq!(relative, path(&["a", "b"]));
    }

    #[test]
    fn equal_paths_fail_closed() {
        let ancestor = path(&["root", "a"]);
        let target = path(&["root", "a"]);
        let error = relative_parameter_tree_path_v1(&ancestor, &target).unwrap_err();
        assert_eq!(error, ParameterTreeRelativePathErrorV1::EmptySuffix);
    }

    #[test]
    fn non_ancestor_fails_closed() {
        let ancestor = path(&["root", "a"]);
        let target = path(&["root", "b", "x"]);
        let error = relative_parameter_tree_path_v1(&ancestor, &target).unwrap_err();
        assert_eq!(error, ParameterTreeRelativePathErrorV1::NotAncestor);
    }

    #[test]
    fn empty_path_fails_closed() {
        let ancestor = path(&[]);
        let target = path(&["root"]);
        let error = relative_parameter_tree_path_v1(&ancestor, &target).unwrap_err();
        assert_eq!(error, ParameterTreeRelativePathErrorV1::EmptyPath);
    }

    #[test]
    fn longer_ancestor_fails_closed() {
        let ancestor = path(&["root", "a", "b"]);
        let target = path(&["root", "a"]);
        let error = relative_parameter_tree_path_v1(&ancestor, &target).unwrap_err();
        assert_eq!(error, ParameterTreeRelativePathErrorV1::NotAncestor);
    }
}
