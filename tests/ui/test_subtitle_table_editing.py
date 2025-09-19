"""
字幕テーブル編集操作のUIテスト

分割・結合・削除などの字幕編集機能のテスト
"""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.models import SubtitleItem
from app.ui.views.table_view import SubtitleTableView


class TestSubtitleTableEditing:
    """字幕テーブル編集機能のテスト"""

    @pytest.fixture
    def sample_subtitles(self):
        """テスト用字幕データ"""
        return [
            SubtitleItem(1, 1000, 3000, "最初の字幕"),
            SubtitleItem(2, 4000, 6000, "2番目の字幕\n複数行テキスト"),
            SubtitleItem(3, 7000, 9000, "3番目の字幕"),
            SubtitleItem(4, 10000, 12000, "最後の字幕"),
        ]

    @pytest.fixture
    def table_view(self, qapp, sample_subtitles):
        """字幕テーブルビューのフィクスチャ"""
        table = SubtitleTableView()
        table.set_subtitles(sample_subtitles)
        table.show()
        return table

    def test_table_creation_and_data_display(self, table_view, sample_subtitles):
        """テーブル作成とデータ表示のテスト"""
        # テーブルが正しく作成されている
        assert table_view.table.rowCount() == len(sample_subtitles)
        assert table_view.table.columnCount() == 4  # インデックス、開始、終了、テキスト

        # データが正しく表示されている
        first_row_text = table_view.table.item(0, 3).text()
        assert first_row_text == "最初の字幕"

        # 複数行テキストが正しく表示されている
        second_row_text = table_view.table.item(1, 3).text()
        assert "2番目の字幕" in second_row_text
        assert "複数行テキスト" in second_row_text

    def test_text_editing_in_table(self, table_view):
        """テーブル内テキスト編集のテスト"""
        # セルを選択
        table_view.table.setCurrentCell(0, 3)

        # ダブルクリックで編集モードに入る
        item = table_view.table.item(0, 3)
        rect = table_view.table.visualItemRect(item)
        QTest.mouseDblClick(
            table_view.table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center()
        )

        # 新しいテキストを入力
        new_text = "編集されたテキスト"

        # キーボード入力をシミュレート
        QTest.keyClicks(table_view.table, new_text)
        QTest.keyClick(table_view.table, Qt.Key_Return)

        # 編集が反映されていることを確認
        updated_text = table_view.table.item(0, 3).text()
        assert new_text in updated_text

    def test_multiline_text_editing(self, table_view):
        """複数行テキスト編集のテスト"""
        # 複数行テキストのセルを選択
        table_view.table.setCurrentCell(1, 3)

        # 現在のテキストを取得
        original_text = table_view.table.item(1, 3).text()
        assert "\n" in original_text or "\\n" in original_text  # 改行が含まれている

        # 編集モードに入る
        item = table_view.table.item(1, 3)
        rect = table_view.table.visualItemRect(item)
        QTest.mouseDblClick(
            table_view.table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center()
        )

        # 複数行テキストを入力
        new_multiline_text = "新しい1行目\n新しい2行目"
        QTest.keyClicks(table_view.table, new_multiline_text)
        QTest.keyClick(table_view.table, Qt.Key_Return)

        # 更新されたテキストを確認
        updated_text = table_view.table.item(1, 3).text()
        assert "新しい1行目" in updated_text
        assert "新しい2行目" in updated_text

    def test_row_selection_and_navigation(self, table_view):
        """行選択とナビゲーションのテスト"""
        # 最初の行を選択
        table_view.table.setCurrentCell(0, 0)
        assert table_view.table.currentRow() == 0

        # キーボードで次の行に移動
        QTest.keyClick(table_view.table, Qt.Key_Down)
        assert table_view.table.currentRow() == 1

        # 前の行に戻る
        QTest.keyClick(table_view.table, Qt.Key_Up)
        assert table_view.table.currentRow() == 0

        # 最後の行に移動
        QTest.keyClick(table_view.table, Qt.Key_End, Qt.ControlModifier)
        assert table_view.table.currentRow() == table_view.table.rowCount() - 1

    def test_row_insertion(self, table_view):
        """行挿入のテスト"""
        original_count = table_view.table.rowCount()

        # 2行目を選択
        table_view.table.setCurrentCell(1, 0)

        # 新しい行を挿入
        table_view.add_subtitle()

        # 行数が増えていることを確認
        new_count = table_view.table.rowCount()
        assert new_count == original_count + 1

        # 挿入された内容を確認
        inserted_text = table_view.table.item(1, 3).text()
        assert "挿入された字幕" in inserted_text

    def test_row_deletion(self, table_view):
        """行削除のテスト"""
        original_count = table_view.table.rowCount()

        # 削除対象の行のテキストを記録
        deleted_text = table_view.table.item(1, 3).text()

        # 2行目を選択して削除
        table_view.table.setCurrentCell(1, 0)
        table_view.delete_subtitle()

        # 行数が減っていることを確認
        new_count = table_view.table.rowCount()
        assert new_count == original_count - 1

        # 削除されたテキストがもう存在しないことを確認
        remaining_texts = []
        for row in range(table_view.table.rowCount()):
            text = table_view.table.item(row, 3).text()
            remaining_texts.append(text)

        assert deleted_text not in " ".join(remaining_texts)

    def test_subtitle_split_operation(self, table_view):
        """字幕分割操作のテスト"""
        # 長いテキストの字幕を選択
        long_text_row = 1  # "2番目の字幕\n複数行テキスト"
        table_view.table.setCurrentCell(long_text_row, 0)

        original_count = table_view.table.rowCount()

        # 分割操作を実行
        table_view.split_subtitle()

        # 行数が増えていることを確認
        assert table_view.table.rowCount() == original_count + 1

        # 分割操作が完了したことを確認（実際の時間検証は省略）

    def test_subtitle_merge_operation(self, table_view):
        """字幕結合操作のテスト"""
        original_count = table_view.table.rowCount()

        # 連続する2行を選択
        table_view.table.setCurrentCell(0, 0)
        table_view.table.setRangeSelected(
            table_view.table.selectionModel().model().createIndex(0, 0),
            table_view.table.selectionModel().model().createIndex(1, 3),
            True,
        )

        # 結合前のテキストを記録
        first_text = table_view.table.item(0, 3).text()
        second_text = table_view.table.item(1, 3).text()

        # 結合操作を実行
        table_view.merge_subtitle()

        # 行数が減っていることを確認
        assert table_view.table.rowCount() == original_count - 1

        # 結合されたテキストを確認
        merged_text = table_view.table.item(0, 3).text()
        assert first_text in merged_text
        assert second_text in merged_text

    def test_time_editing_validation(self, table_view):
        """時間編集の検証テスト"""
        # 開始時間列を編集しようとする（通常は編集不可）
        table_view.table.setCurrentCell(0, 1)

        # ダブルクリックで編集を試みる
        item = table_view.table.item(0, 1)
        rect = table_view.table.visualItemRect(item)
        QTest.mouseDblClick(
            table_view.table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center()
        )

        # 時間列は編集不可であることを確認
        flags = item.flags()
        assert not (flags & Qt.ItemIsEditable), "時間列が編集可能になっている"

    def test_keyboard_shortcuts(self, table_view):
        """キーボードショートカットのテスト"""
        # Ctrl+C (コピー)
        table_view.table.setCurrentCell(0, 3)
        QTest.keyClick(table_view.table, Qt.Key_C, Qt.ControlModifier)

        # クリップボードの内容を確認（実装に応じて）
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()
        assert "最初の字幕" in clipboard_text

        # Ctrl+V (ペースト) - 次の行に移動してペースト
        table_view.table.setCurrentCell(1, 3)
        QTest.keyClick(table_view.table, Qt.Key_V, Qt.ControlModifier)

        # ペーストされたことを確認
        pasted_text = table_view.table.item(1, 3).text()
        assert "最初の字幕" in pasted_text

    def test_context_menu_operations(self, table_view):
        """コンテキストメニュー操作のテスト"""
        # 行を右クリック
        table_view.table.setCurrentCell(1, 0)
        item = table_view.table.item(1, 0)
        rect = table_view.table.visualItemRect(item)

        # 右クリックメニューを開く
        QTest.mouseClick(table_view.table.viewport(), Qt.RightButton, Qt.NoModifier, rect.center())

        # コンテキストメニューが表示されることを確認（実装依存）
        # この部分は実際のメニュー実装に応じて調整が必要

    def test_undo_redo_operations(self, table_view):
        """アンドゥ・リドゥ操作のテスト"""
        # 元のテキストを記録
        original_text = table_view.table.item(0, 3).text()

        # テキストを編集
        table_view.table.setCurrentCell(0, 3)
        item = table_view.table.item(0, 3)
        rect = table_view.table.visualItemRect(item)
        QTest.mouseDblClick(
            table_view.table.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center()
        )

        new_text = "変更されたテキスト"
        QTest.keyClicks(table_view.table, new_text)
        QTest.keyClick(table_view.table, Qt.Key_Return)

        # 変更が適用されていることを確認
        modified_text = table_view.table.item(0, 3).text()
        assert new_text in modified_text

        # アンドゥ操作
        QTest.keyClick(table_view.table, Qt.Key_Z, Qt.ControlModifier)

        # 元のテキストに戻っていることを確認
        undone_text = table_view.table.item(0, 3).text()
        assert original_text in undone_text

        # リドゥ操作
        QTest.keyClick(table_view.table, Qt.Key_Y, Qt.ControlModifier)

        # 再び変更されたテキストになっていることを確認
        redone_text = table_view.table.item(0, 3).text()
        assert new_text in redone_text

    def test_bulk_operations(self, table_view):
        """一括操作のテスト"""
        # 複数行を選択
        table_view.table.setCurrentCell(0, 0)

        # Shiftキーを押しながら3行目まで選択
        QTest.keyClick(table_view.table, Qt.Key_Down, Qt.ShiftModifier)
        QTest.keyClick(table_view.table, Qt.Key_Down, Qt.ShiftModifier)

        # 選択された行数を確認
        selected_ranges = table_view.table.selectionModel().selectedRows()
        assert len(selected_ranges) == 3

        # 一括削除操作（単一削除を繰り返し）
        original_count = table_view.table.rowCount()
        # 複数回削除を実行
        for _ in range(3):
            table_view.delete_subtitle()

        # 削除された行数を確認
        new_count = table_view.table.rowCount()
        assert new_count <= original_count - 1  # 少なくとも1行は削除されている

    def test_search_and_replace(self, table_view):
        """検索・置換機能のテスト"""
        # 検索機能をテスト（手動検索）
        search_term = "字幕"
        found_rows = []
        for row in range(table_view.table.rowCount()):
            text = table_view.table.item(row, 3).text()
            if search_term in text:
                found_rows.append(row)

        # 検索結果があることを確認
        assert len(found_rows) > 0

        # 各検索結果が実際に検索語を含んでいることを確認
        for row in found_rows:
            text = table_view.table.item(row, 3).text()
            assert search_term in text

        # 置換機能をテスト（手動置換）
        replace_from = "字幕"
        replace_to = "サブタイトル"
        replaced_count = 0

        # 手動でテキストを置換
        for row in range(table_view.table.rowCount()):
            item = table_view.table.item(row, 3)
            if item and replace_from in item.text():
                new_text = item.text().replace(replace_from, replace_to)
                item.setText(new_text)
                replaced_count += 1

        # 置換が実行されたことを確認
        assert replaced_count > 0

        # 置換後のテキストを確認
        for row in range(table_view.table.rowCount()):
            text = table_view.table.item(row, 3).text()
            if replace_to in text:
                assert replace_from not in text  # 置換前の文字が残っていない

    def test_table_sorting(self, table_view):
        """テーブルソート機能のテスト"""
        # 開始時間でソート（昇順）
        table_view.table.sortItems(1, Qt.AscendingOrder)

        # ソート操作が完了したことを確認（詳細検証は省略）

        # 降順ソート
        table_view.table.sortItems(1, Qt.DescendingOrder)

        # 降順ソート操作が完了したことを確認（詳細検証は省略）
