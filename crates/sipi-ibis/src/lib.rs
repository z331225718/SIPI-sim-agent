#![forbid(unsafe_code)]

//! Clean-room structural parsing for bounded IBIS text input.
//!
//! This crate recognizes physical lines, comments, bracketed keyword records,
//! and whitespace-delimited data records. It deliberately assigns no IBIS
//! electrical, package, PVT, AMI, or table semantics.

use std::{error::Error, fmt, num::NonZeroUsize};

use sha2::{Digest, Sha256};
use sipi_types::{Amps, FiniteF64, Volts};

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
    records: Vec<StructuralRecordV1>,
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

    fn records(&self) -> &[StructuralRecordV1] {
        &self.records
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
        records: document.records().to_vec(),
    })
}

/// Required-keyword profile validation is intentionally unavailable until an
/// owner selects a profile and independently freezes its semantic charter.
pub fn profile_semantic_rules_status_v1() -> IbisSemanticDiagnosticCodeV1 {
    IbisSemanticDiagnosticCodeV1::ProfileRulesUnavailable
}

/// Pure in-memory structural inspection service for one product-owned text.
pub struct IbisInspectServiceV1;

impl IbisInspectServiceV1 {
    /// Parses and builds a typed envelope without evaluating electrical behavior.
    pub fn inspect(
        text: &str,
        limits: ParseLimitsV1,
    ) -> Result<IbisInspectReportV1, IbisInspectErrorV1> {
        let bytes = text.as_bytes();
        let document =
            parse_structural_v1(bytes, limits).map_err(IbisInspectErrorV1::Structural)?;
        let envelope =
            build_semantic_envelope_v1(&document).map_err(IbisInspectErrorV1::Semantic)?;
        Ok(IbisInspectReportV1 {
            input_byte_length: bytes.len(),
            input_sha256: hex_sha256(bytes),
            declared_version: envelope.version().spelling().to_owned(),
            component_count: envelope.components().len(),
            model_count: envelope.models().len(),
            block_count: envelope.blocks().len(),
        })
    }
}

/// A structural/semantic result that deliberately has no electrical claim.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IbisInspectReportV1 {
    input_byte_length: usize,
    input_sha256: String,
    declared_version: String,
    component_count: usize,
    model_count: usize,
    block_count: usize,
}

impl IbisInspectReportV1 {
    pub const fn input_byte_length(&self) -> usize {
        self.input_byte_length
    }

    pub fn input_sha256(&self) -> &str {
        &self.input_sha256
    }

    pub fn declared_version(&self) -> &str {
        &self.declared_version
    }

    pub const fn component_count(&self) -> usize {
        self.component_count
    }

    pub const fn model_count(&self) -> usize {
        self.model_count
    }

    pub const fn block_count(&self) -> usize {
        self.block_count
    }

    pub const fn electrical_behavior_status(&self) -> &'static str {
        "not_evaluated"
    }

    pub const fn external_profile_acceptance_status(&self) -> &'static str {
        "not_evaluated"
    }

    pub const fn capability_matrix_id(&self) -> &'static str {
        "sipi.p4a-ibis-conformance-matrix.v1"
    }
}

/// Stable structural or semantic rejection from the inspect service.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IbisInspectErrorV1 {
    Structural(IbisDiagnosticV1),
    Semantic(IbisSemanticDiagnosticV1),
}

impl fmt::Display for IbisInspectErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Structural(error) => error.fmt(formatter),
            Self::Semantic(error) => error.fmt(formatter),
        }
    }
}

impl Error for IbisInspectErrorV1 {}

/// Pure in-memory service for the selected Input/TYP static DC clamp scope.
/// It deliberately consumes caller-provided text only; no external asset,
/// file, URL, package, PVT fallback, transient, or AMI behavior is involved.
pub struct IbisDcEvaluateServiceV1;

impl IbisDcEvaluateServiceV1 {
    pub fn evaluate(
        text: &str,
        profile: &SelectedDcClampProfileV1,
        probe: DcClampProbeV1,
        limits: ParseLimitsV1,
    ) -> Result<IbisDcEvaluateReportV1, IbisDcEvaluateErrorV1> {
        let bytes = text.as_bytes();
        let document =
            parse_structural_v1(bytes, limits).map_err(IbisDcEvaluateErrorV1::Structural)?;
        let envelope =
            build_semantic_envelope_v1(&document).map_err(IbisDcEvaluateErrorV1::Semantic)?;
        let decoded = decode_selected_dc_clamps_v1(&envelope, profile)
            .map_err(IbisDcEvaluateErrorV1::Profile)?;
        let response =
            evaluate_dc_clamps_v1(decoded.model(), probe).map_err(IbisDcEvaluateErrorV1::Dc)?;
        Ok(IbisDcEvaluateReportV1 {
            input_byte_length: bytes.len(),
            input_sha256: hex_sha256(bytes),
            ibis_version: profile.ibis_version().to_owned(),
            model_selector: profile.model_selector().to_owned(),
            gnd_current: response.gnd_current(),
            power_current: response.power_current(),
            total_shunt_current: response.total_shunt_current(),
        })
    }
}

/// Bounded projection of a successful static DC evaluation.
#[derive(Clone, Debug, PartialEq)]
pub struct IbisDcEvaluateReportV1 {
    input_byte_length: usize,
    input_sha256: String,
    ibis_version: String,
    model_selector: String,
    gnd_current: Amps,
    power_current: Amps,
    total_shunt_current: Amps,
}

impl IbisDcEvaluateReportV1 {
    pub const fn input_byte_length(&self) -> usize {
        self.input_byte_length
    }

    pub fn input_sha256(&self) -> &str {
        &self.input_sha256
    }

