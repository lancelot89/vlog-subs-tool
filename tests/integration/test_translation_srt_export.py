#!/usr/bin/env python3
"""
翻訳SRT出力の統合テスト
実際のSRTファイル出力を確認
"""

import sys
import tempfile
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import time

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.models import SubtitleItem
from app.core.format.srt import SRTFormatter, SRTFormatSettings


# モック翻訳プロバイダ（Google Translateの代替）
class MockTranslateProvider:
    """テスト用翻訳プロバイダ"""

    def __init__(self, settings):
        self.settings = settings
        self.is_initialized = True  # モックなので常に初期化済み

    def initialize(self) -> bool:
        """初期化（モック）"""
        self.is_initialized = True
        return True

    def translate_batch(
        self,
        texts: List[str],
        target_language: str,
        source_language: str = "ja",
        progress_callback=None
    ) -> List[str]:
        """バッチ翻訳（モック）"""
        if not self.is_initialized:
            raise Exception("プロバイダが初期化されていません")

        # 翻訳の模擬
        translated_texts = []

        # 言語別の翻訳パターン
        translation_patterns = {
            "en": self._translate_to_english,
            "zh": self._translate_to_chinese,
            "ko": self._translate_to_korean,
            "es": self._translate_to_spanish,
            "fr": self._translate_to_french,
        }

        translate_func = translation_patterns.get(target_language, self._translate_generic)

        total_texts = len(texts)
        for i, text in enumerate(texts):
            if progress_callback:
                progress = int((i * 100) / total_texts)
                progress_callback(f"翻訳中 {i+1}/{total_texts}", progress)

            translated_text = translate_func(text)
            translated_texts.append(translated_text)

            # 実際のAPIコール時間を模擬
            time.sleep(0.01)

        if progress_callback:
            progress_callback("翻訳完了", 100)

        return translated_texts

    def _translate_to_english(self, text: str) -> str:
        """英語翻訳の模擬"""
        translations = {
            "こんにちは": "Hello",
            "さようなら": "Goodbye",
            "ありがとう": "Thank you",
            "おはよう": "Good morning",
            "こんばんは": "Good evening",
            "さて図書館行って、病院行って、銀行にも行ってくるでは出発です": "Well, I'll go to the library, hospital, and bank. Let's go!",
            "汗だくで帰宅しました、シャワー浴びてきたのでスッキリ": "I came home sweaty, but I feel refreshed after taking a shower"
        }
        return translations.get(text, f"[EN] {text}")

    def _translate_to_chinese(self, text: str) -> str:
        """中国語翻訳の模擬"""
        translations = {
            "こんにちは": "你好",
            "さようなら": "再见",
            "ありがとう": "谢谢",
            "おはよう": "早上好",
            "こんばんは": "晚上好"
        }
        return translations.get(text, f"[ZH] {text}")

    def _translate_to_korean(self, text: str) -> str:
        """韓国語翻訳の模擬"""
        translations = {
            "こんにちは": "안녕하세요",
            "さようなら": "안녕히 가세요",
            "ありがとう": "감사합니다",
            "おはよう": "좋은 아침입니다",
            "こんばんは": "안녕하세요"
        }
        return translations.get(text, f"[KO] {text}")

    def _translate_to_spanish(self, text: str) -> str:
        """スペイン語翻訳の模擬"""
        translations = {
            "こんにちは": "Hola",
            "さようなら": "Adiós",
            "ありがとう": "Gracias",
            "おはよう": "Buenos días",
            "こんばんは": "Buenas noches"
        }
        return translations.get(text, f"[ES] {text}")

    def _translate_to_french(self, text: str) -> str:
        """フランス語翻訳の模擬"""
        translations = {
            "こんにちは": "Bonjour",
            "さようなら": "Au revoir",
            "ありがとう": "Merci",
            "おはよう": "Bonjour",
            "こんばんは": "Bonsoir"
        }
        return translations.get(text, f"[FR] {text}")

    def _translate_generic(self, text: str) -> str:
        """汎用翻訳の模擬"""
        return f"[TRANSLATED] {text}"


