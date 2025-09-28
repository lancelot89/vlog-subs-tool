#!/usr/bin/env python3
"""VLog字幕ツールのエントリーポイント。

同梱Python環境からの起動と従来のソースコード実行の両方をサポートする。
"""

from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any, List, Tuple, Union

CURRENT_LOG_FILE: Path | None = None


def is_console_available() -> bool:
    """
    コンソールが利用可能かどうかを判定
    """
    try:
        # PyInstallerのコンソール設定を確認
        if getattr(sys, "frozen", False):
            # 標準入力がアクセス可能かテスト
            if hasattr(sys.stdin, "fileno"):
                return True
            # Windowsでコンソールが割り当てられているかチェック
            if sys.platform == "win32":
                import msvcrt

                try:
                    msvcrt.kbhit()
                    return True
                except OSError:
                    return False
        # 非frozen環境では通常利用可能
        return True
    except:
        return False


def safe_input_prompt(message: str = "Press Enter to continue...") -> None:
    """
    安全なinputプロンプト（コンソールが利用可能な場合のみ）
    """
    if is_console_available():
        try:
            input(message)
        except (EOFError, OSError):
            pass  # コンソールエラーは無視


def get_user_log_dir(log_dir_override: Path | None = None) -> Path:
    """Resolve the log directory under the current user's profile."""

    if log_dir_override is not None:
        return log_dir_override

    home = Path.home()

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return base / "VlogSubsTool" / "logs"

    if sys.platform == "darwin":
        return home / "Library" / "Logs" / "vlog-subs-tool"

    state_home = Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state"))
    return state_home / "vlog-subs-tool" / "logs"


def setup_logging(log_dir_override: Path | None = None) -> Path:
    """Configure logging so that launch diagnostics reach the user folder."""

    global CURRENT_LOG_FILE

    log_dir = get_user_log_dir(log_dir_override)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "vlog-subs-tool-debug.log"

    handlers: List[Union[logging.FileHandler, logging.StreamHandler]] = [
        logging.FileHandler(log_file, encoding="utf-8")
    ]

    if is_console_available():
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )

    CURRENT_LOG_FILE = log_file

    logger = logging.getLogger(__name__)
    logger.info("=== VLog字幕ツール ログ開始 ===")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform: {sys.platform}")
    logger.info(f"Executable: {sys.executable}")
    logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")
    if hasattr(sys, "_MEIPASS"):
        logger.info(f"_MEIPASS: {sys._MEIPASS}")
    logger.info(f"Log file: {log_file}")

    log_dependency_versions(logger)

    return log_file


def log_dependency_versions(logger: logging.Logger) -> None:
    """Log pinned dependency versions for support diagnostics."""

    packages = [
        "PySide6",
        "opencv-python",
        "ffmpeg-python",
        "paddlepaddle",
        "paddleocr",
        "pytesseract",
        "torch",
        "ctranslate2",
        "transformers",
        "sentencepiece",
        "langdetect",
        "opencc-python-reimplemented",
        "pandas",
        "numpy",
        "python-bidi",
        "pysrt",
        "PyYAML",
        "Pillow",
        "loguru",
        "tqdm",
        "requests",
        "psutil",
    ]

    for package in packages:
        try:
            version = importlib_metadata.version(package)
            logger.info("Dependency check: %s==%s", package, version)
        except importlib_metadata.PackageNotFoundError:
            logger.warning("Dependency missing: %s (not installed)", package)


