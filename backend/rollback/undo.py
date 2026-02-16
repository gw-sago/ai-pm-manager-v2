"""
AI PM Framework - 直前操作取り消し（Undo）

直前の操作を change_history テーブルから取得し、逆操作を実行して取り消す。
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


class UndoError(Exception):
    """Undo操作エラー"""
    pass


@dataclass
class Operation:
    """操作履歴データ"""
    id: int
    entity_type: str
    entity_id: str
    field_name: str
    old_value: Optional[str]
    new_value: Optional[str]
    changed_by: str
    change_reason: Optional[str]
    changed_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Operation":
        """sqlite3.Rowからインスタンスを生成"""
        return cls(
            id=row["id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            field_name=row["field_name"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            changed_by=row["changed_by"],
            change_reason=row["change_reason"],
            changed_at=row["changed_at"],
        )


def get_last_operation(
    conn: sqlite3.Connection,
    project_id: Optional[str] = None,
    entity_type: Optional[str] = None,
) -> Optional[Operation]:
    """
    直前の操作を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID（フィルタリング用、オプション）
        entity_type: エンティティ種別（フィルタリング用、オプション）

    Returns:
        Operation: 直前の操作、なければNone
    """
    conditions = ["1=1"]
    params = []

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)

    if project_id:
        # プロジェクトに関連するエンティティをフィルタ（複合キー対応）
        # entity_id がプロジェクトIDを含む、または直接プロジェクトのエンティティ
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
    LIMIT 1
    """

    row = fetch_one(conn, query, tuple(params) if params else None)
    if row:
        return Operation.from_row(row)
    return None


def get_recent_operations(
    conn: sqlite3.Connection,
    limit: int = 10,
    project_id: Optional[str] = None,
    entity_type: Optional[str] = None,
) -> List[Operation]:
    """
    最近の操作一覧を取得

    Args:
        conn: データベース接続
        limit: 取得件数
        project_id: プロジェクトID（フィルタリング用、オプション）
        entity_type: エンティティ種別（フィルタリング用、オプション）

    Returns:
        List[Operation]: 操作一覧（新しい順）
    """
    conditions = ["1=1"]
    params = []

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

    params.append(limit)

    query = f"""
    SELECT * FROM change_history
    WHERE {' AND '.join(conditions)}
    ORDER BY changed_at DESC, id DESC
    LIMIT ?
    """

    rows = fetch_all(conn, query, tuple(params))
    return [Operation.from_row(row) for row in rows]


