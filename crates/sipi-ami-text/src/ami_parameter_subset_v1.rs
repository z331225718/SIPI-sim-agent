//! Narrow, product-owned AMI parameter-tree admission for the selected ADS
//! TX/RX text profiles.
//!
//! This module deliberately does not load a DLL, call an AMI entry point, or
//! infer a runtime value from a declaration default.  It parses the already
//! bounded structural AST, records only typed declaration facts, and validates
//! a caller-supplied forwarded subset.  The subset therefore proves host-side
//! forwarding identity only; it does not prove that a vendor model consumed a
//! parameter.

use std::fmt;

use sha2::{Digest, Sha256};

/// Policy identifier for the selected host-forwarded subset adapter.
pub const AMI_PARAMETER_SUBSET_POLICY_V1: &str =
    "sipi.p4b-02.ami-parameter-subset.v1.host-forwarded-only";
/// Policy identifier for the canonical typed declaration tree.
pub const AMI_PARAMETER_TREE_POLICY_V1: &str =
    "sipi.p4b-02.ami-parameter-tree.v1.selected-ads-profile";

/// The two exact external profile roots admitted for this observation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiParameterProfileRoleV1 {
    Tx,
    Rx,
}

impl AmiParameterProfileRoleV1 {
    pub const fn root_name(self) -> &'static str {
        match self {
            Self::Tx => "whistler_tx",
            Self::Rx => "whistler_rx",
        }
    }

    pub const fn token(self) -> &'static str {
        match self {
            Self::Tx => "tx",
            Self::Rx => "rx",
        }
    }
}

/// Product-owned AMI declaration type tokens observed in the selected files.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiDeclaredParameterTypeV1 {
    String,
    Boolean,
    Integer,
    Float,
    Ui,
    Tap,
}

impl AmiDeclaredParameterTypeV1 {
    pub const fn token(self) -> &'static str {
        match self {
            Self::String => "String",
            Self::Boolean => "Boolean",
            Self::Integer => "Integer",
            Self::Float => "Float",
            Self::Ui => "UI",
            Self::Tap => "Tap",
        }
    }

    fn parse(token: &str) -> Option<Self> {
        Some(match token {
            "String" => Self::String,
            "Boolean" => Self::Boolean,
            "Integer" => Self::Integer,
            "Float" => Self::Float,
            "UI" => Self::Ui,
            "Tap" => Self::Tap,
            _ => return None,
        })
    }
}

/// AMI declaration usage role.  `InOut` is accepted only when explicitly
/// selected; `Out` and `Info` are never admitted into an init subset.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiParameterUsageV1 {
    In,
    Out,
    Info,
    InOut,
}

impl AmiParameterUsageV1 {
    pub const fn token(self) -> &'static str {
        match self {
            Self::In => "In",
            Self::Out => "Out",
            Self::Info => "Info",
            Self::InOut => "InOut",
        }
    }

    fn parse(token: &str) -> Option<Self> {
        Some(match token {
            "In" => Self::In,
            "Out" => Self::Out,
            "Info" => Self::Info,
            "InOut" => Self::InOut,
            _ => return None,
        })
    }
}

/// Declaration payload format.  `ValueAndList` is retained as a distinct
/// format so a caller cannot silently treat a choice declaration as scalar.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiParameterFormatV1 {
    Value,
    List,
    ValueAndList,
}

impl AmiParameterFormatV1 {
    pub const fn token(self) -> &'static str {
        match self {
            Self::Value => "Value",
            Self::List => "List",
            Self::ValueAndList => "ValueAndList",
        }
    }
}

/// Format of a caller-selected forwarded value.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiParameterSelectionFormatV1 {
    Value,
    Choice,
}

impl AmiParameterSelectionFormatV1 {
    pub const fn token(self) -> &'static str {
        match self {
            Self::Value => "Value",
            Self::Choice => "Choice",
        }
    }
}

/// A finite inclusive range carried by an AMI declaration.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AmiRangeV1 {
    current: f64,
    lower: f64,
    upper: f64,
}

impl AmiRangeV1 {
    pub const fn current(self) -> f64 {
        self.current
    }

    pub const fn lower(self) -> f64 {
        self.lower
    }

    pub const fn upper(self) -> f64 {
        self.upper
    }
}

/// Fixed work limits for one tree/subset operation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AmiParameterProfileLimitsV1 {
    max_entries: usize,
    max_depth: usize,
    max_metadata_forms: usize,
    max_value_bytes: usize,
    max_selected: usize,
}

impl AmiParameterProfileLimitsV1 {
    pub fn try_new(
        max_entries: usize,
        max_depth: usize,
        max_metadata_forms: usize,
        max_value_bytes: usize,
        max_selected: usize,
    ) -> Result<Self, AmiSubsetErrorV1> {
        if [
            max_entries,
            max_depth,
            max_metadata_forms,
            max_value_bytes,
            max_selected,
        ]
        .contains(&0)
        {
            return Err(AmiSubsetErrorV1::ZeroLimit);
        }
        Ok(Self {
            max_entries,
            max_depth,
            max_metadata_forms,
            max_value_bytes,
            max_selected,
        })
    }

