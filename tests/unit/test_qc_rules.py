"""
QCルールモジュールのテスト
"""

import pytest

from app.core.models import QCResult, SubtitleItem
from app.core.qc.rules import (
    DuplicateTextRule,
    DurationRule,
    EmptyTextRule,
    LineLengthRule,
    MaxLinesRule,
    QCChecker,
    QCSeverity,
    ReadingSpeedRule,
    TimeOrderRule,
    TimeOverlapRule,
)


class TestLineLengthRule:
    """LineLengthRuleのテスト"""

    def test_valid_line_length(self):
        """有効な行長のテスト"""
        rule = LineLengthRule(max_chars=42)
        subtitle = SubtitleItem(1, 1000, 3000, "短いテキスト")

        results = rule.check([subtitle])
        assert len(results) == 0

    def test_invalid_line_length(self):
        """無効な行長のテスト"""
        rule = LineLengthRule(max_chars=10)
        subtitle = SubtitleItem(1, 1000, 3000, "これは非常に長いテキストです")

        results = rule.check([subtitle])
        assert len(results) == 1
        assert results[0].severity == "warning"
        assert "文字" in results[0].message

    def test_multiline_text(self):
        """複数行テキストのテスト"""
        rule = LineLengthRule(max_chars=10)
        subtitle = SubtitleItem(1, 1000, 3000, "短い行\n非常に長い行のテキスト")

        results = rule.check([subtitle])
        assert len(results) == 1
        assert "行2" in results[0].message


class TestMaxLinesRule:
    """MaxLinesRuleのテスト"""

    def test_valid_lines(self):
        """有効な行数のテスト"""
        rule = MaxLinesRule(max_lines=2)
        subtitle = SubtitleItem(1, 1000, 3000, "行1\n行2")

        results = rule.check([subtitle])
        assert len(results) == 0

    def test_invalid_lines(self):
        """無効な行数のテスト"""
        rule = MaxLinesRule(max_lines=2)
        subtitle = SubtitleItem(1, 1000, 3000, "行1\n行2\n行3\n行4")

        results = rule.check([subtitle])
        assert len(results) == 1
        assert results[0].severity == "warning"
        assert "4行" in results[0].message


class TestDurationRule:
    """DurationRuleのテスト"""

    def test_valid_duration(self):
        """有効な表示時間のテスト"""
        rule = DurationRule(min_duration_ms=500, max_duration_ms=10000)
        subtitle = SubtitleItem(1, 1000, 3000, "テスト")  # 2秒

        results = rule.check([subtitle])
        assert len(results) == 0

    def test_too_short_duration(self):
        """短すぎる表示時間のテスト"""
        rule = DurationRule(min_duration_ms=1000)
        subtitle = SubtitleItem(1, 1000, 1500, "テスト")  # 0.5秒

        results = rule.check([subtitle])
        assert len(results) == 1
        assert results[0].severity == "warning"
        assert "短すぎ" in results[0].message

    def test_too_long_duration(self):
        """長すぎる表示時間のテスト"""
        rule = DurationRule(max_duration_ms=5000)
        subtitle = SubtitleItem(1, 1000, 8000, "テスト")  # 7秒

        results = rule.check([subtitle])
        assert len(results) == 1
        assert results[0].severity == "info"
        assert "長すぎ" in results[0].message


class TestTimeOverlapRule:
    """TimeOverlapRuleのテスト"""

    def test_no_overlap(self):
        """重複なしのテスト"""
        rule = TimeOverlapRule()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "字幕1"),
            SubtitleItem(2, 4000, 6000, "字幕2"),
        ]

        results = rule.check(subtitles)
        assert len(results) == 0

    def test_overlap_detected(self):
        """重複検出のテスト"""
        rule = TimeOverlapRule()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "字幕1"),
            SubtitleItem(2, 2500, 4500, "字幕2"),  # 500ms重複
        ]

        results = rule.check(subtitles)
        assert len(results) == 1
        assert results[0].severity == "error"
        assert "重複" in results[0].message


