"""
AI PM Framework - テストランナー

全テストを実行するスクリプト。
"""

import sys
from pathlib import Path

# aipm-db を aipm_db としてインポートできるようにシンボリックリンク相当の処理
# パスを追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# aipm-db を aipm_db としてインポートできるようにする
import importlib.util
aipm_db_path = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("aipm_db", aipm_db_path / "__init__.py")
aipm_db = importlib.util.module_from_spec(spec)
sys.modules["aipm_db"] = aipm_db

# サブモジュールも登録
config_spec = importlib.util.spec_from_file_location("aipm_db.config", aipm_db_path / "config.py")
config_module = importlib.util.module_from_spec(config_spec)
sys.modules["aipm_db.config"] = config_module
config_spec.loader.exec_module(config_module)

# utils パッケージを登録
sys.modules["aipm_db.utils"] = type(sys)("aipm_db.utils")

# utils.db を登録
db_spec = importlib.util.spec_from_file_location("aipm_db.utils.db", aipm_db_path / "utils" / "db.py")
db_module = importlib.util.module_from_spec(db_spec)
sys.modules["aipm_db.utils.db"] = db_module
db_spec.loader.exec_module(db_module)

# utils.validation を登録
validation_spec = importlib.util.spec_from_file_location("aipm_db.utils.validation", aipm_db_path / "utils" / "validation.py")
validation_module = importlib.util.module_from_spec(validation_spec)
sys.modules["aipm_db.utils.validation"] = validation_module
validation_spec.loader.exec_module(validation_module)

# utils.transition を登録
transition_spec = importlib.util.spec_from_file_location("aipm_db.utils.transition", aipm_db_path / "utils" / "transition.py")
transition_module = importlib.util.module_from_spec(transition_spec)
sys.modules["aipm_db.utils.transition"] = transition_module
transition_spec.loader.exec_module(transition_module)


def run_all():
    """全テストを実行"""
    print("=" * 60)
    print("AI PM Framework - Database Module Tests")
    print("=" * 60)

    # 各テストモジュールをインポートして実行
    # 直接インポートではなくimportlibを使用
    import importlib.util
    test_dir = Path(__file__).parent

    def run_test_module(module_name):
        """テストモジュールを実行"""
        module_path = test_dir / f"{module_name}.py"
        if not module_path.exists():
            print(f"SKIP: {module_name} not found")
            return

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, 'run_all_tests'):
            module.run_all_tests()

    run_test_module("test_validation")
    run_test_module("test_db")
    run_test_module("test_transition")

    print("=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
