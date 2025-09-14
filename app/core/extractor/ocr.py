"""
OCRエンジンの実装（PaddleOCR / Tesseract対応）
"""

import cv2
import numpy as np
import os
import sys
import subprocess
import time
import ssl
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
from typing import List, Tuple, Optional, Dict, Any, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path
import logging
import tempfile
import shutil

# PaddleOCR（推奨）
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    logging.warning("PaddleOCRが利用できません。pip install paddleocrでインストールしてください。")

# Tesseract（オプション）
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logging.warning("Tesseractが利用できません。pip install pytesseractでインストールしてください。")


class OCRModelDownloader:
    """OCRモデルのダウンロード管理"""

    # ダウンロード設定
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0  # 秒
    DOWNLOAD_TIMEOUT = 300  # 5分
    CHUNK_SIZE = 8192

    @staticmethod
    def get_paddleocr_cache_dir() -> Path:
        """PaddleOCRのキャッシュディレクトリ取得"""
        home_dir = Path.home()
        # 新しいPaddleXは.paddlexディレクトリを使用
        cache_dir = home_dir / ".paddlex"

        # キャッシュディレクトリが存在しない場合は作成
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            logging.debug(f"PaddleXキャッシュディレクトリ: {cache_dir}")
        except Exception as e:
            logging.error(f"キャッシュディレクトリ作成エラー: {e}")

        return cache_dir

    @staticmethod
    def is_paddleocr_model_available(lang: str = "ja") -> bool:
        """PaddleOCRモデルが利用可能かチェック"""
        if not PADDLEOCR_AVAILABLE:
            return False

        try:
            cache_dir = OCRModelDownloader.get_paddleocr_cache_dir()

            # 日本語モデルの場合、PaddleXのofficial_modelsディレクトリを確認
            if lang in ["ja", "japan", "japanese"]:
                official_models_dir = cache_dir / "official_models"

                # PaddleXの日本語OCRに必要なモデル
                required_models = [
                    "PP-OCRv5_server_det",  # テキスト検出
                    "PP-OCRv5_server_rec",  # テキスト認識
                ]

                for model_name in required_models:
                    model_dir = official_models_dir / model_name
                    if not model_dir.exists() or not any(model_dir.iterdir()):
                        logging.debug(f"PaddleXモデル未検出: {model_name}")
                        return False

                logging.debug(f"PaddleXモデルが利用可能: {required_models}")
                return True

            # 他の言語は基本的なチェック
            return cache_dir.exists() and (cache_dir / "official_models").exists()

        except Exception as e:
            logging.error(f"PaddleOCRモデル確認エラー: {e}")
            return False

    @staticmethod
    def download_paddleocr_model(lang: str = "ja", progress_callback: Optional[Callable[[str, int], None]] = None):
        """PaddleOCRモデルをダウンロード（リトライ機能付き）"""
        if not PADDLEOCR_AVAILABLE:
            raise Exception("PaddleOCRがインストールされていません")

        last_error = None

        for attempt in range(OCRModelDownloader.MAX_RETRIES):
            try:
                if progress_callback:
                    if attempt == 0:
                        progress_callback("PaddleOCRモデルの初期化を開始...", 10)
                    else:
                        progress_callback(f"再試行中... ({attempt + 1}/{OCRModelDownloader.MAX_RETRIES})", 10 + (attempt * 20))

                # SSL設定を調整（Windows環境対応）
                OCRModelDownloader._configure_ssl_for_windows()

                # プロキシ設定を確認・適用
                OCRModelDownloader._configure_proxy_settings()

                # タイムアウト設定付きでPaddleOCRインスタンスを作成
                ocr = OCRModelDownloader._create_paddleocr_with_timeout(
                    lang=lang,
                    progress_callback=progress_callback,
                    attempt=attempt
                )

                if progress_callback:
                    progress_callback("モデル初期化テスト中...", 80 + (attempt * 5))

                # ダミー画像でモデル初期化を確実に実行
                dummy_image = np.ones((100, 100, 3), dtype=np.uint8) * 255
                # 新しいPaddleOCRバージョンではpredictメソッドを使用
                try:
                    result = ocr.predict(dummy_image)
                except AttributeError:
                    # predict メソッドが無い場合は旧APIを試す
                    result = ocr.ocr(dummy_image)

                if progress_callback:
                    progress_callback("モデル初期化完了", 100)

                logging.info(f"PaddleOCRモデル({lang})のダウンロードが完了しました (試行回数: {attempt + 1})")
                return

            except Exception as e:
                last_error = e
                error_msg = str(e)
                logging.warning(f"PaddleOCRダウンロード試行 {attempt + 1} 失敗: {error_msg}")

                if attempt < OCRModelDownloader.MAX_RETRIES - 1:
                    if progress_callback:
                        progress_callback(f"エラー発生、{OCRModelDownloader.RETRY_DELAY}秒後に再試行...", 30 + (attempt * 20))
                    time.sleep(OCRModelDownloader.RETRY_DELAY)
                else:
                    # 最終試行も失敗した場合
                    detailed_error = OCRModelDownloader._analyze_download_error(error_msg)
                    final_error = f"PaddleOCRモデルのダウンロードに失敗しました（{OCRModelDownloader.MAX_RETRIES}回試行）:\n{detailed_error}"
                    logging.error(final_error)
                    raise Exception(final_error)

    @staticmethod
    def _configure_ssl_for_windows():
        """Windows環境向けSSL設定"""
        try:
            # Windows環境でのSSL証明書検証問題を解決
            if sys.platform == 'win32':
                import ssl
                ssl._create_default_https_context = ssl._create_unverified_context
                logging.debug("Windows環境向けSSL設定を適用しました")
        except Exception as e:
            logging.debug(f"SSL設定の適用に失敗: {e}")

    @staticmethod
    def _configure_proxy_settings():
        """プロキシ設定の確認と適用"""
        try:
            # 環境変数からプロキシ設定を確認
            http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
            https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')

            if http_proxy or https_proxy:
                logging.info(f"プロキシ設定を検出: HTTP={http_proxy}, HTTPS={https_proxy}")

        except Exception as e:
            logging.debug(f"プロキシ設定確認エラー: {e}")

    @staticmethod
    def _create_paddleocr_with_timeout(lang: str, progress_callback: Optional[Callable], attempt: int):
        """タイムアウト設定付きPaddleOCRインスタンス作成"""
        try:
            if progress_callback:
                progress_callback(f"PaddleOCRインスタンス作成中... (試行 {attempt + 1})", 30 + (attempt * 20))

            # タイムアウト設定
            import socket
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(OCRModelDownloader.DOWNLOAD_TIMEOUT)

            try:
                # PaddleOCRの言語コード変換
                paddle_lang = "japan" if lang in ["ja", "japanese"] else lang

                # 最も基本的なパラメータでPaddleOCRインスタンス作成
                ocr = PaddleOCR(lang=paddle_lang)

                if progress_callback:
                    progress_callback("モデルダウンロード完了", 70 + (attempt * 5))

                return ocr

            finally:
                # タイムアウトを元に戻す
                socket.setdefaulttimeout(original_timeout)

        except Exception as e:
            raise Exception(f"PaddleOCRインスタンス作成エラー: {str(e)}")

    @staticmethod
    def _analyze_download_error(error_msg: str) -> str:
        """ダウンロードエラーの詳細分析"""
        error_suggestions = []

        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            error_suggestions.append("• ネットワーク接続が不安定です。安定したインターネット環境で再試行してください。")

        if "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
            error_suggestions.append("• SSL証明書の問題です。セキュリティソフトまたはファイアウォール設定を確認してください。")

        if "proxy" in error_msg.lower():
            error_suggestions.append("• プロキシ環境が原因の可能性があります。ネットワーク管理者に相談してください。")

        if "connection" in error_msg.lower() or "network" in error_msg.lower():
            error_suggestions.append("• インターネット接続を確認してください。")

        if "permission" in error_msg.lower() or "access" in error_msg.lower():
            error_suggestions.append("• ファイル書き込み権限の問題です。管理者権限で実行してください。")

        if not error_suggestions:
            error_suggestions.append("• 不明なエラーです。Tesseractエンジンをご利用ください。")

        suggestions_text = "\n".join(error_suggestions)
        return f"エラー詳細: {error_msg}\n\n解決方法:\n{suggestions_text}"


