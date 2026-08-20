//! R480 MATLAB numeric-literal parser (P5-02k).
//!
//! Port of agent-com config/literals.py (MIT source, P5-02k): full
//! parse_matlab_literal, _vector, _expand_scaled_ones and _COLON covering
//! the empty literal, bracket vector/matrix literals, MATLAB colon ranges,
//! the bounded scaled-ones idiom N*ones(1,M) inside bracket rows, and the
//! single-negative disambiguation ([1 - 2] == -1 vs [1 -2] == [1,-2]).
//! Scalar arithmetic delegates to the shared scalar evaluator in
//! value_consumption_v1.

use super::value_consumption_v1::{evaluate_scalar, ConsumptionErrorV1, ResolvedDefaultV1};

/// A resolved MATLAB numeric literal (P5-02k).
#[derive(Clone, Debug, PartialEq)]
pub enum LiteralV1 {
    Scalar(f64),
    Vector(Vec<f64>),
    Matrix(Vec<Vec<f64>>),
    Empty,
}

/// A number token: [+-]? (digits[.digits?] | .digits) ([eE][+-]?digits)?
fn is_number_token(token: &str) -> bool {
    let t = token.trim();
    if t.is_empty() {
        return false;
    }
    let bytes = t.as_bytes();
    let mut i = 0;
    if bytes[i] == b'+' || bytes[i] == b'-' {
        i += 1;
    }
    let mut has_digit = false;
    let mut has_dot = false;
    while i < bytes.len() {
        match bytes[i] {
            b'0'..=b'9' => {
                has_digit = true;
                i += 1;
            }
            b'.' if !has_dot => {
                has_dot = true;
                i += 1;
            }
            b'e' | b'E' if has_digit && i > 0 && (bytes[i - 1].is_ascii_digit() || bytes[i - 1] == b'.') => {
                i += 1;
                if i < bytes.len() && (bytes[i] == b'+' || bytes[i] == b'-') {
                    i += 1;
                }
                let mut exp_digit = false;
                while i < bytes.len() && bytes[i].is_ascii_digit() {
                    exp_digit = true;
                    i += 1;
                }
                if !exp_digit {
                    return false;
                }
                has_digit = true;
                break;
            }
            _ => return false,
        }
    }
    has_digit
}

/// `1:5` or `1:2:9` colon-range token -> optional expanded values.
fn colon_range(token: &str) -> Option<Vec<f64>> {
    let t = token.trim();
    if t.is_empty() {
        return None;
    }
    let parts: Vec<&str> = t.split(':').collect();
    if parts.len() < 2 || parts.len() > 3 {
        return None;
    }
    if !parts.iter().all(|p| is_number_token(p)) {
        return None;
    }
    let start: f64 = parts[0].trim().parse().ok()?;
    let second: f64 = parts[1].trim().parse().ok()?;
    let third: Option<f64> = if parts.len() == 3 {
        Some(parts[2].trim().parse().ok()?)
    } else {
        None
    };
    let (step, end) = match third {
        None => (1.0, second),
        Some(stop) => (second, stop),
    };
    if step == 0.0 || (end - start) * step < 0.0 {
        return Some(Vec::new());
    }
    let count = (((end - start) / step) + 1e-12).floor() as i64 + 1;
    if count < 0 {
        return Some(Vec::new());
    }
    let mut values = Vec::with_capacity(count as usize);
    for i in 0..count {
        values.push(start + step * (i as f64));
    }
    Some(values)
}

/// Collapse whitespace around colon operators within a row.
fn compact_colon(row: &str) -> String {
    let mut out = String::new();
    let chars: Vec<char> = row.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == ':' {
            if out.ends_with(' ') {
                out.pop();
            }
            out.push(':');
            i += 1;
            while i < chars.len() && chars[i] == ' ' {
                i += 1;
            }
        } else {
            out.push(chars[i]);
            i += 1;
        }
    }
    out
}

