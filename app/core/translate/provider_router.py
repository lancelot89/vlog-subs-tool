"""
翻訳プロバイダールーター
複数の翻訳プロバイダー（Google、DeepL、ローカル）を統一インターフェースで管理
"""

import logging
from enum import Enum
from typing import List, Dict, Optional, Callable, Any, Union
from dataclasses import dataclass

from .provider_local import LocalTranslateProvider, LocalTranslateSettings, LocalTranslateError


class TranslationProviderType(Enum):
    """翻訳プロバイダータイプ"""
    LOCAL = "local"
    MOCK = "mock"  # テスト用


@dataclass
class TranslationResult:
    """翻訳結果"""
    translated_texts: List[str]
    source_language: str
    target_language: str
    provider_used: TranslationProviderType
    success: bool
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None


class TranslationError(Exception):
    """翻訳関連エラー"""

    def __init__(self, message: str, provider: TranslationProviderType, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.provider = provider
        self.original_error = original_error


class MockTranslateProvider:
    """テスト用モック翻訳プロバイダー"""

    def __init__(self):
        self.is_initialized = True

    def initialize(self) -> bool:
        return True

    def translate_batch(
        self,
        texts: List[str],
        target_language: str,
        source_language: str = "ja",
        progress_callback: Optional[Callable[[str, int], None]] = None
    ) -> List[str]:
        """モック翻訳（テスト用）"""
        if progress_callback:
            progress_callback("モック翻訳中...", 50)
            progress_callback("モック翻訳完了", 100)

        # 簡単な置換ベースのモック翻訳
        mock_translations = []
        for text in texts:
            if target_language == "en":
                # 日本語 -> 英語のモック
                mock_text = text.replace("こんにちは", "Hello").replace("ありがとう", "Thank you")
                if mock_text == text:  # 変更がなかった場合
                    mock_text = f"[EN] {text}"
            elif target_language == "ja":
                # 英語 -> 日本語のモック
                mock_text = text.replace("Hello", "こんにちは").replace("Thank you", "ありがとう")
                if mock_text == text:  # 変更がなかった場合
                    mock_text = f"[JA] {text}"
            else:
                # その他の言語
                mock_text = f"[{target_language.upper()}] {text}"

            mock_translations.append(mock_text)

        return mock_translations

    def get_supported_languages(self) -> Dict[str, str]:
        return {
            'ja': '日本語',
            'en': 'English',
            'zh-cn': '中文（简体）',
            'ar': 'العربية',
        }

    def is_language_supported(self, lang_code: str) -> bool:
        return lang_code in self.get_supported_languages()


class TranslationProviderRouter:
    """翻訳プロバイダールーター"""

    def __init__(self):
        self.providers: Dict[TranslationProviderType, Any] = {}
        self.provider_settings: Dict[TranslationProviderType, Any] = {}
        self.default_provider: Optional[TranslationProviderType] = None
        self.fallback_providers: List[TranslationProviderType] = []

    def register_provider(self, provider_type: TranslationProviderType, settings: Any) -> bool:
        """翻訳プロバイダーを登録"""
        try:
            provider = None

            if provider_type == TranslationProviderType.LOCAL:
                provider = LocalTranslateProvider(settings)
            elif provider_type == TranslationProviderType.MOCK:
                provider = MockTranslateProvider()
            else:
                raise ValueError(f"未対応のプロバイダータイプ: {provider_type}")

            # 初期化を試行
            if provider.initialize():
                self.providers[provider_type] = provider
                self.provider_settings[provider_type] = settings

                # デフォルトプロバイダーが未設定の場合は最初のプロバイダーを設定
                if self.default_provider is None:
                    self.default_provider = provider_type

                logging.info(f"翻訳プロバイダー登録完了: {provider_type.value}")
                return True
            else:
                logging.warning(f"翻訳プロバイダーの初期化に失敗: {provider_type.value}")
                return False

        except Exception as e:
            logging.error(f"翻訳プロバイダー登録エラー ({provider_type.value}): {e}")
            return False

    def set_default_provider(self, provider_type: TranslationProviderType):
        """デフォルト翻訳プロバイダーを設定"""
        if provider_type in self.providers:
            self.default_provider = provider_type
            logging.info(f"デフォルト翻訳プロバイダー設定: {provider_type.value}")
        else:
            raise ValueError(f"未登録のプロバイダー: {provider_type.value}")

    def set_fallback_providers(self, providers: List[TranslationProviderType]):
        """フォールバックプロバイダーを設定"""
        valid_providers = [p for p in providers if p in self.providers]
        self.fallback_providers = valid_providers
        logging.info(f"フォールバック翻訳プロバイダー設定: {[p.value for p in valid_providers]}")

    def get_available_providers(self) -> List[TranslationProviderType]:
        """利用可能なプロバイダー一覧を取得"""
        return list(self.providers.keys())

    def is_provider_available(self, provider_type: TranslationProviderType) -> bool:
        """プロバイダーが利用可能かチェック"""
        return provider_type in self.providers and self.providers[provider_type].is_initialized

    def translate_batch(
        self,
        texts: List[str],
        target_language: str,
        source_language: Optional[str] = None,
        provider_type: Optional[TranslationProviderType] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None
    ) -> TranslationResult:
        """バッチ翻訳実行"""
        if not texts:
            return TranslationResult(
                translated_texts=[],
                source_language=source_language or "unknown",
                target_language=target_language,
                provider_used=TranslationProviderType.MOCK,
                success=True
            )

        # 使用するプロバイダーを決定
        providers_to_try = []

        if provider_type is not None:
            # 指定されたプロバイダーを最優先
            providers_to_try.append(provider_type)
        elif self.default_provider is not None:
            # デフォルトプロバイダーを最優先
            providers_to_try.append(self.default_provider)

        # フォールバックプロバイダーを追加
        providers_to_try.extend(self.fallback_providers)

        # 利用可能なすべてのプロバイダーを追加（最後の手段）
        for provider in self.providers.keys():
            if provider not in providers_to_try:
                providers_to_try.append(provider)

        # 翻訳を試行
        last_error = None

        for provider in providers_to_try:
            if not self.is_provider_available(provider):
                continue

            try:
                if progress_callback:
                    progress_callback(f"{provider.value}で翻訳中...", 0)

                provider_instance = self.providers[provider]
                translated_texts = provider_instance.translate_batch(
                    texts=texts,
                    target_language=target_language,
                    source_language=source_language,
                    progress_callback=progress_callback
                )

                # 成功
                return TranslationResult(
                    translated_texts=translated_texts,
                    source_language=source_language or "auto-detected",
                    target_language=target_language,
                    provider_used=provider,
                    success=True,
                    metadata={
                        'provider_settings': self.provider_settings.get(provider),
                        'text_count': len(texts)
                    }
                )

            except Exception as e:
                logging.warning(f"翻訳プロバイダー {provider.value} でエラー: {e}")
                last_error = e

                # 次のプロバイダーを試行
                continue

        # すべてのプロバイダーで失敗
        error_message = f"すべての翻訳プロバイダーで失敗しました"
        if last_error:
            error_message += f": {str(last_error)}"

        return TranslationResult(
            translated_texts=[],
            source_language=source_language or "unknown",
            target_language=target_language,
            provider_used=TranslationProviderType.MOCK,  # ダミー値
            success=False,
            error_message=error_message
        )

    def get_supported_languages(self, provider_type: Optional[TranslationProviderType] = None) -> Dict[str, str]:
        """サポートされている言語一覧を取得"""
        if provider_type is not None and provider_type in self.providers:
            return self.providers[provider_type].get_supported_languages()

        # すべてのプロバイダーの共通言語を取得
        if not self.providers:
            return {}

        common_languages = None
        for provider in self.providers.values():
            provider_languages = set(provider.get_supported_languages().keys())
            if common_languages is None:
                common_languages = provider_languages
            else:
                common_languages = common_languages.intersection(provider_languages)

        if common_languages is None:
            return {}

        # 最初のプロバイダーから言語名を取得
        first_provider = next(iter(self.providers.values()))
        all_languages = first_provider.get_supported_languages()

        return {lang: name for lang, name in all_languages.items() if lang in common_languages}

    def get_provider_error_guidance(self, provider_type: TranslationProviderType, error: Exception) -> str:
        """プロバイダー固有のエラーガイダンスを取得"""
        if provider_type not in self.providers:
            return f"プロバイダー {provider_type.value} は利用できません"

        provider = self.providers[provider_type]

        # プロバイダー固有のエラーガイダンスがある場合は使用
        if hasattr(provider, 'get_error_guidance'):
            return provider.get_error_guidance(error)

        return f"翻訳エラー ({provider_type.value}): {str(error)}"