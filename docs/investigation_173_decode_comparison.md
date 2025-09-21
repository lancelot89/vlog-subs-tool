# Issue #173: OpenCVデコード vs ffmpeg CLI事前フレーム抽出の速度比較

## 📋 概要

動画デコードがボトルネックかどうかを確認し、OpenCV VideoCapture vs ffmpeg CLI事前フレーム抽出の性能差を定量測定して、最適なデコード方式を決定します。

## 🎯 調査目的

- **デコードボトルネック確認**: 現行OpenCV方式でのデコード時間が全体に占める割合
- **ffmpeg効果測定**: ハードウェアアクセラレーション付きffmpeg事前抽出の改善度
- **採用方針決定**: OpenCV継続 vs ffmpeg前展開の技術的判断
- **総合的性能評価**: デコード時間 + OCR時間の総合比較

## 🛠️ 使用ツール

- `benchmark_decode_comparison.py`: OpenCV vs ffmpeg デコード比較ベンチマーク
- Issue #170で実装されたステージ別タイミング機能を活用
- ffmpeg ハードウェアアクセラレーション（`-hwaccel auto`）

## 📊 測定項目

### OpenCV方式（現行）
1. **フレーム別デコード時間**: `cv2.VideoCapture().read()` の処理時間
2. **OCR処理時間**: 各フレームのOCR実行時間
3. **総処理時間**: デコード + OCR の合計時間

### ffmpeg方式（検証対象）
1. **一括抽出時間**: `ffmpeg -hwaccel auto -i input.mp4 -vsync 0 -qscale:v 2 frames/%06d.jpg`
2. **画像読み込み時間**: 抽出済み画像ファイルの `cv2.imread()` 時間
3. **OCR処理時間**: 抽出画像からのOCR実行時間
4. **総処理時間**: 抽出 + 読み込み + OCR の合計時間

## 🔬 調査手順

### Step 1: 基本ベンチマーク実行

```bash
# テスト動画自動生成での比較
python benchmark_decode_comparison.py --duration 10 --fps 2

# 実際の動画ファイルでの比較
python benchmark_decode_comparison.py --input-video path/to/video.mp4

# 詳細な結果保存
python benchmark_decode_comparison.py \
    --input-video sample.mp4 \
    --output decode_results.json \
    --keep-temp
```

### Step 2: Windows/WSL/Linux での比較

#### Windows環境（ハードウェアアクセラレーション期待）
```bash
# Windows でのネイティブ実行
python benchmark_decode_comparison.py --duration 15 --fps 1
```

#### WSL環境（制限付きハードウェアアクセス）
```bash
# WSL での比較実行（参考データ）
python benchmark_decode_comparison.py --duration 15 --fps 1
```

### Step 3: 結果分析とボトルネック特定

ベンチマーク実行後、以下の分析が自動出力されます：

```
OPENCV vs FFMPEG DECODE COMPARISON
==================================================
PERFORMANCE COMPARISON:
  OpenCV Method:
    Total time:    25.450 s
    Decode time:   8.200 s (32.2%)
    OCR time:      17.250 s (67.8%)

  ffmpeg Method:
    Total time:    20.100 s
    Extract time:  3.500 s (17.4%)
    OCR time:      16.600 s (82.6%)

IMPROVEMENT ANALYSIS:
  Total time improvement: +21.0% (+5.350 s)
  Decode vs Extract:      +57.3% (+4.700 s)

ISSUE #173 RECOMMENDATIONS:
🚀 Significant improvement with ffmpeg (21.0%)
   RECOMMEND: Switch to ffmpeg pre-extraction method
   Benefit: Substantial decode time reduction
```

## 📈 期待される結果

### デコードがボトルネックの場合
- **OpenCV デコード時間**: 総時間の30-50%を占める
- **ffmpeg改善効果**: 総時間で10-30%短縮
- **推奨**: ffmpeg事前抽出方式を採用

### OCRがボトルネックの場合
- **OpenCV デコード時間**: 総時間の10%未満
- **ffmpeg改善効果**: 総時間で5%未満の改善
- **推奨**: 現行OpenCV方式を継続、OCR最適化を優先

### 環境別期待値
- **Windows + GPU**: ffmpegハードウェアアクセラレーションで大幅改善
- **WSL/Linux**: ソフトウェアデコードでも中程度改善
- **macOS**: VideoToolbox活用で改善効果期待

## 🔍 技術的詳細

### ffmpeg コマンド詳細
```bash
ffmpeg -hwaccel auto -i input.mp4 -vsync 0 -qscale:v 2 frames/%06d.jpg
```

- `-hwaccel auto`: 利用可能なハードウェアアクセラレーション自動選択
- `-vsync 0`: フレームドロップ無効（全フレーム出力）
- `-qscale:v 2`: 高品質JPEG出力（OCR精度確保）
- `%06d.jpg`: 6桁ゼロパディングファイル名

### OCR処理の統一性
- **同一OCRエンジン**: 両方式で `SimplePaddleOCREngine` を使用
- **同一設定**: confidence_threshold、画像サイズ制限等を統一
- **ステージ別計測**: Issue #170のタイミング機能でOCR内訳も分析

## 📝 完了条件

✅ OpenCV方式の詳細タイミング測定完了
✅ ffmpeg方式の詳細タイミング測定完了
✅ 2方式の総時間・デコード時間比較記録
✅ ボトルネック特定（デコード vs OCR）
✅ 採用方針の技術的結論決定
✅ Meta Issue #180への結果報告

## ⚠️ 注意事項

1. **ffmpeg依存**: ffmpegがシステムにインストールされている必要
2. **一時ファイル**: ffmpeg方式は大量の画像ファイルを生成（`--keep-temp`で保持可能）
3. **メモリ使用量**: 長時間動画では抽出画像によるディスク使用量に注意
4. **ハードウェア差**: GPU・CPUアーキテクチャによる結果変動を考慮

## 🔗 関連Issue

- Issue #170: ステージ別OCRベンチマーク（測定基盤）
- Issue #171: Windows Defender除外設定調査
- Issue #172: 短いパスI/O最適化調査
- Issue #180: Windows遅延対策ロードマップ（Meta Issue）

## 📋 使用例

### 基本実行
```bash
python benchmark_decode_comparison.py
```

### カスタム動画ファイル
```bash
python benchmark_decode_comparison.py \
    --input-video /path/to/vlog.mp4 \
    --output detailed_comparison.json
```

### デバッグ用（一時ファイル保持）
```bash
python benchmark_decode_comparison.py \
    --duration 5 \
    --fps 2 \
    --keep-temp
```

この調査により、vlog-subs-toolの動画処理パイプラインにおいて、デコード最適化がどの程度重要かを定量的に判断し、技術的に最適な方式を選択できます。