#!/usr/bin/env python3
"""
VLog字幕ツール メインエントリーポイント
PyInstaller バイナリとソースコード実行の両方に対応
"""

import sys
import os
from pathlib import Path

def setup_paths():
    """
    実行環境に応じてパスを設定
    PyInstallerでビルドされたバイナリとソースコード実行の両方に対応
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
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

def main():
    """メインエントリーポイント"""
    is_standalone = setup_paths()

    try:
        # スタンドアロンバイナリの場合は直接インポート
        if is_standalone:
            from ui.main_window import main as app_main
        else:
            # ソースコード実行の場合はパッケージインポートを試行
            try:
                from app.ui.main_window import main as app_main
            except (ImportError, ModuleNotFoundError):
                from ui.main_window import main as app_main

        # アプリケーション起動
        app_main()

    except ModuleNotFoundError as e:
        if is_standalone:
            # スタンドアロンバイナリでこのエラーが発生する場合はビルドエラー
            show_standalone_error(e)
        else:
            # ソースコード実行時の依存関係エラー
            show_source_error(e)
        sys.exit(1)

    except ImportError as e:
        if is_standalone:
            show_standalone_error(e)
        else:
            show_package_error(e)
        sys.exit(1)

    except Exception as e:
        print(f"❌ 予期しないエラーが発生しました: {e}")
        print()
        print("🔧 解決方法:")
        print("- アプリケーションを再起動してください")
        print("- 問題が続く場合は以下にご報告ください:")
        print("  https://github.com/lancelot89/vlog-subs-tool/issues")
        sys.exit(1)

def show_standalone_error(error):
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

def show_source_error(error):
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

def show_package_error(error):
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