def _reverse_operation(conn: sqlite3.Connection, op: Operation) -> Dict[str, Any]:
    """
    操作を逆転（内部関数）

    Args:
        conn: データベース接続
        op: 逆転する操作

    Returns:
        Dict: 逆転結果

    Raises:
        UndoError: 逆転不可能な操作
    """
    # 逆転可能なエンティティとフィールド
    reversible = {
        "project": ["status"],
        "order": ["status", "priority"],
        "task": ["status", "assignee", "priority"],
        "backlog": ["status", "priority"],
        "review": ["status", "reviewer", "priority"],
    }

    if op.entity_type not in reversible:
        raise UndoError(f"逆転不可能なエンティティ種別: {op.entity_type}")

    if op.field_name not in reversible[op.entity_type]:
        raise UndoError(f"逆転不可能なフィールド: {op.entity_type}.{op.field_name}")

    # テーブル名マッピング
    table_map = {
        "project": "projects",
        "order": "orders",
        "task": "tasks",
        "backlog": "backlog_items",
        "review": "review_queue",
    }

    table = table_map[op.entity_type]

    # 現在の値を確認
    id_column = "task_id" if op.entity_type == "review" else "id"
    check_query = f"SELECT {op.field_name} FROM {table} WHERE {id_column} = ?"
    current_row = fetch_one(conn, check_query, (op.entity_id,))

    if not current_row:
        raise UndoError(f"エンティティが見つかりません: {op.entity_type}:{op.entity_id}")

    current_value = current_row[op.field_name]

    # 現在値が操作後の値と一致するか確認（整合性チェック）
    if str(current_value) != str(op.new_value) if op.new_value else current_value is not None:
        # 既に別の操作で変更されている可能性
        # 警告を出すが、続行を許可
        pass

    # 逆転（old_valueに戻す）
    update_query = f"UPDATE {table} SET {op.field_name} = ? WHERE {id_column} = ?"
    execute_query(conn, update_query, (op.old_value, op.entity_id))

    # 逆転操作を履歴に記録
    execute_query(
        conn,
        """
        INSERT INTO change_history (
            entity_type, entity_id, field_name,
            old_value, new_value, changed_by, change_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            op.entity_type,
            op.entity_id,
            op.field_name,
            op.new_value,  # 逆転なのでold/newが逆
            op.old_value,
            "System (Undo)",
            f"Undo operation #{op.id}",
        )
    )

    return {
        "entity_type": op.entity_type,
        "entity_id": op.entity_id,
        "field_name": op.field_name,
        "reverted_from": op.new_value,
        "reverted_to": op.old_value,
    }


def undo_last_operation(
    conn: Optional[sqlite3.Connection] = None,
    project_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    render_after: bool = True,
) -> Dict[str, Any]:
    """
    直前の操作を取り消す

    Args:
        conn: データベース接続（Noneの場合は新規作成）
        project_id: プロジェクトID（フィルタリング用、オプション）
        entity_type: エンティティ種別（フィルタリング用、オプション）
        render_after: 取り消し後にMDをレンダリングするか

    Returns:
        Dict: {
            "undone": Operation,
            "result": Dict (逆転結果)
        }

    Raises:
        UndoError: 取り消し不可能な場合
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        with transaction(conn) as txn:
            # 直前の操作を取得
            last_op = get_last_operation(txn, project_id, entity_type)
            if not last_op:
                raise UndoError("取り消し可能な操作がありません")

            # 逆転実行
            result = _reverse_operation(txn, last_op)

        # MDレンダリング（トランザクション外）
        if render_after and project_id:
            _render_project_md(project_id)

        return {
            "undone": last_op,
            "result": result,
        }

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
        description="直前の操作を取り消す"
    )
    parser.add_argument(
        "project_id",
        nargs="?",
        help="プロジェクトID（オプション）"
    )
    parser.add_argument(
        "--entity-type",
        choices=["project", "order", "task", "backlog", "review"],
        help="エンティティ種別でフィルタ"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="最近の操作を一覧表示"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="一覧表示の件数（--list と併用）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際には取り消さず、対象を表示のみ"
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
            # 最近の操作一覧
            ops = get_recent_operations(
                conn,
                limit=args.limit,
                project_id=args.project_id,
                entity_type=args.entity_type,
            )

            if args.json:
                print(json.dumps([{
                    "id": op.id,
                    "entity_type": op.entity_type,
                    "entity_id": op.entity_id,
                    "field_name": op.field_name,
                    "old_value": op.old_value,
                    "new_value": op.new_value,
                    "changed_by": op.changed_by,
                    "changed_at": op.changed_at,
                } for op in ops], ensure_ascii=False, indent=2))
            else:
                print(f"最近の操作（{len(ops)}件）:")
                print("-" * 80)
                for op in ops:
                    print(f"[{op.id}] {op.changed_at}")
                    print(f"    {op.entity_type}:{op.entity_id}.{op.field_name}")
                    print(f"    {op.old_value} → {op.new_value}")
                    print(f"    by {op.changed_by}")
                    print()

        else:
            # Undo実行
            last_op = get_last_operation(
                conn,
                project_id=args.project_id,
                entity_type=args.entity_type,
            )

            if not last_op:
                print("[ERROR] 取り消し可能な操作がありません")
                return 1

            if args.dry_run:
                print("[DRY-RUN] 以下の操作を取り消します:")
                print(f"  操作ID: {last_op.id}")
                print(f"  日時: {last_op.changed_at}")
                print(f"  対象: {last_op.entity_type}:{last_op.entity_id}")
                print(f"  フィールド: {last_op.field_name}")
                print(f"  変更: {last_op.old_value} → {last_op.new_value}")
                print(f"  実行者: {last_op.changed_by}")
                print()
                print("実際に取り消すには --dry-run を外して実行してください")
                return 0

            result = undo_last_operation(
                conn,
                project_id=args.project_id,
                entity_type=args.entity_type,
                render_after=not args.no_render,
            )

            if args.json:
                print(json.dumps({
                    "undone": {
                        "id": result["undone"].id,
                        "entity_type": result["undone"].entity_type,
                        "entity_id": result["undone"].entity_id,
                        "field_name": result["undone"].field_name,
                        "old_value": result["undone"].old_value,
                        "new_value": result["undone"].new_value,
                    },
                    "result": result["result"],
                }, ensure_ascii=False, indent=2))
            else:
                op = result["undone"]
                r = result["result"]
                print("[OK] 操作を取り消しました")
                print(f"  操作ID: {op.id}")
                print(f"  対象: {r['entity_type']}:{r['entity_id']}")
                print(f"  フィールド: {r['field_name']}")
                print(f"  {r['reverted_from']} → {r['reverted_to']}")

        conn.close()
        return 0

    except UndoError as e:
        print(f"[ERROR] {e}")
        return 1
    except DatabaseError as e:
        print(f"[DB ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
