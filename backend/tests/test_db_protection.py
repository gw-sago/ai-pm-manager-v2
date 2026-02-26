"""
AI PM Framework - 本番DB保護チェック ユニットテスト

config/db_config.py の is_production_db() および
warn_if_production_db() の動作をテストする。

テスト実行:
    # AIPM_DB_PATH 未設定（本番DB判定になる）
    python backend/tests/test_db_protection.py

    # AIPM_DB_PATH を設定（テストDB判定になる）
    AIPM_DB_PATH=data/test_aipm.db python backend/tests/test_db_protection.py

    # または pytest
    pytest backend/tests/test_db_protection.py -v
"""

import io
import os
import sys
from pathlib import Path

# backend/ をパスに追加
_test_dir = Path(__file__).resolve().parent
_backend_dir = _test_dir.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from config.db_config import is_production_db, warn_if_production_db, USER_DATA_PATH


# ============================================================
# is_production_db() のテスト
# ============================================================

def test_production_db_when_env_not_set():
    """AIPM_DB_PATH 未設定時は本番DBと判定されること"""
    original = os.environ.pop("AIPM_DB_PATH", None)
    try:
        result = is_production_db()
        assert result is True, "AIPM_DB_PATH 未設定時は True を返すべき"
    finally:
        if original is not None:
            os.environ["AIPM_DB_PATH"] = original
    print("  PASS: AIPM_DB_PATH 未設定 → 本番DB (True)")


def test_not_production_db_when_temp_path_set():
    """AIPM_DB_PATH に一時パスを設定した場合はテストDBと判定されること"""
    import tempfile
    temp_db = Path(tempfile.gettempdir()) / "aipm_test_check.db"
    os.environ["AIPM_DB_PATH"] = str(temp_db)
    try:
        result = is_production_db()
        assert result is False, f"一時パス設定時は False を返すべき: {temp_db}"
    finally:
        del os.environ["AIPM_DB_PATH"]
    print("  PASS: 一時パス設定 → テストDB (False)")


def test_production_db_when_production_path_set():
    """AIPM_DB_PATH に本番DBパスを明示指定した場合も本番DBと判定されること"""
    production_db_path = USER_DATA_PATH / "data" / "aipm.db"
    os.environ["AIPM_DB_PATH"] = str(production_db_path)
    try:
        result = is_production_db()
        assert result is True, f"本番DBパス設定時は True を返すべき: {production_db_path}"
    finally:
        del os.environ["AIPM_DB_PATH"]
    print("  PASS: 本番DBパス明示設定 → 本番DB (True)")


def test_not_production_db_when_test_aipm_db_set():
    """AIPM_DB_PATH に data/test_aipm.db を設定した場合はテストDBと判定されること"""
    # 相対パスではなく絶対パスで比較するため、AI_PM_ROOT を元にパスを構築
    ai_pm_root = _backend_dir.parent  # backend/ の1つ上
    test_db_path = ai_pm_root / "data" / "test_aipm.db"
    os.environ["AIPM_DB_PATH"] = str(test_db_path)
    try:
        result = is_production_db()
        assert result is False, f"test_aipm.db 設定時は False を返すべき: {test_db_path}"
    finally:
        del os.environ["AIPM_DB_PATH"]
    print("  PASS: test_aipm.db 設定 → テストDB (False)")


def test_production_db_returns_bool():
    """is_production_db() は bool 型を返すこと"""
    original = os.environ.pop("AIPM_DB_PATH", None)
    try:
        result = is_production_db()
        assert isinstance(result, bool), f"bool 型を返すべき: {type(result)}"
    finally:
        if original is not None:
            os.environ["AIPM_DB_PATH"] = original

    os.environ["AIPM_DB_PATH"] = "/tmp/test.db"
    try:
        result = is_production_db()
        assert isinstance(result, bool), f"bool 型を返すべき: {type(result)}"
    finally:
        del os.environ["AIPM_DB_PATH"]
    print("  PASS: is_production_db() は常に bool を返す")


# ============================================================
# warn_if_production_db() のテスト
# ============================================================

def test_warn_outputs_when_production():
    """本番DB使用時に警告メッセージが出力されること"""
    original = os.environ.pop("AIPM_DB_PATH", None)
    try:
        # stderr をキャプチャ
        captured = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured
        try:
            result = warn_if_production_db("test_command")
        finally:
            sys.stderr = original_stderr

        assert result is True, "本番DB時は True を返すべき"
        output = captured.getvalue()
        assert "[WARNING]" in output, f"警告メッセージに [WARNING] が含まれていない: {output!r}"
        assert "本番DB" in output, f"警告メッセージに '本番DB' が含まれていない: {output!r}"
        assert "AIPM_DB_PATH" in output, f"警告メッセージに AIPM_DB_PATH が含まれていない: {output!r}"
    finally:
        if original is not None:
            os.environ["AIPM_DB_PATH"] = original
    print("  PASS: 本番DB時に [WARNING] 警告メッセージが出力される")


