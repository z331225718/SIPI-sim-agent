//! AMI parameter tree longest common path prefix core (P4B-02b67).
//!
//! Computes the longest common prefix of two canonical paths
//! (`[root_name, ...]`): the leading segments shared by both paths. This is
//! the common-ancestor primitive for diff/compose and path algebra. Fail-closed:
//! an empty path is strictly rejected; a totally disjoint pair yields an empty
//! prefix (a valid result).

/// Scope policy for the longest common prefix core.
pub const PARAMETER_TREE_LONGEST_COMMON_PREFIX_POLICY_V1: &str =
    "sipi.p4b-02b67.parameter-tree-longest-common-prefix-v1.path-lcp";

/// Fail-closed errors during longest common prefix computation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreeLcpErrorV1 {
    /// Either path is empty.
    EmptyPath,
}

/// Compute the longest common prefix of canonical paths `a` and `b`.
///
/// Returns the shared leading segments (possibly empty for totally disjoint
/// paths). Fails closed on an empty path.
pub fn longest_common_path_prefix_v1(
    a: &[String],
    b: &[String],
) -> Result<Vec<String>, ParameterTreeLcpErrorV1> {
    if a.is_empty() || b.is_empty() {
        return Err(ParameterTreeLcpErrorV1::EmptyPath);
    }
    let common = a.iter().zip(b.iter()).take_while(|(x, y)| x == y).count();
    Ok(a[..common].to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn path(segments: &[&str]) -> Vec<String> {
        segments.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn computes_shared_prefix() {
        let a = path(&["root", "sub", "deep"]);
        let b = path(&["root", "sub", "other"]);
        let prefix = longest_common_path_prefix_v1(&a, &b).expect("prefix");
        assert_eq!(prefix, path(&["root", "sub"]));
    }

    #[test]
    fn identical_paths_yield_full_prefix() {
        let a = path(&["root", "sub", "deep"]);
        let b = path(&["root", "sub", "deep"]);
        let prefix = longest_common_path_prefix_v1(&a, &b).expect("prefix");
        assert_eq!(prefix, path(&["root", "sub", "deep"]));
    }

    #[test]
    fn disjoint_paths_yield_empty_prefix() {
        let a = path(&["a", "x"]);
        let b = path(&["b", "y"]);
        let prefix = longest_common_path_prefix_v1(&a, &b).expect("prefix");
        assert!(prefix.is_empty());
    }

    #[test]
    fn one_path_contained_yields_shorter() {
        let a = path(&["root", "sub"]);
        let b = path(&["root", "sub", "deep"]);
        let prefix = longest_common_path_prefix_v1(&a, &b).expect("prefix");
        assert_eq!(prefix, path(&["root", "sub"]));
    }

    #[test]
    fn empty_path_fails_closed() {
        let a = path(&[]);
        let b = path(&["root"]);
        let error = longest_common_path_prefix_v1(&a, &b).unwrap_err();
        assert_eq!(error, ParameterTreeLcpErrorV1::EmptyPath);
    }
}
