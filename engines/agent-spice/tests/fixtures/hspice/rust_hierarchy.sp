* Rust native hierarchy compatibility deck
.option post=2 numdgt=10
.param base_r='500*sqrt(4)' total_gain='max(1,3-1)'
Vdrive input 0 DC 0.25 AC 1 PULSE(0.25 1 1n 0.2n 0.2n 1.5n 3n)
Xamplifier input output wrapper total_gain=total_gain r=base_r
Rexternal output 0 2k
.subckt stage stage_in stage_out gain=1 load=1k
Eamp buffer 0 stage_in 0 'gain'
Rseries buffer stage_out 'load/2'
Rshunt stage_out 0 'load'
.ends stage
.subckt wrapper wrapper_in wrapper_out total_gain=1 r=1k
.param child_gain='total_gain+1'
Xinner wrapper_in wrapper_out stage gain=child_gain load=r
.ends wrapper
.op
.dc Vdrive 0 1 0.25
.ac lin 1 1meg 1meg
.tran 0.2n 2n
.measure dc hierarchy_dc find v(output) at=1
.measure ac hierarchy_ac find vr(output) at=1meg
.measure tran hierarchy_tran find v(output) at=1.2n
.end
