"""
翻訳システムの統合インターフェース
"""

from .provider_router import TranslationProviderRouter, TranslationProviderType, TranslationResult
from .provider_google import GoogleTranslateProvider, GoogleTranslateSettings, GoogleTranslateError
from .provider_deepl import DeepLProvider, DeepLSettings, DeepLError
from .provider_local import LocalTranslateProvider, LocalTranslateSettings, LocalTranslateError
from .language_detector import LanguageDetector, LanguageDetectionResult, LanguageDetectionError

__all__ = [
    # Router
    'TranslationProviderRouter',
    'TranslationProviderType',
    'TranslationResult',

    # Providers
    'GoogleTranslateProvider',
    'DeepLProvider',
    'LocalTranslateProvider',

    # Settings
    'GoogleTranslateSettings',
    'DeepLSettings',
    'LocalTranslateSettings',

    # Errors
    'GoogleTranslateError',
    'DeepLError',
    'LocalTranslateError',

    # Language Detection
    'LanguageDetector',
    'LanguageDetectionResult',
    'LanguageDetectionError',
]