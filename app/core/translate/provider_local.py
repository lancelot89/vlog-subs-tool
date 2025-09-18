"""
ローカル翻訳プロバイダ（CTranslate2 + MarianMT）の実装
"""

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    import ctranslate2
    import sentencepiece as spm
    import transformers

    CTRANSLATE2_AVAILABLE = True
except ImportError:
    CTRANSLATE2_AVAILABLE = False
    # CTranslate2はローカル翻訳機能でのみ使用され、現在は無効化されているため警告を出力しない

try:
    import opencc

    OPENCC_AVAILABLE = True
except ImportError:
    OPENCC_AVAILABLE = False
    # OpenCCは中国語変換でのみ使用され、現在は無効化されているため警告を出力しない

from .language_detector import LanguageDetectionError, LanguageDetector


@dataclass
class LocalTranslateSettings:
    """ローカル翻訳設定"""

    models_dir: str
    max_batch_size: int = 16
    beam_size: int = 1  # より厳格に
    num_hypotheses: int = 1
    length_penalty: float = 0.2  # より短い翻訳を強く優遇
    coverage_penalty: float = 0.0
    repetition_penalty: float = 1.5  # より強い繰り返し抑制
    no_repeat_ngram_size: int = 3  # 3-gramの繰り返しを防ぐ
    max_decoding_length: int = 50  # さらに短く制限
    min_decoding_length: int = 1
    use_vmap: bool = True
    inter_threads: int = 1
    intra_threads: int = 0  # 0で自動設定


