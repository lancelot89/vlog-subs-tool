"""PyInstaller hook to ensure paddlex data files ship with the binary.

paddlex lazily reads its `.version` marker along with various configuration
files when imported.  PyInstaller does not automatically collect dotfiles, so
building without an explicit hook leads to runtime FileNotFoundError on
`paddlex/.version` once the app is frozen.  This hook mirrors the subset of
files the package loads dynamically and registers all of its lazy imports so
`paddleocr` can depend on them safely.
"""

from __future__ import annotations

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

_datas = []
_hiddenimports = []

try:
    # Collect the `.version` marker alongside the lightweight configs paddlex
    # touches when bootstrapping.  The explicit patterns keep the hook fast
    # while still covering nested resources.
    _datas.extend(
        collect_data_files(
            "paddlex",
            includes=[
                ".version",
                "*.version",
                "**/.version",
                "**/*.json",
                "**/*.yml",
                "**/*.yaml",
                "**/*.txt",
            ],
        )
    )

    # paddlex exposes optional helper modules that paddleocr imports lazily.
    # Register all of them so PyInstaller pulls the bytecode into the build.
    _hiddenimports.extend(collect_submodules("paddlex"))
except ModuleNotFoundError:
    # The project does not always install paddlex (it is an optional
    # dependency).  Allow the build to continue without it; if the package is
    # missing at runtime paddleocr will gracefully fall back to the pure
    # PaddlePaddle path.
    pass

# PyInstaller expects module-level names `datas` and `hiddenimports`.
datas = _datas
hiddenimports = _hiddenimports
