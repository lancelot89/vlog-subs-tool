"""
プレビュー同期とプログレス表示のUIテスト

動画プレビューと字幕テーブル同期、長時間処理のプログレス表示のテスト
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QTimer, pyqtSignal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QProgressBar, QProgressDialog

from app.core.models import SubtitleItem
from app.ui.extraction_worker import ExtractionWorker
from app.ui.views.player_view import VideoPlayerView
from app.ui.views.table_view import SubtitleTableView


class TestVideoPreviewSync:
    """動画プレビュー同期テスト"""

    @pytest.fixture
    def test_video_with_subtitles(self):
        """字幕付きテスト動画のフィクスチャ"""
        # テスト動画を作成
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            video_path = Path(f.name)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (640, 480))

        # 10秒間の動画を作成
        for i in range(300):  # 10秒 × 30fps
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

            # 時間に応じて異なる背景色
            if i < 90:  # 0-3秒: 青
                frame[:, :, 0] = 100
            elif i < 180:  # 3-6秒: 緑
                frame[:, :, 1] = 100
            else:  # 6-10秒: 赤
                frame[:, :, 2] = 100

            # 時間表示
            time_text = f"{i/30:.1f}s"
            cv2.putText(frame, time_text, (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            out.write(frame)

        out.release()

        # 対応する字幕データ
        subtitles = [
            SubtitleItem(1, 1000, 3000, "最初の字幕 (1-3秒)"),
            SubtitleItem(2, 3500, 5500, "2番目の字幕 (3.5-5.5秒)"),
            SubtitleItem(3, 6000, 8000, "3番目の字幕 (6-8秒)"),
            SubtitleItem(4, 8500, 9500, "最後の字幕 (8.5-9.5秒)"),
        ]

        yield video_path, subtitles

        # クリーンアップ
        if video_path.exists():
            video_path.unlink()

    @pytest.fixture
    def player_view(self, qapp):
        """動画プレーヤービューのフィクスチャ"""
        player = VideoPlayerView()
        player.show()
        return player

    @pytest.fixture
    def table_view(self, qapp):
        """字幕テーブルビューのフィクスチャ"""
        table = SubtitleTableView()
        table.show()
        return table

    def test_player_subtitle_sync_initialization(self, player_view, table_view, test_video_with_subtitles):
        """プレーヤーと字幕同期の初期化テスト"""
        video_path, subtitles = test_video_with_subtitles

        # 動画を読み込み
        player_view.load_video(str(video_path))

        # 字幕を読み込み
        table_view.load_subtitles(subtitles)

        # プレーヤーと字幕テーブルの同期設定
        player_view.sync_with_subtitle_table(table_view)

        # 同期が設定されていることを確認
        assert hasattr(player_view, '_subtitle_table'), "字幕テーブル参照が設定されていない"
        assert player_view._subtitle_table == table_view, "字幕テーブル参照が正しくない"

    def test_subtitle_selection_updates_player_position(self, player_view, table_view, test_video_with_subtitles):
        """字幕選択でプレーヤー位置が更新されるテスト"""
        video_path, subtitles = test_video_with_subtitles

        # セットアップ
        player_view.load_video(str(video_path))
        table_view.load_subtitles(subtitles)
        player_view.sync_with_subtitle_table(table_view)

        # 2番目の字幕を選択（3.5-5.5秒）
        table_view.table.setCurrentCell(1, 0)

        # プレーヤーの位置が字幕の開始時間に移動することを確認
        # 実装に応じて適切な時間取得メソッドを使用
        current_position = player_view.get_current_position_ms()
        expected_position = subtitles[1].start_ms  # 3500ms

        # 多少の誤差を許容
        assert abs(current_position - expected_position) < 1000, f"プレーヤー位置が正しくない: {current_position} != {expected_position}"

    def test_player_position_updates_subtitle_selection(self, player_view, table_view, test_video_with_subtitles):
        """プレーヤー位置で字幕選択が更新されるテスト"""
        video_path, subtitles = test_video_with_subtitles

        # セットアップ
        player_view.load_video(str(video_path))
        table_view.load_subtitles(subtitles)
        player_view.sync_with_subtitle_table(table_view)

        # プレーヤーを4秒の位置に移動（2番目の字幕の範囲内）
        target_position = 4000  # 4秒
        player_view.seek_to_position_ms(target_position)

        # 対応する字幕が選択されることを確認
        selected_row = table_view.table.currentRow()

        # 4秒の位置にある字幕を特定
        expected_row = -1
        for i, subtitle in enumerate(subtitles):
            if subtitle.start_ms <= target_position <= subtitle.end_ms:
                expected_row = i
                break

        assert selected_row == expected_row, f"字幕選択が正しくない: {selected_row} != {expected_row}"

    def test_subtitle_highlighting_during_playback(self, player_view, table_view, test_video_with_subtitles):
        """再生中の字幕ハイライトテスト"""
        video_path, subtitles = test_video_with_subtitles

        # セットアップ
        player_view.load_video(str(video_path))
        table_view.load_subtitles(subtitles)
        player_view.sync_with_subtitle_table(table_view)

        # 再生開始
        player_view.play()

        # タイマーで位置を確認
        test_positions = [1500, 4000, 7000]  # 各字幕の中間位置

        for position in test_positions:
            # 指定位置に移動
            player_view.seek_to_position_ms(position)

            # 少し待機
            QTest.qWait(100)

            # 対応する字幕がハイライトされることを確認
            current_row = table_view.table.currentRow()
            expected_subtitle = None

            for i, subtitle in enumerate(subtitles):
                if subtitle.start_ms <= position <= subtitle.end_ms:
                    expected_subtitle = i
                    break

            if expected_subtitle is not None:
                assert current_row == expected_subtitle, f"位置{position}msで字幕{expected_subtitle}がハイライトされていない"

        # 再生停止
        player_view.pause()

    def test_sync_with_edited_subtitles(self, player_view, table_view, test_video_with_subtitles):
        """字幕編集後の同期テスト"""
        video_path, subtitles = test_video_with_subtitles

        # セットアップ
        player_view.load_video(str(video_path))
        table_view.load_subtitles(subtitles)
        player_view.sync_with_subtitle_table(table_view)

        # 字幕のタイミングを編集
        modified_subtitle = SubtitleItem(2, 2000, 4000, "編集された字幕")  # 元: 3500-5500
        table_view.update_subtitle_at_row(1, modified_subtitle)

        # 編集後の同期を確認
        player_view.seek_to_position_ms(3000)  # 3秒位置
        QTest.qWait(100)

        selected_row = table_view.table.currentRow()
        assert selected_row == 1, "編集された字幕との同期が正しくない"

    def test_performance_with_many_subtitles(self, player_view, table_view):
        """大量字幕での同期パフォーマンステスト"""
        # 大量の字幕データを生成
        many_subtitles = []
        for i in range(1000):  # 1000個の字幕
            start_ms = i * 1000
            end_ms = start_ms + 500
            text = f"字幕{i+1}"
            many_subtitles.append(SubtitleItem(i+1, start_ms, end_ms, text))

        # 字幕を読み込み
        table_view.load_subtitles(many_subtitles)
        player_view.sync_with_subtitle_table(table_view)

        # 同期パフォーマンスをテスト
        import time

        start_time = time.time()

        # 複数の位置で同期をテスト
        test_positions = [5000, 50000, 100000, 500000]
        for position in test_positions:
            player_view.seek_to_position_ms(position)
            QTest.qWait(10)

        sync_time = time.time() - start_time

        # 同期が高速であることを確認（1秒以内）
        assert sync_time < 1.0, f"大量字幕での同期が遅すぎる: {sync_time:.2f}秒"


class TestProgressDisplays:
    """プログレス表示テスト"""

    @pytest.fixture
    def extraction_worker(self, qapp):
        """抽出ワーカーのフィクスチャ"""
        worker = ExtractionWorker()
        return worker

    def test_extraction_progress_initialization(self, extraction_worker):
        """抽出プログレス初期化テスト"""
        # プログレス関連のシグナルが存在することを確認
        assert hasattr(extraction_worker, 'progress_updated'), "プログレス更新シグナルが存在しない"
        assert hasattr(extraction_worker, 'status_updated'), "ステータス更新シグナルが存在しない"

    def test_progress_signal_emission(self, extraction_worker, qapp):
        """プログレスシグナル発行テスト"""
        progress_values = []
        status_messages = []

        # シグナルを接続
        def on_progress(value):
            progress_values.append(value)

        def on_status(message):
            status_messages.append(message)

        extraction_worker.progress_updated.connect(on_progress)
        extraction_worker.status_updated.connect(on_status)

        # プログレス更新をシミュレート
        test_progress_values = [0, 25, 50, 75, 100]
        test_status_messages = ["開始中", "フレーム抽出中", "OCR処理中", "結果処理中", "完了"]

        for progress, status in zip(test_progress_values, test_status_messages):
            extraction_worker.progress_updated.emit(progress)
            extraction_worker.status_updated.emit(status)

        # イベントループを回して信号を処理
        QTest.qWait(100)

        # シグナルが正しく受信されることを確認
        assert progress_values == test_progress_values, "プログレス値が正しく受信されていない"
        assert status_messages == test_status_messages, "ステータスメッセージが正しく受信されていない"

    def test_progress_dialog_creation(self, qapp):
        """プログレスダイアログ作成テスト"""
        from PySide6.QtWidgets import QProgressDialog

        # プログレスダイアログを作成
        progress_dialog = QProgressDialog("処理中...", "キャンセル", 0, 100)
        progress_dialog.setWindowTitle("字幕抽出中")

        # ダイアログが正しく設定されていることを確認
        assert progress_dialog.minimum() == 0, "最小値が正しくない"
        assert progress_dialog.maximum() == 100, "最大値が正しくない"
        assert progress_dialog.labelText() == "処理中...", "ラベルテキストが正しくない"
        assert progress_dialog.windowTitle() == "字幕抽出中", "ウィンドウタイトルが正しくない"

    def test_progress_bar_updates(self, qapp):
        """プログレスバー更新テスト"""
        # プログレスバーを作成
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)

        # 値を設定
        test_values = [0, 10, 30, 60, 90, 100]

        for value in test_values:
            progress_bar.setValue(value)
            assert progress_bar.value() == value, f"プログレスバーの値が正しくない: {progress_bar.value()} != {value}"

    def test_long_operation_progress_simulation(self, extraction_worker, qapp):
        """長時間操作のプログレスシミュレーションテスト"""
        # モックを使用して長時間操作をシミュレート
        progress_updates = []
        status_updates = []

        def track_progress(value):
            progress_updates.append(value)

        def track_status(message):
            status_updates.append(message)

        extraction_worker.progress_updated.connect(track_progress)
        extraction_worker.status_updated.connect(track_status)

        # 長時間操作をシミュレート
        operation_steps = [
            (0, "初期化中"),
            (10, "動画読み込み中"),
            (25, "フレーム抽出中 (1/4)"),
            (50, "フレーム抽出中 (2/4)"),
            (75, "OCR処理中"),
            (90, "結果整理中"),
            (100, "完了")
        ]

        for progress, status in operation_steps:
            extraction_worker.progress_updated.emit(progress)
            extraction_worker.status_updated.emit(status)
            QTest.qWait(50)  # 短い待機で操作をシミュレート

        # 全てのプログレス更新が記録されていることを確認
        assert len(progress_updates) == len(operation_steps), "プログレス更新数が正しくない"
        assert len(status_updates) == len(operation_steps), "ステータス更新数が正しくない"

        # 最終的に100%に達していることを確認
        assert progress_updates[-1] == 100, "最終プログレスが100%でない"
        assert "完了" in status_updates[-1], "完了ステータスが含まれていない"

    def test_progress_cancellation(self, extraction_worker, qapp):
        """プログレスキャンセル機能のテスト"""
        # キャンセレーションフラグをテスト
        extraction_worker.request_cancellation()

        # キャンセル要求が正しく設定されていることを確認
        assert extraction_worker.is_cancellation_requested(), "キャンセル要求が設定されていない"

        # キャンセル後の状態リセット
        extraction_worker.reset_cancellation()
        assert not extraction_worker.is_cancellation_requested(), "キャンセル状態がリセットされていない"

    def test_indeterminate_progress(self, qapp):
        """不確定プログレスのテスト"""
        # 不確定プログレスバーを作成
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 0)  # 不確定モード

        # 不確定モードが設定されていることを確認
        assert progress_bar.minimum() == 0, "不確定プログレスの最小値が正しくない"
        assert progress_bar.maximum() == 0, "不確定プログレスの最大値が正しくない"

        # 不確定プログレス中のアニメーション確認（実装依存）
        progress_bar.show()
        QTest.qWait(500)  # アニメーションを観察

    def test_nested_progress_operations(self, qapp):
        """ネストしたプログレス操作のテスト"""
        # メインプログレスダイアログ
        main_progress = QProgressDialog("メイン処理中...", "キャンセル", 0, 100)

        # サブプログレスバー
        sub_progress = QProgressBar()
        sub_progress.setRange(0, 100)

        # ネストした操作をシミュレート
        main_steps = 5
        sub_steps = 20

        for main_step in range(main_steps):
            main_progress.setValue((main_step * 100) // main_steps)

            # サブ操作
            for sub_step in range(sub_steps):
                sub_progress.setValue((sub_step * 100) // sub_steps)
                QTest.qWait(10)

            QTest.qWait(50)

        main_progress.setValue(100)

        # 最終状態の確認
        assert main_progress.value() == 100, "メインプログレスが完了していない"
        assert sub_progress.value() == 100, "サブプログレスが完了していない"

    def test_progress_error_handling(self, extraction_worker, qapp):
        """プログレスエラーハンドリングのテスト"""
        error_occurred = False
        error_message = ""

        def on_error(message):
            nonlocal error_occurred, error_message
            error_occurred = True
            error_message = message

        # エラーシグナルを接続（存在する場合）
        if hasattr(extraction_worker, 'error_occurred'):
            extraction_worker.error_occurred.connect(on_error)

            # エラーをシミュレート
            extraction_worker.error_occurred.emit("テストエラー")
            QTest.qWait(100)

            # エラーが正しく処理されることを確認
            assert error_occurred, "エラーが検出されていない"
            assert "テストエラー" in error_message, "エラーメッセージが正しくない"

    def test_progress_with_file_operations(self, qapp):
        """ファイル操作でのプログレステスト"""
        import tempfile
        import os

        # 一時ファイルを作成してプログレス付きで処理
        temp_files = []
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 10)

        try:
            for i in range(10):
                # ファイル作成をシミュレート
                with tempfile.NamedTemporaryFile(delete=False) as f:
                    temp_files.append(f.name)
                    f.write(b"test data")

                # プログレス更新
                progress_bar.setValue(i + 1)
                QTest.qWait(50)

            # 完了状態の確認
            assert progress_bar.value() == 10, "ファイル操作プログレスが完了していない"

        finally:
            # クリーンアップ
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass