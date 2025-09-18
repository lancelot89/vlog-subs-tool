"""
エラーハンドリングとユーザーフィードバック用のユーティリティ
"""

import logging
import traceback
from typing import Optional, Dict, Any, Callable, Union
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import QWidget, QMessageBox, QProgressDialog
from PySide6.QtCore import QTimer, Signal, QObject
from PySide6.QtGui import QIcon


class ErrorSeverity:
    """エラー重要度の定義"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory:
    """エラーカテゴリの定義"""
    FILE_OPERATION = "file_operation"
    OCR_PROCESSING = "ocr_processing"
    VIDEO_PROCESSING = "video_processing"
    NETWORK = "network"
    VALIDATION = "validation"
    SYSTEM = "system"
    USER_INPUT = "user_input"


class ErrorInfo:
    """エラー情報を格納するクラス"""

    def __init__(self,
                 message: str,
                 category: str = ErrorCategory.SYSTEM,
                 severity: str = ErrorSeverity.ERROR,
                 technical_details: Optional[str] = None,
                 suggestions: Optional[list] = None,
                 recovery_options: Optional[Dict[str, Callable]] = None):
        self.message = message
        self.category = category
        self.severity = severity
        self.technical_details = technical_details
        self.suggestions = suggestions or []
        self.recovery_options = recovery_options or {}
        self.timestamp = datetime.now()


class ErrorHandler(QObject):
    """統合エラーハンドラー"""

    # シグナル定義
    error_logged = Signal(ErrorInfo)
    recovery_suggested = Signal(str, dict)  # recovery_option_id, context

    def __init__(self, parent_widget: Optional[QWidget] = None):
        super().__init__()
        self.parent_widget = parent_widget
        self.logger = logging.getLogger(__name__)

        # エラー統計
        self.error_count = 0
        self.error_history: list = []

        # 自動復旧オプション
        self.auto_recovery_enabled = True
        self.max_retry_attempts = 3

    def handle_error(self,
                    error: Union[Exception, ErrorInfo],
                    context: Optional[Dict[str, Any]] = None,
                    show_dialog: bool = True,
                    allow_retry: bool = False) -> bool:
        """
        エラーを処理し、適切なフィードバックを提供

        Returns:
            bool: エラーが解決されたかどうか（再試行で成功した場合など）
        """
        context = context or {}

        # ErrorInfoオブジェクトに変換
        if isinstance(error, Exception):
            error_info = self._exception_to_error_info(error, context)
        else:
            error_info = error

        # ログに記録
        self._log_error(error_info, context)

        # UI表示
        if show_dialog and self.parent_widget:
            return self._show_error_dialog(error_info, context, allow_retry)

        return False

    def _exception_to_error_info(self, exception: Exception, context: Dict[str, Any]) -> ErrorInfo:
        """例外をErrorInfoオブジェクトに変換"""

        # 例外タイプに基づくカテゴリ判定
        category = ErrorCategory.SYSTEM
        suggestions = []

        if isinstance(exception, (FileNotFoundError, PermissionError, OSError)):
            category = ErrorCategory.FILE_OPERATION
            suggestions = [
                "ファイルが存在することを確認してください",
                "ファイルの権限を確認してください",
                "ディスク容量が十分にあることを確認してください"
            ]
        elif isinstance(exception, (MemoryError, RuntimeError)):
            category = ErrorCategory.SYSTEM
            suggestions = [
                "他のアプリケーションを終了してメモリを解放してください",
                "より小さいファイルで試してください",
                "システムを再起動してください"
            ]
        elif isinstance(exception, (ValueError, TypeError)):
            category = ErrorCategory.VALIDATION
            suggestions = [
                "入力データの形式を確認してください",
                "設定項目を見直してください"
            ]
        elif isinstance(exception, TimeoutError):
            category = ErrorCategory.NETWORK if "network" in str(exception).lower() else ErrorCategory.SYSTEM
            suggestions = [
                "インターネット接続を確認してください",
                "しばらく時間をおいて再試行してください"
            ]

        # 重要度判定
        severity = ErrorSeverity.ERROR
        if isinstance(exception, (MemoryError, PermissionError)):
            severity = ErrorSeverity.CRITICAL
        elif isinstance(exception, (FileNotFoundError, ValueError)):
            severity = ErrorSeverity.WARNING

        return ErrorInfo(
            message=self._get_user_friendly_message(exception),
            category=category,
            severity=severity,
            technical_details=f"{type(exception).__name__}: {str(exception)}",
            suggestions=suggestions
        )

    def _get_user_friendly_message(self, exception: Exception) -> str:
        """例外からユーザーフレンドリーなメッセージを生成"""

        error_messages = {
            FileNotFoundError: "指定されたファイルが見つかりません",
            PermissionError: "ファイルまたはフォルダへのアクセス権限がありません",
            MemoryError: "メモリが不足しています",
            TimeoutError: "処理がタイムアウトしました",
            ValueError: "入力データの形式が正しくありません",
            RuntimeError: "システムエラーが発生しました",
            OSError: "システムリソースへのアクセスに失敗しました"
        }

        exception_type = type(exception)
        base_message = error_messages.get(exception_type, "予期しないエラーが発生しました")

        # 特定のエラーパターンのカスタマイズ
        error_str = str(exception).lower()
        if "no space left" in error_str:
            return "ディスク容量が不足しています"
        elif "permission denied" in error_str:
            return "ファイルまたはフォルダへのアクセスが拒否されました"
        elif "connection" in error_str and "refused" in error_str:
            return "サーバーへの接続に失敗しました"

        return base_message

    def _log_error(self, error_info: ErrorInfo, context: Dict[str, Any]):
        """エラーをログに記録"""

        # 統計更新
        self.error_count += 1
        self.error_history.append(error_info)

        # ログレベル決定
        log_level = {
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }.get(error_info.severity, logging.ERROR)

        # ログメッセージ構築
        log_message = f"[{error_info.category}] {error_info.message}"
        if context:
            log_message += f" (コンテキスト: {context})"
        if error_info.technical_details:
            log_message += f" - 詳細: {error_info.technical_details}"

        self.logger.log(log_level, log_message)

        # シグナル送信
        self.error_logged.emit(error_info)

    def _show_error_dialog(self,
                          error_info: ErrorInfo,
                          context: Dict[str, Any],
                          allow_retry: bool) -> bool:
        """エラーダイアログを表示"""

        # アイコン決定
        icon_map = {
            ErrorSeverity.INFO: QMessageBox.Information,
            ErrorSeverity.WARNING: QMessageBox.Warning,
            ErrorSeverity.ERROR: QMessageBox.Critical,
            ErrorSeverity.CRITICAL: QMessageBox.Critical
        }

        # メッセージボックス作成
        msg_box = QMessageBox(self.parent_widget)
        msg_box.setIcon(icon_map.get(error_info.severity, QMessageBox.Critical))
        msg_box.setWindowTitle("エラーが発生しました")
        msg_box.setText(error_info.message)

        # 詳細テキスト構築
        details = []
        if error_info.technical_details:
            details.append(f"技術的詳細: {error_info.technical_details}")

        if error_info.suggestions:
            details.append("\n解決策:")
            for i, suggestion in enumerate(error_info.suggestions, 1):
                details.append(f"{i}. {suggestion}")

        if context:
            details.append(f"\nコンテキスト: {context}")

        if details:
            msg_box.setDetailedText("\n".join(details))

        # ボタン設定
        if allow_retry:
            msg_box.addButton("再試行", QMessageBox.AcceptRole)
            msg_box.addButton("キャンセル", QMessageBox.RejectRole)
        else:
            msg_box.addButton("OK", QMessageBox.AcceptRole)

        # 復旧オプションがある場合
        recovery_buttons = {}
        for option_id, option_func in error_info.recovery_options.items():
            button = msg_box.addButton(option_id, QMessageBox.ActionRole)
            recovery_buttons[button] = (option_id, option_func)

        # ダイアログ表示
        result = msg_box.exec()
        clicked_button = msg_box.clickedButton()

        # 復旧オプションの処理
        if clicked_button in recovery_buttons:
            option_id, option_func = recovery_buttons[clicked_button]
            try:
                option_func()
                self.recovery_suggested.emit(option_id, context)
                return True
            except Exception as e:
                self.handle_error(e, {"recovery_attempt": option_id}, show_dialog=False)
                return False

        # 再試行の場合
        return allow_retry and msg_box.buttonRole(clicked_button) == QMessageBox.AcceptRole

    def create_progress_error_handler(self,
                                    operation_name: str,
                                    total_steps: int = 100) -> 'ProgressErrorHandler':
        """プログレス付きエラーハンドラーを作成"""
        return ProgressErrorHandler(self, operation_name, total_steps, self.parent_widget)

    def get_error_summary(self) -> Dict[str, Any]:
        """エラー統計のサマリーを取得"""
        category_counts = {}
        severity_counts = {}

        for error in self.error_history[-50:]:  # 最新50件
            category_counts[error.category] = category_counts.get(error.category, 0) + 1
            severity_counts[error.severity] = severity_counts.get(error.severity, 0) + 1

        return {
            "total_errors": self.error_count,
            "recent_errors": len(self.error_history[-10:]),
            "category_breakdown": category_counts,
            "severity_breakdown": severity_counts,
            "last_error": self.error_history[-1] if self.error_history else None
        }


class ProgressErrorHandler(QObject):
    """プログレス表示付きエラーハンドラー"""

    # シグナル
    operation_completed = Signal()
    operation_cancelled = Signal()
    operation_failed = Signal(ErrorInfo)

    def __init__(self,
                 error_handler: ErrorHandler,
                 operation_name: str,
                 total_steps: int,
                 parent_widget: Optional[QWidget] = None):
        super().__init__()

        self.error_handler = error_handler
        self.operation_name = operation_name
        self.total_steps = total_steps
        self.parent_widget = parent_widget

        self.current_step = 0
        self.is_cancelled = False
        self.progress_dialog: Optional[QProgressDialog] = None

        # 自動復旧設定
        self.retry_count = 0
        self.max_retries = 3

    def start_operation(self, show_progress: bool = True) -> bool:
        """操作を開始"""

        if show_progress and self.parent_widget:
            self.progress_dialog = QProgressDialog(
                f"{self.operation_name}を実行中...",
                "キャンセル",
                0,
                self.total_steps,
                self.parent_widget
            )
            self.progress_dialog.setWindowModality(2)  # Qt.ApplicationModal
            self.progress_dialog.canceled.connect(self.cancel_operation)
            self.progress_dialog.show()

        return True

    def update_progress(self, step: int, message: str = ""):
        """プログレス更新"""
        self.current_step = step

        if self.progress_dialog:
            self.progress_dialog.setValue(step)
            if message:
                self.progress_dialog.setLabelText(f"{self.operation_name}: {message}")

        # キャンセルチェック
        if self.progress_dialog and self.progress_dialog.wasCanceled():
            self.is_cancelled = True
            return False

        return not self.is_cancelled

    def handle_operation_error(self,
                              error: Union[Exception, ErrorInfo],
                              context: Optional[Dict[str, Any]] = None,
                              allow_retry: bool = True) -> bool:
        """操作中のエラーを処理"""

        context = context or {}
        context.update({
            "operation": self.operation_name,
            "step": self.current_step,
            "total_steps": self.total_steps,
            "retry_count": self.retry_count
        })

        # プログレスダイアログを一時的に隠す
        if self.progress_dialog:
            self.progress_dialog.hide()

        # 自動復旧の試行
        if allow_retry and self.retry_count < self.max_retries:
            self.retry_count += 1

            # 再試行確認ダイアログ
            if isinstance(error, Exception):
                error_info = self.error_handler._exception_to_error_info(error, context)
            else:
                error_info = error

            retry_context = context.copy()
            retry_context["auto_retry_attempt"] = True

            should_retry = self.error_handler.handle_error(
                error_info, retry_context, show_dialog=True, allow_retry=True
            )

            if should_retry:
                # プログレスダイアログを再表示
                if self.progress_dialog:
                    self.progress_dialog.show()
                return True

        # エラー処理
        if isinstance(error, Exception):
            error_info = self.error_handler._exception_to_error_info(error, context)
        else:
            error_info = error

        self.error_handler.handle_error(error_info, context, show_dialog=True, allow_retry=False)

        # 操作失敗として完了
        self.complete_operation(success=False, error_info=error_info)
        return False

    def complete_operation(self, success: bool = True, error_info: Optional[ErrorInfo] = None):
        """操作完了"""

        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        if success:
            self.operation_completed.emit()
        elif error_info:
            self.operation_failed.emit(error_info)

    def cancel_operation(self):
        """操作キャンセル"""
        self.is_cancelled = True

        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        self.operation_cancelled.emit()


# 便利な関数群

def create_file_operation_error(file_path: Union[str, Path],
                               operation: str,
                               original_error: Exception) -> ErrorInfo:
    """ファイル操作エラー用のErrorInfoを作成"""

    suggestions = [
        "ファイルが存在し、アクセス可能であることを確認してください",
        "他のアプリケーションでファイルが開かれていないか確認してください",
        "ディスク容量が十分にあることを確認してください"
    ]

    recovery_options = {}

    if isinstance(original_error, PermissionError):
        suggestions.append("管理者権限でアプリケーションを実行してみてください")

    elif isinstance(original_error, FileNotFoundError):
        recovery_options["別のファイルを選択"] = lambda: None  # コールバックは呼び出し元で設定

    return ErrorInfo(
        message=f"{operation}に失敗しました: {Path(file_path).name}",
        category=ErrorCategory.FILE_OPERATION,
        severity=ErrorSeverity.ERROR,
        technical_details=f"{type(original_error).__name__}: {str(original_error)}",
        suggestions=suggestions,
        recovery_options=recovery_options
    )


def create_ocr_error(frame_number: Optional[int] = None,
                    original_error: Optional[Exception] = None) -> ErrorInfo:
    """OCR処理エラー用のErrorInfoを作成"""

    message = "OCR処理でエラーが発生しました"
    if frame_number is not None:
        message += f" (フレーム {frame_number})"

    suggestions = [
        "画像の品質を確認してください（解像度・明度・コントラスト）",
        "OCRエンジンの設定を調整してみてください",
        "別の画像範囲を選択してみてください"
    ]

    technical_details = None
    if original_error:
        technical_details = f"{type(original_error).__name__}: {str(original_error)}"

        # メモリエラーの特別処理
        if isinstance(original_error, MemoryError):
            suggestions = [
                "他のアプリケーションを終了してメモリを解放してください",
                "より小さい解像度でOCRを実行してみてください",
                "システムを再起動してください"
            ]

    return ErrorInfo(
        message=message,
        category=ErrorCategory.OCR_PROCESSING,
        severity=ErrorSeverity.WARNING,
        technical_details=technical_details,
        suggestions=suggestions
    )