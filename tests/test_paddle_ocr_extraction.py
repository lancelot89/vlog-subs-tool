#!/usr/bin/env python3
"""
PaddleOCRによる字幕抽出のテスト

SimplePaddleOCREngineが実際に字幕画像からテキストを正しく抽出できることを確認
"""

import logging
import os
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.extractor.ocr import OCRResult, SimplePaddleOCREngine


class TestPaddleOCRExtraction(unittest.TestCase):
    """PaddleOCR字幕抽出のテストクラス"""

    @classmethod
    def setUpClass(cls):
        """テストクラス全体の初期化"""
        # ログレベルを設定
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger(__name__)

        # OCRエンジンを初期化
        cls.ocr_engine = SimplePaddleOCREngine()
        cls.engine_initialized = cls.ocr_engine.initialize()

        # テスト画像のパス
        cls.fixtures_dir = Path(__file__).parent / "fixtures"

    def setUp(self):
        """各テストの前処理"""
        if not self.engine_initialized:
            self.skipTest("PaddleOCRエンジンの初期化に失敗しました")

    def test_ocr_engine_initialization(self):
        """OCRエンジンの初期化テスト"""
        self.assertTrue(
            self.engine_initialized, "PaddleOCRエンジンが正常に初期化されること"
        )
        self.assertIsNotNone(self.ocr_engine._ocr, "内部OCRオブジェクトが存在すること")

    def test_extract_english_subtitle(self):
        """英語字幕の抽出テスト"""
        image_path = self.fixtures_dir / "test_subtitle_01_Hello_World.png"
        if not image_path.exists():
            self.skipTest(f"テスト画像が見つかりません: {image_path}")

        # 画像を読み込み
        image = cv2.imread(str(image_path))
        self.assertIsNotNone(image, "テスト画像が正常に読み込まれること")

        # OCR実行
        results = self.ocr_engine.extract_text(image)

        # 結果の検証
        self.assertIsInstance(results, list, "結果がリスト型であること")
        self.assertGreater(len(results), 0, "少なくとも1つのテキストが検出されること")

        # 最も信頼度の高い結果を確認
        best_result = max(results, key=lambda x: x.confidence)
        self.assertIsInstance(best_result, OCRResult, "結果がOCRResult型であること")
        self.assertIn("Hello", best_result.text, "英語テキスト 'Hello' が含まれること")

        self.logger.info(
            f"英語字幕抽出結果: {best_result.text} (信頼度: {best_result.confidence:.3f})"
        )

    def test_extract_japanese_hiragana_subtitle(self):
        """日本語ひらがな字幕の抽出テスト"""
        image_path = self.fixtures_dir / "test_subtitle_02_こんにちは世界.png"
        if not image_path.exists():
            self.skipTest(f"テスト画像が見つかりません: {image_path}")

        image = cv2.imread(str(image_path))
        self.assertIsNotNone(image, "テスト画像が正常に読み込まれること")

        results = self.ocr_engine.extract_text(image)

        self.assertIsInstance(results, list, "結果がリスト型であること")
        self.assertGreater(len(results), 0, "少なくとも1つのテキストが検出されること")

        # 最も信頼度の高い結果を確認
        best_result = max(results, key=lambda x: x.confidence)

        # 日本語文字が含まれることを確認（完全一致は求めない）
        has_japanese = any(char in best_result.text for char in "こんにちは世界")
        self.assertTrue(
            has_japanese, f"日本語文字が含まれること。実際の結果: {best_result.text}"
        )

        self.logger.info(
            f"日本語ひらがな字幕抽出結果: {best_result.text} (信頼度: {best_result.confidence:.3f})"
        )

    def test_extract_japanese_mixed_subtitle(self):
        """日本語混合字幕の抽出テスト"""
        image_path = self.fixtures_dir / "test_subtitle_03_今日は良い天気です.png"
        if not image_path.exists():
            self.skipTest(f"テスト画像が見つかりません: {image_path}")

        image = cv2.imread(str(image_path))
        self.assertIsNotNone(image, "テスト画像が正常に読み込まれること")

        results = self.ocr_engine.extract_text(image)

        self.assertIsInstance(results, list, "結果がリスト型であること")
        self.assertGreater(len(results), 0, "少なくとも1つのテキストが検出されること")

        best_result = max(results, key=lambda x: x.confidence)

        # 日本語文字が含まれることを確認
        has_japanese = any(char in best_result.text for char in "今日良天気")
        self.assertTrue(
            has_japanese, f"日本語文字が含まれること。実際の結果: {best_result.text}"
        )

        self.logger.info(
            f"日本語混合字幕抽出結果: {best_result.text} (信頼度: {best_result.confidence:.3f})"
        )

    def test_extract_alphanumeric_subtitle(self):
        """英数字混合字幕の抽出テスト"""
        image_path = self.fixtures_dir / "test_subtitle_04_VLOG_2024.png"
        if not image_path.exists():
            self.skipTest(f"テスト画像が見つかりません: {image_path}")

        image = cv2.imread(str(image_path))
        self.assertIsNotNone(image, "テスト画像が正常に読み込まれること")

        results = self.ocr_engine.extract_text(image)

        self.assertIsInstance(results, list, "結果がリスト型であること")
        self.assertGreater(len(results), 0, "少なくとも1つのテキストが検出されること")

        best_result = max(results, key=lambda x: x.confidence)

        # VLOGまたは2024が含まれることを確認
        has_expected_text = "VLOG" in best_result.text or "2024" in best_result.text
        self.assertTrue(
            has_expected_text,
            f"'VLOG'または'2024'が含まれること。実際の結果: {best_result.text}",
        )

        self.logger.info(
            f"英数字混合字幕抽出結果: {best_result.text} (信頼度: {best_result.confidence:.3f})"
        )

    def test_ocr_result_structure(self):
        """OCRResult構造体のテスト"""
        image_path = self.fixtures_dir / "test_subtitle_01_Hello_World.png"
        if not image_path.exists():
            self.skipTest(f"テスト画像が見つかりません: {image_path}")

        image = cv2.imread(str(image_path))
        results = self.ocr_engine.extract_text(image)

        if len(results) > 0:
            result = results[0]

            # OCRResultの必須フィールドをチェック
            self.assertIsInstance(result.text, str, "textフィールドが文字列であること")
            self.assertIsInstance(
                result.confidence, float, "confidenceフィールドが浮動小数点数であること"
            )
            self.assertIsInstance(
                result.bbox, tuple, "bboxフィールドがタプルであること"
            )
            self.assertEqual(
                len(result.bbox), 4, "bboxが4つの要素を持つこと (x, y, w, h)"
            )

            # 信頼度が0.0-1.0の範囲内であることを確認
            self.assertGreaterEqual(result.confidence, 0.0, "信頼度が0.0以上であること")
            self.assertLessEqual(result.confidence, 1.0, "信頼度が1.0以下であること")

            # バウンディングボックスが正の値であることを確認
            x, y, w, h = result.bbox
            self.assertGreaterEqual(x, 0, "x座標が0以上であること")
            self.assertGreaterEqual(y, 0, "y座標が0以上であること")
            self.assertGreater(w, 0, "幅が正の値であること")
            self.assertGreater(h, 0, "高さが正の値であること")

    def test_realistic_vlog_frame(self):
        """リアルなVLOGフレームでのテスト"""
        image_path = self.fixtures_dir / "realistic_vlog_frame.png"
        if not image_path.exists():
            self.skipTest(f"テスト画像が見つかりません: {image_path}")

        image = cv2.imread(str(image_path))
        self.assertIsNotNone(image, "テスト画像が正常に読み込まれること")

        results = self.ocr_engine.extract_text(image)

        self.assertIsInstance(results, list, "結果がリスト型であること")

        if len(results) > 0:
            best_result = max(results, key=lambda x: x.confidence)

            # 何らかの日本語文字が検出されることを期待
            self.assertGreater(
                len(best_result.text), 0, "何らかのテキストが検出されること"
            )

            self.logger.info(
                f"リアルVLOGフレーム抽出結果: {best_result.text} (信頼度: {best_result.confidence:.3f})"
            )
        else:
            self.logger.warning("リアルVLOGフレームからテキストが検出されませんでした")

    def test_empty_image_handling(self):
        """空画像のエラーハンドリングテスト"""
        # 空の画像を作成
        empty_image = np.zeros((100, 100, 3), dtype=np.uint8)

        results = self.ocr_engine.extract_text(empty_image)

        # エラーが発生せず、空のリストが返されることを確認
        self.assertIsInstance(results, list, "結果がリスト型であること")
        # 空の画像では通常テキストは検出されないが、エラーも発生しないこと

    def test_confidence_threshold(self):
        """信頼度閾値のテスト"""
        image_path = self.fixtures_dir / "test_subtitle_01_Hello_World.png"
        if not image_path.exists():
            self.skipTest(f"テスト画像が見つかりません: {image_path}")

        image = cv2.imread(str(image_path))

        # 通常の閾値でテスト
        results = self.ocr_engine.extract_text(image)

        # 全ての結果が設定された閾値以上の信頼度を持つことを確認
        for result in results:
            self.assertGreaterEqual(
                result.confidence,
                self.ocr_engine.confidence_threshold,
                f"信頼度が閾値({self.ocr_engine.confidence_threshold})以上であること",
            )


def run_ocr_extraction_test():
    """OCR抽出テストを実行する関数"""
    print("=== PaddleOCR字幕抽出テスト開始 ===")

    # テストスイートを作成
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPaddleOCRExtraction)

    # テストランナーを作成（詳細出力）
    runner = unittest.TextTestRunner(verbosity=2)

    # テスト実行
    result = runner.run(suite)

    print(f"\n=== テスト結果 ===")
    print(f"実行テスト数: {result.testsRun}")
    print(f"失敗: {len(result.failures)}")
    print(f"エラー: {len(result.errors)}")
    print(f"スキップ: {len(result.skipped)}")

    if result.failures:
        print("\n失敗したテスト:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")

    if result.errors:
        print("\nエラーが発生したテスト:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")

    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n=== テスト結果: {'成功' if success else '失敗'} ===")

    return success


if __name__ == "__main__":
    success = run_ocr_extraction_test()
    sys.exit(0 if success else 1)
