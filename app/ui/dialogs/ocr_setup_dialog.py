"""
OCR初回セットアップダイアログ
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QTextEdit, QCheckBox, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap, QPainter
import logging
from pathlib import Path
from typing import Optional

from app.core.extractor.ocr import OCRModelDownloader, PADDLEOCR_AVAILABLE


class OCRSetupWorker(QThread):
    """OCRセットアップバックグラウンドワーカー"""

    progress_updated = Signal(str, int)  # message, progress
    setup_completed = Signal(bool)  # success
    error_occurred = Signal(str)  # error_message

    def __init__(self, language: str = "ja"):
        super().__init__()
        self.language = language

    def run(self):
        """セットアップ実行"""
        try:
            def progress_callback(message: str, progress: int):
                self.progress_updated.emit(message, progress)

            # PaddleOCRモデルダウンロード実行
            OCRModelDownloader.download_paddleocr_model(
                self.language,
                progress_callback
            )

            self.setup_completed.emit(True)

        except Exception as e:
            self.error_occurred.emit(str(e))
            self.setup_completed.emit(False)


class OCRSetupDialog(QDialog):
    """OCR初回セットアップダイアログ"""

    def __init__(self, parent=None, language: str = "ja"):
        super().__init__(parent)
        self.language = language
        self.worker = None
        self.setup_success = False

        self.setWindowTitle("OCRエンジン初期セットアップ")
        self.setFixedSize(500, 400)
        self.setModal(True)

        self.init_ui()
        self.check_current_status()

    def init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # タイトル
        title_label = QLabel("OCRエンジンの初期セットアップ")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 説明文
        description = QLabel(
            "字幕抽出を行うために、PaddleOCRの日本語認識モデルが必要です。\n"
            "初回のみ、インターネットからモデルファイル（約50MB）をダウンロードします。\n"
            "ダウンロード完了後、オフラインでも字幕抽出が可能になります。\n\n"
            "※ ダウンロードに失敗する場合は、ネットワーク接続やファイアウォール設定を\n"
            "　 確認してください。また、Tesseractエンジンも利用可能です。"
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignLeft)
        layout.addWidget(description)

        # 区切り線
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # ステータス表示
        self.status_label = QLabel("セットアップステータス確認中...")
        layout.addWidget(self.status_label)

        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # プログレスメッセージ
        self.progress_message = QLabel("")
        self.progress_message.setAlignment(Qt.AlignCenter)
        self.progress_message.setVisible(False)
        layout.addWidget(self.progress_message)

        # 詳細ログ
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(100)
        self.log_text.setVisible(False)
        layout.addWidget(self.log_text)

        # ログ表示チェックボックス
        self.show_log_check = QCheckBox("詳細ログを表示")
        self.show_log_check.toggled.connect(self.toggle_log_display)
        layout.addWidget(self.show_log_check)

        # ボタン
        button_layout = QHBoxLayout()

        self.setup_btn = QPushButton("セットアップ開始")
        self.setup_btn.clicked.connect(self.start_setup)
        self.setup_btn.setEnabled(False)
        button_layout.addWidget(self.setup_btn)

        self.skip_btn = QPushButton("スキップ（Tesseractを使用）")
        self.skip_btn.clicked.connect(self.skip_setup)
        button_layout.addWidget(self.skip_btn)

        self.close_btn = QPushButton("キャンセル")
        self.close_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        # ストレッチでレイアウト調整
        layout.addStretch()

    def check_current_status(self):
        """現在のOCRステータス確認"""
        QTimer.singleShot(500, self._check_status)

    def _check_status(self):
        """ステータス確認実行"""
        try:
            if not PADDLEOCR_AVAILABLE:
                self.status_label.setText("❌ PaddleOCRがインストールされていません")
                self.status_label.setStyleSheet("color: red;")
                self.setup_btn.setEnabled(False)
                self.add_log("PaddleOCRパッケージが見つかりません")
                return

            if OCRModelDownloader.is_paddleocr_model_available(self.language):
                self.status_label.setText("✅ PaddleOCRモデルは既にダウンロード済みです")
                self.status_label.setStyleSheet("color: green;")
                self.setup_btn.setText("完了")
                self.setup_btn.setEnabled(True)
                self.skip_btn.setText("閉じる")
                self.setup_success = True
                self.add_log("PaddleOCRモデルが利用可能です")
            else:
                self.status_label.setText("⚠️ PaddleOCRモデルのダウンロードが必要です")
                self.status_label.setStyleSheet("color: orange;")
                self.setup_btn.setEnabled(True)
                self.add_log("PaddleOCRモデルが見つかりません")

        except Exception as e:
            self.status_label.setText(f"❌ エラー: {str(e)}")
            self.status_label.setStyleSheet("color: red;")
            self.add_log(f"ステータス確認エラー: {str(e)}")

    def start_setup(self):
        """セットアップ開始"""
        if self.setup_success:
            self.accept()
            return

        if not PADDLEOCR_AVAILABLE:
            QMessageBox.warning(
                self,
                "エラー",
                "PaddleOCRがインストールされていません。\n"
                "pip install paddleocrでインストールしてください。"
            )
            return

        # 確認ダイアログ（初回のみ）
        if not hasattr(self, '_setup_confirmed'):
            reply = QMessageBox.question(
                self,
                "セットアップ確認",
                "PaddleOCRモデルのダウンロードを開始します。\n\n"
                "- ダウンロードサイズ: 約50MB\n"
                "- 所要時間: 1-5分程度\n"
                "- 3回まで自動リトライします\n\n"
                "続行しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return
            self._setup_confirmed = True

        # UI状態を更新
        self.setup_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_message.setVisible(True)

        # ワーカースレッド開始
        self.worker = OCRSetupWorker(self.language)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.setup_completed.connect(self.on_setup_completed)
        self.worker.error_occurred.connect(self.on_error_occurred)
        self.worker.start()

        self.add_log("PaddleOCRモデルのダウンロードを開始します（リトライ機能付き）...")

    def skip_setup(self):
        """セットアップをスキップ"""
        if self.setup_success:
            self.accept()
            return

        reply = QMessageBox.question(
            self,
            "確認",
            "PaddleOCRのセットアップをスキップしますか？\n\n"
            "スキップした場合：\n"
            "・Tesseractエンジンが使用されます\n"
            "・OCR精度がPaddleOCRより劣る場合があります\n"
            "・後で設定画面からPaddleOCRを有効化できます",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.reject()

    def on_progress_updated(self, message: str, progress: int):
        """プログレス更新"""
        self.progress_message.setText(message)
        self.progress_bar.setValue(progress)
        self.add_log(f"[{progress}%] {message}")

    def on_setup_completed(self, success: bool):
        """セットアップ完了"""
        self.progress_bar.setVisible(False)
        self.progress_message.setVisible(False)

        if success:
            self.status_label.setText("✅ PaddleOCRセットアップが完了しました！")
            self.status_label.setStyleSheet("color: green;")
            self.setup_btn.setText("完了")
            self.setup_btn.setEnabled(True)
            self.skip_btn.setText("閉じる")
            self.close_btn.setEnabled(True)
            self.setup_success = True
            self.add_log("セットアップが正常に完了しました")
        else:
            self.status_label.setText("❌ セットアップに失敗しました")
            self.status_label.setStyleSheet("color: red;")
            self.setup_btn.setText("再試行")
            self.setup_btn.setEnabled(True)
            self.skip_btn.setEnabled(True)
            self.close_btn.setEnabled(True)

    def on_error_occurred(self, error_message: str):
        """エラー発生"""
        self.add_log(f"エラー: {error_message}")

        # エラーメッセージの表示（詳細なトラブルシューティング情報付き）
        detailed_message = self._format_error_message(error_message)

        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setWindowTitle("PaddleOCRセットアップエラー")
        error_dialog.setText("PaddleOCRのセットアップに失敗しました")
        error_dialog.setDetailedText(detailed_message)
        error_dialog.setStandardButtons(QMessageBox.Ok)
        error_dialog.exec()

    def _format_error_message(self, error_message: str) -> str:
        """エラーメッセージを詳細な形式に整形"""
        formatted_msg = f"エラー詳細:\n{error_message}\n\n"

        # 一般的な解決方法
        formatted_msg += "解決方法:\n"
        formatted_msg += "1. インターネット接続を確認してください\n"
        formatted_msg += "2. ファイアウォールやアンチウイルスソフトの設定を確認してください\n"
        formatted_msg += "3. 企業ネットワークの場合、プロキシ設定を確認してください\n"
        formatted_msg += "4. 'セットアップ開始'ボタンで再試行してください\n"
        formatted_msg += "5. 問題が解決しない場合は、'スキップ（Tesseractを使用）'をお試しください\n\n"

        # システム情報
        import platform
        formatted_msg += f"システム情報:\n"
        formatted_msg += f"- OS: {platform.system()} {platform.release()}\n"
        formatted_msg += f"- Python: {platform.python_version()}\n"

        return formatted_msg

    def add_log(self, message: str):
        """ログ追加"""
        self.log_text.append(f"[{self._get_timestamp()}] {message}")
        logging.info(f"OCRSetup: {message}")

    def toggle_log_display(self, checked: bool):
        """ログ表示切り替え"""
        self.log_text.setVisible(checked)
        if checked:
            self.setFixedSize(500, 500)
        else:
            self.setFixedSize(500, 400)

    def _get_timestamp(self):
        """タイムスタンプ取得"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def closeEvent(self, event):
        """ダイアログクローズ時"""
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "確認",
                "ダウンロード中です。中断しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.worker.terminate()
                self.worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()