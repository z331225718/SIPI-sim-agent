#![forbid(unsafe_code)]

//! Clean-room bounded structural parsing for AMI-like text forms.
//!
//! This crate intentionally has no AMI parameter, model, ABI, file, or runtime
//! semantics. It retains only bounded UTF-8 structural text and source spans.

use std::{error::Error, fmt, num::NonZeroUsize};

/// A byte and physical source location in an input document.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SourceSpanV1 {
    byte_start: usize,
    byte_end: usize,
    line: usize,
    column_start: usize,
}

impl SourceSpanV1 {
    const fn new(byte_start: usize, byte_end: usize, line: usize, column_start: usize) -> Self {
        Self {
            byte_start,
            byte_end,
            line,
            column_start,
        }
    }

    pub const fn byte_start(self) -> usize {
        self.byte_start
    }

    pub const fn byte_end(self) -> usize {
        self.byte_end
    }

    pub const fn line(self) -> usize {
        self.line
    }

    pub const fn column_start(self) -> usize {
        self.column_start
    }
}

/// Original token spelling and its byte-based source span.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiTextTokenV1 {
    spelling: String,
    span: SourceSpanV1,
}

impl AmiTextTokenV1 {
    pub fn spelling(&self) -> &str {
        &self.spelling
    }

    pub const fn span(&self) -> SourceSpanV1 {
        self.span
    }
}

/// One balanced list in the structural document.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiTextListV1 {
    open_span: SourceSpanV1,
    close_span: SourceSpanV1,
    items: Vec<AmiTextNodeV1>,
}

impl AmiTextListV1 {
    pub const fn open_span(&self) -> SourceSpanV1 {
        self.open_span
    }

    pub const fn close_span(&self) -> SourceSpanV1 {
        self.close_span
    }

    pub fn items(&self) -> &[AmiTextNodeV1] {
        &self.items
    }
}

/// A structural node. Quoted spelling includes its surrounding quotes and any
/// escape characters; this layer deliberately does not decode it.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AmiTextNodeV1 {
    List(AmiTextListV1),
    Atom(AmiTextTokenV1),
    Quoted(AmiTextTokenV1),
}

/// A complete successful parse. It contains no semantic validation result.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiTextDocumentV1 {
    forms: Vec<AmiTextListV1>,
}

/// Caller-provided AMI text retained byte-for-byte after a successful parse.
/// It has no path, origin, model, DLL, or semantic metadata.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RawAmiTextV1 {
    bytes: Vec<u8>,
}

impl RawAmiTextV1 {
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }

    pub const fn byte_len(&self) -> usize {
        self.bytes.len()
    }
}

/// Exact in-memory association of retained raw bytes and their structural AST.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiTextBindingV1 {
    raw: RawAmiTextV1,
    document: AmiTextDocumentV1,
}

impl AmiTextBindingV1 {
    pub fn raw(&self) -> &RawAmiTextV1 {
        &self.raw
    }

    pub fn document(&self) -> &AmiTextDocumentV1 {
        &self.document
    }
}

impl AmiTextDocumentV1 {
    pub fn forms(&self) -> &[AmiTextListV1] {
        &self.forms
    }
}

/// Explicit limits for one parse operation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ParseLimitsV1 {
    max_input_bytes: NonZeroUsize,
    max_nesting_depth: NonZeroUsize,
    max_nodes: NonZeroUsize,
    max_token_bytes: NonZeroUsize,
}

impl ParseLimitsV1 {
    pub fn try_new(
        max_input_bytes: usize,
        max_nesting_depth: usize,
        max_nodes: usize,
        max_token_bytes: usize,
    ) -> Result<Self, LimitErrorV1> {
        Ok(Self {
            max_input_bytes: NonZeroUsize::new(max_input_bytes).ok_or(LimitErrorV1::Zero)?,
            max_nesting_depth: NonZeroUsize::new(max_nesting_depth).ok_or(LimitErrorV1::Zero)?,
            max_nodes: NonZeroUsize::new(max_nodes).ok_or(LimitErrorV1::Zero)?,
            max_token_bytes: NonZeroUsize::new(max_token_bytes).ok_or(LimitErrorV1::Zero)?,
        })
    }

    pub const fn max_input_bytes(self) -> NonZeroUsize {
        self.max_input_bytes
    }

    pub const fn max_nesting_depth(self) -> NonZeroUsize {
        self.max_nesting_depth
    }

