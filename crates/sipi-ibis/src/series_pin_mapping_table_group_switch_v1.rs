//! Typed IBIS [Series Pin Mapping] group switch association core (P4A-03bb).
//!
//! Lifts and validates IBIS [Series Pin Mapping] group switch association records
//! (group_name, on_group_name, off_group_name, function_table_group) into typed clean-room structures.
//! Fail-closed: empty group names, non-ASCII characters, identical ON/OFF groups,
//! or invalid name spellings are strictly rejected.

/// Scope policy for the typed series pin table group switch core.
pub const SERIES_PIN_TABLE_GROUP_SWITCH_POLICY_V1: &str =
    "sipi.p4a-03bb.series-pin-table-group-switch-v1.typed-group-switch";

/// Fail-closed errors during series pin table group switch lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinTableGroupSwitchErrorV1 {
    EmptyGroupName,
    EmptyStateGroupName,
    NonAsciiName,
    InvalidName,
    IdenticalStateGroups,
}

/// A typed IBIS [Series Pin Mapping] group switch association record.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSeriesPinGroupSwitchRecordV1 {
    group_name: String,
    on_group_name: String,
    off_group_name: String,
    function_table_group: Option<String>,
}

impl TypedSeriesPinGroupSwitchRecordV1 {
    pub fn try_new(
        group_name: impl Into<String>,
        on_group_name: impl Into<String>,
        off_group_name: impl Into<String>,
        function_table_group: Option<impl Into<String>>,
    ) -> Result<Self, SeriesPinTableGroupSwitchErrorV1> {
        let gn = group_name.into().trim().to_string();
        let on_g = on_group_name.into().trim().to_string();
        let off_g = off_group_name.into().trim().to_string();

        if gn.is_empty() {
            return Err(SeriesPinTableGroupSwitchErrorV1::EmptyGroupName);
        }
        if on_g.is_empty() || off_g.is_empty() {
            return Err(SeriesPinTableGroupSwitchErrorV1::EmptyStateGroupName);
        }
        if !gn.is_ascii() || !on_g.is_ascii() || !off_g.is_ascii() {
            return Err(SeriesPinTableGroupSwitchErrorV1::NonAsciiName);
        }
        if !gn
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !on_g
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !off_g
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinTableGroupSwitchErrorV1::InvalidName);
        }
        if on_g == off_g {
            return Err(SeriesPinTableGroupSwitchErrorV1::IdenticalStateGroups);
        }

        let ftg = function_table_group.and_then(|g| {
            let t = g.into().trim().to_string();
            if t.is_empty() { None } else { Some(t) }
        });

        if let Some(ref g) = ftg
            && !g.is_ascii()
        {
            return Err(SeriesPinTableGroupSwitchErrorV1::NonAsciiName);
        }

        Ok(Self {
            group_name: gn,
            on_group_name: on_g,
            off_group_name: off_g,
            function_table_group: ftg,
        })
    }

    pub fn group_name(&self) -> &str {
        &self.group_name
    }

    pub fn on_group_name(&self) -> &str {
        &self.on_group_name
    }

    pub fn off_group_name(&self) -> &str {
        &self.off_group_name
    }

    pub fn function_table_group(&self) -> Option<&str> {
        self.function_table_group.as_deref()
    }
}

/// Lift one series pin group switch association record.
pub fn lift_series_pin_group_switch_record_v1(
    group_name: &str,
    on_group_name: &str,
    off_group_name: &str,
    function_table_group: Option<&str>,
) -> Result<TypedSeriesPinGroupSwitchRecordV1, SeriesPinTableGroupSwitchErrorV1> {
    TypedSeriesPinGroupSwitchRecordV1::try_new(
        group_name,
        on_group_name,
        off_group_name,
        function_table_group,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_PIN_TABLE_GROUP_SWITCH_POLICY_V1,
            "sipi.p4a-03bb.series-pin-table-group-switch-v1.typed-group-switch"
        );
    }

    #[test]
    fn valid_full_group_switch_record() {
        let rec = lift_series_pin_group_switch_record_v1(
            "SERIES_GRP1",
            "GROUP_ON_1",
            "GROUP_OFF_1",
            Some("GRP1"),
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.on_group_name(), "GROUP_ON_1");
        assert_eq!(rec.off_group_name(), "GROUP_OFF_1");
        assert_eq!(rec.function_table_group(), Some("GRP1"));
    }

    #[test]
    fn valid_minimal_group_switch_record() {
        let rec = lift_series_pin_group_switch_record_v1(
            "SERIES_GRP1",
            "GROUP_ON_1",
            "GROUP_OFF_1",
            None,
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.on_group_name(), "GROUP_ON_1");
        assert_eq!(rec.off_group_name(), "GROUP_OFF_1");
        assert_eq!(rec.function_table_group(), None);
    }

    #[test]
    fn rejects_empty_group_name() {
        assert_eq!(
            lift_series_pin_group_switch_record_v1("", "GROUP_ON_1", "GROUP_OFF_1", None),
            Err(SeriesPinTableGroupSwitchErrorV1::EmptyGroupName)
        );
    }

    #[test]
    fn rejects_identical_state_groups() {
        assert_eq!(
            lift_series_pin_group_switch_record_v1("SERIES_GRP1", "GROUP_1", "GROUP_1", None),
            Err(SeriesPinTableGroupSwitchErrorV1::IdenticalStateGroups)
        );
    }
}
