//! Typed IBIS [Test Data] & [Test Load] declaration core (P4A-03r).
//!
//! Lifts and validates IBIS [Test Data] & [Test Load] test fixture declarations
//! (fixture name, R_fixture, C_fixture, L_fixture, V_fixture) into typed clean-room structures.
//! Fail-closed: empty fixture names, non-ASCII characters, non-finite values,
//! or negative R/C/L fixture values are strictly rejected.

use sipi_types::FiniteF64;

/// Scope policy for the typed test data declaration core.
pub const TEST_DATA_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03r.test-data-declaration-v1.typed-test-data";

/// Fail-closed errors during test data declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TestDataDeclarationErrorV1 {
    EmptyFixtureName,
    NonAsciiFixtureName,
    InvalidFixtureName,
    NonFiniteValue,
    NegativeFixtureParameter,
}

/// A typed IBIS [Test Data] / [Test Load] fixture declaration.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedTestDataDeclarationV1 {
    fixture_name: String,
    r_fixture_ohm: Option<FiniteF64>,
    c_fixture_farad: Option<FiniteF64>,
    l_fixture_henry: Option<FiniteF64>,
    v_fixture_volts: Option<FiniteF64>,
}

impl TypedTestDataDeclarationV1 {
    pub fn try_new(
        fixture_name: impl Into<String>,
        r_fixture_ohm: Option<f64>,
        c_fixture_farad: Option<f64>,
        l_fixture_henry: Option<f64>,
        v_fixture_volts: Option<f64>,
    ) -> Result<Self, TestDataDeclarationErrorV1> {
        let name = fixture_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(TestDataDeclarationErrorV1::EmptyFixtureName);
        }
        if !trimmed.is_ascii() {
            return Err(TestDataDeclarationErrorV1::NonAsciiFixtureName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(TestDataDeclarationErrorV1::InvalidFixtureName);
        }

        let validate_non_negative = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, TestDataDeclarationErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(TestDataDeclarationErrorV1::NonFiniteValue);
                    }
                    if v < 0.0 {
                        return Err(TestDataDeclarationErrorV1::NegativeFixtureParameter);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| TestDataDeclarationErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let validate_finite = |val: Option<f64>, kind: &'static str| -> Result<Option<FiniteF64>, TestDataDeclarationErrorV1> {
            match val {
                None => Ok(None),
                Some(v) => {
                    if !v.is_finite() {
                        return Err(TestDataDeclarationErrorV1::NonFiniteValue);
                    }
                    let finite = FiniteF64::try_new(v, kind)
                        .map_err(|_| TestDataDeclarationErrorV1::NonFiniteValue)?;
                    Ok(Some(finite))
                }
            }
        };

        let r_fixture_ohm = validate_non_negative(r_fixture_ohm, "r_fixture_ohm")?;
        let c_fixture_farad = validate_non_negative(c_fixture_farad, "c_fixture_farad")?;
        let l_fixture_henry = validate_non_negative(l_fixture_henry, "l_fixture_henry")?;
        let v_fixture_volts = validate_finite(v_fixture_volts, "v_fixture_volts")?;

        Ok(Self {
            fixture_name: trimmed.to_string(),
            r_fixture_ohm,
            c_fixture_farad,
            l_fixture_henry,
            v_fixture_volts,
        })
    }

    pub fn fixture_name(&self) -> &str {
        &self.fixture_name
    }

    pub fn r_fixture_ohm(&self) -> Option<FiniteF64> {
        self.r_fixture_ohm
    }

    pub fn c_fixture_farad(&self) -> Option<FiniteF64> {
        self.c_fixture_farad
    }

    pub fn l_fixture_henry(&self) -> Option<FiniteF64> {
        self.l_fixture_henry
    }

    pub fn v_fixture_volts(&self) -> Option<FiniteF64> {
        self.v_fixture_volts
    }
}

/// Lift one test data / test load fixture declaration.
pub fn lift_test_data_declaration_v1(
    fixture_name: &str,
    r_fixture_ohm: Option<f64>,
    c_fixture_farad: Option<f64>,
    l_fixture_henry: Option<f64>,
    v_fixture_volts: Option<f64>,
) -> Result<TypedTestDataDeclarationV1, TestDataDeclarationErrorV1> {
    TypedTestDataDeclarationV1::try_new(
        fixture_name,
        r_fixture_ohm,
        c_fixture_farad,
        l_fixture_henry,
        v_fixture_volts,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            TEST_DATA_DECLARATION_POLICY_V1,
            "sipi.p4a-03r.test-data-declaration-v1.typed-test-data"
        );
    }

    #[test]
    fn valid_full_test_data() {
        let fixture = lift_test_data_declaration_v1(
            "FIX_DUT_1",
            Some(50.0),
            Some(2e-12),
            Some(1e-9),
            Some(1.5),
        )
        .expect("lift");
        assert_eq!(fixture.fixture_name(), "FIX_DUT_1");
        assert_eq!(fixture.r_fixture_ohm().unwrap().get(), 50.0);
        assert_eq!(fixture.c_fixture_farad().unwrap().get(), 2e-12);
        assert_eq!(fixture.l_fixture_henry().unwrap().get(), 1e-9);
        assert_eq!(fixture.v_fixture_volts().unwrap().get(), 1.5);
    }

    #[test]
    fn valid_minimal_test_data() {
        let fixture = lift_test_data_declaration_v1("FIX_MIN", None, None, None, None).expect("lift");
        assert_eq!(fixture.fixture_name(), "FIX_MIN");
        assert_eq!(fixture.r_fixture_ohm(), None);
        assert_eq!(fixture.c_fixture_farad(), None);
        assert_eq!(fixture.l_fixture_henry(), None);
        assert_eq!(fixture.v_fixture_volts(), None);
    }

    #[test]
    fn rejects_empty_fixture_name() {
        assert_eq!(
            lift_test_data_declaration_v1("", Some(50.0), None, None, None),
            Err(TestDataDeclarationErrorV1::EmptyFixtureName)
        );
    }

    #[test]
    fn rejects_negative_r_fixture() {
        assert_eq!(
            lift_test_data_declaration_v1("FIX", Some(-50.0), None, None, None),
            Err(TestDataDeclarationErrorV1::NegativeFixtureParameter)
        );
    }

    #[test]
    fn rejects_non_finite_values() {
        assert_eq!(
            lift_test_data_declaration_v1("FIX", Some(f64::NAN), None, None, None),
            Err(TestDataDeclarationErrorV1::NonFiniteValue)
        );
    }
}
