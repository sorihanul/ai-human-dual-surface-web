# Dual Surface Delivery Profile 0.1

Tool release: **1.1.0-candidate.1**. Core compatibility: **1.0**.

This is an optional, project-specific delivery extension to AI-Human Dual Surface Web. It is not an IETF/W3C standard, a replacement core specification, an automatic crawler-discovery guarantee or a bot authorization protocol.

## 1. Preservation contract

The source page bundle retains its core `standard_version: "1.0"`, original manifest, routes and Markdown files. No dates, evidence status, authority, limitations, raw source content or instructions are rewritten. Markdown/YAML is transported as UTF-8 text, not interpreted or executed.

A bundle entry has `source_path`, `role`, `media_type`, `sha256`, `evidence_use`, `content`. Encoding `content` back to UTF-8 must reproduce the exact source file bytes. JSON escaping is a transport representation, not a rewrite of the decoded source. Relative links in `content` resolve against its original `source_path` at the deployment base path, never against the generated bundle URL.

The core bundle contains manifest, routes, canon and evidence. `evidence_use` is `conditional` for canon, `evaluate_source` for evidence, and `never` for supporting roles. It is not an independent verification status. Examples, trace, tests and schemas remain separate, and their role/path is listed under `not_bundled`. Their content is available through the original relative paths. Their omission from the default transfer does not delete them.

Publisher reading guidance has only page-local scope. A site's `stop_when` cannot terminate the user's cross-site comparison or override the user's/system's instructions. Reading access grants no permission to order, pay, edit, reserve or delete. These are data-boundary declarations; real-model compliance has not been validated.

## 2. Discovery and deterministic representation

`<base_path>ai/index.json` is an explicitly advertised endpoint. Clients must be given or discover it through a mechanism they support. The package claims no reserved well-known URI or universal agent support.

The index identifies the current core bundle through its URL, SHA-256 and byte count. It also records a full `snapshot_sha256` over sorted `[source_path, role, sha256]` records for all declared source files, including the human test page. This separates a support-only update from a core-content update.

The bundle filename is `ai/bundles/<sha256-of-complete-bundle-bytes>.json`. Serialization is UTF-8, sorted JSON object keys, compact separators, one trailing LF, no request/build time or random identifier. This is this implementation's serializer, not an RFC 8785 canonical JSON conformance claim. Same input bytes produce identical output bytes in the supported implementation. Whitespace changes in an original file are changes, even when its interpreted JSON meaning is unchanged.

The index itself is not answer evidence. A bundle hash proves byte identity relative to a trusted expected hash, not origin identity, evidence truth, currentness or purchase validity. A client must revalidate the index before treating retained content as current. When the current index still names a locally retained bundle whose bytes match its digest, the client can reuse that body without fetching it again. A freshness-acceptable local index can also be reused according to HTTP rules; there is no new mandatory network fetch independent of the user's freshness requirement.

## 3. HTTP reference behavior

The reference server binds only to `127.0.0.1`. It serves an in-memory, integrity-checked release inventory, not arbitrary disk paths. A release change requires a restart/new application. The development server is not a production security perimeter.

- `GET` returns the identity-coded bytes with UTF-8 Content-Type, strong SHA-256 ETag and Content-Length.
- `HEAD` returns corresponding metadata without a response body.
- `If-None-Match` uses weak comparison for GET/HEAD, including lists and wildcard. A match returns `304` with ETag/Cache-Control and no response body. No Content-Length is emitted on that 304.
- `If-Match` is evaluated first with strong comparison; failure returns `412`.
- No Last-Modified is synthesized from evidence dates. Date-based preconditions are ignored because this reference supplies no representation modification time.
- No content-coding negotiation is implemented. A production server changing coding/bytes must use appropriate validators and Vary semantics, not blindly reuse the reference's strong tag for different bytes.
- The index and stable source paths use `public, max-age=0, must-revalidate`. Content-addressed bundles use `public, max-age=300, must-revalidate`. These deliberately conservative defaults are not transactional guarantees.
- Errors are `no-store`; arbitrary files/directories are not served. `POST`, `PUT`, `PATCH`, `DELETE` are rejected.
- The response includes `Link: <.../ai/index.json>; rel="describedby"; type="application/json"`, including a denied human-page response.
- `--deny-human` denies the human page and root alias to **all** callers. It simulates path isolation and must not be described as bot classification/authentication.

A 304 avoids a body transfer, not a request. A CDN hit avoids an origin hit, not client/CDN traffic. Fresh-cache reuse may avoid both, but neither this package nor its benchmark is a full browser/CDN cache implementation.

## 4. Build and publication boundaries

Only declared local surface paths are accepted. References must stay inside the input page bundle. Symlinks, hidden files, unsupported file types/roles, ambiguous JSON keys, non-finite JSON tokens, invalid manifest calendar dates, common manifest placeholders, overlapping roles and undeclared route targets are rejected. Evidence directories contain Markdown; schema directories contain JSON. They must be nonempty. These checks are scoped and not a complete Markdown/YAML/semantic/secret verifier.

The profile bounds a single source file to 1 MiB, total source bytes to 4 MiB, the serialized bundle to 8 MiB and selected sources to 256 files. It fails rather than silently truncating. Larger content should be split into independently addressable page bundles, or the implementation should be deliberately extended and retested.

The builder never edits its input and refuses existing or source-nested output directories. It writes a new directory and writes `.dualweb-deployment.json` last. Incomplete output is not a valid release. This is not an atomic multi-file production deploy; build outside the live deployment, inspect it, then switch deployment using the host's mechanisms. Build from stable input, not a concurrently mutating database export.

The inventory is for local release inspection and is not served by the reference handler. It contains no absolute source path. The human-page copy is for demonstration; the builder does not copy or reconstruct the entire site's CSS, images, sessions or application.

## 5. Snapshot comparison

`compare before after` requires complete validated releases with the same page ID and base path. It reports created/updated/deleted original source files with before/after hashes. Generated index/bundle changes are summarized by bundle identifiers rather than treated as new evidence changes. Absence in a partial retrieval is never a deletion signal.

This is a two-snapshot local comparison, not ResourceSync, a WebSub service, a durable incremental change log, a delivery acknowledgment, an automatic client synchronization routine or a revocation guarantee. Existing copied public content cannot be remotely recalled by this tool.

## 6. References

Primary source specifications checked for the implemented HTTP behavior:

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html), especially 8.8, 13.1.1, 13.1.2 and 15.4.5.
- [RFC 9111 — HTTP Caching](https://httpwg.org/specs/rfc9111.html), especially stored-response reuse and validation.
- [Python http.server documentation](https://docs.python.org/3/library/http.server.html), including its non-production warning.
- Upstream core identity and byte hashes: `UPSTREAM.json`.

Passing local tests is not proof of complete RFC compliance, production availability, independent source truth, adoption, browser compatibility or LLM adherence.