    pub const fn selected_profile() -> Self {
        Self {
            max_entries: 256,
            max_depth: 16,
            max_metadata_forms: 2048,
            max_value_bytes: 4096,
            max_selected: 64,
        }
    }

    pub const fn max_entries(self) -> usize {
        self.max_entries
    }

    pub const fn max_depth(self) -> usize {
        self.max_depth
    }

    pub const fn max_metadata_forms(self) -> usize {
        self.max_metadata_forms
    }

    pub const fn max_value_bytes(self) -> usize {
        self.max_value_bytes
    }

    pub const fn max_selected(self) -> usize {
        self.max_selected
    }
}

/// One canonicalized declaration leaf in the selected parameter tree.
#[derive(Clone, Debug, PartialEq)]
pub struct AmiParameterTreeEntryV1 {
    path: String,
    name: String,
    usage: AmiParameterUsageV1,
    declared_type: AmiDeclaredParameterTypeV1,
    format: AmiParameterFormatV1,
    value_token: Option<String>,
    list_tokens: Vec<String>,
    default_token: Option<String>,
    range: Option<AmiRangeV1>,
}

impl AmiParameterTreeEntryV1 {
    pub fn path(&self) -> &str {
        &self.path
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub const fn usage(&self) -> AmiParameterUsageV1 {
        self.usage
    }

    pub const fn declared_type(&self) -> AmiDeclaredParameterTypeV1 {
        self.declared_type
    }

    pub const fn format(&self) -> AmiParameterFormatV1 {
        self.format
    }

    pub fn value_token(&self) -> Option<&str> {
        self.value_token.as_deref()
    }

    pub fn list_tokens(&self) -> &[String] {
        &self.list_tokens
    }

    pub fn default_token(&self) -> Option<&str> {
        self.default_token.as_deref()
    }

    pub const fn range(&self) -> Option<AmiRangeV1> {
        self.range
    }
}

/// Canonical typed tree for one exact TX or RX `.ami` text binding.
#[derive(Clone, Debug, PartialEq)]
pub struct AmiTypedParameterTreeV1 {
    role: AmiParameterProfileRoleV1,
    root_name: String,
    source_sha256: String,
    canonical_digest: String,
    limits: AmiParameterProfileLimitsV1,
    entries: Vec<AmiParameterTreeEntryV1>,
}

impl AmiTypedParameterTreeV1 {
    pub const fn role(&self) -> AmiParameterProfileRoleV1 {
        self.role
    }

    pub fn root_name(&self) -> &str {
        &self.root_name
    }

    pub fn source_sha256(&self) -> &str {
        &self.source_sha256
    }

    pub fn canonical_digest(&self) -> &str {
        &self.canonical_digest
    }

    pub fn entries(&self) -> &[AmiParameterTreeEntryV1] {
        &self.entries
    }

    pub fn entry(&self, path: &str) -> Option<&AmiParameterTreeEntryV1> {
        self.entries.iter().find(|entry| entry.path == path)
    }

    pub const fn limits(&self) -> AmiParameterProfileLimitsV1 {
        self.limits
    }
}

/// One explicit caller-selected value to be forwarded to AMI_Init.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiParameterSelectionV1 {
    path: String,
    usage: AmiParameterUsageV1,
    declared_type: AmiDeclaredParameterTypeV1,
    format: AmiParameterSelectionFormatV1,
    value_token: String,
}

impl AmiParameterSelectionV1 {
    pub fn new(
        path: impl Into<String>,
        usage: AmiParameterUsageV1,
        declared_type: AmiDeclaredParameterTypeV1,
        format: AmiParameterSelectionFormatV1,
        value_token: impl Into<String>,
    ) -> Self {
        Self {
            path: path.into(),
            usage,
            declared_type,
            format,
            value_token: value_token.into(),
        }
    }

    pub fn path(&self) -> &str {
        &self.path
    }

    pub const fn usage(&self) -> AmiParameterUsageV1 {
        self.usage
    }

    pub const fn declared_type(&self) -> AmiDeclaredParameterTypeV1 {
        self.declared_type
    }

    pub const fn format(&self) -> AmiParameterSelectionFormatV1 {
        self.format
    }

    pub fn value_token(&self) -> &str {
        &self.value_token
    }
}

/// A typed, hash-bound subset the host is allowed to forward.  The subset is
/// intentionally separate from DLL consumption or runtime acceptance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiForwardedParameterSubsetV1 {
    role: AmiParameterProfileRoleV1,
    source_sha256: String,
    tree_digest: String,
    canonical_digest: String,
    limits: AmiParameterProfileLimitsV1,
    parameters: Vec<AmiParameterSelectionV1>,
}

impl AmiForwardedParameterSubsetV1 {
    pub const fn role(&self) -> AmiParameterProfileRoleV1 {
        self.role
    }

    pub fn source_sha256(&self) -> &str {
        &self.source_sha256
    }

    pub fn tree_digest(&self) -> &str {
        &self.tree_digest
    }

    pub fn canonical_digest(&self) -> &str {
        &self.canonical_digest
    }

