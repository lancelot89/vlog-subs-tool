"""
ROI（関心領域）検出機能の実装
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .sampler import VideoFrame


class ROIMode(Enum):
    """ROI検出モード"""

    AUTO = "auto"  # 自動検出
    BOTTOM_30 = "bottom_30"  # 下段30%固定
    MANUAL = "manual"  # 手動指定


@dataclass
class ROIRegion:
    """ROI領域の情報"""

    x: int
    y: int
    width: int
    height: int
    confidence: float = 1.0

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        """矩形タプルを返す (x, y, w, h)"""
        return (self.x, self.y, self.width, self.height)

    @property
    def area(self) -> int:
        """面積を計算"""
        return self.width * self.height


class ROIDetector:
    """ROI検出器のベースクラス"""

    def __init__(self, frame_width: int, frame_height: int):
        self.frame_width = frame_width
        self.frame_height = frame_height

    def detect(self, frames: List[VideoFrame]) -> ROIRegion:
        """ROI領域を検出（サブクラスで実装）"""
        raise NotImplementedError

    def visualize_roi(
        self, frame: np.ndarray, roi: ROIRegion, color=(0, 255, 0), thickness=2
    ) -> np.ndarray:
        """ROI領域を可視化"""
        vis_frame = frame.copy()
        x, y, w, h = roi.rect

        # 矩形描画
        cv2.rectangle(vis_frame, (x, y), (x + w, y + h), color, thickness)

        # 信頼度表示
        label = f"ROI (conf: {roi.confidence:.2f})"
        cv2.putText(
            vis_frame,
            label,
            (x, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            thickness,
        )

        return vis_frame


class BottomROIDetector(ROIDetector):
    """下段固定ROI検出器"""

    def __init__(self, frame_width: int, frame_height: int, bottom_ratio: float = 0.3):
        super().__init__(frame_width, frame_height)
        self.bottom_ratio = bottom_ratio

    def detect(self, frames: List[VideoFrame]) -> ROIRegion:
        """下段領域を返す"""
        height = int(self.frame_height * self.bottom_ratio)
        y = self.frame_height - height

        return ROIRegion(
            x=0, y=y, width=self.frame_width, height=height, confidence=1.0
        )


class AutoROIDetector(ROIDetector):
    """自動ROI検出器（文字領域を自動検出）"""

    def __init__(self, frame_width: int, frame_height: int):
        super().__init__(frame_width, frame_height)

    def detect(self, frames: List[VideoFrame]) -> ROIRegion:
        """複数フレームから字幕領域を自動検出"""
        if not frames:
            # フォールバック: 下段30%
            return BottomROIDetector(self.frame_width, self.frame_height).detect(frames)

        # 複数フレームでテキスト領域を検出
        text_regions = []

        for frame in frames:
            regions = self._detect_text_regions(frame.image)
            text_regions.extend(regions)

        if not text_regions:
            # テキスト領域が見つからない場合は下段30%にフォールバック
            return BottomROIDetector(self.frame_width, self.frame_height).detect(frames)

        # 最も頻繁に出現する領域を字幕領域と判定
        roi = self._find_consistent_roi(text_regions)

        return roi

    def _detect_text_regions(self, frame: np.ndarray) -> List[ROIRegion]:
        """単一フレームからテキスト領域を検出"""
        # グレースケール変換
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # MSERを使用してテキスト候補領域を検出
        mser = cv2.MSER_create()
        regions, _ = mser.detectRegions(gray)

        text_regions = []

        for region in regions:
            # 領域の外接矩形を計算
            x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))

            # 字幕らしい領域をフィルタリング
            if self._is_subtitle_like_region(x, y, w, h, frame.shape):
                confidence = self._calculate_text_confidence(gray[y : y + h, x : x + w])

                text_regions.append(
                    ROIRegion(x=x, y=y, width=w, height=h, confidence=confidence)
                )

        return text_regions

    def _is_subtitle_like_region(
        self, x: int, y: int, w: int, h: int, frame_shape: Tuple[int, int, int]
    ) -> bool:
        """字幕らしい領域かどうかを判定"""
        frame_h, frame_w = frame_shape[:2]

        # サイズフィルター
        if w < 50 or h < 15:  # 小さすぎる
            return False
        if w > frame_w * 0.8:  # 大きすぎる
            return False
        if h > frame_h * 0.3:  # 高すぎる
            return False

        # アスペクト比フィルター
        aspect_ratio = w / h
        if aspect_ratio < 2 or aspect_ratio > 20:
            return False

        # 位置フィルター（画面下半分に集中）
        if y < frame_h * 0.5:
            return False

        return True

    def _calculate_text_confidence(self, roi_image: np.ndarray) -> float:
        """テキスト領域の信頼度を計算"""
        if roi_image.size == 0:
            return 0.0

        # エッジ密度を計算（テキストはエッジが多い）
        edges = cv2.Canny(roi_image, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size

        # コントラストを計算
        std_dev = np.std(roi_image)

        # 信頼度の計算（エッジ密度とコントラストの組み合わせ）
        confidence = min(edge_density * 2 + std_dev / 255, 1.0)

        return confidence

    def _find_consistent_roi(self, text_regions: List[ROIRegion]) -> ROIRegion:
        """一貫性のあるROI領域を見つける"""
        if not text_regions:
            # フォールバック
            return ROIRegion(
                0,
                int(self.frame_height * 0.7),
                self.frame_width,
                int(self.frame_height * 0.3),
            )

        # Y座標でグルーピング（垂直位置が近い領域をまとめる）
        y_groups = {}
        group_threshold = self.frame_height * 0.1  # 10%の範囲内

        for region in text_regions:
            found_group = False
            for group_y in y_groups.keys():
                if abs(region.y - group_y) < group_threshold:
                    y_groups[group_y].append(region)
                    found_group = True
                    break

            if not found_group:
                y_groups[region.y] = [region]

        # 最も多くの領域があるグループを選択
        best_group = max(y_groups.values(), key=len)

        # グループ内の領域を統合
        min_x = min(r.x for r in best_group)
        max_x = max(r.x + r.width for r in best_group)
        min_y = min(r.y for r in best_group)
        max_y = max(r.y + r.height for r in best_group)
        avg_confidence = sum(r.confidence for r in best_group) / len(best_group)

        return ROIRegion(
            x=min_x,
            y=min_y,
            width=max_x - min_x,
            height=max_y - min_y,
            confidence=avg_confidence,
        )


class ManualROIDetector(ROIDetector):
    """手動指定ROI検出器"""

    def __init__(
        self,
        frame_width: int,
        frame_height: int,
        manual_rect: Tuple[int, int, int, int],
    ):
        super().__init__(frame_width, frame_height)
        self.manual_rect = manual_rect

    def detect(self, frames: List[VideoFrame]) -> ROIRegion:
        """手動指定された領域を返す"""
        x, y, w, h = self.manual_rect

        return ROIRegion(x=x, y=y, width=w, height=h, confidence=1.0)


class ROIManager:
    """ROI検出の管理クラス"""

    def __init__(self, frame_width: int, frame_height: int):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.detectors = {
            ROIMode.AUTO: AutoROIDetector(frame_width, frame_height),
            ROIMode.BOTTOM_30: BottomROIDetector(frame_width, frame_height, 0.3),
        }
        self.manual_detector: Optional[ManualROIDetector] = None

    def set_manual_roi(self, rect: Tuple[int, int, int, int]):
        """手動ROI矩形を設定"""
        self.manual_detector = ManualROIDetector(
            self.frame_width, self.frame_height, rect
        )

    def detect_roi(self, mode: ROIMode, frames: List[VideoFrame]) -> ROIRegion:
        """指定モードでROIを検出"""
        if mode == ROIMode.MANUAL:
            if not self.manual_detector:
                raise ValueError("手動ROIが設定されていません")
            return self.manual_detector.detect(frames)

        detector = self.detectors.get(mode)
        if not detector:
            raise ValueError(f"未対応のROIモード: {mode}")

        return detector.detect(frames)

    def visualize_roi(
        self, frame: np.ndarray, roi: ROIRegion, mode: ROIMode
    ) -> np.ndarray:
        """ROI可視化"""
        colors = {
            ROIMode.AUTO: (0, 255, 0),  # 緑
            ROIMode.BOTTOM_30: (0, 0, 255),  # 赤
            ROIMode.MANUAL: (255, 0, 0),  # 青
        }

        color = colors.get(mode, (128, 128, 128))
        detector = self.detectors.get(mode, self.manual_detector)

        if detector:
            return detector.visualize_roi(frame, roi, color)

        return frame
