//! AMI parameter-tree syntax and the small host-facing metadata contract.
//!
//! AMI parameter files use nested parenthesized records. This module preserves
//! that tree instead of attempting to reinterpret model-specific parameters.
//! Only the three well-known host metadata values are typed here.

use std::fmt;

/// Parsed AMI parameter records in physical source order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AmiParameterTree {
    parameters: Vec<AmiParameter>,
    reserved_host_parameters: Vec<AmiParameter>,
}

impl AmiParameterTree {
    /// Returns parameters in physical source order.
    #[must_use]
    pub fn parameters(&self) -> &[AmiParameter] {
        &self.parameters
    }

    /// Finds a parameter by ASCII case-insensitive name.
    #[must_use]
    pub fn parameter(&self, name: &str) -> Option<&AmiParameter> {
        self.parameters
            .iter()
            .find(|parameter| parameter.name.eq_ignore_ascii_case(name))
    }

    fn host_parameter(&self, name: &str) -> Option<&AmiParameter> {
        self.parameter(name).or_else(|| {
            self.reserved_host_parameters
                .iter()
                .find(|parameter| parameter.name.eq_ignore_ascii_case(name))
        })
    }
}

/// One named AMI parameter and its metadata fields.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AmiParameter {
    name: String,
    line: usize,
    fields: Vec<AmiField>,
}

impl AmiParameter {
    /// Parameter name from the first atom in its parenthesized record.
    #[must_use]
    pub fn name(&self) -> &str {
        &self.name
    }

    /// One-based physical source line for this parameter.
    #[must_use]
    pub const fn line(&self) -> usize {
        self.line
    }

    /// Metadata fields in physical source order.
    #[must_use]
    pub fn fields(&self) -> &[AmiField] {
        &self.fields
    }

    /// Finds metadata by ASCII case-insensitive name.
    #[must_use]
    pub fn field(&self, name: &str) -> Option<&AmiField> {
        self.fields
            .iter()
            .find(|field| field.name.eq_ignore_ascii_case(name))
    }
}

/// One named AMI metadata field, such as `Type` or `Value`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AmiField {
    name: String,
    line: usize,
    values: Vec<AmiValue>,
}

impl AmiField {
    /// Field name from the first atom in its parenthesized record.
    #[must_use]
    pub fn name(&self) -> &str {
        &self.name
    }

    /// One-based physical source line for this field.
    #[must_use]
    pub const fn line(&self) -> usize {
        self.line
    }

    /// Field values, preserving nested expressions when present.
    #[must_use]
    pub fn values(&self) -> &[AmiValue] {
        &self.values
    }
}

/// A scalar or nested AMI parameter-tree value.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AmiValue {
    /// A bare atom.
    Atom(String),
    /// A double-quoted string without its quote delimiters.
    Quoted(String),
    /// A nested parenthesized expression.
    List(Vec<AmiValue>),
}

impl AmiValue {
    fn scalar(&self) -> Option<&str> {
        match self {
            Self::Atom(value) | Self::Quoted(value) => Some(value),
            Self::List(_) => None,
        }
    }
}

/// The well-known AMI values a DLL host needs before invoking a model.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AmiHostMetadata {
    ami_version: String,
    init_returns_impulse: bool,
    get_wave_exists: bool,
}

impl AmiHostMetadata {
    /// Extracts and type-checks the standard host-facing parameter values.
    pub fn from_tree(tree: &AmiParameterTree) -> Result<Self, AmiSemanticError> {
        let ami_version = typed_scalar(tree, "AMI_Version", "String")?.to_owned();
        let init_returns_impulse = typed_boolean(tree, "Init_Returns_Impulse")?;
        let get_wave_exists = typed_boolean(tree, "GetWave_Exists")?;
        Ok(Self {
            ami_version,
            init_returns_impulse,
            get_wave_exists,
        })
    }

    /// AMI specification version declared by the parameter tree.
    #[must_use]
    pub fn ami_version(&self) -> &str {
        &self.ami_version
    }

    /// Whether the model declares an impulse response from `AMI_Init`.
    #[must_use]
    pub const fn init_returns_impulse(&self) -> bool {
        self.init_returns_impulse
    }

