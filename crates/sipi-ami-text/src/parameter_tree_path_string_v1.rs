//! AMI parameter tree path-string parsing core (P4B-02b45).
//!
//! Parses a dotted path string (`"root.sub.deep"`) into path segments, the
//! input form accepted by the path-addressed tree APIs (P4B-02b8 query,
//! P4B-02b23 subtree, P4B-02b26 compose, P4B-02b27 replace, P4B-02b39 set).
//! Raw bytes are preserved: segments are not trimmed and are not validated as
//! identifiers (resolution is the downstream APIs' job). Fail-closed: an empty
//! path string and any empty segment (leading, trailing, or doubled dots) are
//! strictly rejected.

/// Scope policy for the parameter tree path-string parsing core.
pub const PARAMETER_TREE_PATH_STRING_POLICY_V1: &str =
    "sipi.p4b-02b45.parameter-tree-path-string-v1.dotted-path-parse";

/// Fail-closed errors during path-string parsing.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterTreePathParseErrorV1 {
    /// The path string is empty.
    EmptyPath,
    /// A segment between dots is empty (leading, trailing, or doubled dots).
    EmptySegment,
}

/// Parse `path` into non-empty segments split on `.`.
///
/// Fails closed on an empty path string or any empty segment. Raw bytes are
/// preserved (no trimming, no identifier validation).
pub fn parse_parameter_tree_path_string_v1(
    path: &str,
) -> Result<Vec<String>, ParameterTreePathParseErrorV1> {
    if path.is_empty() {
        return Err(ParameterTreePathParseErrorV1::EmptyPath);
    }
    let mut segments = Vec::new();
    for segment in path.split('.') {
        if segment.is_empty() {
            return Err(ParameterTreePathParseErrorV1::EmptySegment);
        }
        segments.push(segment.to_string());
    }
    Ok(segments)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_basic_path() {
        let segments = parse_parameter_tree_path_string_v1("a.b.c").expect("parsed");
        assert_eq!(
            segments,
            vec!["a".to_string(), "b".to_string(), "c".to_string()]
        );
    }

    #[test]
    fn parses_single_segment() {
        let segments = parse_parameter_tree_path_string_v1("a").expect("parsed");
        assert_eq!(segments, vec!["a".to_string()]);
    }

    #[test]
    fn empty_path_fails_closed() {
        let error = parse_parameter_tree_path_string_v1("").unwrap_err();
        assert_eq!(error, ParameterTreePathParseErrorV1::EmptyPath);
    }

    #[test]
    fn leading_dot_fails_closed() {
        let error = parse_parameter_tree_path_string_v1(".a").unwrap_err();
        assert_eq!(error, ParameterTreePathParseErrorV1::EmptySegment);
    }

    #[test]
    fn trailing_dot_fails_closed() {
        let error = parse_parameter_tree_path_string_v1("a.").unwrap_err();
        assert_eq!(error, ParameterTreePathParseErrorV1::EmptySegment);
    }

    #[test]
    fn double_dot_fails_closed() {
        let error = parse_parameter_tree_path_string_v1("a..b").unwrap_err();
        assert_eq!(error, ParameterTreePathParseErrorV1::EmptySegment);
    }

    #[test]
    fn dots_only_fails_closed() {
        let error = parse_parameter_tree_path_string_v1("..").unwrap_err();
        assert_eq!(error, ParameterTreePathParseErrorV1::EmptySegment);
    }

    #[test]
    fn raw_segments_are_preserved() {
        let segments = parse_parameter_tree_path_string_v1("root.my-gain").expect("parsed");
        assert_eq!(
            segments,
            vec!["root".to_string(), "my-gain".to_string()]
        );
    }
}
