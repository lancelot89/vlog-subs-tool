"""
DeepL API プロバイダの実装
"""

import logging
import requests
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
import time


@dataclass
class DeepLSettings:
    """DeepL設定"""
    api_key: str
    formality: Optional[str] = None  # "formal" | "informal" | None
    use_pro_api: bool = False  # False=Free API, True=Pro API


class DeepLError(Exception):
    """DeepL関連エラー"""

    def __init__(self, message: str, error_code: str = "", status_code: int = 0, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.original_error = original_error


class DeepLProvider:
    """DeepL APIプロバイダ"""

    def __init__(self, settings: DeepLSettings):
        self.settings = settings
        self.is_initialized = False

        # API エンドポイント
        if settings.use_pro_api:
            self.base_url = "https://api.deepl.com/v2"
        else:
            self.base_url = "https://api-free.deepl.com/v2"

        # セッション
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"DeepL-Auth-Key {settings.api_key}",
            "Content-Type": "application/json"
        })

    def initialize(self) -> bool:
        """初期化"""
        try:
            # API接続テスト（使用量確認）
            self._test_connection()

            self.is_initialized = True
            logging.info("DeepL APIの初期化が完了しました")
            return True

        except DeepLError:
            raise
        except Exception as e:
            raise DeepLError(
                f"DeepL APIの初期化に失敗しました: {str(e)}",
                "INIT_FAILED",
                original_error=e
            )

    def _test_connection(self):
        """接続テスト"""
        try:
            response = self.session.get(f"{self.base_url}/usage")

            if response.status_code == 200:
                usage_data = response.json()
                character_limit = usage_data.get('character_limit', 0)
                character_count = usage_data.get('character_count', 0)

                logging.info(f"DeepL API接続成功 - 使用量: {character_count}/{character_limit}")

                # 使用量チェック
                if character_limit > 0 and character_count >= character_limit:
                    raise DeepLError(
                        "DeepL APIの月間文字制限に達しています。制限がリセットされるまでお待ちください。",
                        "QUOTA_EXCEEDED",
                        429
                    )

            elif response.status_code == 403:
                raise DeepLError(
                    "DeepL API キーが無効です。正しいAPIキーを設定してください。",
                    "INVALID_API_KEY",
                    403
                )
            elif response.status_code == 456:
                raise DeepLError(
                    "DeepL APIの月間文字制限に達しています。制限がリセットされるまでお待ちください。",
                    "QUOTA_EXCEEDED",
                    456
                )
            else:
                raise DeepLError(
                    f"DeepL API接続エラー: HTTP {response.status_code}",
                    "CONNECTION_FAILED",
                    response.status_code
                )

        except requests.exceptions.ConnectionError as e:
            raise DeepLError(
                "インターネット接続を確認してください。DeepL APIサーバーに接続できません。",
                "NETWORK_ERROR",
                original_error=e
            )
        except requests.exceptions.Timeout as e:
            raise DeepLError(
                "DeepL APIのリクエストがタイムアウトしました。しばらく時間をおいて再試行してください。",
                "TIMEOUT",
                original_error=e
            )

    def translate_batch(
        self,
        texts: List[str],
        target_language: str,
        source_language: str = "ja",
        progress_callback: Optional[Callable[[str, int], None]] = None
    ) -> List[str]:
        """バッチ翻訳実行"""
        if not self.is_initialized:
            raise DeepLError("プロバイダが初期化されていません", "NOT_INITIALIZED")

        if not texts:
            return []

        try:
            translated_texts = []

            # DeepL APIはバッチサイズに制限があるため分割処理
            batch_size = 50
            total_batches = (len(texts) + batch_size - 1) // batch_size

            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_num = i // batch_size + 1

                if progress_callback:
                    progress_callback(
                        f"翻訳中... ({batch_num}/{total_batches})",
                        int(batch_num * 100 / total_batches)
                    )

                # 翻訳リクエスト
                batch_result = self._translate_batch_request(
                    batch_texts,
                    target_language,
                    source_language
                )
                translated_texts.extend(batch_result)

                # レート制限対策（短い間隔を置く）
                if batch_num < total_batches:
                    time.sleep(0.1)

            if progress_callback:
                progress_callback("翻訳完了", 100)

            logging.info(f"DeepL バッチ翻訳完了: {len(texts)}件 -> {target_language}")
            return translated_texts

        except DeepLError:
            raise
        except Exception as e:
            raise DeepLError(
                f"翻訳中にエラーが発生しました: {str(e)}",
                "TRANSLATION_FAILED",
                original_error=e
            )

    def _translate_batch_request(self, texts: List[str], target_language: str, source_language: str) -> List[str]:
        """単一バッチの翻訳リクエスト"""
        # DeepL言語コード変換
        target_lang = self._convert_language_code(target_language)
        source_lang = self._convert_language_code(source_language)

        # リクエストデータ
        data = {
            "text": texts,
            "target_lang": target_lang,
            "source_lang": source_lang
        }

        # フォーマリティ設定
        if self.settings.formality and target_lang in ["DE", "FR", "IT", "ES", "NL", "PL", "PT", "RU"]:
            data["formality"] = self.settings.formality

        try:
            response = self.session.post(
                f"{self.base_url}/translate",
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                translations = result.get("translations", [])
                return [t["text"] for t in translations]

            elif response.status_code == 400:
                raise DeepLError(
                    "翻訳リクエストのパラメータが無効です。言語コードやテキストを確認してください。",
                    "INVALID_PARAMS",
                    400
                )
            elif response.status_code == 403:
                raise DeepLError(
                    "DeepL API キーが無効です。正しいAPIキーを設定してください。",
                    "INVALID_API_KEY",
                    403
                )
            elif response.status_code == 413:
                raise DeepLError(
                    "翻訳テキストが長すぎます。テキストを分割して再試行してください。",
                    "TEXT_TOO_LONG",
                    413
                )
            elif response.status_code == 456:
                raise DeepLError(
                    "DeepL APIの月間文字制限に達しています。制限がリセットされるまでお待ちください。",
                    "QUOTA_EXCEEDED",
                    456
                )
            elif response.status_code == 429:
                raise DeepLError(
                    "DeepL APIのレート制限に達しました。しばらく時間をおいて再試行してください。",
                    "RATE_LIMITED",
                    429
                )
            else:
                raise DeepLError(
                    f"DeepL API翻訳エラー: HTTP {response.status_code}",
                    "TRANSLATION_FAILED",
                    response.status_code
                )

        except requests.exceptions.ConnectionError as e:
            raise DeepLError(
                "インターネット接続を確認してください。",
                "NETWORK_ERROR",
                original_error=e
            )
        except requests.exceptions.Timeout as e:
            raise DeepLError(
                "リクエストがタイムアウトしました。しばらく時間をおいて再試行してください。",
                "TIMEOUT",
                original_error=e
            )

    def _convert_language_code(self, lang_code: str) -> str:
        """言語コードをDeepL形式に変換"""
        # 標準的な言語コードをDeepL APIの形式に変換
        conversion_map = {
            "ja": "JA",
            "en": "EN",
            "zh": "ZH",
            "ko": "KO",
            "ar": "AR",
            "de": "DE",
            "fr": "FR",
            "it": "IT",
            "es": "ES",
            "pt": "PT",
            "ru": "RU",
            "nl": "NL",
            "pl": "PL",
            "sv": "SV",
            "da": "DA",
            "fi": "FI",
            "no": "NB",
        }

        return conversion_map.get(lang_code.lower(), lang_code.upper())

    def get_supported_languages(self) -> Dict[str, str]:
        """サポートされている言語一覧を取得"""
        try:
            # ソース言語
            source_response = self.session.get(f"{self.base_url}/languages?type=source")
            # ターゲット言語
            target_response = self.session.get(f"{self.base_url}/languages?type=target")

            languages = {}

            if source_response.status_code == 200:
                for lang in source_response.json():
                    languages[lang["language"].lower()] = lang["name"]

            if target_response.status_code == 200:
                for lang in target_response.json():
                    languages[lang["language"].lower()] = lang["name"]

            return languages

        except Exception as e:
            raise DeepLError(
                f"サポート言語の取得に失敗しました: {str(e)}",
                "LANGUAGE_LIST_FAILED",
                original_error=e
            )

    def get_error_guidance(self, error: DeepLError) -> str:
        """エラー種別に応じたユーザ向けガイダンス"""
        guidance_map = {
            "INVALID_API_KEY": (
                "DeepL API キーが無効です。\n\n"
                "解決方法：\n"
                "1. DeepL APIのウェブサイトでアカウントを確認\n"
                "2. 正しいAPIキーをコピーして設定画面で更新\n"
                "3. Free版とPro版でAPIキー形式が異なることに注意"
            ),
            "QUOTA_EXCEEDED": (
                "DeepL APIの月間文字制限に達しています。\n\n"
                "解決方法：\n"
                "1. 月末まで待って制限リセット後に再試行\n"
                "2. DeepL Pro版への升級を検討\n"
                "3. 一時的にGoogle Translateを使用"
            ),
            "RATE_LIMITED": (
                "DeepL APIのレート制限に達しました。\n\n"
                "解決方法：\n"
                "1. 5-10分間待ってから再試行\n"
                "2. 翻訳テキストを小分けにして処理\n"
                "3. DeepL Pro版の利用を検討（レート制限が緩い）"
            ),
            "NETWORK_ERROR": (
                "ネットワーク接続エラーが発生しました。\n\n"
                "解決方法：\n"
                "1. インターネット接続を確認\n"
                "2. ファイアウォールやプロキシ設定を確認\n"
                "3. しばらく時間をおいて再試行"
            ),
            "TIMEOUT": (
                "DeepL APIのリクエストがタイムアウトしました。\n\n"
                "解決方法：\n"
                "1. しばらく時間をおいて再試行\n"
                "2. 翻訳テキスト数を減らして再実行\n"
                "3. インターネット接続速度を確認"
            ),
            "INVALID_PARAMS": (
                "翻訳パラメータが無効です。\n\n"
                "解決方法：\n"
                "1. 言語コードが正しいか確認\n"
                "2. 空のテキストが含まれていないか確認\n"
                "3. 特殊文字や制御文字を除去してから再試行"
            ),
            "TEXT_TOO_LONG": (
                "翻訳テキストが長すぎます。\n\n"
                "解決方法：\n"
                "1. 字幕テキストを短く分割\n"
                "2. 不要な空白や改行を削除\n"
                "3. バッチサイズを小さくして処理"
            ),
        }

        return guidance_map.get(error.error_code, f"予期しないエラーが発生しました：{str(error)}")