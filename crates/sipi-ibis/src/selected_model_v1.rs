//! Explicit selected-model grammar and bounded consumer (P4A-03).
//!
//! This module is intentionally narrower than a general IBIS parser.  A
//! caller must provide the terminal identity, the direct model or selector
//! branch, an explicit corner/PVT record, and one known table family.  The
//! consumer resolves only that request against a complete typed inventory and
//! returns table identity metadata; it does not read a default model/corner,
//! evaluate table values, or compose a transient.

use std::{error::Error, fmt};

use crate::{
    IbisDiagnosticV1, IbisTypedInventoryErrorV1, IbisTypedInventoryReportV1,
    IbisTypedInventoryServiceV1, ModelTypeV1, ParseLimitsV1, StructuralRecordV1,
    TypedPinDeclarationV1, build_semantic_envelope_v1, parse_structural_v1,
};

/// Stable policy identifier for the explicit selected-model consumer.
pub const SELECTED_MODEL_POLICY_V1: &str =
    "sipi.p4a-03.selected-model-consumer.v1.explicit-profile-only";

/// Bounded lexical length for caller-supplied identifiers.
pub const SELECTED_MODEL_MAX_NAME_BYTES_V1: usize = 128;

/// Bounded number of opaque rows represented by one returned table identity.
pub const SELECTED_MODEL_MAX_TABLE_ROWS_V1: usize = 1_000_000;

fn checked_name(value: impl Into<String>) -> Result<String, SelectedModelRequestErrorV1> {
    let value = value.into();
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return Err(SelectedModelRequestErrorV1::EmptyName);
    }
    if !trimmed.is_ascii() {
        return Err(SelectedModelRequestErrorV1::NonAsciiName);
    }
    if trimmed.len() > SELECTED_MODEL_MAX_NAME_BYTES_V1 {
        return Err(SelectedModelRequestErrorV1::NameTooLong {
            max_bytes: SELECTED_MODEL_MAX_NAME_BYTES_V1,
        });
    }
    if !trimmed
        .chars()
        .all(|character| character.is_ascii_alphanumeric() || "_.-".contains(character))
    {
        return Err(SelectedModelRequestErrorV1::InvalidName);
    }
    Ok(trimmed.to_owned())
}

/// A caller-owned terminal identity.  No signal or pin fallback is applied.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SignalPinRoleV1 {
    Signal(String),
    Pin(String),
}

impl SignalPinRoleV1 {
    /// Build a signal-role identity from an explicit signal name.
    pub fn signal(value: impl Into<String>) -> Result<Self, SelectedModelRequestErrorV1> {
        Ok(Self::Signal(checked_name(value)?))
    }

    /// Build a pin-role identity from an explicit pin name.
    pub fn pin(value: impl Into<String>) -> Result<Self, SelectedModelRequestErrorV1> {
        Ok(Self::Pin(checked_name(value)?))
    }

    pub fn name(&self) -> &str {
        match self {
            Self::Signal(value) | Self::Pin(value) => value,
        }
    }

    pub const fn kind(&self) -> &'static str {
        match self {
            Self::Signal(_) => "signal",
            Self::Pin(_) => "pin",
        }
    }
}

/// The only two legal model-target shapes.  A selector target always names
/// its selected branch model; the branch is never inferred from its position.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SelectedModelTargetV1 {
    Model(String),
    SelectorBranch { selector: String, branch: String },
}

impl SelectedModelTargetV1 {
    /// Build an explicit direct-model target.
    pub fn model(value: impl Into<String>) -> Result<Self, SelectedModelRequestErrorV1> {
        Ok(Self::Model(checked_name(value)?))
    }

    /// Build an explicit selector and branch-model target.
    pub fn selector_branch(
        selector: impl Into<String>,
        branch: impl Into<String>,
    ) -> Result<Self, SelectedModelRequestErrorV1> {
        Ok(Self::SelectorBranch {
            selector: checked_name(selector)?,
            branch: checked_name(branch)?,
        })
    }

