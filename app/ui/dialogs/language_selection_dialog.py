"""
言語選択ダイアログの実装
SRT出力時に対象言語を選択するためのダイアログ
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QPushButton, QLabel, QScrollArea, QWidget, QMessageBox,
    QLineEdit, QComboBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal
from typing import List, Dict, Tuple, Optional
from pathlib import Path


class LanguageSelectionDialog(QDialog):
    """言語選択ダイアログ"""

    # シグナル定義
    export_confirmed = Signal(list, dict)  # selected_languages, export_options

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SRT出力言語選択")
        self.setModal(True)
        self.resize(500, 600)

        # サポート言語一覧（Google Translate対応言語）
        self.supported_languages = {
            # 主要言語
            "ja": "日本語",
            "en": "英語",
            "zh": "中国語（簡体字）",
            "zh-tw": "中国語（繁体字）",
            "ko": "韓国語",
            "es": "スペイン語",
            "fr": "フランス語",
            "de": "ドイツ語",
            "it": "イタリア語",
            "pt": "ポルトガル語",
            "ru": "ロシア語",
            "ar": "アラビア語",
            "hi": "ヒンディー語",
            "th": "タイ語",
            "vi": "ベトナム語",
            "nl": "オランダ語",
            "sv": "スウェーデン語",
            "no": "ノルウェー語",
            "da": "デンマーク語",
            "fi": "フィンランド語",
            "pl": "ポーランド語",
            "cs": "チェコ語",
            "hu": "ハンガリー語",
            "ro": "ルーマニア語",
            "bg": "ブルガリア語",
            "hr": "クロアチア語",
            "sk": "スロバキア語",
            "sl": "スロベニア語",
            "et": "エストニア語",
            "lv": "ラトビア語",
            "lt": "リトアニア語",
            "mt": "マルタ語",
            "tr": "トルコ語",
            "he": "ヘブライ語",
            "fa": "ペルシャ語",
            "ur": "ウルドゥー語",
            "bn": "ベンガル語",
            "ta": "タミル語",
            "te": "テルグ語",
            "mr": "マラーティー語",
            "gu": "グジャラート語",
            "kn": "カンナダ語",
            "ml": "マラヤーラム語",
            "pa": "パンジャブ語",
            "ne": "ネパール語",
            "si": "シンハラ語",
            "my": "ミャンマー語",
            "km": "クメール語",
            "lo": "ラオ語",
            "ka": "グルジア語",
            "am": "アムハラ語",
            "sw": "スワヒリ語",
            "zu": "ズールー語",
            "af": "アフリカーンス語",
            "is": "アイスランド語",
            "ga": "アイルランド語",
            "cy": "ウェールズ語",
            "eu": "バスク語",
            "ca": "カタルーニャ語",
            "gl": "ガリシア語",
            "lb": "ルクセンブルク語",
            "mk": "マケドニア語",
            "sq": "アルバニア語",
            "be": "ベラルーシ語",
            "uk": "ウクライナ語",
            "kk": "カザフ語",
            "ky": "キルギス語",
            "uz": "ウズベク語",
            "tg": "タジク語",
            "mn": "モンゴル語",
            "az": "アゼルバイジャン語",
            "hy": "アルメニア語"
        }

        self.language_checkboxes = {}
        self.selected_languages = []

        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        """UI設定"""
        layout = QVBoxLayout(self)

        # タイトル
        title_label = QLabel("出力する言語を選択してください")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # 出力オプション設定
        self.setup_export_options(layout)

        # 言語選択エリア
        self.setup_language_selection(layout)

        # ボタン
        self.setup_buttons(layout)

    def setup_export_options(self, parent_layout: QVBoxLayout):
        """出力オプション設定"""
        options_group = QGroupBox("出力設定")
        options_layout = QVBoxLayout(options_group)

        # 出力先フォルダ設定
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("出力先フォルダ:"))

        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("デフォルト（動画ファイルと同じフォルダ）")
        folder_layout.addWidget(self.output_folder_edit)

        self.browse_folder_btn = QPushButton("参照...")
        self.browse_folder_btn.clicked.connect(self.browse_output_folder)
        folder_layout.addWidget(self.browse_folder_btn)

        options_layout.addLayout(folder_layout)

        # 翻訳プロバイダ設定
        provider_layout = QHBoxLayout()
        provider_layout.addWidget(QLabel("翻訳エンジン:"))

        self.translation_provider_combo = QComboBox()
        self.translation_provider_combo.addItems([
            "Google Translate",
            "DeepL",
            "翻訳しない（日本語のみ出力）"
        ])
        self.translation_provider_combo.setCurrentIndex(0)  # Google Translateをデフォルト
        provider_layout.addWidget(self.translation_provider_combo)

        options_layout.addLayout(provider_layout)

        # 同時翻訳数制限設定
        concurrent_layout = QHBoxLayout()
        concurrent_layout.addWidget(QLabel("同時翻訳数:"))

        self.concurrent_translation_spin = QSpinBox()
        self.concurrent_translation_spin.setRange(1, 5)
        self.concurrent_translation_spin.setValue(3)
        self.concurrent_translation_spin.setSuffix(" 言語")
        concurrent_layout.addWidget(self.concurrent_translation_spin)

        concurrent_layout.addStretch()
        options_layout.addLayout(concurrent_layout)

        parent_layout.addWidget(options_group)

    def setup_language_selection(self, parent_layout: QVBoxLayout):
        """言語選択エリア設定"""
        # 言語選択グループボックス
        lang_group = QGroupBox("対象言語選択")
        lang_layout = QVBoxLayout(lang_group)

        # 一括選択ボタン
        control_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("すべて選択")
        self.select_all_btn.clicked.connect(self.select_all_languages)
        control_layout.addWidget(self.select_all_btn)

        self.select_none_btn = QPushButton("すべて解除")
        self.select_none_btn.clicked.connect(self.select_no_languages)
        control_layout.addWidget(self.select_none_btn)

        self.select_popular_btn = QPushButton("主要言語のみ")
        self.select_popular_btn.clicked.connect(self.select_popular_languages)
        control_layout.addWidget(self.select_popular_btn)

        control_layout.addStretch()
        lang_layout.addLayout(control_layout)

        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # 言語チェックボックス作成
        popular_languages = ["en", "zh", "zh-tw", "ko", "es", "fr", "de", "it", "pt", "ru", "ar", "hi"]

        # 主要言語を先に配置
        for lang_code in popular_languages:
            if lang_code in self.supported_languages:
                lang_name = self.supported_languages[lang_code]
                checkbox = QCheckBox(f"{lang_name} ({lang_code})")
                checkbox.setObjectName(lang_code)
                self.language_checkboxes[lang_code] = checkbox
                scroll_layout.addWidget(checkbox)

        # 区切り線
        separator = QLabel("─" * 50)
        separator.setAlignment(Qt.AlignCenter)
        separator.setStyleSheet("color: gray; margin: 10px 0;")
        scroll_layout.addWidget(separator)

        # その他の言語
        other_languages = sorted(
            [code for code in self.supported_languages.keys() if code not in popular_languages + ["ja"]]
        )

        for lang_code in other_languages:
            lang_name = self.supported_languages[lang_code]
            checkbox = QCheckBox(f"{lang_name} ({lang_code})")
            checkbox.setObjectName(lang_code)
            self.language_checkboxes[lang_code] = checkbox
            scroll_layout.addWidget(checkbox)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        lang_layout.addWidget(scroll_area)

        parent_layout.addWidget(lang_group)

    def setup_buttons(self, parent_layout: QVBoxLayout):
        """ボタン設定"""
        button_layout = QHBoxLayout()

        self.export_btn = QPushButton("SRT出力実行")
        self.export_btn.clicked.connect(self.confirm_export)
        self.export_btn.setDefault(True)
        button_layout.addWidget(self.export_btn)

        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        parent_layout.addLayout(button_layout)

    def setup_connections(self):
        """シグナル接続設定"""
        # 翻訳プロバイダ変更時の処理
        self.translation_provider_combo.currentIndexChanged.connect(self.on_provider_changed)

    def browse_output_folder(self):
        """出力先フォルダ選択"""
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(
            self,
            "出力先フォルダを選択",
            str(Path.home()),
            QFileDialog.ShowDirsOnly
        )

        if folder:
            self.output_folder_edit.setText(folder)

    def on_provider_changed(self):
        """翻訳プロバイダ変更時の処理"""
        provider_index = self.translation_provider_combo.currentIndex()

        # 翻訳しない場合は言語選択を無効化
        if provider_index == 2:  # 翻訳しない
            for checkbox in self.language_checkboxes.values():
                checkbox.setEnabled(False)
                checkbox.setChecked(False)
        else:
            for checkbox in self.language_checkboxes.values():
                checkbox.setEnabled(True)

    def select_all_languages(self):
        """すべての言語を選択"""
        for checkbox in self.language_checkboxes.values():
            if checkbox.isEnabled():
                checkbox.setChecked(True)

    def select_no_languages(self):
        """すべての言語を解除"""
        for checkbox in self.language_checkboxes.values():
            checkbox.setChecked(False)

    def select_popular_languages(self):
        """主要言語のみ選択"""
        popular_languages = ["en", "zh", "zh-tw", "ko", "es", "fr", "de", "it", "pt", "ru", "ar", "hi"]

        for lang_code, checkbox in self.language_checkboxes.items():
            if checkbox.isEnabled():
                checkbox.setChecked(lang_code in popular_languages)

    def get_selected_languages(self) -> List[str]:
        """選択された言語コードのリストを取得"""
        selected = []
        for lang_code, checkbox in self.language_checkboxes.items():
            if checkbox.isChecked():
                selected.append(lang_code)
        return selected

    def get_export_options(self) -> Dict:
        """出力オプションを取得"""
        return {
            "output_folder": self.output_folder_edit.text().strip() or None,
            "translation_provider": ["google", "deepl", "none"][self.translation_provider_combo.currentIndex()],
            "concurrent_translations": self.concurrent_translation_spin.value()
        }

    def confirm_export(self):
        """出力確認処理"""
        selected_languages = self.get_selected_languages()
        export_options = self.get_export_options()

        # 翻訳ありの場合は言語選択必須
        if export_options["translation_provider"] != "none" and not selected_languages:
            QMessageBox.warning(
                self,
                "言語未選択",
                "翻訳出力を行う場合は、少なくとも1つの言語を選択してください。\n\n"
                "日本語のみ出力する場合は、翻訳エンジンを「翻訳しない」に設定してください。"
            )
            return

        # 日本語のみの場合は確認
        if export_options["translation_provider"] == "none":
            reply = QMessageBox.question(
                self,
                "日本語SRT出力確認",
                "日本語SRTファイルのみを出力します。\n\n実行してよろしいですか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return
        else:
            # 翻訳ありの場合の確認
            lang_names = [self.supported_languages[code] for code in selected_languages]
            confirmation_message = (
                f"以下の言語でSRTファイルを出力します：\n\n"
                f"・日本語（元データ）\n"
                f"・{', '.join(lang_names[:5])}"
                f"{', ...' if len(lang_names) > 5 else ''}\n\n"
                f"翻訳エンジン: {self.translation_provider_combo.currentText()}\n"
                f"合計: {len(selected_languages) + 1} ファイル\n\n"
                f"実行してよろしいですか？"
            )

            reply = QMessageBox.question(
                self,
                "翻訳SRT出力確認",
                confirmation_message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return

        # シグナル発出して親ウィンドウに処理を委譲
        self.export_confirmed.emit(selected_languages, export_options)
        self.accept()