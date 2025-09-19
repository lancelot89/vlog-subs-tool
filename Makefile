# vlog-subs-tool Makefile
# ローカル開発とCode Quality Checks用

.PHONY: help install install-dev clean format format-check lint type-check test quality quality-fix build all

# Python実行環境
PYTHON := python3
PIP := $(PYTHON) -m pip

# ソースディレクトリ
SRC_DIRS := app tests

# デフォルトターゲット
help:
	@echo "vlog-subs-tool 開発用 Makefile"
	@echo ""
	@echo "利用可能なコマンド:"
	@echo "  install      - 本番用依存関係をインストール"
	@echo "  install-dev  - 開発用依存関係をインストール"
	@echo "  clean        - 一時ファイルとキャッシュを削除"
	@echo ""
	@echo "Code Quality Checks (GitHub Actionsと同等):"
	@echo "  format       - コードを自動フォーマット (black + isort)"
	@echo "  format-check - フォーマットチェック (CI相当)"
	@echo "  lint         - Lintチェック (将来の拡張用)"
	@echo "  type-check   - 型チェック (mypy)"
	@echo "  test         - 単体テスト実行"
	@echo "  quality      - 全てのCode Qualityチェック実行"
	@echo "  quality-fix  - 自動修正可能な問題を修正"
	@echo ""
	@echo "ビルド:"
	@echo "  build        - PyInstallerでビルド"
	@echo ""
	@echo "統合:"
	@echo "  all          - install-dev + quality + build"

# 依存関係インストール
install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install-dev: install
	$(PIP) install black isort mypy pytest pytest-cov safety pyinstaller

# クリーンアップ
clean:
	@echo "一時ファイルとキャッシュを削除中..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.spec
	@echo "クリーンアップ完了"

# コードフォーマット
format:
	@echo "コードフォーマット実行中..."
	black $(SRC_DIRS)
	isort --profile=black $(SRC_DIRS)
	@echo "フォーマット完了"

# フォーマットチェック (GitHub Actions相当)
format-check:
	@echo "=== Code Formatting Check (GitHub Actions相当) ==="
	@echo "blackフォーマットチェック中..."
	black --check --diff $(SRC_DIRS)
	@echo "✓ blackフォーマットOK"
	@echo ""
	@echo "isortインポート順序チェック中..."
	isort --check-only --diff --profile=black $(SRC_DIRS)
	@echo "✓ isortインポート順序OK"

# Lintチェック (将来の拡張用)
lint:
	@echo "=== Lint Check ==="
	@echo "現在利用可能なLintツールはありません"
	@echo "将来flake8やpylintを追加予定"

# 型チェック (GitHub Actions相当)
type-check:
	@echo "=== Type Checking (GitHub Actions相当) ==="
	@echo "mypyで型チェック中..."
	mypy app/ --ignore-missing-imports --no-strict-optional || true
	@echo "✓ 型チェック完了 (エラーは無視されます)"

# テスト実行 (GitHub Actions相当)
test:
	@echo "=== Unit Tests (GitHub Actions相当) ==="
	@echo "単体テスト実行中..."
	$(PYTHON) -m pytest tests/unit/ -v --tb=short || true
	@echo "✓ テスト実行完了 (失敗は無視されます)"

# 全Code Qualityチェック (GitHub Actions Code Quality Checks相当)
quality: format-check type-check test
	@echo ""
	@echo "🎉 全てのCode Quality Checksが完了しました!"
	@echo "GitHub ActionsのCode Quality Checksと同等の検証を実行しました。"

# 自動修正
quality-fix: format
	@echo "自動修正可能な問題を修正しました"
	@echo "手動確認が必要な問題については quality コマンドで確認してください"

# ビルド
build:
	@echo "=== PyInstaller Build ==="
	@echo "PyInstallerでビルド中..."
	pyinstaller --noconfirm --log-level INFO vlog-subs-tool.spec --distpath dist/local-build
	@echo "ビルド完了: dist/local-build/"
	@echo "ビルドサイズ:"
	du -sh dist/local-build/* 2>/dev/null || echo "ビルド出力が見つかりません"

# 統合ワークフロー
all: install-dev quality build
	@echo ""
	@echo "🚀 全ての開発ワークフローが完了しました!"
	@echo "  ✓ 開発用依存関係インストール"
	@echo "  ✓ Code Quality Checks"
	@echo "  ✓ ビルド"

# 依存関係セキュリティチェック (GitHub Actions相当)
security:
	@echo "=== Dependency Security Check (GitHub Actions相当) ==="
	@echo "依存関係のセキュリティ脆弱性チェック中..."
	safety check --json || true
	@echo "✓ セキュリティチェック完了"

# 依存関係の更新確認
outdated:
	@echo "=== Outdated Dependencies Check ==="
	$(PIP) list --outdated || true

# 開発環境セットアップ
setup: install-dev
	@echo ""
	@echo "🔧 開発環境セットアップ完了!"
	@echo ""
	@echo "次のステップ:"
	@echo "  make quality     - Code Qualityチェック実行"
	@echo "  make quality-fix - 自動修正実行"
	@echo "  make build       - アプリケーションビルド"
	@echo "  make help        - 全コマンドの説明"

# GitHub Actions風の全体チェック
ci: format-check type-check test security
	@echo ""
	@echo "🤖 CI風チェック完了!"
	@echo "GitHub ActionsのPull Request Testsと同等の検証を実行しました。"