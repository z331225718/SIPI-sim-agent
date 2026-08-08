//! Clean-room IBIS/AMI support for SIPI.
//!
//! This crate deliberately starts with a narrow, lossless-enough IBIS section
//! scanner. AMI parameter semantics and vendor DLL hosting are added in later
//! slices; callers must not infer complete IBIS/AMI coverage from this API.

use std::fmt;

/// A parsed IBIS file, preserving the order of its keyword sections.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IbisDocument {
    sections: Vec<IbisSection>,
}

impl IbisDocument {
    /// Returns sections in physical source order.
    #[must_use]
    pub fn sections(&self) -> &[IbisSection] {
        &self.sections
    }

    /// Returns the first section whose keyword matches ASCII case-insensitively.
    #[must_use]
    pub fn section(&self, keyword: &str) -> Option<&IbisSection> {
        self.sections
            .iter()
            .find(|section| section.keyword.eq_ignore_ascii_case(keyword))
    }

    /// Returns the required `[IBIS Ver]` value.
    #[must_use]
    pub fn ibis_version(&self) -> &str {
        self.sections[0]
            .value
            .as_deref()
            .expect("parse_ibis only constructs documents with an IBIS version")
    }
}

/// A bracketed IBIS keyword and the non-keyword records that follow it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IbisSection {
    keyword: String,
    value: Option<String>,
    line: usize,
    records: Vec<IbisRecord>,
}

impl IbisSection {
    /// The text inside the square brackets, normalized only for outer whitespace.
    #[must_use]
    pub fn keyword(&self) -> &str {
        &self.keyword
    }

    /// Text after the closing bracket, if present.
    #[must_use]
    pub fn value(&self) -> Option<&str> {
        self.value.as_deref()
    }

    /// One-based physical source line for the keyword.
    #[must_use]
    pub const fn line(&self) -> usize {
        self.line
    }

    /// Non-keyword records belonging to this section.
    #[must_use]
    pub fn records(&self) -> &[IbisRecord] {
        &self.records
    }
}

/// A non-keyword IBIS record with its physical source line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IbisRecord {
    line: usize,
    text: String,
}

impl IbisRecord {
    /// One-based physical source line for this record.
    #[must_use]
    pub const fn line(&self) -> usize {
        self.line
    }

    /// Record text after trimming outer whitespace and removing an unquoted comment.
    #[must_use]
    pub fn text(&self) -> &str {
        &self.text
    }
}

/// A structural failure while scanning an IBIS file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IbisParseError {
    /// A non-empty record preceded every bracketed keyword.
    RecordBeforeKeyword { line: usize },
    /// A keyword line began with `[` but did not close it.
    UnterminatedKeyword { line: usize },
    /// A keyword line contained no text between `[` and `]`.
    EmptyKeyword { line: usize },
    /// The first keyword was not `[IBIS Ver]`.
    IbisVersionMustBeFirst { line: usize, found: String },
    /// The required `[IBIS Ver]` header did not provide a version value.
    MissingIbisVersionValue { line: usize },
    /// The source contained no bracketed keyword.
    MissingIbisVersion,
}

impl fmt::Display for IbisParseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::RecordBeforeKeyword { line } => {
                write!(formatter, "IBIS record before first keyword at line {line}")
            }
            Self::UnterminatedKeyword { line } => {
                write!(formatter, "unterminated IBIS keyword at line {line}")
            }
            Self::EmptyKeyword { line } => write!(formatter, "empty IBIS keyword at line {line}"),
            Self::IbisVersionMustBeFirst { line, found } => write!(
                formatter,
                "[IBIS Ver] must be the first keyword; found [{found}] at line {line}"
            ),
            Self::MissingIbisVersionValue { line } => {
                write!(formatter, "[IBIS Ver] has no version value at line {line}")
            }
            Self::MissingIbisVersion => write!(formatter, "missing required [IBIS Ver] keyword"),
        }
    }
}

impl std::error::Error for IbisParseError {}

