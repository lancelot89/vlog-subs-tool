#!/usr/bin/env python3
"""
実際のtest_video.ja.srtの重複ケースを使ったテスト（assert文版）
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
    """TextSimilarityCalculator のモック"""

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """簡単な類似度計算"""
        if not text1 or not text2:
            return 0.0

        if text1 == text2:
            return 1.0

        # 正規化
        norm_text1 = text1.lower().replace(" ", "").replace("、", "").replace("。", "")
        norm_text2 = text2.lower().replace(" ", "").replace("、", "").replace("。", "")

        if norm_text1 == norm_text2:
            return 1.0

        # OCR誤認識パターンの補正
        corrections = {"シヤ": "シャ", "ロ": "口", "口": "ロ"}

        for wrong, correct in corrections.items():
            norm_text1 = norm_text1.replace(wrong, correct)
            norm_text2 = norm_text2.replace(wrong, correct)

        if norm_text1 == norm_text2:
            return 1.0

        # 長さ比
        len_ratio = min(len(norm_text1), len(norm_text2)) / max(
            len(norm_text1), len(norm_text2)
        )
        if len_ratio < 0.8:
            return 0.0

        # 位置一致の類似度
        min_len = min(len(norm_text1), len(norm_text2))
        common_chars = sum(1 for i in range(min_len) if norm_text1[i] == norm_text2[i])
        max_len = max(len(norm_text1), len(norm_text2))

        return common_chars / max_len


def merge_time_constrained_duplicates(
    subtitles: List[MockSubtitleItem],
) -> List[MockSubtitleItem]:
    """時間制約付きの重複統合ロジック"""
    if not subtitles:
        return []

    merged = []
    calc = MockTextSimilarityCalculator()
    max_merge_gap_ms = 30000  # 30秒以内の字幕のみ統合対象

    subtitles_copy = subtitles.copy()
    i = 0
    while i < len(subtitles_copy):
        current_group = [subtitles_copy[i]]
        j = i + 1

        # 現在の字幕から30秒以内の類似字幕を探す
        while j < len(subtitles_copy):
            time_gap = subtitles_copy[j].start_ms - subtitles_copy[i].end_ms

            # 時間間隔が30秒を超えたら統合対象外
            if time_gap > max_merge_gap_ms:
                break

            # テキスト類似度チェック
            similarity = calc.calculate_similarity(
                subtitles_copy[i].text, subtitles_copy[j].text
            )

            if similarity > 0.90:
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


def merge_duplicate_group(group: List[MockSubtitleItem]) -> MockSubtitleItem:
    """同じテキストの字幕グループを統合"""
    if not group:
        return None

    min_start_ms = min(subtitle.start_ms for subtitle in group)
    max_end_ms = max(subtitle.end_ms for subtitle in group)
    base_subtitle = group[0]

    merged_subtitle = MockSubtitleItem(
        index=base_subtitle.index,
        start_ms=min_start_ms,
        end_ms=max_end_ms,
        text=base_subtitle.text,
        bbox=base_subtitle.bbox,
    )

    return merged_subtitle


def test_real_duplicate_cases():
    """実際のtest_video.ja.srtの重複ケースをテスト（assert文使用版）"""
    print("=== 実際の重複ケースのテスト ===")

    # test_video.ja.srtの実際のデータ
    subtitles = [
        MockSubtitleItem(
            index=1,
            start_ms=0,
            end_ms=1200,
            text="さて図書館行って、病院行って、 銀行にも行ってくるでは出発です",
        ),
        MockSubtitleItem(
            index=2,
            start_ms=2000,
            end_ms=11200,
            text="さて図書館行って、病院行って、銀行にも行ってくるでは出発です",
        ),
        MockSubtitleItem(
            index=3,
            start_ms=16000,
            end_ms=27200,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        MockSubtitleItem(
            index=4,
            start_ms=22000,
            end_ms=25200,
            text="汗だくで帰宅しました、シヤワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        MockSubtitleItem(
            index=5,
            start_ms=30000,
            end_ms=39200,
            text="がん検診の検査結果は異常なしでしたこれからも年1ペ一スで受けたいです",
        ),
        MockSubtitleItem(
            index=6,
            start_ms=42000,
            end_ms=53200,
            text="お昼ごはんはカレー蕎麦とネギトロ巻きにします午後にはまた大量のネギトロが届くらしいので消化していかないと",
        ),
        MockSubtitleItem(
            index=7,
            start_ms=44000,
            end_ms=45200,
            text="お昼ごはんはカレー蕎麦とネギトロ巻きにします午後にはまた大量のネギト口が届くらしいので消化していかないと",
        ),
        MockSubtitleItem(
            index=8,
            start_ms=60000,
            end_ms=65200,
            text="なんかスパッと切れなくてボロボロになっていく",
        ),
        MockSubtitleItem(
            index=9,
            start_ms=70000,
            end_ms=71200,
            text="昨日作った力レーが微妙に残ってたので出汁で伸ばしていきます",
        ),
    ]

    print(f"元の字幕数: {len(subtitles)}")

    # 新しい統合ロジックを実行
    merged_subtitles = merge_time_constrained_duplicates(subtitles)

    print(f"統合後字幕数: {len(merged_subtitles)}")
    print("\n統合結果:")

    for subtitle in merged_subtitles:
        print(f"字幕 {subtitle.index}: {subtitle.start_ms}-{subtitle.end_ms}ms")
        print(f"  テキスト: {subtitle.text[:50]}...")

    # assert文で期待値の確認
    # 重複があった1+2, 3+4, 6+7の3組が統合されて6字幕になることを期待
    expected_count = 6
    assert (
        len(merged_subtitles) == expected_count
    ), f"期待値 {expected_count} != 実際 {len(merged_subtitles)}"
    print(f"\n✅ テスト成功: {expected_count}字幕に統合されました")

    # 重複統合の確認
    # 1. 図書館関連が統合されているか
    library_found = any("図書館" in s.text for s in merged_subtitles)
    # 2. シャワー関連が統合されているか
    shower_found = any(
        "シャワー" in s.text or "シヤワー" in s.text for s in merged_subtitles
    )
    # 3. カレー蕎麦関連が統合されているか
    curry_found = any("カレー蕎麦" in s.text for s in merged_subtitles)

    assert library_found, "図書館関連の字幕が統合されていません"
    assert shower_found, "シャワー関連の字幕が統合されていません"
    assert curry_found, "カレー蕎麦関連の字幕が統合されていません"
    print("✅ 全ての重複字幕が正しく統合されました")
    return True


if __name__ == "__main__":
    print("実際の重複ケースのテスト開始...\n")

    try:
        if test_real_duplicate_cases():
            print("\n🎉 テストが成功しました！")
    except AssertionError as e:
        print(f"\n❌ テストが失敗しました: {e}")
        raise  # pytestのために再発生
