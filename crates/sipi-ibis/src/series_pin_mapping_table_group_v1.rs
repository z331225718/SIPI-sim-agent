//! Typed IBIS [Series Pin Mapping] group model binding record core (P4A-03bf).
//!
//! Lifts and validates IBIS [Series Pin Mapping] group model binding records
//! (group_name, model_name, function_table_group) into typed clean-room structures.
//! Fail-closed: empty group or model names, non-ASCII characters,
//! or invalid name spellings are strictly rejected.

/// Scope policy for the typed series pin table group core.
pub const SERIES_PIN_TABLE_GROUP_POLICY_V1: &str =
    "sipi.p4a-03bf.series-pin-table-group-v1.typed-table-group";

/// Fail-closed errors during series pin table group lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinTableGroupModelErrorV1 {
    EmptyGroupName,
    EmptyModelName,
    NonAsciiName,
    InvalidName,
}

/// A typed IBIS [Series Pin Mapping] group model binding record.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSeriesPinGroupModelRecordV1 {
    group_name: String,
    model_name: String,
    function_table_group: Option<String>,
}

impl TypedSeriesPinGroupModelRecordV1 {
    pub fn try_new(
        group_name: impl Into<String>,
        model_name: impl Into<String>,
        function_table_group: Option<impl Into<String>>,
    ) -> Result<Self, SeriesPinTableGroupModelErrorV1> {
        let gn = group_name.into().trim().to_string();
        let mn = model_name.into().trim().to_string();

        if gn.is_empty() {
            return Err(SeriesPinTableGroupModelErrorV1::EmptyGroupName);
        }
        if mn.is_empty() {
            return Err(SeriesPinTableGroupModelErrorV1::EmptyModelName);
        }
        if !gn.is_ascii() || !mn.is_ascii() {
            return Err(SeriesPinTableGroupModelErrorV1::NonAsciiName);
        }
        if !gn
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !mn
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinTableGroupModelErrorV1::InvalidName);
        }

        let ftg = function_table_group.and_then(|g| {
            let t = g.into().trim().to_string();
            if t.is_empty() { None } else { Some(t) }
        });

        if let Some(ref g) = ftg
            && !g.is_ascii()
        {
            return Err(SeriesPinTableGroupModelErrorV1::NonAsciiName);
        }

        Ok(Self {
            group_name: gn,
            model_name: mn,
            function_table_group: ftg,
        })
    }

    pub fn group_name(&self) -> &str {
        &self.group_name
    }

    pub fn model_name(&self) -> &str {
        &self.model_name
    }

    pub fn function_table_group(&self) -> Option<&str> {
        self.function_table_group.as_deref()
    }
}

/// Lift one series pin group model binding record.
pub fn lift_series_pin_group_model_record_v1(
    group_name: &str,
    model_name: &str,
    function_table_group: Option<&str>,
) -> Result<TypedSeriesPinGroupModelRecordV1, SeriesPinTableGroupModelErrorV1> {
    TypedSeriesPinGroupModelRecordV1::try_new(group_name, model_name, function_table_group)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_PIN_TABLE_GROUP_POLICY_V1,
            "sipi.p4a-03bf.series-pin-table-group-v1.typed-table-group"
        );
    }

    #[test]
    fn valid_full_group_model_record() {
        let rec = lift_series_pin_group_model_record_v1("SERIES_GRP1", "R_SERIES_50", Some("GRP1"))
            .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.model_name(), "R_SERIES_50");
        assert_eq!(rec.function_table_group(), Some("GRP1"));
    }

    #[test]
    fn valid_minimal_group_model_record() {
        let rec = lift_series_pin_group_model_record_v1("SERIES_GRP1", "R_SERIES_50", None)
            .expect("lift");
        assert_eq!(rec.group_name(), "SERIES_GRP1");
        assert_eq!(rec.model_name(), "R_SERIES_50");
        assert_eq!(rec.function_table_group(), None);
    }

    #[test]
    fn rejects_empty_group_name() {
        assert_eq!(
            lift_series_pin_group_model_record_v1("", "R_SERIES_50", None),
            Err(SeriesPinTableGroupModelErrorV1::EmptyGroupName)
        );
    }

    #[test]
    fn rejects_empty_model_name() {
        assert_eq!(
            lift_series_pin_group_model_record_v1("SERIES_GRP1", "", None),
            Err(SeriesPinTableGroupModelErrorV1::EmptyModelName)
        );
    }
}
