//! Typed IBIS [Golden Waveforms] complete block required keywords core (P4A-03aj).
//!
//! Lifts and validates IBIS [Golden Waveforms] complete block required sub-keyword entries
//! (waveform_declaration) into typed clean-room structures.
//! Fail-closed: invalid golden waveform declarations or missing required fields are strictly rejected.

use crate::golden_wave_declaration_v1::TypedGoldenWaveDeclarationV1;

/// Scope policy for the typed golden waveforms keywords core.
pub const GOLDEN_WAVE_KEYWORDS_POLICY_V1: &str =
    "sipi.p4a-03aj.golden-wave-keywords-v1.typed-golden-keywords";

/// Fail-closed errors during golden waveforms keywords validation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum GoldenWaveKeywordsErrorV1 {
    MissingGoldenWaveformDeclaration,
}

/// A composite typed IBIS [Golden Waveforms] complete block entry.
#[derive(Clone, Debug, PartialEq)]
pub struct TypedGoldenWaveBlockV1 {
    waveform_declaration: TypedGoldenWaveDeclarationV1,
}

impl TypedGoldenWaveBlockV1 {
    pub fn try_new(
        waveform_declaration: TypedGoldenWaveDeclarationV1,
    ) -> Result<Self, GoldenWaveKeywordsErrorV1> {
        Ok(Self {
            waveform_declaration,
        })
    }

    pub fn waveform_declaration(&self) -> &TypedGoldenWaveDeclarationV1 {
        &self.waveform_declaration
    }
}

/// Lift one complete golden waveforms block entry.
pub fn lift_golden_wave_block_v1(
    waveform_declaration: TypedGoldenWaveDeclarationV1,
) -> Result<TypedGoldenWaveBlockV1, GoldenWaveKeywordsErrorV1> {
    TypedGoldenWaveBlockV1::try_new(waveform_declaration)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::golden_wave_declaration_v1::lift_golden_wave_declaration_v1;

    #[test]
    fn policy_fixed() {
        assert_eq!(
            GOLDEN_WAVE_KEYWORDS_POLICY_V1,
            "sipi.p4a-03aj.golden-wave-keywords-v1.typed-golden-keywords"
        );
    }

    #[test]
    fn valid_golden_wave_block() {
        let wave = lift_golden_wave_declaration_v1("GOLDEN_WAVE_1", Some("DUT_FBGA84")).unwrap();
        let block = lift_golden_wave_block_v1(wave).expect("lift");

        assert_eq!(
            block.waveform_declaration().waveform_name(),
            "GOLDEN_WAVE_1"
        );
        assert_eq!(block.waveform_declaration().dut_name(), Some("DUT_FBGA84"));
    }
}
