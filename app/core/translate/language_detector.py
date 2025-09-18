"""
言語検出機能の実装
"""

import logging
from typing import Optional, List, Dict
from dataclasses import dataclass

try:
    import langdetect
    from langdetect import detect, detect_langs
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    # langdetectは自動言語検出機能でのみ使用され、現在は無効化されているため警告を出力しない


@dataclass
class LanguageDetectionResult:
    """言語検出結果"""
    language: str
    confidence: float
    alternatives: List[Dict[str, float]]


class LanguageDetectionError(Exception):
    """言語検出関連エラー"""
    pass


class LanguageDetector:
    """言語検出器"""

    # サポートされている言語コードのマッピング
    SUPPORTED_LANGUAGES = {
        'ja': 'japanese',
        'en': 'english',
        'zh-cn': 'chinese_simplified',
        'zh-tw': 'chinese_traditional',
        'ar': 'arabic',
        'ko': 'korean',
        'es': 'spanish',
        'fr': 'french',
        'de': 'german',
        'it': 'italian',
        'pt': 'portuguese',
        'ru': 'russian',
        'th': 'thai',
        'vi': 'vietnamese',
    }

    # langdetectの言語コードから内部言語コードへのマッピング
    LANGDETECT_TO_INTERNAL = {
        'ja': 'ja',
        'en': 'en',
        'zh': 'zh-cn',  # デフォルトで簡体中国語
        'ar': 'ar',
        'ko': 'ko',
        'es': 'es',
        'fr': 'fr',
        'de': 'de',
        'it': 'it',
        'pt': 'pt',
        'ru': 'ru',
        'th': 'th',
        'vi': 'vi',
    }

    def __init__(self):
        if not LANGDETECT_AVAILABLE:
            raise LanguageDetectionError("langdetectパッケージがインストールされていません")

        # langdetectの設定
        langdetect.DetectorFactory.seed = 0  # 一貫した結果のため

    def detect_language(self, text: str, min_confidence: float = 0.8) -> Optional[LanguageDetectionResult]:
        """
        テキストの言語を検出

        Args:
            text: 検出対象のテキスト
            min_confidence: 最小信頼度

        Returns:
            検出結果。信頼度が閾値を下回る場合はNone
        """
        if not text or not text.strip():
            return None

        try:
            # 複数の候補を取得
            lang_probs = detect_langs(text)

            if not lang_probs:
                return None

            # 最も確率の高い言語
            top_lang = lang_probs[0]

            # 内部言語コードに変換
            internal_lang = self.LANGDETECT_TO_INTERNAL.get(top_lang.lang)
            if not internal_lang:
                logging.warning(f"未対応の言語コード: {top_lang.lang}")
                return None

            # 信頼度チェック
            if top_lang.prob < min_confidence:
                logging.info(f"言語検出の信頼度が低い: {internal_lang} ({top_lang.prob:.2f})")
                return None

            # 代替候補も内部言語コードに変換
            alternatives = []
            for lang_prob in lang_probs[1:]:
                alt_internal = self.LANGDETECT_TO_INTERNAL.get(lang_prob.lang)
                if alt_internal:
                    alternatives.append({
                        'language': alt_internal,
                        'confidence': lang_prob.prob
                    })

            return LanguageDetectionResult(
                language=internal_lang,
                confidence=top_lang.prob,
                alternatives=alternatives
            )

        except Exception as e:
            logging.error(f"言語検出中にエラー: {e}")
            raise LanguageDetectionError(f"言語検出に失敗しました: {str(e)}")

    def detect_batch(self, texts: List[str], min_confidence: float = 0.8) -> List[Optional[LanguageDetectionResult]]:
        """
        複数のテキストの言語を一括検出

        Args:
            texts: 検出対象のテキストリスト
            min_confidence: 最小信頼度

        Returns:
            検出結果のリスト
        """
        results = []
        for text in texts:
            try:
                result = self.detect_language(text, min_confidence)
                results.append(result)
            except Exception as e:
                logging.error(f"テキスト '{text[:50]}...' の言語検出に失敗: {e}")
                results.append(None)

        return results

    def is_language_supported(self, lang_code: str) -> bool:
        """
        言語がサポートされているかチェック

        Args:
            lang_code: 言語コード

        Returns:
            サポート状況
        """
        return lang_code in self.SUPPORTED_LANGUAGES

    def get_language_name(self, lang_code: str) -> str:
        """
        言語コードから言語名を取得

        Args:
            lang_code: 言語コード

        Returns:
            言語名（未知の場合は言語コードそのまま）
        """
        return self.SUPPORTED_LANGUAGES.get(lang_code, lang_code)

    def detect_chinese_variant(self, text: str) -> str:
        """
        中国語の簡体字/繁体字を判定

        Args:
            text: 中国語テキスト

        Returns:
            'zh-cn' (簡体字) または 'zh-tw' (繁体字)
        """
        # 簡体字特有の文字
        simplified_chars = set('这样会个电脑机种')
        # 繁体字特有の文字
        traditional_chars = set('這樣會個電腦機種')

        simplified_count = sum(1 for char in text if char in simplified_chars)
        traditional_count = sum(1 for char in text if char in traditional_chars)

        # 特徴的な文字の出現に基づいて判定
        if traditional_count > simplified_count:
            return 'zh-tw'
        else:
            return 'zh-cn'