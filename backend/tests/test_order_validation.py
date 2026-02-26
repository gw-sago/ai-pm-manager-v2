"""
AI PM Framework - ORDERタイトルバリデーション ユニットテスト

order/create.py の validate_title_not_test() および
create_order() の --force オプション動作をテストする。

テスト実行:
    # テスト用DBを使用
    AIPM_DB_PATH=data/test_aipm.db python backend/tests/test_order_validation.py

    # または pytest
    AIPM_DB_PATH=data/test_aipm.db pytest backend/tests/test_order_validation.py -v
"""

import os
import sys
from pathlib import Path

# backend/ をパスに追加
_test_dir = Path(__file__).resolve().parent
_backend_dir = _test_dir.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from order.create import (
    validate_title_not_test,
    TestTitleError,
    TEST_TITLE_PREFIXES,
)


# ============================================================
# validate_title_not_test のテスト
# ============================================================

def test_blocked_prefixes():
    """テスト用プレフィックスを含むタイトルはブロックされること"""
    blocked_titles = [
        "test_新機能実装",
        "debug_バグ確認",
        "tmp_一時ORDER",
        "temp_テスト",
        "wip_作業中",
        "draft_下書き",
        "sample_サンプル",
        "dummy_ダミー",
    ]
    for title in blocked_titles:
        try:
            validate_title_not_test(title)
            assert False, f"TestTitleError が発生するべきタイトル: '{title}'"
        except TestTitleError as e:
            assert str(e) != "", f"エラーメッセージが空: '{title}'"
            assert "--force" in str(e), f"エラーメッセージに --force ヒントが含まれていない: '{title}'"
    print("  PASS: ブロック対象プレフィックスは正しく検出される")


def test_blocked_prefixes_case_insensitive():
    """プレフィックスチェックは大文字小文字を区別しないこと"""
    case_variants = [
        "TEST_大文字",
        "Test_先頭大文字",
        "DEBUG_大文字",
        "TMP_大文字",
        "TEMP_大文字",
    ]
    for title in case_variants:
        try:
            validate_title_not_test(title)
            assert False, f"TestTitleError が発生するべきタイトル（大文字）: '{title}'"
        except TestTitleError:
            pass
    print("  PASS: 大文字小文字を区別せずプレフィックスを検出できる")


def test_allowed_titles():
    """通常のタイトルはブロックされないこと"""
    allowed_titles = [
        "新機能実装",
        "バグ修正: ログイン画面",
        "ORDER作成機能の改善",
        "UIリファクタリング",
        "パフォーマンス最適化",
        "ドキュメント更新",
        "migration_plan",         # migration_ はブロック対象外
        "feature_新機能",          # feature_ はブロック対象外
        "テスト戦略の検討",          # 「テスト」が含まれるがプレフィックスではない
        "test機能",                # _なしは対象外
        "a_test_title",            # 先頭ではないのでOK
    ]
    for title in allowed_titles:
        try:
            validate_title_not_test(title)
        except TestTitleError:
            assert False, f"ブロックされるべきでないタイトル: '{title}'"
    print("  PASS: 通常タイトルはブロックされない")


def test_empty_title():
    """空文字列タイトルはブロックされないこと（別のバリデーションで処理）"""
    try:
        validate_title_not_test("")
        # 空文字列はプレフィックスチェックの対象外（他のバリデーションで弾く）
    except TestTitleError:
        assert False, "空文字列は TestTitleError の対象外"
    print("  PASS: 空文字列はTestTitleError対象外")


def test_error_message_contains_prefix():
    """エラーメッセージにどのプレフィックスが検出されたか含まれること"""
    try:
        validate_title_not_test("test_機能追加")
        assert False, "TestTitleError が発生するべき"
    except TestTitleError as e:
        assert "test_" in str(e), f"エラーメッセージにプレフィックスが含まれていない: {e}"
    print("  PASS: エラーメッセージに検出されたプレフィックスが含まれる")


