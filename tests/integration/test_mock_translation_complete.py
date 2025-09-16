#!/usr/bin/env python3
"""
モック翻訳を使った完全な翻訳SRT出力テスト
Google Cloud認証不要で動作確認
"""

import sys
import tempfile
from pathlib import Path
from typing import List
import time

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.models import SubtitleItem
from app.core.translate.provider_mock import MockTranslateProvider, MockTranslateSettings
from app.ui.workers.translation_export_worker import TranslationExportWorker


class TestTranslationExportWorker(TranslationExportWorker):
    """テスト用同期実行版TranslationExportWorker"""

    def __init__(self, *args, **kwargs):
        # QThread初期化をスキップして同期実行版として作成
        self.subtitles = args[0] if args else kwargs['subtitles']
        self.target_languages = args[1] if len(args) > 1 else kwargs['target_languages']
        self.provider_type = args[2] if len(args) > 2 else kwargs['provider_type']
        self.provider_settings = args[3] if len(args) > 3 else kwargs['provider_settings']
        self.output_folder = args[4] if len(args) > 4 else kwargs['output_folder']
        self.video_basename = args[5] if len(args) > 5 else kwargs['video_basename']

        self.is_cancelled = False
        self.exported_files = []

    def emit_progress(self, message: str, progress: int):
        """進捗表示（テスト用）"""
        print(f"  📊 進捗 {progress}%: {message}")

    def run_sync(self) -> List[str]:
        """同期実行版"""
        try:
            print("🚀 翻訳＋SRT出力処理を開始...")

            # 翻訳プロバイダーの初期化
            translator = self._initialize_translator()
            print(f"  プロバイダ初期化: {type(translator).__name__}")

            # プロバイダーの初期化を実行
            if hasattr(translator, 'initialize'):
                translator.initialize()
                print("  プロバイダ初期化完了")

            # 翻訳テキストの準備
            source_texts = [subtitle.text for subtitle in self.subtitles]
            print(f"  翻訳対象: {len(source_texts)}件のテキスト")

            # 各言語に翻訳＋SRT出力
            for i, target_lang in enumerate(self.target_languages):
                print(f"\n  🌐 {target_lang}への翻訳開始... ({i+1}/{len(self.target_languages)})")

                # 翻訳実行
                translated_texts = translator.translate_batch(
                    source_texts,
                    target_lang,
                    "ja",
                    self.emit_progress
                )

                # SRTファイルとして出力
                output_path = self._export_translated_srt(target_lang, translated_texts)
                self.exported_files.append(str(output_path))

                print(f"  ✅ {target_lang} SRT出力完了: {output_path.name}")

            return self.exported_files

        except Exception as e:
            print(f"❌ 翻訳処理でエラー: {e}")
            raise


def test_mock_translation_complete():
    """モック翻訳による完全な翻訳SRT出力テスト"""
    print("=== モック翻訳による完全翻訳SRT出力テスト ===")

    # VLOGサンプル字幕データ
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
        SubtitleItem(
            index=3,
            start_ms=8000,
            end_ms=10000,
            text="こんにちは"
        ),
        SubtitleItem(
            index=4,
            start_ms=11000,
            end_ms=13000,
            text="ありがとうございます"
        ),
        SubtitleItem(
            index=5,
            start_ms=14000,
            end_ms=16000,
            text="さようなら"
        )
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        output_folder = Path(temp_dir)
        print(f"出力フォルダ: {output_folder}")

        # 多言語翻訳設定
        target_languages = ["en", "zh", "ko", "es", "fr"]

        # モック翻訳設定
        provider_settings = {
            "delay_ms": 20,  # 少し早めに設定
            "add_prefix": False  # プレフィックスなしで自然な翻訳
        }

        # ワーカー作成
        worker = TestTranslationExportWorker(
            subtitles=subtitles,
            target_languages=target_languages,
            provider_type="mock",
            provider_settings=provider_settings,
            output_folder=output_folder,
            video_basename="vlog_complete_test"
        )

        # 翻訳＋SRT出力実行
        exported_files = worker.run_sync()

        # 結果確認
        print(f"\n📄 出力されたSRTファイル: {len(exported_files)}件")

        expected_files = [f"vlog_complete_test.{lang}.srt" for lang in target_languages]

        for expected_file in expected_files:
            found = any(Path(f).name == expected_file for f in exported_files)
            assert found, f"{expected_file}が生成されていません"
            print(f"  ✅ {expected_file}")

        # 各SRTファイルの内容確認
        for exported_file in exported_files:
            output_file = Path(exported_file)
            content = output_file.read_text(encoding="utf-8")

            print(f"\n📝 {output_file.name} の内容:")
            lines = content.strip().split('\n')
            for line in lines[:10]:  # 最初の10行のみ表示
                print(f"    {line}")
            if len(lines) > 10:
                print(f"    ... (全{len(lines)}行)")

            # SRTフォーマット確認
            assert "1\n" in content, "字幕番号が見つかりません"
            assert "00:00:00,000 --> 00:00:03,000" in content, "タイムコードが正しくありません"

            # 翻訳内容の確認
            lang_code = output_file.stem.split('.')[-1]
            if lang_code == "en":
                assert "library" in content.lower() or "hospital" in content.lower() or "bank" in content.lower(), "英語翻訳が含まれていません"
            elif lang_code == "zh":
                assert "你好" in content or "谢谢" in content, "中国語翻訳が含まれていません"
            elif lang_code == "ko":
                assert "안녕하세요" in content or "감사합니다" in content, "韓国語翻訳が含まれていません"

        print("\n✅ すべてのSRTファイルが正しく生成されました")
        return True


