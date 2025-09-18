"""
字幕抽出ワーカー（別スレッド処理）
強化されたエラーハンドリングとユーザーフィードバック付き
"""

from PySide6.QtCore import QThread, Signal, QObject, QTimer
from typing import List, Optional, Dict, Any
import logging
import time
from pathlib import Path

from app.core.models import SubtitleItem, ProjectSettings
from app.core.extractor.detector import SubtitleDetector
from app.core.error_handler import (
    ErrorHandler, ErrorInfo, ErrorCategory, ErrorSeverity,
    create_ocr_error, create_file_operation_error
)


class ExtractionWorker(QThread):
    """字幕抽出ワーカースレッド - 強化されたエラーハンドリング付き"""

    # シグナル定義
    progress_updated = Signal(int, str)  # プログレス更新 (percentage, message)
    subtitles_extracted = Signal(list)   # 抽出完了 (subtitle_items)
    error_occurred = Signal(str)         # 基本エラー発生 (error_message) - 互換性のため維持
    detailed_error_occurred = Signal(ErrorInfo, dict)  # 詳細エラー情報 (error_info, context)
    cancelled = Signal()                 # キャンセル完了
    recovery_suggested = Signal(str, dict)  # 復旧提案 (recovery_option, context)

    # 新しいシグナル
    operation_retrying = Signal(int, str)  # 再試行中 (attempt, reason)
    partial_success = Signal(list, list)   # 部分成功 (extracted_subtitles, failed_frames)
    
    def __init__(self, video_path: str, settings: ProjectSettings, parent_widget=None):
        super().__init__()
        self.video_path = video_path
        self.settings = settings
        self.detector: Optional[SubtitleDetector] = None
        self._is_cancelled = False

        # エラーハンドリング
        self.error_handler = ErrorHandler(parent_widget)
        self.logger = logging.getLogger(__name__)

        # 統計と復旧設定
        self.retry_count = 0
        self.max_retries = 3
        self.failed_frames: List[Dict[str, Any]] = []
        self.partial_results: List[SubtitleItem] = []

        # タイムアウト設定
        self.operation_timeout = 300  # 5分
        self.start_time: Optional[float] = None

        # パフォーマンス監視
        self.performance_stats = {
            "frames_processed": 0,
            "ocr_failures": 0,
            "memory_errors": 0,
            "timeout_errors": 0
        }
    
    def run(self):
        """ワーカーメイン処理 - 強化されたエラーハンドリング付き"""
        self.start_time = time.time()

        try:
            # 動画ファイルの事前検証
            if not self._validate_video_file():
                return

            # 検出器の初期化（リトライ機能付き）
            if not self._initialize_detector_with_retry():
                return

            # プログレスコールバックを設定
            self.detector.set_progress_callback(self._on_progress_with_monitoring)

            # 字幕抽出実行（エラーハンドリング強化版）
            subtitle_items = self._execute_extraction_with_recovery()

            if self._is_cancelled:
                self.cancelled.emit()
                return

            # 結果の検証と通知
            self._handle_extraction_results(subtitle_items)

        except Exception as e:
            self._handle_unexpected_error(e)

        finally:
            self._cleanup_and_log_stats()
    
    def _on_progress_with_monitoring(self, percentage: int, message: str):
        """プログレスコールバック - 監視機能付き"""
        if self._is_cancelled:
            return

        # タイムアウトチェック
        if self.start_time and time.time() - self.start_time > self.operation_timeout:
            self._handle_timeout_error()
            return

        # プログレス更新
        self.progress_updated.emit(percentage, message)

        # パフォーマンス統計更新
        if "フレーム" in message and "処理中" in message:
            self.performance_stats["frames_processed"] += 1

    # === 新しいプライベートメソッド ===

    def _validate_video_file(self) -> bool:
        """動画ファイルの事前検証"""
        try:
            video_path = Path(self.video_path)

            if not video_path.exists():
                error_info = create_file_operation_error(
                    self.video_path, "動画ファイルの読み込み",
                    FileNotFoundError(f"ファイルが見つかりません: {self.video_path}")
                )
                self.detailed_error_occurred.emit(error_info, {"validation_stage": "file_existence"})
                self.error_occurred.emit(error_info.message)  # 互換性のため
                return False

            if not video_path.is_file():
                error_info = ErrorInfo(
                    message="指定されたパスはファイルではありません",
                    category=ErrorCategory.VALIDATION,
                    severity=ErrorSeverity.ERROR,
                    technical_details=f"Path is not a file: {self.video_path}"
                )
                self.detailed_error_occurred.emit(error_info, {"validation_stage": "file_type"})
                self.error_occurred.emit(error_info.message)
                return False

            # ファイルサイズチェック
            file_size = video_path.stat().st_size
            if file_size == 0:
                error_info = ErrorInfo(
                    message="動画ファイルが空です",
                    category=ErrorCategory.VALIDATION,
                    severity=ErrorSeverity.ERROR,
                    suggestions=["別の動画ファイルを選択してください"]
                )
                self.detailed_error_occurred.emit(error_info, {"validation_stage": "file_size"})
                self.error_occurred.emit(error_info.message)
                return False

            self.logger.info(f"動画ファイル検証完了: {video_path.name} ({file_size:,} bytes)")
            return True

        except Exception as e:
            error_info = create_file_operation_error(self.video_path, "動画ファイル検証", e)
            self.detailed_error_occurred.emit(error_info, {"validation_stage": "exception"})
            self.error_occurred.emit(error_info.message)
            return False

    def _initialize_detector_with_retry(self) -> bool:
        """検出器の初期化（リトライ機能付き）"""
        for attempt in range(1, self.max_retries + 1):
            if self._is_cancelled:
                return False

            try:
                self.progress_updated.emit(5 * attempt, f"OCRエンジン初期化中... ({attempt}/{self.max_retries})")
                self.detector = SubtitleDetector(self.settings)
                self.logger.info(f"検出器初期化成功 (試行 {attempt}/{self.max_retries})")
                return True

            except Exception as e:
                self.logger.warning(f"検出器初期化失敗 (試行 {attempt}/{self.max_retries}): {e}")

                if attempt < self.max_retries:
                    self.operation_retrying.emit(attempt, "OCRエンジン初期化")
                    time.sleep(2 ** (attempt - 1))  # 指数バックオフ
                else:
                    # 最終試行でも失敗
                    error_info = ErrorInfo(
                        message="OCRエンジンの初期化に失敗しました",
                        category=ErrorCategory.OCR_PROCESSING,
                        severity=ErrorSeverity.CRITICAL,
                        technical_details=f"{type(e).__name__}: {str(e)}",
                        suggestions=[
                            "アプリケーションを再起動してください",
                            "システムのメモリが十分にあることを確認してください",
                            "他のアプリケーションを終了してリソースを解放してください"
                        ]
                    )
                    self.detailed_error_occurred.emit(error_info, {"initialization_attempts": attempt})
                    self.error_occurred.emit(error_info.message)
                    return False

        return False

    def cancel(self):
        """
        抽出処理をキャンセル - 安全な終了処理付き

        注意: このメソッドはメインスレッドからのみ呼び出すこと
        ワーカースレッド内からの呼び出しはself.wait()でデッドロックする
        """
        self.logger.info("字幕抽出のキャンセルが要求されました")
        self._is_cancelled = True

        if self.detector:
            try:
                # 検出器にキャンセル要請
                self.detector.cancel()
            except Exception as e:
                self.logger.warning(f"検出器キャンセル中にエラー: {e}")

        # スレッドが実行中の場合は段階的終了
        if self.isRunning():
            # 通常終了を待つ
            self.wait(3000)  # 3秒待機

            if self.isRunning():
                self.logger.warning("通常終了に失敗、強制終了を試行")
                # 強制終了
                self.terminate()
                self.wait(1000)  # 1秒待機

                if self.isRunning():
                    self.logger.error("強制終了にも失敗")

        # 統計ログ
        self._log_cancellation_stats()
    
    def cleanup(self):
        """リソースクリーンアップ - 強化版"""
        try:
            if self.detector:
                self.detector._cleanup()
                self.detector = None

            # エラーハンドラーのクリーンアップ
            if hasattr(self, 'error_handler'):
                del self.error_handler

        except Exception as e:
            self.logger.error(f"クリーンアップ中にエラー: {e}")

    def _execute_extraction_with_recovery(self) -> List[SubtitleItem]:
        """字幕抽出実行（復旧機能付き）"""
        subtitle_items = []

        try:
            self.progress_updated.emit(10, "字幕抽出を開始しています...")
            subtitle_items = self.detector.detect_subtitles(self.video_path)

        except MemoryError as e:
            self.performance_stats["memory_errors"] += 1
            error_info = ErrorInfo(
                message="メモリ不足のため抽出処理に失敗しました",
                category=ErrorCategory.SYSTEM,
                severity=ErrorSeverity.CRITICAL,
                technical_details=str(e),
                suggestions=[
                    "他のアプリケーションを終了してメモリを解放してください",
                    "より小さい解像度で処理を実行してください",
                    "システムを再起動してください"
                ],
                recovery_options={
                    "低解像度で再試行": lambda: self._retry_with_lower_resolution(),
                    "部分抽出を試行": lambda: self._try_partial_extraction()
                }
            )

            if self._attempt_recovery_extraction(error_info):
                return self.partial_results
            else:
                raise

        except TimeoutError as e:
            self.performance_stats["timeout_errors"] += 1
            error_info = ErrorInfo(
                message="処理がタイムアウトしました",
                category=ErrorCategory.SYSTEM,
                severity=ErrorSeverity.ERROR,
                technical_details=str(e),
                suggestions=[
                    "より短い動画で試してください",
                    "設定でフレームサンプリング率を下げてください"
                ],
                recovery_options={
                    "部分抽出を試行": lambda: self._try_partial_extraction()
                }
            )

            if self._attempt_recovery_extraction(error_info):
                return self.partial_results
            else:
                raise

        except InterruptedError:
            # キャンセル関連例外は即座に終了（復旧処理をスキップ）
            self.logger.info("字幕抽出がキャンセルされました")
            self.cancelled.emit()
            return []

        except Exception as e:
            # その他の例外は詳細な分析を行う
            return self._handle_extraction_exception(e)

        return subtitle_items

    def _handle_extraction_exception(self, exception: Exception) -> List[SubtitleItem]:
        """抽出処理例外の詳細ハンドリング"""

        # キャンセル関連例外の優先処理
        if isinstance(exception, InterruptedError):
            # ユーザーキャンセルによるInterruptedError - 復旧処理をスキップ
            self.logger.info("字幕抽出がキャンセルされました (InterruptedError)")
            self.cancelled.emit()
            return []

        # OCR固有エラーの判定
        if "paddle" in str(exception).lower() or "ocr" in str(exception).lower():
            self.performance_stats["ocr_failures"] += 1
            error_info = create_ocr_error(original_error=exception)

        elif isinstance(exception, (OSError, IOError)):
            error_info = create_file_operation_error(self.video_path, "動画処理", exception)

        else:
            # 汎用エラー
            error_info = ErrorInfo(
                message="字幕抽出中に予期しないエラーが発生しました",
                category=ErrorCategory.SYSTEM,
                severity=ErrorSeverity.ERROR,
                technical_details=f"{type(exception).__name__}: {str(exception)}",
                suggestions=[
                    "アプリケーションを再起動してください",
                    "別の動画ファイルで試してください",
                    "設定を初期化してください"
                ]
            )

        # 復旧試行
        if self._attempt_recovery_extraction(error_info):
            return self.partial_results
        else:
            raise exception

    def _attempt_recovery_extraction(self, error_info: ErrorInfo) -> bool:
        """復旧抽出の試行"""
        context = {
            "recovery_attempt": True,
            "original_error": error_info.technical_details,
            "performance_stats": self.performance_stats.copy()
        }

        self.detailed_error_occurred.emit(error_info, context)

        # 部分抽出の試行
        if self._try_partial_extraction():
            return True

        return False

    def _try_partial_extraction(self) -> bool:
        """部分的な抽出の試行"""
        try:
            self.logger.info("部分抽出を試行中...")
            self.progress_updated.emit(50, "部分抽出を試行しています...")

            # より保守的な設定で再試行
            from app.core.models import ProjectSettings

            # 設定を一時的に変更（より保守的に）
            conservative_settings = ProjectSettings(
                fps_sample=min(1.0, self.settings.fps_sample / 2),  # FPS半減
                ocr_confidence=max(0.8, self.settings.ocr_confidence),  # 信頼度向上
                max_chars=self.settings.max_chars,
                max_lines=min(1, self.settings.max_lines)  # 1行のみ
            )

            # 新しい検出器で部分抽出試行
            partial_detector = SubtitleDetector(conservative_settings)
            partial_detector.set_progress_callback(self._on_progress_with_monitoring)

            # 短時間での抽出試行
            self.partial_results = partial_detector.detect_subtitles(self.video_path)

            if self.partial_results:
                self.logger.info(f"部分抽出成功: {len(self.partial_results)}件の字幕を取得")
                return True

        except Exception as e:
            self.logger.error(f"部分抽出も失敗: {e}")

        return False

    def _handle_extraction_results(self, subtitle_items: List[SubtitleItem]):
        """抽出結果の処理"""
        if not subtitle_items:
            # 結果が空の場合
            error_info = ErrorInfo(
                message="字幕が検出されませんでした",
                category=ErrorCategory.OCR_PROCESSING,
                severity=ErrorSeverity.WARNING,
                suggestions=[
                    "動画に字幕が含まれていることを確認してください",
                    "OCR設定（信頼度、領域指定など）を調整してみてください",
                    "動画の画質や字幕の鮮明度を確認してください"
                ]
            )
            self.detailed_error_occurred.emit(error_info, {"result_count": 0})
            self.error_occurred.emit(error_info.message)
            return

        # 正常結果の処理
        self.logger.info(f"字幕抽出完了: {len(subtitle_items)}件")

        # パフォーマンス統計をログ
        self._log_performance_stats(len(subtitle_items))

        # 部分成功の場合
        if self.failed_frames:
            self.partial_success.emit(subtitle_items, self.failed_frames)
        else:
            self.subtitles_extracted.emit(subtitle_items)

    def _handle_unexpected_error(self, exception: Exception):
        """予期しないエラーの処理"""
        if self._is_cancelled:
            self.cancelled.emit()
            return

        self.logger.error(f"予期しないエラー: {exception}", exc_info=True)

        error_info = ErrorInfo(
            message="予期しないエラーが発生しました",
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.CRITICAL,
            technical_details=f"{type(exception).__name__}: {str(exception)}",
            suggestions=[
                "アプリケーションを再起動してください",
                "システムの状態を確認してください",
                "問題が継続する場合はサポートにお問い合わせください"
            ]
        )

        context = {
            "unexpected_error": True,
            "stack_trace": str(exception.__traceback__)
        }

        self.detailed_error_occurred.emit(error_info, context)
        self.error_occurred.emit(error_info.message)

    def _handle_timeout_error(self):
        """タイムアウトエラーの処理"""
        error_info = ErrorInfo(
            message=f"処理が制限時間（{self.operation_timeout}秒）を超過しました",
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.ERROR,
            suggestions=[
                "より短い動画で試してください",
                "フレームサンプリング設定を調整してください"
            ]
        )

        context = {
            "timeout_seconds": self.operation_timeout,
            "elapsed_time": time.time() - self.start_time if self.start_time else 0
        }

        self.detailed_error_occurred.emit(error_info, context)
        self.error_occurred.emit(error_info.message)

        # タイムアウト時はメインスレッドにキャンセル要求をシグナル送信
        # ワーカースレッド内でself.wait()を呼ぶとデッドロックするため
        self._request_cancel_from_main_thread()

    def _request_cancel_from_main_thread(self):
        """メインスレッドにキャンセル要求をシグナル送信（デッドロック回避）"""
        # シグナルを使ってメインスレッドに安全にキャンセル要求を送る
        # ワーカースレッド内でself.wait()を呼ばないことでデッドロックを防ぐ
        self._is_cancelled = True

        # 検出器にはすぐにキャンセル通知
        if self.detector:
            try:
                self.detector.cancel()
            except Exception as e:
                self.logger.warning(f"検出器キャンセル中にエラー: {e}")

        # メインスレッドにキャンセル要求を送信
        # 実際のスレッド終了処理はメインスレッド側で行う
        self.recovery_suggested.emit("cancel_from_timeout", {
            "reason": "timeout_deadlock_prevention"
        })

    def _cleanup_and_log_stats(self):
        """クリーンアップと統計ログ"""
        try:
            if self.detector:
                self.detector._cleanup()

        except Exception as e:
            self.logger.error(f"クリーンアップエラー: {e}")

        finally:
            # 実行時間計算
            if self.start_time:
                elapsed_time = time.time() - self.start_time
                self.performance_stats["total_execution_time"] = elapsed_time

            # 統計ログ
            self.logger.info(f"抽出処理統計: {self.performance_stats}")

    def _log_performance_stats(self, result_count: int):
        """パフォーマンス統計のログ"""
        stats = self.performance_stats.copy()
        stats["extracted_subtitles"] = result_count

        if self.start_time:
            stats["total_time"] = time.time() - self.start_time
            if stats["frames_processed"] > 0:
                stats["frames_per_second"] = stats["frames_processed"] / stats["total_time"]

        self.logger.info(f"抽出完了統計: {stats}")

    def _log_cancellation_stats(self):
        """キャンセル統計のログ"""
        if self.start_time:
            elapsed = time.time() - self.start_time
            self.logger.info(
                f"抽出キャンセル - 実行時間: {elapsed:.1f}秒, "
                f"処理フレーム: {self.performance_stats['frames_processed']}"
            )

    def _retry_with_lower_resolution(self):
        """低解像度での再試行"""
        # この関数は recovery_options から呼び出される
        # 実装は main_window側で行う
        self.recovery_suggested.emit("lower_resolution_retry", {"original_path": self.video_path})


# 下位互換性のためのエイリアス
ExtractionWorkerLegacy = ExtractionWorker  # 必要に応じて旧バージョンとして利用可能