* Rust native linear PI compatibility deck
.option post=2 numdgt=15
.param vnom=0.8 rvrm=2m
Vvrm vdd 0 DC vnom AC 1
Rvrm vdd rail rvrm
Lpkg rail load 500p
Cbulk load 0 100u
Iload load 0 DC 0.1 AC 0 PWL(0 0.1 1n 0.1 1.1n 8 5n 8)
.op
.dc Vvrm 0.7 0.9 0.1
.ac lin 3 100k 1meg
.tran 10p 5n
.measure dc dc_load find v(load) at=0.8
.measure ac ac_load_mag find vm(load) at=1meg
.measure ac ac_load_phase find vp(load) at=1meg
.measure tran min_vload min v(load) from=1n to=5n
.end
