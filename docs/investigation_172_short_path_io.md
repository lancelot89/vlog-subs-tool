# Issue #172: 短いパスによるI/O性能最適化調査

## 📋 概要

OneDrive/ネットワークドライブや長い日本語パスによるI/O劣化を排除し、短いASCIIパス (`C:\work\input\`, `C:\work\out\`) での性能改善効果を定量測定します。

## 🎯 調査目的

- **長いパス vs 短いパス**: ファイルパス長がI/O性能に与える影響を実測
- **OneDrive/ネットワーク回避**: ローカルSSD直下の短いパスによる改善度を検証
- **日本語パス影響**: Unicode文字を含むパスとASCIIパスの性能差を測定
- **最適パス構成の決定**: Issue #170のタイミング機能を活用した詳細分析

## 🛠️ 使用ツール

- `benchmark_short_path_io.py`: 短いパス vs 長いパス比較ベンチマーク
- Issue #170で実装されたステージ別タイミング機能を活用
- パス長・I/O時間・OCR処理時間の分離測定

## 📊 測定項目

1. **ファイルI/O時間**: `cv2.imread()` でのファイル読み込み時間
2. **パス長**: ファイルパス文字数 (短いパス vs 長いパス)
3. **OCRステージ別時間**: Detection/Classification/Recognition各段階
4. **総処理時間**: ファイル読み込み～OCR完了まで

## 🔬 調査手順

### Step 1: ベンチマーク環境準備

```bash
# Windows環境での推奨実行方法
# 短いパス: C:\work\input\
# 長いパス: C:\Users\Documents\very_long_folder_name_for_io_testing\input\

python benchmark_short_path_io.py \
    --short-base "C:\work\input" \
    --long-base "C:\Users\Documents\very_long_folder_name_for_io_testing\input" \
    --runs 5
```

### Step 2: Linux/WSL環境での動作確認

```bash
# Linux環境 (開発・テスト用)
python benchmark_short_path_io.py \
    --short-base "/tmp/short" \
    --long-base "/tmp/very_long_folder_name_for_io_testing_on_linux_system" \
    --runs 3
```

### Step 3: 結果分析とパス最適化推奨

ベンチマーク完了後、自動的に以下の分析が表示されます：

```
SHORT vs LONG PATH PERFORMANCE COMPARISON
========================================
SHORT PATH PERFORMANCE:
  Average path length:  45 characters
  File I/O time:        2.150 ms
  OCR processing:       8450.230 ms
  Total time:           8452.380 ms

LONG PATH PERFORMANCE:
  Average path length:  120 characters
  File I/O time:        5.780 ms
  OCR processing:       8451.100 ms
  Total time:           8456.880 ms

PATH OPTIMIZATION IMPACT ANALYSIS:
  Path length reduction: 120 → 45 characters (62.5% shorter)
  I/O time improvement:  +62.8% (+3.630 ms)
  OCR time change:       -0.0% (-0.870 ms)
  Total time improvement: +0.1% (+4.500 ms)
```

## 📈 期待される結果

### I/O改善が大きい場合 (>10% I/O時間短縮):
- **推奨**: 短いASCIIパス (`C:\work\input\`, `C:\work\out\`) を標準採用
- **効果**: 大量ファイル処理時の体感速度向上
- **対象**: OneDrive同期、ネットワークドライブ利用者

### I/O改善が中程度の場合 (5-10% I/O時間短縮):
- **推奨**: 頻繁に処理する場合は短いパスを検討
- **効果**: 長時間作業での累積的改善

### I/O改善が軽微な場合 (<5% I/O時間短縮):
- **推奨**: パス最適化は任意、利便性優先でも可
- **効果**: システム環境ではパス長の影響は限定的

## 🔍 実装詳細

### テストファイル生成
```python
# 短いパス例: C:\work\input\frame_1.png (約45文字)
# 長いパス例: C:\Users\Documents\very_long_folder_name_for_io_testing\input\test_frame_1_long_filename_for_io_testing.png (約120文字)
```

### 測定内容
1. **パス長**: `len(str(file_path))` による文字数測定
2. **I/O時間**: `time.perf_counter()` でのファイル読み込み時間測定
3. **OCR時間**: Issue #170のステージ別タイミング活用
4. **比較分析**: 短いパス vs 長いパスの改善率計算

### プラットフォーム対応
- **Windows**: `C:\work\` ベースの短いパス (本来の対象環境)
- **Linux/WSL**: `/tmp/` ベースの短いパス (開発・テスト環境)

## 📝 完了条件

✅ 短いパス vs 長いパスの測定データ取得
✅ I/O時間改善率の数値化 (%)
✅ パス長とI/O性能の相関関係確認
✅ 最適パス構成の推奨決定
✅ Meta Issue #180への結果報告

## ⚠️ 注意事項

1. **測定環境**: 他のディスクアクセスを最小限に抑制
2. **パス設定**: OneDrive同期フォルダは測定に影響するため注意
3. **再現性**: 同一条件での複数回測定を実施
4. **ディスク状態**: 測定前にディスクキャッシュをクリア

## 🔗 関連Issue

- Issue #170: ステージ別OCRベンチマーク（測定基盤）
- Issue #171: Windows Defender除外設定調査
- Issue #180: Windows遅延対策ロードマップ（Meta Issue）

## 📋 使用例

### 基本実行
```bash
python benchmark_short_path_io.py
```

### カスタム設定
```bash
python benchmark_short_path_io.py \
    --short-base "C:\work\input" \
    --long-base "C:\Users\username\OneDrive\Documents\Projects\vlog-subs-tool\very_long_input_directory" \
    --runs 5 \
    --output-short short_path_results.json \
    --output-long long_path_results.json
```

### テストファイル保持 (デバッグ用)
```bash
python benchmark_short_path_io.py --skip-cleanup
```

この調査により、vlog-subs-toolのI/O性能最適化において、パス設計がどの程度重要かを定量的に判断できます。