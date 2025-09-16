#!/usr/bin/env python3
"""
字幕テーブルのハイライト機能テスト
Issue #105: 抽出字幕を一度選択した場所がブラックアウトする問題の修正テスト
"""

import sys
from pathlib import Path

# アプリケーションのパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QHBoxLayout
from PySide6.QtCore import QTimer
from app.ui.views.table_view import SubtitleTableView
from app.core.models import SubtitleItem

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("字幕テーブル ハイライトテスト")
        self.setGeometry(100, 100, 800, 600)

        # メインウィジェット
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # テスト用ボタン
        button_layout = QHBoxLayout()

        self.highlight_btn1 = QPushButton("字幕1をハイライト")
        self.highlight_btn1.clicked.connect(lambda: self.table_view.highlight_current_subtitle(1000))
        button_layout.addWidget(self.highlight_btn1)

        self.highlight_btn2 = QPushButton("字幕2をハイライト")
        self.highlight_btn2.clicked.connect(lambda: self.table_view.highlight_current_subtitle(3000))
        button_layout.addWidget(self.highlight_btn2)

        self.clear_btn = QPushButton("ハイライトクリア")
        self.clear_btn.clicked.connect(lambda: self.table_view.highlight_current_subtitle(-1))
        button_layout.addWidget(self.clear_btn)

        layout.addLayout(button_layout)

        # 字幕テーブル
        self.table_view = SubtitleTableView()
        layout.addWidget(self.table_view)

        # テスト用字幕データを設定
        self.setup_test_data()

    def setup_test_data(self):
        """テスト用の字幕データを設定"""
        test_subtitles = [
            SubtitleItem(index=1, start_ms=0, end_ms=2000, text="テスト字幕1"),
            SubtitleItem(index=2, start_ms=2500, end_ms=4500, text="テスト字幕2"),
            SubtitleItem(index=3, start_ms=5000, end_ms=7000, text="テスト字幕3"),
            SubtitleItem(index=4, start_ms=7500, end_ms=9500, text="テスト字幕4"),
        ]
        self.table_view.set_subtitles(test_subtitles)

def main():
    app = QApplication(sys.argv)

    window = TestWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()