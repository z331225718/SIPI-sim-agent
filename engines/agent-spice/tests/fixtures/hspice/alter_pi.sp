* tiny HSPICE PI fixture with alter cases
.param cdecap=1u
VVRM vdd 0 0.8
RPDN vdd load 10m
CDECAP load 0 cdecap
ILOAD load 0 PWL(0 0.01 1n 0.1 5n 0.1)
.probe tran v(load)
.tran 1p 5n
.alter high_decap
.param cdecap=2u
.alter low_decap
.param cdecap=500n
.end
