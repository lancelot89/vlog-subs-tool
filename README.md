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
- **⚡ 性能最適化**: プラットフォーム別OCR性能向上システム (Linux 1.2-2倍, Windows/Mac 最適化対応)
- **📊 ベンチマーク**: OCR性能測定・診断・比較機能

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

### ⚡ OCR性能最適化

#### Linux環境（1.2-2倍性能向上）
- **NUMA対応**: マルチソケット環境での最適スレッド配置
- **CPU別特化設定**: Intel/AMD各アーキテクチャ向け最適化
- **OpenBLASバリアント**: Ubuntu環境での最適ライブラリ自動選択
- **メモリサブシステム最適化**: THP、glibc malloc、PaddleOCR設定
- **I/O・キャッシュ最適化**: SSD/HDD判定による読み込み戦略

| 環境 | 性能向上 | 対象CPU例 |
|------|----------|-----------|
| **NUMA環境** | **1.5-2倍** | 2ソケットXeon、EPYC |
| **Intel新世代** | **1.2-1.5倍** | 10世代以降Core、Xeon |
| **AMD Ryzen/EPYC** | **1.3-1.8倍** | Zen 2/3/4アーキテクチャ |
| **一般環境** | **1.1-1.3倍** | その他のLinux環境 |

```python
# 最適化の適用方法
from app.core.linux_optimizer import apply_comprehensive_linux_optimization

# Linux環境で自動的に最適化設定を適用
optimization_results = apply_comprehensive_linux_optimization()
```

#### Windows・macOS環境
- **適応的スレッド設定**: CPU・メモリ構成に応じた最適化
- **プラットフォーム固有最適化**: OS・ハードウェア特性を活用
- **診断・推奨機能**: 性能問題の早期発見と改善提案

### 📊 ベンチマーク・診断機能

#### OCR性能測定
- **標準ベンチマーク画像セット**: 複数パターンのテスト画像で一貫性のある性能測定
- **包括的メトリクス**: 処理時間・認識精度・メモリ使用量・設定情報を記録
- **プラットフォーム間比較**: 異なる環境での性能比較とランキング

#### 診断・推奨システム
- **自動問題検出**: 処理速度・精度・メモリ使用量の異常を自動診断
- **最適化提案**: プラットフォーム固有の改善方法を具体的に提示
- **Issue連携**: 既知の最適化Issue（#127-#132）との自動マッピング

#### ベンチマーク実行方法
```python
# 基本的なベンチマーク実行
from app.core.benchmark import BenchmarkManager

manager = BenchmarkManager()
result = manager.run_comprehensive_analysis()

# 結果の確認
print(f"総合性能スコア: {result['result'].overall_performance_score():.1f}")
print(f"診断結果: {len(result['issues'])}個の問題を検出")
```

#### レポート生成
- **JSON形式**: 詳細データの保存・分析
- **CSV形式**: Excel等での比較分析
- **テキストレポート**: 人間可読な診断結果
- **自動保存**: `~/.vlog-subs-tool/benchmarks/` に履歴保存

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

### 元データCSVエクスポート
- メニュー: **ファイル → 字幕を出力 → CSV出力**
- ツールバー: **CSV出力** ボタン
- 生成内容: 字幕番号・時間情報・本文・文字数などの一覧CSV
- 外部編集やQCチェック用に、抽出直後の字幕をそのままCSV保存できます

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

# ベンチマーク・最適化機能のテスト
python -m pytest tests/unit/test_benchmark.py -v              # ベンチマーク機能
python -m pytest tests/unit/test_linux_optimizer.py -v       # Linux最適化システム
PYTHONPATH=/path/to/project python3 tests/unit/test_benchmark.py    # 直接実行
```

#### ベンチマーク・性能テスト
```bash
# ベンチマークシステムの動作確認
python -c "
from app.core.benchmark import BenchmarkManager
manager = BenchmarkManager()
print('ベンチマーク機能が正常に動作しています')
"

# Linux最適化システムの動作確認
python -c "
from app.core.linux_optimizer import apply_comprehensive_linux_optimization
results = apply_comprehensive_linux_optimization()
print(f'最適化設定: {sum(len(v) for v in results.values())}個の環境変数を設定')
"

