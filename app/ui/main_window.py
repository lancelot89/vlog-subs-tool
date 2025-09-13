"""
メインウィンドウの実装
DESIGN.mdの画面仕様に基づくGUIレイアウト
"""

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QMenuBar, QToolBar, QStatusBar, QSplitter, QPushButton,
    QFileDialog, QMessageBox, QProgressBar, QLabel
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction, QIcon

from .views.player_view import PlayerView
from .views.table_view import SubtitleTableView
from .views.translate_view import TranslateView
from .views.settings_view import SettingsView
from .extraction_worker import ExtractionWorker
from ..core.models import Project, SubtitleItem
from ..core.format.srt import SRTFormatter, SRTFormatSettings
from ..core.qc.rules import QCChecker


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
        
        file_menu.addSeparator()
        
        exit_action = QAction("終了(&X)", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 編集メニュー
        edit_menu = menubar.addMenu("編集(&E)")
        
        # 表示メニュー
        view_menu = menubar.addMenu("表示(&V)")
        
        # 翻訳メニュー
        translate_menu = menubar.addMenu("翻訳(&T)")
        
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
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        
        # 動画を開く
        open_btn = QPushButton("動画を開く")
        open_btn.clicked.connect(self.open_video)
        toolbar.addWidget(open_btn)
        
        toolbar.addSeparator()
        
        # 自動抽出
        self.extract_btn = QPushButton("自動抽出")
        self.extract_btn.clicked.connect(self.start_extraction)
        self.extract_btn.setEnabled(False)
        toolbar.addWidget(self.extract_btn)
        
        # 再抽出
        self.re_extract_btn = QPushButton("再抽出")
        self.re_extract_btn.clicked.connect(self.re_extract)
        self.re_extract_btn.setEnabled(False)
        toolbar.addWidget(self.re_extract_btn)
        
        toolbar.addSeparator()
        
        # QCチェック
        self.qc_btn = QPushButton("QCチェック")
        self.qc_btn.clicked.connect(self.run_qc_check)
        self.qc_btn.setEnabled(False)
        toolbar.addWidget(self.qc_btn)
        
        toolbar.addSeparator()
        
        # 保存
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_project)
        self.save_btn.setEnabled(False)
        toolbar.addWidget(self.save_btn)
        
        # SRT出力
        self.export_srt_btn = QPushButton("SRT出力")
        self.export_srt_btn.clicked.connect(self.export_japanese_srt)
        self.export_srt_btn.setEnabled(False)
        toolbar.addWidget(self.export_srt_btn)
    
    def create_central_widget(self):
        """中央ウィジェットの作成"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # メインレイアウト
        main_layout = QHBoxLayout(central_widget)
        
        # スプリッター
        splitter = QSplitter(Qt.Horizontal)
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
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
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
    
    def open_video(self):
        """動画ファイルを開く"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "動画ファイルを選択",
            "",
            "動画ファイル (*.mp4 *.mov *.avi *.mkv);;すべてのファイル (*)"
        )
        
        if file_path:
            self.load_video(file_path)
    
    def load_video(self, file_path: str):
        """動画を読み込む"""
        try:
            self.current_video_path = file_path
            
            # プレイヤーに動画を読み込み
            self.player_view.load_video(file_path)
            
            # プロジェクトを作成
            self.current_project = Project.create_new(file_path)
            
            # UIの更新
            self.extract_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
            
            # ファイル情報の更新
            file_name = Path(file_path).name
            self.file_info_label.setText(f"動画: {file_name}")
            
            self.video_loaded.emit(file_path)
            self.status_label.setText("動画を読み込みました")
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"動画の読み込みに失敗しました: {str(e)}")
    
    def on_video_loaded(self, file_path: str):
        """動画読み込み完了時の処理"""
        self.setWindowTitle(f"VLog字幕ツール v1.0 - {Path(file_path).name}")
    
    def start_extraction(self):
        """字幕抽出を開始"""
        if not self.current_project or not self.current_video_path:
            return
        
        # 既存の抽出処理をキャンセル
        if self.extraction_worker and self.extraction_worker.isRunning():
            self.extraction_worker.cancel()
            self.extraction_worker.wait()
        
        # UI状態の更新
        self.extraction_started.emit()
        self.status_label.setText("字幕抽出を開始しています...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.extract_btn.setEnabled(False)
        self.re_extract_btn.setEnabled(False)
        
        # 抽出ワーカーの作成と開始
        self.extraction_worker = ExtractionWorker(
            self.current_video_path,
            self.current_project.settings
        )
        
        # ワーカーシグナルの接続
        self.extraction_worker.progress_updated.connect(self.on_extraction_progress)
        self.extraction_worker.subtitles_extracted.connect(self.on_extraction_completed)
        self.extraction_worker.error_occurred.connect(self.on_extraction_error)
        self.extraction_worker.finished.connect(self.on_extraction_finished)
        
        # 抽出開始
        self.extraction_worker.start()
    
    def on_extraction_progress(self, percentage: int, message: str):
        """抽出プログレス更新"""
        self.progress_bar.setValue(percentage)
        self.status_label.setText(message)
    
    def on_extraction_completed(self, subtitle_items: List[SubtitleItem]):
        """抽出完了処理"""
        # プロジェクトに字幕を設定
        self.current_project.subtitles = subtitle_items
        
        # テーブルビューに字幕を表示
        self.table_view.set_subtitles(subtitle_items)
        
        # プレイヤービューにも字幕を設定
        self.player_view.set_subtitles(subtitle_items)
        
        # UI状態の更新
        self.extract_btn.setEnabled(True)
        self.re_extract_btn.setEnabled(True)
        self.qc_btn.setEnabled(True)
        self.export_srt_btn.setEnabled(True)
        
        self.status_label.setText(f"字幕の抽出が完了しました ({len(subtitle_items)}件)")
        self.extraction_completed.emit()
    
    def on_extraction_error(self, error_message: str):
        """抽出エラー処理"""
        QMessageBox.critical(self, "抽出エラー", f"字幕の抽出に失敗しました:\\n{error_message}")
        
        # UI状態をリセット
        self.extract_btn.setEnabled(True)
        self.status_label.setText("字幕の抽出に失敗しました")
    
    def on_extraction_finished(self):
        """抽出処理終了時の共通処理"""
        self.progress_bar.setVisible(False)
        
        # ワーカーのクリーンアップ
        if self.extraction_worker:
            self.extraction_worker.cleanup()
            self.extraction_worker = None
    
    def re_extract(self):
        """再抽出"""
        self.start_extraction()
    
    def run_qc_check(self):
        """QCチェックを実行"""
        if not self.current_project or not self.current_project.subtitles:
            QMessageBox.information(self, "情報", "QCチェックする字幕がありません。\\n先に字幕を抽出してください。")
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
                "品質チェックが完了しました。\\n問題は検出されませんでした。"
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
        
        if summary['error'] > 0:
            msg_box.setIcon(QMessageBox.Critical)
        elif summary['warning'] > 0:
            msg_box.setIcon(QMessageBox.Warning)
        else:
            msg_box.setIcon(QMessageBox.Information)
        
        msg_box.exec()
    
    def save_project(self):
        """プロジェクトを保存"""
        if not self.current_project:
            return
        
        # TODO: プロジェクト保存処理の実装
        self.status_label.setText("プロジェクトを保存しました")
        self.project_saved.emit("project.subproj")
    
    def save_project_as(self):
        """名前を付けてプロジェクトを保存"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "プロジェクトを保存",
            "",
            "字幕プロジェクト (*.subproj);;すべてのファイル (*)"
        )
        
        if file_path and self.current_project:
            # TODO: プロジェクト保存処理の実装
            self.status_label.setText(f"プロジェクトを保存しました: {file_path}")
            self.project_saved.emit(file_path)
    
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
            "技術スタック: Python + PySide6 + OpenCV + PaddleOCR"
        )
    
    def export_japanese_srt(self):
        """日本語SRTファイルを出力"""
        if not self.current_project or not self.current_project.subtitles:
            QMessageBox.information(self, "情報", "出力する字幕がありません。\\n先に字幕を抽出してください。")
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
            "SRTファイル (*.srt);;すべてのファイル (*)"
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
                max_lines=2
            )
            formatter = SRTFormatter(settings)
            
            # SRTファイルを保存
            success = formatter.save_srt_file(self.current_project.subtitles, Path(file_path))
            
            if success:
                QMessageBox.information(
                    self, 
                    "保存完了", 
                    f"日本語SRTファイルを保存しました:\\n{file_path}"
                )
                self.status_label.setText(f"SRTファイルを保存: {Path(file_path).name}")
            else:
                QMessageBox.critical(self, "保存エラー", "SRTファイルの保存に失敗しました。")
        
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"SRTファイルの保存でエラーが発生しました:\\n{str(e)}")
    
    def export_all_srt(self):
        """全言語のSRTファイルを出力（現在は日本語のみ）"""
        # 将来的に多言語対応する際のプレースホルダー
        self.export_japanese_srt()
    
    def get_srt_export_settings(self) -> SRTFormatSettings:
        """SRT出力設定を取得（設定画面から）"""
        # TODO: 設定画面から取得する実装
        return SRTFormatSettings(
            encoding="utf-8",
            with_bom=False,
            line_ending="lf",
            max_chars_per_line=42,
            max_lines=2
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
        """ドラッグ開始イベント"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """ドロップイベント"""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if Path(file_path).suffix.lower() in ['.mp4', '.mov', '.avi', '.mkv']:
                self.load_video(file_path)


def main():
    """メイン関数"""
    app = QApplication(sys.argv)
    
    # アプリケーションの設定
    app.setApplicationName("VLog字幕ツール")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("VLogTools")
    
    # メインウィンドウの作成と表示
    window = MainWindow()
    window.show()
    
    # アプリケーションの実行
    sys.exit(app.exec())