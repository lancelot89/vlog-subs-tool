#!/usr/bin/env python3
"""
重複字幕統合機能のテスト
Issue #112の対応
"""

import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.core.extractor.group import ExtractionProcessor
from app.core.models import SubtitleItem


def test_duplicate_merge_basic():
    """基本的な重複字幕統合テスト"""
    print("=== 基本的な重複字幕統合テスト ===")

    # Issue #112のサンプルと同様の重複字幕
    subtitles = [
        SubtitleItem(
            index=7,
            start_ms=16000,
            end_ms=17200,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        SubtitleItem(
            index=8,
            start_ms=18000,
            end_ms=19200,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        SubtitleItem(
            index=9,
            start_ms=20000,
            end_ms=21200,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        SubtitleItem(
            index=10,
            start_ms=22000,
            end_ms=23200,
            text="汗だくで帰宅しました、シヤワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),  # "シヤワー"に変更
        SubtitleItem(
            index=11,
            start_ms=24000,
            end_ms=25200,
            text="汗だくで帰宅しました、シヤワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
        SubtitleItem(
            index=12,
            start_ms=26000,
            end_ms=27200,
            text="汗だくで帰宅しました、シャワー浴びてきたのでスッキリ凍らせた水持って出かけたけど真夏の外出は危険だと思った",
        ),
    ]

    # テスト用設定
    settings = {
        "similarity_threshold": 0.90,
        "min_duration_sec": 1.2,
        "max_gap_sec": 0.5,
    }

    processor = ExtractionProcessor(settings)

    # 重複除去処理を実行
    merged_subtitles = processor._remove_duplicates(subtitles)

    print(f"元の字幕数: {len(subtitles)}")
    print(f"統合後字幕数: {len(merged_subtitles)}")

    # 結果を確認
    for subtitle in merged_subtitles:
        print(f"字幕 {subtitle.index}: {subtitle.start_ms}-{subtitle.end_ms}ms")
        print(f"  テキスト: {subtitle.text[:50]}...")

    # 期待値の確認
    # "シャワー"版と"シヤワー"版で2つのグループに分かれることを期待
    expected_groups = 2
    if len(merged_subtitles) == expected_groups:
        print(f"✅ テスト成功: {expected_groups}つのグループに統合されました")

        # 最初のグループの時間範囲を確認（シャワー版: 16000-27200ms）
        shower_group = None
        for subtitle in merged_subtitles:
            if "シャワー" in subtitle.text:
                shower_group = subtitle
                break

        if shower_group and shower_group.start_ms == 16000 and shower_group.end_ms == 27200:
            print("✅ 時間範囲統合が正しく動作しました")
            return True
        else:
            print(f"❌ 時間範囲が正しくありません: {shower_group.start_ms}-{shower_group.end_ms}ms")
            return False
    else:
        print(f"❌ テスト失敗: 期待値 {expected_groups} != 実際 {len(merged_subtitles)}")
        return False


def test_no_duplicates():
    """重複がない場合のテスト"""
    print("\n=== 重複がない場合のテスト ===")

    subtitles = [
        SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="最初の字幕"),
        SubtitleItem(index=2, start_ms=3000, end_ms=4000, text="2番目の字幕"),
        SubtitleItem(index=3, start_ms=5000, end_ms=6000, text="3番目の字幕"),
    ]

    settings = {
        "similarity_threshold": 0.90,
        "min_duration_sec": 1.2,
        "max_gap_sec": 0.5,
    }
    processor = ExtractionProcessor(settings)

    merged_subtitles = processor._remove_duplicates(subtitles)

    print(f"元の字幕数: {len(subtitles)}")
    print(f"統合後字幕数: {len(merged_subtitles)}")

    if len(merged_subtitles) == len(subtitles):
        print("✅ テスト成功: 重複がない場合は字幕数が変わりません")
        return True
    else:
        print(f"❌ テスト失敗: 期待値 {len(subtitles)} != 実際 {len(merged_subtitles)}")
        return False


def test_exact_duplicate():
    """完全に同一のテキストの統合テスト"""
    print("\n=== 完全に同一のテキストの統合テスト ===")

    subtitles = [
        SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="同じテキスト"),
        SubtitleItem(index=2, start_ms=2500, end_ms=3500, text="同じテキスト"),
        SubtitleItem(index=3, start_ms=4000, end_ms=5000, text="同じテキスト"),
        SubtitleItem(index=4, start_ms=6000, end_ms=7000, text="異なるテキスト"),
    ]

    settings = {
        "similarity_threshold": 0.90,
        "min_duration_sec": 1.2,
        "max_gap_sec": 0.5,
    }
    processor = ExtractionProcessor(settings)

    merged_subtitles = processor._remove_duplicates(subtitles)

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


if __name__ == "__main__":
    print("重複字幕統合機能のテスト開始...\n")

    success_count = 0
    total_tests = 3

    if test_duplicate_merge_basic():
        success_count += 1

    if test_no_duplicates():
        success_count += 1

    if test_exact_duplicate():
        success_count += 1

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 すべてのテストが成功しました！")
    else:
        print("❌ 一部のテストが失敗しました")
