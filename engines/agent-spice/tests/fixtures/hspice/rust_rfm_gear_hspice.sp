* HSPICE expanded-state Gear2 RFM compatibility deck
.option post=2 numdgt=10 method=gear resmin=1e-15
.include 'rust_rfm_one_port_macro.sp'
Vsrc src 0 DC 0 AC 1 PULSE(0 1 100p 20p 20p 500p 1n)
Rsrc src p 50
Rload p 0 50
Xchannel p rfm_macro
.op
.dc Vsrc 0 1 0.5
.ac lin 1 1g 1g
.tran 2p 2n
.measure dc dc_p find v(p) at=1
.measure ac ac_p_mag find vm(p) at=1g
.measure ac ac_p_phase find vp(p) at=1g
.measure tran p_120p find v(p) at=120p
.measure tran p_200p find v(p) at=200p
.measure tran p_620p find v(p) at=620p
.measure tran p_1n find v(p) at=1n
.measure tran p_2n find v(p) at=2n
.end