    pub fn ibis_version(&self) -> &str {
        &self.ibis_version
    }

    pub fn model_selector(&self) -> &str {
        &self.model_selector
    }

    pub const fn gnd_current(&self) -> Amps {
        self.gnd_current
    }

    pub const fn power_current(&self) -> Amps {
        self.power_current
    }

    pub const fn total_shunt_current(&self) -> Amps {
        self.total_shunt_current
    }

    pub const fn c_comp_current_amps(&self) -> f64 {
        // This route is static DC only. The declaration is validated by the
        // selected decoder but its current contribution is exactly zero.
        0.0
    }
}

/// Stable rejection families for the static DC service.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IbisDcEvaluateErrorV1 {
    Structural(IbisDiagnosticV1),
    Semantic(IbisSemanticDiagnosticV1),
    Profile(IbisProfileDiagnosticV1),
    Dc(DcClampErrorV1),
}

impl fmt::Display for IbisDcEvaluateErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Structural(error) => error.fmt(formatter),
            Self::Semantic(error) => error.fmt(formatter),
            Self::Profile(error) => error.fmt(formatter),
            Self::Dc(error) => error.fmt(formatter),
        }
    }
}

impl Error for IbisDcEvaluateErrorV1 {}

fn hex_sha256(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let digest = Sha256::digest(bytes);
    let mut text = String::with_capacity(digest.len() * 2);
    for byte in digest {
        text.push(HEX[usize::from(byte >> 4)] as char);
        text.push(HEX[usize::from(byte & 0x0f)] as char);
    }
    text
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
        if !data_brackets_are_balanced(&bytes[content_start..content_end]) {
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

fn data_brackets_are_balanced(bytes: &[u8]) -> bool {
    let mut depth = 0usize;
    for byte in bytes {
        match *byte {
            b'[' => depth += 1,
            b']' if depth == 0 => return false,
            b']' => depth -= 1,
            _ => {}
        }
    }
    depth == 0
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

/// One finite, signed DC current-versus-voltage knot. The current sign is
/// caller-defined and is never changed by this primitive.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DcIvKnotV1 {
    voltage: Volts,
    current: Amps,
}

impl DcIvKnotV1 {
    pub const fn new(voltage: Volts, current: Amps) -> Self {
        Self { voltage, current }
    }

    pub const fn voltage(self) -> Volts {
        self.voltage
    }

    pub const fn current(self) -> Amps {
        self.current
    }
}

/// One bounded, strictly ordered piecewise-linear DC I-V table.
#[derive(Clone, Debug, PartialEq)]
pub struct DcIvTableV1 {
    knots: Vec<DcIvKnotV1>,
}

impl DcIvTableV1 {
    pub fn try_new(knots: Vec<DcIvKnotV1>) -> Result<Self, DcClampErrorV1> {
        if knots.len() < 2 {
            return Err(DcClampErrorV1::InsufficientKnots);
        }
        for pair in knots.windows(2) {
            if pair[0].voltage().get() >= pair[1].voltage().get() {
                return Err(DcClampErrorV1::VoltageNotStrictlyIncreasing);
            }
        }
        Ok(Self { knots })
    }

    pub fn knots(&self) -> &[DcIvKnotV1] {
        &self.knots
    }

    fn evaluate(&self, voltage: Volts, branch: ClampBranchV1) -> Result<Amps, DcClampErrorV1> {
        let requested = voltage.get();
        let first = self.knots[0].voltage().get();
        let last = self.knots[self.knots.len() - 1].voltage().get();
        if requested < first || requested > last {
            return Err(DcClampErrorV1::OutOfDomain { branch });
        }
        for pair in self.knots.windows(2) {
            let lower = pair[0];
            let upper = pair[1];
            if requested == lower.voltage().get() {
                return Ok(lower.current());
            }
            if requested <= upper.voltage().get() {
                let distance = upper.voltage().get() - lower.voltage().get();
                let ratio = (requested - lower.voltage().get()) / distance;
                let value =
                    lower.current().get() + ratio * (upper.current().get() - lower.current().get());
                return Amps::try_new(value).map_err(|_| DcClampErrorV1::NonFiniteEvaluation);
            }
        }
        Ok(self.knots[self.knots.len() - 1].current())
    }
}

/// Product-owned typed data for the selected profile's two DC clamp tables.
#[derive(Clone, Debug, PartialEq)]
pub struct InputClampDcModelV1 {
    gnd_clamp: DcIvTableV1,
    power_clamp: DcIvTableV1,
}

impl InputClampDcModelV1 {
    pub const fn new(gnd_clamp: DcIvTableV1, power_clamp: DcIvTableV1) -> Self {
        Self {
            gnd_clamp,
            power_clamp,
        }
    }

    pub const fn gnd_clamp(&self) -> &DcIvTableV1 {
        &self.gnd_clamp
    }

    pub const fn power_clamp(&self) -> &DcIvTableV1 {
        &self.power_clamp
    }
}

/// Explicit per-table voltages for a DC clamp probe. This core never infers a
/// supply, reference, polarity, or power-clamp offset from a model.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DcClampProbeV1 {
    gnd_drive: Volts,
    power_drive: Volts,
}

impl DcClampProbeV1 {
    pub const fn new(gnd_drive: Volts, power_drive: Volts) -> Self {
        Self {
            gnd_drive,
            power_drive,
        }
    }

    pub const fn gnd_drive(self) -> Volts {
        self.gnd_drive
    }

    pub const fn power_drive(self) -> Volts {
        self.power_drive
    }
}

/// One named clamp branch for stable out-of-domain diagnostics.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ClampBranchV1 {
    Gnd,
    Power,
}

