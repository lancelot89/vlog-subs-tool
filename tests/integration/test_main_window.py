"""
メインウィンドウのGUIテスト
"""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.models import SubtitleItem
from app.ui.main_window import MainWindow


class TestMainWindow:
    """MainWindowクラスのGUIテスト"""

    @pytest.fixture
    def main_window(self, qapp):
        """メインウィンドウのフィクスチャ"""
        window = MainWindow()
        window.show()
        return window

    def test_window_creation(self, main_window):
        """ウィンドウ作成のテスト"""
        assert main_window.isVisible()
        assert main_window.windowTitle() == "VLog字幕ツール v1.0"

    def test_menu_structure(self, main_window):
        """メニュー構造のテスト"""
        menubar = main_window.menuBar()

        # メニューが存在することを確認
        menu_titles = [action.text() for action in menubar.actions()]
        assert "ファイル(&F)" in menu_titles
        assert "編集(&E)" in menu_titles
        assert "表示(&V)" in menu_titles
        assert "ツール(&T)" in menu_titles
        assert "ヘルプ(&H)" in menu_titles

    def test_toolbar_existence(self, main_window):
        """ツールバーの存在確認"""
        toolbar = main_window.toolbar
        assert toolbar is not None
        assert toolbar.isVisible()

        # ツールバーアクションの確認
        actions = toolbar.actions()
        action_texts = [action.text() for action in actions if action.text()]

        # 主要なアクションが存在することを確認
        expected_actions = ["開く", "保存", "字幕抽出", "SRT出力"]
        for expected in expected_actions:
            assert any(expected in text for text in action_texts)

    def test_central_widget_structure(self, main_window):
        """中央ウィジェットの構造テスト"""
        central_widget = main_window.centralWidget()
        assert central_widget is not None

        # スプリッターが存在することを確認
        splitter = main_window.splitter
        assert splitter is not None
        assert splitter.count() == 2  # 左側（テーブル）と右側（プレビュー）

    def test_subtitle_table_widget(self, main_window):
        """字幕テーブルウィジェットのテスト"""
        table_view = main_window.table_view
        assert table_view is not None
        assert table_view.isVisible()

        # テーブルモデルの確認
        model = table_view.model()
        assert model is not None

    def test_video_preview_widget(self, main_window):
        """動画プレビューウィジェットのテスト"""
        preview_view = main_window.preview_view
        assert preview_view is not None
        assert preview_view.isVisible()

    def test_status_bar(self, main_window):
        """ステータスバーのテスト"""
        status_bar = main_window.statusBar()
        assert status_bar is not None
        assert status_bar.isVisible()

    def test_load_subtitles(self, main_window, sample_subtitles):
        """字幕データ読み込みのテスト"""
        # 字幕データを設定
        main_window.table_view.model().set_subtitles(sample_subtitles)

        # モデルのデータを確認
        model = main_window.table_view.model()
        assert model.rowCount() == len(sample_subtitles)

        # 最初の字幕のテキストを確認
        index = model.index(0, 3)  # テキスト列
        text = model.data(index, Qt.DisplayRole)
        assert text == sample_subtitles[0].text

    def test_menu_actions_exist(self, main_window):
        """メニューアクションの存在確認"""
        # ファイルメニューのアクション確認
        file_menu = None
        for action in main_window.menuBar().actions():
            if "ファイル" in action.text():
                file_menu = action.menu()
                break

        assert file_menu is not None

        file_actions = [action.text() for action in file_menu.actions()]
        assert any("開く" in action for action in file_actions)
        assert any("保存" in action for action in file_actions)
        assert any("終了" in action for action in file_actions)

    def test_csv_export_action(self, main_window):
        """CSVエクスポートアクションのテスト"""
        # CSVエクスポートアクションが存在することを確認
        csv_export_action = main_window.csv_export_action
        assert csv_export_action is not None
        assert csv_export_action.text() == "CSV出力"
        assert csv_export_action.isEnabled()

    def test_csv_import_action(self, main_window):
        """CSVインポートアクションのテスト"""
        # CSVインポートアクションが存在することを確認
        csv_import_action = main_window.csv_import_action
        assert csv_import_action is not None
        assert csv_import_action.text() == "翻訳インポート"
        assert csv_import_action.isEnabled()

    def test_srt_export_action(self, main_window):
        """SRTエクスポートアクションのテスト"""
        # SRTエクスポートアクションが存在することを確認
        srt_export_action = main_window.srt_export_action
        assert srt_export_action is not None
        assert srt_export_action.text() == "SRT出力"
        assert srt_export_action.isEnabled()

    def test_subtitle_extraction_action(self, main_window):
        """字幕抽出アクションのテスト"""
        # 字幕抽出アクションが存在することを確認
        extract_action = main_window.extract_action
        assert extract_action is not None
        assert extract_action.text() == "字幕抽出"

        # 動画が読み込まれていない状態では無効
        assert not extract_action.isEnabled()

    def test_qc_check_action(self, main_window):
        """QCチェックアクションのテスト"""
        # QCチェックアクションが存在することを確認
        qc_action = main_window.qc_action
        assert qc_action is not None
        assert qc_action.text() == "QCチェック"
        assert qc_action.isEnabled()

    def test_keyboard_shortcuts(self, main_window):
        """キーボードショートカットのテスト"""
        # Ctrl+Oで開くアクション
        open_action = main_window.open_action
        assert open_action.shortcut().toString() == "Ctrl+O"

        # Ctrl+Sで保存アクション
        save_action = main_window.save_action
        assert save_action.shortcut().toString() == "Ctrl+S"

        # F5で字幕抽出アクション
        extract_action = main_window.extract_action
        assert extract_action.shortcut().toString() == "F5"


class TestSubtitleTableIntegration:
    """字幕テーブルの統合テスト"""

    @pytest.fixture
    def main_window_with_data(self, qapp, sample_subtitles):
        """データ付きメインウィンドウ"""
        window = MainWindow()
        window.show()
        window.table_view.model().set_subtitles(sample_subtitles)
        return window

    def test_table_selection(self, main_window_with_data):
        """テーブル選択のテスト"""
        table_view = main_window_with_data.table_view
        model = table_view.model()

        # 最初の行を選択
        selection_model = table_view.selectionModel()
        index = model.index(0, 0)
        selection_model.setCurrentIndex(
            index, selection_model.SelectionFlag.ClearAndSelect
        )

        # 選択が正しく設定されていることを確認
        current_index = selection_model.currentIndex()
        assert current_index.row() == 0

    def test_table_data_display(self, main_window_with_data, sample_subtitles):
        """テーブルデータ表示のテスト"""
        model = main_window_with_data.table_view.model()

        # 各列のデータを確認
        for row, subtitle in enumerate(sample_subtitles):
            # インデックス列
            index_data = model.data(model.index(row, 0), Qt.DisplayRole)
            assert index_data == subtitle.index

            # テキスト列
            text_data = model.data(model.index(row, 3), Qt.DisplayRole)
            assert text_data == subtitle.text

    def test_table_editing(self, main_window_with_data):
        """テーブル編集のテスト"""
        model = main_window_with_data.table_view.model()

        # テキスト列の編集をテスト
        text_index = model.index(0, 3)
        original_text = model.data(text_index, Qt.DisplayRole)

        # 新しいテキストを設定
        new_text = "編集されたテキスト"
        success = model.setData(text_index, new_text, Qt.EditRole)
        assert success

        # 変更が反映されていることを確認
        updated_text = model.data(text_index, Qt.DisplayRole)
        assert updated_text == new_text
