"""
CSVモジュールのテスト
"""

import pytest
import csv
from pathlib import Path

from app.core.models import SubtitleItem
from app.core.csv.exporter import SubtitleCSVExporter, CSVExportSettings, TranslationWorkflowManager
from app.core.csv.importer import SubtitleCSVImporter, CSVImportSettings, TranslationImportResult


class TestCSVExportSettings:
    """CSVExportSettingsのテスト"""
    
    def test_default_settings(self):
        """デフォルト設定のテスト"""
        settings = CSVExportSettings()
        
        assert settings.encoding == "utf-8"
        assert settings.with_bom == True
        assert settings.delimiter == ","
        assert settings.include_index == True
        assert settings.include_timing == True
        assert settings.include_metadata == True


class TestSubtitleCSVExporter:
    """SubtitleCSVExporterのテスト"""
    
    def test_export_for_translation(self, sample_subtitles, temp_dir):
        """翻訳用CSVエクスポートのテスト"""
        exporter = SubtitleCSVExporter()
        output_path = temp_dir / "translation.csv"
        
        success = exporter.export_for_translation(sample_subtitles, output_path, "ja")
        assert success
        assert output_path.exists()
        
        # ファイル内容確認
        with open(output_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            assert "字幕番号" in content
            assert "原文(ja)" in content
            assert "翻訳文" in content
            assert "こんにちは世界" in content
    
    def test_export_standard(self, sample_subtitles, temp_dir):
        """標準CSVエクスポートのテスト"""
        exporter = SubtitleCSVExporter()
        output_path = temp_dir / "standard.csv"
        
        success = exporter.export_standard(sample_subtitles, output_path)
        assert success
        assert output_path.exists()
        
        # CSV内容読み込み
        with open(output_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        # ヘッダーチェック
        assert "字幕番号" in rows[0]
        assert "字幕テキスト" in rows[0]
        
        # データ行チェック
        assert len(rows) == 4  # ヘッダー + 3データ行
        assert rows[1][0] == "1"  # 最初の字幕番号
    
    def test_format_time_for_csv(self):
        """CSV用時間フォーマットのテスト"""
        exporter = SubtitleCSVExporter()
        
        # 1分30秒500ミリ秒
        formatted = exporter._format_time_for_csv(90500)
        assert formatted == "01:30.500"
        
        # 3秒
        formatted = exporter._format_time_for_csv(3000)
        assert formatted == "00:03.000"
    
    def test_custom_settings(self, sample_subtitles, temp_dir):
        """カスタム設定のテスト"""
        settings = CSVExportSettings(
            with_bom=False,
            include_metadata=False,
            delimiter=";"
        )
        exporter = SubtitleCSVExporter(settings)
        output_path = temp_dir / "custom.csv"
        
        success = exporter.export_for_translation(sample_subtitles, output_path)
        assert success
        
        # セミコロン区切りで確認
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert ";" in content
            # メタデータ行がないことを確認
            assert "# 字幕翻訳用CSVファイル" not in content


class TestCSVImportSettings:
    """CSVImportSettingsのテスト"""
    
    def test_default_settings(self):
        """デフォルト設定のテスト"""
        settings = CSVImportSettings()
        
        assert settings.encoding == "utf-8"
        assert settings.delimiter == ","
        assert settings.skip_empty_translations == True
        assert settings.validate_timing == True
        assert settings.auto_detect_encoding == True


class TestSubtitleCSVImporter:
    """SubtitleCSVImporterのテスト"""
    
    def test_import_translated_csv(self, sample_subtitles, temp_dir):
        """翻訳済みCSVインポートのテスト"""
        # まずエクスポートでCSVを作成
        exporter = SubtitleCSVExporter()
        csv_path = temp_dir / "for_import.csv"
        exporter.export_for_translation(sample_subtitles, csv_path, "ja")
        
        # CSVファイルを手動で編集（翻訳を追加）
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
        
        # 翻訳文を追加（簡易的に）
        modified_lines = []
        for line in lines:
            if "こんにちは世界" in line:
                line = line.replace('""', '"Hello World"', 1)  # 翻訳文列に追加
            modified_lines.append(line)
        
        with open(csv_path, 'w', encoding='utf-8-sig') as f:
            f.writelines(modified_lines)
        
        # インポートテスト
        importer = SubtitleCSVImporter()
        result = importer.import_translated_csv(csv_path, sample_subtitles)
        
        assert result.success
        assert result.imported_count > 0
        assert result.language != ""
    
    def test_detect_language_from_filename(self):
        """ファイル名からの言語検出のテスト"""
        importer = SubtitleCSVImporter()
        
        assert importer._detect_language_from_filename(Path("test_en.csv")) == "en"
        assert importer._detect_language_from_filename(Path("video_zh_translated.csv")) == "zh"
        assert importer._detect_language_from_filename(Path("korean_ko.csv")) == "ko"
        assert importer._detect_language_from_filename(Path("japanese.csv")) == "unknown"
    
    def test_parse_time_from_csv(self):
        """CSV時間解析のテスト"""
        importer = SubtitleCSVImporter()
        
        # MM:SS.mmm形式
        assert importer._parse_time_from_csv("01:30.500") == 90500
        assert importer._parse_time_from_csv("00:03.000") == 3000
        
        # 単純な数値（ミリ秒）
        assert importer._parse_time_from_csv("5000") == 5000
        
        # 不正な値
        assert importer._parse_time_from_csv("invalid") == 0
    
    def test_validate_headers(self):
        """ヘッダー検証のテスト"""
        importer = SubtitleCSVImporter()
        
        # 有効なヘッダー
        valid_headers = ["字幕番号", "開始時間", "終了時間", "原文", "翻訳文"]
        assert importer._validate_headers(valid_headers) == True
        
        # 不正なヘッダー
        invalid_headers = ["番号", "時間", "テキスト"]
        assert importer._validate_headers(invalid_headers) == False
        
        # 空のヘッダー
        assert importer._validate_headers([]) == False
    
    def test_import_standard_csv(self, temp_dir):
        """標準CSVインポートのテスト"""
        # 標準CSVファイルを作成
        csv_path = temp_dir / "standard.csv"
        
        csv_data = [
            ["字幕番号", "開始時間(ms)", "終了時間(ms)", "字幕テキスト"],
            ["1", "1000", "3000", "テスト字幕1"],
            ["2", "4000", "6000", "テスト字幕2"]
        ]
        
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)
        
        # インポートテスト
        importer = SubtitleCSVImporter()
        result = importer.import_standard_csv(csv_path)
        
        assert result.success
        assert result.imported_count == 2
        assert len(result.subtitles) == 2
        assert result.subtitles[0].text == "テスト字幕1"


class TestTranslationWorkflowManager:
    """TranslationWorkflowManagerのテスト"""
    
    def test_init(self, temp_dir):
        """初期化のテスト"""
        manager = TranslationWorkflowManager(temp_dir)
        
        assert manager.base_path == temp_dir
        assert manager.export_dir == temp_dir / "subs"
        assert manager.export_dir.exists()
    
    def test_create_translation_workflow(self, sample_subtitles, temp_dir):
        """翻訳ワークフロー作成のテスト"""
        manager = TranslationWorkflowManager(temp_dir)
        
        created_files = manager.create_translation_workflow(
            sample_subtitles, 
            "test_video", 
            ["en", "zh"]
        )
        
        assert "source" in created_files
        assert "template_en" in created_files
        assert "template_zh" in created_files
        assert "config" in created_files
        assert "readme" in created_files
        
        # ファイル存在確認
        for file_path in created_files.values():
            assert file_path.exists()
        
        # 設定ファイル内容確認
        import json
        config_path = created_files["config"]
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        assert config["project_name"] == "test_video"
        assert config["source_language"] == "ja"
        assert "en" in config["target_languages"]
        assert "zh" in config["target_languages"]
    
    def test_create_workflow_readme(self, temp_dir):
        """手順書作成のテスト"""
        manager = TranslationWorkflowManager(temp_dir)
        readme_path = temp_dir / "test_readme.md"
        
        success = manager._create_workflow_readme("test_video", ["en", "zh"], readme_path)
        assert success
        assert readme_path.exists()
        
        # 内容確認
        content = readme_path.read_text(encoding='utf-8')
        assert "test_video" in content
        assert "翻訳手順" in content
        assert "test_video.en.srt" in content
        assert "test_video.zh.srt" in content


class TestTranslationImportResult:
    """TranslationImportResultのテスト"""
    
    def test_init(self):
        """初期化のテスト"""
        result = TranslationImportResult(
            success=True,
            subtitles=[],
            language="en",
            imported_count=5,
            skipped_count=1,
            error_count=0,
            errors=[],
            warnings=["警告メッセージ"]
        )
        
        assert result.success == True
        assert result.language == "en"
        assert result.imported_count == 5
        assert result.skipped_count == 1
        assert result.error_count == 0
        assert len(result.warnings) == 1