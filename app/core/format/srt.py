"""
SRT字幕ファイルフォーマット処理
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.core.models import SubtitleItem


@dataclass
class SRTFormatSettings:
    """SRT出力設定"""
    encoding: str = "utf-8"
    with_bom: bool = False
    line_ending: str = "lf"  # "lf", "crlf"
    max_chars_per_line: int = 42
    max_lines: int = 2
    
    @property
    def line_separator(self) -> str:
        """改行コードを取得"""
        return "\r\n" if self.line_ending == "crlf" else "\n"


class SRTFormatter:
    """SRTフォーマッタ"""
    
    def __init__(self, settings: Optional[SRTFormatSettings] = None):
        self.settings = settings or SRTFormatSettings()
    
    def format_time(self, time_ms: int) -> str:
        """
        ミリ秒をSRT時間フォーマットに変換
        
        Args:
            time_ms: 時間（ミリ秒）
            
        Returns:
            str: SRT時間形式 "HH:MM:SS,mmm"
        """
        total_seconds = time_ms // 1000
        milliseconds = time_ms % 1000
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    def parse_time(self, time_str: str) -> int:
        """
        SRT時間フォーマットをミリ秒に変換
        
        Args:
            time_str: SRT時間形式 "HH:MM:SS,mmm"
            
        Returns:
            int: 時間（ミリ秒）
        """
        # パターンマッチング
        pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3})'
        match = re.match(pattern, time_str)
        
        if not match:
            raise ValueError(f"Invalid SRT time format: {time_str}")
        
        hours, minutes, seconds, milliseconds = map(int, match.groups())
        
        total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        return total_ms
    
    def format_text(self, text: str) -> str:
        """
        テキストをSRT用にフォーマット
        
        Args:
            text: 元のテキスト
            
        Returns:
            str: フォーマット済みテキスト
        """
        if not text:
            return ""
        
        # 基本的なクリーンアップ
        formatted_text = text.strip()
        
        # HTML エンティティの変換
        html_entities = {
            "&lt;": "<",
            "&gt;": ">",
            "&amp;": "&",
            "&quot;": '"',
            "&apos;": "'",
            "&nbsp;": " "
        }
        
        for entity, char in html_entities.items():
            formatted_text = formatted_text.replace(entity, char)
        
        # 行分割処理
        formatted_text = self._wrap_text(formatted_text)
        
        return formatted_text
    
    def _wrap_text(self, text: str) -> str:
        """テキストの行分割処理"""
        # 既存の改行を考慮
        lines = text.split('\n')
        wrapped_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 行が長すぎる場合は分割
            if len(line) <= self.settings.max_chars_per_line:
                wrapped_lines.append(line)
            else:
                wrapped_lines.extend(self._split_long_line(line))
        
        # 最大行数に制限
        if len(wrapped_lines) > self.settings.max_lines:
            wrapped_lines = wrapped_lines[:self.settings.max_lines]
        
        return '\n'.join(wrapped_lines)
    
    def _split_long_line(self, line: str) -> List[str]:
        """長い行を適切に分割"""
        max_chars = self.settings.max_chars_per_line
        words = line.split()
        
        if not words:
            return [line[:max_chars]]  # 単語境界がない場合は強制分割
        
        lines = []
        current_line = ""
        
        for word in words:
            # 単語自体が長すぎる場合
            if len(word) > max_chars:
                if current_line:
                    lines.append(current_line.strip())
                    current_line = ""
                # 長い単語を分割
                while len(word) > max_chars:
                    lines.append(word[:max_chars])
                    word = word[max_chars:]
                if word:
                    current_line = word + " "
                continue
            
            # 現在の行に単語を追加できるかチェック
            test_line = current_line + word + " "
            if len(test_line.strip()) <= max_chars:
                current_line = test_line
            else:
                # 現在の行を確定し、新しい行を開始
                if current_line:
                    lines.append(current_line.strip())
                current_line = word + " "
        
        # 最後の行を追加
        if current_line:
            lines.append(current_line.strip())
        
        return lines
    
    def format_subtitle_entry(self, index: int, subtitle: SubtitleItem) -> str:
        """
        単一字幕エントリをSRT形式にフォーマット
        
        Args:
            index: 字幕番号（1から開始）
            subtitle: 字幕アイテム
            
        Returns:
            str: SRT形式の字幕エントリ
        """
        start_time = self.format_time(subtitle.start_ms)
        end_time = self.format_time(subtitle.end_ms)
        text = self.format_text(subtitle.text)
        
        entry = f"{index}{self.settings.line_separator}"
        entry += f"{start_time} --> {end_time}{self.settings.line_separator}"
        entry += f"{text}{self.settings.line_separator}"
        
        return entry
    
    def subtitles_to_srt(self, subtitles: List[SubtitleItem]) -> str:
        """
        字幕リストをSRT形式に変換
        
        Args:
            subtitles: 字幕アイテムリスト
            
        Returns:
            str: SRT形式の文字列
        """
        if not subtitles:
            return ""
        
        srt_entries = []
        
        for i, subtitle in enumerate(subtitles, 1):
            entry = self.format_subtitle_entry(i, subtitle)
            srt_entries.append(entry)
        
        # エントリ間の空行
        return self.settings.line_separator.join(srt_entries)
    
    def save_srt_file(self, subtitles: List[SubtitleItem], filepath: Path) -> bool:
        """
        SRTファイルを保存
        
        Args:
            subtitles: 字幕アイテムリスト
            filepath: 保存先ファイルパス
            
        Returns:
            bool: 保存成功可否
        """
        try:
            srt_content = self.subtitles_to_srt(subtitles)
            
            # エンコーディング処理
            if self.settings.with_bom and self.settings.encoding.lower() == "utf-8":
                # UTF-8 BOM付き
                with open(filepath, 'wb') as f:
                    f.write(b'\xef\xbb\xbf')  # BOM
                    f.write(srt_content.encode('utf-8'))
            else:
                # 通常の保存
                with open(filepath, 'w', encoding=self.settings.encoding, newline='') as f:
                    f.write(srt_content)
            
            return True
            
        except Exception as e:
            print(f"SRT保存エラー: {e}")
            return False


class SRTParser:
    """SRTファイルパーサー"""
    
    def __init__(self):
        self.formatter = SRTFormatter()
    
    def parse_srt_file(self, filepath: Path) -> List[SubtitleItem]:
        """
        SRTファイルを読み込んで字幕リストを作成
        
        Args:
            filepath: SRTファイルパス
            
        Returns:
            List[SubtitleItem]: 字幕アイテムリスト
        """
        try:
            # エンコーディングを自動検出して読み込み
            content = self._read_file_with_encoding(filepath)
            return self.parse_srt_content(content)
            
        except Exception as e:
            print(f"SRT読み込みエラー: {e}")
            return []
    
    def _read_file_with_encoding(self, filepath: Path) -> str:
        """エンコーディングを自動検出してファイルを読み込み"""
        encodings = ['utf-8', 'utf-8-sig', 'shift_jis', 'cp932', 'euc-jp']
        
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        
        # すべて失敗した場合はutf-8でエラーを発生させる
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    
    def parse_srt_content(self, content: str) -> List[SubtitleItem]:
        """
        SRT文字列を解析して字幕リストを作成
        
        Args:
            content: SRT形式の文字列
            
        Returns:
            List[SubtitleItem]: 字幕アイテムリスト
        """
        subtitles = []
        
        # 改行コードの統一
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # エントリごとに分割（空行で区切られている）
        entries = re.split(r'\n\s*\n', content.strip())
        
        for entry in entries:
            if not entry.strip():
                continue
            
            subtitle = self._parse_single_entry(entry.strip())
            if subtitle:
                subtitles.append(subtitle)
        
        return subtitles
    
    def _parse_single_entry(self, entry: str) -> Optional[SubtitleItem]:
        """単一SRTエントリを解析"""
        lines = entry.strip().split('\n')
        
        if len(lines) < 3:
            return None
        
        try:
            # インデックス行
            index = int(lines[0])
            
            # タイムコード行
            time_line = lines[1]
            time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', time_line)
            
            if not time_match:
                return None
            
            start_time_str, end_time_str = time_match.groups()
            start_ms = self.formatter.parse_time(start_time_str)
            end_ms = self.formatter.parse_time(end_time_str)
            
            # テキスト行（複数行の可能性）
            text_lines = lines[2:]
            text = '\n'.join(text_lines)
            
            return SubtitleItem(
                index=index,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text
            )
            
        except (ValueError, IndexError) as e:
            print(f"SRTエントリ解析エラー: {e}")
            return None


class MultiLanguageSRTManager:
    """多言語SRT管理クラス"""
    
    def __init__(self, base_filepath: Path):
        """
        Args:
            base_filepath: ベースとなるファイルパス（拡張子なし）
        """
        self.base_filepath = base_filepath
        self.formatters: Dict[str, SRTFormatter] = {}
    
    def add_language(self, lang_code: str, settings: Optional[SRTFormatSettings] = None):
        """言語フォーマッタを追加"""
        self.formatters[lang_code] = SRTFormatter(settings or SRTFormatSettings())
    
    def generate_filepath(self, lang_code: str) -> Path:
        """言語コードに基づいてファイルパスを生成"""
        base_path = Path(self.base_filepath)
        return base_path.parent / f"{base_path.stem}.{lang_code}.srt"
    
    def save_multilang_srt(self, multilang_subtitles: Dict[str, List[SubtitleItem]]) -> Dict[str, bool]:
        """
        多言語SRTファイルを一括保存
        
        Args:
            multilang_subtitles: 言語コードをキーとした字幕辞書
            
        Returns:
            Dict[str, bool]: 各言語の保存結果
        """
        results = {}
        
        for lang_code, subtitles in multilang_subtitles.items():
            filepath = self.generate_filepath(lang_code)
            
            # 言語専用のフォーマッタを取得
            formatter = self.formatters.get(lang_code, SRTFormatter())
            
            success = formatter.save_srt_file(subtitles, filepath)
            results[lang_code] = success
        
        return results
    
    def get_saved_files(self) -> List[Path]:
        """保存されたSRTファイルの一覧を取得"""
        base_path = Path(self.base_filepath)
        pattern = f"{base_path.stem}.*.srt"
        
        return list(base_path.parent.glob(pattern))