#!/usr/bin/env python3
"""
AI PM Framework - モジュールロック一覧スクリプト

Usage:
    python backend/lock/list.py PROJECT_ID

Options:
    --order ORDER_ID   特定ORDERのロックのみ表示
    --json             JSON形式で出力

Example:
    python backend/lock/list.py AI_PM_PJ
    python backend/lock/list.py AI_PM_PJ --order ORDER_094
    python backend/lock/list.py AI_PM_PJ --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection, fetch_all, rows_to_dicts, DatabaseError
)
from utils.validation import (
    validate_project_name, validate_order_id, ValidationError
)


def list_locks(
    project_id: str,
    *,
    order_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    モジュールロック一覧を取得

    Args:
        project_id: プロジェクトID
        order_id: 特定ORDERのみ表示（オプション）

    Returns:
        ロック一覧

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)

    if order_id:
        validate_order_id(order_id)

    conn = get_connection()
    try:
        # ロック一覧を取得
        query = """
        SELECT ml.id, ml.project_id, ml.order_id, ml.module_name, ml.locked_at,
               o.title as order_title, o.status as order_status
        FROM module_locks ml
        LEFT JOIN orders o ON ml.order_id = o.id AND ml.project_id = o.project_id
        WHERE ml.project_id = ?
        """
        params: List[Any] = [project_id]

        if order_id:
            query += " AND ml.order_id = ?"
            params.append(order_id)

        query += " ORDER BY ml.order_id, ml.module_name"

        rows = fetch_all(conn, query, tuple(params))
        locks = rows_to_dicts(rows)

        # ORDER別に集計
        locks_by_order: Dict[str, List[Dict[str, Any]]] = {}
        for lock in locks:
            oid = lock['order_id']
            if oid not in locks_by_order:
                locks_by_order[oid] = []
            locks_by_order[oid].append(lock)

        # 統計
        unique_orders = set(lock['order_id'] for lock in locks)
        unique_modules = set(lock['module_name'] for lock in locks)

        return {
            'project_id': project_id,
            'filter_order_id': order_id,
            'total_locks': len(locks),
            'unique_orders': len(unique_orders),
            'unique_modules': len(unique_modules),
            'locks': locks,
            'locks_by_order': locks_by_order,
        }

    finally:
        conn.close()


def format_table(result: Dict[str, Any]) -> str:
    """
    ロック一覧をテーブル形式でフォーマット
    """
    locks = result['locks']

    if not locks:
        return "ロックがありません。"

    lines = [
        f"プロジェクト: {result['project_id']}",
        f"総ロック数: {result['total_locks']} ({result['unique_orders']} ORDER, {result['unique_modules']} モジュール)",
        "",
        "| ORDER ID   | モジュール名                   | ロック日時          | ORDER状態   |",
        "|------------|-------------------------------|---------------------|-------------|"
    ]

    for lock in locks:
        order_id = lock['order_id'][:10]
        module = lock['module_name'][:29]
        locked_at = lock['locked_at'][:19] if lock['locked_at'] else '-'
        status = lock.get('order_status', '-')[:11]

        lines.append(
            f"| {order_id:<10} | {module:<29} | {locked_at:<19} | {status:<11} |"
        )

    return "\n".join(lines)


def format_by_order(result: Dict[str, Any]) -> str:
    """
    ORDER別にグループ化してフォーマット
    """
    locks_by_order = result['locks_by_order']

    if not locks_by_order:
        return "ロックがありません。"

    lines = [
        f"プロジェクト: {result['project_id']}",
        f"総ロック数: {result['total_locks']}",
        "",
    ]

    for order_id, locks in locks_by_order.items():
        order_title = locks[0].get('order_title', 'N/A') if locks else 'N/A'
        order_status = locks[0].get('order_status', 'N/A') if locks else 'N/A'

        lines.append(f"{order_id}: {order_title} ({order_status})")
        for lock in locks:
            lines.append(f"  - {lock['module_name']}")
        lines.append("")

    return "\n".join(lines)


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="モジュールロック一覧を表示",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--order", dest="order_id", help="特定ORDERのロックのみ表示")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--table", action="store_true", help="テーブル形式で出力")

    args = parser.parse_args()

    try:
        result = list_locks(
            args.project_id,
            order_id=args.order_id,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        elif args.table:
            print(format_table(result))
        else:
            # デフォルト: ORDER別グループ化表示
            print(format_by_order(result))

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
