//! AMI parameter profile completeness check core (P4B-02b55).
//!
//! Checks an assembled parameter map (leaf name -> `AmiParameterValueV1`, e.g.
//! produced by P4B-02b44) against a caller-supplied required-name set and
//! reports which required names are missing. This is the name-presence
//! complement of profile assembly: assembly does not know the required set, and
//! the catalog layer (P4B-02b3) does Usage=In checking at the catalog level —
//! this slice is the lighter required-name check on the assembled profile.
//! The check reports in the result; an incomplete profile is not itself an
//! error. Fail-closed: an empty required-name set is strictly rejected.

use std::collections::{BTreeMap, BTreeSet};

use crate::AmiParameterValueV1;

/// Scope policy for the parameter profile completeness check core.
pub const PARAMETER_PROFILE_COMPLETENESS_POLICY_V1: &str =
    "sipi.p4b-02b55.parameter-profile-completeness-check-v1.required-name-check";

/// Fail-closed errors during the completeness check.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParameterProfileCompletenessErrorV1 {
    /// The required-name set is empty; a completeness check against nothing is
    /// a caller error.
    EmptyRequired,
}

/// Outcome of a completeness check pass.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ParameterProfileCompletenessV1 {
    /// Number of required names.
    expected: usize,
    /// Number of required names present in the profile.
    present: usize,
    /// Required names missing from the profile (sorted).
    missing: Vec<String>,
    /// True when every required name is present.
    complete: bool,
}

impl ParameterProfileCompletenessV1 {
    pub fn expected(&self) -> usize {
        self.expected
    }

    pub fn present(&self) -> usize {
        self.present
    }

    pub fn missing(&self) -> &[String] {
        &self.missing
    }

    pub fn is_complete(&self) -> bool {
        self.complete
    }
}

/// Check `parameters` against `required`.
///
/// Returns expected/present counts plus the sorted missing names and a
/// completeness flag. Extra parameters not in the required set are ignored.
/// Fails closed on an empty required-name set.
pub fn check_parameter_profile_completeness_v1(
    parameters: &BTreeMap<String, AmiParameterValueV1>,
    required: &BTreeSet<String>,
) -> Result<ParameterProfileCompletenessV1, ParameterProfileCompletenessErrorV1> {
    if required.is_empty() {
        return Err(ParameterProfileCompletenessErrorV1::EmptyRequired);
    }
    let mut present = 0usize;
    let mut missing = Vec::new();
    for name in required {
        if parameters.contains_key(name) {
            present += 1;
        } else {
            missing.push(name.clone());
        }
    }
    let complete = missing.is_empty();
    Ok(ParameterProfileCompletenessV1 {
        expected: required.len(),
        present,
        missing,
        complete,
    })
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
            .map(|(name, type_token, value)| (name.to_string(), parameter(name, type_token, value)))
            .collect()
    }

    fn required_of(names: &[&str]) -> BTreeSet<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn complete_profile_is_reported() {
        let parameters = profile(&[("gain", "Float", "0.5"), ("steps", "Integer", "7")]);
        let result =
            check_parameter_profile_completeness_v1(&parameters, &required_of(&["gain", "steps"]))
                .expect("checked");
        assert_eq!(result.expected(), 2);
        assert_eq!(result.present(), 2);
        assert!(result.missing().is_empty());
        assert!(result.is_complete());
    }

    #[test]
    fn missing_required_names_are_reported_sorted() {
        let parameters = profile(&[("gain", "Float", "0.5")]);
        let result = check_parameter_profile_completeness_v1(
            &parameters,
            &required_of(&["mode", "gain", "steps"]),
        )
        .expect("checked");
        assert_eq!(result.expected(), 3);
        assert_eq!(result.present(), 1);
        assert_eq!(result.missing(), &["mode".to_string(), "steps".to_string()]);
        assert!(!result.is_complete());
    }

    #[test]
    fn extra_parameters_are_ignored() {
        let parameters = profile(&[("gain", "Float", "0.5"), ("extra", "Integer", "1")]);
        let result = check_parameter_profile_completeness_v1(&parameters, &required_of(&["gain"]))
            .expect("checked");
        assert_eq!(result.expected(), 1);
        assert_eq!(result.present(), 1);
        assert!(result.is_complete());
    }

    #[test]
    fn empty_required_fails_closed() {
        let parameters = profile(&[("gain", "Float", "0.5")]);
        let error =
            check_parameter_profile_completeness_v1(&parameters, &required_of(&[])).unwrap_err();
        assert_eq!(error, ParameterProfileCompletenessErrorV1::EmptyRequired);
    }
}
