#!/usr/bin/env python3
"""
2行字幕検出の基本ロジックテスト（依存関係なし）
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class MockOCRResult:
    """OCRResult のモック"""

    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, w, h


def group_by_vertical_position(
    sorted_results: List[MockOCRResult],
) -> List[List[MockOCRResult]]:
    """OCR結果を垂直位置でグループ化（テスト用実装）"""
    if not sorted_results:
        return []

    line_groups = []
    current_group = [sorted_results[0]]
    current_y_center = sorted_results[0].bbox[1] + sorted_results[0].bbox[3] // 2

    # Y座標の許容範囲（テキストの高さの50%程度）
    for result in sorted_results[1:]:
        result_y_center = result.bbox[1] + result.bbox[3] // 2
        text_height = result.bbox[3]

        # 同じ行と判定する垂直距離の閾値
        vertical_threshold = text_height * 0.5

        if abs(result_y_center - current_y_center) <= vertical_threshold:
            # 同じ行のグループに追加
            current_group.append(result)
        else:
            # 新しい行のグループを開始
            line_groups.append(current_group)
            current_group = [result]
            current_y_center = result_y_center

    # 最後のグループを追加
    if current_group:
        line_groups.append(current_group)

    return line_groups


def detect_multiline_text(ocr_results: List[MockOCRResult]) -> str:
    """フレーム内の複数OCR結果から2行字幕を検出・構成（テスト用実装）"""
    if len(ocr_results) <= 1:
        return ocr_results[0].text if ocr_results else ""

    # OCR結果をY座標でソート（上から下へ）
    sorted_results = sorted(ocr_results, key=lambda x: x.bbox[1])

    # 2行字幕の候補を検出
    line_groups = group_by_vertical_position(sorted_results)

    if len(line_groups) >= 2:
        # 2行以上の場合、最初の2つのグループを使用
        line1_texts = [result.text for result in line_groups[0]]
        line2_texts = [result.text for result in line_groups[1]]

        # 各行内でX座標順にソート
        line1_texts.sort(
            key=lambda text: next(
                result.bbox[0] for result in line_groups[0] if result.text == text
            )
        )
        line2_texts.sort(
            key=lambda text: next(
                result.bbox[0] for result in line_groups[1] if result.text == text
            )
        )

        # 行を結合
        line1 = " ".join(line1_texts).strip()
        line2 = " ".join(line2_texts).strip()

        if line1 and line2:
            return f"{line1}\n{line2}"

    # 2行構成できない場合は最初の結果を返す
    return sorted_results[0].text if sorted_results else ""


def test_multiline_detection():
    """2行字幕検出のテスト"""
    print("2行字幕検出ロジックのテスト開始...")

    # モックOCR結果を作成（2行字幕のシミュレーション）
    # 上段: "こんにちは" (Y座標: 50-70)
    # 下段: "皆さん" (Y座標: 80-100)
    ocr_results = [
        MockOCRResult(text="こんにちは", confidence=0.9, bbox=(100, 50, 120, 20)),  # 1行目
        MockOCRResult(text="皆さん", confidence=0.85, bbox=(110, 80, 80, 20)),  # 2行目
    ]

    # 2行字幕検出を実行
    detected_text = detect_multiline_text(ocr_results)

    print(f"検出されたテキスト: '{detected_text}'")

    # 期待結果の確認
    expected = "こんにちは\n皆さん"
    if detected_text == expected:
        print("✅ テスト成功: 2行字幕が正しく検出されました")
        return True
    else:
        print(f"❌ テスト失敗: 期待値 '{expected}' != 実際 '{detected_text}'")
        return False


def test_single_line_fallback():
    """単行字幕のフォールバック処理テスト"""
    print("\n単行字幕フォールバック処理のテスト...")

    # 単一のOCR結果
    ocr_results = [
        MockOCRResult(text="こんにちは皆さん", confidence=0.9, bbox=(100, 50, 200, 20)),
    ]

    detected_text = detect_multiline_text(ocr_results)

    print(f"検出されたテキスト: '{detected_text}'")

    # 単行として処理されることを確認
    expected = "こんにちは皆さん"
    if detected_text == expected and "\n" not in detected_text:
        print("✅ テスト成功: 単行字幕が正しく処理されました")
        return True
    else:
        print(f"❌ テスト失敗: 期待値 '{expected}' != 実際 '{detected_text}'")
        return False


def test_horizontal_ordering():
    """水平方向の文字順序テスト"""
    print("\n水平方向文字順序のテスト...")

    # 2行で、各行に複数の文字が水平に配置
    ocr_results = [
        MockOCRResult(text="んにちは", confidence=0.9, bbox=(150, 50, 80, 20)),  # 1行目右
        MockOCRResult(text="こ", confidence=0.85, bbox=(100, 50, 30, 20)),  # 1行目左
        MockOCRResult(text="さん", confidence=0.8, bbox=(150, 80, 60, 20)),  # 2行目右
        MockOCRResult(text="皆", confidence=0.85, bbox=(110, 80, 30, 20)),  # 2行目左
    ]

    detected_text = detect_multiline_text(ocr_results)

    print(f"検出されたテキスト: '{detected_text}'")

    # 正しい順序で結合されることを確認
    expected = "こ んにちは\n皆 さん"
    if detected_text == expected:
        print("✅ テスト成功: 水平順序が正しく処理されました")
        return True
    else:
        print(f"❌ テスト失敗: 期待値 '{expected}' != 実際 '{detected_text}'")
        return False


def test_same_line_grouping():
    """同一行のグルーピングテスト"""
    print("\n同一行グルーピングのテスト...")

    # Y座標が近い複数のテキスト（同一行とみなされるべき）
    ocr_results = [
        MockOCRResult(text="こんに", confidence=0.9, bbox=(100, 50, 60, 20)),
        MockOCRResult(
            text="ちは", confidence=0.85, bbox=(170, 52, 40, 18)
        ),  # わずかにY座標がずれている
        MockOCRResult(text="皆さん", confidence=0.8, bbox=(110, 90, 80, 20)),  # 明らかに異なる行
    ]

    detected_text = detect_multiline_text(ocr_results)

    print(f"検出されたテキスト: '{detected_text}'")

    # 1行目のテキストが結合され、2行目が分離されることを確認
    expected = "こんに ちは\n皆さん"
    if detected_text == expected:
        print("✅ テスト成功: 同一行グルーピングが正しく動作しました")
        return True
    else:
        print(f"❌ テスト失敗: 期待値 '{expected}' != 実際 '{detected_text}'")
        return False


if __name__ == "__main__":
    print("=== 2行字幕検出機能の基本ロジックテスト ===\n")

    success_count = 0
    total_tests = 4

    if test_multiline_detection():
        success_count += 1

    if test_single_line_fallback():
        success_count += 1

    if test_horizontal_ordering():
        success_count += 1

    if test_same_line_grouping():
        success_count += 1

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 すべてのテストが成功しました！")
    else:
        print("❌ 一部のテストが失敗しました")
