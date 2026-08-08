.subckt conditioned conditioned_in conditioned_out params: scale=1
Egain amplified 0 conditioned_in 0 {library_gain*scale}
Rseries amplified conditioned_out {base_r}
Dclamp conditioned_out 0 selected_diode
.ends conditioned