# 修正版TranslationExportWorker（モック翻訳プロバイダ使用）
class MockTranslationExportWorker:
    """テスト用翻訳＋SRT出力ワーカー"""

    def __init__(self, subtitles: List[SubtitleItem], target_languages: List[str],
                 provider_type: str, provider_settings: dict, output_folder: Path, video_basename: str):
        self.subtitles = subtitles
        self.target_languages = target_languages
        self.provider_type = provider_type
        self.provider_settings = provider_settings
        self.output_folder = output_folder
        self.video_basename = video_basename
        self.exported_files = []

    def run_sync(self) -> List[str]:
        """同期版の翻訳＋SRT出力実行"""
        try:
            print(f"翻訳処理を開始: {self.target_languages}")

            # 翻訳プロバイダーの初期化
            translator = self._initialize_translator()

            # 翻訳テキストの準備
            source_texts = [subtitle.text for subtitle in self.subtitles]

            # 各言語に翻訳＋SRT出力
            for target_lang in self.target_languages:
                print(f"\n{target_lang}への翻訳を開始...")

                def progress_callback(message: str, progress: int):
                    print(f"  {target_lang}: {message} ({progress}%)")

                # 翻訳実行
                translated_texts = translator.translate_batch(
                    source_texts,
                    target_lang,
                    "ja",
                    progress_callback
                )

                # SRTファイルとして出力
                output_path = self._export_translated_srt(target_lang, translated_texts)
                self.exported_files.append(str(output_path))

                print(f"  {target_lang} SRT出力完了: {output_path}")

            return self.exported_files

        except Exception as e:
            print(f"翻訳処理でエラーが発生: {e}")
            raise

    def _initialize_translator(self):
        """翻訳プロバイダーの初期化"""
        if self.provider_type == "google" or self.provider_type == "mock":
            return MockTranslateProvider(self.provider_settings)
        else:
            raise ValueError(f"未対応の翻訳プロバイダ: {self.provider_type}")

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


def test_single_language_srt_export():
    """単言語SRT出力テスト"""
    print("=== 単言語SRT出力テスト ===")

    # テスト用字幕データ
    subtitles = [
        SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="こんにちは"),
        SubtitleItem(index=2, start_ms=4000, end_ms=6000, text="さようなら"),
        SubtitleItem(index=3, start_ms=7000, end_ms=9000, text="ありがとう")
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        output_folder = Path(temp_dir)
        print(f"出力フォルダ: {output_folder}")

        # ワーカー作成
        worker = MockTranslationExportWorker(
            subtitles=subtitles,
            target_languages=["en"],
            provider_type="mock",
            provider_settings={},
            output_folder=output_folder,
            video_basename="test_video"
        )

        # 翻訳＋SRT出力実行
        exported_files = worker.run_sync()

        # 結果確認
        assert len(exported_files) == 1
        output_file = Path(exported_files[0])
        assert output_file.exists()
        assert output_file.name == "test_video.en.srt"

        # SRTファイルの内容確認
        content = output_file.read_text(encoding="utf-8")
        print(f"\n生成されたSRTファイル内容:\n{content}")

        # 翻訳内容の確認
        assert "Hello" in content
        assert "Goodbye" in content
        assert "Thank you" in content

        print("✅ 単言語SRT出力テスト成功")
        return True


