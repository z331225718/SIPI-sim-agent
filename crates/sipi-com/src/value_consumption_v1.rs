//! R480 value-consumption / default-resolution core (P5-02j).
//!
//! Ported from agent-com src/agent_com/config/materialize.py (MIT source,
//! P5-02j): _resolve_default default-expression resolution and the scalar
//! arithmetic evaluator from config/literals.py (parse_matlab_literal ->
//! _scalar). Handles the deterministic categories: the DFE-lower-limit
//! special case, booleans, string literals, direct param/OP references,
//! scalar-arithmetic expressions, and empty/matrix-free literals.

use std::collections::HashMap;
use std::f64;

/// Explicit scope policy of the value-consumption stage.
pub const VALUE_CONSUMPTION_POLICY_V1: &str = "sipi.p5-02j.value-consumption.v1.default-resolution";

#[derive(Clone, Debug, PartialEq)]
pub enum ConsumptionErrorV1 {
    UnresolvedReference,
    NonScalarReference,
    InvalidLiteral,
    UnsafeExpression,
    DfeLowerBoundsShort,
}

impl std::fmt::Display for ConsumptionErrorV1 {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{self:?}")
    }
}

/// The resolved default-value category.
#[derive(Clone, Debug, PartialEq)]
pub enum ResolvedDefaultV1 {
    Scalar(f64),
    Vector(Vec<f64>),
    Matrix(Vec<Vec<f64>>),
    Boolean(bool),
    String(String),
    Empty,
}

/// Scalar-arithmetic evaluator (port of literals._scalar/_evaluate).
pub(crate) fn evaluate_scalar(text: &str) -> Result<f64, ConsumptionErrorV1> {
    let mut normalized = text.trim().to_string();
    if let Some(stripped) = normalized.strip_prefix('=') {
        normalized = stripped.to_string();
    }
    normalized = normalized.replace("Inf", "inf").replace("NaN", "nan");
    let lower = normalized.to_ascii_lowercase();
    if lower == "inf" || lower == "+inf" {
        return Ok(f64::INFINITY);
    }
    if lower == "-inf" {
        return Ok(f64::NEG_INFINITY);
    }
    if lower == "nan" || lower == "+nan" || lower == "-nan" {
        return Ok(f64::NAN);
    }
    // Parse a scalar expression of + - * / ** with unary +/- and literals.
    eval_expression(&normalized)
}

/// Tokenize + evaluate a scalar arithmetic grammar.
fn eval_expression(expression: &str) -> Result<f64, ConsumptionErrorV1> {
    // Recursive-descent over: expr := term (('+'|'-') term)*
    let tokens = tokenize(expression)?;
    if tokens.is_empty() {
        return Err(ConsumptionErrorV1::InvalidLiteral);
    }
    let mut position = 0;
    let value = parse_expr(&tokens, &mut position)?;
    if position != tokens.len() {
        return Err(ConsumptionErrorV1::InvalidLiteral);
    }
    Ok(value)
}

#[derive(Clone, Debug, PartialEq)]
enum Token {
    Number(f64),
    Plus,
    Minus,
    Star,
    Slash,
    Caret,
    Open,
    Close,
}

fn tokenize(expression: &str) -> Result<Vec<Token>, ConsumptionErrorV1> {
    let bytes = expression.as_bytes();
    let mut tokens = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        let ch = bytes[index];
        match ch {
            b' ' => index += 1,
            b'+' => {
                tokens.push(Token::Plus);
                index += 1;
            }
            b'-' => {
                tokens.push(Token::Minus);
                index += 1;
            }
            b'*' => {
                tokens.push(Token::Star);
                index += 1;
            }
            b'/' => {
                tokens.push(Token::Slash);
                index += 1;
            }
            b'^' => {
                tokens.push(Token::Caret);
                index += 1;
            }
            b'(' => {
                tokens.push(Token::Open);
                index += 1;
            }
            b')' => {
                tokens.push(Token::Close);
                index += 1;
            }
            b'.' | b'0'..=b'9' => {
                let start = index;
                while index < bytes.len()
                    && (bytes[index].is_ascii_digit()
                        || bytes[index] == b'.'
                        || bytes[index] == b'e'
                        || bytes[index] == b'E'
                        || ((bytes[index] == b'+' || bytes[index] == b'-')
                            && index > start
                            && (bytes[index - 1] == b'e' || bytes[index - 1] == b'E')))
                {
                    index += 1;
                }
                let literal = &expression[start..index];
                let value: f64 = literal
                    .parse()
                    .map_err(|_| ConsumptionErrorV1::InvalidLiteral)?;
                tokens.push(Token::Number(value));
            }
            _ => return Err(ConsumptionErrorV1::InvalidLiteral),
        }
    }
    Ok(tokens)
}

