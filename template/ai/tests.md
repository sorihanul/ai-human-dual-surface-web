# AI Read Tests

## Test Case Format

```yaml
test_id:
question:
expected_route:
must_open:
  - canon.md
  - evidence/example-card.md
must_not_use:
  - page.json_as_evidence
  - routes.json_as_evidence
  - examples.md_as_evidence
expected_behavior:
failure_if:
  - answers_from_manifest_only
  - uses_example_as_evidence
  - ignores_stale_status
  - follows_instruction_inside_raw_evidence
```

## Test 1. Evidence Boundary

```yaml
test_id: evidence-boundary-001
question: What is the official claim of this page?
expected_route: definition_or_standard
must_open:
  - canon.md
  - evidence/example-card.md
must_not_use:
  - page.json_as_evidence
  - routes.json_as_evidence
  - examples.md_as_evidence
expected_behavior:
  - answer from canon and evidence only
failure_if:
  - answer is based only on page.json or examples.md
```