/// Fail-closed DC clamp construction and evaluation errors.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DcClampErrorV1 {
    InsufficientKnots,
    VoltageNotStrictlyIncreasing,
    OutOfDomain { branch: ClampBranchV1 },
    NonFiniteEvaluation,
}

impl fmt::Display for DcClampErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InsufficientKnots => write!(formatter, "a DC I-V table needs at least two knots"),
            Self::VoltageNotStrictlyIncreasing => {
                write!(
                    formatter,
                    "DC I-V table voltages must be strictly increasing"
                )
            }
            Self::OutOfDomain { branch } => {
                write!(formatter, "{branch:?} clamp probe is out of domain")
            }
            Self::NonFiniteEvaluation => write!(formatter, "DC clamp evaluation is not finite"),
        }
    }
}

impl Error for DcClampErrorV1 {}

/// A complete DC-only clamp response. Capacitive current is always exactly
/// zero in this primitive; transient C_comp behavior is deliberately absent.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DcClampResponseV1 {
    gnd_current: Amps,
    power_current: Amps,
    capacitive_current: Amps,
    total_shunt_current: Amps,
}

impl DcClampResponseV1 {
    pub const fn gnd_current(self) -> Amps {
        self.gnd_current
    }

    pub const fn power_current(self) -> Amps {
        self.power_current
    }

    pub const fn capacitive_current(self) -> Amps {
        self.capacitive_current
    }

    pub const fn total_shunt_current(self) -> Amps {
        self.total_shunt_current
    }
}

/// Evaluates two caller-supplied DC I-V clamp tables. No table decoding,
/// package model, PVT selection, sign conversion, or extrapolation occurs.
pub fn evaluate_dc_clamps_v1(
    model: &InputClampDcModelV1,
    probe: DcClampProbeV1,
) -> Result<DcClampResponseV1, DcClampErrorV1> {
    let gnd_current = model
        .gnd_clamp
        .evaluate(probe.gnd_drive(), ClampBranchV1::Gnd)?;
    let power_current = model
        .power_clamp
        .evaluate(probe.power_drive(), ClampBranchV1::Power)?;
    let capacitive_current = Amps::try_new(0.0).map_err(|_| DcClampErrorV1::NonFiniteEvaluation)?;
    let total_shunt_current = Amps::try_new(gnd_current.get() + power_current.get())
        .map_err(|_| DcClampErrorV1::NonFiniteEvaluation)?;
    Ok(DcClampResponseV1 {
        gnd_current,
        power_current,
        capacitive_current,
        total_shunt_current,
    })
}

/// The only PVT corner admitted by the selected input-static profile.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DcClampCornerV1 {
    Typical,
}

/// Caller-selected lexical identity for a profile-scoped input clamp decode.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SelectedDcClampProfileV1 {
    ibis_version: String,
    model_selector: String,
    corner: DcClampCornerV1,
}

impl SelectedDcClampProfileV1 {
    pub fn try_new(
        ibis_version: &str,
        model_selector: &str,
        corner: DcClampCornerV1,
    ) -> Result<Self, IbisProfileDiagnosticV1> {
        if !is_version_token(ibis_version) {
            return Err(IbisProfileDiagnosticV1::InvalidExpectedVersion);
        }
        if !is_declaration_name(model_selector) {
            return Err(IbisProfileDiagnosticV1::InvalidModelSelector);
        }
        Ok(Self {
            ibis_version: ibis_version.to_owned(),
            model_selector: model_selector.to_owned(),
            corner,
        })
    }

    pub fn ibis_version(&self) -> &str {
        &self.ibis_version
    }

    pub fn model_selector(&self) -> &str {
        &self.model_selector
    }

    pub const fn corner(&self) -> DcClampCornerV1 {
        self.corner
    }
}

/// A finite, non-negative `C_comp` declaration expressed in farads.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CCompDeclarationV1 {
    capacitance_farads: FiniteF64,
}

impl CCompDeclarationV1 {
    pub fn try_new(capacitance_farads: f64) -> Result<Self, InputClampConstitutiveErrorV1> {
        if !capacitance_farads.is_finite() || capacitance_farads < 0.0 {
            return Err(InputClampConstitutiveErrorV1::InvalidCComp);
        }
        Ok(Self {
            capacitance_farads: FiniteF64::try_new(capacitance_farads, "C_comp capacitance")
                .map_err(|_| InputClampConstitutiveErrorV1::InvalidCComp)?,
        })
    }

    pub const fn capacitance_farads(self) -> FiniteF64 {
        self.capacitance_farads
    }
}

/// Memoryless I-V clamps plus an ideal continuous `C_comp` relation.
///
/// The two clamp drives remain independently caller-supplied. This type does
/// not infer a supply, a signal voltage, or a derivative from a waveform.
#[derive(Clone, Debug, PartialEq)]
pub struct InputClampConstitutiveV1 {
    dc_model: InputClampDcModelV1,
    c_comp: CCompDeclarationV1,
}

impl InputClampConstitutiveV1 {
    pub fn try_new(
        dc_model: InputClampDcModelV1,
        c_comp: CCompDeclarationV1,
    ) -> Result<Self, InputClampConstitutiveErrorV1> {
        let capacitance = c_comp.capacitance_farads().get();
        if !capacitance.is_finite() || capacitance < 0.0 {
            return Err(InputClampConstitutiveErrorV1::InvalidCComp);
        }
        Ok(Self { dc_model, c_comp })
    }

    pub const fn dc_model(&self) -> &InputClampDcModelV1 {
        &self.dc_model
    }

    pub const fn c_comp(&self) -> CCompDeclarationV1 {
        self.c_comp
    }
}