    pub fn model_name(&self) -> &str {
        match self {
            Self::Model(model) => model,
            Self::SelectorBranch { branch, .. } => branch,
        }
    }
}

/// Explicit PVT input carried by a selection.  The consumer preserves these
/// values but does not use them to choose an undeclared table column.
#[derive(Clone, Debug, PartialEq)]
pub struct CornerPvtV1 {
    corner: String,
    voltage_v: f64,
    temperature_c: f64,
}

impl CornerPvtV1 {
    pub fn try_new(
        corner: impl Into<String>,
        voltage_v: f64,
        temperature_c: f64,
    ) -> Result<Self, SelectedModelRequestErrorV1> {
        let corner = checked_name(corner)?;
        if !voltage_v.is_finite() {
            return Err(SelectedModelRequestErrorV1::NonFiniteVoltage);
        }
        if !temperature_c.is_finite() {
            return Err(SelectedModelRequestErrorV1::NonFiniteTemperature);
        }
        Ok(Self {
            corner,
            voltage_v,
            temperature_c,
        })
    }

    pub fn corner(&self) -> &str {
        &self.corner
    }

    pub const fn voltage_v(&self) -> f64 {
        self.voltage_v
    }

    pub const fn temperature_c(&self) -> f64 {
        self.temperature_c
    }
}

/// Known table families admitted by this scoped consumer.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum TableFamilyV1 {
    GndClamp,
    PowerClamp,
    Pulldown,
    Pullup,
    Ramp,
    RisingWaveform,
    FallingWaveform,
    CompositeCurrent,
    IssoPd,
    IssoPu,
}

impl TableFamilyV1 {
    pub const fn canonical_name(self) -> &'static str {
        match self {
            Self::GndClamp => "GND Clamp",
            Self::PowerClamp => "POWER Clamp",
            Self::Pulldown => "Pulldown",
            Self::Pullup => "Pullup",
            Self::Ramp => "Ramp",
            Self::RisingWaveform => "Rising Waveform",
            Self::FallingWaveform => "Falling Waveform",
            Self::CompositeCurrent => "Composite Current",
            Self::IssoPd => "ISSO_PD",
            Self::IssoPu => "ISSO_PU",
        }
    }

    fn from_keyword(spelling: &str) -> Option<Self> {
        let normalized = spelling
            .replace('_', " ")
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
            .to_ascii_lowercase();
        match normalized.as_str() {
            "gnd clamp" => Some(Self::GndClamp),
            "power clamp" => Some(Self::PowerClamp),
            "pulldown" => Some(Self::Pulldown),
            "pullup" => Some(Self::Pullup),
            "ramp" => Some(Self::Ramp),
            "rising waveform" => Some(Self::RisingWaveform),
            "falling waveform" => Some(Self::FallingWaveform),
            "composite current" => Some(Self::CompositeCurrent),
            "isso pd" => Some(Self::IssoPd),
            "isso pu" => Some(Self::IssoPu),
            _ => None,
        }
    }

    /// Parse a table family supplied by a caller.  Unknown family spellings
    /// are rejected instead of becoming an opaque fallback.
    pub fn parse(value: &str) -> Result<Self, SelectedModelRequestErrorV1> {
        Self::from_keyword(value.trim()).ok_or_else(|| {
            SelectedModelRequestErrorV1::UnsupportedTableFamily(value.trim().to_owned())
        })
    }
}

/// The complete caller-supplied selection grammar.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedModelRequestV1 {
    role: SignalPinRoleV1,
    target: SelectedModelTargetV1,
    corner_pvt: CornerPvtV1,
    table_family: TableFamilyV1,
}

