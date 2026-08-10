#![forbid(unsafe_code)]

//! Clean-room structural parsing for bounded IBIS text input.
//!
//! This crate recognizes physical lines, comments, bracketed keyword records,
//! and whitespace-delimited data records. It deliberately assigns no IBIS
//! electrical, package, PVT, AMI, or table semantics.

use std::{error::Error, fmt, num::NonZeroUsize};

/// A byte and physical-line location in one UTF-8-free ASCII source stream.
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

/// Newline spelling retained for source diagnostics; neither spelling has
/// semantic meaning in this structural layer.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LineEndingV1 {
    Lf,
    Crlf,
    EndOfInput,
}

/// One physical input line before comment stripping.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PhysicalLineV1 {
    span: SourceSpanV1,
    ending: LineEndingV1,
}

impl PhysicalLineV1 {
    pub const fn span(&self) -> SourceSpanV1 {
        self.span
    }

    pub const fn ending(&self) -> LineEndingV1 {
        self.ending
    }
}

/// A source token with its original ASCII spelling.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct StructuralTokenV1 {
    spelling: String,
    span: SourceSpanV1,
}

impl StructuralTokenV1 {
    pub fn spelling(&self) -> &str {
        &self.spelling
    }

    pub const fn span(&self) -> SourceSpanV1 {
        self.span
    }
}

/// A keyword or opaque data record. Unknown keywords stay structural tokens.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum StructuralRecordV1 {
    Keyword {
        keyword: StructuralTokenV1,
        payload: Vec<StructuralTokenV1>,
        span: SourceSpanV1,
    },
    Data {
        tokens: Vec<StructuralTokenV1>,
        span: SourceSpanV1,
    },
}

impl StructuralRecordV1 {
    pub const fn span(&self) -> SourceSpanV1 {
        match self {
            Self::Keyword { span, .. } | Self::Data { span, .. } => *span,
        }
    }
}

/// A successful structural parse. It contains no semantic validation result.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IbisDocumentV1 {
    physical_lines: Vec<PhysicalLineV1>,
    records: Vec<StructuralRecordV1>,
}

impl IbisDocumentV1 {
    pub fn physical_lines(&self) -> &[PhysicalLineV1] {
        &self.physical_lines
    }

    pub fn records(&self) -> &[StructuralRecordV1] {
        &self.records
    }
}

/// A lexically valid document-version token. It does not select a supported
/// IBIS revision or assign any electrical meaning to that revision.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IbisVersionTokenV1 {
    spelling: String,
    span: SourceSpanV1,
}

impl IbisVersionTokenV1 {
    pub fn spelling(&self) -> &str {
        &self.spelling
    }

    pub const fn span(&self) -> SourceSpanV1 {
        self.span
    }
}

/// Product-owned roles for a deliberately small semantic envelope. All other
/// structural keyword spelling remains explicitly represented as `Other`.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SectionKindV1 {
    IbisVersion,
    Component,
    Model,
    ModelType,
    Other(String),
}

/// One declared component name with its source ownership boundary.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ComponentDeclV1 {
    name: StructuralTokenV1,
    section_span: SourceSpanV1,
}

impl ComponentDeclV1 {
    pub fn name(&self) -> &StructuralTokenV1 {
        &self.name
    }

    pub const fn section_span(&self) -> SourceSpanV1 {
        self.section_span
    }
}

/// One declared model name with its source ownership boundary.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ModelDeclV1 {
    name: StructuralTokenV1,
    section_span: SourceSpanV1,
}

impl ModelDeclV1 {
    pub fn name(&self) -> &StructuralTokenV1 {
        &self.name
    }

    pub const fn section_span(&self) -> SourceSpanV1 {
        self.section_span
    }
}

/// A contiguous structural block owned by exactly one bracketed section.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticBlockV1 {
    kind: SectionKindV1,
    section_span: SourceSpanV1,
    owned_record_spans: Vec<SourceSpanV1>,
}

impl SemanticBlockV1 {
    pub fn kind(&self) -> &SectionKindV1 {
        &self.kind
    }

    pub const fn section_span(&self) -> SourceSpanV1 {
        self.section_span
    }

    pub fn owned_record_spans(&self) -> &[SourceSpanV1] {
        &self.owned_record_spans
    }
}

