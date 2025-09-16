"""
CSV字幕エクスポート処理
"""

import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from app.core.models import SubtitleItem


@dataclass
class CSVExportSettings:
    """CSVエクスポート設定"""
    encoding: str = "utf-8"
    with_bom: bool = True  # Google Apps Script用
    delimiter: str = ","
    include_index: bool = True
    include_timing: bool = True
    include_metadata: bool = True


class SubtitleCSVExporter:
    """字幕CSVエクスポーター"""
    
    def __init__(self, settings: Optional[CSVExportSettings] = None):
        self.settings = settings or CSVExportSettings()
    
    def export_for_translation(self, subtitles: List[SubtitleItem], filepath: Path, 
                             source_lang: str = "ja") -> bool:
        """
        翻訳用CSVエクスポート（Google Apps Script連携用）
        
        Args:
            subtitles: 字幕アイテムリスト
            filepath: 出力ファイルパス
            source_lang: ソース言語コード
            
        Returns:
            bool: エクスポート成功可否
        """
        try:
            headers = self._get_translation_headers(source_lang)
            rows = []
            
            # メタデータ行
            if self.settings.include_metadata:
                rows.append([
                    f"# 字幕翻訳用CSVファイル",
                    f"作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"字幕数: {len(subtitles)}",
                    f"ソース言語: {source_lang}",
                    "",  # 翻訳先言語（空欄）
                    "", "", "", ""  # その他の列を埋める
                ])
                rows.append([])  # 空行
            
            # ヘッダー行
            rows.append(headers)
            
            # 字幕データ行
            for subtitle in subtitles:
                row = self._create_translation_row(subtitle, source_lang)
                rows.append(row)
            
            # CSVファイル書き込み
            self._write_csv_file(filepath, rows)
            return True
            
        except Exception as e:
            print(f"CSV翻訳エクスポートエラー: {e}")
            return False
    
    def export_standard(self, subtitles: List[SubtitleItem], filepath: Path) -> bool:
        """
        標準CSVエクスポート
        
        Args:
            subtitles: 字幕アイテムリスト
            filepath: 出力ファイルパス
            
        Returns:
            bool: エクスポート成功可否
        """
        try:
            headers = self._get_standard_headers()
            rows = []
            
            # ヘッダー行
            rows.append(headers)
            
            # 字幕データ行
            for subtitle in subtitles:
                row = self._create_standard_row(subtitle)
                rows.append(row)
            
            # CSVファイル書き込み
            self._write_csv_file(filepath, rows)
            return True
            
        except Exception as e:
            print(f"CSV標準エクスポートエラー: {e}")
            return False
    
    def _get_translation_headers(self, source_lang: str) -> List[str]:
        """翻訳用CSVヘッダーを取得"""
        headers = []
        
        if self.settings.include_index:
            headers.append("字幕番号")
        
        if self.settings.include_timing:
            headers.extend(["開始時間", "終了時間", "表示時間(秒)"])
        
        headers.extend([
            f"原文({source_lang})",
            "翻訳文",
            "翻訳ステータス",
            "翻訳者コメント",
            "品質確認"
        ])
        
        return headers
    
    def _get_standard_headers(self) -> List[str]:
        """標準CSVヘッダーを取得"""
        headers = []

        if self.settings.include_index:
            headers.append("字幕番号")

        if self.settings.include_timing:
            headers.extend(["開始時間", "終了時間", "表示時間(秒)"])

        headers.extend([
            "字幕テキスト"
        ])

        return headers
    
    def _create_translation_row(self, subtitle: SubtitleItem, source_lang: str) -> List[str]:
        """翻訳用行データを作成"""
        row = []
        
        if self.settings.include_index:
            row.append(str(subtitle.index))
        
        if self.settings.include_timing:
            start_time = self._format_time_for_csv(subtitle.start_ms)
            end_time = self._format_time_for_csv(subtitle.end_ms)
            duration = (subtitle.end_ms - subtitle.start_ms) / 1000
            row.extend([start_time, end_time, f"{duration:.1f}"])
        
        row.extend([
            subtitle.text,      # 原文
            "",                # 翻訳文（空欄）
            "未翻訳",           # 翻訳ステータス
            "",                # 翻訳者コメント（空欄）
            ""                 # 品質確認（空欄）
        ])
        
        return row
    
    def _create_standard_row(self, subtitle: SubtitleItem) -> List[str]:
        """標準行データを作成"""
        row = []

        if self.settings.include_index:
            row.append(str(subtitle.index))

        if self.settings.include_timing:
            start_time = self._format_time_for_csv(subtitle.start_ms)
            end_time = self._format_time_for_csv(subtitle.end_ms)
            duration = (subtitle.end_ms - subtitle.start_ms) / 1000
            row.extend([
                start_time,
                end_time,
                f"{duration:.1f}"
            ])

        row.extend([
            subtitle.text
        ])

        return row
    
    def _format_time_for_csv(self, time_ms: int) -> str:
        """CSV用時間フォーマット（MM:SS.mmm）"""
        total_seconds = time_ms / 1000
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:06.3f}"
    
    def _write_csv_file(self, filepath: Path, rows: List[List[str]]):
        """CSVファイル書き込み"""
        # ディレクトリ作成
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # エンコーディング処理
        if self.settings.with_bom and self.settings.encoding.lower() == "utf-8":
            # UTF-8 BOM付きで書き込み（Google Apps Script対応）
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f, delimiter=self.settings.delimiter)
                writer.writerows(rows)
        else:
            # 通常の書き込み
            with open(filepath, 'w', encoding=self.settings.encoding, newline='') as f:
                writer = csv.writer(f, delimiter=self.settings.delimiter)
                writer.writerows(rows)