/// Port of _expand_scaled_ones: replace N*ones(1,M) -> "N N ... N" (M times).
fn expand_scaled_ones(row: &str) -> Result<String, ConsumptionErrorV1> {
    let bytes = row.as_bytes();
    let lower = row.to_ascii_lowercase();
    let mut out = String::new();
    let mut i = 0;
    while i < bytes.len() {
        if i + 4 < bytes.len() + 1 && lower[i..].starts_with("ones(") {
            // Find the '*' immediately before 'ones' (allowing spaces).
            let mut star_idx: Option<usize> = None;
            let mut p = i;
            while p > 0 && (bytes[p - 1] == b' ' || bytes[p - 1] == b'\t') {
                p -= 1;
            }
            if p > 0 && bytes[p - 1] == b'*' {
                star_idx = Some(p - 1);
            }
            let star = match star_idx {
                Some(s) => s,
                None => {
                    out.push(bytes[i] as char);
                    i += 1;
                    continue;
                }
            };
            // scan the factor immediately before the '*'
            let mut k2 = star;
            while k2 > 0 {
                let c = bytes[k2 - 1];
                if c.is_ascii_digit() || c == b'.' || c == b'e' || c == b'E' || c == b'+' || c == b'-' {
                    k2 -= 1;
                } else {
                    break;
                }
            }
            if k2 == star {
                out.push(bytes[i] as char);
                i += 1;
                continue;
            }
            let factor_str = &row[k2..star];
            if !is_number_token(factor_str) {
                out.push(bytes[i] as char);
                i += 1;
                continue;
            }
            // find matching close paren for "ones(" at i
            let mut depth = 0usize;
            let mut m = i + 5;
            let mut close = None;
            while m < bytes.len() {
                match bytes[m] {
                    b'(' => depth += 1,
                    b')' => {
                        if depth == 0 {
                            close = Some(m);
                            break;
                        }
                        depth -= 1;
                    }
                    _ => {}
                }
                m += 1;
            }
            let close = match close {
                Some(c) => c,
                None => return Err(ConsumptionErrorV1::InvalidLiteral),
            };
            let args = &row[i + 5..close];
            let comma = args.find(',').ok_or(ConsumptionErrorV1::InvalidLiteral)?;
            let dim1: usize = args[..comma].trim().parse().map_err(|_| ConsumptionErrorV1::InvalidLiteral)?;
            let dim2: usize = args[comma + 1..].trim().parse().map_err(|_| ConsumptionErrorV1::InvalidLiteral)?;
            if dim1 != 1 || dim2 < 1 || dim2 > 4096 {
                return Err(ConsumptionErrorV1::UnsafeExpression);
            }
            let factor: f64 = factor_str.parse().map_err(|_| ConsumptionErrorV1::InvalidLiteral)?;
            let mut repeat = String::new();
            for _ in 0..dim2 {
                if !repeat.is_empty() {
                    repeat.push(' ');
                }
                repeat.push_str(&format!("{}", factor));
            }
            // Replace the whole {factor}*ones(1,M) span with M repeated
            // factors (port of _SCALED_ONES.sub). The factor+star bytes are
            // already in `out` (pushed byte-by-byte), so truncate them.
            let factor_span = star.saturating_sub(k2) + 1; // factor + '*'
            let new_len = out.len().saturating_sub(factor_span);
            out.truncate(new_len);
            out.push_str(&repeat);
            i = close + 1;
            continue;
        }
        out.push(bytes[i] as char);
        i += 1;
    }
    Ok(out)
}

/// Port of literals._vector on a single row string.
fn parse_row(row: &str) -> Result<Vec<f64>, ConsumptionErrorV1> {
    let compact = compact_colon(row);
    let compact = compact.trim().to_string();
    if has_spaced_sign(&compact) {
        return Ok(vec![evaluate_scalar(&compact)?]);
    }
    let mut values = Vec::new();
    for token in split_on_sep(&compact) {
        if token.is_empty() {
            continue;
        }
        if let Some(range) = colon_range(token) {
            values.extend(range);
        } else {
            values.push(evaluate_scalar(token)?);
        }
    }
    Ok(values)
}

/// Does the row contain a whitespace-padded '+'/'-' binomial sign?
fn has_spaced_sign(text: &str) -> bool {
    let bytes = text.as_bytes();
    if bytes.len() < 3 {
        return false;
    }
    for i in 1..bytes.len() - 1 {
        if (bytes[i] == b'+' || bytes[i] == b'-')
            && (bytes[i - 1] == b' ' || bytes[i - 1] == b'\t')
            && (bytes[i + 1] == b' ' || bytes[i + 1] == b'\t')
        {
            return true;
        }
    }
    false
}

