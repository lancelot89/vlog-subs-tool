#!/usr/bin/env python3
"""
VLog字幕ツール メインエントリーポイント
PyInstaller バイナリとソースコード実行の両方に対応
"""

import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


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


def setup_logging() -> None:
    """
    デバッグ用ロギング設定
    """
    # ログファイルのパス設定
    if getattr(sys, "frozen", False):
        # PyInstallerでビルドされた場合、実行ファイルと同じディレクトリに
        log_dir = Path(sys.executable).parent
    else:
        # 開発環境では現在のディレクトリに
        log_dir = Path.cwd()

    log_file = log_dir / "vlog-subs-tool-debug.log"

    # ハンドラーリスト（ファイル出力のみ）
    handlers = [logging.FileHandler(log_file, encoding="utf-8")]

    # ロガー設定
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )

    logger = logging.getLogger(__name__)
    logger.info("=== VLog字幕ツール ログ開始 ===")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform: {sys.platform}")
    logger.info(f"Executable: {sys.executable}")
    logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")
    if hasattr(sys, "_MEIPASS"):
        logger.info(f"_MEIPASS: {sys._MEIPASS}")
    logger.info(f"Log file: {log_file}")


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
        if getattr(sys, "frozen", False):
            from ui.main_window import main as app_main
        else:
            try:
                from app.ui.main_window import main as app_main
            except (ImportError, ModuleNotFoundError):
                from ui.main_window import main as app_main
        logger.info("✅ Stage 5: アプリケーションモジュール - OK")
        return True
    except Exception as e:
        logger.error(f"❌ Stage 5: アプリケーションモジュール - {e}")
        return False


def main() -> None:
    """メインエントリーポイント"""
    # PyInstallerバイナリ実行時の安全対策（PaddleXエラー対策）
    import multiprocessing

    multiprocessing.freeze_support()

    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("メインエントリーポイント開始")
    logger.info("multiprocessing.freeze_support() 実行完了")

    # Issue #200 対応: PaddleX重複初期化エラーの防止
    try:
        from app.core.paddlex_init_guard import get_paddlex_init_status, initialize_for_binary

        # バイナリ実行時の初期化ガードを実行
        initialize_for_binary()

        # 初期化状態をログ出力
        init_status = get_paddlex_init_status()
        logger.info(f"PaddleX initialization status: {init_status}")

    except Exception as e:
        logger.warning(f"PaddleX initialization guard failed: {e}")
        # ガードが失敗してもアプリは継続実行

    is_standalone = setup_paths()
    logger.info(f"実行環境: {'スタンドアロン' if is_standalone else 'ソースコード'}")

    try:
        # デバッグ: 段階的インポートテスト
        if not test_imports(logger):
            logger.error("段階的インポートテストに失敗しました")
            if getattr(sys, "frozen", False):
                safe_input_prompt("Press Enter to continue...")  # コンソール版で確認
            sys.exit(1)

        # メインアプリケーション起動
        logger.info("アプリケーション起動開始")

        if is_standalone:
            from ui.main_window import main as app_main
        else:
            try:
                from app.ui.main_window import main as app_main
            except (ImportError, ModuleNotFoundError):
                from ui.main_window import main as app_main

        logger.info("UIモジュール読み込み完了、アプリケーション起動中...")
        app_main()
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
        print(f"   ログファイル: vlog-subs-tool-debug.log")
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
