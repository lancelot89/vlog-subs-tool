"""
メインウィンドウの実装
DESIGN.mdの画面仕様に基づくGUIレイアウト
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.core.csv import SubtitleCSVExporter
from app.core.extractor.ocr import SimplePaddleOCREngine
from app.core.format.srt import MultiLanguageSRTManager, SRTFormatSettings, SRTFormatter
from app.core.models import Project, SubtitleItem
from app.core.project_manager import get_project_manager
from app.core.qc.rules import QCChecker
from app.core.settings_manager import get_settings_manager
from app.core.translate import (
    LocalTranslateError,
    LocalTranslateProvider,
    LocalTranslateSettings,
    TranslationProviderRouter,
    TranslationProviderType,
)

from .dialogs.multilang_export_dialog import MultiLanguageExportDialog
from .dialogs.ocr_setup_dialog import OCRSetupDialog
from .extraction_worker import ExtractionWorker
from .views.player_view import PlayerView
from .views.settings_view import SettingsView
from .views.table_view import SubtitleTableView
from .views.translate_view import TranslateView


def setup_japanese_support(app):
    """日本語表示サポート設定"""
    import locale
    import os

    from PySide6.QtCore import QLocale
    from PySide6.QtGui import QFont, QFontDatabase

    try:
        # システムエンコーディング設定
        if hasattr(locale, "getpreferredencoding"):
            encoding = locale.getpreferredencoding()
            if encoding.lower() not in ["utf-8", "utf8"]:
                os.environ["LANG"] = "ja_JP.UTF-8"
                os.environ["LC_ALL"] = "ja_JP.UTF-8"

        # Qt ロケール設定
        QLocale.setDefault(QLocale(QLocale.Japanese))

        # フォント設定
        font_database = QFontDatabase()

        # 利用可能な日本語フォントを検索
        japanese_fonts = [
            "Noto Sans CJK JP",
            "IPAexGothic",
            "IPAPGothic",
            "VL PGothic",
            "TakaoExGothic",
            "TakaoPGothic",
            "MS Gothic",
            "Meiryo",
            "Yu Gothic",
            "ヒラギノ角ゴ ProN",
            "Source Han Sans JP",
            "DejaVu Sans",
        ]

        selected_font = None
        for font_name in japanese_fonts:
            families = font_database.families()
            for family in families:
                if font_name.lower() in family.lower():
                    selected_font = family
                    break
            if selected_font:
                break

        # フォールバック: システムのデフォルト日本語フォント
        if not selected_font:
            # システムフォントから検索
            for family in font_database.families():
                # CJK（中日韓）文字対応フォントを検索
                if any(
                    keyword in family.lower()
                    for keyword in ["cjk", "gothic", "mincho", "jp", "japanese"]
                ):
                    selected_font = family
                    break

        # 最終フォールバック: 汎用Unicode対応フォント
        if not selected_font:
            fallback_fonts = [
                "Arial Unicode MS",
                "DejaVu Sans",
                "Liberation Sans",
                "FreeSans",
                "sans-serif",
            ]
            for fallback in fallback_fonts:
                if fallback in font_database.families():
                    selected_font = fallback
                    break

            # 全てのフォールバックが失敗した場合
            if not selected_font:
                selected_font = font_database.families()[0] if font_database.families() else "Arial"

        # アプリケーション全体のフォント設定
        font = QFont(selected_font, 10)
        # 日本語表示に最適なヒント設定
        font.setStyleHint(QFont.SansSerif, QFont.PreferDefault)
        font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(font)

        import logging

        logging.info(f"日本語フォント設定完了: {selected_font}")

        # 利用可能なフォント一覧をデバッグ出力（最初の10個）
        available_fonts = font_database.families()[:10]
        logging.info(f"利用可能なフォント (最初10個): {available_fonts}")

    except Exception as e:
        import logging

        logging.error(f"日本語サポート設定でエラー: {e}")
        # エラーの場合はデフォルトフォントを使用
        default_font = QFont("DejaVu Sans", 10)
        app.setFont(default_font)


class MainWindow(QMainWindow):
    """メインウィンドウクラス"""

    # シグナル定義
    video_loaded = Signal(str)  # 動画読み込み完了
    project_saved = Signal(str)  # プロジェクト保存完了
    extraction_started = Signal()  # 抽出開始
    extraction_completed = Signal()  # 抽出完了

    def __init__(self):
        super().__init__()
        self.current_project: Optional[Project] = None
        self.current_video_path: Optional[str] = None

        # 抽出ワーカー
        self.extraction_worker: Optional[ExtractionWorker] = None

        self.init_ui()
        self.connect_signals()
        self.setup_shortcuts()

        # ステータス更新タイマー
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)  # 1秒ごと

    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle("VLog字幕ツール v1.0")
        self.setGeometry(100, 100, 1200, 800)

        # メニューバーの作成
        self.create_menu_bar()

        # ツールバーの作成
        self.create_toolbar()

        # 中央ウィジェットの作成
        self.create_central_widget()

        # ステータスバーの作成
        self.create_status_bar()

        # ドラッグ&ドロップを有効化
        self.setAcceptDrops(True)

    def create_menu_bar(self):
        """メニューバーの作成"""
        menubar = self.menuBar()

        # ファイルメニュー
        file_menu = menubar.addMenu("ファイル(&F)")

        open_action = QAction("動画を開く(&O)", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_video)
        file_menu.addAction(open_action)

        recent_menu = file_menu.addMenu("最近使用したファイル(&R)")
        file_menu.addSeparator()

        save_action = QAction("プロジェクトを保存(&S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction("名前を付けて保存(&A)", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        # SRT出力メニュー
        export_menu = file_menu.addMenu("字幕を出力(&E)")

        export_ja_action = QAction("日本語SRT(&J)", self)
        export_ja_action.triggered.connect(self.export_japanese_srt)
        export_menu.addAction(export_ja_action)

        export_all_action = QAction("全言語SRT(&A)", self)
        export_all_action.triggered.connect(self.export_all_srt)
        export_menu.addAction(export_all_action)

        # 元データCSVエクスポート
        self.csv_export_menu_action = QAction("CSV出力(&C)", self)
        self.csv_export_menu_action.setEnabled(False)
        self.csv_export_menu_action.triggered.connect(self.export_original_csv)
        export_menu.addAction(self.csv_export_menu_action)

        file_menu.addSeparator()

        exit_action = QAction("終了(&X)", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 編集メニュー
        edit_menu = menubar.addMenu("編集(&E)")

        qc_check_action = QAction("QCチェック(&Q)", self)
        qc_check_action.setShortcut("Ctrl+Q")
        qc_check_action.triggered.connect(self.run_qc_check)
        edit_menu.addAction(qc_check_action)

        # 表示メニュー
        view_menu = menubar.addMenu("表示(&V)")

        # 翻訳メニュー
        translate_menu = menubar.addMenu("翻訳(&T)")

        translate_settings_action = QAction("翻訳設定(&S)", self)
        translate_settings_action.triggered.connect(self.show_translate_view)
        translate_menu.addAction(translate_settings_action)

        translate_menu.addSeparator()

        export_csv_action = QAction("CSVエクスポート(&E)", self)
        export_csv_action.triggered.connect(self.export_translation_csv)
        translate_menu.addAction(export_csv_action)

        import_csv_action = QAction("翻訳CSVインポート(&I)", self)
        import_csv_action.triggered.connect(self.import_translation_csv)
        translate_menu.addAction(import_csv_action)

        # 設定メニュー
        settings_menu = menubar.addMenu("設定(&S)")

        settings_action = QAction("設定(&P)", self)
        settings_action.triggered.connect(self.show_settings)
        settings_menu.addAction(settings_action)

        # ヘルプメニュー
        help_menu = menubar.addMenu("ヘルプ(&H)")

        about_action = QAction("このアプリについて(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_toolbar(self):
        """ツールバーの作成"""
        toolbar = self.addToolBar("メイン")
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        # 動画を開く
        open_btn = QPushButton("動画を開く")
        open_btn.clicked.connect(self.open_video)
        toolbar.addWidget(open_btn)

        toolbar.addSeparator()

        # 字幕抽出
        self.extract_btn = QPushButton("字幕抽出")
        self.extract_btn.clicked.connect(self.start_extraction)
        self.extract_btn.setEnabled(False)
        toolbar.addWidget(self.extract_btn)

        # 旧キャンセルボタン（下位互換のため残すが、使用は停止）
        self.cancel_btn = QPushButton("🛑 抽出停止")
        self.cancel_btn.clicked.connect(self.cancel_extraction)
        self.cancel_btn.setVisible(False)  # 常に非表示
        # NOTE: 新しい実装では自動抽出ボタン自体がキャンセルボタンに変化するため、
        # この独立したキャンセルボタンは表示されません

        toolbar.addSeparator()

        # 翻訳・CSV連携
        self.translate_btn = QPushButton("翻訳設定")
        self.translate_btn.clicked.connect(self.show_translate_view)
        self.translate_btn.setEnabled(False)
        toolbar.addWidget(self.translate_btn)

        self.csv_export_btn = QPushButton("CSV出力")
        self.csv_export_btn.clicked.connect(self.export_original_csv)
        self.csv_export_btn.setEnabled(False)
        toolbar.addWidget(self.csv_export_btn)
        # 旧テスト互換用エイリアス
        self.csv_export_action = self.csv_export_btn

        toolbar.addSeparator()

        # SRT出力
        self.export_srt_btn = QPushButton("SRT出力")
        self.export_srt_btn.clicked.connect(self.show_multilang_export_dialog)
        self.export_srt_btn.setEnabled(False)
        toolbar.addWidget(self.export_srt_btn)

    def create_central_widget(self):
        """中央ウィジェットの作成"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # メインレイアウト
        main_layout = QHBoxLayout(central_widget)

        # スプリッター
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # 左ペイン: 動画プレビュー
        self.player_view = PlayerView()
        splitter.addWidget(self.player_view)

        # 右ペイン: 字幕テーブル
        self.table_view = SubtitleTableView()
        splitter.addWidget(self.table_view)

        # 分割比率の設定
        splitter.setSizes([600, 600])

    def create_status_bar(self):
        """ステータスバーの作成"""
        self.status_bar = self.statusBar()

        # プログレスバー（ETA表示対応）
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)  # テキスト表示を有効化
        self.progress_bar.setFormat("%p% - 待機中...")  # 初期テキスト
        self.status_bar.addPermanentWidget(self.progress_bar)

        # ステータスラベル
        self.status_label = QLabel("準備完了")
        self.status_bar.addWidget(self.status_label)

        # ファイル情報ラベル
        self.file_info_label = QLabel("")
        self.status_bar.addPermanentWidget(self.file_info_label)

    def connect_signals(self):
        """シグナルの接続"""
        # 動画読み込み時
        self.video_loaded.connect(self.on_video_loaded)

        # テーブル選択時のプレビュー同期
        self.table_view.subtitle_selected.connect(self.player_view.seek_to_time)

        # プレビュー時間変更時のテーブル同期
        self.player_view.time_changed.connect(self.table_view.highlight_current_subtitle)

        # 新しい同期機能
        self.table_view.seek_requested.connect(self.player_view.seek_to_time)
        self.table_view.loop_region_set.connect(self.player_view.set_loop_region)

        # 字幕変更時の更新
        self.table_view.subtitle_changed.connect(self.on_subtitle_changed)
        self.table_view.subtitles_reordered.connect(self.on_subtitles_reordered)

    def setup_shortcuts(self):
        """ショートカットキーの設定"""
        # Space: 再生/一時停止
        self.play_pause_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.play_pause_shortcut.activated.connect(self.toggle_playback)

        # S: 字幕分割
        self.split_shortcut = QShortcut(QKeySequence(Qt.Key.Key_S), self)
        self.split_shortcut.activated.connect(self.table_view.split_subtitle)

        # M: 字幕結合
        self.merge_shortcut = QShortcut(QKeySequence(Qt.Key.Key_M), self)
        self.merge_shortcut.activated.connect(self.table_view.merge_subtitle)

        # Ctrl+Q: QCチェック
        self.qc_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.qc_shortcut.activated.connect(self.run_qc_check)

        # 左右矢印: フレーム移動
        self.frame_back_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.frame_back_shortcut.activated.connect(self.seek_frame_back)

        self.frame_forward_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.frame_forward_shortcut.activated.connect(self.seek_frame_forward)

    def toggle_playback(self):
        """再生/一時停止の切り替え（ショートカット用）"""
        if hasattr(self.player_view, "toggle_play"):
            self.player_view.toggle_play()

    def seek_frame_back(self):
        """1フレーム戻る"""
        if hasattr(self.player_view, "current_frame") and self.player_view.current_frame > 0:
            self.player_view.seek_to_frame(self.player_view.current_frame - 1)

    def seek_frame_forward(self):
        """1フレーム進む"""
        if (
            hasattr(self.player_view, "current_frame")
            and hasattr(self.player_view, "total_frames")
            and self.player_view.current_frame < self.player_view.total_frames - 1
        ):
            self.player_view.seek_to_frame(self.player_view.current_frame + 1)

    def open_video(self):
        """動画ファイルを開く"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "動画ファイルを選択",
            "",
            "動画ファイル (*.mp4 *.mov *.avi *.mkv);;すべてのファイル (*)",
        )

        if file_path:
            self.load_video(file_path)

    def load_video(self, file_path: str):
        """動画を読み込む（エラーハンドリング強化版）"""
        try:
            # ファイルの存在確認
            if not Path(file_path).exists():
                QMessageBox.warning(
                    self,
                    "ファイルエラー",
                    f"指定されたファイルが見つかりません:\n{file_path}",
                )
                return

            # ファイルサイズ確認
            file_size = Path(file_path).stat().st_size
            if file_size == 0:
                QMessageBox.warning(
                    self,
                    "ファイルエラー",
                    "ファイルサイズが0バイトです。破損している可能性があります。",
                )
                return

            # 対応形式の確認
            supported_formats = [
                ".mp4",
                ".mov",
                ".avi",
                ".mkv",
                ".flv",
                ".wmv",
                ".webm",
            ]
            file_ext = Path(file_path).suffix.lower()
            if file_ext not in supported_formats:
                reply = QMessageBox.question(
                    self,
                    "形式確認",
                    f"ファイル形式 '{file_ext}' は推奨されていません。\n"
                    f"推奨形式: {', '.join(supported_formats)}\n\n"
                    f"続行しますか？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    return

            self.current_video_path = file_path

            # プレイヤーに動画を読み込み
            self.player_view.load_video(file_path)

            # プロジェクトを作成
            self.current_project = Project.create_new(file_path)

            # UIの更新
            self.extract_btn.setEnabled(True)

            # ファイル情報の更新
            file_name = Path(file_path).name
            file_size_mb = file_size / (1024 * 1024)
            self.file_info_label.setText(f"動画: {file_name} ({file_size_mb:.1f}MB)")

            self.video_loaded.emit(file_path)
            self.status_label.setText("動画を読み込みました")

        except cv2.error as e:
            self.handle_video_codec_error(file_path, str(e))
        except Exception as e:
            self.handle_general_video_error(file_path, str(e))

    def handle_video_codec_error(self, file_path: str, error_msg: str):
        """動画コーデック関連エラーの処理"""
        file_ext = Path(file_path).suffix.lower()

        error_dialog = QMessageBox(self)
        error_dialog.setWindowTitle("動画コーデックエラー")
        error_dialog.setIcon(QMessageBox.Icon.Critical)

        error_text = f"動画ファイルを開けませんでした。\n\n"
        error_text += f"ファイル: {Path(file_path).name}\n"
        error_text += f"形式: {file_ext}\n\n"
        error_text += "考えられる原因:\n"
        error_text += "• サポートされていないコーデック\n"
        error_text += "• ファイルの破損\n"
        error_text += "• DRMによる保護\n\n"
        error_text += "対処法:\n"
        error_text += "• mp4, mov形式への変換をお試しください\n"
        error_text += "• ffmpegやHandBrakeなどを利用してください\n"
        error_text += f"• 推奨形式: mp4 (H.264 + AAC)"

        error_dialog.setText(error_text)
        error_dialog.exec()

    def handle_general_video_error(self, file_path: str, error_msg: str):
        """一般的な動画読み込みエラーの処理"""
        QMessageBox.critical(
            self,
            "動画読み込みエラー",
            f"動画の読み込みに失敗しました。\n\n"
            f"ファイル: {Path(file_path).name}\n"
            f"エラー詳細: {error_msg}\n\n"
            f"• ファイルが使用中でないか確認してください\n"
            f"• ファイル形式が対応しているか確認してください",
        )

    def on_video_loaded(self, file_path: str):
        """動画読み込み完了時の処理"""
        self.setWindowTitle(f"VLog字幕ツール v1.0 - {Path(file_path).name}")

    def stop_extraction(self):
        """抽出処理を停止"""
        if self.extraction_worker and self.extraction_worker.isRunning():
            self.extraction_worker.cancel()
            self.extraction_worker.wait()

    def on_extraction_progress(self, percentage: int, message: str):
        """抽出プログレス更新（ETA情報付き）"""
        self.progress_bar.setValue(percentage)

        # プログレスバーのテキスト表示も更新
        if percentage < 100:
            self.progress_bar.setFormat(f"{percentage}% - 処理中...")
        else:
            self.progress_bar.setFormat(f"{percentage}% - 完了")

        # ステータスラベルにメッセージ（ETA情報含む）を表示
        self.status_label.setText(message)

    def on_extraction_completed(self, subtitle_items: List[SubtitleItem]):
        """抽出完了処理"""
        # プロジェクトに字幕を設定
        self.current_project.subtitles = subtitle_items

        # テーブルビューに字幕を表示
        self.table_view.set_subtitles(subtitle_items)

        # プレイヤービューにも字幕を設定
        self.player_view.set_subtitles(subtitle_items)

        # プログレスバーを非表示
        self.progress_bar.setVisible(False)

        # 自動抽出ボタンを元の状態に戻す
        logging.info("自動抽出ボタンを元の状態に戻します")
        self._restore_extract_button()

        # UI状態の更新
        self.extract_btn.setEnabled(True)
        self.translate_btn.setEnabled(True)
        self.csv_export_btn.setEnabled(True)
        if hasattr(self, "csv_export_menu_action") and self.csv_export_menu_action is not None:
            self.csv_export_menu_action.setEnabled(True)
        self.export_srt_btn.setEnabled(True)

        self.status_label.setText(f"字幕の抽出が完了しました ({len(subtitle_items)}件)")
        self.extraction_completed.emit()

    def on_extraction_error(self, error_message: str):
        """抽出エラー処理"""
        # プログレスバーを非表示
        self.progress_bar.setVisible(False)

        # 自動抽出ボタンを元の状態に戻す
        logging.info("エラー時: 自動抽出ボタンを元の状態に戻します")
        self._restore_extract_button()

        QMessageBox.critical(self, "抽出エラー", f"字幕の抽出に失敗しました:\\n{error_message}")

        # UI状態をリセット
        self.extract_btn.setEnabled(True)
        self.status_label.setText("字幕の抽出に失敗しました")

    def on_extraction_cancelled(self):
        """抽出キャンセル処理"""
        # プログレスバーを非表示
        self.progress_bar.setVisible(False)

        # 自動抽出ボタンを元の状態に戻す
        logging.info("キャンセル時: 自動抽出ボタンを元の状態に戻します")
        self._restore_extract_button()

        # UI状態をリセット
        self.extract_btn.setEnabled(True)
        self.status_label.setText("字幕抽出がキャンセルされました")

    def on_extraction_finished(self):
        """抽出処理終了時の共通処理"""
        self.progress_bar.setVisible(False)

        # 自動抽出ボタンを元の状態に戻す（念のため）
        logging.info("終了時: 自動抽出ボタンを元の状態に戻します")
        self._restore_extract_button()

        # ワーカーのクリーンアップ
        if self.extraction_worker:
            self.extraction_worker.cleanup()
            self.extraction_worker = None

    def start_extraction(self):
        """字幕抽出を開始"""
        if not self.current_project or not self.current_project.source_video:
            QMessageBox.warning(self, "警告", "動画ファイルが選択されていません。")
            return

        # 抽出開始前の確認ダイアログ（先に表示）
        if not self._confirm_extraction_start():
            return

        # OCRセットアップ確認（確認ダイアログの後に実行）
        if not self.check_ocr_setup():
            return

        # 既存の抽出処理を停止
        self.stop_extraction()

        # プログレスバー表示
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0% - 準備中...")

        # 自動抽出ボタンをキャンセルボタンに変更
        logging.info("=== 🛑 自動抽出ボタンをキャンセルボタンに変更開始 ===")

        # 元のボタンの接続を切断
        self.extract_btn.clicked.disconnect()

        # キャンセル機能に変更
        self.extract_btn.setText("🛑 抽出停止")
        self.extract_btn.setEnabled(True)
        self.extract_btn.clicked.connect(self.cancel_extraction)

        # デフォルトスタイルを維持（他のボタンと同じ見た目）
        self.extract_btn.setStyleSheet("")

        # 再抽出ボタンも無効化

        logging.info("自動抽出ボタンが🛑抽出停止ボタンに変更されました")
        logging.info("=== 🛑 ボタン変更処理完了 ===")

        # ワーカースレッド作成・開始
        self.extraction_worker = ExtractionWorker(
            self.current_project.source_video, self.current_project.settings
        )

        # シグナル接続
        self.extraction_worker.progress_updated.connect(self.on_extraction_progress)
        self.extraction_worker.subtitles_extracted.connect(self.on_extraction_completed)
        self.extraction_worker.error_occurred.connect(self.on_extraction_error)
        self.extraction_worker.cancelled.connect(self.on_extraction_cancelled)
        self.extraction_worker.finished.connect(self.on_extraction_finished)

        # 抽出開始
        self.extraction_worker.start()

    def re_extract(self):
        """再抽出"""
        self.start_extraction()

    def cancel_extraction(self):
        """抽出処理をキャンセル"""
        if not self.extraction_worker or not self.extraction_worker.isRunning():
            return

        # キャンセル確認ダイアログ
        reply = QMessageBox.question(
            self,
            "キャンセル確認",
            "字幕抽出を中止しますか？\n\n" "進行中の処理が停止され、現在までの結果は破棄されます。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # キャンセル実行
            logging.info("ユーザーがキャンセルを確定しました")
            # 自動抽出ボタン（現在はキャンセルボタン）を「キャンセル中...」に変更
            self.extract_btn.setEnabled(False)  # 連打防止
            self.extract_btn.setText("⏳ キャンセル中...")
            # デフォルトスタイルを維持（無効化時の標準的な見た目）
            self.extract_btn.setStyleSheet("")
            self.status_label.setText("処理を中止しています...")

            # ワーカーにキャンセル要請
            logging.info("ExtractionWorkerにキャンセル要請を送信")
            self.extraction_worker.cancel()

    def _confirm_extraction_start(self) -> bool:
        """抽出開始前の確認ダイアログ"""
        try:
            # 動画情報を取得して処理時間を推定
            video_path = self.current_project.source_video
            import cv2

            cap = cv2.VideoCapture(video_path)

            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS) or 30
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = frame_count / fps if fps > 0 else 0
                cap.release()

                # 処理時間の目安を計算（概算）
                estimated_minutes = max(1, int(duration / 60 * 0.5))  # 動画時間の約50%

                duration_str = f"{int(duration // 60)}分{int(duration % 60)}秒"
                estimated_str = f"約{estimated_minutes}分"
            else:
                duration_str = "不明"
                estimated_str = "数分"

        except Exception:
            duration_str = "不明"
            estimated_str = "数分"

        # 確認ダイアログを表示
        message = f"""字幕の自動抽出を開始しますか？

