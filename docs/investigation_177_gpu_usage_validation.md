# Issue #177: GPU利用の有無を明確化し、Windows/WSLの利用差をチェック

## 📋 概要

Windows環境とWSL環境でのGPU利用状況の非対称性を検出・解消し、PaddleOCRの実行環境を統一することで、性能差の真の原因を特定します。

## 🎯 調査目的

- **GPU利用状況の確認**: Windows/WSL両環境でのGPU使用プロセスを`nvidia-smi`で監視
- **非対称性の検出**: 一方でCUDA/oneDNNが有効、他方でCPUのみという状況を特定
- **環境統一**: 「両方CPU」または「両方GPU」に統一して再測定
- **性能差収束**: 統一後の性能差が許容範囲内に収束することを確認

## 🛠️ 使用ツール

- `benchmark_gpu_usage_validation.py`: GPU利用状況検証ベンチマーク
- Issue #170で実装されたステージ別タイミング機能を活用
- `nvidia-smi`コマンドによるリアルタイムGPU監視

## 📊 検証対象項目

### 1. GPU使用状況の監視
- **目的**: PaddleOCR実行中のGPU利用プロセスを検出
- **監視項目**: プロセス名、GPU使用率、メモリ使用量
- **確認方法**: `nvidia-smi pmon -i 0 -s um -c 1`

### 2. CUDA/oneDNN有効化状況
- **目的**: 深層学習ライブラリの最適化設定確認
- **検証項目**:
  - PaddlePaddle CUDA利用可否
  - Intel oneDNN（MKL-DNN）有効化状況
  - OpenCV GPU加速利用状況

### 3. 環境統一による再測定
- **目的**: 同一条件での公平な性能比較
- **統一方針**:
  - **CPU統一**: 両環境でGPU無効化、CPU推論のみ
  - **GPU統一**: 両環境でCUDA有効化、GPU推論利用

## 🔬 調査手順

### Step 1: 現在のGPU利用状況確認

```bash
# Windows/WSL両環境でのGPU監視
python benchmark_gpu_usage_validation.py \
    --monitor-gpu \
    --environment windows \
    --output gpu_usage_windows.json

# WSL環境での同様の監視
python benchmark_gpu_usage_validation.py \
    --monitor-gpu \
    --environment wsl \
    --output gpu_usage_wsl.json
```

### Step 2: 非対称性の検出と分析

```bash
# GPU利用状況の比較分析
python benchmark_gpu_usage_validation.py \
    --compare-environments \
    --windows-data gpu_usage_windows.json \
    --wsl-data gpu_usage_wsl.json \
    --detect-asymmetry
```

### Step 3: 環境統一と再測定

```bash
# CPU統一による再測定
python benchmark_gpu_usage_validation.py \
    --force-cpu-only \
    --comprehensive-benchmark \
    --output cpu_unified_results.json

# GPU統一による再測定（CUDA利用可能な場合）
python benchmark_gpu_usage_validation.py \
    --force-gpu-usage \
    --comprehensive-benchmark \
    --output gpu_unified_results.json
```

## 📈 期待される結果

### 非対称性が検出された場合:
- **推奨**: 環境統一により公平な比較を実施
- **効果**: 真の性能差を特定し、最適化対象を明確化
- **対象**: GPU加速非対称による性能差の解消

### 既に統一されている場合:
- **推奨**: 他の要因（メモリ、ディスクI/O等）を調査
- **効果**: ハードウェア差による性能差の特定
- **対象**: システムレベル最適化の方向性決定

### 統一後に性能差が収束した場合:
- **推奨**: 統一設定を標準として採用
- **効果**: 環境差による予期しない性能変動を排除
- **対象**: 再現性の高い性能測定環境の確立

## 🔍 実装詳細

### GPU利用状況の検出

```python
def detect_gpu_usage():
    """PaddleOCR実行中のGPU利用状況を監視"""
    try:
        import subprocess
        # nvidia-smiでGPU使用プロセスを監視
        cmd = ["nvidia-smi", "pmon", "-i", "0", "-s", "um", "-c", "10"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # PaddleOCR関連プロセスのGPU利用を検出
        gpu_processes = parse_nvidia_smi_output(result.stdout)
        return gpu_processes
    except Exception as e:
        return {"error": str(e), "gpu_available": False}
```

### CUDA利用可否の確認

```python
def check_cuda_availability():
    """PaddlePaddleのCUDA利用可否を確認"""
    try:
        import paddle
        return {
            "cuda_available": paddle.is_compiled_with_cuda(),
            "gpu_count": paddle.device.cuda.device_count() if paddle.is_compiled_with_cuda() else 0,
            "current_device": str(paddle.get_device())
        }
    except ImportError:
        return {"error": "PaddlePaddle not available"}
```

### 環境統一設定

```python
def force_cpu_only():
    """CPU推論のみに強制設定"""
    import os
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["PADDLE_USE_GPU"] = "0"

def force_gpu_usage():
    """GPU推論に強制設定"""
    import os
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["PADDLE_USE_GPU"] = "1"
```

## 📝 完了条件

✅ Windows/WSL両環境でのGPU利用状況監視完了
✅ 非対称性の有無を検出・分析完了
✅ 環境統一（CPU統一またはGPU統一）による再測定実施
✅ 統一後の性能差が許容範囲内に収束することを確認
✅ GPU利用状況レポートの生成とMeta Issue #180への報告

## ⚠️ 注意事項

1. **GPU監視**: nvidia-smiが利用できない環境での代替手段確保
2. **プロセス識別**: PaddleOCR関連プロセスの正確な識別
3. **環境切替**: GPU/CPU設定変更後のプロセス再起動確保
4. **権限問題**: GPU監視コマンドの実行権限確認

## 🔗 関連Issue

- Issue #170: ステージ別OCRベンチマーク（測定基盤）
- Issue #180: Windows遅延対策ロードマップ（Meta Issue）
- Issue #176: PaddleOCRパラメータ最適化

## 📋 使用例

### 基本GPU監視
```bash
python benchmark_gpu_usage_validation.py --monitor-gpu
```

### 環境比較分析
```bash
python benchmark_gpu_usage_validation.py \
    --compare-environments \
    --detect-asymmetry
```

### CPU統一での性能測定
```bash
python benchmark_gpu_usage_validation.py \
    --force-cpu-only \
    --comprehensive-benchmark \
    --output cpu_unified_benchmark.json
```

### GPU統一での性能測定
```bash
python benchmark_gpu_usage_validation.py \
    --force-gpu-usage \
    --comprehensive-benchmark \
    --output gpu_unified_benchmark.json
```

この調査により、vlog-subs-toolのWindows/WSL性能差の真の原因を特定し、統一された実行環境での公平な性能比較を実現できます。