/// The product-owned typed semantic envelope. It deliberately contains no
/// table, package, PVT, clamp, AMI, or electrical evaluation semantics.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IbisSemanticDocumentV1 {
    version: IbisVersionTokenV1,
    components: Vec<ComponentDeclV1>,
    models: Vec<ModelDeclV1>,
    blocks: Vec<SemanticBlockV1>,
}

impl IbisSemanticDocumentV1 {
    pub fn version(&self) -> &IbisVersionTokenV1 {
        &self.version
    }

    pub fn components(&self) -> &[ComponentDeclV1] {
        &self.components
    }

    pub fn models(&self) -> &[ModelDeclV1] {
        &self.models
    }

    pub fn blocks(&self) -> &[SemanticBlockV1] {
        &self.blocks
    }
}

/// Stable diagnostics for the bounded semantic envelope. These are not
/// profile-specific required-keyword rules.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IbisSemanticDiagnosticCodeV1 {
    MissingDocumentVersion,
    DuplicateDocumentVersion,
    InvalidDocumentVersion,
    MissingSectionName,
    InvalidSectionName,
    DuplicateComponentName,
    DuplicateModelName,
    OrphanDataRecord,
    ProfileRulesUnavailable,
}

/// A fail-closed semantic diagnostic with a stable code and source location.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct IbisSemanticDiagnosticV1 {
    code: IbisSemanticDiagnosticCodeV1,
    span: SourceSpanV1,
}

impl IbisSemanticDiagnosticV1 {
    pub const fn code(self) -> IbisSemanticDiagnosticCodeV1 {
        self.code
    }

    pub const fn span(self) -> SourceSpanV1 {
        self.span
    }
}

impl fmt::Display for IbisSemanticDiagnosticV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "IBIS semantic envelope {:?} at line {}, column {}",
            self.code, self.span.line, self.span.column_start
        )
    }
}

impl Error for IbisSemanticDiagnosticV1 {}

/// Builds the typed semantic envelope from an already structural document.
/// It never reads an asset, selects an IBIS revision, or applies a profile.
pub fn build_semantic_envelope_v1(
    document: &IbisDocumentV1,
) -> Result<IbisSemanticDocumentV1, IbisSemanticDiagnosticV1> {
    let mut version = None;
    let mut components = Vec::new();
    let mut models = Vec::new();
    let mut blocks = Vec::new();
    let mut current_block = None;

    for record in document.records() {
        match record {
            StructuralRecordV1::Keyword {
                keyword,
                payload,
                span,
            } => {
                let kind = section_kind(keyword.spelling());
                match &kind {
                    SectionKindV1::IbisVersion => {
                        if version.is_some() {
                            return Err(semantic_diagnostic(
                                IbisSemanticDiagnosticCodeV1::DuplicateDocumentVersion,
                                *span,
                            ));
                        }
                        let token = exactly_one_name(payload, *span)?;
                        if !is_version_token(token.spelling()) {
                            return Err(semantic_diagnostic(
                                IbisSemanticDiagnosticCodeV1::InvalidDocumentVersion,
                                token.span(),
                            ));
                        }
                        version = Some(IbisVersionTokenV1 {
                            spelling: token.spelling.clone(),
                            span: token.span(),
                        });
                    }
                    SectionKindV1::Component => {
                        let name = exactly_one_name(payload, *span)?;
                        if !is_declaration_name(name.spelling()) {
                            return Err(semantic_diagnostic(
                                IbisSemanticDiagnosticCodeV1::InvalidSectionName,
                                name.span(),
                            ));
                        }
                        if components
                            .iter()
                            .any(|item: &ComponentDeclV1| item.name.spelling == name.spelling)
                        {
                            return Err(semantic_diagnostic(
                                IbisSemanticDiagnosticCodeV1::DuplicateComponentName,
                                name.span(),
                            ));
                        }
                        components.push(ComponentDeclV1 {
                            name: name.clone(),
                            section_span: *span,
                        });
                    }
                    SectionKindV1::Model => {
                        let name = exactly_one_name(payload, *span)?;
                        if !is_declaration_name(name.spelling()) {
                            return Err(semantic_diagnostic(
                                IbisSemanticDiagnosticCodeV1::InvalidSectionName,
                                name.span(),
                            ));
                        }
                        if models
                            .iter()
                            .any(|item: &ModelDeclV1| item.name.spelling == name.spelling)
                        {
                            return Err(semantic_diagnostic(
                                IbisSemanticDiagnosticCodeV1::DuplicateModelName,
                                name.span(),
                            ));
                        }
                        models.push(ModelDeclV1 {
                            name: name.clone(),
                            section_span: *span,
                        });
                    }
                    SectionKindV1::ModelType | SectionKindV1::Other(_) => {}
                }
                blocks.push(SemanticBlockV1 {
                    kind,
                    section_span: *span,
                    owned_record_spans: Vec::new(),
                });
                current_block = Some(blocks.len() - 1);
            }
            StructuralRecordV1::Data { span, .. } => {
                let Some(index) = current_block else {
                    return Err(semantic_diagnostic(
                        IbisSemanticDiagnosticCodeV1::OrphanDataRecord,
                        *span,
                    ));
                };
                blocks[index].owned_record_spans.push(*span);
            }
        }
    }

    let Some(version) = version else {
        return Err(semantic_diagnostic(
            IbisSemanticDiagnosticCodeV1::MissingDocumentVersion,
            SourceSpanV1::new(0, 0, 1, 1),
        ));
    };
    Ok(IbisSemanticDocumentV1 {
        version,
        components,
        models,
        blocks,
    })
}

