# プロジェクト概要（ClaudeCode向け・実装仕様）

**目的**: VLOG動画（音声なし／日本語ハードサブ）から字幕を自動抽出（OCR）し、編集・翻訳・多言語SRT出力までを非エンジニアでも扱えるデスクトップアプリとして提供する。

---

## ゴール / 非ゴール

* **ゴール**

  * macOS/Windows/Linux で動作する **デスクトップGUIアプリ**。
  * 動画を読み込んで **自動で日本語字幕を抽出（OCR）** → 編集 → **SRT出力**。
  * **翻訳**: 内蔵API（Google v3 / DeepL）または **CSV↔GAS** 連携の両対応。
  * **非エンジニア向けUI**（表形式の直接編集・再生プレビュー同期）。
* **非ゴール**

  * 高度な動画編集機能（字幕合成レンダリング等）は範囲外。
  * 難解なモデル学習やDNNカスタム学習は初版では行わない。

---

## 採用スタック（理由）

* **言語**: Python

  * 理由: OCR/映像処理ライブラリが豊富（OpenCV/ffmpeg/PaddleOCR/Tesseract）・配布が容易（PyInstaller）。
* **GUI**: PySide6 (Qt for Python)

  * 理由: クロスプラットフォーム・ネイティブ風UI・表編集やプレビューの相性が良い。
* **OCR**: PaddleOCR(ja) を既定／Tesseract(jpn) を選択式

  * 検出＋認識の一体運用がしやすく、日本語に強い。Tesseractはオフライン重視時に利用。
* **動画IO**: ffmpeg + OpenCV

  * 幅広いコーデック対応・サンプリング制御・ROI切り出しが容易。
* **配布**: PyInstaller

  * macOS .app / Windows .exe / Linux AppImage を想定。

---

## 画面仕様（ワイヤー）

### 画面A: 抽出／編集

* ヘッダ: メニュー（ファイル/編集/表示/翻訳/設定/ヘルプ）
* ツールバー: \[動画を開く] \[最近] \[自動抽出] \[再抽出] \[QCチェック] \[保存]
* 左ペイン: **動画プレビュー**（再生ヘッド・区間ループ・抽出領域枠表示ON/OFF・字幕オーバーレイON/OFF）
* 右ペイン: **字幕テーブル**（列: `# / 開始 / 終了 / 本文`、Excel風セル直接編集）
* 行操作: \[分割] \[結合] \[上へ] \[下へ]、一括置換（辞書）
* ステータスバー: 出力先・ファイル名パターン・処理状態

### 画面B: 翻訳

* プロバイダ選択: なし(CSV外部)/Google v3/DeepL（API設定ボタン）
* Glossary: CSV選択＋適用トグル
* 言語チェック: en/zh/ko/ar（増減可能）
* 整形オプション: 句読点改行・行長上限・最大行数・最小表示秒・RTL整形（ar）・HTMLエンティティ解除
* ボタン: \[一括翻訳] \[SRT一括保存] \[CSVに書き出し] \[翻訳CSVを取り込む→SRT化]

### 画面C: 設定

* 抽出: サンプリングFPS、解析解像度、自動検出/下段%/手動矩形、OCRエンジン（PaddleOCR/Tesseract）
* 整形: 行長上限、最大行数、最小表示秒、類似度しきい値、記号正規化
* 翻訳: Google v3（Project/Location/API Key/Glossary管理）、DeepL（API Key/フォーマリティ）
* 出力: 出力フォルダ、文字コード(UTF-8推奨)、ファイル名パターン、上書き動作

---

## 入出力仕様

### 入力: 動画

* 対応: mp4/mov/mkv/avi 等（ffmpeg準拠）
* 取得: OpenCVでフレーム & 実時間（秒）／fpsサンプリング（例 2〜5fps）

### 入力: SRT（任意）

* 読み込み: UTF-8推奨。既存字幕の再編集に対応。

### 入出力: CSV（翻訳連携）

