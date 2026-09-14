from __future__ import annotations

import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _json_request(opener, url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(request, timeout=20) as response:
        body = json.loads(response.read().decode() or "{}")
        return int(response.status), body


def run_smoke(repo_root: Path) -> dict:
    gateway_port = _free_port()
    llm_port = _free_port()
    workspace_port = _free_port()
    with tempfile.TemporaryDirectory(prefix="eod-f10-db-auth-") as temp:
        fixture_root = Path(temp)
        uvicorn_wrapper = fixture_root / "uvicorn-wrapper.sh"
        uvicorn_wrapper.write_text(
            "#!/usr/bin/env bash\nexec uv run --extra dev python -m uvicorn \"$@\"\n",
            encoding="utf-8",
        )
        uvicorn_wrapper.chmod(0o755)
        env = os.environ.copy()
        env.update(
            {
                "F10_GATEWAY_PORT": str(gateway_port),
                "F10_LLM_PORT": str(llm_port),
                "F10_WORKSPACE_PORT": str(workspace_port),
                "F10_RUN_PLAYWRIGHT": "0",
                "UVICORN_BIN": str(uvicorn_wrapper),
            }
        )
        process = subprocess.Popen(
            ["bash", "scripts/run_f10_playwright.sh", str(fixture_root)],
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        gateway = f"http://127.0.0.1:{gateway_port}"
        try:
            ready = False
            deadline = time.time() + 90
            while time.time() < deadline:
                if process.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(f"{gateway}/health", timeout=2) as response:
                        ready = response.status == 200
                    if ready and (fixture_root / "credentials.json").exists():
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            if not ready:
                diagnostics = {}
                for name in ("gateway.log", "deterministic-llm.log", "hermes-workspace.log"):
                    path = fixture_root / name
                    if path.exists():
                        diagnostics[name] = path.read_text(errors="replace")[-3000:]
                if process.poll() is not None and process.stdout is not None:
                    diagnostics["launcher"] = process.stdout.read()[-3000:]
                raise RuntimeError(f"F10_GATEWAY_NOT_READY:{json.dumps(diagnostics, sort_keys=True)}")

            credentials = json.loads((fixture_root / "credentials.json").read_text())
            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            login_status, login = _json_request(
                opener,
                f"{gateway}/auth/password/login",
                {"login": credentials["login"], "password": credentials["password"]},
            )
            if login_status != 200 or not login.get("authenticated"):
                raise RuntimeError("DB_BACKED_PASSWORD_LOGIN_FAILED")

            chat_status, chat = _json_request(
                opener,
                f"{gateway}/api/sessions/eod-db-auth-smoke/chat",
                {
                    "message": "Return one short sentence confirming the authenticated gateway chat path.",
                    "model": "qwen3.5-plus",
                },
            )
            message = chat.get("message")
            if chat_status != 200 or not isinstance(message, str) or not message.strip():
                raise RuntimeError("AUTHENTICATED_GATEWAY_CHAT_FAILED")

            return {
                "status": "PASS",
                "auth": "DB_BACKED_USERNAME_PASSWORD",
                "login_endpoint": "/auth/password/login",
                "chat_endpoint": "/api/sessions/{session_id}/chat",
                "authenticated": True,
                "workspace_slug": login.get("workspace_slug"),
                "gateway_chat_nonempty": True,
                "provider_mode": "F10_DETERMINISTIC_TRANSPORT_ONLY",
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    print(json.dumps(run_smoke(repo_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
