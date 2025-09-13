# テストガイド

## テスト構造

```
tests/
├── __init__.py
├── conftest.py              # pytest設定とフィクスチャ
├── test_runner.py           # テストランナー
├── unit/                    # 単体テスト
│   ├── test_models.py       # データモデルのテスト
│   ├── test_srt.py          # SRTフォーマット処理のテスト
│   ├── test_qc_rules.py     # QCルールのテスト
│   ├── test_csv_modules.py  # CSV処理のテスト
│   └── test_subtitle_table.py # 字幕テーブルモデルのテスト
├── integration/             # 統合テスト
│   └── test_main_window.py  # メインウィンドウのGUIテスト
└── fixtures/                # テスト用データ
    ├── sample.srt           # サンプルSRTファイル
    ├── sample_translation.csv # サンプル翻訳CSV
    └── test_project.subproj # サンプルプロジェクト
```

## テスト実行方法

### 前提条件

```bash
# 必要なパッケージのインストール
pip install pytest pytest-cov pytest-qt

# または開発用依存関係をインストール
pip install -e ".[dev]"
```

### テスト実行

```bash
# 全テスト実行
python tests/test_runner.py all

# 単体テストのみ実行
python tests/test_runner.py unit

# 統合テストのみ実行
python tests/test_runner.py integration

# pytestを直接使用
pytest tests/ -v

# カバレッジ付きで実行
pytest tests/ --cov=app --cov-report=html
```

### テストマーカー

- `@pytest.mark.unit`: 単体テスト
- `@pytest.mark.integration`: 統合テスト
- `@pytest.mark.gui`: GUIテスト
- `@pytest.mark.ocr`: OCRモデルが必要なテスト
- `@pytest.mark.slow`: 時間のかかるテスト

```bash
# 特定のマーカーのテストのみ実行
pytest tests/ -m "unit"
pytest tests/ -m "not slow"
```

## テスト対象

### 単体テスト

- **models.py**: データモデル（SubtitleItem、Project、Settings等）
- **srt.py**: SRTファイル処理（フォーマット、パース、多言語対応）
- **qc/rules.py**: 品質チェックルール（8種類のチェック機能）
- **csv/**: CSV処理（エクスポート、インポート、翻訳ワークフロー）
- **subtitle_table.py**: テーブルモデル（表示、編集、シグナル）

### 統合テスト

- **main_window.py**: メインウィンドウのGUI機能
  - メニュー・ツールバー構造
  - ウィジェット配置
  - アクション動作
  - キーボードショートカット

## フィクスチャ

### conftest.py で定義

- `qapp`: QApplication インスタンス
- `sample_subtitles`: テスト用字幕データ（3件）
- `test_video_path`: テスト動画ファイルパス
- `temp_dir`: 一時ディレクトリ
- `sample_csv_content`: テスト用CSVデータ

### fixtures/ ディレクトリ

- `sample.srt`: 標準的なSRTファイル
- `sample_translation.csv`: 翻訳済みCSVファイル
- `test_project.subproj`: プロジェクトファイル

## 継続的インテグレーション

### GitHub Actions での実行例

```yaml
- name: Run tests
  run: |
    pip install pytest pytest-cov pytest-qt
    pytest tests/ --cov=app --cov-report=xml
```

### ローカル開発

```bash
# テストウォッチモード
pytest tests/ -f

# 失敗したテストのみ再実行
pytest tests/ --lf

# 詳細出力
pytest tests/ -vvv -s
```

## トラブルシューティング

### GUIテストでの問題

```bash
# Xvfbを使用（Linux CI環境）
xvfb-run -a pytest tests/integration/

# DISPLAY環境変数設定
export DISPLAY=:99
pytest tests/integration/
```

### OCRテスト

OCRモデルが必要なテストは `@pytest.mark.ocr` でマークされています。
モデルがインストールされていない環境では以下でスキップ：

```bash
pytest tests/ -m "not ocr"
```

### パフォーマンス

時間のかかるテストは `@pytest.mark.slow` でマークされています：

```bash
pytest tests/ -m "not slow"  # 高速テストのみ
```