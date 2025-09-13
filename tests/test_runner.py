"""
テストランナー
"""

import sys
import pytest
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_unit_tests():
    """単体テストを実行"""
    return pytest.main([
        "tests/unit/",
        "-v",
        "--tb=short",
        "--cov=app",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov"
    ])


def run_integration_tests():
    """統合テストを実行"""
    return pytest.main([
        "tests/integration/",
        "-v",
        "--tb=short"
    ])


def run_all_tests():
    """全テストを実行"""
    return pytest.main([
        "tests/",
        "-v",
        "--tb=short",
        "--cov=app",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov"
    ])


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="テストランナー")
    parser.add_argument(
        "test_type", 
        choices=["unit", "integration", "all"],
        default="all",
        nargs="?",
        help="実行するテストタイプ"
    )
    
    args = parser.parse_args()
    
    if args.test_type == "unit":
        exit_code = run_unit_tests()
    elif args.test_type == "integration":
        exit_code = run_integration_tests()
    else:
        exit_code = run_all_tests()
    
    sys.exit(exit_code)