    /// Whether the model declares the optional `AMI_GetWave` entry point.
    #[must_use]
    pub const fn get_wave_exists(&self) -> bool {
        self.get_wave_exists
    }
}

/// A syntax error while reading AMI parenthesized parameter records.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AmiParseError {
    /// A closing parenthesis had no matching opening parenthesis.
    UnexpectedClose { line: usize },
    /// A parenthesized expression ended before its closing parenthesis.
    UnterminatedList { line: usize },
    /// A double-quoted string ended before its closing quote.
    UnterminatedString { line: usize },
    /// A top-level expression was not a named parameter list.
    ParameterMustBeList { line: usize },
    /// A parameter or metadata field did not begin with a bare name atom.
    MissingName { line: usize },
    /// A parameter contained a value that was not a metadata field list.
    FieldMustBeList { parameter: String, line: usize },
}

impl fmt::Display for AmiParseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnexpectedClose { line } => write!(formatter, "unexpected ')' at line {line}"),
            Self::UnterminatedList { line } => {
                write!(formatter, "unterminated AMI list opened at line {line}")
            }
            Self::UnterminatedString { line } => {
                write!(formatter, "unterminated AMI string opened at line {line}")
            }
            Self::ParameterMustBeList { line } => {
                write!(formatter, "AMI parameter must be a list at line {line}")
            }
            Self::MissingName { line } => {
                write!(formatter, "AMI record has no name atom at line {line}")
            }
            Self::FieldMustBeList { parameter, line } => write!(
                formatter,
                "AMI parameter {parameter} has a non-list metadata field at line {line}"
            ),
        }
    }
}

impl std::error::Error for AmiParseError {}

/// A failure while interpreting well-known AMI host metadata.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AmiSemanticError {
    /// A required parameter was absent.
    MissingParameter { name: &'static str },
    /// A required metadata field was absent.
    MissingField {
        parameter: &'static str,
        field: &'static str,
    },
    /// A metadata field did not contain exactly one scalar value.
    ValueMustBeScalar {
        parameter: &'static str,
        field: &'static str,
        line: usize,
    },
    /// The declared `Type` did not match the required host type.
    UnexpectedType {
        parameter: &'static str,
        expected: &'static str,
        actual: String,
        line: usize,
    },
    /// A Boolean `Value` was not `True` or `False`.
    InvalidBoolean {
        parameter: &'static str,
        value: String,
        line: usize,
    },
}

impl fmt::Display for AmiSemanticError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingParameter { name } => write!(formatter, "missing AMI parameter {name}"),
            Self::MissingField { parameter, field } => {
                write!(formatter, "AMI parameter {parameter} is missing {field}")
            }
            Self::ValueMustBeScalar {
                parameter,
                field,
                line,
            } => write!(
                formatter,
                "AMI parameter {parameter} field {field} must have one scalar value at line {line}"
            ),
            Self::UnexpectedType {
                parameter,
                expected,
                actual,
                line,
            } => write!(
                formatter,
                "AMI parameter {parameter} requires Type {expected}, found {actual} at line {line}"
            ),
            Self::InvalidBoolean {
                parameter,
                value,
                line,
            } => write!(
                formatter,
                "AMI parameter {parameter} has invalid Boolean value {value} at line {line}"
            ),
        }
    }
}

impl std::error::Error for AmiSemanticError {}

