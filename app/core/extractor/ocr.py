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

PADDLEOCR_AVAILABLE = False
PADDLEX_AVAILABLE = False
# まず PaddleOCR の可否を厳密に判定
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
    logging.info("PaddleOCR が利用可能です")
except ImportError:
    logging.warning("PaddleOCR が利用できません。pip install paddleocr を実行してください。")
# 任意: PaddleX はあくまでオプション
try:
    from paddlex import create_pipeline
    PADDLEX_AVAILABLE = True
    logging.info("PaddleX v3.2+ が利用可能です（任意機能）")
except ImportError:
    pass

# Tesseract（オプション）
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logging.warning("Tesseractが利用できません。pip install pytesseractでインストールしてください。")


def _create_safe_paddleocr_kwargs(base_kwargs: dict) -> dict:
    """
    PaddleOCR への kwargs を安全に整形する。
    - base_kwargs を尊重しつつ、新しいPaddleOCRでサポートされていないパラメータを除外
    - 新旧パラメータの変換も実行
    - セグメンテーションフォルト回避のための安全設定を追加
    """
    merged = dict(base_kwargs) if base_kwargs else {}

    # 新旧PaddleOCRパラメータの互換性対応
    if "use_angle_cls" in merged:
        # use_angle_cls → use_textline_orientation に変換（新しいPaddleOCR対応）
        use_angle_value = merged.pop("use_angle_cls")
        merged["use_textline_orientation"] = use_angle_value
        logging.debug(f"use_angle_cls={use_angle_value} → use_textline_orientation={use_angle_value} に変換")

    # 新しいPaddleOCRでサポートされていないパラメータを除外
    unsupported_params = [
        "show_log",           # ログ制御パラメータ（内部的に処理）
        "use_space_char",     # 空白文字認識パラメータ（廃止）
        "drop_score",         # スコア閾値パラメータ（text_rec_score_threshに統合）
        "use_gpu",            # GPU使用フラグ（デバイス指定に変更）
        "cls_model_dir",      # 分類モデルディレクトリ（廃止）
    ]

    removed_params = []
    for param in unsupported_params:
        if param in merged:
            removed_params.append(f"{param}={merged.pop(param)}")

    if removed_params:
        logging.debug(f"新PaddleOCRでサポート外のパラメータを除外: {', '.join(removed_params)}")

    # 基本パラメータの設定
    merged.setdefault("lang", "japan")         # 既定は日本語

    # drop_scoreの代替としてtext_rec_score_threshを設定
    if "drop_score" in base_kwargs and "text_rec_score_thresh" not in merged:
        merged["text_rec_score_thresh"] = base_kwargs["drop_score"]
        logging.debug(f"drop_score → text_rec_score_thresh に変換")

    # セグメンテーションフォルト回避のための安全設定
    # モデルディレクトリが指定されている場合、それらを一旦除外して最小構成にする
    model_dirs = {}
    for key in ["det_model_dir", "rec_model_dir", "cls_model_dir", "textline_orientation_model_dir"]:
        if key in merged:
            model_dirs[key] = merged.pop(key)
            logging.debug(f"セグメンテーションフォルト回避のため{key}を一時除外")

    logging.info(f"PaddleOCR 安全初期化設定: {merged}")
    if model_dirs:
        logging.debug(f"除外されたモデルディレクトリ: {model_dirs}")

    return merged, model_dirs


