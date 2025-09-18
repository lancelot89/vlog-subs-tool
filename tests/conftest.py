"""
テスト設定ファイル
"""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def qapp():
    """QApplicationインスタンスを提供"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sample_subtitles():
    """テスト用字幕データ"""
    from app.core.models import SubtitleItem

    return [
        SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="こんにちは世界"),
        SubtitleItem(index=2, start_ms=4000, end_ms=6000, text="これはテストです"),
        SubtitleItem(index=3, start_ms=7000, end_ms=9000, text="最後の字幕"),
    ]


@pytest.fixture
def test_video_path():
    """テスト用動画ファイルパス"""
    return Path(__file__).parent / "fixtures" / "test_video.mp4"


@pytest.fixture
def temp_dir(tmp_path):
    """一時ディレクトリ"""
    return tmp_path


@pytest.fixture
def sample_csv_content():
    """テスト用CSVデータ"""
    return [
        ["字幕番号", "開始時間", "終了時間", "原文", "翻訳文"],
        ["1", "00:01.000", "00:03.000", "こんにちは世界", "Hello World"],
        ["2", "00:04.000", "00:06.000", "これはテストです", "This is a test"],
        ["3", "00:07.000", "00:09.000", "最後の字幕", "Last subtitle"],
    ]
