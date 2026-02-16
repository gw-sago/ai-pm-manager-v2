#!/usr/bin/env python3
"""
AI PM Framework - ORDER更新スクリプト

Usage:
    python backend/order/update.py PROJECT_NAME ORDER_ID --status NEW_STATUS [options]
    python backend/order/update.py PROJECT_NAME ORDER_ID --complete [options]

Options:
    --status        ステータス変更（PLANNING/IN_PROGRESS/REVIEW/COMPLETED/ON_HOLD/CANCELLED）
    --complete      COMPLETEDまで自動段階遷移（PLANNING→IN_PROGRESS→REVIEW→COMPLETED）
    --title         タイトル変更
    --priority      優先度変更（P0/P1/P2）
    --role          操作者の役割（PM、デフォルト: PM）
    --reason        変更理由
    --render        Markdown生成を実行（デフォルト: True）
    --json          JSON形式で出力

Example:
    python backend/order/update.py AI_PM_PJ ORDER_036 --status IN_PROGRESS
    python backend/order/update.py AI_PM_PJ ORDER_036 --status ON_HOLD --reason "リソース調整"
    python backend/order/update.py AI_PM_PJ ORDER_036 --priority P0
    python backend/order/update.py AI_PM_PJ ORDER_036 --complete --reason "全タスク完了"
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
    get_connection, transaction, execute_query, fetch_one, fetch_all,
    row_to_dict, DatabaseError
)
from utils.validation import (
    validate_project_name, validate_order_id,
    validate_status, validate_priority,
    order_exists, ValidationError
)
from utils.transition import (
    validate_transition, record_transition, TransitionError
)


def update_order(
    project_id: str,
    order_id: str,
    *,
    status: Optional[str] = None,
    title: Optional[str] = None,
    priority: Optional[str] = None,
    role: str = "PM",
    reason: Optional[str] = None,
    render: bool = True,
) -> Dict[str, Any]:
    """
    ORDERを更新

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        status: 新しいステータス
        title: 新しいタイトル
        priority: 新しい優先度
        role: 操作者の役割（PM）
        reason: 変更理由
        render: Markdown生成を実行するか

    Returns:
        更新されたORDER情報

    Raises:
        ValidationError: 入力検証エラー
        TransitionError: 状態遷移エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_order_id(order_id)

    if status:
        validate_status(status, "order")

    if priority:
        validate_priority(priority)

    if role != "PM":
        raise ValidationError(f"ORDER操作はPMのみ可能です: {role}", "role", role)

    with transaction() as conn:
        # ORDER存在確認（複合キー対応）
        if not order_exists(conn, order_id, project_id):
            raise ValidationError(f"ORDERが見つかりません: {order_id} (project: {project_id})", "order_id", order_id)

        # 現在のORDER情報を取得（複合キー対応）
        current = fetch_one(
            conn,
            "SELECT * FROM orders WHERE id = ? AND project_id = ?",
            (order_id, project_id)
        )

        if not current:
            raise ValidationError(f"ORDERが見つかりません: {order_id} (project: {project_id})", "order_id", order_id)

        current_dict = dict(current)
        updates = []
        params = []
        changes = []

        # ステータス更新
        if status and status != current_dict["status"]:
            # 状態遷移検証
            validate_transition(conn, "order", current_dict["status"], status, role)

            updates.append("status = ?")
            params.append(status)
            changes.append(("status", current_dict["status"], status))

            # ステータスに応じたタイムスタンプ更新
            if status == "IN_PROGRESS" and not current_dict.get("started_at"):
                updates.append("started_at = ?")
                params.append(datetime.now().isoformat())

            if status == "COMPLETED":
                updates.append("completed_at = ?")
                params.append(datetime.now().isoformat())

                # ORDER完了時にダッシュボードを更新
                try:
                    _trigger_dashboard_update()
                except Exception as e:
                    # ダッシュボード更新失敗は警告のみ（メイン処理は継続）
                    import logging
                    logging.warning(f"ダッシュボード更新に失敗しました: {e}")

        # タイトル更新
        if title and title != current_dict["title"]:
            updates.append("title = ?")
            params.append(title)
            changes.append(("title", current_dict["title"], title))

        # 優先度更新
        if priority and priority != current_dict["priority"]:
            updates.append("priority = ?")
            params.append(priority)
            changes.append(("priority", current_dict["priority"], priority))

        # 更新がなければ早期リターン
        if not updates:
            return row_to_dict(current)

        # updated_at を追加
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())

        # WHERE句のパラメータ（複合キー対応）
        params.append(order_id)
        params.append(project_id)

        # UPDATE実行（複合キー対応）
        execute_query(
            conn,
            f"UPDATE orders SET {', '.join(updates)} WHERE id = ? AND project_id = ?",
            tuple(params)
        )

        # 変更履歴を記録
        changed_by = "PM"
        for field, old_val, new_val in changes:
            execute_query(
                conn,
                """
                INSERT INTO change_history (
                    entity_type, entity_id, field_name,
                    old_value, new_value, changed_by, change_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("order", order_id, field, str(old_val) if old_val else None, str(new_val) if new_val else None, changed_by, reason)
            )

        # ステータス変更時は状態遷移履歴も記録
        if status and status != current_dict["status"]:
            record_transition(
                conn,
                "order",
                order_id,
                current_dict["status"],
                status,
                changed_by,
                reason
            )

        # 更新後のORDERを取得（複合キー対応）
        updated = fetch_one(
            conn,
            "SELECT * FROM orders WHERE id = ? AND project_id = ?",
            (order_id, project_id)
        )

        result = row_to_dict(updated)

    return result


def update_order_status(
    project_id: str,
    order_id: str,
    status: str,
    role: str = "PM",
    reason: Optional[str] = None,
    render: bool = True,
) -> Dict[str, Any]:
    """
    ORDERのステータスのみを更新（ショートカット関数）

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        status: 新しいステータス
        role: 操作者の役割（PM）
        reason: 変更理由
        render: Markdown生成を実行するか

    Returns:
        更新されたORDER情報
    """
    return update_order(
        project_id,
        order_id,
        status=status,
        role=role,
        reason=reason,
        render=render,
    )


def complete_order(
    project_id: str,
    order_id: str,
    reason: Optional[str] = None,
    render: bool = True,
) -> Dict[str, Any]:
    """
    ORDERを完了状態にする（自動段階遷移）

    現在のステータスから COMPLETED まで自動的に段階遷移を実行します。
    PLANNING → IN_PROGRESS → REVIEW → COMPLETED の順に遷移します。
    ORDER完了時に、紐付いているBACKLOGも自動的にDONEに更新します。

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        reason: 変更理由
        render: Markdown生成を実行するか（各遷移後は抑制、最終遷移後のみ実行）

    Returns:
        更新されたORDER情報

    Raises:
        ValidationError: 入力検証エラー
        TransitionError: 状態遷移エラー（既にCOMPLETEDの場合など）
        DatabaseError: DB操作エラー

    Example:
        # PLANNINGから一気にCOMPLETEDへ
        result = complete_order("AI_PM_PJ", "ORDER_046")

        # IN_PROGRESSから一気にCOMPLETEDへ
        result = complete_order("AI_PM_PJ", "ORDER_046", reason="全タスク完了")
    """
    # 入力検証
    validate_project_name(project_id)
    validate_order_id(order_id)

    # 遷移パス定義（順番に遷移していく）
    transitions = [
        ("PLANNING", "IN_PROGRESS"),
        ("IN_PROGRESS", "REVIEW"),
        ("REVIEW", "COMPLETED"),
    ]

    # 現在のORDER情報を取得
    with get_connection() as conn:
        current = fetch_one(
            conn,
            "SELECT * FROM orders WHERE id = ? AND project_id = ?",
            (order_id, project_id)
        )

        if not current:
            raise ValidationError(f"ORDERが見つかりません: {order_id} (project: {project_id})", "order_id", order_id)

        current_status = dict(current)["status"]

    # 既にCOMPLETEDの場合はそのまま返す
    if current_status == "COMPLETED":
        return row_to_dict(current)

    # 現在のステータスから順次遷移
    executed_transitions = []
    result = None

    for from_status, to_status in transitions:
        if current_status == from_status:
            # このステップの遷移を実行（途中はrenderを抑制）
            is_final = (to_status == "COMPLETED")
            result = update_order(
                project_id,
                order_id,
                status=to_status,
                reason=reason,
                render=render and is_final,  # 最終遷移のみrender
            )
            executed_transitions.append((from_status, to_status))
            current_status = to_status

    # 何も遷移できなかった場合（CANCELLED, ON_HOLD等）
    if not executed_transitions:
        raise TransitionError(
            f"ORDERを完了できません: 現在のステータス '{current_status}' からCOMPLETEDへの遷移パスがありません",
            entity_type="order",
            from_status=current_status,
            to_status="COMPLETED",
            role="PM",
        )

    # ORDER完了後、紐付いているBACKLOGをDONEに更新
    if current_status == "COMPLETED":
        _complete_related_backlog(project_id, order_id, reason)

    return result


def _trigger_dashboard_update() -> None:
    """
    ORDER完了時にダッシュボード更新を実行

    portfolio/generate_json.py を呼び出してJSON統計を更新する
    """
    try:
        from portfolio.generate_json import generate_portfolio_json
        from pathlib import Path

        # JSON出力先ディレクトリ
        _script_dir = Path(__file__).resolve().parent.parent
        output_dir = _script_dir / "portfolio" / "portfolio"

        # ダッシュボードJSON更新
        generate_portfolio_json(output_dir)
    except ImportError:
        # モジュールが見つからない場合はスキップ
        pass
    except Exception as e:
        # その他のエラーは上位に伝播
        raise


def _complete_related_backlog(
    project_id: str,
    order_id: str,
    reason: Optional[str] = None,
) -> None:
    """
    ORDER完了時に紐付いているBACKLOGをDONEに更新

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        reason: 変更理由
    """
    with transaction() as conn:
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
            # 紐付きがない場合は何もしない（手動ORDER等）
            return

        backlog_dict = dict(backlog)
        backlog_id = backlog_dict["id"]
        current_status = backlog_dict["status"]

        # 既にDONEの場合はスキップ
        if current_status == "DONE":
            return

        # IN_PROGRESS → DONE の遷移を実行
        if current_status == "IN_PROGRESS":
            now = datetime.now().isoformat()

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
                "PM",
                reason or f"ORDER {order_id} 完了に伴う自動更新"
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
                ("backlog", backlog_id, "status", "IN_PROGRESS", "DONE", "PM", reason or f"ORDER {order_id} 完了に伴う自動更新")
            )


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="ORDERを更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", help="ORDER ID")
    parser.add_argument("--status", help="ステータス変更")
    parser.add_argument("--complete", action="store_true", help="COMPLETEDまで自動段階遷移")
    parser.add_argument("--title", help="タイトル変更")
    parser.add_argument("--priority", help="優先度変更（P0/P1/P2）")
    parser.add_argument("--role", default="PM", help="操作者の役割（PM）")
    parser.add_argument("--reason", help="変更理由")
    parser.add_argument("--no-render", action="store_true", help="Markdown生成をスキップ")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # --completeと--statusは排他的
    if args.complete and args.status:
        print("エラー: --complete と --status は同時に指定できません", file=sys.stderr)
        sys.exit(1)

    # 更新内容がなければエラー
    if not any([args.status, args.complete, args.title, args.priority]):
        print("エラー: 更新内容を指定してください", file=sys.stderr)
        sys.exit(1)

    try:
        # --completeの場合は complete_order を使用
        if args.complete:
            result = complete_order(
                args.project_id,
                args.order_id,
                reason=args.reason,
                render=not args.no_render,
            )
        else:
            result = update_order(
                args.project_id,
                args.order_id,
                status=args.status,
                title=args.title,
                priority=args.priority,
                role=args.role,
                reason=args.reason,
                render=not args.no_render,
            )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            if args.complete:
                print(f"ORDERを完了しました: {result['id']}")
            else:
                print(f"ORDERを更新しました: {result['id']}")
            print(f"  タイトル: {result['title']}")
            print(f"  優先度: {result['priority']}")
            print(f"  ステータス: {result['status']}")

    except (ValidationError, TransitionError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
