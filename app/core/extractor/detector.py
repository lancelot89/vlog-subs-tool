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
from .ocr import SimplePaddleOCREngine, OCRResult
from .group import FrameOCRResult, ExtractionProcessor


class SubtitleDetector:
    """統合字幕検出器"""
    
    def __init__(self, settings: ProjectSettings):
        """
        Args:
            settings: プロジェクト設定
        """
        self.settings = settings
        self.ocr_engine = SimplePaddleOCREngine()
        self.roi_manager: Optional[ROIManager] = None
        self.sampler: Optional[VideoSampler] = None
        
        # プログレスコールバック（進捗率、メッセージ、ETA情報を含む）
        self.progress_callback: Optional[Callable[[int, str], None]] = None

        # ETA計算用変数
        self.start_time: Optional[float] = None
        self.phase_weights = {
            'init': 5,           # 初期化: 5%
            'roi_detection': 10, # ROI検出: 10%
            'sampling': 15,      # サンプリング: 15%
            'ocr': 60,          # OCR処理: 60%
            'grouping': 10      # グルーピング: 10%
        }

        # キャンセル機能
        self._is_cancelled = False

        # ログ設定
        self.logger = logging.getLogger(__name__)
        
        # SimplePaddleOCREngineの初期化
        if not self.ocr_engine.initialize():
            raise RuntimeError("PaddleOCRエンジンの初期化に失敗しました")

        self.logger.info("字幕検出器を初期化しました: SimplePaddleOCREngine")
    
    
    def set_progress_callback(self, callback: Callable[[int, str], None]):
        """プログレスコールバックを設定"""
        self.progress_callback = callback

    def _emit_progress(self, percentage: int, message: str):
        """プログレス通知を発信（ETA情報付き）"""
        # ETA計算
        eta_info = self._calculate_eta(percentage)

        # メッセージにETA情報を含める
        if eta_info and percentage >= 10:  # 10%以降からETA表示
            enhanced_message = f"{message} (残り約{eta_info['remaining_str']}, {eta_info['completion_time']}頃完了予定)"
        else:
            enhanced_message = message

        if self.progress_callback:
            self.progress_callback(percentage, enhanced_message)
        self.logger.info(f"[{percentage}%] {enhanced_message}")

    def _calculate_eta(self, current_progress: int) -> Optional[dict]:
        """ETA（予定完了時間）を計算"""
        if not self.start_time or current_progress <= 5:
            return None

        elapsed_time = time.time() - self.start_time

        if current_progress <= 0:
            return None

        # 推定総時間 = 経過時間 / (進捗率 / 100)
        estimated_total_time = elapsed_time / (current_progress / 100)
        remaining_time = estimated_total_time - elapsed_time

        if remaining_time <= 0:
            return None

        # 残り時間を分秒で表示
        if remaining_time >= 60:
            remaining_str = f"{int(remaining_time // 60)}分{int(remaining_time % 60)}秒"
        else:
            remaining_str = f"{int(remaining_time)}秒"

        # 完了予定時刻
        from datetime import datetime, timedelta
        completion_time = (datetime.now() + timedelta(seconds=remaining_time)).strftime("%H:%M")

        return {
            'remaining_seconds': remaining_time,
            'remaining_str': remaining_str,
            'completion_time': completion_time
        }

    def cancel(self):
        """字幕検出処理をキャンセル"""
        self._is_cancelled = True
        self.logger.info("字幕検出処理のキャンセルが要求されました")

    def _check_cancelled(self):
        """キャンセル状態をチェックし、必要に応じて例外を発生"""
        if self._is_cancelled:
            raise InterruptedError("字幕検出処理がキャンセルされました")
    
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
            self.start_time = time.time()

            # Step 1: 動画サンプリングの準備
            self._check_cancelled()
            self._emit_progress(5, "動画を読み込んでいます...")
            self._initialize_sampler(video_path)

            # 動画情報を表示
            video_info = self.sampler.video_info
            total_frames = video_info.get('frame_count', 0)
            duration = video_info.get('duration_sec', 0)
            fps = video_info.get('fps', 0)

            self._emit_progress(10, f"動画読み込み完了 ({total_frames}フレーム, {duration:.1f}秒, {fps:.1f}FPS)")

            # Step 2: ROI検出
            self._check_cancelled()
            self._emit_progress(15, "字幕領域を検出しています...")
            roi_region = self._detect_roi()
            self._emit_progress(25, "字幕領域検出完了")

            # Step 3: フレームサンプリング
            self._check_cancelled()
            self._emit_progress(30, "フレームをサンプリングしています...")
            frames = self._sample_frames(roi_region)

            if not frames:
                self._emit_progress(100, "字幕が検出されませんでした")
                return []

            self._emit_progress(35, f"フレームサンプリング完了 ({len(frames)}フレーム)")

            # Step 4: OCR実行（最も時間がかかる処理）
            self._check_cancelled()
            self._emit_progress(40, f"OCRを実行しています... ({len(frames)}フレーム)")
            frame_results = self._perform_ocr(frames)

            # Step 5: グルーピング・統合
            self._check_cancelled()
            self._emit_progress(85, "字幕をグルーピングしています...")
            subtitle_items = self._group_subtitles(frame_results)
            self._emit_progress(95, "グルーピング完了")
            
            # Step 6: 完了
            elapsed_time = time.time() - self.start_time
            self._emit_progress(100, f"検出完了: {len(subtitle_items)}件 ({elapsed_time:.1f}秒)")

            self.logger.info(f"字幕検出完了: {len(subtitle_items)}件の字幕を検出")
            return subtitle_items
            
        except InterruptedError as e:
            # キャンセル例外は特別扱い
            self.logger.info(f"字幕検出がキャンセルされました: {e}")
            self._emit_progress(100, "処理がキャンセルされました")
            raise

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
        frame_count = 0
        last_progress_time = time.time()

        # 動画の総フレーム数を取得
        video_info = self.sampler.video_info
        total_video_frames = video_info.get('frame_count', 0)

        try:
            self.logger.info(f"フレームサンプリング開始: ROI={roi_region.rect}")
            self.logger.info(f"動画総フレーム数: {total_video_frames}")

            if isinstance(self.sampler, BottomROISampler):
                # 下段専用サンプラーの場合
                self.logger.debug("下段専用サンプラーを使用")
                for frame in self.sampler.sample_bottom_frames():
                    self._check_cancelled()
                    frames.append(frame)
                    frame_count += 1

                    # 進捗を定期的に報告（1秒間隔）
                    current_time = time.time()
                    if current_time - last_progress_time >= 1.0:
                        if total_video_frames > 0:
                            processed_ratio = (frame.frame_number / total_video_frames) * 100
                            self._emit_progress(32, f"フレームサンプリング中... ({frame_count}フレーム, {processed_ratio:.1f}%処理済み)")
                        else:
                            self._emit_progress(32, f"フレームサンプリング中... ({frame_count}フレーム)")
                        last_progress_time = current_time

            else:
                # 汎用サンプラーの場合
                self.logger.debug(f"汎用サンプラーを使用: ROI={roi_region.rect}")
                for frame in self.sampler.extract_roi_frames(roi_region.rect):
                    self._check_cancelled()
                    frames.append(frame)
                    frame_count += 1

                    # 進捗を定期的に報告（1秒間隔）
                    current_time = time.time()
                    if current_time - last_progress_time >= 1.0:
                        if total_video_frames > 0:
                            processed_ratio = (frame.frame_number / total_video_frames) * 100
                            self._emit_progress(32, f"フレームサンプリング中... ({frame_count}フレーム, {processed_ratio:.1f}%処理済み)")
                        else:
                            self._emit_progress(32, f"フレームサンプリング中... ({frame_count}フレーム)")
                        last_progress_time = current_time

            self.logger.info(f"フレームサンプリング完了: {len(frames)}フレーム（動画全体の{len(frames)}/{total_video_frames}フレーム処理）")
            return frames

        except Exception as e:
            self.logger.error(f"フレームサンプリングエラー: {e}")
            self.logger.error(f"サンプラー種別: {type(self.sampler)}")
            self.logger.error(f"ROI情報: {roi_region}")
            self.logger.error(f"取得済みフレーム数: {len(frames)}")
            self.logger.error(f"動画総フレーム数: {total_video_frames}")
            raise
    
    def _perform_ocr(self, frames: List[VideoFrame]) -> List[FrameOCRResult]:
        """OCR実行"""
        frame_results = []
        total_frames = len(frames)

        self.logger.info(f"OCR処理開始: {total_frames}フレーム")

        # 並列処理用の設定
        max_workers = min(4, total_frames)  # 最大4並列
        self.logger.debug(f"OCR並列実行: {max_workers}ワーカー")

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # OCRタスクを並列実行
            future_to_frame = {
                executor.submit(self._ocr_single_frame, frame): frame
                for frame in frames
            }

            completed_count = 0
            successful_count = 0
            last_progress_time = time.time()

            for future in as_completed(future_to_frame):
                # キャンセルチェック
                self._check_cancelled()

                frame = future_to_frame[future]

                try:
                    ocr_results = future.result()

                    if ocr_results:  # OCR結果がある場合のみ追加
                        frame_results.append(FrameOCRResult(
                            frame=frame,
                            ocr_results=ocr_results
                        ))
                        successful_count += 1

                except Exception as e:
                    self.logger.warning(f"フレーム {frame.frame_number} のOCR処理に失敗: {e}")

                completed_count += 1

                # キャンセルチェック
                self._check_cancelled()

                # プログレス更新（詳細な情報付き）
                progress = 40 + int((completed_count / total_frames) * 45)

                # 経過時間と推定残り時間を計算
                elapsed = time.time() - start_time
                if completed_count > 0:
                    avg_time_per_frame = elapsed / completed_count
                    remaining_frames = total_frames - completed_count
                    estimated_remaining = avg_time_per_frame * remaining_frames

                    if estimated_remaining > 60:
                        eta_str = f"{int(estimated_remaining // 60)}分{int(estimated_remaining % 60)}秒"
                    else:
                        eta_str = f"{int(estimated_remaining)}秒"

                    message = f"OCR処理中... ({completed_count}/{total_frames}) テキスト検出:{successful_count}件 残り約{eta_str}"
                else:
                    message = f"OCR処理中... ({completed_count}/{total_frames}) テキスト検出:{successful_count}件"

                # 進捗を0.5秒間隔で更新
                current_time = time.time()
                if current_time - last_progress_time >= 0.5 or completed_count == total_frames:
                    self._emit_progress(progress, message)
                    last_progress_time = current_time
        
        # 時間順にソート
        frame_results.sort(key=lambda x: x.frame.timestamp_ms)

        total_elapsed = time.time() - start_time
        self.logger.info(f"OCR処理完了: {len(frame_results)}フレームでテキストを検出 "
                        f"({successful_count}/{total_frames}) {total_elapsed:.1f}秒")
        return frame_results
    
    def _ocr_single_frame(self, frame: VideoFrame) -> List[OCRResult]:
        """単一フレームのOCR処理"""
        try:
            return self.ocr_engine.extract_text(frame.image)
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
        
        info['ocr_info'] = "SimplePaddleOCREngine"
        
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