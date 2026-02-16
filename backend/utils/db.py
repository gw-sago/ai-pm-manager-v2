"""
AI PM Framework - DB接続ユーティリティ

SQLiteデータベースへの接続・クエリ実行・トランザクション管理を提供。
"""

import sqlite3
import re
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple, Union, Generator
import threading

# スレッドローカルなコネクション管理
_local = threading.local()


class DatabaseError(Exception):
    """データベース操作エラー"""
    pass


def get_connection(
    db_path: Optional[Path] = None,
    *,
    check_same_thread: bool = False,
    timeout: float = 30.0,
) -> sqlite3.Connection:
    """
    SQLiteデータベースへの接続を取得

    Args:
        db_path: データベースファイルパス（Noneの場合はデフォルトパスを使用）
        check_same_thread: 同一スレッドチェックを有効にするか（デフォルト: False）
        timeout: ロック待機タイムアウト秒数（デフォルト: 30秒）

    Returns:
        sqlite3.Connection: データベース接続

    Note:
        - Row ファクトリを設定し、辞書形式でアクセス可能
        - 外部キー制約を有効化
    """
    if db_path is None:
        # デフォルトパスはconfigパッケージから取得（循環インポート回避のため遅延インポート）
        try:
            from config import get_db_config
        except ImportError:
            # 直接実行の場合 - backend/config/db_config.pyを明示的にインポート
            import importlib.util
            from pathlib import Path as P
            config_path = P(__file__).resolve().parent.parent / "config" / "db_config.py"
            spec = importlib.util.spec_from_file_location("aipm_db_config", config_path)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            get_db_config = config_module.get_db_config
        db_path = get_db_config().db_path

    db_path = Path(db_path)

    # 親ディレクトリを作成
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(db_path),
        check_same_thread=check_same_thread,
        timeout=timeout,
    )

    # Row ファクトリを設定（辞書形式でアクセス可能）
    conn.row_factory = sqlite3.Row

    # 外部キー制約を有効化
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def close_connection(conn: sqlite3.Connection) -> None:
    """
    データベース接続を閉じる

    Args:
        conn: 閉じる接続
    """
    if conn:
        try:
            conn.close()
        except sqlite3.Error:
            pass


@contextmanager
def transaction(
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Path] = None,
) -> Generator[sqlite3.Connection, None, None]:
    """
    トランザクションを管理するコンテキストマネージャ

    Args:
        conn: 既存の接続（Noneの場合は新規作成）
        db_path: データベースファイルパス（conn がNoneの場合に使用）

    Yields:
        sqlite3.Connection: トランザクション中の接続

    Note:
        - 正常終了時は自動コミット
        - 例外発生時は自動ロールバック

    Example:
        with transaction() as conn:
            execute_query(conn, "INSERT INTO ...")
            execute_query(conn, "UPDATE ...")
        # 自動コミット
    """
    close_on_exit = False
    if conn is None:
        conn = get_connection(db_path)
        close_on_exit = True

    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise DatabaseError(f"トランザクションエラー: {e}") from e
    finally:
        if close_on_exit:
            close_connection(conn)


def execute_query(
    conn: sqlite3.Connection,
    query: str,
    params: Optional[Union[Tuple, Dict]] = None,
) -> sqlite3.Cursor:
    """
    SQLクエリを実行

    Args:
        conn: データベース接続
        query: SQLクエリ文字列
        params: クエリパラメータ（タプルまたは辞書）

    Returns:
        sqlite3.Cursor: 実行結果のカーソル

    Raises:
        DatabaseError: クエリ実行エラー

    Example:
        # タプル形式
        execute_query(conn, "SELECT * FROM tasks WHERE id = ?", ("TASK_188",))

        # 辞書形式
        execute_query(conn, "SELECT * FROM tasks WHERE id = :id", {"id": "TASK_188"})
    """
    try:
        if params:
            return conn.execute(query, params)
        return conn.execute(query)
    except sqlite3.Error as e:
        raise DatabaseError(f"クエリ実行エラー: {e}\nQuery: {query}") from e


def execute_many(
    conn: sqlite3.Connection,
    query: str,
    params_list: List[Union[Tuple, Dict]],
) -> sqlite3.Cursor:
    """
    複数のパラメータでSQLクエリを一括実行

    Args:
        conn: データベース接続
        query: SQLクエリ文字列
        params_list: パラメータのリスト

    Returns:
        sqlite3.Cursor: 実行結果のカーソル

    Raises:
        DatabaseError: クエリ実行エラー

    Example:
        execute_many(
            conn,
            "INSERT INTO tasks (id, title) VALUES (?, ?)",
            [("TASK_001", "タスク1"), ("TASK_002", "タスク2")]
        )
    """
    try:
        return conn.executemany(query, params_list)
    except sqlite3.Error as e:
        raise DatabaseError(f"一括クエリ実行エラー: {e}\nQuery: {query}") from e


