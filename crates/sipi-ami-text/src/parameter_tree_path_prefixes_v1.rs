//! AMI parameter tree path prefix enumeration core (P4B-02b68).
//!
//! Enumerates every non-empty prefix of a canonical path
//! (`[root_name, ...]`): the ancestor chain `[0..1], [0..2], ..., [0..n]`
//! (the last entry is the path itself). This is the ancestor-chain primitive
//! for validation and traversal. Fail-closed: an empty path is strictly
//! rejected.

/// Scope policy for the path prefix enumeration core.
pub const PARAMETER_TREE_PATH_PREFIXES_POLICY_V1: &str =
    "sipi.p4b-02b68.parameter-tree-path-prefixes-v1.ancestor-chain-enumeration";

/// Fail-closed errors during path prefix enumeration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreePathPrefixErrorV1 {
    /// The path is empty.
    EmptyPath,
}

/// Enumerate every non-empty prefix of canonical path `path`.
///
/// Returns `[path[0..1], path[0..2], ..., path[0..n]]` (the last entry is the
/// path itself). Fails closed on an empty path.
pub fn enumerate_parameter_tree_path_prefixes_v1(
    path: &[String],
) -> Result<Vec<Vec<String>>, ParameterTreePathPrefixErrorV1> {
    if path.is_empty() {
        return Err(ParameterTreePathPrefixErrorV1::EmptyPath);
    }
    let mut prefixes = Vec::with_capacity(path.len());
    for length in 1..=path.len() {
        prefixes.push(path[..length].to_vec());
    }
    Ok(prefixes)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn path(segments: &[&str]) -> Vec<String> {
        segments.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn enumerates_ancestor_chain_of_deep_path() {
        let p = path(&["root", "sub", "deep"]);
        let prefixes = enumerate_parameter_tree_path_prefixes_v1(&p).expect("prefixes");
        assert_eq!(
            prefixes,
            vec![
                path(&["root"]),
                path(&["root", "sub"]),
                path(&["root", "sub", "deep"]),
            ]
        );
    }

    #[test]
    fn enumerates_medium_path() {
        let p = path(&["root", "sub"]);
        let prefixes = enumerate_parameter_tree_path_prefixes_v1(&p).expect("prefixes");
        assert_eq!(
            prefixes,
            vec![path(&["root"]), path(&["root", "sub"])]
        );
    }

    #[test]
    fn single_segment_has_one_prefix() {
        let p = path(&["root"]);
        let prefixes = enumerate_parameter_tree_path_prefixes_v1(&p).expect("prefixes");
        assert_eq!(prefixes, vec![path(&["root"])]);
    }

    #[test]
    fn empty_path_fails_closed() {
        let p = path(&[]);
        let error = enumerate_parameter_tree_path_prefixes_v1(&p).unwrap_err();
        assert_eq!(error, ParameterTreePathPrefixErrorV1::EmptyPath);
    }
}