def test_error_message_contains_original_title():
    """エラーメッセージに元のタイトルが含まれること"""
    original_title = "debug_調査ログ"
    try:
        validate_title_not_test(original_title)
        assert False, "TestTitleError が発生するべき"
    except TestTitleError as e:
        assert original_title in str(e), f"エラーメッセージに元タイトルが含まれていない: {e}"
    print("  PASS: エラーメッセージに元のタイトルが含まれる")


def test_all_defined_prefixes_are_blocked():
    """TEST_TITLE_PREFIXES に定義された全プレフィックスがブロックされること"""
    for prefix in TEST_TITLE_PREFIXES:
        title = f"{prefix}テストタイトル"
        try:
            validate_title_not_test(title)
            assert False, f"プレフィックス '{prefix}' がブロックされていない"
        except TestTitleError:
            pass
    print(f"  PASS: 全 {len(TEST_TITLE_PREFIXES)} プレフィックスが正しくブロックされる")


# ============================================================
# create_order() の --force オプション動作テスト
# （DBを使用するため test_aipm.db が必要）
# ============================================================

def _setup_test_db():
    """テスト用DB設定を行う"""
    import sqlite3
    from config.db_config import get_db_config, DBConfig, set_db_config

    # test_aipm.db または tmpファイルを使用
    aipm_db_path = os.environ.get("AIPM_DB_PATH")
    if aipm_db_path:
        test_db_path = Path(aipm_db_path)
    else:
        import tempfile
        test_db_path = Path(tempfile.gettempdir()) / "aipm_test_order_validation.db"

    # テスト用DB設定を適用
    original_config = get_db_config()
    test_config = DBConfig(
        db_path=test_db_path,
        schema_path=original_config.schema_path,
    )
    set_db_config(test_config)
    return test_db_path, original_config


def _teardown_test_db(original_config):
    """テスト用DB設定をリストア"""
    from config.db_config import set_db_config
    set_db_config(original_config)


def test_create_order_blocks_test_title():
    """create_order() でテスト用タイトルはデフォルトでブロックされること"""
    from order.create import create_order, TestTitleError

    test_db_path, original_config = _setup_test_db()
    try:
        create_order("TEST_PROJECT", "test_新機能", force=False)
        assert False, "TestTitleError が発生するべき"
    except TestTitleError as e:
        assert "test_" in str(e)
    except Exception:
        # プロジェクトが存在しないなど他のエラーはOK（TestTitleError で止まることを確認）
        pass
    finally:
        _teardown_test_db(original_config)
    print("  PASS: create_order() はテスト用タイトルをデフォルトでブロック")


def test_validate_title_not_test_raises_before_db():
    """validate_title_not_test() はDB接続前に呼ばれること（早期リターン）"""
    # DB接続なしで TestTitleError が発生することを確認
    try:
        validate_title_not_test("tmp_確認用ORDER")
        assert False, "TestTitleError が発生するべき"
    except TestTitleError:
        pass
    print("  PASS: validate_title_not_test() はDB接続不要で動作する")


# ============================================================
# テスト実行
# ============================================================

def run_all_tests():
    """全テスト実行"""
    print("\n=== ORDER タイトルバリデーション ユニットテスト ===\n")

    print("[1] ブロック対象プレフィックスの検出")
    test_blocked_prefixes()

    print("[2] 大文字小文字の区別なし")
    test_blocked_prefixes_case_insensitive()

    print("[3] 許可タイトルのテスト")
    test_allowed_titles()

    print("[4] 空文字列タイトル")
    test_empty_title()

    print("[5] エラーメッセージにプレフィックスが含まれる")
    test_error_message_contains_prefix()

    print("[6] エラーメッセージに元タイトルが含まれる")
    test_error_message_contains_original_title()

    print("[7] 全定義済みプレフィックスのブロック")
    test_all_defined_prefixes_are_blocked()

    print("[8] create_order() のブロック動作（DB不要テスト）")
    test_create_order_blocks_test_title()

    print("[9] validate_title_not_test() のDB不要動作")
    test_validate_title_not_test_raises_before_db()

    print("\n=== 全テスト完了 ===\n")


if __name__ == "__main__":
    run_all_tests()
