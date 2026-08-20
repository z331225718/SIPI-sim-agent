//! Typed IBIS [Series Pin Mapping] group association core (P4A-03v).
//!
//! Lifts and validates IBIS [Series Pin Mapping] series group declarations
//! (group name, series pin pair lists) into typed clean-room structures.
//! Fail-closed: empty group names, non-ASCII characters, invalid name spellings,
//! empty pin pair lists, or duplicate pin pairs within a group are strictly rejected.

use std::collections::BTreeSet;

/// Scope policy for the typed series pin group core.
pub const SERIES_PIN_MAPPING_GROUP_POLICY_V1: &str =
    "sipi.p4a-03v.series-pin-mapping-group-v1.typed-group";

/// Fail-closed errors during series pin group declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinMappingGroupErrorV1 {
    EmptyGroupName,
    NonAsciiName,
    InvalidName,
    EmptyPinPairs,
    DuplicatePinPair(String, String),
    IdenticalPinPair(String),
}

/// One series pin pair inside a group declaration.
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub struct SeriesPinPairV1 {
    pin_first: String,
    pin_second: String,
}

impl SeriesPinPairV1 {
    pub fn try_new(
        pin_first: impl Into<String>,
        pin_second: impl Into<String>,
    ) -> Result<Self, SeriesPinMappingGroupErrorV1> {
        let pf = pin_first.into().trim().to_string();
        let ps = pin_second.into().trim().to_string();

        if pf.is_empty() || ps.is_empty() {
            return Err(SeriesPinMappingGroupErrorV1::EmptyGroupName);
        }
        if !pf.is_ascii() || !ps.is_ascii() {
            return Err(SeriesPinMappingGroupErrorV1::NonAsciiName);
        }
        if !pf.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ps.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinMappingGroupErrorV1::InvalidName);
        }
        if pf == ps {
            return Err(SeriesPinMappingGroupErrorV1::IdenticalPinPair(pf));
        }

        Ok(Self {
            pin_first: pf,
            pin_second: ps,
        })
    }

    pub fn pin_first(&self) -> &str {
        &self.pin_first
    }

    pub fn pin_second(&self) -> &str {
        &self.pin_second
    }
}

/// A typed IBIS [Series Pin Mapping] group declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSeriesPinGroupV1 {
    group_name: String,
    pin_pairs: Vec<SeriesPinPairV1>,
}

impl TypedSeriesPinGroupV1 {
    pub fn try_new(
        group_name: impl Into<String>,
        pin_pairs: Vec<SeriesPinPairV1>,
    ) -> Result<Self, SeriesPinMappingGroupErrorV1> {
        let name = group_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(SeriesPinMappingGroupErrorV1::EmptyGroupName);
        }
        if !trimmed.is_ascii() {
            return Err(SeriesPinMappingGroupErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinMappingGroupErrorV1::InvalidName);
        }

        if pin_pairs.is_empty() {
            return Err(SeriesPinMappingGroupErrorV1::EmptyPinPairs);
        }

        let mut seen = BTreeSet::new();
        for pair in &pin_pairs {
            if !seen.insert(pair.clone()) {
                return Err(SeriesPinMappingGroupErrorV1::DuplicatePinPair(
                    pair.pin_first().to_string(),
                    pair.pin_second().to_string(),
                ));
            }
        }

        Ok(Self {
            group_name: trimmed.to_string(),
            pin_pairs,
        })
    }

    pub fn group_name(&self) -> &str {
        &self.group_name
    }

    pub fn pin_pairs(&self) -> &[SeriesPinPairV1] {
        &self.pin_pairs
    }
}

/// Lift one series pin group declaration.
pub fn lift_series_pin_group_v1(
    group_name: &str,
    pin_pairs: Vec<SeriesPinPairV1>,
) -> Result<TypedSeriesPinGroupV1, SeriesPinMappingGroupErrorV1> {
    TypedSeriesPinGroupV1::try_new(group_name, pin_pairs)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_PIN_MAPPING_GROUP_POLICY_V1,
            "sipi.p4a-03v.series-pin-mapping-group-v1.typed-group"
        );
    }

    #[test]
    fn valid_group_declaration() {
        let p1 = SeriesPinPairV1::try_new("P1", "P2").unwrap();
        let p2 = SeriesPinPairV1::try_new("P3", "P4").unwrap();
        let group = lift_series_pin_group_v1("SERIES_GRP1", vec![p1, p2]).expect("lift");
        assert_eq!(group.group_name(), "SERIES_GRP1");
        assert_eq!(group.pin_pairs().len(), 2);
    }

    #[test]
    fn rejects_empty_group_name() {
        let p1 = SeriesPinPairV1::try_new("P1", "P2").unwrap();
        assert_eq!(
            lift_series_pin_group_v1("", vec![p1]),
            Err(SeriesPinMappingGroupErrorV1::EmptyGroupName)
        );
    }

    #[test]
    fn rejects_empty_pin_pairs() {
        assert_eq!(
            lift_series_pin_group_v1("GRP1", vec![]),
            Err(SeriesPinMappingGroupErrorV1::EmptyPinPairs)
        );
    }

    #[test]
    fn rejects_duplicate_pin_pair() {
        let p1 = SeriesPinPairV1::try_new("P1", "P2").unwrap();
        let p2 = SeriesPinPairV1::try_new("P1", "P2").unwrap();
        assert_eq!(
            lift_series_pin_group_v1("GRP1", vec![p1, p2]),
            Err(SeriesPinMappingGroupErrorV1::DuplicatePinPair(
                "P1".to_string(),
                "P2".to_string()
            ))
        );
    }
}
