"""
CSV エクスポート・インポート機能の統合テスト

外部翻訳ワークフロー（GAS連携）のためのCSV機能のテスト
"""

import csv
import tempfile
from pathlib import Path

import pytest

from app.core.csv.exporter import CSVExporter
from app.core.csv.importer import CSVImporter
from app.core.models import SubtitleItem


class TestCSVExportImportIntegration:
    """CSV エクスポート・インポート統合テスト"""

    @pytest.fixture
    def sample_subtitles_japanese(self):
        """日本語字幕のサンプルデータ"""
        return [
            SubtitleItem(1, 1000, 3000, "こんにちは、世界！"),
            SubtitleItem(2, 4000, 6000, "これはテストです。\n複数行のテキスト。"),
            SubtitleItem(3, 7000, 9000, "最後の字幕"),
            SubtitleItem(4, 10000, 12000, ""),  # 空の字幕
            SubtitleItem(5, 13000, 15000, "特殊文字: @#$%^&*()"),
        ]

    @pytest.fixture
    def sample_translated_csv_content(self):
        """翻訳済みCSVの内容"""
        return [
            ["Index", "Start Time", "End Time", "Original Text", "Translated Text"],
            ["1", "00:00:01,000", "00:00:03,000", "こんにちは、世界！", "Hello, World!"],
            ["2", "00:00:04,000", "00:00:06,000", "これはテストです。\\n複数行のテキスト。", "This is a test.\\nMultiple lines of text."],
            ["3", "00:00:07,000", "00:00:09,000", "最後の字幕", "Last subtitle"],
            ["4", "00:00:10,000", "00:00:12,000", "", ""],
            ["5", "00:00:13,000", "00:00:15,000", "特殊文字: @#$%^&*()", "Special chars: @#$%^&*()"],
        ]

    def test_export_import_roundtrip(self, sample_subtitles_japanese):
        """エクスポート→インポートの往復テスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            csv_path = Path(f.name)

        try:
            # Step 1: エクスポート
            exporter = CSVExporter()
            exporter.export_for_translation(
                subtitles=sample_subtitles_japanese,
                output_path=str(csv_path),
                source_language="ja",
                target_language="en"
            )

            # ファイルが作成されていることを確認
            assert csv_path.exists(), "CSVファイルが作成されていない"

            # ファイル内容の確認
            with open(csv_path, 'r', encoding='utf-8') as f:
                content = f.read()
                assert "こんにちは、世界！" in content, "日本語テキストがエクスポートされていない"
                assert "00:00:01,000" in content, "タイムコードがエクスポートされていない"

            # Step 2: インポート（翻訳前のデータとして）
            importer = CSVImporter()
            imported_subtitles = importer.import_from_csv(str(csv_path))

            # インポート結果の検証
            assert len(imported_subtitles) == len(sample_subtitles_japanese), "インポートされた字幕数が一致しない"

            for original, imported in zip(sample_subtitles_japanese, imported_subtitles):
                assert imported.index == original.index, f"インデックスが一致しない: {imported.index} != {original.index}"
                assert imported.start_ms == original.start_ms, f"開始時間が一致しない: {imported.start_ms} != {original.start_ms}"
                assert imported.end_ms == original.end_ms, f"終了時間が一致しない: {imported.end_ms} != {original.end_ms}"
                assert imported.text == original.text, f"テキストが一致しない: '{imported.text}' != '{original.text}'"

        finally:
            # クリーンアップ
            if csv_path.exists():
                csv_path.unlink()

    def test_translated_csv_import(self, sample_translated_csv_content):
        """翻訳済みCSVのインポートテスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='') as f:
            csv_path = Path(f.name)
            writer = csv.writer(f)
            writer.writerows(sample_translated_csv_content)

        try:
            # 翻訳済みCSVをインポート
            importer = CSVImporter()
            imported_subtitles = importer.import_translated_csv(str(csv_path))

            # 結果の検証
            assert len(imported_subtitles) == 5, f"期待される字幕数と異なる: {len(imported_subtitles)}"

            # 1番目の字幕の詳細チェック
            first_subtitle = imported_subtitles[0]
            assert first_subtitle.index == 1, "インデックスが正しくない"
            assert first_subtitle.start_ms == 1000, "開始時間が正しくない"
            assert first_subtitle.end_ms == 3000, "終了時間が正しくない"
            assert first_subtitle.text == "Hello, World!", f"翻訳テキストが正しくない: '{first_subtitle.text}'"

            # 複数行テキストのチェック
            second_subtitle = imported_subtitles[1]
            expected_multiline = "This is a test.\nMultiple lines of text."
            assert second_subtitle.text == expected_multiline, f"複数行テキストが正しくない: '{second_subtitle.text}'"

            # 空テキストのチェック
            empty_subtitle = imported_subtitles[3]
            assert empty_subtitle.text == "", f"空テキストが正しくない: '{empty_subtitle.text}'"

        finally:
            # クリーンアップ
            if csv_path.exists():
                csv_path.unlink()

    def test_csv_encoding_handling(self, sample_subtitles_japanese):
        """CSV文字エンコーディングのテスト"""
        encodings_to_test = ['utf-8', 'utf-8-sig']  # BOM付きUTF-8も含む

        for encoding in encodings_to_test:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding=encoding) as f:
                csv_path = Path(f.name)

            try:
                # エクスポート
                exporter = CSVExporter()
                exporter.export_for_translation(
                    subtitles=sample_subtitles_japanese,
                    output_path=str(csv_path),
                    source_language="ja",
                    target_language="en",
                    encoding=encoding
                )

                # インポート
                importer = CSVImporter()
                imported_subtitles = importer.import_from_csv(str(csv_path))

                # 文字化けしていないことを確認
                first_subtitle = imported_subtitles[0]
                assert "こんにちは" in first_subtitle.text, f"エンコーディング '{encoding}' で文字化けが発生"

            finally:
                if csv_path.exists():
                    csv_path.unlink()

    def test_csv_special_characters_handling(self):
        """CSV特殊文字の処理テスト"""
        special_subtitles = [
            SubtitleItem(1, 1000, 3000, 'カンマ含む, テキスト'),
            SubtitleItem(2, 4000, 6000, 'ダブルクォート"含む'),
            SubtitleItem(3, 7000, 9000, "改行\n含む\nテキスト"),
            SubtitleItem(4, 10000, 12000, "タブ\t含む"),
            SubtitleItem(5, 13000, 15000, "両方\"カンマ,改行\n\"含む"),
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            csv_path = Path(f.name)

        try:
            # エクスポート
            exporter = CSVExporter()
            exporter.export_for_translation(
                subtitles=special_subtitles,
                output_path=str(csv_path),
                source_language="ja",
                target_language="en"
            )

            # インポート
            importer = CSVImporter()
            imported_subtitles = importer.import_from_csv(str(csv_path))

            # 特殊文字が正しく処理されていることを確認
            assert len(imported_subtitles) == len(special_subtitles), "特殊文字により字幕数が変わった"

            for original, imported in zip(special_subtitles, imported_subtitles):
                assert imported.text == original.text, f"特殊文字が正しく処理されていない: '{imported.text}' != '{original.text}'"

        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_csv_validation_and_error_handling(self):
        """CSV検証とエラーハンドリングのテスト"""
        importer = CSVImporter()

        # 存在しないファイル
        with pytest.raises(FileNotFoundError):
            importer.import_from_csv("nonexistent_file.csv")

        # 不正なCSV形式
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            csv_path = Path(f.name)
            f.write("Invalid,CSV,Format\n")
            f.write("Missing,Columns\n")

        try:
            with pytest.raises(Exception):  # 適切な例外タイプに変更可能
                importer.import_from_csv(str(csv_path))
        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_large_csv_performance(self):
        """大量データCSVのパフォーマンステスト"""
        import time

        # 大量の字幕データを生成（1000項目）
        large_subtitles = []
        for i in range(1000):
            start_ms = i * 2000
            end_ms = start_ms + 1500
            text = f"字幕番号 {i+1}: これは長いテキストサンプルです。パフォーマンステストのために使用されます。"
            large_subtitles.append(SubtitleItem(i+1, start_ms, end_ms, text))

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            csv_path = Path(f.name)

        try:
            # エクスポート時間を測定
            start_time = time.time()
            exporter = CSVExporter()
            exporter.export_for_translation(
                subtitles=large_subtitles,
                output_path=str(csv_path),
                source_language="ja",
                target_language="en"
            )
            export_time = time.time() - start_time

            # インポート時間を測定
            start_time = time.time()
            importer = CSVImporter()
            imported_subtitles = importer.import_from_csv(str(csv_path))
            import_time = time.time() - start_time

            # パフォーマンス検証
            assert export_time < 5.0, f"エクスポートが遅すぎる: {export_time:.2f}秒"
            assert import_time < 5.0, f"インポートが遅すぎる: {import_time:.2f}秒"
            assert len(imported_subtitles) == 1000, "大量データのインポートで字幕数が一致しない"

        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_gas_compatible_format(self, sample_subtitles_japanese):
        """Google Apps Script互換フォーマットのテスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            csv_path = Path(f.name)

        try:
            # GAS互換形式でエクスポート
            exporter = CSVExporter()
            exporter.export_for_gas_translation(
                subtitles=sample_subtitles_japanese,
                output_path=str(csv_path),
                source_language="ja",
                target_language="en"
            )

            # ファイル内容を直接確認
            with open(csv_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # ヘッダー行の確認
            header = lines[0].strip()
            expected_columns = ["Index", "Start Time", "End Time", "Original Text", "Translated Text"]

            for column in expected_columns:
                assert column in header, f"GAS互換ヘッダーに '{column}' が含まれていない"

            # データ行の確認
            assert len(lines) >= 6, "期待されるデータ行数が不足"  # ヘッダー + 5つの字幕

        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_batch_translation_workflow(self, sample_subtitles_japanese):
        """バッチ翻訳ワークフローのテスト"""
        export_path = None
        import_path = None

        try:
            # Step 1: 翻訳用CSVをエクスポート
            with tempfile.NamedTemporaryFile(mode='w', suffix='_export.csv', delete=False, encoding='utf-8') as f:
                export_path = Path(f.name)

            exporter = CSVExporter()
            exporter.export_for_translation(
                subtitles=sample_subtitles_japanese,
                output_path=str(export_path),
                source_language="ja",
                target_language="en"
            )

            # Step 2: 翻訳済みCSVをシミュレート（手動で作成）
            with tempfile.NamedTemporaryFile(mode='w', suffix='_translated.csv', delete=False, encoding='utf-8', newline='') as f:
                import_path = Path(f.name)
                writer = csv.writer(f)

                # ヘッダー
                writer.writerow(["Index", "Start Time", "End Time", "Original Text", "Translated Text"])

                # 翻訳データ
                translations = [
                    "Hello, World!",
                    "This is a test.\\nMultiple lines of text.",
                    "Last subtitle",
                    "",
                    "Special chars: @#$%^&*()"
                ]

                for i, subtitle in enumerate(sample_subtitles_japanese):
                    start_time = f"{subtitle.start_ms // 3600000:02d}:{(subtitle.start_ms % 3600000) // 60000:02d}:{(subtitle.start_ms % 60000) // 1000:02d},{subtitle.start_ms % 1000:03d}"
                    end_time = f"{subtitle.end_ms // 3600000:02d}:{(subtitle.end_ms % 3600000) // 60000:02d}:{(subtitle.end_ms % 60000) // 1000:02d},{subtitle.end_ms % 1000:03d}"

                    writer.writerow([
                        subtitle.index,
                        start_time,
                        end_time,
                        subtitle.text.replace('\n', '\\n'),
                        translations[i]
                    ])

            # Step 3: 翻訳済みCSVをインポート
            importer = CSVImporter()
            translated_subtitles = importer.import_translated_csv(str(import_path))

            # Step 4: 結果の検証
            assert len(translated_subtitles) == len(sample_subtitles_japanese), "翻訳後の字幕数が一致しない"

            # 翻訳されたテキストの確認
            assert translated_subtitles[0].text == "Hello, World!", "1番目の翻訳が正しくない"
            assert "This is a test.\nMultiple lines of text." == translated_subtitles[1].text, "2番目の翻訳（複数行）が正しくない"

        finally:
            # クリーンアップ
            for path in [export_path, import_path]:
                if path and path.exists():
                    path.unlink()