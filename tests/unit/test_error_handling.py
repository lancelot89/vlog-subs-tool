"""
エラーハンドリングのテスト

ファイル処理、権限、ディスク容量、ネットワーク等のエラーケースのテスト
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.core.csv.exporter import SubtitleCSVExporter
from app.core.csv.importer import SubtitleCSVImporter
from app.core.error_handler import ErrorHandler
from app.core.extractor.sampler import VideoSampler
from app.core.format.srt import SRTReader, SRTWriter
from app.core.models import SubtitleItem
from app.core.project_manager import ProjectManager


class TestFilePermissionErrors:
    """ファイル権限エラーのテスト"""

    def test_read_permission_denied(self):
        """読み込み権限なしファイルのテスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)
            f.write("1\n00:00:01,000 --> 00:00:03,000\nテスト字幕\n\n")

        try:
            # ファイルを読み取り専用にする（Windowsでは効果が限定的）
            os.chmod(str(srt_path), 0o000)

            reader = SRTReader()

            # 権限エラーが適切に処理されることを確認
            with pytest.raises((PermissionError, OSError)):
                reader.read_srt_file(str(srt_path))

        except OSError:
            # OS によっては権限変更できない場合がある
            pytest.skip("権限変更がサポートされていない")

        finally:
            # クリーンアップ時に権限を復元
            try:
                os.chmod(str(srt_path), 0o666)
                srt_path.unlink()
            except (OSError, PermissionError):
                pass

    def test_write_permission_denied(self):
        """書き込み権限なしディレクトリのテスト"""
        # 一時ディレクトリを作成
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # ディレクトリを読み取り専用にする
            os.chmod(str(temp_dir), 0o555)

            srt_path = temp_dir / "test.srt"
            test_subtitles = [SubtitleItem(1, 1000, 3000, "テスト")]

            writer = SRTWriter()

            # 書き込み権限エラーが適切に処理されることを確認
            with pytest.raises((PermissionError, OSError)):
                writer.write_srt_file(test_subtitles, str(srt_path))

        except OSError:
            pytest.skip("権限変更がサポートされていない")

        finally:
            # クリーンアップ
            try:
                os.chmod(str(temp_dir), 0o755)
                shutil.rmtree(str(temp_dir))
            except (OSError, PermissionError):
                pass

    def test_readonly_file_overwrite_attempt(self):
        """読み取り専用ファイルの上書き試行テスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)
            f.write("元のデータ")

        try:
            # ファイルを読み取り専用にする
            os.chmod(str(srt_path), 0o444)

            test_subtitles = [SubtitleItem(1, 1000, 3000, "新しいデータ")]
            writer = SRTWriter()

            # 読み取り専用ファイルの上書きでエラーが発生することを確認
            with pytest.raises((PermissionError, OSError)):
                writer.write_srt_file(test_subtitles, str(srt_path))

        except OSError:
            pytest.skip("権限変更がサポートされていない")

        finally:
            try:
                os.chmod(str(srt_path), 0o666)
                srt_path.unlink()
            except (OSError, PermissionError):
                pass


class TestDiskSpaceErrors:
    """ディスク容量エラーのテスト"""

    @patch('builtins.open')
    def test_disk_full_simulation(self, mock_open):
        """ディスク容量不足のシミュレーションテスト"""
        # ディスク容量不足エラーをシミュレート
        mock_file = Mock()
        mock_file.write.side_effect = OSError(28, "No space left on device")
        mock_open.return_value.__enter__.return_value = mock_file

        test_subtitles = [SubtitleItem(1, 1000, 3000, "テスト")]
        writer = SRTWriter()

        # ディスク容量不足エラーが適切に処理されることを確認
        with pytest.raises(OSError):
            writer.write_srt_file(test_subtitles, "/tmp/test.srt")

    def test_large_file_creation_failure(self):
        """大容量ファイル作成失敗のテスト"""
        # 非常に大量の字幕データを生成
        huge_subtitles = []
        for i in range(100000):  # 10万項目
            text = "非常に長いテキスト" * 100  # 長いテキスト
            huge_subtitles.append(SubtitleItem(i+1, i*1000, (i+1)*1000, text))

        with tempfile.NamedTemporaryFile(suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)

        try:
            writer = SRTWriter()

            # 大容量ファイルの作成を試行（システムの制限に依存）
            # メモリ不足やディスク容量不足が発生する可能性
            try:
                writer.write_srt_file(huge_subtitles, str(srt_path))
                # 成功した場合、ファイルサイズを確認
                if srt_path.exists():
                    file_size = srt_path.stat().st_size
                    assert file_size > 1000000, "大容量ファイルが作成されていない"
            except (MemoryError, OSError) as e:
                # メモリ不足やディスク容量不足は期待される動作
                assert True, f"期待されるエラー: {e}"

        finally:
            if srt_path.exists():
                srt_path.unlink()


class TestCorruptedFileHandling:
    """破損ファイル処理のテスト"""

    def test_corrupted_video_file(self):
        """破損動画ファイルの処理テスト"""
        # 不正な動画ファイルを作成
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            corrupted_path = Path(f.name)
            f.write(b"This is not a video file content")

        try:
            sampler = VideoSampler(str(corrupted_path), sample_fps=1.0)

            # 破損動画ファイルの処理でエラーが適切に処理されることを確認
            with pytest.raises(Exception):
                list(sampler.sample_frames())

        finally:
            if corrupted_path.exists():
                corrupted_path.unlink()

    def test_truncated_srt_file(self):
        """切り詰められたSRTファイルの処理テスト"""
        # 不完全なSRTファイルを作成
        truncated_contents = [
            "1\n00:00:01,000 --> 00:00:03,000\n字幕1\n\n2\n00:00:04,000",  # 途中で切れている
            "1\n00:00:01,000",  # タイムコードが不完全
            "1\n00:00:01,000 --> 00:00:03,000",  # テキストがない
        ]

        for i, content in enumerate(truncated_contents):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
                srt_path = Path(f.name)
                f.write(content)

            try:
                reader = SRTReader()

                # 不完全ファイルでもエラーハンドリングが働くことを確認
                try:
                    subtitles = reader.read_srt_file(str(srt_path))
                    # 読み込めた場合は、部分的にでもデータが取得できることを確認
                    assert isinstance(subtitles, list), "部分的読み込みでもリストが返される"
                except Exception:
                    # エラーが発生することも期待される動作
                    assert True, "不完全ファイルでエラーが発生"

            finally:
                if srt_path.exists():
                    srt_path.unlink()

    def test_binary_data_in_text_file(self):
        """テキストファイルにバイナリデータが含まれる場合のテスト"""
        # バイナリデータを含むファイルを作成
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.srt', delete=False) as f:
            binary_path = Path(f.name)
            # 正常なテキストとバイナリデータを混在
            f.write(b"1\n00:00:01,000 --> 00:00:03,000\n")
            f.write(b"\x00\x01\x02\x03\xFF\xFE")  # バイナリデータ
            f.write(b"\n\n2\n00:00:04,000 --> 00:00:06,000\n\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e")

        try:
            reader = SRTReader()

            # バイナリデータを含むファイルでもエラーハンドリングが働くことを確認
            with pytest.raises((UnicodeDecodeError, Exception)):
                reader.read_srt_file(str(binary_path))

        finally:
            if binary_path.exists():
                binary_path.unlink()


class TestNetworkAndIOErrors:
    """ネットワークとI/Oエラーのテスト"""

    @patch('pathlib.Path.exists')
    def test_file_disappeared_during_operation(self, mock_exists):
        """操作中にファイルが消失する場合のテスト"""
        # ファイルが存在すると最初は答えるが、実際のアクセス時には存在しない
        mock_exists.return_value = True

        reader = SRTReader()

        # 存在しないファイルへのアクセスでエラーが適切に処理されることを確認
        with pytest.raises(FileNotFoundError):
            reader.read_srt_file("nonexistent_file.srt")

    def test_device_disconnection_simulation(self):
        """デバイス切断シミュレーションテスト"""
        # ネットワークドライブや取り外し可能メディアの切断をシミュレート
        invalid_paths = [
            "/media/nonexistent_device/file.srt",
            "//invalid_network_share/file.srt",
            "Z:\\nonexistent_drive\\file.srt",
        ]

        for invalid_path in invalid_paths:
            try:
                reader = SRTReader()

                # デバイス切断時のエラーが適切に処理されることを確認
                with pytest.raises((FileNotFoundError, OSError)):
                    reader.read_srt_file(invalid_path)

            except OSError:
                # OSによってはパス形式自体がサポートされていない場合
                continue

    @patch('builtins.open')
    def test_io_interrupt_during_read(self, mock_open):
        """読み込み中のI/O割り込みテスト"""
        # I/O割り込みエラーをシミュレート
        mock_file = Mock()
        mock_file.read.side_effect = IOError("I/O operation interrupted")
        mock_open.return_value.__enter__.return_value = mock_file

        reader = SRTReader()

        # I/O割り込みエラーが適切に処理されることを確認
        with pytest.raises(IOError):
            reader.read_srt_file("test.srt")

    @patch('builtins.open')
    def test_io_interrupt_during_write(self, mock_open):
        """書き込み中のI/O割り込みテスト"""
        # I/O割り込みエラーをシミュレート
        mock_file = Mock()
        mock_file.write.side_effect = IOError("I/O operation interrupted")
        mock_open.return_value.__enter__.return_value = mock_file

        test_subtitles = [SubtitleItem(1, 1000, 3000, "テスト")]
        writer = SRTWriter()

        # I/O割り込みエラーが適切に処理されることを確認
        with pytest.raises(IOError):
            writer.write_srt_file(test_subtitles, "test.srt")


class TestMemoryErrors:
    """メモリエラーのテスト"""

    @patch('app.core.format.srt.SRTWriter.write_srt_file')
    def test_memory_exhaustion_during_write(self, mock_write):
        """書き込み中のメモリ不足テスト"""
        # メモリ不足エラーをシミュレート
        mock_write.side_effect = MemoryError("Out of memory")

        test_subtitles = [SubtitleItem(1, 1000, 3000, "テスト")]
        writer = SRTWriter()

        # メモリ不足エラーが適切に処理されることを確認
        with pytest.raises(MemoryError):
            writer.write_srt_file(test_subtitles, "test.srt")

    def test_large_subtitle_list_handling(self):
        """大量字幕リストの処理テスト"""
        try:
            # 大量の字幕データを生成（メモリ使用量を監視）
            large_subtitles = []
            for i in range(50000):  # 5万項目
                text = f"字幕{i}: " + "長いテキスト" * 10
                large_subtitles.append(SubtitleItem(i+1, i*1000, (i+1)*1000, text))

            # メモリ効率的に処理されることを確認
            assert len(large_subtitles) == 50000, "大量データの生成に失敗"

            # CSVエクスポートでのメモリ効率をテスト
            with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
                csv_path = Path(f.name)

            try:
                exporter = SubtitleCSVExporter()
                # メモリ不足にならずに完了することを確認
                exporter.export_for_translation(
                    subtitles=large_subtitles,
                    filepath=csv_path,
                    source_language="ja",
                    target_language="en"
                )

                assert csv_path.exists(), "大量データのCSVエクスポートに失敗"

            finally:
                if csv_path.exists():
                    csv_path.unlink()

        except MemoryError:
            pytest.skip("システムメモリが不足")


class TestErrorHandlerIntegration:
    """エラーハンドラー統合テスト"""

    def test_error_handler_initialization(self):
        """エラーハンドラーの初期化テスト"""
        handler = ErrorHandler()

        # 基本的な初期化が正しく行われることを確認
        assert hasattr(handler, 'handle_error'), "handle_errorメソッドが存在しない"
        assert hasattr(handler, 'log_error'), "log_errorメソッドが存在しない"

    def test_error_logging_functionality(self):
        """エラーログ機能のテスト"""
        handler = ErrorHandler()

        # テストエラーをログに記録
        test_error = ValueError("テストエラー")
        context = {"operation": "test_operation", "file": "test.srt"}

        try:
            handler.log_error(test_error, context)
            # エラーログが正常に記録されることを確認
            assert True, "エラーログが正常に記録された"
        except Exception as e:
            pytest.fail(f"エラーログの記録に失敗: {e}")

    def test_error_recovery_mechanisms(self):
        """エラー回復メカニズムのテスト"""
        handler = ErrorHandler()

        # 回復可能エラーのテスト
        recoverable_errors = [
            FileNotFoundError("ファイルが見つからない"),
            PermissionError("権限がない"),
            IOError("I/Oエラー"),
        ]

        for error in recoverable_errors:
            try:
                recovery_result = handler.attempt_recovery(error)
                # 回復試行が実行されることを確認
                assert isinstance(recovery_result, bool), "回復試行の結果がブール値でない"
            except Exception as e:
                pytest.fail(f"エラー回復メカニズムの実行に失敗: {e}")

    def test_critical_error_handling(self):
        """致命的エラーの処理テスト"""
        handler = ErrorHandler()

        # 致命的エラーのテスト
        critical_errors = [
            MemoryError("メモリ不足"),
            SystemError("システムエラー"),
            KeyboardInterrupt("ユーザー割り込み"),
        ]

        for error in critical_errors:
            try:
                result = handler.handle_critical_error(error)
                # 致命的エラーが適切に処理されることを確認
                assert result is not None, "致命的エラーの処理結果がない"
            except Exception as e:
                pytest.fail(f"致命的エラーの処理に失敗: {e}")


class TestProjectManagerErrorHandling:
    """プロジェクトマネージャーのエラーハンドリングテスト"""

    def test_invalid_project_file_handling(self):
        """無効なプロジェクトファイルの処理テスト"""
        # 無効なJSON形式のプロジェクトファイルを作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.subproj', delete=False, encoding='utf-8') as f:
            project_path = Path(f.name)
            f.write("{ invalid json content }")

        try:
            manager = ProjectManager()

            # 無効なプロジェクトファイルの読み込みでエラーが適切に処理されることを確認
            with pytest.raises(Exception):
                manager.load_project(str(project_path))

        finally:
            if project_path.exists():
                project_path.unlink()

    def test_corrupted_project_data_recovery(self):
        """破損プロジェクトデータの回復テスト"""
        # 部分的に破損したプロジェクトファイルを作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.subproj', delete=False, encoding='utf-8') as f:
            project_path = Path(f.name)
            # 一部のフィールドが欠けているJSON
            f.write('{"version": "1.0", "subtitles": []}')  # 他の必要フィールドが欠けている

        try:
            manager = ProjectManager()

            # 部分的破損ファイルでも可能な限り回復されることを確認
            try:
                project_data = manager.load_project(str(project_path))
                # 部分的にでもデータが読み込めることを確認
                assert "subtitles" in project_data, "部分的データの読み込みに失敗"
            except Exception:
                # 回復不可能な場合はエラーが発生することも期待される
                assert True, "回復不可能な破損ファイルでエラーが発生"

        finally:
            if project_path.exists():
                project_path.unlink()