def fetch_one(
    conn: sqlite3.Connection,
    query: str,
    params: Optional[Union[Tuple, Dict]] = None,
) -> Optional[sqlite3.Row]:
    """
    1行を取得

    Args:
        conn: データベース接続
        query: SQLクエリ文字列
        params: クエリパラメータ

    Returns:
        sqlite3.Row or None: 結果行（なければNone）

    Example:
        row = fetch_one(conn, "SELECT * FROM tasks WHERE id = ?", ("TASK_188",))
        if row:
            print(row["title"])
    """
    cursor = execute_query(conn, query, params)
    return cursor.fetchone()


def fetch_all(
    conn: sqlite3.Connection,
    query: str,
    params: Optional[Union[Tuple, Dict]] = None,
) -> List[sqlite3.Row]:
    """
    全行を取得

    Args:
        conn: データベース接続
        query: SQLクエリ文字列
        params: クエリパラメータ

    Returns:
        List[sqlite3.Row]: 結果行のリスト

    Example:
        rows = fetch_all(conn, "SELECT * FROM tasks WHERE order_id = ?", ("ORDER_036",))
        for row in rows:
            print(row["id"], row["title"])
    """
    cursor = execute_query(conn, query, params)
    return cursor.fetchall()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """
    sqlite3.Row を辞書に変換

    Args:
        row: 変換する行

    Returns:
        Dict or None: 辞書形式の行データ
    """
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    """
    sqlite3.Row のリストを辞書のリストに変換

    Args:
        rows: 変換する行のリスト

    Returns:
        List[Dict]: 辞書形式の行データのリスト
    """
    return [dict(row) for row in rows]