/// Scans the structural subset of an IBIS file used by later semantic layers.
///
/// The scanner recognizes bracketed keywords, preserves the value following a
/// keyword, and assigns subsequent data records to that keyword. An unquoted
/// `|` begins a comment; a `|` inside single or double quotes remains data.
/// It enforces the required `[IBIS Ver]` header but does not yet validate
/// keyword-specific IBIS or AMI semantics.
pub fn parse_ibis(source: &str) -> Result<IbisDocument, IbisParseError> {
    let mut sections = Vec::new();

    for (offset, raw_line) in source.lines().enumerate() {
        let line = offset + 1;
        let logical = strip_comment(raw_line).trim();
        if logical.is_empty() {
            continue;
        }

        if logical.starts_with('[') {
            let Some(close_offset) = logical.find(']') else {
                return Err(IbisParseError::UnterminatedKeyword { line });
            };
            let keyword = logical[1..close_offset].trim();
            if keyword.is_empty() {
                return Err(IbisParseError::EmptyKeyword { line });
            }
            if sections.is_empty() && !keyword.eq_ignore_ascii_case("IBIS Ver") {
                return Err(IbisParseError::IbisVersionMustBeFirst {
                    line,
                    found: keyword.to_owned(),
                });
            }

            let value = logical[close_offset + 1..].trim();
            if sections.is_empty() && value.is_empty() {
                return Err(IbisParseError::MissingIbisVersionValue { line });
            }
            sections.push(IbisSection {
                keyword: keyword.to_owned(),
                value: (!value.is_empty()).then(|| value.to_owned()),
                line,
                records: Vec::new(),
            });
            continue;
        }

        let Some(section) = sections.last_mut() else {
            return Err(IbisParseError::RecordBeforeKeyword { line });
        };
        section.records.push(IbisRecord {
            line,
            text: logical.to_owned(),
        });
    }

    if sections.is_empty() {
        return Err(IbisParseError::MissingIbisVersion);
    }
    Ok(IbisDocument { sections })
}

fn strip_comment(line: &str) -> &str {
    let mut quote = None;
    let mut escaped = false;
    for (offset, character) in line.char_indices() {
        if escaped {
            escaped = false;
            continue;
        }
        if quote.is_some() && character == '\\' {
            escaped = true;
            continue;
        }
        match (quote, character) {
            (None, '\'' | '"') => quote = Some(character),
            (Some(active), next) if active == next => quote = None,
            (None, '|') => return &line[..offset],
            _ => {}
        }
    }
    line
}

#[cfg(test)]
mod tests {
    use super::{IbisParseError, parse_ibis};

    #[test]
    fn preserves_keywords_records_and_source_lines() {
        let document = parse_ibis(
            "| preamble\n[IBIS Ver] 7.2 | standard version\n[File Name] demo.ibs\n\n[Component] demo\n[Pin]\n1 SIG model | pin comment\n2 GND \"quoted | data\"\n",
        )
        .expect("valid structural IBIS input");

        assert_eq!(document.ibis_version(), "7.2");
        assert_eq!(document.sections().len(), 4);
        assert_eq!(document.section("component").unwrap().value(), Some("demo"));
        let pins = document.section("Pin").unwrap();
        assert_eq!(pins.line(), 6);
        assert_eq!(pins.records()[0].line(), 7);
        assert_eq!(pins.records()[0].text(), "1 SIG model");
        assert_eq!(pins.records()[1].text(), "2 GND \"quoted | data\"");
    }

    #[test]
    fn rejects_records_before_the_header() {
        assert_eq!(
            parse_ibis("orphan\n[IBIS Ver] 7.2\n"),
            Err(IbisParseError::RecordBeforeKeyword { line: 1 })
        );
    }

    #[test]
    fn requires_a_complete_first_version_header() {
        assert_eq!(
            parse_ibis("[Component] demo\n"),
            Err(IbisParseError::IbisVersionMustBeFirst {
                line: 1,
                found: "Component".to_owned(),
            })
        );
        assert_eq!(
            parse_ibis("[IBIS Ver]\n"),
            Err(IbisParseError::MissingIbisVersionValue { line: 1 })
        );
        assert_eq!(
            parse_ibis("| only a comment\n"),
            Err(IbisParseError::MissingIbisVersion)
        );
    }

    #[test]
    fn rejects_malformed_keywords() {
        assert_eq!(
            parse_ibis("[IBIS Ver 7.2\n"),
            Err(IbisParseError::UnterminatedKeyword { line: 1 })
        );
        assert_eq!(
            parse_ibis("[] 7.2\n"),
            Err(IbisParseError::EmptyKeyword { line: 1 })
        );
    }
}
