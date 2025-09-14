#!/usr/bin/env python3
"""
VLog字幕ツール メインエントリーポイント
"""

import sys
import os
from pathlib import Path

# アプリケーションパスを追加
app_dir = Path(__file__).parent
sys.path.insert(0, str(app_dir))

# PySide6アプリケーション起動
if __name__ == "__main__":
    try:
        from ui.main_window import main
        main()
    except ModuleNotFoundError as e:
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
        print(f"🐛 元のエラー: {e}")
        sys.exit(1)
    except ImportError as e:
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
        print(f"🐛 元のエラー: {e}")
        sys.exit(1)