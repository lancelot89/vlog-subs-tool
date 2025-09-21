# Issue #171: Windows Defender 除外設定による性能影響調査

## 📋 概要

Windows Defenderのリアルタイム保護が、vlog-subs-toolのOCR処理性能に与える影響を定量的に測定します。

## 🎯 調査目的

- 入力動画ファイルと作業用ディレクトリをDefender除外リストに追加することで、I/O遅延がどの程度改善されるかを検証
- 除外前後の性能差を数値化し、推奨設定を決定

## 🛠️ 使用ツール

- `benchmark_defender_exclusion.py`: 専用ベンチマークスクリプト
- Issue #170で実装されたステージ別タイミング機能を活用

## 📊 測定項目

1. **ファイルI/O時間**: 画像ファイル読み込み時間（Defenderスキャンの影響を受けやすい）
2. **OCRステージ別時間**: Detection/Classification/Recognition各段階
3. **総処理時間**: ファイル読み込み～OCR完了まで

## 🔬 調査手順

### Step 1: 除外設定前の測定

```bash
# 1. 作業ディレクトリ作成
mkdir C:\work\vlog-subs-tool\workspace

# 2. 除外前ベンチマーク実行
python benchmark_defender_exclusion.py \
    --workspace "C:\work\vlog-subs-tool\workspace" \
    --exclusion-status before \
    --runs 5 \
    --output defender_before.json
```

### Step 2: Windows Defender除外設定

Windows Defender設定で以下を除外リストに追加:

1. **作業ディレクトリ**: `C:\work\vlog-subs-tool\workspace\`
2. **入力動画ディレクトリ**: 処理予定の動画ファイル格納場所
3. **アプリケーション実行ファイル**: `vlog-subs-tool.exe` (該当する場合)

#### 除外設定手順:
1. Windows Security → ウイルスと脅威の防止
2. ウイルスと脅威の防止の設定 → 設定の管理
3. 除外 → 除外の追加または削除
4. フォルダーを追加し、上記パスを指定

### Step 3: 除外設定後の測定

```bash
# 除外後ベンチマーク実行
python benchmark_defender_exclusion.py \
    --workspace "C:\work\vlog-subs-tool\workspace" \
    --exclusion-status after \
    --runs 5 \
    --output defender_after.json
```

### Step 4: 結果比較・分析

```bash
# 除外前後の比較分析
python benchmark_defender_exclusion.py \
    --compare-before defender_before.json \
    --compare-after defender_after.json
```

## 📈 期待される結果

### 改善が見込まれる場合:
- **ファイルI/O時間**: 10-30%の短縮
- **総処理時間**: 5-15%の短縮
- **Defenderによるディスクアクセス遅延の軽減**

### 影響が軽微な場合:
- **I/O時間変化**: 5%未満
- **OCR処理時間**: ほぼ変化なし（CPU集約的処理のため）

## 🔍 結果の解釈

### 高い改善効果 (総処理時間 >5% 短縮)
- **推奨**: 作業ディレクトリをDefender除外に追加
- **効果**: 大量ファイル処理時の体感速度向上

### 中程度の改善効果 (1-5% 短縮)
- **推奨**: 必要に応じて除外設定を検討
- **効果**: 長時間作業時の累積的改善

### 軽微な改善効果 (<1% 短縮)
- **推奨**: 除外設定は任意
- **効果**: セキュリティを優先し、現状維持でも問題なし

## 📝 完了条件

✅ 除外前後の測定データ取得
✅ I/O影響の有無と差分％を記録
✅ 推奨設定の決定
✅ Meta Issue #180への結果報告

## ⚠️ 注意事項

1. **セキュリティリスク**: 除外ディレクトリはマルウェアスキャン対象外となる
2. **測定環境**: 他のアプリケーションは最小限に抑制
3. **再現性**: 同一条件での複数回測定を実施
4. **ディスク状態**: 測定前にディスクの断片化やキャッシュ状態を確認

## 🔗 関連Issue

- Issue #170: ステージ別OCRベンチマーク（測定基盤）
- Issue #180: Windows遅延対策ロードマップ（Meta Issue）