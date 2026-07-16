* Expanded-state oracle for native/AgentSpice.Engine/fixtures/one_port.rfm
.SUBCKT rfm_macro p1
V1 p1 s1 0
R1 s1 0 50.0
Gd1_1 0 s1 p1 0 0.002
Fd1_1 0 s1 V1 0.1
Gr1_1_1 0 s1 x1_a1 0 141421356.23730952
Gr2_re_1_1 0 s1 x2_re_a1 0 56568542.4949238
Gr2_im_1_1 0 s1 x2_im_a1 0 84852813.7423857
Cx1_a1 x1_a1 0 1.0
Gx1_a1 0 x1_a1 p1 0 0.07071067811865475
Fx1_a1 0 x1_a1 V1 3.5355339059327378
Rp1_a1 0 x1_a1 5e-10
Cx2_re_a1 x2_re_a1 0 1.0
Gx2_re_a1 0 x2_re_a1 p1 0 0.1414213562373095
Fx2_re_a1 0 x2_re_a1 V1 7.0710678118654755
Rp2_re_re_a1 0 x2_re_a1 3.333333333333333e-10
Gp2_re_im_a1 0 x2_re_a1 x2_im_a1 0 4000000000.0
Cx2_im_a1 x2_im_a1 0 1.0
Gp2_im_re_a1 0 x2_im_a1 x2_re_a1 0 -4000000000.0
Rp2_im_im_a1 0 x2_im_a1 3.333333333333333e-10
.ENDS rfm_macro
