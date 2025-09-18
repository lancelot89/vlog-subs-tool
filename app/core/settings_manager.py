"""
設定ファイル管理クラス
ユーザー設定の永続化を行う
"""

import json
import logging
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ExtractionSettings:
    """抽出設定"""

    fps_sample: float = 3.0
    resolution: str = "オリジナル"
    roi_mode: str = "bottom"  # "auto", "bottom", "manual"
    bottom_ratio: float = 0.3
    ocr_engine: str = "paddleocr"  # "paddleocr", "tesseract"
    ocr_confidence: float = 0.8


@dataclass
class FormattingSettings:
    """整形設定"""

    max_chars: int = 42
    max_lines: int = 2
    min_duration: float = 1.2
    similarity_threshold: float = 0.9
    merge_gap: float = 0.5
    normalize_punctuation: bool = True
    normalize_whitespace: bool = True
    remove_duplicate: bool = False


@dataclass
class OutputSettings:
    """出力設定"""

    output_folder: str = ""
    filename_pattern: str = "{basename}.{lang}.srt"
    encoding: str = "UTF-8"
    srt_bom: bool = False
    srt_crlf: bool = False
    default_languages: str = "日本語 + 英語"
    auto_translate: bool = False
    overwrite_mode: str = "ask"  # "ask", "auto", "backup"


@dataclass
class UISettings:
    """UI設定"""

    theme: str = "システム"
    font_size: int = 9
    auto_save: bool = False
    auto_save_interval: int = 5
    recent_files_count: int = 10


@dataclass
class AppSettings:
    """アプリケーション設定"""

    extraction: ExtractionSettings
    formatting: FormattingSettings
    output: OutputSettings
    ui: UISettings
    version: str = "1.0.0"

    def __post_init__(self):
        """設定の初期化後処理"""
        # デフォルトの出力フォルダ設定
        if not self.output.output_folder:
            self.output.output_folder = str(self.get_default_output_directory())

    def get_default_output_directory(self) -> Path:
        """デフォルト出力ディレクトリを取得"""
        home = Path.home()

        # プラットフォーム別のデフォルトフォルダ
        if platform.system() == "Windows":
            documents = home / "Documents"
            if documents.exists():
                return documents / "VLogSubtitles"
        elif platform.system() == "Darwin":  # macOS
            documents = home / "Documents"
            if documents.exists():
                return documents / "VLogSubtitles"
        else:  # Linux
            documents = home / "Documents"
            if documents.exists():
                return documents / "VLogSubtitles"

        # フォールバック: ホームディレクトリ
        return home / "VLogSubtitles"


