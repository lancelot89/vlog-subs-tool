# Issue #175: OpenCV/FFmpeg ビルド差の確認と採用方針の決定

## 📋 概要

`opencv-python`（FFmpeg同梱）と`opencv-python-headless`の性能差、およびFFmpegバージョン差がvlog-subs-toolに与える影響を詳細調査し、最適なビルド構成と依存関係固定方針を決定します。

## 🎯 調査目的

- **OpenCVビルド差確認**: opencv-python vs opencv-python-headlessの性能・機能差を実測
- **FFmpegバージョン影響**: 同梱FFmpegバージョンによる動画処理性能差を測定
- **依存関係固定方針**: 再現性確保のためのバージョンピン戦略決定
- **最適構成決定**: Windows環境での最速構成を技術的に判断

## 🛠️ 使用ツール

- `benchmark_opencv_ffmpeg_build.py`: OpenCVビルド構成比較ベンチマーク
- Issue #170で実装されたステージ別タイミング機能を活用
- 仮想環境分離による正確な比較測定

## 📊 比較対象構成

### 1. OpenCVビルドバリアント
- **opencv-python**: フル機能版（GUI、FFmpeg、その他コーデック同梱）
- **opencv-python-headless**: ヘッドレス版（GUI機能なし、軽量）

### 2. FFmpeg構成
- **同梱FFmpeg**: opencv-pythonに内蔵されたFFmpegライブラリ
- **外部FFmpeg**: システムにインストールされた独立FFmpeg
- **バージョン差**: 異なるFFmpegバージョンの性能影響

### 3. 依存関係管理
- **requirements.txt**: バージョン固定の明示的指定
- **poetry.lock**: Poetry環境での厳密な依存解決
- **再現性確保**: 異なる環境での一貫した動作保証

## 🔬 調査手順

### Step 1: OpenCVビルド差ベンチマーク

```bash
# 現在の構成での基準測定
python benchmark_opencv_ffmpeg_build.py --current-config --baseline

# opencv-python構成でのテスト
python benchmark_opencv_ffmpeg_build.py --opencv-variant full --test-name "opencv-python"

# opencv-python-headless構成でのテスト
python benchmark_opencv_ffmpeg_build.py --opencv-variant headless --test-name "opencv-headless"
```

### Step 2: FFmpegバージョン影響調査

```bash
# FFmpegバージョン情報と性能測定
python benchmark_opencv_ffmpeg_build.py \
    --ffmpeg-analysis \
    --test-codecs h264,hevc,vp9 \
    --test-resolutions 720p,1080p

# 外部FFmpeg vs 同梱FFmpeg比較
python benchmark_opencv_ffmpeg_build.py \
    --compare-ffmpeg-sources \
    --external-ffmpeg-path /usr/bin/ffmpeg
```

### Step 3: 総合比較と推奨構成決定

```bash
# 包括的比較分析
python benchmark_opencv_ffmpeg_build.py \
    --comprehensive \
    --output opencv_build_analysis.json \
    --generate-requirements
```

## 📈 期待される結果

### パフォーマンス差が大きい場合 (>15% 差):
- **推奨**: 高速な構成を標準採用
- **効果**: 動画処理パイプライン全体の大幅高速化
- **対象**: 頻繁に大量動画を処理するユーザー

### パフォーマンス差が中程度の場合 (5-15% 差):
- **推奨**: 用途に応じた選択肢を提供
- **効果**: 特定用途での最適化
- **対象**: 性能重視 vs 軽量性重視での使い分け

### パフォーマンス差が軽微な場合 (<5% 差):
- **推奨**: 互換性・安定性を優先した構成
- **効果**: シンプルな依存関係管理
- **対象**: 安定性と再現性を重視

## 🔍 実装詳細

### OpenCVビルド情報取得

```python
import cv2

def get_opencv_build_info():
    """OpenCVビルド情報を取得"""
    return {
        "version": cv2.__version__,
        "build_info": cv2.getBuildInformation(),
        "ffmpeg_enabled": cv2.VideoCapture(0).isOpened(),  # FFmpeg利用可否
        "gui_support": hasattr(cv2, 'imshow'),  # GUI機能有無
    }
```

### FFmpegバージョン検出

```python
def detect_ffmpeg_versions():
    """OpenCV同梱とシステムFFmpegのバージョンを検出"""
    # OpenCV経由でのFFmpeg情報
    cap = cv2.VideoCapture()
    opencv_ffmpeg_info = cap.get(cv2.CAP_PROP_FOURCC)

    # システムFFmpeg情報
    system_ffmpeg = subprocess.run(['ffmpeg', '-version'],
                                   capture_output=True, text=True)

    return {
        "opencv_ffmpeg": opencv_ffmpeg_info,
        "system_ffmpeg": system_ffmpeg.stdout if system_ffmpeg.returncode == 0 else None
    }
```

### 性能測定項目

1. **動画読み込み時間**: cv2.VideoCapture().read()速度
2. **動画書き込み時間**: cv2.VideoWriter()性能
3. **コーデック対応**: 各種フォーマット処理能力
4. **メモリ使用量**: 処理中のメモリ消費パターン
5. **CPU使用率**: デコード・エンコード負荷

## 📝 完了条件

✅ opencv-python vs opencv-python-headless性能比較完了
✅ FFmpegバージョン差による影響測定完了
✅ 最適構成の技術的推奨決定
✅ requirements.txtまたはpoetry.lockでの依存固定方針決定
✅ Meta Issue #180への結果報告

## ⚠️ 注意事項

1. **環境分離**: 正確な比較のため仮想環境を分けて測定
2. **キャッシュ影響**: 測定間でのディスクキャッシュクリア
3. **再現性**: 同一動画ファイルでの複数回測定
4. **システム負荷**: 他プロセス最小化での測定環境確保

## 🔗 関連Issue

- Issue #170: ステージ別OCRベンチマーク（測定基盤）
- Issue #173: OpenCV vs ffmpeg デコード比較
- Issue #180: Windows遅延対策ロードマップ（Meta Issue）

## 📋 使用例

### 基本比較
```bash
python benchmark_opencv_ffmpeg_build.py
```

### 詳細分析
```bash
python benchmark_opencv_ffmpeg_build.py \
    --opencv-variant both \
    --ffmpeg-analysis \
    --test-video sample.mp4 \
    --output detailed_build_comparison.json
```

### 依存関係固定ファイル生成
```bash
python benchmark_opencv_ffmpeg_build.py \
    --generate-requirements \
    --format requirements.txt
```

この調査により、vlog-subs-toolの依存関係を最適化し、Windows環境での動画処理性能を最大化する技術的基盤を確立できます。