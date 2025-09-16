#!/usr/bin/env python3
"""
時間制約付き重複字幕統合機能のテスト
PR #115のコメント対応
"""

import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.core.extractor.group import ExtractionProcessor
from app.core.models import SubtitleItem


def test_time_constrained_duplicate_merge():
    """時間制約付き重複字幕統合テスト"""
    print("=== 時間制約付き重複字幕統合テスト ===")

    # 近接する類似字幕（統合対象）
    subtitles = [
        SubtitleItem(index=1, start_ms=16000, end_ms=17200, text="汗だくで帰宅しました、シャワー浴びてきた"),
        SubtitleItem(index=2, start_ms=18000, end_ms=19200, text="汗だくで帰宅しました、シヤワー浴びてきた"),  # OCR誤認識版
        SubtitleItem(index=3, start_ms=20000, end_ms=21200, text="汗だくで帰宅しました、シャワー浴びてきた"),
    ]

    settings = {
        'similarity_threshold': 0.90,
        'min_duration_sec': 1.2,
        'max_gap_sec': 0.5
    }

    processor = ExtractionProcessor(settings)
    merged_subtitles = processor._remove_duplicates(subtitles)

    print(f"元の字幕数: {len(subtitles)}")
    print(f"統合後字幕数: {len(merged_subtitles)}")

    for subtitle in merged_subtitles:
        print(f"字幕 {subtitle.index}: {subtitle.start_ms}-{subtitle.end_ms}ms")
        print(f"  テキスト: {subtitle.text}")

    # 近接する類似字幕は統合される
    assert len(merged_subtitles) == 1, f"期待値 1 != 実際 {len(merged_subtitles)}"

    merged_subtitle = merged_subtitles[0]
    assert merged_subtitle.start_ms == 16000, f"開始時間が不正: {merged_subtitle.start_ms}"
    assert merged_subtitle.end_ms == 21200, f"終了時間が不正: {merged_subtitle.end_ms}"

    print("✅ テスト成功: 近接する類似字幕が正しく統合されました")
    return True


def test_distant_duplicates_not_merged():
    """時間的に離れた重複字幕は統合されないテスト"""
    print("\n=== 時間的に離れた重複字幕は統合されないテスト ===")

    # 同じテキストだが時間的に大きく離れた字幕（統合対象外）
    subtitles = [
        SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="ありがとうございます"),
        SubtitleItem(index=2, start_ms=10000, end_ms=11000, text="普通の字幕"),
        SubtitleItem(index=3, start_ms=600000, end_ms=601000, text="ありがとうございます"),  # 10分後
    ]

    settings = {
        'similarity_threshold': 0.90,
        'min_duration_sec': 1.2,
        'max_gap_sec': 0.5
    }

    processor = ExtractionProcessor(settings)
    merged_subtitles = processor._remove_duplicates(subtitles)

    print(f"元の字幕数: {len(subtitles)}")
    print(f"統合後字幕数: {len(merged_subtitles)}")

    for subtitle in merged_subtitles:
        print(f"字幕 {subtitle.index}: {subtitle.start_ms}-{subtitle.end_ms}ms")
        print(f"  テキスト: {subtitle.text}")

    # 時間的に離れた字幕は統合されない（3つのまま）
    assert len(merged_subtitles) == 3, f"期待値 3 != 実際 {len(merged_subtitles)}"

    # "ありがとうございます"が2つ残っている
    thanks_count = sum(1 for s in merged_subtitles if s.text == "ありがとうございます")
    assert thanks_count == 2, f"「ありがとうございます」の字幕数が不正: {thanks_count}"

    print("✅ テスト成功: 時間的に離れた重複字幕は統合されませんでした")
    return True


def test_mixed_scenario():
    """混合シナリオ: 近接統合と遠隔非統合"""
    print("\n=== 混合シナリオテスト ===")

    subtitles = [
        # グループ1: 近接する類似字幕（統合対象）
        SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="こんにちは"),
        SubtitleItem(index=2, start_ms=3000, end_ms=4000, text="こんにちは"),

        # グループ2: 普通の字幕
        SubtitleItem(index=3, start_ms=10000, end_ms=11000, text="普通の内容"),

        # グループ3: 遠く離れた同じテキスト（統合対象外）
        SubtitleItem(index=4, start_ms=60000, end_ms=61000, text="こんにちは"),  # 1分後

        # グループ4: 別の近接類似グループ（統合対象）
        SubtitleItem(index=5, start_ms=70000, end_ms=71000, text="さようなら"),
        SubtitleItem(index=6, start_ms=72000, end_ms=73000, text="さようなら"),
    ]

    settings = {
        'similarity_threshold': 0.90,
        'min_duration_sec': 1.2,
        'max_gap_sec': 0.5
    }

    processor = ExtractionProcessor(settings)
    merged_subtitles = processor._remove_duplicates(subtitles)

    print(f"元の字幕数: {len(subtitles)}")
    print(f"統合後字幕数: {len(merged_subtitles)}")

    for subtitle in merged_subtitles:
        print(f"字幕 {subtitle.index}: {subtitle.start_ms}-{subtitle.end_ms}ms")
        print(f"  テキスト: {subtitle.text}")

    # 期待結果: 4つの字幕
    # 1. 統合された"こんにちは"（1000-4000ms）
    # 2. "普通の内容"（10000-11000ms）
    # 3. 遠い"こんにちは"（60000-61000ms）
    # 4. 統合された"さようなら"（70000-73000ms）
    assert len(merged_subtitles) == 4, f"期待値 4 != 実際 {len(merged_subtitles)}"

    # "こんにちは"が2つ、"さようなら"が1つ
    hello_count = sum(1 for s in merged_subtitles if s.text == "こんにちは")
    goodbye_count = sum(1 for s in merged_subtitles if s.text == "さようなら")

    assert hello_count == 2, f"「こんにちは」の字幕数が不正: {hello_count}"
    assert goodbye_count == 1, f"「さようなら」の字幕数が不正: {goodbye_count}"

    print("✅ テスト成功: 混合シナリオが正しく処理されました")
    return True


if __name__ == "__main__":
    print("時間制約付き重複字幕統合機能のテスト開始...\n")

    success_count = 0
    total_tests = 3

    try:
        if test_time_constrained_duplicate_merge():
            success_count += 1
    except Exception as e:
        print(f"❌ test_time_constrained_duplicate_merge失敗: {e}")

    try:
        if test_distant_duplicates_not_merged():
            success_count += 1
    except Exception as e:
        print(f"❌ test_distant_duplicates_not_merged失敗: {e}")

    try:
        if test_mixed_scenario():
            success_count += 1
    except Exception as e:
        print(f"❌ test_mixed_scenario失敗: {e}")

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 すべてのテストが成功しました！")
    else:
        print("❌ 一部のテストが失敗しました")
        sys.exit(1)