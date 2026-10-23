"""Behavioral tests using synthetic records; no live APIs."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import threat_intel as ti


def ok(data, source="test", more=False):
    return {"source": source, "status": "ok", "data": data,
            "has_next_page": more, "retrieved_at": "2026-10-23T00:00:00+00:00"}


class ThreatTests(unittest.TestCase):
    def test_exact_version_query_and_empty_osv_page_continues(self):
        with patch.object(ti, "request", side_effect=[
                ok({"next_page_token": "page2"}), ok({"vulns": [{"id": "TEST-1"}]})]) as req:
            records, receipts, complete = ti.osv_lookup("PyPI", "example", "1.2.3")
        self.assertTrue(complete)
        self.assertEqual(records, [{"id": "TEST-1"}])
        self.assertEqual(len(receipts), 2)
        self.assertEqual(req.call_args.args[2]["version"], "1.2.3")
        self.assertEqual(req.call_args.args[2]["page_token"], "page2")

    def test_osv_pagination_cap_is_incomplete(self):
        with patch.object(ti, "request", return_value=ok({"next_page_token": "more"})):
            self.assertFalse(ti.osv_lookup("npm", "example", "1")[2])

    def test_source_failure_retains_partial_findings(self):
        responses = [ok({"vulns": [{"id": "TEST-1", "withdrawn": "2026-01-01"}]}),
                     ti.unavailable("github_reviewed", "http_429"),
                     ok([{"ghsa_id": "GHSA-test-1234-abcd", "type": "malware"}])]
        with patch.object(ti, "request", side_effect=responses) as req:
            result = ti.package_lookup("PyPI", "example", "1")
        self.assertEqual(result["findings"][0]["status"], "withdrawn")
        self.assertEqual(result["findings"][1]["kind"], "malicious_package")
        self.assertFalse(result["coverage"]["github_reviewed"])
        self.assertIn("type=malware", req.call_args.args[1])

    def test_github_pagination_is_visible(self):
        with patch.object(ti, "request", return_value=ok([], more=True)):
            self.assertFalse(ti.github_lookup("npm", "example", "1", "reviewed")[2])

    def test_unsupported_ecosystem_is_not_clean(self):
        with patch.object(ti, "request") as req:
            records, receipts, complete = ti.github_lookup("Debian:12", "example", "1", "reviewed")
        req.assert_not_called()
        self.assertEqual(records, [])
        self.assertFalse(complete)
        self.assertEqual(receipts[0]["status"], "unavailable")

    def test_failed_kev_is_unknown(self):
        with patch.object(ti, "request", side_effect=[
                ok({"vulnerabilities": []}), ti.unavailable("cisa_kev", "http_403"),
                ok({"data": []})]):
            result = ti.cve_lookup("CVE-2026-12345")
        self.assertEqual(result["kev_status"], "unknown")

    def test_kev_absence_and_presence_are_distinct(self):
        for entries, state in [([], "not_listed"),
                ([{"cveID": "CVE-2026-12345"}], "listed")]:
            with patch.object(ti, "request", side_effect=[
                    ok({}), ok({"vulnerabilities": entries}), ok({"data": []})]):
                self.assertEqual(ti.cve_lookup("CVE-2026-12345")["kev_status"], state)

    def test_malformed_osv_is_not_clean(self):
        with patch.object(ti, "request", return_value=ok({"vulns": {}})):
            self.assertFalse(ti.osv_lookup("PyPI", "example", "1")[2])

    def test_no_coordinate_disclosure_without_flag(self):
        with patch.object(ti, "request") as req, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                ti.main(["package", "--ecosystem", "PyPI", "--name", "example", "--version", "1"])
        req.assert_not_called()

    def test_all_inventory_validated_before_network(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "inventory.json"
            p.write_text(json.dumps([{"ecosystem": "PyPI", "name": "example", "version": "1"},
                                    {"ecosystem": "PyPI", "name": "other", "version": ">=2"}]))
            with patch.object(ti, "request") as req, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    ti.main(["inventory", "--file", str(p), "--share-package-coordinates"])
            req.assert_not_called()

    def test_request_error_does_not_print_secret(self):
        import urllib.error
        with patch.object(ti.urllib.request, "build_opener") as builder:
            builder.return_value.open.side_effect = urllib.error.URLError("secret-token")
            receipt = ti.request("test", "https://api.osv.dev/v1/query",
                                 headers={"Authorization": "Bearer secret-token"})
        self.assertEqual(receipt["status"], "unavailable")
        self.assertNotIn("secret-token", json.dumps(receipt))

    def test_malformed_kev_entries_are_unknown(self):
        with patch.object(ti, "request", side_effect=[
                ok({}), ok({"vulnerabilities": ["bad"]}), ok({"data": []})]):
            result = ti.cve_lookup("CVE-2026-12345")
        self.assertEqual(result["kev_status"], "unknown")
        self.assertEqual(result["evidence"][1]["status"], "invalid_response")

    def test_nvd_rejected_is_not_active(self):
        with patch.object(ti, "request", side_effect=[
                ok({"vulnerabilities": [{"cve": {"id": "CVE-2026-12345",
                                               "vulnStatus": "Rejected"}}]}),
                ok({"vulnerabilities": []}), ok({"data": []})]):
            result = ti.cve_lookup("CVE-2026-12345")
        self.assertEqual(result["nvd_status"], "rejected")
        self.assertEqual(result["epss_status"], "not_found")

    def test_query_separator_is_rejected_before_lookup(self):
        with self.assertRaises(ValueError):
            ti.valid_package({"ecosystem": "npm", "name": "a,b", "version": "1"})

    def test_cli_returns_versioned_json(self):
        with patch.object(ti, "package_lookup", return_value={"coverage": {"osv": False}}):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                ti.main(["package", "--ecosystem", "npm", "--name", "example", "--version", "1",
                         "--share-package-coordinates"])
        result = json.loads(output.getvalue())
        self.assertEqual(result["schema_version"], "threat-intel-cve.v1")
        self.assertFalse(result["results"][0]["coverage"]["osv"])


if __name__ == "__main__":
    unittest.main()
