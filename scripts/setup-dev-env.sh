#!/bin/bash

# VLog字幕ツール 開発環境セットアップスクリプト
# Usage: ./scripts/setup-dev-env.sh

set -e

echo "🚀 VLog字幕ツール開発環境をセットアップしています..."

# Python version check
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.12"

echo "📋 Python version: $PYTHON_VERSION"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python $REQUIRED_VERSION 以上が必要です (現在: $PYTHON_VERSION)"
    exit 1
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 仮想環境を作成しています..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 仮想環境を有効化しています..."
source venv/bin/activate

# Upgrade pip
echo "📈 pipを最新版にアップデートしています..."
pip install --upgrade pip

# Install dependencies
echo "📚 依存関係をインストールしています..."
pip install -r requirements.txt

# Install development dependencies
echo "🛠️ 開発用ツールをインストールしています..."
pip install black isort mypy pytest pytest-cov pyinstaller safety

# Install pre-commit hooks if available
if [ -f ".pre-commit-config.yaml" ]; then
    echo "🪝 pre-commitフックをインストールしています..."
    pip install pre-commit
    pre-commit install
fi

# Create development directories
echo "📁 開発用ディレクトリを作成しています..."
mkdir -p logs
mkdir -p temp
mkdir -p test_outputs
mkdir -p test_videos

# Set up Git hooks (if not using pre-commit)
if [ ! -f ".pre-commit-config.yaml" ]; then
    echo "🔗 Gitフックをセットアップしています..."
    cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
# 自動コードフォーマットとチェック
echo "🔍 コード品質チェック中..."

# Black formatting check
if ! black --check --diff app/ tests/ 2>/dev/null; then
    echo "❌ コードフォーマットが必要です: black app/ tests/"
    exit 1
fi

# Import sorting check
if ! isort --check-only --diff app/ tests/ 2>/dev/null; then
    echo "❌ import文の並び替えが必要です: isort app/ tests/"
    exit 1
fi

echo "✅ コード品質チェック通過"
EOF
    chmod +x .git/hooks/pre-commit
fi

# Create development configuration
cat > .env.dev << 'EOF'
# 開発環境用設定
VLOG_SUBS_DEBUG=true
PYTHONPATH=.
EOF

echo ""
echo "🎉 開発環境のセットアップが完了しました！"
echo ""
echo "📋 次のステップ:"
echo "1. 仮想環境の有効化: source venv/bin/activate"
echo "2. アプリケーションの起動: python app/main.py"
echo "3. テストの実行: python -m pytest tests/"
echo "4. コードフォーマット: black app/ tests/"
echo "5. 型チェック: mypy app/"
echo ""
echo "🛠️ 開発用コマンド:"
echo "- フォーマット: black app/ tests/ && isort app/ tests/"
echo "- テスト実行: python -m pytest tests/ -v"
echo "- ビルド: ./scripts/build_binary.sh --platform linux"
echo "- セキュリティチェック: safety check"
echo ""
echo "📖 詳細は README.md をご覧ください"