    pub const fn max_nodes(self) -> NonZeroUsize {
        self.max_nodes
    }

    pub const fn max_token_bytes(self) -> NonZeroUsize {
        self.max_token_bytes
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LimitErrorV1 {
    Zero,
}

impl fmt::Display for LimitErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "AMI text parse limits must be nonzero")
    }
}

impl Error for LimitErrorV1 {}

/// Stable fail-closed structural parse diagnostics.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiTextDiagnosticCodeV1 {
    InputLimitExceeded,
    InvalidUtf8,
    NulByte,
    ForbiddenControlCharacter,
    BareCarriageReturn,
    NestingLimitExceeded,
    NodeLimitExceeded,
    TokenLimitExceeded,
    UnexpectedClosingParenthesis,
    TopLevelAtom,
    UnclosedList,
    UnterminatedQuotedText,
}

/// A stable diagnostic with bounded source context.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AmiTextDiagnosticV1 {
    code: AmiTextDiagnosticCodeV1,
    span: SourceSpanV1,
}

impl AmiTextDiagnosticV1 {
    pub const fn code(self) -> AmiTextDiagnosticCodeV1 {
        self.code
    }

    pub const fn span(self) -> SourceSpanV1 {
        self.span
    }
}

impl fmt::Display for AmiTextDiagnosticV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "AMI text structural parse {:?} at line {}, column {}",
            self.code, self.span.line, self.span.column_start
        )
    }
}

impl Error for AmiTextDiagnosticV1 {}

/// Fail-closed errors for an exact raw-text binding check.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AmiTextBindingErrorV1 {
    Parse(AmiTextDiagnosticV1),
    RawBytesMismatch,
    StructuralIdentityMismatch,
}

impl fmt::Display for AmiTextBindingErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Parse(error) => write!(formatter, "raw AMI text binding parse error: {error}"),
            Self::RawBytesMismatch => write!(formatter, "raw AMI text bytes do not match binding"),
            Self::StructuralIdentityMismatch => {
                write!(
                    formatter,
                    "raw AMI text structural identity does not match binding"
                )
            }
        }
    }
}

impl Error for AmiTextBindingErrorV1 {}

/// Semantic validation is intentionally unavailable in this structural layer.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiTextSemanticStatusV1 {
    RulesUnavailable,
}

pub const fn semantic_validation_status_v1() -> AmiTextSemanticStatusV1 {
    AmiTextSemanticStatusV1::RulesUnavailable
}

/// Parses bounded UTF-8 parenthesized forms without AMI parameter semantics.
pub fn parse_ami_text_v1(
    bytes: &[u8],
    limits: ParseLimitsV1,
) -> Result<AmiTextDocumentV1, AmiTextDiagnosticV1> {
    if bytes.len() > limits.max_input_bytes.get() {
        return Err(diagnostic(
            AmiTextDiagnosticCodeV1::InputLimitExceeded,
            0,
            0,
            1,
            1,
        ));
    }
    let source = std::str::from_utf8(bytes).map_err(|error| {
        diagnostic(
            AmiTextDiagnosticCodeV1::InvalidUtf8,
            error.valid_up_to(),
            error.valid_up_to(),
            1,
            1,
        )
    })?;
    validate_characters(source)?;

    let mut parser = Parser {
        source,
        limits,
        offset: 0,
        line: 1,
        column: 1,
        nodes: 0,
    };
    let mut forms = Vec::new();
    parser.skip_ignorable()?;
    while !parser.at_end() {
        if parser.peek_char() == Some(')') {
            return Err(
                parser.current_diagnostic(AmiTextDiagnosticCodeV1::UnexpectedClosingParenthesis, 1)
            );
        }
        if parser.peek_char() != Some('(') {
            return Err(parser.current_diagnostic(AmiTextDiagnosticCodeV1::TopLevelAtom, 1));
        }
        forms.push(parser.parse_list(1)?);
        parser.skip_ignorable()?;
    }
    Ok(AmiTextDocumentV1 { forms })
}

/// Parses and retains exactly one caller-provided raw AMI text byte sequence.
/// No newline, Unicode, case, or token-spelling normalization is performed.
pub fn parse_and_bind_v1(
    bytes: &[u8],
    limits: ParseLimitsV1,
) -> Result<AmiTextBindingV1, AmiTextDiagnosticV1> {
    let document = parse_ami_text_v1(bytes, limits)?;
    Ok(AmiTextBindingV1 {
        raw: RawAmiTextV1 {
            bytes: bytes.to_vec(),
        },
        document,
    })
}

