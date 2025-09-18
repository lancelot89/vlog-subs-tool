"""
プロジェクトファイル管理クラス
.subproj ファイルの読み書きを行う
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.models import Project, ProjectSettings, SubtitleItem


@dataclass
class ProjectMetadata:
    """プロジェクトメタデータ"""

    id: str
    name: str
    created_at: str
    modified_at: str
    version: str = "1.0.0"
    description: str = ""

    def __post_init__(self):
        """メタデータの初期化後処理"""
        if not self.id:
            self.id = str(uuid.uuid4())


@dataclass
class ProjectData:
    """プロジェクトデータ"""

    metadata: ProjectMetadata
    video_file_path: str
    subtitles: List[Dict[str, Any]]
    translations: Dict[str, List[Dict[str, Any]]]
    qc_results: List[Dict[str, Any]]
    settings: Dict[str, Any]

    def get_subtitle_items(self) -> List[SubtitleItem]:
        """字幕アイテムのリストを取得"""
        subtitle_items = []
        for i, subtitle_data in enumerate(self.subtitles):
            try:
                item = SubtitleItem(
                    index=i + 1,
                    start_ms=subtitle_data["start_time"],
                    end_ms=subtitle_data["end_time"],
                    text=subtitle_data["text"],
                )
                subtitle_items.append(item)
            except (KeyError, TypeError) as e:
                logging.warning(
                    f"字幕データの読み込みに失敗: {subtitle_data}, エラー: {e}"
                )
        return subtitle_items

    def get_translated_subtitles(self, language: str) -> Optional[List[SubtitleItem]]:
        """指定言語の翻訳字幕を取得"""
        if language not in self.translations:
            return None

        translated_items = []
        for i, trans_data in enumerate(self.translations[language]):
            try:
                item = SubtitleItem(
                    index=i + 1,
                    start_ms=trans_data["start_time"],
                    end_ms=trans_data["end_time"],
                    text=trans_data["text"],
                )
                translated_items.append(item)
            except (KeyError, TypeError) as e:
                logging.warning(
                    f"翻訳データの読み込みに失敗: {trans_data}, エラー: {e}"
                )
        return translated_items


class ProjectManager:
    """プロジェクトファイル管理クラス"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.current_project: Optional[ProjectData] = None
        self.current_file_path: Optional[Path] = None

    def create_new_project(self, name: str, video_path: str) -> ProjectData:
        """新しいプロジェクトを作成"""
        now = datetime.now().isoformat()

        metadata = ProjectMetadata(
            id="",  # __post_init__で自動生成
            name=name,
            created_at=now,
            modified_at=now,
            description=f"VLog字幕プロジェクト: {name}",
        )

        project_data = ProjectData(
            metadata=metadata,
            video_file_path=video_path,
            subtitles=[],
            translations={},
            qc_results=[],
            settings={},
        )

        self.current_project = project_data
        self.current_file_path = None

        self.logger.info(f"新しいプロジェクト作成: {name}")
        return project_data

    def load_project(self, file_path: Path) -> ProjectData:
        """プロジェクトファイルを読み込み"""
        if not file_path.exists():
            raise FileNotFoundError(
                f"プロジェクトファイルが見つかりません: {file_path}"
            )

        if file_path.suffix.lower() != ".subproj":
            raise ValueError(f"サポートされていないファイル形式: {file_path.suffix}")

        self.logger.info(f"プロジェクト読み込み開始: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                project_dict = json.load(f)

            # バージョン確認
            file_version = project_dict.get("metadata", {}).get("version", "1.0.0")
            if file_version != "1.0.0":
                self.logger.warning(
                    f"プロジェクトファイルのバージョンが異なります: {file_version}"
                )

            # プロジェクトデータに変換
            project_data = self._dict_to_project_data(project_dict)

            # ファイルパスの存在確認
            if project_data.video_file_path:
                video_path = Path(project_data.video_file_path)
                if not video_path.is_absolute():
                    # 相対パスの場合、プロジェクトファイルの場所を基準に解決
                    video_path = file_path.parent / video_path
                    project_data.video_file_path = str(video_path)

                if not video_path.exists():
                    self.logger.warning(f"動画ファイルが見つかりません: {video_path}")

            self.current_project = project_data
            self.current_file_path = file_path

            self.logger.info(f"プロジェクト読み込み完了: {project_data.metadata.name}")
            return project_data

        except json.JSONDecodeError as e:
            raise ValueError(f"プロジェクトファイルの形式が正しくありません: {e}")
        except Exception as e:
            raise RuntimeError(f"プロジェクト読み込みエラー: {e}")

    def save_project(
        self, project_data: ProjectData, file_path: Optional[Path] = None
    ) -> bool:
        """プロジェクトを保存"""
        if file_path is None:
            if self.current_file_path is None:
                raise ValueError("保存先パスが指定されていません")
            file_path = self.current_file_path

        try:
            # メタデータの更新
            project_data.metadata.modified_at = datetime.now().isoformat()

            # 辞書形式に変換
            project_dict = self._project_data_to_dict(project_data)

            # バックアップを作成
            self._create_backup(file_path)

            # ファイルを保存
            self.logger.info(f"プロジェクト保存開始: {file_path}")

            # 親ディレクトリを作成
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(project_dict, f, indent=2, ensure_ascii=False)

            self.current_project = project_data
            self.current_file_path = file_path

            self.logger.info(f"プロジェクト保存完了: {project_data.metadata.name}")
            return True

        except Exception as e:
            self.logger.error(f"プロジェクト保存エラー: {e}")
            return False

    def save_as_project(self, project_data: ProjectData, file_path: Path) -> bool:
        """プロジェクトを別名で保存"""
        return self.save_project(project_data, file_path)

    def update_subtitles(self, subtitles: List[SubtitleItem]):
        """字幕データを更新"""
        if self.current_project is None:
            raise RuntimeError("プロジェクトが開かれていません")

        self.current_project.subtitles = [
            {
                "start_time": subtitle.start_ms,
                "end_time": subtitle.end_ms,
                "text": subtitle.text,
            }
            for subtitle in subtitles
        ]

        self.logger.info(f"字幕データ更新: {len(subtitles)}件")

    def update_translations(self, language: str, subtitles: List[SubtitleItem]):
        """翻訳データを更新"""
        if self.current_project is None:
            raise RuntimeError("プロジェクトが開かれていません")

        self.current_project.translations[language] = [
            {
                "start_time": subtitle.start_ms,
                "end_time": subtitle.end_ms,
                "text": subtitle.text,
            }
            for subtitle in subtitles
        ]

        self.logger.info(f"翻訳データ更新 ({language}): {len(subtitles)}件")

    def update_qc_results(self, qc_results: List[Dict[str, Any]]):
        """QCチェック結果を更新"""
        if self.current_project is None:
            raise RuntimeError("プロジェクトが開かれていません")

        self.current_project.qc_results = qc_results
        self.logger.info(f"QC結果更新: {len(qc_results)}件")

    def get_current_project(self) -> Optional[ProjectData]:
        """現在のプロジェクトを取得"""
        return self.current_project

    def get_current_file_path(self) -> Optional[Path]:
        """現在のファイルパスを取得"""
        return self.current_file_path

    def is_project_modified(self) -> bool:
        """プロジェクトが変更されているかチェック"""
        if self.current_project is None:
            return False

        if self.current_file_path is None:
            return True  # 新しいプロジェクトで未保存

        # TODO: より詳細な変更検出の実装
        # 現在は簡易的に modified_at を確認
        return True

    def close_project(self):
        """プロジェクトを閉じる"""
        if self.current_project:
            self.logger.info(f"プロジェクト終了: {self.current_project.metadata.name}")

        self.current_project = None
        self.current_file_path = None

    def _project_data_to_dict(self, project_data: ProjectData) -> Dict[str, Any]:
        """プロジェクトデータを辞書に変換"""
        return {
            "metadata": asdict(project_data.metadata),
            "video_file_path": project_data.video_file_path,
            "subtitles": project_data.subtitles,
            "translations": project_data.translations,
            "qc_results": project_data.qc_results,
            "settings": project_data.settings,
        }

    def _dict_to_project_data(self, project_dict: Dict[str, Any]) -> ProjectData:
        """辞書をプロジェクトデータに変換"""
        try:
            # メタデータの変換
            metadata_dict = project_dict.get("metadata", {})
            metadata = ProjectMetadata(**metadata_dict)

            # プロジェクトデータの作成
            project_data = ProjectData(
                metadata=metadata,
                video_file_path=project_dict.get("video_file_path", ""),
                subtitles=project_dict.get("subtitles", []),
                translations=project_dict.get("translations", {}),
                qc_results=project_dict.get("qc_results", []),
                settings=project_dict.get("settings", {}),
            )

            return project_data

        except Exception as e:
            self.logger.error(f"プロジェクトデータ変換エラー: {e}")
            raise ValueError(f"プロジェクトファイルの形式が正しくありません: {e}")

    def _create_backup(self, file_path: Path):
        """バックアップファイルを作成"""
        if file_path.exists():
            backup_path = file_path.with_suffix(f".subproj.backup")
            try:
                import shutil

                shutil.copy2(file_path, backup_path)
                self.logger.debug(f"バックアップ作成: {backup_path}")
            except Exception as e:
                self.logger.warning(f"バックアップ作成失敗: {e}")

    def validate_project_data(self, project_data: ProjectData) -> List[str]:
        """プロジェクトデータの妥当性を確認"""
        errors = []

        # メタデータの確認
        if not project_data.metadata.name.strip():
            errors.append("プロジェクト名が設定されていません")

        # 動画ファイルの確認
        if not project_data.video_file_path:
            errors.append("動画ファイルパスが設定されていません")
        else:
            video_path = Path(project_data.video_file_path)
            if not video_path.exists():
                errors.append(f"動画ファイルが見つかりません: {video_path}")

        # 字幕データの確認
        for i, subtitle in enumerate(project_data.subtitles):
            try:
                start_time = subtitle.get("start_time")
                end_time = subtitle.get("end_time")

                if start_time is None or end_time is None:
                    errors.append(f"字幕 {i + 1}: 時間情報が不正です")
                elif start_time >= end_time:
                    errors.append(f"字幕 {i + 1}: 開始時間が終了時間以降です")

                if not subtitle.get("text", "").strip():
                    errors.append(f"字幕 {i + 1}: テキストが空です")

            except (KeyError, TypeError):
                errors.append(f"字幕 {i + 1}: データ形式が不正です")

        return errors

    def export_to_legacy_format(self, output_path: Path) -> bool:
        """レガシー形式でエクスポート（互換性用）"""
        if self.current_project is None:
            raise RuntimeError("プロジェクトが開かれていません")

        try:
            # 簡易形式での保存（最小限のデータのみ）
            legacy_data = {
                "video_path": self.current_project.video_file_path,
                "subtitles": self.current_project.subtitles,
            }

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(legacy_data, f, indent=2, ensure_ascii=False)

            self.logger.info(f"レガシー形式でエクスポート完了: {output_path}")
            return True

        except Exception as e:
            self.logger.error(f"レガシー形式エクスポートエラー: {e}")
            return False


# シングルトンインスタンス
_project_manager_instance = None


def get_project_manager() -> ProjectManager:
    """プロジェクトマネージャーのシングルトンインスタンスを取得"""
    global _project_manager_instance
    if _project_manager_instance is None:
        _project_manager_instance = ProjectManager()
    return _project_manager_instance