@dataclass
class OCRResult:
    """OCR結果のデータクラス"""
    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, width, height
    
    def __post_init__(self):
        """後処理でテキストをクリーンアップ"""
        self.text = self._clean_text(self.text)
    
    def _clean_text(self, text: str) -> str:
        """テキストのクリーンアップ"""
        if not text:
            return ""
        
        # 基本的な正規化
        text = text.strip()
        
        # 特殊文字の除去・置換
        text = text.replace('\\n', '\n')
        text = text.replace('\\t', ' ')
        
        # 連続する空白を1つに
        import re
        text = re.sub(r'\\s+', ' ', text)
        
        return text
    
    @property
    def is_valid(self) -> bool:
        """有効なOCR結果かどうか"""
        return bool(self.text.strip()) and self.confidence > 0.5


class OCREngine(ABC):
    """OCRエンジンの抽象基底クラス"""
    
    def __init__(self, language: str = "ja"):
        self.language = language
        self.is_initialized = False
    
    @abstractmethod
    def initialize(self) -> bool:
        """エンジンの初期化"""
        pass
    
    @abstractmethod
    def extract_text(self, image: np.ndarray) -> List[OCRResult]:
        """画像からテキストを抽出"""
        pass
    
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """画像の前処理（共通処理）"""
        # グレースケール変換
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        # ノイズ除去
        denoised = cv2.medianBlur(gray, 3)
        
        # コントラスト向上
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        
        # 二値化（適応的閾値）
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        return binary
    
    def upscale_image(self, image: np.ndarray, scale_factor: float = 2.0) -> np.ndarray:
        """画像の拡大（低解像度対応）"""
        height, width = image.shape[:2]
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        
        return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_CUBIC)


