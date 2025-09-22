# 最小構成PyInstallerビルド手順

## 概要

Issue #216対応として、PyInstaller設定を簡素化し、ソース実行と完全同一挙動を最優先にする最小構成ビルド手順です。

## 背景

従来の設定では以下の問題がありました：
- 大量の除外設定（166行）によるモジュール不足
- 複雑なhiddenimports（71個の手動設定）
- カスタムフック（PaddleXスタブ化）による副作用
- 複雑な収集設定による不安定性

## 最小構成の原則

1. **何も除外しない** - PyInstallerのデフォルト動作に任せる
2. **hiddenimportsは最小限** - ImportErrorが出た分だけ追加
3. **カスタムフックは使わない** - 標準フックのみ使用
4. **onedir形式** - onefileは避けて安定性優先
5. **最適化しない** - UPX圧縮、strip等は無効

## 必要な環境

```bash
# Python 3.12以降
python3 --version

# 最小依存関係のみインストール
pip install -r requirements-minimal.txt
```

## 最小依存関係 (requirements-minimal.txt)

```
# GUI Framework (必須)
PySide6>=6.5.0

# Video Processing (必須)
opencv-python<=4.6.0.66

# OCR (必須)
paddlepaddle==3.0.0
paddleocr==2.7.*

# Data Processing (必須)
pandas>=2.0.0
numpy>=1.24.0,<2.0

# File Handling (必須)
python-bidi>=0.4.2
pysrt>=1.1.2

# Packaging (必須)
pyinstaller>=5.13.0

# Configuration (必須)
PyYAML>=6.0

# Image Processing (必須)
Pillow>=10.0.0

# System monitoring (必須)
psutil>=5.9.0
```

## ビルド手順

### 1. 最小仮想環境の作成

```bash
# 新しい仮想環境を作成
python3 -m venv venv-minimal

# 仮想環境を有効化
source venv-minimal/bin/activate

# 最小依存関係をインストール
pip install -r requirements-minimal.txt
```

### 2. 最小specファイルの使用

`vlog-subs-tool-minimal.spec`の内容：

```python
# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['app/main.py'],                     # エントリポイント一本化
    pathex=[],                           # パス設定は最小限
    binaries=[],                         # 必要なバイナリがあれば後で追加
    datas=[
        ('README.md', '.'),
        ('app', 'app'),                  # アプリケーション全体を物理同梱
    ],
    hiddenimports=[
        # 必要最小限のみ（動作確認後に不足分を追加）
    ],
    hookspath=[],                        # 独自フックは使わない
    runtime_hooks=[],                    # ランタイムフックも使わない
    excludes=[],                         # 何も除外しない
    noarchive=False,                     # デフォルト設定
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,               # onedir形式
    name='vlog-subs-tool',
    debug=False,
    strip=False,                         # ストリップしない
    upx=False,                          # UPX圧縮使わない
    console=True,                       # 例外可視化のため一時的にTrue
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False,                        # ストリップしない
    upx=False,                          # UPX圧縮使わない
    name='vlog-subs-tool',
)
```

### 3. ビルド実行

```bash
# 最小構成でビルド
pyinstaller --clean vlog-subs-tool-minimal.spec

# 実行可能ファイルの確認
ls -la ./vlog-subs-tool
file ./vlog-subs-tool
```

## トラブルシューティング

### ImportError が発生した場合

1. エラーメッセージで不足モジュールを確認
2. `vlog-subs-tool-minimal.spec` の `hiddenimports` に追加：

```python
hiddenimports=[
    # 例：ImportError: No module named 'xxx' が出た場合
    'xxx',
],
```

### 動的ライブラリが見つからない場合

1. エラーメッセージで不足ライブラリを確認
2. `binaries` に追加または `--add-binary` オプション使用

### リソースファイルが見つからない場合

1. `datas` に追加または `--add-data` オプション使用

## GitHub Actions対応

CI/CDパイプラインも最小構成に対応済みです：

### ワークフロー変更点

- `requirements.txt` → `requirements-minimal.txt` を使用
- `scripts/build_binary.sh` → 直接 `pyinstaller` コマンドを実行
- プラットフォーム別最小specファイルを使用：
  - Linux/Windows: `vlog-subs-tool-minimal.spec`
  - macOS: `vlog-subs-tool-macos-minimal.spec`

### 自動ビルド

```yaml
# .github/workflows/build-binaries.yml (抜粋)
- name: Install Python dependencies (minimal config)
  run: |
    pip install -r requirements-minimal.txt

- name: Build Linux binary (simplified PyInstaller)
  run: |
    pyinstaller --clean vlog-subs-tool-minimal.spec
```

### リリース作成

タグをプッシュすると自動でバイナリがビルドされ、GitHub Releasesに公開されます：

```bash
git tag v1.1.0-minimal
git push origin v1.1.0-minimal
```

## 次のステップ

1. **基本動作確認** - 最小構成で動作することを確認
2. **機能別テスト** - OCR、GUI、ファイルI/O等の個別テスト
3. **段階的機能追加** - 翻訳機能など、必要に応じて依存関係を追加
4. **サイズ最適化** - 動作確認後、必要に応じて最適化を検討

## 元の設定との比較

| 項目 | 従来設定 | 最小設定 |
|------|----------|----------|
| excludes | 166行 | 0行 |
| hiddenimports | 71個 | 0個（必要時追加） |
| カスタムフック | あり | なし |
| UPX圧縮 | 無効 | 無効 |
| バイナリサイズ | ~300MB | ~1.5GB（一時的） |
| 安定性 | 不安定 | 安定 |

## 注意事項

- 現在の最小構成はサイズが大きい（1.5GB）が、動作安定性を優先
- 動作確認後、段階的に最適化を行う
- `console=True` は一時的な設定（動作確認後に `False` に変更）