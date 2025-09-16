"""
CSV字幕インポート処理
"""

import csv
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from app.core.models import SubtitleItem


@dataclass
class CSVImportSettings:
    """CSVインポート設定"""
    encoding: str = "utf-8"
    delimiter: str = ","
    skip_empty_translations: bool = True
    validate_timing: bool = True
    auto_detect_encoding: bool = True


@dataclass
class TranslationImportResult:
    """翻訳インポート結果"""
    success: bool
    subtitles: List[SubtitleItem]
    language: str
    imported_count: int
    skipped_count: int
    error_count: int
    errors: List[str]
    warnings: List[str]


class SubtitleCSVImporter:
    """字幕CSVインポーター"""
    
    def __init__(self, settings: Optional[CSVImportSettings] = None):
        self.settings = settings or CSVImportSettings()
    
    def import_translated_csv(self, filepath: Path, 
                            original_subtitles: List[SubtitleItem]) -> TranslationImportResult:
        """
        翻訳済みCSVをインポート
        
        Args:
            filepath: CSVファイルパス
            original_subtitles: 元の字幕データ（タイミング参照用）
            
        Returns:
            TranslationImportResult: インポート結果
        """
        result = TranslationImportResult(
            success=False,
            subtitles=[],
            language="",
            imported_count=0,
            skipped_count=0,
            error_count=0,
            errors=[],
            warnings=[]
        )
        
        try:
            # CSVファイル読み込み
            content = self._read_csv_file(filepath)
            if not content:
                result.errors.append("CSVファイルの読み込みに失敗しました")
                return result
            
            # ヘッダー解析
            headers = content[0] if content else []
            if not self._validate_headers(headers):
                result.errors.append("CSVファイルの形式が正しくありません")
                return result
            
            # 言語コード検出
            result.language = self._detect_language_from_filename(filepath)
            
            # データ行処理
            data_rows = content[1:]  # ヘッダーを除く
            translated_subtitles = []
            
            for row_index, row in enumerate(data_rows, start=2):  # 行番号は1ベース + ヘッダー
                try:
                    # メタデータ行やコメント行をスキップ
                    if self._is_metadata_row(row):
                        continue
                    
                    # 翻訳字幕アイテムを作成
                    subtitle_item = self._create_subtitle_from_row(
                        row, headers, original_subtitles, row_index
                    )
                    
                    if subtitle_item:
                        # 翻訳文の検証
                        if self._validate_translation(subtitle_item, row_index, result):
                            translated_subtitles.append(subtitle_item)
                            result.imported_count += 1
                        else:
                            result.skipped_count += 1
                    else:
                        result.skipped_count += 1
                
                except Exception as e:
                    result.error_count += 1
                    result.errors.append(f"行{row_index}: {str(e)}")
            
            # インデックスの再採番
            for i, subtitle in enumerate(translated_subtitles, 1):
                subtitle.index = i
            
            result.subtitles = translated_subtitles
            result.success = result.imported_count > 0
            
            if result.success:
                print(f"CSV翻訳インポート完了: {result.imported_count}件取得")
            
            return result
            
        except Exception as e:
            result.errors.append(f"インポート処理エラー: {str(e)}")
            return result
    
    def import_standard_csv(self, filepath: Path) -> TranslationImportResult:
        """
        標準CSVをインポート
        
        Args:
            filepath: CSVファイルパス
            
        Returns:
            TranslationImportResult: インポート結果
        """
        result = TranslationImportResult(
            success=False,
            subtitles=[],
            language="ja",  # 標準は日本語と仮定
            imported_count=0,
            skipped_count=0,
            error_count=0,
            errors=[],
            warnings=[]
        )
        
        try:
            content = self._read_csv_file(filepath)
            if not content:
                result.errors.append("CSVファイルの読み込みに失敗しました")
                return result
            
            headers = content[0] if content else []
            data_rows = content[1:]
            subtitles = []
            
            for row_index, row in enumerate(data_rows, start=2):
                try:
                    subtitle_item = self._create_standard_subtitle_from_row(row, headers, row_index)
                    if subtitle_item:
                        subtitles.append(subtitle_item)
                        result.imported_count += 1
                    else:
                        result.skipped_count += 1
                        
                except Exception as e:
                    result.error_count += 1
                    result.errors.append(f"行{row_index}: {str(e)}")
            
            result.subtitles = subtitles
            result.success = result.imported_count > 0
            
            return result
            
        except Exception as e:
            result.errors.append(f"標準インポートエラー: {str(e)}")
            return result
    
    def _read_csv_file(self, filepath: Path) -> List[List[str]]:
        """CSVファイル読み込み"""
        content = []
        
        encodings = ['utf-8-sig', 'utf-8', 'shift_jis', 'cp932'] if self.settings.auto_detect_encoding else [self.settings.encoding]
        
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding, newline='') as f:
                    reader = csv.reader(f, delimiter=self.settings.delimiter)
                    content = [row for row in reader]
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"CSV読み込みエラー ({encoding}): {e}")
                continue
        
        return content
    
    def _validate_headers(self, headers: List[str]) -> bool:
        """ヘッダー形式の検証"""
        if not headers:
            return False
        
        # 翻訳用CSVの必須フィールドをチェック
        required_fields = ["翻訳文", "原文"]  # 最低限必要
        header_text = " ".join(headers).lower()
        
        return any(field in header_text for field in required_fields)
    
    def _detect_language_from_filename(self, filepath: Path) -> str:
        """ファイル名から言語コードを検出"""
        name = filepath.stem.lower()
        
        # 言語コードマッピング
        lang_patterns = {
            "en": ["en", "english", "英語"],
            "zh": ["zh", "chinese", "中文", "中国語"],
            "ko": ["ko", "korean", "한국어", "韓国語"],
            "es": ["es", "spanish", "español", "スペイン語"],
            "fr": ["fr", "french", "français", "フランス語"],
            "de": ["de", "german", "deutsch", "ドイツ語"],
            "ar": ["ar", "arabic", "عربي", "アラビア語"]
        }
        
        for lang_code, patterns in lang_patterns.items():
            if any(pattern in name for pattern in patterns):
                return lang_code
        
        return "unknown"
    
    def _is_metadata_row(self, row: List[str]) -> bool:
        """メタデータ行かどうかの判定"""
        if not row or not row[0]:
            return True
        
        first_cell = row[0].strip()
        return (first_cell.startswith("#") or 
                first_cell.startswith("作成日時") or
                not first_cell)
    
    def _create_subtitle_from_row(self, row: List[str], headers: List[str],
                                original_subtitles: List[SubtitleItem], 
                                row_index: int) -> Optional[SubtitleItem]:
        """行データから字幕アイテムを作成"""
        if len(row) < len(headers):
            # 不足する列を空文字で埋める
            row.extend([""] * (len(headers) - len(row)))
        
        # 列インデックス取得
        indices = self._get_column_indices(headers)
        
        try:
            # 字幕番号から元データを特定
            subtitle_index = int(row[indices.get("index", 0)]) if indices.get("index") is not None else row_index - 1
            
            # 元の字幕データからタイミング情報を取得
            if 1 <= subtitle_index <= len(original_subtitles):
                original = original_subtitles[subtitle_index - 1]
                start_ms = original.start_ms
                end_ms = original.end_ms
            else:
                # タイミング情報を直接取得
                start_ms = self._parse_time_from_csv(row[indices.get("start_time", 1)])
                end_ms = self._parse_time_from_csv(row[indices.get("end_time", 2)])
            
            # 翻訳テキスト取得
            translation_index = indices.get("translation", 4)  # 翻訳文列
            translated_text = row[translation_index].strip() if translation_index < len(row) else ""
            
            if not translated_text and self.settings.skip_empty_translations:
                return None
            
            return SubtitleItem(
                index=subtitle_index,
                start_ms=start_ms,
                end_ms=end_ms,
                text=translated_text
            )
            
        except (ValueError, IndexError) as e:
            print(f"字幕作成エラー (行{row_index}): {e}")
            return None
    
    def _create_standard_subtitle_from_row(self, row: List[str], headers: List[str],
                                         row_index: int) -> Optional[SubtitleItem]:
        """標準CSVから字幕アイテムを作成"""
        try:
            indices = self._get_column_indices(headers)

            index = int(row[indices.get("index", 0)])

            # 新しい形式（開始時間/終了時間）を優先、古い形式にもフォールバック
            if indices.get("start_time_ms") is not None and indices.get("end_time_ms") is not None:
                # 古い形式：ミリ秒数値
                start_ms = int(row[indices.get("start_time_ms")])
                end_ms = int(row[indices.get("end_time_ms")])
            elif indices.get("start_time") is not None and indices.get("end_time") is not None:
                # 新しい形式：MM:SS.mmm
                start_ms = self._parse_time_from_csv(row[indices.get("start_time")])
                end_ms = self._parse_time_from_csv(row[indices.get("end_time")])
            else:
                # デフォルトフォールバック
                start_ms = self._parse_time_from_csv(row[1]) if len(row) > 1 else 0
                end_ms = self._parse_time_from_csv(row[2]) if len(row) > 2 else 0

            text_index = indices.get("text", 4)  # 字幕テキスト列のデフォルトインデックス調整
            text = row[text_index] if text_index < len(row) else ""

            return SubtitleItem(
                index=index,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text
            )

        except (ValueError, IndexError) as e:
            print(f"標準字幕作成エラー (行{row_index}): {e}")
            return None
    
    def _get_column_indices(self, headers: List[str]) -> Dict[str, Optional[int]]:
        """列インデックスマッピングを取得"""
        indices = {}
        
        for i, header in enumerate(headers):
            header_lower = header.lower().strip()
            
            if "字幕番号" in header or "番号" in header or "index" in header_lower:
                indices["index"] = i
            elif "開始" in header and "時間" in header:
                indices["start_time"] = i
            elif "終了" in header and "時間" in header:
                indices["end_time"] = i
            elif "開始時間(ms)" in header or "start_ms" in header_lower:
                indices["start_time_ms"] = i
            elif "終了時間(ms)" in header or "end_ms" in header_lower:
                indices["end_time_ms"] = i
            elif "翻訳文" in header or "translation" in header_lower:
                indices["translation"] = i
            elif "字幕テキスト" in header or "テキスト" in header or "text" in header_lower:
                indices["text"] = i
        
        return indices
    
    def _parse_time_from_csv(self, time_str: str) -> int:
        """CSV時間文字列をミリ秒に変換"""
        try:
            time_str = time_str.strip()
            
            # MM:SS.mmm 形式
            if ":" in time_str:
                parts = time_str.split(":")
                minutes = int(parts[0])
                seconds = float(parts[1])
                return int((minutes * 60 + seconds) * 1000)
            
            # 単純な数値（ミリ秒）
            return int(float(time_str))
            
        except ValueError:
            return 0
    
    def _validate_translation(self, subtitle: SubtitleItem, row_index: int, 
                            result: TranslationImportResult) -> bool:
        """翻訳の妥当性チェック"""
        if not subtitle.text.strip():
            if not self.settings.skip_empty_translations:
                result.warnings.append(f"行{row_index}: 翻訳文が空です")
            return False
        
        # 時間の妥当性チェック
        if self.settings.validate_timing:
            if subtitle.start_ms >= subtitle.end_ms:
                result.warnings.append(f"行{row_index}: 時間設定が不正です")
                return False
            
            duration = subtitle.end_ms - subtitle.start_ms
            if duration < 500:  # 0.5秒未満
                result.warnings.append(f"行{row_index}: 表示時間が短すぎます")
        
        # 文字数チェック（簡易）
        lines = subtitle.text.split('\n')
        if len(lines) > 2:
            result.warnings.append(f"行{row_index}: 行数が多すぎます（{len(lines)}行）")
        
        for line in lines:
            if len(line) > 50:  # 少し緩めの制限
                result.warnings.append(f"行{row_index}: 行が長すぎます（{len(line)}文字）")
        
        return True


class CSVWorkflowValidator:
    """CSVワークフロー検証"""
    
    @staticmethod
    def validate_translation_workflow(source_file: Path, translated_files: List[Path]) -> Dict[str, Any]:
        """翻訳ワークフロー全体の検証"""
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "language_coverage": {},
            "file_status": {}
        }
        
        try:
            # ソースファイル検証
            if not source_file.exists():
                result["errors"].append("ソースファイルが見つかりません")
                result["valid"] = False
                return result
            
            # 翻訳ファイル検証
            for trans_file in translated_files:
                lang = SubtitleCSVImporter()._detect_language_from_filename(trans_file)
                
                if trans_file.exists():
                    result["file_status"][lang] = "available"
                    result["language_coverage"][lang] = True
                else:
                    result["file_status"][lang] = "missing"
                    result["language_coverage"][lang] = False
                    result["warnings"].append(f"{lang} 翻訳ファイルが見つかりません: {trans_file.name}")
        
        except Exception as e:
            result["errors"].append(f"検証エラー: {str(e)}")
            result["valid"] = False
        
        return result