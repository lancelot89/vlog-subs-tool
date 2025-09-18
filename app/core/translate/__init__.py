"""
翻訳システムの統合インターフェース
"""

from .language_detector import (
    LanguageDetectionError,
    LanguageDetectionResult,
    LanguageDetector,
)
from .provider_local import (
    LocalTranslateError,
    LocalTranslateProvider,
    LocalTranslateSettings,
)
from .provider_router import (
    TranslationProviderRouter,
    TranslationProviderType,
    TranslationResult,
)

__all__ = [
    # Router
    "TranslationProviderRouter",
    "TranslationProviderType",
    "TranslationResult",
    # Providers
    "LocalTranslateProvider",
    # Settings
    "LocalTranslateSettings",
    # Errors
    "LocalTranslateError",
    # Language Detection
    "LanguageDetector",
    "LanguageDetectionResult",
    "LanguageDetectionError",
]
