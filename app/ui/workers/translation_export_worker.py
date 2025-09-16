"""
翻訳＋SRT出力ワーカー
Google翻訳による一括翻訳と多言語SRT出力を並行処理
"""

from PySide6.QtCore import QThread, Signal
from pathlib import Path
from typing import List, Dict, Optional
import concurrent.futures
import threading
import traceback

from app.core.models import SubtitleItem
from app.core.format.srt import SRTFormatter, SRTFormatSettings
from app.core.translate.provider_google import GoogleTranslateProvider, GoogleTranslateSettings, GoogleTranslateError
from app.core.translate.provider_deepl import DeepLProvider, DeepLSettings, DeepLError


class TranslationExportWorker(QThread):
    """翻訳＋SRT出力バックグラウンドワーカー"""

    # シグナル定義
    progress_updated = Signal(str, int)  # message, progress_percent
    export_completed = Signal(list)  # exported_file_paths
    export_error = Signal(str)  # error_message

    def __init__(self, subtitles: List[SubtitleItem], target_languages: List[str],
                 provider_type: str, provider_settings: dict, output_folder: Path, video_basename: str):
        super().__init__()
        self.subtitles = subtitles
        self.target_languages = target_languages
        self.provider_type = provider_type
        self.provider_settings = provider_settings
        self.output_folder = output_folder
        self.video_basename = video_basename

        # 内部状態
        self.is_cancelled = False
        self.current_progress = 0
        self.exported_files = []

        # スレッドセーフな進捗管理
        self.progress_lock = threading.Lock()

    def cancel(self):
        """処理のキャンセル"""
        self.is_cancelled = True

    def run(self):
        """翻訳＋SRT出力の実行"""
        try:
            self.progress_updated.emit("翻訳処理を初期化中...", 0)

            # 翻訳プロバイダーの初期化
            translator = self._initialize_translator()

            # プロバイダーの初期化を実行
            if hasattr(translator, 'initialize'):
                translator.initialize()

            # 翻訳テキストの準備
            source_texts = [subtitle.text for subtitle in self.subtitles]

            if self.is_cancelled:
                return

            # 同時翻訳数を制限（APIクォータ対策）
            max_concurrent = min(3, len(self.target_languages))

            # 並行翻訳処理
            self._translate_and_export_parallel(translator, source_texts, max_concurrent)

            if not self.is_cancelled:
                self.export_completed.emit(self.exported_files)

        except Exception as e:
            error_message = f"翻訳処理でエラーが発生しました:\n{str(e)}\n\n{traceback.format_exc()}"
            self.export_error.emit(error_message)

    def _initialize_translator(self):
        """翻訳プロバイダーの初期化"""
        if self.provider_type == "google":
            settings = GoogleTranslateSettings(
                project_id=self.provider_settings.get("project_id", ""),
                service_account_path=self.provider_settings.get("service_account_path", ""),
                glossary_id=self.provider_settings.get("glossary_id")
            )
            return GoogleTranslateProvider(settings)

        elif self.provider_type == "deepl":
            settings = DeepLSettings(
                api_key=self.provider_settings.get("api_key", ""),
                use_pro_api=self.provider_settings.get("use_pro", False)
            )
            return DeepLProvider(settings)

        else:
            raise ValueError(f"未対応の翻訳プロバイダ: {self.provider_type}")

    def _translate_and_export_parallel(self, translator, source_texts: List[str], max_concurrent: int):
        """並行翻訳＋SRT出力処理"""
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            # 各言語の翻訳タスクをサブミット
            future_to_language = {}

            for target_lang in self.target_languages:
                if self.is_cancelled:
                    break

                future = executor.submit(
                    self._translate_single_language,
                    translator, source_texts, target_lang
                )
                future_to_language[future] = target_lang

            # 翻訳結果を順次処理
            completed_count = 0
            total_languages = len(self.target_languages)

            for future in concurrent.futures.as_completed(future_to_language):
                if self.is_cancelled:
                    break

                target_lang = future_to_language[future]

                try:
                    # 翻訳結果を取得
                    translated_texts = future.result()

                    # SRTファイルとして出力
                    output_path = self._export_translated_srt(target_lang, translated_texts)
                    self.exported_files.append(str(output_path))

                    # 進捗更新
                    completed_count += 1
                    progress = int((completed_count * 100) / total_languages)

                    with self.progress_lock:
                        self.current_progress = progress
                        self.progress_updated.emit(
                            f"{target_lang} 翻訳完了 ({completed_count}/{total_languages})",
                            progress
                        )

                except Exception as e:
                    # 個別言語のエラーは警告レベルとして処理継続
                    error_msg = f"{target_lang} 翻訳でエラー: {str(e)}"
                    self.progress_updated.emit(error_msg, self.current_progress)

    def _translate_single_language(self, translator, source_texts: List[str], target_lang: str) -> List[str]:
        """単一言語の翻訳処理"""
        def progress_callback(message: str, progress: int):
            if not self.is_cancelled:
                with self.progress_lock:
                    self.progress_updated.emit(f"{target_lang}: {message}", self.current_progress)

        # バッチ翻訳実行
        translated_texts = translator.translate_batch(
            source_texts,
            target_lang,
            "ja",  # ソース言語は日本語
            progress_callback
        )

        return translated_texts

    def _export_translated_srt(self, target_lang: str, translated_texts: List[str]) -> Path:
        """翻訳されたテキストをSRTファイルとして出力"""
        # 出力ファイルパス
        output_filename = f"{self.video_basename}.{target_lang}.srt"
        output_path = self.output_folder / output_filename

        # 翻訳済み字幕アイテムの作成
        translated_subtitles = []
        for i, translated_text in enumerate(translated_texts):
            original_subtitle = self.subtitles[i]
            translated_subtitle = SubtitleItem(
                index=original_subtitle.index,
                start_ms=original_subtitle.start_ms,
                end_ms=original_subtitle.end_ms,
                text=translated_text,
                bbox=original_subtitle.bbox
            )
            translated_subtitles.append(translated_subtitle)

        # SRTフォーマッタで出力
        settings = SRTFormatSettings(
            encoding="utf-8",
            with_bom=False,
            line_ending="lf",
            max_chars_per_line=42,
            max_lines=2
        )
        formatter = SRTFormatter(settings)

        success = formatter.save_srt_file(translated_subtitles, output_path)

        if not success:
            raise Exception(f"{target_lang} SRTファイルの保存に失敗しました: {output_path}")

        return output_path

    def _handle_translation_error(self, error: Exception, target_lang: str) -> str:
        """翻訳エラーのハンドリング"""
        if isinstance(error, GoogleTranslateError):
            if hasattr(error, 'error_code'):
                if error.error_code == "QUOTA_EXCEEDED":
                    return f"{target_lang}: Google Translate APIクォータを超過しました"
                elif error.error_code == "INVALID_CREDENTIALS":
                    return f"{target_lang}: Google Translate認証情報が無効です"
                elif error.error_code == "NETWORK_ERROR":
                    return f"{target_lang}: ネットワークエラーが発生しました"

        elif isinstance(error, DeepLError):
            if hasattr(error, 'error_code'):
                if error.error_code == "QUOTA_EXCEEDED":
                    return f"{target_lang}: DeepL APIクォータを超過しました"
                elif error.error_code == "AUTH_KEY_INVALID":
                    return f"{target_lang}: DeepL APIキーが無効です"

        # 汎用エラーメッセージ
        return f"{target_lang}: {str(error)}"