"""
設定ビューの実装
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsView(QDialog):
    """設定ダイアログ"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setModal(True)
        self.resize(500, 600)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)

        # タブウィジェット
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 各タブを作成
        self.create_extraction_tab()
        self.create_formatting_tab()
        self.create_output_tab()
        self.create_ui_tab()

        # ボタン
        button_layout = QHBoxLayout()

        self.reset_btn = QPushButton("デフォルトに戻す")
        self.reset_btn.clicked.connect(self.reset_settings)
        button_layout.addWidget(self.reset_btn)

        button_layout.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept_settings)
        button_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def create_extraction_tab(self):
        """抽出設定タブ"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # サンプリング設定
        sampling_group = QGroupBox("サンプリング設定")
        sampling_layout = QFormLayout(sampling_group)

        self.fps_sample_spin = QDoubleSpinBox()
        self.fps_sample_spin.setRange(0.5, 10.0)
        self.fps_sample_spin.setSingleStep(0.5)
        self.fps_sample_spin.setValue(3.0)
        self.fps_sample_spin.setSuffix(" fps")
        sampling_layout.addRow("サンプリングFPS:", self.fps_sample_spin)

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["オリジナル", "720p", "480p", "360p"])
        sampling_layout.addRow("解析解像度:", self.resolution_combo)

        layout.addWidget(sampling_group)

        # ROI設定
        roi_group = QGroupBox("抽出領域（ROI）設定")
        roi_layout = QVBoxLayout(roi_group)

        self.roi_auto_radio = QCheckBox("自動検出")
        roi_layout.addWidget(self.roi_auto_radio)

        self.roi_bottom_radio = QCheckBox("下段固定")
        self.roi_bottom_radio.setChecked(True)
        roi_layout.addWidget(self.roi_bottom_radio)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(QLabel("下段比率:"))
        self.bottom_ratio_spin = QSpinBox()
        self.bottom_ratio_spin.setRange(10, 50)
        self.bottom_ratio_spin.setValue(30)
        self.bottom_ratio_spin.setSuffix("%")
        bottom_layout.addWidget(self.bottom_ratio_spin)
        bottom_layout.addStretch()
        roi_layout.addLayout(bottom_layout)

        self.roi_manual_radio = QCheckBox("手動矩形")
        roi_layout.addWidget(self.roi_manual_radio)

        layout.addWidget(roi_group)

        # OCRエンジン設定
        ocr_group = QGroupBox("OCRエンジン")
        ocr_layout = QFormLayout(ocr_group)

        self.ocr_engine_combo = QComboBox()
        self.ocr_engine_combo.addItems(["PaddleOCR (推奨)", "Tesseract"])
        ocr_layout.addRow("エンジン:", self.ocr_engine_combo)

        self.ocr_confidence_spin = QSpinBox()
        self.ocr_confidence_spin.setRange(50, 100)
        self.ocr_confidence_spin.setValue(80)
        self.ocr_confidence_spin.setSuffix("%")
        ocr_layout.addRow("信頼度閾値:", self.ocr_confidence_spin)

        layout.addWidget(ocr_group)

        layout.addStretch()
        self.tab_widget.addTab(tab, "抽出")

    def create_formatting_tab(self):
        """整形設定タブ"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # テキスト整形
        text_group = QGroupBox("テキスト整形")
        text_layout = QFormLayout(text_group)

        self.max_chars_spin = QSpinBox()
        self.max_chars_spin.setRange(20, 100)
        self.max_chars_spin.setValue(42)
        text_layout.addRow("行長上限（文字）:", self.max_chars_spin)

        self.max_lines_spin = QSpinBox()
        self.max_lines_spin.setRange(1, 5)
        self.max_lines_spin.setValue(2)
        text_layout.addRow("最大行数:", self.max_lines_spin)

        self.min_duration_spin = QDoubleSpinBox()
        self.min_duration_spin.setRange(0.5, 5.0)
        self.min_duration_spin.setSingleStep(0.1)
        self.min_duration_spin.setValue(1.2)
        self.min_duration_spin.setSuffix(" 秒")
        text_layout.addRow("最小表示秒:", self.min_duration_spin)

        layout.addWidget(text_group)

        # グルーピング設定
        grouping_group = QGroupBox("グルーピング設定")
        grouping_layout = QFormLayout(grouping_group)

        self.similarity_spin = QSpinBox()
        self.similarity_spin.setRange(70, 100)
        self.similarity_spin.setValue(90)
        self.similarity_spin.setSuffix("%")
        grouping_layout.addRow("類似度閾値:", self.similarity_spin)

        self.merge_gap_spin = QDoubleSpinBox()
        self.merge_gap_spin.setRange(0.1, 2.0)
        self.merge_gap_spin.setSingleStep(0.1)
        self.merge_gap_spin.setValue(0.5)
        self.merge_gap_spin.setSuffix(" 秒")
        grouping_layout.addRow("結合可能間隔:", self.merge_gap_spin)

        layout.addWidget(grouping_group)

        # 正規化設定
        normalize_group = QGroupBox("正規化設定")
        normalize_layout = QVBoxLayout(normalize_group)

        self.normalize_punctuation_check = QCheckBox("句読点正規化")
        self.normalize_punctuation_check.setChecked(True)
        normalize_layout.addWidget(self.normalize_punctuation_check)

        self.normalize_whitespace_check = QCheckBox("空白正規化")
        self.normalize_whitespace_check.setChecked(True)
        normalize_layout.addWidget(self.normalize_whitespace_check)

        self.remove_duplicate_check = QCheckBox("重複文字除去")
        normalize_layout.addWidget(self.remove_duplicate_check)

        layout.addWidget(normalize_group)

        layout.addStretch()
        self.tab_widget.addTab(tab, "整形")

    def create_output_tab(self):
        """出力設定タブ"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ファイル設定
        file_group = QGroupBox("ファイル設定")
        file_layout = QFormLayout(file_group)

        output_layout = QHBoxLayout()
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("出力フォルダを選択...")
        output_layout.addWidget(self.output_folder_edit)

        self.output_browse_btn = QPushButton("参照")
        self.output_browse_btn.clicked.connect(self.browse_output_folder)
        output_layout.addWidget(self.output_browse_btn)

        file_layout.addRow("出力フォルダ:", output_layout)

        self.filename_pattern_edit = QLineEdit()
        self.filename_pattern_edit.setText("{basename}.{lang}.srt")
        file_layout.addRow("ファイル名パターン:", self.filename_pattern_edit)

        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["UTF-8", "UTF-8 BOM", "Shift_JIS", "CP932"])
        file_layout.addRow("文字エンコーディング:", self.encoding_combo)

        layout.addWidget(file_group)

        # SRT設定
        srt_group = QGroupBox("SRT設定")
        srt_layout = QVBoxLayout(srt_group)

        self.srt_bom_check = QCheckBox("BOM付きで保存")
        srt_layout.addWidget(self.srt_bom_check)

        self.srt_crlf_check = QCheckBox("CRLF改行コード（Windows）")
        srt_layout.addWidget(self.srt_crlf_check)

        layout.addWidget(srt_group)

        # 多言語エクスポート設定
        multilang_group = QGroupBox("多言語エクスポート設定")
        multilang_layout = QFormLayout(multilang_group)

        # デフォルト選択言語
        self.default_languages_combo = QComboBox()
        self.default_languages_combo.addItems(
            [
                "日本語のみ",
                "日本語 + 英語",
                "日本語 + 英語 + 中国語（簡体）",
                "カスタム",
            ]
        )
        self.default_languages_combo.setCurrentText("日本語 + 英語")
        multilang_layout.addRow("デフォルト選択:", self.default_languages_combo)

        # 自動翻訳設定（将来的な実装用）
        self.auto_translate_check = QCheckBox("自動翻訳を有効化（実装予定）")
        self.auto_translate_check.setEnabled(False)  # 現在は無効
        multilang_layout.addWidget(self.auto_translate_check)

        layout.addWidget(multilang_group)

        # 上書き動作
        overwrite_group = QGroupBox("上書き動作")
        overwrite_layout = QVBoxLayout(overwrite_group)

        self.overwrite_ask_radio = QCheckBox("確認する")
        self.overwrite_ask_radio.setChecked(True)
        overwrite_layout.addWidget(self.overwrite_ask_radio)

        self.overwrite_auto_radio = QCheckBox("自動上書き")
        overwrite_layout.addWidget(self.overwrite_auto_radio)

        self.overwrite_backup_radio = QCheckBox("バックアップ作成")
        overwrite_layout.addWidget(self.overwrite_backup_radio)

        layout.addWidget(overwrite_group)

        layout.addStretch()
        self.tab_widget.addTab(tab, "出力")

    def create_ui_tab(self):
        """UI設定タブ"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 外観設定
        appearance_group = QGroupBox("外観設定")
        appearance_layout = QFormLayout(appearance_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["システム", "ライト", "ダーク"])
        appearance_layout.addRow("テーマ:", self.theme_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(9)
        appearance_layout.addRow("フォントサイズ:", self.font_size_spin)

        layout.addWidget(appearance_group)

        # 動作設定
        behavior_group = QGroupBox("動作設定")
        behavior_layout = QVBoxLayout(behavior_group)

        self.auto_save_check = QCheckBox("自動保存")
        behavior_layout.addWidget(self.auto_save_check)

        auto_save_layout = QHBoxLayout()
        auto_save_layout.addWidget(QLabel("間隔:"))
        self.auto_save_interval_spin = QSpinBox()
        self.auto_save_interval_spin.setRange(1, 60)
        self.auto_save_interval_spin.setValue(5)
        self.auto_save_interval_spin.setSuffix(" 分")
        auto_save_layout.addWidget(self.auto_save_interval_spin)
        auto_save_layout.addStretch()
        behavior_layout.addLayout(auto_save_layout)

        self.recent_files_spin = QSpinBox()
        self.recent_files_spin.setRange(5, 20)
        self.recent_files_spin.setValue(10)
        recent_layout = QHBoxLayout()
        recent_layout.addWidget(QLabel("最近使用したファイル:"))
        recent_layout.addWidget(self.recent_files_spin)
        recent_layout.addWidget(QLabel("件"))
        recent_layout.addStretch()
        behavior_layout.addLayout(recent_layout)

        layout.addWidget(behavior_group)

        # ショートカット設定
        shortcut_group = QGroupBox("ショートカット")
        shortcut_layout = QFormLayout(shortcut_group)

        shortcut_layout.addRow("再生/一時停止:", QLabel("Space"))
        shortcut_layout.addRow("分割:", QLabel("S"))
        shortcut_layout.addRow("結合:", QLabel("M"))
        shortcut_layout.addRow("保存:", QLabel("Ctrl+S"))
        shortcut_layout.addRow("QCチェック:", QLabel("Ctrl+Q"))

        layout.addWidget(shortcut_group)

        layout.addStretch()
        self.tab_widget.addTab(tab, "UI")

    def browse_output_folder(self):
        """出力フォルダを参照"""
        folder = QFileDialog.getExistingDirectory(
            self, "出力フォルダを選択", self.output_folder_edit.text()
        )
        if folder:
            self.output_folder_edit.setText(folder)

    def load_settings(self):
        """設定を読み込み"""
        # TODO: 実際の設定読み込み処理
        pass

    def reset_settings(self):
        """設定をデフォルトに戻す"""
        # 抽出設定
        self.fps_sample_spin.setValue(3.0)
        self.resolution_combo.setCurrentIndex(0)
        self.roi_bottom_radio.setChecked(True)
        self.bottom_ratio_spin.setValue(30)
        self.ocr_engine_combo.setCurrentIndex(0)
        self.ocr_confidence_spin.setValue(80)

        # 整形設定
        self.max_chars_spin.setValue(42)
        self.max_lines_spin.setValue(2)
        self.min_duration_spin.setValue(1.2)
        self.similarity_spin.setValue(90)
        self.merge_gap_spin.setValue(0.5)
        self.normalize_punctuation_check.setChecked(True)
        self.normalize_whitespace_check.setChecked(True)
        self.remove_duplicate_check.setChecked(False)

        # 出力設定
        self.output_folder_edit.clear()
        self.filename_pattern_edit.setText("{basename}.{lang}.srt")
        self.encoding_combo.setCurrentIndex(0)
        self.srt_bom_check.setChecked(False)
        self.srt_crlf_check.setChecked(False)
        self.default_languages_combo.setCurrentText("日本語 + 英語")
        self.auto_translate_check.setChecked(False)
        self.overwrite_ask_radio.setChecked(True)

        # UI設定
        self.theme_combo.setCurrentIndex(0)
        self.font_size_spin.setValue(9)
        self.auto_save_check.setChecked(False)
        self.auto_save_interval_spin.setValue(5)
        self.recent_files_spin.setValue(10)

    def accept_settings(self):
        """設定を適用して閉じる"""
        # TODO: 設定保存処理
        self.accept()

    def get_settings(self):
        """現在の設定値を取得"""
        return {
            # 抽出設定
            "fps_sample": self.fps_sample_spin.value(),
            "resolution": self.resolution_combo.currentText(),
            "roi_mode": "bottom" if self.roi_bottom_radio.isChecked() else "auto",
            "bottom_ratio": self.bottom_ratio_spin.value() / 100.0,
            "ocr_engine": (
                "paddleocr"
                if self.ocr_engine_combo.currentIndex() == 0
                else "tesseract"
            ),
            "ocr_confidence": self.ocr_confidence_spin.value() / 100.0,
            # 整形設定
            "max_chars": self.max_chars_spin.value(),
            "max_lines": self.max_lines_spin.value(),
            "min_duration": self.min_duration_spin.value(),
            "similarity_threshold": self.similarity_spin.value() / 100.0,
            "merge_gap": self.merge_gap_spin.value(),
            "normalize_punctuation": self.normalize_punctuation_check.isChecked(),
            "normalize_whitespace": self.normalize_whitespace_check.isChecked(),
            "remove_duplicate": self.remove_duplicate_check.isChecked(),
            # 出力設定
            "output_folder": self.output_folder_edit.text(),
            "filename_pattern": self.filename_pattern_edit.text(),
            "encoding": self.encoding_combo.currentText(),
            "srt_bom": self.srt_bom_check.isChecked(),
            "srt_crlf": self.srt_crlf_check.isChecked(),
            "default_languages": self.default_languages_combo.currentText(),
            "auto_translate": self.auto_translate_check.isChecked(),
            "overwrite_mode": "ask" if self.overwrite_ask_radio.isChecked() else "auto",
            # UI設定
            "theme": self.theme_combo.currentText(),
            "font_size": self.font_size_spin.value(),
            "auto_save": self.auto_save_check.isChecked(),
            "auto_save_interval": self.auto_save_interval_spin.value(),
            "recent_files_count": self.recent_files_spin.value(),
        }

    def get_default_languages(self):
        """デフォルト選択言語を取得"""
        selection = self.default_languages_combo.currentText()
        if selection == "日本語のみ":
            return ["ja"]
        elif selection == "日本語 + 英語":
            return ["ja", "en"]
        elif selection == "日本語 + 英語 + 中国語（簡体）":
            return ["ja", "en", "zh-cn"]
        else:  # カスタム
            return ["ja"]  # デフォルトは日本語

    def get_default_output_directory(self):
        """デフォルト出力ディレクトリを取得"""
        output_dir = self.output_folder_edit.text().strip()
        if output_dir:
            return Path(output_dir)
        return None

    def get_srt_format_settings(self):
        """SRT出力設定を取得"""
        from pathlib import Path

        from app.core.format.srt import SRTFormatSettings

        encoding = "utf-8"
        with_bom = False

        if self.encoding_combo.currentText() == "UTF-8 BOM":
            encoding = "utf-8"
            with_bom = True
        elif self.encoding_combo.currentText() == "Shift_JIS":
            encoding = "shift_jis"
        elif self.encoding_combo.currentText() == "CP932":
            encoding = "cp932"
        else:  # UTF-8
            encoding = "utf-8"

        return SRTFormatSettings(
            encoding=encoding,
            with_bom=with_bom or self.srt_bom_check.isChecked(),
            line_ending="crlf" if self.srt_crlf_check.isChecked() else "lf",
            max_chars_per_line=self.max_chars_spin.value(),
            max_lines=self.max_lines_spin.value(),
        )
