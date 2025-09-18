"""
字幕テーブルモデルのテスト
"""

import pytest
from PySide6.QtCore import Qt

from app.core.models import SubtitleItem
from app.ui.views.table_view import SubtitleTableModel


class TestSubtitleTableModel:
    """SubtitleTableModelクラスのテスト"""

    @pytest.fixture
    def model(self, qapp):
        """テーブルモデルのフィクスチャ"""
        return SubtitleTableModel()

    @pytest.fixture
    def model_with_data(self, qapp, sample_subtitles):
        """データ付きテーブルモデルのフィクスチャ"""
        model = SubtitleTableModel()
        model.set_subtitles(sample_subtitles)
        return model

    def test_init(self, model):
        """初期化のテスト"""
        assert model.rowCount() == 0
        assert model.columnCount() == 4  # インデックス、開始、終了、テキスト

    def test_headers(self, model):
        """ヘッダーのテスト"""
        expected_headers = ["#", "開始時間", "終了時間", "字幕テキスト"]

        for col, expected in enumerate(expected_headers):
            header = model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
            assert header == expected

    def test_set_subtitles(self, model, sample_subtitles):
        """字幕データ設定のテスト"""
        model.set_subtitles(sample_subtitles)

        assert model.rowCount() == len(sample_subtitles)
        assert len(model._subtitles) == len(sample_subtitles)

    def test_data_display(self, model_with_data, sample_subtitles):
        """データ表示のテスト"""
        model = model_with_data

        # 最初の字幕のデータをチェック
        subtitle = sample_subtitles[0]

        # インデックス列
        index_data = model.data(model.index(0, 0), Qt.DisplayRole)
        assert index_data == subtitle.index

        # 開始時間列
        start_data = model.data(model.index(0, 1), Qt.DisplayRole)
        assert "00:00:01" in start_data  # フォーマットされた時間

        # 終了時間列
        end_data = model.data(model.index(0, 2), Qt.DisplayRole)
        assert "00:00:03" in end_data

        # テキスト列
        text_data = model.data(model.index(0, 3), Qt.DisplayRole)
        assert text_data == subtitle.text

    def test_data_editing(self, model_with_data):
        """データ編集のテスト"""
        model = model_with_data

        # テキスト列の編集（編集可能）
        text_index = model.index(0, 3)
        new_text = "新しいテキスト"

        success = model.setData(text_index, new_text, Qt.EditRole)
        assert success

        # データが更新されていることを確認
        updated_text = model.data(text_index, Qt.DisplayRole)
        assert updated_text == new_text

        # 内部データも更新されていることを確認
        assert model._subtitles[0].text == new_text

    def test_non_editable_columns(self, model_with_data):
        """編集不可列のテスト"""
        model = model_with_data

        # インデックス列（編集不可）
        index_index = model.index(0, 0)
        success = model.setData(index_index, 999, Qt.EditRole)
        assert not success

        # 開始時間列（編集不可）
        start_index = model.index(0, 1)
        success = model.setData(start_index, "新しい時間", Qt.EditRole)
        assert not success

    def test_flags(self, model_with_data):
        """フラグのテスト"""
        model = model_with_data

        # テキスト列は編集可能
        text_index = model.index(0, 3)
        flags = model.flags(text_index)
        assert flags & Qt.ItemIsEditable
        assert flags & Qt.ItemIsEnabled
        assert flags & Qt.ItemIsSelectable

        # インデックス列は編集不可
        index_index = model.index(0, 0)
        flags = model.flags(index_index)
        assert not (flags & Qt.ItemIsEditable)
        assert flags & Qt.ItemIsEnabled
        assert flags & Qt.ItemIsSelectable

    def test_invalid_index(self, model_with_data):
        """無効インデックスのテスト"""
        model = model_with_data

        # 範囲外のインデックス
        invalid_index = model.index(999, 0)
        data = model.data(invalid_index, Qt.DisplayRole)
        assert data is None

    def test_add_subtitle(self, model):
        """字幕追加のテスト"""
        new_subtitle = SubtitleItem(1, 1000, 3000, "新しい字幕")

        # 手動でリストに追加してモデルをリフレッシュ
        model._subtitles = [new_subtitle]
        model.beginResetModel()
        model.endResetModel()

        assert model.rowCount() == 1
        text_data = model.data(model.index(0, 3), Qt.DisplayRole)
        assert text_data == "新しい字幕"

    def test_clear_subtitles(self, model_with_data):
        """字幕クリアのテスト"""
        model = model_with_data

        # データがあることを確認
        assert model.rowCount() > 0

        # クリア
        model.set_subtitles([])

        # データがクリアされていることを確認
        assert model.rowCount() == 0
        assert len(model._subtitles) == 0

    def test_time_formatting(self, model_with_data):
        """時間フォーマットのテスト"""
        model = model_with_data

        # 1秒の字幕
        subtitle_1s = SubtitleItem(1, 1000, 2000, "1秒")
        model._subtitles[0] = subtitle_1s

        start_data = model.data(model.index(0, 1), Qt.DisplayRole)
        end_data = model.data(model.index(0, 2), Qt.DisplayRole)

        # フォーマットされた時間文字列の確認
        assert "00:00:01" in start_data
        assert "00:00:02" in end_data

    def test_get_subtitle_at_index(self, model_with_data, sample_subtitles):
        """インデックス指定での字幕取得テスト"""
        model = model_with_data

        # 最初の字幕を取得
        subtitle = model.get_subtitle_at_index(0)
        assert subtitle is not None
        assert subtitle.text == sample_subtitles[0].text

        # 範囲外インデックス
        subtitle = model.get_subtitle_at_index(999)
        assert subtitle is None

    def test_get_all_subtitles(self, model_with_data, sample_subtitles):
        """全字幕取得のテスト"""
        model = model_with_data

        all_subtitles = model.get_all_subtitles()
        assert len(all_subtitles) == len(sample_subtitles)
        assert all_subtitles[0].text == sample_subtitles[0].text


class TestSubtitleTableModelSignals:
    """SubtitleTableModelのシグナルテスト"""

    @pytest.fixture
    def model(self, qapp):
        """テーブルモデルのフィクスチャ"""
        return SubtitleTableModel()

    def test_data_changed_signal(self, model, sample_subtitles):
        """dataChangedシグナルのテスト"""
        model.set_subtitles(sample_subtitles)

        signal_emitted = False

        def on_data_changed(top_left, bottom_right, roles):
            nonlocal signal_emitted
            signal_emitted = True

        model.dataChanged.connect(on_data_changed)

        # データを変更
        text_index = model.index(0, 3)
        model.setData(text_index, "変更されたテキスト", Qt.EditRole)

        # シグナルが発行されていることを確認
        assert signal_emitted

    def test_model_reset_signal(self, model, sample_subtitles):
        """modelResetシグナルのテスト"""
        signal_emitted = False

        def on_model_reset():
            nonlocal signal_emitted
            signal_emitted = True

        model.modelReset.connect(on_model_reset)

        # データを設定（モデルリセットが発生）
        model.set_subtitles(sample_subtitles)

        # シグナルが発行されていることを確認
        assert signal_emitted
