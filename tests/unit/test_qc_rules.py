"""
QCルールモジュールのテスト
"""

import pytest

from app.core.models import SubtitleItem, QCResult
from app.core.qc.rules import (
    QCChecker, LineLengthRule, MaxLinesRule, DurationRule, 
    TimeOverlapRule, DuplicateRule, EmptyTextRule,
    TimingOrderRule, CharacterCountRule
)


class TestLineLengthRule:
    """LineLengthRuleのテスト"""
    
    def test_valid_line_length(self):
        """有効な行長のテスト"""
        rule = LineLengthRule(max_length=42)
        subtitle = SubtitleItem(1, 1000, 3000, "短いテキスト")
        
        results = rule.check(subtitle)
        assert len(results) == 0
    
    def test_invalid_line_length(self):
        """無効な行長のテスト"""
        rule = LineLengthRule(max_length=10)
        subtitle = SubtitleItem(1, 1000, 3000, "これは非常に長いテキストです")
        
        results = rule.check(subtitle)
        assert len(results) == 1
        assert results[0].severity == "WARNING"
        assert "長すぎます" in results[0].message
    
    def test_multiline_text(self):
        """複数行テキストのテスト"""
        rule = LineLengthRule(max_length=10)
        subtitle = SubtitleItem(1, 1000, 3000, "短い行\n非常に長い行のテキスト")
        
        results = rule.check(subtitle)
        assert len(results) == 1
        assert "2行目" in results[0].message


class TestMaxLinesRule:
    """MaxLinesRuleのテスト"""
    
    def test_valid_lines(self):
        """有効な行数のテスト"""
        rule = MaxLinesRule(max_lines=2)
        subtitle = SubtitleItem(1, 1000, 3000, "行1\n行2")
        
        results = rule.check(subtitle)
        assert len(results) == 0
    
    def test_invalid_lines(self):
        """無効な行数のテスト"""
        rule = MaxLinesRule(max_lines=2)
        subtitle = SubtitleItem(1, 1000, 3000, "行1\n行2\n行3\n行4")
        
        results = rule.check(subtitle)
        assert len(results) == 1
        assert results[0].severity == "ERROR"
        assert "4行" in results[0].message


class TestDurationRule:
    """DurationRuleのテスト"""
    
    def test_valid_duration(self):
        """有効な表示時間のテスト"""
        rule = DurationRule(min_duration_ms=500, max_duration_ms=10000)
        subtitle = SubtitleItem(1, 1000, 3000, "テスト")  # 2秒
        
        results = rule.check(subtitle)
        assert len(results) == 0
    
    def test_too_short_duration(self):
        """短すぎる表示時間のテスト"""
        rule = DurationRule(min_duration_ms=1000)
        subtitle = SubtitleItem(1, 1000, 1500, "テスト")  # 0.5秒
        
        results = rule.check(subtitle)
        assert len(results) == 1
        assert results[0].severity == "WARNING"
        assert "短すぎます" in results[0].message
    
    def test_too_long_duration(self):
        """長すぎる表示時間のテスト"""
        rule = DurationRule(max_duration_ms=5000)
        subtitle = SubtitleItem(1, 1000, 8000, "テスト")  # 7秒
        
        results = rule.check(subtitle)
        assert len(results) == 1
        assert results[0].severity == "WARNING"
        assert "長すぎます" in results[0].message


class TestTimeOverlapRule:
    """TimeOverlapRuleのテスト"""
    
    def test_no_overlap(self):
        """重複なしのテスト"""
        rule = TimeOverlapRule()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "字幕1"),
            SubtitleItem(2, 4000, 6000, "字幕2")
        ]
        
        results = rule.check_all(subtitles)
        assert len(results) == 0
    
    def test_overlap_detected(self):
        """重複検出のテスト"""
        rule = TimeOverlapRule()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "字幕1"),
            SubtitleItem(2, 2500, 4500, "字幕2")  # 500ms重複
        ]
        
        results = rule.check_all(subtitles)
        assert len(results) == 1
        assert results[0].severity == "ERROR"
        assert "重複" in results[0].message


class TestDuplicateRule:
    """DuplicateRuleのテスト"""
    
    def test_no_duplicates(self):
        """重複なしのテスト"""
        rule = DuplicateRule()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "字幕1"),
            SubtitleItem(2, 4000, 6000, "字幕2")
        ]
        
        results = rule.check_all(subtitles)
        assert len(results) == 0
    
    def test_exact_duplicates(self):
        """完全重複のテスト"""
        rule = DuplicateRule()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "同じテキスト"),
            SubtitleItem(2, 4000, 6000, "同じテキスト")
        ]
        
        results = rule.check_all(subtitles)
        assert len(results) == 1
        assert results[0].severity == "WARNING"
        assert "重複" in results[0].message
    
    def test_similar_duplicates(self):
        """類似重複のテスト"""
        rule = DuplicateRule(similarity_threshold=0.8)
        subtitles = [
            SubtitleItem(1, 1000, 3000, "これはテストです"),
            SubtitleItem(2, 4000, 6000, "これはテスト")  # 類似
        ]
        
        results = rule.check_all(subtitles)
        assert len(results) == 1
        assert "類似" in results[0].message