/// Explicit quasi-static clamp drives and the SIG-to-REF voltage derivative.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct QuasiStaticClampStateV1 {
    dc_probe: DcClampProbeV1,
    sig_to_ref_slope_v_per_s: FiniteF64,
}

impl QuasiStaticClampStateV1 {
    pub fn try_new(
        gnd_clamp_drive: Volts,
        power_clamp_drive: Volts,
        sig_to_ref_slope_v_per_s: f64,
    ) -> Result<Self, InputClampConstitutiveErrorV1> {
        Ok(Self {
            dc_probe: DcClampProbeV1::new(gnd_clamp_drive, power_clamp_drive),
            sig_to_ref_slope_v_per_s: FiniteF64::try_new(
                sig_to_ref_slope_v_per_s,
                "SIG-to-REF voltage slope in volts per second",
            )
            .map_err(|_| InputClampConstitutiveErrorV1::InvalidSlope)?,
        })
    }

    pub const fn dc_probe(self) -> DcClampProbeV1 {
        self.dc_probe
    }

    pub fn sig_to_ref_slope_v_per_s(self) -> f64 {
        self.sig_to_ref_slope_v_per_s.get()
    }
}

/// The signed quasi-static clamp response, with all currents positive into
/// the selected shunt relation.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct QuasiStaticClampResponseV1 {
    gnd_current: Amps,
    power_current: Amps,
    c_comp_current: Amps,
    total_shunt_current: Amps,
}

impl QuasiStaticClampResponseV1 {
    pub const fn gnd_current(self) -> Amps {
        self.gnd_current
    }

    pub const fn power_current(self) -> Amps {
        self.power_current
    }

    pub const fn c_comp_current(self) -> Amps {
        self.c_comp_current
    }

    pub const fn total_shunt_current(self) -> Amps {
        self.total_shunt_current
    }
}

/// Fail-closed errors for the quasi-static clamp-plus-capacitance relation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum InputClampConstitutiveErrorV1 {
    Dc(DcClampErrorV1),
    InvalidCComp,
    InvalidSlope,
    NonFiniteCapacitiveCurrent,
    NonFiniteTotalCurrent,
}

impl fmt::Display for InputClampConstitutiveErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Dc(error) => error.fmt(formatter),
            Self::InvalidCComp => write!(formatter, "C_comp must be finite and non-negative"),
            Self::InvalidSlope => write!(formatter, "SIG-to-REF voltage slope must be finite"),
            Self::NonFiniteCapacitiveCurrent => write!(formatter, "C_comp current is not finite"),
            Self::NonFiniteTotalCurrent => write!(formatter, "total shunt current is not finite"),
        }
    }
}

impl Error for InputClampConstitutiveErrorV1 {}

/// Evaluates the memoryless I-V clamps and ideal continuous `C_comp` current.
///
/// This does not integrate, retain state, accept a time step, or infer a
/// derivative. The DC table evaluation is performed first and its out-of-
/// domain error is returned before any capacitive result is published.
pub fn evaluate_quasi_static_clamps_v1(
    model: &InputClampConstitutiveV1,
    state: QuasiStaticClampStateV1,
) -> Result<QuasiStaticClampResponseV1, InputClampConstitutiveErrorV1> {
    let dc = evaluate_dc_clamps_v1(model.dc_model(), state.dc_probe())
        .map_err(InputClampConstitutiveErrorV1::Dc)?;
    let c_comp_current_value =
        model.c_comp().capacitance_farads().get() * state.sig_to_ref_slope_v_per_s();
    let c_comp_current = Amps::try_new(c_comp_current_value)
        .map_err(|_| InputClampConstitutiveErrorV1::NonFiniteCapacitiveCurrent)?;
    let total_shunt_current =
        Amps::try_new(dc.gnd_current().get() + dc.power_current().get() + c_comp_current.get())
            .map_err(|_| InputClampConstitutiveErrorV1::NonFiniteTotalCurrent)?;
    Ok(QuasiStaticClampResponseV1 {
        gnd_current: dc.gnd_current(),
        power_current: dc.power_current(),
        c_comp_current,
        total_shunt_current,
    })
}

/// The strict decoder output for the selected input-static profile.
#[derive(Clone, Debug, PartialEq)]
pub struct DecodedDcClampProfileV1 {
    model: InputClampDcModelV1,
    c_comp: CCompDeclarationV1,
}

impl DecodedDcClampProfileV1 {
    pub const fn model(&self) -> &InputClampDcModelV1 {
        &self.model
    }

    pub const fn c_comp(&self) -> CCompDeclarationV1 {
        self.c_comp
    }
}

/// Stable rejection codes for the selected profile decoder.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IbisProfileDiagnosticV1 {
    InvalidExpectedVersion,
    InvalidModelSelector,
    VersionMismatch,
    SelectedModelMissing,
    ModelTypeMissing,
    ModelTypeNotInput,
    CCompMissing,
    CCompDuplicate,
    CCompInvalid,
    CCompNegative,
    GndClampMissing,
    GndClampDuplicate,
    PowerClampMissing,
    PowerClampDuplicate,
    ClampRowInvalid,
    ClampTableInvalid,
    AlgorithmicModelPresent,
}

impl fmt::Display for IbisProfileDiagnosticV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected IBIS DC clamp profile rejection: {self:?}"
        )
    }
}

impl Error for IbisProfileDiagnosticV1 {}

