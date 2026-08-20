//! Typed IBIS [Series Switch Groups] mapping table core (P4A-03p).
//!
//! Lifts and validates IBIS [Series Switch Groups] standalone table records
//! (on_group_name, off_group_name) into typed, clean-room structures.
//! Fail-closed: empty group names, non-ASCII characters, or identical ON/OFF groups
//! are strictly rejected.

/// Scope policy for the typed series switch groups mapping table core.
pub const SERIES_SWITCH_MAPPING_TABLE_POLICY_V1: &str =
    "sipi.p4a-03p.series-switch-mapping-v1.typed-table";

/// Fail-closed errors during series switch mapping lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesSwitchMappingTableErrorV1 {
    EmptyGroupName,
    NonAsciiName,
    InvalidName,
    IdenticalGroups,
}

/// A typed IBIS [Series Switch Groups] mapping table record.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSeriesSwitchRecordV1 {
    on_group_name: String,
    off_group_name: String,
}

impl TypedSeriesSwitchRecordV1 {
    pub fn try_new(
        on_group_name: impl Into<String>,
        off_group_name: impl Into<String>,
    ) -> Result<Self, SeriesSwitchMappingTableErrorV1> {
        let on_g = on_group_name.into().trim().to_string();
        let off_g = off_group_name.into().trim().to_string();

        if on_g.is_empty() || off_g.is_empty() {
            return Err(SeriesSwitchMappingTableErrorV1::EmptyGroupName);
        }
        if !on_g.is_ascii() || !off_g.is_ascii() {
            return Err(SeriesSwitchMappingTableErrorV1::NonAsciiName);
        }
        if !on_g
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !off_g
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesSwitchMappingTableErrorV1::InvalidName);
        }
        if on_g == off_g {
            return Err(SeriesSwitchMappingTableErrorV1::IdenticalGroups);
        }

        Ok(Self {
            on_group_name: on_g,
            off_group_name: off_g,
        })
    }

    pub fn on_group_name(&self) -> &str {
        &self.on_group_name
    }

    pub fn off_group_name(&self) -> &str {
        &self.off_group_name
    }
}

/// Lift one series switch mapping record.
pub fn lift_series_switch_record_v1(
    on_group_name: &str,
    off_group_name: &str,
) -> Result<TypedSeriesSwitchRecordV1, SeriesSwitchMappingTableErrorV1> {
    TypedSeriesSwitchRecordV1::try_new(on_group_name, off_group_name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_SWITCH_MAPPING_TABLE_POLICY_V1,
            "sipi.p4a-03p.series-switch-mapping-v1.typed-table"
        );
    }

    #[test]
    fn valid_record() {
        let rec = lift_series_switch_record_v1("GROUP_ON_1", "GROUP_OFF_1").expect("lift");
        assert_eq!(rec.on_group_name(), "GROUP_ON_1");
        assert_eq!(rec.off_group_name(), "GROUP_OFF_1");
    }

    #[test]
    fn rejects_empty_group_name() {
        assert_eq!(
            lift_series_switch_record_v1("", "GROUP_OFF_1"),
            Err(SeriesSwitchMappingTableErrorV1::EmptyGroupName)
        );
    }

    #[test]
    fn rejects_identical_groups() {
        assert_eq!(
            lift_series_switch_record_v1("GROUP_1", "GROUP_1"),
            Err(SeriesSwitchMappingTableErrorV1::IdenticalGroups)
        );
    }

    #[test]
    fn rejects_non_ascii_name() {
        assert_eq!(
            lift_series_switch_record_v1("组_ON", "GROUP_OFF"),
            Err(SeriesSwitchMappingTableErrorV1::NonAsciiName)
        );
    }
}
