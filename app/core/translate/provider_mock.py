"""
モック翻訳プロバイダの実装
認証不要でテスト・デモ用途に使用
"""

import logging
import time
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass


@dataclass
class MockTranslateSettings:
    """モック翻訳設定"""
    delay_ms: int = 10  # 翻訳時の遅延（ミリ秒）
    add_prefix: bool = True  # 翻訳結果にプレフィックスを付けるか


class MockTranslateError(Exception):
    """モック翻訳関連エラー"""

    def __init__(self, message: str, error_code: str = "", original_error: Optional[Exception] = None):
        super().__init__(message)
        self.error_code = error_code
        self.original_error = original_error


class MockTranslateProvider:
    """モック翻訳プロバイダ（認証不要）"""

    def __init__(self, settings: MockTranslateSettings):
        self.settings = settings
        self.is_initialized = False

        # 高品質な翻訳例辞書
        self.translation_dict = {
            "en": {
                "こんにちは": "Hello",
                "さようなら": "Goodbye",
                "ありがとう": "Thank you",
                "ありがとうございます": "Thank you very much",
                "おはよう": "Good morning",
                "おはようございます": "Good morning",
                "こんばんは": "Good evening",
                "おやすみなさい": "Good night",
                "すみません": "Excuse me",
                "はじめまして": "Nice to meet you",
                "お疲れさまでした": "Good work",
                "いただきます": "Let's eat",
                "ごちそうさまでした": "Thank you for the meal",
                "さて図書館行って、病院行って、銀行にも行ってくるでは出発です": "Well, I'll go to the library, hospital, and bank. Let's go!",
                "汗だくで帰宅しました、シャワー浴びてきたのでスッキリ": "I came home sweaty, but I feel refreshed after taking a shower",
                "凍らせた水持って出かけたけど真夏の外出は危険だと思った": "I went out with frozen water, but I thought going out in midsummer is dangerous",
                "がん検診の検査結果は異常なしでした": "The cancer screening test results were normal",
                "これからも年1ペースで受けたいです": "I would like to continue receiving it once a year",
                "お昼ごはんはカレー蕎麦とネギトロ巻きにします": "For lunch, I'll have curry soba and negitoro rolls",
                "午後にはまた大量のネギトロが届くらしいので消化していかないと": "I heard that a large amount of negitoro will arrive in the afternoon, so I have to consume it",
                "なんかスパッと切れなくてボロボロになっていく": "It doesn't cut cleanly and becomes tattered",
                "昨日作ったカレーが微妙に残ってたので出汁で伸ばしていきます": "There was a little curry left from yesterday, so I'll dilute it with broth"
            },
            "zh": {
                "こんにちは": "你好",
                "さようなら": "再见",
                "ありがとう": "谢谢",
                "ありがとうございます": "非常感谢",
                "おはよう": "早上好",
                "おはようございます": "早上好",
                "こんばんは": "晚上好",
                "おやすみなさい": "晚安",
                "すみません": "不好意思",
                "はじめまして": "初次见面",
                "お疲れさまでした": "辛苦了",
                "いただきます": "我开动了",
                "ごちそうさまでした": "谢谢款待",
                "さて図書館行って、病院行って、銀行にも行ってくるでは出発です": "好，我要去图书馆、医院和银行，出发！",
                "汗だくで帰宅しました、シャワー浴びてきたのでスッキリ": "满身大汗回到家，洗了个澡很舒服"
            },
            "ko": {
                "こんにちは": "안녕하세요",
                "さようなら": "안녕히 가세요",
                "ありがとう": "감사합니다",
                "ありがとうございます": "정말 감사합니다",
                "おはよう": "좋은 아침입니다",
                "おはようございます": "좋은 아침입니다",
                "こんばんは": "안녕하세요",
                "おやすみなさい": "안녕히 주무세요",
                "すみません": "죄송합니다",
                "はじめまして": "처음 뵙겠습니다",
                "お疲れさまでした": "수고하셨습니다",
                "いただきます": "잘 먹겠습니다",
                "ごちそうさまでした": "잘 먹었습니다",
                "さて図書館行って、病院行って、銀行にも行ってくるでは出発です": "자, 도서관, 병원, 은행에 가야겠습니다. 출발!",
                "汗だくで帰宅しました、シャワー浴びてきたのでスッキリ": "땀범벅이 되어 집에 왔는데, 샤워를 해서 시원해졌습니다"
            },
            "es": {
                "こんにちは": "Hola",
                "さようなら": "Adiós",
                "ありがとう": "Gracias",
                "ありがとうございます": "Muchas gracias",
                "おはよう": "Buenos días",
                "こんばんは": "Buenas noches",
                "すみません": "Disculpe",
                "はじめまして": "Mucho gusto",
                "さて図書館行って、病院行って、銀行にも行ってくるでは出発です": "Bueno, voy a ir a la biblioteca, al hospital y al banco. ¡Vámonos!"
            },
            "fr": {
                "こんにちは": "Bonjour",
                "さようなら": "Au revoir",
                "ありがとう": "Merci",
                "ありがとうございます": "Merci beaucoup",
                "おはよう": "Bonjour",
                "こんばんは": "Bonsoir",
                "すみません": "Excusez-moi",
                "はじめまして": "Enchanté(e)",
                "さて図書館行って、病院行って、銀行にも行ってくるでは出発です": "Bon, je vais aller à la bibliothèque, à l'hôpital et à la banque. Allons-y!"
            },
            "de": {
                "こんにちは": "Hallo",
                "さようなら": "Auf Wiedersehen",
                "ありがとう": "Danke",
                "ありがとうございます": "Vielen Dank",
                "おはよう": "Guten Morgen",
                "こんばんは": "Guten Abend",
                "すみません": "Entschuldigung",
                "はじめまして": "Freut mich",
                "さて図書館行って、病院行って、銀行にも行ってくるでは出発です": "Nun, ich gehe zur Bibliothek, zum Krankenhaus und zur Bank. Los geht's!"
            }
        }

    def initialize(self) -> bool:
        """初期化"""
        try:
            logging.info("モック翻訳プロバイダを初期化中...")

            # 模擬的な初期化時間
            time.sleep(0.1)

            self.is_initialized = True
            logging.info("モック翻訳プロバイダの初期化が完了しました")
            return True

        except Exception as e:
            raise MockTranslateError(
                f"モック翻訳プロバイダの初期化に失敗しました: {str(e)}",
                "INIT_FAILED",
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
            raise MockTranslateError("プロバイダが初期化されていません", "NOT_INITIALIZED")

        if not texts:
            return []

        try:
            translated_texts = []
            total_texts = len(texts)

            # 対象言語の翻訳辞書を取得
            target_dict = self.translation_dict.get(target_language, {})

            for i, text in enumerate(texts):
                if progress_callback:
                    progress = int((i * 100) / total_texts)
                    progress_callback(f"翻訳中... {i+1}/{total_texts}", progress)

                # 実際のAPI遅延を模擬
                if self.settings.delay_ms > 0:
                    time.sleep(self.settings.delay_ms / 1000.0)

                # 翻訳実行
                translated_text = self._translate_single(text, target_language, target_dict)
                translated_texts.append(translated_text)

            if progress_callback:
                progress_callback("翻訳完了", 100)

            logging.info(f"モック翻訳完了: {total_texts}件を{target_language}に翻訳")
            return translated_texts

        except Exception as e:
            raise MockTranslateError(
                f"翻訳処理中にエラーが発生しました: {str(e)}",
                "TRANSLATE_FAILED",
                e
            )

    def _translate_single(self, text: str, target_language: str, target_dict: Dict[str, str]) -> str:
        """単一テキストの翻訳"""
        # 辞書に完全一致があればそれを使用
        if text in target_dict:
            return target_dict[text]

        # 部分一致を試す
        for japanese_text, translated_text in target_dict.items():
            if japanese_text in text or text in japanese_text:
                # 部分的に置換
                if japanese_text in text:
                    return text.replace(japanese_text, translated_text)

        # 辞書にない場合の汎用翻訳
        if self.settings.add_prefix:
            lang_prefix = target_language.upper()
            return f"[{lang_prefix}] {text}"
        else:
            # シンプルな変換ルール
            return self._generic_translate(text, target_language)

    def _generic_translate(self, text: str, target_language: str) -> str:
        """汎用翻訳ルール"""
        # 基本的な変換パターン
        generic_rules = {
            "en": {
                "です": " is",
                "ます": "s",
                "した": "ed",
                "と": " and ",
                "の": " of ",
                "を": " ",
                "に": " to ",
                "で": " at "
            },
            "zh": {
                "です": "",
                "ます": "",
                "した": "了",
                "と": "和",
                "の": "的",
                "を": "",
                "に": "在",
                "で": "在"
            },
            "ko": {
                "です": "입니다",
                "ます": "습니다",
                "した": "했습니다",
                "と": "와",
                "の": "의",
                "を": "을",
                "に": "에",
                "で": "에서"
            }
        }

        rules = generic_rules.get(target_language, {})
        result = text

        for japanese, replacement in rules.items():
            result = result.replace(japanese, replacement)

        return result

    def get_supported_languages(self) -> List[str]:
        """サポートされている言語コードの一覧を取得"""
        return list(self.translation_dict.keys())

    def get_error_guidance(self, error: MockTranslateError) -> str:
        """エラー時のユーザーガイダンス"""
        if error.error_code == "NOT_INITIALIZED":
            return "モック翻訳プロバイダが初期化されていません。アプリケーションの再起動を試してください。"
        elif error.error_code == "TRANSLATE_FAILED":
            return "翻訳処理中にエラーが発生しました。入力テキストを確認してください。"
        elif error.error_code == "INIT_FAILED":
            return "モック翻訳プロバイダの初期化に失敗しました。アプリケーションの再起動を試してください。"
        else:
            return "予期しないエラーが発生しました。アプリケーションの再起動を試してください。"