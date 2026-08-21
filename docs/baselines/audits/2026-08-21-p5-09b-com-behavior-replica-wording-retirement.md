# P5-09 COM behavior-replica wording retirement audit

The former `behavior_replica_candidate` wording had no product report or
capability consumer. It is now retired, not promoted. P5-08e provides the real
product-owned `ComRunArtifactExecutionReportV1`, so P5-09 binds only to that
report's narrower, observable capability: one exact local pulse artifact is
consumed, the existing COM core executes with a P5-05g parameter-ingestion
result, one immutable result artifact is published, and P5-08d verifies its
bounded metadata.

The product wording is `bounded_artifact_execution`. The report states
`product_owned_bounded_execution_complete`, `not_claimed` for behavioral
replication, and `blocked_missing_authoritative_reference` for external
acceptance. The retired candidate text is not a product capability label and
must not reappear as positive product wording.

The policy continues to reject positive claims such as IEEE-certified,
standards-compliant, validated, approved, qualified, equivalent, match/pass,
reference implementation, parity, conformance, release, acceptance, or
completed behavioral replication. External oracle comparison, the full metric
and checkpoint tolerance matrix, public `com.run` CLI admission, product
acceptance, and promotion remain blocked or false.

This closes P5-09 by binding honest non-acceptance wording to a real report
consumer. It does not convert local product semantics into external COM parity
or IEEE official certification.