def _safe_paddleocr_init(kwargs: dict, model_dirs: dict = None) -> tuple:
    """
    セグメンテーションフォルト対策を含むPaddleOCR初期化
    returns: (ocr_instance, success, error_message)
    """
    import signal
    import sys
    import gc

    # メモリクリア
    gc.collect()

    try:
        from paddleocr import PaddleOCR

        # ステップ1: 最小構成で初期化
        logging.info("PaddleOCR最小構成での初期化を試行...")
        minimal_kwargs = {"lang": kwargs.get("lang", "japan")}

        try:
            ocr = PaddleOCR(**minimal_kwargs)
            logging.info("✓ PaddleOCR最小構成初期化成功")
            return ocr, True, None

        except Exception as e1:
            logging.warning(f"最小構成初期化失敗: {e1}")

            # ステップ2: 段階的にパラメータを追加
            logging.info("段階的パラメータ追加で初期化を試行...")

            safe_configs = [
                # 設定1: 言語のみ + テキスト方向
                {
                    "lang": kwargs.get("lang", "japan"),
                    "use_textline_orientation": kwargs.get("use_textline_orientation", False)
                },
                # 設定2: 基本パラメータのみ
                {
                    "lang": kwargs.get("lang", "japan")
                },
                # 設定3: 絶対最小（英語）
                {
                    "lang": "en"
                }
            ]

            for i, config in enumerate(safe_configs, 1):
                try:
                    logging.debug(f"設定{i}を試行: {config}")
                    ocr = PaddleOCR(**config)
                    logging.info(f"✓ PaddleOCR設定{i}で初期化成功")
                    return ocr, True, None

                except Exception as e:
                    logging.warning(f"設定{i}初期化失敗: {e}")
                    continue

            # 全ての設定で失敗
            return None, False, f"全ての初期化設定が失敗: 最小={e1}"

    except Exception as e:
        logging.error(f"PaddleOCR初期化で予期しないエラー: {e}")
        return None, False, str(e)

    finally:
        # メモリクリア
        gc.collect()


