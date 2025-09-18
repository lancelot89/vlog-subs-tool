"""
設定管理機能のテスト
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.core.settings_manager import (
    SettingsManager, AppSettings, ExtractionSettings,
    FormattingSettings, OutputSettings, UISettings
)


@pytest.fixture
def temp_settings_dir(tmp_path):
    """一時設定ディレクトリ"""
    return tmp_path / "vlog-subs-tool"


@pytest.fixture
def mock_settings_manager(temp_settings_dir):
    """モック化された設定マネージャー"""
    with patch.object(SettingsManager, '_get_settings_path') as mock_path:
        mock_path.return_value = temp_settings_dir / "settings.json"
        temp_settings_dir.mkdir(parents=True, exist_ok=True)
        return SettingsManager()


class TestSettingsManager:
    """設定マネージャーのテスト"""

    def test_create_default_settings(self, mock_settings_manager):
        """デフォルト設定の作成テスト"""
        settings = mock_settings_manager._create_default_settings()

        assert isinstance(settings, AppSettings)
        assert settings.version == "1.0.0"
        assert settings.extraction.fps_sample == 3.0
        assert settings.formatting.max_chars == 42
        assert settings.output.encoding == "UTF-8"
        assert settings.ui.theme == "システム"

    def test_load_settings_no_file(self, mock_settings_manager):
        """設定ファイルが存在しない場合のテスト"""
        settings = mock_settings_manager.load_settings()

        assert isinstance(settings, AppSettings)
        assert settings.extraction.fps_sample == 3.0  # デフォルト値

    def test_save_and_load_settings(self, mock_settings_manager):
        """設定の保存と読み込みテスト"""
        # カスタム設定を作成
        custom_settings = AppSettings(
            extraction=ExtractionSettings(
                fps_sample=5.0,
                ocr_confidence=0.9
            ),
            formatting=FormattingSettings(
                max_chars=50,
                max_lines=3
            ),
            output=OutputSettings(
                encoding="UTF-8 BOM",
                srt_bom=True
            ),
            ui=UISettings(
                theme="ダーク",
                font_size=12
            )
        )

        # 保存
        assert mock_settings_manager.save_settings(custom_settings)

        # 新しいマネージャーインスタンスで読み込み
        new_manager = SettingsManager()
        new_manager._settings_path = mock_settings_manager._settings_path
        loaded_settings = new_manager.load_settings()

        # 設定値の確認
        assert loaded_settings.extraction.fps_sample == 5.0
        assert loaded_settings.extraction.ocr_confidence == 0.9
        assert loaded_settings.formatting.max_chars == 50
        assert loaded_settings.formatting.max_lines == 3
        assert loaded_settings.output.encoding == "UTF-8 BOM"
        assert loaded_settings.output.srt_bom is True
        assert loaded_settings.ui.theme == "ダーク"
        assert loaded_settings.ui.font_size == 12

    def test_corrupted_settings_file(self, mock_settings_manager, temp_settings_dir):
        """壊れた設定ファイルの処理テスト"""
        # 不正なJSONファイルを作成
        settings_path = temp_settings_dir / "settings.json"
        settings_path.write_text("invalid json content", encoding='utf-8')

        # デフォルト設定が読み込まれることを確認
        settings = mock_settings_manager.load_settings()
        assert isinstance(settings, AppSettings)
        assert settings.extraction.fps_sample == 3.0  # デフォルト値

    def test_partial_settings_file(self, mock_settings_manager, temp_settings_dir):
        """部分的な設定ファイルの処理テスト"""
        # 一部の設定のみを含むファイルを作成
        partial_settings = {
            "version": "1.0.0",
            "extraction": {
                "fps_sample": 4.0
            },
            "ui": {
                "theme": "ライト"
            }
        }

        settings_path = temp_settings_dir / "settings.json"
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(partial_settings, f)

        # 読み込み
        settings = mock_settings_manager.load_settings()

        # 指定された設定は適用され、その他はデフォルト値
        assert settings.extraction.fps_sample == 4.0
        assert settings.ui.theme == "ライト"
        assert settings.formatting.max_chars == 42  # デフォルト値
        assert settings.output.encoding == "UTF-8"  # デフォルト値

    def test_settings_validation(self, mock_settings_manager):
        """設定の妥当性検証テスト"""
        # 不正な設定値
        invalid_settings = AppSettings(
            extraction=ExtractionSettings(
                fps_sample=15.0,  # 上限を超える
                ocr_confidence=1.5  # 範囲外
            ),
            formatting=FormattingSettings(
                max_chars=5,  # 下限を下回る
                max_lines=15  # 上限を超える
            ),
            output=OutputSettings(
                output_folder="/nonexistent/path"
            ),
            ui=UISettings()
        )

        errors = mock_settings_manager.validate_settings(invalid_settings)

        # エラーが検出されることを確認
        assert len(errors) > 0
        assert any("サンプリングFPS" in error for error in errors)
        assert any("OCR信頼度" in error for error in errors)
        assert any("最大文字数" in error for error in errors)
        assert any("最大行数" in error for error in errors)

    def test_reset_to_defaults(self, mock_settings_manager):
        """デフォルト設定へのリセットテスト"""
        # カスタム設定を保存
        custom_settings = AppSettings(
            extraction=ExtractionSettings(fps_sample=7.0),
            formatting=FormattingSettings(max_chars=60),
            output=OutputSettings(),
            ui=UISettings()
        )
        mock_settings_manager.save_settings(custom_settings)

        # デフォルトにリセット
        reset_settings = mock_settings_manager.reset_to_defaults()

        # デフォルト値が復元されることを確認
        assert reset_settings.extraction.fps_sample == 3.0
        assert reset_settings.formatting.max_chars == 42

    def test_recent_files_management(self, mock_settings_manager):
        """最近使用したファイルの管理テスト"""
        # ファイルを追加
        mock_settings_manager.add_recent_file("/path/to/file1.subproj")
        mock_settings_manager.add_recent_file("/path/to/file2.subproj")
        mock_settings_manager.add_recent_file("/path/to/file3.subproj")

        # 最近使用したファイルを取得
        recent_files = mock_settings_manager.load_recent_files()

        assert len(recent_files) == 3
        assert recent_files[0] == "/path/to/file3.subproj"  # 最新が先頭
        assert recent_files[1] == "/path/to/file2.subproj"
        assert recent_files[2] == "/path/to/file1.subproj"

        # 重複ファイルの追加
        mock_settings_manager.add_recent_file("/path/to/file1.subproj")
        recent_files = mock_settings_manager.load_recent_files()

        assert len(recent_files) == 3  # 重複は除去
        assert recent_files[0] == "/path/to/file1.subproj"  # 先頭に移動

    def test_recent_files_limit(self, mock_settings_manager):
        """最近使用したファイルの上限テスト"""
        # デフォルト上限（10件）を超える数のファイルを追加
        for i in range(15):
            mock_settings_manager.add_recent_file(f"/path/to/file{i}.subproj")

        recent_files = mock_settings_manager.load_recent_files()

        # 上限数以内に制限されることを確認
        assert len(recent_files) <= 10
        assert recent_files[0] == "/path/to/file14.subproj"  # 最新が先頭

    def test_backup_creation(self, mock_settings_manager, temp_settings_dir):
        """バックアップファイルの作成テスト"""
        # 最初の設定を保存
        settings1 = AppSettings(
            extraction=ExtractionSettings(fps_sample=3.0),
            formatting=FormattingSettings(),
            output=OutputSettings(),
            ui=UISettings()
        )
        mock_settings_manager.save_settings(settings1)

        # 2回目の設定を保存（バックアップが作成される）
        settings2 = AppSettings(
            extraction=ExtractionSettings(fps_sample=5.0),
            formatting=FormattingSettings(),
            output=OutputSettings(),
            ui=UISettings()
        )
        mock_settings_manager.save_settings(settings2)

        # バックアップファイルが作成されることを確認
        backup_path = temp_settings_dir / "settings.json.backup"
        assert backup_path.exists()

        # バックアップの内容確認
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        assert backup_data['extraction']['fps_sample'] == 3.0  # 古い設定

    def test_cross_platform_paths(self, mock_settings_manager):
        """クロスプラットフォームでのパス処理テスト"""
        # 各プラットフォーム用のパスをテスト
        with patch('platform.system', return_value='Windows'):
            with patch.dict('os.environ', {'APPDATA': str(Path.home() / "AppData" / "Roaming")}):
                windows_manager = SettingsManager()
                windows_path = windows_manager._get_settings_path()
                assert "vlog-subs-tool" in str(windows_path)

        with patch('platform.system', return_value='Darwin'):  # macOS
            macos_manager = SettingsManager()
            macos_path = macos_manager._get_settings_path()
            assert "Application Support" in str(macos_path)

        with patch('platform.system', return_value='Linux'):
            linux_manager = SettingsManager()
            linux_path = linux_manager._get_settings_path()
            assert ".config" in str(linux_path)


class TestSettingsManagerSingleton:
    """設定マネージャーシングルトンのテスト"""

    def test_singleton_pattern(self):
        """シングルトンパターンのテスト"""
        from app.core.settings_manager import get_settings_manager

        manager1 = get_settings_manager()
        manager2 = get_settings_manager()

        # 同じインスタンスが返されることを確認
        assert manager1 is manager2

    def test_singleton_reset(self):
        """シングルトンのリセットテスト"""
        from app.core.settings_manager import get_settings_manager
        import app.core.settings_manager

        # 最初のインスタンス取得
        manager1 = get_settings_manager()

        # シングルトンをリセット
        app.core.settings_manager._settings_manager_instance = None

        # 新しいインスタンス取得
        manager2 = get_settings_manager()

        # 異なるインスタンスが作成されることを確認
        assert manager1 is not manager2