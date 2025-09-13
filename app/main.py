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
    from ui.main_window import main
    main()