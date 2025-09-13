"""
翻訳ビューの実装
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QPushButton, QComboBox, QCheckBox, QSpinBox, QLineEdit,
    QLabel, QProgressBar, QTextEdit, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QThread, pyqtSignal


class TranslateView(QDialog):
    """翻訳設定・実行ダイアログ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("翻訳設定")
        self.setModal(True)
        self.resize(600, 500)
        
        self.init_ui()
    
    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)
        
        # 翻訳プロバイダ選択
        provider_group = QGroupBox("翻訳プロバイダ")
        provider_layout = QVBoxLayout(provider_group)
        
        self.none_radio = QRadioButton("なし（CSV外部連携）")
        self.none_radio.setChecked(True)
        provider_layout.addWidget(self.none_radio)
        
        self.google_radio = QRadioButton("Google Cloud Translation v3")
        provider_layout.addWidget(self.google_radio)
        
        self.deepl_radio = QRadioButton("DeepL")
        provider_layout.addWidget(self.deepl_radio)
        
        # API設定ボタン
        api_layout = QHBoxLayout()
        self.api_settings_btn = QPushButton("API設定")
        self.api_settings_btn.clicked.connect(self.show_api_settings)
        api_layout.addWidget(self.api_settings_btn)
        api_layout.addStretch()
        provider_layout.addLayout(api_layout)
        
        layout.addWidget(provider_group)
        
        # 対象言語選択
        lang_group = QGroupBox("対象言語")
        lang_layout = QVBoxLayout(lang_group)
        
        lang_check_layout = QHBoxLayout()
        self.en_check = QCheckBox("English (en)")
        self.en_check.setChecked(True)
        lang_check_layout.addWidget(self.en_check)
        
        self.zh_check = QCheckBox("中文 (zh)")
        self.zh_check.setChecked(True)
        lang_check_layout.addWidget(self.zh_check)
        
        self.ko_check = QCheckBox("한국어 (ko)")
        self.ko_check.setChecked(True)
        lang_check_layout.addWidget(self.ko_check)
        
        self.ar_check = QCheckBox("العربية (ar)")
        self.ar_check.setChecked(True)
        lang_check_layout.addWidget(self.ar_check)
        
        lang_layout.addLayout(lang_check_layout)
        layout.addWidget(lang_group)
        
        # Glossary設定
        glossary_group = QGroupBox("用語集（Glossary）")
        glossary_layout = QHBoxLayout(glossary_group)
        
        self.glossary_path = QLineEdit()
        self.glossary_path.setPlaceholderText("CSVファイルを選択...")
        glossary_layout.addWidget(self.glossary_path)
        
        self.glossary_browse_btn = QPushButton("参照")
        self.glossary_browse_btn.clicked.connect(self.browse_glossary)
        glossary_layout.addWidget(self.glossary_browse_btn)
        
        self.glossary_enable_check = QCheckBox("適用")
        glossary_layout.addWidget(self.glossary_enable_check)
        
        layout.addWidget(glossary_group)
        
        # 整形オプション
        format_group = QGroupBox("整形オプション")
        format_layout = QVBoxLayout(format_group)
        
        # 行長・行数制限
        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("行長上限:"))
        self.max_chars_spin = QSpinBox()
        self.max_chars_spin.setRange(20, 100)
        self.max_chars_spin.setValue(42)
        limit_layout.addWidget(self.max_chars_spin)
        
        limit_layout.addWidget(QLabel("最大行数:"))
        self.max_lines_spin = QSpinBox()
        self.max_lines_spin.setRange(1, 5)
        self.max_lines_spin.setValue(2)
        limit_layout.addWidget(self.max_lines_spin)
        
        limit_layout.addWidget(QLabel("最小表示秒:"))
        self.min_duration_spin = QSpinBox()
        self.min_duration_spin.setRange(1, 10)
        self.min_duration_spin.setValue(1)
        limit_layout.addWidget(self.min_duration_spin)
        
        limit_layout.addStretch()
        format_layout.addLayout(limit_layout)
        
        # その他オプション
        option_layout = QHBoxLayout()
        self.punctuation_break_check = QCheckBox("句読点優先改行")
        self.punctuation_break_check.setChecked(True)
        option_layout.addWidget(self.punctuation_break_check)
        
        self.rtl_format_check = QCheckBox("RTL整形（ar）")
        option_layout.addWidget(self.rtl_format_check)
        
        self.html_decode_check = QCheckBox("HTMLエンティティ解除")
        option_layout.addWidget(self.html_decode_check)
        
        option_layout.addStretch()
        format_layout.addLayout(option_layout)
        
        layout.addWidget(format_group)
        
        # 実行ボタン
        button_layout = QHBoxLayout()
        
        self.translate_btn = QPushButton("一括翻訳")
        self.translate_btn.clicked.connect(self.start_translation)
        button_layout.addWidget(self.translate_btn)
        
        self.export_csv_btn = QPushButton("CSVに書き出し")
        self.export_csv_btn.clicked.connect(self.export_csv)
        button_layout.addWidget(self.export_csv_btn)
        
        self.import_csv_btn = QPushButton("翻訳CSVを取り込み")
        self.import_csv_btn.clicked.connect(self.import_csv)
        button_layout.addWidget(self.import_csv_btn)
        
        self.save_srt_btn = QPushButton("SRT一括保存")
        self.save_srt_btn.clicked.connect(self.save_all_srt)
        button_layout.addWidget(self.save_srt_btn)
        
        button_layout.addStretch()
        
        self.close_btn = QPushButton("閉じる")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # ログ表示
        log_group = QGroupBox("ログ")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(100)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)
    
    def show_api_settings(self):
        """API設定ダイアログを表示"""
        if self.google_radio.isChecked():
            self.show_google_api_settings()
        elif self.deepl_radio.isChecked():
            self.show_deepl_api_settings()
        else:
            QMessageBox.information(self, "情報", "CSV外部連携モードではAPI設定は不要です")
    
    def show_google_api_settings(self):
        """Google Cloud Translation API設定"""
        dialog = GoogleApiSettingsDialog(self)
        dialog.exec()
    
    def show_deepl_api_settings(self):
        """DeepL API設定"""
        dialog = DeepLApiSettingsDialog(self)
        dialog.exec()
    
    def browse_glossary(self):
        """用語集ファイルを参照"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "用語集CSVファイルを選択",
            "",
            "CSVファイル (*.csv);;すべてのファイル (*)"
        )
        if file_path:
            self.glossary_path.setText(file_path)
    
    def start_translation(self):
        """翻訳を開始"""
        if self.none_radio.isChecked():
            QMessageBox.information(
                self, 
                "情報", 
                "CSV外部連携モードです。\\n「CSVに書き出し」で外部翻訳用ファイルを作成してください。"
            )
            return
        
        self.log_text.append("翻訳を開始しています...")
        self.progress_bar.setVisible(True)
        self.translate_btn.setEnabled(False)
        
        # TODO: 実際の翻訳処理を別スレッドで実行
        # 現在は仮の処理
        self.log_text.append("翻訳が完了しました（仮処理）")
        self.progress_bar.setVisible(False)
        self.translate_btn.setEnabled(True)
    
    def export_csv(self):
        """CSVに書き出し"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "翻訳用CSVファイルを保存",
            "subs/export.csv",
            "CSVファイル (*.csv);;すべてのファイル (*)"
        )
        
        if file_path:
            # TODO: 実際のCSVエクスポート処理
            self.log_text.append(f"CSVを書き出しました: {file_path}")
    
    def import_csv(self):
        """翻訳済みCSVを取り込み"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "翻訳済みCSVファイルを選択",
            "subs/",
            "CSVファイル (*.csv);;すべてのファイル (*)"
        )
        
        if file_path:
            # TODO: 実際のCSVインポート処理
            self.log_text.append(f"翻訳CSVを取り込みました: {file_path}")
    
    def save_all_srt(self):
        """全言語のSRTファイルを保存"""
        # TODO: 実際のSRT保存処理
        languages = []
        if self.en_check.isChecked():
            languages.append("en")
        if self.zh_check.isChecked():
            languages.append("zh")
        if self.ko_check.isChecked():
            languages.append("ko")
        if self.ar_check.isChecked():
            languages.append("ar")
        
        self.log_text.append(f"SRTファイルを保存しました: {', '.join(languages)}")


class GoogleApiSettingsDialog(QDialog):
    """Google Cloud Translation API設定ダイアログ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Google Cloud Translation API設定")
        self.setModal(True)
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Project ID:"))
        self.project_id_edit = QLineEdit()
        layout.addWidget(self.project_id_edit)
        
        layout.addWidget(QLabel("Location:"))
        self.location_edit = QLineEdit()
        self.location_edit.setText("global")
        layout.addWidget(self.location_edit)
        
        layout.addWidget(QLabel("API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.api_key_edit)
        
        # ボタン
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
    
    def save_settings(self):
        """設定を保存"""
        # TODO: 実際の設定保存処理
        self.accept()


class DeepLApiSettingsDialog(QDialog):
    """DeepL API設定ダイアログ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DeepL API設定")
        self.setModal(True)
        self.resize(400, 200)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.api_key_edit)
        
        layout.addWidget(QLabel("フォーマリティ:"))
        self.formality_combo = QComboBox()
        self.formality_combo.addItems(["default", "more", "less"])
        layout.addWidget(self.formality_combo)
        
        # ボタン
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
    
    def save_settings(self):
        """設定を保存"""
        # TODO: 実際の設定保存処理
        self.accept()