class TranslationWorkflowManager:
    """翻訳ワークフロー管理"""
    
    def __init__(self, base_path: Path):
        """
        Args:
            base_path: プロジェクトベースパス
        """
        self.base_path = base_path
        self.export_dir = base_path / "subs"
        self.export_dir.mkdir(exist_ok=True)
    
    def create_translation_workflow(self, subtitles: List[SubtitleItem], 
                                  video_name: str, target_langs: List[str]) -> Dict[str, Path]:
        """
        翻訳ワークフロー用ファイル群を作成
        
        Args:
            subtitles: 字幕データ
            video_name: 動画ファイル名（拡張子なし）
            target_langs: 翻訳対象言語リスト
            
        Returns:
            Dict[str, Path]: 作成ファイル辞書
        """
        created_files = {}
        exporter = SubtitleCSVExporter()
        
        # 日本語エクスポート（ソース）
        ja_export_path = self.export_dir / f"{video_name}_ja_export.csv"
        if exporter.export_for_translation(subtitles, ja_export_path, "ja"):
            created_files["source"] = ja_export_path
        
        # 各言語用のテンプレートファイル作成
        for lang in target_langs:
            template_path = self.export_dir / f"{video_name}_{lang}_template.csv"
            if self._create_translation_template(subtitles, template_path, lang):
                created_files[f"template_{lang}"] = template_path
        
        # GAS用設定ファイル作成
        config_path = self.export_dir / f"{video_name}_translation_config.json"
        if self._create_gas_config(video_name, target_langs, config_path):
            created_files["config"] = config_path
        
        # README作成
        readme_path = self.export_dir / f"{video_name}_翻訳手順.md"
        if self._create_workflow_readme(video_name, target_langs, readme_path):
            created_files["readme"] = readme_path
        
        return created_files
    
    def _create_translation_template(self, subtitles: List[SubtitleItem], 
                                   filepath: Path, target_lang: str) -> bool:
        """翻訳テンプレートファイル作成"""
        try:
            exporter = SubtitleCSVExporter()
            # ターゲット言語用のテンプレート
            return exporter.export_for_translation(subtitles, filepath, target_lang)
        except Exception as e:
            print(f"翻訳テンプレート作成エラー: {e}")
            return False
    
    def _create_gas_config(self, video_name: str, target_langs: List[str], 
                          filepath: Path) -> bool:
        """Google Apps Script用設定ファイル作成"""
        try:
            import json
            
            config = {
                "project_name": video_name,
                "source_language": "ja",
                "target_languages": target_langs,
                "files": {
                    "source": f"{video_name}_ja_export.csv",
                    "templates": [f"{video_name}_{lang}_template.csv" for lang in target_langs]
                },
                "translation_settings": {
                    "api_provider": "google",  # google, deepl, manual
                    "glossary_enabled": False,
                    "quality_check": True,
                    "auto_export_srt": True
                },
                "created_at": datetime.now().isoformat(),
                "version": "1.0"
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"GAS設定作成エラー: {e}")
            return False
    
    def _create_workflow_readme(self, video_name: str, target_langs: List[str], 
                              filepath: Path) -> bool:
        """翻訳ワークフロー手順書作成"""
        try:
            readme_content = f"""# 字幕翻訳ワークフロー - {video_name}

## ファイル構成
```
subs/
├── {video_name}_ja_export.csv          # 日本語字幕（翻訳元）
├── {video_name}_translation_config.json  # GAS用設定
├── {video_name}_翻訳手順.md             # この手順書
"""
            
            for lang in target_langs:
                readme_content += f"├── {video_name}_{lang}_template.csv        # {lang}翻訳テンプレート\n"
            
            readme_content += """└── (翻訳完了後)
"""
            
            for lang in target_langs:
                readme_content += f"    ├── {video_name}_{lang}_translated.csv  # {lang}翻訳済み\n"
            
            readme_content += f"""
## 翻訳手順

### 1. Google Apps Script使用の場合
1. Google Drive に `{video_name}_ja_export.csv` をアップロード
2. GASスクリプトで自動翻訳実行
3. 翻訳結果CSVをダウンロード
4. アプリで「翻訳インポート」実行

### 2. 手動翻訳の場合
1. `{video_name}_ja_export.csv` をExcel等で開く
2. 「翻訳文」列に各言語で翻訳を入力
3. `{video_name}_[言語]_translated.csv` として保存
4. アプリで「翻訳インポート」実行

### 3. 外部翻訳サービスの場合
1. CSV内の「原文」列をコピー
2. DeepL、Google翻訳等で一括翻訳
3. 翻訳結果を「翻訳文」列に貼り付け
4. CSVとして保存後、アプリでインポート

## 注意事項
- 翻訳時は字幕の時間制限（1行42文字、最大2行）を考慮してください
- 専門用語や固有名詞は統一してください
- 翻訳ステータス列で進捗を管理できます

## サポート対象言語
"""
            
            for lang in target_langs:
                readme_content += f"- {lang}\n"
            
            readme_content += f"""
## 生成されるSRTファイル
翻訳完了後、以下のSRTファイルが生成されます：
- `{video_name}.ja.srt` (日本語)
"""
            
            for lang in target_langs:
                readme_content += f"- `{video_name}.{lang}.srt` ({lang})\n"
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(readme_content)
            
            return True
            
        except Exception as e:
            print(f"手順書作成エラー: {e}")
            return False