📹 動画時間: {duration_str}
⏱️ 予想処理時間: {estimated_str}

📋 処理内容:
• 動画フレームの解析
• OCRによる文字認識
• 字幕のグルーピング

⚠️ 注意:
• 処理中はアプリケーションが専有されます
• 長時間の動画では時間がかかる場合があります
• いつでもキャンセルボタンで中止できます"""

        reply = QMessageBox.question(
            self,
            "字幕抽出の開始確認",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        return reply == QMessageBox.StandardButton.Yes

    def _show_cancel_button_with_force(self):
        """キャンセルボタンを確実に表示する強化メソッド"""
        # 複数のアプローチで確実に表示
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("🛑 抽出停止")

        # スタイルシートを再適用（絵文字版、より目立つデザイン）
        self.cancel_btn.setStyleSheet(
            """
            QPushButton {
                color: white;
                font-weight: bold;
                font-size: 16px;
                background-color: #d32f2f;
                border: 3px solid #b71c1c;
                border-radius: 8px;
                padding: 10px 15px;
                text-align: center;
                min-width: 120px;
                max-width: 120px;
                min-height: 35px;
                max-height: 35px;
            }
            QPushButton:hover {
                background-color: #f44336;
                border-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
            QPushButton:disabled {
                color: #999;
                border-color: #ccc;
                background-color: #f0f0f0;
            }
        """
        )

        # 強制更新の複数アプローチ（詳細ログ付き）
        logging.info("段階1: ボタン直接更新")
        self.cancel_btn.show()  # show()も明示的に呼び出し
        self.cancel_btn.raise_()  # 前面に持ってくる
        self.cancel_btn.repaint()
        self.cancel_btn.update()
        logging.info(f"段階1後のvisible状態: {self.cancel_btn.isVisible()}")

        # ツールバー全体を更新
        logging.info("段階2: ツールバー更新")
        toolbar = self.cancel_btn.parent()
        if toolbar:
            toolbar.show()
            toolbar.repaint()
            toolbar.update()
            # ツールバー内のウィジェット数をログ出力
            toolbar_children = toolbar.children()
            logging.info(f"ツールバー子要素数: {len(toolbar_children)}")
            # キャンセルボタンがツールバーの子要素に含まれているかチェック
            is_in_toolbar = self.cancel_btn in toolbar_children
            logging.info(f"キャンセルボタンはツールバーに含まれる: {is_in_toolbar}")
        else:
            logging.warning("キャンセルボタンの親ウィジェット（ツールバー）が見つかりません")

        # 全体UI更新
        logging.info("段階3: ウィンドウ全体更新")
        self.update()
        self.repaint()
        QApplication.processEvents()  # イベント処理を明示的に実行

        # QTimerで遅延チェック（複数回）
        from PySide6.QtCore import QTimer

        QTimer.singleShot(50, self._verify_cancel_button_visibility)
        QTimer.singleShot(200, self._verify_cancel_button_visibility)
        QTimer.singleShot(500, self._verify_cancel_button_visibility)

        final_visible = self.cancel_btn.isVisible()
        final_enabled = self.cancel_btn.isEnabled()
        final_size = self.cancel_btn.size()
        final_pos = self.cancel_btn.pos()

        logging.info(f"🛑 強制表示完了 - visible: {final_visible}, enabled: {final_enabled}")
        logging.info(f"🛑 最終状態 - size: {final_size}, pos: {final_pos}")

        if not final_visible:
            logging.error("⚠️ 警告: すべての処理を実行してもキャンセルボタンが表示されていません")

    def _restore_extract_button(self):
        """自動抽出ボタンを元の状態に戻す"""
        logging.info("🔄 自動抽出ボタンを元の状態に復元開始")

        # 既存の接続を切断
        try:
            self.extract_btn.clicked.disconnect()
        except Exception:
            pass  # 既に切断されている場合は無視

        # 元の機能に戻す
        self.extract_btn.setText("字幕抽出")
        self.extract_btn.setEnabled(True)
        self.extract_btn.clicked.connect(self.start_extraction)

        # 元のスタイルに戻す（デフォルトスタイル）
        self.extract_btn.setStyleSheet("")

        logging.info("🔄 自動抽出ボタンの復元完了")

    def _verify_cancel_button_visibility(self):
        """キャンセルボタンの表示を検証"""
        if not self.cancel_btn.isVisible():
            logging.warning("キャンセルボタンがまだ表示されていません。再試行します。")
            self.cancel_btn.setVisible(True)
            self.cancel_btn.show()  # show()メソッドも試行
            self.cancel_btn.raise_()  # 前面に持ってくる
            self.cancel_btn.repaint()

            # 親ウィジェットの更新も試行
            if self.cancel_btn.parent():
                self.cancel_btn.parent().update()
        else:
            logging.info("キャンセルボタンの表示が確認されました")

    def check_ocr_setup(self) -> bool:
        """OCRセットアップの確認（SimplePaddleOCREngine使用）"""
        try:
            # 初期化開始をユーザーに通知
            self.status_label.setText("OCRエンジン初期化中...")
            # UIの更新を強制実行
            QApplication.processEvents()

            # SimplePaddleOCREngineの利用可能性をチェック
            ocr_engine = SimplePaddleOCREngine()

            if ocr_engine.initialize():
                logging.info("SimplePaddleOCREngineを使用して字幕抽出を開始します")
                self.status_label.setText("PaddleOCRエンジンで字幕抽出を開始...")
                return True
            else:
                # 初期化失敗時の詳細メッセージ
                QMessageBox.critical(
                    self,
                    "PaddleOCR初期化エラー",
                    "PaddleOCRエンジンの初期化に失敗しました。\n\n"
                    "考えられる原因：\n"
                    "• モデルファイルが見つからない\n"
                    "• PaddleOCRライブラリの問題\n"
                    "• メモリ不足\n"
                    "• 依存関係の問題\n\n"
                    "ログを確認してください。",
                )
                return False

        except Exception as e:
            # 予期しないエラーの場合
            logging.error(f"OCRセットアップ確認中にエラー: {e}")
            QMessageBox.critical(
                self,
                "OCRセットアップエラー",
                f"OCRエンジンの確認中にエラーが発生しました：\n{str(e)}\n\n"
                "アプリケーションを再起動してお試しください。",
            )
            return False

    def run_qc_check(self):
        """QCチェックを実行"""
        if not self.current_project or not self.current_project.subtitles:
            QMessageBox.information(
                self,
                "情報",
                "QCチェックする字幕がありません。\\n先に字幕を抽出してください。",
            )
            return

        try:
            # QCチェッカーでチェック実行
            qc_checker = QCChecker()
            qc_results = qc_checker.check_all(self.current_project.subtitles)

            # 結果のサマリー
            summary = qc_checker.get_summary(qc_results)

            # 結果表示
            self.show_qc_results(qc_results, summary)

            self.status_label.setText(f"QCチェック完了: {summary['total']}件の問題を検出")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"QCチェックでエラーが発生しました:\\n{str(e)}")

    def show_qc_results(self, qc_results, summary):
        """QC結果を表示"""
        if not qc_results:
            QMessageBox.information(
                self,
                "QCチェック結果",
                "品質チェックが完了しました。\\n問題は検出されませんでした。",
            )
            return

        # 結果の詳細メッセージを作成
        message = f"品質チェック結果:\\n"
        message += f"・エラー: {summary['error']}件\\n"
        message += f"・警告: {summary['warning']}件\\n"
        message += f"・情報: {summary['info']}件\\n\\n"

        # エラーと警告の詳細を表示（最大10件）
        error_warnings = [r for r in qc_results if r.severity in ["error", "warning"]]
        if error_warnings:
            message += "主な問題:\\n"
            for i, result in enumerate(error_warnings[:10]):
                message += f"{i+1}. 字幕{result.subtitle_index+1}: {result.message}\\n"

            if len(error_warnings) > 10:
                message += f"...他 {len(error_warnings)-10}件\\n"

        # メッセージボックスで表示
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("QCチェック結果")
        msg_box.setText(message)

        if summary["error"] > 0:
            msg_box.setIcon(QMessageBox.Icon.Critical)
        elif summary["warning"] > 0:
            msg_box.setIcon(QMessageBox.Icon.Warning)
        else:
            msg_box.setIcon(QMessageBox.Icon.Information)

        msg_box.exec()

    def save_project(self):
        """プロジェクトを保存"""
        if not self.current_project:
            QMessageBox.information(self, "保存エラー", "保存するプロジェクトがありません。")
            return

        try:
            project_manager = get_project_manager()
            current_project_data = project_manager.get_current_project()

            if current_project_data is None:
                # 新しいプロジェクトの場合は名前を付けて保存
                self.save_project_as()
                return

            # 現在の字幕データでプロジェクトを更新
            if hasattr(self.table_view, "model") and self.table_view.model():
                subtitles = self.table_view.model().get_all_subtitles()
                project_manager.update_subtitles(subtitles)

            # プロジェクトを保存
            if project_manager.save_project(current_project_data):
                file_path = project_manager.get_current_file_path()
                self.status_label.setText(
                    f"プロジェクトを保存しました: {file_path.name if file_path else 'project.subproj'}"
                )
                self.project_saved.emit(str(file_path) if file_path else "project.subproj")
            else:
                QMessageBox.warning(
                    self,
                    "保存エラー",
                    "プロジェクトの保存に失敗しました。\nディスクの容量やアクセス権限を確認してください。",
                )

        except Exception as e:
            logging.error(f"プロジェクト保存エラー: {e}")
            QMessageBox.critical(
                self, "エラー", f"プロジェクト保存中にエラーが発生しました:\n{str(e)}"
            )

    def save_project_as(self):
        """名前を付けてプロジェクトを保存"""
        if not self.current_project:
            QMessageBox.information(self, "保存エラー", "保存するプロジェクトがありません。")
            return

        # デフォルトの保存先を設定マネージャーから取得
        settings_manager = get_settings_manager()
        settings = settings_manager.load_settings()
        default_dir = settings.output.output_folder or str(Path.home())

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "プロジェクトを保存",
            str(Path(default_dir) / "project.subproj"),
            "字幕プロジェクト (*.subproj);;すべてのファイル (*)",
        )

        if file_path:
            try:
                project_manager = get_project_manager()

                # 新しいプロジェクトデータを作成または既存データを取得
                current_project_data = project_manager.get_current_project()
                if current_project_data is None:
                    # 新しいプロジェクトを作成
                    project_name = Path(file_path).stem
                    video_path = getattr(self, "current_video_path", "") or ""
                    current_project_data = project_manager.create_new_project(
                        project_name, video_path
                    )

                # 現在の字幕データでプロジェクトを更新
                if hasattr(self.table_view, "model") and self.table_view.model():
                    subtitles = self.table_view.model().get_all_subtitles()
                    project_manager.update_subtitles(subtitles)

                # プロジェクトを指定されたパスに保存
                if project_manager.save_as_project(current_project_data, Path(file_path)):
                    self.status_label.setText(f"プロジェクトを保存しました: {Path(file_path).name}")
                    self.project_saved.emit(file_path)

                    # 最近使用したファイルに追加
                    settings_manager.add_recent_file(file_path)
                else:
                    QMessageBox.warning(
                        self,
                        "保存エラー",
                        "プロジェクトの保存に失敗しました。\nディスクの容量やアクセス権限を確認してください。",
                    )

            except Exception as e:
                logging.error(f"名前を付けて保存エラー: {e}")
                QMessageBox.critical(
                    self,
                    "エラー",
                    f"プロジェクト保存中にエラーが発生しました:\n{str(e)}",
                )

    def show_settings(self):
        """設定画面を表示"""
        settings_dialog = SettingsView(self)
        settings_dialog.exec()

    def show_about(self):
        """アプリについて画面を表示"""
        QMessageBox.about(
            self,
            "VLog字幕ツールについて",
            "VLog字幕ツール v1.0\\n\\n"
            "VLOG動画から字幕を自動抽出し、編集・翻訳・出力を行うアプリケーションです。\\n\\n"
            "技術スタック: Python + PySide6 + OpenCV + PaddleOCR",
        )

    def export_japanese_srt(self):
        """日本語SRTファイルを出力"""
        if not self.current_project or not self.current_project.subtitles:
            QMessageBox.information(
                self,
                "情報",
                "出力する字幕がありません。\\n先に字幕を抽出してください。",
            )
            return

        # 保存先の選択
        if self.current_video_path:
            video_path = Path(self.current_video_path)
            default_filename = f"{video_path.stem}.ja.srt"
        else:
            default_filename = "subtitles.ja.srt"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "日本語SRTファイルを保存",
            default_filename,
            "SRTファイル (*.srt);;すべてのファイル (*)",
        )

        if not file_path:
            return

        try:
            # SRT フォーマッタを作成
            settings = SRTFormatSettings(
                encoding="utf-8",
                with_bom=False,
                line_ending="lf",
                max_chars_per_line=42,
                max_lines=2,
            )
            formatter = SRTFormatter(settings)

            # SRTファイルを保存
            success = formatter.save_srt_file(self.current_project.subtitles, Path(file_path))

            if success:
                QMessageBox.information(
                    self, "保存完了", f"日本語SRTファイルを保存しました:\\n{file_path}"
                )
                self.status_label.setText(f"SRTファイルを保存: {Path(file_path).name}")
            else:
                QMessageBox.critical(self, "保存エラー", "SRTファイルの保存に失敗しました。")

        except Exception as e:
            QMessageBox.critical(
                self, "エラー", f"SRTファイルの保存でエラーが発生しました:\\n{str(e)}"
            )

    def export_all_srt(self):
        """全言語のSRTファイルを出力（現在は日本語のみ）"""
        # 将来的に多言語対応する際のプレースホルダー
        self.export_japanese_srt()

    def show_multilang_export_dialog(self):
        """多言語SRTエクスポートダイアログを表示"""
        if not self.current_project or not self.current_project.subtitles:
            QMessageBox.information(
                self, "情報", "出力する字幕がありません。\n先に字幕を抽出してください。"
            )
            return

        # デフォルトの出力先を決定
        default_output_dir = None
        if self.current_video_path:
            default_output_dir = Path(self.current_video_path).parent
        elif self.current_project and self.current_project.source_video:
            default_output_dir = Path(self.current_project.source_video).parent
        else:
            default_output_dir = Path.cwd()

        # ダイアログを表示
        result = MultiLanguageExportDialog.get_export_settings(default_output_dir, self)

        if result:
            selected_languages, output_dir = result
            self.export_multilang_srt(selected_languages, Path(output_dir))

    def export_multilang_srt(self, selected_languages: list, output_dir: Path):
        """複数言語のSRTファイルをエクスポート"""
        try:
            # ベースファイル名を決定
            if self.current_video_path:
                video_path = Path(self.current_video_path)
                base_filename = video_path.stem
            elif self.current_project and self.current_project.source_video:
                video_path = Path(self.current_project.source_video)
                base_filename = video_path.stem
            else:
                base_filename = "subtitles"

            base_filepath = output_dir / base_filename

            # MultiLanguageSRTManagerを作成
            srt_manager = MultiLanguageSRTManager(base_filepath)

            # 各言語のフォーマッタを設定
            for lang_code in selected_languages:
                settings = self._get_srt_format_settings()
                srt_manager.add_language(lang_code, settings)

            # 字幕データを準備
            multilang_subtitles = {}

            # 日本語は常に含める
            multilang_subtitles["ja"] = self.current_project.subtitles

            # 他の言語を翻訳
            other_languages = [lang for lang in selected_languages if lang != "ja"]

            if other_languages:
                try:
                    # 翻訳プロバイダーの初期化
                    translation_results = self._translate_to_languages(
                        self.current_project.subtitles, other_languages
                    )
                    multilang_subtitles.update(translation_results)
                except Exception as translation_error:
                    # 翻訳エラーが発生した場合の処理
                    QMessageBox.warning(
                        self,
                        "翻訳エラー",
                        f"翻訳処理でエラーが発生しました：\n{str(translation_error)}\n\n"
                        "日本語のみ出力します。",
                    )
                    # 日本語のみに制限
                    selected_languages = ["ja"]

            # SRTファイルを保存
            results = srt_manager.save_multilang_srt(multilang_subtitles)

            # 結果の表示
            success_count = sum(1 for success in results.values() if success)
            total_count = len(results)

            if success_count == total_count:
                # すべて成功
                saved_files = srt_manager.get_saved_files()
                file_list = "\n".join(f"- {f.name}" for f in saved_files)
                message = (
                    f"{success_count}個の言語のSRTファイルを出力しました：\n\n"
                    f"{file_list}\n\n"
                    f"出力先: {output_dir}"
                )
                QMessageBox.information(self, "エクスポート完了", message)
                self.status_label.setText(f"多言語SRT出力完了: {success_count}ファイル")
            else:
                # 一部失敗
                success_langs = [lang for lang, success in results.items() if success]
                failed_langs = [lang for lang, success in results.items() if not success]

                message = f"エクスポート結果:\n\n"
                message += f"成功: {len(success_langs)}ファイル ({', '.join(success_langs)})\n"
                message += f"失敗: {len(failed_langs)}ファイル ({', '.join(failed_langs)})\n\n"
                message += f"出力先: {output_dir}"

                if success_count > 0:
                    QMessageBox.warning(self, "エクスポート部分完了", message)
                else:
                    QMessageBox.critical(self, "エクスポート失敗", message)

                self.status_label.setText(f"多言語SRT出力: {success_count}/{total_count}成功")

        except Exception as e:
            QMessageBox.critical(
                self,
                "エラー",
                f"多言語SRTエクスポートでエラーが発生しました：\n{str(e)}",
            )

    def _translate_to_languages(
        self, subtitles: List[SubtitleItem], target_languages: List[str]
    ) -> Dict[str, List[SubtitleItem]]:
        """字幕を複数言語に翻訳"""
        translation_results = {}

        try:
            # ローカル翻訳プロバイダーの初期化
            models_dir = Path.cwd() / "app" / "models" / "translation"
            models_dir.mkdir(parents=True, exist_ok=True)

            settings = LocalTranslateSettings(
                models_dir=str(models_dir),
                max_batch_size=16,
                beam_size=1,
                length_penalty=0.2,
                repetition_penalty=1.5,
                max_decoding_length=50,
            )

            router = TranslationProviderRouter()
            router.register_provider(TranslationProviderType.LOCAL, settings)

            # 字幕テキストを抽出
            subtitle_texts = [subtitle.text for subtitle in subtitles]

            # 各言語に翻訳
            for target_lang in target_languages:
                try:
                    self.status_label.setText(f"翻訳中: 日本語 → {target_lang}...")

                    # 翻訳実行
                    translation_result = router.translate_batch(
                        subtitle_texts,
                        target_language=target_lang,
                        source_language="ja",  # 日本語から翻訳
                        provider_type=TranslationProviderType.LOCAL,
                    )

                    if translation_result.success:
                        # 翻訳された字幕アイテムを作成
                        translated_subtitles = []
                        for i, (original_subtitle, translated_text) in enumerate(
                            zip(subtitles, translation_result.translated_texts)
                        ):
                            translated_subtitle = SubtitleItem(
                                index=original_subtitle.index,
                                start_ms=original_subtitle.start_ms,
                                end_ms=original_subtitle.end_ms,
                                text=translated_text,
                                bbox=original_subtitle.bbox,
                            )
                            translated_subtitles.append(translated_subtitle)

                        translation_results[target_lang] = translated_subtitles
                        logging.info(f"翻訳完了: {target_lang} ({len(translated_subtitles)}件)")

                    else:
                        # 翻訳失敗の場合は元のテキストにプレフィックス付きで使用
                        logging.warning(
                            f"翻訳失敗: {target_lang} - {translation_result.error_message}"
                        )
                        fallback_subtitles = []
                        for subtitle in subtitles:
                            fallback_text = f"[{target_lang.upper()}] {subtitle.text}"
                            fallback_subtitle = SubtitleItem(
                                index=subtitle.index,
                                start_ms=subtitle.start_ms,
                                end_ms=subtitle.end_ms,
                                text=fallback_text,
                                bbox=subtitle.bbox,
                            )
                            fallback_subtitles.append(fallback_subtitle)
                        translation_results[target_lang] = fallback_subtitles

                except Exception as lang_error:
                    logging.error(f"言語 {target_lang} の翻訳でエラー: {lang_error}")
                    # エラー時のフォールバック
                    fallback_subtitles = []
                    for subtitle in subtitles:
                        fallback_text = f"[ERROR:{target_lang.upper()}] {subtitle.text}"
                        fallback_subtitle = SubtitleItem(
                            index=subtitle.index,
                            start_ms=subtitle.start_ms,
                            end_ms=subtitle.end_ms,
                            text=fallback_text,
                            bbox=subtitle.bbox,
                        )
                        fallback_subtitles.append(fallback_subtitle)
                    translation_results[target_lang] = fallback_subtitles

            self.status_label.setText("翻訳処理完了")
            return translation_results

        except Exception as e:
            logging.error(f"翻訳処理でエラー: {e}")
            raise Exception(f"翻訳プロバイダーの初期化に失敗しました: {str(e)}")

    def _get_srt_format_settings(self) -> SRTFormatSettings:
        """SRT出力設定を取得"""
        # 設定画面からの設定取得を試行
        try:
            # 設定ビューの作成とデフォルト値の取得
            settings_view = SettingsView()
            return settings_view.get_srt_format_settings()
        except Exception:
            # フォールバック: デフォルト値を使用
            return SRTFormatSettings(
                encoding="utf-8",
                with_bom=False,
                line_ending="lf",
                max_chars_per_line=42,
                max_lines=2,
            )

    def export_original_csv(self):
        """元データのCSVをエクスポート"""
        if not self.table_view.subtitles:
            QMessageBox.warning(self, "警告", "エクスポートする字幕データがありません")
            return

        if self.current_project and self.current_project.source_video:
            video_path = Path(self.current_project.source_video)
        elif self.current_video_path:
            video_path = Path(self.current_video_path)
        else:
            video_path = Path.cwd() / "subtitles.mp4"

        default_dir = video_path.parent if video_path.parent.exists() else Path.cwd()
        default_name = f"{video_path.stem}_source.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "元データCSVの保存先を選択",
            str(default_dir / default_name),
            "CSVファイル (*.csv);;すべてのファイル (*)",
        )

        if not file_path:
            return

        try:
            exporter = SubtitleCSVExporter()
            success = exporter.export_standard(self.table_view.subtitles, Path(file_path))

            if success:
                QMessageBox.information(self, "保存完了", f"元データCSVを保存しました\n{file_path}")
                self.status_label.setText(f"CSVを出力: {Path(file_path).name}")
            else:
                QMessageBox.critical(self, "エラー", "CSVエクスポートに失敗しました。")
        except Exception as e:
            logging.exception("CSVエクスポートでエラーが発生しました")
            QMessageBox.critical(self, "エラー", f"CSVエクスポートに失敗しました\n{str(e)}")

    def show_translate_view(self):
        """翻訳設定画面を表示"""
        if not self.table_view.subtitles:
            QMessageBox.warning(
                self, "警告", "字幕データがありません\\n先に字幕抽出を行ってください"
            )
            return

        translate_dialog = TranslateView(self)
        translate_dialog.set_subtitles(self.table_view.subtitles, self.current_project)
        translate_dialog.translations_updated.connect(self.on_translations_updated)
        translate_dialog.exec()

    def export_translation_csv(self):
        """翻訳用CSVエクスポート"""
        if not self.table_view.subtitles:
            QMessageBox.warning(self, "警告", "字幕データがありません")
            return

        # 翻訳設定画面を開く
        self.show_translate_view()

    def import_translation_csv(self):
        """翻訳済みCSVインポート"""
        if not self.table_view.subtitles:
            QMessageBox.warning(self, "警告", "元の字幕データがありません")
            return

        # 翻訳設定画面を開く
        self.show_translate_view()

    def on_translations_updated(self, translations_dict):
        """翻訳データ更新時の処理"""
        # 現在のプロジェクトに翻訳データを保存
        if self.current_project:
            # プロジェクトデータに翻訳情報を追加（将来の拡張用）
            pass

        self.status_label.setText(f"翻訳データ更新: {len(translations_dict)}言語")

    def get_srt_export_settings(self) -> SRTFormatSettings:
        """SRT出力設定を取得（設定画面から）"""
        try:
            settings_manager = get_settings_manager()
            settings = settings_manager.load_settings()

            # エンコーディング設定
            encoding = "utf-8"
            with_bom = settings.output.srt_bom

            if settings.output.encoding == "UTF-8 BOM":
                encoding = "utf-8"
                with_bom = True
            elif settings.output.encoding == "Shift_JIS":
                encoding = "shift_jis"
            elif settings.output.encoding == "CP932":
                encoding = "cp932"

            return SRTFormatSettings(
                encoding=encoding,
                with_bom=with_bom,
                line_ending="crlf" if settings.output.srt_crlf else "lf",
                max_chars_per_line=settings.formatting.max_chars,
                max_lines=settings.formatting.max_lines,
            )

        except Exception as e:
            logging.error(f"SRT設定取得エラー: {e}")
            # エラー時はデフォルト設定を返す
            return SRTFormatSettings(
                encoding="utf-8",
                with_bom=False,
                line_ending="lf",
                max_chars_per_line=42,
                max_lines=2,
            )

    def update_status(self):
        """ステータスの定期更新"""
        pass

    def on_subtitle_changed(self, row: int, subtitle_item: SubtitleItem):
        """字幕変更時の処理"""
        if self.current_project and 0 <= row < len(self.current_project.subtitles):
            # プロジェクトの字幕を更新
            self.current_project.subtitles[row] = subtitle_item

            # プレイヤーの字幕リストも更新
            self.player_view.set_subtitles(self.current_project.subtitles)

    def on_subtitles_reordered(self):
        """字幕順序変更時の処理"""
        if self.current_project:
            # テーブルから最新の字幕リストを取得
            self.current_project.subtitles = self.table_view.subtitles[:]

            # プレイヤーの字幕リストも更新
            self.player_view.set_subtitles(self.current_project.subtitles)

    def dragEnterEvent(self, event):
        """ドラッグ開始イベント（強化版）"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                file_ext = Path(file_path).suffix.lower()

                # 動画ファイルかプロジェクトファイルの場合のみ受け入れ
                video_formats = [
                    ".mp4",
                    ".mov",
                    ".avi",
                    ".mkv",
                    ".flv",
                    ".wmv",
                    ".webm",
                ]
                project_formats = [".subproj"]

                if file_ext in video_formats + project_formats:
                    event.acceptProposedAction()
                    self.status_label.setText(f"ドロップして {file_ext} ファイルを開く")

    def dropEvent(self, event):
        """ドロップイベント（強化版）"""
        urls = event.mimeData().urls()
        if not urls:
            return

        file_path = urls[0].toLocalFile()
        file_ext = Path(file_path).suffix.lower()

        try:
            if file_ext == ".subproj":
                # プロジェクトファイルの読み込み
                self.load_project(file_path)
            else:
                # 動画ファイルの読み込み
                self.load_video(file_path)

        except Exception as e:
            QMessageBox.critical(
                self,
                "ドラッグ&ドロップエラー",
                f"ファイルの読み込みに失敗しました:\n{str(e)}",
            )
        finally:
            self.status_label.setText("準備完了")

    def load_project(self, file_path: str):
        """プロジェクトファイルを読み込む"""
        try:
            project_manager = get_project_manager()
            settings_manager = get_settings_manager()

            # 現在の状態を保存（ロールバック用）
            previous_project = project_manager.current_project
            previous_file_path = project_manager.current_file_path

            # プロジェクトファイルを読み込み
            project_data = project_manager.load_project(Path(file_path))

            # プロジェクトデータの妥当性を確認
            errors = project_manager.validate_project_data(project_data)
            if errors:
                # エラーがある場合は警告表示（続行可能）
                error_msg = "プロジェクトファイルに以下の問題があります:\n\n" + "\n".join(
                    f"• {error}" for error in errors
                )
                error_msg += "\n\n続行しますか？"

                reply = QMessageBox.question(
                    self,
                    "プロジェクト読み込み警告",
                    error_msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )

                if reply == QMessageBox.StandardButton.No:
                    # ユーザーがキャンセルした場合、ProjectManagerの状態をロールバック
                    project_manager.current_project = previous_project
                    project_manager.current_file_path = previous_file_path
                    return

            # 動画ファイルの確認
            if project_data.video_file_path:
                video_path = Path(project_data.video_file_path)
                if video_path.exists():
                    # 動画をロード
                    self.current_video_path = str(video_path)
                    self.player_view.load_video(str(video_path))
                else:
                    # 動画ファイルが見つからない場合、新しいパスを選択
                    reply = QMessageBox.question(
                        self,
                        "動画ファイルが見つかりません",
                        f"動画ファイルが見つかりません:\n{video_path}\n\n新しい場所を指定しますか？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes,
                    )

                    if reply == QMessageBox.StandardButton.Yes:
                        new_video_path, _ = QFileDialog.getOpenFileName(
                            self,
                            "動画ファイルを選択",
                            str(video_path.parent),
                            "動画ファイル (*.mp4 *.avi *.mov *.mkv);;すべてのファイル (*)",
                        )

                        if new_video_path:
                            project_data.video_file_path = new_video_path
                            self.current_video_path = new_video_path
                            self.player_view.load_video(new_video_path)

            # 字幕データをテーブルに設定
            subtitle_items = project_data.get_subtitle_items()
            if subtitle_items and hasattr(self.table_view, "model") and self.table_view.model():
                self.table_view.model().set_subtitles(subtitle_items)

            # 翻訳データを設定
            for language, translated_items in project_data.translations.items():
                if translated_items:
                    translated_subtitles = project_data.get_translated_subtitles(language)
                    if translated_subtitles:
                        # 翻訳ビューに設定（メソッドが存在する場合のみ）
                        if hasattr(self, "translate_view") and hasattr(
                            self.translate_view, "set_translations"
                        ):
                            self.translate_view.set_translations(language, translated_subtitles)
                        else:
                            # 代替手段: 翻訳データをプロジェクトに保持するだけ
                            logging.info(
                                f"翻訳データを読み込み: {language} ({len(translated_subtitles)}件)"
                            )

            # プロジェクト情報を更新
            from app.core.models import ProjectSettings

            self.current_project = Project(
                source_video=project_data.video_file_path,
                settings=ProjectSettings(),
                subtitles=subtitle_items,
            )

            # 最近使用したファイルに追加
            settings_manager.add_recent_file(file_path)

            # ステータス更新
            self.status_label.setText(f"プロジェクト読み込み完了: {project_data.metadata.name}")
            self.setWindowTitle(f"VLog字幕ツール - {project_data.metadata.name}")

            message = (
                f"プロジェクト '{project_data.metadata.name}' を読み込みました。\n"
                f"字幕数: {len(subtitle_items)}\n"
                f"翻訳言語数: {len(project_data.translations)}"
            )
            QMessageBox.information(self, "プロジェクト読み込み完了", message)

        except FileNotFoundError:
            # エラー時もProjectManagerの状態をロールバック
            try:
                project_manager.current_project = previous_project
                project_manager.current_file_path = previous_file_path
            except:
                pass
            QMessageBox.critical(
                self, "エラー", f"プロジェクトファイルが見つかりません:\n{file_path}"
            )
        except ValueError as e:
            # エラー時もProjectManagerの状態をロールバック
            try:
                project_manager.current_project = previous_project
                project_manager.current_file_path = previous_file_path
            except:
                pass
            QMessageBox.critical(
                self,
                "形式エラー",
                f"プロジェクトファイルの形式が正しくありません:\n{str(e)}",
            )
        except Exception as e:
            # エラー時もProjectManagerの状態をロールバック
            try:
                project_manager.current_project = previous_project
                project_manager.current_file_path = previous_file_path
            except:
                pass
            logging.error(f"プロジェクト読み込みエラー: {e}")
            QMessageBox.critical(
                self,
                "エラー",
                f"プロジェクト読み込み中にエラーが発生しました:\n{str(e)}",
            )


def main():
    """メイン関数"""
    try:
        import logging

        # ロギング設定
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Qt のメッセージハンドラ設定
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        def qt_message_handler(mode, context, message):
            if mode == QtMsgType.QtCriticalMsg or mode == QtMsgType.QtFatalMsg:
                logging.error(f"Qt Error: {message}")
            elif mode == QtMsgType.QtWarningMsg:
                logging.warning(f"Qt Warning: {message}")
            else:
                logging.info(f"Qt Info: {message}")

        qInstallMessageHandler(qt_message_handler)

        app = QApplication(sys.argv)

        # 日本語対応設定
        setup_japanese_support(app)

        # アプリケーションの設定
        app.setApplicationName("VLog字幕ツール")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("VLogTools")

        # 依存関係の確認
        try:
            import cv2

            logging.info(f"OpenCV version: {cv2.__version__}")
        except ImportError as e:
            logging.error(f"OpenCV import failed: {e}")

        try:
            import paddleocr

            logging.info("PaddleOCR imported successfully")
        except ImportError as e:
            logging.error(f"PaddleOCR import failed: {e}")

        # メインウィンドウの作成と表示
        window = MainWindow()
        window.show()

        # アプリケーションの実行
        sys.exit(app.exec())

    except Exception as e:
        # 致命的エラーの処理
        import traceback

        error_msg = f"アプリケーション起動エラー: {str(e)}\n\n{traceback.format_exc()}"

        try:
            # Qt が使用可能な場合はメッセージボックスで表示
            if "app" in locals():
                QMessageBox.critical(None, "起動エラー", error_msg)
            else:
                print(error_msg, file=sys.stderr)
        except:
            # 最終手段として標準エラー出力に表示
            print(error_msg, file=sys.stderr)

        sys.exit(1)
