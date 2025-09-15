了解。リポジトリの OCR 実装（PaddleOCR/Tesseract対応）を読むと、**PaddleOCR 初期化が不安定になる根本原因**がいくつか混在しています。下に**問題点の特定**→**修正方針**→\*\*ClaudeCode 向けの具体的な修正指示（パッチ案付き）\*\*をまとめました。&#x20;

---

# 要旨（まず直すべき3点）

1. **PaddleX と PaddleOCR の扱いが混線**

* `paddlex` が import できた場合に **`PADDLEOCR_AVAILABLE=True` にしてしまう**ロジックがあり、実際には `paddleocr` が未導入でも「あることに」なってしまう。
* その結果、**フォールバックで `from paddleocr import PaddleOCR` が落ちる**ケースが発生。
  → *PaddleX は完全に任意扱い*。**可用性フラグを分離**し、PaddleOCR を確実に import して可否判定する。

2. **モデル存在チェック（キャッシュ判定）が誤り**

* PaddleOCR のモデルキャッシュは通常 `~/.paddleocr` 配下だが、コードは **`~/.paddlex/official_models` を見て判定**している。
  → これだと **常に「未ダウンロード」判定**になりやすい。**`~/.paddleocr` を判定**対象にする（必要なら両方見る）。

3. **安全ラッパ `_create_safe_paddleocr_kwargs` が必要パラメータを落とす**

* `base_kwargs` の `use_angle_cls`, `show_log`, `use_space_char`, `drop_score` などが **無視される**。
* さらに Windows 分岐で **`use_angle_cls=True` を潰してしまう**箇所がある。
  → **渡された有効なキーをそのまま尊重**し、デフォルトを補う最小限の合流に改める。

---

# 問題点（詳細）

* **可用性フラグの誤設定**
  `paddlex` import 成功時に `PADDLEX_AVAILABLE=True` と同時に **`PADDLEOCR_AVAILABLE=True` まで立てている**。`paddleocr` を import できていないのに利用可能と誤認。（→ フォールバックで例外）&#x20;

* **モデル存在チェック先の誤り**
  `OCRModelDownloader.is_paddleocr_model_available()` が **`.paddlex/official_models`** の存在をもって判定しているため、**純正 PaddleOCR の自動DLキャッシュ（`~/.paddleocr`）を見ていない**。結果として毎回 DL しようとして初期化に失敗しやすい。&#x20;

* **初期化用キーワードの破棄/上書き**
  `_create_safe_paddleocr_kwargs()` が `use_angle_cls`, `show_log`, `use_space_char`, `drop_score`, `cls_model_dir` などを **破棄**。さらに Windows 分岐で **`paddleocr_kwargs` を `{ 'lang': 'japan', 'use_gpu': False }` に作り直し**、上位で指定した `use_angle_cls=True` を失う。**日本語縦横や角度補正が効かない**→精度悪化/失敗の一因。&#x20;

* **PaddleX パイプライン優先での複雑化**
  PaddleX の `create_pipeline(task="OCR")` 試行が多段になっており、**失敗時例外メッセージが肥大化**。まずは **従来の `PaddleOCR` を既定**にして安定させ、PaddleX はオプションにするのが安全。&#x20;

---

# 修正方針

* **優先順位の単純化**：

  1. まず **従来 PaddleOCR（CPU, lang='japan', use\_angle\_cls=True, show\_log=False）で初期化**
  2. 失敗時のみ **PaddleX を試す（任意）**
* **可用性フラグの厳格化**：`paddleocr` と `paddlex` の import 判定を**完全分離**。
* **モデルキャッシュの正しい判定**：`~/.paddleocr`（必要なら `~/.paddlex` も）を確認。
* **kwargs の合流を素直に**：渡された `base_kwargs` を尊重し、**欠けている最低限（`use_gpu` 既定 False など）だけ補完**。
* **Windows 特有の上書きをやめる**：必要でも **既存キーを潰さない**形で merge。

---

# ClaudeCode 向け修正指示（AIがそのまま適用できる形）

以下の差分を適用してください。該当ファイルは **OCRエンジンの実装ファイル**（あなたのリポジトリ内で PaddleOCR/Tesseract を定義している Python ファイル）です。**行番号は環境でずれるので、関数/クラス名を目印**にパッチを当ててください。&#x20;

## 1) import と可用性フラグを厳密化

