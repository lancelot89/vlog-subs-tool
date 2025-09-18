"""
SRTフォーマットモジュールのテスト
"""

from pathlib import Path

import pytest

from app.core.format.srt import MultiLanguageSRTManager, SRTFormatter, SRTParser
from app.core.models import SubtitleItem


class TestSRTFormatter:
    """SRTFormatterクラスのテスト"""

    def test_format_time(self):
        """時間フォーマットのテスト"""
        # 1秒
        assert SRTFormatter.format_time(1000) == "00:00:01,000"

        # 1分30秒500ミリ秒
        assert SRTFormatter.format_time(90500) == "00:01:30,500"

        # 1時間2分3秒4ミリ秒
        assert SRTFormatter.format_time(3723004) == "01:02:03,004"

    def test_format_single_subtitle(self):
        """単一字幕フォーマットのテスト"""
        subtitle = SubtitleItem(1, 1000, 3000, "テストテキスト")
        formatted = SRTFormatter.format_subtitle(subtitle)

        expected = """1
00:00:01,000 --> 00:00:03,000
テストテキスト"""

        assert formatted == expected

    def test_format_multiple_subtitles(self, sample_subtitles):
        """複数字幕フォーマットのテスト"""
        formatted = SRTFormatter.format_subtitles(sample_subtitles)

        lines = formatted.strip().split("\n\n")
        assert len(lines) == 3

        # 最初の字幕をチェック
        first_subtitle = lines[0].split("\n")
        assert first_subtitle[0] == "1"
        assert "00:00:01,000 --> 00:00:03,000" in first_subtitle[1]
        assert first_subtitle[2] == "こんにちは世界"

    def test_save_srt(self, sample_subtitles, temp_dir):
        """SRTファイル保存のテスト"""
        output_path = temp_dir / "test.srt"

        success = SRTFormatter.save_srt(sample_subtitles, output_path)
        assert success
        assert output_path.exists()

        # ファイル内容確認
        content = output_path.read_text(encoding="utf-8")
        assert "こんにちは世界" in content
        assert "00:00:01,000 --> 00:00:03,000" in content


class TestSRTParser:
    """SRTParserクラスのテスト"""

    def test_parse_time(self):
        """時間パースのテスト"""
        # 基本的な時間
        assert SRTParser.parse_time("00:00:01,000") == 1000
        assert SRTParser.parse_time("00:01:30,500") == 90500
        assert SRTParser.parse_time("01:02:03,004") == 3723004

    def test_parse_srt_content(self):
        """SRT内容パースのテスト"""
        srt_content = """1
00:00:01,000 --> 00:00:03,000
こんにちは世界

2
00:00:04,000 --> 00:00:06,000
これはテストです

3
00:00:07,000 --> 00:00:09,000
最後の字幕"""

        subtitles = SRTParser.parse_srt_content(srt_content)

        assert len(subtitles) == 3
        assert subtitles[0].index == 1
        assert subtitles[0].start_ms == 1000
        assert subtitles[0].end_ms == 3000
        assert subtitles[0].text == "こんにちは世界"

        assert subtitles[2].text == "最後の字幕"

    def test_parse_multiline_subtitle(self):
        """複数行字幕のパースのテスト"""
        srt_content = """1
00:00:01,000 --> 00:00:03,000
行1
行2

2
00:00:04,000 --> 00:00:06,000
単一行"""

        subtitles = SRTParser.parse_srt_content(srt_content)

        assert len(subtitles) == 2
        assert subtitles[0].text == "行1\n行2"
        assert subtitles[1].text == "単一行"

    def test_load_srt_file(self, temp_dir):
        """SRTファイル読み込みのテスト"""
        srt_path = temp_dir / "test.srt"
        srt_content = """1
00:00:01,000 --> 00:00:03,000
テスト字幕"""

        srt_path.write_text(srt_content, encoding="utf-8")

        subtitles = SRTParser.load_srt(srt_path)

        assert len(subtitles) == 1
        assert subtitles[0].text == "テスト字幕"


class TestMultiLanguageSRTManager:
    """MultiLanguageSRTManagerクラスのテスト"""

    def test_generate_filename(self):
        """ファイル名生成のテスト"""
        manager = MultiLanguageSRTManager("/path/to/video.mp4")

        assert manager.generate_filename("ja") == "video.ja.srt"
        assert manager.generate_filename("en") == "video.en.srt"
        assert manager.generate_filename("zh") == "video.zh.srt"

    def test_export_single_language(self, sample_subtitles, temp_dir):
        """単一言語エクスポートのテスト"""
        video_path = temp_dir / "test_video.mp4"
        manager = MultiLanguageSRTManager(str(video_path))

        result = manager.export_language(sample_subtitles, "ja", temp_dir)

        assert result is not None
        expected_path = temp_dir / "test_video.ja.srt"
        assert expected_path.exists()

        # 内容確認
        content = expected_path.read_text(encoding="utf-8")
        assert "こんにちは世界" in content

    def test_export_multiple_languages(self, sample_subtitles, temp_dir):
        """複数言語エクスポートのテスト"""
        video_path = temp_dir / "test_video.mp4"
        manager = MultiLanguageSRTManager(str(video_path))

        # テスト用の翻訳データ
        translations = {
            "en": [
                SubtitleItem(1, 1000, 3000, "Hello World"),
                SubtitleItem(2, 4000, 6000, "This is a test"),
                SubtitleItem(3, 7000, 9000, "Last subtitle"),
            ],
            "zh": [
                SubtitleItem(1, 1000, 3000, "你好世界"),
                SubtitleItem(2, 4000, 6000, "这是测试"),
                SubtitleItem(3, 7000, 9000, "最后字幕"),
            ],
        }

        results = manager.export_all_languages(translations, temp_dir)

        assert len(results) == 2
        assert "en" in results
        assert "zh" in results

        # ファイル存在確認
        en_path = temp_dir / "test_video.en.srt"
        zh_path = temp_dir / "test_video.zh.srt"

        assert en_path.exists()
        assert zh_path.exists()

        # 内容確認
        en_content = en_path.read_text(encoding="utf-8")
        zh_content = zh_path.read_text(encoding="utf-8")

        assert "Hello World" in en_content
        assert "你好世界" in zh_content