/// Split on whitespace or commas (port of re.split(r"[ ,]+", compact)).
fn split_on_sep<'a>(text: &'a str) -> Vec<&'a str> {
    let mut tokens = Vec::new();
    let mut start: Option<usize> = None;
    for (i, ch) in text.char_indices() {
        if ch == ' ' || ch == '\t' || ch == ',' {
            if let Some(s) = start.take() {
                tokens.push(&text[s..i]);
            }
        } else if start.is_none() {
            start = Some(i);
        }
    }
    if let Some(s) = start {
        tokens.push(&text[s..]);
    }
    tokens
}

/// Full literal parser (port of parse_matlab_literal).
pub fn parse_literal_v1(value: &str) -> Result<LiteralV1, ConsumptionErrorV1> {
    let text = value.trim();
    if text == "[]" {
        return Ok(LiteralV1::Empty);
    }
    if text.starts_with('[') && text.ends_with(']') {
        let inner = &text[1..text.len() - 1];
        let mut rows = Vec::new();
        for raw_row in inner.split(';') {
            let expanded = expand_scaled_ones(raw_row)?;
            rows.push(parse_row(&expanded)?);
        }
        if rows.len() == 1 {
            let row = rows.into_iter().next().unwrap();
            if row.is_empty() {
                return Ok(LiteralV1::Empty);
            }
            return Ok(LiteralV1::Vector(row));
        }
        let first_len = rows[0].len();
        if rows.iter().any(|r| r.len() != first_len) {
            return Err(ConsumptionErrorV1::InvalidLiteral);
        }
        return Ok(LiteralV1::Matrix(rows));
    }
    if colon_range(text).is_some() {
        return Ok(LiteralV1::Vector(parse_row(text)?));
    }
    Ok(LiteralV1::Scalar(evaluate_scalar(text)?))
}

impl LiteralV1 {
    pub fn to_resolved(&self) -> ResolvedDefaultV1 {
        match self {
            LiteralV1::Scalar(v) => ResolvedDefaultV1::Scalar(*v),
            LiteralV1::Vector(v) => ResolvedDefaultV1::Vector(v.clone()),
            LiteralV1::Matrix(m) => ResolvedDefaultV1::Matrix(m.clone()),
            LiteralV1::Empty => ResolvedDefaultV1::Empty,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn vector_and_matrix_literals() {
        assert_eq!(
            parse_literal_v1("[1 3 2 4]").unwrap(),
            LiteralV1::Vector(vec![1.0, 3.0, 2.0, 4.0])
        );
        assert_eq!(parse_literal_v1("[50,50]").unwrap(), LiteralV1::Vector(vec![50.0, 50.0]));
        assert_eq!(parse_literal_v1("[0 0]").unwrap(), LiteralV1::Vector(vec![0.0, 0.0]));
        assert_eq!(
            parse_literal_v1("[1 2; 3 4]").unwrap(),
            LiteralV1::Matrix(vec![vec![1.0, 2.0], vec![3.0, 4.0]])
        );
    }

    #[test]
    fn colon_ranges() {
        assert_eq!(parse_literal_v1("[1:1:3]").unwrap(), LiteralV1::Vector(vec![1.0, 2.0, 3.0]));
        assert_eq!(parse_literal_v1("[1:3]").unwrap(), LiteralV1::Vector(vec![1.0, 2.0, 3.0]));
    }

    #[test]
    fn single_negative_disambiguation() {
        assert_eq!(parse_literal_v1("[1 - 2]").unwrap(), LiteralV1::Vector(vec![-1.0]));
        assert_eq!(parse_literal_v1("[1 -2]").unwrap(), LiteralV1::Vector(vec![1.0, -2.0]));
        assert_eq!(parse_literal_v1("[-50 -50]").unwrap(), LiteralV1::Vector(vec![-50.0, -50.0]));
    }

    #[test]
    fn scaled_ones_inside_row() {
        let exp = expand_scaled_ones("0.5*ones(1,4)").expect("expand");
        let parsed = parse_row(&exp).expect("row");
        assert_eq!(parsed, vec![0.5; 4]);
    }

    #[test]
    fn empty_literal() {
        assert_eq!(parse_literal_v1("[]").unwrap(), LiteralV1::Empty);
    }

    #[test]
    fn scalar_delegation() {
        assert_eq!(parse_literal_v1("78.2").unwrap(), LiteralV1::Scalar(78.2));
        assert_eq!(parse_literal_v1("92").unwrap(), LiteralV1::Scalar(92.0));
        assert_eq!(parse_literal_v1("0.5").unwrap(), LiteralV1::Scalar(0.5));
    }
}
