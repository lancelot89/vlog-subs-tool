#!/usr/bin/env python3
"""Cross-platform build helper for PyInstaller packages.

This script mirrors the behaviour of ``scripts/build_binary.sh`` while
remaining runnable on Windows where the shell script is unavailable.

Usage
-----

.. code-block:: bash

    python scripts/build_binary.py windows

The command accepts ``windows`` (default), ``macos`` or ``linux`` as the
target platform.  The script performs a couple of convenience steps that the
shell version already handled:

* ensure PyInstaller is available (install via ``pip`` if necessary)
* clean previously generated ``build`` / ``dist`` directories
* run the appropriate ``pyinstaller`` command (preferring the bundled
  ``*.spec`` files when present)
* optionally build an AppImage on Linux if ``appimagetool`` exists

The implementation intentionally avoids any Unix specific tooling so that the
same workflow can be triggered from ``cmd.exe`` or PowerShell.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"

APP_NAME = "VLog字幕ツール"
WINDOWS_SPEC = ROOT_DIR / "vlog-subs-tool.spec"
MAC_SPEC = ROOT_DIR / "vlog-subs-tool-macos.spec"

# ``--add-data`` uses ``;`` on Windows and ``:`` on other platforms.
ADD_DATA_SEPARATOR = ";" if os.name == "nt" else ":"


def _log(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _run_command(args: Sequence[str]) -> None:
    """Execute a subprocess and raise a helpful error on failure."""

    _log("CMD", " ".join(args))
    completed = subprocess.run(args, cwd=ROOT_DIR)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command {' '.join(args)} failed with exit code {completed.returncode}"
        )


def _ensure_pyinstaller() -> None:
    """Install PyInstaller if it is missing.

    Installing automatically mirrors the behaviour of the shell script which
    attempted to ``pip install pyinstaller`` when not available.  The command
    honours the active Python interpreter so it also works inside virtual
    environments on Windows.
    """

    if shutil.which("pyinstaller") is None:
        _log("WARN", "PyInstaller not found – installing it via pip ...")
        _run_command([sys.executable, "-m", "pip", "install", "pyinstaller"])


def _warn_if_no_virtualenv() -> None:
    """Display a hint when a Python virtual environment is not active."""

    if os.environ.get("GITHUB_ACTIONS") == "true":
        return

    if not os.environ.get("VIRTUAL_ENV"):
        _log(
            "WARN",
            "Python仮想環境がアクティブではありません。`python -m venv venv` での利用を推奨します。",
        )


def _cleanup_previous_build() -> None:
    """Remove previous ``dist``/``build`` directories and stray spec files."""

    for path in (DIST_DIR, BUILD_DIR):
        if path.exists():
            _log("INFO", f"Removing {path}")
            shutil.rmtree(path)

    # Remove auto-generated spec files but keep the curated ones checked into git.
    keep_specs = {
        WINDOWS_SPEC.name,
        MAC_SPEC.name,
        "vlog-subs-tool-debug.spec",
    }
    for spec_file in ROOT_DIR.glob("*.spec"):
        if spec_file.name not in keep_specs:
            _log("INFO", f"Deleting temporary spec file {spec_file}")
            spec_file.unlink()


def _format_add_data(src: Path, target: str) -> str:
    return f"{src}{ADD_DATA_SEPARATOR}{target}"


def _base_pyinstaller_args(dist_subdir: str, build_subdir: str) -> List[str]:
    return [
        "pyinstaller",
        "--distpath",
        str(DIST_DIR / dist_subdir),
        "--workpath",
        str(BUILD_DIR / build_subdir),
    ]


def _fallback_common_args(additional: Iterable[str]) -> List[str]:
    args: List[str] = [
        "--hidden-import",
        "PySide6.QtCore",
        "--hidden-import",
        "PySide6.QtGui",
        "--hidden-import",
        "PySide6.QtWidgets",
        "--hidden-import",
        "paddleocr",
        "--hidden-import",
        "paddle",
        "--hidden-import",
        "cv2",
        "--hidden-import",
        "numpy",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "matplotlib",
        "--noupx",
    ]
    args.extend(additional)
    args.append("app/main.py")
    return args


def _run_pyinstaller_with_spec(
    spec_path: Path, dist_subdir: str, build_subdir: str, fallback_args: Sequence[str]
) -> None:
    base_args = _base_pyinstaller_args(dist_subdir, build_subdir)
    if spec_path.exists():
        _log("INFO", f"Using spec file {spec_path.name}")
        _run_command(base_args + [str(spec_path)])
    else:
        _log("WARN", f"Spec file {spec_path.name} not found. Falling back to command options.")
        _run_command(base_args + list(fallback_args))


def build_windows() -> None:
    fallback = [
        "--onedir",
        "--windowed",
        "--name",
        "vlog-subs-tool",
        "--add-data",
        _format_add_data(Path("README.md"), "."),
    ]
    _run_pyinstaller_with_spec(WINDOWS_SPEC, "windows", "windows", _fallback_common_args(fallback))
    _log("INFO", "Windows build finished: dist/windows/vlog-subs-tool/")


def build_macos() -> None:
    fallback = [
        "--windowed",
        "--name",
        APP_NAME,
        "--add-data",
        _format_add_data(Path("README.md"), "."),
        "--osx-bundle-identifier",
        "com.vlogsubs.tool",
    ]
    _run_pyinstaller_with_spec(MAC_SPEC, "macos", "macos", _fallback_common_args(fallback))
    _log("INFO", f"macOS build finished: dist/macos/{APP_NAME}.app")


def _create_appimage(dist_root: Path) -> None:
    appimage_tool = shutil.which("appimagetool")
    if appimage_tool is None:
        _log("WARN", "appimagetool not found. Skipping AppImage generation.")
        return

    appdir = dist_root / f"{APP_NAME}.AppDir"
    bin_dir = appdir / "usr" / "bin"
    if appdir.exists():
        shutil.rmtree(appdir)
    bin_dir.mkdir(parents=True, exist_ok=True)

    source = dist_root / "vlog-subs-tool"
    if source.exists():
        destination = bin_dir / "vlog-subs-tool"
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)
    else:
        _log("WARN", f"PyInstaller output {source} not found. Skipping AppImage step.")
        return

    desktop_entry = appdir / "vlog-subs-tool.desktop"
    desktop_entry.write_text(
        """[Desktop Entry]
