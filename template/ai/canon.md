# Canon

```yaml
canon_id:
status: active
last_verified: YYYY-MM-DD
```

## Claims

```yaml
claim_id:
claim:
scope:
status: active | stale | deprecated | draft | disputed
authority:
evidence_required: true
evidence:
  - ./evidence/example-card.md
last_verified:
limits:
```

Template example:

```yaml
claim_id: example-claim-001
claim: Replace this with an official claim.
scope: replace-with-scope
status: draft
authority: replace-with-authority
evidence_required: true
evidence:
  - ./evidence/example-card.md
last_verified: YYYY-MM-DD
limits:
  - Replace this with the claim boundary.
```

## Rules

- Put official definitions, rules, and claims here.
- Do not put unverified assumptions here.
- Mark outdated claims as `stale`.
- Mark removed claims as `deprecated`.