class SettingsManager:
    """設定管理クラス"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._settings_path = self._get_settings_path()
        self._settings: Optional[AppSettings] = None

    def _get_settings_path(self) -> Path:
        """設定ファイルのパスを取得"""
        # プラットフォーム別の設定フォルダ
        if platform.system() == "Windows":
            # Windows: %APPDATA%
            config_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif platform.system() == "Darwin":  # macOS
            # macOS: ~/Library/Application Support
            config_dir = Path.home() / "Library" / "Application Support"
        else:  # Linux
            # Linux: ~/.config
            config_dir = Path.home() / ".config"

        app_config_dir = config_dir / "vlog-subs-tool"
        app_config_dir.mkdir(parents=True, exist_ok=True)

        return app_config_dir / "settings.json"

    def load_settings(self) -> AppSettings:
        """設定を読み込み"""
        if self._settings is not None:
            return self._settings

        try:
            if self._settings_path.exists():
                self.logger.info(f"設定ファイル読み込み: {self._settings_path}")
                with open(self._settings_path, "r", encoding="utf-8") as f:
                    settings_dict = json.load(f)

                # バージョン確認
                file_version = settings_dict.get("version", "1.0.0")
                if file_version != "1.0.0":
                    self.logger.warning(f"設定ファイルのバージョンが異なります: {file_version}")

                # 設定オブジェクトに変換
                self._settings = self._dict_to_settings(settings_dict)
                self.logger.info("設定読み込み完了")
            else:
                self.logger.info("設定ファイルが見つかりません。デフォルト設定を使用")
                self._settings = self._create_default_settings()

        except Exception as e:
            self.logger.error(f"設定読み込みエラー: {e}")
            self.logger.info("デフォルト設定を使用")
            self._settings = self._create_default_settings()

        return self._settings

    def save_settings(self, settings: AppSettings) -> bool:
        """設定を保存"""
        try:
            self._settings = settings
            settings_dict = self._settings_to_dict(settings)

            # バックアップを作成
            self._create_backup()

            self.logger.info(f"設定ファイル保存: {self._settings_path}")
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(settings_dict, f, indent=2, ensure_ascii=False)

            self.logger.info("設定保存完了")
            return True

        except Exception as e:
            self.logger.error(f"設定保存エラー: {e}")
            return False

    def _create_default_settings(self) -> AppSettings:
        """デフォルト設定を作成"""
        return AppSettings(
            extraction=ExtractionSettings(),
            formatting=FormattingSettings(),
            output=OutputSettings(),
            ui=UISettings(),
        )

    def _settings_to_dict(self, settings: AppSettings) -> Dict[str, Any]:
        """設定オブジェクトを辞書に変換"""
        return {
            "version": settings.version,
            "extraction": asdict(settings.extraction),
            "formatting": asdict(settings.formatting),
            "output": asdict(settings.output),
            "ui": asdict(settings.ui),
        }

    def _dict_to_settings(self, settings_dict: Dict[str, Any]) -> AppSettings:
        """辞書を設定オブジェクトに変換"""
        try:
            # デフォルト設定を作成
            default_settings = self._create_default_settings()

            # 各セクションを更新
            if "extraction" in settings_dict:
                extraction_dict = settings_dict["extraction"]
                default_settings.extraction = ExtractionSettings(
                    **{
                        k: v
                        for k, v in extraction_dict.items()
                        if k in ExtractionSettings.__dataclass_fields__
                    }
                )

            if "formatting" in settings_dict:
                formatting_dict = settings_dict["formatting"]
                default_settings.formatting = FormattingSettings(
                    **{
                        k: v
                        for k, v in formatting_dict.items()
                        if k in FormattingSettings.__dataclass_fields__
                    }
                )

            if "output" in settings_dict:
                output_dict = settings_dict["output"]
                default_settings.output = OutputSettings(
                    **{
                        k: v
                        for k, v in output_dict.items()
                        if k in OutputSettings.__dataclass_fields__
                    }
                )

            if "ui" in settings_dict:
                ui_dict = settings_dict["ui"]
                default_settings.ui = UISettings(
                    **{k: v for k, v in ui_dict.items() if k in UISettings.__dataclass_fields__}
                )

            if "version" in settings_dict:
                default_settings.version = settings_dict["version"]

            return default_settings

        except Exception as e:
            self.logger.error(f"設定変換エラー: {e}")
            return self._create_default_settings()

    def _create_backup(self):
        """設定ファイルのバックアップを作成"""
        if self._settings_path.exists():
            backup_path = self._settings_path.with_suffix(".json.backup")
            try:
                import shutil

                shutil.copy2(self._settings_path, backup_path)
                self.logger.debug(f"バックアップ作成: {backup_path}")
            except Exception as e:
                self.logger.warning(f"バックアップ作成失敗: {e}")

    def reset_to_defaults(self) -> AppSettings:
        """設定をデフォルトに戻す"""
        self.logger.info("設定をデフォルトに戻します")
        default_settings = self._create_default_settings()
        if self.save_settings(default_settings):
            return default_settings
        return self.load_settings()

    def get_recent_files_path(self) -> Path:
        """最近使用したファイルのパスを取得"""
        return self._settings_path.parent / "recent_files.json"

    def load_recent_files(self) -> List[str]:
        """最近使用したファイルを読み込み"""
        recent_files_path = self.get_recent_files_path()
        try:
            if recent_files_path.exists():
                with open(recent_files_path, "r", encoding="utf-8") as f:
                    recent_files = json.load(f)
                return recent_files.get("files", [])
        except Exception as e:
            self.logger.error(f"最近使用したファイル読み込みエラー: {e}")

        return []

    def save_recent_files(self, files: List[str]):
        """最近使用したファイルを保存"""
        recent_files_path = self.get_recent_files_path()
        try:
            recent_data = {
                "files": files,
                "last_updated": str(Path(__file__).stat().st_mtime),
            }
            with open(recent_files_path, "w", encoding="utf-8") as f:
                json.dump(recent_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"最近使用したファイル保存エラー: {e}")

    def add_recent_file(self, file_path: str):
        """最近使用したファイルに追加"""
        settings = self.load_settings()
        max_files = settings.ui.recent_files_count

        recent_files = self.load_recent_files()

        # 既存のエントリを削除
        if file_path in recent_files:
            recent_files.remove(file_path)

        # 先頭に追加
        recent_files.insert(0, file_path)

        # 上限を超えた分を削除
        if len(recent_files) > max_files:
            recent_files = recent_files[:max_files]

        self.save_recent_files(recent_files)

    def validate_settings(self, settings: AppSettings) -> List[str]:
        """設定の妥当性を確認"""
        errors = []

        # 抽出設定の検証
        if settings.extraction.fps_sample < 0.5 or settings.extraction.fps_sample > 10.0:
            errors.append("サンプリングFPSは0.5から10.0の間で設定してください")

        if settings.extraction.ocr_confidence < 0.0 or settings.extraction.ocr_confidence > 1.0:
            errors.append("OCR信頼度は0から1の間で設定してください")

        # 整形設定の検証
        if settings.formatting.max_chars < 10 or settings.formatting.max_chars > 200:
            errors.append("最大文字数は10から200の間で設定してください")

        if settings.formatting.max_lines < 1 or settings.formatting.max_lines > 10:
            errors.append("最大行数は1から10の間で設定してください")

        # 出力フォルダの検証
        if settings.output.output_folder:
            output_path = Path(settings.output.output_folder)
            if not output_path.parent.exists():
                errors.append(f"出力フォルダの親ディレクトリが存在しません: {output_path.parent}")

        return errors

    def migrate_settings(self, old_version: str, new_version: str) -> bool:
        """設定ファイルのマイグレーション"""
        self.logger.info(f"設定ファイルをマイグレーション: {old_version} → {new_version}")

        # 現在は v1.0.0 のみサポート
        if old_version == new_version:
            return True

        # 将来的なバージョンアップ時のマイグレーション処理をここに実装
        self.logger.warning(f"サポートされていないバージョン: {old_version}")
        return False


# シングルトンインスタンス
_settings_manager_instance = None


def get_settings_manager() -> SettingsManager:
    """設定マネージャーのシングルトンインスタンスを取得"""
    global _settings_manager_instance
    if _settings_manager_instance is None:
        _settings_manager_instance = SettingsManager()
    return _settings_manager_instance
