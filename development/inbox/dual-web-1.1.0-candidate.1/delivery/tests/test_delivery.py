"""Acceptance, boundary and live-loopback HTTP tests. No external services."""
from pathlib import Path
import hashlib
import http.client
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

DELIVERY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DELIVERY))
from dualweb import core
from dualweb.core import BuildError, READY_FILE, build, load_source, render
from dualweb.server import Application, compare_releases, make_server, tag_matches


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        shutil.copytree(DELIVERY / "example", self.source)
        self.out = self.base / "release"

    def page_edit(self, callback):
        p = self.source / "ai/page.json"
        value = read_json(p)
        callback(value)
        write_json(p, value)

    def routes_edit(self, callback):
        p = self.source / "ai/routes.json"
        value = read_json(p)
        callback(value)
        write_json(p, value)

    def reject(self):
        with self.assertRaises(BuildError):
            build(self.source, self.out)
        self.assertFalse(self.out.exists())

    def test_upstream_fixture_is_exact(self):
        provenance = read_json(DELIVERY / "UPSTREAM.json")
        for rel, meta in provenance["files"].items():
            data = (DELIVERY / rel).read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            self.assertEqual(meta["git_blob_sha"], actual, rel)
            self.assertEqual(meta["bytes"], len(data), rel)

    def test_all_source_bytes_and_evidence_roles_preserved(self):
        old = {p.relative_to(self.source).as_posix(): p.read_bytes()
               for p in self.source.rglob("*") if p.is_file()}
        report = build(self.source, self.out)
        self.assertEqual(7, report["source_resources"])
        index = read_json(self.out / "ai/index.json")
        bundle_path = self.out / index["bundle"]["href"].lstrip("/")
        raw = bundle_path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), index["bundle"]["sha256"])
        bundle = json.loads(raw)
        roles = {"ai/page.json": "manifest", "ai/routes.json": "routes",
                 "ai/canon.md": "canon", "ai/evidence/sample-claim.md": "evidence",
                 "ai/examples.md": "examples", "ai/tests.md": "tests", "ai/changelog.md": "trace"}
        self.assertEqual(4, len(bundle["resources"]))
        self.assertEqual({"examples", "trace", "tests"}, {r["role"] for r in bundle["not_bundled"]})
        for record in bundle["resources"]:
            key = record["source_path"]
            self.assertEqual(old[key], record["content"].encode())
            self.assertEqual(roles[key], record["role"])
            if roles[key] not in {"canon", "evidence"}:
                self.assertEqual("never", record["evidence_use"])
        for path, data in old.items():
            self.assertEqual(data, (self.source / path).read_bytes())
            self.assertEqual(data, (self.out / path).read_bytes())
        self.assertEqual("1.0", read_json(self.out / "ai/page.json")["standard_version"])
        self.assertEqual("2026-05-21", read_json(self.out / "ai/page.json")["last_verified"])

    def test_identical_builds_are_byte_identical(self):
        build(self.source, self.out)
        second = self.base / "second"
        build(self.source, second)
        first_files = {p.relative_to(self.out).as_posix(): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
        second_files = {p.relative_to(second).as_posix(): p.read_bytes() for p in second.rglob("*") if p.is_file()}
        self.assertEqual(first_files, second_files)

    def test_evidence_change_changes_bundle_id_without_resetting_dates(self):
        build(self.source, self.out)
        evidence = self.source / "ai/evidence/sample-claim.md"
        evidence.write_bytes(evidence.read_bytes() + b"\nAdditional scope limit.\n")
        after = self.base / "after"
        build(self.source, after)
        self.assertNotEqual(read_json(self.out / "ai/index.json")["bundle"]["sha256"],
                            read_json(after / "ai/index.json")["bundle"]["sha256"])
        self.assertEqual("2026-05-21", read_json(after / "ai/page.json")["last_verified"])

    def test_change_report_created_updated_deleted(self):
        remove = self.source / "ai/evidence/retired.md"
        remove.write_text("Previously published evidence\n")
        build(self.source, self.out)
        remove.unlink()
        (self.source / "ai/evidence/new.md").write_text("New evidence\n")
        with (self.source / "ai/canon.md").open("a") as f:
            f.write("\nChanged scope\n")
        after = self.base / "after"
        build(self.source, after)
        actual = {x["source_path"]: x["change"] for x in compare_releases(self.out, after)["changes"]}
        self.assertEqual({"ai/evidence/retired.md": "deleted", "ai/evidence/new.md": "created", "ai/canon.md": "updated"}, actual)

    def test_unchanged_change_report_is_empty(self):
        build(self.source, self.out)
        after = self.base / "after"
        build(self.source, after)
        self.assertEqual([], compare_releases(self.out, after)["changes"])

    def test_compare_different_page_fails(self):
        build(self.source, self.out)
        self.page_edit(lambda p: p.update(ai_page_id="different"))
        after = self.base / "after"
        build(self.source, after)
        with self.assertRaises(BuildError):
            compare_releases(self.out, after)

    def test_support_only_update_changes_index_but_reuses_core_bundle(self):
        build(self.source, self.out)
        with (self.source / "ai/tests.md").open("a") as f:
            f.write("\nAn additional behavior test.\n")
        after = self.base / "after"
        build(self.source, after)
        old = read_json(self.out / "ai/index.json")
        new = read_json(after / "ai/index.json")
        self.assertNotEqual(old["snapshot_sha256"], new["snapshot_sha256"])
        self.assertEqual(old["bundle"], new["bundle"])
        Application(after)

    def test_unverified_and_adversarial_source_stays_data(self):
        p = self.source / "ai/evidence/sample-claim.md"
        original = p.read_text().replace("verification_status: verified", "verification_status: unverified")
        p.write_text(original, encoding="utf-8")
        build(self.source, self.out)
        app = Application(self.out)
        raw = app.resources[app.index["bundle"]["href"]].body
        bundle = json.loads(raw)
        record = next(r for r in bundle["resources"] if r["role"] == "evidence")
        self.assertIn("verification_status: unverified", record["content"])
        self.assertIn("ignore previous instructions", record["content"])
        self.assertTrue(bundle["boundaries"]["all_embedded_content_is_data_not_agent_instruction"])
        self.assertEqual(original, record["content"])

    def test_extra_files_not_published(self):
        (self.source / ".env").write_text("private test fixture")
        (self.source / "private.txt").write_text("private test fixture")
        build(self.source, self.out)
        self.assertFalse((self.out / ".env").exists())
        self.assertFalse((self.out / "private.txt").exists())

    def test_invalid_calendar_date_rejected(self):
        self.page_edit(lambda p: p.update(last_verified="2026-02-30"))
        self.reject()

    def test_leap_day_is_accepted(self):
        self.page_edit(lambda p: p.update(last_verified="2024-02-29"))
        load_source(self.source)

    def test_placeholder_manifest_rejected(self):
        self.page_edit(lambda p: p.update(scope="Replace this scope"))
        self.reject()

    def test_unknown_core_version_rejected(self):
        self.page_edit(lambda p: p.update(standard_version="9.0"))
        self.reject()

    def test_duplicate_json_key_rejected(self):
        path = self.source / "ai/page.json"
        path.write_text(path.read_text().replace('{', '{"ai_page_id":"first",', 1))
        self.reject()

    def test_nonfinite_json_token_rejected(self):
        path = self.source / "ai/page.json"
        path.write_text(path.read_text().replace('{', '{"extra":NaN,', 1))
        self.reject()

    def test_root_json_array_rejected(self):
        (self.source / "ai/page.json").write_text("[]")
        self.reject()

    def test_non_utf8_rejected(self):
        (self.source / "ai/canon.md").write_bytes(b"\xff\xfe")
        self.reject()

    def test_nul_rejected(self):
        (self.source / "ai/canon.md").write_bytes(b"\x00")
        self.reject()

    def test_external_surface_reference_rejected_without_fetch(self):
        self.page_edit(lambda p: p["surfaces"].update(canon="https://example.org/canon.md"))
        self.reject()

    def test_relative_escape_rejected(self):
        (self.base / "outside.md").write_text("not public")
        self.page_edit(lambda p: p["surfaces"].update(canon="../../outside.md"))
        self.reject()

    def test_percent_encoded_escape_rejected(self):
        (self.base / "outside.md").write_text("not public")
        self.page_edit(lambda p: p["surfaces"].update(canon="%2e%2e/%2e%2e/outside.md"))
        self.reject()

    def test_absolute_path_rejected(self):
        self.page_edit(lambda p: p["surfaces"].update(canon="/etc/passwd"))
        self.reject()

    def test_external_symlink_rejected(self):
        path = self.source / "ai/canon.md"
        path.unlink()
        outside = self.base / "outside.md"
        outside.write_text("private")
        path.symlink_to(outside)
        self.reject()

    def test_internal_symlink_rejected(self):
        path = self.source / "ai/canon.md"
        path.unlink()
        path.symlink_to(self.source / "ai/examples.md")
        self.reject()

    def test_hidden_evidence_file_rejected(self):
        (self.source / "ai/evidence/.private.md").write_text("private")
        self.reject()

    def test_unexpected_file_under_evidence_rejected(self):
        (self.source / "ai/evidence/secret.txt").write_text("private")
        self.reject()

    def test_missing_surface_rejected(self):
        (self.source / "ai/canon.md").unlink()
        self.reject()

    def test_support_role_cannot_be_promoted(self):
        self.page_edit(lambda p: p["answer_policy"]["use_as_evidence"].append("examples"))
        self.reject()

    def test_conflicting_policy_rejected(self):
        self.page_edit(lambda p: p["answer_policy"]["do_not_use_as_evidence"].append("canon"))
        self.reject()

    def test_unknown_surface_role_rejected(self):
        self.page_edit(lambda p: p["surfaces"].update(secret="./canon.md"))
        self.reject()

    def test_overlapping_surface_roles_rejected(self):
        self.page_edit(lambda p: p["surfaces"].update(examples="./canon.md"))
        self.reject()

    def test_missing_route_target_rejected(self):
        self.routes_edit(lambda r: r["routes"][0].update(read_next=["./missing.md"]))
        self.reject()

    def test_undeclared_route_file_rejected(self):
        (self.source / "ai/extra.md").write_text("not declared")
        self.routes_edit(lambda r: r["routes"][0].update(read_next=["./extra.md"]))
        self.reject()

    def test_duplicate_question_type_rejected(self):
        self.routes_edit(lambda r: r["routes"].append(dict(r["routes"][0])))
        self.reject()

    def test_string_instead_of_read_array_rejected(self):
        self.routes_edit(lambda r: r["routes"][0].update(read_first="./canon.md"))
        self.reject()

    def test_empty_evidence_directory_rejected(self):
        (self.source / "ai/evidence/sample-claim.md").unlink()
        self.reject()

    def test_oversized_source_rejected(self):
        with mock.patch.object(core, "MAX_FILE_BYTES", 16):
            self.reject()

    def test_oversized_serialized_bundle_rejected(self):
        with mock.patch.object(core, "MAX_BUNDLE_BYTES", 16):
            self.reject()

    def test_existing_output_is_not_overwritten(self):
        self.out.mkdir()
        sentinel = self.out / "keep.txt"
        sentinel.write_text("keep")
        with self.assertRaises(BuildError):
            build(self.source, self.out)
        self.assertEqual("keep", sentinel.read_text())
        self.assertEqual([sentinel], list(self.out.iterdir()))

    def test_empty_existing_output_also_refused(self):
        self.out.mkdir()
        with self.assertRaises(BuildError):
            build(self.source, self.out)

    def test_nested_output_refused(self):
        with self.assertRaises(BuildError):
            build(self.source, self.source / "build")
        self.assertFalse((self.source / "build").exists())

    def test_valid_subdirectory_mount(self):
        build(self.source, self.out, "/docs/guide/")
        app = Application(self.out)
        self.assertEqual(200, app.respond("GET", "/docs/guide/ai/index.json", {})[0])
        self.assertEqual(404, app.respond("GET", "/ai/index.json", {})[0])
        self.assertTrue(app.index["bundle"]["href"].startswith("/docs/guide/ai/"))

    def test_invalid_base_paths(self):
        for prefix in ("docs/", "/docs", "/../", "/./", "/a\r\n/", "//evil/", "/a b/"):
            with self.subTest(prefix=prefix), self.assertRaises(BuildError):
                core.base_path(prefix)

    def test_release_file_tamper_detected(self):
        build(self.source, self.out)
        (self.out / "ai/canon.md").write_text("tampered")
        with self.assertRaisesRegex(BuildError, "integrity"):
            Application(self.out)

    def test_incomplete_release_refused(self):
        build(self.source, self.out)
        (self.out / READY_FILE).unlink()
        with self.assertRaises(BuildError):
            Application(self.out)

    def test_optional_schemas_stay_out_of_core_bundle(self):
        schema_dir = self.source / "ai/schemas"
        schema_dir.mkdir()
        write_json(schema_dir / "sample.schema.json", {"type": "object"})
        self.page_edit(lambda p: p["surfaces"].update(schemas="./schemas/"))
        self.page_edit(lambda p: p["answer_policy"]["do_not_use_as_evidence"].append("schemas"))
        build(self.source, self.out)
        app = Application(self.out)
        bundle = json.loads(app.resources[app.index["bundle"]["href"]].body)
        self.assertNotIn("schemas", {r["role"] for r in bundle["resources"]})
        self.assertIn("schemas", {r["role"] for r in bundle["not_bundled"]})

    def test_empty_schema_directory_rejected(self):
        (self.source / "ai/schemas").mkdir()
        self.page_edit(lambda p: p["surfaces"].update(schemas="./schemas/"))
        self.page_edit(lambda p: p["answer_policy"]["do_not_use_as_evidence"].append("schemas"))
        self.reject()

    def test_non_string_base_path_rejected(self):
        with self.assertRaises(BuildError):
            core.base_path(None)

    def test_per_request_state_does_not_rebuild_release(self):
        build(self.source, self.out)
        app = Application(self.out)
        before = {p.relative_to(self.out).as_posix(): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
        for _ in range(3):
            app.respond("GET", app.index_url, {})
        after = {p.relative_to(self.out).as_posix(): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_cli_bad_input_nonzero(self):
        command = [sys.executable, str(DELIVERY / "run.py"), "check", str(self.base / "missing")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(2, result.returncode)
        self.assertIn("ERROR:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name) / "release"
        build(DELIVERY / "example", cls.out)
        cls.server = make_server(cls.out, deny_human=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.bundle_url = cls.server.application.index["bundle"]["href"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def request(self, method="GET", path="/ai/index.json", headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_html_denied_but_index_and_bundle_open(self):
        status, headers, body = self.request(path="/page.html")
        self.assertEqual(403, status)
        self.assertIn('</ai/index.json>; rel="describedby"', headers["Link"])
        self.assertEqual("/ai/index.json", json.loads(body)["ai_index"])
        self.assertEqual(200, self.request()[0])
        self.assertEqual(200, self.request(path=self.bundle_url)[0])

    def test_root_alias_cannot_bypass_human_denial(self):
        self.assertEqual(403, self.request(path="/")[0])

    def test_denial_is_not_user_agent_detection(self):
        for ua in ("Mozilla/5.0", "ExampleAgent", "Googlebot"):
            self.assertEqual(403, self.request(path="/page.html", headers={"User-Agent": ua})[0])
            self.assertEqual(200, self.request(headers={"User-Agent": ua})[0])

    def test_repeated_index_returns_real_304_and_zero_body(self):
        _, initial, original = self.request()
        status, repeated, body = self.request(headers={"If-None-Match": initial["ETag"]})
        self.assertEqual(304, status)
        self.assertEqual(b"", body)
        self.assertEqual(initial["ETag"], repeated["ETag"])
        self.assertNotIn("Content-Length", repeated)
        self.assertEqual('"sha256-' + hashlib.sha256(original).hexdigest() + '"', initial["ETag"])

    def test_weak_index_tag_matches(self):
        tag = self.request()[1]["ETag"]
        self.assertEqual(304, self.request(headers={"If-None-Match": "W/" + tag})[0])

    def test_tag_list_matches(self):
        tag = self.request()[1]["ETag"]
        self.assertEqual(304, self.request(headers={"If-None-Match": '"different,opaque", W/' + tag})[0])

    def test_wildcard_matches(self):
        self.assertEqual(304, self.request(headers={"If-None-Match": "*"})[0])

    def test_mismatched_tag_sends_body(self):
        status, headers, body = self.request(headers={"If-None-Match": '"old"'})
        self.assertEqual(200, status)
        self.assertEqual(len(body), int(headers["Content-Length"]))
        self.assertGreater(len(body), 0)

    def test_head_has_no_body_but_get_length(self):
        _, get_headers, data = self.request(path=self.bundle_url)
        status, head_headers, body = self.request("HEAD", self.bundle_url)
        self.assertEqual(200, status)
        self.assertEqual(b"", body)
        self.assertEqual(str(len(data)), head_headers["Content-Length"])
        self.assertEqual(get_headers["ETag"], head_headers["ETag"])

    def test_head_conditional_returns_304(self):
        tag = self.request()[1]["ETag"]
        status, _, body = self.request("HEAD", headers={"If-None-Match": tag})
        self.assertEqual((304, b""), (status, body))

    def test_if_match_checked_before_if_none_match(self):
        tag = self.request()[1]["ETag"]
        status, _, _ = self.request(headers={"If-Match": '"other"', "If-None-Match": tag})
        self.assertEqual(412, status)

    def test_weak_if_match_not_accepted(self):
        tag = self.request()[1]["ETag"]
        self.assertEqual(412, self.request(headers={"If-Match": "W/" + tag})[0])

    def test_if_match_same_is_accepted(self):
        tag = self.request()[1]["ETag"]
        self.assertEqual(200, self.request(headers={"If-Match": tag})[0])

    def test_mutation_methods_denied(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertEqual(405, self.request(method)[0], method)

    def test_directory_and_private_files_not_served(self):
        for path in ("/ai/", "/ai/evidence/", "/private.txt", "/not-found"):
            self.assertEqual(404, self.request(path=path)[0], path)
        for path in ("/.env", "/.git/config", "/" + READY_FILE):
            self.assertEqual(403, self.request(path=path)[0], path)

    def test_traversal_and_encoded_traversal_denied(self):
        for path in ("/../page.html", "/ai/%2e%2e/page.html", "/ai/%2E%2E/%2E%2E/etc/passwd"):
            self.assertEqual(403, self.request(path=path)[0], path)
        self.assertEqual(400, self.request(path="/ai/%252e%252e/page.html")[0])

    def test_encoded_html_does_not_bypass_denial(self):
        self.assertEqual(403, self.request(path="/%70age.html")[0])

    def test_query_does_not_create_new_representation(self):
        original = self.request()
        self.assertEqual(original[2], self.request(path="/ai/index.json?tracking=123")[2])
        self.assertEqual(original[1]["ETag"], self.request(path="/ai/index.json?tracking=456")[1]["ETag"])

    def test_freshness_headers_not_evidence_dates(self):
        headers = self.request()[1]
        self.assertEqual("public, max-age=0, must-revalidate", headers["Cache-Control"])
        self.assertNotIn("Last-Modified", headers)
        self.assertNotIn("Content-Encoding", headers)
        self.assertEqual("public, max-age=300, must-revalidate", self.request(path=self.bundle_url)[1]["Cache-Control"])

    def test_missing_resource_never_304_even_wildcard(self):
        self.assertEqual(404, self.request(path="/missing", headers={"If-None-Match": "*"})[0])

    def test_denied_resource_never_304(self):
        self.assertEqual(403, self.request(path="/page.html", headers={"If-None-Match": "*"})[0])

    def test_etag_parser_corner_cases(self):
        self.assertTrue(tag_matches('"a,b", W/"c"', '"c"', weak=True))
        self.assertFalse(tag_matches('"a,b", W/"c"', '"c"', weak=False))
        for invalid in ('garbage "c"', '* , "c"', 'W/"c" broken', '"c""d"'):
            self.assertFalse(tag_matches(invalid, '"c"', weak=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
