"""
Google Cloud Translation API v3プロバイダの実装
"""

import logging
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass

try:
    from google.cloud import translate_v3 as translate
    from google.oauth2 import service_account
    from google.api_core import exceptions as gcp_exceptions
    GOOGLE_TRANSLATE_AVAILABLE = True
except ImportError:
    GOOGLE_TRANSLATE_AVAILABLE = False
    logging.warning("Google Cloud Translate APIが利用できません。pip install google-cloud-translateでインストールしてください。")


@dataclass
class GoogleTranslateSettings:
    """Google Translate設定"""
    project_id: str
    location: str = "global"
    api_key: Optional[str] = None
    service_account_path: Optional[str] = None
    glossary_id: Optional[str] = None
    formality: Optional[str] = None


class GoogleTranslateError(Exception):
    """Google Translate関連エラー"""

    def __init__(self, message: str, error_code: str = "", original_error: Optional[Exception] = None):
        super().__init__(message)
        self.error_code = error_code
        self.original_error = original_error


class GoogleTranslateProvider:
    """Google Cloud Translation v3プロバイダ"""

    def __init__(self, settings: GoogleTranslateSettings):
        self.settings = settings
        self.client: Optional[translate.TranslationServiceClient] = None
        self.is_initialized = False

    def initialize(self) -> bool:
        """初期化"""
        if not GOOGLE_TRANSLATE_AVAILABLE:
            raise GoogleTranslateError("Google Cloud Translate APIがインストールされていません", "PACKAGE_MISSING")

        try:
            # 認証情報の設定
            if self.settings.service_account_path:
                credentials = service_account.Credentials.from_service_account_file(
                    self.settings.service_account_path
                )
                self.client = translate.TranslationServiceClient(credentials=credentials)
            elif self.settings.api_key:
                # API Key認証（環境変数設定が必要）
                self.client = translate.TranslationServiceClient()
            else:
                # デフォルト認証（ADCなど）
                self.client = translate.TranslationServiceClient()

            # 接続テスト
            self._test_connection()

            self.is_initialized = True
            logging.info("Google Cloud Translation APIの初期化が完了しました")
            return True

        except gcp_exceptions.Unauthenticated as e:
            raise GoogleTranslateError(
                "Google Cloud認証に失敗しました。認証情報を確認してください。",
                "AUTH_FAILED",
                e
            )
        except gcp_exceptions.PermissionDenied as e:
            raise GoogleTranslateError(
                "Google Cloud Translation APIへのアクセス権限がありません。",
                "PERMISSION_DENIED",
                e
            )
        except Exception as e:
            raise GoogleTranslateError(
                f"Google Cloud Translation APIの初期化に失敗しました: {str(e)}",
                "INIT_FAILED",
                e
            )

    def _test_connection(self):
        """接続テスト"""
        try:
            # 簡単なテスト翻訳を実行
            parent = f"projects/{self.settings.project_id}/locations/{self.settings.location}"

            request = translate.TranslateTextRequest(
                parent=parent,
                contents=["test"],
                target_language_code="en",
                source_language_code="ja"
            )

            self.client.translate_text(request)
            logging.info("Google Cloud Translation API接続テスト成功")

        except gcp_exceptions.NotFound as e:
            raise GoogleTranslateError(
                f"指定されたプロジェクトまたはロケーションが見つかりません: {self.settings.project_id}/{self.settings.location}",
                "PROJECT_NOT_FOUND",
                e
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
            raise GoogleTranslateError("プロバイダが初期化されていません", "NOT_INITIALIZED")

        if not texts:
            return []

        try:
            parent = f"projects/{self.settings.project_id}/locations/{self.settings.location}"
            translated_texts = []

            # バッチサイズ（Google APIの制限に配慮）
            batch_size = 100
            total_batches = (len(texts) + batch_size - 1) // batch_size

            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_num = i // batch_size + 1

                if progress_callback:
                    progress_callback(
                        f"翻訳中... ({batch_num}/{total_batches})",
                        int(batch_num * 100 / total_batches)
                    )

                # 翻訳リクエスト作成
                request = translate.TranslateTextRequest(
                    parent=parent,
                    contents=batch_texts,
                    target_language_code=target_language,
                    source_language_code=source_language,
                    mime_type="text/plain"
                )

                # Glossaryが設定されている場合
                if self.settings.glossary_id:
                    glossary_config = translate.TranslateTextGlossaryConfig(
                        glossary=f"{parent}/glossaries/{self.settings.glossary_id}"
                    )
                    request.glossary_config = glossary_config

                # 翻訳実行
                response = self.client.translate_text(request)

                # 結果を追加
                for translation in response.translations:
                    translated_texts.append(translation.translated_text)

            if progress_callback:
                progress_callback("翻訳完了", 100)

            logging.info(f"Google Translate バッチ翻訳完了: {len(texts)}件 -> {target_language}")
            return translated_texts

        except gcp_exceptions.ResourceExhausted as e:
            raise GoogleTranslateError(
                "Google Cloud Translation APIのクォータを超過しました。しばらく時間をおいてから再試行してください。",
                "QUOTA_EXCEEDED",
                e
            )
        except gcp_exceptions.InvalidArgument as e:
            raise GoogleTranslateError(
                f"翻訳パラメータが無効です。言語コードなどを確認してください: {target_language}",
                "INVALID_PARAMS",
                e
            )
        except Exception as e:
            raise GoogleTranslateError(
                f"翻訳中にエラーが発生しました: {str(e)}",
                "TRANSLATION_FAILED",
                e
            )

    def get_supported_languages(self) -> Dict[str, str]:
        """サポートされている言語一覧を取得"""
        if not self.is_initialized:
            raise GoogleTranslateError("プロバイダが初期化されていません", "NOT_INITIALIZED")

        try:
            parent = f"projects/{self.settings.project_id}/locations/{self.settings.location}"
            response = self.client.get_supported_languages(parent=parent)

            languages = {}
            for language in response.languages:
                languages[language.language_code] = language.display_name

            return languages

        except Exception as e:
            raise GoogleTranslateError(
                f"サポート言語の取得に失敗しました: {str(e)}",
                "LANGUAGE_LIST_FAILED",
                e
            )

    def get_error_guidance(self, error: GoogleTranslateError) -> str:
        """エラー種別に応じたユーザ向けガイダンス"""
        guidance_map = {
            "PACKAGE_MISSING": (
                "Google Cloud Translation APIパッケージがインストールされていません。\n\n"
                "解決方法：\n"
                "1. コマンドプロンプト/ターミナルを開く\n"
                "2. pip install google-cloud-translate を実行\n"
                "3. アプリケーションを再起動"
            ),
            "AUTH_FAILED": (
                "Google Cloud認証に失敗しました。\n\n"
                "解決方法：\n"
                "1. サービスアカウントキーファイルのパスを確認\n"
                "2. ファイルが存在し、読み取り権限があることを確認\n"
                "3. Google Cloud Consoleで認証情報を再作成"
            ),
            "PERMISSION_DENIED": (
                "Google Cloud Translation APIへのアクセス権限がありません。\n\n"
                "解決方法：\n"
                "1. Google Cloud ConsoleでTranslation APIが有効化されているか確認\n"
                "2. サービスアカウントにTranslation API使用権限があるか確認\n"
                "3. 課金アカウントが設定されているか確認"
            ),
            "PROJECT_NOT_FOUND": (
                "指定されたGoogle Cloudプロジェクトまたはロケーションが見つかりません。\n\n"
                "解決方法：\n"
                "1. プロジェクトIDが正しいか確認\n"
                "2. ロケーション設定を確認（通常は'global'）\n"
                "3. Google Cloud Consoleでプロジェクトが存在するか確認"
            ),
            "QUOTA_EXCEEDED": (
                "Google Cloud Translation APIのクォータを超過しました。\n\n"
                "解決方法：\n"
                "1. しばらく時間をおいてから再試行\n"
                "2. Google Cloud Consoleでクォータ使用量を確認\n"
                "3. 必要に応じてクォータの増量を申請"
            ),
            "INVALID_PARAMS": (
                "翻訳パラメータが無効です。\n\n"
                "解決方法：\n"
                "1. 言語コードが正しいか確認（例：ja, en, zh）\n"
                "2. テキストが空でないか確認\n"
                "3. 特殊文字や制御文字が含まれていないか確認"
            ),
        }

        return guidance_map.get(error.error_code, f"予期しないエラーが発生しました：{str(error)}")