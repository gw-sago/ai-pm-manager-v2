#!/usr/bin/env python3
"""
マイグレーション: ordersテーブルのbacklog_idをbacklog_items.related_order_idから逆引き補完

背景:
    backlog_itemsとordersは既にほぼ1対1で紐付いている（related_order_id経由）。
    ただしorders側のbacklog_idは大部分が未設定のため、逆引きで補完する。
    データ移行（新ORDER作成）は不要 - 既存の紐付け関係を整備するのみ。

処理内容:
    1. backlog_items.related_order_idが設定されているレコードを取得
    2. 対応するordersレコードのbacklog_idを設定（未設定の場合のみ）

Usage:
    python backend/migrations/sync_backlog_order_ids.py [--dry-run] [--verbose]
"""

import sys
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.migration_base import MigrationRunner, MigrationError


def migrate():
    """マイグレーション実行"""
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv

    runner = MigrationRunner(
        "sync_backlog_order_ids",
        backup=True,
        check_workers=True,
        dry_run=dry_run,
        verbose=verbose,
    )

    def migration_logic(conn):
        cursor = conn.cursor()

        # backlog_items.related_order_id → orders.backlog_id の逆引き補完
        cursor.execute("""
            SELECT b.id AS backlog_id, b.related_order_id, b.project_id
            FROM backlog_items b
            WHERE b.related_order_id IS NOT NULL
        """)
        rows = cursor.fetchall()

        updated = 0
        skipped = 0
        not_found = 0

        for row in rows:
            backlog_id = row[0]
            order_id = row[1]
            project_id = row[2]

            # orders側のbacklog_idが未設定の場合のみ更新
            cursor.execute(
                "SELECT backlog_id FROM orders WHERE id = ? AND project_id = ?",
                (order_id, project_id)
            )
            order_row = cursor.fetchone()

            if order_row is None:
                not_found += 1
                if verbose:
                    print(f"  [SKIP] ORDER {order_id} not found for {backlog_id}")
                continue

            if order_row[0] is not None:
                skipped += 1
                if verbose:
                    print(f"  [SKIP] {order_id} already has backlog_id={order_row[0]}")
                continue

            cursor.execute(
                "UPDATE orders SET backlog_id = ? WHERE id = ? AND project_id = ?",
                (backlog_id, order_id, project_id)
            )
            updated += 1
            if verbose:
                print(f"  [UPDATE] {order_id} <- backlog_id={backlog_id}")

        print(f"  結果: 更新={updated}, スキップ(設定済み)={skipped}, ORDER不在={not_found}")
        return True

    return runner.run(migration_logic)


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
