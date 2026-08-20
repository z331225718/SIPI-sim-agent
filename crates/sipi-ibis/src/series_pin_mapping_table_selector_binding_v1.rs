//! Typed IBIS [Series Pin Mapping] Model Selector binding record core (P4A-03aq).
//!
//! Lifts and validates IBIS [Series Pin Mapping] Model Selector binding records
//! (pin_first, pin_second, model_selector_name, function_table_group) into typed clean-room structures.
//! Fail-closed: empty pin or selector names, non-ASCII characters, identical pin pairs,
//! or invalid name spellings are strictly rejected.

/// Scope policy for the typed series pin table selector core.
pub const SERIES_PIN_TABLE_SELECTOR_POLICY_V1: &str =
    "sipi.p4a-03aq.series-pin-table-selector-v1.typed-table-selector";

/// Fail-closed errors during series pin table selector lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinTableSelectorErrorV1 {
    EmptyPinName,
    EmptySelectorName,
    NonAsciiName,
    InvalidName,
    IdenticalPins,
}

/// A typed IBIS [Series Pin Mapping] Model Selector binding record.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSeriesPinSelectorRecordV1 {
    pin_first: String,
    pin_second: String,
    model_selector_name: String,
    function_table_group: Option<String>,
}

impl TypedSeriesPinSelectorRecordV1 {
    pub fn try_new(
        pin_first: impl Into<String>,
        pin_second: impl Into<String>,
        model_selector_name: impl Into<String>,
        function_table_group: Option<impl Into<String>>,
    ) -> Result<Self, SeriesPinTableSelectorErrorV1> {
        let pf = pin_first.into().trim().to_string();
        let ps = pin_second.into().trim().to_string();
        let ms = model_selector_name.into().trim().to_string();

        if pf.is_empty() || ps.is_empty() {
            return Err(SeriesPinTableSelectorErrorV1::EmptyPinName);
        }
        if ms.is_empty() {
            return Err(SeriesPinTableSelectorErrorV1::EmptySelectorName);
        }
        if !pf.is_ascii() || !ps.is_ascii() || !ms.is_ascii() {
            return Err(SeriesPinTableSelectorErrorV1::NonAsciiName);
        }
        if !pf.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ps.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ms.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinTableSelectorErrorV1::InvalidName);
        }
        if pf == ps {
            return Err(SeriesPinTableSelectorErrorV1::IdenticalPins);
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
                return Err(SeriesPinTableSelectorErrorV1::NonAsciiName);
            }
        }

        Ok(Self {
            pin_first: pf,
            pin_second: ps,
            model_selector_name: ms,
            function_table_group: ftg,
        })
    }

    pub fn pin_first(&self) -> &str {
        &self.pin_first
    }

    pub fn pin_second(&self) -> &str {
        &self.pin_second
    }

    pub fn model_selector_name(&self) -> &str {
        &self.model_selector_name
    }

    pub fn function_table_group(&self) -> Option<&str> {
        self.function_table_group.as_deref()
    }
}

/// Lift one series pin selector binding record.
pub fn lift_series_pin_selector_record_v1(
    pin_first: &str,
    pin_second: &str,
    model_selector_name: &str,
    function_table_group: Option<&str>,
) -> Result<TypedSeriesPinSelectorRecordV1, SeriesPinTableSelectorErrorV1> {
    TypedSeriesPinSelectorRecordV1::try_new(
        pin_first,
        pin_second,
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
            SERIES_PIN_TABLE_SELECTOR_POLICY_V1,
            "sipi.p4a-03aq.series-pin-table-selector-v1.typed-table-selector"
        );
    }

    #[test]
    fn valid_full_selector_record() {
        let rec = lift_series_pin_selector_record_v1(
            "P1",
            "P2",
            "SEL_SERIES_RES",
            Some("GRP1"),
        )
        .expect("lift");
        assert_eq!(rec.pin_first(), "P1");
        assert_eq!(rec.pin_second(), "P2");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.function_table_group(), Some("GRP1"));
    }

    #[test]
    fn valid_minimal_selector_record() {
        let rec = lift_series_pin_selector_record_v1(
            "P1",
            "P2",
            "SEL_SERIES_RES",
            None,
        )
        .expect("lift");
        assert_eq!(rec.pin_first(), "P1");
        assert_eq!(rec.pin_second(), "P2");
        assert_eq!(rec.model_selector_name(), "SEL_SERIES_RES");
        assert_eq!(rec.function_table_group(), None);
    }

    #[test]
    fn rejects_empty_pin_name() {
        assert_eq!(
            lift_series_pin_selector_record_v1("", "P2", "SEL1", None),
            Err(SeriesPinTableSelectorErrorV1::EmptyPinName)
        );
    }

    #[test]
    fn rejects_identical_pins() {
        assert_eq!(
            lift_series_pin_selector_record_v1("P1", "P1", "SEL1", None),
            Err(SeriesPinTableSelectorErrorV1::IdenticalPins)
        );
    }
}
