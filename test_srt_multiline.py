#!/usr/bin/env python3
"""
SRT出力での改行テスト
"""

import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from app.core.format.srt import SRTFormatter
from app.core.models import SubtitleItem


def test_srt_multiline_output():
    """SRT出力での改行テスト"""
    print("=== SRT改行出力テスト ===")

    # テスト用字幕データ
    subtitles = [
        SubtitleItem(index=1, start_ms=0, end_ms=2000, text="単行字幕"),
        SubtitleItem(index=2, start_ms=2500, end_ms=4500, text="こんにちは\n皆さん"),  # 2行字幕
        SubtitleItem(index=3, start_ms=5000, end_ms=7000, text="今日は良い\n天気ですね"),  # 2行字幕
    ]

    # SRTフォーマッタを作成
    formatter = SRTFormatter()

    # SRT出力を生成
    srt_output = formatter.subtitles_to_srt(subtitles)

    print("生成されたSRT出力:")
    print("=" * 50)
    print(srt_output)
    print("=" * 50)

    # 期待される改行文字の確認
    lines = srt_output.split('\n')
    multiline_found = False

    for i, line in enumerate(lines):
        if "こんにちは" in line:
            print(f"行 {i}: '{line}' (こんにちは)")
            if i + 1 < len(lines) and "皆さん" in lines[i + 1]:
                print(f"行 {i+1}: '{lines[i + 1]}' (皆さん)")
                multiline_found = True
                print("✅ 2行字幕が正しく改行されています")

        if "今日は良い" in line:
            print(f"行 {i}: '{line}' (今日は良い)")
            if i + 1 < len(lines) and "天気ですね" in lines[i + 1]:
                print(f"行 {i+1}: '{lines[i + 1]}' (天気ですね)")
                multiline_found = True
                print("✅ 2行字幕が正しく改行されています")

    if multiline_found:
        print("\n🎉 SRT出力での改行が正しく動作しています")
        return True
    else:
        print("\n❌ SRT出力で改行が正しく処理されていません")
        return False


def test_srt_parsing():
    """SRT解析での改行復元テスト"""
    print("\n=== SRT解析改行復元テスト ===")

    # 改行を含むSRTコンテンツ
    srt_content = """1
00:00:00,000 --> 00:00:02,000
単行字幕

2
00:00:02,500 --> 00:00:04,500
こんにちは
皆さん

3
00:00:05,000 --> 00:00:07,000
今日は良い
天気ですね"""

    from app.core.format.srt import SRTParser
    parser = SRTParser()

    # SRTを解析
    parsed_subtitles = parser.parse_srt_content(srt_content)

    print(f"解析された字幕数: {len(parsed_subtitles)}")

    success = True
    for subtitle in parsed_subtitles:
        print(f"字幕 {subtitle.index}: '{subtitle.text}'")
        if subtitle.index == 2:
            expected = "こんにちは\n皆さん"
            if subtitle.text == expected:
                print("✅ 改行が正しく復元されました")
            else:
                print(f"❌ 期待値: '{expected}', 実際: '{subtitle.text}'")
                success = False
        elif subtitle.index == 3:
            expected = "今日は良い\n天気ですね"
            if subtitle.text == expected:
                print("✅ 改行が正しく復元されました")
            else:
                print(f"❌ 期待値: '{expected}', 実際: '{subtitle.text}'")
                success = False

    return success


if __name__ == "__main__":
    print("2行字幕のSRT処理テスト開始...\n")

    success_count = 0
    total_tests = 2

    if test_srt_multiline_output():
        success_count += 1

    if test_srt_parsing():
        success_count += 1

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 すべてのSRTテストが成功しました！")
    else:
        print("❌ 一部のSRTテストが失敗しました")