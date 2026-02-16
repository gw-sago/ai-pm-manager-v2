#!/usr/bin/env python3
"""
AI PM Framework - Migration Base Utility
Version: 1.0.0

マイグレーションスクリプト用の共通基盤を提供。
PRAGMA foreign_keys制御、自動バックアップ、Worker実行中の防止機構を含む。

Usage:
    from utils.migration_base import MigrationRunner, MigrationError

    def migrate():
        runner = MigrationRunner("add_new_feature")

        def migration_logic(conn):
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE ...")
            return True

        return runner.run(migration_logic)

Safety Features:
    - 自動バックアップ作成（タイムスタンプ付き）
    - PRAGMA foreign_keys 制御（マイグレーション中は無効化、終了時に復元）
    - Worker実行中の検出と警告
    - トランザクション管理（自動commit/rollback）
    - ドライランモード対応
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Any, Dict, List

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_all


class MigrationError(Exception):
    """マイグレーション実行エラー"""
    pass


class MigrationRunner:
    """
    マイグレーションスクリプトの実行基盤

    Features:
        - 自動バックアップ
        - PRAGMA foreign_keys制御
        - Worker実行中の検出
        - トランザクション管理
    """

    def __init__(
        self,
        migration_name: str,
        *,
        db_path: Optional[Path] = None,
        backup: bool = True,
        check_workers: bool = True,
        dry_run: bool = False,
        verbose: bool = False,
    ):
        """
        Args:
            migration_name: マイグレーション名（バックアップファイル名に使用）
            db_path: データベースファイルパス（Noneの場合はデフォルト）
            backup: バックアップを作成するか（デフォルト: True）
            check_workers: Worker実行中をチェックするか（デフォルト: True）
            dry_run: ドライランモード（デフォルト: False）
            verbose: 詳細ログを出力するか（デフォルト: False）
        """
        self.migration_name = migration_name
        self.backup_enabled = backup
        self.check_workers = check_workers
        self.dry_run = dry_run
        self.verbose = verbose

        # データベースパスを解決
        if db_path is None:
            try:
                from config import get_db_path
                self.db_path = Path(get_db_path())
            except ImportError:
                raise MigrationError("データベースパスが指定されていません")
        else:
            self.db_path = Path(db_path)

        if not self.db_path.exists():
            raise MigrationError(f"データベースファイルが見つかりません: {self.db_path}")

        self.backup_path: Optional[Path] = None
        self.conn: Optional[sqlite3.Connection] = None
        self.original_fk_state: Optional[int] = None

    def _log(self, message: str, level: str = "INFO") -> None:
        """ログメッセージを出力"""
        if self.verbose or level != "DEBUG":
            print(f"[{level}] {message}")

    def _check_running_workers(self) -> List[Dict[str, Any]]:
        """
        Worker実行中のタスクを検出

        Returns:
            実行中タスクのリスト
        """
        if not self.check_workers:
            self._log("Worker実行チェックをスキップ", "DEBUG")
            return []

        try:
            conn = get_connection(self.db_path)
            try:
                # IN_PROGRESS状態のタスクを検索
                running_tasks = fetch_all(
                    conn,
                    """
                    SELECT t.id, t.project_id, t.title, t.status, t.assignee, t.updated_at
                    FROM tasks t
                    WHERE t.status = 'IN_PROGRESS'
                    ORDER BY t.updated_at DESC
                    """
                )

                if running_tasks:
                    self._log(f"実行中のWorkerタスクを検出: {len(running_tasks)}件", "WARNING")
                    for task in running_tasks:
                        self._log(
                            f"  - {task['id']} ({task['project_id']}): {task['title']} "
                            f"[assignee={task['assignee']}, updated={task['updated_at']}]",
                            "WARNING"
                        )

                return [dict(task) for task in running_tasks]

            finally:
                conn.close()

        except Exception as e:
            self._log(f"Worker実行チェック失敗: {e}", "WARNING")
            return []

    def _create_backup(self) -> Optional[Path]:
        """
        データベースのバックアップを作成

        Returns:
            バックアップファイルパス、または None（バックアップ無効時）
        """
        if not self.backup_enabled or self.dry_run:
            self._log("バックアップをスキップ", "DEBUG")
            return None

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self.db_path.parent / f"{self.db_path.name}.backup_{self.migration_name}_{timestamp}"

        try:
            shutil.copy2(self.db_path, backup_path)
            self._log(f"バックアップ作成: {backup_path}", "INFO")
            return backup_path
        except Exception as e:
            raise MigrationError(f"バックアップ作成に失敗: {e}")

    def _disable_foreign_keys(self) -> None:
        """
        外部キー制約を無効化（現在の状態を保存）
        """
        cursor = self.conn.cursor()

        # 現在の状態を取得
        cursor.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()
        self.original_fk_state = result[0] if result else 1

        if self.dry_run:
            self._log(f"PRAGMA foreign_keys = OFF (ドライラン, 元の状態: {self.original_fk_state})", "DEBUG")
            # ドライランでも無効化を実行（読み取り操作のため問題なし）
            cursor.execute("PRAGMA foreign_keys = OFF")
        else:
            # 外部キー制約を無効化
            cursor.execute("PRAGMA foreign_keys = OFF")
            self._log(f"PRAGMA foreign_keys = OFF (元の状態: {self.original_fk_state})", "DEBUG")

    def _restore_foreign_keys(self) -> None:
        """
        外部キー制約を復元
        """
        if self.original_fk_state is None:
            return

        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA foreign_keys = {self.original_fk_state}")
        self._log(f"PRAGMA foreign_keys = {self.original_fk_state} (復元)", "DEBUG")

    def run(
        self,
        migration_func: Callable[[sqlite3.Connection], bool],
        *,
        force: bool = False,
    ) -> bool:
        """
        マイグレーションを実行

        Args:
            migration_func: マイグレーションロジックを実装した関数
                          引数: sqlite3.Connection
                          戻り値: bool (成功時True)
            force: Worker実行中でも強制実行するか（デフォルト: False）

        Returns:
            成功時True、失敗時False

        Raises:
            MigrationError: マイグレーション実行エラー

        Example:
            def my_migration(conn):
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE ...")
                return True

            runner = MigrationRunner("add_table")
            runner.run(my_migration)
        """
        try:
            # Step 1: Worker実行チェック
            running_tasks = self._check_running_workers()
            if running_tasks and not force:
                self._log(
                    "⚠️  Worker実行中のタスクが存在します。"
                    "マイグレーション実行はスキーマ変更によりタスク失敗の原因となる可能性があります。",
                    "WARNING"
                )
                self._log("実行を継続する場合は --force オプションを指定してください。", "WARNING")

                if not self.dry_run:
                    response = input("\nマイグレーションを実行しますか？ [y/N]: ")
                    if response.lower() != 'y':
                        self._log("マイグレーションをキャンセルしました", "INFO")
                        return False

            # Step 2: バックアップ作成
            self.backup_path = self._create_backup()

            # Step 3: データベース接続
            if self.dry_run:
                self._log("ドライランモード - データベース変更はコミットされません", "INFO")
                # ドライラン用の読み取り専用接続
                self.conn = get_connection(self.db_path)
            else:
                self.conn = get_connection(self.db_path)

            # Step 4: PRAGMA foreign_keys 無効化
            self._disable_foreign_keys()

            # Step 5: トランザクション開始
            self.conn.execute("BEGIN TRANSACTION")
            if self.dry_run:
                self._log("トランザクション開始（ドライラン）", "DEBUG")
            else:
                self._log("トランザクション開始", "DEBUG")

            # Step 6: マイグレーション実行
            self._log(f"マイグレーション実行: {self.migration_name}", "INFO")
            success = migration_func(self.conn)

            if not success:
                raise MigrationError("マイグレーション関数がFalseを返しました")

            # Step 7: コミット or ロールバック
            if self.dry_run:
                self._log("ドライラン - 変更をロールバック", "INFO")
                self.conn.rollback()
            else:
                self.conn.commit()
                self._log("マイグレーション成功 - 変更をコミット", "INFO")

            # Step 8: PRAGMA foreign_keys 復元
            self._restore_foreign_keys()

            return True

        except Exception as e:
            self._log(f"マイグレーション失敗: {e}", "ERROR")

            # ロールバック
            if self.conn:
                try:
                    self.conn.rollback()
                    self._log("変更をロールバックしました", "INFO")
                except Exception as rb_error:
                    self._log(f"ロールバック失敗: {rb_error}", "ERROR")

            # バックアップから復元の案内
            if self.backup_path and not self.dry_run:
                self._log(
                    f"バックアップから復元する場合:\n"
                    f"  cp {self.backup_path} {self.db_path}",
                    "INFO"
                )

            raise MigrationError(f"マイグレーション失敗: {e}")

        finally:
            # クリーンアップ
            if self.conn:
                try:
                    self._restore_foreign_keys()
                except Exception:
                    pass
                self.conn.close()


def create_migration_parser():
    """
    マイグレーションスクリプト用の共通ArgumentParserを作成

    Returns:
        argparse.ArgumentParser

    Example:
        parser = create_migration_parser()
        parser.description = "Add new feature to database"
        args = parser.parse_args()

        runner = MigrationRunner("add_feature", **vars(args))
        runner.run(my_migration_func)
    """
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--db",
        type=Path,
        help="データベースファイルパス（デフォルト: data/aipm.db）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ドライランモード - 変更をコミットせず、実行内容のみ確認"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="バックアップを作成しない（非推奨）"
    )
    parser.add_argument(
        "--no-worker-check",
        action="store_true",
        help="Worker実行中のチェックをスキップ"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Worker実行中でも強制実行"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細ログを出力"
    )

    return parser


def check_worker_safety(verbose: bool = False) -> Dict[str, Any]:
    """
    Worker実行中のタスクをチェックし、マイグレーション実行の安全性を評価

    マイグレーションスクリプトを実行する前に呼び出すことで、
    他のWorkerが実行中でないかを確認できる。

    Args:
        verbose: 詳細ログを出力するか

    Returns:
        {
            "safe": bool,  # 安全かどうか
            "running_tasks": list,  # 実行中タスクのリスト
            "warning": str,  # 警告メッセージ（ある場合）
        }

    Example:
        from utils.migration_base import check_worker_safety

        safety = check_worker_safety(verbose=True)
        if not safety["safe"]:
            print(f"警告: {safety['warning']}")
            print(f"実行中タスク: {len(safety['running_tasks'])}件")
            # MigrationRunnerを使用すれば、自動的に処理される
    """
    result = {
        "safe": True,
        "running_tasks": [],
        "warning": None,
    }

    try:
        conn = get_connection()
        try:
            # IN_PROGRESS状態のタスクを検索
            running_tasks = fetch_all(
                conn,
                """
                SELECT t.id, t.project_id, t.title, t.status, t.assignee, t.updated_at
                FROM tasks t
                WHERE t.status = 'IN_PROGRESS'
                ORDER BY t.updated_at DESC
                """
            )

            if running_tasks:
                result["safe"] = False
                result["running_tasks"] = [dict(task) for task in running_tasks]
                result["warning"] = (
                    f"{len(running_tasks)}件の実行中タスクが検出されました。"
                    "マイグレーション実行はスキーマ変更により他のタスクが失敗する原因となる可能性があります。"
                )

                if verbose:
                    print(f"[WARNING] {result['warning']}")
                    for task in running_tasks:
                        print(
                            f"  - {task['id']} ({task['project_id']}): {task['title']} "
                            f"[assignee={task['assignee']}, updated={task['updated_at']}]"
                        )

        finally:
            conn.close()

    except Exception as e:
        result["warning"] = f"Worker実行チェックに失敗: {e}"
        if verbose:
            print(f"[WARNING] {result['warning']}")

    return result


if __name__ == "__main__":
    # テスト実行
    print("Migration Base Utility - Test")

    # 使用例を表示
    print("""
Usage Example:

    from utils.migration_base import MigrationRunner, MigrationError

    def my_migration(conn):
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY)")
        return True

    runner = MigrationRunner("test_migration", dry_run=True, verbose=True)
    success = runner.run(my_migration)
    print(f"Migration {'succeeded' if success else 'failed'}")
""")
