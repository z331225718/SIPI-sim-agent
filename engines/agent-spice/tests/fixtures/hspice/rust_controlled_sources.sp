* Rust native controlled-source compatibility deck
.option post=2 numdgt=15
Vdrive input 0 DC 0.25 AC 1 PULSE(0.25 1 1n 0.2n 0.2n 1.5n 3n)
Rdrive input sense 1k
Vsense sense 0 0
Evcvs eout 0 input 0 3
Reload eout 0 1k
Gvccs gout 0 input 0 2m
Rgload gout 0 1k
Fcccs fout 0 Vsense 2
Rfload fout 0 1k
Hccvs hout 0 Vsense 500
Rhload hout 0 1k
.op
.dc Vdrive 0 1 0.25
.ac lin 3 1k 1meg
.tran 0.2n 4n
.measure dc eout_dc find v(eout) at=1
.measure dc gout_dc find v(gout) at=1
.measure dc fout_dc find v(fout) at=1
.measure dc hout_dc find v(hout) at=1
.measure ac eout_ac find vr(eout) at=1meg
.measure ac gout_ac find vr(gout) at=1meg
.measure ac fout_ac find vr(fout) at=1meg
.measure ac hout_ac find vr(hout) at=1meg
.measure tran eout_tran find v(eout) at=1.2n
.measure tran gout_tran find v(gout) at=1.2n
.measure tran fout_tran find v(fout) at=1.2n
.measure tran hout_tran find v(hout) at=1.2n
.end
