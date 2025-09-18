"""
動画フレームサンプリング機能の実装
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List, Tuple

import cv2
import numpy as np


@dataclass
class VideoFrame:
    """動画フレームのデータクラス"""

    frame_number: int
    timestamp_ms: int
    image: np.ndarray

    @property
    def timestamp_sec(self) -> float:
        """タイムスタンプ（秒）"""
        return self.timestamp_ms / 1000.0


class VideoSampler:
    """動画フレームサンプラー"""

    def __init__(self, video_path: str, sample_fps: float = 3.0):
        """
        Args:
            video_path: 動画ファイルパス
            sample_fps: サンプリングFPS（既定値: 3.0）
        """
        self.video_path = Path(video_path)
        self.sample_fps = sample_fps
        self.cap = None
        self._video_info = None

        self._initialize_capture()

    def _initialize_capture(self):
        """VideoCapture の初期化"""
        if not self.video_path.exists():
            raise FileNotFoundError(f"動画ファイルが見つかりません: {self.video_path}")

        self.cap = cv2.VideoCapture(str(self.video_path))
        if not self.cap.isOpened():
            raise RuntimeError(f"動画ファイルを開けませんでした: {self.video_path}")

        # 動画情報の取得
        self._video_info = {
            "fps": self.cap.get(cv2.CAP_PROP_FPS),
            "frame_count": int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "duration_sec": int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            / self.cap.get(cv2.CAP_PROP_FPS),
        }

    @property
    def video_info(self) -> dict:
        """動画情報を取得"""
        return self._video_info.copy() if self._video_info else {}

    def sample_frames(self) -> Generator[VideoFrame, None, None]:
        """
        指定したFPSでフレームをサンプリング

        Yields:
            VideoFrame: サンプリングされたフレーム
        """
        if not self.cap or not self.cap.isOpened():
            return

        original_fps = self._video_info["fps"]
        frame_interval = int(original_fps / self.sample_fps)

        frame_number = 0
        while True:
            # 指定フレーム位置にシーク
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

            ret, frame = self.cap.read()
            if not ret:
                break

            # タイムスタンプの計算
            timestamp_ms = int((frame_number / original_fps) * 1000)

            yield VideoFrame(
                frame_number=frame_number, timestamp_ms=timestamp_ms, image=frame.copy()
            )

            frame_number += frame_interval

    def get_frame_at_time(self, time_ms: int) -> VideoFrame:
        """
        指定時間のフレームを取得

        Args:
            time_ms: 時間（ミリ秒）

        Returns:
            VideoFrame: 指定時間のフレーム
        """
        if not self.cap or not self.cap.isOpened():
            raise RuntimeError("動画が開かれていません")

        # フレーム番号を計算
        frame_number = int((time_ms / 1000.0) * self._video_info["fps"])

        # 指定フレームにシーク
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

        ret, frame = self.cap.read()
        if not ret:
            raise RuntimeError(f"フレーム {frame_number} の読み込みに失敗しました")

        return VideoFrame(
            frame_number=frame_number, timestamp_ms=time_ms, image=frame.copy()
        )

    def get_frames_in_range(self, start_ms: int, end_ms: int) -> List[VideoFrame]:
        """
        指定時間範囲のフレームを取得

        Args:
            start_ms: 開始時間（ミリ秒）
            end_ms: 終了時間（ミリ秒）

        Returns:
            List[VideoFrame]: 指定範囲のフレーム一覧
        """
        frames = []

        original_fps = self._video_info["fps"]
        frame_interval = int(original_fps / self.sample_fps)

        start_frame = int((start_ms / 1000.0) * original_fps)
        end_frame = int((end_ms / 1000.0) * original_fps)

        for frame_number in range(start_frame, end_frame + 1, frame_interval):
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

            ret, frame = self.cap.read()
            if not ret:
                break

            timestamp_ms = int((frame_number / original_fps) * 1000)

            frames.append(
                VideoFrame(
                    frame_number=frame_number,
                    timestamp_ms=timestamp_ms,
                    image=frame.copy(),
                )
            )

        return frames

    def extract_roi_frames(
        self, roi_rect: Tuple[int, int, int, int]
    ) -> Generator[VideoFrame, None, None]:
        """
        指定矩形領域を切り出してサンプリング

        Args:
            roi_rect: ROI矩形 (x, y, width, height)

        Yields:
            VideoFrame: ROI領域を切り出したフレーム
        """
        x, y, w, h = roi_rect

        for frame in self.sample_frames():
            # ROI領域を切り出し
            roi_image = frame.image[y : y + h, x : x + w]

            yield VideoFrame(
                frame_number=frame.frame_number,
                timestamp_ms=frame.timestamp_ms,
                image=roi_image,
            )

    def close(self):
        """リソースの解放"""
        if self.cap:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        """コンテキストマネージャーの開始"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了"""
        self.close()


class BottomROISampler(VideoSampler):
    """下段領域専用サンプラー（DESIGN.mdの下段30%仕様）"""

    def __init__(
        self, video_path: str, sample_fps: float = 3.0, bottom_ratio: float = 0.3
    ):
        """
        Args:
            video_path: 動画ファイルパス
            sample_fps: サンプリングFPS
            bottom_ratio: 下段比率（0.3 = 30%）
        """
        super().__init__(video_path, sample_fps)
        self.bottom_ratio = bottom_ratio

        # 下段ROI矩形を計算
        height = self._video_info["height"]
        width = self._video_info["width"]

        roi_height = int(height * bottom_ratio)
        roi_y = height - roi_height

        self.roi_rect = (0, roi_y, width, roi_height)

    def get_bottom_roi_rect(self) -> Tuple[int, int, int, int]:
        """下段ROI矩形を取得"""
        return self.roi_rect

    def sample_bottom_frames(self) -> Generator[VideoFrame, None, None]:
        """下段領域のフレームをサンプリング"""
        yield from self.extract_roi_frames(self.roi_rect)

    def visualize_roi(self, frame: np.ndarray) -> np.ndarray:
        """ROI領域を可視化した画像を返す"""
        vis_frame = frame.copy()
        x, y, w, h = self.roi_rect

        # 赤い矩形で描画
        cv2.rectangle(vis_frame, (x, y), (x + w, y + h), (0, 0, 255), 2)

        # ラベル描画
        cv2.putText(
            vis_frame,
            f"OCR Area ({self.bottom_ratio*100:.0f}%)",
            (x + 10, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )

        return vis_frame
