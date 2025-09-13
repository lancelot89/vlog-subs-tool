"""
OCRエンジンの実装（PaddleOCR / Tesseract対応）
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path
import logging

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
    
    def initialize(self) -> bool:
        """PaddleOCRの初期化"""
        if not PADDLEOCR_AVAILABLE:
            logging.error("PaddleOCRが利用できません")
            return False
        
        try:
            # PaddleOCRモデルの初期化
            self.ocr_model = PaddleOCR(
                use_angle_cls=True,
                lang=self.language,
                show_log=False
            )
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
            
            # OCR実行
            results = self.ocr_model.ocr(processed_image, cls=True)
            
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
    
    def initialize_engine(self, engine_name: str) -> bool:
        """指定エンジンの初期化"""
        if engine_name not in self.engines:
            logging.error(f"未対応のOCRエンジン: {engine_name}")
            return False
        
        engine = self.engines[engine_name]
        if engine.initialize():
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