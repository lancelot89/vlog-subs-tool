"""
多言語SRTエクスポートダイアログの実装
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QGroupBox, QScrollArea, QWidget, QLineEdit,
    QFileDialog, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from pathlib import Path
from typing import Dict, List, Optional, Set


class MultiLanguageExportDialog(QDialog):
    """多言語SRTエクスポートダイアログ"""

    # 対応言語の定義（翻訳プロバイダーで実際にサポートされる言語）
    SUPPORTED_LANGUAGES = {
        'ja': '日本語',
        'en': 'English',
        'zh-cn': '中文（简体）',
        'zh-tw': '中文（繁體）',
        'ar': 'العربية',
        'ko': '한국어',
        'es': 'Español',
        'fr': 'Français',
        'de': 'Deutsch',
        'it': 'Italiano',
        'pt': 'Português',
        'ru': 'Русский',
        'th': 'ไทย',
        'vi': 'Tiếng Việt'
    }

    # エクスポート実行のシグナル（選択された言語リストと出力先パスを送信）
    export_requested = Signal(list, str)

    def __init__(self, default_output_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.default_output_dir = default_output_dir or Path.cwd()
        self.language_checkboxes: Dict[str, QCheckBox] = {}

        self.setWindowTitle("多言語SRT出力")
        self.setModal(True)
        self.resize(500, 600)

        self.init_ui()
        self.load_default_settings()

    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)

        # 説明ラベル
        description = QLabel(
            "エクスポートする言語を選択してください。\n"
            "選択された言語に翻訳したSRTファイルが生成されます。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # 言語選択エリア
        self.create_language_selection_area(layout)

        # 出力先設定
        self.create_output_settings_area(layout)

        # ボタンエリア
        self.create_button_area(layout)

    def create_language_selection_area(self, parent_layout):
        """言語選択エリアの作成"""
        group_box = QGroupBox("翻訳言語の選択")
        parent_layout.addWidget(group_box)

        # スクロール可能なエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # 全選択/全解除ボタン
        control_layout = QHBoxLayout()

        select_all_btn = QPushButton("全選択")
        select_all_btn.clicked.connect(self.select_all_languages)
        control_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("全解除")
        deselect_all_btn.clicked.connect(self.deselect_all_languages)
        control_layout.addWidget(deselect_all_btn)

        control_layout.addStretch()
        scroll_layout.addLayout(control_layout)

        # 言語チェックボックス
        for lang_code, lang_name in self.SUPPORTED_LANGUAGES.items():
            checkbox = QCheckBox(f"{lang_name} ({lang_code})")
            self.language_checkboxes[lang_code] = checkbox
            scroll_layout.addWidget(checkbox)

        scroll_area.setWidget(scroll_widget)

        group_layout = QVBoxLayout(group_box)
        group_layout.addWidget(scroll_area)

    def create_output_settings_area(self, parent_layout):
        """出力先設定エリアの作成"""
        group_box = QGroupBox("出力設定")
        parent_layout.addWidget(group_box)

        form_layout = QFormLayout(group_box)

        # 出力先ディレクトリ選択
        output_layout = QHBoxLayout()

        self.output_dir_edit = QLineEdit(str(self.default_output_dir))
        output_layout.addWidget(self.output_dir_edit)

        browse_btn = QPushButton("参照...")
        browse_btn.clicked.connect(self.browse_output_directory)
        output_layout.addWidget(browse_btn)

        form_layout.addRow("出力先ディレクトリ:", output_layout)

        # ファイル名パターンの説明
        pattern_label = QLabel(
            "ファイル名形式: {ベース名}.{言語コード}.srt\n"
            "例: video.ja.srt, video.en.srt"
        )
        pattern_label.setStyleSheet("QLabel { color: #666; font-size: 10pt; }")
        form_layout.addRow("", pattern_label)

    def create_button_area(self, parent_layout):
        """ボタンエリアの作成"""
        button_layout = QHBoxLayout()

        # キャンセルボタン
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        button_layout.addStretch()

        # エクスポートボタン
        self.export_btn = QPushButton("エクスポート")
        self.export_btn.clicked.connect(self.handle_export)
        self.export_btn.setDefault(True)
        button_layout.addWidget(self.export_btn)

        parent_layout.addLayout(button_layout)

    def load_default_settings(self):
        """デフォルト設定の読み込み"""
        # 設定画面からデフォルト言語を取得を試行
        try:
            from app.ui.views.settings_view import SettingsView
            settings_view = SettingsView()
            default_languages = settings_view.get_default_languages()
        except Exception:
            # フォールバック: デフォルト言語を設定
            default_languages = ['ja', 'en']

        # デフォルト言語を選択
        for lang_code in default_languages:
            if lang_code in self.language_checkboxes:
                self.language_checkboxes[lang_code].setChecked(True)

    def select_all_languages(self):
        """全言語を選択"""
        for checkbox in self.language_checkboxes.values():
            checkbox.setChecked(True)

    def deselect_all_languages(self):
        """全言語の選択を解除"""
        for checkbox in self.language_checkboxes.values():
            checkbox.setChecked(False)

    def browse_output_directory(self):
        """出力先ディレクトリの選択"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "出力先ディレクトリを選択",
            str(self.default_output_dir)
        )

        if directory:
            self.output_dir_edit.setText(directory)

    def get_selected_languages(self) -> List[str]:
        """選択された言語のリストを取得"""
        selected = []
        for lang_code, checkbox in self.language_checkboxes.items():
            if checkbox.isChecked():
                selected.append(lang_code)
        return selected

    def get_output_directory(self) -> Path:
        """出力先ディレクトリを取得"""
        return Path(self.output_dir_edit.text())

    def handle_export(self):
        """エクスポート処理"""
        selected_languages = self.get_selected_languages()

        # 選択チェック
        if not selected_languages:
            QMessageBox.warning(
                self,
                "警告",
                "少なくとも1つの言語を選択してください。"
            )
            return

        # 出力先チェック
        output_dir = self.get_output_directory()
        if not output_dir.exists():
            reply = QMessageBox.question(
                self,
                "確認",
                f"出力先ディレクトリが存在しません。作成しますか？\n{output_dir}",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "エラー",
                        f"ディレクトリの作成に失敗しました：\n{str(e)}"
                    )
                    return
            else:
                return

        # 確認ダイアログ
        lang_names = [self.SUPPORTED_LANGUAGES.get(lang, lang) for lang in selected_languages]
        message = (
            f"以下の{len(selected_languages)}言語でSRTファイルを出力します：\n\n"
            f"{', '.join(lang_names)}\n\n"
            f"出力先: {output_dir}"
        )

        reply = QMessageBox.question(
            self,
            "確認",
            message,
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # エクスポート実行のシグナルを送信
            self.export_requested.emit(selected_languages, str(output_dir))
            self.accept()

    @staticmethod
    def get_export_settings(default_output_dir: Optional[Path] = None, parent=None) -> Optional[tuple]:
        """
        静的メソッド：エクスポート設定を取得

        Returns:
            tuple: (selected_languages: List[str], output_dir: str) または None（キャンセル時）
        """
        dialog = MultiLanguageExportDialog(default_output_dir, parent)

        selected_languages = []
        output_dir = ""

        def handle_export_request(languages, directory):
            nonlocal selected_languages, output_dir
            selected_languages = languages
            output_dir = directory

        dialog.export_requested.connect(handle_export_request)

        if dialog.exec() == QDialog.Accepted and selected_languages:
            return selected_languages, output_dir

        return None