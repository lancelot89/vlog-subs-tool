#!/bin/bash

# VLog字幕ツール バイナリビルドスクリプト
# 使用方法: ./scripts/build_binary.sh [platform]
# platform: windows, macos, linux, all

set -e

# 設定
APP_NAME="VLog字幕ツール"
VERSION="1.2.0"  # Linux最適化、ベンチマーク、CPU profilerに対応
DIST_DIR="dist"
BUILD_DIR="build"

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 環境確認
check_environment() {
    log_info "環境確認中..."

    # Python仮想環境確認（GitHub Actionsの場合はスキップ）
    if [[ "$VIRTUAL_ENV" == "" && "$GITHUB_ACTIONS" != "true" ]]; then
        log_error "仮想環境が有効化されていません"
        log_info "以下のコマンドを実行してください："
        log_info "source venv/bin/activate"
        exit 1
    fi

    # Python バージョン確認
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [[ "$python_version" < "3.12" ]]; then
        log_warn "Python 3.12以降を推奨します（現在: $python_version）"
    fi

    # PyInstaller確認
    if ! command -v pyinstaller &> /dev/null; then
        log_warn "PyInstallerがインストールされていません。インストール中..."
        pip install pyinstaller>=6.15.0
    fi

    # 重要な依存関係確認
    log_info "重要な依存関係の確認中..."
    python3 -c "import PySide6, paddleocr, cv2, numpy, pandas, psutil" 2>/dev/null || {
        log_error "必要な依存関係が不足しています。requirements.txtまたはpyproject.tomlから再インストールしてください"
        exit 1
    }

    log_info "環境確認完了 (Python $python_version)"
}

# クリーンアップ
cleanup() {
    log_info "前回のビルドファイルをクリーンアップ中..."
    rm -rf "$BUILD_DIR" "$DIST_DIR"
    # 自動生成されたspecファイルのみ削除（手動作成したspecファイルは保持）
    find . -name "*.spec" \
        -not -name "vlog-subs-tool.spec" \
        -not -name "vlog-subs-tool-macos.spec" \
        -not -name "temp-macos.spec" \
        -delete 2>/dev/null || true
}

# Windowsビルド
build_windows() {
    log_info "Windows用バイナリをビルド中..."

    # specファイルが存在する場合はそれを使用
    if [[ -f "vlog-subs-tool.spec" ]]; then
        log_info "specファイルを使用してビルド中..."
        pyinstaller \
            --distpath "$DIST_DIR/windows" \
            --workpath "$BUILD_DIR/windows" \
            vlog-subs-tool.spec
    else
        log_warn "specファイルが見つかりません。従来の方法でビルド..."
        pyinstaller \
            --onedir \
            --windowed \
            --name "vlog-subs-tool" \
            --distpath "$DIST_DIR/windows" \
            --workpath "$BUILD_DIR/windows" \
            --add-data "README.md:." \
            --hidden-import "PySide6.QtCore" \
            --hidden-import "PySide6.QtGui" \
            --hidden-import "PySide6.QtWidgets" \
            --hidden-import "paddleocr" \
            --hidden-import "paddle" \
            --hidden-import "paddlex" \
            --hidden-import "cv2" \
            --hidden-import "numpy" \
            --hidden-import "psutil" \
            --exclude-module "tkinter" \
            --exclude-module "matplotlib" \
            --noupx \
            app/main.py
    fi

    log_info "Windows用バイナリ完成: $DIST_DIR/windows/vlog-subs-tool/"
}

# macOSビルド
build_macos() {
    log_info "macOS用バイナリをビルド中..."

    # macOS専用specファイルが存在する場合はそれを優先使用
    if [[ -f "vlog-subs-tool-macos.spec" ]]; then
        log_info "macOS専用specファイルを使用してビルド中..."
        pyinstaller \
            --distpath "$DIST_DIR/macos" \
            --workpath "$BUILD_DIR/macos" \
            vlog-subs-tool-macos.spec
    elif [[ -f "vlog-subs-tool.spec" ]]; then
        log_info "汎用specファイルを使用してビルド中..."
        # 汎用specファイルをmacOS用に一時変更
        sed 's/name='\''vlog-subs-tool'\''/name='\''VLog字幕ツール'\''/' vlog-subs-tool.spec > temp-macos.spec
        pyinstaller \
            --distpath "$DIST_DIR/macos" \
            --workpath "$BUILD_DIR/macos" \
            temp-macos.spec
        rm -f temp-macos.spec
    else
        log_warn "specファイルが見つかりません。従来の方法でビルド..."
        pyinstaller \
            --windowed \
            --name "$APP_NAME" \
            --distpath "$DIST_DIR/macos" \
            --workpath "$BUILD_DIR/macos" \
            --add-data "README.md:." \
            --hidden-import "PySide6.QtCore" \
            --hidden-import "PySide6.QtGui" \
            --hidden-import "PySide6.QtWidgets" \
            --hidden-import "paddleocr" \
            --hidden-import "paddle" \
            --hidden-import "paddlex" \
            --hidden-import "cv2" \
            --hidden-import "numpy" \
            --hidden-import "psutil" \
            --exclude-module "tkinter" \
            --exclude-module "matplotlib" \
            --noupx \
            --osx-bundle-identifier "com.vlogsubs.tool" \
            app/main.py
    fi

    log_info "macOS用バイナリ完成: $DIST_DIR/macos/$APP_NAME.app"
}

