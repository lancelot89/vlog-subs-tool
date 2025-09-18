"""
QC（品質管理）チェックルールの実装
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from app.core.models import QCResult, SubtitleItem


class QCSeverity(Enum):
    """QC結果の重要度"""

    ERROR = "error"  # エラー（修正必須）
    WARNING = "warning"  # 警告（推奨修正）
    INFO = "info"  # 情報（参考）


@dataclass
class QCRule:
    """QCルールの基底クラス"""

    name: str
    description: str
    enabled: bool = True

    def check(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        """字幕リストをチェック（サブクラスで実装）"""
        raise NotImplementedError


class LineLengthRule(QCRule):
    """行長チェックルール"""

    def __init__(self, max_chars: int = 42, enabled: bool = True):
        super().__init__(
            name="行長チェック", description=f"1行{max_chars}文字以内", enabled=enabled
        )
        self.max_chars = max_chars

    def check(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        results = []

        for i, subtitle in enumerate(subtitles):
            lines = subtitle.text.split("\n")

            for line_num, line in enumerate(lines, 1):
                if len(line) > self.max_chars:
                    results.append(
                        QCResult(
                            subtitle_index=i,
                            error_type="line_too_long",
                            message=f"行{line_num}: {len(line)}文字（{self.max_chars}文字制限）",
                            severity=QCSeverity.WARNING.value,
                        )
                    )

        return results


class MaxLinesRule(QCRule):
    """最大行数チェックルール"""

    def __init__(self, max_lines: int = 2, enabled: bool = True):
        super().__init__(name="最大行数チェック", description=f"最大{max_lines}行", enabled=enabled)
        self.max_lines = max_lines

    def check(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        results = []

        for i, subtitle in enumerate(subtitles):
            lines = subtitle.text.split("\n")
            line_count = len([line for line in lines if line.strip()])

            if line_count > self.max_lines:
                results.append(
                    QCResult(
                        subtitle_index=i,
                        error_type="too_many_lines",
                        message=f"{line_count}行（{self.max_lines}行制限）",
                        severity=QCSeverity.WARNING.value,
                    )
                )

        return results


class DurationRule(QCRule):
    """表示時間チェックルール"""

    def __init__(
        self,
        min_duration_ms: int = 1200,
        max_duration_ms: int = 10000,
        enabled: bool = True,
    ):
        super().__init__(
            name="表示時間チェック",
            description=f"表示時間 {min_duration_ms/1000:.1f}秒-{max_duration_ms/1000:.1f}秒",
            enabled=enabled,
        )
        self.min_duration_ms = min_duration_ms
        self.max_duration_ms = max_duration_ms

    def check(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        results = []

        for i, subtitle in enumerate(subtitles):
            duration = subtitle.end_ms - subtitle.start_ms

            if duration < self.min_duration_ms:
                results.append(
                    QCResult(
                        subtitle_index=i,
                        error_type="duration_too_short",
                        message=f"表示時間短すぎ: {duration/1000:.1f}秒（最小{self.min_duration_ms/1000:.1f}秒）",
                        severity=QCSeverity.WARNING.value,
                    )
                )

            elif duration > self.max_duration_ms:
                results.append(
                    QCResult(
                        subtitle_index=i,
                        error_type="duration_too_long",
                        message=f"表示時間長すぎ: {duration/1000:.1f}秒（最大{self.max_duration_ms/1000:.1f}秒）",
                        severity=QCSeverity.INFO.value,
                    )
                )

        return results


class TimeOverlapRule(QCRule):
    """時間重複チェックルール"""

    def __init__(self, enabled: bool = True):
        super().__init__(
            name="時間重複チェック", description="字幕の時間重複を検出", enabled=enabled
        )

    def check(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        results = []

        for i, subtitle1 in enumerate(subtitles):
            for j, subtitle2 in enumerate(subtitles[i + 1 :], i + 1):
                # 時間重複の判定
                if subtitle1.start_ms < subtitle2.end_ms and subtitle1.end_ms > subtitle2.start_ms:

                    overlap_start = max(subtitle1.start_ms, subtitle2.start_ms)
                    overlap_end = min(subtitle1.end_ms, subtitle2.end_ms)
                    overlap_duration = overlap_end - overlap_start

                    results.append(
                        QCResult(
                            subtitle_index=i,
                            error_type="time_overlap",
                            message=f"字幕{j+1}と時間重複: {overlap_duration/1000:.1f}秒",
                            severity=QCSeverity.ERROR.value,
                        )
                    )

        return results


class TimeOrderRule(QCRule):
    """時間順序チェックルール"""

    def __init__(self, enabled: bool = True):
        super().__init__(
            name="時間順序チェック",
            description="開始時間≦終了時間の確認",
            enabled=enabled,
        )

    def check(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        results = []

        for i, subtitle in enumerate(subtitles):
            if subtitle.start_ms >= subtitle.end_ms:
                results.append(
                    QCResult(
                        subtitle_index=i,
                        error_type="invalid_time_order",
                        message="開始時間≧終了時間",
                        severity=QCSeverity.ERROR.value,
                    )
                )

        return results


class EmptyTextRule(QCRule):
    """空文字チェックルール"""

    def __init__(self, enabled: bool = True):
        super().__init__(
            name="空文字チェック", description="空の字幕テキストを検出", enabled=enabled
        )

    def check(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        results = []

        for i, subtitle in enumerate(subtitles):
            if not subtitle.text.strip():
                results.append(
                    QCResult(
                        subtitle_index=i,
                        error_type="empty_text",
                        message="字幕テキストが空です",
                        severity=QCSeverity.ERROR.value,
                    )
                )

        return results


class DuplicateTextRule(QCRule):
    """重複テキストチェックルール"""

    def __init__(self, enabled: bool = True):
        super().__init__(
            name="重複テキストチェック",
            description="同じテキストの字幕を検出",
            enabled=enabled,
        )

    def check(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        results = []
        seen_texts = {}

        for i, subtitle in enumerate(subtitles):
            text = subtitle.text.strip().lower()

            if text in seen_texts:
                # 時間が近い場合のみ重複として扱う
                prev_index = seen_texts[text]
                prev_subtitle = subtitles[prev_index]

                time_gap = abs(subtitle.start_ms - prev_subtitle.end_ms)
                if time_gap < 5000:  # 5秒以内
                    results.append(
                        QCResult(
                            subtitle_index=i,
                            error_type="duplicate_text",
                            message=f"字幕{prev_index+1}と重複テキスト",
                            severity=QCSeverity.WARNING.value,
                        )
                    )
            else:
                seen_texts[text] = i

        return results


class ReadingSpeedRule(QCRule):
    """読み速度チェックルール"""

    def __init__(self, max_chars_per_second: float = 20.0, enabled: bool = True):
        super().__init__(
            name="読み速度チェック",
            description=f"最大読み速度 {max_chars_per_second}文字/秒",
            enabled=enabled,
        )
        self.max_chars_per_second = max_chars_per_second

    def check(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        results = []

        for i, subtitle in enumerate(subtitles):
            duration_sec = (subtitle.end_ms - subtitle.start_ms) / 1000
            char_count = len(subtitle.text.replace("\n", "").replace(" ", ""))

            if duration_sec > 0:
                reading_speed = char_count / duration_sec

                if reading_speed > self.max_chars_per_second:
                    results.append(
                        QCResult(
                            subtitle_index=i,
                            error_type="reading_speed_too_fast",
                            message=f"読み速度: {reading_speed:.1f}文字/秒（最大{self.max_chars_per_second}文字/秒）",
                            severity=QCSeverity.WARNING.value,
                        )
                    )

        return results


class QCChecker:
    """QCチェッカー統合クラス"""

    def __init__(self):
        self.rules: List[QCRule] = []
        self._init_default_rules()

    def _init_default_rules(self):
        """デフォルトルールの初期化"""
        self.rules = [
            LineLengthRule(max_chars=42),
            MaxLinesRule(max_lines=2),
            DurationRule(min_duration_ms=1200, max_duration_ms=10000),
            TimeOverlapRule(),
            TimeOrderRule(),
            EmptyTextRule(),
            DuplicateTextRule(),
            ReadingSpeedRule(max_chars_per_second=20.0),
        ]

    def add_rule(self, rule: QCRule):
        """ルールを追加"""
        self.rules.append(rule)

    def remove_rule(self, rule_name: str):
        """ルールを削除"""
        self.rules = [rule for rule in self.rules if rule.name != rule_name]

    def enable_rule(self, rule_name: str, enabled: bool = True):
        """ルールの有効/無効を設定"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = enabled
                break

    def check_all(self, subtitles: List[SubtitleItem]) -> List[QCResult]:
        """すべてのルールでチェック実行"""
        all_results = []

        for rule in self.rules:
            if rule.enabled:
                try:
                    results = rule.check(subtitles)
                    all_results.extend(results)
                except Exception as e:
                    print(f"QCルール '{rule.name}' でエラー: {e}")

        return all_results

    def get_summary(self, results: List[QCResult]) -> Dict[str, int]:
        """QC結果のサマリーを取得"""
        summary = {"total": len(results), "error": 0, "warning": 0, "info": 0}

        for result in results:
            if result.severity in summary:
                summary[result.severity] += 1

        return summary

    def filter_results(
        self, results: List[QCResult], severity: QCSeverity = None
    ) -> List[QCResult]:
        """重要度でフィルタリング"""
        if severity is None:
            return results

        return [result for result in results if result.severity == severity.value]

    def get_rule_status(self) -> Dict[str, bool]:
        """ルールの有効状態を取得"""
        return {rule.name: rule.enabled for rule in self.rules}
