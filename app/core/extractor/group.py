"""
OCR結果のグルーピング・統合機能
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from app.core.models import SubtitleItem

from .ocr import OCRResult
from .sampler import VideoFrame


@dataclass
class FrameOCRResult:
    """フレーム単位のOCR結果"""

    frame: VideoFrame
    ocr_results: List[OCRResult]

    @property
    def best_text(self) -> str:
        """最も信頼度の高いテキストを取得"""
        if not self.ocr_results:
            return ""

        best_result = max(self.ocr_results, key=lambda x: x.confidence)
        return best_result.text

    @property
    def average_confidence(self) -> float:
        """平均信頼度を取得"""
        if not self.ocr_results:
            return 0.0

        return sum(r.confidence for r in self.ocr_results) / len(self.ocr_results)


class TextSimilarityCalculator:
    """テキスト類似度計算器"""

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """
        2つのテキストの類似度を計算（OCR誤認識対応版）

        Args:
            text1: テキスト1
            text2: テキスト2

        Returns:
            float: 類似度（0.0-1.0）
        """
        if not text1 or not text2:
            return 0.0

        # 正規化（空白・記号の統一）
        norm_text1 = TextSimilarityCalculator._normalize_text(text1)
        norm_text2 = TextSimilarityCalculator._normalize_text(text2)

        # 完全一致
        if norm_text1 == norm_text2:
            return 1.0

        # OCR誤認識対応の類似度計算
        ocr_similarity = TextSimilarityCalculator._calculate_ocr_aware_similarity(
            norm_text1, norm_text2
        )

        return ocr_similarity

    @staticmethod
    def _normalize_text(text: str) -> str:
        """テキストの正規化"""
        # 小文字化
        normalized = text.lower()

        # 全角・半角の統一
        normalized = normalized.translate(
            str.maketrans(
                "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
                "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
                "０１２３４５６７８９",
                "abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "0123456789",
            )
        )

        # 句読点・記号の正規化
        normalized = re.sub(r"[。、．，]", "", normalized)
        normalized = re.sub(r"[!！]", "!", normalized)
        normalized = re.sub(r"[?？]", "?", normalized)

        # 連続空白を1つに & 全ての空白を除去（OCR誤認識対応）
        normalized = re.sub(r"\s+", "", normalized)

        return normalized.strip()

    @staticmethod
    def _calculate_ocr_aware_similarity(text1: str, text2: str) -> float:
        """
        OCR誤認識を考慮した類似度計算
        """
        if not text1 or not text2:
            return 0.0

        # 長さの差が大きすぎる場合は低い類似度
        len_ratio = min(len(text1), len(text2)) / max(len(text1), len(text2))
        if len_ratio < 0.7:  # 70%未満の長さ差は別テキストと判定
            return 0.0

        # OCR誤認識の一般的なパターンをマッピング
        ocr_corrections = {
            "シヤ": "シャ",
            "シユ": "シュ",
            "シヨ": "ショ",
            "チヤ": "チャ",
            "チユ": "チュ",
            "チヨ": "チョ",
            "ロ": "口",
            "口": "ロ",  # 「ロ」と「口」の相互変換
            "ニ": "コ",
            "コ": "ニ",  # 「ニ」と「コ」の相互変換
            "0": "O",
            "O": "0",
            "1": "l",
            "l": "1",
            "I": "1",
        }

        # OCR補正適用
        corrected_text1 = text1
        corrected_text2 = text2

        for wrong, correct in ocr_corrections.items():
            corrected_text1 = corrected_text1.replace(wrong, correct)
            corrected_text2 = corrected_text2.replace(wrong, correct)

        # 補正後の比較
        if corrected_text1 == corrected_text2:
            return 1.0

        # 文字単位の編集距離ベースの類似度
        edit_distance = TextSimilarityCalculator._calculate_edit_distance(
            corrected_text1, corrected_text2
        )
        max_len = max(len(corrected_text1), len(corrected_text2))

        if max_len == 0:
            return 1.0

        # 編集距離ベースの類似度（1文字違いでも高い類似度を保持）
        similarity = 1.0 - (edit_distance / max_len)

        # OCR誤認識の場合は類似度を底上げ（1-2文字の違いなら統合対象とする）
        if edit_distance <= 2 and len_ratio >= 0.9:
            similarity = max(similarity, 0.92)  # 90%閾値を超える値に設定

        return similarity

    @staticmethod
    def _calculate_edit_distance(s1: str, s2: str) -> int:
        """
        レーベンシュタイン距離（編集距離）を計算
        """
        if len(s1) < len(s2):
            return TextSimilarityCalculator._calculate_edit_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # 挿入、削除、置換のコスト
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]


class SubtitleGrouper:
    """字幕グルーピング処理"""

    def __init__(
        self,
        similarity_threshold: float = 0.90,
        min_duration_sec: float = 1.2,
        max_gap_sec: float = 0.5,
    ):
        """
        Args:
            similarity_threshold: 類似度閾値（この値以上で同一字幕と判定）
            min_duration_sec: 最小表示秒数
            max_gap_sec: 結合可能な最大間隔（秒）
        """
        self.similarity_threshold = similarity_threshold
        self.min_duration_ms = int(min_duration_sec * 1000)
        self.max_gap_ms = int(max_gap_sec * 1000)
        self.similarity_calc = TextSimilarityCalculator()

    def group_frame_results(
        self, frame_results: List[FrameOCRResult]
    ) -> List[SubtitleItem]:
        """
        フレームOCR結果を字幕アイテムにグルーピング

        Args:
            frame_results: フレーム別OCR結果リスト

        Returns:
            List[SubtitleItem]: グルーピングされた字幕アイテム
        """
        if not frame_results:
            return []

        # フレーム結果を時間順にソート
        sorted_results = sorted(frame_results, key=lambda x: x.frame.timestamp_ms)

        # 空のフレームを除去
        valid_results = [r for r in sorted_results if r.best_text.strip()]

        if not valid_results:
            return []

        # 連続する類似フレームをグルーピング
        groups = self._group_similar_frames(valid_results)

        # グループを字幕アイテムに変換
        subtitle_items = []
        for i, group in enumerate(groups):
            item = self._create_subtitle_item(i + 1, group)
            if item:
                subtitle_items.append(item)

        # 短すぎる字幕を統合
        subtitle_items = self._merge_short_subtitles(subtitle_items)

        # インデックスを再採番
        for i, item in enumerate(subtitle_items, 1):
            item.index = i

        return subtitle_items

    def _group_similar_frames(
        self, frame_results: List[FrameOCRResult]
    ) -> List[List[FrameOCRResult]]:
        """類似フレームをグルーピング"""
        if not frame_results:
            return []

        groups = []
        current_group = [frame_results[0]]

        for i in range(1, len(frame_results)):
            current_result = frame_results[i]
            prev_result = frame_results[i - 1]

            # テキスト類似度の計算
            similarity = self.similarity_calc.calculate_similarity(
                current_result.best_text, prev_result.best_text
            )

            # 時間間隔の確認
            time_gap = (
                current_result.frame.timestamp_ms - prev_result.frame.timestamp_ms
            )

            # 同一グループに追加する条件
            if (
                similarity >= self.similarity_threshold
                and time_gap <= self.max_gap_ms * 3
            ):  # 少し余裕を持たせる
                current_group.append(current_result)
            else:
                # 新しいグループを開始
                groups.append(current_group)
                current_group = [current_result]

        # 最後のグループを追加
        if current_group:
            groups.append(current_group)

        return groups

    def _create_subtitle_item(
        self, index: int, group: List[FrameOCRResult]
    ) -> Optional[SubtitleItem]:
        """グループから字幕アイテムを作成"""
        if not group:
            return None

        # 時間範囲の計算
        start_ms = group[0].frame.timestamp_ms
        end_ms = group[-1].frame.timestamp_ms

        # 最小表示時間の保証
        if end_ms - start_ms < self.min_duration_ms:
            end_ms = start_ms + self.min_duration_ms

        # 最も信頼度の高いテキストを選択
        best_text = self._select_best_text(group)

        if not best_text.strip():
            return None

        # バウンディングボックスの計算（最初のフレームの結果を使用）
        bbox = self._calculate_bbox(group[0])

        return SubtitleItem(
            index=index, start_ms=start_ms, end_ms=end_ms, text=best_text, bbox=bbox
        )

    def _select_best_text(self, group: List[FrameOCRResult]) -> str:
        """グループから最適なテキストを選択（2行字幕検出対応）"""
        if not group:
            return ""

        # 最も信頼度の高いフレームを選択
        best_frame = max(group, key=lambda x: x.average_confidence)

        # そのフレームから2行字幕を検出・構成
        multi_line_text = self._detect_multiline_text(best_frame)

        if multi_line_text:
            return self._clean_subtitle_text(multi_line_text)

        # フォールバック: 従来の単行処理
        text_confidence_pairs = []
        for frame_result in group:
            text = frame_result.best_text
            confidence = frame_result.average_confidence
            if text.strip():
                text_confidence_pairs.append((text, confidence))

        if not text_confidence_pairs:
            return ""

        # 信頼度が最も高いテキストを選択
        best_text, _ = max(text_confidence_pairs, key=lambda x: x[1])

        # テキストクリーンアップ
        return self._clean_subtitle_text(best_text)

    def _detect_multiline_text(self, frame_result: FrameOCRResult) -> str:
        """フレーム内の複数OCR結果から2行字幕を検出・構成"""
        if len(frame_result.ocr_results) <= 1:
            return frame_result.best_text  # 単一テキストの場合はそのまま返す

        # OCR結果をY座標でソート（上から下へ）
        sorted_results = sorted(frame_result.ocr_results, key=lambda x: x.bbox[1])

        # 2行字幕の候補を検出
        line_groups = self._group_by_vertical_position(sorted_results)

        if len(line_groups) >= 2:
            # 2行以上の場合、最初の2つのグループを使用
            line1_texts = [result.text for result in line_groups[0]]
            line2_texts = [result.text for result in line_groups[1]]

            # 各行内でX座標順にソート
            line1_texts.sort(
                key=lambda text: next(
                    result.bbox[0] for result in line_groups[0] if result.text == text
                )
            )
            line2_texts.sort(
                key=lambda text: next(
                    result.bbox[0] for result in line_groups[1] if result.text == text
                )
            )

            # 行を結合
            line1 = " ".join(line1_texts).strip()
            line2 = " ".join(line2_texts).strip()

            if line1 and line2:
                return f"{line1}\n{line2}"

        # 2行構成できない場合は単行として返す
        return frame_result.best_text

    def _group_by_vertical_position(
        self, sorted_results: List[OCRResult]
    ) -> List[List[OCRResult]]:
        """OCR結果を垂直位置でグループ化"""
        if not sorted_results:
            return []

        line_groups = []
        current_group = [sorted_results[0]]
        current_y_center = sorted_results[0].bbox[1] + sorted_results[0].bbox[3] // 2

        # Y座標の許容範囲（テキストの高さの50%程度）
        for result in sorted_results[1:]:
            result_y_center = result.bbox[1] + result.bbox[3] // 2
            text_height = result.bbox[3]

            # 同じ行と判定する垂直距離の閾値
            vertical_threshold = text_height * 0.5

            if abs(result_y_center - current_y_center) <= vertical_threshold:
                # 同じ行のグループに追加
                current_group.append(result)
            else:
                # 新しい行のグループを開始
                line_groups.append(current_group)
                current_group = [result]
                current_y_center = result_y_center

        # 最後のグループを追加
        if current_group:
            line_groups.append(current_group)

        return line_groups

    def _clean_subtitle_text(self, text: str) -> str:
        """字幕テキストのクリーンアップ"""
        if not text:
            return ""

        # 基本的なクリーンアップ
        cleaned = text.strip()

        # 明らかな誤認識文字の除去・修正
        replacements = {
            "|": "l",
            "0": "O",  # 文脈によって
            "1": "l",  # 文脈によって
        }

        # OCR特有の誤認識パターンの修正
        cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", cleaned)  # 制御文字除去

        # 連続する同じ文字の除去（明らかな誤認識）
        cleaned = re.sub(r"(.)\1{3,}", r"\1", cleaned)

        return cleaned

    def _calculate_bbox(
        self, frame_result: FrameOCRResult
    ) -> Optional[Tuple[int, int, int, int]]:
        """バウンディングボックスの計算"""
        if not frame_result.ocr_results:
            return None

        # 全ての検出領域を統合
        min_x = min(r.bbox[0] for r in frame_result.ocr_results)
        min_y = min(r.bbox[1] for r in frame_result.ocr_results)
        max_x = max(r.bbox[0] + r.bbox[2] for r in frame_result.ocr_results)
        max_y = max(r.bbox[1] + r.bbox[3] for r in frame_result.ocr_results)

        return (min_x, min_y, max_x - min_x, max_y - min_y)

    def _merge_short_subtitles(
        self, subtitles: List[SubtitleItem]
    ) -> List[SubtitleItem]:
        """短すぎる字幕を前後と統合"""
        if not subtitles:
            return []

        merged = []
        i = 0

        while i < len(subtitles):
            current = subtitles[i]

            # 表示時間が短すぎる場合
            if current.duration_ms() < self.min_duration_ms:
                # 次の字幕と統合可能かチェック
                if (
                    i + 1 < len(subtitles)
                    and subtitles[i + 1].start_ms - current.end_ms <= self.max_gap_ms
                ):

                    next_subtitle = subtitles[i + 1]

                    # 統合
                    merged_subtitle = SubtitleItem(
                        index=current.index,
                        start_ms=current.start_ms,
                        end_ms=next_subtitle.end_ms,
                        text=f"{current.text} {next_subtitle.text}",
                        bbox=current.bbox,
                    )

                    merged.append(merged_subtitle)
                    i += 2  # 2つの字幕をスキップ
                    continue

                # 前の字幕と統合可能かチェック
                elif merged and current.start_ms - merged[-1].end_ms <= self.max_gap_ms:
                    prev_subtitle = merged.pop()

                    # 統合
                    merged_subtitle = SubtitleItem(
                        index=prev_subtitle.index,
                        start_ms=prev_subtitle.start_ms,
                        end_ms=current.end_ms,
                        text=f"{prev_subtitle.text} {current.text}",
                        bbox=prev_subtitle.bbox,
                    )

                    merged.append(merged_subtitle)
                    i += 1
                    continue

                else:
                    # 統合できない場合は最小時間まで延長
                    current.end_ms = current.start_ms + self.min_duration_ms

            merged.append(current)
            i += 1

        return merged


class ExtractionProcessor:
    """抽出処理の統合クラス"""

    def __init__(self, settings: Dict):
        """
        Args:
            settings: 抽出設定辞書
        """
        self.settings = settings
        self.grouper = SubtitleGrouper(
            similarity_threshold=settings.get("similarity_threshold", 0.90),
            min_duration_sec=settings.get("min_duration_sec", 1.2),
            max_gap_sec=settings.get("max_gap_sec", 0.5),
        )

    def process_extraction_results(
        self, frame_results: List[FrameOCRResult]
    ) -> List[SubtitleItem]:
        """
        抽出結果の処理

        Args:
            frame_results: フレーム別OCR結果

        Returns:
            List[SubtitleItem]: 処理済み字幕アイテム
        """
        # グルーピング処理
        subtitle_items = self.grouper.group_frame_results(frame_results)

        # 追加の後処理
        subtitle_items = self._post_process_subtitles(subtitle_items)

        return subtitle_items

    def _post_process_subtitles(
        self, subtitles: List[SubtitleItem]
    ) -> List[SubtitleItem]:
        """字幕の後処理"""
        # 重複除去
        subtitles = self._remove_duplicates(subtitles)

        # 時間順ソート
        subtitles.sort(key=lambda x: x.start_ms)

        # インデックス再採番
        for i, subtitle in enumerate(subtitles, 1):
            subtitle.index = i

        return subtitles

    def _remove_duplicates(self, subtitles: List[SubtitleItem]) -> List[SubtitleItem]:
        """重複字幕の統合（同じテキストの字幕をマージ）"""
        if not subtitles:
            return []

        # 時間順にソート
        sorted_subtitles = sorted(subtitles, key=lambda x: x.start_ms)

        # 時間制約付きの重複統合（近接する類似字幕のみ統合）
        time_aware_merged = self._merge_time_constrained_duplicates(sorted_subtitles)

        # 最後に時間重複ベースの統合（従来の重複除去）
        final_merged = self._merge_overlapping_subtitles(time_aware_merged)

        return final_merged

    def _merge_time_constrained_duplicates(
        self, subtitles: List[SubtitleItem]
    ) -> List[SubtitleItem]:
        """時間制約付きテキスト類似度による統合（近接する字幕のみ対象）"""
        if not subtitles:
            return []

        merged = []
        calc = TextSimilarityCalculator()
        max_merge_gap_ms = 30000  # 30秒以内の字幕のみ統合対象とする

        i = 0
        while i < len(subtitles):
            current_group = [subtitles[i]]
            j = i + 1

            # 現在の字幕から30秒以内の類似字幕を探す
            while j < len(subtitles):
                time_gap = subtitles[j].start_ms - subtitles[i].end_ms

                # 時間間隔が30秒を超えたら統合対象外
                if time_gap > max_merge_gap_ms:
                    break

                # 連鎖的重複対応: 既存グループのいずれかとの類似度をチェック
                is_similar_to_group = False
                for group_member in current_group:
                    similarity = calc.calculate_similarity(
                        group_member.text, subtitles[j].text
                    )
                    if similarity > 0.90:
                        is_similar_to_group = True
                        break

                if is_similar_to_group:
                    current_group.append(subtitles[j])
                    subtitles.pop(j)  # 統合対象を削除
                else:
                    j += 1

            # グループを統合して追加
            if len(current_group) == 1:
                merged.append(current_group[0])
            else:
                merged_subtitle = self._merge_duplicate_group(current_group)
                merged.append(merged_subtitle)

            i += 1

        return merged

    def _merge_overlapping_subtitles(
        self, subtitles: List[SubtitleItem]
    ) -> List[SubtitleItem]:
        """時間重複している字幕の統合"""
        if not subtitles:
            return []

        # 時間順にソート
        sorted_subtitles = sorted(subtitles, key=lambda x: x.start_ms)
        merged = []
        calc = TextSimilarityCalculator()

        for subtitle in sorted_subtitles:
            # 既存の字幕と時間重複かつテキスト類似度をチェック
            found_overlap = False

            for i, existing in enumerate(merged):
                # 時間重複の判定
                time_overlap = (
                    subtitle.start_ms < existing.end_ms
                    and subtitle.end_ms > existing.start_ms
                )

                if time_overlap:
                    # テキスト類似度の判定
                    similarity = calc.calculate_similarity(subtitle.text, existing.text)
                    if similarity > 0.80:  # 80%以上の類似度で統合
                        # 既存の字幕と統合
                        merged_subtitle = SubtitleItem(
                            index=existing.index,
                            start_ms=min(existing.start_ms, subtitle.start_ms),
                            end_ms=max(existing.end_ms, subtitle.end_ms),
                            text=existing.text,  # より長いテキストを保持
                            bbox=existing.bbox,
                        )
                        # より長いテキストを選択
                        if len(subtitle.text) > len(existing.text):
                            merged_subtitle.text = subtitle.text

                        merged[i] = merged_subtitle
                        found_overlap = True
                        break

            if not found_overlap:
                merged.append(subtitle)

        return merged

    def _merge_duplicate_group(self, group: List[SubtitleItem]) -> SubtitleItem:
        """同じテキストの字幕グループを統合"""
        if not group:
            return None

        # 最も早い開始時間と最も遅い終了時間を取得
        min_start_ms = min(subtitle.start_ms for subtitle in group)
        max_end_ms = max(subtitle.end_ms for subtitle in group)

        # 最も信頼度の高い（または最初の）字幕のテキストとbboxを使用
        base_subtitle = group[0]

        # 統合された字幕を作成
        merged_subtitle = SubtitleItem(
            index=base_subtitle.index,  # インデックスは後で再採番される
            start_ms=min_start_ms,
            end_ms=max_end_ms,
            text=base_subtitle.text,
            bbox=base_subtitle.bbox,
        )

        return merged_subtitle
