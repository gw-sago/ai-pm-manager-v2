#!/usr/bin/env python3
"""
AI PM Framework - 横断バックログ振り分け実行スクリプト

Usage:
    python backend/xbacklog/dispatch.py XBACKLOG_ID PROJECT_ID [options]

Arguments:
    XBACKLOG_ID         横断バックログID（例: XBACKLOG_001）
    PROJECT_ID          振り分け先プロジェクトID

Options:
    --auto              分析結果の推奨プロジェクトを自動選択（PROJECT_ID不要）
    --priority PRIORITY 作成するバックログの優先度（High/Medium/Low）
    --json              JSON形式で出力

Example:
    python backend/xbacklog/dispatch.py XBACKLOG_001 AI_PM_PJ
    python backend/xbacklog/dispatch.py XBACKLOG_001 --auto
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

from utils.db import get_connection, execute_query, fetch_one, fetch_all, DatabaseError
from utils.validation import ValidationError


def get_next_backlog_id(conn, project_id: str) -> str:
    """
    指定プロジェクトの次のBACKLOG IDを取得

    Args:
        conn: DB接続
        project_id: プロジェクトID

    Returns:
        次のBACKLOG ID
    """
    result = fetch_one(
        conn,
        """
        SELECT id FROM backlog_items
        WHERE project_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (project_id,)
    )

    if result:
        current_num = int(result['id'].split('_')[1])
        return f"BACKLOG_{current_num + 1:03d}"
    else:
        return "BACKLOG_001"


def dispatch_xbacklog(
    xbacklog_id: str,
    project_id: Optional[str] = None,
    auto: bool = False,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    """
    横断バックログを指定プロジェクトに振り分け

    Args:
        xbacklog_id: 横断バックログID
        project_id: 振り分け先プロジェクトID（autoの場合は省略可）
        auto: 分析結果の推奨プロジェクトを自動選択
        priority: 作成するバックログの優先度（省略時は横断バックログから継承）

    Returns:
        振り分け結果

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    conn = get_connection()
    try:
        # 横断バックログ取得
        xbacklog = fetch_one(
            conn,
            "SELECT * FROM cross_project_backlog WHERE id = ?",
            (xbacklog_id,)
        )

        if not xbacklog:
            raise ValidationError(f"横断バックログ '{xbacklog_id}' が見つかりません")

        xbacklog = dict(xbacklog)

        # 既に振り分け済みの場合
        if xbacklog['status'] == 'ASSIGNED':
            raise ValidationError(
                f"横断バックログ '{xbacklog_id}' は既に振り分け済みです "
                f"(振り分け先: {xbacklog['assigned_project_id']})"
            )

        if xbacklog['status'] == 'DONE':
            raise ValidationError(f"横断バックログ '{xbacklog_id}' は完了済みです")

        # 自動モードの場合、分析結果から推奨プロジェクトを取得
        if auto:
            if not xbacklog.get('analysis_result'):
                raise ValidationError(
                    "自動振り分けには分析結果が必要です。先に analyze を実行してください"
                )

            try:
                analysis = json.loads(xbacklog['analysis_result'])
                if analysis.get('top_recommendation'):
                    project_id = analysis['top_recommendation']['project_id']
                elif analysis.get('recommendations'):
                    project_id = analysis['recommendations'][0]['project_id']
                else:
                    raise ValidationError("分析結果に推奨プロジェクトがありません")
            except json.JSONDecodeError:
                raise ValidationError("分析結果のJSON解析に失敗しました")

        if not project_id:
            raise ValidationError("振り分け先プロジェクトIDを指定してください")

        # プロジェクト存在確認
        project = fetch_one(
            conn,
            "SELECT id, name FROM projects WHERE id = ?",
            (project_id,)
        )
        if not project:
            raise ValidationError(f"プロジェクト '{project_id}' が見つかりません")

        # 優先度の決定
        backlog_priority = priority or xbacklog['priority']

        # 新規BACKLOG ID採番
        new_backlog_id = get_next_backlog_id(conn, project_id)
        now = datetime.now().isoformat()

        # backlog_itemsに追加
        execute_query(
            conn,
            """
            INSERT INTO backlog_items
            (id, project_id, title, description, priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'TODO', ?, ?)
            """,
            (
                new_backlog_id,
                project_id,
                xbacklog['title'],
                f"[横断バックログから振り分け: {xbacklog_id}]\n\n{xbacklog.get('description', '')}",
                backlog_priority,
                now,
                now
            )
        )

        # 横断バックログを更新
        execute_query(
            conn,
            """
            UPDATE cross_project_backlog
            SET status = 'ASSIGNED',
                assigned_project_id = ?,
                assigned_backlog_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (project_id, new_backlog_id, now, xbacklog_id)
        )

        conn.commit()

        return {
            'success': True,
            'xbacklog_id': xbacklog_id,
            'xbacklog_title': xbacklog['title'],
            'assigned_project_id': project_id,
            'assigned_project_name': project['name'],
            'assigned_backlog_id': new_backlog_id,
            'priority': backlog_priority,
            'auto_selected': auto,
            'message': f"横断バックログ '{xbacklog_id}' を {project_id} の {new_backlog_id} に振り分けました"
        }

    except Exception as e:
        conn.rollback()
        if isinstance(e, ValidationError):
            raise
        raise DatabaseError(f"振り分けエラー: {e}")
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
        description="横断バックログをプロジェクトに振り分け",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("xbacklog_id", help="横断バックログID")
    parser.add_argument("project_id", nargs="?", help="振り分け先プロジェクトID")
    parser.add_argument("--auto", action="store_true",
                        help="分析結果の推奨プロジェクトを自動選択")
    parser.add_argument("--priority", choices=['High', 'Medium', 'Low'],
                        help="作成するバックログの優先度")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # project_idとautoの両方がない場合はエラー
    if not args.project_id and not args.auto:
        parser.error("PROJECT_ID または --auto を指定してください")

    try:
        result = dispatch_xbacklog(
            args.xbacklog_id,
            project_id=args.project_id,
            auto=args.auto,
            priority=args.priority,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== 振り分け完了 ===")
            print(result['message'])
            print(f"\n  横断バックログ: {result['xbacklog_id']}")
            print(f"  タイトル: {result['xbacklog_title']}")
            print(f"  振り分け先: {result['assigned_project_id']} ({result['assigned_project_name']})")
            print(f"  作成BACKLOG: {result['assigned_backlog_id']}")
            print(f"  優先度: {result['priority']}")
            if result['auto_selected']:
                print(f"  (分析結果に基づく自動選択)")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