/// Required-keyword profile validation is intentionally unavailable until an
/// owner selects a profile and independently freezes its semantic charter.
pub fn profile_semantic_rules_status_v1() -> IbisSemanticDiagnosticCodeV1 {
    IbisSemanticDiagnosticCodeV1::ProfileRulesUnavailable
}

/// Explicit hard bounds for one structural parse.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ParseLimitsV1 {
    max_input_bytes: NonZeroUsize,
    max_line_bytes: NonZeroUsize,
    max_physical_lines: NonZeroUsize,
    max_records: NonZeroUsize,
}

impl ParseLimitsV1 {
    pub fn try_new(
        max_input_bytes: usize,
        max_line_bytes: usize,
        max_physical_lines: usize,
        max_records: usize,
    ) -> Result<Self, LimitErrorV1> {
        Ok(Self {
            max_input_bytes: NonZeroUsize::new(max_input_bytes).ok_or(LimitErrorV1::Zero)?,
            max_line_bytes: NonZeroUsize::new(max_line_bytes).ok_or(LimitErrorV1::Zero)?,
            max_physical_lines: NonZeroUsize::new(max_physical_lines).ok_or(LimitErrorV1::Zero)?,
            max_records: NonZeroUsize::new(max_records).ok_or(LimitErrorV1::Zero)?,
        })
    }

    pub const fn max_input_bytes(self) -> NonZeroUsize {
        self.max_input_bytes
    }

    pub const fn max_line_bytes(self) -> NonZeroUsize {
        self.max_line_bytes
    }

    pub const fn max_physical_lines(self) -> NonZeroUsize {
        self.max_physical_lines
    }

    pub const fn max_records(self) -> NonZeroUsize {
        self.max_records
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LimitErrorV1 {
    Zero,
}

impl fmt::Display for LimitErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "structural parse limits must be nonzero")
    }
}

impl Error for LimitErrorV1 {}

/// Stable structural failure codes. Semantic diagnostics are deliberately out
/// of scope for this parser foundation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IbisDiagnosticCodeV1 {
    InputLimitExceeded,
    LineLimitExceeded,
    PhysicalLineLimitExceeded,
    RecordLimitExceeded,
    NulByte,
    NonAsciiByte,
    BareCarriageReturn,
    EmptyKeyword,
    UnclosedKeyword,
    InvalidKeywordSyntax,
    InvalidDataRecordSyntax,
}

/// A fail-closed parse diagnostic with a stable code and bounded location.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct IbisDiagnosticV1 {
    code: IbisDiagnosticCodeV1,
    span: SourceSpanV1,
}

impl IbisDiagnosticV1 {
    pub const fn code(self) -> IbisDiagnosticCodeV1 {
        self.code
    }

    pub const fn span(self) -> SourceSpanV1 {
        self.span
    }
}