    pub fn parameters(&self) -> &[AmiParameterSelectionV1] {
        &self.parameters
    }

    pub const fn limits(&self) -> AmiParameterProfileLimitsV1 {
        self.limits
    }

    /// Rebuild the typed tree and subset against the exact binding before a
    /// host forwards raw bytes.  This prevents a stale subset from being
    /// paired with another text asset and does not inspect or invoke a DLL.
    pub fn verify_binding_v1(
        &self,
        binding: &crate::AmiTextBindingV1,
    ) -> Result<(), AmiSubsetErrorV1> {
        if sha256_hex(binding.raw().bytes()) != self.source_sha256 {
            return Err(AmiSubsetErrorV1::SourceDigestMismatch);
        }
        let tree = build_ami_parameter_tree_v1(binding, self.role, self.limits)?;
        if tree.canonical_digest != self.tree_digest {
            return Err(AmiSubsetErrorV1::TreeDigestMismatch);
        }
        let subset = build_forwarded_parameter_subset_v1(&tree, &self.parameters)?;
        if subset.canonical_digest != self.canonical_digest {
            return Err(AmiSubsetErrorV1::SubsetDigestMismatch);
        }
        Ok(())
    }
}

/// Fail-closed errors for tree construction and subset validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AmiSubsetErrorV1 {
    ZeroLimit,
    EmptyDocument,
    RootCount,
    RootName,
    InvalidNodeName,
    MixedNodeContent,
    DuplicateNode(String),
    DepthLimit,
    EntryLimit,
    MetadataLimit,
    ValueLimit,
    MetadataShape(String),
    DuplicateMetadata(String),
    UnknownMetadata(String),
    MissingUsage(String),
    MissingType(String),
    UnknownUsage(String),
    UnknownType(String),
    InvalidMetadataValue(String),
    InvalidRange(String),
    InvalidChoice(String),
    UnknownPath(String),
    DuplicateSelection(String),
    SelectionLimit,
    UsageMismatch(String),
    TypeMismatch(String),
    FormatMismatch(String),
    InvalidSelectedValue(String),
    ChoiceMismatch(String),
    RangeViolation(String),
    SourceDigestMismatch,
    TreeDigestMismatch,
    SubsetDigestMismatch,
    Parse(crate::AmiTextDiagnosticV1),
}

impl fmt::Display for AmiSubsetErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "AMI parameter subset error: {self:?}")
    }
}

impl std::error::Error for AmiSubsetErrorV1 {}

#[derive(Default)]
struct WalkState {
    entries: Vec<AmiParameterTreeEntryV1>,
    metadata_forms: usize,
}

fn token(node: &crate::AmiTextNodeV1) -> Option<&str> {
    match node {
        crate::AmiTextNodeV1::Atom(value) | crate::AmiTextNodeV1::Quoted(value) => {
            Some(value.spelling())
        }
        crate::AmiTextNodeV1::List(_) => None,
    }
}

fn valid_name(value: &str) -> bool {
    !value.is_empty()
        && value.is_ascii()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
}

fn checked_value_size(
    value: &str,
    limits: AmiParameterProfileLimitsV1,
) -> Result<(), AmiSubsetErrorV1> {
    if value.len() > limits.max_value_bytes {
        Err(AmiSubsetErrorV1::ValueLimit)
    } else {
        Ok(())
    }
}

fn parse_finite(value: &str) -> Option<f64> {
    value.parse::<f64>().ok().filter(|value| value.is_finite())
}

fn parse_range(path: &str, list: &crate::AmiTextListV1) -> Result<AmiRangeV1, AmiSubsetErrorV1> {
    let values = &list.items()[1..];
    if values.len() != 3 {
        return Err(AmiSubsetErrorV1::MetadataShape(path.to_owned()));
    }
    let numbers: Option<Vec<f64>> = values
        .iter()
        .map(token)
        .map(|value| value.and_then(parse_finite))
        .collect();
    let numbers = numbers.ok_or_else(|| AmiSubsetErrorV1::InvalidRange(path.to_owned()))?;
    let range = AmiRangeV1 {
        current: numbers[0],
        lower: numbers[1],
        upper: numbers[2],
    };
    if range.lower > range.upper || range.current < range.lower || range.current > range.upper {
        return Err(AmiSubsetErrorV1::InvalidRange(path.to_owned()));
    }
    Ok(range)
}

fn parse_typed_token(
    path: &str,
    parameter_type: AmiDeclaredParameterTypeV1,
    value: &str,
) -> Result<(), AmiSubsetErrorV1> {
    let valid = match parameter_type {
        AmiDeclaredParameterTypeV1::String => {
            value.len() >= 2 && value.starts_with('"') && value.ends_with('"')
        }
        AmiDeclaredParameterTypeV1::Boolean => matches!(value, "True" | "False"),
        AmiDeclaredParameterTypeV1::Integer => value.parse::<i64>().is_ok(),
        AmiDeclaredParameterTypeV1::Float
        | AmiDeclaredParameterTypeV1::Ui
        | AmiDeclaredParameterTypeV1::Tap => parse_finite(value).is_some(),
    };
    if valid {
        Ok(())
    } else {
        Err(AmiSubsetErrorV1::InvalidMetadataValue(path.to_owned()))
    }
}

