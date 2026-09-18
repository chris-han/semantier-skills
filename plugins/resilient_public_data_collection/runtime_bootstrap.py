#!/usr/bin/env python3
"""Lazily provision the pinned Crawlee runtime used by resilient-public-data-collection.

Runtime isolation prefers stdlib venv when ensurepip is available. On minimal
Debian/Ubuntu Python installations without ensurepip/python3-venv, auto mode
falls back to an isolated target-directory runtime installed with host pip or uv.
Browser dependencies and Chromium remain an explicit separate escalation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

SUPPORTED_CRAWLEE_VERSION = "1.10.1"
CORE_REQUIREMENT = f"crawlee=={SUPPORTED_CRAWLEE_VERSION}"
BROWSER_REQUIREMENT = f"crawlee[playwright]=={SUPPORTED_CRAWLEE_VERSION}"
MIN_PYTHON = (3, 10)
BACKENDS = ("auto", "venv", "target")


def default_runtime_dir() -> Path:
    root = os.environ.get("SEMANTIER_SKILLS_RUNTIME_CACHE")
    if root:
        return Path(root).expanduser() / "data-collection" / f"crawlee-{SUPPORTED_CRAWLEE_VERSION}"
    return Path.home() / ".cache" / "semantier-skills" / "resilient-public-data-collection" / f"crawlee-{SUPPORTED_CRAWLEE_VERSION}"


def venv_python(runtime_dir: Path) -> Path:
    if os.name == "nt":
        return runtime_dir / "venv" / "Scripts" / "python.exe"
    return runtime_dir / "venv" / "bin" / "python"


def target_site_packages(runtime_dir: Path) -> Path:
    return runtime_dir / "target" / "site-packages"


def target_python(runtime_dir: Path) -> Path:
    if os.name == "nt":
        return runtime_dir / "target" / "python.cmd"
    return runtime_dir / "target" / "bin" / "python"


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)


def runtime_backend(runtime_dir: Path) -> str | None:
    if venv_python(runtime_dir).is_file():
        return "venv"
    if target_python(runtime_dir).is_file():
        return "target"
    return None


def runtime_python(runtime_dir: Path) -> Path:
    backend = runtime_backend(runtime_dir)
    if backend == "venv":
        return venv_python(runtime_dir)
    if backend == "target":
        return target_python(runtime_dir)
    return venv_python(runtime_dir)


def _ensurepip_available() -> bool:
    result = run([sys.executable, "-m", "ensurepip", "--version"])
    return result.returncode == 0


def _host_pip_available() -> bool:
    return run([sys.executable, "-m", "pip", "--version"]).returncode == 0


def _uv_path() -> str | None:
    return shutil.which("uv")


def _write_target_launcher(runtime_dir: Path) -> Path:
    site = target_site_packages(runtime_dir)
    launcher = target_python(runtime_dir)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    site.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        launcher.write_text(
            '@echo off\r\n'
            f'set "PYTHONPATH={site};%PYTHONPATH%"\r\n'
            f'"{sys.executable}" %*\r\n',
            encoding="utf-8",
        )
    else:
        import shlex

        launcher.write_text(
            "#!/bin/sh\n"
            f"PYTHONPATH={shlex.quote(str(site))}${{PYTHONPATH:+:$PYTHONPATH}} "
            f"exec {shlex.quote(sys.executable)} \"$@\"\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    return launcher


def installed_crawlee_version(python: Path) -> str | None:
    code = (
        "import importlib.metadata as m;"
        "\ntry: print(m.version('crawlee'))"
        "\nexcept m.PackageNotFoundError: raise SystemExit(7)"
    )
    result = run([str(python), "-c", code])
    if result.returncode == 7:
        return None
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to query Crawlee version")
    return result.stdout.strip()


def module_available(python: Path, module: str) -> bool:
    result = run([
        str(python),
        "-c",
        f"import importlib.util,sys; sys.exit(0 if importlib.util.find_spec({module!r}) else 9)",
    ])
    return result.returncode == 0


def verify_core(python: Path) -> None:
    result = run([
        str(python),
        "-c",
        "from crawlee.crawlers import FileDownloadCrawler; print(FileDownloadCrawler.__name__)",
    ])
    if result.returncode != 0 or "FileDownloadCrawler" not in result.stdout:
        raise RuntimeError(result.stderr.strip() or "Crawlee FileDownloadCrawler verification failed")


def verify_browser_extra(python: Path) -> None:
    result = run([
        str(python),
        "-c",
        "from crawlee.crawlers import PlaywrightCrawler; import playwright; print(PlaywrightCrawler.__name__)",
    ])
    if result.returncode != 0 or "PlaywrightCrawler" not in result.stdout:
        raise RuntimeError(result.stderr.strip() or "Crawlee Playwright extra verification failed")


def _create_venv_runtime(runtime_dir: Path) -> Path:
    if not _ensurepip_available():
        raise RuntimeError("ensurepip unavailable; stdlib venv cannot provision pip")
    venv.EnvBuilder(with_pip=True, clear=False).create(runtime_dir / "venv")
    python = venv_python(runtime_dir)
    if not python.is_file():
        raise RuntimeError(f"venv Python missing after creation: {python}")
    return python


def _create_target_runtime(runtime_dir: Path) -> Path:
    if os.name == "nt":
        # Windows normally ships ensurepip with CPython; target fallback remains
        # available through a command wrapper if required.
        pass
    if not _host_pip_available() and not _uv_path():
        raise RuntimeError(
            "target runtime requires either host 'python -m pip' or 'uv'; "
            "neither installer is available"
        )
    return _write_target_launcher(runtime_dir)


def ensure_runtime(runtime_dir: Path, backend: str) -> tuple[Path, bool, str, str | None]:
    existing = runtime_backend(runtime_dir)
    if existing:
        return runtime_python(runtime_dir), False, existing, None

    if backend == "target":
        python = _create_target_runtime(runtime_dir)
        return python, True, "target", "target backend explicitly requested"

    if backend == "venv":
        python = _create_venv_runtime(runtime_dir)
        return python, True, "venv", None

    try:
        python = _create_venv_runtime(runtime_dir)
        return python, True, "venv", None
    except Exception as exc:
        shutil.rmtree(runtime_dir / "venv", ignore_errors=True)
        fallback_reason = f"{type(exc).__name__}: {exc}"
        python = _create_target_runtime(runtime_dir)
        return python, True, "target", fallback_reason


def install_requirement(runtime_dir: Path, python: Path, backend: str, requirement: str) -> str:
    if backend == "venv":
        result = run([
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            requirement,
        ])
        installer = "venv-pip"
    else:
        site = target_site_packages(runtime_dir)
        site.mkdir(parents=True, exist_ok=True)
        if _host_pip_available():
            result = run([
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--upgrade",
                "--target",
                str(site),
                requirement,
            ])
            installer = "host-pip-target"
        else:
            uv = _uv_path()
            if not uv:
                raise RuntimeError("target runtime installer disappeared after preflight")
            result = run([
                uv,
                "pip",
                "install",
                "--target",
                str(site),
                "--python",
                sys.executable,
                requirement,
            ])
            installer = "uv-target"

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"failed to install {requirement}")
    return installer


def browser_ready_marker(runtime_dir: Path) -> Path:
    return runtime_dir / "browser-ready.json"


def install_chromium(python: Path, browser_dir: Path, runtime_dir: Path) -> None:
    browser_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
    result = run([str(python), "-m", "playwright", "install", "chromium"], env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "failed to install Playwright Chromium runtime")
    browser_ready_marker(runtime_dir).write_text(
        json.dumps({
            "crawlee_version": SUPPORTED_CRAWLEE_VERSION,
            "browser": "chromium",
            "playwright_browsers_path": str(browser_dir),
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("core", "browser"), default="core")
    parser.add_argument("--backend", choices=BACKENDS, default="auto")
    parser.add_argument("--runtime-dir", type=Path, default=default_runtime_dir())
    parser.add_argument("--plan", action="store_true", help="Describe the lazy install without modifying the runtime.")
    parser.add_argument("--check-only", action="store_true", help="Verify the selected runtime is already ready; do not install.")
    parser.add_argument("--offline", action="store_true", help="Reuse cached runtime only; never create a runtime, invoke an installer, or download browser binaries.")
    parser.add_argument(
        "--skip-browser-binary",
        action="store_true",
        help="Browser mode only: install/verify the Playwright Python extra but do not download Chromium.",
    )
    args = parser.parse_args()

    if sys.version_info < MIN_PYTHON:
        print(json.dumps({
            "state": "UNSUPPORTED_PYTHON",
            "required_python": ">=3.10",
            "actual_python": ".".join(map(str, sys.version_info[:3])),
        }, sort_keys=True))
        return 5

    runtime_dir = args.runtime_dir.expanduser().resolve()
    python = runtime_python(runtime_dir)
    detected_backend = runtime_backend(runtime_dir)
    requirement = CORE_REQUIREMENT if args.mode == "core" else BROWSER_REQUIREMENT
    browser_dir = runtime_dir / "browsers"

    plan = {
        "state": "PLAN",
        "mode": args.mode,
        "backend_requested": args.backend,
        "runtime_backend": detected_backend,
        "crawlee_version": SUPPORTED_CRAWLEE_VERSION,
        "requirement": requirement,
        "runtime_dir": str(runtime_dir),
        "python_executable": str(python),
        "browser_extra": args.mode == "browser",
        "offline": args.offline,
        "browser_binary_requested": args.mode == "browser" and not args.skip_browser_binary,
        "playwright_browsers_path": str(browser_dir) if args.mode == "browser" else None,
    }
    if args.plan:
        print(json.dumps(plan, sort_keys=True))
        return 0

    if args.check_only or args.offline:
        if not detected_backend or not python.is_file():
            state = "OFFLINE_CACHE_MISS" if args.offline else "MISSING_RUNTIME"
            print(json.dumps({**plan, "state": state}, sort_keys=True))
            return 4
        version = installed_crawlee_version(python)
        if version != SUPPORTED_CRAWLEE_VERSION:
            print(json.dumps({
                **plan,
                "runtime_backend": detected_backend,
                "python_executable": str(python),
                "state": ("OFFLINE_VERSION_MISMATCH" if version else "OFFLINE_CACHE_MISS") if args.offline else ("VERSION_MISMATCH" if version else "MISSING_CRAWLEE"),
                "installed_version": version,
            }, sort_keys=True))
            return 4
        try:
            verify_core(python)
            if args.mode == "browser":
                verify_browser_extra(python)
                if not args.skip_browser_binary and not browser_ready_marker(runtime_dir).is_file():
                    state = "OFFLINE_BROWSER_BINARY_MISSING" if args.offline else "MISSING_BROWSER_BINARY"
                    print(json.dumps({
                        **plan,
                        "runtime_backend": detected_backend,
                        "python_executable": str(python),
                        "state": state,
                        "installed_version": version,
                    }, sort_keys=True))
                    return 4
        except RuntimeError as exc:
            state = "OFFLINE_CAPABILITY_MISS" if args.offline else "CAPABILITY_MISMATCH"
            print(json.dumps({**plan, "runtime_backend": detected_backend, "state": state, "error": str(exc)}, sort_keys=True))
            return 4
        print(json.dumps({
            **plan,
            "state": "READY",
            "runtime_backend": detected_backend,
            "python_executable": str(python),
            "installed_version": version,
            "installed_dependency": False,
        }, sort_keys=True))
        return 0

    try:
        python, created, selected_backend, fallback_reason = ensure_runtime(runtime_dir, args.backend)
        before = installed_crawlee_version(python)
        installed = False
        installer = None

        if args.mode == "core":
            if before != SUPPORTED_CRAWLEE_VERSION:
                installer = install_requirement(runtime_dir, python, selected_backend, CORE_REQUIREMENT)
                installed = True
        else:
            if before != SUPPORTED_CRAWLEE_VERSION or not module_available(python, "playwright"):
                installer = install_requirement(runtime_dir, python, selected_backend, BROWSER_REQUIREMENT)
                installed = True

        after = installed_crawlee_version(python)
        if after != SUPPORTED_CRAWLEE_VERSION:
            raise RuntimeError(
                f"Crawlee version verification failed: expected {SUPPORTED_CRAWLEE_VERSION}, got {after!r}"
            )

        verify_core(python)
        browser_binary_installed = False
        if args.mode == "browser":
            verify_browser_extra(python)
            if not args.skip_browser_binary:
                install_chromium(python, browser_dir, runtime_dir)
                browser_binary_installed = True
    except Exception as exc:
        current_python = runtime_python(runtime_dir)
        installed_version = None
        if current_python.is_file():
            try:
                installed_version = installed_crawlee_version(current_python)
            except Exception:
                installed_version = None
        print(json.dumps({
            **plan,
            "state": "INSTALL_FAILED",
            "error": str(exc),
            "runtime_backend": runtime_backend(runtime_dir),
            "python_executable": str(current_python),
            "installed_version": installed_version,
        }, sort_keys=True))
        return 6

    print(json.dumps({
        **plan,
        "state": "READY",
        "runtime_backend": selected_backend,
        "fallback_reason": fallback_reason,
        "python_executable": str(python),
        "created_runtime": created,
        "installed_dependency": installed,
        "installer": installer,
        "installed_version": after,
        "browser_binary_installed": browser_binary_installed,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