impl fmt::Display for IbisDiagnosticV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "IBIS structural parse {:?} at line {}, column {}",
            self.code, self.span.line, self.span.column_start
        )
    }
}

impl Error for IbisDiagnosticV1 {}

/// Parses an ASCII structural document without interpreting any IBIS semantics.
pub fn parse_structural_v1(
    bytes: &[u8],
    limits: ParseLimitsV1,
) -> Result<IbisDocumentV1, IbisDiagnosticV1> {
    if bytes.len() > limits.max_input_bytes.get() {
        return Err(diagnostic(
            IbisDiagnosticCodeV1::InputLimitExceeded,
            0,
            0,
            1,
            1,
        ));
    }
    validate_bytes(bytes)?;

    let mut physical_lines = Vec::new();
    let mut records = Vec::new();
    let mut start = 0;
    let mut line_number = 1;

    while start < bytes.len() {
        if physical_lines.len() == limits.max_physical_lines.get() {
            return Err(diagnostic(
                IbisDiagnosticCodeV1::PhysicalLineLimitExceeded,
                start,
                start,
                line_number,
                1,
            ));
        }
        let (end, ending, next_start) = find_line_end(bytes, start, line_number)?;
        if end - start > limits.max_line_bytes.get() {
            return Err(diagnostic(
                IbisDiagnosticCodeV1::LineLimitExceeded,
                start,
                end,
                line_number,
                1,
            ));
        }
        let line_span = SourceSpanV1::new(start, end, line_number, 1);
        physical_lines.push(PhysicalLineV1 {
            span: line_span,
            ending,
        });
        parse_line(bytes, start, end, line_number, limits, &mut records)?;
        start = next_start;
        line_number += 1;
    }

    Ok(IbisDocumentV1 {
        physical_lines,
        records,
    })
}

fn section_kind(spelling: &str) -> SectionKindV1 {
    if spelling.eq_ignore_ascii_case("IBIS Ver") {
        SectionKindV1::IbisVersion
    } else if spelling.eq_ignore_ascii_case("Component") {
        SectionKindV1::Component
    } else if spelling.eq_ignore_ascii_case("Model") {
        SectionKindV1::Model
    } else if spelling.eq_ignore_ascii_case("Model_type") {
        SectionKindV1::ModelType
    } else {
        SectionKindV1::Other(spelling.to_owned())
    }
}

fn exactly_one_name(
    payload: &[StructuralTokenV1],
    span: SourceSpanV1,
) -> Result<&StructuralTokenV1, IbisSemanticDiagnosticV1> {
    if payload.len() != 1 {
        return Err(semantic_diagnostic(
            IbisSemanticDiagnosticCodeV1::MissingSectionName,
            span,
        ));
    }
    Ok(&payload[0])
}

fn is_version_token(value: &str) -> bool {
    let mut segments = value.split('.');
    let mut count = 0;
    for segment in &mut segments {
        if segment.is_empty() || !segment.bytes().all(|byte| byte.is_ascii_digit()) {
            return false;
        }
        count += 1;
    }
    count >= 2
}

fn is_declaration_name(value: &str) -> bool {
    !value.is_empty()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
}

const fn semantic_diagnostic(
    code: IbisSemanticDiagnosticCodeV1,
    span: SourceSpanV1,
) -> IbisSemanticDiagnosticV1 {
    IbisSemanticDiagnosticV1 { code, span }
}

fn validate_bytes(bytes: &[u8]) -> Result<(), IbisDiagnosticV1> {
    for (index, byte) in bytes.iter().copied().enumerate() {
        if byte == 0 {
            return Err(diagnostic(
                IbisDiagnosticCodeV1::NulByte,
                index,
                index + 1,
                1,
                index + 1,
            ));
        }
        if byte > 0x7f {
            return Err(diagnostic(
                IbisDiagnosticCodeV1::NonAsciiByte,
                index,
                index + 1,
                1,
                index + 1,
            ));
        }
    }
    Ok(())
}

