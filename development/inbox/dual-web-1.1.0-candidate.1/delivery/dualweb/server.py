"""Loopback-only reference HTTP server. NOT a production bot filter or CDN.

Load a verified release snapshot once; serve only inventory-listed resources.
No directory listing, arbitrary filesystem serving, user-agent authentication,
state-changing operation, proxying, TLS or production rate-limiting is provided.
"""
from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from typing import Mapping
import re

from .core import (BOUNDARIES, BUNDLED_ROLES, ROLE_USE, BuildError, MAX_BUNDLE_BYTES, MAX_FILES, PROFILE, READY_FILE,
                   base_path, digest, etag, json_bytes, local_ref, parse_json,
                   public_url)

TAG = re.compile(r'(?:W/)?"[\x21\x23-\x7e\x80-\xff]*"')


def tag_matches(value: str, current: str, *, weak: bool) -> bool:
    """Parse a tag list (commas inside quoted opaque tags are legal)."""
    value = value.strip()
    if value == "*":
        return True
    position = 0
    matched = False
    count = 0
    while position < len(value):
        # HTTP list parsing permits empty list members to a reasonable extent.
        while position < len(value) and value[position] in " \t,":
            position += 1
        if position == len(value):
            break
        found = TAG.match(value, position)
        if not found:
            return False
        token = found.group()
        matched |= (token.removeprefix("W/") == current if weak else token == current)
        count += 1
        position = found.end()
        while position < len(value) and value[position] in " \t":
            position += 1
        if position < len(value) and value[position] != ",":
            return False
    return bool(count and matched)


@dataclass(frozen=True)
class Stored:
    body: bytes
    tag: str
    media_type: str
    cache_control: str
    role: str


