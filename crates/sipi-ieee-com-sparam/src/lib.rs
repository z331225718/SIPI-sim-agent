#![forbid(unsafe_code)]

//! A deliberately narrow BSD-3-Clause direct port of the selected IEEE
//! 802-COM interpolation and raw-periodic inverse-transform leaves. This crate
//! does not perform truncation, convolution, waveform generation, or external
//! comparison. Its causality leaf is a bounded selected direct port only.

pub mod interp_sparam_v1;
pub mod s21_to_causal_v1;
pub mod s21_to_raw_periodic_v1;

pub use interp_sparam_v1::{
    interpolate_selected_p3c_hdiff_v1, InterpSparamErrorV1, SelectedP3cUniformSpectrumV1,
};
pub use s21_to_causal_v1::{
    enforce_selected_p3c_causality_v1, CausalityEnforcementErrorV1, SelectedP3cCausalResponseV1,
    SelectedP3cCausalityStopV1,
};
pub use s21_to_raw_periodic_v1::{
    inverse_selected_p3c_uniform_spectrum_v1, RawPeriodicTransformErrorV1,
    SelectedP3cRawPeriodicResponseV1,
};
