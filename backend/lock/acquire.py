#!/usr/bin/env python3
"""
AI PM Framework - モジュールロック取得スクリプト

Usage:
    python backend/lock/acquire.py PROJECT_ID ORDER_ID MODULE1 [MODULE2 ...]

Options:
    --force    競合を無視して強制取得
    --json     JSON形式で出力

Example:
    python backend/lock/acquire.py AI_PM_PJ ORDER_094 backend .claude/commands
    python backend/lock/acquire.py AI_PM_PJ ORDER_094 backend --force
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection, transaction, execute_query, fetch_one, fetch_all,
    row_to_dict, rows_to_dicts, DatabaseError
)
from utils.validation import (
    validate_project_name, validate_order_id, order_exists, ValidationError
)


class LockConflictError(Exception):
    """ロック競合エラー"""
    def __init__(self, message: str, conflicts: List[Dict[str, Any]]):
        super().__init__(message)
        self.conflicts = conflicts


def check_conflicts(
    conn,
    project_id: str,
    modules: List[str],
    exclude_order_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    モジュールの競合をチェック

    Args:
        conn: データベース接続
        project_id: プロジェクトID
        modules: チェックするモジュール名リスト
        exclude_order_id: 除外するORDER ID（自分自身）

    Returns:
        競合情報のリスト
    """
    conflicts = []

    for module in modules:
        query = """
        SELECT ml.id, ml.project_id, ml.order_id, ml.module_name, ml.locked_at,
               o.title as order_title, o.status as order_status
        FROM module_locks ml
        LEFT JOIN orders o ON ml.order_id = o.id AND ml.project_id = o.project_id
        WHERE ml.project_id = ? AND ml.module_name = ?
        """
        params = [project_id, module]

        if exclude_order_id:
            query += " AND ml.order_id != ?"
            params.append(exclude_order_id)

        row = fetch_one(conn, query, tuple(params))
        if row:
            conflicts.append(row_to_dict(row))

    return conflicts


def acquire_lock(
    project_id: str,
    order_id: str,
    modules: List[str],
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """
    モジュールのロックを取得

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        modules: ロック対象のモジュール名リスト
        force: 競合を無視して強制取得

    Returns:
        取得結果（取得したロック情報、更新したORDER情報）

    Raises:
        ValidationError: 入力検証エラー
        LockConflictError: ロック競合エラー（forceがFalseの場合）
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_order_id(order_id)

    if not modules:
        raise ValidationError("モジュールを1つ以上指定してください", "modules", modules)

    # 事前チェック（トランザクション外）
    conn_check = get_connection()
    try:
        # ORDER存在確認
        if not order_exists(conn_check, order_id, project_id):
            raise ValidationError(
                f"ORDERが見つかりません: {order_id} (project: {project_id})",
                "order_id", order_id
            )

        # 競合チェック
        conflicts = check_conflicts(conn_check, project_id, modules, exclude_order_id=order_id)

        if conflicts and not force:
            conflict_details = [
                f"  - {c['module_name']}: {c['order_id']} ({c.get('order_title', 'N/A')})"
                for c in conflicts
            ]
            raise LockConflictError(
                f"ロック競合が発生しています:\n" + "\n".join(conflict_details),
                conflicts
            )
    finally:
        conn_check.close()

    with transaction() as conn:
        # 競合を再確認（トランザクション内で再チェック）
        conflicts = check_conflicts(conn, project_id, modules, exclude_order_id=order_id)

        # 強制モードの場合、既存ロックを解除
        if force and conflicts:
            for conflict in conflicts:
                execute_query(
                    conn,
                    "DELETE FROM module_locks WHERE id = ?",
                    (conflict['id'],)
                )

        # 既存の自分のロックを取得
        existing_locks = fetch_all(
            conn,
            "SELECT module_name FROM module_locks WHERE project_id = ? AND order_id = ?",
            (project_id, order_id)
        )
        existing_modules = {row['module_name'] for row in existing_locks}

        # 新しいロックを取得
        acquired = []
        for module in modules:
            if module in existing_modules:
                # 既に自分がロック済み
                acquired.append({
                    'module_name': module,
                    'status': 'already_locked',
                })
            else:
                execute_query(
                    conn,
                    """
                    INSERT INTO module_locks (project_id, order_id, module_name, locked_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (project_id, order_id, module, datetime.now().isoformat())
                )
                acquired.append({
                    'module_name': module,
                    'status': 'acquired',
                })

        # ordersテーブルのtarget_modulesを更新
        all_modules = existing_modules.union(set(modules))
        target_modules_str = ','.join(sorted(all_modules))
        execute_query(
            conn,
            "UPDATE orders SET target_modules = ?, updated_at = ? WHERE id = ? AND project_id = ?",
            (target_modules_str, datetime.now().isoformat(), order_id, project_id)
        )

        # 現在のロック一覧を取得
        current_locks = fetch_all(
            conn,
            "SELECT * FROM module_locks WHERE project_id = ? AND order_id = ?",
            (project_id, order_id)
        )

        return {
            'project_id': project_id,
            'order_id': order_id,
            'acquired': acquired,
            'forced': force and len(conflicts) > 0,
            'conflicts_overwritten': conflicts if force else [],
            'current_locks': rows_to_dicts(current_locks),
            'target_modules': target_modules_str,
        }


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="モジュールのロックを取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", help="ORDER ID")
    parser.add_argument("modules", nargs="+", help="ロック対象のモジュール名")
    parser.add_argument("--force", action="store_true", help="競合を無視して強制取得")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = acquire_lock(
            args.project_id,
            args.order_id,
            args.modules,
            force=args.force,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"ロックを取得しました: {args.order_id}")
            for lock in result['acquired']:
                status_text = "取得済み" if lock['status'] == 'already_locked' else "新規取得"
                print(f"  - {lock['module_name']}: {status_text}")
            if result['forced']:
                print(f"\n[警告] 以下のロックを強制上書きしました:")
                for c in result['conflicts_overwritten']:
                    print(f"  - {c['module_name']}: {c['order_id']}")
            print(f"\n対象モジュール: {result['target_modules']}")

    except LockConflictError as e:
        if args.json:
            print(json.dumps({
                'error': 'conflict',
                'message': str(e),
                'conflicts': e.conflicts
            }, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except (ValidationError, DatabaseError) as e:
        if args.json:
            print(json.dumps({'error': str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if args.json:
            print(json.dumps({'error': str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
