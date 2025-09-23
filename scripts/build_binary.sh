#!/usr/bin/env bash

# Minimal PyInstaller build helper.
# Usage examples:
#   ./scripts/build_binary.sh                 # auto-detect platform
#   ./scripts/build_binary.sh linux           # explicit positional argument
#   ./scripts/build_binary.sh --platform mac  # explicit flag

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PLATFORM=""

print_help() {
    cat <<'USAGE'
Usage: build_binary.sh [--platform <linux|macos|windows>] [--help]

Creates an onedir build that mirrors running the source tree.  The build is
performed with the tracked vlog-subs-tool.spec file without any additional
flags so the output matches the developer workflow.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform|-p)
            if [[ $# -lt 2 ]]; then
                echo "error: --platform requires a value" >&2
                exit 1
            fi
            PLATFORM="$2"
            shift 2
            ;;
        --help|-h)
            print_help
            exit 0
            ;;
        --*)
            echo "error: unknown option $1" >&2
            exit 1
            ;;
        *)
            if [[ -z "$PLATFORM" ]]; then
                PLATFORM="$1"
                shift
            else
                echo "error: unexpected argument $1" >&2
                exit 1
            fi
            ;;
    esac
done

if [[ -z "$PLATFORM" || "$PLATFORM" == "auto" ]]; then
    case "$(uname -s 2>/dev/null || echo unknown)" in
        Linux)
            PLATFORM="linux"
            ;;
        Darwin)
            PLATFORM="macos"
            ;;
        CYGWIN*|MINGW*|MSYS*)
            PLATFORM="windows"
            ;;
        *)
            PLATFORM="local"
            ;;
    esac
fi

case "${PLATFORM}" in
    linux|Linux)
        PLATFORM="linux"
        ;;
    mac|macos|darwin|osx)
        PLATFORM="macos"
        ;;
    win|windows|windows_nt)
        PLATFORM="windows"
        ;;
    local)
        PLATFORM="local"
        ;;
    *)
        echo "error: unsupported platform '${PLATFORM}'" >&2
        exit 1
        ;;
esac

DIST_DIR="dist/${PLATFORM}"
BUILD_DIR="build/${PLATFORM}"

mkdir -p "${DIST_DIR}" "${BUILD_DIR}"

if ! command -v pyinstaller >/dev/null 2>&1; then
    echo "error: pyinstaller is not available. Install it with 'pip install pyinstaller'." >&2
    exit 1
fi

echo "[build] PyInstaller ${PLATFORM} onedir build"
pyinstaller --clean \
    --distpath "${DIST_DIR}" \
    --workpath "${BUILD_DIR}" \
    vlog-subs-tool.spec

OUTPUT_DIR="${DIST_DIR}/vlog-subs-tool"
if [[ -d "${OUTPUT_DIR}" ]]; then
    if [[ -f "${OUTPUT_DIR}/vlog-subs-tool.exe" ]]; then
        LAUNCHER="${OUTPUT_DIR}/vlog-subs-tool.exe"
    elif [[ -f "${OUTPUT_DIR}/vlog-subs-tool" ]]; then
        LAUNCHER="${OUTPUT_DIR}/vlog-subs-tool"
    else
        LAUNCHER="${OUTPUT_DIR}"
    fi
    echo "[build] Output directory: ${OUTPUT_DIR}" >&2
    echo "[build] Launcher:        ${LAUNCHER}" >&2
else
    echo "warning: build output not found at ${OUTPUT_DIR}" >&2
fi