impl SelectedModelRequestV1 {
    pub fn try_new(
        role: SignalPinRoleV1,
        target: SelectedModelTargetV1,
        corner_pvt: CornerPvtV1,
        table_family: TableFamilyV1,
    ) -> Result<Self, SelectedModelRequestErrorV1> {
        let role_name = checked_name(role.name())?;
        if role_name != role.name() {
            return Err(SelectedModelRequestErrorV1::InvalidName);
        }
        match &target {
            SelectedModelTargetV1::Model(model) => {
                let checked = checked_name(model)?;
                if checked != *model {
                    return Err(SelectedModelRequestErrorV1::InvalidName);
                }
            }
            SelectedModelTargetV1::SelectorBranch { selector, branch } => {
                let checked_selector = checked_name(selector)?;
                let checked_branch = checked_name(branch)?;
                if checked_selector != *selector || checked_branch != *branch {
                    return Err(SelectedModelRequestErrorV1::InvalidName);
                }
            }
        }
        Ok(Self {
            role,
            target,
            corner_pvt,
            table_family,
        })
    }

    pub fn role(&self) -> &SignalPinRoleV1 {
        &self.role
    }

    pub fn target(&self) -> &SelectedModelTargetV1 {
        &self.target
    }

    pub const fn corner_pvt(&self) -> &CornerPvtV1 {
        &self.corner_pvt
    }

    pub const fn table_family(&self) -> TableFamilyV1 {
        self.table_family
    }
}

/// Stable request-construction diagnostics.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SelectedModelRequestErrorV1 {
    EmptyName,
    NonAsciiName,
    InvalidName,
    NameTooLong { max_bytes: usize },
    NonFiniteVoltage,
    NonFiniteTemperature,
    UnsupportedTableFamily(String),
}

impl fmt::Display for SelectedModelRequestErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "selected IBIS model request: {self:?}")
    }
}

impl Error for SelectedModelRequestErrorV1 {}

/// Exact identity of the requested opaque table section.  Values are not
/// parsed or returned; only the bounded section/row identity is exposed.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequiredTableIdentityV1 {
    family: TableFamilyV1,
    model_name: String,
    row_count: usize,
    section_span: crate::SourceSpanV1,
}

impl RequiredTableIdentityV1 {
    pub const fn family(&self) -> TableFamilyV1 {
        self.family
    }

    pub fn model_name(&self) -> &str {
        &self.model_name
    }

    pub const fn row_count(&self) -> usize {
        self.row_count
    }

    pub const fn section_span(&self) -> crate::SourceSpanV1 {
        self.section_span
    }
}

/// Resolved target identity after checking the caller's target against the
/// complete inventory and the selected role's pin linkage.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResolvedModelTargetV1 {
    selector: Option<String>,
    branch: String,
}

impl ResolvedModelTargetV1 {
    pub fn selector(&self) -> Option<&str> {
        self.selector.as_deref()
    }

    pub fn branch(&self) -> &str {
        &self.branch
    }
}

/// Bounded result of one explicit selected-model request.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedModelSelectionV1 {
    role: SignalPinRoleV1,
    pin_name: String,
    signal_name: String,
    target: ResolvedModelTargetV1,
    corner_pvt: CornerPvtV1,
    table: RequiredTableIdentityV1,
    model_type: ModelTypeV1,
}

impl SelectedModelSelectionV1 {
    pub fn role(&self) -> &SignalPinRoleV1 {
        &self.role
    }

    pub fn pin_name(&self) -> &str {
        &self.pin_name
    }

    pub fn signal_name(&self) -> &str {
        &self.signal_name
    }

    pub const fn target(&self) -> &ResolvedModelTargetV1 {
        &self.target
    }

    pub const fn corner_pvt(&self) -> &CornerPvtV1 {
        &self.corner_pvt
    }

    pub const fn table(&self) -> &RequiredTableIdentityV1 {
        &self.table
    }

    pub const fn model_type(&self) -> &ModelTypeV1 {
        &self.model_type
    }
}

