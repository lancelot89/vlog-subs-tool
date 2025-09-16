"""
ローカル翻訳機能の基本テスト（依存関係なし）
"""

import unittest
from unittest.mock import Mock, patch
import tempfile
import shutil
from pathlib import Path

from app.core.translate import (
    TranslationProviderRouter,
    TranslationProviderType,
    TranslationResult
)


class TestBasicTranslationProviderRouter(unittest.TestCase):
    """翻訳プロバイダールーターの基本テスト"""

    def setUp(self):
        """テスト準備"""
        self.router = TranslationProviderRouter()

    def test_mock_provider_registration(self):
        """モックプロバイダー登録のテスト"""
        result = self.router.register_provider(TranslationProviderType.MOCK, None)

        self.assertTrue(result)
        self.assertIn(TranslationProviderType.MOCK, self.router.get_available_providers())
        self.assertEqual(self.router.default_provider, TranslationProviderType.MOCK)

    def test_mock_translation(self):
        """モック翻訳のテスト"""
        self.router.register_provider(TranslationProviderType.MOCK, None)

        texts = ["こんにちは", "ありがとう"]
        result = self.router.translate_batch(
            texts=texts,
            target_language="en",
            source_language="ja"
        )

        self.assertTrue(result.success)
        self.assertEqual(result.provider_used, TranslationProviderType.MOCK)
        self.assertEqual(len(result.translated_texts), 2)
        self.assertIn("Hello", result.translated_texts[0])
        self.assertIn("Thank you", result.translated_texts[1])

    def test_empty_text_translation(self):
        """空テキスト翻訳のテスト"""
        self.router.register_provider(TranslationProviderType.MOCK, None)

        result = self.router.translate_batch(
            texts=[],
            target_language="en",
            source_language="ja"
        )

        self.assertTrue(result.success)
        self.assertEqual(len(result.translated_texts), 0)

    def test_provider_availability_check(self):
        """プロバイダー可用性チェックのテスト"""
        # 未登録プロバイダー
        self.assertFalse(self.router.is_provider_available(TranslationProviderType.LOCAL))

        # プロバイダー登録後
        self.router.register_provider(TranslationProviderType.MOCK, None)
        self.assertTrue(self.router.is_provider_available(TranslationProviderType.MOCK))

    def test_supported_languages(self):
        """サポート言語のテスト"""
        self.router.register_provider(TranslationProviderType.MOCK, None)

        languages = self.router.get_supported_languages()

        self.assertIn('ja', languages)
        self.assertIn('en', languages)
        self.assertIn('zh-cn', languages)
        self.assertIn('ar', languages)

    def test_multi_language_translation_workflow(self):
        """多言語翻訳ワークフローテスト"""
        router = TranslationProviderRouter()
        router.register_provider(TranslationProviderType.MOCK, None)

        # 日本語字幕のサンプルデータ
        subtitle_texts = [
            "おはようございます",
            "今日は良い天気ですね",
            "ありがとうございました"
        ]

        # 複数言語への翻訳テスト
        target_languages = ['en', 'zh-cn', 'ar']

        for lang in target_languages:
            with self.subTest(language=lang):
                result = router.translate_batch(
                    texts=subtitle_texts,
                    target_language=lang,
                    source_language="ja"
                )

                self.assertTrue(result.success)
                self.assertEqual(len(result.translated_texts), 3)
                self.assertEqual(result.target_language, lang)
                self.assertEqual(result.provider_used, TranslationProviderType.MOCK)

    def test_fallback_provider_functionality(self):
        """フォールバックプロバイダー機能のテスト"""
        # モックプロバイダーを登録
        self.router.register_provider(TranslationProviderType.MOCK, None)

        # フォールバック設定
        self.router.set_fallback_providers([TranslationProviderType.MOCK])

        # デフォルトプロバイダー設定
        self.router.set_default_provider(TranslationProviderType.MOCK)

        # 翻訳実行
        result = self.router.translate_batch(
            texts=["テスト"],
            target_language="en",
            source_language="ja"
        )

        self.assertTrue(result.success)
        self.assertEqual(result.provider_used, TranslationProviderType.MOCK)

    def test_error_handling_no_providers(self):
        """プロバイダーなしでのエラーハンドリング"""
        # プロバイダーを登録しない状態で翻訳実行
        result = self.router.translate_batch(
            texts=["テスト"],
            target_language="en",
            source_language="ja"
        )

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error_message)

    def test_translation_result_structure(self):
        """翻訳結果構造のテスト"""
        self.router.register_provider(TranslationProviderType.MOCK, None)

        result = self.router.translate_batch(
            texts=["テスト"],
            target_language="en",
            source_language="ja"
        )

        # 結果構造の確認
        self.assertIsInstance(result, TranslationResult)
        self.assertIsInstance(result.translated_texts, list)
        self.assertIsInstance(result.source_language, str)
        self.assertIsInstance(result.target_language, str)
        self.assertIsInstance(result.provider_used, TranslationProviderType)
        self.assertIsInstance(result.success, bool)

        if result.success:
            self.assertEqual(result.source_language, "ja")
            self.assertEqual(result.target_language, "en")
            self.assertIsNone(result.error_message)
        else:
            self.assertIsNotNone(result.error_message)


if __name__ == '__main__':
    unittest.main()