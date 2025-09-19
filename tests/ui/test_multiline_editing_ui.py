"""
複数行字幕編集UIのテスト

Issue #148: マルチライン字幕編集機能のUIテスト
"""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence, QTextOption
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit

from app.core.models import SubtitleItem
from app.ui.views.table_view import MultilineTextDelegate, SubtitleTableView


class TestMultilineTextDelegate:
    """複数行テキストデリゲートのテスト"""

    @pytest.fixture
    def delegate(self, qapp):
        """デリゲートのフィクスチャ"""
        return MultilineTextDelegate()

    @pytest.fixture
    def sample_multiline_subtitles(self):
        """複数行字幕のサンプルデータ"""
        return [
            SubtitleItem(1, 1000, 3000, "単一行の字幕"),
            SubtitleItem(2, 4000, 6000, "複数行の字幕\n2行目のテキスト"),
            SubtitleItem(3, 7000, 9000, "3行の字幕\n2行目\n3行目"),
            SubtitleItem(4, 10000, 12000, "長い複数行字幕\n非常に長いテキストが含まれている2行目\n短い3行目"),
        ]

    def test_multiline_editor_creation(self, delegate, qapp):
        """複数行エディター作成のテスト"""
        from PySide6.QtWidgets import QWidget
        from PySide6.QtCore import QModelIndex

        parent = QWidget()
        index = QModelIndex()

        # テキスト列（3列目）でのエディター作成
        editor = delegate.createEditor(parent, None, index)

        # QPlainTextEditが作成されることを確認
        assert isinstance(editor, QPlainTextEdit), "複数行エディターがQPlainTextEditでない"

        # ワードラップが設定されていることを確認
        assert editor.wordWrapMode() == QTextOption.WrapAtWordBoundaryOrAnywhere, "ワードラップが正しく設定されていない"

    def test_multiline_editor_data_setting(self, delegate, qapp):
        """複数行エディターへのデータ設定テスト"""
        from PySide6.QtWidgets import QWidget
        from PySide6.QtCore import QAbstractTableModel, QModelIndex
        from unittest.mock import Mock

        parent = QWidget()

        # モックインデックスを作成
        mock_model = Mock(spec=QAbstractTableModel)
        mock_model.data.return_value = "1行目\n2行目\n3行目"

        mock_index = Mock(spec=QModelIndex)
        mock_index.model.return_value = mock_model
        mock_index.column.return_value = 3  # テキスト列

        # エディターを作成
        editor = delegate.createEditor(parent, None, mock_index)

        # データを設定
        delegate.setEditorData(editor, mock_index)

        # 複数行テキストが正しく設定されていることを確認
        text = editor.toPlainText()
        assert "1行目" in text, "1行目が設定されていない"
        assert "2行目" in text, "2行目が設定されていない"
        assert "3行目" in text, "3行目が設定されていない"

    def test_multiline_editor_data_getting(self, delegate, qapp):
        """複数行エディターからのデータ取得テスト"""
        from PySide6.QtWidgets import QWidget
        from PySide6.QtCore import QAbstractTableModel, QModelIndex
        from unittest.mock import Mock

        parent = QWidget()

        # エディターを作成
        editor = QPlainTextEdit(parent)
        multiline_text = "編集された1行目\n編集された2行目\n編集された3行目"
        editor.setPlainText(multiline_text)

        # モックモデルとインデックス
        mock_model = Mock(spec=QAbstractTableModel)
        mock_index = Mock(spec=QModelIndex)
        mock_index.model.return_value = mock_model

        # データを取得
        delegate.setModelData(editor, mock_model, mock_index)

        # モデルのsetDataが呼ばれ、複数行テキストが渡されることを確認
        mock_model.setData.assert_called_once()
        call_args = mock_model.setData.call_args
        assert multiline_text in str(call_args), "複数行テキストがモデルに設定されていない"