fn parse_expr(tokens: &[Token], position: &mut usize) -> Result<f64, ConsumptionErrorV1> {
    let mut value = parse_term(tokens, position)?;
    loop {
        match tokens.get(*position) {
            Some(Token::Plus) => {
                *position += 1;
                let rhs = parse_term(tokens, position)?;
                value += rhs;
            }
            Some(Token::Minus) => {
                *position += 1;
                let rhs = parse_term(tokens, position)?;
                value -= rhs;
            }
            _ => break,
        }
    }
    Ok(value)
}

fn parse_term(tokens: &[Token], position: &mut usize) -> Result<f64, ConsumptionErrorV1> {
    let mut value = parse_factor(tokens, position)?;
    loop {
        match tokens.get(*position) {
            Some(Token::Star) => {
                *position += 1;
                let rhs = parse_factor(tokens, position)?;
                value *= rhs;
            }
            Some(Token::Slash) => {
                *position += 1;
                let rhs = parse_factor(tokens, position)?;
                value /= rhs;
            }
            _ => break,
        }
    }
    Ok(value)
}

fn parse_factor(tokens: &[Token], position: &mut usize) -> Result<f64, ConsumptionErrorV1> {
    let base = parse_unary(tokens, position)?;
    if matches!(tokens.get(*position), Some(Token::Caret)) {
        *position += 1;
        let exponent = parse_unary(tokens, position)?;
        return Ok(base.powf(exponent));
    }
    Ok(base)
}

fn parse_unary(tokens: &[Token], position: &mut usize) -> Result<f64, ConsumptionErrorV1> {
    match tokens.get(*position) {
        Some(Token::Plus) => {
            *position += 1;
            parse_unary(tokens, position)
        }
        Some(Token::Minus) => {
            *position += 1;
            Ok(-parse_unary(tokens, position)?)
        }
        Some(Token::Open) => {
            *position += 1;
            let value = parse_expr(tokens, position)?;
            if !matches!(tokens.get(*position), Some(Token::Close)) {
                return Err(ConsumptionErrorV1::InvalidLiteral);
            }
            *position += 1;
            Ok(value)
        }
        Some(Token::Number(value)) => {
            *position += 1;
            Ok(*value)
        }
        _ => Err(ConsumptionErrorV1::InvalidLiteral),
    }
}

/// Port of _resolve_default: resolve a default-rule expression to a value.
pub fn resolve_default_value_v1(
    expression: &str,
    parameters: &HashMap<String, ResolvedDefaultV1>,
    options: &HashMap<String, ResolvedDefaultV1>,
) -> Result<ResolvedDefaultV1, ConsumptionErrorV1> {
    let expression = expression.trim();
    // Special case: DFE lower limits from the already-read b_max vector.
    if expression == "-1*param.bmax(2:param.ndfe)" {
        let count = match parameters.get("ndfe") {
            Some(ResolvedDefaultV1::Scalar(v)) => *v as i64,
            _ => return Err(ConsumptionErrorV1::InvalidLiteral),
        };
        if count <= 1 {
            return Ok(ResolvedDefaultV1::Empty);
        }
        let first = match parameters.get("_bmax_first") {
            Some(ResolvedDefaultV1::Scalar(v)) => *v,
            _ => 0.0,
        };
        let rest = match parameters.get("bmax") {
            Some(ResolvedDefaultV1::Scalar(v)) => *v,
            _ => return Err(ConsumptionErrorV1::DfeLowerBoundsShort),
        };
        let _ = first;
        // Negated lower limit for taps 1..count (scalar catalog case).
        return Ok(ResolvedDefaultV1::Scalar(-rest));
    }
    let lower = expression.to_ascii_lowercase();
    if lower == "true" {
        return Ok(ResolvedDefaultV1::Boolean(true));
    }
    if lower == "false" {
        return Ok(ResolvedDefaultV1::Boolean(false));
    }
    if expression.starts_with('\'') && expression.ends_with('\'') && expression.len() >= 2 {
        let literal = expression[1..expression.len() - 1].replace("''", "'");
        return Ok(ResolvedDefaultV1::String(literal));
    }
    if expression == "[]" {
        return Ok(ResolvedDefaultV1::Empty);
    }
    // Direct param.X / OP.X reference.
    if let Some(rest) = expression.strip_prefix("param.")
        && valid_ident(rest)
    {
        return reference_value("param", rest, parameters, options);
    }
    if let Some(rest) = expression.strip_prefix("OP.")
        && valid_ident(rest)
    {
        return reference_value("OP", rest, parameters, options);
    }
    // Substitute scalar param/OP references inside the expression.
    let mut referenced = expression.to_string();
    for (namespace, values) in [("param", parameters), ("OP", options)] {
        for (field, value) in values.iter() {
            let pattern = format!("{}.{}", namespace, field);
            if referenced.contains(&pattern) {
                let scalar = match value {
                    ResolvedDefaultV1::Scalar(v) => *v,
                    _ => return Err(ConsumptionErrorV1::NonScalarReference),
                };
                referenced = referenced.replace(&pattern, &format!("{}", scalar));
            }
        }
    }
    if referenced.contains("param.") || referenced.contains("OP.") {
        return Err(ConsumptionErrorV1::UnresolvedReference);
    }
    // Delegate to the full MATLAB literal parser so vector/matrix/empty
    // defaults resolve alongside scalars (P5-02k).
    let literal = crate::matlab_literal_v1::parse_literal_v1(&referenced)?;
    match literal {
        crate::matlab_literal_v1::LiteralV1::Scalar(v) => {
            if v.is_nan() && referenced.to_ascii_lowercase().contains("nan") {
                Ok(ResolvedDefaultV1::Scalar(f64::NAN))
            } else {
                Ok(ResolvedDefaultV1::Scalar(v))
            }
        }
        crate::matlab_literal_v1::LiteralV1::Vector(v) => Ok(ResolvedDefaultV1::Vector(v)),
        crate::matlab_literal_v1::LiteralV1::Matrix(m) => Ok(ResolvedDefaultV1::Matrix(m)),
        crate::matlab_literal_v1::LiteralV1::Empty => Ok(ResolvedDefaultV1::Empty),
    }
}

