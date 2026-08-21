# P4A-03d Exact Asset Structural Consumer Audit

This slice binds the owner-selected IBIS object to the existing clean-room
typed declaration consumer. The authority is SIPI-sim-agent commit
`b6071779d8164e685d15ddf45c19dcb6b2553c78`; the parser and runner blobs are
recorded in the evidence YAML. The asset is the owner-selected
`as4c512m16md4v-053bin.ibs`, SHA-256
`d72cf62b56d67d30f4004f56ea3b79b4cb1241615692b147682f47540e615a0b`,
4,215,925 bytes.

The production parser path is exercised through the external-only
`p4a_03d_model_declaration_runner`: 67 typed model declarations were observed,
with 27 `Input` and 40 `IO` declarations. The generated JSON is hash-bound in
the evidence and must be supplied explicitly for dynamic verification. No
model selector, corner, required-keyword profile, electrical evaluation,
transient endpoint, AMI behavior, runtime, or release claim is made.

The dynamic verifier takes an explicit asset root and runner-output path. It
fails closed on either missing input, path escape, hash/length drift, or typed
declaration drift. This is a bounded structural consumer observation, not
authorization to add a profile or to use the asset in a product runtime.

## Remaining gates

P4A-01 still lacks owner-frozen model selector/corner and endpoint stimulus,
timebase, initial state, observable, and tolerance. P4A-02 behavior parity and
P4B AMI parameter/runtime/rights closure remain blocked. No P4B-08 typed edge
is admitted because the observed open-circuit differential response is not yet
contractually equivalent to the matched S21 input consumed by `sipi-channel`.