/// Verifies that supplied bytes exactly match a binding and reconstruct the
/// same structural document under explicit limits.
pub fn verify_binding_v1(
    bytes: &[u8],
    binding: &AmiTextBindingV1,
    limits: ParseLimitsV1,
) -> Result<(), AmiTextBindingErrorV1> {
    if bytes != binding.raw.bytes() {
        return Err(AmiTextBindingErrorV1::RawBytesMismatch);
    }
    let document = parse_ami_text_v1(bytes, limits).map_err(AmiTextBindingErrorV1::Parse)?;
    if document != binding.document {
        return Err(AmiTextBindingErrorV1::StructuralIdentityMismatch);
    }
    Ok(())
}

struct Parser<'a> {
    source: &'a str,
    limits: ParseLimitsV1,
    offset: usize,
    line: usize,
    column: usize,
    nodes: usize,
}

impl Parser<'_> {
    fn parse_list(&mut self, depth: usize) -> Result<AmiTextListV1, AmiTextDiagnosticV1> {
        if depth > self.limits.max_nesting_depth.get() {
            return Err(self.current_diagnostic(AmiTextDiagnosticCodeV1::NestingLimitExceeded, 0));
        }
        let open_span = self.current_span(1);
        self.consume_char();
        self.take_node()?;
        let mut items = Vec::new();
        loop {
            self.skip_ignorable()?;
            if self.at_end() {
                return Err(diagnostic(
                    AmiTextDiagnosticCodeV1::UnclosedList,
                    open_span.byte_start,
                    open_span.byte_end,
                    open_span.line,
                    open_span.column_start,
                ));
            }
            match self.peek_char() {
                Some(')') => {
                    let close_span = self.current_span(1);
                    self.consume_char();
                    return Ok(AmiTextListV1 {
                        open_span,
                        close_span,
                        items,
                    });
                }
                Some('(') => items.push(AmiTextNodeV1::List(self.parse_list(depth + 1)?)),
                Some('"') => items.push(AmiTextNodeV1::Quoted(self.parse_quoted()?)),
                Some(_) => items.push(AmiTextNodeV1::Atom(self.parse_atom()?)),
                None => unreachable!("at_end is checked above"),
            }
        }
    }

    fn parse_atom(&mut self) -> Result<AmiTextTokenV1, AmiTextDiagnosticV1> {
        self.take_node()?;
        let start = self.offset;
        let line = self.line;
        let column = self.column;
        while let Some(character) = self.peek_char() {
            if character.is_whitespace() || matches!(character, '(' | ')' | '"' | '|') {
                break;
            }
            self.consume_char();
        }
        self.token_from(start, line, column)
    }

    fn parse_quoted(&mut self) -> Result<AmiTextTokenV1, AmiTextDiagnosticV1> {
        self.take_node()?;
        let start = self.offset;
        let line = self.line;
        let column = self.column;
        self.consume_char();
        loop {
            let Some(character) = self.peek_char() else {
                return Err(diagnostic(
                    AmiTextDiagnosticCodeV1::UnterminatedQuotedText,
                    start,
                    self.offset,
                    line,
                    column,
                ));
            };
            if matches!(character, '\n' | '\r') {
                return Err(diagnostic(
                    AmiTextDiagnosticCodeV1::UnterminatedQuotedText,
                    start,
                    self.offset,
                    line,
                    column,
                ));
            }
            self.consume_char();
            if character == '\\' {
                if self.at_end() || matches!(self.peek_char(), Some('\n' | '\r')) {
                    return Err(diagnostic(
                        AmiTextDiagnosticCodeV1::UnterminatedQuotedText,
                        start,
                        self.offset,
                        line,
                        column,
                    ));
                }
                self.consume_char();
            } else if character == '"' {
                return self.token_from(start, line, column);
            }
        }
    }

    fn token_from(
        &self,
        start: usize,
        line: usize,
        column: usize,
    ) -> Result<AmiTextTokenV1, AmiTextDiagnosticV1> {
        let length = self.offset - start;
        if length > self.limits.max_token_bytes.get() {
            return Err(diagnostic(
                AmiTextDiagnosticCodeV1::TokenLimitExceeded,
                start,
                self.offset,
                line,
                column,
            ));
        }
        Ok(AmiTextTokenV1 {
            spelling: self.source[start..self.offset].to_owned(),
            span: SourceSpanV1::new(start, self.offset, line, column),
        })
    }

    fn take_node(&mut self) -> Result<(), AmiTextDiagnosticV1> {
        self.nodes = self.nodes.checked_add(1).ok_or_else(|| {
            self.current_diagnostic(AmiTextDiagnosticCodeV1::NodeLimitExceeded, 0)
        })?;
        if self.nodes > self.limits.max_nodes.get() {
            return Err(self.current_diagnostic(AmiTextDiagnosticCodeV1::NodeLimitExceeded, 0));
        }
        Ok(())
    }

    fn skip_ignorable(&mut self) -> Result<(), AmiTextDiagnosticV1> {
        loop {
            match self.peek_char() {
                Some(' ' | '\t' | '\n') => self.consume_char(),
                Some('\r') => {
                    if self.source.as_bytes().get(self.offset + 1) != Some(&b'\n') {
                        return Err(
                            self.current_diagnostic(AmiTextDiagnosticCodeV1::BareCarriageReturn, 1)
                        );
                    }
                    self.offset += 2;
                    self.line += 1;
                    self.column = 1;
                }
                Some('|') => {
                    while let Some(character) = self.peek_char() {
                        if matches!(character, '\n' | '\r') {
                            break;
                        }
                        self.consume_char();
                    }
                }
                _ => return Ok(()),
            }
        }
    }

    fn at_end(&self) -> bool {
        self.offset == self.source.len()
    }

    fn peek_char(&self) -> Option<char> {
        self.source[self.offset..].chars().next()
    }

    fn consume_char(&mut self) {
        let character = self.peek_char().expect("consume only within source");
        self.offset += character.len_utf8();
        if character == '\n' {
            self.line += 1;
            self.column = 1;
        } else {
            self.column += 1;
        }
    }

    fn current_span(&self, byte_length: usize) -> SourceSpanV1 {
        SourceSpanV1::new(
            self.offset,
            self.offset.saturating_add(byte_length),
            self.line,
            self.column,
        )
    }

    fn current_diagnostic(
        &self,
        code: AmiTextDiagnosticCodeV1,
        byte_length: usize,
    ) -> AmiTextDiagnosticV1 {
        AmiTextDiagnosticV1 {
            code,
            span: self.current_span(byte_length),
        }
    }
}

