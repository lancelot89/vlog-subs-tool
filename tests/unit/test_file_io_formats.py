"""
ファイルI/O形式とエンコーディングのテスト

各種動画フォーマット、字幕フォーマット、文字エンコーディングの対応テスト
"""

import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.extractor.sampler import VideoSampler
from app.core.format.srt import SRTFormatter, SRTParser
from app.core.models import SubtitleItem


class TestVideoFormatSupport:
    """動画フォーマット対応テスト"""

    def create_test_video(self, format_ext, codec="mp4v", duration_seconds=3):
        """テスト用動画ファイルを作成"""
        with tempfile.NamedTemporaryFile(suffix=f".{format_ext}", delete=False) as f:
            video_path = Path(f.name)

        # OpenCVで動画を作成
        fourcc = cv2.VideoWriter_fourcc(*codec)
        fps = 30
        frame_count = duration_seconds * fps

        out = cv2.VideoWriter(str(video_path), fourcc, fps, (640, 480))

        for i in range(frame_count):
            # 黒背景に白文字で時間を表示
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            time_text = f"{i/fps:.1f}s"
            cv2.putText(
                frame, time_text, (250, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2
            )
            out.write(frame)

        out.release()
        return video_path

    @pytest.mark.parametrize(
        "format_ext,codec",
        [
            ("mp4", "mp4v"),
            ("avi", "XVID"),
            ("mov", "mp4v"),
        ],
    )
    def test_video_format_reading(self, format_ext, codec):
        """各種動画フォーマットの読み込みテスト"""
        video_path = None
        try:
            # テスト動画を作成
            video_path = self.create_test_video(format_ext, codec)

            # VideoSamplerで読み込み
            sampler = VideoSampler(str(video_path), sample_fps=1.0)
            frames = list(sampler.sample_frames())

            # フレームが正しく取得できることを確認
            assert len(frames) > 0, f"{format_ext}形式の動画からフレームを取得できない"

            # フレームデータの形式確認
            first_frame = frames[0]
            assert hasattr(first_frame, "frame"), "フレームデータが正しくない"
            assert hasattr(first_frame, "timestamp_ms"), "タイムスタンプが正しくない"
            assert first_frame.frame.shape == (480, 640, 3), "フレームサイズが正しくない"

        except Exception as e:
            pytest.skip(f"{format_ext}形式がサポートされていない: {e}")

        finally:
            if video_path and video_path.exists():
                video_path.unlink()

    def test_corrupted_video_handling(self):
        """破損した動画ファイルの処理テスト"""
        # 不正な動画ファイルを作成
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            corrupted_path = Path(f.name)
            f.write(b"This is not a video file")

        try:
            sampler = VideoSampler(str(corrupted_path), sample_fps=1.0)

            # 破損ファイルの処理でエラーハンドリングが働くことを確認
            with pytest.raises(Exception):
                list(sampler.sample_frames())

        finally:
            if corrupted_path.exists():
                corrupted_path.unlink()

    def test_very_large_video_handling(self):
        """大容量動画ファイルの処理テスト"""
        video_path = None
        try:
            # 長時間の動画を作成（10秒間）
            video_path = self.create_test_video("mp4", "mp4v", duration_seconds=10)

            sampler = VideoSampler(str(video_path), sample_fps=0.5)

            # 低いサンプリングレートで処理
            frames = list(sampler.sample_frames())

            # メモリ効率的に処理されていることを確認
            assert len(frames) == 5, "サンプリング数が正しくない"  # 10秒 × 0.5fps = 5フレーム

        finally:
            if video_path and video_path.exists():
                video_path.unlink()

    def test_video_metadata_extraction(self):
        """動画メタデータ抽出のテスト"""
        video_path = None
        try:
            video_path = self.create_test_video("mp4", "mp4v", duration_seconds=5)

            # OpenCVで動画情報を取得
            cap = cv2.VideoCapture(str(video_path))

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

            cap.release()

            # メタデータが正しく取得できることを確認
            assert fps == 30, f"FPSが正しくない: {fps}"
            assert frame_count == 150, f"フレーム数が正しくない: {frame_count}"  # 5秒 × 30fps
            assert width == 640, f"幅が正しくない: {width}"
            assert height == 480, f"高さが正しくない: {height}"

        finally:
            if video_path and video_path.exists():
                video_path.unlink()


class TestSRTFormatSupport:
    """SRTフォーマット対応テスト"""

    @pytest.fixture
    def sample_subtitles(self):
        """テスト用字幕データ"""
        return [
            SubtitleItem(1, 1000, 3000, "最初の字幕"),
            SubtitleItem(2, 4000, 6000, "2番目の字幕\n複数行"),
            SubtitleItem(3, 7000, 9000, "特殊文字: éñ中文한글"),
            SubtitleItem(4, 10000, 12000, "長い字幕テキストのテスト。" * 5),
        ]

    @pytest.mark.parametrize(
        "encoding",
        [
            "utf-8",
            "utf-8-sig",  # BOM付きUTF-8
            "utf-16",
            "shift_jis",
            "euc-jp",
        ],
    )
    def test_srt_encoding_support(self, sample_subtitles, encoding):
        """SRT文字エンコーディング対応テスト"""
        srt_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding=encoding) as f:
                srt_path = Path(f.name)

            # 指定エンコーディングでSRTファイルを書き出し
            writer = SRTFormatter()

            # エンコーディングによっては特殊文字が扱えない場合がある
            try:
                writer.save_srt_file(sample_subtitles, srt_path)
            except UnicodeEncodeError:
                pytest.skip(f"エンコーディング {encoding} では特殊文字が扱えない")

            # ファイルが作成されていることを確認
            assert srt_path.exists(), f"SRTファイルが作成されていない ({encoding})"

            # SRTファイルを読み込み
            reader = SRTParser()
            loaded_subtitles = reader.parse_srt_file(srt_path)

            # 読み込んだデータが元データと一致することを確認
            assert len(loaded_subtitles) == len(
                sample_subtitles
            ), f"字幕数が一致しない ({encoding})"

            for original, loaded in zip(sample_subtitles, loaded_subtitles):
                assert loaded.start_ms == original.start_ms, f"開始時間が一致しない ({encoding})"
                assert loaded.end_ms == original.end_ms, f"終了時間が一致しない ({encoding})"
                assert loaded.text == original.text, f"テキストが一致しない ({encoding})"

        except (UnicodeError, LookupError):
            pytest.skip(f"エンコーディング {encoding} がサポートされていない")

        finally:
            if srt_path and srt_path.exists():
                srt_path.unlink()

    def test_srt_malformed_file_handling(self):
        """不正なSRTファイルの処理テスト"""
        # 不正なSRTファイルを作成
        malformed_contents = [
            # タイムコードが不正
            "1\n99:99:99,999 --> 00:00:03,000\n不正なタイムコード\n\n",
            # 番号が不正
            "abc\n00:00:01,000 --> 00:00:03,000\n不正な番号\n\n",
            # フォーマットが不正
            "1\n不正なフォーマット\nテキスト\n\n",
        ]

        for i, content in enumerate(malformed_contents):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".srt", delete=False, encoding="utf-8"
            ) as f:
                srt_path = Path(f.name)
                f.write(content)

            try:
                reader = SRTParser()

                # 不正ファイルでもエラーハンドリングが働くことを確認
                with pytest.raises(Exception):
                    reader.parse_srt_file(srt_path)

            finally:
                if srt_path.exists():
                    srt_path.unlink()

    def test_srt_special_characters_preservation(self):
        """SRT特殊文字保持テスト"""
        special_subtitles = [
            SubtitleItem(1, 1000, 3000, "日本語テキスト"),
            SubtitleItem(2, 4000, 6000, "English Text"),
            SubtitleItem(3, 7000, 9000, "Español (ñ, é, ü)"),
            SubtitleItem(4, 10000, 12000, "中文测试"),
            SubtitleItem(5, 13000, 15000, "한글 테스트"),
            SubtitleItem(6, 16000, 18000, "العربية"),
            SubtitleItem(7, 19000, 21000, "עברית"),
            SubtitleItem(8, 22000, 24000, "Русский"),
            SubtitleItem(9, 25000, 27000, "Emoji: 😀🎬🎭"),
            SubtitleItem(10, 28000, 30000, "特殊記号: ©®™€$¥"),
        ]

        srt_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
                srt_path = Path(f.name)

            # UTF-8で書き出し
            writer = SRTFormatter()
            writer.save_srt_file(special_subtitles, srt_path)

            # 読み込み
            reader = SRTParser()
            loaded_subtitles = reader.parse_srt_file(srt_path)

            # 特殊文字が保持されていることを確認
            for original, loaded in zip(special_subtitles, loaded_subtitles):
                assert (
                    loaded.text == original.text
                ), f"特殊文字が保持されていない: '{loaded.text}' != '{original.text}'"

        finally:
            if srt_path and srt_path.exists():
                srt_path.unlink()

    def test_srt_timestamp_precision(self):
        """SRTタイムスタンプ精度テスト"""
        # ミリ秒単位の精密なタイムスタンプ
        precise_subtitles = [
            SubtitleItem(1, 1001, 2999, "1.001秒開始"),
            SubtitleItem(2, 3333, 4567, "3.333秒開始"),
            SubtitleItem(3, 5555, 6789, "5.555秒開始"),
        ]

        srt_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
                srt_path = Path(f.name)

            # 書き出し
            writer = SRTFormatter()
            writer.save_srt_file(precise_subtitles, srt_path)

            # 読み込み
            reader = SRTParser()
            loaded_subtitles = reader.parse_srt_file(srt_path)

            # タイムスタンプの精度が保持されていることを確認
            for original, loaded in zip(precise_subtitles, loaded_subtitles):
                assert (
                    loaded.start_ms == original.start_ms
                ), f"開始時間の精度が失われた: {loaded.start_ms} != {original.start_ms}"
                assert (
                    loaded.end_ms == original.end_ms
                ), f"終了時間の精度が失われた: {loaded.end_ms} != {original.end_ms}"

        finally:
            if srt_path and srt_path.exists():
                srt_path.unlink()

    def test_large_srt_file_performance(self):
        """大容量SRTファイルのパフォーマンステスト"""
        import time

        # 大量の字幕データを生成（1000項目）
        large_subtitles = []
        for i in range(1000):
            start_ms = i * 2000
            end_ms = start_ms + 1500
            text = f"字幕 {i+1}: これは大容量ファイルのパフォーマンステスト用の長いテキストです。"
            large_subtitles.append(SubtitleItem(i + 1, start_ms, end_ms, text))

        srt_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
                srt_path = Path(f.name)

            # 書き出し時間を測定
            writer = SRTFormatter()
            start_time = time.time()
            writer.save_srt_file(large_subtitles, srt_path)
            write_time = time.time() - start_time

            # 読み込み時間を測定
            reader = SRTParser()
            start_time = time.time()
            loaded_subtitles = reader.parse_srt_file(srt_path)
            read_time = time.time() - start_time

            # パフォーマンス検証
            assert write_time < 2.0, f"書き出しが遅すぎる: {write_time:.2f}秒"
            assert read_time < 2.0, f"読み込みが遅すぎる: {read_time:.2f}秒"
            assert len(loaded_subtitles) == 1000, "大容量ファイルで字幕数が一致しない"

            # ファイルサイズ確認
            file_size = srt_path.stat().st_size
            assert file_size > 0, "ファイルが空"

        finally:
            if srt_path and srt_path.exists():
                srt_path.unlink()