/// Decodes the deliberately narrow selected input-clamp profile from an
/// in-memory semantic document. It performs no file access, external identity
/// lookup, package/pin/PVT fallback, V-T/ramp handling, or AMI composition.
pub fn decode_selected_dc_clamps_v1(
    document: &IbisSemanticDocumentV1,
    profile: &SelectedDcClampProfileV1,
) -> Result<DecodedDcClampProfileV1, IbisProfileDiagnosticV1> {
    if document.version().spelling() != profile.ibis_version() {
        return Err(IbisProfileDiagnosticV1::VersionMismatch);
    }
    let records = document.records();
    let model_index = records
        .iter()
        .position(|record| model_name(record).is_some_and(|name| name == profile.model_selector()));
    let Some(model_index) = model_index else {
        return Err(IbisProfileDiagnosticV1::SelectedModelMissing);
    };
    let end = records[model_index + 1..]
        .iter()
        .position(|record| model_name(record).is_some())
        .map_or(records.len(), |offset| model_index + 1 + offset);
    let scope = &records[model_index + 1..end];

    let model_type_count = scope
        .iter()
        .filter(|record| data_keyword_equals(record, "model_type"))
        .count();
    if model_type_count == 0 {
        return Err(IbisProfileDiagnosticV1::ModelTypeMissing);
    }
    if model_type_count != 1
        || !scope
            .iter()
            .any(|record| data_two_tokens_equals(record, "model_type", "input"))
    {
        return Err(IbisProfileDiagnosticV1::ModelTypeNotInput);
    }
    let c_comp_entries = scope
        .iter()
        .filter_map(c_comp_from_record)
        .collect::<Vec<_>>();
    let c_comp = match c_comp_entries.as_slice() {
        [] => return Err(IbisProfileDiagnosticV1::CCompMissing),
        [entry] => (*entry)?,
        _ => return Err(IbisProfileDiagnosticV1::CCompDuplicate),
    };

    if scope
        .iter()
        .any(|record| keyword_equals(record, "algorithmic model"))
    {
        return Err(IbisProfileDiagnosticV1::AlgorithmicModelPresent);
    }
    let gnd_clamp = decode_named_clamp(scope, "gnd_clamp", ClampBranchV1::Gnd)?;
    let power_clamp = decode_named_clamp(scope, "power_clamp", ClampBranchV1::Power)?;
    Ok(DecodedDcClampProfileV1 {
        model: InputClampDcModelV1::new(gnd_clamp, power_clamp),
        c_comp,
    })
}

fn model_name(record: &StructuralRecordV1) -> Option<&str> {
    let StructuralRecordV1::Keyword {
        keyword, payload, ..
    } = record
    else {
        return None;
    };
    if !keyword.spelling().eq_ignore_ascii_case("model") || payload.len() != 1 {
        return None;
    }
    Some(payload[0].spelling())
}

fn keyword_equals(record: &StructuralRecordV1, expected: &str) -> bool {
    matches!(record, StructuralRecordV1::Keyword { keyword, .. } if keyword.spelling().eq_ignore_ascii_case(expected))
}

fn data_keyword_equals(record: &StructuralRecordV1, expected: &str) -> bool {
    matches!(record, StructuralRecordV1::Data { tokens, .. } if tokens.first().is_some_and(|token| token.spelling().eq_ignore_ascii_case(expected)))
}

fn data_two_tokens_equals(record: &StructuralRecordV1, first: &str, second: &str) -> bool {
    matches!(record, StructuralRecordV1::Data { tokens, .. } if tokens.len() == 2 && tokens[0].spelling().eq_ignore_ascii_case(first) && tokens[1].spelling().eq_ignore_ascii_case(second))
}

fn c_comp_from_record(
    record: &StructuralRecordV1,
) -> Option<Result<CCompDeclarationV1, IbisProfileDiagnosticV1>> {
    let StructuralRecordV1::Data { tokens, .. } = record else {
        return None;
    };
    if !tokens
        .first()
        .is_some_and(|token| token.spelling().eq_ignore_ascii_case("c_comp"))
    {
        return None;
    }
    if tokens.len() < 2 {
        return Some(Err(IbisProfileDiagnosticV1::CCompInvalid));
    }
    Some(
        parse_scaled_value(tokens[1].spelling(), "f")
            .map_err(|_| IbisProfileDiagnosticV1::CCompInvalid)
            .and_then(|value| {
                if value < 0.0 {
                    Err(IbisProfileDiagnosticV1::CCompNegative)
                } else {
                    FiniteF64::try_new(value, "C_comp farads")
                        .map(|capacitance_farads| CCompDeclarationV1 { capacitance_farads })
                        .map_err(|_| IbisProfileDiagnosticV1::CCompInvalid)
                }
            }),
    )
}

fn decode_named_clamp(
    scope: &[StructuralRecordV1],
    keyword: &str,
    branch: ClampBranchV1,
) -> Result<DcIvTableV1, IbisProfileDiagnosticV1> {
    let indices = scope
        .iter()
        .enumerate()
        .filter_map(|(index, record)| keyword_equals(record, keyword).then_some(index))
        .collect::<Vec<_>>();
    match indices.as_slice() {
        [] => Err(match branch {
            ClampBranchV1::Gnd => IbisProfileDiagnosticV1::GndClampMissing,
            ClampBranchV1::Power => IbisProfileDiagnosticV1::PowerClampMissing,
        }),
        [index] => {
            let end = scope[*index + 1..]
                .iter()
                .position(|record| matches!(record, StructuralRecordV1::Keyword { .. }))
                .map_or(scope.len(), |offset| index + 1 + offset);
            let knots = scope[index + 1..end]
                .iter()
                .map(parse_clamp_row)
                .collect::<Result<Vec<_>, _>>()?;
            DcIvTableV1::try_new(knots).map_err(|_| IbisProfileDiagnosticV1::ClampTableInvalid)
        }
        _ => Err(match branch {
            ClampBranchV1::Gnd => IbisProfileDiagnosticV1::GndClampDuplicate,
            ClampBranchV1::Power => IbisProfileDiagnosticV1::PowerClampDuplicate,
        }),
    }
}

