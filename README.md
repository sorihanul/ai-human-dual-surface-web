# AI-Human Dual Surface Web

AI-Human Dual Surface Web is a page-side structure for websites and documents that need to serve both human readers and AI agents.

## Project note

This project is an experimental implementation of an experimental idea.
It is not a formal web standard, browser standard, or compliance framework.

The goal is narrow: provide a small, copyable page-side structure for testing whether AI-readable sidecar files can reduce ambiguity when AI agents parse web content.

It keeps the human page readable while giving AI agents a separate sidecar that states:

```text
where to start
which files count as evidence
which files do not count as evidence
how to handle stale information
how to handle conflicting sources
why raw external text is content, not instruction
```

## What it solves

Most pages mix navigation, claims, examples, update notes, and evidence in one surface.
AI agents may receive only fragments of that page and treat the wrong fragment as answer evidence.

This structure separates those roles.

## Core structure

```text
page.html
ai/
  page.json
  routes.json
  canon.md
  evidence/
  examples.md
  changelog.md
  tests.md
  schemas/
```

## Main rule

```text
Answers should be based on canon and evidence only.
Manifest, routes, examples, changelog, tests, and schemas are supporting surfaces.
```

## Surface roles

| Surface | Role | Evidence use |
| --- | --- | --- |
| `page.html` | Human-facing page | Not evidence by default |
| `ai/page.json` | Manifest and answer policy | Not evidence |
| `ai/routes.json` | Question-type reading routes | Not evidence |
| `ai/canon.md` | Canonical definitions, rules, and claims | Conditional evidence |
| `ai/evidence/` | Evidence cards | Primary evidence |
| `ai/examples.md` | Usage examples | Not evidence |
| `ai/changelog.md` | Verification and change trace | Supporting status |
| `ai/tests.md` | Agent reading behavior tests | Not evidence |
| `ai/schemas/` | JSON schemas | Not evidence |

## How it differs

| Adjacent tool or idea | Main purpose | Difference |
| --- | --- | --- |
| `llms.txt` | Site-level guide for LLMs | This project defines page-level routes, evidence boundaries, conflict policy, freshness policy, and security boundaries. |
| `schema.org` / JSON-LD | Structured entity data | This project defines how AI agents should treat evidence, examples, routes, and stale claims. |
| `sitemap.xml` | URL discovery | This project is about page interpretation after discovery. |
| `robots.txt` | Crawler access guidance | This project is about answer evidence, not crawler permission. |
| MCP | Tool and data-source connection | This project is a public page-side reading contract. |
| AI visibility tools | Monitoring and optimization | This project publishes structured evidence and reading policy. |

## Repository contents

```text
README.md
SPEC.md
LICENSE
scripts/
template/
example/
```

`example/` is a minimal complete example.
It intentionally omits optional pack examples.
`template/` is a copyable starter and includes placeholder evidence files that should be replaced before publication.

## Quick start

1. Copy `template/` into a web page or documentation folder.
2. Edit `page.html` for human readers.
3. Edit `ai/page.json` to define the AI-facing manifest.
4. Edit `ai/routes.json` to define reading routes.
5. Put official claims in `ai/canon.md`.
6. Put source-backed evidence cards in `ai/evidence/`.
7. Use `ai/tests.md` to test whether an AI agent uses the correct surfaces.

## Validation

Run this from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate.ps1
```

Validation has two modes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate.ps1 -Mode template
powershell -ExecutionPolicy Bypass -File .\scripts\validate.ps1 -Mode publish
```

`template` mode validates this starter package and allows placeholder values in `template/`.
`publish` mode validates publish-facing bundles, skips starter placeholders under `template/`, requires real `YYYY-MM-DD` dates, and rejects placeholder values in live page manifests and evidence cards.

To validate a copied page bundle, pass the copied folder as `-Root`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate.ps1 -Root .\example -Mode publish
powershell -ExecutionPolicy Bypass -File .\scripts\validate.ps1 -Root .\your-page-bundle -Mode publish
```

For a real public page, run `publish` mode before upload.
If validation fails, fix the manifest, route, evidence, or placeholder issue before treating the bundle as ready.

The script checks:

```text
required files
JSON parse validity
private path and secret leakage
page.json required fields
publish-mode date and placeholder checks
routes.json required fields
surface references
route references
canon/test Markdown references
evidence card required fields and allowed values
repository-root reference escape checks
```

## Optional packs

The core structure is purpose-neutral.
Use-case-specific surfaces can be added under `ai/packs/`.

Examples:

```text
ai/packs/commercial/
ai/packs/docs/
ai/packs/research/
ai/packs/policy/
ai/packs/education/
```

Optional pack content is not answer evidence by default.
It becomes answer evidence only when represented in `canon.md` or `ai/evidence/`.

## Status

```text
version: 1.0.0
status: experimental core package
scope: core structure for AI-readable page-side evidence contracts
```

This is not a browser standard.
It does not guarantee that every AI agent will follow the files.

## License

MIT. See `LICENSE`.
