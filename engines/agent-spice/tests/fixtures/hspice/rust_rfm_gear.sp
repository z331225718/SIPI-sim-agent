* Rust native fixed-output Gear2 RFM compatibility deck
Xchannel p 0 rfm_direct
Vsrc src 0 DC 0 AC 1 PULSE(0 1 100p 20p 20p 500p 1n)
Rsrc src p 50
Rload p 0 50
.options method=gear
.op
.dc Vsrc 0 1 0.5
.ac lin 1 1g 1g
.tran 2p 2n
.end
