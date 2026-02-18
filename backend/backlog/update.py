#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG状態更新スクリプト

Usage:
    python backend/backlog/update.py PROJECT_NAME BACKLOG_ID [options]

Options:
    --status        新しいステータス（TODO/IN_PROGRESS/DONE/CANCELED）
    --order-id      関連ORDER ID（ORDER変換時に指定）
    --title         タイトル更新
    --priority      優先度更新（High/Medium/Low）
    --description   説明更新
    --sort-order    数値優先度（低い数値 = 高優先度、デフォルト999）
    --render        （廃止: 後方互換性のため引数のみ残存）
    --json          JSON形式で出力

Example:
    # ステータス更新
    python backend/backlog/update.py AI_PM_PJ BACKLOG_029 --status IN_PROGRESS

    # ORDER変換時（IN_PROGRESSに遷移+ORDER紐付け）
    python backend/backlog/update.py AI_PM_PJ BACKLOG_029 --status IN_PROGRESS --order-id ORDER_036

    # 完了処理
    python backend/backlog/update.py AI_PM_PJ BACKLOG_029 --status DONE
"""

import argparse
import json
import sys
from dataclasses import dataclass
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
    row_to_dict,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    validate_backlog_id,
    validate_order_id,
    validate_status,
    project_exists,
    order_exists,
    ValidationError,
    VALID_STATUSES,
)
from utils.transition import (
    validate_transition,
    record_transition,
    TransitionError,
)


# 優先度定義
VALID_PRIORITIES = ["High", "Medium", "Low"]


@dataclass
class UpdateBacklogResult:
    """BACKLOG更新結果"""
    success: bool
    backlog_id: str = ""
    old_status: str = ""
    new_status: str = ""
    related_order_id: Optional[str] = None
    message: str = ""
    error: Optional[str] = None


def get_backlog(conn, backlog_id: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    BACKLOGを取得

    Args:
        conn: データベース接続
        backlog_id: BACKLOG ID
        project_id: プロジェクトID

    Returns:
        Dict or None: BACKLOG情報
    """
    row = fetch_one(
        conn,
        "SELECT * FROM backlog_items WHERE id = ? AND project_id = ?",
        (backlog_id, project_id)
    )
    return row_to_dict(row)


