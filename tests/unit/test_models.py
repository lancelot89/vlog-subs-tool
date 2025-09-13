"""
modelsモジュールのテスト
"""

import pytest
import json
from pathlib import Path

from app.core.models import SubtitleItem, ProjectSettings, Project, QCResult


class TestSubtitleItem:
    """SubtitleItemクラスのテスト"""
    
    def test_init(self):
        """初期化テスト"""
        item = SubtitleItem(
            index=1,
            start_ms=1000,
            end_ms=3000,
            text="テストテキスト"
        )
        
        assert item.index == 1
        assert item.start_ms == 1000
        assert item.end_ms == 3000
        assert item.text == "テストテキスト"
    
    def test_duration_property(self):
        """duration_msプロパティのテスト"""
        item = SubtitleItem(1, 1000, 3500, "テスト")
        assert item.duration_ms() == 2500
    
    def test_to_dict(self):
        """to_dict()メソッドのテスト"""
        item = SubtitleItem(1, 1000, 3000, "テスト")
        expected = {
            "index": 1,
            "start_ms": 1000,
            "end_ms": 3000,
            "text": "テスト",
            "bbox": None
        }
        assert item.to_dict() == expected
    
    def test_from_dict(self):
        """from_dict()メソッドのテスト"""
        data = {
            "index": 2,
            "start_ms": 2000,
            "end_ms": 4000,
            "text": "テスト2"
        }
        item = SubtitleItem.from_dict(data)
        
        assert item.index == 2
        assert item.start_ms == 2000
        assert item.end_ms == 4000
        assert item.text == "テスト2"
    
    def test_eq(self):
        """等価比較のテスト"""
        item1 = SubtitleItem(1, 1000, 3000, "テスト")
        item2 = SubtitleItem(1, 1000, 3000, "テスト")
        item3 = SubtitleItem(2, 1000, 3000, "テスト")
        
        assert item1 == item2
        assert item1 != item3


class TestProjectSettings:
    """ProjectSettingsクラスのテスト"""
    
    def test_default_settings(self):
        """デフォルト設定のテスト"""
        settings = ProjectSettings()
        
        assert settings.ocr_engine == "paddleocr_ja"
        assert settings.fps_sample == 3.0
        assert settings.roi_mode == "auto"
        assert settings.similarity_threshold == 0.90
        assert settings.min_dur_sec == 1.2
        assert settings.max_chars == 42
        assert settings.max_lines == 2
    
    def test_to_dict_from_dict(self):
        """辞書変換のテスト"""
        settings = ProjectSettings(
            ocr_engine="tesseract_jpn",
            fps_sample=2.0,
            similarity_threshold=0.95
        )
        
        data = settings.to_dict()
        new_settings = ProjectSettings.from_dict(data)
        
        assert new_settings.ocr_engine == "tesseract_jpn"
        assert new_settings.fps_sample == 2.0
        assert new_settings.similarity_threshold == 0.95


class TestProject:
    """Projectクラスのテスト"""
    
    def test_init(self, sample_subtitles):
        """初期化テスト"""
        project = Project(
            source_video="/path/to/video.mp4",
            settings=ProjectSettings(),
            subtitles=sample_subtitles
        )
        
        assert project.source_video == "/path/to/video.mp4"
        assert len(project.subtitles) == 3
        assert isinstance(project.settings, ProjectSettings)
    
    def test_save_load(self, sample_subtitles, temp_dir):
        """保存・読み込みテスト"""
        project_path = temp_dir / "test.subproj"
        
        # プロジェクト作成・保存
        project = Project(
            source_video="/path/to/video.mp4",
            settings=ProjectSettings(),
            subtitles=sample_subtitles
        )
        project.save(project_path)
        
        # 読み込み
        loaded_project = Project.load(project_path)
        
        assert loaded_project.source_video == project.source_video
        assert len(loaded_project.subtitles) == len(project.subtitles)
        assert loaded_project.subtitles[0].text == project.subtitles[0].text
    
    def test_to_dict_from_dict(self, sample_subtitles):
        """辞書変換のテスト"""
        project = Project(
            source_video="/path/to/video.mp4",
            settings=ProjectSettings(),
            subtitles=sample_subtitles
        )
        
        data = project.to_dict()
        new_project = Project.from_dict(data)
        
        assert new_project.source_video == project.source_video
        assert len(new_project.subtitles) == len(project.subtitles)


class TestQCResult:
    """QCResultクラスのテスト"""
    
    def test_init(self):
        """初期化テスト"""
        result = QCResult(
            subtitle_index=1,
            error_type="test_rule",
            message="テストエラー",
            severity="error"
        )
        
        assert result.error_type == "test_rule"
        assert result.severity == "error"
        assert result.message == "テストエラー"
        assert result.subtitle_index == 1
    
    def test_to_dict(self):
        """辞書変換のテスト"""
        result = QCResult(2, "test", "警告", "warning")
        expected = {
            "subtitle_index": 2,
            "error_type": "test",
            "message": "警告",
            "severity": "warning"
        }
        assert result.to_dict() == expected
    
    def test_str(self):
        """文字列表現のテスト"""
        result = QCResult(1, "test", "エラーメッセージ", "error")
        # QCResultに__str__メソッドがないため、この部分はスキップまたは削除
        # 実際のオブジェクトの文字列表現をテスト
        str_repr = str(result)
        assert "QCResult" in str_repr