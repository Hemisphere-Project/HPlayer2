#!/usr/bin/env python3
"""Clone and build the local CZMQ and Zyre dependencies.

This script keeps the ZeroMQ helper libraries up to date so ``uv sync`` can
install the bundled Python bindings that live under ``scripts/czmq`` and
``scripts/zyre``.  It defaults to installing the shared libraries into the
user's ``~/.local`` prefix to avoid requiring root access.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPOS: dict[str, str] = {
    "czmq": "https://github.com/zeromq/czmq.git",
    "zyre": "https://github.com/zeromq/zyre.git",
}

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DEFAULT_PREFIX = Path.home() / ".local"


class StepError(RuntimeError):
    """Raised when a build step fails."""


def run(cmd: Iterable[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"→ {' '.join(cmd)}", flush=True)
    try:
        subprocess.run(cmd, cwd=cwd, env=env, check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - logging
        raise StepError(f"Command {' '.join(cmd)} failed with code {exc.returncode}") from exc


def ensure_git_repo(name: str, url: str, depth: int) -> Path:
    dest = SCRIPTS / name
    if dest.exists() and (dest / ".git").exists():
        print(f"Updating {name}…", flush=True)
        run(["git", "fetch", "--depth", str(depth)], dest)
        run(["git", "reset", "--hard", "FETCH_HEAD"], dest)
    elif dest.exists():
        raise StepError(f"Directory {dest} exists but is not a git repository")
    else:
        print(f"Cloning {name} into {dest}…", flush=True)
        run(["git", "clone", "--depth", str(depth), url, str(dest)], ROOT)
    return dest


def build_repo(path: Path, prefix: Path, jobs: int) -> None:
    env = os.environ.copy()
    pkg_path = prefix / "lib" / "pkgconfig"
    env["PKG_CONFIG_PATH"] = f"{pkg_path}:{env.get('PKG_CONFIG_PATH', '')}" if pkg_path.exists() else env.get("PKG_CONFIG_PATH", "")

    run(["./autogen.sh"], path, env)
    run(["./configure", f"--prefix={prefix}"], path, env)
    run(["make", f"-j{jobs}"], path, env)
    run(["make", "install"], path, env)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap CZMQ and Zyre dependencies")
    parser.add_argument(
        "--prefix",
        type=Path,
        default=DEFAULT_PREFIX,
        help="Installation prefix for the compiled libraries (default: ~/.local)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=max(1, os.cpu_count() or 1),
        help="Parallel build jobs to pass to make",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Only ensure repositories are cloned without running autogen/configure/make",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="Clone depth used for git fetch/clone",
    )
    args = parser.parse_args(argv)

    if shutil.which("git") is None:
        raise StepError("git is required to bootstrap the native dependencies")

    if not SCRIPTS.exists():
        raise StepError(f"Scripts directory not found at {SCRIPTS}")

    prefix = args.prefix.expanduser().resolve()
    prefix.mkdir(parents=True, exist_ok=True)

    for name, url in REPOS.items():
        repo_path = ensure_git_repo(name, url, args.depth)
        if args.skip_build:
            continue
        print(f"Building {name} with prefix {prefix}…", flush=True)
        build_repo(repo_path, prefix, args.jobs)

    pkg_config_hint = prefix / "lib" / "pkgconfig"
    if pkg_config_hint.exists():
        print(
            "Set PKG_CONFIG_PATH to include",
            pkg_config_hint,
            "before running 'uv sync', e.g.:",
            flush=True,
        )
        print(f"  export PKG_CONFIG_PATH={pkg_config_hint}:${{PKG_CONFIG_PATH:-}}", flush=True)

    print("Native dependency bootstrap complete.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except StepError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
