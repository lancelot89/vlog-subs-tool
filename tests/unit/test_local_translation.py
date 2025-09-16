"""
ローカル翻訳機能のテスト
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil
from pathlib import Path

from app.core.translate.provider_local import (
    LocalTranslateProvider,
    LocalTranslateSettings,
    LocalTranslateError,
    ModelManager
)
from app.core.translate.language_detector import (
    LanguageDetector,
    LanguageDetectionResult,
    LanguageDetectionError
)
from app.core.translate.provider_router import (
    TranslationProviderRouter,
    TranslationProviderType,
    TranslationResult
)


class TestLanguageDetector(unittest.TestCase):
    """言語検出機能のテスト"""

    @patch('app.core.translate.language_detector.LANGDETECT_AVAILABLE', True)
    def setUp(self):
        """テスト準備"""
        with patch('langdetect.detect_langs') as mock_detect:
            # モックの設定
            mock_lang_prob = Mock()
            mock_lang_prob.lang = 'ja'
            mock_lang_prob.prob = 0.95
            mock_detect.return_value = [mock_lang_prob]

            self.detector = LanguageDetector()

    @patch('app.core.translate.language_detector.LANGDETECT_AVAILABLE', True)
    @patch('langdetect.detect_langs')
    def test_detect_japanese(self, mock_detect_langs):
        """日本語検出のテスト"""
        # モック設定
        mock_lang = Mock()
        mock_lang.lang = 'ja'
        mock_lang.prob = 0.95
        mock_detect_langs.return_value = [mock_lang]

        # テスト実行
        detector = LanguageDetector()
        result = detector.detect_language("これは日本語のテストです")

        # 検証
        self.assertIsNotNone(result)
        self.assertEqual(result.language, 'ja')
        self.assertEqual(result.confidence, 0.95)

    @patch('app.core.translate.language_detector.LANGDETECT_AVAILABLE', True)
    @patch('langdetect.detect_langs')
    def test_detect_english(self, mock_detect_langs):
        """英語検出のテスト"""
        # モック設定
        mock_lang = Mock()
        mock_lang.lang = 'en'
        mock_lang.prob = 0.90
        mock_detect_langs.return_value = [mock_lang]

        # テスト実行
        detector = LanguageDetector()
        result = detector.detect_language("This is an English test")

        # 検証
        self.assertIsNotNone(result)
        self.assertEqual(result.language, 'en')
        self.assertEqual(result.confidence, 0.90)

    @patch('app.core.translate.language_detector.LANGDETECT_AVAILABLE', True)
    @patch('langdetect.detect_langs')
    def test_low_confidence_detection(self, mock_detect_langs):
        """低い信頼度での検出テスト"""
        # モック設定
        mock_lang = Mock()
        mock_lang.lang = 'ja'
        mock_lang.prob = 0.5  # 低い信頼度
        mock_detect_langs.return_value = [mock_lang]

        # テスト実行
        detector = LanguageDetector()
        result = detector.detect_language("テスト", min_confidence=0.8)

        # 検証（信頼度が低いためNoneが返される）
        self.assertIsNone(result)

    def test_chinese_variant_detection(self):
        """中国語の簡体字/繁体字判定テスト"""
        detector = LanguageDetector()

        # 簡体字
        result_simplified = detector.detect_chinese_variant("这是简体中文")
        self.assertEqual(result_simplified, 'zh-cn')

        # 繁体字
        result_traditional = detector.detect_chinese_variant("這是繁體中文")
        self.assertEqual(result_traditional, 'zh-tw')


class TestModelManager(unittest.TestCase):
    """モデル管理機能のテスト"""

    def setUp(self):
        """テスト準備"""
        self.temp_dir = tempfile.mkdtemp()
        self.model_manager = ModelManager(self.temp_dir)

    def tearDown(self):
        """テスト後処理"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_model_path_generation(self):
        """モデルパス生成のテスト"""
        path = self.model_manager.get_model_path('ja', 'en')
        expected = Path(self.temp_dir) / "ja-en"
        self.assertEqual(path, expected)

    def test_translation_route_direct(self):
        """直接翻訳ルートのテスト"""
        route = self.model_manager.get_translation_route('ja', 'en')
        self.assertEqual(route, [('ja', 'en')])

    def test_translation_route_pivot(self):
        """ピボット翻訳ルートのテスト"""
        route = self.model_manager.get_translation_route('ja', 'ar')
        self.assertEqual(route, [('ja', 'en'), ('en', 'ar')])

    def test_unsupported_language_pair(self):
        """未対応言語ペアのテスト"""
        with self.assertRaises(LocalTranslateError):
            self.model_manager.get_translation_route('fr', 'de')

    def test_model_availability_check(self):
        """モデル可用性チェックのテスト"""
        # 存在しないモデル
        self.assertFalse(self.model_manager.is_model_available('ja', 'en'))

        # モデルディレクトリと設定ファイルを作成
        model_path = self.model_manager.get_model_path('ja', 'en')
        model_path.mkdir(parents=True)
        (model_path / "config.json").touch()

        # 今度は利用可能
        self.assertTrue(self.model_manager.is_model_available('ja', 'en'))


