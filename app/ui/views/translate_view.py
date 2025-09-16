"""
翻訳ビューの実装
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QPushButton, QComboBox, QCheckBox, QSpinBox, QLineEdit,
    QLabel, QProgressBar, QTextEdit, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QThread
from pathlib import Path
from typing import List, Dict, Optional

from app.core.models import SubtitleItem, Project
from app.core.csv import (
    SubtitleCSVExporter, SubtitleCSVImporter,
    TranslationWorkflowManager, CSVExportSettings
)
from app.core.format.srt import SRTFormatter
from app.core.translate import (
    TranslationProviderRouter,
    TranslationProviderType,
    LocalTranslateProvider,
    LocalTranslateSettings,
    LocalTranslateError
)


class TranslationWorker(QThread):
    """ローカル翻訳バックグラウンドワーカー"""

    progress_updated = Signal(str, int)  # message, progress
    translation_completed = Signal(dict)  # translations: Dict[lang, List[SubtitleItem]]
    translation_error = Signal(str)  # error_message

    def __init__(self, subtitles: List[SubtitleItem], target_languages: List[str],
                 models_dir: str):
        super().__init__()
        self.subtitles = subtitles
        self.target_languages = target_languages
        self.models_dir = models_dir

    def run(self):
        """ローカル翻訳実行"""
        try:
            translations = {}

            # ローカル翻訳プロバイダーの初期化
            router = self._init_local_provider()

            # 翻訳テキスト準備
            texts_to_translate = [subtitle.text for subtitle in self.subtitles]

            total_languages = len(self.target_languages)

            for i, target_lang in enumerate(self.target_languages):
                lang_progress = int((i * 100) / total_languages)
                self.progress_updated.emit(f"{target_lang}への翻訳を開始...", lang_progress)

                def progress_callback(message: str, progress: int):
                    # 言語単位の進捗を全体進捗に変換
                    total_progress = lang_progress + int(progress / total_languages)
                    self.progress_updated.emit(f"{target_lang}: {message}", total_progress)

                # ローカル翻訳実行
                result = router.translate_batch(
                    texts=texts_to_translate,
                    target_language=target_lang,
                    source_language="ja",
                    progress_callback=progress_callback
                )

                if result.success:
                    # 翻訳結果をSubtitleItemに変換
                    translated_subtitles = []
                    for j, translated_text in enumerate(result.translated_texts):
                        original_subtitle = self.subtitles[j]
                        translated_subtitle = SubtitleItem(
                            index=original_subtitle.index,
                            start_ms=original_subtitle.start_ms,
                            end_ms=original_subtitle.end_ms,
                            text=translated_text,
                            bbox=original_subtitle.bbox
                        )
                        translated_subtitles.append(translated_subtitle)

                    translations[target_lang] = translated_subtitles
                else:
                    raise Exception(f"{target_lang}への翻訳に失敗: {result.error_message}")

            self.translation_completed.emit(translations)

        except LocalTranslateError as e:
            # ローカル翻訳固有エラー
            guidance = ""
            if hasattr(e, 'error_code'):
                temp_provider = LocalTranslateProvider(LocalTranslateSettings(self.models_dir))
                guidance = temp_provider.get_error_guidance(e)

            self.translation_error.emit(f"{str(e)}\\n\\n{guidance}")

        except Exception as e:
            self.translation_error.emit(f"予期しないエラーが発生しました: {str(e)}")

    def _init_local_provider(self) -> TranslationProviderRouter:
        """ローカル翻訳プロバイダーの初期化"""
        router = TranslationProviderRouter()

        # ローカル翻訳設定
        local_settings = LocalTranslateSettings(
            models_dir=self.models_dir,
            max_batch_size=4,
            beam_size=1,
            length_penalty=0.2,
            repetition_penalty=1.5,
            no_repeat_ngram_size=3,
            max_decoding_length=50
        )

        # ローカル翻訳プロバイダーを登録
        success = router.register_provider(TranslationProviderType.LOCAL, local_settings)
        if not success:
            raise Exception("ローカル翻訳プロバイダーの初期化に失敗しました")

        return router


class TranslateView(QDialog):
    """翻訳設定・実行ダイアログ"""
    
    # シグナル定義
    translations_updated = Signal(dict)  # 翻訳データ更新
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("翻訳設定")
        self.setModal(True)
        self.resize(600, 500)
        
        # データ
        self.subtitles: List[SubtitleItem] = []
        self.project: Optional[Project] = None
        self.translated_subtitles: Dict[str, List[SubtitleItem]] = {}
        
        self.init_ui()
    
    def set_subtitles(self, subtitles: List[SubtitleItem], project: Optional[Project] = None):
        """字幕データを設定"""
        self.subtitles = subtitles
        self.project = project
        
        # ボタンの有効/無効を設定
        has_subtitles = len(subtitles) > 0
        self.export_csv_btn.setEnabled(has_subtitles)
        self.translate_btn.setEnabled(has_subtitles)
        self.save_srt_btn.setEnabled(len(self.translated_subtitles) > 0)
    
    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)

        # 翻訳プロバイダ選択
        provider_group = QGroupBox("翻訳プロバイダ")
        provider_layout = QVBoxLayout(provider_group)

        self.none_radio = QRadioButton("なし（CSV外部連携）")
        provider_layout.addWidget(self.none_radio)

        self.local_radio = QRadioButton("ローカル翻訳（オフライン）")
        self.local_radio.setChecked(True)  # デフォルトでローカル翻訳を選択
        provider_layout.addWidget(self.local_radio)

        # モデル設定情報
        info_layout = QHBoxLayout()
        info_label = QLabel("※ 初回実行時にモデルを自動ダウンロードします（約250MB）")
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        provider_layout.addLayout(info_layout)

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

        # 選択された翻訳言語をチェック
        selected_languages = self.get_selected_languages()
        if not selected_languages:
            QMessageBox.warning(
                self,
                "警告",
                "翻訳する言語が選択されていません。\\n言語のチェックボックスを有効にしてください。"
            )
            return

        # ローカル翻訳の確認
        if self.local_radio.isChecked():
            provider_name = "ローカル翻訳（オフライン）"
        else:
            QMessageBox.warning(self, "警告", "翻訳プロバイダが選択されていません。")
            return

        # UI状態を更新
        self.log_text.append(f"{provider_name}を使用して翻訳を開始しています...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.translate_btn.setEnabled(False)
        self.close_btn.setEnabled(False)

        try:
            # モデル保存ディレクトリを作成
            models_dir = Path.home() / ".vlog-subs-tool" / "translation_models"
            models_dir.mkdir(parents=True, exist_ok=True)

            # ローカル翻訳ワーカーを開始
            self.translation_worker = TranslationWorker(
                subtitles=self.subtitles,
                target_languages=selected_languages,
                models_dir=str(models_dir)
            )

            self.translation_worker.progress_updated.connect(self.on_translation_progress)
            self.translation_worker.translation_completed.connect(self.on_translation_completed)
            self.translation_worker.translation_error.connect(self.on_translation_error)
            self.translation_worker.start()

        except Exception as e:
            self.on_translation_error(f"翻訳初期化エラー: {str(e)}")


    def get_selected_languages(self) -> List[str]:
        """選択された翻訳言語一覧を取得"""
        selected = []
        if hasattr(self, 'en_check') and self.en_check.isChecked():
            selected.append('en')
        if hasattr(self, 'zh_check') and self.zh_check.isChecked():
            selected.append('zh')
        if hasattr(self, 'ko_check') and self.ko_check.isChecked():
            selected.append('ko')
        if hasattr(self, 'ar_check') and self.ar_check.isChecked():
            selected.append('ar')
        return selected


    def on_translation_progress(self, message: str, progress: int):
        """翻訳進捗更新"""
        self.log_text.append(message)
        self.progress_bar.setValue(progress)

    def on_translation_completed(self, translations: Dict[str, List]):
        """翻訳完了"""
        self.translated_subtitles = translations
        self.log_text.append("翻訳が正常に完了しました！")

        # UI状態を復元
        self.progress_bar.setVisible(False)
        self.translate_btn.setEnabled(True)
        self.close_btn.setEnabled(True)
        self.save_srt_btn.setEnabled(True)

        # 結果を表示
        total_translations = sum(len(subs) for subs in translations.values())
        self.log_text.append(f"翻訳済み字幕数: {total_translations}件")

        # シグナルを発信
        self.translations_updated.emit(translations)

    def on_translation_error(self, error_message: str):
        """翻訳エラー処理"""
        self.log_text.append(f"エラー: {error_message}")

        # UI状態を復元
        self.progress_bar.setVisible(False)
        self.translate_btn.setEnabled(True)
        self.close_btn.setEnabled(True)

        # 詳細なエラーダイアログを表示
        self.show_translation_error_dialog(error_message)

    def show_translation_error_dialog(self, error_message: str):
        """翻訳エラーダイアログ表示"""
        # エラータイプを判定してユーザー向けガイダンスを表示
        if "API" in error_message or "認証" in error_message:
            title = "API認証エラー"
            guidance = (
                "翻訳APIの認証に失敗しました。\\n\\n"
                "確認事項：\\n"
                "1. APIキーが正しく設定されているか\\n"
                "2. インターネット接続が安定しているか\\n"
                "3. API使用制限に達していないか\\n\\n"
                "設定画面でAPI設定を確認してください。"
            )
        elif "制限" in error_message or "quota" in error_message.lower():
            title = "API制限エラー"
            guidance = (
                "翻訳APIの使用制限に達しました。\\n\\n"
                "対処方法：\\n"
                "1. しばらく時間をおいてから再試行\\n"
                "2. 一度に翻訳する字幕数を減らす\\n"
                "3. 有料プランへのアップグレードを検討\\n\\n"
                "または、CSV出力で外部翻訳をご利用ください。"
            )
        elif "ネットワーク" in error_message or "接続" in error_message:
            title = "ネットワークエラー"
            guidance = (
                "ネットワーク接続に問題があります。\\n\\n"
                "確認事項：\\n"
                "1. インターネット接続が有効か\\n"
                "2. ファイアウォール設定が適切か\\n"
                "3. プロキシ設定が正しいか\\n\\n"
                "接続を確認してから再試行してください。"
            )
        else:
            title = "翻訳エラー"
            guidance = (
                "翻訳処理中にエラーが発生しました。\\n\\n"
                "対処方法：\\n"
                "1. しばらく時間をおいて再試行\\n"
                "2. 字幕テキストに特殊文字が含まれていないか確認\\n"
                "3. 翻訳する言語数を減らして試行\\n\\n"
                "問題が継続する場合は、CSV出力をご利用ください。"
            )

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(guidance)
        msg_box.setDetailedText(f"詳細エラー情報:\\n{error_message}")
        msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Help)

        # ヘルプボタンで設定画面を開く
        result = msg_box.exec()
        if result == QMessageBox.Help:
            self.open_settings_dialog()
    
    def export_csv(self):
        """CSVに書き出し"""
        if not self.subtitles:
            QMessageBox.warning(self, "警告", "字幕データがありません")
            return
        
        # 選択された言語を取得
        target_langs = self._get_selected_languages()
        if not target_langs:
            QMessageBox.warning(self, "警告", "対象言語が選択されていません")
            return
        
        # ベースディレクトリの選択
        base_dir = QFileDialog.getExistingDirectory(
            self,
            "翻訳ファイル出力先フォルダを選択",
            str(Path.cwd() / "subs")
        )
        
        if not base_dir:
            return
        
        try:
            # プロジェクト名を決定
            project_name = self._get_project_name()
            
            # 翻訳ワークフローを作成
            workflow_manager = TranslationWorkflowManager(Path(base_dir))
            created_files = workflow_manager.create_translation_workflow(
                self.subtitles, project_name, target_langs
            )
            
            # 結果をログに表示
            self.log_text.append("翻訳ワークフローファイルを作成しました:")
            for file_type, file_path in created_files.items():
                self.log_text.append(f"  {file_type}: {file_path.name}")
            
            # 成功メッセージ
            QMessageBox.information(
                self, 
                "完了", 
                f"翻訳用ファイルを作成しました\\n出力先: {base_dir}\\n\\n"
                f"作成されたファイル:\\n" + 
                "\\n".join([f"• {path.name}" for path in created_files.values()])
            )
            
        except Exception as e:
            self.log_text.append(f"エクスポートエラー: {str(e)}")
            QMessageBox.critical(self, "エラー", f"CSVエクスポートに失敗しました:\\n{str(e)}")
    
    def import_csv(self):
        """翻訳済みCSVを取り込み"""
        if not self.subtitles:
            QMessageBox.warning(self, "警告", "元の字幕データがありません\\n先に字幕抽出を行ってください")
            return
        
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "翻訳済みCSVファイルを選択（複数選択可）",
            str(Path.cwd() / "subs"),
            "CSVファイル (*.csv);;すべてのファイル (*)"
        )
        
        if not file_paths:
            return
        
        try:
            importer = SubtitleCSVImporter()
            imported_languages = []
            total_imported = 0
            
            for file_path in file_paths:
                self.log_text.append(f"インポート中: {Path(file_path).name}")
                
                # CSVインポート実行
                result = importer.import_translated_csv(Path(file_path), self.subtitles)
                
                if result.success:
                    self.translated_subtitles[result.language] = result.subtitles
                    imported_languages.append(result.language)
                    total_imported += result.imported_count
                    
                    self.log_text.append(f"  ✓ {result.language}: {result.imported_count}件取得")
                    
                    # 警告があれば表示
                    if result.warnings:
                        self.log_text.append(f"  警告: {len(result.warnings)}件")
                        for warning in result.warnings[:3]:  # 最初の3件のみ表示
                            self.log_text.append(f"    {warning}")
                        if len(result.warnings) > 3:
                            self.log_text.append(f"    ...他{len(result.warnings) - 3}件")
                else:
                    self.log_text.append(f"  ✗ インポート失敗: {Path(file_path).name}")
                    for error in result.errors:
                        self.log_text.append(f"    エラー: {error}")
            
            # 結果表示
            if imported_languages:
                self.save_srt_btn.setEnabled(True)
                self.translations_updated.emit(self.translated_subtitles)
                
                QMessageBox.information(
                    self, 
                    "インポート完了", 
                    f"翻訳データを取り込みました\\n\\n"
                    f"言語: {', '.join(imported_languages)}\\n"
                    f"合計字幕数: {total_imported}件\\n\\n"
                    f"「SRT一括保存」で字幕ファイルを生成できます"
                )
            else:
                QMessageBox.warning(self, "警告", "有効な翻訳データが見つかりませんでした")
            
        except Exception as e:
            self.log_text.append(f"インポートエラー: {str(e)}")
            QMessageBox.critical(self, "エラー", f"CSVインポートに失敗しました:\\n{str(e)}")
    
    def save_all_srt(self):
        """全言語のSRTファイルを保存"""
        if not self.translated_subtitles and not self.subtitles:
            QMessageBox.warning(self, "警告", "保存する字幕データがありません")
            return
        
        # 保存先ディレクトリを選択
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "SRTファイル保存先フォルダを選択",
            str(Path.cwd())
        )
        
        if not output_dir:
            return
        
        try:
            formatter = SRTFormatter()
            project_name = self._get_project_name()
            saved_files = []
            
            # 日本語（元データ）を保存
            if self.subtitles:
                ja_path = Path(output_dir) / f"{project_name}.ja.srt"
                if formatter.save_srt_file(self.subtitles, ja_path):
                    saved_files.append(f"ja: {ja_path.name}")
                    self.log_text.append(f"日本語SRT保存: {ja_path.name}")
            
            # 各翻訳言語を保存
            for lang, subtitles in self.translated_subtitles.items():
                if subtitles:
                    srt_path = Path(output_dir) / f"{project_name}.{lang}.srt"
                    if formatter.save_srt_file(subtitles, srt_path):
                        saved_files.append(f"{lang}: {srt_path.name}")
                        self.log_text.append(f"{lang}SRT保存: {srt_path.name}")
            
            if saved_files:
                QMessageBox.information(
                    self,
                    "保存完了",
                    f"SRTファイルを保存しました\\n保存先: {output_dir}\\n\\n"
                    f"保存されたファイル:\\n" + "\\n".join([f"• {file}" for file in saved_files])
                )
            else:
                QMessageBox.warning(self, "警告", "保存できるファイルがありませんでした")
            
        except Exception as e:
            self.log_text.append(f"SRT保存エラー: {str(e)}")
            QMessageBox.critical(self, "エラー", f"SRT保存に失敗しました:\\n{str(e)}")
    
    def _get_selected_languages(self) -> List[str]:
        """選択された言語リストを取得"""
        languages = []
        if self.en_check.isChecked():
            languages.append("en")
        if self.zh_check.isChecked():
            languages.append("zh")
        if self.ko_check.isChecked():
            languages.append("ko")
        if self.ar_check.isChecked():
            languages.append("ar")
        return languages
    
    def _get_project_name(self) -> str:
        """プロジェクト名を取得"""
        if self.project and self.project.settings.video_path:
            return Path(self.project.settings.video_path).stem
        return "subtitles"