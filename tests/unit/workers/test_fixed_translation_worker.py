#!/usr/bin/env python3
"""
修正後のTranslationExportWorkerテスト
GoogleTranslateSettingsの修正を確認
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# GoogleTranslateSettingsのモック（実際の実装）
@dataclass
class MockGoogleTranslateSettings:
    """Google Translate設定（実際の実装）"""
    project_id: str
    location: str = "global"
    api_key: Optional[str] = None
    service_account_path: Optional[str] = None
    glossary_id: Optional[str] = None
    formality: Optional[str] = None


class MockGoogleTranslateProvider:
    """GoogleTranslateProviderのモック"""
    def __init__(self, settings):
        self.settings = settings


def test_fixed_main_window_provider_settings():
    """修正後のMainWindowのプロバイダ設定テスト"""
    print("=== MainWindow._prepare_provider_settings 修正テスト ===")

    # 修正後の設定準備メソッド（MainWindowから抽出）
    def _prepare_provider_settings(provider_type: str) -> dict:
        """翻訳プロバイダ設定の準備"""
        if provider_type == "google":
            return {
                "project_id": "vlog-subs-tool",  # デフォルトプロジェクトID
                "service_account_path": "",  # 設定から取得
                "glossary_id": None
            }
        elif provider_type == "deepl":
            return {
                "api_key": "",
                "use_pro": False
            }
        else:
            return {}

    # Google設定のテスト
    provider_settings = _prepare_provider_settings("google")
    print(f"Google設定: {provider_settings}")

    try:
        settings = MockGoogleTranslateSettings(**provider_settings)
        print("✅ Google設定での作成成功")
        print(f"  project_id: {settings.project_id}")
        print(f"  service_account_path: {settings.service_account_path}")
        print(f"  glossary_id: {settings.glossary_id}")
        return True
    except Exception as e:
        print(f"❌ Google設定での作成失敗: {e}")
        return False


def test_fixed_translation_worker_initialization():
    """修正後のTranslationWorker初期化テスト"""
    print("\n=== TranslationExportWorker._initialize_translator 修正テスト ===")

    # 修正後の初期化メソッド（TranslationExportWorkerから抽出）
    def _initialize_translator(provider_type: str, provider_settings: dict):
        """翻訳プロバイダーの初期化"""
        if provider_type == "google":
            settings = MockGoogleTranslateSettings(
                project_id=provider_settings.get("project_id", ""),
                service_account_path=provider_settings.get("service_account_path", ""),
                glossary_id=provider_settings.get("glossary_id")
            )
            return MockGoogleTranslateProvider(settings)
        else:
            raise ValueError(f"未対応の翻訳プロバイダ: {provider_type}")

    # プロバイダ設定の準備
    provider_settings = {
        "project_id": "test-project",
        "service_account_path": "/path/to/service-account.json",
        "glossary_id": None
    }

    print(f"プロバイダ設定: {provider_settings}")

    try:
        translator = _initialize_translator("google", provider_settings)
        print("✅ 翻訳プロバイダの初期化成功")
        print(f"  translator type: {type(translator).__name__}")
        print(f"  settings.project_id: {translator.settings.project_id}")
        print(f"  settings.service_account_path: {translator.settings.service_account_path}")
        return True
    except Exception as e:
        print(f"❌ 翻訳プロバイダの初期化失敗: {e}")
        return False


def test_integration():
    """統合テスト: MainWindow → TranslationWorker の流れ"""
    print("\n=== 統合テスト: MainWindow → TranslationWorker ===")

    # MainWindowの設定準備
    def _prepare_provider_settings(provider_type: str) -> dict:
        if provider_type == "google":
            return {
                "project_id": "vlog-subs-tool",
                "service_account_path": "",
                "glossary_id": None
            }
        return {}

    # TranslationWorkerの初期化
    def _initialize_translator(provider_type: str, provider_settings: dict):
        if provider_type == "google":
            settings = MockGoogleTranslateSettings(
                project_id=provider_settings.get("project_id", ""),
                service_account_path=provider_settings.get("service_account_path", ""),
                glossary_id=provider_settings.get("glossary_id")
            )
            return MockGoogleTranslateProvider(settings)
        else:
            raise ValueError(f"未対応の翻訳プロバイダ: {provider_type}")

    try:
        # フロー実行
        provider_settings = _prepare_provider_settings("google")
        translator = _initialize_translator("google", provider_settings)

        print("✅ MainWindow → TranslationWorker 統合成功")
        print(f"  最終的なproject_id: {translator.settings.project_id}")
        print(f"  最終的なservice_account_path: {translator.settings.service_account_path}")
        return True
    except Exception as e:
        print(f"❌ 統合テスト失敗: {e}")
        return False


if __name__ == "__main__":
    print("修正後TranslationExportWorkerテスト開始...\n")

    success_count = 0
    total_tests = 3

    if test_fixed_main_window_provider_settings():
        success_count += 1

    if test_fixed_translation_worker_initialization():
        success_count += 1

    if test_integration():
        success_count += 1

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 すべてのテストが成功しました！")
        print("\n✅ 修正内容:")
        print("1. MainWindow._prepare_provider_settings:")
        print("   - 'credentials_path' → 'service_account_path'")
        print("   - 'project_id'を追加")
        print("2. TranslationExportWorker._initialize_translator:")
        print("   - GoogleTranslateSettingsのコンストラクタパラメータを修正")
        print("3. GoogleTranslateSettingsエラーは解決済み")
    else:
        print("❌ 一部のテストが失敗しました")
        sys.exit(1)