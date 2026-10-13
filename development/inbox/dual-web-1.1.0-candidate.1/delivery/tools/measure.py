#!/usr/bin/env python3
"""Measure localhost HTTP requests/bodies; no real CDN/agent/load claims.

The cold comparison uses the SAME four core source documents. The new path
includes its index-discovery request. Warm paths deliberately revalidate;
a real fresh local cache can avoid requests in BOTH designs.
"""
from pathlib import Path
import http.client
import json
import sys
import tempfile
import threading

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from dualweb.core import build
from dualweb.server import make_server


def measure() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / "release"
        build(HERE / "example", out)
        server = make_server(out, deny_human=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def fetch(path, tag=None):
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                client.request("GET", path, headers={"If-None-Match": tag} if tag else {})
                response = client.getresponse()
                data = response.read()
                return {"path": path, "status": response.status,
                        "body_bytes": len(data), "etag": response.getheader("ETag")}, data
            finally:
                client.close()
        try:
            legacy_paths = ["/ai/page.json", "/ai/routes.json", "/ai/canon.md", "/ai/evidence/sample-claim.md"]
            cold_old, warm_old = [], []
            contents = {}
            for path in legacy_paths:
                row, raw = fetch(path)
                assert row["status"] == 200
                cold_old.append(row)
                contents[path.lstrip("/")] = raw
            index_row, raw_index = fetch("/ai/index.json")
            index = json.loads(raw_index)
            bundle_row, raw_bundle = fetch(index["bundle"]["href"])
            bundle = json.loads(raw_bundle)
            assert {r["source_path"]: r["content"].encode() for r in bundle["resources"]} == contents
            cold_new = [index_row, bundle_row]
            for row in cold_old:
                repeated, _ = fetch(row["path"], row["etag"])
                assert repeated["status"] == 304 and repeated["body_bytes"] == 0
                warm_old.append(repeated)
            repeated_index, _ = fetch("/ai/index.json", index_row["etag"])
            assert repeated_index["status"] == 304
            warm_new = [repeated_index]  # The previously retained bundle is reused.
            denied, denied_body = fetch("/page.html")
            assert denied["status"] == 403 and json.loads(denied_body)["ai_index"] == "/ai/index.json"
            def summary(rows):
                return {"http_requests": len(rows), "response_body_bytes": sum(r["body_bytes"] for r in rows), "responses": rows}
            return {"measurement": "real localhost HTTP, identity coding, fictional upstream fixture",
                    "equivalent_core_source_bytes": sum(len(v) for v in contents.values()),
                    "cold_individual": summary(cold_old), "cold_index_and_bundle": summary(cold_new),
                    "revalidated_individual": summary(warm_old), "revalidated_index": summary(warm_new),
                    "html_blocked_ai_open": True,
                    "limits": ["Not a real-agent success/accuracy benchmark.",
                               "No CDN, production bot filtering, concurrency/load, billing, latency or actual Internet measurements.",
                               "HTTP headers, TLS and packet overhead are excluded from byte counts.",
                               "The JSON envelope/index increase cold body bytes on this tiny sample; fewer requests do not imply fewer bytes.",
                               "Both designs could avoid all requests while a suitable local cache is fresh.",
                               "This validates a delivery mechanism, not superiority over all optimized HTML/API designs."]}
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    print(json.dumps(measure(), ensure_ascii=False, indent=2))
