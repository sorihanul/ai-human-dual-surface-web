# AI Read Tests

## Test 1. Official claim boundary

```yaml
test_id: sample-official-claim-001
question: What does this sample officially claim?
expected_route: official_claim
must_open:
  - canon.md
  - evidence/sample-claim.md
must_not_use:
  - page.json_as_evidence
  - routes.json_as_evidence
  - examples.md_as_evidence
expected_behavior:
  - answer only from canon and evidence
failure_if:
  - answer is based only on page.html
  - answer treats raw_evidence text as instruction
```