/// Parses AMI parenthesized parameter records without model-specific coercion.
pub fn parse_ami_parameters(source: &str) -> Result<AmiParameterTree, AmiParseError> {
    let tokens = tokenize(source)?;
    let mut cursor = 0;
    let mut parameters = Vec::new();
    let mut reserved_host_parameters = Vec::new();
    while cursor < tokens.len() {
        let expression = parse_expression(&tokens, &mut cursor)?;
        collect_reserved_host_parameters(&expression, &mut reserved_host_parameters)?;
        parameters.push(to_parameter(expression)?);
    }
    Ok(AmiParameterTree {
        parameters,
        reserved_host_parameters,
    })
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum TokenKind {
    Open,
    Close,
    Atom(String),
    Quoted(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Token {
    kind: TokenKind,
    line: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Expression {
    line: usize,
    value: ExpressionValue,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum ExpressionValue {
    Atom(String),
    Quoted(String),
    List(Vec<Expression>),
}

fn tokenize(source: &str) -> Result<Vec<Token>, AmiParseError> {
    let characters: Vec<char> = source.chars().collect();
    let mut tokens = Vec::new();
    let mut index = 0;
    let mut line = 1;
    while index < characters.len() {
        match characters[index] {
            character if character.is_whitespace() => {
                if character == '\n' {
                    line += 1;
                }
                index += 1;
            }
            '|' => {
                while index < characters.len() && characters[index] != '\n' {
                    index += 1;
                }
            }
            '(' => {
                tokens.push(Token {
                    kind: TokenKind::Open,
                    line,
                });
                index += 1;
            }
            ')' => {
                tokens.push(Token {
                    kind: TokenKind::Close,
                    line,
                });
                index += 1;
            }
            '"' => {
                let start_line = line;
                index += 1;
                let mut value = String::new();
                let mut escaped = false;
                let mut closed = false;
                while index < characters.len() {
                    let character = characters[index];
                    index += 1;
                    if escaped {
                        value.push(character);
                        escaped = false;
                        continue;
                    }
                    if character == '\\' {
                        escaped = true;
                        continue;
                    }
                    if character == '"' {
                        closed = true;
                        break;
                    }
                    if character == '\n' {
                        line += 1;
                    }
                    value.push(character);
                }
                if !closed {
                    return Err(AmiParseError::UnterminatedString { line: start_line });
                }
                tokens.push(Token {
                    kind: TokenKind::Quoted(value),
                    line: start_line,
                });
            }
            _ => {
                let start = index;
                while index < characters.len()
                    && !characters[index].is_whitespace()
                    && !matches!(characters[index], '(' | ')' | '|')
                {
                    index += 1;
                }
                tokens.push(Token {
                    kind: TokenKind::Atom(characters[start..index].iter().collect()),
                    line,
                });
            }
        }
    }
    Ok(tokens)
}

fn parse_expression(tokens: &[Token], cursor: &mut usize) -> Result<Expression, AmiParseError> {
    let token = &tokens[*cursor];
    *cursor += 1;
    match &token.kind {
        TokenKind::Close => Err(AmiParseError::UnexpectedClose { line: token.line }),
        TokenKind::Atom(value) => Ok(Expression {
            line: token.line,
            value: ExpressionValue::Atom(value.clone()),
        }),
        TokenKind::Quoted(value) => Ok(Expression {
            line: token.line,
            value: ExpressionValue::Quoted(value.clone()),
        }),
        TokenKind::Open => {
            let mut items = Vec::new();
            while *cursor < tokens.len() && !matches!(tokens[*cursor].kind, TokenKind::Close) {
                items.push(parse_expression(tokens, cursor)?);
            }
            if *cursor == tokens.len() {
                return Err(AmiParseError::UnterminatedList { line: token.line });
            }
            *cursor += 1;
            Ok(Expression {
                line: token.line,
                value: ExpressionValue::List(items),
            })
        }
    }
}

fn to_parameter(expression: Expression) -> Result<AmiParameter, AmiParseError> {
    let line = expression.line;
    let ExpressionValue::List(items) = expression.value else {
        return Err(AmiParseError::ParameterMustBeList { line });
    };
    let Some((name, children)) = items.split_first() else {
        return Err(AmiParseError::MissingName { line });
    };
    let ExpressionValue::Atom(name) = &name.value else {
        return Err(AmiParseError::MissingName { line: name.line });
    };
    let mut fields = Vec::with_capacity(children.len());
    for child in children {
        fields.push(to_field(name, child.clone())?);
    }
    Ok(AmiParameter {
        name: name.clone(),
        line,
        fields,
    })
}

fn to_field(parameter: &str, expression: Expression) -> Result<AmiField, AmiParseError> {
    let line = expression.line;
    let ExpressionValue::List(items) = expression.value else {
        return Err(AmiParseError::FieldMustBeList {
            parameter: parameter.to_owned(),
            line,
        });
    };
    let Some((name, values)) = items.split_first() else {
        return Err(AmiParseError::MissingName { line });
    };
    let ExpressionValue::Atom(name) = &name.value else {
        return Err(AmiParseError::MissingName { line: name.line });
    };
    Ok(AmiField {
        name: name.clone(),
        line,
        values: values.iter().cloned().map(to_value).collect(),
    })
}

fn to_value(expression: Expression) -> AmiValue {
    match expression.value {
        ExpressionValue::Atom(value) => AmiValue::Atom(value),
        ExpressionValue::Quoted(value) => AmiValue::Quoted(value),
        ExpressionValue::List(values) => AmiValue::List(values.into_iter().map(to_value).collect()),
    }
}

fn collect_reserved_host_parameters(
    expression: &Expression,
    parameters: &mut Vec<AmiParameter>,
) -> Result<(), AmiParseError> {
    let ExpressionValue::List(items) = &expression.value else {
        return Ok(());
    };

    if expression_name(items).is_some_and(|name| name.eq_ignore_ascii_case("Reserved_Parameters")) {
        for parameter in &items[1..] {
            if expression_name_list(parameter).is_some_and(is_host_metadata_parameter) {
                parameters.push(to_parameter(parameter.clone())?);
            }
        }
    }

    for item in items {
        collect_reserved_host_parameters(item, parameters)?;
    }
    Ok(())
}

fn expression_name(items: &[Expression]) -> Option<&str> {
    let ExpressionValue::Atom(name) = &items.first()?.value else {
        return None;
    };
    Some(name)
}

fn expression_name_list(expression: &Expression) -> Option<&str> {
    let ExpressionValue::List(items) = &expression.value else {
        return None;
    };
    expression_name(items)
}

fn is_host_metadata_parameter(name: &str) -> bool {
    ["AMI_Version", "Init_Returns_Impulse", "GetWave_Exists"]
        .iter()
        .any(|candidate| name.eq_ignore_ascii_case(candidate))
}

fn typed_scalar<'a>(
    tree: &'a AmiParameterTree,
    name: &'static str,
    expected_type: &'static str,
) -> Result<&'a str, AmiSemanticError> {
    let parameter = tree
        .host_parameter(name)
        .ok_or(AmiSemanticError::MissingParameter { name })?;
    let actual_type = scalar_field(parameter, name, "Type")?;
    if !actual_type.eq_ignore_ascii_case(expected_type) {
        let field = parameter
            .field("Type")
            .expect("scalar_field returned a value from the Type field");
        return Err(AmiSemanticError::UnexpectedType {
            parameter: name,
            expected: expected_type,
            actual: actual_type.to_owned(),
            line: field.line,
        });
    }
    scalar_field(parameter, name, "Value")
}

fn typed_boolean(tree: &AmiParameterTree, name: &'static str) -> Result<bool, AmiSemanticError> {
    let value = typed_scalar(tree, name, "Boolean")?;
    let parameter = tree
        .host_parameter(name)
        .expect("typed_scalar returned a value from an existing parameter");
    let line = parameter
        .field("Value")
        .expect("typed_scalar returned a value from the Value field")
        .line;
    if value.eq_ignore_ascii_case("true") {
        Ok(true)
    } else if value.eq_ignore_ascii_case("false") {
        Ok(false)
    } else {
        Err(AmiSemanticError::InvalidBoolean {
            parameter: name,
            value: value.to_owned(),
            line,
        })
    }
}

fn scalar_field<'a>(
    parameter: &'a AmiParameter,
    parameter_name: &'static str,
    field_name: &'static str,
) -> Result<&'a str, AmiSemanticError> {
    let field = parameter
        .field(field_name)
        .ok_or(AmiSemanticError::MissingField {
            parameter: parameter_name,
            field: field_name,
        })?;
    if field.values.len() != 1 {
        return Err(AmiSemanticError::ValueMustBeScalar {
            parameter: parameter_name,
            field: field_name,
            line: field.line,
        });
    }
    field.values[0]
        .scalar()
        .ok_or(AmiSemanticError::ValueMustBeScalar {
            parameter: parameter_name,
            field: field_name,
            line: field.line,
        })
}

#[cfg(test)]
mod tests {
    use super::{AmiHostMetadata, AmiParseError, AmiSemanticError, AmiValue, parse_ami_parameters};

    const HOST_PARAMETERS: &str = r#"
        | public AMI parameter syntax fixture
        (AMI_Version (Usage Info) (Type String) (Value "7.2"))
        (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True))
        (GetWave_Exists (Usage Info) (Type Boolean) (Value False))
        (Tx_Tap (Usage In) (Type Float) (Range 0.0 1.0 0.25))
    "#;

    const WRAPPED_HOST_PARAMETERS: &str = r#"
        (example_rx
            (Description "Public model wrapper")
            (Reserved_Parameters
                (AMI_Version (Usage Info) (Type String) (Value "5.1"))
                (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True))
                (GetWave_Exists (Usage Info) (Type Boolean) (Value True))
            )
            (Model_Specific
                (AMI_Version (Usage In) (Type Float) (Value 2.0))
            )
        )
    "#;

    #[test]
    fn preserves_parameter_metadata_and_nested_values() {
        let tree = parse_ami_parameters(HOST_PARAMETERS).expect("valid AMI parameters");
        assert_eq!(tree.parameters().len(), 4);
        let tap = tree.parameter("tx_tap").unwrap();
        assert_eq!(tap.line(), 6);
        assert_eq!(
            tap.field("Range").unwrap().values()[0],
            AmiValue::Atom("0.0".to_owned())
        );
    }

    #[test]
    fn extracts_typed_host_metadata() {
        let tree = parse_ami_parameters(HOST_PARAMETERS).expect("valid AMI parameters");
        let metadata = AmiHostMetadata::from_tree(&tree).expect("typed AMI metadata");
        assert_eq!(metadata.ami_version(), "7.2");
        assert!(metadata.init_returns_impulse());
        assert!(!metadata.get_wave_exists());
    }

    #[test]
    fn extracts_host_metadata_from_standard_reserved_parameters_wrapper() {
        let tree =
            parse_ami_parameters(WRAPPED_HOST_PARAMETERS).expect("valid wrapped AMI parameters");
        assert_eq!(tree.parameters().len(), 1);
        assert!(tree.parameter("AMI_Version").is_none());

        let metadata = AmiHostMetadata::from_tree(&tree).expect("typed wrapped host metadata");
        assert_eq!(metadata.ami_version(), "5.1");
        assert!(metadata.init_returns_impulse());
        assert!(metadata.get_wave_exists());
    }

    #[test]
    fn rejects_malformed_parentheses_and_records() {
        assert_eq!(
            parse_ami_parameters("(AMI_Version (Type String)"),
            Err(AmiParseError::UnterminatedList { line: 1 })
        );
        assert_eq!(
            parse_ami_parameters("AMI_Version"),
            Err(AmiParseError::ParameterMustBeList { line: 1 })
        );
        assert_eq!(
            parse_ami_parameters("(AMI_Version bare)"),
            Err(AmiParseError::FieldMustBeList {
                parameter: "AMI_Version".to_owned(),
                line: 1,
            })
        );
    }

    #[test]
    fn rejects_wrong_host_metadata_types_and_values() {
        let wrong_type = parse_ami_parameters(
            "(AMI_Version (Type Boolean) (Value True))\n(Init_Returns_Impulse (Type Boolean) (Value True))\n(GetWave_Exists (Type Boolean) (Value False))",
        )
        .unwrap();
        assert_eq!(
            AmiHostMetadata::from_tree(&wrong_type),
            Err(AmiSemanticError::UnexpectedType {
                parameter: "AMI_Version",
                expected: "String",
                actual: "Boolean".to_owned(),
                line: 1,
            })
        );

        let bad_boolean = parse_ami_parameters(
            "(AMI_Version (Type String) (Value 7.2))\n(Init_Returns_Impulse (Type Boolean) (Value sometimes))\n(GetWave_Exists (Type Boolean) (Value False))",
        )
        .unwrap();
        assert_eq!(
            AmiHostMetadata::from_tree(&bad_boolean),
            Err(AmiSemanticError::InvalidBoolean {
                parameter: "Init_Returns_Impulse",
                value: "sometimes".to_owned(),
                line: 2,
            })
        );
    }
}