fn parse_leaf(
    list: &crate::AmiTextListV1,
    path: &str,
    limits: AmiParameterProfileLimitsV1,
    state: &mut WalkState,
) -> Result<(), AmiSubsetErrorV1> {
    let items = list.items();
    let name = token(&items[0]).ok_or(AmiSubsetErrorV1::InvalidNodeName)?;
    let mut usage = None;
    let mut declared_type = None;
    let mut value_token = None;
    let mut list_tokens = Vec::new();
    let mut default_token = None;
    let mut range = None;

    for item in &items[1..] {
        let child = match item {
            crate::AmiTextNodeV1::List(child) => child,
            _ => return Err(AmiSubsetErrorV1::MixedNodeContent),
        };
        state.metadata_forms = state
            .metadata_forms
            .checked_add(1)
            .ok_or(AmiSubsetErrorV1::MetadataLimit)?;
        if state.metadata_forms > limits.max_metadata_forms {
            return Err(AmiSubsetErrorV1::MetadataLimit);
        }
        let head = child
            .items()
            .first()
            .and_then(token)
            .ok_or_else(|| AmiSubsetErrorV1::MetadataShape(path.to_owned()))?;
        let metadata_path = format!("{path}/{head}");
        match head {
            "Usage" => {
                if usage.is_some() || child.items().len() != 2 {
                    return Err(AmiSubsetErrorV1::DuplicateMetadata(metadata_path));
                }
                let raw = child
                    .items()
                    .get(1)
                    .and_then(token)
                    .ok_or_else(|| AmiSubsetErrorV1::MetadataShape(metadata_path.clone()))?;
                usage = Some(
                    AmiParameterUsageV1::parse(raw)
                        .ok_or_else(|| AmiSubsetErrorV1::UnknownUsage(raw.to_owned()))?,
                );
            }
            "Type" => {
                if declared_type.is_some() || child.items().len() != 2 {
                    return Err(AmiSubsetErrorV1::DuplicateMetadata(metadata_path));
                }
                let raw = child
                    .items()
                    .get(1)
                    .and_then(token)
                    .ok_or_else(|| AmiSubsetErrorV1::MetadataShape(metadata_path.clone()))?;
                declared_type = Some(
                    AmiDeclaredParameterTypeV1::parse(raw)
                        .ok_or_else(|| AmiSubsetErrorV1::UnknownType(raw.to_owned()))?,
                );
            }
            "Value" => {
                if value_token.is_some() || child.items().len() != 2 {
                    return Err(AmiSubsetErrorV1::DuplicateMetadata(metadata_path));
                }
                value_token = Some(
                    child
                        .items()
                        .get(1)
                        .and_then(token)
                        .ok_or_else(|| AmiSubsetErrorV1::MetadataShape(metadata_path.clone()))?
                        .to_owned(),
                );
            }
            "List" => {
                if !list_tokens.is_empty() || child.items().len() < 2 {
                    return Err(AmiSubsetErrorV1::DuplicateMetadata(metadata_path));
                }
                for value in &child.items()[1..] {
                    let value = token(value)
                        .ok_or_else(|| AmiSubsetErrorV1::InvalidChoice(metadata_path.clone()))?;
                    checked_value_size(value, limits)?;
                    list_tokens.push(value.to_owned());
                }
            }
            "Default" => {
                if default_token.is_some() || child.items().len() != 2 {
                    return Err(AmiSubsetErrorV1::DuplicateMetadata(metadata_path));
                }
                default_token = Some(
                    child
                        .items()
                        .get(1)
                        .and_then(token)
                        .ok_or_else(|| AmiSubsetErrorV1::MetadataShape(metadata_path.clone()))?
                        .to_owned(),
                );
            }
            "Range" => {
                if range.is_some() {
                    return Err(AmiSubsetErrorV1::DuplicateMetadata(metadata_path));
                }
                range = Some(parse_range(path, child)?);
            }
            "Description" | "List_Tip" | "Corner" => {
                if child.items().len() < 2 {
                    return Err(AmiSubsetErrorV1::MetadataShape(metadata_path));
                }
                if head == "Corner" {
                    for value in &child.items()[1..] {
                        let value = token(value).and_then(parse_finite).ok_or_else(|| {
                            AmiSubsetErrorV1::InvalidMetadataValue(path.to_owned())
                        })?;
                        let _ = value;
                    }
                }
            }
            _ => return Err(AmiSubsetErrorV1::UnknownMetadata(head.to_owned())),
        }
    }

    let usage = usage.ok_or_else(|| AmiSubsetErrorV1::MissingUsage(path.to_owned()))?;
    let declared_type =
        declared_type.ok_or_else(|| AmiSubsetErrorV1::MissingType(path.to_owned()))?;
    if let Some(range) = range {
        match declared_type {
            AmiDeclaredParameterTypeV1::String | AmiDeclaredParameterTypeV1::Boolean => {
                return Err(AmiSubsetErrorV1::InvalidRange(path.to_owned()));
            }
            AmiDeclaredParameterTypeV1::Integer
                if [range.current, range.lower, range.upper]
                    .into_iter()
                    .any(|value| {
                        value.fract() != 0.0 || value < i64::MIN as f64 || value > i64::MAX as f64
                    }) =>
            {
                return Err(AmiSubsetErrorV1::InvalidRange(path.to_owned()));
            }
            _ => {}
        }
    }
    let format = match (value_token.is_some(), list_tokens.is_empty()) {
        (true, true) => AmiParameterFormatV1::Value,
        (false, false) => AmiParameterFormatV1::List,
        (true, false) => AmiParameterFormatV1::ValueAndList,
        (false, true) if range.is_some() || default_token.is_some() => AmiParameterFormatV1::Value,
        (false, true) => return Err(AmiSubsetErrorV1::MetadataShape(path.to_owned())),
    };

    if let Some(value) = &value_token {
        checked_value_size(value, limits)?;
        parse_typed_token(path, declared_type, value)?;
    }
    for value in &list_tokens {
        parse_typed_token(path, declared_type, value)?;
    }
    if let Some(default) = &default_token {
        checked_value_size(default, limits)?;
        parse_typed_token(path, declared_type, default)?;
    }
    if let (Some(value), Some(range)) = (&value_token, range)
        && let Some(number) = parse_finite(value)
        && (number < range.lower || number > range.upper)
    {
        return Err(AmiSubsetErrorV1::RangeViolation(path.to_owned()));
    }
    if let (Some(default), Some(range)) = (&default_token, range)
        && let Some(number) = parse_finite(default)
        && (number < range.lower || number > range.upper)
    {
        return Err(AmiSubsetErrorV1::RangeViolation(path.to_owned()));
    }
    if let Some(default) = &default_token
        && !list_tokens.is_empty()
        && !list_tokens.iter().any(|value| value == default)
    {
        return Err(AmiSubsetErrorV1::ChoiceMismatch(path.to_owned()));
    }

    state.entries.push(AmiParameterTreeEntryV1 {
        path: path.to_owned(),
        name: name.to_owned(),
        usage,
        declared_type,
        format,
        value_token,
        list_tokens,
        default_token,
        range,
    });
    Ok(())
}