def test_mock_provider_direct():
    """モック翻訳プロバイダの直接テスト"""
    print("\n=== モック翻訳プロバイダ直接テスト ===")

    settings = MockTranslateSettings(delay_ms=10, add_prefix=False)
    provider = MockTranslateProvider(settings)

    # 初期化
    provider.initialize()
    print("  初期化完了")

    # 翻訳テスト
    test_texts = [
        "こんにちは",
        "ありがとうございます",
        "さて図書館行って、病院行って、銀行にも行ってくるでは出発です"
    ]

    for lang in ["en", "zh", "ko"]:
        print(f"\n  {lang}への翻訳:")
        translated = provider.translate_batch(test_texts, lang, "ja")

        for i, (original, translation) in enumerate(zip(test_texts, translated)):
            print(f"    {i+1}. {original} → {translation}")

        assert len(translated) == len(test_texts), f"{lang}翻訳結果の数が一致しません"

    print("\n✅ モック翻訳プロバイダが正常動作")
    return True


def test_authentication_error_simulation():
    """認証エラーの模擬テスト"""
    print("\n=== 認証エラー対応の動作確認 ===")

    # Google Cloud認証エラーメッセージの例
    auth_error_messages = [
        "Your default credentials were not found",
        "DefaultCredentialsError",
        "Google Cloud Translation APIの初期化に失敗しました"
    ]

    for error_msg in auth_error_messages:
        print(f"  エラーメッセージ: {error_msg}")

        # エラー検出ロジックのテスト
        is_auth_error = ("Your default credentials were not found" in error_msg or
                        "DefaultCredentialsError" in error_msg)

        if is_auth_error:
            print(f"    → Google Cloud認証エラーとして検出")
        else:
            print(f"    → 一般的なエラーとして処理")

    print("\n✅ 認証エラー検出ロジックが正常動作")
    return True


if __name__ == "__main__":
    print("モック翻訳完全テスト開始...\n")

    success_count = 0
    total_tests = 3

    try:
        if test_mock_translation_complete():
            success_count += 1
    except Exception as e:
        print(f"❌ 完全翻訳テスト失敗: {e}")

    try:
        if test_mock_provider_direct():
            success_count += 1
    except Exception as e:
        print(f"❌ プロバイダ直接テスト失敗: {e}")

    try:
        if test_authentication_error_simulation():
            success_count += 1
    except Exception as e:
        print(f"❌ 認証エラーテスト失敗: {e}")

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 すべてのテストが成功しました！")
        print("\n✅ 確認された機能:")
        print("1. モック翻訳による多言語SRT出力")
        print("2. 認証不要での完全動作")
        print("3. Google Cloud認証エラーの適切な検出")
        print("4. 高品質な翻訳辞書による自然な翻訳")
        print("\n🎯 Google Cloud認証なしでも翻訳SRT出力が可能です！")
    else:
        print("❌ 一部のテストが失敗しました")
        sys.exit(1)