class PaddleOCREngine(OCREngine):
    """PaddleOCRエンジン実装"""

    def __init__(self, language: str = "ja"):
        super().__init__(language)
        self.ocr_model = None
        self.confidence_threshold = 0.7

    def initialize(self, download_callback: Optional[Callable[[str, int], None]] = None) -> bool:
        """PaddleOCRの初期化（モデル自動ダウンロード付き）"""
        if not PADDLEOCR_AVAILABLE:
            logging.error("PaddleOCRが利用できません")
            return False

        try:
            # モデル存在チェック
            if not OCRModelDownloader.is_paddleocr_model_available(self.language):
                logging.info("PaddleOCRモデルが見つかりません。ダウンロードを開始します...")

                if download_callback:
                    download_callback("PaddleOCRモデルをダウンロード中...", 0)

                # モデルダウンロード実行
                OCRModelDownloader.download_paddleocr_model(self.language, download_callback)

            # PaddleOCRモデルの初期化
            if download_callback:
                download_callback("PaddleOCRエンジンを初期化中...", 90)

            # PaddleOCRの言語コード変換
            paddle_lang = "japan" if self.language in ["ja", "japanese"] else self.language

            # 最も基本的なパラメータでPaddleOCRインスタンス作成
            self.ocr_model = PaddleOCR(lang=paddle_lang)

            if download_callback:
                download_callback("初期化完了", 100)

            self.is_initialized = True
            logging.info("PaddleOCRの初期化が完了しました")
            return True

        except Exception as e:
            logging.error(f"PaddleOCRの初期化に失敗しました: {e}")
            return False
    
    def extract_text(self, image: np.ndarray) -> List[OCRResult]:
        """PaddleOCRでテキスト抽出"""
        if not self.is_initialized or not self.ocr_model:
            return []
        
        try:
            # 前処理
            processed_image = self.preprocess_image(image)
            
            # OCR実行（新しいAPIに対応）
            try:
                results = self.ocr_model.predict(processed_image)
                # 新しいAPIの結果を旧APIの形式に変換
                if hasattr(results, 'json') and results.json:
                    # 新しい形式の結果を解析
                    results = self._convert_new_api_results(results)
                else:
                    results = [[]]  # 結果がない場合
            except AttributeError:
                # 旧APIを使用
                results = self.ocr_model.ocr(processed_image)
            
            ocr_results = []
            
            if results and results[0]:
                for result in results[0]:
                    # PaddleOCR結果の解析
                    bbox_points = result[0]  # 4点の座標
                    text_info = result[1]    # (text, confidence)
                    
                    text = text_info[0]
                    confidence = text_info[1]
                    
                    # 信頼度フィルタ
                    if confidence < self.confidence_threshold:
                        continue
                    
                    # 4点から矩形を計算
                    x_coords = [p[0] for p in bbox_points]
                    y_coords = [p[1] for p in bbox_points]
                    
                    x = int(min(x_coords))
                    y = int(min(y_coords))
                    width = int(max(x_coords) - x)
                    height = int(max(y_coords) - y)
                    
                    ocr_results.append(OCRResult(
                        text=text,
                        confidence=confidence,
                        bbox=(x, y, width, height)
                    ))
            
            return ocr_results
            
        except Exception as e:
            logging.error(f"PaddleOCR実行エラー: {e}")
            return []

    def _convert_new_api_results(self, api_result):
        """新しいPaddleOCRのAPI結果を旧形式に変換"""
        try:
            converted_results = [[]]

            # 新しいAPIの結果構造を解析して旧形式に変換
            if hasattr(api_result, 'json') and api_result.json:
                for item in api_result.json.get('dt_polys', []):
                    bbox_points = item.get('poly', [])
                    text = item.get('text', '')
                    confidence = item.get('score', 0.0)

                    if text and confidence > 0.5:
                        converted_results[0].append([bbox_points, [text, confidence]])

            return converted_results

        except Exception as e:
            logging.debug(f"API結果変換エラー: {e}")
            return [[]]