fn walk_list(
    list: &crate::AmiTextListV1,
    parent_path: Option<&str>,
    depth: usize,
    limits: AmiParameterProfileLimitsV1,
    state: &mut WalkState,
) -> Result<(), AmiSubsetErrorV1> {
    if depth > limits.max_depth {
        return Err(AmiSubsetErrorV1::DepthLimit);
    }
    let items = list.items();
    let name = items
        .first()
        .and_then(token)
        .ok_or(AmiSubsetErrorV1::InvalidNodeName)?;
    if !valid_name(name) {
        return Err(AmiSubsetErrorV1::InvalidNodeName);
    }
    let path = match parent_path {
        Some(parent) => format!("{parent}/{name}"),
        None => name.to_owned(),
    };
    let children: Vec<&crate::AmiTextListV1> = items[1..]
        .iter()
        .filter_map(|item| match item {
            crate::AmiTextNodeV1::List(child) => Some(child),
            _ => None,
        })
        .collect();
    let scalar_siblings = items[1..]
        .iter()
        .any(|item| !matches!(item, crate::AmiTextNodeV1::List(_)));
    if scalar_siblings {
        return Err(AmiSubsetErrorV1::MixedNodeContent);
    }
    let metadata = children.iter().any(|child| {
        child
            .items()
            .first()
            .and_then(token)
            .is_some_and(is_metadata_head)
    });
    if metadata {
        parse_leaf(list, &path, limits, state)?;
    } else {
        let mut names = Vec::new();
        for child in children {
            let child_name = child.items().first().and_then(token).unwrap_or("");
            if names.contains(&child_name) {
                return Err(AmiSubsetErrorV1::DuplicateNode(child_name.to_owned()));
            }
            names.push(child_name);
            walk_list(child, Some(&path), depth + 1, limits, state)?;
        }
    }
    if state.entries.len() > limits.max_entries {
        return Err(AmiSubsetErrorV1::EntryLimit);
    }
    Ok(())
}

fn is_metadata_head(value: &str) -> bool {
    matches!(
        value,
        "Usage"
            | "Type"
            | "Value"
            | "List"
            | "Default"
            | "Range"
            | "Description"
            | "List_Tip"
            | "Corner"
    )
}

