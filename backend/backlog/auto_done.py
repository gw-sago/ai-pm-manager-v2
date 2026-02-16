#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG自動DONE更新モジュール

ORDER完了時に、紐付いているBACKLOGを自動的にDONEステータスに更新する。
order/update.py の complete_order() から呼び出される。

Usage:
    from backlog.auto_done import auto_update_backlog_on_order_complete

    # ORDER完了時に自動呼び出し
    auto_update_backlog_on_order_complete(project_id, order_id, reason)

Architecture:
    - order/update.py の _complete_related_backlog() から統合済み
    - このモジュールは将来的な拡張や独立実行用に残す

Example:
    # 手動実行（デバッグ用）
    python backend/backlog/auto_done.py AI_PM_PJ ORDER_036
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

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
    validate_order_id,
    project_exists,
    order_exists,
    ValidationError,
)
from utils.transition import (
    record_transition,
    TransitionError,
)


def auto_update_backlog_on_order_complete(
    project_id: str,
    order_id: str,
    reason: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    ORDER完了時に紐付いているBACKLOGをDONEに自動更新

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        reason: 変更理由（省略時は自動生成）
        db_path: データベースパス（テスト用）

    Returns:
        dict: 更新結果
            - success: bool
            - backlog_id: str (更新されたBACKLOG ID、なければNone)
            - old_status: str (更新前ステータス、なければNone)
            - new_status: str (更新後ステータス、常に"DONE")
            - message: str
            - error: str (エラー時のみ)

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    try:
        # 入力検証
        validate_project_name(project_id)
        validate_order_id(order_id)

        with transaction(db_path=db_path) as conn:
            # プロジェクト存在確認
            if not project_exists(conn, project_id):
                return {
                    "success": False,
                    "error": f"プロジェクトが見つかりません: {project_id}",
                }

            # ORDER存在確認
            if not order_exists(conn, order_id, project_id):
                return {
                    "success": False,
                    "error": f"ORDERが見つかりません: {order_id} (project: {project_id})",
                }

            # 紐付いているBACKLOGを検索
            backlog = fetch_one(
                conn,
                """
                SELECT id, status FROM backlog_items
                WHERE related_order_id = ? AND project_id = ?
                """,
                (order_id, project_id)
            )

            if not backlog:
                # 紐付きがない場合（手動ORDERなど）
                return {
                    "success": True,
                    "backlog_id": None,
                    "old_status": None,
                    "new_status": None,
                    "message": f"ORDER {order_id} に紐付くBACKLOGはありません（手動ORDERの可能性）",
                }

            backlog_dict = dict(backlog)
            backlog_id = backlog_dict["id"]
            current_status = backlog_dict["status"]

            # 既にDONEの場合はスキップ
            if current_status == "DONE":
                return {
                    "success": True,
                    "backlog_id": backlog_id,
                    "old_status": current_status,
                    "new_status": "DONE",
                    "message": f"BACKLOG {backlog_id} は既にDONEです",
                }

            # IN_PROGRESS → DONE の遷移を実行
            if current_status == "IN_PROGRESS":
                now = datetime.now().isoformat()
                change_reason = reason or f"ORDER {order_id} 完了に伴う自動更新"

                # BACKLOGステータス更新
                execute_query(
                    conn,
                    """
                    UPDATE backlog_items
                    SET status = ?, completed_at = ?, updated_at = ?
                    WHERE id = ? AND project_id = ?
                    """,
                    ("DONE", now, now, backlog_id, project_id)
                )

                # 状態遷移履歴を記録
                record_transition(
                    conn,
                    "backlog",
                    backlog_id,
                    "IN_PROGRESS",
                    "DONE",
                    "System",
                    change_reason
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
                    ("backlog", backlog_id, "status", "IN_PROGRESS", "DONE", "System", change_reason)
                )

                return {
                    "success": True,
                    "backlog_id": backlog_id,
                    "old_status": "IN_PROGRESS",
                    "new_status": "DONE",
                    "message": f"BACKLOG {backlog_id} をDONEに更新しました",
                }
            else:
                # IN_PROGRESS以外のステータスは更新しない（想定外の状態）
                return {
                    "success": False,
                    "backlog_id": backlog_id,
                    "old_status": current_status,
                    "new_status": None,
                    "error": f"BACKLOG {backlog_id} のステータスが IN_PROGRESS ではありません: {current_status}",
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


def main():
    """コマンドライン実行（デバッグ用）"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="ORDER完了時にBACKLOGをDONEに自動更新（デバッグ用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", help="ORDER ID")
    parser.add_argument("--reason", help="変更理由")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    result = auto_update_backlog_on_order_complete(
        args.project_id,
        args.order_id,
        args.reason,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            print(f"[OK] {result['message']}")
            if result["old_status"] and result["new_status"]:
                print(f"  BACKLOG: {result['backlog_id']}")
                print(f"  ステータス: {result['old_status']} → {result['new_status']}")
        else:
            print(f"[ERROR] {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
