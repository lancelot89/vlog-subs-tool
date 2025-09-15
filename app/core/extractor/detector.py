"""
統合字幕検出器 - すべてのコンポーネントを統合
"""

import logging
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from app.core.models import SubtitleItem, ProjectSettings
from .sampler import VideoSampler, BottomROISampler, VideoFrame
from .roi import ROIManager, ROIMode, ROIRegion
from .ocr import OCRManager, OCRResult
from .group import FrameOCRResult, ExtractionProcessor


class SubtitleDetector:
    """統合字幕検出器"""
    
    def __init__(self, settings: ProjectSettings):
        """
        Args:
            settings: プロジェクト設定
        """
        self.settings = settings
        self.ocr_manager = OCRManager()
        self.roi_manager: Optional[ROIManager] = None
        self.sampler: Optional[VideoSampler] = None
        
        # プログレスコールバック
        self.progress_callback: Optional[Callable[[int, str], None]] = None
        
        # ログ設定
        self.logger = logging.getLogger(__name__)
        
        # OCRエンジンの初期化（組み込みモデル優先で自動選択）
        preferred_engine = self._get_preferred_ocr_engine()

        if preferred_engine:
            # 設定で特定のエンジンが指定されている場合は、それを試行
            if not self.ocr_manager.initialize_engine(preferred_engine):
                self.logger.warning(f"設定されたOCRエンジンの初期化に失敗: {preferred_engine}")
                # フォールバックして自動選択
                if not self.ocr_manager.initialize_best_available_engine():
                    raise RuntimeError("利用可能なOCRエンジンがありません")
            else:
                self.logger.info(f"設定されたOCRエンジンで初期化: {preferred_engine}")
        else:
            # 設定がない場合は自動選択
            if not self.ocr_manager.initialize_best_available_engine():
                raise RuntimeError("利用可能なOCRエンジンがありません")

        current_engine_info = self.ocr_manager.get_engine_info()
        self.logger.info(f"字幕検出器を初期化しました: {current_engine_info}")
    
    def _get_preferred_ocr_engine(self) -> Optional[str]:
        """設定から優先OCRエンジン名を取得"""
        ocr_engine = self.settings.ocr_engine

        if ocr_engine == "paddleocr_ja":
            # 組み込みモデルがあれば優先、なければ従来版
            if 'paddleocr_bundled' in self.ocr_manager.get_available_engines():
                return "paddleocr_bundled"
            else:
                return "paddleocr"
        elif ocr_engine == "tesseract_jpn":
            return "tesseract"
        else:
            # 設定がない場合はNone（自動選択）
            return None
    
    def set_progress_callback(self, callback: Callable[[int, str], None]):
        """プログレスコールバックを設定"""
        self.progress_callback = callback
    
    def _emit_progress(self, percentage: int, message: str):
        """プログレス通知を発信"""
        if self.progress_callback:
            self.progress_callback(percentage, message)
        self.logger.info(f"[{percentage}%] {message}")
    
    def detect_subtitles(self, video_path: str) -> List[SubtitleItem]:
        """
        動画から字幕を検出
        
        Args:
            video_path: 動画ファイルパス
            
        Returns:
            List[SubtitleItem]: 検出された字幕アイテム
        """
        try:
            self.logger.info(f"字幕検出開始: {video_path}")
            start_time = time.time()
            
            # Step 1: 動画サンプリングの準備
            self._emit_progress(10, "動画を読み込んでいます...")
            self._initialize_sampler(video_path)
            
            # Step 2: ROI検出
            self._emit_progress(20, "字幕領域を検出しています...")
            roi_region = self._detect_roi()
            
            # Step 3: フレームサンプリング
            self._emit_progress(30, "フレームをサンプリングしています...")
            frames = self._sample_frames(roi_region)
            
            if not frames:
                self._emit_progress(100, "字幕が検出されませんでした")
                return []
            
            # Step 4: OCR実行
            self._emit_progress(50, f"OCRを実行しています... ({len(frames)}フレーム)")
            frame_results = self._perform_ocr(frames)
            
            # Step 5: グルーピング・統合
            self._emit_progress(80, "字幕をグルーピングしています...")
            subtitle_items = self._group_subtitles(frame_results)
            
            # Step 6: 完了
            elapsed_time = time.time() - start_time
            self._emit_progress(100, f"検出完了: {len(subtitle_items)}件 ({elapsed_time:.1f}秒)")
            
            self.logger.info(f"字幕検出完了: {len(subtitle_items)}件の字幕を検出")
            return subtitle_items
            
        except Exception as e:
            self.logger.error(f"字幕検出エラー: {e}")
            self._emit_progress(100, f"エラーが発生しました: {str(e)}")
            raise
        
        finally:
            self._cleanup()
    
    def _initialize_sampler(self, video_path: str):
        """サンプラーの初期化"""
        if self.settings.roi_mode == "bottom_30" or not self.settings.roi_rect:
            # 下段30%専用サンプラー
            self.sampler = BottomROISampler(
                video_path,
                sample_fps=self.settings.fps_sample,
                bottom_ratio=0.3  # 30%
            )
        else:
            # 汎用サンプラー
            self.sampler = VideoSampler(
                video_path,
                sample_fps=self.settings.fps_sample
            )
        
        # ROIManagerの初期化
        video_info = self.sampler.video_info
        self.roi_manager = ROIManager(
            video_info['width'],
            video_info['height']
        )
        
        # 手動ROIが設定されている場合
        if self.settings.roi_rect:
            self.roi_manager.set_manual_roi(self.settings.roi_rect)
    
    def _detect_roi(self) -> ROIRegion:
        """ROI領域の検出"""
        # 検出用にいくつかのサンプルフレームを取得
        sample_frames = []
        frame_count = 0
        
        for frame in self.sampler.sample_frames():
            sample_frames.append(frame)
            frame_count += 1
            if frame_count >= 10:  # 10フレームで十分
                break
        
        # ROIモードの変換
        roi_mode_map = {
            "auto": ROIMode.AUTO,
            "bottom_30": ROIMode.BOTTOM_30,
            "manual": ROIMode.MANUAL
        }
        
        roi_mode = roi_mode_map.get(self.settings.roi_mode, ROIMode.BOTTOM_30)
        
        # ROI検出実行
        roi_region = self.roi_manager.detect_roi(roi_mode, sample_frames)
        
        self.logger.info(f"ROI検出完了: {roi_region.rect}, 信頼度: {roi_region.confidence}")
        return roi_region
    
    def _sample_frames(self, roi_region: ROIRegion) -> List[VideoFrame]:
        """ROI領域でフレームサンプリング"""
        frames = []
        
        if isinstance(self.sampler, BottomROISampler):
            # 下段専用サンプラーの場合
            for frame in self.sampler.sample_bottom_frames():
                frames.append(frame)
        else:
            # 汎用サンプラーの場合
            for frame in self.sampler.extract_roi_frames(roi_region.rect):
                frames.append(frame)
        
        self.logger.info(f"フレームサンプリング完了: {len(frames)}フレーム")
        return frames
    
    def _perform_ocr(self, frames: List[VideoFrame]) -> List[FrameOCRResult]:
        """OCR実行"""
        frame_results = []
        total_frames = len(frames)
        
        # 並列処理用の設定
        max_workers = min(4, total_frames)  # 最大4並列
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # OCRタスクを並列実行
            future_to_frame = {
                executor.submit(self._ocr_single_frame, frame): frame 
                for frame in frames
            }
            
            completed_count = 0
            
            for future in as_completed(future_to_frame):
                frame = future_to_frame[future]
                
                try:
                    ocr_results = future.result()
                    
                    if ocr_results:  # OCR結果がある場合のみ追加
                        frame_results.append(FrameOCRResult(
                            frame=frame,
                            ocr_results=ocr_results
                        ))
                    
                except Exception as e:
                    self.logger.warning(f"フレーム {frame.frame_number} のOCR処理に失敗: {e}")
                
                completed_count += 1
                
                # プログレス更新
                progress = 50 + int((completed_count / total_frames) * 30)
                self._emit_progress(progress, f"OCR処理中... ({completed_count}/{total_frames})")
        
        # 時間順にソート
        frame_results.sort(key=lambda x: x.frame.timestamp_ms)
        
        self.logger.info(f"OCR処理完了: {len(frame_results)}フレームでテキストを検出")
        return frame_results
    
    def _ocr_single_frame(self, frame: VideoFrame) -> List[OCRResult]:
        """単一フレームのOCR処理"""
        try:
            return self.ocr_manager.extract_text(frame.image)
        except Exception as e:
            self.logger.warning(f"フレーム {frame.frame_number} のOCR失敗: {e}")
            return []
    
    def _group_subtitles(self, frame_results: List[FrameOCRResult]) -> List[SubtitleItem]:
        """字幕のグルーピング・統合"""
        # 設定の変換
        grouping_settings = {
            'similarity_threshold': self.settings.similarity_threshold,
            'min_duration_sec': self.settings.min_dur_sec,
            'max_gap_sec': 0.5  # 固定値
        }
        
        # グルーピング処理器を作成
        processor = ExtractionProcessor(grouping_settings)
        
        # グルーピング実行
        subtitle_items = processor.process_extraction_results(frame_results)
        
        self.logger.info(f"グルーピング完了: {len(subtitle_items)}件の字幕")
        return subtitle_items
    
    def _cleanup(self):
        """リソースの解放"""
        if self.sampler:
            self.sampler.close()
            self.sampler = None
    
    def get_detection_info(self) -> Dict[str, Any]:
        """検出情報を取得"""
        info = {
            'settings': {
                'fps_sample': self.settings.fps_sample,
                'roi_mode': self.settings.roi_mode,
                'ocr_engine': self.settings.ocr_engine,
                'similarity_threshold': self.settings.similarity_threshold,
                'min_duration_sec': self.settings.min_dur_sec
            }
        }
        
        if self.sampler:
            info['video_info'] = self.sampler.video_info
        
        info['ocr_info'] = self.ocr_manager.get_engine_info()
        
        return info


class DetectionStatus:
    """検出状態の管理"""
    
    def __init__(self):
        self.is_running = False
        self.current_step = ""
        self.progress = 0
        self.start_time: Optional[float] = None
        self.error: Optional[str] = None
    
    def start(self):
        """検出開始"""
        self.is_running = True
        self.progress = 0
        self.current_step = "初期化中..."
        self.start_time = time.time()
        self.error = None
    
    def update(self, progress: int, step: str):
        """状態更新"""
        self.progress = progress
        self.current_step = step
    
    def complete(self):
        """検出完了"""
        self.is_running = False
        self.progress = 100
        self.current_step = "完了"
    
    def fail(self, error: str):
        """検出失敗"""
        self.is_running = False
        self.error = error
        self.current_step = f"エラー: {error}"
    
    @property
    def elapsed_time(self) -> float:
        """経過時間（秒）"""
        if not self.start_time:
            return 0.0
        return time.time() - self.start_time