Type=Application
Name=VLog字幕ツール
Comment=VLOG動画字幕抽出・編集・翻訳ツール
Exec=vlog-subs-tool
Icon=vlog-subs-tool
Categories=AudioVideo;Video;
""",
        encoding="utf-8",
    )

    _run_command([appimage_tool, str(appdir), str(dist_root / f"{APP_NAME}-x86_64.AppImage")])


def build_linux() -> None:
    fallback = [
        "--onedir",
        "--windowed",
        "--name",
        "vlog-subs-tool",
        "--add-data",
        _format_add_data(Path("README.md"), "."),
    ]
    _run_pyinstaller_with_spec(WINDOWS_SPEC, "linux", "linux", _fallback_common_args(fallback))

    _create_appimage(DIST_DIR / "linux")
    _log("INFO", "Linux build finished: dist/linux/vlog-subs-tool/")


def _print_file_sizes() -> None:
    if not DIST_DIR.exists():
        return

    _log("INFO", "Generated artefacts:")
    for path in DIST_DIR.rglob("*"):
        if path.is_file() and (
            "vlog-subs-tool" in path.name or path.suffix in {".app", ".AppImage"}
        ):
            size = path.stat().st_size / (1024 * 1024)
            _log("INFO", f"  {path.relative_to(DIST_DIR)}: {size:.1f} MB")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PyInstaller build helper")
    parser.add_argument(
        "platform",
        choices=("windows", "macos", "linux"),
        nargs="?",
        default="windows",
        help="Target platform to build (default: windows)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _log("INFO", f"Starting build for platform: {args.platform}")
    _warn_if_no_virtualenv()
    _ensure_pyinstaller()
    _cleanup_previous_build()

    if args.platform == "windows":
        build_windows()
    elif args.platform == "macos":
        build_macos()
    else:
        build_linux()

    _print_file_sizes()
    _log("INFO", "Build finished successfully.")


if __name__ == "__main__":
    main()
