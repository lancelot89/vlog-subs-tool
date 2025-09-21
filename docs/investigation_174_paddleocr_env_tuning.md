# Issue #174: PaddleOCR 並列化・MKLDNN有効化の環境変数チューニング

## 📋 概要

WindowsでCPU推論の並列処理性能が十分に発揮されない問題を改善するため、PaddleOCRの環境変数を最適化し、最高性能の組み合わせを探索します。

## 🎯 調査目的

- **並列処理最適化**: CPU物理コア数に応じた並列スレッド数の最適値を特定
- **MKLDNN有効化**: Intel MKL-DNN（DNNL）ライブラリによる高速化効果を測定
- **バッチサイズ調整**: `rec_batch_num`パラメータの最適値を探索
- **環境設定提案**: 最適な組み合わせを`.env.example`形式で提供

## 🛠️ 使用ツール

- `benchmark_paddleocr_env_tuning.py`: 環境変数組み合わせ最適化ベンチマーク
- Issue #170で実装されたステージ別タイミング機能を活用
- 複数環境変数の組み合わせテストとパフォーマンス測定

## 📊 チューニング対象環境変数

### 1. 並列処理制御
- **`OMP_NUM_THREADS`**: OpenMP並列スレッド数
- **`MKL_NUM_THREADS`**: Intel MKL並列スレッド数
- **`KMP_AFFINITY`**: スレッドアフィニティ設定（任意）

### 2. MKLDNN最適化
- **`FLAGS_use_mkldnn`**: Intel MKL-DNN有効化フラグ

### 3. PaddleOCRパラメータ
- **`rec_batch_num`**: テキスト認識バッチサイズ

## 🔬 調査手順

### Step 1: 基本環境変数探索

```bash
# 段階的スレッド数テスト (1, 2, 4, 8, 16...)
python benchmark_paddleocr_env_tuning.py \
    --thread-counts 1,2,4,8 \
    --mkldnn-enabled \
    --rec-batch-sizes 8,16,32

# 物理コア数自動検出での最適化
python benchmark_paddleocr_env_tuning.py \
    --auto-detect-cores \
    --mkldnn-enabled
```

### Step 2: アフィニティ設定最適化

```bash
# 各種アフィニティパターンのテスト
python benchmark_paddleocr_env_tuning.py \
    --thread-counts 4,8 \
    --affinity-modes compact,scatter,disabled \
    --mkldnn-enabled
```

### Step 3: 組み合わせ最適化とベスト設定抽出

```bash
# 詳細結果保存
python benchmark_paddleocr_env_tuning.py \
    --comprehensive \
    --output env_tuning_results.json \
    --generate-env-config
```

## 📈 期待される結果

### 高い改善効果 (>30% 性能向上):
- **推奨**: 最適設定を標準採用
- **効果**: 大幅なOCR処理速度向上

### 中程度の改善効果 (10-30% 性能向上):
- **推奨**: 設定オプションとして提供
- **効果**: ユーザー環境に応じた性能向上

### 軽微な改善効果 (<10% 性能向上):
- **推奨**: デフォルト設定維持
- **効果**: 複雑性よりもシンプルさを優先

## 🔍 実装詳細

### 環境変数組み合わせテスト

```python
# テスト対象の組み合わせ例
test_configurations = [
    {
        "OMP_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
        "FLAGS_use_mkldnn": "1",
        "rec_batch_num": 16
    },
    {
        "OMP_NUM_THREADS": "8",
        "MKL_NUM_THREADS": "8",
        "FLAGS_use_mkldnn": "1",
        "KMP_AFFINITY": "granularity=fine,compact,1,0",
        "rec_batch_num": 32
    }
]
```

### 性能測定項目

1. **OCR総処理時間**: 環境変数設定前後の比較
2. **ステージ別時間**: Detection/Classification/Recognition各段階
3. **バッチ処理効率**: `rec_batch_num`による処理速度変化
4. **CPU使用率**: 並列化効果の確認

### プラットフォーム対応

- **Windows**: 本来の対象環境（MKLDNN/OpenMP最適化）
- **Linux/WSL**: 開発・テスト環境（参考データ）
- **macOS**: Apple Silicon対応確認

## 📝 完了条件

✅ 各環境変数の単体効果測定完了
✅ 組み合わせパターンのベンチマーク実行
✅ 最高性能設定の特定と改善率記録
✅ `.env.example`形式での推奨設定提案
✅ Meta Issue #180への結果報告

## ⚠️ 注意事項

1. **システム負荷**: 並列テスト中の他プロセス最小化
2. **再現性**: 同一条件での複数回測定実施
3. **CPU温度**: 高負荷テスト時の熱暴走対策
4. **メモリ使用量**: 大きなバッチサイズでのメモリ不足注意

## 🔗 関連Issue

- Issue #170: ステージ別OCRベンチマーク（測定基盤）
- Issue #180: Windows遅延対策ロードマップ（Meta Issue）

## 📋 使用例

### 基本実行
```bash
python benchmark_paddleocr_env_tuning.py
```

### カスタム設定
```bash
python benchmark_paddleocr_env_tuning.py \
    --thread-counts 2,4,8,16 \
    --rec-batch-sizes 8,16,32,64 \
    --mkldnn-enabled \
    --output detailed_tuning.json
```

### 最適設定自動検出
```bash
python benchmark_paddleocr_env_tuning.py \
    --auto-optimize \
    --generate-env-config
```

この調査により、vlog-subs-toolのPaddleOCR性能を環境変数レベルで最適化し、Windows環境での大幅な高速化を実現できます。