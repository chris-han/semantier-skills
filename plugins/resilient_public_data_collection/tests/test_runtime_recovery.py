from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from plugins.resilient_public_data_collection import recovery_policy, tools


class RuntimeBootstrapTests(unittest.TestCase):
    def test_plan_is_non_mutating_and_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime"
            result = json.loads(tools.prepare_crawlee_runtime({
                "mode": "core",
                "backend": "auto",
                "runtime_dir": str(runtime),
                "plan": True,
            }))
            self.assertTrue(result["ok"])
            self.assertEqual(result["state"], "PLAN")
            self.assertEqual(result["requirement"], "crawlee==1.10.1")
            self.assertEqual(result["backend_requested"], "auto")
            self.assertFalse(runtime.exists())

    def test_offline_cache_miss_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime"
            result = json.loads(tools.prepare_crawlee_runtime({
                "mode": "core",
                "runtime_dir": str(runtime),
                "offline": True,
            }))
            self.assertFalse(result["ok"])
            self.assertEqual(result["state"], "OFFLINE_CACHE_MISS")
            self.assertEqual(result["exit_code"], 4)
            self.assertFalse(runtime.exists())

    def test_check_only_cache_miss_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime"
            result = json.loads(tools.prepare_crawlee_runtime({
                "mode": "core",
                "runtime_dir": str(runtime),
                "check_only": True,
            }))
            self.assertFalse(result["ok"])
            self.assertEqual(result["state"], "MISSING_RUNTIME")
            self.assertEqual(result["exit_code"], 4)
            self.assertFalse(runtime.exists())

    def test_target_backend_is_exposed_in_plan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = json.loads(tools.prepare_crawlee_runtime({
                "mode": "core",
                "backend": "target",
                "runtime_dir": str(Path(td) / "runtime"),
                "plan": True,
            }))
            self.assertTrue(result["ok"])
            self.assertEqual(result["backend_requested"], "target")


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