def test_multi_language_srt_export():
    """多言語SRT出力テスト"""
    print("\n=== 多言語SRT出力テスト ===")

    # テスト用字幕データ（実際のVLOGサンプル）
    subtitles = [
        SubtitleItem(
            index=1,
            start_ms=0,
            end_ms=3000,
            text="さて図書館行って、病院行って、銀行にも行ってくるでは出発です"
        ),
        SubtitleItem(
            index=2,
            start_ms=4000,
            end_ms=7000,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ"
        ),
        SubtitleItem(index=3, start_ms=8000, end_ms=10000, text="こんばんは")
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        output_folder = Path(temp_dir)
        print(f"出力フォルダ: {output_folder}")

        # 多言語翻訳設定
        target_languages = ["en", "zh", "ko"]

        # ワーカー作成
        worker = MockTranslationExportWorker(
            subtitles=subtitles,
            target_languages=target_languages,
            provider_type="mock",
            provider_settings={},
            output_folder=output_folder,
            video_basename="vlog_sample"
        )

        # 翻訳＋SRT出力実行
        exported_files = worker.run_sync()

        # 結果確認
        assert len(exported_files) == 3
        expected_files = ["vlog_sample.en.srt", "vlog_sample.zh.srt", "vlog_sample.ko.srt"]

        for expected_file in expected_files:
            found = any(Path(f).name == expected_file for f in exported_files)
            assert found, f"{expected_file}が生成されていません"

        # 各SRTファイルの内容確認
        for exported_file in exported_files:
            output_file = Path(exported_file)
            assert output_file.exists()

            content = output_file.read_text(encoding="utf-8")
            print(f"\n{output_file.name} の内容:")
            print(content[:200] + "..." if len(content) > 200 else content)

            # SRTフォーマットの確認
            assert "1\n" in content  # 字幕番号
            assert "00:00:00,000 --> 00:00:03,000" in content  # タイムコード
            assert "2\n" in content
            assert "00:00:04,000 --> 00:00:07,000" in content

        print("✅ 多言語SRT出力テスト成功")
        return True


def test_provider_initialization_fix():
    """プロバイダ初期化修正の確認テスト"""
    print("\n=== プロバイダ初期化修正確認テスト ===")

    subtitles = [
        SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="テスト")
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        output_folder = Path(temp_dir)

        # 初期化なしでの翻訳実行
        provider = MockTranslateProvider({})
        provider.is_initialized = False  # 初期化フラグをオフ

        try:
            provider.translate_batch(["テスト"], "en")
            assert False, "初期化なしでも翻訳できてしまいました"
        except Exception as e:
            assert "プロバイダが初期化されていません" in str(e)
            print("✅ 初期化チェックが正常に動作")

        # 初期化ありでの翻訳実行
        provider.initialize()
        translated_texts = provider.translate_batch(["テスト"], "en")
        assert len(translated_texts) == 1
        print("✅ 初期化後の翻訳が正常に動作")

        return True


def test_srt_file_structure():
    """出力されるSRTファイルの構造テスト"""
    print("\n=== SRTファイル構造テスト ===")

    subtitles = [
        SubtitleItem(index=1, start_ms=1000, end_ms=2500, text="最初の字幕"),
        SubtitleItem(index=2, start_ms=3000, end_ms=4500, text="2番目の字幕"),
        SubtitleItem(index=3, start_ms=5000, end_ms=7000, text="最後の字幕")
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        output_folder = Path(temp_dir)

        worker = MockTranslationExportWorker(
            subtitles=subtitles,
            target_languages=["en"],
            provider_type="mock",
            provider_settings={},
            output_folder=output_folder,
            video_basename="structure_test"
        )

        exported_files = worker.run_sync()
        output_file = Path(exported_files[0])
        content = output_file.read_text(encoding="utf-8")

        print(f"SRTファイル全内容:\n{content}")

        # SRT構造の詳細確認
        lines = content.strip().split('\n')

        # 1番目の字幕
        assert lines[0] == "1"
        assert lines[1] == "00:00:01,000 --> 00:00:02,500"
        assert "[EN]" in lines[2] or "最初の字幕" in lines[2]

        # 空行
        assert lines[3] == ""

        # 2番目の字幕
        assert lines[4] == "2"
        assert lines[5] == "00:00:03,000 --> 00:00:04,500"

        print("✅ SRTファイル構造が正しく生成されています")
        return True


if __name__ == "__main__":
    print("翻訳SRT出力統合テスト開始...\n")

    success_count = 0
    total_tests = 4

    try:
        if test_single_language_srt_export():
            success_count += 1
    except Exception as e:
        print(f"❌ 単言語SRT出力テスト失敗: {e}")

    try:
        if test_multi_language_srt_export():
            success_count += 1
    except Exception as e:
        print(f"❌ 多言語SRT出力テスト失敗: {e}")

    try:
        if test_provider_initialization_fix():
            success_count += 1
    except Exception as e:
        print(f"❌ プロバイダ初期化テスト失敗: {e}")

    try:
        if test_srt_file_structure():
            success_count += 1
    except Exception as e:
        print(f"❌ SRTファイル構造テスト失敗: {e}")

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 すべてのテストが成功しました！")
        print("\n✅ 確認された機能:")
        print("1. 単言語SRT出力")
        print("2. 多言語SRT出力")
        print("3. プロバイダ初期化チェック")
        print("4. 正しいSRTファイル構造")
        print("\nTranslationExportWorkerの修正が必要な場合は実装を確認してください。")
    else:
        print("❌ 一部のテストが失敗しました")
        sys.exit(1)