# Linuxビルド
build_linux() {
    log_info "Linux用バイナリをビルド中..."

    # specファイルが存在する場合はそれを使用
    if [[ -f "vlog-subs-tool.spec" ]]; then
        log_info "specファイルを使用してビルド中..."
        pyinstaller \
            --distpath "$DIST_DIR/linux" \
            --workpath "$BUILD_DIR/linux" \
            vlog-subs-tool.spec
    else
        log_warn "specファイルが見つかりません。従来の方法でビルド..."
        pyinstaller \
            --onedir \
            --windowed \
            --name "vlog-subs-tool" \
            --distpath "$DIST_DIR/linux" \
            --workpath "$BUILD_DIR/linux" \
            --add-data "README.md:." \
            --hidden-import "PySide6.QtCore" \
            --hidden-import "PySide6.QtGui" \
            --hidden-import "PySide6.QtWidgets" \
            --hidden-import "paddleocr" \
            --hidden-import "paddle" \
            --hidden-import "paddlex" \
            --hidden-import "cv2" \
            --hidden-import "numpy" \
            --hidden-import "psutil" \
            --exclude-module "tkinter" \
            --exclude-module "matplotlib" \
            --noupx \
            app/main.py
    fi

    # AppImage作成（オプション）
    if command -v appimagetool &> /dev/null; then
        log_info "AppImage作成中..."
        create_appimage
    else
        log_warn "AppImageToolが見つかりません。通常のバイナリのみ作成"
    fi

    log_info "Linux用バイナリ完成: $DIST_DIR/linux/vlog-subs-tool/"
}

# AppImage作成
create_appimage() {
    APPDIR="$DIST_DIR/linux/VLog字幕ツール.AppDir"
    mkdir -p "$APPDIR/usr/bin"
    
    # バイナリコピー
    cp "$DIST_DIR/linux/vlog-subs-tool" "$APPDIR/usr/bin/"
    
    # デスクトップファイル作成
    cat > "$APPDIR/vlog-subs-tool.desktop" << EOF
[Desktop Entry]
Type=Application
Name=VLog字幕ツール
Comment=VLOG動画字幕抽出・編集・翻訳ツール
Exec=vlog-subs-tool
Icon=vlog-subs-tool
Categories=AudioVideo;Video;
EOF
    
    # AppImage作成
    appimagetool "$APPDIR" "$DIST_DIR/linux/VLog字幕ツール-x86_64.AppImage"
}

# ファイルサイズ確認
check_file_sizes() {
    log_info "生成されたファイルサイズ:"
    find "$DIST_DIR" -name "*vlog-subs-tool*" -o -name "*.app" -o -name "*.AppImage" | while read file; do
        if [[ -f "$file" ]]; then
            size=$(du -h "$file" | cut -f1)
            echo "  $file: $size"
        elif [[ -d "$file" ]]; then
            size=$(du -sh "$file" | cut -f1)
            echo "  $file/: $size (directory)"
        fi
    done

    # 予想サイズ情報を表示
    log_info "予想配布サイズ (PaddleOCRモデル込み):"
    log_info "  Linux/Windows: ~300-400MB"
    log_info "  macOS: ~350-450MB"
}

# メイン処理
main() {
    local platform="${1:-linux}"

    log_info "VLog字幕ツール バイナリビルド開始"
    log_info "バージョン: $VERSION"
    log_info "プラットフォーム: $platform"

    # デバッグモードの確認
    if [[ "${VLOG_SUBS_DEBUG:-false}" == "true" ]]; then
        log_warn "デバッグモードでビルドします（コンソール表示有効）"
    else
        log_info "本番モードでビルドします（コンソール表示無効）"
    fi

    check_environment
    cleanup
    
    case "$platform" in
        windows)
            build_windows
            ;;
        macos)
            build_macos
            ;;
        linux)
            build_linux
            ;;
        all)
            build_linux
            log_warn "クロスプラットフォームビルドには各OS環境が必要です"
            ;;
        *)
            log_error "不正なプラットフォーム: $platform"
            log_info "使用可能なプラットフォーム: windows, macos, linux, all"
            exit 1
            ;;
    esac
    
    check_file_sizes
    log_info "ビルド完了！"
}

# スクリプト実行
main "$@"