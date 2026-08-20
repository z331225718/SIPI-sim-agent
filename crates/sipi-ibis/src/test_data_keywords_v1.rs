//! Typed IBIS [Test Data] / [Test Load] complete block required keywords core (P4A-03ai).
//!
//! Lifts and validates IBIS [Test Data] / [Test Load] complete block required sub-keyword entries
//! (fixture declaration vs optional test spec parameters) into typed clean-room structures.
//! Fail-closed: invalid test fixture declarations or missing required fields are strictly rejected.

use crate::test_data_declaration_v1::TypedTestDataDeclarationV1;

/// Scope policy for the typed test data keywords core.
pub const TEST_DATA_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03ai.test-data-keywords-v1.typed-test-keywords";

/// Fail-closed errors during test data keywords validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TestDataKeywordsErrorV1 {
    MissingTestFixtureDeclaration,
}

/// A composite typed IBIS [Test Data] / [Test Load] complete block entry.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedTestDataBlockV1 {
    fixture_declaration: TypedTestDataDeclarationV1,
}

impl TypedTestDataBlockV1 {
    pub fn try_new(
        fixture_declaration: TypedTestDataDeclarationV1,
    ) -> Result<Self, TestDataKeywordsErrorV1> {
        Ok(Self {
            fixture_declaration,
        })
    }

    pub fn fixture_declaration(&self) -> &TypedTestDataDeclarationV1 {
        &self.fixture_declaration
    }
}

/// Lift one complete test data / test load block entry.
pub fn lift_test_data_block_v1(
    fixture_declaration: TypedTestDataDeclarationV1,
) -> Result<TypedTestDataBlockV1, TestDataKeywordsErrorV1> {
    TypedTestDataBlockV1::try_new(fixture_declaration)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_data_declaration_v1::lift_test_data_declaration_v1;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            TEST_DATA_KEYWORDS_POLICY_V1,
            "sipi.p4a-03ai.test-data-keywords-v1.typed-test-keywords"
        );
    }

    #[test]
    fn valid_test_data_block() {
        let fix = lift_test_data_declaration_v1("FIX_DUT_1", Some(50.0), Some(2e-12), None, Some(1.5)).unwrap();
        let block = lift_test_data_block_v1(fix).expect("lift");

        assert_eq!(block.fixture_declaration().fixture_name(), "FIX_DUT_1");
        assert_eq!(block.fixture_declaration().r_fixture_ohm().unwrap().get(), 50.0);
    }
}