fn validate_characters(source: &str) -> Result<(), AmiTextDiagnosticV1> {
    let mut line = 1;
    let mut column = 1;
    let mut previous_was_cr = false;
    for (offset, character) in source.char_indices() {
        if character == '\0' {
            return Err(diagnostic(
                AmiTextDiagnosticCodeV1::NulByte,
                offset,
                offset + 1,
                line,
                column,
            ));
        }
        if character == '\r' {
            previous_was_cr = true;
            continue;
        }
        if previous_was_cr && character != '\n' {
            return Err(diagnostic(
                AmiTextDiagnosticCodeV1::BareCarriageReturn,
                offset - 1,
                offset,
                line,
                column,
            ));
        }
        previous_was_cr = false;
        if character.is_control() && !matches!(character, '\t' | '\n') {
            return Err(diagnostic(
                AmiTextDiagnosticCodeV1::ForbiddenControlCharacter,
                offset,
                offset + character.len_utf8(),
                line,
                column,
            ));
        }
        if character == '\n' {
            line += 1;
            column = 1;
        } else {
            column += 1;
        }
    }
    if previous_was_cr {
        return Err(diagnostic(
            AmiTextDiagnosticCodeV1::BareCarriageReturn,
            source.len() - 1,
            source.len(),
            line,
            column,
        ));
    }
    Ok(())
}