/// Fail-closed errors from the selected-model consumer.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SelectedModelConsumerErrorV1 {
    Inventory(IbisTypedInventoryErrorV1),
    Structural(IbisDiagnosticV1),
    Request(SelectedModelRequestErrorV1),
    RoleNotFound {
        kind: String,
        name: String,
    },
    RoleAmbiguous {
        kind: String,
        name: String,
        count: usize,
    },
    ModelNotFound {
        model: String,
    },
    SelectorNotFound {
        selector: String,
    },
    SelectorBranchNotFound {
        selector: String,
        branch: String,
    },
    SelectorBranchAmbiguous {
        selector: String,
        branch: String,
        count: usize,
    },
    TargetNotLinkedToRole {
        pin: String,
        reference: String,
        target: String,
    },
    ModelBlockMissing {
        model: String,
    },
    TableFamilyMissing {
        model: String,
        family: String,
    },
    TableFamilyAmbiguous {
        model: String,
        family: String,
        count: usize,
    },
    TableFamilyEmpty {
        model: String,
        family: String,
    },
    TableTooManyRows {
        model: String,
        family: String,
        count: usize,
    },
}

impl fmt::Display for SelectedModelConsumerErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Inventory(error) => write!(formatter, "selected model inventory: {error}"),
            Self::Structural(error) => error.fmt(formatter),
            Self::Request(error) => error.fmt(formatter),
            other => write!(formatter, "selected model rejected: {other:?}"),
        }
    }
}

impl Error for SelectedModelConsumerErrorV1 {}

/// Production in-memory consumer for a caller-owned selected-model profile.
pub struct SelectedModelConsumerV1;

impl SelectedModelConsumerV1 {
    /// Resolve only an explicit request against a complete typed document.
    ///
    /// The marker set remains caller-owned.  In particular, this function
    /// never treats a spelling such as `NC`, `GND`, or `POWER` as a model.
    pub fn select(
        bytes: &[u8],
        limits: ParseLimitsV1,
        allowed_markers: &std::collections::BTreeSet<String>,
        request: &SelectedModelRequestV1,
    ) -> Result<SelectedModelSelectionV1, SelectedModelConsumerErrorV1> {
        let inventory = IbisTypedInventoryServiceV1::inspect(bytes, limits, allowed_markers)
            .map_err(SelectedModelConsumerErrorV1::Inventory)?;
        let document =
            parse_structural_v1(bytes, limits).map_err(SelectedModelConsumerErrorV1::Structural)?;
        let envelope = build_semantic_envelope_v1(&document).map_err(|error| {
            SelectedModelConsumerErrorV1::Inventory(IbisTypedInventoryErrorV1::Semantic(error))
        })?;
        let (pin, target) = resolve_role_and_target(&inventory, request)?;
        let model = inventory
            .models()
            .iter()
            .find(|model| model.model_name() == target.branch)
            .ok_or_else(|| SelectedModelConsumerErrorV1::ModelNotFound {
                model: target.branch.clone(),
            })?;
        let (model_start, model_end) = model_block_bounds(envelope.records(), model.model_name())?;
        let table = locate_table(
            envelope.records(),
            model_start,
            model_end,
            model.model_name(),
            request.table_family,
        )?;

        Ok(SelectedModelSelectionV1 {
            role: request.role.clone(),
            pin_name: pin.pin_name().to_owned(),
            signal_name: pin.signal_name().to_owned(),
            target,
            corner_pvt: request.corner_pvt.clone(),
            table,
            model_type: model.model_type().clone(),
        })
    }
}

