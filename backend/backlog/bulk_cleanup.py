#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG一括整理スクリプト

COMPLETED済みORDERに紐づくIN_PROGRESSバックログをDONEに更新し、
孤立したIN_PROGRESSバックログを検出するバックエンドスクリプト。

Usage:
    # 全プロジェクトを一括整理（プレビューのみ）
    python backend/backlog/bulk_cleanup.py --dry-run

    # 全プロジェクトを一括整理（実行）
    python backend/backlog/bulk_cleanup.py

    # 特定プロジェクトのみ整理
    python backend/backlog/bulk_cleanup.py --project AI_PM_PJ

    # JSON形式で出力
    python backend/backlog/bulk_cleanup.py --json

Architecture:
    - COMPLETED済みORDERに紐づくIN_PROGRESSバックログを自動DONE化
    - 孤立したIN_PROGRESSバックログ（ORDERなし）を検出してレポート
    - UI画面の「バックログ整理」ボタンから呼び出し可能

Example:
    from backlog.bulk_cleanup import cleanup_all_backlogs

    result = cleanup_all_backlogs(dry_run=False)
    print(f"更新: {result['updated_count']} 件")
    print(f"孤立: {result['orphaned_count']} 件")
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    transaction,
    execute_query,
    fetch_one,
    fetch_all,
    row_to_dict,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    project_exists,
    ValidationError,
)
from utils.transition import (
    record_transition,
    TransitionError,
)