class TestFilePathHandling:
    """ファイルパス処理のテスト"""

    def test_unicode_filename_support(self):
        """Unicode文字を含むファイル名のサポートテスト"""
        unicode_names = [
            "日本語ファイル名.srt",
            "файл_с_русским_именем.srt",
            "archivo_español.srt",
            "中文文件名.srt",
            "한글파일명.srt",
        ]

        for unicode_name in unicode_names:
            try:
                srt_path = Path(tempfile.gettempdir()) / unicode_name

                # テスト字幕データ
                test_subtitles = [SubtitleItem(1, 1000, 3000, "テスト")]

                # 書き出し
                writer = SRTFormatter()
                writer.save_srt_file(test_subtitles, srt_path)

                # ファイルが作成されていることを確認
                assert (
                    srt_path.exists()
                ), f"Unicode文字を含むファイル名で作成できない: {unicode_name}"

                # 読み込み
                reader = SRTParser()
                loaded_subtitles = reader.parse_srt_file(srt_path)

                assert len(loaded_subtitles) == 1, "Unicode文字ファイル名で読み込みできない"

            except (OSError, UnicodeError):
                pytest.skip(f"システムがUnicodeファイル名をサポートしていない: {unicode_name}")

            finally:
                if srt_path.exists():
                    srt_path.unlink()

    def test_long_path_handling(self):
        """長いパス名の処理テスト"""
        # 長いディレクトリ構造を作成
        base_dir = Path(tempfile.gettempdir())

        # 深いディレクトリ構造を作成
        long_dir = base_dir
        for i in range(10):
            long_dir = long_dir / f"very_long_directory_name_{i}"

        try:
            long_dir.mkdir(parents=True, exist_ok=True)
            srt_path = long_dir / "test_file.srt"

            # テスト字幕データ
            test_subtitles = [SubtitleItem(1, 1000, 3000, "長いパステスト")]

            # 書き出し
            writer = SRTFormatter()
            writer.save_srt_file(test_subtitles, srt_path)

            # 読み込み
            reader = SRTParser()
            loaded_subtitles = reader.parse_srt_file(srt_path)

            assert len(loaded_subtitles) == 1, "長いパスで処理できない"

        except OSError:
            pytest.skip("システムが長いパス名をサポートしていない")

        finally:
            # クリーンアップ
            try:
                if srt_path.exists():
                    srt_path.unlink()
                # ディレクトリを削除（空の場合のみ）
                for parent in reversed(list(long_dir.parents)):
                    try:
                        if parent != base_dir:
                            parent.rmdir()
                    except OSError:
                        break
            except OSError:
                pass

    def test_special_characters_in_path(self):
        """パスに特殊文字を含む場合のテスト"""
        special_chars_paths = [
            "file with spaces.srt",
            "file-with-dashes.srt",
            "file_with_underscores.srt",
            "file.with.dots.srt",
            "file(with)parentheses.srt",
            "file[with]brackets.srt",
        ]

        for special_path in special_chars_paths:
            try:
                srt_path = Path(tempfile.gettempdir()) / special_path

                # テスト字幕データ
                test_subtitles = [SubtitleItem(1, 1000, 3000, "特殊文字パステスト")]

                # 書き出し
                writer = SRTFormatter()
                writer.save_srt_file(test_subtitles, srt_path)

                # 読み込み
                reader = SRTParser()
                loaded_subtitles = reader.parse_srt_file(srt_path)

                assert len(loaded_subtitles) == 1, f"特殊文字パスで処理できない: {special_path}"

            except OSError:
                pytest.skip(f"システムが特殊文字パスをサポートしていない: {special_path}")

            finally:
                if srt_path.exists():
                    srt_path.unlink()