def init_database(
    db_path: Optional[Path] = None,
    schema_path: Optional[Path] = None,
) -> None:
    """
    データベースを初期化（スキーマ適用）

    Args:
        db_path: データベースファイルパス
        schema_path: スキーマファイルパス（Noneの場合はデフォルト）

    Note:
        - 既存のデータベースがある場合はスキーマのみ適用（データは保持）
        - CREATE IF NOT EXISTS を使用しているため冪等
    """
    if schema_path is None:
        # デフォルトスキーマパスを取得
        try:
            from config import get_db_config
        except ImportError:
            # 直接実行の場合 - backend/config/db_config.pyを明示的にインポート
            import importlib.util
            from pathlib import Path as P
            config_path = P(__file__).resolve().parent.parent / "config" / "db_config.py"
            spec = importlib.util.spec_from_file_location("aipm_db_config", config_path)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            get_db_config = config_module.get_db_config
        config = get_db_config()
        schema_path = config.schema_path

    schema_path = Path(schema_path)

    if not schema_path.exists():
        raise DatabaseError(f"スキーマファイルが見つかりません: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")

    with transaction(db_path=db_path) as conn:
        conn.executescript(schema_sql)


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """
    テーブルが存在するかを確認

    Args:
        conn: データベース接続
        table_name: テーブル名

    Returns:
        bool: テーブルが存在すればTrue
    """
    row = fetch_one(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return row is not None


def count_rows(
    conn: sqlite3.Connection,
    table_name: str,
    where_clause: str = "",
    params: Optional[Union[Tuple, Dict]] = None,
) -> int:
    """
    テーブルの行数をカウント

    Args:
        conn: データベース接続
        table_name: テーブル名
        where_clause: WHERE句（"WHERE "は含めない）
        params: WHERE句のパラメータ

    Returns:
        int: 行数
    """
    query = f"SELECT COUNT(*) as count FROM {table_name}"
    if where_clause:
        query += f" WHERE {where_clause}"

    row = fetch_one(conn, query, params)
    return row["count"] if row else 0


def ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    """
    schema_versionテーブルが存在することを確認

    Args:
        conn: データベース接続
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def get_applied_migrations(conn: sqlite3.Connection) -> List[str]:
    """
    適用済みマイグレーションのバージョンリストを取得

    Args:
        conn: データベース接続

    Returns:
        List[str]: 適用済みバージョンのリスト（例: ['001', '002']）
    """
    ensure_schema_version_table(conn)
    rows = fetch_all(conn, "SELECT version FROM schema_version ORDER BY version")
    return [row["version"] for row in rows]


def record_migration(
    conn: sqlite3.Connection,
    version: str,
    description: str
) -> None:
    """
    マイグレーション適用を記録

    Args:
        conn: データベース接続
        version: マイグレーションバージョン（例: '001'）
        description: マイグレーションの説明
    """
    execute_query(
        conn,
        "INSERT INTO schema_version (version, description) VALUES (?, ?)",
        (version, description)
    )
    conn.commit()


def _split_sql_statements(sql_text: str) -> List[str]:
    """
    SQL文を個別のステートメントに分割する

    executescript()の暗黙的COMMITを回避するため、
    SQLテキストを個別のexecute()呼び出し用に分割する。

    Args:
        sql_text: 分割するSQL文字列

    Returns:
        List[str]: 個別のSQL文のリスト（コメント・空行除去済み）

    Note:
        - コメント行（-- で始まる行）は除去
        - ブロックコメント（/* ... */）は除去
        - セミコロンでステートメントを分割
        - 空のステートメントは除去
    """
    # ブロックコメントを除去
    sql_text = re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)

    # 行コメントを除去
    lines = []
    for line in sql_text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('--'):
            continue
        lines.append(line)
    sql_text = '\n'.join(lines)

    # セミコロンでステートメントを分割
    statements = []
    for stmt in sql_text.split(';'):
        stmt = stmt.strip()
        if stmt:
            statements.append(stmt)

    return statements


def run_migrations(
    db_path: Optional[Path] = None,
    migrations_dir: Optional[Path] = None,
    verbose: bool = True
) -> List[str]:
    """
    未適用のマイグレーションを実行

    Args:
        db_path: データベースファイルパス（Noneの場合はデフォルト）
        migrations_dir: マイグレーションディレクトリ（Noneの場合はデフォルト）
        verbose: 実行ログを出力するか

    Returns:
        List[str]: 適用したマイグレーションバージョンのリスト

    Note:
        - data/migrations/ 内の *.sql ファイルを検出
        - ファイル名形式: {version}_{description}.sql (例: 001_add_column.sql)
        - 未適用のマイグレーションをバージョン順にソート→実行
        - executescript()ではなくexecute()で各SQL文を個別実行
          （executescript()の暗黙的COMMITによるトランザクション問題を回避）
        - PRAGMA文はトランザクション外で実行
    """
    if migrations_dir is None:
        # デフォルトのマイグレーションディレクトリ
        # backend/utils/db.py → backend → ai-pm-manager-v2 → data/migrations
        migrations_dir = Path(__file__).resolve().parent.parent.parent / "data" / "migrations"
    else:
        migrations_dir = Path(migrations_dir)

    if not migrations_dir.exists():
        if verbose:
            print(f"  マイグレーションディレクトリが存在しません: {migrations_dir}")
        return []

    conn = get_connection(db_path)

    try:
        # 適用済みマイグレーションを取得
        applied = get_applied_migrations(conn)

        # マイグレーションファイルを検出
        migration_files = sorted(migrations_dir.glob("*.sql"))

        if not migration_files:
            if verbose:
                print("  マイグレーションファイルが見つかりません")
            return []

        applied_versions = []

        for migration_file in migration_files:
            # ファイル名から version と description を抽出
            # 形式: 001_description.sql
            filename = migration_file.stem  # .sqlを除いた部分
            parts = filename.split("_", 1)

            if len(parts) < 2:
                if verbose:
                    print(f"  無効なマイグレーションファイル名: {migration_file.name}")
                continue

            version, description = parts[0], parts[1]

            # 既に適用済みならスキップ
            if version in applied:
                if verbose:
                    print(f"  スキップ（適用済み）: {version} - {description}")
                continue

            if verbose:
                print(f"  マイグレーション適用中: {version} - {description}")

            try:
                # マイグレーションSQLを読み込み
                migration_sql = migration_file.read_text(encoding="utf-8")

                # SQL文を個別に分割
                statements = _split_sql_statements(migration_sql)

                # PRAGMA文とDDL/DML文を分離
                pragma_statements = []
                regular_statements = []
                for stmt in statements:
                    if stmt.strip().upper().startswith("PRAGMA"):
                        pragma_statements.append(stmt)
                    else:
                        regular_statements.append(stmt)

                # PRAGMA文はトランザクション外で先に実行
                for pragma_stmt in pragma_statements:
                    if verbose:
                        print(f"    PRAGMA実行: {pragma_stmt.strip()}")
                    conn.execute(pragma_stmt)

                # DDL/DML文をトランザクション内で実行
                try:
                    conn.execute("BEGIN")
                    for stmt in regular_statements:
                        try:
                            conn.execute(stmt)
                        except sqlite3.OperationalError as stmt_err:
                            err_msg = str(stmt_err).lower()
                            # ALTER TABLE ADD COLUMNで既にカラムが存在する場合は許容
                            # （schema_v2.sqlで既に追加済みのDBに対するマイグレーション）
                            if "duplicate column name" in err_msg:
                                if verbose:
                                    print(f"    スキップ（既存カラム）: {stmt_err}")
                                continue
                            raise
                    # マイグレーション適用を記録
                    conn.execute(
                        "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                        (version, description)
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

                # PRAGMA foreign_keys = ON を復元（OFFにしていた場合）
                conn.execute("PRAGMA foreign_keys = ON")

                applied_versions.append(version)

                if verbose:
                    print(f"  マイグレーション完了: {version}")

            except Exception as e:
                if verbose:
                    print(f"  マイグレーション失敗: {version}")
                    print(f"   エラー: {e}")
                raise DatabaseError(f"マイグレーション失敗 ({version}): {e}") from e

        if applied_versions:
            if verbose:
                print(f"  {len(applied_versions)}個のマイグレーションを適用しました")
        else:
            if verbose:
                print("  すべてのマイグレーションは適用済みです")

        return applied_versions

    finally:
        close_connection(conn)


def is_destructive_db_operation(sql_text: str) -> bool:
    """
    SQL文が破壊的なDB操作を含むかチェック

    Args:
        sql_text: チェックするSQL文字列（単一SQL文またはスクリプト）

    Returns:
        bool: 破壊的操作を含む場合True

    Note:
        破壊的操作と判定されるパターン:
        - DROP TABLE
        - DROP VIEW
        - DROP INDEX
        - ALTER TABLE ... DROP COLUMN
        - TRUNCATE TABLE
        - DELETE FROM (WHERE句なし)

    Example:
        >>> is_destructive_db_operation("DROP TABLE users")
        True
        >>> is_destructive_db_operation("CREATE TABLE users (id TEXT)")
        False
    """
    sql_upper = sql_text.upper()

    # 破壊的操作パターン
    destructive_patterns = [
        r'\bDROP\s+TABLE\b',
        r'\bDROP\s+VIEW\b',
        r'\bDROP\s+INDEX\b',
        r'\bALTER\s+TABLE\s+.*\s+DROP\s+COLUMN\b',
        r'\bTRUNCATE\s+TABLE\b',
        r'\bDELETE\s+FROM\s+\w+\s*;',  # WHERE句なしDELETE
        r'\bDELETE\s+FROM\s+\w+\s*$',  # WHERE句なしDELETE（末尾）
    ]

    for pattern in destructive_patterns:
        if re.search(pattern, sql_upper):
            return True

    return False


def get_destructive_db_tasks(
    conn: sqlite3.Connection,
    project_id: str,
    order_id: Optional[str] = None
) -> List[sqlite3.Row]:
    """
    破壊的DB変更タスクを取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID
        order_id: ORDER ID（指定した場合、そのORDERのタスクのみ取得）

    Returns:
        List[sqlite3.Row]: 破壊的DB変更タスクのリスト

    Example:
        destructive_tasks = get_destructive_db_tasks(conn, "ai_pm_manager", "ORDER_146")
        for task in destructive_tasks:
            print(f"{task['id']}: {task['title']}")
    """
    if order_id:
        query = """
            SELECT * FROM tasks
            WHERE project_id = ? AND order_id = ? AND is_destructive_db_change = 1
            ORDER BY id
        """
        return fetch_all(conn, query, (project_id, order_id))
    else:
        query = """
            SELECT * FROM tasks
            WHERE project_id = ? AND is_destructive_db_change = 1
            ORDER BY order_id, id
        """
        return fetch_all(conn, query, (project_id,))


def mark_task_as_destructive_db_change(
    conn: sqlite3.Connection,
    task_id: str,
    project_id: str,
    is_destructive: bool = True
) -> None:
    """
    タスクを破壊的DB変更タスクとしてマーク

    Args:
        conn: データベース接続
        task_id: タスクID
        project_id: プロジェクトID
        is_destructive: 破壊的DB変更フラグ（デフォルト: True）

    Example:
        mark_task_as_destructive_db_change(conn, "TASK_1196", "ai_pm_manager")
    """
    execute_query(
        conn,
        "UPDATE tasks SET is_destructive_db_change = ? WHERE id = ? AND project_id = ?",
        (1 if is_destructive else 0, task_id, project_id)
    )
    conn.commit()
