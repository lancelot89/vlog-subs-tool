"""
字幕抽出ワーカー（別スレッド処理）
"""

from PySide6.QtCore import QThread, Signal, QObject
from typing import List, Optional

from app.core.models import SubtitleItem, ProjectSettings
from app.core.extractor.detector import SubtitleDetector


class ExtractionWorker(QThread):
    """字幕抽出ワーカースレッド"""
    
    # シグナル定義
    progress_updated = Signal(int, str)  # プログレス更新 (percentage, message)
    subtitles_extracted = Signal(list)   # 抽出完了 (subtitle_items)
    error_occurred = Signal(str)         # エラー発生 (error_message)
    
    def __init__(self, video_path: str, settings: ProjectSettings):
        super().__init__()
        self.video_path = video_path
        self.settings = settings
        self.detector: Optional[SubtitleDetector] = None
        self._is_cancelled = False
    
    def run(self):
        """ワーカーメイン処理"""
        try:
            # 検出器の初期化
            self.detector = SubtitleDetector(self.settings)
            
            # プログレスコールバックを設定
            self.detector.set_progress_callback(self._on_progress)
            
            # キャンセルチェック
            if self._is_cancelled:
                return
            
            # 字幕抽出実行
            subtitle_items = self.detector.detect_subtitles(self.video_path)
            
            # キャンセルチェック
            if self._is_cancelled:
                return
            
            # 結果を通知
            self.subtitles_extracted.emit(subtitle_items)
            
        except Exception as e:
            if not self._is_cancelled:
                self.error_occurred.emit(str(e))
    
    def _on_progress(self, percentage: int, message: str):
        """プログレスコールバック"""
        if not self._is_cancelled:
            self.progress_updated.emit(percentage, message)
    
    def cancel(self):
        """抽出処理をキャンセル"""
        self._is_cancelled = True
        if self.detector:
            # TODO: 検出器のキャンセル機能を実装
            pass
    
    def cleanup(self):
        """リソースクリーンアップ"""
        if self.detector:
            self.detector._cleanup()
            self.detector = None