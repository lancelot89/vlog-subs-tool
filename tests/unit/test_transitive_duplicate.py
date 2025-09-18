#!/usr/bin/env python3
"""
連鎖的重複（A≈B≈C）のテスト
PRコメント対応 - assert文使用版
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@dataclass
class MockSubtitleItem:
    """SubtitleItem のモック"""

    index: int
    start_ms: int
    end_ms: int
    text: str
    bbox: Optional[Tuple[int, int, int, int]] = None


class MockTextSimilarityCalculator:
    """簡易版テキスト類似度計算器"""

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0

        if text1 == text2:
            return 1.0

        # 編集距離ベースの類似度計算
        edit_distance = MockTextSimilarityCalculator._calculate_edit_distance(text1, text2)
        max_len = max(len(text1), len(text2))

        if max_len == 0:
            return 1.0

        return 1.0 - (edit_distance / max_len)

    @staticmethod
    def _calculate_edit_distance(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return MockTextSimilarityCalculator._calculate_edit_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]


def merge_time_constrained_duplicates_with_transitive(
    subtitles: List[MockSubtitleItem],
) -> List[MockSubtitleItem]:
    """修正版: 連鎖的重複対応の時間制約付き統合"""
    if not subtitles:
        return []

    merged = []
    calc = MockTextSimilarityCalculator()
    max_merge_gap_ms = 30000

    subtitles_copy = subtitles.copy()
    i = 0
    while i < len(subtitles_copy):
        current_group = [subtitles_copy[i]]
        j = i + 1

        while j < len(subtitles_copy):
            time_gap = subtitles_copy[j].start_ms - subtitles_copy[i].end_ms

            if time_gap > max_merge_gap_ms:
                break

            # 連鎖的重複対応: 既存グループのいずれかとの類似度をチェック
            is_similar_to_group = False
            for group_member in current_group:
                similarity = calc.calculate_similarity(group_member.text, subtitles_copy[j].text)
                if similarity > 0.90:
                    is_similar_to_group = True
                    break

            if is_similar_to_group:
                current_group.append(subtitles_copy[j])
                subtitles_copy.pop(j)
            else:
                j += 1

        # グループを統合して追加
        if len(current_group) == 1:
            merged.append(current_group[0])
        else:
            merged_subtitle = merge_duplicate_group(current_group)
            merged.append(merged_subtitle)

        i += 1

    return merged


def merge_time_constrained_duplicates_old_behavior(
    subtitles: List[MockSubtitleItem],
) -> List[MockSubtitleItem]:
    """旧版: 最初の字幕とのみ比較（連鎖的重複バグあり）"""
    if not subtitles:
        return []

    merged = []
    calc = MockTextSimilarityCalculator()
    max_merge_gap_ms = 30000

    subtitles_copy = subtitles.copy()
    i = 0
    while i < len(subtitles_copy):
        current_group = [subtitles_copy[i]]
        j = i + 1

        while j < len(subtitles_copy):
            time_gap = subtitles_copy[j].start_ms - subtitles_copy[i].end_ms

            if time_gap > max_merge_gap_ms:
                break

            # 旧実装: 最初の字幕とのみ比較
            similarity = calc.calculate_similarity(subtitles_copy[i].text, subtitles_copy[j].text)

            if similarity > 0.90:
                current_group.append(subtitles_copy[j])
                subtitles_copy.pop(j)
            else:
                j += 1

        if len(current_group) == 1:
            merged.append(current_group[0])
        else:
            merged_subtitle = merge_duplicate_group(current_group)
            merged.append(merged_subtitle)

        i += 1

    return merged


def merge_duplicate_group(group: List[MockSubtitleItem]) -> MockSubtitleItem:
    """字幕グループを統合"""
    if not group:
        return None

    min_start_ms = min(subtitle.start_ms for subtitle in group)
    max_end_ms = max(subtitle.end_ms for subtitle in group)
    base_subtitle = group[0]

    return MockSubtitleItem(
        index=base_subtitle.index,
        start_ms=min_start_ms,
        end_ms=max_end_ms,
        text=base_subtitle.text,
        bbox=base_subtitle.bbox,
    )


def test_transitive_duplicate_chain():
    """連鎖的重複のテスト: A≈B≈Cケース（assert文使用）"""
    print("=== 連鎖的重複のテスト ===")

    # 連鎖的重複のケース: A≈B (91%+), B≈C (91%+), but A-C (82% < 90%)
    subtitles = [
        MockSubtitleItem(index=1, start_ms=1000, end_ms=2000, text="abcdefghijk"),  # A (11文字)
        MockSubtitleItem(
            index=2, start_ms=3000, end_ms=4000, text="abcdefghijX"
        ),  # B (1文字違い: k→X)
        MockSubtitleItem(
            index=3, start_ms=5000, end_ms=6000, text="abcdefghiYX"
        ),  # C (A-C: 2文字違い: j→Y, k→X)
    ]

    print("テストケース:")
    for sub in subtitles:
        print(f'  {sub.index}: "{sub.text}"')

    # 類似度を確認
    calc = MockTextSimilarityCalculator()
    sim_ab = calc.calculate_similarity(subtitles[0].text, subtitles[1].text)
    sim_bc = calc.calculate_similarity(subtitles[1].text, subtitles[2].text)
    sim_ac = calc.calculate_similarity(subtitles[0].text, subtitles[2].text)

    print(f"\n類似度:")
    print(f"  A-B: {sim_ab:.3f}")
    print(f"  B-C: {sim_bc:.3f}")
    print(f"  A-C: {sim_ac:.3f}")

    # 前提条件をassert
    assert sim_ab > 0.90, f"A-B類似度が90%未満: {sim_ab}"
    assert sim_bc > 0.90, f"B-C類似度が90%未満: {sim_bc}"
    assert sim_ac < 0.90, f"A-C類似度が90%以上: {sim_ac}"

    # 旧実装（バグあり）
    old_result = merge_time_constrained_duplicates_old_behavior(subtitles.copy())
    print(f"\n旧実装結果: {len(old_result)}字幕")

    # 新実装（修正版）
    new_result = merge_time_constrained_duplicates_with_transitive(subtitles.copy())
    print(f"新実装結果: {len(new_result)}字幕")

    # 修正が効果的だったかをassert
    assert len(new_result) < len(
        old_result
    ), f"新実装で統合されていません: 旧{len(old_result)} vs 新{len(new_result)}"
    assert len(new_result) == 1, f"連鎖的重複が1つに統合されませんでした: {len(new_result)}"
    print("✅ 修正成功: 連鎖的重複が正しく統合されました")
    return True


def test_normal_case_unchanged():
    """通常ケース: 修正による影響がないことを確認（assert文使用）"""
    print("\n=== 通常ケースのテスト ===")

    subtitles = [
        MockSubtitleItem(index=1, start_ms=1000, end_ms=2000, text="こんにちは"),
        MockSubtitleItem(index=2, start_ms=3000, end_ms=4000, text="こんにちは"),  # 同一
        MockSubtitleItem(index=3, start_ms=10000, end_ms=11000, text="さようなら"),  # 異なる
    ]

    old_result = merge_time_constrained_duplicates_old_behavior(subtitles.copy())
    new_result = merge_time_constrained_duplicates_with_transitive(subtitles.copy())

    print(f"旧実装結果: {len(old_result)}字幕")
    print(f"新実装結果: {len(new_result)}字幕")

    # 通常ケースに影響がないことをassert
    assert len(old_result) == len(
        new_result
    ), f"通常ケースに予期しない影響: 旧{len(old_result)} vs 新{len(new_result)}"
    assert len(new_result) == 2, f"期待される統合結果と異なります: {len(new_result)}"
    print("✅ 通常ケースへの影響なし")
    return True


if __name__ == "__main__":
    print("連鎖的重複修正のテスト開始...\n")

    success_count = 0
    total_tests = 2

    try:
        if test_transitive_duplicate_chain():
            success_count += 1
    except AssertionError as e:
        print(f"❌ test_transitive_duplicate_chain失敗: {e}")

    try:
        if test_normal_case_unchanged():
            success_count += 1
    except AssertionError as e:
        print(f"❌ test_normal_case_unchanged失敗: {e}")

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 連鎖的重複の修正が成功しました！")
    else:
        print("❌ 修正に問題があります")
        raise SystemExit(1)
