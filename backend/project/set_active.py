#!/usr/bin/env python3
"""
AI PM Framework - プロジェクトアクティブ状態切り替えスクリプト

Usage:
    python backend/project/set_active.py PROJECT_ID --active
    python backend/project/set_active.py PROJECT_ID --inactive
    python backend/project/set_active.py PROJECT_ID --active --json

Options:
    PROJECT_ID      プロジェクトID（例: AI_PM_PJ）
    --active        プロジェクトをアクティブ状態（is_active=1）にする
    --inactive      プロジェクトを非アクティブ状態（is_active=0）にする
    --json          JSON形式で出力

Example:
    python backend/project/set_active.py AI_PM_PJ --active
    python backend/project/set_active.py Old_Project --inactive --json
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

from utils.db import (
    get_connection, fetch_one, execute_query, transaction, DatabaseError
)
from utils.validation import (
    validate_project_name, validate_project_exists, ValidationError
)


def get_project_info(conn, project_id: str) -> Optional[Dict[str, Any]]:
    """
    プロジェクト情報を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        プロジェクト情報の辞書、存在しなければNone
    """
    row = fetch_one(
        conn,
        """
        SELECT id, name, path, status, is_active, current_order_id,
               created_at, updated_at
        FROM projects
        WHERE id = ?
        """,
        (project_id,)
    )
    return dict(row) if row else None


def set_project_active(
    project_id: str,
    is_active: bool,
) -> Dict[str, Any]:
    """
    プロジェクトのアクティブ状態を設定

    Args:
        project_id: プロジェクトID
        is_active: アクティブ状態（True=アクティブ、False=非アクティブ）

    Returns:
        更新後のプロジェクト情報

    Raises:
        ValidationError: プロジェクトが存在しない場合
        DatabaseError: DB操作エラー
    """
    # プロジェクト名の形式検証
    validate_project_name(project_id)

    conn = get_connection()
    try:
        # プロジェクト存在確認
        validate_project_exists(conn, project_id)

        # 現在の状態を取得
        before_info = get_project_info(conn, project_id)
        before_is_active = before_info.get("is_active", 1)

        # 状態に変更がない場合
        if before_is_active == (1 if is_active else 0):
            return {
                "success": True,
                "project_id": project_id,
                "is_active": is_active,
                "changed": False,
                "message": f"プロジェクト {project_id} は既に{'アクティブ' if is_active else '非アクティブ'}状態です",
                "project": before_info,
            }

        # アクティブ状態を更新
        with transaction(conn) as tx_conn:
            execute_query(
                tx_conn,
                """
                UPDATE projects
                SET is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (1 if is_active else 0, datetime.now().isoformat(), project_id)
            )

        # 更新後の情報を取得
        after_info = get_project_info(conn, project_id)

        return {
            "success": True,
            "project_id": project_id,
            "is_active": is_active,
            "changed": True,
            "message": f"プロジェクト {project_id} を{'アクティブ' if is_active else '非アクティブ'}に変更しました",
            "project": after_info,
        }

    finally:
        conn.close()


def format_result(result: Dict[str, Any]) -> str:
    """
    結果を人間可読な形式でフォーマット

    Args:
        result: 操作結果

    Returns:
        フォーマットされた文字列
    """
    lines = []

    if result["success"]:
        if result["changed"]:
            lines.append(f"[OK] {result['message']}")
        else:
            lines.append(f"[INFO] {result['message']}")

        project = result.get("project", {})
        if project:
            lines.append("")
            lines.append("プロジェクト情報:")
            lines.append(f"  ID: {project.get('id', '-')}")
            lines.append(f"  名前: {project.get('name', '-')}")
            lines.append(f"  ステータス: {project.get('status', '-')}")
            lines.append(f"  アクティブ: {'はい' if project.get('is_active', 1) else 'いいえ'}")
            lines.append(f"  更新日時: {project.get('updated_at', '-')}")
    else:
        lines.append(f"[ERROR] {result.get('message', '不明なエラー')}")

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
        description="プロジェクトのアクティブ/非アクティブ状態を切り替え",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: AI_PM_PJ）"
    )

    # 排他グループ（--active / --inactive）
    state_group = parser.add_mutually_exclusive_group(required=True)
    state_group.add_argument(
        "--active",
        action="store_true",
        help="プロジェクトをアクティブにする"
    )
    state_group.add_argument(
        "--inactive",
        action="store_true",
        help="プロジェクトを非アクティブにする"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    try:
        # アクティブ状態を設定
        result = set_project_active(
            project_id=args.project_id,
            is_active=args.active,
        )

        # 出力
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(format_result(result))

    except ValidationError as e:
        error_result = {
            "success": False,
            "project_id": args.project_id,
            "message": str(e),
            "error_type": "ValidationError",
        }
        if args.json:
            print(json.dumps(error_result, ensure_ascii=False, indent=2))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    except DatabaseError as e:
        error_result = {
            "success": False,
            "project_id": args.project_id,
            "message": str(e),
            "error_type": "DatabaseError",
        }
        if args.json:
            print(json.dumps(error_result, ensure_ascii=False, indent=2))
        else:
            print(f"DBエラー: {e}", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        error_result = {
            "success": False,
            "project_id": args.project_id,
            "message": str(e),
            "error_type": type(e).__name__,
        }
        if args.json:
            print(json.dumps(error_result, ensure_ascii=False, indent=2))
        else:
            print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
