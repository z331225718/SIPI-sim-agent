# P3C Selected Four-Port Static Bench v1

This product-owned slice parses only the selected four-port `# Hz S RI R 50.0`
lexical subset and reduces the fixed matched bench with port order
`TX+, RX+, TX-, RX-`. The scalar differential transfer is
`(S21 - S23 - S41 + S43) / 4`.

The result remains an explicit-frequency static spectrum. It does not
interpolate, add DC, extend high frequency, enforce causality or passivity,
construct an impulse response, convolve a PRBS9 stimulus, or produce a
candidate waveform. It does not read an external asset, expose a CLI, or bind
the external ADS reference.