class OCRModelDownloader:
    """OCRモデルのダウンロード管理"""

    # ダウンロード設定
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0  # 秒
    DOWNLOAD_TIMEOUT = 300  # 5分
    CHUNK_SIZE = 8192

    @staticmethod
    def get_paddleocr_cache_dir() -> Path:
        """PaddleOCRのキャッシュディレクトリ取得（標準: ~/.paddleocr）"""
        home_dir = Path.home()
        cache_dir = home_dir / ".paddleocr"

        # キャッシュディレクトリが存在しない場合は作成
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            logging.debug(f"PaddleOCRキャッシュディレクトリ: {cache_dir}")
        except Exception as e:
            logging.error(f"キャッシュディレクトリ作成エラー: {e}")

        return cache_dir

    @staticmethod
    def is_paddleocr_model_available(lang: str = "ja") -> bool:
        """PaddleOCRモデルが利用可能かチェック"""
        if not PADDLEOCR_AVAILABLE:
            return False

        try:
            # PaddleOCR の既定キャッシュ
            poc = OCRModelDownloader.get_paddleocr_cache_dir()
            # 代表的なディレクトリが生成されているかでざっくり判定
            if poc.exists() and any(poc.rglob("inference.*")):
                return True
            # 任意: PaddleX 側の公式モデルも見る（存在すれば OK とみなす）
            px = Path.home() / ".paddlex" / "official_models"
            if px.exists() and any(px.iterdir()):
                return True
            return False

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
    def _apply_windows_specific_settings():
        """Windows環境向け固有設定の適用"""
        try:
            if sys.platform == 'win32':
                # 環境変数の設定
                os.environ.setdefault('CUDA_VISIBLE_DEVICES', '-1')  # GPU無効化
                os.environ.setdefault('PADDLE_DISABLE_STATIC', '1')  # 静的グラフ無効化

                # Windows環境でのPaddleパフォーマンス向上
                os.environ.setdefault('FLAGS_allocator_strategy', 'auto_growth')
                os.environ.setdefault('FLAGS_fraction_of_gpu_memory_to_use', '0.1')

                # マルチプロセス設定
                os.environ.setdefault('FLAGS_eager_delete_tensor_gb', '0.0')

                logging.debug("Windows環境向けPaddle設定を適用しました")

        except Exception as e:
            logging.debug(f"Windows固有設定の適用に失敗: {e}")

    @staticmethod
    def _get_windows_system_info() -> str:
        """Windows環境のシステム情報取得"""
        try:
            import platform
            info_lines = []

            # 基本システム情報
            info_lines.append(f"OS: {platform.system()} {platform.release()}")
            info_lines.append(f"Python: {platform.python_version()}")
            info_lines.append(f"Architecture: {platform.machine()}")

            # PaddleOCR関連の環境変数
            paddle_vars = [
                'CUDA_VISIBLE_DEVICES', 'PADDLE_DISABLE_STATIC',
                'FLAGS_allocator_strategy', 'FLAGS_fraction_of_gpu_memory_to_use'
            ]

            for var in paddle_vars:
                value = os.environ.get(var, 'Not Set')
                info_lines.append(f"{var}: {value}")

            # PaddleOCRモジュール情報
            try:
                if PADDLEOCR_AVAILABLE:
                    import paddleocr
                    if hasattr(paddleocr, '__version__'):
                        info_lines.append(f"PaddleOCR Version: {paddleocr.__version__}")
                    else:
                        info_lines.append("PaddleOCR Version: Unknown")
                else:
                    info_lines.append("PaddleOCR: Not Available")
            except:
                info_lines.append("PaddleOCR: Import Error")

            # PaddleX情報
            try:
                if PADDLEX_AVAILABLE:
                    import paddlex
                    if hasattr(paddlex, '__version__'):
                        info_lines.append(f"PaddleX Version: {paddlex.__version__}")
                    else:
                        info_lines.append("PaddleX Version: Unknown")
                else:
                    info_lines.append("PaddleX: Not Available")
            except:
                info_lines.append("PaddleX: Import Error")

            # キャッシュディレクトリ情報
            cache_dir = OCRModelDownloader.get_paddleocr_cache_dir()
            if cache_dir.exists():
                try:
                    cache_size = sum(f.stat().st_size for f in cache_dir.rglob('*') if f.is_file())
                    info_lines.append(f"Cache Dir: {cache_dir} (Size: {cache_size / 1024 / 1024:.1f} MB)")
                except:
                    info_lines.append(f"Cache Dir: {cache_dir} (Size: Unknown)")
            else:
                info_lines.append(f"Cache Dir: {cache_dir} (Not Exists)")

            return "Windows System Info:\n" + "\n".join(f"  {line}" for line in info_lines)

        except Exception as e:
            return f"Windows System Info: 取得エラー - {e}"

    @staticmethod
    def _create_paddleocr_with_timeout(lang: str, progress_callback: Optional[Callable], attempt: int):
        """タイムアウト設定付きPaddleOCRインスタンス作成（Windows環境強化版）"""
        errors_log = []  # 詳細なエラーログを保存

        try:
            if progress_callback:
                progress_callback(f"PaddleOCRインスタンス作成中... (試行 {attempt + 1})", 30 + (attempt * 20))

            # Windows環境での追加設定
            OCRModelDownloader._apply_windows_specific_settings()

            # タイムアウト設定
            import socket
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(OCRModelDownloader.DOWNLOAD_TIMEOUT)

            try:
                # PaddleOCRの言語コード変換
                paddle_lang = "japan" if lang in ["ja", "japanese"] else lang

                # 新しいPaddleX v3.2+を優先して試行
                if PADDLEX_AVAILABLE:
                    try:
                        logging.info("PaddleX v3.2+でのパイプライン作成を開始...")
                        paddle_pipeline = None
                        paddlex_errors = []

                        # 方法1: 直接OCRタスクを指定
                        try:
                            logging.debug("PaddleX方法1: create_pipeline(task='OCR')を試行...")
                            paddle_pipeline = create_pipeline(task="OCR")
                            logging.info("PaddleX方法1: 成功")
                        except Exception as e1:
                            error_msg = f"方法1失敗: {type(e1).__name__}: {str(e1)}"
                            paddlex_errors.append(error_msg)
                            logging.debug(error_msg)

                        # 方法2: 設定ファイルパスを指定
                        if paddle_pipeline is None:
                            try:
                                logging.debug("PaddleX方法2: create_pipeline(pipeline='OCR')を試行...")
                                paddle_pipeline = create_pipeline(pipeline="OCR")
                                logging.info("PaddleX方法2: 成功")
                            except Exception as e2:
                                error_msg = f"方法2失敗: {type(e2).__name__}: {str(e2)}"
                                paddlex_errors.append(error_msg)
                                logging.debug(error_msg)

                        # 方法3: 明示的な設定で作成
                        if paddle_pipeline is None:
                            try:
                                logging.debug("PaddleX方法3: 明示的設定でパイプライン作成を試行...")
                                paddle_pipeline = create_pipeline(
                                    task="OCR",
                                    pipeline="OCR-B",
                                    device="cpu"
                                )
                                logging.info("PaddleX方法3: 成功")
                            except Exception as e3:
                                error_msg = f"方法3失敗: {type(e3).__name__}: {str(e3)}"
                                paddlex_errors.append(error_msg)
                                logging.debug(error_msg)

                        # 方法4: Windows環境向け最小設定
                        if paddle_pipeline is None:
                            try:
                                logging.debug("PaddleX方法4: Windows向け最小設定を試行...")
                                paddle_pipeline = create_pipeline(
                                    task="OCR",
                                    device="cpu",
                                    precision="fp32"
                                )
                                logging.info("PaddleX方法4: 成功")
                            except Exception as e4:
                                error_msg = f"方法4失敗: {type(e4).__name__}: {str(e4)}"
                                paddlex_errors.append(error_msg)
                                logging.debug(error_msg)

                        if paddle_pipeline:
                            if progress_callback:
                                progress_callback("PaddleXパイプライン作成完了", 70 + (attempt * 5))
                            logging.info("PaddleXパイプライン作成成功")
                            return paddle_pipeline
                        else:
                            paddlex_error_summary = "; ".join(paddlex_errors)
                            errors_log.append(f"PaddleX全失敗: {paddlex_error_summary}")

                    except Exception as e:
                        error_msg = f"PaddleX初期化例外: {type(e).__name__}: {str(e)}"
                        errors_log.append(error_msg)
                        logging.warning(error_msg)

                # 従来のPaddleOCRを使用（フォールバック） - 安全な初期化方式を使用
                if PADDLEOCR_AVAILABLE:
                    try:
                        logging.info("従来PaddleOCRでのフォールバックを開始...")

                        # Windows環境向けの基本設定
                        base_kwargs = {
                            "lang": paddle_lang,
                            "use_angle_cls": True,
                        }

                        # Windows でも上位設定を尊重。必要があれば追加で setdefault のみ行う
                        if sys.platform == 'win32':
                            base_kwargs.setdefault('use_gpu', False)

                        # 安全なPaddleOCR初期化を実行
                        ocr, success, error_message = _safe_paddleocr_init(base_kwargs)

                        if success and ocr:
                            if progress_callback:
                                progress_callback("従来PaddleOCR作成完了", 70 + (attempt * 5))
                            logging.info("従来PaddleOCR作成成功")
                            return ocr
                        else:
                            raise Exception(f"安全な初期化に失敗: {error_message}")

                    except Exception as e:
                        error_msg = f"従来PaddleOCR失敗: {type(e).__name__}: {str(e)}"
                        errors_log.append(error_msg)
                        logging.warning(error_msg)

                # 全ての方法が失敗した場合の詳細エラー
                detailed_errors = "; ".join(errors_log)
                raise Exception(f"PaddleOCRインスタンスの作成に失敗しました（全ての方法が失敗）。詳細: {detailed_errors}")

            finally:
                # タイムアウトを元に戻す
                socket.setdefaulttimeout(original_timeout)

        except Exception as e:
            # Windows環境での追加情報を含む詳細エラー
            system_info = OCRModelDownloader._get_windows_system_info()
            raise Exception(f"PaddleOCRインスタンス作成エラー: {str(e)}\n\n{system_info}")

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
        self.is_paddlex = False  # PaddleXパイプラインを使用しているかのフラグ

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

            # Windows環境向け設定の適用
            OCRModelDownloader._apply_windows_specific_settings()

            # 新しいPaddleX v3.2+を優先して試行
            if PADDLEX_AVAILABLE:
                try:
                    logging.info("PaddleX v3.2+での初期化を開始...")
                    paddle_pipeline = None
                    paddlex_errors = []

                    # 方法1: 直接OCRタスクを指定
                    try:
                        logging.debug("PaddleX方法1: create_pipeline(task='OCR')を試行...")
                        paddle_pipeline = create_pipeline(task="OCR")
                        logging.info("PaddleX方法1: 成功")
                    except Exception as e1:
                        error_msg = f"方法1失敗: {type(e1).__name__}: {str(e1)}"
                        paddlex_errors.append(error_msg)
                        logging.debug(error_msg)

                    # 方法2: 設定ファイルパスを指定
                    if paddle_pipeline is None:
                        try:
                            logging.debug("PaddleX方法2: create_pipeline(pipeline='OCR')を試行...")
                            paddle_pipeline = create_pipeline(pipeline="OCR")
                            logging.info("PaddleX方法2: 成功")
                        except Exception as e2:
                            error_msg = f"方法2失敗: {type(e2).__name__}: {str(e2)}"
                            paddlex_errors.append(error_msg)
                            logging.debug(error_msg)

                    # 方法3: 明示的な設定で作成
                    if paddle_pipeline is None:
                        try:
                            logging.debug("PaddleX方法3: 明示的設定でパイプライン作成を試行...")
                            paddle_pipeline = create_pipeline(
                                task="OCR",
                                pipeline="OCR-B",
                                device="cpu"
                            )
                            logging.info("PaddleX方法3: 成功")
                        except Exception as e3:
                            error_msg = f"方法3失敗: {type(e3).__name__}: {str(e3)}"
                            paddlex_errors.append(error_msg)
                            logging.debug(error_msg)

                    # 方法4: Windows環境向け最小設定
                    if paddle_pipeline is None:
                        try:
                            logging.debug("PaddleX方法4: Windows向け最小設定を試行...")
                            paddle_pipeline = create_pipeline(
                                task="OCR",
                                device="cpu",
                                precision="fp32"
                            )
                            logging.info("PaddleX方法4: 成功")
                        except Exception as e4:
                            error_msg = f"方法4失敗: {type(e4).__name__}: {str(e4)}"
                            paddlex_errors.append(error_msg)
                            logging.debug(error_msg)

                    if paddle_pipeline:
                        self.ocr_model = paddle_pipeline
                        self.is_paddlex = True
                        logging.info("PaddleXパイプラインで初期化完了")
                    else:
                        paddlex_error_summary = "; ".join(paddlex_errors)
                        raise Exception(f"PaddleXパイプラインの作成に失敗: {paddlex_error_summary}")

                except Exception as e:
                    logging.warning(f"PaddleXパイプライン作成失敗、従来APIを使用: {e}")
                    # フォールバックして従来のPaddleOCRを使用
                    if PADDLEOCR_AVAILABLE:
                        from paddleocr import PaddleOCR

                        # Windows環境向けの基本設定
                        base_kwargs = {
                            "lang": paddle_lang,
                            "use_angle_cls": True,
                        }

                        # 安全なPaddleOCR設定を作成
                        paddleocr_kwargs = _create_safe_paddleocr_kwargs(base_kwargs)

                        # Windows でも上位設定を尊重。必要があれば追加で setdefault のみ行う
                        if sys.platform == 'win32':
                            paddleocr_kwargs.setdefault('use_gpu', False)

                        logging.debug(f"従来PaddleOCR設定: {paddleocr_kwargs}")
                        self.ocr_model = PaddleOCR(**paddleocr_kwargs)
                        self.is_paddlex = False
                        logging.info("従来のPaddleOCRで初期化完了")
                    else:
                        raise e
            else:
                # 従来のPaddleOCRを使用
                from paddleocr import PaddleOCR

                # Windows環境向けの基本設定
                base_kwargs = {
                    "lang": paddle_lang,
                    "use_angle_cls": True,
                }

                # 安全なPaddleOCR設定を作成
                paddleocr_kwargs = _create_safe_paddleocr_kwargs(base_kwargs)

                # Windows でも上位設定を尊重。必要があれば追加で setdefault のみ行う
                if sys.platform == 'win32':
                    paddleocr_kwargs.setdefault('use_gpu', False)

                logging.debug(f"従来PaddleOCR設定: {paddleocr_kwargs}")
                self.ocr_model = PaddleOCR(**paddleocr_kwargs)
                self.is_paddlex = False
                logging.info("従来のPaddleOCRで初期化完了")

            if download_callback:
                download_callback("初期化完了", 100)

            self.is_initialized = True
            logging.info("PaddleOCRの初期化が完了しました")
            return True

        except Exception as e:
            # Windows環境での詳細エラー情報を含める
            error_msg = f"PaddleOCRの初期化に失敗しました: {e}"

            if sys.platform == 'win32':
                system_info = OCRModelDownloader._get_windows_system_info()
                error_msg += f"\n\n{system_info}"

            logging.error(error_msg)
            return False
    
    def extract_text(self, image: np.ndarray) -> List[OCRResult]:
        """PaddleOCRでテキスト抽出"""
        if not self.is_initialized or not self.ocr_model:
            return []
        
        try:
            # 前処理
            processed_image = self.preprocess_image(image)
            
            # OCR実行（PaddleXとPaddleOCRの両方に対応）
            if self.is_paddlex:
                # PaddleXパイプラインを使用
                try:
                    paddle_result = self.ocr_model.predict(processed_image)
                    results = self._convert_paddlex_results(paddle_result)
                except Exception as e:
                    logging.error(f"PaddleX実行エラー: {e}")
                    results = [[]]
            else:
                # 従来のPaddleOCRを使用
                try:
                    results = self.ocr_model.ocr(processed_image)
                except Exception as e:
                    logging.error(f"PaddleOCR実行エラー: {e}")
                    results = [[]]
            
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

    def _convert_paddlex_results(self, paddle_result):
        """PaddleXパイプラインの結果を従来のPaddleOCR形式に変換"""
        try:
            converted_results = [[]]

            # PaddleXの結果構造を解析
            if hasattr(paddle_result, 'json') and paddle_result.json:
                # OCRパイプラインの結果から情報を抽出
                for item in paddle_result.json.get('dt_polys', []):
                    bbox_points = item.get('poly', [])
                    text = item.get('text', '')
                    confidence = item.get('score', 0.0)

                    if text and confidence > 0.5:
                        converted_results[0].append([bbox_points, [text, confidence]])
            elif hasattr(paddle_result, 'result'):
                # 別の形式の結果構造
                result = paddle_result.result
                if isinstance(result, dict) and 'texts' in result:
                    for i, text in enumerate(result['texts']):
                        if text.strip():
                            # 簡易的なbboxを生成（実際の座標がない場合）
                            bbox = [[0, i*20], [100, i*20], [100, (i+1)*20], [0, (i+1)*20]]
                            confidence = result.get('scores', [0.9])[i] if i < len(result.get('scores', [])) else 0.9
                            converted_results[0].append([bbox, [text, confidence]])

            return converted_results

        except Exception as e:
            logging.debug(f"PaddleX結果変換エラー: {e}")
            return [[]]

    def _convert_new_api_results(self, api_result):
        """旧メソッド名の互換性維持"""
        return self._convert_paddlex_results(api_result)


