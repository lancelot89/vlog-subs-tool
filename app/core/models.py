"""
データモデル定義
DESIGN.mdに基づくSubtitleItemとProjectクラスの実装
"""

from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple, Dict, Any
import json
from pathlib import Path


@dataclass
class SubtitleItem:
    """字幕アイテムのデータクラス"""
    index: int
    start_ms: int
    end_ms: int
    text: str
    bbox: Optional[Tuple[int, int, int, int]] = None  # x, y, w, h の検出領域
    
    def duration_ms(self) -> int:
        """表示時間（ミリ秒）を取得"""
        return self.end_ms - self.start_ms
    
    def duration_sec(self) -> float:
        """表示時間（秒）を取得"""
        return self.duration_ms() / 1000.0
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubtitleItem':
        """辞書から作成"""
        return cls(**data)


@dataclass
class ProjectSettings:
    """プロジェクト設定のデータクラス"""
    fps_sample: float = 3.0
    roi_mode: str = "auto"  # "auto", "bottom_30", "manual"
    roi_rect: Optional[Tuple[int, int, int, int]] = None  # manual時の矩形
    ocr_engine: str = "paddleocr_ja"  # "paddleocr_ja", "tesseract_jpn"
    max_chars: int = 42
    max_lines: int = 2
    min_dur_sec: float = 1.2
    similarity_threshold: float = 0.90
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectSettings':
        """辞書から作成"""
        return cls(**data)


@dataclass
class Project:
    """プロジェクトデータのメインクラス"""
    source_video: str
    settings: ProjectSettings
    subtitles: List[SubtitleItem]
    version: str = "1.0"
    
    def __post_init__(self):
        """初期化後の処理"""
        if isinstance(self.settings, dict):
            self.settings = ProjectSettings.from_dict(self.settings)
        
        # subtitlesが辞書のリストの場合、SubtitleItemに変換
        if self.subtitles and isinstance(self.subtitles[0], dict):
            self.subtitles = [SubtitleItem.from_dict(item) for item in self.subtitles]
    
    def add_subtitle(self, subtitle: SubtitleItem) -> None:
        """字幕を追加"""
        self.subtitles.append(subtitle)
        self._reindex()
    
    def remove_subtitle(self, index: int) -> None:
        """字幕を削除"""
        if 0 <= index < len(self.subtitles):
            del self.subtitles[index]
            self._reindex()
    
    def _reindex(self) -> None:
        """インデックスを再採番"""
        for i, subtitle in enumerate(self.subtitles, 1):
            subtitle.index = i
    
    def get_subtitle_by_time(self, time_ms: int) -> Optional[SubtitleItem]:
        """指定時間に表示される字幕を取得"""
        for subtitle in self.subtitles:
            if subtitle.start_ms <= time_ms <= subtitle.end_ms:
                return subtitle
        return None
    
    def sort_by_time(self) -> None:
        """時間順にソート"""
        self.subtitles.sort(key=lambda x: x.start_ms)
        self._reindex()
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "version": self.version,
            "source_video": self.source_video,
            "settings": self.settings.to_dict(),
            "subtitles": [subtitle.to_dict() for subtitle in self.subtitles]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """辞書から作成"""
        return cls(
            version=data.get("version", "1.0"),
            source_video=data["source_video"],
            settings=ProjectSettings.from_dict(data["settings"]),
            subtitles=[SubtitleItem.from_dict(item) for item in data["subtitles"]]
        )
    
    def save(self, filepath: Path) -> None:
        """プロジェクトファイルを保存"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, filepath: Path) -> 'Project':
        """プロジェクトファイルを読み込み"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    @classmethod
    def create_new(cls, video_path: str) -> 'Project':
        """新しいプロジェクトを作成"""
        return cls(
            source_video=video_path,
            settings=ProjectSettings(),
            subtitles=[]
        )


class QCResult:
    """QCチェック結果"""
    def __init__(self, subtitle_index: int, error_type: str, message: str, severity: str = "warning"):
        self.subtitle_index = subtitle_index
        self.error_type = error_type  # "time_overlap", "duration_short", "text_long", etc.
        self.message = message
        self.severity = severity  # "error", "warning", "info"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtitle_index": self.subtitle_index,
            "error_type": self.error_type,
            "message": self.message,
            "severity": self.severity
        }