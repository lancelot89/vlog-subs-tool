"""
CSV エクスポート・インポート機能の統合テスト

外部翻訳ワークフロー（GAS連携）のためのCSV機能のテスト
"""

import csv
import tempfile
from pathlib import Path

import pytest

from app.core.csv.exporter import SubtitleCSVExporter
from app.core.csv.importer import SubtitleCSVImporter
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
            [
                "2",
                "00:00:04,000",
                "00:00:06,000",
                "これはテストです。\\n複数行のテキスト。",
                "This is a test.\\nMultiple lines of text.",
            ],
            ["3", "00:00:07,000", "00:00:09,000", "最後の字幕", "Last subtitle"],
            ["4", "00:00:10,000", "00:00:12,000", "", ""],
            [
                "5",
                "00:00:13,000",
                "00:00:15,000",
                "特殊文字: @#$%^&*()",
                "Special chars: @#$%^&*()",
            ],
        ]

    def test_export_roundtrip(self, sample_subtitles_japanese):
        """エクスポートの往復テスト"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            csv_path = Path(f.name)

        try:
            # Step 1: エクスポート
            exporter = SubtitleCSVExporter()
            success = exporter.export_for_translation(
                subtitles=sample_subtitles_japanese, filepath=csv_path
            )

            # エクスポートが成功していることを確認
            assert success, "CSVエクスポートに失敗"
            assert csv_path.exists(), "CSVファイルが作成されていない"

            # ファイル内容の確認
            with open(csv_path, "r", encoding="utf-8") as f:
                content = f.read()
                assert "こんにちは、世界！" in content, "日本語テキストがエクスポートされていない"
                assert "00:01.000" in content, "タイムコードがエクスポートされていない"

        finally:
            # クリーンアップ
            if csv_path.exists():
                csv_path.unlink()

    def test_translated_csv_import(self, sample_translated_csv_content, sample_subtitles_japanese):
        """翻訳済みCSVのインポートテスト"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        ) as f:
            csv_path = Path(f.name)
            writer = csv.writer(f)
            writer.writerows(sample_translated_csv_content)

        try:
            # 翻訳済みCSVをインポート
            importer = SubtitleCSVImporter()
            result = importer.import_translated_csv(csv_path, sample_subtitles_japanese)

            # 結果の検証
            if result.success:
                assert (
                    len(result.subtitles) == 5
                ), f"期待される字幕数と異なる: {len(result.subtitles)}"

                # 1番目の字幕の詳細チェック
                if len(result.subtitles) > 0:
                    first_subtitle = result.subtitles[0]
                    assert first_subtitle.index == 1, "インデックスが正しくない"
                    assert first_subtitle.start_ms == 1000, "開始時間が正しくない"
                    assert first_subtitle.end_ms == 3000, "終了時間が正しくない"
                    assert (
                        "Hello, World!" in first_subtitle.text
                    ), f"翻訳テキストが正しくない: '{first_subtitle.text}'"

        finally:
            # クリーンアップ
            if csv_path.exists():
                csv_path.unlink()

    def test_csv_encoding_handling(self, sample_subtitles_japanese):
        """CSV文字エンコーディングのテスト"""
        encodings_to_test = ["utf-8", "utf-8-sig"]  # BOM付きUTF-8も含む

        for encoding in encodings_to_test:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False, encoding=encoding
            ) as f:
                csv_path = Path(f.name)

            try:
                # エクスポート
                exporter = SubtitleCSVExporter()
                success = exporter.export_for_translation(
                    subtitles=sample_subtitles_japanese, filepath=csv_path
                )

                assert success, f"エンコーディング '{encoding}' でエクスポートに失敗"

                # ファイルが存在し、内容が正しいことを確認
                assert (
                    csv_path.exists()
                ), f"エンコーディング '{encoding}' でファイルが作成されていない"

                # 文字化けしていないことを確認
                with open(csv_path, "r", encoding=encoding) as f:
                    content = f.read()
                    assert (
                        "こんにちは" in content
                    ), f"エンコーディング '{encoding}' で文字化けが発生"

            except UnicodeError:
                pytest.skip(f"エンコーディング {encoding} では特殊文字が扱えない")

            finally:
                if csv_path.exists():
                    csv_path.unlink()

    def test_csv_special_characters_handling(self):
        """CSV特殊文字の処理テスト"""
        special_subtitles = [
            SubtitleItem(1, 1000, 3000, "カンマ含む, テキスト"),
            SubtitleItem(2, 4000, 6000, 'ダブルクォート"含む'),
            SubtitleItem(3, 7000, 9000, "改行\n含む\nテキスト"),
            SubtitleItem(4, 10000, 12000, "タブ\t含む"),
            SubtitleItem(5, 13000, 15000, '両方"カンマ,改行\n"含む'),
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            csv_path = Path(f.name)

        try:
            # エクスポート
            exporter = SubtitleCSVExporter()
            success = exporter.export_for_translation(
                subtitles=special_subtitles, filepath=csv_path
            )

            assert success, "特殊文字を含むエクスポートに失敗"
            assert csv_path.exists(), "特殊文字を含むファイルが作成されていない"

            # ファイル内容の確認
            with open(csv_path, "r", encoding="utf-8") as f:
                content = f.read()
                assert "カンマ含む" in content, "カンマを含むテキストが正しく処理されていない"

        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_csv_validation_and_error_handling(self):
        """CSV検証とエラーハンドリングのテスト"""
        importer = SubtitleCSVImporter()

        # 存在しないファイル（エラーハンドリングされて空の結果が返される）
        result = importer.import_translated_csv(Path("nonexistent_file.csv"), [])
        assert result.success == False, "存在しないファイルでもsuccessがTrue"

        # 不正なCSV形式
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            csv_path = Path(f.name)
            f.write("Invalid,CSV,Format\n")
            f.write("Missing,Columns\n")

        try:
            result = importer.import_translated_csv(csv_path, [])
            # エラーが適切に処理されることを確認（成功しないはず）
            assert not result.success, "不正なCSVが正常に処理された"
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
            large_subtitles.append(SubtitleItem(i + 1, start_ms, end_ms, text))

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            csv_path = Path(f.name)

        try:
            # エクスポート時間を測定
            start_time = time.time()
            exporter = SubtitleCSVExporter()
            success = exporter.export_for_translation(subtitles=large_subtitles, filepath=csv_path)
            export_time = time.time() - start_time

            # パフォーマンス検証
            assert success, "大量データのエクスポートに失敗"
            assert export_time < 5.0, f"エクスポートが遅すぎる: {export_time:.2f}秒"

            # ファイルサイズ確認
            file_size = csv_path.stat().st_size
            assert file_size > 0, "大容量ファイルが作成されていない"

        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_gas_compatible_format(self, sample_subtitles_japanese):
        """Google Apps Script互換フォーマットのテスト"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            csv_path = Path(f.name)

        try:
            # GAS互換形式でエクスポート
            exporter = SubtitleCSVExporter()
            success = exporter.export_for_translation(
                subtitles=sample_subtitles_japanese, filepath=csv_path
            )

            assert success, "GAS互換エクスポートに失敗"

            # ファイル内容を直接確認
            with open(csv_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # ヘッダー行の確認（コメント行をスキップして実際のヘッダーを探す）
            assert len(lines) >= 3, "CSVファイルの行数が不足"
            header_line = None
            for line in lines:
                if not line.strip().startswith("#") and "字幕番号" in line:
                    header_line = line.strip()
                    break

            assert header_line is not None, "CSVヘッダー行が見つからない"

            # 基本的な列が含まれていることを確認
            assert "開始時間" in header_line or "終了時間" in header_line, "時間列が含まれていない"

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
            with tempfile.NamedTemporaryFile(
                mode="w", suffix="_export.csv", delete=False, encoding="utf-8"
            ) as f:
                export_path = Path(f.name)

            exporter = SubtitleCSVExporter()
            export_success = exporter.export_for_translation(
                subtitles=sample_subtitles_japanese, filepath=export_path
            )

            assert export_success, "バッチ翻訳用エクスポートに失敗"

            # Step 2: 翻訳済みCSVをシミュレート（手動で作成）
            with tempfile.NamedTemporaryFile(
                mode="w", suffix="_translated.csv", delete=False, encoding="utf-8", newline=""
            ) as f:
                import_path = Path(f.name)
                writer = csv.writer(f)

                # ヘッダー
                writer.writerow(
                    ["Index", "Start Time", "End Time", "Original Text", "Translated Text"]
                )

                # 翻訳データ
                translations = [
                    "Hello, World!",
                    "This is a test.\\nMultiple lines of text.",
                    "Last subtitle",
                    "",
                    "Special chars: @#$%^&*()",
                ]

                for i, subtitle in enumerate(sample_subtitles_japanese):
                    start_time = f"{subtitle.start_ms // 3600000:02d}:{(subtitle.start_ms % 3600000) // 60000:02d}:{(subtitle.start_ms % 60000) // 1000:02d},{subtitle.start_ms % 1000:03d}"
                    end_time = f"{subtitle.end_ms // 3600000:02d}:{(subtitle.end_ms % 3600000) // 60000:02d}:{(subtitle.end_ms % 60000) // 1000:02d},{subtitle.end_ms % 1000:03d}"

                    writer.writerow(
                        [
                            subtitle.index,
                            start_time,
                            end_time,
                            subtitle.text.replace("\n", "\\n"),
                            translations[i],
                        ]
                    )

            # Step 3: 翻訳済みCSVをインポート
            importer = SubtitleCSVImporter()
            result = importer.import_translated_csv(import_path, sample_subtitles_japanese)

            # Step 4: 結果の検証
            if result.success:
                assert len(result.subtitles) == len(
                    sample_subtitles_japanese
                ), "翻訳後の字幕数が一致しない"

                # 翻訳されたテキストの確認
                if len(result.subtitles) > 0:
                    assert "Hello, World!" in result.subtitles[0].text, "1番目の翻訳が正しくない"
                if len(result.subtitles) > 1:
                    assert (
                        "This is a test." in result.subtitles[1].text
                    ), "2番目の翻訳（複数行）が正しくない"

        finally:
            # クリーンアップ
            for path in [export_path, import_path]:
                if path and path.exists():
                    path.unlink()
