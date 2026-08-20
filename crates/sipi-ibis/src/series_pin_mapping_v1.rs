//! Typed IBIS [Series Pin Mapping] standalone table core (P4A-03o).
//!
//! Lifts and validates standalone IBIS [Series Pin Mapping] records
//! (pin_1, pin_2, model_name, function_table_group) into typed, clean-room structures.
//! Fail-closed: empty pin or model names, non-ASCII characters, or identical pin pairs
//! are strictly rejected.

/// Scope policy for the typed series pin mapping table core.
pub const SERIES_PIN_MAPPING_TABLE_POLICY_V1: &str =
    "sipi.p4a-03o.series-pin-mapping-v1.typed-table";

/// Fail-closed errors during series pin mapping lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SeriesPinMappingTableErrorV1 {
    EmptyPinName,
    EmptyModelName,
    NonAsciiName,
    InvalidName,
    IdenticalPins,
}

/// A typed IBIS [Series Pin Mapping] table record.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedSeriesPinRecordV1 {
    pin_first: String,
    pin_second: String,
    model_name: String,
    function_table_group: Option<String>,
}

impl TypedSeriesPinRecordV1 {
    pub fn try_new(
        pin_first: impl Into<String>,
        pin_second: impl Into<String>,
        model_name: impl Into<String>,
        function_table_group: Option<impl Into<String>>,
    ) -> Result<Self, SeriesPinMappingTableErrorV1> {
        let pf = pin_first.into().trim().to_string();
        let ps = pin_second.into().trim().to_string();
        let mn = model_name.into().trim().to_string();

        if pf.is_empty() || ps.is_empty() {
            return Err(SeriesPinMappingTableErrorV1::EmptyPinName);
        }
        if mn.is_empty() {
            return Err(SeriesPinMappingTableErrorV1::EmptyModelName);
        }
        if !pf.is_ascii() || !ps.is_ascii() || !mn.is_ascii() {
            return Err(SeriesPinMappingTableErrorV1::NonAsciiName);
        }
        if !pf.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !ps.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
            || !mn.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(SeriesPinMappingTableErrorV1::InvalidName);
        }
        if pf == ps {
            return Err(SeriesPinMappingTableErrorV1::IdenticalPins);
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
                return Err(SeriesPinMappingTableErrorV1::NonAsciiName);
            }
        }

        Ok(Self {
            pin_first: pf,
            pin_second: ps,
            model_name: mn,
            function_table_group: ftg,
        })
    }

    pub fn pin_first(&self) -> &str {
        &self.pin_first
    }

    pub fn pin_second(&self) -> &str {
        &self.pin_second
    }

    pub fn model_name(&self) -> &str {
        &self.model_name
    }

    pub fn function_table_group(&self) -> Option<&str> {
        self.function_table_group.as_deref()
    }
}

/// Lift one series pin mapping record.
pub fn lift_series_pin_record_v1(
    pin_first: &str,
    pin_second: &str,
    model_name: &str,
    function_table_group: Option<&str>,
) -> Result<TypedSeriesPinRecordV1, SeriesPinMappingTableErrorV1> {
    TypedSeriesPinRecordV1::try_new(pin_first, pin_second, model_name, function_table_group)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            SERIES_PIN_MAPPING_TABLE_POLICY_V1,
            "sipi.p4a-03o.series-pin-mapping-v1.typed-table"
        );
    }

    #[test]
    fn valid_full_record() {
        let rec = lift_series_pin_record_v1("P1", "P2", "R_SERIES_50", Some("GRP1")).expect("lift");
        assert_eq!(rec.pin_first(), "P1");
        assert_eq!(rec.pin_second(), "P2");
        assert_eq!(rec.model_name(), "R_SERIES_50");
        assert_eq!(rec.function_table_group(), Some("GRP1"));
    }

    #[test]
    fn valid_minimal_record() {
        let rec = lift_series_pin_record_v1("P1", "P2", "R_SERIES_50", None).expect("lift");
        assert_eq!(rec.pin_first(), "P1");
        assert_eq!(rec.pin_second(), "P2");
        assert_eq!(rec.model_name(), "R_SERIES_50");
        assert_eq!(rec.function_table_group(), None);
    }

    #[test]
    fn rejects_empty_pin_name() {
        assert_eq!(
            lift_series_pin_record_v1("", "P2", "R1", None),
            Err(SeriesPinMappingTableErrorV1::EmptyPinName)
        );
    }

    #[test]
    fn rejects_empty_model_name() {
        assert_eq!(
            lift_series_pin_record_v1("P1", "P2", "", None),
            Err(SeriesPinMappingTableErrorV1::EmptyModelName)
        );
    }

    #[test]
    fn rejects_identical_pins() {
        assert_eq!(
            lift_series_pin_record_v1("P1", "P1", "R1", None),
            Err(SeriesPinMappingTableErrorV1::IdenticalPins)
        );
    }
}
