#![forbid(unsafe_code)]

//! TRAN package boundary only.
//!
//! This crate intentionally exposes no circuit representation, parser, solver,
//! analysis request, or numerical behavior until a required TRAN acceptance
//! profile and its clean-room specification are accepted.

/// The only currently observable crate state: TRAN is not implemented.
pub const FOUNDATION_STATUS: &str = "unsupported";

#[cfg(test)]
mod tests {
    use super::FOUNDATION_STATUS;

    #[test]
    fn remains_explicitly_unsupported() {
        assert_eq!(FOUNDATION_STATUS, "unsupported");
    }
}
