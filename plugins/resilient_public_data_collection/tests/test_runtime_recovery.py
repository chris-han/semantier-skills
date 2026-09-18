from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from plugins.resilient_public_data_collection import recovery_policy, runtime_bootstrap


class RuntimeBootstrapTests(unittest.TestCase):
    def test_plan_is_non_mutating_and_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime"
            result = runtime_bootstrap.prepare_runtime(
                mode="core",
                runtime_dir=runtime,
                plan=True,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["state"], "PLAN")
            self.assertEqual(result["requirement"], "crawlee==1.10.1")
            self.assertFalse(runtime.exists())

    def test_offline_cache_miss_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime"
            result = runtime_bootstrap.prepare_runtime(
                mode="core",
                runtime_dir=runtime,
                offline=True,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["state"], "OFFLINE_CACHE_MISS")
            self.assertFalse(runtime.exists())

    def test_check_only_cache_miss_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime"
            result = runtime_bootstrap.prepare_runtime(
                mode="core",
                runtime_dir=runtime,
                check_only=True,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["state"], "MISSING_RUNTIME")
            self.assertFalse(runtime.exists())

    def test_install_failure_is_structured(self) -> None:
        fake_python = Path("/tmp/fake-crawlee-python")
        with patch.object(runtime_bootstrap, "ensure_venv", return_value=(fake_python, True)), \
             patch.object(runtime_bootstrap, "installed_crawlee_version", return_value=None), \
             patch.object(runtime_bootstrap, "pip_install", side_effect=RuntimeError("no package index")):
            result = runtime_bootstrap.prepare_runtime(mode="core", runtime_dir="/tmp/fake-runtime")
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "INSTALL_FAILED")
        self.assertIn("no package index", result["error"])


class RecoveryPolicyTests(unittest.TestCase):
    def test_recovered_route_precedes_blocked_retry(self) -> None:
        result = recovery_policy.decide_recovery({
            "initial_failure": "ATTACHMENT_HTTP_FAILURE",
            "http_status": 403,
            "alternate_source": "NOT_FOUND",
            "same_site_alternate_entry": "FOUND_PUBLIC_ANNOUNCEMENT",
            "public_resource_confirmed": True,
            "blocked_interpretation": "SESSION_OR_BOT_BLOCK",
            "blocked_retry_attempts": 0,
        })
        self.assertEqual(result, "USE_RECOVERED_ROUTE")

    def test_401_never_auto_escalates(self) -> None:
        result = recovery_policy.decide_recovery({
            "initial_failure": "LOGIN_REQUIRED",
            "http_status": 401,
            "alternate_source": "NOT_FOUND",
            "same_site_alternate_entry": "NOT_FOUND",
            "blocked_retry_attempts": 0,
        })
        self.assertEqual(result, "STOP_AUTH_REQUIRED")

    def test_403_public_session_block_may_retry_once(self) -> None:
        result = recovery_policy.decide_recovery({
            "initial_failure": "ATTACHMENT_HTTP_FAILURE",
            "http_status": 403,
            "alternate_source": "NOT_FOUND",
            "same_site_alternate_entry": "NOT_FOUND",
            "public_resource_confirmed": True,
            "blocked_interpretation": "SESSION_OR_BOT_BLOCK",
            "blocked_retry_attempts": 0,
        })
        self.assertEqual(result, "BLOCKED_RETRY_ONCE")

    def test_blocked_retry_is_bounded(self) -> None:
        result = recovery_policy.decide_recovery({
            "initial_failure": "ATTACHMENT_HTTP_FAILURE",
            "http_status": 403,
            "alternate_source": "NOT_FOUND",
            "same_site_alternate_entry": "NOT_FOUND",
            "public_resource_confirmed": True,
            "blocked_interpretation": "SESSION_OR_BOT_BLOCK",
            "blocked_retry_attempts": 1,
        })
        self.assertEqual(result, "STOP_AFTER_BOUNDED_RETRY")


if __name__ == "__main__":
    unittest.main()