```diff
@@
-# PaddleOCR（推奨）
-try:
-    # 新しいPaddleX v3.2+を先に試行
-    try:
-        from paddlex import create_pipeline
-        PADDLEX_AVAILABLE = True
-        PADDLEOCR_AVAILABLE = True
-        logging.info("PaddleX v3.2+ が利用可能です")
-    except ImportError:
-        # 従来のPaddleOCRにフォールバック
-        from paddleocr import PaddleOCR
-        PADDLEX_AVAILABLE = False
-        PADDLEOCR_AVAILABLE = True
-        logging.info("従来のPaddleOCR が利用可能です")
-except ImportError:
-    PADDLEX_AVAILABLE = False
-    PADDLEOCR_AVAILABLE = False
-    logging.warning("PaddleOCRが利用できません。pip install paddleocrでインストールしてください。")
+PADDLEOCR_AVAILABLE = False
+PADDLEX_AVAILABLE = False
+# まず PaddleOCR の可否を厳密に判定
+try:
+    from paddleocr import PaddleOCR
+    PADDLEOCR_AVAILABLE = True
+    logging.info("PaddleOCR が利用可能です")
+except ImportError:
+    logging.warning("PaddleOCR が利用できません。pip install paddleocr を実行してください。")
+# 任意: PaddleX はあくまでオプション
+try:
+    from paddlex import create_pipeline
+    PADDLEX_AVAILABLE = True
+    logging.info("PaddleX v3.2+ が利用可能です（任意機能）")
+except ImportError:
+    pass
```

## 2) `_create_safe_paddleocr_kwargs` を「落とさない合流」に変更

```diff
 def _create_safe_paddleocr_kwargs(base_kwargs: dict) -> dict:
-    """PaddleOCRの設定をシンプルで安全な方法で作成"""
-    lang = base_kwargs.get("lang", "japan")
-    det_model_dir = base_kwargs.get("det_model_dir")
-    rec_model_dir = base_kwargs.get("rec_model_dir")
-
-    safe_config = {
-        'lang': lang,
-        'use_gpu': False  # 必ずCPUモード
-    }
-
-    if det_model_dir and rec_model_dir:
-        safe_config.update({
-            'det_model_dir': det_model_dir,
-            'rec_model_dir': rec_model_dir,
-            'use_angle_cls': False  # 角度分類は無効化
-        })
-
-    logging.info(f"シンプルPaddleOCR設定を使用: {safe_config}")
-    return safe_config
+    """
+    PaddleOCR への kwargs を安全に整形する。
+    - base_kwargs を尊重しつつ、デフォルトで use_gpu=False を補うのみ
+    - 渡された use_angle_cls / show_log / use_space_char / drop_score などは破棄しない
+    """
+    merged = dict(base_kwargs) if base_kwargs else {}
+    merged.setdefault("use_gpu", False)        # 既定は CPU
+    merged.setdefault("lang", "japan")         # 既定は日本語
+    # None をわざわざ上書きしない
+    logging.info(f"PaddleOCR 初期化設定: {merged}")
+    return merged
```

## 3) モデルキャッシュ判定を PaddleOCR 既定に修正（必要なら PaddleX も追加チェック）

```diff
 class OCRModelDownloader:
@@
-    def get_paddleocr_cache_dir() -> Path:
-        """PaddleOCRのキャッシュディレクトリ取得"""
-        home_dir = Path.home()
-        # 新しいPaddleXは.paddlexディレクトリを使用
-        cache_dir = home_dir / ".paddlex"
+    def get_paddleocr_cache_dir() -> Path:
+        """PaddleOCRのキャッシュディレクトリ取得（標準: ~/.paddleocr）"""
+        home_dir = Path.home()
+        cache_dir = home_dir / ".paddleocr"
@@
-    def is_paddleocr_model_available(lang: str = "ja") -> bool:
+    def is_paddleocr_model_available(lang: str = "ja") -> bool:
@@
-        try:
-            cache_dir = OCRModelDownloader.get_paddleocr_cache_dir()
-
-            # 日本語モデルの場合、PaddleXのofficial_modelsディレクトリを確認
-            if lang in ["ja", "japan", "japanese"]:
-                official_models_dir = cache_dir / "official_models"
-
-                required_models = [
-                    "PP-OCRv5_server_det",
-                    "PP-OCRv5_server_rec",
-                ]
-
-                for model_name in required_models:
-                    model_dir = official_models_dir / model_name
-                    if not model_dir.exists() or not any(model_dir.iterdir()):
-                        logging.debug(f"PaddleXモデル未検出: {model_name}")
-                        return False
-
-                logging.debug(f"PaddleXモデルが利用可能: {required_models}")
-                return True
-
-            return cache_dir.exists() and (cache_dir / "official_models").exists()
+        try:
+            # PaddleOCR の既定キャッシュ
+            poc = OCRModelDownloader.get_paddleocr_cache_dir()
+            # 代表的なディレクトリが生成されているかでざっくり判定
+            if poc.exists() and any(poc.rglob("inference.*")):
+                return True
+            # 任意: PaddleX 側の公式モデルも見る（存在すれば OK とみなす）
+            px = Path.home() / ".paddlex" / "official_models"
+            if px.exists() and any(px.iterdir()):
+                return True
+            return False
```

