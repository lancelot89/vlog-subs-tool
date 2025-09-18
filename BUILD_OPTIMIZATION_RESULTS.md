# PyInstaller Build Optimization Results

## Issue #154: PyInstaller ビルドファイルサイズ最適化

### 最適化対象
- vlog-subs-tool.spec（メインビルドファイル）
- vlog-subs-tool-macos.spec（macOS専用）
- vlog-subs-tool-debug.spec（デバッグ用）

### 実施した最適化

#### 1. 隠しインポートの削除
**削除対象:**
- `paddlex` 関連モジュール（アプリで未使用）
- `loguru`, `tqdm`（削除済み機能で使用）
- `deepl`, `google.cloud.translate*`（未実装翻訳機能）
- `google.auth`, `google.api_core`（翻訳機能依存）
- 未使用大型ライブラリ（openpyxl, xlsxwriter, xlrd, seaborn, plotly）

**保持:**
- PySide6 関連（必須GUI）
- PaddleOCR コアモジュール（paddleocr, paddlepaddle, paddle）
- OpenCV, NumPy（画像処理必須）
- 基本ライブラリ（PIL, pytesseract, pysrt, pandas, yaml, bidi.algorithm）
- アプリケーション内部モジュール（必要最小限）

#### 2. データファイル収集の最適化
**変更前:**
```python
datas = [
    ('README.md', '.'),
    ('app/models', 'models'),  # 無条件で追加
]

collect_data = [
    'paddleocr',
    'paddle',
    'paddlex',  # 未使用
]
```

**変更後:**
```python
datas = [
    ('README.md', '.'),
]
# app/models が存在する場合のみ追加
app_models_path = project_root / "app" / "models"
if app_models_path.exists():
    datas.append(('app/models', 'models'))

collect_data = [
    'paddleocr',  # 必要最小限
]
```

#### 3. 除外モジュールの拡張
**追加された除外対象:**
- 削除済み機能: `app.core.benchmark`, `app.core.linux_optimizer`
- 未使用翻訳ライブラリ: `deepl`, `google.cloud.*`, `google.auth`
- 大型ライブラリ: `openpyxl`, `xlsxwriter`, `xlrd`, `seaborn`, `plotly`
- ネットワーク関連: `requests_oauthlib`, `urllib3.contrib.pyopenssl`

#### 4. クロスプラットフォーム統合
- 3つのspecファイル全てに同様の最適化を適用
- 環境変数 `VLOG_SUBS_DEBUG=true` でデバッグモード制御
- macOS版では`.app`バンドル対応を維持

### 現在のビルドサイズ
- **Linux版**: 1.8GB（最適化前）
- テストビルド環境が利用不可のため、実際のサイズ削減効果は未測定

### 期待される効果
1. **隠しインポート削減**: 推定100-200MB削減
   - PaddleX関連: ~50MB
   - 未使用翻訳ライブラリ: ~30-50MB
   - 大型ライブラリ: ~50-100MB

2. **データファイル最適化**: 推定50-100MB削減
   - 条件付きapp/models追加
   - PaddleX データファイル除外

3. **総削減見込み**: 150-300MB（1.8GB → 1.5-1.65GB）

### 次のステップ
1. 仮想環境でのテストビルド実行
2. 実際のサイズ削減効果測定
3. クロスプラットフォームでのビルド確認
4. 機能動作確認（OCR, GUI, ファイル出力）

### ファイル変更履歴
- `vlog-subs-tool.spec`: 完全最適化
- `vlog-subs-tool-macos.spec`: macOS対応最適化
- `vlog-subs-tool-debug.spec`: デバッグ用最適化

最適化は既存機能を損なわず、ビルドサイズの削減のみを目的として実施。