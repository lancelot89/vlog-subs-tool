"""
プロジェクト管理機能のテスト
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import SubtitleItem
from app.core.project_manager import ProjectData, ProjectManager, ProjectMetadata


@pytest.fixture
def temp_project_dir(tmp_path):
    """一時プロジェクトディレクトリ"""
    return tmp_path / "projects"


@pytest.fixture
def sample_project_data():
    """サンプルプロジェクトデータ"""
    metadata = ProjectMetadata(
        id="test-project-001",
        name="テストプロジェクト",
        created_at="2024-01-01T00:00:00",
        modified_at="2024-01-01T00:00:00",
        description="テスト用のプロジェクト",
    )

    subtitles = [
        {
            "start_time": 1000,
            "end_time": 3000,
            "text": "こんにちは",
            "confidence": 0.95,
        },
        {"start_time": 4000, "end_time": 6000, "text": "世界", "confidence": 0.92},
    ]

    return ProjectData(
        metadata=metadata,
        video_file_path="/test/video.mp4",
        subtitles=subtitles,
        translations={
            "en": [
                {
                    "start_time": 1000,
                    "end_time": 3000,
                    "text": "Hello",
                    "confidence": 0.95,
                }
            ]
        },
        qc_results=[],
        settings={},
    )


@pytest.fixture
def project_manager():
    """プロジェクトマネージャー"""
    return ProjectManager()


class TestProjectManager:
    """プロジェクトマネージャーのテスト"""

    def test_create_new_project(self, project_manager):
        """新しいプロジェクト作成のテスト"""
        project_data = project_manager.create_new_project("新プロジェクト", "/path/to/video.mp4")

        assert project_data.metadata.name == "新プロジェクト"
        assert project_data.video_file_path == "/path/to/video.mp4"
        assert len(project_data.subtitles) == 0
        assert len(project_data.translations) == 0
        assert project_data.metadata.id != ""  # IDが生成される
        assert project_data.metadata.created_at != ""

    def test_save_project(self, project_manager, sample_project_data, temp_project_dir):
        """プロジェクト保存のテスト"""
        temp_project_dir.mkdir(parents=True, exist_ok=True)
        project_file = temp_project_dir / "test.subproj"

        # プロジェクトを保存
        success = project_manager.save_project(sample_project_data, project_file)

        assert success
        assert project_file.exists()

        # ファイル内容の確認
        with open(project_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)

        assert saved_data["metadata"]["name"] == "テストプロジェクト"
        assert saved_data["video_file_path"] == "/test/video.mp4"
        assert len(saved_data["subtitles"]) == 2
        assert "en" in saved_data["translations"]

    def test_load_project(self, project_manager, sample_project_data, temp_project_dir):
        """プロジェクト読み込みのテスト"""
        temp_project_dir.mkdir(parents=True, exist_ok=True)
        project_file = temp_project_dir / "test.subproj"

        # プロジェクトを保存
        project_manager.save_project(sample_project_data, project_file)

        # 新しいマネージャーで読み込み
        new_manager = ProjectManager()
        loaded_data = new_manager.load_project(project_file)

        assert loaded_data.metadata.name == "テストプロジェクト"
        assert loaded_data.video_file_path == "/test/video.mp4"
        assert len(loaded_data.subtitles) == 2
        assert "en" in loaded_data.translations

        # SubtitleItem への変換確認
        subtitle_items = loaded_data.get_subtitle_items()
        assert len(subtitle_items) == 2
        assert subtitle_items[0].text == "こんにちは"
        assert subtitle_items[0].start_ms == 1000
        assert subtitle_items[0].end_ms == 3000

    def test_load_nonexistent_project(self, project_manager):
        """存在しないプロジェクトファイルの処理テスト"""
        with pytest.raises(FileNotFoundError):
            project_manager.load_project(Path("/nonexistent/file.subproj"))

    def test_load_invalid_format(self, project_manager, temp_project_dir):
        """不正な形式のプロジェクトファイルの処理テスト"""
        temp_project_dir.mkdir(parents=True, exist_ok=True)
        invalid_file = temp_project_dir / "invalid.subproj"

        # 不正なJSONファイルを作成
        invalid_file.write_text("invalid json content", encoding="utf-8")

        with pytest.raises(ValueError, match="プロジェクトファイルの形式が正しくありません"):
            project_manager.load_project(invalid_file)

    def test_update_subtitles(self, project_manager, sample_project_data):
        """字幕データ更新のテスト"""
        project_manager.current_project = sample_project_data

        new_subtitles = [SubtitleItem(index=1, start_ms=2000, end_ms=4000, text="新しい字幕")]

        project_manager.update_subtitles(new_subtitles)

        assert len(project_manager.current_project.subtitles) == 1
        assert project_manager.current_project.subtitles[0]["text"] == "新しい字幕"
        assert project_manager.current_project.subtitles[0]["start_time"] == 2000

    def test_update_translations(self, project_manager, sample_project_data):
        """翻訳データ更新のテスト"""
        project_manager.current_project = sample_project_data

        new_translations = [SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="Bonjour")]

        project_manager.update_translations("fr", new_translations)

        assert "fr" in project_manager.current_project.translations
        assert len(project_manager.current_project.translations["fr"]) == 1
        assert project_manager.current_project.translations["fr"][0]["text"] == "Bonjour"

    def test_update_without_current_project(self, project_manager):
        """現在のプロジェクトがない場合の更新テスト"""
        with pytest.raises(RuntimeError, match="プロジェクトが開かれていません"):
            project_manager.update_subtitles([])

        with pytest.raises(RuntimeError, match="プロジェクトが開かれていません"):
            project_manager.update_translations("en", [])

    def test_validate_project_data(self, project_manager, sample_project_data):
        """プロジェクトデータ妥当性確認のテスト"""
        # 正常なデータの場合
        errors = project_manager.validate_project_data(sample_project_data)
        assert len(errors) == 1  # 動画ファイルが存在しないエラー

        # 不正なデータの場合
        invalid_data = sample_project_data
        invalid_data.metadata.name = ""  # 空の名前
        invalid_data.video_file_path = ""  # 空の動画パス
        invalid_data.subtitles = [
            {
                "start_time": 5000,
                "end_time": 3000,  # 開始時間が終了時間より後
                "text": "",  # 空のテキスト
                "confidence": 0.9,
            }
        ]

        errors = project_manager.validate_project_data(invalid_data)
        assert len(errors) >= 3  # 複数のエラーが検出される

    def test_backup_creation(self, project_manager, sample_project_data, temp_project_dir):
        """バックアップファイル作成のテスト"""
        temp_project_dir.mkdir(parents=True, exist_ok=True)
        project_file = temp_project_dir / "test.subproj"

        # 最初の保存
        project_manager.save_project(sample_project_data, project_file)

        # 2回目の保存（バックアップが作成される）
        sample_project_data.metadata.name = "更新されたプロジェクト"
        project_manager.save_project(sample_project_data, project_file)

        # バックアップファイルの存在確認
        backup_file = project_file.with_suffix(".subproj.backup")
        assert backup_file.exists()

        # バックアップの内容確認
        with open(backup_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
        assert backup_data["metadata"]["name"] == "テストプロジェクト"  # 古い名前

    def test_save_as_project(self, project_manager, sample_project_data, temp_project_dir):
        """名前を付けて保存のテスト"""
        temp_project_dir.mkdir(parents=True, exist_ok=True)
        original_file = temp_project_dir / "original.subproj"
        new_file = temp_project_dir / "new.subproj"

        # 元のファイルで保存
        project_manager.save_project(sample_project_data, original_file)

        # 別名で保存
        success = project_manager.save_as_project(sample_project_data, new_file)

        assert success
        assert new_file.exists()
        assert original_file.exists()  # 元のファイルも残る

        # 現在のファイルパスが更新されることを確認
        assert project_manager.get_current_file_path() == new_file

    def test_close_project(self, project_manager, sample_project_data):
        """プロジェクト終了のテスト"""
        project_manager.current_project = sample_project_data
        project_manager.current_file_path = Path("/test/path.subproj")

        project_manager.close_project()

        assert project_manager.current_project is None
        assert project_manager.current_file_path is None

    def test_is_project_modified(self, project_manager, sample_project_data):
        """プロジェクト変更状態の確認テスト"""
        # プロジェクトがない場合
        assert not project_manager.is_project_modified()

        # 新しいプロジェクト（未保存）
        project_manager.current_project = sample_project_data
        project_manager.current_file_path = None
        assert project_manager.is_project_modified()

        # 保存済みプロジェクト
        project_manager.current_file_path = Path("/test/saved.subproj")
        # TODO: より詳細な変更検出の実装後にテストを追加
        assert project_manager.is_project_modified()

    def test_export_legacy_format(self, project_manager, sample_project_data, temp_project_dir):
        """レガシー形式でのエクスポートテスト"""
        temp_project_dir.mkdir(parents=True, exist_ok=True)
        export_file = temp_project_dir / "legacy.json"

        project_manager.current_project = sample_project_data

        success = project_manager.export_to_legacy_format(export_file)

        assert success
        assert export_file.exists()

        # レガシー形式の確認
        with open(export_file, "r", encoding="utf-8") as f:
            legacy_data = json.load(f)

        assert "video_path" in legacy_data
        assert "subtitles" in legacy_data
        # メタデータや翻訳データは含まれない
        assert "metadata" not in legacy_data
        assert "translations" not in legacy_data

    def test_relative_path_resolution(self, project_manager, temp_project_dir):
        """相対パスの解決テスト"""
        temp_project_dir.mkdir(parents=True, exist_ok=True)
        project_file = temp_project_dir / "test.subproj"
        video_dir = temp_project_dir / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        video_file = video_dir / "test_video.mp4"
        video_file.touch()  # 空のファイルを作成

        # 相対パスでプロジェクトデータを作成
        project_data = ProjectData(
            metadata=ProjectMetadata(
                id="test-relative",
                name="相対パステスト",
                created_at=datetime.now().isoformat(),
                modified_at=datetime.now().isoformat(),
            ),
            video_file_path="videos/test_video.mp4",  # 相対パス
            subtitles=[],
            translations={},
            qc_results=[],
            settings={},
        )

        # プロジェクトを保存
        project_manager.save_project(project_data, project_file)

        # 新しいマネージャーで読み込み
        new_manager = ProjectManager()
        loaded_data = new_manager.load_project(project_file)

        # 絶対パスに変換されることを確認
        assert Path(loaded_data.video_file_path).is_absolute()
        assert loaded_data.video_file_path.endswith("test_video.mp4")


class TestProjectManagerSingleton:
    """プロジェクトマネージャーシングルトンのテスト"""

    def test_singleton_pattern(self):
        """シングルトンパターンのテスト"""
        from app.core.project_manager import get_project_manager

        manager1 = get_project_manager()
        manager2 = get_project_manager()

        # 同じインスタンスが返されることを確認
        assert manager1 is manager2

    def test_singleton_reset(self):
        """シングルトンのリセットテスト"""
        import app.core.project_manager
        from app.core.project_manager import get_project_manager

        # 最初のインスタンス取得
        manager1 = get_project_manager()

        # シングルトンをリセット
        app.core.project_manager._project_manager_instance = None

        # 新しいインスタンス取得
        manager2 = get_project_manager()

        # 異なるインスタンスが作成されることを確認
        assert manager1 is not manager2


class TestProjectData:
    """プロジェクトデータのテスト"""

    def test_get_subtitle_items(self, sample_project_data):
        """SubtitleItem変換のテスト"""
        subtitle_items = sample_project_data.get_subtitle_items()

        assert len(subtitle_items) == 2
        assert isinstance(subtitle_items[0], SubtitleItem)
        assert subtitle_items[0].text == "こんにちは"
        assert subtitle_items[0].start_ms == 1000

    def test_get_subtitle_items_with_invalid_data(self):
        """不正な字幕データでのSubtitleItem変換テスト"""
        project_data = ProjectData(
            metadata=ProjectMetadata(
                id="test",
                name="test",
                created_at="2024-01-01T00:00:00",
                modified_at="2024-01-01T00:00:00",
            ),
            video_file_path="",
            subtitles=[
                {
                    "start_time": 1000,
                    "end_time": 3000,
                    "text": "正常データ",
                    "confidence": 0.9,
                },
                {"invalid": "data"},  # 不正なデータ
                {"start_time": None, "end_time": 3000, "text": "null時間"},  # null時間
            ],
            translations={},
            qc_results=[],
            settings={},
        )

        subtitle_items = project_data.get_subtitle_items()

        # 正常なデータのみが変換される
        assert len(subtitle_items) == 1
        assert subtitle_items[0].text == "正常データ"

    def test_get_translated_subtitles(self, sample_project_data):
        """翻訳字幕取得のテスト"""
        # 存在する言語
        en_subtitles = sample_project_data.get_translated_subtitles("en")
        assert en_subtitles is not None
        assert len(en_subtitles) == 1
        assert en_subtitles[0].text == "Hello"

        # 存在しない言語
        fr_subtitles = sample_project_data.get_translated_subtitles("fr")
        assert fr_subtitles is None
