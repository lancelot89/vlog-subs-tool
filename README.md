# VLog字幕ツール

🎬 VLOG動画から字幕を自動抽出・編集・翻訳・出力する非エンジニア向けデスクトップアプリケーション

## 📋 概要

VLog字幕ツールは、音声なしのVLOG動画に焼き付けられた日本語字幕（ハードサブ）を自動抽出し、編集・翻訳・多言語字幕出力を一貫して行うGUIアプリケーションです。

### 🎯 主要機能

- **📖 OCR字幕抽出**: PaddleOCR/Tesseractによる日本語字幕の自動認識
- **✏️ 直感的編集**: Excel風テーブルでの字幕直接編集・プレビュー同期
- **🌍 多言語翻訳**: Google Cloud Translation・DeepL API・CSV外部連携対応
- **📁 SRT出力**: 日本語・多言語SRTファイルの一括生成
- **🔍 品質管理**: 行長・表示時間・重複・時間矛盾の自動チェック

## 🚀 クイックスタート

### 必要環境

- **OS**: Windows 10/11, macOS 10.15+, Linux (Ubuntu 20.04+)
- **Python**: 3.8+ (開発・ソースコード実行時)
- **RAM**: 4GB以上推奨
- **ストレージ**: 2GB以上の空き容量

### Linux環境での追加設定

Linux環境で日本語UIを正しく表示するために、以下の追加設定が必要です：

#### 日本語フォントのインストール
```bash
# Ubuntu/Debian系
sudo apt update
sudo apt install fonts-noto-cjk fonts-noto-cjk-extra fonts-dejavu

# CentOS/RHEL系
sudo yum install google-noto-cjk-fonts dejavu-sans-fonts

# Arch Linux
sudo pacman -S noto-fonts-cjk ttf-dejavu
```

#### ロケール設定（オプション）
```bash
# 日本語ロケールの有効化
sudo locale-gen ja_JP.UTF-8

# 環境変数設定（シェル設定ファイルに追加）
export LANG=ja_JP.UTF-8
export LC_ALL=ja_JP.UTF-8
```

### インストール

#### 方法1: バイナリ版（推奨）

