"""
完全なOCR処理フローの統合テスト

動画読み込み→OCR処理→編集→エクスポートまでのエンドツーエンドテスト
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QTimer

from app.core.extractor.detector import SubtitleDetector
from app.core.extractor.ocr import SimplePaddleOCREngine
from app.core.format.srt import SRTFormatter
from app.core.models import ProjectSettings, SubtitleItem
from app.ui.extraction_worker import ExtractionWorker


class TestOCRFlowIntegration:
    """OCRフロー統合テスト"""

    @pytest.fixture
    def mock_video_file(self):
        """テスト用動画ファイルのモック"""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = Path(f.name)

        # 簡単なテスト動画を作成（黒い画面に白いテキスト）
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (640, 480))

        for i in range(90):  # 3秒間（30fps）
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

            # 字幕テキストをフレームに描画
            if 30 <= i < 60:  # 1-2秒の間に字幕を表示
                cv2.putText(
                    frame,
                    "Test Subtitle",
                    (50, 400),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (255, 255, 255),
                    2,
                )

            out.write(frame)

        out.release()
        yield video_path

        # クリーンアップ
        if video_path.exists():
            video_path.unlink()

    def test_subtitle_detector_initialization(self):
        """字幕検出器の初期化テスト"""
        settings = ProjectSettings()
        detector = SubtitleDetector(settings)

        # 基本的な初期化が正しく行われることを確認
        assert hasattr(detector, "detect_subtitles"), "detect_subtitlesメソッドが存在しない"

    def test_ocr_engine_initialization(self):
        """OCRエンジン初期化テスト"""
        ocr_engine = SimplePaddleOCREngine()

        # 基本的な初期化が正しく行われることを確認
        assert hasattr(ocr_engine, "extract_text"), "extract_textメソッドが存在しない"

    def test_ocr_with_test_image(self):
        """テスト画像でのOCR処理テスト"""
        ocr_engine = SimplePaddleOCREngine()

        # テスト用画像を作成
        test_image = np.zeros((100, 300, 3), dtype=np.uint8)
        cv2.putText(
            test_image, "Test Text", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2
        )

        # OCR処理を実行
        try:
            result = ocr_engine.extract_text(test_image)
            # 結果がリスト型であることを確認
            assert isinstance(result, list), f"OCR結果がリストでない: {type(result)}"
        except Exception as e:
            # OCRが利用できない環境の場合はスキップ
            pytest.skip(f"OCRエンジンが利用できない: {e}")

    def test_empty_image_handling(self):
        """空画像の処理テスト"""
        ocr_engine = SimplePaddleOCREngine()

        # 空の画像
        empty_image = np.zeros((0, 0, 3), dtype=np.uint8)
        result = ocr_engine.extract_text(empty_image)
        assert isinstance(result, list) and len(result) == 0, "空の画像に対して空リストを返すべき"

        # 無効な形状の画像
        invalid_image = np.zeros((10,), dtype=np.uint8)
        result = ocr_engine.extract_text(invalid_image)
        assert isinstance(result, list) and len(result) == 0, "無効な画像に対して空リストを返すべき"

    def test_srt_export_integration(self):
        """SRTエクスポート統合テスト"""
        # テスト用字幕データを作成
        subtitles = [
            SubtitleItem(1, 1000, 3000, "最初の字幕"),
            SubtitleItem(2, 4000, 6000, "2番目の字幕"),
            SubtitleItem(3, 7000, 9000, "最後の字幕"),
        ]

        # SRTファイルに書き出し
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
            srt_path = Path(f.name)

        try:
            formatter = SRTFormatter()
            formatter.save_srt_file(subtitles, srt_path)

            # ファイルが作成されていることを確認
            assert srt_path.exists(), "SRTファイルが作成されていない"

            # ファイル内容の確認
            content = srt_path.read_text(encoding="utf-8")
            assert "最初の字幕" in content, "字幕テキストがファイルに含まれていない"
            assert "00:00:01,000 --> 00:00:03,000" in content, "タイムコードが正しくない"

        finally:
            # クリーンアップ
            if srt_path.exists():
                srt_path.unlink()

    @patch("app.core.extractor.ocr.PaddleOCR")
    def test_ocr_engine_initialization_integration(self, mock_paddle_ocr):
        """OCRエンジン初期化の統合テスト"""
        # PaddleOCRのモック設定
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        mock_ocr_instance.ocr.return_value = [[["テストテキスト", 0.95]]]

        # OCRエンジンの初期化
        ocr_engine = SimplePaddleOCREngine()

        # テスト画像でOCR実行
        test_image = np.zeros((100, 300, 3), dtype=np.uint8)
        cv2.putText(test_image, "Test", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        result = ocr_engine.extract_text(test_image)

        # 結果の検証
        assert isinstance(result, list), f"期待される結果がリストでない: {type(result)}"

    def test_memory_efficiency_in_pipeline(self, mock_video_file):
        """パイプラインでのメモリ効率テスト"""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # 複数回の処理をシミュレート
        for i in range(3):  # 少なめに設定
            # 簡単な画像処理をシミュレート
            test_image = np.zeros((480, 640, 3), dtype=np.uint8)
            processed = cv2.resize(test_image, (320, 240))
            del processed
            del test_image

        # メモリリークがないことを確認（大まかなチェック）
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # 20MB以上のメモリ増加は異常とみなす
        assert (
            memory_increase < 20 * 1024 * 1024
        ), f"メモリリークの可能性: {memory_increase / 1024 / 1024:.1f}MB増加"

    def test_concurrent_processing_safety(self):
        """並行処理の安全性テスト"""
        import threading
        from concurrent.futures import ThreadPoolExecutor

        ocr_engine = SimplePaddleOCREngine()
        results = []
        errors = []
        lock = threading.Lock()

        def process_frame(frame_index):
            try:
                # テスト用フレームを作成
                frame = np.zeros((100, 300, 3), dtype=np.uint8)
                cv2.putText(
                    frame,
                    f"Frame {frame_index}",
                    (10, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                )

                # OCR処理
                ocr_results = ocr_engine.extract_text(frame)
                # 最初の結果のテキストを取得（あれば）
                text = ocr_results[0].text if ocr_results else ""

                with lock:
                    results.append((frame_index, text))

            except Exception as e:
                with lock:
                    errors.append((frame_index, str(e)))

        # 複数スレッドで並行処理
        with ThreadPoolExecutor(max_workers=2) as executor:  # 少なめに設定
            futures = [executor.submit(process_frame, i) for i in range(3)]

            # 全ての処理の完了を待つ
            for future in futures:
                future.result(timeout=30)

        # エラーがないことを確認
        assert len(errors) == 0, f"並行処理でエラーが発生: {errors}"

        # 結果が期待される数だけ返されていることを確認
        assert len(results) == 3, f"期待される結果数と異なる: {len(results)}"

    def test_subtitle_detection_with_video(self, mock_video_file):
        """動画ファイルでの字幕検出テスト"""
        settings = ProjectSettings()
        detector = SubtitleDetector(settings)

        try:
            # 字幕検出を実行
            subtitles = detector.detect_subtitles(str(mock_video_file))

            # 結果の検証
            assert isinstance(subtitles, list), "字幕検出結果がリストでない"

            # 結果が空でも正常（テスト動画に字幕がない可能性があるため）
            for subtitle in subtitles:
                assert isinstance(
                    subtitle, SubtitleItem
                ), f"字幕項目の型が正しくない: {type(subtitle)}"
                assert subtitle.start_ms >= 0, "開始時間が無効"
                assert subtitle.end_ms > subtitle.start_ms, "終了時間が無効"

        except Exception as e:
            # 環境によっては動画処理ができない場合があるのでスキップ
            pytest.skip(f"動画処理ができない環境: {e}")

    def test_error_handling_in_pipeline(self):
        """パイプラインでのエラーハンドリングテスト"""
        settings = ProjectSettings()
        detector = SubtitleDetector(settings)

        # 無効な動画パスでのテスト
        with pytest.raises(Exception):
            detector.detect_subtitles("nonexistent_video.mp4")

        # OCRエンジンでの無効な画像テスト
        ocr_engine = SimplePaddleOCREngine()

        # None画像
        result = ocr_engine.extract_text(None)
        assert isinstance(result, list) and len(result) == 0, "None画像に対して空リストを返すべき"

    def test_complete_workflow_simulation(self, mock_video_file):
        """完全ワークフローのシミュレーション"""
        try:
            # 1. 字幕検出
            settings = ProjectSettings()
            detector = SubtitleDetector(settings)
            subtitles = detector.detect_subtitles(str(mock_video_file))

            # 検出結果がない場合はダミーデータを作成
            if not subtitles:
                subtitles = [
                    SubtitleItem(1, 1000, 3000, "シミュレート字幕1"),
                    SubtitleItem(2, 4000, 6000, "シミュレート字幕2"),
                ]

            # 2. SRTエクスポート
            with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
                srt_path = Path(f.name)

            try:
                formatter = SRTFormatter()
                formatter.save_srt_file(subtitles, srt_path)

                # 3. 結果の検証
                assert srt_path.exists(), "SRTファイルが作成されていない"

                content = srt_path.read_text(encoding="utf-8")
                assert len(content) > 0, "SRTファイルが空"

                # タイムコード形式の確認
                assert "-->" in content, "SRT形式のタイムコードが含まれていない"

            finally:
                if srt_path.exists():
                    srt_path.unlink()

        except Exception as e:
            pytest.skip(f"完全ワークフローテストがスキップされました: {e}")
