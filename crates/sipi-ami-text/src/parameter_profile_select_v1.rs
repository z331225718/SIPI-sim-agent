//! AMI parameter profile selection core (P4B-02b64).
//!
//! Selects a sub-profile from an assembled parameter map (leaf name ->
//! `AmiParameterValueV1`, e.g. produced by P4B-02b44) by a caller-supplied
//! name set, the profile consumption step (pick which parameters to pass on).
//! Fail-closed: an empty selection and any requested name absent from the map
//! are strictly rejected.

use std::collections::{BTreeMap, BTreeSet};

use crate::AmiParameterValueV1;

/// Scope policy for the parameter profile selection core.
pub const PARAMETER_PROFILE_SELECTION_POLICY_V1: &str =
    "sipi.p4b-02b64.parameter-profile-select-v1.name-set-selection";

/// Fail-closed errors during profile selection.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterProfileSelectionErrorV1 {
    /// The selection name set is empty.
    EmptySelection,
    /// A requested name is absent from the profile.
    MissingParameter(String),
}

/// Outcome of a successful profile selection pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileSelectionV1 {
    selected: BTreeMap<String, AmiParameterValueV1>,
}

impl ParameterProfileSelectionV1 {
    pub fn selected(&self) -> &BTreeMap<String, AmiParameterValueV1> {
        &self.selected
    }

    pub fn selected_count(&self) -> usize {
        self.selected.len()
    }
}

/// Select the parameters of `parameters` named in `select`.
///
/// Returns the selected sub-profile (byte-wise name order). Fails closed on an
/// empty selection or any requested name absent from the map.
pub fn select_parameter_profile_v1(
    parameters: &BTreeMap<String, AmiParameterValueV1>,
    select: &BTreeSet<String>,
) -> Result<ParameterProfileSelectionV1, ParameterProfileSelectionErrorV1> {
    if select.is_empty() {
        return Err(ParameterProfileSelectionErrorV1::EmptySelection);
    }
    let mut selected = BTreeMap::new();
    for name in select {
        let parameter = parameters
            .get(name)
            .ok_or_else(|| ParameterProfileSelectionErrorV1::MissingParameter(name.clone()))?;
        selected.insert(name.clone(), parameter.clone());
    }
    Ok(ParameterProfileSelectionV1 { selected })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parameter(name: &str, type_token: &str, value: &str) -> AmiParameterValueV1 {
        AmiParameterValueV1::try_new(name, type_token, value).expect("valid parameter")
    }

    fn profile(pairs: &[(&str, &str, &str)]) -> BTreeMap<String, AmiParameterValueV1> {
        pairs
            .iter()
            .map(|(name, type_token, value)| {
                (
                    name.to_string(),
                    parameter(name, type_token, value),
                )
            })
            .collect()
    }

    fn select_of(names: &[&str]) -> BTreeSet<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn selects_requested_subset() {
        let parameters = profile(&[
            ("gain", "Float", "0.5"),
            ("steps", "Integer", "7"),
        ]);
        let result = select_parameter_profile_v1(&parameters, &select_of(&["gain"]))
            .expect("selected");
        assert_eq!(result.selected_count(), 1);
        assert!(result.selected().contains_key("gain"));
        assert!(!result.selected().contains_key("steps"));
    }

    #[test]
    fn selecting_all_returns_identical_map() {
        let parameters = profile(&[
            ("gain", "Float", "0.5"),
            ("steps", "Integer", "7"),
        ]);
        let result = select_parameter_profile_v1(
            &parameters,
            &select_of(&["gain", "steps"]),
        )
        .expect("selected");
        assert_eq!(result.selected(), &parameters);
    }

    #[test]
    fn empty_selection_fails_closed() {
        let parameters = profile(&[("gain", "Float", "0.5")]);
        let error = select_parameter_profile_v1(&parameters, &select_of(&[])).unwrap_err();
        assert_eq!(error, ParameterProfileSelectionErrorV1::EmptySelection);
    }

    #[test]
    fn missing_parameter_fails_closed() {
        let parameters = profile(&[("gain", "Float", "0.5")]);
        let error =
            select_parameter_profile_v1(&parameters, &select_of(&["nope"])).unwrap_err();
        assert_eq!(
            error,
            ParameterProfileSelectionErrorV1::MissingParameter("nope".to_string())
        );
    }
}