/// Build a canonical typed tree from one exact parsed AMI text binding.
pub fn build_ami_parameter_tree_v1(
    binding: &crate::AmiTextBindingV1,
    role: AmiParameterProfileRoleV1,
    limits: AmiParameterProfileLimitsV1,
) -> Result<AmiTypedParameterTreeV1, AmiSubsetErrorV1> {
    let forms = binding.document().forms();
    if forms.is_empty() {
        return Err(AmiSubsetErrorV1::EmptyDocument);
    }
    if forms.len() != 1 {
        return Err(AmiSubsetErrorV1::RootCount);
    }
    let root_name = forms[0]
        .items()
        .first()
        .and_then(token)
        .ok_or(AmiSubsetErrorV1::RootName)?;
    if root_name != role.root_name() {
        return Err(AmiSubsetErrorV1::RootName);
    }
    let mut state = WalkState::default();
    walk_list(&forms[0], None, 1, limits, &mut state)?;
    state
        .entries
        .sort_by(|left, right| left.path.cmp(&right.path));
    let mut last = None;
    for entry in &state.entries {
        if last.is_some_and(|value: &str| value == entry.path) {
            return Err(AmiSubsetErrorV1::DuplicateNode(entry.path.clone()));
        }
        last = Some(entry.path.as_str());
    }
    if state.entries.is_empty() {
        return Err(AmiSubsetErrorV1::EntryLimit);
    }
    let canonical = canonical_tree_bytes(role, root_name, &state.entries);
    Ok(AmiTypedParameterTreeV1 {
        role,
        root_name: root_name.to_owned(),
        source_sha256: sha256_hex(binding.raw().bytes()),
        canonical_digest: sha256_hex(&canonical),
        limits,
        entries: state.entries,
    })
}

/// Build a hash-bound forwarded subset.  No declaration default is used when
/// a selection is absent; callers choose every value explicitly.
pub fn build_forwarded_parameter_subset_v1(
    tree: &AmiTypedParameterTreeV1,
    selections: &[AmiParameterSelectionV1],
) -> Result<AmiForwardedParameterSubsetV1, AmiSubsetErrorV1> {
    if selections.len() > tree.limits.max_selected {
        return Err(AmiSubsetErrorV1::SelectionLimit);
    }
    let mut parameters = selections.to_vec();
    parameters.sort_by(|left, right| left.path.cmp(&right.path));
    for pair in parameters.windows(2) {
        if pair[0].path == pair[1].path {
            return Err(AmiSubsetErrorV1::DuplicateSelection(pair[0].path.clone()));
        }
    }
    for selection in &parameters {
        let entry = tree
            .entry(&selection.path)
            .ok_or_else(|| AmiSubsetErrorV1::UnknownPath(selection.path.clone()))?;
        if selection.usage != entry.usage {
            return Err(AmiSubsetErrorV1::UsageMismatch(selection.path.clone()));
        }
        if !matches!(
            selection.usage,
            AmiParameterUsageV1::In | AmiParameterUsageV1::InOut
        ) {
            return Err(AmiSubsetErrorV1::UsageMismatch(selection.path.clone()));
        }
        if selection.declared_type != entry.declared_type {
            return Err(AmiSubsetErrorV1::TypeMismatch(selection.path.clone()));
        }
        let format_matches = matches!(
            (entry.format, selection.format),
            (
                AmiParameterFormatV1::Value,
                AmiParameterSelectionFormatV1::Value
            ) | (
                AmiParameterFormatV1::List,
                AmiParameterSelectionFormatV1::Choice
            ) | (
                AmiParameterFormatV1::ValueAndList,
                AmiParameterSelectionFormatV1::Value
            ) | (
                AmiParameterFormatV1::ValueAndList,
                AmiParameterSelectionFormatV1::Choice
            )
        );
        if !format_matches {
            return Err(AmiSubsetErrorV1::FormatMismatch(selection.path.clone()));
        }
        checked_value_size(&selection.value_token, tree.limits)?;
        parse_typed_token(
            &selection.path,
            selection.declared_type,
            &selection.value_token,
        )
        .map_err(|_| AmiSubsetErrorV1::InvalidSelectedValue(selection.path.clone()))?;
        if matches!(selection.format, AmiParameterSelectionFormatV1::Choice)
            && !entry
                .list_tokens
                .iter()
                .any(|value| value == &selection.value_token)
        {
            return Err(AmiSubsetErrorV1::ChoiceMismatch(selection.path.clone()));
        }
        if let Some(range) = entry.range
            && let Some(value) = parse_finite(&selection.value_token)
            && (value < range.lower || value > range.upper)
        {
            return Err(AmiSubsetErrorV1::RangeViolation(selection.path.clone()));
        }
    }
    let canonical = canonical_subset_bytes(
        tree.role,
        &tree.source_sha256,
        &tree.canonical_digest,
        &parameters,
    );
    Ok(AmiForwardedParameterSubsetV1 {
        role: tree.role,
        source_sha256: tree.source_sha256.clone(),
        tree_digest: tree.canonical_digest.clone(),
        canonical_digest: sha256_hex(&canonical),
        limits: tree.limits,
        parameters,
    })
}

fn tx(
    path: impl Into<String>,
    usage: AmiParameterUsageV1,
    ty: AmiDeclaredParameterTypeV1,
    format: AmiParameterSelectionFormatV1,
    value: impl Into<String>,
) -> AmiParameterSelectionV1 {
    AmiParameterSelectionV1::new(path, usage, ty, format, value)
}