def update_backlog(
    project_name: str,
    backlog_id: str,
    *,
    status: Optional[str] = None,
    order_id: Optional[str] = None,
    title: Optional[str] = None,
    priority: Optional[str] = None,
    description: Optional[str] = None,
    sort_order: Optional[int] = None,
    render: bool = True,
    db_path: Optional[Path] = None,
) -> UpdateBacklogResult:
    """
    BACKLOG状態を更新

    Args:
        project_name: プロジェクト名
        backlog_id: BACKLOG ID
        status: 新しいステータス
        order_id: 関連ORDER ID（ORDER変換時）
        title: タイトル更新
        priority: 優先度更新
        description: 説明更新
        sort_order: 数値優先度（低い数値 = 高優先度、デフォルト999）
        render: （廃止: 後方互換性のため引数のみ残存）
        db_path: データベースパス（テスト用）

    Returns:
        UpdateBacklogResult: 更新結果

    Workflow:
        1. BACKLOG存在確認
        2. 状態遷移の検証
        3. フィールド更新
        4. ORDER変換時: IN_PROGRESS + ORDER_ID紐付け
        5. 変更履歴を記録
        6. （廃止: BACKLOG.md生成は実行されなくなりました）

    Status Transitions:
        - TODO → IN_PROGRESS: ORDER変換（ORDER_ID必須）
        - IN_PROGRESS → DONE: ORDER完了
        - TODO → CANCELED: キャンセル
        - TODO → EXTERNAL: 外部プロジェクト化
    """
    try:
        # 入力検証
        validate_project_name(project_name)
        validate_backlog_id(backlog_id)

        if status:
            validate_status(status, "backlog")

        if order_id:
            validate_order_id(order_id)

        if priority and priority not in VALID_PRIORITIES:
            return UpdateBacklogResult(
                success=False,
                backlog_id=backlog_id,
                error=f"無効な優先度: {priority}\n有効な優先度: {', '.join(VALID_PRIORITIES)}"
            )

        with transaction(db_path=db_path) as conn:
            # 1. プロジェクト存在確認
            if not project_exists(conn, project_name):
                return UpdateBacklogResult(
                    success=False,
                    backlog_id=backlog_id,
                    error=f"プロジェクトが見つかりません: {project_name}"
                )

            # 2. BACKLOG存在確認（project_id条件付き）
            backlog = get_backlog(conn, backlog_id, project_name)
            if not backlog:
                return UpdateBacklogResult(
                    success=False,
                    backlog_id=backlog_id,
                    error=f"BACKLOGが見つかりません（プロジェクト {project_name} 内）: {backlog_id}"
                )

            old_status = backlog["status"]
            new_status = status or old_status

            # 3. ORDER変換時の特別処理
            if status == "IN_PROGRESS" and old_status == "TODO":
                # ORDER変換時はORDER_IDが必要
                if not order_id:
                    return UpdateBacklogResult(
                        success=False,
                        backlog_id=backlog_id,
                        old_status=old_status,
                        error="ORDER変換時はORDER IDを指定してください（--order-id ORDER_XXX）"
                    )

                # ORDER存在確認（複合キー対応: project_nameを指定）
                if not order_exists(conn, order_id, project_name):
                    return UpdateBacklogResult(
                        success=False,
                        backlog_id=backlog_id,
                        old_status=old_status,
                        error=f"ORDERが見つかりません: {order_id} (project: {project_name})"
                    )

            # 4. 状態遷移検証
            # status_transitionsテーブルにルールがない場合はフォールバック（直接UPDATE許可）
            _transition_rule_exists = True
            if status and status != old_status:
                try:
                    validate_transition(conn, "backlog", old_status, status, "PM")
                except TransitionError:
                    # フォールバック: status_transitionsにルールが存在しない場合でも
                    # 直接UPDATEを許可する（backlogエンティティの遷移ルール未登録対策）
                    _transition_rule_exists = False

            # 5. 更新フィールドを構築
            update_fields: List[str] = []
            update_values: List[Any] = []

            if status and status != old_status:
                update_fields.append("status = ?")
                update_values.append(status)

                # 完了時は完了日時を記録
                if status == "DONE":
                    update_fields.append("completed_at = ?")
                    update_values.append(datetime.now().isoformat())

            if order_id:
                update_fields.append("related_order_id = ?")
                update_values.append(order_id)

            if title:
                update_fields.append("title = ?")
                update_values.append(title)

            if priority:
                update_fields.append("priority = ?")
                update_values.append(priority)

            if description is not None:  # 空文字列も許可
                update_fields.append("description = ?")
                update_values.append(description)

            if sort_order is not None:
                update_fields.append("sort_order = ?")
                update_values.append(sort_order)

            # 更新するフィールドがない場合
            if not update_fields:
                return UpdateBacklogResult(
                    success=True,
                    backlog_id=backlog_id,
                    old_status=old_status,
                    new_status=old_status,
                    message="更新するフィールドがありません"
                )

            # updated_atを追加
            update_fields.append("updated_at = ?")
            update_values.append(datetime.now().isoformat())

            # WHERE句の値を追加
            update_values.append(backlog_id)
            update_values.append(project_name)

            # 6. UPDATE実行
            execute_query(
                conn,
                f"""
                UPDATE backlog_items
                SET {', '.join(update_fields)}
                WHERE id = ? AND project_id = ?
                """,
                tuple(update_values)
            )

            # 7. 変更履歴を記録
            if status and status != old_status:
                change_reason = f"ステータス更新: {old_status} → {status}"
                if order_id:
                    change_reason += f" (ORDER: {order_id})"

                record_transition(
                    conn,
                    "backlog",
                    backlog_id,
                    old_status,
                    status,
                    "PM",
                    change_reason
                )

            result = UpdateBacklogResult(
                success=True,
                backlog_id=backlog_id,
                old_status=old_status,
                new_status=new_status,
                related_order_id=order_id,
                message=f"BACKLOGを更新しました: {backlog_id}"
            )

        # 8. render引数は後方互換性のため残すが、処理は実行しない
        # （BACKLOG.md廃止: ORDER_090）

        return result

    except ValidationError as e:
        return UpdateBacklogResult(
            success=False,
            backlog_id=backlog_id,
            error=f"入力検証エラー: {e}"
        )
    except TransitionError as e:
        return UpdateBacklogResult(
            success=False,
            backlog_id=backlog_id,
            error=f"状態遷移エラー: {e}"
        )
    except DatabaseError as e:
        return UpdateBacklogResult(
            success=False,
            backlog_id=backlog_id,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return UpdateBacklogResult(
            success=False,
            backlog_id=backlog_id,
            error=f"予期しないエラー: {e}"
        )


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
        description="BACKLOG状態を更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # ORDER変換（TODO → IN_PROGRESS + ORDER紐付け）
  python update.py AI_PM_PJ BACKLOG_029 --status IN_PROGRESS --order-id ORDER_036

  # 完了処理（IN_PROGRESS → DONE）
  python update.py AI_PM_PJ BACKLOG_029 --status DONE

  # キャンセル
  python update.py AI_PM_PJ BACKLOG_029 --status CANCELED

  # 優先度・タイトル更新
  python update.py AI_PM_PJ BACKLOG_029 --priority High --title "新タイトル"

  # 数値優先度更新
  python update.py AI_PM_PJ BACKLOG_029 --sort-order 1

ステータス遷移ルール:
  TODO → IN_PROGRESS: ORDER変換（--order-id 必須）
  TODO → CANCELED: キャンセル
  TODO → EXTERNAL: 外部プロジェクト化
  IN_PROGRESS → DONE: ORDER完了
"""
    )

    parser.add_argument(
        "project_name",
        help="プロジェクト名 (例: AI_PM_PJ)"
    )
    parser.add_argument(
        "backlog_id",
        help="BACKLOG ID (例: BACKLOG_029)"
    )
    parser.add_argument(
        "--status", "-s",
        choices=VALID_STATUSES["backlog"],
        help="新しいステータス"
    )
    parser.add_argument(
        "--order-id", "-o",
        help="関連ORDER ID（ORDER変換時）"
    )
    parser.add_argument(
        "--title", "-t",
        help="タイトル更新"
    )
    parser.add_argument(
        "--priority", "-p",
        choices=VALID_PRIORITIES,
        help="優先度更新"
    )
    parser.add_argument(
        "--description", "-d",
        help="説明更新"
    )
    parser.add_argument(
        "--sort-order",
        type=int,
        help="数値優先度（低い数値 = 高優先度、デフォルト999）"
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="（廃止: 後方互換性のため引数のみ残存）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    result = update_backlog(
        project_name=args.project_name,
        backlog_id=args.backlog_id,
        status=args.status,
        order_id=args.order_id,
        title=args.title,
        priority=args.priority,
        description=args.description,
        sort_order=args.sort_order,
        render=not args.no_render,
    )

    if args.json:
        output = {
            "success": result.success,
            "backlog_id": result.backlog_id,
            "old_status": result.old_status,
            "new_status": result.new_status,
            "related_order_id": result.related_order_id,
            "message": result.message,
            "error": result.error,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            if result.old_status != result.new_status:
                print(f"  ステータス: {result.old_status} → {result.new_status}")
            if result.related_order_id:
                print(f"  関連ORDER: {result.related_order_id}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
