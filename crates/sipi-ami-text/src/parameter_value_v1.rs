//! Typed .ami parameter value declaration core with explicit product-owned
//! validation rules.
//!
//! P4B-02b1: caller-supplied parameter name, declared type token, and value
//! token are validated against explicit product-owned syntax rules. This
//! slice does NOT carry an IBIS-AMI reserved-name catalog, does not infer
//! defaults, does not decode text documents, and does not claim coverage of
//! the IBIS-AMI parameter catalog.

/// Parameter type tokens accepted by this core, matched exactly.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiParameterTypeV1 {
    Float,
    Integer,
    Boolean,
    String_,
    List,
}

/// Maximum UTF-8 byte length of one caller-supplied parameter name.
pub const MAX_PARAMETER_NAME_BYTES_V1: usize = 256;
/// Maximum UTF-8 byte length of one caller-supplied value token.
pub const MAX_PARAMETER_VALUE_TOKEN_BYTES_V1: usize = 65_536;
/// Maximum number of comma-separated items in one validated List value.
pub const MAX_PARAMETER_LIST_ITEMS_V1: usize = 512;
/// Maximum item-pair cells reachable by operations over two validated Lists.
pub const MAX_PARAMETER_LIST_PAIR_CELLS_V1: usize =
    MAX_PARAMETER_LIST_ITEMS_V1 * MAX_PARAMETER_LIST_ITEMS_V1;

impl AmiParameterTypeV1 {
    pub const fn token(self) -> &'static str {
        match self {
            Self::Float => "Float",
            Self::Integer => "Integer",
            Self::Boolean => "Boolean",
            Self::String_ => "String",
            Self::List => "List",
        }
    }

    pub fn from_token(token: &str) -> Option<Self> {
        match token {
            "Float" => Some(Self::Float),
            "Integer" => Some(Self::Integer),
            "Boolean" => Some(Self::Boolean),
            "String" => Some(Self::String_),
            "List" => Some(Self::List),
            _ => None,
        }
    }
}

/// One validated caller-supplied (name, type token, value token) triple.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiParameterValueV1 {
    name: String,
    parameter_type: AmiParameterTypeV1,
    value_token: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiParameterValueErrorV1 {
    EmptyName,
    InvalidName,
    NameTooLong,
    UnknownTypeToken,
    ValueTokenTooLong,
    InvalidFloat,
    InvalidInteger,
    InvalidBoolean,
    EmptyStringValue,
    InvalidList,
    ListTooLong,
}

impl AmiParameterValueV1 {
    /// Validate one caller-supplied parameter declaration.
    ///
    /// Product-owned rules, documented in the P4B-02b1 charter:
    /// - name: non-empty ASCII `[A-Za-z_][A-Za-z0-9_]*`.
    /// - type token: exact `Float | Integer | Boolean | String | List`.
    /// - value token per type: Float parses as finite f64; Integer parses as
    ///   i64; Boolean is exactly `True` or `False`; String is non-empty;
    ///   List is `(item, item, ...)` with non-empty trimmed items.
    pub fn try_new(
        name: &str,
        type_token: &str,
        value_token: &str,
    ) -> Result<Self, AmiParameterValueErrorV1> {
        if name.is_empty() {
            return Err(AmiParameterValueErrorV1::EmptyName);
        }
        if name.len() > MAX_PARAMETER_NAME_BYTES_V1 {
            return Err(AmiParameterValueErrorV1::NameTooLong);
        }
        let mut characters = name.chars();
        let first = characters.next().expect("non-empty name");
        let valid_name = (first.is_ascii_alphabetic() || first == '_')
            && characters.all(|character| character.is_ascii_alphanumeric() || character == '_');
        if !valid_name {
            return Err(AmiParameterValueErrorV1::InvalidName);
        }
        let parameter_type = AmiParameterTypeV1::from_token(type_token)
            .ok_or(AmiParameterValueErrorV1::UnknownTypeToken)?;
        if value_token.len() > MAX_PARAMETER_VALUE_TOKEN_BYTES_V1 {
            return Err(AmiParameterValueErrorV1::ValueTokenTooLong);
        }
        match parameter_type {
            AmiParameterTypeV1::Float => match value_token.parse::<f64>() {
                Ok(value) if value.is_finite() => {}
                _ => return Err(AmiParameterValueErrorV1::InvalidFloat),
            },
            AmiParameterTypeV1::Integer => {
                if value_token.parse::<i64>().is_err() {
                    return Err(AmiParameterValueErrorV1::InvalidInteger);
                }
            }
            AmiParameterTypeV1::Boolean => {
                if value_token != "True" && value_token != "False" {
                    return Err(AmiParameterValueErrorV1::InvalidBoolean);
                }
            }
            AmiParameterTypeV1::String_ => {
                if value_token.is_empty() {
                    return Err(AmiParameterValueErrorV1::EmptyStringValue);
                }
            }
            AmiParameterTypeV1::List => {
                if !value_token.starts_with('(') || !value_token.ends_with(')') {
                    return Err(AmiParameterValueErrorV1::InvalidList);
                }
                let inner = &value_token[1..value_token.len() - 1];
                if inner.is_empty() || inner.split(',').any(|item| item.trim().is_empty()) {
                    return Err(AmiParameterValueErrorV1::InvalidList);
                }
                if inner
                    .split(',')
                    .take(MAX_PARAMETER_LIST_ITEMS_V1 + 1)
                    .count()
                    > MAX_PARAMETER_LIST_ITEMS_V1
                {
                    return Err(AmiParameterValueErrorV1::ListTooLong);
                }
            }
        }
        Ok(Self {
            name: name.to_string(),
            parameter_type,
            value_token: value_token.to_string(),
        })
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub const fn parameter_type(&self) -> AmiParameterTypeV1 {
        self.parameter_type
    }

    pub fn value_token(&self) -> &str {
        &self.value_token
    }
}

/// Explicit scope policy of this slice: syntax-only validation without a
/// catalog, reserved names, defaults, or document decoding.
pub const PARAMETER_VALUE_POLICY_V1: &str =
    "sipi.p4b-02b1.parameter-value-v1.syntax-only-no-catalog-no-defaults";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_each_supported_type() {
        let float = AmiParameterValueV1::try_new("Resistance", "Float", "50.0").expect("float");
        assert_eq!(float.parameter_type(), AmiParameterTypeV1::Float);
        assert_eq!(float.name(), "Resistance");
        let integer = AmiParameterValueV1::try_new("SinkTime", "Integer", "100").expect("integer");
        assert_eq!(integer.parameter_type(), AmiParameterTypeV1::Integer);
        let boolean = AmiParameterValueV1::try_new("Ignore", "Boolean", "True").expect("boolean");
        assert_eq!(boolean.parameter_type(), AmiParameterTypeV1::Boolean);
        let string = AmiParameterValueV1::try_new("Mode", "String", "Linear").expect("string");
        assert_eq!(string.parameter_type(), AmiParameterTypeV1::String_);
        let list = AmiParameterValueV1::try_new("Taps", "List", "(1, 2, 3)").expect("list");
        assert_eq!(list.parameter_type(), AmiParameterTypeV1::List);
    }

