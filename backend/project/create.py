#!/usr/bin/env python3
"""
AI PM Framework - プロジェクト作成スクリプト

Usage:
    python backend/project/create.py PROJECT_ID [options]

Arguments:
    PROJECT_ID          プロジェクトID（ディレクトリ名）

Options:
    --name              プロジェクト表示名（省略時はPROJECT_IDを使用）
    --path              プロジェクトパス（省略時は PROJECTS/PROJECT_ID）
    --status            初期ステータス（デフォルト: INITIAL）
    --json              JSON形式で出力

Example:
    python backend/project/create.py AI_manager_PJ --name "AI_manager システム開発"
    python backend/project/create.py My_Project --json
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


# プロジェクトステータスの有効値
VALID_PROJECT_STATUSES = (
    'INITIAL', 'PLANNING', 'IN_PROGRESS', 'REVIEW', 'REWORK',
    'ESCALATED', 'ESCALATION_RESOLVED', 'COMPLETED', 'ON_HOLD',
    'CANCELLED', 'INTERRUPTED'
)


def validate_project_id(project_id: str) -> None:
    """プロジェクトIDを検証"""
    if not project_id:
        raise ValidationError("プロジェクトIDは必須です")

    # 無効な文字のチェック
    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', ' ']
    for char in invalid_chars:
        if char in project_id:
            raise ValidationError(
                f"プロジェクトIDに無効な文字が含まれています: '{char}'. "
                f"使用できない文字: {' '.join(repr(c) for c in invalid_chars)}"
            )


def validate_project_status(status: str) -> None:
    """プロジェクトステータスを検証"""
    if status not in VALID_PROJECT_STATUSES:
        raise ValidationError(
            f"無効なプロジェクトステータス: {status}. "
            f"有効な値: {', '.join(VALID_PROJECT_STATUSES)}"
        )


def project_exists(project_id: str) -> bool:
    """
    プロジェクトがDBに存在するか確認

    Args:
        project_id: プロジェクトID

    Returns:
        存在する場合True
    """
    conn = get_connection()
    try:
        result = fetch_one(
            conn,
            "SELECT id FROM projects WHERE id = ?",
            (project_id,)
        )
        return result is not None
    finally:
        conn.close()


def create_project(
    project_id: str,
    *,
    name: Optional[str] = None,
    path: Optional[str] = None,
    status: str = "INITIAL",
    is_active: bool = True,
) -> Dict[str, Any]:
    """
    プロジェクトをDBに作成

    Args:
        project_id: プロジェクトID（必須）
        name: プロジェクト表示名（省略時はproject_idを使用）
        path: プロジェクトパス（省略時は PROJECTS/project_id）
        status: 初期ステータス（デフォルト: INITIAL）
        is_active: アクティブフラグ（デフォルト: True）

    Returns:
        作成されたプロジェクト情報

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー（重複など）
    """
    # バリデーション
    validate_project_id(project_id)
    validate_project_status(status)

    # デフォルト値の設定
    if name is None:
        name = project_id
    if path is None:
        path = f"PROJECTS/{project_id}"

    # 重複チェック
    if project_exists(project_id):
        raise ValidationError(f"プロジェクト '{project_id}' は既に存在します")

    now = datetime.now().isoformat()

    conn = get_connection()
    try:
        # プロジェクト作成
        execute_query(
            conn,
            """
            INSERT INTO projects (id, name, path, status, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, name, path, status, 1 if is_active else 0, now, now)
        )
        conn.commit()

        # 作成したプロジェクトを取得して返す
        result = fetch_one(
            conn,
            """
            SELECT id, name, path, status, current_order_id, is_active, created_at, updated_at
            FROM projects WHERE id = ?
            """,
            (project_id,)
        )

        if result:
            return dict(result)
        else:
            raise DatabaseError("プロジェクトの作成に失敗しました")

    except Exception as e:
        conn.rollback()
        if "UNIQUE constraint failed" in str(e):
            raise ValidationError(f"プロジェクト '{project_id}' は既に存在します")
        raise DatabaseError(f"プロジェクト作成エラー: {e}")
    finally:
        conn.close()


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="プロジェクトをDBに作成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID（ディレクトリ名）")
    parser.add_argument("--name", help="プロジェクト表示名（省略時はproject_idを使用）")
    parser.add_argument("--path", help="プロジェクトパス（省略時は PROJECTS/PROJECT_ID）")
    parser.add_argument("--status", default="INITIAL",
                        help="初期ステータス（デフォルト: INITIAL）")
    parser.add_argument("--inactive", action="store_true",
                        help="非アクティブとして作成")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        project = create_project(
            args.project_id,
            name=args.name,
            path=args.path,
            status=args.status,
            is_active=not args.inactive,
        )

        if args.json:
            print(json.dumps(project, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"プロジェクト '{args.project_id}' を作成しました。")
            print(f"  ID: {project['id']}")
            print(f"  名前: {project['name']}")
            print(f"  パス: {project['path']}")
            print(f"  ステータス: {project['status']}")
            print(f"  アクティブ: {'Yes' if project.get('is_active') else 'No'}")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