class TestLocalTranslateProvider(unittest.TestCase):
    """ローカル翻訳プロバイダーのテスト"""

    def setUp(self):
        """テスト準備"""
        self.temp_dir = tempfile.mkdtemp()
        self.settings = LocalTranslateSettings(
            models_dir=self.temp_dir,
            max_batch_size=4
        )

    def tearDown(self):
        """テスト後処理"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('app.core.translate.provider_local.CTRANSLATE2_AVAILABLE', True)
    @patch('app.core.translate.provider_local.LanguageDetector')
    def test_initialization(self, mock_detector):
        """初期化のテスト"""
        provider = LocalTranslateProvider(self.settings)

        # 初期化実行
        result = provider.initialize()

        self.assertTrue(result)
        self.assertTrue(provider.is_initialized)

    @patch('app.core.translate.provider_local.CTRANSLATE2_AVAILABLE', False)
    def test_initialization_without_ctranslate2(self):
        """CTranslate2なしでの初期化テスト"""
        provider = LocalTranslateProvider(self.settings)

        with self.assertRaises(LocalTranslateError) as context:
            provider.initialize()

        self.assertEqual(context.exception.error_code, "PACKAGE_MISSING")

    def test_text_preprocessing(self):
        """テキスト前処理のテスト"""
        provider = LocalTranslateProvider(self.settings)

        # 改行と連続空白の正規化
        input_text = "これは\n\rテスト\n  です   。"
        processed = provider._preprocess_text(input_text, 'ja')
        expected = "これは テスト です 。"

        self.assertEqual(processed, expected)

    def test_text_postprocessing_arabic(self):
        """アラビア語後処理のテスト"""
        provider = LocalTranslateProvider(self.settings)

        input_text = "مرحبا"
        processed = provider._postprocess_text(input_text, 'ar')

        # RLM文字（U+200F）が追加されているかチェック
        self.assertTrue(processed.startswith('\u200F'))
        self.assertIn("مرحبا", processed)

    def test_supported_languages(self):
        """サポート言語のテスト"""
        provider = LocalTranslateProvider(self.settings)

        languages = provider.get_supported_languages()

        # 主要言語が含まれているかチェック
        self.assertIn('ja', languages)
        self.assertIn('en', languages)
        self.assertIn('zh-cn', languages)
        self.assertIn('ar', languages)

    def test_language_support_check(self):
        """言語サポートチェックのテスト"""
        provider = LocalTranslateProvider(self.settings)

        self.assertTrue(provider.is_language_supported('ja'))
        self.assertTrue(provider.is_language_supported('en'))
        self.assertFalse(provider.is_language_supported('unknown'))


class TestTranslationProviderRouter(unittest.TestCase):
    """翻訳プロバイダールーターのテスト"""

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
        # モック翻訳の結果をチェック
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

    def test_fallback_provider_functionality(self):
        """フォールバックプロバイダー機能のテスト"""
        # 2つのモックプロバイダーを登録
        self.router.register_provider(TranslationProviderType.MOCK, None)

        # フォールバック設定
        self.router.set_fallback_providers([TranslationProviderType.MOCK])

        # 翻訳実行
        result = self.router.translate_batch(
            texts=["テスト"],
            target_language="en",
            source_language="ja"
        )

        self.assertTrue(result.success)

    def test_supported_languages_aggregation(self):
        """サポート言語集約のテスト"""
        self.router.register_provider(TranslationProviderType.MOCK, None)

        languages = self.router.get_supported_languages()

        self.assertIn('ja', languages)
        self.assertIn('en', languages)

    def test_provider_availability_check(self):
        """プロバイダー可用性チェックのテスト"""
        # 未登録プロバイダー
        self.assertFalse(self.router.is_provider_available(TranslationProviderType.LOCAL))

        # プロバイダー登録後
        self.router.register_provider(TranslationProviderType.MOCK, None)
        self.assertTrue(self.router.is_provider_available(TranslationProviderType.MOCK))


class TestIntegrationScenarios(unittest.TestCase):
    """統合シナリオのテスト"""

    def test_translation_workflow_with_mock(self):
        """モックプロバイダーでの翻訳ワークフローテスト"""
        router = TranslationProviderRouter()
        router.register_provider(TranslationProviderType.MOCK, None)

        # 日本語字幕のサンプルデータ
        subtitle_texts = [
            "おはようございます",
            "今日は良い天気ですね",
            "ありがとうございました"
        ]

        # 英語翻訳
        result = router.translate_batch(
            texts=subtitle_texts,
            target_language="en",
            source_language="ja"
        )

        self.assertTrue(result.success)
        self.assertEqual(len(result.translated_texts), 3)
        self.assertEqual(result.target_language, "en")
        self.assertEqual(result.provider_used, TranslationProviderType.MOCK)

    def test_multi_language_translation(self):
        """多言語翻訳のテスト"""
        router = TranslationProviderRouter()
        router.register_provider(TranslationProviderType.MOCK, None)

        original_text = ["こんにちは世界"]

        # 複数言語への翻訳
        target_languages = ['en', 'zh-cn', 'ar']

        for lang in target_languages:
            result = router.translate_batch(
                texts=original_text,
                target_language=lang,
                source_language="ja"
            )

            self.assertTrue(result.success)
            self.assertEqual(len(result.translated_texts), 1)
            self.assertEqual(result.target_language, lang)


if __name__ == '__main__':
    unittest.main()