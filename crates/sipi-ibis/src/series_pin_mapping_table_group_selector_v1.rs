//! Typed IBIS [Series Pin Mapping] group Model Selector binding record core (P4A-03as).
//!
//! Lifts and validates IBIS [Series Pin Mapping] group Model Selector binding records
//! (group_name, model_selector_name, function_table_group) into typed clean-room structures.
//! Fail-closed: empty group or selector names, non-ASCII characters,
//! or invalid name spellings are strictly rejected.

/// Scope policy for the typed series pin table group selector core.
pub const SERIES_PIN_TABLE_GROUP_SELECTOR_POLICY_V1: &str =
    "sipi.p4a-03as.series-pin-table-group-selector-v1.typed-table-group-selector";

/// Fail-closed errors during series pin table group selector lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinTableGroupSelectorErrorV1 {
    EmptyGroupName,
    EmptySelectorName,
    NonAsciiName,
    InvalidName,
}

/// A typed IBIS [Series Pin Mapping] group Model Selector binding record.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSeriesPinGroupSelectorRecordV1 {
    group_name: String,
    model_selector_name: String,
    function_table_group: Option<String>,
}

impl TypedSeriesPinGroupSelectorRecordV1 {
    pub fn try_new(
        group_name: impl Into<String>,
        model_selector_name: impl Into<String>,
        function_table_group: Option<impl Into<String>>,
    ) -> Result<Self, SeriesPinTableGroupSelectorErrorV1> {
        let gn = group_name.into().trim().to_string();
        let ms = model_selector_name.into().trim().to_string();

        if gn.is_empty() {
            return Err(SeriesPinTableGroupSelectorErrorV1::EmptyGroupName);
        }
        if ms.is_empty() {
            return Err(SeriesPinTableGroupSelectorErrorV1::EmptySelectorName);
        }
        if !gn.is_ascii() || !ms.is_ascii() {
            return Err(SeriesPinTableGroupSelectorErrorV1::NonAsciiName);
        }
        if !gn.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ms.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinTableGroupSelectorErrorV1::InvalidName);
        }

        let ftg = function_table_group.and_then(|g| {
            let t = g.into().trim().to_string();
            if t.is_empty() {
                None
            } else {
                Some(t)
            }
        });

        if let Some(ref g) = ftg {
            if !g.is_ascii() {
                return Err(SeriesPinTableGroupSelectorErrorV1::NonAsciiName);
            }
        }

        Ok(Self {
            group_name: gn,
            model_selector_name: ms,
            function_table_group: ftg,
        })
    }

    pub fn group_name(&self) -> &str {
        &self.group_name
    }

    pub fn model_selector_name(&self) -> &str {
        &self.model_selector_name
    }

    pub fn function_table_group(&self) -> Option<&str> {
        self.function_table_group.as_deref()
    }
}

/// Lift one series pin group selector binding record.
pub fn lift_series_pin_group_selector_record_v1(
    group_name: &str,
    model_selector_name: &str,
    function_table_group: Option<&str>,
) -> Result<TypedSeriesPinGroupSelectorRecordV1, SeriesPinTableGroupSelectorErrorV1> {
    TypedSeriesPinGroupSelectorRecordV1::try_new(
        group_name,
        model_selector_name,
        function_table_group,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_PIN_TABLE_GROUP_SELECTOR_POLICY_V1,
            "sipi.p4a-03as.series-pin-table-group-selector-v1.typed-table-group-selector"
        );
    }

    #[test]
    fn valid_full_group_selector_record() {
        let rec = lift_series_pin_group_selector_record_v1(
            "SERIES_GRP1",
            "SEL_SERIES_RES",
            Some("GRP1"),
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.function_table_group(), Some("GRP1"));
    }

    #[test]
    fn valid_minimal_group_selector_record() {
        let rec = lift_series_pin_group_selector_record_v1(
            "SERIES_GRP1",
            "SEL_SERIES_RES",
            None,
        )
        .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.function_table_group(), None);
    }

    #[test]
    fn rejects_empty_group_name() {
        assert_eq!(
            lift_series_pin_group_selector_record_v1("", "SEL1", None),
            Err(SeriesPinTableGroupSelectorErrorV1::EmptyGroupName)
        );
    }

    #[test]
    fn rejects_empty_selector_name() {
        assert_eq!(
            lift_series_pin_group_selector_record_v1("SERIES_GRP1", "", None),
            Err(SeriesPinTableGroupSelectorErrorV1::EmptySelectorName)
        );
    }
}