class TestEmptyTextRule:
    """EmptyTextRuleのテスト"""
    
    def test_valid_text(self):
        """有効テキストのテスト"""
        rule = EmptyTextRule()
        subtitle = SubtitleItem(1, 1000, 3000, "有効なテキスト")
        
        results = rule.check(subtitle)
        assert len(results) == 0
    
    def test_empty_text(self):
        """空テキストのテスト"""
        rule = EmptyTextRule()
        subtitle = SubtitleItem(1, 1000, 3000, "")
        
        results = rule.check(subtitle)
        assert len(results) == 1
        assert results[0].severity == "ERROR"
        assert "空" in results[0].message
    
    def test_whitespace_only(self):
        """空白のみのテスト"""
        rule = EmptyTextRule()
        subtitle = SubtitleItem(1, 1000, 3000, "   \n\t  ")
        
        results = rule.check(subtitle)
        assert len(results) == 1
        assert "空" in results[0].message


class TestTimingOrderRule:
    """TimingOrderRuleのテスト"""
    
    def test_valid_timing(self):
        """有効な時間順序のテスト"""
        rule = TimingOrderRule()
        subtitle = SubtitleItem(1, 1000, 3000, "テスト")
        
        results = rule.check(subtitle)
        assert len(results) == 0
    
    def test_invalid_timing(self):
        """無効な時間順序のテスト"""
        rule = TimingOrderRule()
        subtitle = SubtitleItem(1, 3000, 1000, "テスト")  # 開始 > 終了
        
        results = rule.check(subtitle)
        assert len(results) == 1
        assert results[0].severity == "ERROR"
        assert "開始時間" in results[0].message


class TestCharacterCountRule:
    """CharacterCountRuleのテスト"""
    
    def test_valid_count(self):
        """有効な文字数のテスト"""
        rule = CharacterCountRule(max_chars=100)
        subtitle = SubtitleItem(1, 1000, 3000, "適切な長さのテキスト")
        
        results = rule.check(subtitle)
        assert len(results) == 0
    
    def test_too_many_chars(self):
        """文字数過多のテスト"""
        rule = CharacterCountRule(max_chars=10)
        subtitle = SubtitleItem(1, 1000, 3000, "これは非常に長いテキストで文字数制限を超えています")
        
        results = rule.check(subtitle)
        assert len(results) == 1
        assert results[0].severity == "WARNING"
        assert "文字数" in results[0].message


class TestQCChecker:
    """QCCheckerクラスのテスト"""
    
    def test_check_single_subtitle(self):
        """単一字幕チェックのテスト"""
        checker = QCChecker()
        subtitle = SubtitleItem(1, 1000, 1200, "短")  # 短すぎる表示時間
        
        results = checker.check_subtitle(subtitle)
        assert len(results) > 0
        
        # 複数のルールが検出する可能性
        severities = [r.severity for r in results]
        assert "WARNING" in severities
    
    def test_check_all_subtitles(self):
        """全字幕チェックのテスト"""
        checker = QCChecker()
        subtitles = [
            SubtitleItem(1, 1000, 3000, "正常な字幕"),
            SubtitleItem(2, 2500, 4000, "重複時間"),  # 時間重複
            SubtitleItem(3, 5000, 5200, "短"),        # 短すぎる
            SubtitleItem(4, 6000, 7000, "")           # 空テキスト
        ]
        
        results = checker.check_all(subtitles)
        assert len(results) > 0
        
        # エラーレベルの結果があることを確認
        error_results = [r for r in results if r.severity == "ERROR"]
        assert len(error_results) > 0
    
    def test_get_summary(self):
        """サマリー取得のテスト"""
        results = [
            QCResult("rule1", "ERROR", "エラー1", 1),
            QCResult("rule2", "WARNING", "警告1", 2),
            QCResult("rule3", "WARNING", "警告2", 3),
            QCResult("rule4", "INFO", "情報1", 4)
        ]
        
        summary = QCChecker.get_summary(results)
        
        assert summary["total"] == 4
        assert summary["errors"] == 1
        assert summary["warnings"] == 2
        assert summary["info"] == 1