# CPU情報の詳細表示（デバッグ用）
python -c "
from app.core.linux_optimizer import CPUDetector
detector = CPUDetector()
cpu_info = detector.detect_cpu_info()
print(f'CPU: {cpu_info.vendor} {cpu_info.model}')
print(f'コア: {cpu_info.cores}/{cpu_info.threads}, 世代: {cpu_info.generation}')
print(f'機能: {cpu_info.features}')
"
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
- **性能最適化**: プラットフォーム別自動設定・NUMA対応・CPU特化調整
- **ベンチマーク**: 標準画像セット・包括的メトリクス・診断システム

### ディレクトリ構成
```
app/
├── core/              # コアロジック
│   ├── extractor/     # OCR抽出エンジン
│   ├── format/        # SRT・CSV処理
│   ├── qc/           # 品質管理
│   ├── benchmark.py  # ベンチマーク・診断システム
│   ├── linux_optimizer.py # Linux性能最適化システム
│   ├── cpu_profiler.py     # CPU情報検出・最適化
│   └── models.py     # データモデル
├── ui/               # GUI
│   ├── views/        # 画面・ダイアログ
│   └── main_window.py # メインウィンドウ
└── main.py           # エントリーポイント

tests/
├── unit/             # 単体テスト
│   ├── test_models.py         # データモデルテスト
│   ├── test_srt.py            # SRT処理テスト
│   ├── test_qc_rules.py       # QCルールテスト
│   ├── test_csv_modules.py    # CSV処理テスト
│   ├── test_benchmark.py      # ベンチマーク機能テスト
│   ├── test_linux_optimizer.py # Linux最適化テスト
│   └── test_cpu_profiler.py   # CPU検出テスト
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
- **単体テスト**: コアモジュール・データモデル・フォーマット処理・性能最適化
- **統合テスト**: GUI操作・ウィンドウ連携・ユーザーワークフロー
- **フィクスチャ**: 実データに近いサンプルファイル
- **カスタムランナー**: テストタイプ別実行・カバレッジレポート
- **ベンチマークテスト**: 33個のテスト（ベンチマーク機能）
- **最適化テスト**: 38個のテスト（Linux性能最適化）
- **総テスト数**: 100+個のテストケースによる包括的品質保証

## 🛠️ トラブルシューティング

### デバッグモード（開発版）
現在のバージョンではexeファイル実行時にターミナル・コンソールが表示されます：
- **目的**: 実行時エラーの詳細確認とデバッグ
- **対象**: Windows・macOS・Linux版
- **ログファイル**: 実行ファイル同階層の `vlog-subs-tool-debug.log`
- **注意**: **v1.0リリース時にこの機能は削除予定**

### よくある問題
- **起動しない**: ログファイルで詳細エラーを確認
- **OCR精度が低い**: ROI設定・解像度・フレームレートを調整
- **メモリ不足**: 大容量動画は分割処理を推奨
- **翻訳失敗**: API設定・ネットワーク・利用制限を確認
- **OCR処理が遅い**: ベンチマーク機能で性能診断・最適化提案を確認
- **Linux環境での性能問題**: 最適化システムの自動適用を確認

### 🔧 性能診断・最適化
```bash
# 性能問題の診断
python -c "
from app.core.benchmark import BenchmarkManager
manager = BenchmarkManager()
result = manager.run_comprehensive_analysis()
print('=== 性能診断レポート ===')
print(result['text_report'])
"

# Linux環境での最適化確認
python -c "
from app.core.linux_optimizer import apply_comprehensive_linux_optimization
import platform
if platform.system() == 'Linux':
    results = apply_comprehensive_linux_optimization()
    print(f'Linux最適化: {sum(len(v) for v in results.values())}個の設定を適用')
else:
    print('Linux環境以外では自動最適化は適用されません')
"
```

### エラー報告
問題が発生した場合は以下を添えてIssueを作成してください：
1. **ログファイル**: `vlog-subs-tool-debug.log`
2. **動作環境**: OS・Python版・依存関係版
3. **再現手順**: 具体的な操作手順
4. **期待動作**: 想定していた結果

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