fn resolve_role_and_target<'a>(
    inventory: &'a IbisTypedInventoryReportV1,
    request: &SelectedModelRequestV1,
) -> Result<(&'a TypedPinDeclarationV1, ResolvedModelTargetV1), SelectedModelConsumerErrorV1> {
    let role = request.role();
    let candidates: Vec<&TypedPinDeclarationV1> = inventory
        .pins()
        .iter()
        .filter(|pin| match role {
            SignalPinRoleV1::Signal(name) => pin.signal_name() == name,
            SignalPinRoleV1::Pin(name) => pin.pin_name() == name,
        })
        .collect();
    if candidates.is_empty() {
        return Err(SelectedModelConsumerErrorV1::RoleNotFound {
            kind: role.kind().to_owned(),
            name: role.name().to_owned(),
        });
    }
    if candidates.len() != 1 {
        return Err(SelectedModelConsumerErrorV1::RoleAmbiguous {
            kind: role.kind().to_owned(),
            name: role.name().to_owned(),
            count: candidates.len(),
        });
    }
    let pin = candidates[0];

    let target = match request.target() {
        SelectedModelTargetV1::Model(model) => {
            if !inventory
                .models()
                .iter()
                .any(|declared| declared.model_name() == model)
            {
                return Err(SelectedModelConsumerErrorV1::ModelNotFound {
                    model: model.clone(),
                });
            }
            if pin.model_name() != model {
                return Err(SelectedModelConsumerErrorV1::TargetNotLinkedToRole {
                    pin: pin.pin_name().to_owned(),
                    reference: pin.model_name().to_owned(),
                    target: model.clone(),
                });
            }
            ResolvedModelTargetV1 {
                selector: None,
                branch: model.clone(),
            }
        }
        SelectedModelTargetV1::SelectorBranch { selector, branch } => {
            let selector_decl = inventory
                .selectors()
                .iter()
                .find(|candidate| candidate.selector_name() == selector)
                .ok_or_else(|| SelectedModelConsumerErrorV1::SelectorNotFound {
                    selector: selector.clone(),
                })?;
            let branches: Vec<&crate::ModelBranchV1> = selector_decl
                .branches()
                .iter()
                .filter(|candidate| candidate.model_name() == branch)
                .collect();
            if branches.is_empty() {
                return Err(SelectedModelConsumerErrorV1::SelectorBranchNotFound {
                    selector: selector.clone(),
                    branch: branch.clone(),
                });
            }
            if branches.len() != 1 {
                return Err(SelectedModelConsumerErrorV1::SelectorBranchAmbiguous {
                    selector: selector.clone(),
                    branch: branch.clone(),
                    count: branches.len(),
                });
            }
            if pin.model_name() != selector {
                return Err(SelectedModelConsumerErrorV1::TargetNotLinkedToRole {
                    pin: pin.pin_name().to_owned(),
                    reference: pin.model_name().to_owned(),
                    target: selector.clone(),
                });
            }
            ResolvedModelTargetV1 {
                selector: Some(selector.clone()),
                branch: branch.clone(),
            }
        }
    };
    Ok((pin, target))
}

fn model_block_bounds(
    records: &[StructuralRecordV1],
    model_name: &str,
) -> Result<(usize, usize), SelectedModelConsumerErrorV1> {
    let mut starts = records.iter().enumerate().filter_map(|(index, record)| {
        let StructuralRecordV1::Keyword {
            keyword, payload, ..
        } = record
        else {
            return None;
        };
        (keyword.spelling().eq_ignore_ascii_case("Model")
            && payload.len() == 1
            && payload[0].spelling() == model_name)
            .then_some(index)
    });
    let Some(start) = starts.next() else {
        return Err(SelectedModelConsumerErrorV1::ModelBlockMissing {
            model: model_name.to_owned(),
        });
    };
    if starts.next().is_some() {
        return Err(SelectedModelConsumerErrorV1::ModelBlockMissing {
            model: model_name.to_owned(),
        });
    }
    let end = records
        .iter()
        .enumerate()
        .skip(start + 1)
        .find_map(|(index, record)| match record {
            StructuralRecordV1::Keyword { keyword, .. }
                if keyword.spelling().eq_ignore_ascii_case("Model")
                    || keyword.spelling().eq_ignore_ascii_case("End") =>
            {
                Some(index)
            }
            _ => None,
        })
        .unwrap_or(records.len());
    Ok((start, end))
}

