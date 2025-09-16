#!/usr/bin/env python3
"""
テスト動画での字幕抽出機能のテストスクリプト
"""

import sys
import logging
from pathlib import Path

# アプリケーションのパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from app.core.models import ProjectSettings
from app.core.extractor.detector import SubtitleDetector

def test_subtitle_extraction():
    """テスト動画での字幕抽出を実行"""

    # ログ設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # テスト動画のパス
    test_video_path = "tests/fixtures/test_video.mp4"

    if not Path(test_video_path).exists():
        print(f"エラー: テスト動画が見つかりません: {test_video_path}")
        return False

    print(f"テスト動画: {test_video_path}")

    # プロジェクト設定
    settings = ProjectSettings(
        fps_sample=1.0,  # 1秒間隔でサンプリング
        roi_mode="bottom_30",  # 下部30%の領域
        roi_rect=None,
        ocr_engine="paddleocr",
        similarity_threshold=0.8,
        min_dur_sec=1.0
    )

    try:
        # 字幕検出器を初期化
        print("字幕検出器を初期化しています...")
        detector = SubtitleDetector(settings)

        # 進捗コールバックを設定
        def progress_callback(percentage, message):
            print(f"[{percentage:3d}%] {message}")

        detector.set_progress_callback(progress_callback)

        # 字幕抽出を実行
        print("字幕抽出を開始します...")
        subtitle_items = detector.detect_subtitles(test_video_path)

        print(f"\n=== 抽出結果 ===")
        print(f"検出された字幕数: {len(subtitle_items)}")

        if subtitle_items:
            print("\n=== 抽出された字幕 ===")
            for i, item in enumerate(subtitle_items[:10]):  # 最初の10件を表示
                start_time = f"{item.start_ms // 1000}s"
                end_time = f"{item.end_ms // 1000}s"
                print(f"{i+1:2d}. [{start_time}-{end_time}] {item.text}")

            if len(subtitle_items) > 10:
                print(f"... および他 {len(subtitle_items) - 10} 件")
        else:
            print("字幕が検出されませんでした")

        return True

    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_subtitle_extraction()
    sys.exit(0 if success else 1)