def cleanup_all_backlogs(
    project_id: Optional[str] = None,
    dry_run: bool = False,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    BACKLOG一括整理を実行

    1. COMPLETED済みORDERに紐づくIN_PROGRESSバックログをDONEに更新
    2. 孤立したIN_PROGRESSバックログ（ORDERなし、または非COMPLETEDのORDER）を検出

    Args:
        project_id: プロジェクトID（省略時は全プロジェクト）
        dry_run: プレビューモード（True: 実行しない、False: 実行）
        db_path: データベースパス（テスト用）

    Returns:
        dict: 整理結果
            - success: bool
            - updated_count: int (DONE更新した件数)
            - orphaned_count: int (孤立バックログ件数)
            - updated_backlogs: list[dict] (更新されたバックログ情報)
            - orphaned_backlogs: list[dict] (孤立バックログ情報)
            - message: str
            - error: str (エラー時のみ)
    """
    try:
        # 入力検証
        if project_id:
            validate_project_name(project_id)

        updated_backlogs = []
        orphaned_backlogs = []

        with transaction(db_path=db_path) as conn:
            # プロジェクト条件
            project_filter = ""
            params = []
            if project_id:
                if not project_exists(conn, project_id):
                    return {
                        "success": False,
                        "error": f"プロジェクトが見つかりません: {project_id}",
                    }
                project_filter = "AND b.project_id = ?"
                params.append(project_id)

            # 1. COMPLETED済みORDERに紐づくIN_PROGRESSバックログを検索
            query = f"""
                SELECT
                    b.id,
                    b.project_id,
                    b.title,
                    b.status,
                    b.related_order_id,
                    o.status as order_status
                FROM backlog_items b
                LEFT JOIN orders o ON b.related_order_id = o.id AND b.project_id = o.project_id
                WHERE b.status = 'IN_PROGRESS'
                  AND b.related_order_id IS NOT NULL
                  AND o.status = 'COMPLETED'
                  {project_filter}
                ORDER BY b.project_id, b.id
            """

            completed_order_backlogs = fetch_all(conn, query, tuple(params))

            # DONE更新（dry_runでない場合）
            if not dry_run and completed_order_backlogs:
                now = datetime.now().isoformat()
                for row in completed_order_backlogs:
                    backlog_dict = dict(row)
                    backlog_id = backlog_dict["id"]
                    proj_id = backlog_dict["project_id"]
                    order_id = backlog_dict["related_order_id"]

                    # BACKLOGステータス更新
                    execute_query(
                        conn,
                        """
                        UPDATE backlog_items
                        SET status = ?, completed_at = ?, updated_at = ?
                        WHERE id = ? AND project_id = ?
                        """,
                        ("DONE", now, now, backlog_id, proj_id)
                    )

                    # 状態遷移履歴を記録
                    record_transition(
                        conn,
                        "backlog",
                        backlog_id,
                        "IN_PROGRESS",
                        "DONE",
                        "System",
                        f"一括整理: ORDER {order_id} 完了に伴う自動更新"
                    )

                    # 変更履歴を記録
                    execute_query(
                        conn,
                        """
                        INSERT INTO change_history (
                            entity_type, entity_id, field_name,
                            old_value, new_value, changed_by, change_reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        ("backlog", backlog_id, "status", "IN_PROGRESS", "DONE", "System", f"一括整理: ORDER {order_id} 完了に伴う自動更新")
                    )

                    updated_backlogs.append({
                        "id": backlog_id,
                        "project_id": proj_id,
                        "title": backlog_dict["title"],
                        "order_id": order_id,
                    })

            # dry_runの場合も情報を収集
            elif dry_run and completed_order_backlogs:
                for row in completed_order_backlogs:
                    backlog_dict = dict(row)
                    updated_backlogs.append({
                        "id": backlog_dict["id"],
                        "project_id": backlog_dict["project_id"],
                        "title": backlog_dict["title"],
                        "order_id": backlog_dict["related_order_id"],
                    })

            # 2. 孤立したIN_PROGRESSバックログを検索
            # - related_order_idがNULL
            # - または関連ORDERが非COMPLETED
            orphaned_query = f"""
                SELECT
                    b.id,
                    b.project_id,
                    b.title,
                    b.status,
                    b.related_order_id,
                    o.status as order_status
                FROM backlog_items b
                LEFT JOIN orders o ON b.related_order_id = o.id AND b.project_id = o.project_id
                WHERE b.status = 'IN_PROGRESS'
                  AND (
                      b.related_order_id IS NULL
                      OR o.status IS NULL
                      OR o.status != 'COMPLETED'
                  )
                  {project_filter}
                ORDER BY b.project_id, b.id
            """

            orphaned = fetch_all(conn, orphaned_query, tuple(params))

            for row in orphaned:
                orphaned_dict = dict(row)
                orphaned_backlogs.append({
                    "id": orphaned_dict["id"],
                    "project_id": orphaned_dict["project_id"],
                    "title": orphaned_dict["title"],
                    "order_id": orphaned_dict.get("related_order_id"),
                    "order_status": orphaned_dict.get("order_status"),
                    "reason": _get_orphaned_reason(orphaned_dict),
                })

        # 結果サマリ
        mode = "プレビュー" if dry_run else "実行"
        message = f"BACKLOG一括整理 {mode} 完了:\n"
        message += f"  - DONE更新: {len(updated_backlogs)} 件\n"
        message += f"  - 孤立検出: {len(orphaned_backlogs)} 件"

        return {
            "success": True,
            "updated_count": len(updated_backlogs),
            "orphaned_count": len(orphaned_backlogs),
            "updated_backlogs": updated_backlogs,
            "orphaned_backlogs": orphaned_backlogs,
            "message": message,
            "dry_run": dry_run,
        }

    except ValidationError as e:
        return {
            "success": False,
            "error": f"入力検証エラー: {e}",
        }
    except DatabaseError as e:
        return {
            "success": False,
            "error": f"データベースエラー: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"予期しないエラー: {e}",
        }


def _get_orphaned_reason(backlog_dict: Dict[str, Any]) -> str:
    """孤立理由を取得"""
    order_id = backlog_dict.get("related_order_id")
    order_status = backlog_dict.get("order_status")

    if not order_id:
        return "ORDERが未割り当て"
    elif order_status is None:
        return f"ORDER {order_id} が存在しない"
    else:
        return f"ORDER {order_id} が非COMPLETED ({order_status})"


def main():
    """コマンドライン実行"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="BACKLOG一括整理スクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 全プロジェクトをプレビュー
  python bulk_cleanup.py --dry-run

  # 全プロジェクトを実行
  python bulk_cleanup.py

  # 特定プロジェクトのみ実行
  python bulk_cleanup.py --project AI_PM_PJ

  # JSON形式で出力
  python bulk_cleanup.py --json

処理内容:
  1. COMPLETED済みORDERに紐づくIN_PROGRESSバックログをDONEに更新
  2. 孤立したIN_PROGRESSバックログを検出してレポート
"""
    )

    parser.add_argument(
        "--project", "-p",
        help="プロジェクトID（省略時は全プロジェクト）"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="プレビューモード（実際には更新しない）"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    result = cleanup_all_backlogs(
        project_id=args.project,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            print(result["message"])
            print()

            if result["updated_backlogs"]:
                print("【DONE更新されたバックログ】")
                for item in result["updated_backlogs"]:
                    print(f"  - {item['project_id']}/{item['id']}: {item['title']} (ORDER: {item['order_id']})")
                print()

            if result["orphaned_backlogs"]:
                print("【孤立バックログ（要確認）】")
                for item in result["orphaned_backlogs"]:
                    order_info = f"ORDER: {item['order_id']}" if item['order_id'] else "ORDERなし"
                    print(f"  - {item['project_id']}/{item['id']}: {item['title']} ({order_info}) - {item['reason']}")
                print()

            if args.dry_run:
                print("※ プレビューモードで実行しました。実際の更新は行われていません。")
                print("  実行する場合は --dry-run オプションを外してください。")
        else:
            print(f"[ERROR] {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
