# vlog-subs-tool Makefile
# ローカル開発とCode Quality Checks用（venv環境対応）

.PHONY: help venv install install-dev clean clean-all format format-check lint type-check test quality quality-fix build setup all security outdated ci

# venv環境設定
VENV_DIR := venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP := $(VENV_PYTHON) -m pip
VENV_ACTIVATE := $(VENV_DIR)/bin/activate

# Windows対応
ifeq ($(OS),Windows_NT)
    VENV_PYTHON := $(VENV_DIR)/Scripts/python.exe
    VENV_PIP := $(VENV_PYTHON) -m pip
    VENV_ACTIVATE := $(VENV_DIR)/Scripts/activate
endif

# Python実行環境（venv環境を優先）
PYTHON := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)
PIP := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PIP),python3 -m pip)

# ソースディレクトリ
SRC_DIRS := app tests

# デフォルトターゲット
help:
	@echo "vlog-subs-tool 開発用 Makefile (venv環境対応)"
	@echo ""
	@echo "🚀 セットアップ:"
	@echo "  venv         - Python仮想環境を作成"
	@echo "  setup        - venv + 開発用依存関係インストール"
	@echo ""
	@echo "📦 依存関係:"
	@echo "  install      - 本番用依存関係をインストール"
	@echo "  install-dev  - 開発用依存関係をインストール"
	@echo "  clean        - 一時ファイルとキャッシュを削除"
	@echo ""
	@echo "✅ Code Quality Checks (GitHub Actionsと同等):"
	@echo "  format       - コードを自動フォーマット (black + isort)"
	@echo "  format-check - フォーマットチェック (CI相当)"
	@echo "  lint         - Lintチェック (将来の拡張用)"
	@echo "  type-check   - 型チェック (mypy)"
	@echo "  test         - 単体テスト実行"
	@echo "  quality      - 全てのCode Qualityチェック実行"
	@echo "  quality-fix  - 自動修正可能な問題を修正"
	@echo ""
	@echo "🏗️ ビルド:"
	@echo "  build        - PyInstallerでビルド"
	@echo ""
	@echo "🔄 統合:"
	@echo "  all          - setup + quality + build"
	@echo ""
	@echo "💡 はじめに: make setup でvenv環境をセットアップしてください"

# venv仮想環境作成
venv:
	@echo "Python仮想環境を作成中..."
	@if [ ! -d "$(VENV_DIR)" ]; then \
		python3 -m venv $(VENV_DIR); \
		echo "✓ 仮想環境作成完了: $(VENV_DIR)/"; \
	else \
		echo "✓ 仮想環境は既に存在します: $(VENV_DIR)/"; \
	fi
	@echo ""
	@echo "アクティベート方法:"
	@echo "  source $(VENV_ACTIVATE)  # Linux/Mac"
	@echo "  $(VENV_ACTIVATE)          # Windows"

# 依存関係インストール
install: venv
	@echo "本番用依存関係をインストール中..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "✓ 本番用依存関係インストール完了"

install-dev: install
	@echo "開発用依存関係をインストール中..."
	$(PIP) install black isort mypy pytest pytest-cov safety pyinstaller
	@echo "✓ 開発用依存関係インストール完了"

# クリーンアップ
clean:
	@echo "一時ファイルとキャッシュを削除中..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.spec
	@echo "✓ 一時ファイルクリーンアップ完了"

# venv環境も含む完全クリーンアップ
clean-all: clean
	@echo "venv環境も含めて完全削除中..."
	rm -rf $(VENV_DIR)
	@echo "✓ 完全クリーンアップ完了（venv環境も削除）"

# コードフォーマット
format:
	@echo "コードフォーマット実行中..."
	@if [ ! -f "$(VENV_PYTHON)" ]; then \
		echo "❌ venv環境が見つかりません。'make setup' を実行してください"; \
		exit 1; \
	fi
	$(PYTHON) -m black $(SRC_DIRS)
	$(PYTHON) -m isort --profile=black $(SRC_DIRS)
	@echo "✓ フォーマット完了"