class TestDuplicateTextRule:
    """DuplicateTextRuleのテスト"""

    def test_no_duplicates(self):
        """重複なしのテスト"""
        rule = DuplicateTextRule()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "字幕1"),
            SubtitleItem(2, 4000, 6000, "字幕2"),
        ]

        results = rule.check(subtitles)
        assert len(results) == 0

    def test_exact_duplicates(self):
        """完全重複のテスト"""
        rule = DuplicateTextRule()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "同じテキスト"),
            SubtitleItem(2, 2000, 3000, "同じテキスト"),  # 近い時間で重複
        ]

        results = rule.check(subtitles)
        assert len(results) == 1
        assert results[0].severity == "warning"
        assert "重複" in results[0].message


class TestEmptyTextRule:
    """EmptyTextRuleのテスト"""

    def test_valid_text(self):
        """有効テキストのテスト"""
        rule = EmptyTextRule()
        subtitle = SubtitleItem(1, 1000, 3000, "有効なテキスト")

        results = rule.check([subtitle])
        assert len(results) == 0

    def test_empty_text(self):
        """空テキストのテスト"""
        rule = EmptyTextRule()
        subtitle = SubtitleItem(1, 1000, 3000, "")

        results = rule.check([subtitle])
        assert len(results) == 1
        assert results[0].severity == "error"
        assert "空" in results[0].message

    def test_whitespace_only(self):
        """空白のみのテスト"""
        rule = EmptyTextRule()
        subtitle = SubtitleItem(1, 1000, 3000, "   \n\t  ")

        results = rule.check([subtitle])
        assert len(results) == 1
        assert "空" in results[0].message


class TestTimeOrderRule:
    """TimeOrderRuleのテスト"""

    def test_valid_timing(self):
        """有効な時間順序のテスト"""
        rule = TimeOrderRule()
        subtitle = SubtitleItem(1, 1000, 3000, "テスト")

        results = rule.check([subtitle])
        assert len(results) == 0

    def test_invalid_timing(self):
        """無効な時間順序のテスト"""
        rule = TimeOrderRule()
        subtitle = SubtitleItem(1, 3000, 1000, "テスト")  # 開始 > 終了

        results = rule.check([subtitle])
        assert len(results) == 1
        assert results[0].severity == "error"
        assert "開始時間" in results[0].message


class TestReadingSpeedRule:
    """ReadingSpeedRuleのテスト"""

    def test_valid_speed(self):
        """有効な読み速度のテスト"""
        rule = ReadingSpeedRule(max_chars_per_second=20.0)
        subtitle = SubtitleItem(1, 1000, 3000, "適切な長さ")  # 2秒で5文字 = 2.5文字/秒

        results = rule.check([subtitle])
        assert len(results) == 0

    def test_too_fast_reading(self):
        """読み速度過多のテスト"""
        rule = ReadingSpeedRule(max_chars_per_second=5.0)
        subtitle = SubtitleItem(
            1, 1000, 2000, "これは非常に長いテキストで読み速度制限を超えています"
        )

        results = rule.check([subtitle])
        assert len(results) == 1
        assert results[0].severity == "warning"
        assert "読み速度" in results[0].message


class TestQCChecker:
    """QCCheckerクラスのテスト"""

    def test_check_all_subtitles(self):
        """全字幕チェックのテスト"""
        checker = QCChecker()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "正常な字幕"),
            SubtitleItem(2, 2500, 4000, "重複時間"),  # 時間重複
            SubtitleItem(3, 5000, 5200, "短"),  # 短すぎる
            SubtitleItem(4, 6000, 7000, ""),  # 空テキスト
        ]

        results = checker.check_all(subtitles)
        assert len(results) > 0

        # エラーレベルの結果があることを確認
        error_results = [r for r in results if r.severity == "error"]
        assert len(error_results) > 0

    def test_get_summary(self):
        """サマリー取得のテスト"""
        checker = QCChecker()
        results = [
            QCResult(0, "rule1", "エラー1", "error"),
            QCResult(1, "rule2", "警告1", "warning"),
            QCResult(2, "rule3", "警告2", "warning"),
            QCResult(3, "rule4", "情報1", "info"),
        ]

        summary = checker.get_summary(results)

        assert summary["total"] == 4
        assert summary["error"] == 1
        assert summary["warning"] == 2
        assert summary["info"] == 1

    def test_rule_management(self):
        """ルール管理のテスト"""
        checker = QCChecker()

        # ルールの無効化
        checker.enable_rule("行長チェック", False)
        status = checker.get_rule_status()
        assert status["行長チェック"] == False

        # ルールの有効化
        checker.enable_rule("行長チェック", True)
        status = checker.get_rule_status()
        assert status["行長チェック"] == True