fn find_line_end(
    bytes: &[u8],
    start: usize,
    line: usize,
) -> Result<(usize, LineEndingV1, usize), IbisDiagnosticV1> {
    let mut index = start;
    while index < bytes.len() {
        match bytes[index] {
            b'\n' => return Ok((index, LineEndingV1::Lf, index + 1)),
            b'\r' if bytes.get(index + 1) == Some(&b'\n') => {
                return Ok((index, LineEndingV1::Crlf, index + 2));
            }
            b'\r' => {
                return Err(diagnostic(
                    IbisDiagnosticCodeV1::BareCarriageReturn,
                    index,
                    index + 1,
                    line,
                    index - start + 1,
                ));
            }
            _ => index += 1,
        }
    }
    Ok((bytes.len(), LineEndingV1::EndOfInput, bytes.len()))
}

fn parse_line(
    bytes: &[u8],
    start: usize,
    end: usize,
    line: usize,
    limits: ParseLimitsV1,
    records: &mut Vec<StructuralRecordV1>,
) -> Result<(), IbisDiagnosticV1> {
    let comment_end = bytes[start..end]
        .iter()
        .position(|byte| *byte == b'|')
        .map_or(end, |offset| start + offset);
    let Some((content_start, content_end)) = trim_ascii(bytes, start, comment_end) else {
        return Ok(());
    };
    if records.len() == limits.max_records.get() {
        return Err(diagnostic(
            IbisDiagnosticCodeV1::RecordLimitExceeded,
            content_start,
            content_end,
            line,
            content_start - start + 1,
        ));
    }
    let span = SourceSpanV1::new(content_start, content_end, line, content_start - start + 1);
    if bytes[content_start] == b'[' {
        records.push(parse_keyword(bytes, content_start, content_end, span)?);
    } else {
        if bytes[content_start..content_end]
            .iter()
            .any(|byte| matches!(*byte, b'[' | b']'))
        {
            return Err(diagnostic(
                IbisDiagnosticCodeV1::InvalidDataRecordSyntax,
                content_start,
                content_end,
                line,
                span.column_start,
            ));
        }
        records.push(StructuralRecordV1::Data {
            tokens: tokens(bytes, content_start, content_end, line, start),
            span,
        });
    }
    Ok(())
}

fn parse_keyword(
    bytes: &[u8],
    start: usize,
    end: usize,
    span: SourceSpanV1,
) -> Result<StructuralRecordV1, IbisDiagnosticV1> {
    let Some(close_offset) = bytes[start + 1..end].iter().position(|byte| *byte == b']') else {
        return Err(diagnostic(
            IbisDiagnosticCodeV1::UnclosedKeyword,
            start,
            end,
            span.line,
            span.column_start,
        ));
    };
    let close = start + 1 + close_offset;
    let Some((keyword_start, keyword_end)) = trim_ascii(bytes, start + 1, close) else {
        return Err(diagnostic(
            IbisDiagnosticCodeV1::EmptyKeyword,
            start,
            close + 1,
            span.line,
            span.column_start,
        ));
    };
    if bytes[keyword_start..keyword_end]
        .iter()
        .any(|byte| matches!(*byte, b'[' | b']') || !is_keyword_byte(*byte))
    {
        return Err(diagnostic(
            IbisDiagnosticCodeV1::InvalidKeywordSyntax,
            keyword_start,
            keyword_end,
            span.line,
            keyword_start - (span.byte_start - (span.column_start - 1)) + 1,
        ));
    }
    let payload_start = close + 1;
    if bytes[payload_start..end]
        .iter()
        .any(|byte| matches!(*byte, b'[' | b']'))
    {
        return Err(diagnostic(
            IbisDiagnosticCodeV1::InvalidKeywordSyntax,
            payload_start,
            end,
            span.line,
            payload_start - (span.byte_start - (span.column_start - 1)) + 1,
        ));
    }
    let line_start = span.byte_start - (span.column_start - 1);
    Ok(StructuralRecordV1::Keyword {
        keyword: StructuralTokenV1 {
            spelling: ascii_string(bytes, keyword_start, keyword_end),
            span: SourceSpanV1::new(
                keyword_start,
                keyword_end,
                span.line,
                keyword_start - line_start + 1,
            ),
        },
        payload: tokens(bytes, payload_start, end, span.line, line_start),
        span,
    })
}

