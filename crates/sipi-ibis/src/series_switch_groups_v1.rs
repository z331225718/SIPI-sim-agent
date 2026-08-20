//! Typed IBIS [Series Switch Groups] declaration core (P4A-03k).
//!
//! Lifts and validates IBIS [Series Switch Groups] declarations
//! (group name, ON-state model list, OFF-state model list) into typed,
//! clean-room structures.
//! Fail-closed: empty group names, non-ASCII characters, invalid name spellings,
//! empty branch lists, or duplicate models within a state list are strictly rejected.

use std::collections::BTreeSet;

/// Scope policy for the typed series switch groups core.
pub const SERIES_SWITCH_GROUPS_POLICY_V1: &str =
    "sipi.p4a-03k.series-switch-groups-v1.typed-switch-groups";

/// Fail-closed errors during series switch group declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesSwitchGroupsErrorV1 {
    EmptyGroupName,
    NonAsciiGroupName,
    InvalidGroupName,
    EmptyStateModels,
    DuplicateModelInGroup(String),
}

/// A typed IBIS [Series Switch Groups] declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSeriesSwitchGroupV1 {
    group_name: String,
    on_state_models: Vec<String>,
    off_state_models: Vec<String>,
}

impl TypedSeriesSwitchGroupV1 {
    pub fn try_new(
        group_name: impl Into<String>,
        on_state_models: Vec<String>,
        off_state_models: Vec<String>,
    ) -> Result<Self, SeriesSwitchGroupsErrorV1> {
        let name = group_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(SeriesSwitchGroupsErrorV1::EmptyGroupName);
        }
        if !trimmed.is_ascii() {
            return Err(SeriesSwitchGroupsErrorV1::NonAsciiGroupName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesSwitchGroupsErrorV1::InvalidGroupName);
        }

        if on_state_models.is_empty() && off_state_models.is_empty() {
            return Err(SeriesSwitchGroupsErrorV1::EmptyStateModels);
        }

        let validate_models = |models: &[String]| -> Result<Vec<String>, SeriesSwitchGroupsErrorV1> {
            let mut seen = BTreeSet::new();
            let mut result = Vec::with_capacity(models.len());
            for m in models {
                let mt = m.trim().to_string();
                if mt.is_empty() {
                    return Err(SeriesSwitchGroupsErrorV1::EmptyGroupName);
                }
                if !mt.is_ascii() {
                    return Err(SeriesSwitchGroupsErrorV1::NonAsciiGroupName);
                }
                if !seen.insert(mt.clone()) {
                    return Err(SeriesSwitchGroupsErrorV1::DuplicateModelInGroup(mt));
                }
                result.push(mt);
            }
            Ok(result)
        };

        let on_clean = validate_models(&on_state_models)?;
        let off_clean = validate_models(&off_state_models)?;

        Ok(Self {
            group_name: trimmed.to_string(),
            on_state_models: on_clean,
            off_state_models: off_clean,
        })
    }

    pub fn group_name(&self) -> &str {
        &self.group_name
    }

    pub fn on_state_models(&self) -> &[String] {
        &self.on_state_models
    }

    pub fn off_state_models(&self) -> &[String] {
        &self.off_state_models
    }
}

/// Lift one series switch group declaration.
pub fn lift_series_switch_group_v1(
    group_name: &str,
    on_state_models: Vec<String>,
    off_state_models: Vec<String>,
) -> Result<TypedSeriesSwitchGroupV1, SeriesSwitchGroupsErrorV1> {
    TypedSeriesSwitchGroupV1::try_new(group_name, on_state_models, off_state_models)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_SWITCH_GROUPS_POLICY_V1,
            "sipi.p4a-03k.series-switch-groups-v1.typed-switch-groups"
        );
    }

    #[test]
    fn valid_full_switch_group() {
        let group = lift_series_switch_group_v1(
            "GROUP_1",
            vec!["R_ON_50".to_string(), "C_ON_1P".to_string()],
            vec!["R_OFF_10K".to_string()],
        )
        .expect("lift");
        assert_eq!(group.group_name(), "GROUP_1");
        assert_eq!(group.on_state_models(), &["R_ON_50", "C_ON_1P"]);
        assert_eq!(group.off_state_models(), &["R_OFF_10K"]);
    }

    #[test]
    fn valid_on_only_switch_group() {
        let group = lift_series_switch_group_v1("GROUP_ON", vec!["SW_ON".to_string()], vec![])
            .expect("lift");
        assert_eq!(group.group_name(), "GROUP_ON");
        assert_eq!(group.on_state_models(), &["SW_ON"]);
        assert!(group.off_state_models().is_empty());
    }

    #[test]
    fn rejects_empty_group_name() {
        assert_eq!(
            lift_series_switch_group_v1("", vec!["SW_ON".to_string()], vec![]),
            Err(SeriesSwitchGroupsErrorV1::EmptyGroupName)
        );
    }

    #[test]
    fn rejects_empty_state_models() {
        assert_eq!(
            lift_series_switch_group_v1("GROUP_EMPTY", vec![], vec![]),
            Err(SeriesSwitchGroupsErrorV1::EmptyStateModels)
        );
    }

    #[test]
    fn rejects_duplicate_model_in_group() {
        assert_eq!(
            lift_series_switch_group_v1(
                "GROUP_DUP",
                vec!["SW_ON".to_string(), "SW_ON".to_string()],
                vec![]
            ),
            Err(SeriesSwitchGroupsErrorV1::DuplicateModelInGroup(
                "SW_ON".to_string()
            ))
        );
    }
}