def setup_paths() -> bool:
    """
    実行環境に応じてパスを設定
    PyInstallerでビルドされたバイナリとソースコード実行の両方に対応
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # PyInstallerでビルドされたバイナリの場合
        base_dir = Path(sys._MEIPASS)
        app_dir = base_dir

        # スタンドアロンバイナリのパス設定
        sys.path.insert(0, str(base_dir))
        sys.path.insert(0, str(app_dir))

        return True  # スタンドアロン実行
    else:
        # ソースコード実行の場合
        app_dir = Path(__file__).parent
        project_root = app_dir.parent

        # 開発環境のパス設定
        sys.path.insert(0, str(project_root))
        sys.path.insert(0, str(app_dir))

        return False  # 開発環境実行


def test_imports(logger: Any) -> bool:
    """段階的インポートテスト"""
    logger.info("=== 段階的インポートテスト開始 ===")

    # Stage 1: 基本Pythonモジュール
    try:
        import csv
        import json
        import os
        import pathlib
        import sys

        logger.info("✅ Stage 1: 基本Pythonモジュール - OK")
    except Exception as e:
        logger.error(f"❌ Stage 1: 基本Pythonモジュール - {e}")
        return False

    # Stage 2: PySide6基本インポート
    try:
        import PySide6

        logger.info(f"✅ Stage 2: PySide6インポート - OK (version: {PySide6.__version__})")
    except Exception as e:
        logger.error(f"❌ Stage 2: PySide6インポート - {e}")
        return False

    # Stage 3: PySide6.QtWidgets
    try:
        from PySide6.QtWidgets import QApplication, QMainWindow

        logger.info("✅ Stage 3: PySide6.QtWidgets - OK")
    except Exception as e:
        logger.error(f"❌ Stage 3: PySide6.QtWidgets - {e}")
        return False

    # Stage 4: 重要ライブラリ
    try:
        import cv2
        import numpy
        import PIL

        logger.info("✅ Stage 4: OpenCV, NumPy, PIL - OK")
    except Exception as e:
        logger.error(f"❌ Stage 4: 重要ライブラリ - {e}")
        return False

    # Stage 5: アプリケーションモジュール
    try:
        import importlib

        try:
            main_module = importlib.import_module("app.ui.main_window")
        except (ImportError, ModuleNotFoundError):
            main_module = importlib.import_module("ui.main_window")

        # Check if main function exists
        if hasattr(main_module, "main"):
            logger.info("✅ Stage 5: アプリケーションモジュール - OK")
            return True
        else:
            logger.error("❌ Stage 5: main function not found")
            return False
    except Exception as e:
        logger.error(f"❌ Stage 5: アプリケーションモジュール - {e}")
        return False


def parse_launch_arguments(argv: List[str]) -> Tuple[argparse.Namespace, List[str]]:
    """Parse command line arguments, keeping Qt arguments intact."""

    parser = argparse.ArgumentParser(
        add_help=True,
        description="VLog字幕ツール ランチャー",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run dependency diagnostics and exit.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Override the directory where launch logs are written.",
    )

    args, remaining = parser.parse_known_args(argv)
    return args, remaining


def main(argv: List[str] | None = None) -> None:
    """メインエントリーポイント"""
    argv = list(sys.argv[1:] if argv is None else argv)
    args, remaining_args = parse_launch_arguments(argv)

    # PyInstallerバイナリ実行時の安全対策（PaddleXエラー対策）
    import multiprocessing

    multiprocessing.freeze_support()

    log_file = setup_logging(args.log_dir)
    logger = logging.getLogger(__name__)
    logger.info("メインエントリーポイント開始")
    logger.info("multiprocessing.freeze_support() 実行完了")

    # Issue #207 対応: PaddleOCRのcpp_extension問題を防止（PaddleX不使用）
    # バイナリ実行時のPaddleOCR環境設定のみを事前に適用
    try:
        from app.core.paddlex_init_guard import (
            complete_binary_initialization,
            get_paddleocr_init_status,
            setup_paddleocr_environment_for_binary,
        )

        # バイナリ実行時の環境設定を適用
        setup_paddleocr_environment_for_binary()

        # 初期化状態をログ出力
        init_status = get_paddleocr_init_status()
        logger.info(f"PaddleOCR environment setup status: {init_status}")

    except Exception as e:
        logger.warning(f"PaddleOCR environment setup failed: {e}")
        # 環境設定が失敗してもアプリは継続実行

    is_standalone = setup_paths()
    logger.info(f"実行環境: {'スタンドアロン' if is_standalone else 'ソースコード'}")

    if args.check:
        logger.info("--check オプションが指定されたため、診断のみを実行します")
        success = test_imports(logger)
        if success:
            logger.info("環境診断が正常に完了しました")
            print("✅ VLog字幕ツール 環境診断が完了しました。")
            print(f"   ログファイル: {log_file}")
            sys.exit(0)
        logger.error("環境診断で問題が見つかりました")
        print("❌ VLog字幕ツール 環境診断で問題が見つかりました。詳細はログを参照してください。")
        print(f"   ログファイル: {log_file}")
        sys.exit(1)

    try:
        # デバッグ: 段階的インポートテスト
        if not test_imports(logger):
            logger.error("段階的インポートテストに失敗しました")
            if getattr(sys, "frozen", False):
                safe_input_prompt("Press Enter to continue...")  # コンソール版で確認
            sys.exit(1)

        # メインアプリケーション起動
        logger.info("アプリケーション起動開始")

        import importlib

        try:
            main_module = importlib.import_module("app.ui.main_window")
        except (ImportError, ModuleNotFoundError):
            main_module = importlib.import_module("ui.main_window")

        logger.info("UIモジュール読み込み完了、アプリケーション起動中...")
        sys.argv = [sys.argv[0]] + remaining_args
        main_module.main()
        logger.info("アプリケーション正常終了")

    except ModuleNotFoundError as e:
        logger.error(f"ModuleNotFoundError: {e}")
        logger.error(traceback.format_exc())
        if is_standalone:
            show_standalone_error(e)
        else:
            show_source_error(e)

        if getattr(sys, "frozen", False):
            safe_input_prompt("Press Enter to continue...")
        sys.exit(1)

    except ImportError as e:
        logger.error(f"ImportError: {e}")
        logger.error(traceback.format_exc())
        if is_standalone:
            show_standalone_error(e)
        else:
            show_package_error(e)

        if getattr(sys, "frozen", False):
            safe_input_prompt("Press Enter to continue...")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())

        print(f"❌ 予期しないエラーが発生しました: {e}")
        print()
        print("🔧 詳細ログ:")
        log_hint = CURRENT_LOG_FILE if CURRENT_LOG_FILE is not None else "(ログファイル未設定)"
        print(f"   ログファイル: {log_hint}")
        print()
        print("🔧 解決方法:")
        print("- アプリケーションを再起動してください")
        print("- 問題が続く場合は以下にご報告ください:")
        print("  https://github.com/lancelot89/vlog-subs-tool/issues")

        if getattr(sys, "frozen", False):
            safe_input_prompt("Press Enter to continue...")
        sys.exit(1)


def show_standalone_error(error: Exception) -> None:
    """スタンドアロンバイナリ実行時のエラー表示"""
    print("❌ エラー: バイナリファイルに問題があります")
    print()
    print("🔧 解決方法:")
    print("1. バイナリファイルを再ダウンロード:")
    print("   https://github.com/lancelot89/vlog-subs-tool/releases/latest")
    print()
    print("2. ウイルス対策ソフトでスキャン後、再実行")
    print()
    print("3. 問題が続く場合はIssueを報告:")
    print("   https://github.com/lancelot89/vlog-subs-tool/issues")
    print()
    print(f"🐛 詳細エラー: {error}")


def show_source_error(error: Exception) -> None:
    """ソースコード実行時の依存関係エラー表示"""
    print("❌ エラー: 依存関係が不足しているか、実行方法に問題があります")
    print()
    print("🔧 解決方法:")
    print("1. 依存関係をインストール:")
    print("   pip install -e .")
    print()
    print("2. 推奨実行方法:")
    print("   python -m app.main")
    print()
    print("3. または、プロジェクトルートから:")
    print("   python app/main.py")
    print()
    print("📋 詳細なインストール手順:")
    print("   https://github.com/lancelot89/vlog-subs-tool#インストール")
    print()
    print(f"🐛 元のエラー: {error}")


def show_package_error(error: Exception) -> None:
    """パッケージインストールエラー表示"""
    print("❌ エラー: 必要なパッケージがインストールされていません")
    print()
    print("🔧 解決方法:")
    print("1. 仮想環境を作成 (推奨):")
    print("   python -m venv venv")
    print("   source venv/bin/activate  # Linux/macOS")
    print("   # venv\\Scripts\\activate   # Windows")
    print()
    print("2. 依存関係をインストール:")
    print("   pip install -e .")
    print()
    print("3. アプリケーションを起動:")
    print("   python -m app.main")
    print()
    print(f"🐛 元のエラー: {error}")


if __name__ == "__main__":
    main()
