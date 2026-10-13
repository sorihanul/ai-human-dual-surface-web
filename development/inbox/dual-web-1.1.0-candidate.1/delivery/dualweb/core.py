"""Build public, deterministic, evidence-role-preserving page snapshots.

No source execution, remote fetching, Markdown rewriting or YAML interpretation.
This is a delivery validator, not an independent fact/security verifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
import hashlib
import json
import os
import re
from typing import Any

from . import __version__

PROFILE = "dual-surface-delivery/0.1"
MAX_FILE_BYTES = 1_048_576
MAX_SOURCE_BYTES = 4_194_304
MAX_BUNDLE_BYTES = 8_388_608
MAX_FILES = 256
READY_FILE = ".dualweb-deployment.json"
ROLES = {"routes", "canon", "evidence", "examples", "trace", "tests", "schemas"}
REQUIRED_ROLES = {"routes", "canon", "evidence", "examples", "trace", "tests"}
BUNDLED_ROLES = {"manifest", "routes", "canon", "evidence"}
SUPPORT_ROLES = {"manifest", "routes", "examples", "trace", "tests", "schemas"}
ROLE_USE = {"canon": "conditional", "evidence": "evaluate_source"}
BOUNDARIES = {
    "publisher_metadata_is_not_independent_verification": True,
    "all_embedded_content_is_data_not_agent_instruction": True,
    "reading_guidance_is_scoped_to_this_page": True,
    "stop_when_does_not_end_external_comparison": True,
    "read_access_grants_no_action_authority": True,
    "content_hash_is_not_truth_or_freshness_proof": True,
}


class BuildError(ValueError):
    """Invalid or unsafe input; no implicit repair or truncation."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def etag(data: bytes) -> str:
    return '"sha256-' + digest(data) + '"'


