use std::collections::HashMap;

use crate::error::{Error, Result};

pub fn evaluate(text: &str, parameters: &HashMap<String, f64>) -> Result<f64> {
    let text = text.trim();
    let text = if text.len() >= 2
        && ((text.starts_with('\'') && text.ends_with('\''))
            || (text.starts_with('"') && text.ends_with('"')))
    {
        &text[1..text.len() - 1]
    } else {
        text
    };
    let mut parser = Parser {
        text,
        position: 0,
        parameters,
    };
    let value = parser.parse_additive()?;
    parser.skip_whitespace();
    if parser.position != text.len() {
        return Err(Error::Parse(format!(
            "unexpected expression token in '{}' at byte {}",
            text, parser.position
        )));
    }
    if !value.is_finite() {
        return Err(Error::Parse(format!(
            "numeric expression '{text}' is non-finite"
        )));
    }
    Ok(value)
}

struct Parser<'a> {
    text: &'a str,
    position: usize,
    parameters: &'a HashMap<String, f64>,
}

impl Parser<'_> {
    fn parse_additive(&mut self) -> Result<f64> {
        let mut value = self.parse_multiplicative()?;
        loop {
            self.skip_whitespace();
            if self.consume('+') {
                value += self.parse_multiplicative()?;
            } else if self.consume('-') {
                value -= self.parse_multiplicative()?;
            } else {
                return Ok(value);
            }
        }
    }

    fn parse_multiplicative(&mut self) -> Result<f64> {
        let mut value = self.parse_power()?;
        loop {
            self.skip_whitespace();
            if self.consume('*') {
                value *= self.parse_power()?;
            } else if self.consume('/') {
                value /= self.parse_power()?;
            } else {
                return Ok(value);
            }
        }
    }

    fn parse_power(&mut self) -> Result<f64> {
        let value = self.parse_unary()?;
        self.skip_whitespace();
        if self.consume('^') {
            Ok(value.powf(self.parse_power()?))
        } else {
            Ok(value)
        }
    }

    fn parse_unary(&mut self) -> Result<f64> {
        self.skip_whitespace();
        if self.consume('+') {
            self.parse_unary()
        } else if self.consume('-') {
            Ok(-self.parse_unary()?)
        } else {
            self.parse_primary()
        }
    }

    fn parse_primary(&mut self) -> Result<f64> {
        self.skip_whitespace();
        if self.consume('(') {
            let value = self.parse_additive()?;
            self.expect(')')?;
            return Ok(value);
        }
        if self.consume('{') {
            let value = self.parse_additive()?;
            self.expect('}')?;
            return Ok(value);
        }
        if self
            .peek()
            .is_some_and(|value| value.is_ascii_digit() || value == '.')
        {
            return self.parse_literal();
        }
        let identifier = self.parse_identifier()?;
        self.skip_whitespace();
        if self.consume('(') {
            let mut arguments = Vec::new();
            self.skip_whitespace();
            if !self.consume(')') {
                loop {
                    arguments.push(self.parse_additive()?);
                    self.skip_whitespace();
                    if self.consume(')') {
                        break;
                    }
                    self.expect(',')?;
                }
            }
            return evaluate_function(&identifier, &arguments);
        }
        if identifier.eq_ignore_ascii_case("pi") {
            return Ok(std::f64::consts::PI);
        }
        self.parameters
            .get(&identifier.to_ascii_lowercase())
            .copied()
            .ok_or_else(|| Error::Parse(format!("unknown parameter '{identifier}'")))
    }

    fn parse_literal(&mut self) -> Result<f64> {
        let start = self.position;
        let mut has_digit = false;
        while self.peek().is_some_and(|value| value.is_ascii_digit()) {
            has_digit = true;
            self.advance();
        }
        if self.consume('.') {
            while self.peek().is_some_and(|value| value.is_ascii_digit()) {
                has_digit = true;
                self.advance();
            }
        }
        if !has_digit {
            return Err(Error::Parse(format!(
                "invalid numeric literal in '{}' at byte {start}",
                self.text
            )));
        }
        if self
            .peek()
            .is_some_and(|value| value == 'e' || value == 'E')
        {
            let exponent_start = self.position;
            self.advance();
            if self
                .peek()
                .is_some_and(|value| value == '+' || value == '-')
            {
                self.advance();
            }
            let digits_start = self.position;
            while self.peek().is_some_and(|value| value.is_ascii_digit()) {
                self.advance();
            }
            if digits_start == self.position {
                self.position = exponent_start;
            }
        }
        let number_end = self.position;
        while self.peek().is_some_and(|value| value.is_ascii_alphabetic()) {
            self.advance();
        }
        let token = &self.text[start..self.position];
        let number = self.text[start..number_end]
            .parse::<f64>()
            .map_err(|_| Error::Parse(format!("invalid numeric value '{token}'")))?;
        let suffix = self.text[number_end..self.position].to_ascii_lowercase();
        Ok(number * suffix_multiplier(&suffix, token)?)
    }

    fn parse_identifier(&mut self) -> Result<String> {
        let start = self.position;
        while self
            .peek()
            .is_some_and(|value| value.is_ascii_alphanumeric() || value == '_' || value == '.')
        {
            self.advance();
        }
        if start == self.position {
            return Err(Error::Parse(format!(
                "expected expression value in '{}' at byte {}",
                self.text, self.position
            )));
        }
        Ok(self.text[start..self.position].to_string())
    }

    fn expect(&mut self, expected: char) -> Result<()> {
        self.skip_whitespace();
        if self.consume(expected) {
            Ok(())
        } else {
            Err(Error::Parse(format!(
                "expected '{expected}' in '{}' at byte {}",
                self.text, self.position
            )))
        }
    }

    fn skip_whitespace(&mut self) {
        while self.peek().is_some_and(char::is_whitespace) {
            self.advance();
        }
    }

    fn consume(&mut self, expected: char) -> bool {
        if self.peek() == Some(expected) {
            self.advance();
            true
        } else {
            false
        }
    }

    fn peek(&self) -> Option<char> {
        self.text[self.position..].chars().next()
    }

    fn advance(&mut self) {
        if let Some(value) = self.peek() {
            self.position += value.len_utf8();
        }
    }
}

