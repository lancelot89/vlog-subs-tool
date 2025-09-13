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
        assert item.duration_ms == 2500
    
    def test_to_dict(self):
        """to_dict()メソッドのテスト"""
        item = SubtitleItem(1, 1000, 3000, "テスト")
        expected = {
            "index": 1,
            "start_ms": 1000,
            "end_ms": 3000,
            "text": "テスト"
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
        
        assert settings.ocr_engine == "paddleocr"
        assert settings.roi_y_start == 0.8
        assert settings.roi_y_end == 1.0
        assert settings.similarity_threshold == 0.8
        assert settings.min_duration_ms == 500
        assert settings.max_line_length == 42
        assert settings.max_lines == 2
    
    def test_to_dict_from_dict(self):
        """辞書変換のテスト"""
        settings = ProjectSettings(
            ocr_engine="tesseract",
            roi_y_start=0.7,
            similarity_threshold=0.9
        )
        
        data = settings.to_dict()
        new_settings = ProjectSettings.from_dict(data)
        
        assert new_settings.ocr_engine == "tesseract"
        assert new_settings.roi_y_start == 0.7
        assert new_settings.similarity_threshold == 0.9


class TestProject:
    """Projectクラスのテスト"""
    
    def test_init(self, sample_subtitles):
        """初期化テスト"""
        project = Project(
            video_path="/path/to/video.mp4",
            subtitles=sample_subtitles
        )
        
        assert project.video_path == Path("/path/to/video.mp4")
        assert len(project.subtitles) == 3
        assert isinstance(project.settings, ProjectSettings)
    
    def test_save_load(self, sample_subtitles, temp_dir):
        """保存・読み込みテスト"""
        project_path = temp_dir / "test.subproj"
        
        # プロジェクト作成・保存
        project = Project(
            video_path="/path/to/video.mp4",
            subtitles=sample_subtitles
        )
        project.save(project_path)
        
        # 読み込み
        loaded_project = Project.load(project_path)
        
        assert loaded_project.video_path == project.video_path
        assert len(loaded_project.subtitles) == len(project.subtitles)
        assert loaded_project.subtitles[0].text == project.subtitles[0].text
    
    def test_to_dict_from_dict(self, sample_subtitles):
        """辞書変換のテスト"""
        project = Project(
            video_path="/path/to/video.mp4",
            subtitles=sample_subtitles
        )
        
        data = project.to_dict()
        new_project = Project.from_dict(data)
        
        assert new_project.video_path == project.video_path
        assert len(new_project.subtitles) == len(project.subtitles)


class TestQCResult:
    """QCResultクラスのテスト"""
    
    def test_init(self):
        """初期化テスト"""
        result = QCResult(
            rule_name="test_rule",
            severity="ERROR",
            message="テストエラー",
            subtitle_index=1
        )
        
        assert result.rule_name == "test_rule"
        assert result.severity == "ERROR"
        assert result.message == "テストエラー"
        assert result.subtitle_index == 1
    
    def test_to_dict(self):
        """辞書変換のテスト"""
        result = QCResult("test", "WARNING", "警告", 2)
        expected = {
            "rule_name": "test",
            "severity": "WARNING", 
            "message": "警告",
            "subtitle_index": 2
        }
        assert result.to_dict() == expected
    
    def test_str(self):
        """文字列表現のテスト"""
        result = QCResult("test", "ERROR", "エラーメッセージ", 1)
        expected = "[ERROR] test: エラーメッセージ (字幕#1)"
        assert str(result) == expected