* **翻訳前エクスポート**（外部翻訳/GAS へ）

  * ヘッダ: `index,start_ms,end_ms,text_ja`
* **翻訳後インポート**（外部→アプリ）

  * 最低ヘッダ: `index,start_ms,end_ms` + `text_{lang}` 列（任意数）
* **マージ規則**: `index/start_ms/end_ms` で一致マージ。非一致は警告。

### Glossary（用語集）

* CSV: `source,en,zh,ko,ar,...`（存在列のみ利用）

### 出力: SRT

* 日本語: `{basename}.ja.srt`
* 多言語: `{basename}.{lang}.srt`（例 `vlog001.en.srt`）
* 形式: `HH:MM:SS,mmm`、UTF-8（BOMなし）
* 整形: 句読点優先改行 / 1行≤42文字・最大2行 / 最小表示秒を保証（短片は併合/延伸）
* RTL: `ar` などはBidi整形（オプションON時）

### プロジェクト保存（途中保存）

* JSON（拡張子 `.subproj`）
* 構造（例）:

```json
{
  "version": "1.0",
  "source_video": "vlog001.mp4",
  "settings": {
    "fps_sample": 3.0,
    "roi_mode": "auto",
    "ocr": "paddleocr_ja",
    "wrap": {"max_chars": 42, "max_lines": 2, "min_dur_sec": 1.2}
  },
  "subtitles": [
    {"index":1, "start_ms":2000, "end_ms":4200, "text":"今日はVLOGを始めます。"},
    {"index":2, "start_ms":4300, "end_ms":6100, "text":"カフェに向かいます。"}
  ]
}
```

---

## データモデル

* `SubtitleItem`

  * `index: int`
  * `start_ms: int`
  * `end_ms: int`
  * `text: str`
  * `bbox: Optional[Tuple[x,y,w,h]]`（検出領域）
* `Project`

  * `source_video: str`
  * `settings: dict`
  * `subtitles: List[SubtitleItem]`

---

## 抽出アルゴリズム（v1.0）

1. **フレームサンプリング**: 入力動画fpsから `fps_sample`（例 3.0fps）で間引き。各フレームの実時間を保持。
2. **ROI決定**

   * 既定: 下段30%（`BOTTOM_RATIO`）
   * 改良: PaddleOCR Detector で文字領域ヒートマップ→垂直位置分布から字幕帯を推定
   * 手動: 矩形をUIで指定→保存
3. **前処理**: グレースケール→ノイズ除去→適応二値化／拡大縮小（低解像度時）
4. **OCR**: 既定 PaddleOCR(ja)。代替 Tesseract(jpn, PSM=6)。
5. **グルーピング**: 連続フレームで同一/類似テキストを1アイテムに集約（類似度>0.90）。空白フレームは区切り。`min_dur_sec` 未満は前後併合。
6. **整形**: 句読点優先折返し、行長42・最大2行、記号正規化。
7. **QC**: 時刻逆転、オーバーラップ、重複、行数超過、未翻訳の検出とガイダンス表示。

---

## 翻訳

* **内蔵**（オプション）: Google Cloud Translation v3（Glossary対応）、DeepL
* **外部**: CSVエクスポート→GAS（現行運用）→CSVインポート→SRT化
* **RTL対応**: アラビア語等はBidi整形オプション

---

## UI/UX要件

* 非エンジニア想定：

  * ドラッグ&ドロップで動画投入／表形式の直接編集／ショートカット（Space再生、S分割、M結合、Cmd/Ctrl+S保存）
  * テーブル行選択で該当区間ループ再生
  * QC結果は行頭にアイコン表示＋クリックで理由を表示

---

## エラーハンドリング

* 動画コーデック未対応→ffmpeg推奨変換案内
* OCRモデル未DL→初回DLダイアログ（進捗表示）
* 翻訳API失敗→HTTPコード/原因をユーザ文言で表示（キー未設定/残高不足/レート制限）
* CSV整合性エラー→不足列・不一致行を明示、該当行へジャンプ