class Application:
    def __init__(self, folder: str | Path, *, deny_human: bool = False):
        root = Path(folder).resolve()
        marker = root / READY_FILE
        if not marker.is_file() or marker.is_symlink():
            raise BuildError("not a complete release: ready inventory missing")
        with marker.open("rb") as stream:
            raw = stream.read(1_048_577)
        if len(raw) > 1_048_576:
            raise BuildError("deployment inventory too large")
        metadata = parse_json(raw, READY_FILE)
        if metadata.get("profile") != PROFILE:
            raise BuildError("unsupported deployment profile")
        self.prefix = base_path(metadata.get("base_path", ""))
        entries = metadata.get("files")
        if not isinstance(entries, dict) or not 1 <= len(entries) <= MAX_FILES + 2:
            raise BuildError("invalid deployment inventory")
        self.resources: dict[str, Stored] = {}
        total = 0
        for relative, item in entries.items():
            if not isinstance(relative, str) or not isinstance(item, dict):
                raise BuildError("invalid inventory entry")
            path = local_ref(root, root, relative)
            if path.relative_to(root).as_posix() != relative or not path.is_file():
                raise BuildError("noncanonical inventory path")
            if any(x.startswith(".") for x in Path(relative).parts):
                raise BuildError("hidden files cannot be served")
            with path.open("rb") as stream:
                data = stream.read(MAX_BUNDLE_BYTES + 1)
            total += len(data)
            if len(data) > MAX_BUNDLE_BYTES or total > 3 * MAX_BUNDLE_BYTES:
                raise BuildError("deployment exceeds size limit")
            if len(data) != item.get("bytes") or digest(data) != item.get("sha256"):
                raise BuildError(f"deployment integrity mismatch: {relative}")
            media = item.get("content_type")
            cache = item.get("cache_control")
            role = item.get("role")
            if media not in {"text/html; charset=utf-8", "text/markdown; charset=utf-8", "application/json; charset=utf-8"}:
                raise BuildError("unsupported Content-Type in inventory")
            if cache not in {"public, max-age=0, must-revalidate", "public, max-age=300, must-revalidate"}:
                raise BuildError("unsupported Cache-Control in inventory")
            self.resources[self.prefix + relative] = Stored(data, etag(data), media, cache, role)
        if metadata.get("index_path") != "ai/index.json":
            raise BuildError("invalid index path")
        self.index_url = public_url(self.prefix, "ai/index.json")
        index_item = self.resources.get(self.prefix + "ai/index.json")
        if not index_item or index_item.role != "index":
            raise BuildError("missing index resource")
        self.index = parse_json(index_item.body, "index.json")
        if self.index.get("profile") != PROFILE or self.index.get("base_path") != self.prefix:
            raise BuildError("index/deployment profile mismatch")
        bundle_info = self.index.get("bundle")
        if not isinstance(bundle_info, dict):
            raise BuildError("missing bundle reference")
        href = bundle_info.get("href", "")
        # Generated content-addressed bundle URLs contain only ASCII-safe characters.
        if not isinstance(href, str):
            raise BuildError("invalid bundle URL")
        payload = self.resources.get(href)
        if not payload or payload.role != "bundle":
            raise BuildError("index points at a missing bundle")
        if digest(payload.body) != bundle_info.get("sha256") or len(payload.body) != bundle_info.get("bytes"):
            raise BuildError("index/bundle integrity mismatch")
        if href != self.prefix + "ai/bundles/" + digest(payload.body) + ".json":
            raise BuildError("bundle URL is not content-addressed")
        bundle = parse_json(payload.body, "bundle.json")
        if bundle.get("profile") != PROFILE or not isinstance(bundle.get("resources"), list):
            raise BuildError("invalid bundle profile")
        if bundle.get("boundaries") != BOUNDARIES:
            raise BuildError("bundle trust boundaries are missing or changed")
        seen = set()
        for record in bundle["resources"]:
            if not isinstance(record, dict) or not isinstance(record.get("content"), str):
                raise BuildError("invalid bundled resource")
            relative = record.get("source_path")
            if not isinstance(relative, str) or relative in seen:
                raise BuildError("duplicate/invalid bundled source path")
            seen.add(relative)
            if record.get("evidence_use") != ROLE_USE.get(record.get("role"), "never"):
                raise BuildError("bundle evidence-use boundary mismatch")
            original = self.resources.get(self.prefix + relative)
            if not original or original.role != record.get("role"):
                raise BuildError("bundled role/source mismatch")
            if record["content"].encode("utf-8") != original.body or digest(original.body) != record.get("sha256"):
                raise BuildError("bundled source content mismatch")
        expected = {p.removeprefix(self.prefix) for p, r in self.resources.items()
                    if r.role in BUNDLED_ROLES}
        if seen != expected:
            raise BuildError("bundle omits or adds declared core resources")
        omitted = bundle.get("not_bundled")
        expected_omitted = [{"source_path": p.removeprefix(self.prefix), "role": r.role, "evidence_use": "never"}
                            for p, r in sorted(self.resources.items())
                            if r.role not in BUNDLED_ROLES | {"index", "bundle", "human"}]
        if omitted != expected_omitted:
            raise BuildError("supporting-surface directory mismatch")
        full_snapshot = [[p.removeprefix(self.prefix), r.role, digest(r.body)]
                         for p, r in sorted(self.resources.items()) if r.role not in {"index", "bundle"}]
        if digest(json_bytes(full_snapshot)) != self.index.get("snapshot_sha256"):
            raise BuildError("index/source snapshot mismatch")
        human = metadata.get("human_path")
        if not isinstance(human, str) or self.resources.get(self.prefix + human, Stored(b"", "", "", "", "")).role != "human":
            raise BuildError("invalid human resource")
        self.human_path = self.prefix + human
        self.deny_human = deny_human

    def respond(self, method: str, target: str, headers: Mapping[str, str]):
        common = {"Link": f'<{self.index_url}>; rel="describedby"; type="application/json"',
                  "X-Content-Type-Options": "nosniff"}

        def error(status, message):
            body = json_bytes({"error": message, "ai_index": self.index_url})
            return status, {**common, "Cache-Control": "no-store",
                            "Content-Type": "application/json; charset=utf-8",
                            "Content-Length": str(len(body)), "Allow": "GET, HEAD"}, b"" if method == "HEAD" else body

        if method not in {"GET", "HEAD"}:
            return error(405, "read-only endpoint")
        try:
            parsed = urlsplit(target)
            path = unquote(parsed.path, encoding="utf-8", errors="strict")
            if parsed.scheme or parsed.netloc or parsed.fragment or not path.startswith("/"):
                return error(400, "invalid request target")
        except (ValueError, UnicodeError):
            return error(400, "invalid request target")
        if "\\" in path or "%" in path or any(ord(c) < 32 for c in path):
            return error(400, "invalid path")
        if any(part in {".", ".."} or part.startswith(".") for part in path.split("/")):
            return error(403, "path is not public")
        if path == self.prefix:
            path = self.human_path
        resource = self.resources.get(path)
        if resource is None:
            return error(404, "not a published resource")
        if self.deny_human and resource.role == "human":
            # This demonstrates path isolation for EVERY requester, not bot recognition.
            return error(403, "human surface disabled in this local demonstration")
        if "If-Match" in headers and not tag_matches(headers["If-Match"], resource.tag, weak=False):
            return error(412, "representation precondition failed")
        successful = {**common, "Content-Type": resource.media_type,
                      "ETag": resource.tag, "Cache-Control": resource.cache_control}
        if "If-None-Match" in headers and tag_matches(headers["If-None-Match"], resource.tag, weak=True):
            return 304, successful, b""  # No Content-Length/body for this 304.
        # No Last-Modified is emitted: evidence dates are not HTTP validators.
        successful["Content-Length"] = str(len(resource.body))
        return 200, successful, b"" if method == "HEAD" else resource.body


