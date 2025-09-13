"""
字幕テーブルビューの実装
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
    QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QFont, QColor, QAction
from typing import List, Optional

from ...core.models import SubtitleItem


class SubtitleTableView(QWidget):
    """字幕テーブルビューウィジェット"""
    
    # シグナル定義
    subtitle_selected = Signal(int)  # 字幕選択（時間ms）
    subtitle_changed = Signal(int, SubtitleItem)  # 字幕変更
    subtitles_reordered = Signal()  # 順序変更
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.subtitles: List[SubtitleItem] = []
        self.current_highlight_row = -1
        
        self.init_ui()
        self.setup_context_menu()
    
    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)
        
        # 操作ボタン
        button_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("追加")
        self.add_btn.clicked.connect(self.add_subtitle)
        button_layout.addWidget(self.add_btn)
        
        self.split_btn = QPushButton("分割")
        self.split_btn.clicked.connect(self.split_subtitle)
        self.split_btn.setEnabled(False)
        button_layout.addWidget(self.split_btn)
        
        self.merge_btn = QPushButton("結合")
        self.merge_btn.clicked.connect(self.merge_subtitle)
        self.merge_btn.setEnabled(False)
        button_layout.addWidget(self.merge_btn)
        
        self.delete_btn = QPushButton("削除")
        self.delete_btn.clicked.connect(self.delete_subtitle)
        self.delete_btn.setEnabled(False)
        button_layout.addWidget(self.delete_btn)
        
        button_layout.addStretch()
        
        self.up_btn = QPushButton("↑")
        self.up_btn.clicked.connect(self.move_up)
        self.up_btn.setEnabled(False)
        button_layout.addWidget(self.up_btn)
        
        self.down_btn = QPushButton("↓")
        self.down_btn.clicked.connect(self.move_down)
        self.down_btn.setEnabled(False)
        button_layout.addWidget(self.down_btn)
        
        layout.addLayout(button_layout)
        
        # テーブル
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "開始", "終了", "本文"])
        
        # テーブルの設定
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)  # インデックス列
        header.setSectionResizeMode(1, QHeaderView.Fixed)  # 開始時間列
        header.setSectionResizeMode(2, QHeaderView.Fixed)  # 終了時間列
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # 本文列
        
        self.table.setColumnWidth(0, 50)   # インデックス
        self.table.setColumnWidth(1, 100)  # 開始時間
        self.table.setColumnWidth(2, 100)  # 終了時間
        
        # 選択モード設定
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        
        # イベント接続
        self.table.cellChanged.connect(self.on_cell_changed)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        
        layout.addWidget(self.table)
    
    def setup_context_menu(self):
        """コンテキストメニューの設定"""
        self.context_menu = QMenu(self)
        
        split_action = QAction("分割", self)
        split_action.triggered.connect(self.split_subtitle)
        self.context_menu.addAction(split_action)
        
        merge_action = QAction("結合", self)
        merge_action.triggered.connect(self.merge_subtitle)
        self.context_menu.addAction(merge_action)
        
        self.context_menu.addSeparator()
        
        delete_action = QAction("削除", self)
        delete_action.triggered.connect(self.delete_subtitle)
        self.context_menu.addAction(delete_action)
    
    def set_subtitles(self, subtitles: List[SubtitleItem]):
        """字幕リストを設定"""
        self.subtitles = subtitles[:]
        self.refresh_table()
    
    def refresh_table(self):
        """テーブルを更新"""
        self.table.setRowCount(len(self.subtitles))
        
        for row, subtitle in enumerate(self.subtitles):
            # インデックス
            index_item = QTableWidgetItem(str(subtitle.index))
            index_item.setFlags(index_item.flags() & ~Qt.ItemIsEditable)
            index_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, index_item)
            
            # 開始時間
            start_time = self.format_time(subtitle.start_ms)
            start_item = QTableWidgetItem(start_time)
            self.table.setItem(row, 1, start_item)
            
            # 終了時間
            end_time = self.format_time(subtitle.end_ms)
            end_item = QTableWidgetItem(end_time)
            self.table.setItem(row, 2, end_item)
            
            # 本文
            text_item = QTableWidgetItem(subtitle.text)
            self.table.setItem(row, 3, text_item)
    
    def format_time(self, time_ms: int) -> str:
        """時間をフォーマット（MM:SS.mmm）"""
        total_seconds = time_ms / 1000
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:06.3f}"
    
    def parse_time(self, time_str: str) -> int:
        """時間文字列をミリ秒に変換"""
        try:
            parts = time_str.split(':')
            if len(parts) == 2:
                minutes = int(parts[0])
                seconds = float(parts[1])
                return int((minutes * 60 + seconds) * 1000)
        except:
            pass
        return 0
    
    def on_cell_changed(self, row: int, column: int):
        """セル変更時の処理"""
        if row >= len(self.subtitles):
            return
        
        item = self.table.item(row, column)
        if not item:
            return
        
        subtitle = self.subtitles[row]
        
        try:
            if column == 1:  # 開始時間
                new_start_ms = self.parse_time(item.text())
                if new_start_ms >= subtitle.end_ms:
                    QMessageBox.warning(self, "警告", "開始時間は終了時間より前に設定してください")
                    item.setText(self.format_time(subtitle.start_ms))
                    return
                subtitle.start_ms = new_start_ms
                
            elif column == 2:  # 終了時間
                new_end_ms = self.parse_time(item.text())
                if new_end_ms <= subtitle.start_ms:
                    QMessageBox.warning(self, "警告", "終了時間は開始時間より後に設定してください")
                    item.setText(self.format_time(subtitle.end_ms))
                    return
                subtitle.end_ms = new_end_ms
                
            elif column == 3:  # 本文
                subtitle.text = item.text()
            
            # 変更シグナルを発信
            self.subtitle_changed.emit(row, subtitle)
            
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"値の変更に失敗しました: {str(e)}")
            self.refresh_table()
    
    def on_selection_changed(self):
        """選択変更時の処理"""
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        
        has_selection = len(selected_rows) > 0
        self.split_btn.setEnabled(has_selection)
        self.merge_btn.setEnabled(len(selected_rows) == 2)
        self.delete_btn.setEnabled(has_selection)
        self.up_btn.setEnabled(has_selection)
        self.down_btn.setEnabled(has_selection)
        
        # 選択された行の字幕時間にシーク
        if selected_rows:
            row = min(selected_rows)
            if 0 <= row < len(self.subtitles):
                subtitle = self.subtitles[row]
                self.subtitle_selected.emit(subtitle.start_ms)
    
    def highlight_current_subtitle(self, time_ms: int):
        """現在時間の字幕をハイライト"""
        # 前のハイライトをクリア
        if self.current_highlight_row >= 0:
            for col in range(self.table.columnCount()):
                item = self.table.item(self.current_highlight_row, col)
                if item:
                    item.setBackground(QColor())
        
        # 現在時間に該当する字幕を検索
        current_row = -1
        for row, subtitle in enumerate(self.subtitles):
            if subtitle.start_ms <= time_ms <= subtitle.end_ms:
                current_row = row
                break
        
        # 新しいハイライトを設定
        if current_row >= 0:
            for col in range(self.table.columnCount()):
                item = self.table.item(current_row, col)
                if item:
                    item.setBackground(QColor(255, 255, 0, 100))  # 薄い黄色
        
        self.current_highlight_row = current_row
    
    def add_subtitle(self):
        """字幕を追加"""
        # 現在選択されている行の後に追加
        current_row = self.table.currentRow()
        insert_index = current_row + 1 if current_row >= 0 else len(self.subtitles)
        
        # デフォルト値で新しい字幕を作成
        new_subtitle = SubtitleItem(
            index=len(self.subtitles) + 1,
            start_ms=0,
            end_ms=2000,
            text="新しい字幕"
        )
        
        self.subtitles.insert(insert_index, new_subtitle)
        self.refresh_table()
        self.subtitles_reordered.emit()
    
    def split_subtitle(self):
        """字幕を分割"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.subtitles):
            return
        
        subtitle = self.subtitles[row]
        middle_time = (subtitle.start_ms + subtitle.end_ms) // 2
        
        # テキストも分割
        text_parts = subtitle.text.split()
        mid_point = len(text_parts) // 2
        first_text = " ".join(text_parts[:mid_point]) if mid_point > 0 else subtitle.text
        second_text = " ".join(text_parts[mid_point:]) if mid_point < len(text_parts) else ""
        
        # 元の字幕を変更
        subtitle.end_ms = middle_time
        subtitle.text = first_text
        
        # 新しい字幕を作成
        new_subtitle = SubtitleItem(
            index=subtitle.index + 1,
            start_ms=middle_time,
            end_ms=subtitle.end_ms,
            text=second_text
        )
        
        self.subtitles.insert(row + 1, new_subtitle)
        self.refresh_table()
        self.subtitles_reordered.emit()
    
    def merge_subtitle(self):
        """選択された2つの字幕を結合"""
        selected_rows = sorted(set(item.row() for item in self.table.selectedItems()))
        if len(selected_rows) != 2:
            QMessageBox.information(self, "情報", "結合するには2つの字幕を選択してください")
            return
        
        first_row, second_row = selected_rows
        if second_row != first_row + 1:
            QMessageBox.information(self, "情報", "隣接する字幕のみ結合できます")
            return
        
        first_subtitle = self.subtitles[first_row]
        second_subtitle = self.subtitles[second_row]
        
        # 結合
        first_subtitle.end_ms = second_subtitle.end_ms
        first_subtitle.text += " " + second_subtitle.text
        
        # 2番目の字幕を削除
        del self.subtitles[second_row]
        
        self.refresh_table()
        self.subtitles_reordered.emit()
    
    def delete_subtitle(self):
        """字幕を削除"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.subtitles):
            return
        
        reply = QMessageBox.question(
            self, "確認", "選択された字幕を削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            del self.subtitles[row]
            self.refresh_table()
            self.subtitles_reordered.emit()
    
    def move_up(self):
        """字幕を上に移動"""
        row = self.table.currentRow()
        if row <= 0 or row >= len(self.subtitles):
            return
        
        # 要素を交換
        self.subtitles[row], self.subtitles[row - 1] = self.subtitles[row - 1], self.subtitles[row]
        
        self.refresh_table()
        self.table.selectRow(row - 1)
        self.subtitles_reordered.emit()
    
    def move_down(self):
        """字幕を下に移動"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.subtitles) - 1:
            return
        
        # 要素を交換
        self.subtitles[row], self.subtitles[row + 1] = self.subtitles[row + 1], self.subtitles[row]
        
        self.refresh_table()
        self.table.selectRow(row + 1)
        self.subtitles_reordered.emit()
    
    def show_context_menu(self, position: QPoint):
        """コンテキストメニューを表示"""
        item = self.table.itemAt(position)
        if item:
            self.context_menu.exec(self.table.mapToGlobal(position))