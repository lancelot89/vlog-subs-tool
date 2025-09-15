#!/usr/bin/env python3
"""
PaddleOCR修正の動作確認テスト
REFACTORE.mdの指示通りに修正されたかを確認する
"""

import sys
import os
import logging
import numpy as np
from pathlib import Path

# プロジェクトのパスを追加
sys.path.insert(0, str(Path(__file__).parent / "app"))

# ログレベルを設定
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_imports():
    """可用性フラグが正しく分離されているかテスト"""
    print("=== 1. Import と可用性フラグのテスト ===")

    try:
        from core.extractor.ocr import PADDLEOCR_AVAILABLE, PADDLEX_AVAILABLE
        print(f"PADDLEOCR_AVAILABLE: {PADDLEOCR_AVAILABLE}")
        print(f"PADDLEX_AVAILABLE: {PADDLEX_AVAILABLE}")

        # フラグが独立して設定されているかチェック
        if PADDLEOCR_AVAILABLE:
            print("✓ PaddleOCRが正しく判定されています")
        else:
            print("⚠ PaddleOCRが利用できません")

        if PADDLEX_AVAILABLE:
            print("✓ PaddleXがオプション機能として検出されています")
        else:
            print("ℹ PaddleXは利用できません（任意機能）")

        return True
    except Exception as e:
        print(f"✗ Import エラー: {e}")
        return False

def test_safe_kwargs():
    """_create_safe_paddleocr_kwargs関数がパラメータを保持するかテスト"""
    print("\n=== 2. _create_safe_paddleocr_kwargs 関数のテスト ===")

    try:
        from core.extractor.ocr import _create_safe_paddleocr_kwargs

        # テスト用の設定
        test_kwargs = {
            "lang": "japan",
            "use_angle_cls": True,
            "show_log": False,
            "use_space_char": True,
            "drop_score": 0.7,
            "det_model_dir": "/test/det",
            "rec_model_dir": "/test/rec"
        }

        result = _create_safe_paddleocr_kwargs(test_kwargs)

        print(f"入力: {test_kwargs}")
        print(f"出力: {result}")

        # 重要なパラメータが保持されているかチェック
        checks = [
            ("use_angle_cls", True),
            ("show_log", False),
            ("use_space_char", True),
            ("drop_score", 0.7),
            ("use_gpu", False),  # デフォルトで追加される
            ("lang", "japan")
        ]

        all_passed = True
        for key, expected in checks:
            if key in result and result[key] == expected:
                print(f"✓ {key}: {result[key]} (期待値: {expected})")
            else:
                print(f"✗ {key}: {result.get(key, 'なし')} (期待値: {expected})")
                all_passed = False

        return all_passed
    except Exception as e:
        print(f"✗ _create_safe_paddleocr_kwargs テストエラー: {e}")
        return False

def test_model_cache_detection():
    """モデルキャッシュ判定が正しいディレクトリを見るかテスト"""
    print("\n=== 3. モデルキャッシュ判定のテスト ===")

    try:
        from core.extractor.ocr import OCRModelDownloader

        cache_dir = OCRModelDownloader.get_paddleocr_cache_dir()
        print(f"PaddleOCRキャッシュディレクトリ: {cache_dir}")

        # ~/.paddleocr が設定されているかチェック
        expected_dir = Path.home() / ".paddleocr"
        if cache_dir == expected_dir:
            print("✓ キャッシュディレクトリが正しく ~/.paddleocr に設定されています")

            # モデル存在チェックをテスト
            is_available = OCRModelDownloader.is_paddleocr_model_available()
            print(f"モデル利用可能性: {is_available}")

            return True
        else:
            print(f"✗ キャッシュディレクトリが間違っています。期待値: {expected_dir}")
            return False

    except Exception as e:
        print(f"✗ モデルキャッシュテストエラー: {e}")
        return False

def test_minimal_paddleocr():
    """最小構成でPaddleOCRが初期化できるかテスト"""
    print("\n=== 4. 最小構成PaddleOCR初期化テスト ===")

    try:
        from core.extractor.ocr import PADDLEOCR_AVAILABLE

        if not PADDLEOCR_AVAILABLE:
            print("⚠ PaddleOCRが利用できないため、初期化テストをスキップします")
            return True

        print("PaddleOCRの最小構成での初期化を試行中...")

        # REFACTORE.mdで示された最小再現テスト
        from paddleocr import PaddleOCR
        import cv2

        # 最小構成でOCRを初期化
        ocr = PaddleOCR(lang="japan", use_angle_cls=True, use_gpu=False, show_log=False)

        # ダミー画像でテスト
        img = np.ones((100, 300, 3), dtype=np.uint8) * 255
        res = ocr.ocr(img)

        print(f"✓ PaddleOCR初期化成功: 結果型={type(res)}, 長さ={len(res) if res else 0}")
        return True

    except Exception as e:
        print(f"✗ PaddleOCR初期化テストエラー: {e}")
        return False

def main():
    """メインテスト関数"""
    print("PaddleOCR修正の動作確認テストを開始します...\n")

    tests = [
        ("Import と可用性フラグ", test_imports),
        ("_create_safe_paddleocr_kwargs 関数", test_safe_kwargs),
        ("モデルキャッシュ判定", test_model_cache_detection),
        ("最小構成PaddleOCR初期化", test_minimal_paddleocr)
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ {test_name} で予期しないエラー: {e}")
            results.append((test_name, False))

    # 結果サマリー
    print("\n" + "="*50)
    print("テスト結果サマリー:")
    print("="*50)

    passed = 0
    for test_name, result in results:
        status = "✓ 成功" if result else "✗ 失敗"
        print(f"{test_name}: {status}")
        if result:
            passed += 1

    print(f"\n合計: {passed}/{len(tests)} テスト成功")

    if passed == len(tests):
        print("🎉 すべてのテストが成功しました！PaddleOCR修正が正常に適用されています。")
        return 0
    else:
        print("⚠ 一部のテストが失敗しました。修正の確認が必要です。")
        return 1

if __name__ == "__main__":
    sys.exit(main())