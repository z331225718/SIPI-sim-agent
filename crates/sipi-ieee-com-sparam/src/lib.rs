#![forbid(unsafe_code)]

//! A deliberately narrow BSD-3-Clause direct port of the selected IEEE
//! 802-COM interpolation leaf. This crate produces only a uniform spectrum;
//! it does not perform an inverse transform, causality enforcement,
//! truncation, convolution, waveform generation, or external comparison.

pub mod interp_sparam_v1;

pub use interp_sparam_v1::{
    InterpSparamErrorV1, SelectedP3cUniformSpectrumV1, interpolate_selected_p3c_hdiff_v1,
};
