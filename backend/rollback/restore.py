"""
AI PM Framework - 時点指定復元（Restore）

指定時点の状態に復元するため、その時点以降の操作を逆順で取り消す。
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

import sys
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    transaction,
    fetch_one,
    fetch_all,
    execute_query,
    row_to_dict,
    DatabaseError,
)

try:
    from rollback.undo import Operation, UndoError, _reverse_operation
except ImportError:
    from undo import Operation, UndoError, _reverse_operation


class RestoreError(Exception):
    """復元操作エラー"""
    pass


def get_operations_after(
    conn: sqlite3.Connection,
    timestamp: str,
    project_id: Optional[str] = None,
    entity_type: Optional[str] = None,
) -> List[Operation]:
    """
    指定時点以降の操作を取得

    Args:
        conn: データベース接続
        timestamp: 復元先の時点（ISO形式）
        project_id: プロジェクトID（フィルタリング用、オプション）
        entity_type: エンティティ種別（フィルタリング用、オプション）

    Returns:
        List[Operation]: 指定時点以降の操作（新しい順）
    """
    conditions = ["changed_at > ?"]
    params = [timestamp]

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)

    if project_id:
        # 複合キー対応: tasksテーブルから直接project_idを参照
        conditions.append("""
            (entity_type = 'project' AND entity_id = ?)
            OR (entity_type = 'order' AND EXISTS (
                SELECT 1 FROM orders WHERE orders.id = entity_id AND orders.project_id = ?
            ))
            OR (entity_type = 'task' AND EXISTS (
                SELECT 1 FROM tasks t
                WHERE t.id = entity_id AND t.project_id = ?
            ))
            OR (entity_type = 'backlog' AND EXISTS (
                SELECT 1 FROM backlog_items WHERE backlog_items.id = entity_id AND backlog_items.project_id = ?
            ))
        """)
        params.extend([project_id, project_id, project_id, project_id])

    query = f"""
    SELECT * FROM change_history
    WHERE {' AND '.join(conditions)}
    ORDER BY changed_at DESC, id DESC
    """

    rows = fetch_all(conn, query, tuple(params))
    return [Operation.from_row(row) for row in rows]


def get_available_restore_points(
    conn: sqlite3.Connection,
    project_id: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    復元可能なポイント（時点）の一覧を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID（フィルタリング用、オプション）
        limit: 取得件数

    Returns:
        List[Dict]: 復元ポイント一覧
        各要素: {
            "timestamp": str,
            "operation_count": int,  # この時点以降の操作数
            "last_entity": str,
            "last_field": str,
        }
    """
    conditions = ["1=1"]
    params = []

    if project_id:
        # 複合キー対応: tasksテーブルから直接project_idを参照
        conditions.append("""
            (entity_type = 'project' AND entity_id = ?)
            OR (entity_type = 'order' AND EXISTS (
                SELECT 1 FROM orders WHERE orders.id = entity_id AND orders.project_id = ?
            ))
            OR (entity_type = 'task' AND EXISTS (
                SELECT 1 FROM tasks t
                WHERE t.id = entity_id AND t.project_id = ?
            ))
            OR (entity_type = 'backlog' AND EXISTS (
                SELECT 1 FROM backlog_items WHERE backlog_items.id = entity_id AND backlog_items.project_id = ?
            ))
        """)
        params.extend([project_id, project_id, project_id, project_id])

    params.append(limit)

    # 時点ごとの操作をグループ化（秒単位）
    query = f"""
    SELECT
        changed_at as timestamp,
        entity_type || ':' || entity_id as last_entity,
        field_name as last_field,
        (
            SELECT COUNT(*) FROM change_history ch2
            WHERE ch2.changed_at >= ch.changed_at
            {f"AND ({conditions[-1]})" if project_id else ""}
        ) as operation_count
    FROM change_history ch
    WHERE {' AND '.join(conditions[:-1] if len(conditions) > 1 else conditions)}
    ORDER BY changed_at DESC
    LIMIT ?
    """

    rows = fetch_all(conn, query, tuple(params))
    return [dict(row) for row in rows]