def make_server(folder: str | Path, port: int = 0, *, deny_human: bool = False):
    application = Application(folder, deny_human=deny_human)

    class Handler(BaseHTTPRequestHandler):
        server_version = "DualSurfaceReference/0.1"
        sys_version = ""
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def handle_request(self):
            # Combine repeated ETag conditional fields using HTTP list semantics.
            request_headers = {}
            for key in ("If-Match", "If-None-Match"):
                values = self.headers.get_all(key)
                if values:
                    request_headers[key] = ",".join(values)
            status, response_headers, body = application.respond(self.command, self.path, request_headers)
            self.send_response(status)
            for key, value in response_headers.items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                self.wfile.write(body)

        do_GET = handle_request
        do_HEAD = handle_request
        do_POST = handle_request
        do_PUT = handle_request
        do_DELETE = handle_request
        do_PATCH = handle_request
        do_OPTIONS = handle_request

        def log_message(self, format, *args):
            pass  # Do not accidentally log request URLs or user data in the reference.

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.application = application
    return httpd


def compare_releases(before: str | Path, after: str | Path) -> dict:
    """Compare two complete same-page snapshots, not an unbounded event stream."""
    old = Application(before)
    new = Application(after)
    if old.index.get("page_id") != new.index.get("page_id") or old.prefix != new.prefix:
        raise BuildError("compare requires the same page_id and deployment base_path")
    def originals(app):
        return {path.removeprefix(app.prefix): resource for path, resource in app.resources.items()
                if resource.role not in {"index", "bundle"}}
    left, right = originals(old), originals(new)
    changes = []
    for path in sorted(left.keys() | right.keys()):
        a, b = left.get(path), right.get(path)
        if a is not None and b is not None and a.body == b.body and a.role == b.role:
            continue
        changes.append({"source_path": path,
                        "change": "created" if a is None else "deleted" if b is None else "updated",
                        "before_sha256": digest(a.body) if a else None,
                        "after_sha256": digest(b.body) if b else None})
    return {"profile": PROFILE, "scope": "complete same-page snapshot difference; not ResourceSync or a durable event feed",
            "page_id": new.index["page_id"], "before_bundle": old.index["bundle"]["sha256"],
            "after_bundle": new.index["bundle"]["sha256"], "changes": changes}