fn trim_ascii(bytes: &[u8], start: usize, end: usize) -> Option<(usize, usize)> {
    let mut left = start;
    while left < end && is_ascii_space(bytes[left]) {
        left += 1;
    }
    let mut right = end;
    while right > left && is_ascii_space(bytes[right - 1]) {
        right -= 1;
    }
    (left < right).then_some((left, right))
}

fn tokens(
    bytes: &[u8],
    start: usize,
    end: usize,
    line: usize,
    line_start: usize,
) -> Vec<StructuralTokenV1> {
    let mut result = Vec::new();
    let mut index = start;
    while index < end {
        while index < end && is_ascii_space(bytes[index]) {
            index += 1;
        }
        let token_start = index;
        while index < end && !is_ascii_space(bytes[index]) {
            index += 1;
        }
        if token_start < index {
            result.push(StructuralTokenV1 {
                spelling: ascii_string(bytes, token_start, index),
                span: SourceSpanV1::new(token_start, index, line, token_start - line_start + 1),
            });
        }
    }
    result
}

fn ascii_string(bytes: &[u8], start: usize, end: usize) -> String {
    // Byte validation happens before any call that reaches this conversion.
    String::from_utf8(bytes[start..end].to_vec()).expect("validated ASCII")
}

const fn is_ascii_space(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t')
}

const fn is_keyword_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || matches!(byte, b' ' | b'_' | b'-')
}

