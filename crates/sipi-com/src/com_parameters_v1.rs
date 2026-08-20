//! COM typed parameter DTO merge core (P5-05e).
//!
//! Combines the workbook parameter surface report (P5-05d) with the
//! resolved default values (P5-02j/k) into a typed COM parameter DTO:
//! for each consumed key the resolved value is chosen as the workbook
//! value if present, otherwise the resolved default; a consumed key
//! with neither is a hard error. Unconsumed workbook keys are retained
//! (nothing is dropped), consistent with the P5-05 scope.

use std::collections::BTreeMap;

use crate::value_consumption_v1::ResolvedDefaultV1;

/// Stable scope policy of the P5-05e COM parameter DTO core.
pub const COM_PARAMETERS_POLICY_V1: &str = "sipi.p5-05e.com-parameters-v1.typed-dto";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ComParametersErrorV1 {
    EmptyConsumed,
    MissingValue(String),
    DuplicateKey(String),
}

/// The merged typed COM parameter DTO.
#[derive(Clone, Debug, PartialEq)]
pub struct ComParametersV1 {
    consumed: BTreeMap<String, ResolvedDefaultV1>,
    unconsumed: Vec<String>,
}

impl ComParametersV1 {
    pub fn consumed(&self) -> &BTreeMap<String, ResolvedDefaultV1> {
        &self.consumed
    }

    pub fn unconsumed(&self) -> &[String] {
        &self.unconsumed
    }

    pub fn consumed_keys(&self) -> Vec<String> {
        self.consumed.keys().cloned().collect()
    }
}

/// Merges a consumed-key set with per-key workbook values and resolved
/// defaults into a typed DTO.
///
/// `consumed_keys` is the canonical consumption key set (unique, ordered).
/// `workbook_values` supplies workbook-provided values for consumed keys;
/// `resolved_defaults` supplies the resolved default when no workbook value
/// is present. Unconsumed keys (from the workbook surface) are given via
/// `unconsumed_keys` and retained verbatim.
pub fn merge_com_parameters_v1(
    consumed_keys: &[String],
    workbook_values: &BTreeMap<String, ResolvedDefaultV1>,
    resolved_defaults: &BTreeMap<String, ResolvedDefaultV1>,
    unconsumed_keys: &[String],
) -> Result<ComParametersV1, ComParametersErrorV1> {
    if consumed_keys.is_empty() {
        return Err(ComParametersErrorV1::EmptyConsumed);
    }
    let mut consumed = BTreeMap::new();
    for key in consumed_keys {
        // Workbook value wins, else resolved default, else error.
        let value = if let Some(v) = workbook_values.get(key) {
            Some(v.clone())
        } else if let Some(v) = resolved_defaults.get(key) {
            Some(v.clone())
        } else {
            return Err(ComParametersErrorV1::MissingValue(key.clone()));
        };
        if let Some(v) = value {
            if consumed.insert(key.clone(), v).is_some() {
                return Err(ComParametersErrorV1::DuplicateKey(key.clone()));
            }
        }
    }
    let unconsumed = unconsumed_keys.to_vec();
    Ok(ComParametersV1 { consumed, unconsumed })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(COM_PARAMETERS_POLICY_V1, "sipi.p5-05e.com-parameters-v1.typed-dto");
    }

    #[test]
    fn workbook_value_wins_over_default() {
        let mut wb = BTreeMap::new();
        wb.insert("fb".to_string(), ResolvedDefaultV1::Scalar(53.125e9));
        let keys = vec!["fb".to_string()];
        let dto = merge_com_parameters_v1(&keys, &wb, &BTreeMap::new(), &[]).expect("merge");
        assert_eq!(dto.consumed().get("fb"), Some(&ResolvedDefaultV1::Scalar(53.125e9)));
    }

    #[test]
    fn default_used_when_no_workbook_value() {
        let mut def = BTreeMap::new();
        def.insert("a_fext".to_string(), ResolvedDefaultV1::Scalar(0.5));
        let keys = vec!["a_fext".to_string()];
        let dto = merge_com_parameters_v1(&keys, &BTreeMap::new(), &def, &[]).expect("merge");
        assert_eq!(dto.consumed().get("a_fext"), Some(&ResolvedDefaultV1::Scalar(0.5)));
    }

    #[test]
    fn missing_value_rejected() {
        let keys = vec!["fb".to_string()];
        let err = merge_com_parameters_v1(&keys, &BTreeMap::new(), &BTreeMap::new(), &[]).err().expect("err");
        assert_eq!(err, ComParametersErrorV1::MissingValue("fb".to_string()));
    }

    #[test]
    fn unconsumed_retained() {
        let keys = vec!["fb".to_string()];
        let mut def = BTreeMap::new();
        def.insert("fb".to_string(), ResolvedDefaultV1::Scalar(53.125e9));
        let dto = merge_com_parameters_v1(&keys, &BTreeMap::new(), &def, &["extraneous".to_string()]).expect("merge");
        assert_eq!(dto.unconsumed(), &["extraneous".to_string()]);
    }

    #[test]
    fn empty_consumed_rejected() {
        let err = merge_com_parameters_v1(&[], &BTreeMap::new(), &BTreeMap::new(), &[]).err().expect("err");
        assert_eq!(err, ComParametersErrorV1::EmptyConsumed);
    }

    #[test]
    fn duplicate_key_rejected() {
        let keys = vec!["fb".to_string(), "fb".to_string()];
        let mut def = BTreeMap::new();
        def.insert("fb".to_string(), ResolvedDefaultV1::Scalar(1.0));
        let err = merge_com_parameters_v1(&keys, &BTreeMap::new(), &def, &[]).err().expect("err");
        assert!(matches!(err, ComParametersErrorV1::DuplicateKey(_)));
    }
}