**📦 [リリースページ](https://github.com/lancelot89/vlog-subs-tool/releases/latest)** からプラットフォーム別のファイルをダウンロード：

- **Windows**: `vlog-subs-tool.exe` (準備中)
- **macOS**: `VLog字幕ツール.app` (準備中)  
- **Linux**: `vlog-subs-tool.AppImage` (準備中)

> **注意**: バイナリファイルは現在準備中です。ソースコードから実行をご利用ください。

#### 方法2: ソースコードから実行
```bash
# リポジトリのクローン
git clone https://github.com/lancelot89/vlog-subs-tool.git
cd vlog-subs-tool

# 仮想環境作成（推奨）
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 依存関係のインストール
pip install -e .

# アプリケーション起動
python -m app.main

# テスト実行（開発者向け）
pip install -e ".[dev]"
python -m pytest tests/unit/test_models.py -v
```

### 基本的な使い方

1. **動画読み込み**: 「動画を開く」で対象ファイルを選択
2. **字幕抽出**: 「自動抽出」ボタンでOCR実行
3. **編集**: 右側テーブルで字幕内容・タイミングを直接編集
4. **品質チェック**: 「QCチェック」で問題箇所を確認
5. **出力**: 「SRT出力」で字幕ファイルを保存

## 🚨 トラブルシューティング

### よくある問題と解決方法

#### 🐛 「ModuleNotFoundError: No module named 'ui'」エラー

**症状**: GitHubからZIPをダウンロードして直接実行すると以下のエラーが発生
```
Traceback (most recent call last):
  File "main.py", line 16, in <module>
ModuleNotFoundError: No module named 'ui'
```

**解決方法**:
```bash
# 1. 依存関係をインストール
pip install -e .

# 2. 推奨実行方法で起動
python -m app.main
```

**Windows環境の場合**:
```cmd
# コマンドプロンプトまたはPowerShellで実行
cd vlog-subs-tool-main
pip install -e .
python -m app.main
```

#### 🐛 「ImportError: No module named 'PySide6'」エラー

**原因**: PySide6やその他の依存パッケージがインストールされていない

**解決方法**:
```bash
# 仮想環境を作成（推奨）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 依存関係をインストール
pip install -e .
```

#### 🐛 Linux環境での日本語文字化け

**解決方法**:
```bash
# 日本語フォントをインストール
sudo apt install fonts-noto-cjk fonts-noto-cjk-extra  # Ubuntu/Debian
sudo yum install google-noto-cjk-fonts                # CentOS/RHEL

# ロケール設定（オプション）
export LANG=ja_JP.UTF-8
export LC_ALL=ja_JP.UTF-8
```

#### 📋 実行方法の優先順位

1. **推奨**: `python -m app.main` （プロジェクトルートから）
2. **次善**: `python app/main.py` （プロジェクトルートから）
3. **非推奨**: `cd app && python main.py` （エラーの原因となりやすい）

## 📖 詳細機能

### OCR字幕抽出

- **エンジン選択**: PaddleOCR（高精度）・Tesseract（軽量）
- **抽出領域**: 自動検出・下段30%固定・手動矩形指定
- **サンプリング**: 3-5fps設定による最適化
- **後処理**: 類似度判定によるテキスト統合・最小表示時間保証

### 編集・プレビュー機能

- **双方向同期**: テーブル選択⇔動画シーク・リアルタイムハイライト
- **字幕操作**: 分割・結合・並び替え・追加・削除
- **区間ループ**: 字幕区間での繰り返し再生
- **字幕オーバーレイ**: 動画上での字幕表示確認

### 翻訳・多言語対応

#### 内蔵API翻訳
- **Google Cloud Translation v3**: プロジェクト・ロケーション・APIキー設定
- **DeepL API**: APIキー・フォーマリティ設定

#### CSV外部翻訳連携
```csv
# エクスポート形式
字幕番号,開始時間,終了時間,原文(ja),翻訳文,翻訳ステータス,翻訳者コメント
1,00:05.000,00:08.000,こんにちは,,未翻訳,
```

- **Google Apps Script連携**: UTF-8 BOM・設定JSON・手順書の自動生成
- **手動翻訳サポート**: Excel・Numbers等での編集ガイド
- **品質検証**: インポート時の妥当性チェック

### QC（品質管理）チェック

| チェック項目 | 説明 | 重要度 |
|-------------|------|--------|
| 行長チェック | 1行42文字制限 | 警告 |
| 最大行数 | 最大2行制限 | 警告 |
| 表示時間 | 1.2-10秒範囲 | 警告/情報 |
| 時間重複 | 字幕間重複検出 | エラー |
| 時間順序 | 開始≦終了検証 | エラー |
| 空文字検出 | 空テキスト検出 | エラー |
| 重複テキスト | 近接同一文字列 | 警告 |
| 読み速度 | 20文字/秒制限 | 警告 |

## 📁 出力ファイル

### SRT字幕ファイル
```
video.ja.srt          # 日本語字幕
video.en.srt          # 英語字幕
video.zh.srt          # 中国語字幕
video.ko.srt          # 韓国語字幕
video.ar.srt          # アラビア語字幕
```

### CSV翻訳ワークフロー
```
subs/
├── video_ja_export.csv           # 翻訳元データ
├── video_en_template.csv         # 英語テンプレート
├── video_translation_config.json # GAS用設定
└── video_翻訳手順.md              # 手順書
```

### プロジェクトファイル
```
project.subproj       # プロジェクト保存（JSON形式）
```

## ⚙️ 設定・カスタマイズ

### OCR設定
- **サンプリングFPS**: 3-5fps（精度 vs 速度）
- **OCRエンジン**: PaddleOCR（既定）・Tesseract（選択式）
- **抽出領域**: 自動検出・下段30%・手動矩形

### 出力設定
- **ファイル名**: `{basename}.{lang}.srt` パターン
- **エンコーディング**: UTF-8（BOMオプション）
- **改行コード**: LF（Unix）・CRLF（Windows）選択

### 翻訳設定
- **Google Cloud Translation**: プロジェクトID・ロケーション・APIキー
- **DeepL**: APIキー・フォーマリティ（default/more/less）
- **整形**: 句読点改行・行長制限・RTL言語対応

## 🛠️ 開発・ビルド

### 開発環境セットアップ

#### 仮想環境での開発（推奨）
```bash
# 仮想環境作成
python3 -m venv venv

# 仮想環境有効化
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 開発用依存関係インストール
pip install -e ".[dev]"

# 開発サーバー起動
python -m app.main
```

#### テスト実行
```bash
# 仮想環境を有効化してからテスト実行
source venv/bin/activate

# 全テスト実行
python -m pytest tests/ -v

# 特定のテストモジュール実行
python -m pytest tests/unit/test_models.py -v

# カバレッジ付きテスト実行
python -m pytest tests/ --cov=app --cov-report=html

# 単体テストのみ実行
python tests/test_runner.py unit

# 統合テストのみ実行  
python tests/test_runner.py integration

# 高速テストのみ実行（時間のかかるテストをスキップ）
python -m pytest tests/ -m "not slow"
```

#### コード品質チェック
```bash
# リント
python -m flake8 app/
python -m mypy app/

# コードフォーマット
python -m black app/
python -m isort app/
```

### バイナリビルド
```bash
# Windows
pyinstaller --onefile --windowed app/main.py

# macOS
pyinstaller --onefile --windowed --name "VLog字幕ツール" app/main.py

# Linux
pyinstaller --onefile app/main.py
```

## 📋 技術仕様

### アーキテクチャ
- **GUI**: PySide6 (Qt for Python)
- **動画処理**: OpenCV + ffmpeg
- **OCR**: PaddleOCR (日本語特化) / Tesseract (汎用)
- **翻訳**: Google Cloud Translation v3 / DeepL API
- **データ**: JSON (プロジェクト) / CSV (翻訳連携) / SRT (出力)

### ディレクトリ構成
```
app/
├── core/              # コアロジック
│   ├── extractor/     # OCR抽出エンジン
│   ├── format/        # SRT・CSV処理
│   ├── qc/           # 品質管理
│   └── models.py     # データモデル
├── ui/               # GUI
│   ├── views/        # 画面・ダイアログ
│   └── main_window.py # メインウィンドウ
└── main.py           # エントリーポイント

tests/
├── unit/             # 単体テスト
│   ├── test_models.py     # データモデルテスト
│   ├── test_srt.py        # SRT処理テスト
│   ├── test_qc_rules.py   # QCルールテスト
│   └── test_csv_modules.py # CSV処理テスト
├── integration/      # 統合テスト
│   └── test_main_window.py # GUIテスト
├── fixtures/         # テストデータ
│   ├── sample.srt         # サンプルSRT
│   └── sample_translation.csv # サンプル翻訳CSV
├── conftest.py       # pytest設定
├── test_runner.py    # カスタムテストランナー
└── README.md         # テスト実行ガイド
```

### テストカバレッジ
- **単体テスト**: コアモジュール・データモデル・フォーマット処理
- **統合テスト**: GUI操作・ウィンドウ連携・ユーザーワークフロー
- **フィクスチャ**: 実データに近いサンプルファイル
- **カスタムランナー**: テストタイプ別実行・カバレッジレポート

## 🤝 コントリビューション

### バグレポート・機能要望
- **Issues**: [GitHub Issues](https://github.com/lancelot89/vlog-subs-tool/issues)
- **サポート**: OCR精度向上・翻訳API追加・UI改善のご提案歓迎

### 開発参加
1. **Fork** このリポジトリ
2. **Feature branch** 作成 (`git checkout -b feature/amazing-feature`)
3. **Commit** 変更 (`git commit -m 'Add amazing feature'`)
4. **Push** to branch (`git push origin feature/amazing-feature`)
5. **Pull Request** 作成

### コーディング規約
- **Python**: PEP 8準拠・型ヒント必須
- **コミット**: Conventional Commits形式
- **テスト**: pytest・カバレッジ80%以上

## 📄 ライセンス

このプロジェクトは [MIT License](LICENSE) のもとで公開されています。

## 🙏 謝辞

- **PaddleOCR**: 高精度日本語OCRエンジン
- **Tesseract**: オープンソースOCRエンジン
- **PySide6**: クロスプラットフォームGUIフレームワーク
- **OpenCV**: 動画・画像処理ライブラリ

## 📞 サポート・お問い合わせ

- **ドキュメント**: [Wiki](https://github.com/lancelot89/vlog-subs-tool/wiki)
- **FAQ**: [よくある質問](https://github.com/lancelot89/vlog-subs-tool/wiki/FAQ)
- **Discussions**: [GitHub Discussions](https://github.com/lancelot89/vlog-subs-tool/discussions)

---

**VLog字幕ツール v1.0** - VLOG動画字幕処理の決定版 🎬✨