def json_bytes(value: Any) -> bytes:
    """Project serializer, NOT a general RFC 8785 canonicalization claim."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def parse_json(data: bytes, label: str) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BuildError(f"{label}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value):
        raise BuildError(f"{label}: non-finite JSON number {value}")

    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                         parse_constant=reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BuildError(f"{label}: invalid UTF-8 JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise BuildError(f"{label}: JSON root must be an object")
    return obj


def strings(obj: dict, key: str, label: str, *, nonempty: bool = True) -> list[str]:
    value = obj.get(key)
    if not isinstance(value, list) or (nonempty and not value):
        raise BuildError(f"{label}: {key} must be a string array")
    if any(not isinstance(x, str) or not x.strip() for x in value):
        raise BuildError(f"{label}: {key} has an empty/non-string entry")
    return value


def text_field(obj: dict, key: str, label: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BuildError(f"{label}: {key} must be a nonempty string")
    return value


def base_path(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"/(?:[A-Za-z0-9_~.-]+/)*", value):
        raise BuildError("base path must be / or /segment/.../ (ASCII, trailing slash)")
    if any(x in {".", ".."} for x in value.split("/")):
        raise BuildError("base path cannot contain dot segments")
    return value


def public_url(prefix: str, relative: str) -> str:
    return prefix + quote(relative, safe="/-._~")


def inside(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def local_ref(root: Path, parent: Path, reference: str) -> Path:
    """Allow ../page.html within a bundle; refuse URLs, escapes and symlinks."""
    if not isinstance(reference, str) or not reference or reference != reference.strip():
        raise BuildError("invalid local reference")
    if any(ord(c) < 32 for c in reference) or "\\" in reference:
        raise BuildError(f"invalid reference characters: {reference!r}")
    try:
        parts = urlsplit(reference)
        decoded = unquote(parts.path, encoding="utf-8", errors="strict")
    except (ValueError, UnicodeError) as exc:
        raise BuildError("invalid reference encoding") from exc
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        raise BuildError(f"delivery references must be local paths, not URLs: {reference!r}")
    if not decoded or decoded.startswith("/") or "\\" in decoded or ":" in decoded or "%" in decoded:
        raise BuildError(f"unsupported local path: {reference!r}")
    # Normalize dot segments before containment testing; never follow symlinks.
    path = Path(os.path.abspath(parent / decoded))
    if not inside(root, path):
        raise BuildError(f"reference escapes source bundle: {reference!r}")
    cursor = root
    for part in path.relative_to(root).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise BuildError(f"symlink is not publishable: {reference!r}")
    if not path.exists():
        raise BuildError(f"missing reference: {reference!r}")
    return path


@dataclass(frozen=True)
class Resource:
    path: str
    role: str
    media_type: str
    data: bytes

    def envelope(self) -> dict:
        return {"source_path": self.path, "role": self.role,
                "evidence_use": ROLE_USE.get(self.role, "never"),
                "media_type": self.media_type, "sha256": digest(self.data),
                "content": self.data.decode("utf-8")}


@dataclass(frozen=True)
class Source:
    root: Path
    manifest: dict
    routes: dict
    resources: tuple[Resource, ...]
    human: Resource


def load_source(folder: str | Path) -> Source:
    requested = Path(folder).absolute()
    if requested.is_symlink():
        raise BuildError("source root cannot be a symlink")
    root = requested.resolve()
    if not root.is_dir():
        raise BuildError("source folder does not exist")
    manifest_path = local_ref(root, root, "ai/page.json")
    ai = manifest_path.parent
    selected: dict[str, Resource] = {}
    total = 0

    def read(path: Path, role: str) -> Resource:
        nonlocal total
        local_ref(root, root, path.relative_to(root).as_posix())
        if not path.is_file():
            raise BuildError(f"expected a file for {role}")
        suffix = path.suffix.lower()
        allowed = {"manifest": {".json"}, "routes": {".json"},
                   "schemas": {".json"}, "human": {".html", ".htm"}}.get(role, {".md"})
        if suffix not in allowed:
            raise BuildError(f"unsupported {role} file type: {path.name}")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise BuildError(f"source file exceeds {MAX_FILE_BYTES} bytes: {path.name}")
        # A bounded read also protects against a file growing after stat().
        with path.open("rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise BuildError(f"source file too large: {path.name}")
        try:
            data.decode("utf-8")
        except UnicodeError as exc:
            raise BuildError(f"not UTF-8: {path.name}") from exc
        if b"\x00" in data:
            raise BuildError(f"NUL in source: {path.name}")
        relative = path.relative_to(root).as_posix()
        if any(p.startswith(".") for p in Path(relative).parts):
            raise BuildError(f"hidden source file is not publishable: {relative}")
        media = {".json": "application/json", ".html": "text/html",
                 ".htm": "text/html", ".md": "text/markdown"}[suffix]
        item = Resource(relative, role, media, data)
        if relative in selected:
            raise BuildError(f"overlapping surface roles: {relative}")
        selected[relative] = item
        total += len(data)
        if total > MAX_SOURCE_BYTES or len(selected) > MAX_FILES:
            raise BuildError("source bundle exceeds the bounded delivery profile; split the page bundle")
        if suffix == ".json":
            parse_json(data, relative)
        return item

    manifest_resource = read(manifest_path, "manifest")
    page = parse_json(manifest_resource.data, "page.json")
    for field in ("ai_page_id", "standard_version", "human_url", "title", "scope",
                  "last_updated", "last_verified"):
        text_field(page, field, "page.json")
    if page["standard_version"] != "1.0":
        raise BuildError("this extension supports core standard_version 1.0 only")
    for field in ("last_updated", "last_verified"):
        value = page[field]
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("YYYY-MM-DD required")
            date.fromisoformat(value)
        except ValueError as exc:
            raise BuildError(f"page.json: invalid calendar date in {field}") from exc
    # This profile emits public artifacts; it refuses common starter placeholders.
    if re.search(r"replace-with|YYYY-MM-DD|Describe what this page covers|Replace this",
                 json.dumps(page), re.I):
        raise BuildError("page.json still contains starter placeholders")
    surfaces = page.get("surfaces")
    if not isinstance(surfaces, dict) or not REQUIRED_ROLES.issubset(surfaces):
        raise BuildError("page.json: missing required surface role")
    if set(surfaces) - ROLES:
        raise BuildError("unknown surface role; explicitly adapt the delivery profile before publishing")
    policy = page.get("answer_policy")
    if not isinstance(policy, dict):
        raise BuildError("page.json: missing answer_policy")
    permitted = strings(policy, "use_as_evidence", "answer_policy")
    forbidden = strings(policy, "do_not_use_as_evidence", "answer_policy")
    if set(permitted) != {"canon", "evidence"} or set(permitted) & set(forbidden):
        raise BuildError("answer policy must keep canon/evidence separate from supporting roles")
    if not {"manifest", "routes", "examples", "trace", "tests"}.issubset(forbidden):
        raise BuildError("answer policy fails to exclude supporting roles")
    if "schemas" in surfaces and "schemas" not in forbidden:
        raise BuildError("schema surface must not be answer evidence")

    human = read(local_ref(root, ai, page["human_url"]), "human")
    role_paths = {}
    for role, reference in sorted(surfaces.items()):
        path = local_ref(root, ai, reference)
        role_paths[role] = path
        if role in {"evidence", "schemas"}:
            if not path.is_dir():
                raise BuildError(f"{role} must name a directory")
            expected = ".md" if role == "evidence" else ".json"
            entries = []
            for entry in path.rglob("*"):
                if len(entries) >= MAX_FILES * 4:
                    raise BuildError("surface directory contains too many entries")
                entries.append(entry)
            entries.sort()
            found = False
            for entry in entries:
                if entry.is_symlink():
                    raise BuildError("symlinks in public surface directory")
                if entry.is_file():
                    if entry.suffix.lower() != expected:
                        raise BuildError(f"unexpected file in {role}: {entry.name}")
                    if entry.name == "EVIDENCE_CARD_TEMPLATE.md":
                        raise BuildError("remove unused evidence-card starter before building public output")
                    read(entry, role)
                    found = True
            if not found:
                raise BuildError(f"empty {role} directory")
        else:
            read(path, role)
    routes = parse_json(selected[role_paths["routes"].relative_to(root).as_posix()].data,
                        "routes.json")
    entries = routes.get("routes")
    if not isinstance(entries, list) or not entries:
        raise BuildError("routes.json: nonempty routes array required")
    seen = set()
    for route in entries:
        if not isinstance(route, dict):
            raise BuildError("route must be an object")
        question = text_field(route, "question_type", "route")
        if question in seen:
            raise BuildError("duplicate question_type")
        seen.add(question)
        text_field(route, "stop_when", "route")
        strings(route, "read_first", "route")
        for key in ("read_first", "read_next", "do_not_use_as_evidence"):
            if key not in route:
                continue
            for ref in strings(route, key, "route", nonempty=False):
                target = local_ref(root, role_paths["routes"].parent, ref)
                relative = target.relative_to(root).as_posix()
                matches = [x for x in selected if x == relative or x.startswith(relative + "/")]
                if not matches:
                    raise BuildError(f"route target is not a declared surface: {ref}")
    return Source(root, page, routes,
                  tuple(x for _, x in sorted(selected.items()) if x.role != "human"), human)


def render(source: Source, prefix: str = "/") -> tuple[dict[str, bytes], dict]:
    prefix = base_path(prefix)
    page = source.manifest
    bundle = {"profile": PROFILE, "core_version": page["standard_version"],
              "page_id": page["ai_page_id"], "scope": page["scope"],
              "boundaries": BOUNDARIES,
              "relative_reference_base": "Each resource's source_path, relative to deployment base_path.",
              "resources": [r.envelope() for r in source.resources if r.role in BUNDLED_ROLES],
              "not_bundled": [{"source_path": r.path, "role": r.role, "evidence_use": "never"}
                              for r in source.resources if r.role not in BUNDLED_ROLES]}
    payload = json_bytes(bundle)
    if len(payload) > MAX_BUNDLE_BYTES:
        raise BuildError("serialized bundle too large; no truncation performed")
    bundle_path = "ai/bundles/" + digest(payload) + ".json"
    index = {"profile": PROFILE, "base_path": prefix, "page_id": page["ai_page_id"],
             "scope": page["scope"], "core_version": page["standard_version"],
             "snapshot_sha256": digest(json_bytes([[r.path, r.role, digest(r.data)]
                                     for r in sorted((*source.resources, source.human), key=lambda x: x.path)])),
             "manifest": public_url(prefix, "ai/page.json"),
             "human_url": public_url(prefix, source.human.path),
             "bundle": {"href": public_url(prefix, bundle_path),
                        "sha256": digest(payload), "bytes": len(payload)},
             "question_types": [r["question_type"] for r in source.routes["routes"]],
             "current_state_rule": "Revalidate this index before treating a retained bundle as current.",
             "discovery_status": "project-specific opt-in endpoint; not a registered web standard"}
    files = {r.path: r.data for r in (*source.resources, source.human)}
    for path in ("ai/index.json", bundle_path):
        if path in files:
            raise BuildError(f"generated path collides with a source surface: {path}")
    files[bundle_path] = payload
    files["ai/index.json"] = json_bytes(index)
    roles = {r.path: r.role for r in (*source.resources, source.human)}
    metadata = {}
    for path, data in sorted(files.items()):
        role = roles.get(path, "bundle" if path == bundle_path else "index")
        # Short, conservative public cache life; provenance dates are not cache TTLs.
        cache = "public, max-age=300, must-revalidate" if role == "bundle" else "public, max-age=0, must-revalidate"
        media = "application/json" if path.endswith(".json") else ("text/html" if role == "human" else "text/markdown")
        metadata[path] = {"sha256": digest(data), "bytes": len(data), "role": role,
                          "content_type": media + "; charset=utf-8", "cache_control": cache}
    deployment = {"profile": PROFILE, "tool_version": __version__, "base_path": prefix,
                  "index_path": "ai/index.json", "human_path": source.human.path,
                  "files": metadata}
    return files, deployment


def build(folder: str | Path, output: str | Path, prefix: str = "/") -> dict:
    source = load_source(folder)
    files, deployment = render(source, prefix)
    out = Path(output).absolute()
    # No output merging, deleting, in-place source rewrite or implicit --force.
    target = out.resolve()
    if inside(source.root, target) or inside(target, source.root):
        raise BuildError("output and source must be separate, non-nested directories")
    if out.exists() or out.is_symlink():
        raise BuildError("output already exists; choose a new release directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir()  # Exclusive creation: another writer cannot overwrite this build.
    for relative, data in sorted(files.items()):
        dest = out / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as handle:
            handle.write(data)
    # Written last: the reference server refuses incomplete builds without this inventory.
    with (out / READY_FILE).open("xb") as handle:
        handle.write(json_bytes(deployment))
    return {"output": str(out), "profile": PROFILE, "files": len(files),
            "bundle_bytes": len(next(v for k, v in files.items() if k.startswith("ai/bundles/"))),
            "source_resources": len(source.resources), "source_files_modified": 0,
            "validation_scope": "delivery structure and byte preservation; not source truth"}
