#!/usr/bin/env python3
"""
AI PM Framework - 横断バックログ更新スクリプト

Usage:
    python backend/xbacklog/update.py XBACKLOG_ID [options]

Arguments:
    XBACKLOG_ID         横断バックログID（例: XBACKLOG_001）

Options:
    --title TITLE       タイトルを変更
    --desc DESCRIPTION  説明を変更
    --priority PRIORITY 優先度を変更（High/Medium/Low）
    --status STATUS     ステータスを変更（PENDING/ANALYZING/ASSIGNED/DONE/CANCELED）
    --project PROJECT_ID 振り分け先プロジェクトを設定
    --backlog BACKLOG_ID 振り分け後のBACKLOG IDを設定
    --analysis JSON     分析結果を設定（JSON文字列）
    --json              JSON形式で出力

Example:
    python backend/xbacklog/update.py XBACKLOG_001 --status ANALYZING
    python backend/xbacklog/update.py XBACKLOG_001 --project AI_PM_PJ --status ASSIGNED
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query, fetch_one, DatabaseError
from utils.validation import ValidationError


# 有効なステータス値
VALID_STATUSES = ('PENDING', 'ANALYZING', 'ASSIGNED', 'DONE', 'CANCELED')

# 有効な優先度値
VALID_PRIORITIES = ('High', 'Medium', 'Low')


def update_xbacklog(
    xbacklog_id: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    assigned_project_id: Optional[str] = None,
    assigned_backlog_id: Optional[str] = None,
    analysis_result: Optional[str] = None,
) -> Dict[str, Any]:
    """
    横断バックログを更新

    Args:
        xbacklog_id: 横断バックログID
        title: 新しいタイトル
        description: 新しい説明
        priority: 新しい優先度
        status: 新しいステータス
        assigned_project_id: 振り分け先プロジェクト
        assigned_backlog_id: 振り分け後のBACKLOG ID
        analysis_result: 分析結果（JSON文字列）

    Returns:
        更新後の横断バックログ情報

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    conn = get_connection()
    try:
        # 存在確認
        existing = fetch_one(
            conn,
            "SELECT * FROM cross_project_backlog WHERE id = ?",
            (xbacklog_id,)
        )

        if not existing:
            raise ValidationError(f"横断バックログ '{xbacklog_id}' が見つかりません")

        # 更新フィールドを構築
        updates = []
        params = []

        if title is not None:
            if not title:
                raise ValidationError("タイトルを空にすることはできません")
            updates.append("title = ?")
            params.append(title)

        if description is not None:
            updates.append("description = ?")
            params.append(description if description else None)

        if priority is not None:
            if priority not in VALID_PRIORITIES:
                raise ValidationError(
                    f"無効な優先度: {priority}. "
                    f"有効な値: {', '.join(VALID_PRIORITIES)}"
                )
            updates.append("priority = ?")
            params.append(priority)

        if status is not None:
            if status not in VALID_STATUSES:
                raise ValidationError(
                    f"無効なステータス: {status}. "
                    f"有効な値: {', '.join(VALID_STATUSES)}"
                )
            updates.append("status = ?")
            params.append(status)

        if assigned_project_id is not None:
            # プロジェクト存在確認
            if assigned_project_id:
                proj = fetch_one(
                    conn,
                    "SELECT id FROM projects WHERE id = ?",
                    (assigned_project_id,)
                )
                if not proj:
                    raise ValidationError(f"プロジェクト '{assigned_project_id}' が見つかりません")
            updates.append("assigned_project_id = ?")
            params.append(assigned_project_id if assigned_project_id else None)

        if assigned_backlog_id is not None:
            updates.append("assigned_backlog_id = ?")
            params.append(assigned_backlog_id if assigned_backlog_id else None)

        if analysis_result is not None:
            # JSON形式の検証
            if analysis_result:
                try:
                    json.loads(analysis_result)
                except json.JSONDecodeError:
                    raise ValidationError("analysis_resultは有効なJSON文字列である必要があります")
            updates.append("analysis_result = ?")
            params.append(analysis_result if analysis_result else None)

        if not updates:
            raise ValidationError("更新するフィールドが指定されていません")

        # updated_atを追加
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())

        # パラメータにIDを追加
        params.append(xbacklog_id)

        # 更新実行
        query = f"UPDATE cross_project_backlog SET {', '.join(updates)} WHERE id = ?"
        execute_query(conn, query, tuple(params))
        conn.commit()

        # 更新後のデータを取得
        result = fetch_one(
            conn,
            """
            SELECT id, supervisor_id, title, description, priority, status,
                   assigned_project_id, assigned_backlog_id, analysis_result,
                   created_at, updated_at
            FROM cross_project_backlog WHERE id = ?
            """,
            (xbacklog_id,)
        )

        return dict(result) if result else {}

    except Exception as e:
        conn.rollback()
        if isinstance(e, ValidationError):
            raise
        raise DatabaseError(f"横断バックログ更新エラー: {e}")
    finally:
        conn.close()


def main():
    """CLI エントリーポイント"""
    try:
        from config import setup_utf8_output
    except ImportError:
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="横断バックログを更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("xbacklog_id", help="横断バックログID")
    parser.add_argument("--title", help="新しいタイトル")
    parser.add_argument("--desc", dest="description", help="新しい説明")
    parser.add_argument("--priority", choices=VALID_PRIORITIES,
                        help="新しい優先度")
    parser.add_argument("--status", choices=VALID_STATUSES,
                        help="新しいステータス")
    parser.add_argument("--project", dest="assigned_project_id",
                        help="振り分け先プロジェクトID")
    parser.add_argument("--backlog", dest="assigned_backlog_id",
                        help="振り分け後のBACKLOG ID")
    parser.add_argument("--analysis", dest="analysis_result",
                        help="分析結果（JSON文字列）")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # 更新対象がなければエラー
    if all(v is None for v in [
        args.title, args.description, args.priority, args.status,
        args.assigned_project_id, args.assigned_backlog_id, args.analysis_result
    ]):
        parser.error("更新するフィールドを指定してください")

    try:
        xbacklog = update_xbacklog(
            args.xbacklog_id,
            title=args.title,
            description=args.description,
            priority=args.priority,
            status=args.status,
            assigned_project_id=args.assigned_project_id,
            assigned_backlog_id=args.assigned_backlog_id,
            analysis_result=args.analysis_result,
        )

        if args.json:
            print(json.dumps(xbacklog, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"横断バックログ '{args.xbacklog_id}' を更新しました。")
            print(f"  タイトル: {xbacklog['title']}")
            print(f"  優先度: {xbacklog['priority']}")
            print(f"  ステータス: {xbacklog['status']}")
            if xbacklog.get('assigned_project_id'):
                print(f"  振り分け先: {xbacklog['assigned_project_id']}")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
