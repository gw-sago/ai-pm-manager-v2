#!/usr/bin/env python3
"""
AI PM Framework - モジュールロック解放スクリプト

Usage:
    python backend/lock/release.py PROJECT_ID ORDER_ID

Options:
    --all      指定プロジェクトの全ロック解放
    --json     JSON形式で出力

Example:
    python backend/lock/release.py AI_PM_PJ ORDER_094
    python backend/lock/release.py AI_PM_PJ --all
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
    get_connection, transaction, execute_query, fetch_all,
    rows_to_dicts, DatabaseError
)
from utils.validation import (
    validate_project_name, validate_order_id, ValidationError
)


def release_lock(
    project_id: str,
    order_id: Optional[str] = None,
    *,
    release_all: bool = False,
) -> Dict[str, Any]:
    """
    モジュールのロックを解放

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID（release_allがFalseの場合は必須）
        release_all: プロジェクト内の全ロックを解放

    Returns:
        解放結果

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)

    if not release_all and not order_id:
        raise ValidationError(
            "ORDER IDを指定するか、--allオプションを使用してください",
            "order_id", order_id
        )

    if order_id:
        validate_order_id(order_id)

    with transaction() as conn:
        # 解放対象のロックを取得
        if release_all:
            locks_to_release = fetch_all(
                conn,
                """
                SELECT ml.*, o.title as order_title
                FROM module_locks ml
                LEFT JOIN orders o ON ml.order_id = o.id AND ml.project_id = o.project_id
                WHERE ml.project_id = ?
                """,
                (project_id,)
            )
        else:
            locks_to_release = fetch_all(
                conn,
                """
                SELECT ml.*, o.title as order_title
                FROM module_locks ml
                LEFT JOIN orders o ON ml.order_id = o.id AND ml.project_id = o.project_id
                WHERE ml.project_id = ? AND ml.order_id = ?
                """,
                (project_id, order_id)
            )

        released_locks = rows_to_dicts(locks_to_release)

        # ロックを削除
        if release_all:
            execute_query(
                conn,
                "DELETE FROM module_locks WHERE project_id = ?",
                (project_id,)
            )
            # 全ORDERのtarget_modulesをクリア
            execute_query(
                conn,
                "UPDATE orders SET target_modules = NULL, updated_at = ? WHERE project_id = ?",
                (datetime.now().isoformat(), project_id)
            )
        else:
            execute_query(
                conn,
                "DELETE FROM module_locks WHERE project_id = ? AND order_id = ?",
                (project_id, order_id)
            )
            # 対象ORDERのtarget_modulesをクリア
            execute_query(
                conn,
                "UPDATE orders SET target_modules = NULL, updated_at = ? WHERE id = ? AND project_id = ?",
                (datetime.now().isoformat(), order_id, project_id)
            )

        # 残りのロック数を取得
        remaining = fetch_all(
            conn,
            "SELECT COUNT(*) as count FROM module_locks WHERE project_id = ?",
            (project_id,)
        )
        remaining_count = remaining[0]['count'] if remaining else 0

        return {
            'project_id': project_id,
            'order_id': order_id if not release_all else None,
            'release_all': release_all,
            'released_count': len(released_locks),
            'released_locks': released_locks,
            'remaining_count': remaining_count,
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
        description="モジュールのロックを解放",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", nargs="?", help="ORDER ID（--allを指定しない場合は必須）")
    parser.add_argument("--all", action="store_true", dest="release_all", help="プロジェクト内の全ロック解放")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # 引数検証
    if not args.release_all and not args.order_id:
        parser.error("ORDER IDを指定するか、--allオプションを使用してください")

    try:
        result = release_lock(
            args.project_id,
            args.order_id,
            release_all=args.release_all,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            if result['release_all']:
                print(f"プロジェクト {args.project_id} の全ロックを解放しました")
            else:
                print(f"{args.order_id} のロックを解放しました")

            print(f"  解放数: {result['released_count']}")
            if result['released_locks']:
                for lock in result['released_locks']:
                    print(f"    - {lock['module_name']} ({lock['order_id']})")
            print(f"  残りロック数: {result['remaining_count']}")

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
