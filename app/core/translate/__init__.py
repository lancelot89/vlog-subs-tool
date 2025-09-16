"""
翻訳システムの統合インターフェース
"""

from .provider_router import TranslationProviderRouter, TranslationProviderType, TranslationResult
from .provider_local import LocalTranslateProvider, LocalTranslateSettings, LocalTranslateError
from .language_detector import LanguageDetector, LanguageDetectionResult, LanguageDetectionError

__all__ = [
    # Router
    'TranslationProviderRouter',
    'TranslationProviderType',
    'TranslationResult',

    # Providers
    'LocalTranslateProvider',

    # Settings
    'LocalTranslateSettings',

    # Errors
    'LocalTranslateError',

    # Language Detection
    'LanguageDetector',
    'LanguageDetectionResult',
    'LanguageDetectionError',
]