class BundledPaddleOCREngine(OCREngine):
    """組み込みモデルを使用するPaddleOCRエンジン実装"""

    def __init__(self, language: str = "ja"):
        super().__init__(language)
        self.ocr_model = None
        self.confidence_threshold = 0.7
        self.is_paddlex = False

    def get_bundled_model_path(self) -> Optional[Path]:
        """組み込みモデルのパスを取得"""
        try:
            # 実行ファイルからの相対パス（PyInstaller対応）
            if getattr(sys, 'frozen', False):
                # PyInstallerでビルドされた実行ファイルの場合
                base_path = Path(sys._MEIPASS)
            else:
                # 開発環境の場合
                base_path = Path(__file__).parent.parent.parent

            models_path = base_path / "models" / "paddleocr"

            if models_path.exists():
                logging.info(f"組み込みモデルパス: {models_path}")
                return models_path
            else:
                logging.warning(f"組み込みモデルが見つかりません: {models_path}")
                return None

        except Exception as e:
            logging.error(f"組み込みモデルパス取得エラー: {e}")
            return None

    def initialize(self, download_callback: Optional[Callable[[str, int], None]] = None) -> bool:
        """組み込みモデルを使用したPaddleOCRの初期化"""
        if not PADDLEOCR_AVAILABLE:
            logging.error("PaddleOCRが利用できません")
            return False

        try:
            if download_callback:
                download_callback("組み込みモデルを読み込み中...", 10)

            # 組み込みモデルパスを取得
            models_path = self.get_bundled_model_path()
            if not models_path:
                raise Exception("組み込みモデルが見つかりません")

            # モデルディレクトリの確認
            det_model_path = models_path / "PP-OCRv5_server_det"
            rec_model_path = models_path / "PP-OCRv5_server_rec"

            if not det_model_path.exists():
                raise Exception(f"テキスト検出モデルが見つかりません: {det_model_path}")
            if not rec_model_path.exists():
                raise Exception(f"テキスト認識モデルが見つかりません: {rec_model_path}")

            logging.info(f"検出モデル: {det_model_path}")
            logging.info(f"認識モデル: {rec_model_path}")

            if download_callback:
                download_callback("PaddleOCRエンジンを初期化中...", 50)

            # Windows環境向け設定の適用
            OCRModelDownloader._apply_windows_specific_settings()

            # PaddleOCRの言語コード変換
            paddle_lang = "japan" if self.language in ["ja", "japanese"] else self.language

            # 組み込みモデルを使用してPaddleOCRを初期化 - 安全な初期化方式を使用
            try:
                # 基本的な組み込みモデル設定
                base_kwargs = {
                    "det_model_dir": str(det_model_path),
                    "rec_model_dir": str(rec_model_path),
                    "use_angle_cls": True,          # 角度補正は既定で有効
                    "lang": paddle_lang,
                    "show_log": False,
                    "use_space_char": True,
                    "drop_score": 0.5
                }

                if download_callback:
                    download_callback("PaddleOCRインスタンス作成中...", 80)

                # 安全なPaddleOCR初期化を実行
                ocr_instance, success, error_message = _safe_paddleocr_init(base_kwargs)

                if success and ocr_instance:
                    self.ocr_model = ocr_instance
                    self.is_paddlex = False

                    if download_callback:
                        download_callback("初期化完了", 100)

                    self.is_initialized = True
                else:
                    raise Exception(f"組み込みモデルでの安全な初期化に失敗: {error_message}")
                logging.info("組み込みモデルでのPaddleOCR初期化が完了しました")
                return True

            except Exception as e:
                error_msg = f"組み込みPaddleOCR初期化失敗: {type(e).__name__}: {str(e)}"
                logging.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            # エラー情報を含める
            error_msg = f"組み込みPaddleOCRの初期化に失敗しました: {e}"

            if sys.platform == 'win32':
                system_info = OCRModelDownloader._get_windows_system_info()
                error_msg += f"\n\n{system_info}"

            logging.error(error_msg)
            return False

    def extract_text(self, image: np.ndarray) -> List[OCRResult]:
        """組み込みPaddleOCRでテキスト抽出"""
        if not self.is_initialized or not self.ocr_model:
            return []

        try:
            # 前処理
            processed_image = self.preprocess_image(image)

            # OCR実行（従来のPaddleOCRを使用）
            try:
                results = self.ocr_model.ocr(processed_image)
            except Exception as e:
                logging.error(f"組み込みPaddleOCR実行エラー: {e}")
                results = [[]]

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
            logging.error(f"組み込みPaddleOCR実行エラー: {e}")
            return []


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

        # 利用可能なエンジンを登録（組み込みモデル優先）
        if PADDLEOCR_AVAILABLE:
            # 組み込みモデルエンジンを優先
            self.engines['paddleocr_bundled'] = BundledPaddleOCREngine()
            # フォールバック用に従来のダウンロード版も登録
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

        # PaddleOCRエンジンの場合はダウンロードコールバックを渡す
        if isinstance(engine, (PaddleOCREngine, BundledPaddleOCREngine)):
            success = engine.initialize(download_callback)
        else:
            success = engine.initialize()

        if success:
            self.current_engine = engine
            logging.info(f"OCRエンジンを切り替えました: {engine_name}")
            return True

        return False

    def initialize_best_available_engine(self, download_callback: Optional[Callable[[str, int], None]] = None) -> bool:
        """最適なエンジンを自動選択して初期化"""
        # 1. 組み込みPaddleOCRを最優先で試行
        if 'paddleocr_bundled' in self.engines:
            if download_callback:
                download_callback("組み込みPaddleOCRを初期化中...", 0)
            if self.initialize_engine('paddleocr_bundled', download_callback):
                logging.info("組み込みPaddleOCRエンジンで初期化成功")
                return True
            else:
                logging.warning("組み込みPaddleOCRエンジンの初期化に失敗、フォールバックします")

        # 2. 従来のPaddleOCR（ダウンロード版）を試行
        if 'paddleocr' in self.engines:
            if download_callback:
                download_callback("従来PaddleOCRを初期化中...", 0)
            if self.initialize_engine('paddleocr', download_callback):
                logging.info("従来PaddleOCRエンジンで初期化成功")
                return True
            else:
                logging.warning("従来PaddleOCRエンジンの初期化に失敗")

        # 3. 最後にTesseractを試行
        if 'tesseract' in self.engines:
            if download_callback:
                download_callback("Tesseractエンジンを初期化中...", 0)
            if self.initialize_engine('tesseract'):
                logging.info("Tesseractエンジンで初期化成功")
                return True

        logging.error("利用可能なOCRエンジンがありません")
        return False

    def is_any_engine_available(self) -> bool:
        """いずれかのOCRエンジンが利用可能かチェック"""
        # 1. 組み込みPaddleOCRをチェック
        if 'paddleocr_bundled' in self.engines:
            bundled_engine = self.engines['paddleocr_bundled']
            if isinstance(bundled_engine, BundledPaddleOCREngine):
                bundled_path = bundled_engine.get_bundled_model_path()
                if bundled_path and bundled_path.exists():
                    logging.debug("組み込みPaddleOCRモデルが利用可能")
                    return True

        # 2. 従来のPaddleOCRをチェック
        if 'paddleocr' in self.engines:
            if PADDLEOCR_AVAILABLE and OCRModelDownloader.is_paddleocr_model_available():
                logging.debug("従来PaddleOCRモデルが利用可能")
                return True

        # 3. Tesseractをチェック
        if 'tesseract' in self.engines:
            if TESSERACT_AVAILABLE:
                logging.debug("Tesseractエンジンが利用可能")
                return True

        return False

    def get_recommended_engine(self) -> Optional[str]:
        """推奨エンジンを取得"""
        # 1. 組み込みPaddleOCRを最優先
        if 'paddleocr_bundled' in self.engines:
            bundled_engine = self.engines['paddleocr_bundled']
            if isinstance(bundled_engine, BundledPaddleOCREngine):
                bundled_path = bundled_engine.get_bundled_model_path()
                if bundled_path and bundled_path.exists():
                    return 'paddleocr_bundled'

        # 2. 従来のPaddleOCR
        if 'paddleocr' in self.engines:
            if PADDLEOCR_AVAILABLE and OCRModelDownloader.is_paddleocr_model_available():
                return 'paddleocr'

        # 3. Tesseract
        if 'tesseract' in self.engines:
            if TESSERACT_AVAILABLE:
                return 'tesseract'

        return None

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