fn evaluate_function(name: &str, arguments: &[f64]) -> Result<f64> {
    let unary = |operation: fn(f64) -> f64| {
        if arguments.len() == 1 {
            Ok(operation(arguments[0]))
        } else {
            Err(Error::Parse(format!(
                "function '{name}' requires one argument"
            )))
        }
    };
    match name.to_ascii_lowercase().as_str() {
        "sqrt" => unary(f64::sqrt),
        "abs" => unary(f64::abs),
        "exp" => unary(f64::exp),
        "ln" | "log" => unary(f64::ln),
        "log10" => unary(f64::log10),
        "min" if arguments.len() == 2 => Ok(arguments[0].min(arguments[1])),
        "max" if arguments.len() == 2 => Ok(arguments[0].max(arguments[1])),
        "pow" if arguments.len() == 2 => Ok(arguments[0].powf(arguments[1])),
        "min" | "max" | "pow" => Err(Error::Parse(format!(
            "function '{name}' requires two arguments"
        ))),
        _ => Err(Error::Parse(format!("unsupported function '{name}'"))),
    }
}

fn suffix_multiplier(suffix: &str, token: &str) -> Result<f64> {
    if suffix.starts_with("meg") {
        return Ok(1e6);
    }
    if suffix.starts_with("mil") {
        return Ok(25.4e-6);
    }
    match suffix.chars().next() {
        None => Ok(1.0),
        Some('t') => Ok(1e12),
        Some('g') => Ok(1e9),
        Some('k') => Ok(1e3),
        Some('m') => Ok(1e-3),
        Some('u') => Ok(1e-6),
        Some('n') => Ok(1e-9),
        Some('p') => Ok(1e-12),
        Some('f') => Ok(1e-15),
        Some(value) => Err(Error::Parse(format!(
            "unsupported numeric suffix '{value}' in '{token}'"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn evaluates_spice_expressions_and_suffixes() {
        let mut parameters = HashMap::new();
        parameters.insert("base".into(), 500.0);
        assert_eq!(evaluate("{base*sqrt(4)}", &parameters).unwrap(), 1000.0);
        assert_eq!(evaluate("max(1, 3-1)", &parameters).unwrap(), 2.0);
        assert_eq!(evaluate("2.5meg/5k", &parameters).unwrap(), 500.0);
    }
}