fn parse_clamp_row(record: &StructuralRecordV1) -> Result<DcIvKnotV1, IbisProfileDiagnosticV1> {
    let StructuralRecordV1::Data { tokens, .. } = record else {
        return Err(IbisProfileDiagnosticV1::ClampRowInvalid);
    };
    if tokens.len() < 2 {
        return Err(IbisProfileDiagnosticV1::ClampRowInvalid);
    }
    let voltage = parse_scaled_value(tokens[0].spelling(), "v").and_then(|value| {
        Volts::try_new(value).map_err(|_| IbisProfileDiagnosticV1::ClampRowInvalid)
    })?;
    let current = parse_scaled_value(tokens[1].spelling(), "a").and_then(|value| {
        Amps::try_new(value).map_err(|_| IbisProfileDiagnosticV1::ClampRowInvalid)
    })?;
    Ok(DcIvKnotV1::new(voltage, current))
}

fn parse_scaled_value(token: &str, base_unit: &str) -> Result<f64, IbisProfileDiagnosticV1> {
    let lower = token.to_ascii_lowercase();
    let suffixes = [
        ("meg", 1.0e6),
        ("g", 1.0e9),
        ("k", 1.0e3),
        ("m", 1.0e-3),
        ("u", 1.0e-6),
        ("n", 1.0e-9),
        ("p", 1.0e-12),
        ("f", 1.0e-15),
        ("", 1.0),
    ];
    for (prefix, scale) in suffixes {
        let unit = format!("{prefix}{base_unit}");
        if let Some(number) = lower.strip_suffix(&unit) {
            let value = number
                .parse::<f64>()
                .map_err(|_| IbisProfileDiagnosticV1::ClampRowInvalid)?;
            let scaled = value * scale;
            return scaled
                .is_finite()
                .then_some(scaled)
                .ok_or(IbisProfileDiagnosticV1::ClampRowInvalid);
        }
    }
    if base_unit == "v" || base_unit == "a" {
        let value = token
            .parse::<f64>()
            .map_err(|_| IbisProfileDiagnosticV1::ClampRowInvalid)?;
        return value
            .is_finite()
            .then_some(value)
            .ok_or(IbisProfileDiagnosticV1::ClampRowInvalid);
    }
    Err(IbisProfileDiagnosticV1::CCompInvalid)
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
    fn preserves_balanced_brackets_inside_opaque_data_tokens() {
        let document = parse_structural_v1(b"A12 a[0] model\n", limits()).expect("data record");
        let StructuralRecordV1::Data { tokens, .. } = &document.records()[0] else {
            panic!("data record");
        };
        assert_eq!(tokens[1].spelling(), "a[0]");
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

    #[test]
    fn inspect_service_reports_only_structural_and_envelope_facts() {
        let report = IbisInspectServiceV1::inspect(
            "[IBIS Ver] 7.1\n[Component] board_0\n[Model] rx_0\n",
            limits(),
        )
        .expect("inspection");

        assert_eq!(report.input_byte_length(), 48);
        assert_eq!(
            report.input_sha256(),
            "a1275718c8b150431021aee40122401d5e5119ba914c1698ec75cc61f0292cba"
        );
        assert_eq!(report.declared_version(), "7.1");
        assert_eq!(report.component_count(), 1);
        assert_eq!(report.model_count(), 1);
        assert_eq!(report.block_count(), 3);
        assert_eq!(report.electrical_behavior_status(), "not_evaluated");
        assert_eq!(report.external_profile_acceptance_status(), "not_evaluated");
        assert_eq!(
            report.capability_matrix_id(),
            "sipi.p4a-ibis-conformance-matrix.v1"
        );
    }

    #[test]
    fn inspect_service_rejects_structural_or_envelope_failures() {
        assert!(matches!(
            IbisInspectServiceV1::inspect("[IBIS Ver] 7.1\n[Model]\n", limits()),
            Err(IbisInspectErrorV1::Semantic(_))
        ));
        assert!(matches!(
            IbisInspectServiceV1::inspect("[IBIS Ver] 7.1\n\0", limits()),
            Err(IbisInspectErrorV1::Structural(_))
        ));
    }

    fn knot(voltage: f64, current: f64) -> DcIvKnotV1 {
        DcIvKnotV1::new(
            Volts::try_new(voltage).expect("finite voltage"),
            Amps::try_new(current).expect("finite current"),
        )
    }

    fn model() -> InputClampDcModelV1 {
        InputClampDcModelV1::new(
            DcIvTableV1::try_new(vec![knot(-1.0, -2.0), knot(0.0, 0.0), knot(1.0, 2.0)])
                .expect("gnd table"),
            DcIvTableV1::try_new(vec![knot(-1.0, 3.0), knot(1.0, -1.0)]).expect("power table"),
        )
    }

    #[test]
    fn evaluates_two_signed_clamps_linearly_without_a_dc_capacitor() {
        let probe = DcClampProbeV1::new(
            Volts::try_new(0.5).expect("voltage"),
            Volts::try_new(0.0).expect("voltage"),
        );
        let result = evaluate_dc_clamps_v1(&model(), probe).expect("response");
        assert_eq!(result.gnd_current().get(), 1.0);
        assert_eq!(result.power_current().get(), 1.0);
        assert_eq!(result.capacitive_current().get(), 0.0);
        assert_eq!(result.total_shunt_current().get(), 2.0);
    }

    fn constitutive(capacitance_farads: f64) -> InputClampConstitutiveV1 {
        InputClampConstitutiveV1::try_new(
            model(),
            CCompDeclarationV1::try_new(capacitance_farads).expect("finite capacitance"),
        )
        .expect("constitutive model")
    }

    fn state(gnd: f64, power: f64, slope: f64) -> QuasiStaticClampStateV1 {
        QuasiStaticClampStateV1::try_new(
            Volts::try_new(gnd).expect("finite voltage"),
            Volts::try_new(power).expect("finite voltage"),
            slope,
        )
        .expect("finite state")
    }

    #[test]
    fn zero_c_comp_matches_the_dc_evaluator() {
        let dc_probe =
            DcClampProbeV1::new(Volts::try_new(0.5).unwrap(), Volts::try_new(0.0).unwrap());
        let dc = evaluate_dc_clamps_v1(&model(), dc_probe).expect("DC response");
        let continuous =
            evaluate_quasi_static_clamps_v1(&constitutive(0.0), state(0.5, 0.0, 7.0e9))
                .expect("continuous response");
        assert_eq!(continuous.gnd_current(), dc.gnd_current());
        assert_eq!(continuous.power_current(), dc.power_current());
        assert_eq!(continuous.c_comp_current().get(), 0.0);
        assert_eq!(continuous.total_shunt_current(), dc.total_shunt_current());
    }

    #[test]
    fn c_comp_is_continuous_and_adds_linearly_to_independent_clamps() {
        let response =
            evaluate_quasi_static_clamps_v1(&constitutive(1.0e-12), state(0.5, 0.0, 1.0e9))
                .expect("response");
        assert_eq!(response.gnd_current().get(), 1.0);
        assert_eq!(response.power_current().get(), 1.0);
        assert_eq!(response.c_comp_current().get(), 0.001);
        assert_eq!(response.total_shunt_current().get(), 2.001);

        let negative =
            evaluate_quasi_static_clamps_v1(&constitutive(1.0e-12), state(0.5, 0.0, -1.0e9))
                .expect("negative slope");
        assert_eq!(negative.c_comp_current().get(), -0.001);
        assert_eq!(negative.total_shunt_current().get(), 1.999);

        let changed_power =
            evaluate_quasi_static_clamps_v1(&constitutive(1.0e-12), state(0.5, 1.0, 1.0e9))
                .expect("independent power drive");
        assert_eq!(changed_power.gnd_current(), response.gnd_current());
        assert_eq!(changed_power.c_comp_current(), response.c_comp_current());
        assert_ne!(changed_power.power_current(), response.power_current());
    }

    #[test]
    fn quasi_static_boundary_rejects_invalid_inputs_and_dc_domain_first() {
        assert_eq!(
            CCompDeclarationV1::try_new(-1.0),
            Err(InputClampConstitutiveErrorV1::InvalidCComp)
        );
        assert_eq!(
            QuasiStaticClampStateV1::try_new(
                Volts::try_new(0.0).unwrap(),
                Volts::try_new(0.0).unwrap(),
                f64::NAN,
            ),
            Err(InputClampConstitutiveErrorV1::InvalidSlope)
        );
        assert_eq!(
            evaluate_quasi_static_clamps_v1(&constitutive(1.0), state(2.0, 0.0, 0.0)),
            Err(InputClampConstitutiveErrorV1::Dc(
                DcClampErrorV1::OutOfDomain {
                    branch: ClampBranchV1::Gnd
                }
            ))
        );
        let overflowing = InputClampConstitutiveV1::try_new(
            model(),
            CCompDeclarationV1::try_new(f64::MAX).unwrap(),
        )
        .unwrap();
        assert_eq!(
            evaluate_quasi_static_clamps_v1(&overflowing, state(0.0, 0.0, f64::MAX)),
            Err(InputClampConstitutiveErrorV1::NonFiniteCapacitiveCurrent)
        );
    }

    #[test]
    fn rejects_invalid_tables_and_probe_domains_without_partial_output() {
        assert_eq!(
            DcIvTableV1::try_new(vec![knot(0.0, 0.0)]),
            Err(DcClampErrorV1::InsufficientKnots)
        );
        assert_eq!(
            DcIvTableV1::try_new(vec![knot(0.0, 0.0), knot(0.0, 1.0)]),
            Err(DcClampErrorV1::VoltageNotStrictlyIncreasing)
        );
        let probe = DcClampProbeV1::new(
            Volts::try_new(2.0).expect("voltage"),
            Volts::try_new(0.0).expect("voltage"),
        );
        assert_eq!(
            evaluate_dc_clamps_v1(&model(), probe),
            Err(DcClampErrorV1::OutOfDomain {
                branch: ClampBranchV1::Gnd
            })
        );
    }

    #[test]
    fn scales_both_clamps_and_keeps_the_result_deterministic() {
        let scaled = InputClampDcModelV1::new(
            DcIvTableV1::try_new(vec![knot(-1.0, -6.0), knot(0.0, 0.0), knot(1.0, 6.0)])
                .expect("gnd table"),
            DcIvTableV1::try_new(vec![knot(-1.0, 9.0), knot(1.0, -3.0)]).expect("power table"),
        );
        let probe = DcClampProbeV1::new(
            Volts::try_new(0.5).expect("voltage"),
            Volts::try_new(0.0).expect("voltage"),
        );
        let base = evaluate_dc_clamps_v1(&model(), probe).expect("base");
        let triple = evaluate_dc_clamps_v1(&scaled, probe).expect("scaled");
        assert_eq!(triple.gnd_current().get(), 3.0 * base.gnd_current().get());
        assert_eq!(
            triple.power_current().get(),
            3.0 * base.power_current().get()
        );
        assert_eq!(
            triple.total_shunt_current().get(),
            3.0 * base.total_shunt_current().get()
        );
        assert_eq!(
            evaluate_dc_clamps_v1(&model(), probe),
            evaluate_dc_clamps_v1(&model(), probe)
        );
    }

    fn decode_profile(source: &[u8]) -> Result<DecodedDcClampProfileV1, IbisProfileDiagnosticV1> {
        let structural = parse_structural_v1(source, limits()).expect("structural parse");
        let semantic = build_semantic_envelope_v1(&structural).expect("semantic envelope");
        let profile = SelectedDcClampProfileV1::try_new(
            "7.1",
            "product_input_model",
            DcClampCornerV1::Typical,
        )
        .expect("profile");
        decode_selected_dc_clamps_v1(&semantic, &profile)
    }

    fn selected_input_source(extra_rows: &[u8]) -> Vec<u8> {
        [
            b"[IBIS Ver] 7.1\n[Model] product_input_model\nModel_type Input\nC_comp 2.5pF NA NA\n[GND_clamp]\n-1V -2A 999A 888A\n0V 0A 999A 888A\n1V 2A 999A 888A\n[POWER_clamp]\n-1V 3A 999A 888A\n1V -1A 999A 888A\n".as_slice(),
            extra_rows,
        ]
        .concat()
    }

    #[test]
    fn decodes_only_the_selected_typical_input_clamp_scope() {
        let decoded = decode_profile(&selected_input_source(
            b"[Package]\nignored 1 2\n[Model] other_model\nModel_type Output\n",
        ))
        .expect("decoded profile");
        assert_eq!(decoded.c_comp().capacitance_farads().get(), 2.5e-12);
        let result = evaluate_dc_clamps_v1(
            decoded.model(),
            DcClampProbeV1::new(
                Volts::try_new(0.5).expect("finite"),
                Volts::try_new(0.0).expect("finite"),
            ),
        )
        .expect("evaluated clamps");
        assert_eq!(result.gnd_current().get(), 1.0);
        assert_eq!(result.power_current().get(), 1.0);
        assert_eq!(result.capacitive_current().get(), 0.0);
    }

    #[test]
    fn dc_evaluate_service_returns_only_selected_static_current_facts() {
        let profile = SelectedDcClampProfileV1::try_new(
            "7.1",
            "product_input_model",
            DcClampCornerV1::Typical,
        )
        .expect("profile");
        let report = IbisDcEvaluateServiceV1::evaluate(
            std::str::from_utf8(&selected_input_source(b"")).expect("UTF-8"),
            &profile,
            DcClampProbeV1::new(
                Volts::try_new(0.5).expect("finite"),
                Volts::try_new(0.0).expect("finite"),
            ),
            limits(),
        )
        .expect("DC evaluation");
        assert_eq!(report.ibis_version(), "7.1");
        assert_eq!(report.model_selector(), "product_input_model");
        assert_eq!(report.gnd_current().get(), 1.0);
        assert_eq!(report.power_current().get(), 1.0);
        assert_eq!(report.total_shunt_current().get(), 2.0);
        assert_eq!(report.c_comp_current_amps(), 0.0);
        assert!(matches!(
            IbisDcEvaluateServiceV1::evaluate(
                std::str::from_utf8(&selected_input_source(b"")).expect("UTF-8"),
                &profile,
                DcClampProbeV1::new(
                    Volts::try_new(3.0).expect("finite"),
                    Volts::try_new(0.0).expect("finite"),
                ),
                limits(),
            ),
            Err(IbisDcEvaluateErrorV1::Dc(
                DcClampErrorV1::OutOfDomain { .. }
            ))
        ));
    }

    #[test]
    fn rejects_selected_profile_scope_mismatches_and_malformed_tables() {
        let cases = [
            (
                b"[IBIS Ver] 7.0\n[Model] product_input_model\nModel_type Input\nC_comp 1pF\n[GND_clamp]\n0V 0A\n1V 1A\n[POWER_clamp]\n0V 0A\n1V 1A\n".as_slice(),
                IbisProfileDiagnosticV1::VersionMismatch,
            ),
            (
                b"[IBIS Ver] 7.1\n[Model] product_input_model\nModel_type Output\nC_comp 1pF\n[GND_clamp]\n0V 0A\n1V 1A\n[POWER_clamp]\n0V 0A\n1V 1A\n".as_slice(),
                IbisProfileDiagnosticV1::ModelTypeNotInput,
            ),
            (
                b"[IBIS Ver] 7.1\n[Model] product_input_model\nModel_type Input\nC_comp -1pF\n[GND_clamp]\n0V 0A\n1V 1A\n[POWER_clamp]\n0V 0A\n1V 1A\n".as_slice(),
                IbisProfileDiagnosticV1::CCompNegative,
            ),
            (
                b"[IBIS Ver] 7.1\n[Model] product_input_model\nModel_type Input\nC_comp 1pF\n[GND_clamp]\n0V 0A\n1V 1A\n[POWER_clamp]\n0V 0A\n0V 1A\n".as_slice(),
                IbisProfileDiagnosticV1::ClampTableInvalid,
            ),
        ];
        for (source, expected) in cases {
            assert_eq!(decode_profile(source), Err(expected));
        }
    }

    #[test]
    fn rejects_duplicate_or_algorithmic_selected_profile_sections() {
        assert_eq!(
            decode_profile(&selected_input_source(b"C_comp 3pF\n")),
            Err(IbisProfileDiagnosticV1::CCompDuplicate)
        );
        assert_eq!(
            decode_profile(&selected_input_source(b"[Algorithmic Model]\nattached\n")),
            Err(IbisProfileDiagnosticV1::AlgorithmicModelPresent)
        );
        assert_eq!(
            decode_profile(&selected_input_source(b"[GND_clamp]\n0V 0A\n1V 1A\n")),
            Err(IbisProfileDiagnosticV1::GndClampDuplicate)
        );
    }
}
