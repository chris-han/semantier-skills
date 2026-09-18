from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import venv
from typing import Any

SUPPORTED_CRAWLEE_VERSION = "1.10.1"
CORE_REQUIREMENT = f"crawlee=={SUPPORTED_CRAWLEE_VERSION}"
BROWSER_REQUIREMENT = f"crawlee[playwright]=={SUPPORTED_CRAWLEE_VERSION}"
MIN_PYTHON = (3, 10)


def default_runtime_dir() -> Path:
    root = os.environ.get("SEMANTIER_SKILLS_RUNTIME_CACHE")
    if root:
        return Path(root).expanduser() / "resilient-public-data-collection" / f"crawlee-{SUPPORTED_CRAWLEE_VERSION}"
    return Path.home() / ".cache" / "semantier-skills" / "resilient-public-data-collection" / f"crawlee-{SUPPORTED_CRAWLEE_VERSION}"


def venv_python(runtime_dir: Path) -> Path:
    if os.name == "nt":
        return runtime_dir / "venv" / "Scripts" / "python.exe"
    return runtime_dir / "venv" / "bin" / "python"


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)


def installed_crawlee_version(python: Path) -> str | None:
    code = (
        "import importlib.metadata as m;"
        "\ntry: print(m.version('crawlee'))"
        "\nexcept m.PackageNotFoundError: raise SystemExit(7)"
    )
    result = _run([str(python), "-c", code])
    if result.returncode == 7:
        return None
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to query Crawlee version")
    return result.stdout.strip()


def module_available(python: Path, module: str) -> bool:
    result = _run([
        str(python),
        "-c",
        f"import importlib.util,sys; sys.exit(0 if importlib.util.find_spec({module!r}) else 9)",
    ])
    return result.returncode == 0


def verify_core(python: Path) -> None:
    result = _run([
        str(python),
        "-c",
        "from crawlee.crawlers import FileDownloadCrawler; print(FileDownloadCrawler.__name__)",
    ])
    if result.returncode != 0 or "FileDownloadCrawler" not in result.stdout:
        raise RuntimeError(result.stderr.strip() or "Crawlee FileDownloadCrawler verification failed")


def verify_browser_extra(python: Path) -> None:
    result = _run([
        str(python),
        "-c",
        "from crawlee.crawlers import PlaywrightCrawler; import playwright; print(PlaywrightCrawler.__name__)",
    ])
    if result.returncode != 0 or "PlaywrightCrawler" not in result.stdout:
        raise RuntimeError(result.stderr.strip() or "Crawlee Playwright extra verification failed")


def ensure_venv(runtime_dir: Path) -> tuple[Path, bool]:
    python = venv_python(runtime_dir)
    if python.is_file():
        return python, False
    (runtime_dir / "venv").parent.mkdir(parents=True, exist_ok=True)
    venv.EnvBuilder(with_pip=True, clear=False).create(runtime_dir / "venv")
    python = venv_python(runtime_dir)
    if not python.is_file():
        raise RuntimeError(f"venv Python missing after creation: {python}")
    return python, True


def pip_install(python: Path, requirement: str) -> None:
    result = _run([
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        requirement,
    ])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"failed to install {requirement}")


def browser_ready_marker(runtime_dir: Path) -> Path:
    return runtime_dir / "browser-ready.json"