/// Explicit values observed in the selected TX host-forwarded input tree.
/// These are not declaration defaults and are never inferred by the adapter.
pub fn selected_tx_forwarded_parameters_v1() -> Vec<AmiParameterSelectionV1> {
    vec![
        tx(
            "whistler_tx/Reserved_Parameters/Modulation",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::String,
            AmiParameterSelectionFormatV1::Value,
            "\"NRZ\"",
        ),
        tx(
            "whistler_tx/Model_Specific/GeneralTX/TX_Corner",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "0",
        ),
        tx(
            "whistler_tx/Model_Specific/GeneralTX/lane",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Float,
            AmiParameterSelectionFormatV1::Value,
            "0",
        ),
        tx(
            "whistler_tx/Model_Specific/GeneralTX/swing_Vppd",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Float,
            AmiParameterSelectionFormatV1::Choice,
            "0.886",
        ),
        tx(
            "whistler_tx/Model_Specific/FFE/TapWeights/-1",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Tap,
            AmiParameterSelectionFormatV1::Value,
            "-0.25",
        ),
        tx(
            "whistler_tx/Model_Specific/FFE/TapWeights/0",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Tap,
            AmiParameterSelectionFormatV1::Value,
            "0.75",
        ),
        tx(
            "whistler_tx/Model_Specific/FFE/TapWeights/1",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Tap,
            AmiParameterSelectionFormatV1::Value,
            "0",
        ),
        tx(
            "whistler_tx/Model_Specific/FFE/Preset",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "11",
        ),
    ]
}

/// Explicit values observed in the selected RX host-forwarded input tree.
pub fn selected_rx_forwarded_parameters_v1() -> Vec<AmiParameterSelectionV1> {
    let mut values = vec![
        tx(
            "whistler_rx/Reserved_Parameters/Modulation",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::String,
            AmiParameterSelectionFormatV1::Value,
            "\"NRZ\"",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/wave_capture_delay",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "1000",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/wave_capture_cnt",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "2047",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/RX_corner",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "0",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/force_linear_model",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "0",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/adapt_mode",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "3",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/wave_capture_mode",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "2",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/init_adapt_for_getwave",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "0",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/serdes_mode",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "0",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/log_level",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "0",
        ),
        tx(
            "whistler_rx/Model_Specific/GeneralRX/lane",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "0",
        ),
        tx(
            "whistler_rx/Model_Specific/CTLE_CTLE/cte_col_index",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "-1",
        ),
        tx(
            "whistler_rx/Model_Specific/CTLE_CTLE/peak",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "34",
        ),
        tx(
            "whistler_rx/Model_Specific/CTLE_CTLE/lfeq",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "4",
        ),
        tx(
            "whistler_rx/Model_Specific/CTLE_VGA/vga_col_index",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "-1",
        ),
        tx(
            "whistler_rx/Model_Specific/CTLE_VGA/gain",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "16",
        ),
        tx(
            "whistler_rx/Model_Specific/CTLE_VGA/vga_indbypass1",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Value,
            "4",
        ),
        tx(
            "whistler_rx/Model_Specific/DFECDR/ReferenceOffset",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Float,
            AmiParameterSelectionFormatV1::Value,
            "0",
        ),
        tx(
            "whistler_rx/Model_Specific/DFECDR/PhaseOffset",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Ui,
            AmiParameterSelectionFormatV1::Value,
            "0",
        ),
        tx(
            "whistler_rx/Model_Specific/DFECDR/Mode",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "2",
        ),
        tx(
            "whistler_rx/Model_Specific/DFECDR/IQPAMode",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Integer,
            AmiParameterSelectionFormatV1::Choice,
            "1",
        ),
        tx(
            "whistler_rx/Model_Specific/DFECDR/IQPAHistScale",
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::Float,
            AmiParameterSelectionFormatV1::Value,
            "10",
        ),
    ];
    for index in 1..=8 {
        values.push(tx(
            format!("whistler_rx/Model_Specific/DFECDR/TapWeights/{index}"),
            AmiParameterUsageV1::InOut,
            AmiDeclaredParameterTypeV1::Tap,
            AmiParameterSelectionFormatV1::Value,
            "0",
        ));
    }
    values
}

fn append_field(output: &mut Vec<u8>, field: &str) {
    output.extend_from_slice(field.len().to_string().as_bytes());
    output.push(b':');
    output.extend_from_slice(field.as_bytes());
    output.push(b'|');
}

fn canonical_tree_bytes(
    role: AmiParameterProfileRoleV1,
    root_name: &str,
    entries: &[AmiParameterTreeEntryV1],
) -> Vec<u8> {
    let mut output = Vec::new();
    append_field(&mut output, AMI_PARAMETER_TREE_POLICY_V1);
    append_field(&mut output, role.token());
    append_field(&mut output, root_name);
    for entry in entries {
        append_field(&mut output, entry.path());
        append_field(&mut output, entry.name());
        append_field(&mut output, entry.usage.token());
        append_field(&mut output, entry.declared_type.token());
        append_field(&mut output, entry.format.token());
        append_field(&mut output, entry.value_token.as_deref().unwrap_or(""));
        for value in &entry.list_tokens {
            append_field(&mut output, value);
        }
        append_field(&mut output, entry.default_token.as_deref().unwrap_or(""));
        if let Some(range) = entry.range {
            append_field(
                &mut output,
                &format!(
                    "{:.17e},{:.17e},{:.17e}",
                    range.current, range.lower, range.upper
                ),
            );
        } else {
            append_field(&mut output, "");
        }
    }
    output
}