    #[test]
    fn rejects_empty_or_invalid_names() {
        assert_eq!(
            AmiParameterValueV1::try_new("", "Float", "1.0"),
            Err(AmiParameterValueErrorV1::EmptyName)
        );
        assert_eq!(
            AmiParameterValueV1::try_new("1Resistance", "Float", "1.0"),
            Err(AmiParameterValueErrorV1::InvalidName)
        );
        assert_eq!(
            AmiParameterValueV1::try_new("Resistance-", "Float", "1.0"),
            Err(AmiParameterValueErrorV1::InvalidName)
        );
    }

    #[test]
    fn rejects_unknown_type_token() {
        assert_eq!(
            AmiParameterValueV1::try_new("Resistance", "resistance", "1.0"),
            Err(AmiParameterValueErrorV1::UnknownTypeToken)
        );
    }

    #[test]
    fn rejects_invalid_values_per_type() {
        assert_eq!(
            AmiParameterValueV1::try_new("Resistance", "Float", "NaN"),
            Err(AmiParameterValueErrorV1::InvalidFloat)
        );
        assert_eq!(
            AmiParameterValueV1::try_new("SinkTime", "Integer", "1.5"),
            Err(AmiParameterValueErrorV1::InvalidInteger)
        );
        assert_eq!(
            AmiParameterValueV1::try_new("Ignore", "Boolean", "true"),
            Err(AmiParameterValueErrorV1::InvalidBoolean)
        );
        assert_eq!(
            AmiParameterValueV1::try_new("Mode", "String", ""),
            Err(AmiParameterValueErrorV1::EmptyStringValue)
        );
        assert_eq!(
            AmiParameterValueV1::try_new("Taps", "List", "1, 2"),
            Err(AmiParameterValueErrorV1::InvalidList)
        );
        assert_eq!(
            AmiParameterValueV1::try_new("Taps", "List", "(1, , 3)"),
            Err(AmiParameterValueErrorV1::InvalidList)
        );
    }

    #[test]
    fn rejects_inputs_above_fixed_capacity_limits() {
        let long_name = "n".repeat(MAX_PARAMETER_NAME_BYTES_V1 + 1);
        assert_eq!(
            AmiParameterValueV1::try_new(&long_name, "Float", "1.0"),
            Err(AmiParameterValueErrorV1::NameTooLong)
        );

        let long_string = "x".repeat(MAX_PARAMETER_VALUE_TOKEN_BYTES_V1 + 1);
        assert_eq!(
            AmiParameterValueV1::try_new("Mode", "String", &long_string),
            Err(AmiParameterValueErrorV1::ValueTokenTooLong)
        );

        let too_many_items = format!("({})", vec!["x"; MAX_PARAMETER_LIST_ITEMS_V1 + 1].join(","));
        assert_eq!(
            AmiParameterValueV1::try_new("Taps", "List", &too_many_items),
            Err(AmiParameterValueErrorV1::ListTooLong)
        );
    }

    #[test]
    fn accepts_list_at_fixed_item_limit() {
        let at_limit = format!("({})", vec!["x"; MAX_PARAMETER_LIST_ITEMS_V1].join(","));
        assert!(AmiParameterValueV1::try_new("Taps", "List", &at_limit).is_ok());
        assert_eq!(MAX_PARAMETER_LIST_PAIR_CELLS_V1, 262_144);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            PARAMETER_VALUE_POLICY_V1,
            "sipi.p4b-02b1.parameter-value-v1.syntax-only-no-catalog-no-defaults"
        );
    }
}
