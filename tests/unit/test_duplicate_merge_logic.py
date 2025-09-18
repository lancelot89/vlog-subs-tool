#!/usr/bin/env python3
"""
重複字幕統合ロジックのテスト（依存関係なし）
Issue #112の対応
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    """TextSimilarityCalculator のモック"""

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """簡単な類似度計算（文字列比較）"""
        if not text1 or not text2:
            return 0.0

        # 完全一致
        if text1 == text2:
            return 1.0

        # 正規化（空白・記号の統一）
        norm_text1 = text1.lower().replace(" ", "").replace("、", "").replace("。", "")
        norm_text2 = text2.lower().replace(" ", "").replace("、", "").replace("。", "")

        # 正規化後の完全一致
        if norm_text1 == norm_text2:
            return 1.0

        # 長さが大きく異なる場合は類似度を下げる
        len_ratio = min(len(norm_text1), len(norm_text2)) / max(len(norm_text1), len(norm_text2))
        if len_ratio < 0.9:
            return 0.0

        # 文字レベルの類似度（厳密版）
        if len(norm_text1) == 0 or len(norm_text2) == 0:
            return 0.0

        # 完全に位置が一致する文字数 / 全文字数
        min_len = min(len(norm_text1), len(norm_text2))
        common_chars = sum(1 for i in range(min_len) if norm_text1[i] == norm_text2[i])
        max_len = max(len(norm_text1), len(norm_text2))

        # 位置一致の類似度
        position_similarity = common_chars / max_len

        # 厳しい閾値を設定（95%以上の一致が必要）
        return position_similarity if position_similarity >= 0.95 else 0.0


def remove_duplicates_logic(
    subtitles: List[MockSubtitleItem],
) -> List[MockSubtitleItem]:
    """重複字幕の統合ロジック（テスト用実装）"""
    if not subtitles:
        return []

    # テキストをキーとして字幕をグループ化
    text_groups = {}
    calc = MockTextSimilarityCalculator()

    for subtitle in subtitles:
        # 既存のグループと比較して類似度の高いものを探す
        merged_with_existing = False

        for existing_text, group in text_groups.items():
            similarity = calc.calculate_similarity(subtitle.text, existing_text)
            if similarity > 0.90:  # 高い類似度（90%以上）で同一テキストと判定
                group.append(subtitle)
                merged_with_existing = True
                break

        # 新しいグループを作成
        if not merged_with_existing:
            text_groups[subtitle.text] = [subtitle]

    # 各グループを統合
    merged_subtitles = []
    for text, group in text_groups.items():
        if len(group) == 1:
            # 単一の字幕はそのまま追加
            merged_subtitles.append(group[0])
        else:
            # 複数の字幕を統合
            merged_subtitle = merge_duplicate_group(group)
            merged_subtitles.append(merged_subtitle)

    return merged_subtitles


def merge_duplicate_group(group: List[MockSubtitleItem]) -> MockSubtitleItem:
    """同じテキストの字幕グループを統合"""
    if not group:
        return None

    # 最も早い開始時間と最も遅い終了時間を取得
    min_start_ms = min(subtitle.start_ms for subtitle in group)
    max_end_ms = max(subtitle.end_ms for subtitle in group)

    # 最も信頼度の高い（または最初の）字幕のテキストとbboxを使用
    base_subtitle = group[0]

    # 統合された字幕を作成
    merged_subtitle = MockSubtitleItem(
        index=base_subtitle.index,  # インデックスは後で再採番される
        start_ms=min_start_ms,
        end_ms=max_end_ms,
        text=base_subtitle.text,
        bbox=base_subtitle.bbox,
    )

    return merged_subtitle


def test_duplicate_merge_basic():
    """基本的な重複字幕統合テスト"""
    print("=== 基本的な重複字幕統合テスト ===")

    # Issue #112のサンプルと同様の重複字幕
    subtitles = [
        MockSubtitleItem(
            index=7,
            start_ms=16000,
            end_ms=17200,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        MockSubtitleItem(
            index=8,
            start_ms=18000,
            end_ms=19200,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        MockSubtitleItem(
            index=9,
            start_ms=20000,
            end_ms=21200,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        MockSubtitleItem(
            index=10,
            start_ms=22000,
            end_ms=23200,
            text="汗だくで帰宅しました、シヤワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),  # "シヤワー"に変更
        MockSubtitleItem(
            index=11,
            start_ms=24000,
            end_ms=25200,
            text="汗だくで帰宅しました、シヤワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        MockSubtitleItem(
            index=12,
            start_ms=26000,
            end_ms=27200,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
    ]

    # 重複除去処理を実行
    merged_subtitles = remove_duplicates_logic(subtitles)

    print(f"元の字幕数: {len(subtitles)}")
    print(f"統合後字幕数: {len(merged_subtitles)}")

    # 結果を確認
    for subtitle in merged_subtitles:
        print(f"字幕 {subtitle.index}: {subtitle.start_ms}-{subtitle.end_ms}ms")
        print(f"  テキスト: {subtitle.text[:50]}...")

    # 期待値の確認
    # 90%類似度で"シャワー"版と"シヤワー"版は1つのグループに統合される
    expected_groups = 1
    if len(merged_subtitles) == expected_groups:
        print(f"✅ テスト成功: {expected_groups}つのグループに統合されました")

        # 統合された字幕の時間範囲を確認（全体: 16000-27200ms）
        merged_subtitle = merged_subtitles[0]

        if merged_subtitle.start_ms == 16000 and merged_subtitle.end_ms == 27200:
            print("✅ 時間範囲統合が正しく動作しました")
            print(f"  統合後時間範囲: {merged_subtitle.start_ms}-{merged_subtitle.end_ms}ms")
            return True
        else:
            print(
                f"❌ 時間範囲が正しくありません: {merged_subtitle.start_ms}-{merged_subtitle.end_ms}ms"
            )
            return False
    else:
        print(f"❌ テスト失敗: 期待値 {expected_groups} != 実際 {len(merged_subtitles)}")
        return False


def test_exact_duplicate():
    """完全に同一のテキストの統合テスト"""
    print("\n=== 完全に同一のテキストの統合テスト ===")

    subtitles = [
        MockSubtitleItem(index=1, start_ms=1000, end_ms=2000, text="同じテキスト"),
        MockSubtitleItem(index=2, start_ms=2500, end_ms=3500, text="同じテキスト"),
        MockSubtitleItem(index=3, start_ms=4000, end_ms=5000, text="同じテキスト"),
        MockSubtitleItem(index=4, start_ms=6000, end_ms=7000, text="異なるテキスト"),
    ]

    merged_subtitles = remove_duplicates_logic(subtitles)

    print(f"元の字幕数: {len(subtitles)}")
    print(f"統合後字幕数: {len(merged_subtitles)}")

    # 2つのグループに統合されることを期待（同じテキスト1つ + 異なるテキスト1つ）
    if len(merged_subtitles) == 2:
        # 統合された字幕の時間範囲を確認
        same_text_subtitle = None
        for subtitle in merged_subtitles:
            if subtitle.text == "同じテキスト":
                same_text_subtitle = subtitle
                break

        if (
            same_text_subtitle
            and same_text_subtitle.start_ms == 1000
            and same_text_subtitle.end_ms == 5000
        ):
            print("✅ テスト成功: 完全同一テキストが正しく統合されました")
            print(f"  統合後時間範囲: {same_text_subtitle.start_ms}-{same_text_subtitle.end_ms}ms")
            return True
        else:
            print(
                f"❌ 時間範囲が不正: {same_text_subtitle.start_ms if same_text_subtitle else 'None'}"
            )
            return False
    else:
        print(f"❌ テスト失敗: 期待値 2 != 実際 {len(merged_subtitles)}")
        return False


def test_no_duplicates():
    """重複がない場合のテスト"""
    print("\n=== 重複がない場合のテスト ===")

    subtitles = [
        MockSubtitleItem(index=1, start_ms=1000, end_ms=2000, text="最初の字幕"),
        MockSubtitleItem(index=2, start_ms=3000, end_ms=4000, text="2番目の字幕"),
        MockSubtitleItem(index=3, start_ms=5000, end_ms=6000, text="3番目の字幕"),
    ]

    merged_subtitles = remove_duplicates_logic(subtitles)

    print(f"元の字幕数: {len(subtitles)}")
    print(f"統合後字幕数: {len(merged_subtitles)}")

    if len(merged_subtitles) == len(subtitles):
        print("✅ テスト成功: 重複がない場合は字幕数が変わりません")
        return True
    else:
        print(f"❌ テスト失敗: 期待値 {len(subtitles)} != 実際 {len(merged_subtitles)}")
        return False


if __name__ == "__main__":
    print("重複字幕統合ロジックのテスト開始...\n")

    success_count = 0
    total_tests = 3

    # assert文を使用したテスト実行
    try:
        if test_duplicate_merge_basic():
            success_count += 1
    except AssertionError as e:
        print(f"❌ test_duplicate_merge_basic失敗: {e}")

    try:
        if test_exact_duplicate():
            success_count += 1
    except AssertionError as e:
        print(f"❌ test_exact_duplicate失敗: {e}")

    try:
        if test_no_duplicates():
            success_count += 1
    except AssertionError as e:
        print(f"❌ test_no_duplicates失敗: {e}")

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 すべてのテストが成功しました！")
    else:
        print("❌ 一部のテストが失敗しました")
        raise SystemExit(1)  # テスト失敗で終了