def restore_to_point(
    conn: Optional[sqlite3.Connection] = None,
    timestamp: str = None,
    project_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    render_after: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    指定時点の状態に復元

    Args:
        conn: データベース接続（Noneの場合は新規作成）
        timestamp: 復元先の時点（ISO形式）
        project_id: プロジェクトID（フィルタリング用、オプション）
        entity_type: エンティティ種別（フィルタリング用、オプション）
        render_after: 復元後にMDをレンダリングするか
        dry_run: 実際には復元せず、対象を表示のみ

    Returns:
        Dict: {
            "restored_to": str,      # 復元先の時点
            "undone_count": int,     # 取り消した操作数
            "operations": List[Dict],  # 取り消した操作の詳細
        }

    Raises:
        RestoreError: 復元不可能な場合
    """
    if not timestamp:
        raise RestoreError("復元先の時点（timestamp）を指定してください")

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        # 指定時点以降の操作を取得（新しい順）
        operations = get_operations_after(
            conn,
            timestamp,
            project_id,
            entity_type,
        )

        if not operations:
            return {
                "restored_to": timestamp,
                "undone_count": 0,
                "operations": [],
                "message": "指定時点以降の操作はありません",
            }

        if dry_run:
            return {
                "restored_to": timestamp,
                "undone_count": len(operations),
                "operations": [{
                    "id": op.id,
                    "entity_type": op.entity_type,
                    "entity_id": op.entity_id,
                    "field_name": op.field_name,
                    "old_value": op.old_value,
                    "new_value": op.new_value,
                    "changed_at": op.changed_at,
                } for op in operations],
                "dry_run": True,
            }

        # トランザクション内で逆順に取り消し
        results = []
        errors = []

        with transaction(conn) as txn:
            for op in operations:
                try:
                    result = _reverse_operation(txn, op)
                    results.append({
                        "operation_id": op.id,
                        "success": True,
                        **result,
                    })
                except UndoError as e:
                    errors.append({
                        "operation_id": op.id,
                        "error": str(e),
                    })
                    # エラーが発生しても続行（部分復元）

        # MDレンダリング（トランザクション外）
        if render_after and project_id:
            _render_project_md(project_id)

        return {
            "restored_to": timestamp,
            "undone_count": len(results),
            "operations": results,
            "errors": errors if errors else None,
        }

    finally:
        if close_conn:
            conn.close()


def restore_to_operation(
    conn: Optional[sqlite3.Connection] = None,
    operation_id: int = None,
    project_id: Optional[str] = None,
    render_after: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    指定操作IDの直前まで復元

    Args:
        conn: データベース接続（Noneの場合は新規作成）
        operation_id: 復元先の操作ID（この操作の直前の状態に復元）
        project_id: プロジェクトID（フィルタリング用、オプション）
        render_after: 復元後にMDをレンダリングするか
        dry_run: 実際には復元せず、対象を表示のみ

    Returns:
        Dict: restore_to_point と同じ形式
    """
    if not operation_id:
        raise RestoreError("操作ID（operation_id）を指定してください")

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        # 指定操作の時点を取得
        op_row = fetch_one(
            conn,
            "SELECT changed_at FROM change_history WHERE id = ?",
            (operation_id,)
        )

        if not op_row:
            raise RestoreError(f"操作ID {operation_id} が見つかりません")

        timestamp = op_row["changed_at"]

        return restore_to_point(
            conn,
            timestamp,
            project_id,
            render_after=render_after,
            dry_run=dry_run,
        )

    finally:
        if close_conn:
            conn.close()


def _render_project_md(project_id: str) -> None:
    """
    プロジェクトのMDファイルをレンダリング（廃止）

    BACKLOG.md廃止（ORDER_090）に伴い、処理は実行されなくなりました。
    関数シグネチャは後方互換性のため残存。

    Args:
        project_id: プロジェクトID
    """
    # BACKLOG.md廃止: ORDER_090
    pass


# === CLI インターフェース ===

def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="指定時点の状態に復元"
    )
    parser.add_argument(
        "project_id",
        nargs="?",
        help="プロジェクトID（オプション）"
    )
    parser.add_argument(
        "--timestamp",
        help="復元先の時点（ISO形式、例: 2026-01-27T10:00:00）"
    )
    parser.add_argument(
        "--operation-id",
        type=int,
        help="復元先の操作ID（この操作の直前の状態に復元）"
    )
    parser.add_argument(
        "--entity-type",
        choices=["project", "order", "task", "backlog", "review"],
        help="エンティティ種別でフィルタ"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="復元可能なポイントを一覧表示"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="一覧表示の件数（--list と併用）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際には復元せず、対象を表示のみ"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="MDレンダリングをスキップ"
    )

    args = parser.parse_args()

    try:
        conn = get_connection()

        if args.list:
            # 復元ポイント一覧
            points = get_available_restore_points(
                conn,
                project_id=args.project_id,
                limit=args.limit,
            )

            if args.json:
                print(json.dumps(points, ensure_ascii=False, indent=2))
            else:
                print(f"復元可能なポイント（{len(points)}件）:")
                print("-" * 80)
                for i, pt in enumerate(points, 1):
                    print(f"{i}. {pt['timestamp']}")
                    print(f"   この時点以降の操作数: {pt['operation_count']}")
                    print(f"   最後の操作: {pt['last_entity']}.{pt['last_field']}")
                    print()

        elif args.timestamp or args.operation_id:
            # 復元実行
            if args.operation_id:
                result = restore_to_operation(
                    conn,
                    operation_id=args.operation_id,
                    project_id=args.project_id,
                    render_after=not args.no_render,
                    dry_run=args.dry_run,
                )
            else:
                result = restore_to_point(
                    conn,
                    timestamp=args.timestamp,
                    project_id=args.project_id,
                    entity_type=args.entity_type,
                    render_after=not args.no_render,
                    dry_run=args.dry_run,
                )

            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                if result.get("dry_run"):
                    print("[DRY-RUN] 以下の操作を取り消します:")
                else:
                    print("[OK] 復元しました")

                print(f"  復元先時点: {result['restored_to']}")
                print(f"  取り消し操作数: {result['undone_count']}")

                if result.get("operations"):
                    print()
                    print("取り消した操作:")
                    for op in result["operations"][:10]:  # 最初の10件のみ表示
                        if isinstance(op, dict):
                            print(f"  - [{op.get('operation_id', op.get('id'))}] "
                                  f"{op.get('entity_type', '')}:{op.get('entity_id', '')}")

                if result.get("errors"):
                    print()
                    print("[WARNING] 一部の操作でエラーが発生:")
                    for err in result["errors"]:
                        print(f"  - [{err['operation_id']}] {err['error']}")

        else:
            print("[ERROR] --timestamp または --operation-id を指定してください")
            print("        --list で復元可能なポイントを確認できます")
            return 1

        conn.close()
        return 0

    except (RestoreError, UndoError) as e:
        print(f"[ERROR] {e}")
        return 1
    except DatabaseError as e:
        print(f"[DB ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