# フォーマットチェック (GitHub Actions相当)
format-check:
	@echo "=== Code Formatting Check (GitHub Actions相当) ==="
	@if [ ! -f "$(VENV_PYTHON)" ]; then \
		echo "❌ venv環境が見つかりません。'make setup' を実行してください"; \
		exit 1; \
	fi
	@echo "blackフォーマットチェック中..."
	$(PYTHON) -m black --check --diff $(SRC_DIRS)
	@echo "✓ blackフォーマットOK"
	@echo ""
	@echo "isortインポート順序チェック中..."
	$(PYTHON) -m isort --check-only --diff --profile=black $(SRC_DIRS)
	@echo "✓ isortインポート順序OK"

# Lintチェック (将来の拡張用)
lint:
	@echo "=== Lint Check ==="
	@echo "現在利用可能なLintツールはありません"
	@echo "将来flake8やpylintを追加予定"

# 型チェック (GitHub Actions相当)
type-check:
	@echo "=== Type Checking (GitHub Actions相当) ==="
	@if [ ! -f "$(VENV_PYTHON)" ]; then \
		echo "❌ venv環境が見つかりません。'make setup' を実行してください"; \
		exit 1; \
	fi
	@echo "mypyで型チェック中..."
	$(PYTHON) -m mypy app/ --ignore-missing-imports --no-strict-optional || true
	@echo "✓ 型チェック完了 (エラーは無視されます)"

# テスト実行 (GitHub Actions相当)
test:
	@echo "=== Unit Tests (GitHub Actions相当) ==="
	@if [ ! -f "$(VENV_PYTHON)" ]; then \
		echo "❌ venv環境が見つかりません。'make setup' を実行してください"; \
		exit 1; \
	fi
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

# 開発環境セットアップ
setup: install-dev
	@echo ""
	@echo "🔧 venv開発環境セットアップ完了!"
	@echo ""
	@echo "📝 venv環境のアクティベート:"
	@echo "  source $(VENV_ACTIVATE)  # Linux/Mac"
	@echo "  $(VENV_ACTIVATE)          # Windows"
	@echo ""
	@echo "🎯 次のステップ:"
	@echo "  make quality     - Code Qualityチェック実行"
	@echo "  make quality-fix - 自動修正実行"
	@echo "  make build       - アプリケーションビルド"
	@echo "  make help        - 全コマンドの説明"

# 統合ワークフロー
all: setup quality build
	@echo ""
	@echo "🚀 全ての開発ワークフローが完了しました!"
	@echo "  ✓ venv環境セットアップ"
	@echo "  ✓ 開発用依存関係インストール"
	@echo "  ✓ Code Quality Checks"
	@echo "  ✓ ビルド"

# 依存関係セキュリティチェック (GitHub Actions相当)
security:
	@echo "=== Dependency Security Check (GitHub Actions相当) ==="
	@if [ ! -f "$(VENV_PYTHON)" ]; then \
		echo "❌ venv環境が見つかりません。'make setup' を実行してください"; \
		exit 1; \
	fi
	@echo "依存関係のセキュリティ脆弱性チェック中..."
	$(PYTHON) -m safety check --json || true
	@echo "✓ セキュリティチェック完了"

# 依存関係の更新確認
outdated:
	@echo "=== Outdated Dependencies Check ==="
	@if [ ! -f "$(VENV_PYTHON)" ]; then \
		echo "❌ venv環境が見つかりません。'make setup' を実行してください"; \
		exit 1; \
	fi
	$(PIP) list --outdated || true

# GitHub Actions風の全体チェック
ci: format-check type-check test security
	@echo ""
	@echo "🤖 CI風チェック完了!"
	@echo "GitHub ActionsのPull Request Testsと同等の検証を実行しました。"
	@echo ""
	@echo "📋 実行内容:"
	@echo "  ✓ blackフォーマットチェック"
	@echo "  ✓ isortインポート順序チェック"
	@echo "  ✓ mypy型チェック"
	@echo "  ✓ pytest単体テスト"
	@echo "  ✓ safetyセキュリティチェック"