fn canonical_subset_bytes(
    role: AmiParameterProfileRoleV1,
    source_sha256: &str,
    tree_digest: &str,
    parameters: &[AmiParameterSelectionV1],
) -> Vec<u8> {
    let mut output = Vec::new();
    append_field(&mut output, AMI_PARAMETER_SUBSET_POLICY_V1);
    append_field(&mut output, role.token());
    append_field(&mut output, source_sha256);
    append_field(&mut output, tree_digest);
    for parameter in parameters {
        append_field(&mut output, parameter.path());
        append_field(&mut output, parameter.usage.token());
        append_field(&mut output, parameter.declared_type.token());
        append_field(&mut output, parameter.format.token());
        append_field(&mut output, parameter.value_token());
    }
    output
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;

    const TX: &str = r#"
(whistler_tx
  (Reserved_Parameters
    (Modulation (Usage In) (Type String) (Value "NRZ")))
  (Model_Specific
    (GeneralTX
      (TX_Corner (Usage In) (Type Integer) (List -1 0 1) (Value 0))
      (lane (Usage In) (Type Float) (Range 0 0 7) (Value 0))
      (swing_Vppd (Usage In) (Type Float) (List 0.886 0.842 0.978) (Default 0.886)))
    (FFE
      (TapWeights
        (-1 (Usage In) (Type Tap) (Range -1 -1 1) (Value -0.25))
        (0 (Usage In) (Type Tap) (Range 0 -1 1) (Value 0.75))
        (1 (Usage In) (Type Tap) (Range 0 -1 1) (Value 0)))
      (Preset (Usage In) (Type Integer) (List 1 11 16) (Value 11)))))
"#;

    fn limits() -> crate::ParseLimitsV1 {
        crate::ParseLimitsV1::try_new(16_384, 64, 4_096, 4_096).expect("limits")
    }

    #[test]
    fn selected_tx_subset_is_explicit_and_bounded() {
        let binding = crate::parse_and_bind_v1(TX.as_bytes(), limits()).expect("binding");
        let tree = build_ami_parameter_tree_v1(
            &binding,
            AmiParameterProfileRoleV1::Tx,
            AmiParameterProfileLimitsV1::selected_profile(),
        )
        .expect("tree");
        let subset =
            build_forwarded_parameter_subset_v1(&tree, &selected_tx_forwarded_parameters_v1())
                .expect("subset");
        assert_eq!(subset.parameters().len(), 8);
        subset.verify_binding_v1(&binding).expect("reverify");
        assert_eq!(
            tree.entries()
                .iter()
                .filter(|entry| entry.usage() == AmiParameterUsageV1::In)
                .count(),
            8
        );
    }

    #[test]
    fn changed_value_and_wrong_usage_fail_closed() {
        let binding = crate::parse_and_bind_v1(TX.as_bytes(), limits()).expect("binding");
        let tree = build_ami_parameter_tree_v1(
            &binding,
            AmiParameterProfileRoleV1::Tx,
            AmiParameterProfileLimitsV1::selected_profile(),
        )
        .expect("tree");
        let mut selections = selected_tx_forwarded_parameters_v1();
        selections[0] = AmiParameterSelectionV1::new(
            selections[0].path(),
            AmiParameterUsageV1::Info,
            AmiDeclaredParameterTypeV1::String,
            AmiParameterSelectionFormatV1::Value,
            "\"NRZ\"",
        );
        assert!(matches!(
            build_forwarded_parameter_subset_v1(&tree, &selections),
            Err(AmiSubsetErrorV1::UsageMismatch(_))
        ));
        selections[0] = AmiParameterSelectionV1::new(
            selections[0].path(),
            AmiParameterUsageV1::In,
            AmiDeclaredParameterTypeV1::String,
            AmiParameterSelectionFormatV1::Value,
            "\"PAM4\"",
        );
        let subset = build_forwarded_parameter_subset_v1(&tree, &selections).expect("subset");
        assert_ne!(subset.canonical_digest(), "");
        let changed = TX.replace("\"NRZ\"", "\"PAM4\"");
        let changed_binding =
            crate::parse_and_bind_v1(changed.as_bytes(), limits()).expect("binding");
        assert!(matches!(
            subset.verify_binding_v1(&changed_binding),
            Err(AmiSubsetErrorV1::SourceDigestMismatch)
        ));
    }

    #[test]
    fn selected_rx_subset_has_only_forwarded_usage_roles() {
        let selections = selected_rx_forwarded_parameters_v1();
        assert_eq!(selections.len(), 30);
        assert!(selections.iter().all(|selection| matches!(
            selection.usage(),
            AmiParameterUsageV1::In | AmiParameterUsageV1::InOut
        )));
        assert!(
            selections
                .iter()
                .all(|selection| !selection.path().ends_with("/Phase"))
        );
    }
}