class TesseractEngine(OCREngine):
    """Tesseractエンジン実装"""
    
    def __init__(self, language: str = "jpn"):
        super().__init__(language)
        self.config = '--psm 6 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZぁ-んァ-ン一-龯'
    
    def initialize(self) -> bool:
        """Tesseractの初期化確認"""
        if not TESSERACT_AVAILABLE:
            logging.error("Tesseractが利用できません")
            return False
        
        try:
            # Tesseractが利用可能かテスト
            pytesseract.get_tesseract_version()
            self.is_initialized = True
            logging.info("Tesseractの初期化が完了しました")
            return True
            
        except Exception as e:
            logging.error(f"Tesseractの初期化に失敗しました: {e}")
            return False
    
    def extract_text(self, image: np.ndarray) -> List[OCRResult]:
        """Tesseractでテキスト抽出"""
        if not self.is_initialized:
            return []
        
        try:
            # 前処理と拡大
            processed_image = self.preprocess_image(image)
            upscaled_image = self.upscale_image(processed_image, 2.0)
            
            # Tesseract実行（詳細な結果を取得）
            data = pytesseract.image_to_data(
                upscaled_image,
                lang=self.language,
                config=self.config,
                output_type=pytesseract.Output.DICT
            )
            
            ocr_results = []
            
            # 結果の解析
            for i in range(len(data['text'])):
                text = data['text'][i].strip()
                confidence = float(data['conf'][i])
                
                if not text or confidence < 60:  # Tesseractの信頼度は0-100
                    continue
                
                # 座標を元の画像サイズに戻す
                x = int(data['left'][i] / 2.0)
                y = int(data['top'][i] / 2.0)
                width = int(data['width'][i] / 2.0)
                height = int(data['height'][i] / 2.0)
                
                ocr_results.append(OCRResult(
                    text=text,
                    confidence=confidence / 100.0,  # 0-1の範囲に正規化
                    bbox=(x, y, width, height)
                ))
            
            return ocr_results
            
        except Exception as e:
            logging.error(f"Tesseract実行エラー: {e}")
            return []


class OCRManager:
    """OCRエンジンの管理クラス"""
    
    def __init__(self):
        self.engines: Dict[str, OCREngine] = {}
        self.current_engine: Optional[OCREngine] = None
        
        # 利用可能なエンジンを登録
        if PADDLEOCR_AVAILABLE:
            self.engines['paddleocr'] = PaddleOCREngine()
        
        if TESSERACT_AVAILABLE:
            self.engines['tesseract'] = TesseractEngine()
    
    def get_available_engines(self) -> List[str]:
        """利用可能なエンジン一覧"""
        return list(self.engines.keys())
    
    def initialize_engine(self, engine_name: str, download_callback: Optional[Callable[[str, int], None]] = None) -> bool:
        """指定エンジンの初期化"""
        if engine_name not in self.engines:
            logging.error(f"未対応のOCRエンジン: {engine_name}")
            return False

        engine = self.engines[engine_name]

        # PaddleOCRの場合はダウンロードコールバックを渡す
        if isinstance(engine, PaddleOCREngine):
            success = engine.initialize(download_callback)
        else:
            success = engine.initialize()

        if success:
            self.current_engine = engine
            logging.info(f"OCRエンジンを切り替えました: {engine_name}")
            return True

        return False
    
    def extract_text(self, image: np.ndarray) -> List[OCRResult]:
        """現在のエンジンでテキスト抽出"""
        if not self.current_engine:
            logging.error("OCRエンジンが初期化されていません")
            return []
        
        return self.current_engine.extract_text(image)
    
    def extract_text_batch(self, images: List[np.ndarray]) -> List[List[OCRResult]]:
        """バッチ処理でテキスト抽出"""
        if not self.current_engine:
            return []
        
        results = []
        for image in images:
            results.append(self.extract_text(image))
        
        return results
    
    def get_engine_info(self) -> Dict[str, Any]:
        """現在のエンジン情報"""
        if not self.current_engine:
            return {}
        
        return {
            'engine_type': type(self.current_engine).__name__,
            'language': self.current_engine.language,
            'is_initialized': self.current_engine.is_initialized
        }