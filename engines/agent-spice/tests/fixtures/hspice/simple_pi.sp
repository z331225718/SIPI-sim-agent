* tiny HSPICE PI fixture
.param vnom=0.8
VVRM vdd 0 vnom
RPDN vdd load 10m
CDECAP load 0 1u
ILOAD load 0 PWL(0 0.01 1n 0.1 5n 0.1)
.probe tran v(load)
.measure tran min_vdd min v(load) from=1n to=5n
.tran 1p 5n
.end
