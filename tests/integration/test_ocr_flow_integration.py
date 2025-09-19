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

from app.core.extractor.detector import FrameBasedSubtitleDetector
from app.core.extractor.group import DuplicateAwareSubtitleGrouper
from app.core.extractor.ocr import SimplePaddleOCREngine
from app.core.extractor.roi import SubtitleROIExtractor
from app.core.extractor.sampler import VideoFrameSampler
from app.core.format.srt import SRTWriter
from app.core.models import SubtitleItem
from app.ui.extraction_worker import ExtractionWorker


class TestOCRFlowIntegration:
    """OCRフロー統合テスト"""

    @pytest.fixture
    def mock_video_file(self):
        """テスト用動画ファイルのモック"""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = Path(f.name)

        # 簡単なテスト動画を作成（黒い画面に白いテキスト）
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (640, 480))

        for i in range(90):  # 3秒間（30fps）
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

            # 字幕テキストをフレームに描画
            if 30 <= i < 60:  # 1-2秒の間に字幕を表示
                cv2.putText(frame, "Test Subtitle", (50, 400),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            out.write(frame)

        out.release()
        yield video_path

        # クリーンアップ
        if video_path.exists():
            video_path.unlink()

    @pytest.fixture
    def extraction_components(self):
        """抽出コンポーネントのセット"""
        sampler = VideoFrameSampler()
        roi_extractor = SubtitleROIExtractor()
        detector = FrameBasedSubtitleDetector()
        ocr_engine = SimplePaddleOCREngine()
        grouper = DuplicateAwareSubtitleGrouper()

        return {
            'sampler': sampler,
            'roi_extractor': roi_extractor,
            'detector': detector,
            'ocr_engine': ocr_engine,
            'grouper': grouper
        }

    def test_complete_ocr_pipeline_flow(self, mock_video_file, extraction_components):
        """完全なOCRパイプラインフローのテスト"""
        # Step 1: 動画からフレームをサンプリング
        sampler = extraction_components['sampler']
        frames = sampler.sample_frames(str(mock_video_file), fps=1.0)

        assert len(frames) > 0, "フレームがサンプリングされていない"

        # Step 2: ROI抽出
        roi_extractor = extraction_components['roi_extractor']
        roi_frames = []

        for frame_data in frames:
            roi = roi_extractor.extract_subtitle_region(frame_data.frame)
            if roi is not None:
                roi_frames.append((frame_data.timestamp_ms, roi))

        # Step 3: 字幕検出
        detector = extraction_components['detector']
        detected_frames = []

        for timestamp, roi in roi_frames:
            if detector.has_subtitle(roi):
                detected_frames.append((timestamp, roi))

        # Step 4: OCR処理
        ocr_engine = extraction_components['ocr_engine']
        raw_subtitles = []

        for timestamp, roi in detected_frames:
            text = ocr_engine.extract_text(roi)
            if text.strip():
                raw_subtitles.append(SubtitleItem(
                    index=len(raw_subtitles) + 1,
                    start_ms=timestamp,
                    end_ms=timestamp + 1000,  # 1秒間とする
                    text=text.strip()
                ))

        # Step 5: グループ化と重複除去
        grouper = extraction_components['grouper']
        final_subtitles = grouper.group_subtitles(raw_subtitles)

        # 結果の検証
        assert len(final_subtitles) > 0, "字幕が抽出されていない"

        # 最初の字幕にテキストが含まれていることを確認
        first_subtitle = final_subtitles[0]
        assert first_subtitle.text, "字幕テキストが空"
        assert first_subtitle.start_ms >= 0, "開始時間が無効"
        assert first_subtitle.end_ms > first_subtitle.start_ms, "終了時間が無効"

    def test_extraction_worker_integration(self, qapp, mock_video_file):
        """ExtractionWorkerとの統合テスト"""
        worker = ExtractionWorker()

        # モック設定
        worker.ocr_engine = Mock()
        worker.ocr_engine.extract_text.return_value = "Extracted Text"

        results = []
        errors = []

        def on_result(subtitles):
            results.append(subtitles)

        def on_error(error_msg):
            errors.append(error_msg)

        worker.extraction_completed.connect(on_result)
        worker.error_occurred.connect(on_error)

        # 抽出開始
        worker.extract_from_video(
            video_path=str(mock_video_file),
            roi_config={"x": 0, "y": 300, "width": 640, "height": 100},
            sampling_fps=1.0
        )

        # 完了を待つ（タイムアウト付き）
        timeout = 10000  # 10秒
        timer = QTimer()
        timer.timeout.connect(lambda: qapp.quit())
        timer.start(timeout)

        while not results and not errors and timer.isActive():
            qapp.processEvents()

        timer.stop()

        # 結果の検証
        if errors:
            pytest.fail(f"抽出エラーが発生: {errors[0]}")

        assert len(results) > 0, "抽出結果が返されていない"
        subtitles = results[0]
        assert isinstance(subtitles, list), "字幕リストが返されていない"

    def test_error_handling_in_pipeline(self, extraction_components):
        """パイプラインでのエラーハンドリングテスト"""
        # 無効な動画パスでのテスト
        sampler = extraction_components['sampler']

        with pytest.raises(Exception):
            sampler.sample_frames("nonexistent_video.mp4", fps=1.0)

        # 無効な画像データでのテスト
        ocr_engine = extraction_components['ocr_engine']

        # 空の画像
        empty_image = np.zeros((0, 0, 3), dtype=np.uint8)
        result = ocr_engine.extract_text(empty_image)
        assert result == "", "空の画像に対して空文字を返すべき"

        # 無効な形状の画像
        invalid_image = np.zeros((10,), dtype=np.uint8)
        result = ocr_engine.extract_text(invalid_image)
        assert result == "", "無効な画像に対して空文字を返すべき"

    def test_srt_export_integration(self, extraction_components):
        """SRTエクスポート統合テスト"""
        # テスト用字幕データを作成
        subtitles = [
            SubtitleItem(1, 1000, 3000, "最初の字幕"),
            SubtitleItem(2, 4000, 6000, "2番目の字幕"),
            SubtitleItem(3, 7000, 9000, "最後の字幕")
        ]

        # SRTファイルに書き出し
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
            srt_path = Path(f.name)

        writer = SRTWriter()
        writer.write_srt_file(subtitles, str(srt_path))

        # ファイルが作成されていることを確認
        assert srt_path.exists(), "SRTファイルが作成されていない"

        # ファイル内容の確認
        content = srt_path.read_text(encoding='utf-8')
        assert "最初の字幕" in content, "字幕テキストがファイルに含まれていない"
        assert "00:00:01,000 --> 00:00:03,000" in content, "タイムコードが正しくない"

        # クリーンアップ
        srt_path.unlink()

    @patch('app.core.extractor.ocr.PaddleOCR')
    def test_ocr_engine_initialization_integration(self, mock_paddle_ocr, extraction_components):
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
        assert result == "テストテキスト", f"期待されるテキストが返されていない: {result}"
        mock_ocr_instance.ocr.assert_called_once()

    def test_memory_efficiency_in_pipeline(self, mock_video_file, extraction_components):
        """パイプラインでのメモリ効率テスト"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # 大量のフレーム処理をシミュレート
        sampler = extraction_components['sampler']

        # メモリ使用量を監視しながら処理
        for i in range(5):  # 複数回処理を実行
            frames = sampler.sample_frames(str(mock_video_file), fps=0.5)

            # 各フレームを処理
            for frame_data in frames:
                # 簡単な処理をシミュレート
                processed = cv2.resize(frame_data.frame, (320, 240))
                del processed

            del frames

        # メモリリークがないことを確認（大まかなチェック）
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # 50MB以上のメモリ増加は異常とみなす
        assert memory_increase < 50 * 1024 * 1024, f"メモリリークの可能性: {memory_increase / 1024 / 1024:.1f}MB増加"

    def test_concurrent_processing_safety(self, mock_video_file, extraction_components):
        """並行処理の安全性テスト"""
        from concurrent.futures import ThreadPoolExecutor
        import threading

        ocr_engine = extraction_components['ocr_engine']
        results = []
        errors = []
        lock = threading.Lock()

        def process_frame(frame_index):
            try:
                # テスト用フレームを作成
                frame = np.zeros((100, 300, 3), dtype=np.uint8)
                cv2.putText(frame, f"Frame {frame_index}", (10, 50),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                # OCR処理
                text = ocr_engine.extract_text(frame)

                with lock:
                    results.append((frame_index, text))

            except Exception as e:
                with lock:
                    errors.append((frame_index, str(e)))

        # 複数スレッドで並行処理
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(process_frame, i) for i in range(5)]

            # 全ての処理の完了を待つ
            for future in futures:
                future.result(timeout=30)

        # エラーがないことを確認
        assert len(errors) == 0, f"並行処理でエラーが発生: {errors}"

        # 結果が期待される数だけ返されていることを確認
        assert len(results) == 5, f"期待される結果数と異なる: {len(results)}"