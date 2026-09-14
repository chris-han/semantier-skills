from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    status: str
    detail: str


def _run(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def inspect_hermes_provider_status(repo_root: Path) -> dict[str, Any]:
    hermes = repo_root / "hermes-agent" / "hermes"
    python_cmd = ["uv", "run", "--extra", "dev", "python", str(hermes)]
    providers = []
    for provider in ("openai-codex", "alibaba"):
        code, stdout, stderr = _run(python_cmd + ["auth", "status", provider], cwd=repo_root)
        text = stdout or stderr
        status = "ready" if code == 0 and "logged out" not in text.lower() else "unavailable"
        providers.append(ProviderStatus(provider=provider, status=status, detail=text))

    any_ready = any(item.status == "ready" for item in providers)
    return {
        "status": "READY" if any_ready else "BLOCKED_EXTERNAL_PROVIDER_CONFIGURATION",
        "providers": [asdict(item) for item in providers],
        "environment_hints": {
            "DASHSCOPE_API_KEY_present": bool(os.environ.get("DASHSCOPE_API_KEY")),
            "OPENROUTER_API_KEY_present": bool(os.environ.get("OPENROUTER_API_KEY")),
            "OPENAI_API_KEY_present": bool(os.environ.get("OPENAI_API_KEY")),
        },
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    result = inspect_hermes_provider_status(repo_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "READY" else 2)


if __name__ == "__main__":
    main()
