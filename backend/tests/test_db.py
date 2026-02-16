"""
AI PM Framework - DB接続ユーティリティテスト

utils/db.py の機能をテスト。
"""

import sqlite3
import tempfile
from pathlib import Path
import sys

# 親ディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from aipm_db.utils.db import (
    get_connection,
    close_connection,
    transaction,
    execute_query,
    execute_many,
    fetch_one,
    fetch_all,
    row_to_dict,
    rows_to_dicts,
    init_database,
    table_exists,
    count_rows,
    DatabaseError,
)
from aipm_db.config import get_db_config


def test_get_connection():
    """DB接続テスト"""
    print("Test: get_connection")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        conn = get_connection(db_path)

        # 接続が有効であることを確認
        assert conn is not None
        cursor = conn.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1

        # 外部キー制約が有効であることを確認
        cursor = conn.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()
        assert result[0] == 1

        close_connection(conn)
        print("  PASS: Connection created and closed successfully")

    finally:
        db_path.unlink(missing_ok=True)


def test_transaction_commit():
    """トランザクション正常コミットテスト"""
    print("Test: transaction commit")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        # テーブル作成
        conn = get_connection(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
        close_connection(conn)

        # トランザクション内で挿入
        with transaction(db_path=db_path) as conn:
            execute_query(conn, "INSERT INTO test (id, name) VALUES (?, ?)", (1, "Alice"))
            execute_query(conn, "INSERT INTO test (id, name) VALUES (?, ?)", (2, "Bob"))

        # コミットされたことを確認
        conn = get_connection(db_path)
        rows = fetch_all(conn, "SELECT * FROM test ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"
        assert rows[1]["name"] == "Bob"
        close_connection(conn)

        print("  PASS: Transaction committed successfully")

    finally:
        db_path.unlink(missing_ok=True)


def test_transaction_rollback():
    """トランザクションロールバックテスト"""
    print("Test: transaction rollback")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        # テーブル作成
        conn = get_connection(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
        close_connection(conn)

        # トランザクション内でエラー発生
        try:
            with transaction(db_path=db_path) as conn:
                execute_query(conn, "INSERT INTO test (id, name) VALUES (?, ?)", (1, "Alice"))
                # 意図的にエラーを発生
                raise ValueError("Intentional error")
        except DatabaseError:
            pass  # 期待されるエラー

        # ロールバックされたことを確認
        conn = get_connection(db_path)
        rows = fetch_all(conn, "SELECT * FROM test")
        assert len(rows) == 0
        close_connection(conn)

        print("  PASS: Transaction rolled back successfully")

    finally:
        db_path.unlink(missing_ok=True)


def test_execute_many():
    """一括挿入テスト"""
    print("Test: execute_many")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        conn = get_connection(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")

        # 一括挿入
        data = [(1, "Alice"), (2, "Bob"), (3, "Charlie")]
        execute_many(conn, "INSERT INTO test (id, name) VALUES (?, ?)", data)
        conn.commit()

        rows = fetch_all(conn, "SELECT * FROM test ORDER BY id")
        assert len(rows) == 3
        close_connection(conn)

        print("  PASS: Batch insert successful")

    finally:
        db_path.unlink(missing_ok=True)


def test_row_to_dict():
    """Row→辞書変換テスト"""
    print("Test: row_to_dict")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        conn = get_connection(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)")
        conn.execute("INSERT INTO test VALUES (1, 'Test', 100)")
        conn.commit()

        row = fetch_one(conn, "SELECT * FROM test WHERE id = ?", (1,))
        d = row_to_dict(row)

        assert d["id"] == 1
        assert d["name"] == "Test"
        assert d["value"] == 100

        close_connection(conn)
        print("  PASS: Row to dict conversion successful")

    finally:
        db_path.unlink(missing_ok=True)


def test_init_database():
    """データベース初期化テスト"""
    print("Test: init_database")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        schema_path = get_db_config().schema_path

        if not schema_path.exists():
            print("  SKIP: Schema file not found")
            return

        init_database(db_path, schema_path)

        conn = get_connection(db_path)

        # 主要テーブルの存在確認
        assert table_exists(conn, "projects")
        assert table_exists(conn, "orders")
        assert table_exists(conn, "tasks")
        assert table_exists(conn, "task_dependencies")
        assert table_exists(conn, "review_queue")
        assert table_exists(conn, "backlog_items")
        assert table_exists(conn, "escalations")
        assert table_exists(conn, "change_history")
        assert table_exists(conn, "status_transitions")

        close_connection(conn)
        print("  PASS: Database initialized with schema")

    finally:
        db_path.unlink(missing_ok=True)


def test_count_rows():
    """行数カウントテスト"""
    print("Test: count_rows")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        conn = get_connection(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, category TEXT)")

        data = [
            (1, "A"), (2, "A"), (3, "A"),
            (4, "B"), (5, "B"),
            (6, "C")
        ]
        execute_many(conn, "INSERT INTO test VALUES (?, ?)", data)
        conn.commit()

        # 全件カウント
        assert count_rows(conn, "test") == 6

        # 条件付きカウント
        assert count_rows(conn, "test", "category = ?", ("A",)) == 3
        assert count_rows(conn, "test", "category = ?", ("B",)) == 2
        assert count_rows(conn, "test", "category = ?", ("C",)) == 1

        close_connection(conn)
        print("  PASS: Row count successful")

    finally:
        db_path.unlink(missing_ok=True)


def run_all_tests():
    """全テスト実行"""
    print("\n=== DB Utility Tests ===\n")

    test_get_connection()
    test_transaction_commit()
    test_transaction_rollback()
    test_execute_many()
    test_row_to_dict()
    test_init_database()
    test_count_rows()

    print("\n=== All DB tests passed ===\n")


if __name__ == "__main__":
    run_all_tests()