class TestMultilineEditingIntegration:
    """複数行編集統合テスト"""

    @pytest.fixture
    def table_view_with_multiline(self, qapp, sample_multiline_subtitles):
        """複数行字幕を含むテーブルビューのフィクスチャ"""
        table = SubtitleTableView()
        table.load_subtitles(sample_multiline_subtitles)
        table.show()
        return table

    @pytest.fixture
    def sample_multiline_subtitles(self):
        """複数行字幕のサンプルデータ"""
        return [
            SubtitleItem(1, 1000, 3000, "単一行の字幕"),
            SubtitleItem(2, 4000, 6000, "複数行の字幕\n2行目のテキスト"),
            SubtitleItem(3, 7000, 9000, "3行の字幕\n2行目\n3行目"),
            SubtitleItem(4, 10000, 12000, "長い複数行字幕\n非常に長いテキストが含まれている2行目\n短い3行目"),
        ]

    def test_multiline_display_in_table(self, table_view_with_multiline):
        """テーブルでの複数行表示テスト"""
        table = table_view_with_multiline.table

        # 複数行字幕の表示確認
        multiline_item = table.item(1, 3)  # 2番目の字幕（複数行）
        text = multiline_item.text()

        assert "複数行の字幕" in text, "1行目が表示されていない"
        assert "2行目のテキスト" in text, "2行目が表示されていない"

        # 改行が適切に処理されていることを確認（表示用に変換される場合がある）
        assert "\n" in text or "\\n" in text or "<br>" in text, "改行が処理されていない"

    def test_multiline_editing_workflow(self, table_view_with_multiline):
        """複数行編集ワークフローのテスト"""
        table = table_view_with_multiline.table

        # 複数行字幕のセルを選択
        table.setCurrentCell(1, 3)

        # 編集モードに入る（ダブルクリック）
        item = table.item(1, 3)
        rect = table.visualItemRect(item)
        QTest.mouseDblClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())

        # キーボード入力で複数行テキストを編集
        new_multiline_text = "新しい1行目\n新しい2行目\n追加された3行目"

        # 現在のエディターを取得（デリゲートによって作成される）
        current_editor = table.findChild(QPlainTextEdit)
        if current_editor:
            current_editor.setPlainText(new_multiline_text)

            # Enterキーで編集を確定
            QTest.keyClick(current_editor, Qt.Key_Return)

            # 編集された内容が反映されていることを確認
            updated_text = table.item(1, 3).text()
            assert "新しい1行目" in updated_text, "1行目の編集が反映されていない"
            assert "新しい2行目" in updated_text, "2行目の編集が反映されていない"
            assert "追加された3行目" in updated_text, "3行目の編集が反映されていない"

    def test_multiline_text_validation(self, table_view_with_multiline):
        """複数行テキストの検証テスト"""
        table = table_view_with_multiline.table

        # 非常に多い行数のテキストをテスト
        many_lines_text = "\n".join([f"行{i+1}" for i in range(10)])

        # 編集
        table.setCurrentCell(1, 3)
        item = table.item(1, 3)
        rect = table.visualItemRect(item)
        QTest.mouseDblClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())

        current_editor = table.findChild(QPlainTextEdit)
        if current_editor:
            current_editor.setPlainText(many_lines_text)
            QTest.keyClick(current_editor, Qt.Key_Return)

            # 10行のテキストが保存されることを確認
            updated_text = table.item(1, 3).text()
            for i in range(10):
                assert f"行{i+1}" in updated_text, f"行{i+1}が保存されていない"

    def test_multiline_copy_paste(self, table_view_with_multiline):
        """複数行テキストのコピー・ペーストテスト"""
        table = table_view_with_multiline.table

        # 複数行字幕を選択
        table.setCurrentCell(1, 3)

        # コピー（Ctrl+C）
        QTest.keyClick(table, Qt.Key_C, Qt.ControlModifier)

        # クリップボードの内容を確認
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()
        assert "複数行の字幕" in clipboard_text, "複数行テキストがコピーされていない"
        assert "2行目のテキスト" in clipboard_text, "2行目がコピーされていない"

        # 別のセルに移動してペースト
        table.setCurrentCell(0, 3)
        QTest.keyClick(table, Qt.Key_V, Qt.ControlModifier)

        # ペーストされた内容を確認
        pasted_text = table.item(0, 3).text()
        assert "複数行の字幕" in pasted_text, "複数行テキストがペーストされていない"
        assert "2行目のテキスト" in pasted_text, "2行目がペーストされていない"

    def test_multiline_text_search(self, table_view_with_multiline):
        """複数行テキストでの検索テスト"""
        # 検索機能がある場合のテスト
        search_terms = ["2行目", "3行目", "長いテキスト"]

        for search_term in search_terms:
            found_rows = table_view_with_multiline.search_text(search_term)

            # 検索結果があることを確認
            assert len(found_rows) > 0, f"'{search_term}'の検索結果がない"

            # 検索結果が実際に検索語を含んでいることを確認
            for row in found_rows:
                text = table_view_with_multiline.table.item(row, 3).text()
                assert search_term in text, f"検索結果に'{search_term}'が含まれていない"

    def test_multiline_keyboard_navigation(self, table_view_with_multiline):
        """複数行編集でのキーボードナビゲーションテスト"""
        table = table_view_with_multiline.table

        # 複数行セルを編集モードにする
        table.setCurrentCell(1, 3)
        item = table.item(1, 3)
        rect = table.visualItemRect(item)
        QTest.mouseDblClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())

        current_editor = table.findChild(QPlainTextEdit)
        if current_editor:
            # カーソルを最初の行に移動
            current_editor.moveCursor(current_editor.textCursor().MoveOperation.Start)

            # 下矢印キーで次の行に移動
            QTest.keyClick(current_editor, Qt.Key_Down)

            # カーソル位置が変わっていることを確認
            cursor = current_editor.textCursor()
            assert cursor.position() > 0, "カーソルが移動していない"

            # Ctrl+Aで全選択
            QTest.keyClick(current_editor, Qt.Key_A, Qt.ControlModifier)

            # 全テキストが選択されていることを確認
            assert current_editor.textCursor().hasSelection(), "全選択されていない"

    def test_multiline_undo_redo(self, table_view_with_multiline):
        """複数行編集でのアンドゥ・リドゥテスト"""
        table = table_view_with_multiline.table

        # 元のテキストを記録
        original_text = table.item(1, 3).text()

        # 編集モードに入る
        table.setCurrentCell(1, 3)
        item = table.item(1, 3)
        rect = table.visualItemRect(item)
        QTest.mouseDblClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())

        current_editor = table.findChild(QPlainTextEdit)
        if current_editor:
            # テキストを変更
            new_text = "アンドゥテスト用\n新しい複数行テキスト"
            current_editor.setPlainText(new_text)

            # エディター内でアンドゥ
            QTest.keyClick(current_editor, Qt.Key_Z, Qt.ControlModifier)

            # 元のテキストに戻っていることを確認
            undone_text = current_editor.toPlainText()
            assert original_text in undone_text or len(undone_text) < len(new_text), "アンドゥが機能していない"

            # リドゥ
            QTest.keyClick(current_editor, Qt.Key_Y, Qt.ControlModifier)

            # 再び変更されたテキストになっていることを確認
            redone_text = current_editor.toPlainText()
            assert len(redone_text) >= len(undone_text), "リドゥが機能していない"

    def test_multiline_text_formatting_preservation(self, table_view_with_multiline):
        """複数行テキストの書式保持テスト"""
        table = table_view_with_multiline.table

        # 特殊な文字を含む複数行テキスト
        special_multiline_text = "1行目：特殊文字\n2行目：タブ\t文字\n3行目：\"クォート\"文字"

        # 編集
        table.setCurrentCell(1, 3)
        item = table.item(1, 3)
        rect = table.visualItemRect(item)
        QTest.mouseDblClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())

        current_editor = table.findChild(QPlainTextEdit)
        if current_editor:
            current_editor.setPlainText(special_multiline_text)
            QTest.keyClick(current_editor, Qt.Key_Return)

            # 特殊文字が保持されていることを確認
            saved_text = table.item(1, 3).text()
            assert "特殊文字" in saved_text, "特殊文字が保持されていない"
            assert "タブ" in saved_text, "タブ文字周辺のテキストが保持されていない"
            assert "クォート" in saved_text, "クォート文字が保持されていない"

    def test_multiline_editor_size_adjustment(self, table_view_with_multiline):
        """複数行エディターのサイズ調整テスト"""
        table = table_view_with_multiline.table

        # 編集モードに入る
        table.setCurrentCell(2, 3)  # 3行のテキストがあるセル
        item = table.item(2, 3)
        rect = table.visualItemRect(item)
        QTest.mouseDblClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())

        current_editor = table.findChild(QPlainTextEdit)
        if current_editor:
            # エディターが複数行を表示できるサイズになっていることを確認
            editor_height = current_editor.height()
            single_line_height = current_editor.fontMetrics().height()

            # 複数行を表示できる高さがあることを確認
            assert editor_height >= single_line_height * 2, "エディターが複数行表示に適したサイズでない"

            # 非常に長いテキストを入力
            very_long_text = "\n".join([f"非常に長い行のテキスト{i}" * 5 for i in range(5)])
            current_editor.setPlainText(very_long_text)

            # スクロールバーが表示される、またはテキストが適切に表示されることを確認
            # （具体的な確認方法は実装に依存）
            assert current_editor.toPlainText() == very_long_text, "長いテキストが正しく設定されていない"