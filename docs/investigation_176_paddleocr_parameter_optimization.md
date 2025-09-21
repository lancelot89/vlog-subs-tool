# Issue #176: 入力解像度・PaddleOCRパラメータの最適化

## 📋 概要

文字サイズと精度を維持しつつ無駄な高解像推論を回避するため、PaddleOCRの`det_limit_side_len`と`rec_batch_num`を段階的に調整し、最速・許容精度の最適値を探索します。

## 🎯 調査目的

- **解像度最適化**: `det_limit_side_len`による推論解像度の段階的調整
- **バッチサイズ最適化**: `rec_batch_num`の同時調整による処理速度向上
- **精度維持**: 文字認識精度を許容範囲内に保持
- **推奨値決定**: Windows/WSL共通または環境別の最適パラメータ特定

## 🛠️ 使用ツール

- `benchmark_paddleocr_parameter_optimization.py`: PaddleOCRパラメータ最適化ベンチマーク
- Issue #170で実装されたステージ別タイミング機能を活用
- 精度・速度トレードオフの定量分析

## 📊 最適化対象パラメータ

### 1. det_limit_side_len (検出解像度制限)
- **目的**: テキスト検出の推論解像度上限を制御
- **影響**: 高解像度ほど精度向上、処理時間増加
- **テスト値**: 640, 960, 1280, 1920, 2560

### 2. rec_batch_num (認識バッチサイズ)
- **目的**: テキスト認識の並列処理数を制御
- **影響**: バッチサイズ増加でスループット向上、メモリ使用量増加
- **テスト値**: 4, 8, 16, 32, 64

### 3. max_text_length (最大テキスト長)
- **目的**: 認識可能な最大文字数制限
- **影響**: 長文対応 vs 処理速度のトレードオフ
- **テスト値**: 25, 50, 100, 200

## 🔬 調査手順

### Step 1: 解像度段階調整ベンチマーク

```bash
# det_limit_side_len段階的テスト
python benchmark_paddleocr_parameter_optimization.py \
    --det-limit-side-lens 640,960,1280,1920 \
    --rec-batch-nums 8,16 \
    --test-video sample.mp4

# 高解像度での詳細比較
python benchmark_paddleocr_parameter_optimization.py \
    --det-limit-side-lens 1920,2560 \
    --rec-batch-nums 16,32,64 \
    --accuracy-analysis
```

### Step 2: バッチサイズ最適化

```bash
# rec_batch_num詳細調整
python benchmark_paddleocr_parameter_optimization.py \
    --det-limit-side-lens 1280 \
    --rec-batch-nums 4,8,16,32,64,128 \
    --memory-profiling
```

### Step 3: 総合最適化と推奨値決定

```bash
# 包括的パラメータ最適化
python benchmark_paddleocr_parameter_optimization.py \
    --comprehensive \
    --output ocr_parameter_optimization.json \
    --generate-config-recommendations
```

## 📈 期待される結果

### 高い最適化効果 (>30% 処理速度向上):
- **推奨**: 最適パラメータを標準設定として採用
- **効果**: OCR処理パイプライン全体の大幅高速化
- **対象**: 大量動画処理、リアルタイム処理用途

### 中程度の最適化効果 (10-30% 処理速度向上):
- **推奨**: 用途別設定オプションを提供
- **効果**: 精度重視 vs 速度重視の使い分け
- **対象**: 高精度要求 vs 高速処理要求での選択

### 軽微な最適化効果 (<10% 処理速度向上):
- **推奨**: 現状維持、安定性優先
- **効果**: 複雑性回避、シンプルな設定維持

## 🔍 実装詳細

### パラメータ組み合わせテスト

```python
# テスト対象パラメータ組み合わせ
parameter_combinations = [
    {
        "det_limit_side_len": 960,
        "rec_batch_num": 16,
        "max_text_length": 50
    },
    {
        "det_limit_side_len": 1280,
        "rec_batch_num": 32,
        "max_text_length": 100
    }
]
```

### 精度測定指標

1. **文字認識精度**: 正解文字数 / 総文字数
2. **検出精度**: 正解テキスト領域数 / 総テキスト領域数
3. **処理速度**: フレーム毎秒 (FPS)
4. **メモリ使用量**: 最大メモリ消費量 (MB)

### 品質評価基準

- **許容精度下限**: 95% (文字認識精度)
- **処理速度目標**: 現状比20%以上向上
- **メモリ制限**: システムメモリの50%以下

## 📝 完了条件

✅ det_limit_side_len段階調整による速度・精度影響測定完了
✅ rec_batch_num最適化による処理性能向上確認
✅ 精度・速度トレードオフの定量分析完了
✅ Windows/WSL環境別推奨パラメータ決定
✅ README/設定ファイルへの推奨値反映PR案作成
✅ Meta Issue #180への結果報告

## ⚠️ 注意事項

1. **メモリ制限**: 高バッチサイズでのメモリ不足対策
2. **精度維持**: 速度優先で精度が著しく低下しないよう注意
3. **テスト動画選定**: 代表的な字幕パターンを含む動画使用
4. **再現性**: 同一条件での複数回測定実施

## 🔗 関連Issue

- Issue #170: ステージ別OCRベンチマーク（測定基盤）
- Issue #174: 環境変数チューニング
- Issue #180: Windows遅延対策ロードマップ（Meta Issue）

## 📋 使用例

### 基本最適化
```bash
python benchmark_paddleocr_parameter_optimization.py
```

### カスタムパラメータテスト
```bash
python benchmark_paddleocr_parameter_optimization.py \
    --det-limit-side-lens 960,1280,1920 \
    --rec-batch-nums 8,16,32 \
    --test-video /path/to/test.mp4 \
    --output detailed_optimization.json
```

### 推奨設定生成
```bash
python benchmark_paddleocr_parameter_optimization.py \
    --comprehensive \
    --generate-config-recommendations \
    --accuracy-threshold 0.95
```

この調査により、vlog-subs-toolのPaddleOCR性能をパラメータレベルで最適化し、文字認識の精度と速度の最適バランスを実現できます。