def test_warn_includes_command_name():
    """コマンド名が指定された場合、警告メッセージに含まれること"""
    original = os.environ.pop("AIPM_DB_PATH", None)
    try:
        captured = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured
        try:
            warn_if_production_db("full_auto")
        finally:
            sys.stderr = original_stderr

        output = captured.getvalue()
        assert "full_auto" in output, f"コマンド名が警告に含まれていない: {output!r}"
    finally:
        if original is not None:
            os.environ["AIPM_DB_PATH"] = original
    print("  PASS: コマンド名が警告メッセージに含まれる")


def test_no_warn_when_test_db():
    """テストDB使用時は警告が出力されないこと"""
    import tempfile
    temp_db = Path(tempfile.gettempdir()) / "aipm_no_warn_test.db"
    os.environ["AIPM_DB_PATH"] = str(temp_db)
    try:
        captured_stderr = io.StringIO()
        captured_stdout = io.StringIO()
        original_stderr = sys.stderr
        original_stdout = sys.stdout
        sys.stderr = captured_stderr
        sys.stdout = captured_stdout
        try:
            result = warn_if_production_db("test_command")
        finally:
            sys.stderr = original_stderr
            sys.stdout = original_stdout

        assert result is False, "テストDB時は False を返すべき"
        assert captured_stderr.getvalue() == "", f"テストDB時は stderr に出力なし: {captured_stderr.getvalue()!r}"
        assert captured_stdout.getvalue() == "", f"テストDB時は stdout に出力なし: {captured_stdout.getvalue()!r}"
    finally:
        del os.environ["AIPM_DB_PATH"]
    print("  PASS: テストDB使用時は警告出力なし")


def test_warn_stdout_option():
    """stderr=False の場合は stdout に出力されること"""
    original = os.environ.pop("AIPM_DB_PATH", None)
    try:
        captured = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = captured
        try:
            result = warn_if_production_db("test_cmd", stderr=False)
        finally:
            sys.stdout = original_stdout

        assert result is True, "本番DB時は True を返すべき"
        output = captured.getvalue()
        assert "[WARNING]" in output, f"stdout に [WARNING] が含まれていない: {output!r}"
    finally:
        if original is not None:
            os.environ["AIPM_DB_PATH"] = original
    print("  PASS: stderr=False の場合は stdout に警告を出力")


def test_warn_without_command_name():
    """コマンド名なしで呼び出した場合もエラーにならないこと"""
    original = os.environ.pop("AIPM_DB_PATH", None)
    try:
        captured = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured
        try:
            result = warn_if_production_db()  # コマンド名なし
        finally:
            sys.stderr = original_stderr

        assert result is True
        output = captured.getvalue()
        assert "[WARNING]" in output
    finally:
        if original is not None:
            os.environ["AIPM_DB_PATH"] = original
    print("  PASS: コマンド名なしでも正常動作")


# ============================================================
# 環境変数の副作用テスト
# ============================================================

def test_env_var_not_leaked():
    """テスト後に AIPM_DB_PATH が意図せず残らないこと（テスト分離）"""
    original = os.environ.get("AIPM_DB_PATH")

    # AIPM_DB_PATH を設定
    os.environ["AIPM_DB_PATH"] = "/tmp/test_isolation.db"
    assert is_production_db() is False

    # 削除
    del os.environ["AIPM_DB_PATH"]
    # 元の状態に応じて確認
    if original is None:
        assert is_production_db() is True, "AIPM_DB_PATH 削除後は本番DB判定に戻るべき"
    else:
        os.environ["AIPM_DB_PATH"] = original

    print("  PASS: AIPM_DB_PATH の設定/削除が is_production_db() に正しく反映される")


# ============================================================
# テスト実行
# ============================================================

def run_all_tests():
    """全テスト実行"""
    print("\n=== 本番DB保護チェック ユニットテスト ===\n")

    print("[1] AIPM_DB_PATH 未設定 → 本番DB")
    test_production_db_when_env_not_set()

    print("[2] 一時パス設定 → テストDB")
    test_not_production_db_when_temp_path_set()

    print("[3] 本番DBパス明示設定 → 本番DB")
    test_production_db_when_production_path_set()

    print("[4] test_aipm.db 設定 → テストDB")
    test_not_production_db_when_test_aipm_db_set()

    print("[5] is_production_db() の戻り値型")
    test_production_db_returns_bool()

    print("[6] 本番DB時の警告出力")
    test_warn_outputs_when_production()

    print("[7] 警告にコマンド名を含む")
    test_warn_includes_command_name()

    print("[8] テストDB時は警告なし")
    test_no_warn_when_test_db()

    print("[9] stderr=False → stdout 出力")
    test_warn_stdout_option()

    print("[10] コマンド名なし呼び出し")
    test_warn_without_command_name()

    print("[11] 環境変数の副作用チェック")
    test_env_var_not_leaked()

    print("\n=== 全テスト完了 ===\n")


if __name__ == "__main__":
    run_all_tests()
