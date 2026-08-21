# P4A-03 Typed Inventory Consumer

## Result

This slice adds one product-owned, in-memory library consumer for the existing IBIS
layers:

1. bounded ASCII structural parse;
2. lexical semantic envelope;
3. typed `[Model]` declarations;
4. typed `[Model Selector]` declarations and branch-to-model checks;
5. typed `[Pin]` declarations; and
6. explicit classification of each pin reference as a declared model, a model
   selector, or a caller-supplied marker.

No model selector branch is chosen. No corner, PVT, supply, reference node,
electrical behavior, transient integration, AMI runtime, external profile, or
release state is inferred.

## Selected Asset Observation

The owner-selected `fixtures/ibis/as4c512m16md4v-053bin.ibs` reaches the new
consumer's selector completeness check and is rejected with:

```text
selector_branch_unknown: DQ_PIN -> DQ_60OHM_60OHM_PREEMP_ON
```

This is a useful fail-closed fact. The implementation must not manufacture
the absent `[Model]` block or silently treat a selector as a selected model.
The later `CKE_PIN` reference classification remains unobserved until the
selector branch gap is resolved or an explicit marker/selector policy is
provided by the owner.

## Remaining Contract Gaps

- complete model blocks for every selected-asset selector branch;
- owner-selected branch/corner/PVT policy;
- electrical profile decoder and independent acceptance evidence; and
- the seven dynamic endpoint fields already listed by the P4A dynamic
  composition contract.

The P4A-03 main item therefore remains open. This slice only establishes a
real library-level composition and a bounded, machine-verifiable rejection
boundary. It does not yet add a public CLI route or invoke the product runtime.
