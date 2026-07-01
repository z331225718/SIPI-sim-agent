* synthetic-real VRM decap PDN smoke deck
.inc 'deps/decap.inc'
.option post=2
.param vdd=0.8 rvrm=2m
Vvrm vdd 0 {vdd}
Rvrm vdd rail {rvrm}
Lpkg rail load 500p
Cbulk load 0 100u
Iload load 0 PWL(0 0 1n 0 1.1n 8 5n 8)
.probe tran v(load) i(Vvrm)
.measure tran min_vload min v(load) from=1n to=5n
.tran 10p 5n
.end
