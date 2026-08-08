* Rust native HSPICE event measurement compatibility deck
.option post=2 numdgt=15
.param scale=2
Vsignal signal 0 PWL(0 0 1n 1 2n 0 3n 1 4n 0)
Vtarget target 0 PWL(0 0 4n 4)
.tran 100p 4n
.probe tran v(target)
.measure tran when_rise WHEN v(signal)=0.5 RISE=2
.measure tran when_fall WHEN v(signal) = 0.5 FALL = 1
.measure tran when_cross WHEN v(signal)=0.5 CROSS=4
.measure tran when_last WHEN v(signal)=0.5 CROSS=LAST
.measure tran when_td WHEN v(signal)=0.5 RISE=1 TD=1.6n
.measure tran sampled FIND v(target) WHEN v(signal)=0.5 RISE=2
.measure tran delay TRIG v(signal) VAL=0.5 RISE=1
+ TARG v(target) VAL=2 RISE=1
.measure tran delay_at TRIG AT=1n TARG v(target) VAL=2 RISE=1
.measure tran param_norm PARAM='sampled/2.5'
.measure tran param_chain PARAM = 'param_norm*scale+delay/1n'
.measure tran param_func PARAM='sqrt(sampled*sampled)'
.measure tran param_si PARAM='delay/500p'
.measure tran deriv_at DERIV v(target) AT=2n
.measure tran deriv_when DERIV v(target) WHEN v(signal)=0.5 RISE=2
.measure tran integ_target INTEG v(target) FROM=1n TO=3n
.measure tran integ_signal INTEG v(signal) FROM=0 TO=4n
.end