const fn diagnostic(
    code: AmiTextDiagnosticCodeV1,
    byte_start: usize,
    byte_end: usize,
    line: usize,
    column_start: usize,
) -> AmiTextDiagnosticV1 {
    AmiTextDiagnosticV1 {
        code,
        span: SourceSpanV1::new(byte_start, byte_end, line, column_start),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(512, 8, 32, 64).expect("limits")
    }

    #[test]
    fn retains_order_spelling_comments_and_spans() {
        let document = parse_ami_text_v1(
            b"| comment\r\n(root alpha (nested \"two words\"))\n(next)",
            limits(),
        )
        .expect("parse");
        assert_eq!(document.forms().len(), 2);
        assert_eq!(document.forms()[0].open_span().line(), 2);
        assert_eq!(document.forms()[0].items().len(), 3);
        let AmiTextNodeV1::Atom(atom) = &document.forms()[0].items()[0] else {
            panic!("atom");
        };
        assert_eq!(atom.spelling(), "root");
        let AmiTextNodeV1::List(nested) = &document.forms()[0].items()[2] else {
            panic!("nested list");
        };
        let AmiTextNodeV1::Quoted(quoted) = &nested.items()[1] else {
            panic!("quoted");
        };
        assert_eq!(quoted.spelling(), "\"two words\"");
    }

    #[test]
    fn rejects_invalid_encoding_structure_and_limits_without_a_partial_document() {
        let cases = [
            (b"(x\0)".as_slice(), AmiTextDiagnosticCodeV1::NulByte),
            (b"(\x80)".as_slice(), AmiTextDiagnosticCodeV1::InvalidUtf8),
            (
                b"(x\r)".as_slice(),
                AmiTextDiagnosticCodeV1::BareCarriageReturn,
            ),
            (b"x".as_slice(), AmiTextDiagnosticCodeV1::TopLevelAtom),
            (
                b")".as_slice(),
                AmiTextDiagnosticCodeV1::UnexpectedClosingParenthesis,
            ),
            (b"(x".as_slice(), AmiTextDiagnosticCodeV1::UnclosedList),
            (
                b"(\"x)".as_slice(),
                AmiTextDiagnosticCodeV1::UnterminatedQuotedText,
            ),
        ];
        for (source, expected) in cases {
            assert_eq!(
                parse_ami_text_v1(source, limits())
                    .expect_err("reject")
                    .code(),
                expected
            );
        }
        let token_limited = ParseLimitsV1::try_new(64, 4, 8, 2).expect("limits");
        assert_eq!(
            parse_ami_text_v1(b"(abc)", token_limited)
                .expect_err("token limit")
                .code(),
            AmiTextDiagnosticCodeV1::TokenLimitExceeded
        );
        let depth_limited = ParseLimitsV1::try_new(64, 1, 8, 8).expect("limits");
        assert_eq!(
            parse_ami_text_v1(b"((x))", depth_limited)
                .expect_err("depth limit")
                .code(),
            AmiTextDiagnosticCodeV1::NestingLimitExceeded
        );
        let node_limited = ParseLimitsV1::try_new(64, 4, 2, 8).expect("limits");
        assert_eq!(
            parse_ami_text_v1(b"(a b)", node_limited)
                .expect_err("node limit")
                .code(),
            AmiTextDiagnosticCodeV1::NodeLimitExceeded
        );
    }

    #[test]
    fn treats_semantics_as_unavailable_and_is_deterministic() {
        let source = b"(future_key value)";
        let first = parse_ami_text_v1(source, limits()).expect("first");
        let second = parse_ami_text_v1(source, limits()).expect("second");
        assert_eq!(first, second);
        assert_eq!(
            semantic_validation_status_v1(),
            AmiTextSemanticStatusV1::RulesUnavailable
        );
        assert_eq!(ParseLimitsV1::try_new(0, 1, 1, 1), Err(LimitErrorV1::Zero));
    }

    #[test]
    fn binds_exact_raw_bytes_without_normalizing_or_accepting_drift() {
        let source = b"(key \"A\\\\B\"\r\n  value)";
        let binding = parse_and_bind_v1(source, limits()).expect("binding");
        assert_eq!(binding.raw().bytes(), source);
        assert_eq!(binding.raw().byte_len(), source.len());
        verify_binding_v1(source, &binding, limits()).expect("exact binding");
        assert_eq!(
            verify_binding_v1(b"(key \"A\\\\B\"\n  value)", &binding, limits()),
            Err(AmiTextBindingErrorV1::RawBytesMismatch)
        );
        let forged = AmiTextBindingV1 {
            raw: binding.raw.clone(),
            document: parse_ami_text_v1(b"(other)", limits()).expect("other document"),
        };
        assert_eq!(
            verify_binding_v1(source, &forged, limits()),
            Err(AmiTextBindingErrorV1::StructuralIdentityMismatch)
        );
    }
}