---

## 既定値（初期設定）

* `fps_sample`: 3.0
* `roi_mode`: 下段30%
* OCR: PaddleOCR(ja)
* 整形: 行長42 / 最大2行 / 最小表示1.2s / 類似度0.90
* 出力言語: en/zh/ko/ar（UIで増減）
* 文字コード: UTF-8（BOMなし）

---

## ディレクトリ構成（提案）

```
app/
  main.py
  ui/
    main_window.py
    views/
      player_view.py
      table_view.py
      translate_view.py
      settings_view.py
  core/
    extractor/
      sampler.py
      roi.py
      detector.py
      ocr.py
      group.py
    qc/
      rules.py
    format/
      srt.py
      csvio.py
      bidi.py
    translate/
      provider_google.py
      provider_deepl.py
      glossary.py
  assets/
    icons/
  models/
    paddleocr/   # 初回DL or 同梱
  config/
    app.yml
  tests/
  packaging/
    pyinstaller.spec
```

---

## 受け入れ基準（v1.0）

1. 動画ドラッグ&ドロップ→\[自動抽出]で日本語字幕がテーブルに並ぶこと。
2. 行編集ができ、該当区間の動画プレビューが同期すること。
3. QCで行長/行数/重複/時間矛盾を検知して表示できること。
4. 日本語SRTを `{basename}.ja.srt` として正しく保存できること。
5. 翻訳タブで "CSVに書き出す" → 外部翻訳CSVを取り込み → 多言語SRTを `{basename}.{lang}.srt` で一括保存できること。
6. macOS/Windows/Linux の最新版で起動・処理・保存が完了すること（PyInstallerビルド）。

---

## 開発タスク（優先度順）

* P1: サンプル動画での **下段30% + PaddleOCR** 抽出／グルーピング／SRT保存
* P1: テーブル編集とプレビュー同期、分割/結合の基本操作
* P1: CSVエクスポート/インポート（翻訳前→後）
* P2: QCルール実装（行長/行数/時間矛盾/オーバーラップ/重複）
* P2: 設定画面（抽出/整形/出力）
* P2: RTL整形（ar）
* P3: 自動字幕帯検出（Detector）切替
* P3: 翻訳プロバイダ（Google v3/DeepL）
* P3: バッチ処理（複数動画）

---

## 実装ポリシー / 注意点

* 初版は **“動く最小”** を最優先（下段30% ROI固定で成立させる）。
* OCRはPaddleOCRを既定、Tesseractはオプション（オフライン要件向け）。
* 文字正規化・折返し・最小表示秒は **ユーザーに見える結果** を最適化する。
* ログはユーザ向け（簡易）と開発向け（詳細）を分離。
* モジュールは **交換可能（Strategy/Adapter）** に設計し、後の精度改善・API差替えに耐える。

---

## 動作確認用の想定テスト

* 背景が明るく字幕が白縁のVLOG（一般的）
* 解像度が低い/高いケース（720p ↔ 4K）
* 字幕の出現間隔が短い・長い、同一文が繰返す
* アラビア語のRTL出力確認（Bidi整形ON/OFF）

---

## 生成物

* アプリ実行ファイル（macOS .app / Windows .exe / Linux AppImage）
* ドキュメント：README（インストール/初回モデルDL/基本操作）
* サンプル: 入力動画、出力SRT、CSV、Glossary 見本

---

### ClaudeCode への依頼文サマリ（この仕様の要点）

* 本仕様に従い、Python + PySide6 でv1.0を実装。
* まずは **下段30% ROI + PaddleOCR(ja)** で抽出→テーブル編集→SRT出力を完成。
* CSV連携（翻訳前/後）を実装し、外部GASワークフローに対応。
* 設定・QC・整形・RTLは仕様の既定値で入れる。
* その後、Detector切替や翻訳API内蔵等を段階追加。

> 質問や前提確認が必要な場合は、このドキュメントにコメントで追記してください。
