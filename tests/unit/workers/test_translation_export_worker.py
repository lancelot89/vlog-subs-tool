#!/usr/bin/env python3
"""
TranslationExportWorkerのテスト
GoogleTranslateSettingsのコンストラクタエラーを再現・修正
"""

import sys
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.core.models import SubtitleItem
from app.core.translate.provider_google import GoogleTranslateSettings, GoogleTranslateProvider
from app.ui.workers.translation_export_worker import TranslationExportWorker


def test_google_translate_settings_constructor_error():
    """GoogleTranslateSettingsのコンストラクタエラーを再現"""

    # 現在のエラーケース: credentials_pathパラメータが存在しない
    try:
        settings = GoogleTranslateSettings(
            credentials_path="",  # このパラメータが存在しない
            glossary_id=None
        )
        assert False, "エラーが発生するはずでした"
    except TypeError as e:
        assert "unexpected keyword argument 'credentials_path'" in str(e)
        print("✅ GoogleTranslateSettingsコンストラクタエラーを再現しました")


def test_google_translate_settings_correct_constructor():
    """正しいコンストラクタでの作成テスト"""

    # 実際の仕様に合わせた正しいコンストラクタ
    settings = GoogleTranslateSettings(
        project_id="test-project",
        location="global",
        service_account_path="",
        glossary_id=None
    )

    assert settings.project_id == "test-project"
    assert settings.location == "global"
    assert settings.service_account_path == ""
    assert settings.glossary_id is None
    print("✅ 正しいコンストラクタでの作成が成功しました")


def test_translation_export_worker_initialization_error():
    """TranslationExportWorkerでGoogleTranslateSettings初期化エラーを再現"""

    # テスト用字幕データ
    subtitles = [
        SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="こんにちは"),
        SubtitleItem(index=2, start_ms=3000, end_ms=4000, text="さようなら")
    ]

    # 一時出力フォルダ
    with tempfile.TemporaryDirectory() as temp_dir:
        output_folder = Path(temp_dir)

        # 問題のあるワーカー作成（credentials_pathを使っている）
        worker = TranslationExportWorker(
            subtitles=subtitles,
            target_languages=["en"],
            provider_type="google",
            provider_settings={
                "credentials_path": "",  # 間違ったパラメータ名
                "glossary_id": None
            },
            output_folder=output_folder,
            video_basename="test_video"
        )

        # 初期化時にエラーが発生するはず
        try:
            translator = worker._initialize_translator()
            assert False, "エラーが発生するはずでした"
        except TypeError as e:
            assert "unexpected keyword argument 'credentials_path'" in str(e)
            print("✅ TranslationExportWorkerでの初期化エラーを再現しました")


def test_translation_export_worker_correct_initialization():
    """修正後のTranslationExportWorkerの初期化テスト"""

    # テスト用字幕データ
    subtitles = [
        SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="こんにちは"),
        SubtitleItem(index=2, start_ms=3000, end_ms=4000, text="さようなら")
    ]

    # 一時出力フォルダ
    with tempfile.TemporaryDirectory() as temp_dir:
        output_folder = Path(temp_dir)

        # 修正後のワーカー作成（正しいパラメータ名を使用）
        worker = TranslationExportWorker(
            subtitles=subtitles,
            target_languages=["en"],
            provider_type="google",
            provider_settings={
                "project_id": "test-project",
                "service_account_path": "",  # 正しいパラメータ名
                "glossary_id": None
            },
            output_folder=output_folder,
            video_basename="test_video"
        )

        # 初期化は成功するはず（ただし、実際のAPIは呼び出されない）
        try:
            translator = worker._initialize_translator()
            assert isinstance(translator, GoogleTranslateProvider)
            print("✅ 修正後のTranslationExportWorker初期化が成功しました")
        except Exception as e:
            # Google Cloud APIが利用できない場合のエラーは許可
            if "PACKAGE_MISSING" in str(e) or "Google Cloud Translate API" in str(e):
                print("⚠️ Google Cloud Translate APIが利用できません（テスト環境では正常）")
            else:
                raise


if __name__ == "__main__":
    print("TranslationExportWorkerのテスト開始...")

    try:
        test_google_translate_settings_constructor_error()
    except Exception as e:
        print(f"❌ GoogleTranslateSettings構築エラーテスト失敗: {e}")

    try:
        test_google_translate_settings_correct_constructor()
    except Exception as e:
        print(f"❌ 正しい構築テスト失敗: {e}")

    try:
        test_translation_export_worker_initialization_error()
    except Exception as e:
        print(f"❌ ワーカー初期化エラーテスト失敗: {e}")

    try:
        test_translation_export_worker_correct_initialization()
    except Exception as e:
        print(f"❌ 修正後ワーカー初期化テスト失敗: {e}")

    print("\nテスト完了")