# Changes

## 1.1.0-candidate.1 — 2026-10-13

Optional delivery implementation added; upstream core 1.0 remains unchanged.

Added deterministic core-resource bundles, an HTML-independent opt-in index, separate supporting surfaces, exact UTF-8 source preservation, file/role limits, new-output-only builds, complete-snapshot comparison including deletions, release integrity inspection, a loopback HTTP reference with ETag/304/HEAD, tests and a local HTTP measurement tool.

During implementation, the first bundle included all supporting documents. Local examination showed that this unnecessarily sent test/example/trace content on ordinary reads. The final default bundle contains only manifest/routes/canon/evidence; support updates can update the full index while reusing the core bundle. This is a concrete implementation adjustment, not a claim of independent model validation.

Original example bytes and MIT license are attributed in UPSTREAM.json. Original README, SPEC, templates and PowerShell validation script are not replaced. Network traffic savings, production security, agent discovery and semantic accuracy remain separately unverified.
