//! Typed IBIS [Diff Pin] complete block required keywords core (P4A-03al).
//!
//! Lifts and validates IBIS [Diff Pin] complete block required sub-keyword entries
//! (diff_pin_declaration) into typed clean-room structures.
//! Fail-closed: invalid differential pin declarations or missing required fields are strictly rejected.

use crate::diff_pin_declaration_v1::TypedDiffPinDeclarationV1;

/// Scope policy for the typed diff pin keywords core.
pub const DIFF_PIN_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03al.diff-pin-keywords-v1.typed-diff-keywords";

/// Fail-closed errors during differential pin keywords validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DiffPinKeywordsErrorV1 {
    MissingDiffPinDeclaration,
}

/// A composite typed IBIS [Diff Pin] complete block entry.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedDiffPinBlockV1 {
    diff_pin_declaration: TypedDiffPinDeclarationV1,
}

impl TypedDiffPinBlockV1 {
    pub fn try_new(
        diff_pin_declaration: TypedDiffPinDeclarationV1,
    ) -> Result<Self, DiffPinKeywordsErrorV1> {
        Ok(Self {
            diff_pin_declaration,
        })
    }

    pub fn diff_pin_declaration(&self) -> &TypedDiffPinDeclarationV1 {
        &self.diff_pin_declaration
    }
}

/// Lift one complete differential pin block entry.
pub fn lift_diff_pin_block_v1(
    diff_pin_declaration: TypedDiffPinDeclarationV1,
) -> Result<TypedDiffPinBlockV1, DiffPinKeywordsErrorV1> {
    TypedDiffPinBlockV1::try_new(diff_pin_declaration)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::diff_pin_declaration_v1::lift_diff_pin_declaration_v1;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            DIFF_PIN_KEYWORDS_POLICY_V1,
            "sipi.p4a-03al.diff-pin-keywords-v1.typed-diff-keywords"
        );
    }

    #[test]
    fn valid_diff_pin_block() {
        let diff = lift_diff_pin_declaration_v1("DP1", "DN1", Some(0.1), Some(1e-10)).unwrap();
        let block = lift_diff_pin_block_v1(diff).expect("lift");

        assert_eq!(block.diff_pin_declaration().pin_non_inv(), "DP1");
        assert_eq!(block.diff_pin_declaration().pin_inv(), "DN1");
        assert_eq!(block.diff_pin_declaration().vdiff_v().unwrap().get(), 0.1);
    }
}
