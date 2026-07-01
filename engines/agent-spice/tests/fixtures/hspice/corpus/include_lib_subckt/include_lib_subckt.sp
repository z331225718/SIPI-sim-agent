* synthetic-real include/lib/subckt deck
.include 'deps/models.inc'
.lib 'deps/corners.lib' tt
Xdecap rail 0 decap_cell c=10u
Vrail rail 0 0.8
.tran 1p 1n
.end