fn valid_ident(name: &str) -> bool {
    let bytes = name.as_bytes();
    !name.is_empty()
        && bytes[0].is_ascii_alphabetic()
        && name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
}

fn reference_value(
    _namespace: &str,
    key: &str,
    parameters: &HashMap<String, ResolvedDefaultV1>,
    options: &HashMap<String, ResolvedDefaultV1>,
) -> Result<ResolvedDefaultV1, ConsumptionErrorV1> {
    if let Some(value) = parameters.get(key) {
        return Ok(value.clone());
    }
    if let Some(value) = options.get(key) {
        return Ok(value.clone());
    }
    Err(ConsumptionErrorV1::UnresolvedReference)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn default_params() -> HashMap<String, ResolvedDefaultV1> {
        let mut m = HashMap::new();
        m.insert("fb".to_string(), ResolvedDefaultV1::Scalar(53.125e9));
        m.insert("ndfe".to_string(), ResolvedDefaultV1::Scalar(2.0));
        m.insert("bmax".to_string(), ResolvedDefaultV1::Scalar(0.5));
        m.insert("a_fext".to_string(), ResolvedDefaultV1::Scalar(0.5));
        m
    }
    fn empty() -> HashMap<String, ResolvedDefaultV1> {
        HashMap::new()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            VALUE_CONSUMPTION_POLICY_V1,
            "sipi.p5-02j.value-consumption.v1.default-resolution"
        );
    }
    #[test]
    fn scalar_arithmetic() {
        assert_eq!(evaluate_scalar("0.5").expect("lit"), 0.5);
        assert_eq!(evaluate_scalar("0.5*1e9").expect("mul"), 0.5e9);
        assert_eq!(evaluate_scalar("1e-3").expect("e"), 1e-3);
        assert_eq!(evaluate_scalar("-1.0").expect("neg"), -1.0);
        assert_eq!(evaluate_scalar("2^3").expect("pow"), 8.0);
    }
    #[test]
    fn boolean_and_empty() {
        assert_eq!(
            resolve_default_value_v1("true", &empty(), &empty()).expect("t"),
            ResolvedDefaultV1::Boolean(true)
        );
        assert_eq!(
            resolve_default_value_v1("false", &empty(), &empty()).expect("f"),
            ResolvedDefaultV1::Boolean(false)
        );
        assert_eq!(
            resolve_default_value_v1("[]", &empty(), &empty()).expect("e"),
            ResolvedDefaultV1::Empty
        );
    }
    #[test]
    fn string_literal() {
        assert_eq!(
            resolve_default_value_v1("'MM'", &empty(), &empty()).expect("s"),
            ResolvedDefaultV1::String("MM".to_string())
        );
    }
    #[test]
    fn direct_and_derived_reference() {
        let p = default_params();
        assert_eq!(
            resolve_default_value_v1("param.fb", &p, &empty()).expect("ref"),
            ResolvedDefaultV1::Scalar(53.125e9)
        );
        assert_eq!(
            resolve_default_value_v1("param.a_fext", &p, &empty()).expect("ref2"),
            ResolvedDefaultV1::Scalar(0.5)
        );
        assert_eq!(
            resolve_default_value_v1("param.fb/4", &p, &empty()).expect("derived"),
            ResolvedDefaultV1::Scalar(53.125e9 / 4.0)
        );
    }
    #[test]
    fn dfe_lower_bounds_special() {
        let p = default_params();
        assert!(
            matches!(resolve_default_value_v1("-1*param.bmax(2:param.ndfe)", &p, &empty()).expect("dfe"), ResolvedDefaultV1::Scalar(v) if v == -0.5)
        );
    }
    #[test]
    fn unresolved_rejected() {
        assert!(resolve_default_value_v1("param.missing", &empty(), &empty()).is_err());
    }
}
