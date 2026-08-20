//! AMI parameter tree path join core (P4B-02b56).
//!
//! Joins path segments into a dotted path string (`"root.sub.deep"`), the
//! inverse of the path-string parser (P4B-02b45). Raw bytes are preserved:
//! segments are not trimmed and not validated as identifiers. Fail-closed: an
//! empty segment list is strictly rejected.

/// Scope policy for the parameter tree path join core.
pub const PARAMETER_TREE_PATH_JOIN_POLICY_V1: &str =
    "sipi.p4b-02b56.parameter-tree-path-join-v1.dotted-path-join";

/// Fail-closed errors during path joining.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreePathJoinErrorV1 {
    /// The segment list is empty.
    EmptyPath,
}

/// Join `segments` into one dotted path string.
///
/// Fails closed on an empty segment list. Raw bytes are preserved (no
/// trimming, no identifier validation) — the exact inverse of
/// `parse_parameter_tree_path_string_v1`.
pub fn join_parameter_tree_path_v1(segments: &[&str]) -> Result<String, ParameterTreePathJoinErrorV1> {
    if segments.is_empty() {
        return Err(ParameterTreePathJoinErrorV1::EmptyPath);
    }
    let mut path = String::new();
    for (index, segment) in segments.iter().enumerate() {
        if index > 0 {
            path.push('.');
        }
        path.push_str(segment);
    }
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn joins_basic_path() {
        let path = join_parameter_tree_path_v1(&["root", "gain"]).expect("joined");
        assert_eq!(path, "root.gain");
    }

    #[test]
    fn joins_deep_path() {
        let path = join_parameter_tree_path_v1(&["root", "sub", "deep"]).expect("joined");
        assert_eq!(path, "root.sub.deep");
    }

    #[test]
    fn joins_single_segment() {
        let path = join_parameter_tree_path_v1(&["a"]).expect("joined");
        assert_eq!(path, "a");
    }

    #[test]
    fn empty_segments_fail_closed() {
        let error = join_parameter_tree_path_v1(&[]).unwrap_err();
        assert_eq!(error, ParameterTreePathJoinErrorV1::EmptyPath);
    }

    #[test]
    fn raw_segments_are_preserved() {
        let path = join_parameter_tree_path_v1(&["my-gain", "x y"]).expect("joined");
        assert_eq!(path, "my-gain.x y");
    }
}