class LocalTranslateError(Exception):
    """ローカル翻訳関連エラー"""

    def __init__(
        self,
        message: str,
        error_code: str = "",
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.original_error = original_error


class ModelManager:
    """翻訳モデル管理クラス"""

    # サポートされている言語ペア（英語ピボット構成）
    SUPPORTED_PAIRS = {
        ("ja", "en"): "Helsinki-NLP/opus-mt-ja-en",
        ("en", "ja"): "Helsinki-NLP/opus-mt-jap-en",  # 実際に存在するモデル
        ("zh", "en"): "Helsinki-NLP/opus-mt-zh-en",
        ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
        ("ar", "en"): "Helsinki-NLP/opus-mt-ar-en",
        ("en", "ar"): "Helsinki-NLP/opus-mt-en-ar",
        ("ko", "en"): "Helsinki-NLP/opus-mt-ko-en",
        ("en", "ko"): "Helsinki-NLP/opus-mt-en-ko",
    }

    def __init__(self, models_dir: str):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.loaded_models: Dict[Tuple[str, str], object] = {}
        self.tokenizers: Dict[Tuple[str, str], object] = {}
        self._lock = threading.Lock()

    def get_model_path(self, src_lang: str, tgt_lang: str) -> Path:
        """モデルパスを取得"""
        return self.models_dir / f"{src_lang}-{tgt_lang}"

    def is_model_available(self, src_lang: str, tgt_lang: str) -> bool:
        """モデルが利用可能かチェック"""
        model_path = self.get_model_path(src_lang, tgt_lang)
        return model_path.exists() and (model_path / "config.json").exists()

    def download_and_convert_model(
        self, src_lang: str, tgt_lang: str, progress_callback: Optional[Callable] = None
    ) -> bool:
        """
        Hugging FaceモデルをダウンロードしてCTranslate2形式に変換
        """
        if not CTRANSLATE2_AVAILABLE:
            raise LocalTranslateError("CTranslate2が利用できません", "PACKAGE_MISSING")

        lang_pair = (src_lang, tgt_lang)
        if lang_pair not in self.SUPPORTED_PAIRS:
            raise LocalTranslateError(
                f"未対応の言語ペア: {src_lang} -> {tgt_lang}",
                "UNSUPPORTED_LANGUAGE_PAIR",
            )

        model_id = self.SUPPORTED_PAIRS[lang_pair]
        model_path = self.get_model_path(src_lang, tgt_lang)

        try:
            if progress_callback:
                progress_callback(f"モデル {model_id} をダウンロード中...", 10)

            if not CTRANSLATE2_AVAILABLE:
                raise LocalTranslateError("CTranslate2が利用できません", "PACKAGE_MISSING")

            # Hugging Faceからモデルをロード
            model = transformers.MarianMTModel.from_pretrained(model_id)
            tokenizer = transformers.MarianTokenizer.from_pretrained(model_id)

            if progress_callback:
                progress_callback("CTranslate2形式に変換中...", 50)

            # CTranslate2形式に変換
            converter = ctranslate2.converters.TransformersConverter(model_id)
            converter.convert(model_path, force=True)

            # トークナイザーを保存
            tokenizer.save_pretrained(model_path)

            if progress_callback:
                progress_callback("変換完了", 100)

            logging.info(f"モデル変換完了: {model_id} -> {model_path}")
            return True

        except Exception as e:
            logging.error(f"モデル変換エラー: {e}")
            raise LocalTranslateError(
                f"モデルのダウンロード・変換に失敗: {str(e)}",
                "MODEL_CONVERSION_FAILED",
                e,
            )

    def load_model(
        self, src_lang: str, tgt_lang: str, settings: LocalTranslateSettings
    ) -> Tuple[Optional[object], Optional[object]]:
        """モデルをロード"""
        lang_pair = (src_lang, tgt_lang)

        with self._lock:
            # 既にロード済みの場合は再利用
            if lang_pair in self.loaded_models:
                return self.loaded_models[lang_pair], self.tokenizers[lang_pair]

            # モデルが存在しない場合はダウンロード
            if not self.is_model_available(src_lang, tgt_lang):
                self.download_and_convert_model(src_lang, tgt_lang)

            model_path = self.get_model_path(src_lang, tgt_lang)

            try:
                if not CTRANSLATE2_AVAILABLE:
                    raise LocalTranslateError("CTranslate2が利用できません", "PACKAGE_MISSING")

                # CTranslate2モデルをロード
                translator = ctranslate2.Translator(
                    str(model_path),
                    device="cpu",
                    inter_threads=settings.inter_threads,
                    intra_threads=settings.intra_threads,
                )

                # トークナイザーをロード
                tokenizer = transformers.MarianTokenizer.from_pretrained(str(model_path))

                # キャッシュに保存
                self.loaded_models[lang_pair] = translator
                self.tokenizers[lang_pair] = tokenizer

                logging.info(f"モデルロード完了: {src_lang}-{tgt_lang}")
                return translator, tokenizer

            except Exception as e:
                logging.error(f"モデルロードエラー: {e}")
                raise LocalTranslateError(f"モデルのロードに失敗: {str(e)}", "MODEL_LOAD_FAILED", e)

    def get_translation_route(self, src_lang: str, tgt_lang: str) -> List[Tuple[str, str]]:
        """翻訳ルートを取得（直接 or ピボット）"""
        direct_pair = (src_lang, tgt_lang)
        if direct_pair in self.SUPPORTED_PAIRS:
            return [direct_pair]

        # 英語ピボット翻訳
        if src_lang != "en" and tgt_lang != "en":
            pivot_route = [(src_lang, "en"), ("en", tgt_lang)]
            # 両方のペアがサポートされているかチェック
            if all(pair in self.SUPPORTED_PAIRS for pair in pivot_route):
                return pivot_route

        raise LocalTranslateError(
            f"翻訳ルートが見つかりません: {src_lang} -> {tgt_lang}",
            "NO_TRANSLATION_ROUTE",
        )


class LocalTranslateProvider:
    """ローカル翻訳プロバイダ"""

    def __init__(self, settings: LocalTranslateSettings):
        self.settings = settings
        self.model_manager = ModelManager(settings.models_dir)
        self.language_detector = None
        self.opencc_converter = None
        self.is_initialized = False

    def initialize(self) -> bool:
        """初期化"""
        if not CTRANSLATE2_AVAILABLE:
            raise LocalTranslateError(
                "CTranslate2パッケージがインストールされていません", "PACKAGE_MISSING"
            )

        try:
            # 言語検出器を初期化
            self.language_detector = LanguageDetector()

            # OpenCCコンバーターを初期化（中国語用）
            if OPENCC_AVAILABLE:
                self.opencc_converter = {
                    "zh-cn-to-zh-tw": opencc.OpenCC("s2t"),  # 簡体字 -> 繁体字
                    "zh-tw-to-zh-cn": opencc.OpenCC("t2s"),  # 繁体字 -> 簡体字
                }

            self.is_initialized = True
            logging.info("ローカル翻訳プロバイダの初期化が完了しました")
            return True

        except Exception as e:
            raise LocalTranslateError(f"初期化に失敗しました: {str(e)}", "INIT_FAILED", e)

    def _preprocess_text(self, text: str, src_lang: str) -> str:
        """テキストの前処理"""
        # 改行を空白に変換
        text = text.replace("\n", " ").replace("\r", " ")
        # 連続する空白を単一空白に変換
        text = " ".join(text.split())
        return text.strip()

    def _postprocess_text(self, text: str, tgt_lang: str) -> str:
        """テキストの後処理"""
        text = text.strip()

        # アラビア語の場合、右から左への文字制御を追加
        if tgt_lang == "ar":
            # RLM (Right-to-Left Mark) を文頭に追加
            text = "\u200f" + text

        # 中国語の場合、OpenCCで変換
        if tgt_lang.startswith("zh-") and OPENCC_AVAILABLE and self.opencc_converter:
            if tgt_lang == "zh-tw" and "zh-cn-to-zh-tw" in self.opencc_converter:
                text = self.opencc_converter["zh-cn-to-zh-tw"].convert(text)
            elif tgt_lang == "zh-cn" and "zh-tw-to-zh-cn" in self.opencc_converter:
                text = self.opencc_converter["zh-tw-to-zh-cn"].convert(text)

        return text

    def _translate_single_step(
        self,
        texts: List[str],
        src_lang: str,
        tgt_lang: str,
        progress_callback: Optional[Callable] = None,
    ) -> List[str]:
        """単一ステップの翻訳実行"""
        if not texts:
            return []

        translator, tokenizer = self.model_manager.load_model(src_lang, tgt_lang, self.settings)

        # テキストの前処理
        processed_texts = [self._preprocess_text(text, src_lang) for text in texts]

        # バッチ処理
        translated_texts = []
        batch_size = self.settings.max_batch_size
        total_batches = (len(processed_texts) + batch_size - 1) // batch_size

        for i in range(0, len(processed_texts), batch_size):
            batch_texts = processed_texts[i : i + batch_size]
            batch_num = i // batch_size + 1

            if progress_callback:
                progress_callback(
                    f"翻訳中 ({src_lang}->{tgt_lang}): {batch_num}/{total_batches}",
                    int(batch_num * 50 / total_batches),
                )

            # トークン化（CTranslate2形式に合わせる）
            source_tokens = []
            for text in batch_texts:
                # テキストを直接トークン化
                tokens = tokenizer.tokenize(text)
                if not tokens:
                    tokens = ["<unk>"]
                source_tokens.append(tokens)

            # 翻訳実行
            results = translator.translate_batch(
                source_tokens,
                beam_size=self.settings.beam_size,
                num_hypotheses=self.settings.num_hypotheses,
                length_penalty=self.settings.length_penalty,
                coverage_penalty=self.settings.coverage_penalty,
                repetition_penalty=self.settings.repetition_penalty,
                no_repeat_ngram_size=self.settings.no_repeat_ngram_size,
                max_decoding_length=self.settings.max_decoding_length,
                min_decoding_length=self.settings.min_decoding_length,
            )

            # デトークン化
            for result in results:
                hypothesis = result.hypotheses[0]  # 最良の仮説を選択
                # トークンを文字列に変換
                translated_text = tokenizer.convert_tokens_to_string(hypothesis)
                translated_text = self._postprocess_text(translated_text, tgt_lang)
                translated_texts.append(translated_text)

        return translated_texts

    def translate_batch(
        self,
        texts: List[str],
        target_language: str,
        source_language: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> List[str]:
        """バッチ翻訳実行"""
        if not self.is_initialized:
            raise LocalTranslateError("プロバイダが初期化されていません", "NOT_INITIALIZED")

        if not texts:
            return []

        try:
            # ソース言語を検出（指定されていない場合）
            if source_language is None:
                if progress_callback:
                    progress_callback("言語検出中...", 5)

                # 複数のテキストから言語を検出（最初の数個を使用）
                sample_texts = texts[: min(5, len(texts))]
                sample_text = " ".join(sample_texts)

                detection_result = self.language_detector.detect_language(sample_text)
                if detection_result is None:
                    raise LocalTranslateError(
                        "ソース言語を検出できませんでした", "LANGUAGE_DETECTION_FAILED"
                    )

                source_language = detection_result.language
                logging.info(
                    f"検出された言語: {source_language} (信頼度: {detection_result.confidence:.2f})"
                )

            # 翻訳ルートを決定
            translation_route = self.model_manager.get_translation_route(
                source_language, target_language
            )

            if progress_callback:
                progress_callback(
                    f"翻訳ルート: {' -> '.join([pair[0] for pair in translation_route] + [translation_route[-1][1]])}",
                    10,
                )

            # 翻訳実行
            current_texts = texts
            current_progress = 10

            for step_idx, (src_lang, tgt_lang) in enumerate(translation_route):
                step_progress_start = current_progress
                step_progress_end = current_progress + (80 // len(translation_route))

                def step_progress_callback(message: str, progress: int):
                    if progress_callback:
                        final_progress = step_progress_start + (
                            progress * (step_progress_end - step_progress_start) // 100
                        )
                        progress_callback(
                            f"ステップ {step_idx + 1}/{len(translation_route)}: {message}",
                            final_progress,
                        )

                current_texts = self._translate_single_step(
                    current_texts, src_lang, tgt_lang, step_progress_callback
                )

                current_progress = step_progress_end

            if progress_callback:
                progress_callback("翻訳完了", 100)

            logging.info(
                f"ローカル翻訳完了: {len(texts)}件 ({source_language} -> {target_language})"
            )
            return current_texts

        except LocalTranslateError:
            raise
        except Exception as e:
            logging.error(f"翻訳中にエラー: {e}")
            raise LocalTranslateError(
                f"翻訳中にエラーが発生しました: {str(e)}", "TRANSLATION_FAILED", e
            )

    def get_supported_languages(self) -> Dict[str, str]:
        """サポートされている言語一覧を取得"""
        languages = {
            "ja": "日本語",
            "en": "English",
            "zh-cn": "中文（简体）",
            "zh-tw": "中文（繁體）",
            "ar": "العربية",
            "ko": "한국어",
        }
        return languages

    def is_language_supported(self, lang_code: str) -> bool:
        """言語がサポートされているかチェック"""
        supported_langs = set(self.get_supported_languages().keys())
        return lang_code in supported_langs

    def get_error_guidance(self, error: LocalTranslateError) -> str:
        """エラー種別に応じたユーザ向けガイダンス"""
        guidance_map = {
            "PACKAGE_MISSING": (
                "CTranslate2パッケージがインストールされていません。\n\n"
                "解決方法：\n"
                "1. コマンドプロンプト/ターミナルを開く\n"
                "2. pip install ctranslate2 transformers を実行\n"
                "3. アプリケーションを再起動"
            ),
            "MODEL_DOWNLOAD_FAILED": (
                "翻訳モデルのダウンロードに失敗しました。\n\n"
                "解決方法：\n"
                "1. インターネット接続を確認\n"
                "2. ディスク容量を確認（モデル1つあたり約250MB必要）\n"
                "3. しばらく時間をおいてから再試行"
            ),
            "UNSUPPORTED_LANGUAGE_PAIR": (
                "指定された言語ペアはサポートされていません。\n\n"
                "サポート言語：日本語、英語、中国語（簡体字・繁体字）、アラビア語、韓国語\n"
                "※英語をピボット言語として使用します"
            ),
            "LANGUAGE_DETECTION_FAILED": (
                "自動言語検出に失敗しました。\n\n"
                "解決方法：\n"
                "1. テキストが短すぎる場合は手動で言語を指定\n"
                "2. テキストに複数の言語が混在している場合は分割\n"
                "3. 特殊文字のみの場合は言語検出不可"
            ),
        }

        return guidance_map.get(error.error_code, f"予期しないエラーが発生しました：{str(error)}")