fn locate_table(
    records: &[StructuralRecordV1],
    model_start: usize,
    model_end: usize,
    model_name: &str,
    family: TableFamilyV1,
) -> Result<RequiredTableIdentityV1, SelectedModelConsumerErrorV1> {
    let mut matches = Vec::new();
    for index in (model_start + 1)..model_end {
        let StructuralRecordV1::Keyword { keyword, span, .. } = &records[index] else {
            continue;
        };
        if TableFamilyV1::from_keyword(keyword.spelling()) != Some(family) {
            continue;
        }
        let row_count = records
            .iter()
            .skip(index + 1)
            .take_while(|record| matches!(record, StructuralRecordV1::Data { .. }))
            .count();
        matches.push((*span, row_count));
    }
    if matches.is_empty() {
        return Err(SelectedModelConsumerErrorV1::TableFamilyMissing {
            model: model_name.to_owned(),
            family: family.canonical_name().to_owned(),
        });
    }
    if matches.len() != 1 {
        return Err(SelectedModelConsumerErrorV1::TableFamilyAmbiguous {
            model: model_name.to_owned(),
            family: family.canonical_name().to_owned(),
            count: matches.len(),
        });
    }
    let (section_span, row_count) = matches[0];
    if row_count == 0 {
        return Err(SelectedModelConsumerErrorV1::TableFamilyEmpty {
            model: model_name.to_owned(),
            family: family.canonical_name().to_owned(),
        });
    }
    if row_count > SELECTED_MODEL_MAX_TABLE_ROWS_V1 {
        return Err(SelectedModelConsumerErrorV1::TableTooManyRows {
            model: model_name.to_owned(),
            family: family.canonical_name().to_owned(),
            count: row_count,
        });
    }
    Ok(RequiredTableIdentityV1 {
        family,
        model_name: model_name.to_owned(),
        row_count,
        section_span,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(64 * 1024, 1024, 256, 1024).expect("limits")
    }

    fn markers() -> BTreeSet<String> {
        BTreeSet::new()
    }

    fn replace_bytes(source: &[u8], old: &[u8], new: &[u8]) -> Vec<u8> {
        let start = source
            .windows(old.len())
            .position(|window| window == old)
            .expect("old");
        let mut output = Vec::with_capacity(source.len() - old.len() + new.len());
        output.extend_from_slice(&source[..start]);
        output.extend_from_slice(new);
        output.extend_from_slice(&source[start + old.len()..]);
        output
    }

    fn source() -> &'static [u8] {
        br#"[IBIS Ver] 5.0
[Component] demo
[Pin] pin signal model R_pin L_pin C_pin
P1 SIG M_DIRECT
P2 SEL_SIG SEL
[Model Selector] SEL
M_BRANCH branch
M_OTHER other
[Model] M_DIRECT
Model_type Input
[GND Clamp]
0V 0A
1V 1A
[Model] M_BRANCH
Model_type Input
[Power Clamp]
0V 0A
1V 2A
[Model] M_OTHER
Model_type Output
[Pulldown]
0V 0A
1V 1A
[End]
"#
    }

    fn request_for_direct() -> SelectedModelRequestV1 {
        SelectedModelRequestV1::try_new(
            SignalPinRoleV1::signal("SIG").expect("role"),
            SelectedModelTargetV1::model("M_DIRECT").expect("target"),
            CornerPvtV1::try_new("typical", 1.2, 25.0).expect("pvt"),
            TableFamilyV1::GndClamp,
        )
        .expect("request")
    }

    #[test]
    fn resolves_explicit_direct_model_and_table_identity() {
        let selection =
            SelectedModelConsumerV1::select(source(), limits(), &markers(), &request_for_direct())
                .expect("selection");
        assert_eq!(selection.pin_name(), "P1");
        assert_eq!(selection.target().selector(), None);
        assert_eq!(selection.target().branch(), "M_DIRECT");
        assert_eq!(selection.table().family(), TableFamilyV1::GndClamp);
        assert_eq!(selection.table().row_count(), 2);
        assert_eq!(selection.corner_pvt().corner(), "typical");
    }

    #[test]
    fn resolves_explicit_selector_branch_without_position_fallback() {
        let request = SelectedModelRequestV1::try_new(
            SignalPinRoleV1::pin("P2").expect("role"),
            SelectedModelTargetV1::selector_branch("SEL", "M_BRANCH").expect("target"),
            CornerPvtV1::try_new("slow", 1.1, 85.0).expect("pvt"),
            TableFamilyV1::PowerClamp,
        )
        .expect("request");
        let selection = SelectedModelConsumerV1::select(source(), limits(), &markers(), &request)
            .expect("selection");
        assert_eq!(selection.target().selector(), Some("SEL"));
        assert_eq!(selection.target().branch(), "M_BRANCH");
        assert_eq!(selection.table().family(), TableFamilyV1::PowerClamp);
    }

    #[test]
    fn rejects_missing_explicit_profile_fields_at_construction() {
        assert_eq!(
            SignalPinRoleV1::signal(" "),
            Err(SelectedModelRequestErrorV1::EmptyName)
        );
        assert_eq!(
            CornerPvtV1::try_new("typical", f64::NAN, 25.0),
            Err(SelectedModelRequestErrorV1::NonFiniteVoltage)
        );
        assert_eq!(
            TableFamilyV1::parse("unknown"),
            Err(SelectedModelRequestErrorV1::UnsupportedTableFamily(
                "unknown".to_owned()
            ))
        );
    }

    #[test]
    fn rejects_ambiguous_role_and_duplicate_table() {
        let duplicate_role = replace_bytes(
            source(),
            b"P2 SEL_SIG SEL\n",
            b"P2 SEL_SIG SEL\nP3 SIG M_DIRECT\n",
        );
        assert!(matches!(
            SelectedModelConsumerV1::select(
                &duplicate_role,
                limits(),
                &markers(),
                &request_for_direct(),
            ),
            Err(SelectedModelConsumerErrorV1::RoleAmbiguous { .. })
        ));

        let duplicate_table = replace_bytes(
            source(),
            b"[GND Clamp]\n0V 0A\n1V 1A\n",
            b"[GND Clamp]\n0V 0A\n1V 1A\n[GND Clamp]\n0V 0A\n1V 1A\n",
        );
        assert!(matches!(
            SelectedModelConsumerV1::select(
                &duplicate_table,
                limits(),
                &markers(),
                &request_for_direct(),
            ),
            Err(SelectedModelConsumerErrorV1::TableFamilyAmbiguous { .. })
        ));
    }

    #[test]
    fn complete_document_gate_rejects_truncated_source() {
        let truncated = &source()[..source().len() - b"[End]\n".len()];
        assert!(matches!(
            SelectedModelConsumerV1::select(truncated, limits(), &markers(), &request_for_direct(),),
            Err(SelectedModelConsumerErrorV1::Inventory(
                IbisTypedInventoryErrorV1::MissingEnd
            ))
        ));
    }

    #[test]
    fn rejects_selector_branch_that_is_not_linked_to_role() {
        let request = SelectedModelRequestV1::try_new(
            SignalPinRoleV1::signal("SIG").expect("role"),
            SelectedModelTargetV1::selector_branch("SEL", "M_BRANCH").expect("target"),
            CornerPvtV1::try_new("typical", 1.2, 25.0).expect("pvt"),
            TableFamilyV1::PowerClamp,
        )
        .expect("request");
        assert!(matches!(
            SelectedModelConsumerV1::select(source(), limits(), &markers(), &request),
            Err(SelectedModelConsumerErrorV1::TargetNotLinkedToRole { .. })
        ));
    }
}
