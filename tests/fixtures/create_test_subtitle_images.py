#!/usr/bin/env python3
"""
テスト用の日本語字幕画像を生成するスクリプト
VLOGでよく見られる白い縁取りのある字幕画像を作成
"""

import os
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont


def get_japanese_font():
    """日本語フォントを取得"""
    # システムにある日本語フォントパスを試す
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # 英語フォント（フォールバック）
        "/System/Library/Fonts/Arial Unicode MS.ttf",  # macOS
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux Noto
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Linux Noto alternative
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, 48)
            except:
                continue

    # フォールバック：デフォルトフォントを使用
    try:
        return ImageFont.load_default()
    except:
        return None


def create_subtitle_image_pil(
    text: str, width: int = 1280, height: int = 720, font_size: int = 48
) -> np.ndarray:
    """
    PILを使用して日本語対応の字幕画像を作成

    Args:
        text: 字幕テキスト
        width: 画像幅
        height: 画像高さ
        font_size: フォントサイズ

    Returns:
        np.ndarray: 生成された画像（OpenCV形式）
    """
    # PIL画像を作成（RGB）
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # フォントを取得
    font = get_japanese_font()

    if font is None:
        # フォントが取得できない場合は簡単な矩形で代用
        bbox = draw.textbbox((0, 0), text)
        text_width = bbox[2] - bbox[0] if bbox else len(text) * 20
        text_height = bbox[3] - bbox[1] if bbox else 30
    else:
        # フォントが利用可能な場合
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

    # テキストを画像の下部中央に配置
    x = (width - text_width) // 2
    y = height - 100  # 下から100ピクセル上

    # 黒い縁取りを描画（ストローク効果）
    stroke_width = 3
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx * dx + dy * dy <= stroke_width * stroke_width:
                draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font)

    # 白いテキストを描画
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    # PILからOpenCV形式に変換
    img_array = np.array(img)
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

    return img_bgr


def create_subtitle_image(
    text: str,
    width: int = 1280,
    height: int = 720,
    font_scale: float = 2.0,
    thickness: int = 3,
) -> np.ndarray:
    """
    字幕画像を作成（日本語対応）

    Args:
        text: 字幕テキスト
        width: 画像幅
        height: 画像高さ
        font_scale: フォントサイズ（PILでは使用しない）
        thickness: フォント太さ（PILでは使用しない）

    Returns:
        np.ndarray: 生成された画像
    """
    # 日本語が含まれている場合はPILを使用
    has_japanese = any(
        "\u3040" <= char <= "\u30ff" or "\u4e00" <= char <= "\u9faf" for char in text
    )

    if has_japanese:
        return create_subtitle_image_pil(text, width, height)
    else:
        # 英語の場合は従来のOpenCV方式
        return create_subtitle_image_opencv(text, width, height, font_scale, thickness)


def create_subtitle_image_opencv(
    text: str,
    width: int = 1280,
    height: int = 720,
    font_scale: float = 2.0,
    thickness: int = 3,
) -> np.ndarray:
    """
    OpenCVを使用した字幕画像作成（英語用）
    """
    # 黒背景の画像を作成
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # フォント設定
    font = cv2.FONT_HERSHEY_SIMPLEX

    # テキストサイズを取得
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]

    # 画像の下部中央に配置
    x = (width - text_size[0]) // 2
    y = height - 80  # 下から80ピクセル上

    # 白い縁取り（ストローク）を描画
    stroke_thickness = thickness + 4
    cv2.putText(img, text, (x, y), font, font_scale, (0, 0, 0), stroke_thickness)

    # 白いテキストを描画
    cv2.putText(img, text, (x, y), font, font_scale, (255, 255, 255), thickness)

    return img


def create_test_images():
    """テスト用の字幕画像を複数作成"""

    # テスト用のテキストリスト
    test_texts = [
        "Hello World",  # 英語（基本テスト）
        "こんにちは世界",  # 日本語ひらがな
        "今日は良い天気です",  # 日本語混合
        "VLOG 2024",  # 英数字混合
        "旅行の思い出を",  # 日本語（一般的な字幕）
    ]

    # 出力ディレクトリ
    output_dir = Path(__file__).parent

    for i, text in enumerate(test_texts, 1):
        # 画像を生成
        img = create_subtitle_image(text)

        # ファイル名を生成
        filename = (
            f"test_subtitle_{i:02d}_{text.replace(' ', '_').replace('/', '_')}.png"
        )
        filepath = output_dir / filename

        # 画像を保存
        cv2.imwrite(str(filepath), img)
        print(f"生成完了: {filepath}")


def create_realistic_vlog_frame():
    """よりリアルなVLOG風の字幕フレームを作成"""

    # 1280x720のフレーム
    width, height = 1280, 720

    # グラデーション背景を作成（より現実的な背景）
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # 簡単なグラデーション背景
    for y in range(height):
        intensity = int(50 + (y / height) * 100)
        img[y, :] = [intensity // 3, intensity // 2, intensity]

    # ノイズを追加してリアルさを演出
    noise = np.random.randint(-20, 20, (height, width, 3), dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # 字幕を追加
    text = "今日は渋谷に来ています"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.8
    thickness = 3

    # テキストサイズを取得
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]

    # 下部中央に配置
    x = (width - text_size[0]) // 2
    y = height - 60

    # 黒い縁取り（より太く）
    stroke_thickness = thickness + 6
    cv2.putText(img, text, (x, y), font, font_scale, (0, 0, 0), stroke_thickness)

    # 白いテキスト
    cv2.putText(img, text, (x, y), font, font_scale, (255, 255, 255), thickness)

    # リアルなVLOG風フレームとして保存
    filepath = Path(__file__).parent / "realistic_vlog_frame.png"
    cv2.imwrite(str(filepath), img)
    print(f"リアルなVLOGフレーム生成完了: {filepath}")

    return img


if __name__ == "__main__":
    print("テスト用字幕画像の生成開始...")
    create_test_images()
    create_realistic_vlog_frame()
    print("画像生成完了！")
