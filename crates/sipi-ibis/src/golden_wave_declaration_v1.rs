//! Typed IBIS [Golden Waveforms] declaration core (P4A-03s).
//!
//! Lifts and validates IBIS [Golden Waveforms] golden reference waveform headers
//! (waveform name, DUT/fixture association) into typed clean-room structures.
//! Fail-closed: empty waveform or DUT names, non-ASCII characters, or invalid name spellings
//! are strictly rejected.

/// Scope policy for the typed golden waveforms declaration core.
pub const GOLDEN_WAVE_DECLARATION_POLICY_V1: &str =
    "sipi.p4a-03s.golden-wave-declaration-v1.typed-golden-wave";

/// Fail-closed errors during golden waveforms declaration lifting.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum GoldenWaveDeclarationErrorV1 {
    EmptyWaveformName,
    NonAsciiName,
    InvalidName,
}

/// A typed IBIS [Golden Waveforms] reference declaration.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TypedGoldenWaveDeclarationV1 {
    waveform_name: String,
    dut_name: Option<String>,
}

impl TypedGoldenWaveDeclarationV1 {
    pub fn try_new(
        waveform_name: impl Into<String>,
        dut_name: Option<impl Into<String>>,
    ) -> Result<Self, GoldenWaveDeclarationErrorV1> {
        let name = waveform_name.into();
        let trimmed = name.trim();
        if trimmed.is_empty() {
            return Err(GoldenWaveDeclarationErrorV1::EmptyWaveformName);
        }
        if !trimmed.is_ascii() {
            return Err(GoldenWaveDeclarationErrorV1::NonAsciiName);
        }
        if !trimmed
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err(GoldenWaveDeclarationErrorV1::InvalidName);
        }

        let dut = dut_name.and_then(|d| {
            let t = d.into().trim().to_string();
            if t.is_empty() {
                None
            } else {
                Some(t)
            }
        });

        if let Some(ref d) = dut {
            if !d.is_ascii() {
                return Err(GoldenWaveDeclarationErrorV1::NonAsciiName);
            }
            if !d.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.') {
                return Err(GoldenWaveDeclarationErrorV1::InvalidName);
            }
        }

        Ok(Self {
            waveform_name: trimmed.to_string(),
            dut_name: dut,
        })
    }

    pub fn waveform_name(&self) -> &str {
        &self.waveform_name
    }

    pub fn dut_name(&self) -> Option<&str> {
        self.dut_name.as_deref()
    }
}

/// Lift one golden waveform reference declaration.
pub fn lift_golden_wave_declaration_v1(
    waveform_name: &str,
    dut_name: Option<&str>,
) -> Result<TypedGoldenWaveDeclarationV1, GoldenWaveDeclarationErrorV1> {
    TypedGoldenWaveDeclarationV1::try_new(waveform_name, dut_name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            GOLDEN_WAVE_DECLARATION_POLICY_V1,
            "sipi.p4a-03s.golden-wave-declaration-v1.typed-golden-wave"
        );
    }

    #[test]
    fn valid_full_golden_wave() {
        let wave = lift_golden_wave_declaration_v1("GOLDEN_WAVE_1", Some("DUT_FBGA84"))
            .expect("lift");
        assert_eq!(wave.waveform_name(), "GOLDEN_WAVE_1");
        assert_eq!(wave.dut_name(), Some("DUT_FBGA84"));
    }

    #[test]
    fn valid_minimal_golden_wave() {
        let wave = lift_golden_wave_declaration_v1("WAVE_MIN", None).expect("lift");
        assert_eq!(wave.waveform_name(), "WAVE_MIN");
        assert_eq!(wave.dut_name(), None);
    }

    #[test]
    fn rejects_empty_waveform_name() {
        assert_eq!(
            lift_golden_wave_declaration_v1("", Some("DUT")),
            Err(GoldenWaveDeclarationErrorV1::EmptyWaveformName)
        );
    }

    #[test]
    fn rejects_non_ascii_name() {
        assert_eq!(
            lift_golden_wave_declaration_v1("波形1", None),
            Err(GoldenWaveDeclarationErrorV1::NonAsciiName)
        );
    }

    #[test]
    fn rejects_invalid_name_characters() {
        assert_eq!(
            lift_golden_wave_declaration_v1("WAVE @1", None),
            Err(GoldenWaveDeclarationErrorV1::InvalidName)
        );
    }
}