const fn diagnostic(
    code: IbisDiagnosticCodeV1,
    byte_start: usize,
    byte_end: usize,
    line: usize,
    column_start: usize,
) -> IbisDiagnosticV1 {
    IbisDiagnosticV1 {
        code,
        span: SourceSpanV1::new(byte_start, byte_end, line, column_start),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(256, 64, 16, 16).expect("limits")
    }

    #[test]
    fn retains_structural_spelling_order_spans_and_line_endings() {
        let source = b"| comment\r\n[IBIS Ver] 7.1 | ignored\n[Future-Key] alpha beta\n1.0 2.0\n";
        let document = parse_structural_v1(source, limits()).expect("structural parse");
        assert_eq!(document.physical_lines().len(), 4);
        assert_eq!(document.physical_lines()[0].ending(), LineEndingV1::Crlf);
        assert_eq!(document.physical_lines()[1].ending(), LineEndingV1::Lf);
        assert_eq!(document.records().len(), 3);
        let StructuralRecordV1::Keyword {
            keyword,
            payload,
            span,
        } = &document.records()[0]
        else {
            panic!("keyword");
        };
        assert_eq!(keyword.spelling(), "IBIS Ver");
        assert_eq!(
            payload
                .iter()
                .map(StructuralTokenV1::spelling)
                .collect::<Vec<_>>(),
            ["7.1"]
        );
        assert_eq!(span.line(), 2);
        let StructuralRecordV1::Data { tokens, span } = &document.records()[2] else {
            panic!("data");
        };
        assert_eq!(
            tokens
                .iter()
                .map(StructuralTokenV1::spelling)
                .collect::<Vec<_>>(),
            ["1.0", "2.0"]
        );
        assert_eq!(span.line(), 4);
    }

    #[test]
    fn unknown_keywords_are_structural_and_have_no_semantic_gate() {
        let document =
            parse_structural_v1(b"[Anything-New] 1\n", limits()).expect("unknown keyword");
        let StructuralRecordV1::Keyword { keyword, .. } = &document.records()[0] else {
            panic!("keyword");
        };
        assert_eq!(keyword.spelling(), "Anything-New");
    }

    #[test]
    fn rejects_encoding_nul_line_and_record_limit_failures() {
        let cases = [
            (b"[X]\0\n".as_slice(), IbisDiagnosticCodeV1::NulByte),
            (b"[X]\x80\n".as_slice(), IbisDiagnosticCodeV1::NonAsciiByte),
            (
                b"[X]\r".as_slice(),
                IbisDiagnosticCodeV1::BareCarriageReturn,
            ),
            (b"[]\n".as_slice(), IbisDiagnosticCodeV1::EmptyKeyword),
            (b"[X\n".as_slice(), IbisDiagnosticCodeV1::UnclosedKeyword),
            (
                b"abc ]\n".as_slice(),
                IbisDiagnosticCodeV1::InvalidDataRecordSyntax,
            ),
        ];
        for (source, expected) in cases {
            assert_eq!(
                parse_structural_v1(source, limits())
                    .expect_err("rejected")
                    .code(),
                expected
            );
        }
        let limited = ParseLimitsV1::try_new(8, 8, 1, 1).expect("limits");
        assert_eq!(
            parse_structural_v1(b"[A]\n[B]\n", limited)
                .expect_err("line limit")
                .code(),
            IbisDiagnosticCodeV1::PhysicalLineLimitExceeded
        );
    }

    #[test]
    fn rejects_limits_without_returning_partial_document() {
        let line_limited = ParseLimitsV1::try_new(64, 3, 8, 8).expect("limits");
        assert_eq!(
            parse_structural_v1(b"[A] 1\n", line_limited)
                .expect_err("line limit")
                .code(),
            IbisDiagnosticCodeV1::LineLimitExceeded
        );
        let record_limited = ParseLimitsV1::try_new(64, 64, 8, 1).expect("limits");
        assert_eq!(
            parse_structural_v1(b"[A]\n[B]\n", record_limited)
                .expect_err("record limit")
                .code(),
            IbisDiagnosticCodeV1::RecordLimitExceeded
        );
    }

    #[test]
    fn rejects_zero_limits() {
        assert_eq!(ParseLimitsV1::try_new(0, 1, 1, 1), Err(LimitErrorV1::Zero));
    }

    #[test]
    fn builds_a_typed_envelope_with_explicit_block_ownership() {
        let source = b"[IBIS Ver] 7.1\n[Component] board_0\nrow data\n[Model] rx_0\n";
        let structural = parse_structural_v1(source, limits()).expect("structural parse");
        let semantic = build_semantic_envelope_v1(&structural).expect("semantic envelope");
        assert_eq!(semantic.version().spelling(), "7.1");
        assert_eq!(semantic.components()[0].name().spelling(), "board_0");
        assert_eq!(semantic.models()[0].name().spelling(), "rx_0");
        assert_eq!(semantic.blocks().len(), 3);
        assert_eq!(semantic.blocks()[1].owned_record_spans().len(), 1);
        assert!(matches!(semantic.blocks()[2].kind(), SectionKindV1::Model));
    }

    #[test]
    fn rejects_invalid_or_ambiguous_envelope_declarations() {
        let cases = [
            (
                b"[Component] board\n".as_slice(),
                IbisSemanticDiagnosticCodeV1::MissingDocumentVersion,
            ),
            (
                b"[IBIS Ver] v7.1\n".as_slice(),
                IbisSemanticDiagnosticCodeV1::InvalidDocumentVersion,
            ),
            (
                b"[IBIS Ver] 7.1\n[IBIS Ver] 7.2\n".as_slice(),
                IbisSemanticDiagnosticCodeV1::DuplicateDocumentVersion,
            ),
            (
                b"[IBIS Ver] 7.1\n[Model]\n".as_slice(),
                IbisSemanticDiagnosticCodeV1::MissingSectionName,
            ),
            (
                b"[IBIS Ver] 7.1\n[Component] same\n[Component] same\n".as_slice(),
                IbisSemanticDiagnosticCodeV1::DuplicateComponentName,
            ),
            (
                b"orphan data\n[IBIS Ver] 7.1\n".as_slice(),
                IbisSemanticDiagnosticCodeV1::OrphanDataRecord,
            ),
        ];
        for (source, expected) in cases {
            let structural = parse_structural_v1(source, limits()).expect("structural parse");
            assert_eq!(
                build_semantic_envelope_v1(&structural)
                    .expect_err("semantic rejection")
                    .code(),
                expected
            );
        }
    }

    #[test]
    fn preserves_unknown_sections_and_keeps_profile_rules_unavailable() {
        let source = b"[IBIS Ver] 7.1\n[Future Section] alpha\nrow\n";
        let structural = parse_structural_v1(source, limits()).expect("structural parse");
        let semantic = build_semantic_envelope_v1(&structural).expect("semantic envelope");
        assert!(matches!(
            semantic.blocks()[1].kind(),
            SectionKindV1::Other(spelling) if spelling == "Future Section"
        ));
        assert_eq!(
            profile_semantic_rules_status_v1(),
            IbisSemanticDiagnosticCodeV1::ProfileRulesUnavailable
        );
    }
}
