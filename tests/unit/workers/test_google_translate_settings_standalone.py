#!/usr/bin/env python3
"""
GoogleTranslateSettingsのスタンドアロンテスト
依存関係なしでエラーを再現
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# GoogleTranslateSettingsのモック（実際の実装と同じ）
@dataclass
class MockGoogleTranslateSettings:
    """Google Translate設定（実際の実装）"""
    project_id: str
    location: str = "global"
    api_key: Optional[str] = None
    service_account_path: Optional[str] = None
    glossary_id: Optional[str] = None
    formality: Optional[str] = None


def test_current_error_case():
    """現在のエラーケース: credentials_pathパラメータが存在しない"""
    print("=== 現在のエラーケースのテスト ===")

    try:
        settings = MockGoogleTranslateSettings(
            credentials_path="",  # このパラメータは存在しない
            glossary_id=None
        )
        print("❌ エラーが発生するはずでした")
        return False
    except TypeError as e:
        error_msg = str(e)
        print(f"✅ 期待通りエラーが発生: {error_msg}")
        assert "unexpected keyword argument 'credentials_path'" in error_msg
        return True


def test_correct_constructor():
    """正しいコンストラクタの使用方法"""
    print("\n=== 正しいコンストラクタのテスト ===")

    try:
        # 実際のパラメータ名を使用
        settings = MockGoogleTranslateSettings(
            project_id="test-project",
            location="global",
            service_account_path="",  # 正しいパラメータ名
            glossary_id=None
        )

        print("✅ 正しいコンストラクタで作成成功")
        print(f"  project_id: {settings.project_id}")
        print(f"  service_account_path: {settings.service_account_path}")
        print(f"  glossary_id: {settings.glossary_id}")
        return True

    except Exception as e:
        print(f"❌ 正しい構築に失敗: {e}")
        return False


def demonstrate_worker_error():
    """TranslationExportWorkerでのエラー発生パターンを再現"""
    print("\n=== TranslationExportWorkerエラーパターンのシミュレーション ===")

    # 現在のTranslationExportWorkerの設定準備ロジック
    def prepare_provider_settings(provider_type: str) -> dict:
        if provider_type == "google":
            return {
                "credentials_path": "",  # ❌ 間違ったパラメータ名
                "glossary_id": None
            }
        return {}

    # 設定作成の試行
    provider_settings = prepare_provider_settings("google")
    print(f"問題のある設定: {provider_settings}")

    try:
        settings = MockGoogleTranslateSettings(**provider_settings)
        print("❌ エラーが発生するはずでした")
        return False
    except TypeError as e:
        print(f"✅ TranslationExportWorkerと同じエラーを再現: {e}")
        return True


def test_corrected_worker_pattern():
    """修正後のTranslationExportWorkerパターン"""
    print("\n=== 修正後のワーカーパターンのテスト ===")

    # 修正後の設定準備ロジック
    def prepare_provider_settings_fixed(provider_type: str) -> dict:
        if provider_type == "google":
            return {
                "project_id": "test-project",
                "service_account_path": "",  # ✅ 正しいパラメータ名
                "glossary_id": None
            }
        return {}

    # 修正後の設定作成
    provider_settings = prepare_provider_settings_fixed("google")
    print(f"修正後の設定: {provider_settings}")

    try:
        settings = MockGoogleTranslateSettings(**provider_settings)
        print("✅ 修正後のパターンで作成成功")
        print(f"  project_id: {settings.project_id}")
        print(f"  service_account_path: {settings.service_account_path}")
        return True
    except Exception as e:
        print(f"❌ 修正後の構築に失敗: {e}")
        return False


if __name__ == "__main__":
    print("GoogleTranslateSettingsエラー再現テスト開始...\n")

    success_count = 0
    total_tests = 4

    if test_current_error_case():
        success_count += 1

    if test_correct_constructor():
        success_count += 1

    if demonstrate_worker_error():
        success_count += 1

    if test_corrected_worker_pattern():
        success_count += 1

    print(f"\n=== テスト結果: {success_count}/{total_tests} 成功 ===")

    if success_count == total_tests:
        print("🎉 すべてのテストが成功しました！")
        print("\n修正必要事項:")
        print("1. TranslationExportWorkerの_prepare_provider_settingsメソッド")
        print("   - 'credentials_path' → 'service_account_path'に変更")
        print("   - 'project_id'パラメータを追加")
    else:
        print("❌ 一部のテストが失敗しました")
        sys.exit(1)