def install_chromium(python: Path, browser_dir: Path, runtime_dir: Path) -> None:
    browser_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
    result = _run([str(python), "-m", "playwright", "install", "chromium"], env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to install Playwright Chromium runtime")
    browser_ready_marker(runtime_dir).write_text(
        json.dumps({
            "crawlee_version": SUPPORTED_CRAWLEE_VERSION,
            "browser": "chromium",
            "playwright_browsers_path": str(browser_dir),
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def prepare_runtime(
    *,
    mode: str = "core",
    runtime_dir: str | Path | None = None,
    plan: bool = False,
    check_only: bool = False,
    offline: bool = False,
    skip_browser_binary: bool = False,
) -> dict[str, Any]:
    if mode not in {"core", "browser"}:
        return {"ok": False, "state": "INVALID_MODE", "mode": mode}
    if sys.version_info < MIN_PYTHON:
        return {
            "ok": False,
            "state": "UNSUPPORTED_PYTHON",
            "required_python": ">=3.10",
            "actual_python": ".".join(map(str, sys.version_info[:3])),
        }

    resolved_runtime = Path(runtime_dir).expanduser().resolve() if runtime_dir else default_runtime_dir().resolve()
    python = venv_python(resolved_runtime)
    requirement = CORE_REQUIREMENT if mode == "core" else BROWSER_REQUIREMENT
    browser_dir = resolved_runtime / "browsers"

    result: dict[str, Any] = {
        "ok": True,
        "state": "PLAN",
        "mode": mode,
        "crawlee_version": SUPPORTED_CRAWLEE_VERSION,
        "requirement": requirement,
        "runtime_dir": str(resolved_runtime),
        "python_executable": str(python),
        "browser_extra": mode == "browser",
        "offline": offline,
        "browser_binary_requested": mode == "browser" and not skip_browser_binary,
        "playwright_browsers_path": str(browser_dir) if mode == "browser" else None,
    }
    if plan:
        return result

    if check_only or offline:
        if not python.is_file():
            result.update(ok=False, state="OFFLINE_CACHE_MISS" if offline else "MISSING_RUNTIME")
            return result
        version = installed_crawlee_version(python)
        if version != SUPPORTED_CRAWLEE_VERSION:
            result.update(
                ok=False,
                state=("OFFLINE_VERSION_MISMATCH" if version else "OFFLINE_CACHE_MISS")
                if offline
                else ("VERSION_MISMATCH" if version else "MISSING_CRAWLEE"),
                installed_version=version,
            )
            return result
        try:
            verify_core(python)
            if mode == "browser":
                verify_browser_extra(python)
                if not skip_browser_binary and not browser_ready_marker(resolved_runtime).is_file():
                    result.update(
                        ok=False,
                        state="OFFLINE_BROWSER_BINARY_MISSING" if offline else "MISSING_BROWSER_BINARY",
                        installed_version=version,
                    )
                    return result
        except RuntimeError as exc:
            result.update(
                ok=False,
                state="OFFLINE_CAPABILITY_MISS" if offline else "CAPABILITY_MISMATCH",
                error=str(exc),
            )
            return result
        result.update(state="READY", installed_version=version, installed_dependency=False)
        return result

    try:
        python, created = ensure_venv(resolved_runtime)
        before = installed_crawlee_version(python)
        installed = False
        if mode == "core":
            if before != SUPPORTED_CRAWLEE_VERSION:
                pip_install(python, CORE_REQUIREMENT)
                installed = True
        else:
            if before != SUPPORTED_CRAWLEE_VERSION or not module_available(python, "playwright"):
                pip_install(python, BROWSER_REQUIREMENT)
                installed = True

        after = installed_crawlee_version(python)
        if after != SUPPORTED_CRAWLEE_VERSION:
            raise RuntimeError(
                f"Crawlee version verification failed: expected {SUPPORTED_CRAWLEE_VERSION}, got {after!r}"
            )
        verify_core(python)
        browser_binary_installed = False
        if mode == "browser":
            verify_browser_extra(python)
            if not skip_browser_binary:
                install_chromium(python, browser_dir, resolved_runtime)
                browser_binary_installed = True
    except RuntimeError as exc:
        installed_version = installed_crawlee_version(python) if python.is_file() else None
        result.update(
            ok=False,
            state="INSTALL_FAILED",
            error=str(exc),
            installed_version=installed_version,
        )
        return result

    result.update(
        state="READY",
        created_runtime=created,
        installed_dependency=installed,
        installed_version=after,
        browser_binary_installed=browser_binary_installed,
    )
    return result


def _exit_code(result: dict[str, Any]) -> int:
    if result.get("ok"):
        return 0
    if result.get("state") == "INSTALL_FAILED":
        return 6
    if result.get("state") == "UNSUPPORTED_PYTHON":
        return 5
    return 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("core", "browser"), default="core")
    parser.add_argument("--runtime-dir")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-browser-binary", action="store_true")
    args = parser.parse_args()
    result = prepare_runtime(
        mode=args.mode,
        runtime_dir=args.runtime_dir,
        plan=args.plan,
        check_only=args.check_only,
        offline=args.offline,
        skip_browser_binary=args.skip_browser_binary,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
