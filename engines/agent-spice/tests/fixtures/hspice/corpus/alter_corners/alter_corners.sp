* synthetic-real alter corner deck
.param cdecap=10u rvrm=2m
Vvrm vdd 0 0.8
Rvrm vdd rail {rvrm}
Cdecap rail 0 {cdecap}
.probe tran v(rail)
.tran 10p 2n
.alter fast
.param cdecap=20u rvrm=1m
.alter slow
.param cdecap=5u rvrm=5m
.end