> ※ 厳密なファイル名まで固定すると将来のモデル更新に弱いので、**存在性ベース**の緩い判定にしています。必要なら `PP-OCRv5*` を追加でチェックしてください。

## 4) Windows 分岐で渡された設定を潰さない

```diff
-# （複数箇所）Windows環境でのメモリ使用量制限（シンプル版）
-if sys.platform == 'win32':
-    # モデルパスを削除してメモリ使用量を削減
-    paddleocr_kwargs = {
-        'lang': paddleocr_kwargs.get('lang', 'japan'),
-        'use_gpu': False
-    }
+# Windows でも上位設定を尊重。必要があれば追加で setdefault のみ行う
+if sys.platform == 'win32':
+    paddleocr_kwargs.setdefault('use_gpu', False)
```

## 5) 初期化フロー：**PaddleOCR を既定**、PaddleX は後段オプションに

```diff
-# 新しいPaddleX v3.2+を優先して試行
-if PADDLEX_AVAILABLE:
-    ...（多段の create_pipeline）...
-    if paddle_pipeline:
-        self.ocr_model = paddle_pipeline
-        self.is_paddlex = True
-    else:
-        例外...
-else:
-    # 従来のPaddleOCRを使用
-    from paddleocr import PaddleOCR
-    self.ocr_model = PaddleOCR(**paddleocr_kwargs)
+from paddleocr import PaddleOCR
+self.ocr_model = PaddleOCR(**paddleocr_kwargs)
+self.is_paddlex = False
+# 任意の最適化として、初期化が成功した後に PADDLEX_AVAILABLE なら
+# ベンチマークして置き換える程度に留める（安定性優先）
```

※ どうしても PaddleX 優先が必要なら、その時点で **PaddleX 結果→従来形式への変換**の信頼性（`_convert_paddlex_results`）も保証する必要があります。現状は戻りの JSON 形が不確実なため、**既定は PaddleOCR**が安全です。

## 6) Bundled モデル（同梱モデル）初期化でも kwargs を落とさない

```diff
- base_kwargs = {
-   "det_model_dir": str(det_model_path),
-   "rec_model_dir": str(rec_model_path),
-   "use_angle_cls": False,
-   "lang": paddle_lang,
-   "show_log": False,
-   "cls_model_dir": None,
-   "use_space_char": True,
-   "drop_score": 0.5
- }
- paddleocr_kwargs = _create_safe_paddleocr_kwargs(base_kwargs)
+ base_kwargs = {
+   "det_model_dir": str(det_model_path),
+   "rec_model_dir": str(rec_model_path),
+   "use_angle_cls": True,          # 角度補正は既定で有効
+   "lang": paddle_lang,
+   "show_log": False,
+   "use_space_char": True,
+   "drop_score": 0.5
+ }
+ paddleocr_kwargs = _create_safe_paddleocr_kwargs(base_kwargs)  # ← ここで保持されるようになった
```

---

# 動作確認チェックリスト

1. **PaddleOCR 単独で初期化できること**（`lang='japan'`, `use_angle_cls=True`, CPU）
2. **モデル存在チェックが True になること**（2回目以降の実行で「毎回DL」にならない）
3. **Windows でも `use_angle_cls` が維持されること**
4. （任意）**Bundled モデル**で `det/rec` パスが正しく使われ、`drop_score` 等が生きること
5. （任意）**PaddleX** を使う設定に変更しても、**PaddleOCR がなければ落ちない**こと（フラグ分離の効果）

---

# 失敗が続く場合の最小再現テスト

* 以下のスニペットで**静止画 1枚**に対して `.ocr()` が動くかを確認（初回でモデルDLをトリガー）：

```python
from paddleocr import PaddleOCR
import cv2
import numpy as np

ocr = PaddleOCR(lang="japan", use_angle_cls=True, use_gpu=False, show_log=False)
img = np.ones((100, 300, 3), dtype=np.uint8) * 255
res = ocr.ocr(img)
print(type(res), len(res))
```

* 上が動けば、**初期化の問題は解消**しているはずです。あとは GUI/フレーム抽出層に進みましょう。

---

必要ならこの指示を\*\*パッチ化（PR用の diff）\*\*まで展開します。まずは上記 1～3 の修正で、**PaddleOCR 初期化の安定化**が見込めます。
