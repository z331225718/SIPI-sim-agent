#![forbid(unsafe_code)]

//! A deliberately narrow BSD-3-Clause direct port of the selected IEEE
//! 802-COM interpolation and raw-periodic inverse-transform leaves. This crate
//! does not perform causality enforcement, truncation, convolution, waveform
//! generation, or external comparison.

pub mod interp_sparam_v1;
pub mod s21_to_raw_periodic_v1;

pub use interp_sparam_v1::{
    InterpSparamErrorV1, SelectedP3cUniformSpectrumV1, interpolate_selected_p3c_hdiff_v1,
};
pub use s21_to_raw_periodic_v1::{
    RawPeriodicTransformErrorV1, SelectedP3cRawPeriodicResponseV1,
    inverse_selected_p3c_uniform_spectrum_v1,
};
