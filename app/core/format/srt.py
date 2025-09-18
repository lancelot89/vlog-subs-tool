"""
SRT字幕ファイルフォーマット処理
強化されたエラーハンドリングとユーザーフィードバック付き
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.core.models import SubtitleItem
from app.core.error_handler import (
    ErrorHandler, ErrorInfo, ErrorCategory, ErrorSeverity,
    create_file_operation_error
)


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
    """SRTフォーマッタ - 強化されたエラーハンドリング付き"""

    def __init__(self, settings: Optional[SRTFormatSettings] = None, error_handler: Optional[ErrorHandler] = None):
        self.settings = settings or SRTFormatSettings()
        self.error_handler = error_handler or ErrorHandler()
        self.logger = logging.getLogger(__name__)
    
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
    
    def save_srt_file(self, subtitles: List[SubtitleItem], filepath: Path, show_errors: bool = True) -> bool:
        """
        SRTファイルを保存 - 強化されたエラーハンドリング付き

        Args:
            subtitles: 字幕アイテムリスト
            filepath: 保存先ファイルパス
            show_errors: エラーダイアログ表示可否

        Returns:
            bool: 保存成功可否
        """
        try:
            # 事前検証
            if not subtitles:
                if show_errors:
                    error_info = ErrorInfo(
                        message="保存する字幕データがありません",
                        category=ErrorCategory.VALIDATION,
                        severity=ErrorSeverity.WARNING,
                        suggestions=["字幕を抽出してから保存してください"]
                    )
                    self.error_handler.handle_error(error_info, {"file_path": str(filepath)})
                return False

            # ディレクトリ存在確認
            parent_dir = filepath.parent
            if not parent_dir.exists():
                try:
                    parent_dir.mkdir(parents=True, exist_ok=True)
                    self.logger.info(f"保存ディレクトリを作成: {parent_dir}")
                except Exception as e:
                    if show_errors:
                        error_info = create_file_operation_error(
                            parent_dir, "保存ディレクトリ作成", e
                        )
                        self.error_handler.handle_error(error_info, {"target_file": str(filepath)})
                    return False

            # 書き込み権限確認
            if filepath.exists():
                try:
                    # 書き込み可能かテスト
                    with open(filepath, 'a', encoding=self.settings.encoding):
                        pass
                except PermissionError as e:
                    if show_errors:
                        error_info = create_file_operation_error(
                            filepath, "ファイル書き込み権限確認", e
                        )
                        error_info.suggestions.extend([
                            "ファイルが他のアプリケーションで開かれていないか確認してください",
                            "管理者権限でアプリケーションを実行してみてください"
                        ])
                        self.error_handler.handle_error(error_info, {"subtitles_count": len(subtitles)})
                    return False

            # SRTコンテンツ生成
            try:
                srt_content = self.subtitles_to_srt(subtitles)
            except Exception as e:
                if show_errors:
                    error_info = ErrorInfo(
                        message="字幕データのSRT形式変換に失敗しました",
                        category=ErrorCategory.VALIDATION,
                        severity=ErrorSeverity.ERROR,
                        technical_details=str(e),
                        suggestions=[
                            "字幕データが正しい形式であることを確認してください",
                            "時間情報が正しく設定されているか確認してください"
                        ]
                    )
                    self.error_handler.handle_error(error_info, {
                        "subtitles_count": len(subtitles),
                        "file_path": str(filepath)
                    })
                return False

            # ファイル保存処理
            backup_created = False
            if filepath.exists():
                # バックアップ作成
                try:
                    backup_path = filepath.with_suffix(f"{filepath.suffix}.backup")
                    filepath.replace(backup_path)
                    backup_created = True
                    self.logger.info(f"バックアップ作成: {backup_path}")
                except Exception as e:
                    self.logger.warning(f"バックアップ作成失敗: {e}")

            try:
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

                # 保存成功ログ
                file_size = filepath.stat().st_size
                self.logger.info(f"SRTファイル保存成功: {filepath.name} ({len(subtitles)}件, {file_size:,}bytes)")
                return True

            except UnicodeEncodeError as e:
                if show_errors:
                    error_info = ErrorInfo(
                        message=f"文字エンコーディング（{self.settings.encoding}）での保存に失敗しました",
                        category=ErrorCategory.FILE_OPERATION,
                        severity=ErrorSeverity.ERROR,
                        technical_details=str(e),
                        suggestions=[
                            "UTF-8エンコーディングを使用してください",
                            "特殊文字が含まれていないか確認してください"
                        ]
                    )
                    self.error_handler.handle_error(error_info, {
                        "encoding": self.settings.encoding,
                        "file_path": str(filepath)
                    })
                return False

            except OSError as e:
                # ディスク容量不足などのシステムエラー
                if show_errors:
                    error_info = create_file_operation_error(filepath, "SRTファイル保存", e)
                    if "No space left" in str(e):
                        error_info.suggestions.insert(0, "ディスク容量を確保してください")
                    self.error_handler.handle_error(error_info, {"subtitles_count": len(subtitles)})
                return False

        except Exception as e:
            # 予期しないエラー
            if show_errors:
                error_info = ErrorInfo(
                    message="SRTファイル保存中に予期しないエラーが発生しました",
                    category=ErrorCategory.SYSTEM,
                    severity=ErrorSeverity.ERROR,
                    technical_details=f"{type(e).__name__}: {str(e)}",
                    suggestions=[
                        "ファイルパスが正しいことを確認してください",
                        "別のファイル名で保存してみてください",
                        "アプリケーションを再起動してみてください"
                    ]
                )
                self.error_handler.handle_error(error_info, {
                    "file_path": str(filepath),
                    "subtitles_count": len(subtitles)
                })
            return False


class SRTParser:
    """SRTファイルパーサー - 強化されたエラーハンドリング付き"""

    def __init__(self, error_handler: Optional[ErrorHandler] = None):
        self.formatter = SRTFormatter()
        self.error_handler = error_handler or ErrorHandler()
        self.logger = logging.getLogger(__name__)
    
    def parse_srt_file(self, filepath: Path, show_errors: bool = True) -> List[SubtitleItem]:
        """
        SRTファイルを読み込んで字幕リストを作成 - 強化されたエラーハンドリング付き

        Args:
            filepath: SRTファイルパス
            show_errors: エラーダイアログ表示可否

        Returns:
            List[SubtitleItem]: 字幕アイテムリスト
        """
        try:
            # ファイル存在確認
            if not filepath.exists():
                if show_errors:
                    error_info = create_file_operation_error(
                        filepath, "SRTファイル読み込み",
                        FileNotFoundError(f"ファイルが見つかりません: {filepath}")
                    )
                    self.error_handler.handle_error(error_info)
                return []

            # ファイルサイズ確認
            try:
                file_size = filepath.stat().st_size
                if file_size == 0:
                    if show_errors:
                        error_info = ErrorInfo(
                            message="SRTファイルが空です",
                            category=ErrorCategory.FILE_OPERATION,
                            severity=ErrorSeverity.WARNING,
                            suggestions=["正しいSRTファイルを選択してください"]
                        )
                        self.error_handler.handle_error(error_info, {"file_path": str(filepath)})
                    return []

                # 大きすぎるファイルの警告
                max_file_size = 50 * 1024 * 1024  # 50MB
                if file_size > max_file_size:
                    if show_errors:
                        error_info = ErrorInfo(
                            message=f"SRTファイルが非常に大きいです ({file_size // 1024 // 1024}MB)",
                            category=ErrorCategory.VALIDATION,
                            severity=ErrorSeverity.WARNING,
                            suggestions=[
                                "ファイルサイズが正しいか確認してください",
                                "処理に時間がかかる可能性があります"
                            ]
                        )
                        self.error_handler.handle_error(error_info, {"file_size": file_size})

            except OSError as e:
                if show_errors:
                    error_info = create_file_operation_error(filepath, "ファイル情報取得", e)
                    self.error_handler.handle_error(error_info)
                return []

            # エンコーディングを自動検出して読み込み
            try:
                content = self._read_file_with_encoding_enhanced(filepath)
            except Exception as e:
                if show_errors:
                    error_info = ErrorInfo(
                        message="SRTファイルの読み込みに失敗しました",
                        category=ErrorCategory.FILE_OPERATION,
                        severity=ErrorSeverity.ERROR,
                        technical_details=str(e),
                        suggestions=[
                            "ファイルが破損していないか確認してください",
                            "ファイルのエンコーディングを確認してください",
                            "別のSRTファイルで試してください"
                        ]
                    )
                    self.error_handler.handle_error(error_info, {"file_path": str(filepath)})
                return []

            # SRT形式の解析
            try:
                subtitle_items = self.parse_srt_content(content)
                self.logger.info(f"SRTファイル読み込み成功: {filepath.name} ({len(subtitle_items)}件)")
                return subtitle_items
            except Exception as e:
                if show_errors:
                    error_info = ErrorInfo(
                        message="SRTファイルの形式解析に失敗しました",
                        category=ErrorCategory.VALIDATION,
                        severity=ErrorSeverity.ERROR,
                        technical_details=str(e),
                        suggestions=[
                            "ファイルが正しいSRT形式であることを確認してください",
                            "時間形式が正しいか確認してください (HH:MM:SS,mmm)",
                            "字幕番号が連続しているか確認してください"
                        ]
                    )
                    self.error_handler.handle_error(error_info, {
                        "file_path": str(filepath),
                        "content_preview": content[:500] if content else ""
                    })
                return []

        except Exception as e:
            if show_errors:
                error_info = ErrorInfo(
                    message="SRTファイル処理中に予期しないエラーが発生しました",
                    category=ErrorCategory.SYSTEM,
                    severity=ErrorSeverity.ERROR,
                    technical_details=f"{type(e).__name__}: {str(e)}",
                    suggestions=[
                        "ファイルが他のアプリケーションで使用されていないか確認してください",
                        "ファイルの権限を確認してください",
                        "アプリケーションを再起動してみてください"
                    ]
                )
                self.error_handler.handle_error(error_info, {"file_path": str(filepath)})
            return []
    
    def _read_file_with_encoding_enhanced(self, filepath: Path) -> str:
        """エンコーディングを自動検出してファイルを読み込み - 強化版"""
        encodings = ['utf-8', 'utf-8-sig', 'shift_jis', 'cp932', 'euc-jp', 'iso-8859-1', 'latin1']

        last_error = None
        attempted_encodings = []

        for encoding in encodings:
            try:
                self.logger.debug(f"エンコーディング試行: {encoding}")
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                    if content:  # 空でない場合
                        self.logger.info(f"ファイル読み込み成功: {encoding} エンコーディング")
                        return content
                attempted_encodings.append(encoding)
            except UnicodeDecodeError as e:
                attempted_encodings.append(encoding)
                last_error = e
                self.logger.debug(f"エンコーディング {encoding} でデコード失敗: {e}")
                continue
            except Exception as e:
                attempted_encodings.append(encoding)
                last_error = e
                self.logger.warning(f"エンコーディング {encoding} で読み込みエラー: {e}")
                continue

        # すべて失敗した場合の詳細エラー
        error_detail = f"試行したエンコーディング: {', '.join(attempted_encodings)}"
        if last_error:
            error_detail += f", 最後のエラー: {last_error}"

        raise UnicodeDecodeError("encoding detection failed", b"", 0, 1, error_detail)

    def _read_file_with_encoding(self, filepath: Path) -> str:
        """エンコーディングを自動検出してファイルを読み込み（レガシー版）"""
        return self._read_file_with_encoding_enhanced(filepath)
    
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