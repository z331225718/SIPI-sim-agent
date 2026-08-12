# P3C PRBS9 Metric Core v2

This product-owned core consumes exactly two finite 49056-sample strict-grid
waveforms. It evaluates only the third PRBS9 period, without alignment,
resampling, fitting, external input, or reference binding.

The waveform NRMSE uses the v2 contract's fixed 1% limit. The sampled eye
partitions each phase by the frozen PRBS9 bit of its current UI. Eye width is
the non-wrapping contiguous interval of positive discrete openings containing
phase 16. The crossing TIE uses the matching ideal transition only, a left
closed/right open half-UI window, the stated directional endpoint ownership,
and linear interpolation. Missing, multiple, or zero-plateau crossings are
structural rejections; raw TIE is never de-meaned.

The result is a formula report, not external-reference binding or candidate,
receiver, profile, or release acceptance. It has no CLI or artifact transport.
