#!/usr/bin/env python3
"""
AI PM Framework - Bug Pattern更新スクリプト

Usage:
    python -m bugs.update BUG_ID [options]

Options:
    --status         ステータス更新（ACTIVE/FIXED/ARCHIVED）
    --severity       深刻度更新（Critical/High/Medium/Low）
    --solution       解決方法を追加/更新
    --increment-count 発生回数をインクリメント
    --title          タイトル更新
    --description    説明更新
    --pattern-type   パターン分類更新
    --json           JSON形式で出力

Example:
    # ステータスをFIXEDに更新
    python -m bugs.update BUG_001 --status FIXED --solution "○○を修正することで解決"

    # 発生回数をインクリメント
    python -m bugs.update BUG_002 --increment-count

    # バグパターンをアーカイブ
    python -m bugs.update BUG_003 --status ARCHIVED
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List

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

# 深刻度定義
VALID_SEVERITIES = ["Critical", "High", "Medium", "Low"]

# ステータス定義
VALID_STATUSES = ["ACTIVE", "FIXED", "ARCHIVED"]


@dataclass
class UpdateBugResult:
    """バグ更新結果"""
    success: bool
    bug_id: str = ""
    updated_fields: List[str] = None
    message: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if self.updated_fields is None:
            self.updated_fields = []


def update_bug(
    bug_id: str,
    *,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    solution: Optional[str] = None,
    increment_count: bool = False,
    title: Optional[str] = None,
    description: Optional[str] = None,
    pattern_type: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> UpdateBugResult:
    """
    バグパターンを更新

    Args:
        bug_id: BUG ID
        status: ステータス更新
        severity: 深刻度更新
        solution: 解決方法
        increment_count: 発生回数をインクリメント
        title: タイトル更新
        description: 説明更新
        pattern_type: パターン分類更新
        db_path: データベースパス（テスト用）

    Returns:
        UpdateBugResult: 更新結果
    """
    try:
        # 入力検証
        if status and status not in VALID_STATUSES:
            return UpdateBugResult(
                success=False,
                error=f"無効なステータス: {status}\n有効なステータス: {', '.join(VALID_STATUSES)}"
            )

        if severity and severity not in VALID_SEVERITIES:
            return UpdateBugResult(
                success=False,
                error=f"無効な深刻度: {severity}\n有効な深刻度: {', '.join(VALID_SEVERITIES)}"
            )

        with transaction(db_path=db_path) as conn:
            # 1. バグ存在確認
            bug = fetch_one(conn, "SELECT * FROM bugs WHERE id = ?", (bug_id,))
            if not bug:
                return UpdateBugResult(
                    success=False,
                    error=f"バグが見つかりません: {bug_id}"
                )

            # 2. 更新フィールドを構築
            updates = []
            params = []
            updated_fields = []

            if status:
                updates.append("status = ?")
                params.append(status)
                updated_fields.append(f"status={status}")

            if severity:
                updates.append("severity = ?")
                params.append(severity)
                updated_fields.append(f"severity={severity}")

            if solution:
                updates.append("solution = ?")
                params.append(solution)
                updated_fields.append("solution")

            if title:
                updates.append("title = ?")
                params.append(title)
                updated_fields.append("title")

            if description:
                updates.append("description = ?")
                params.append(description)
                updated_fields.append("description")

            if pattern_type:
                updates.append("pattern_type = ?")
                params.append(pattern_type)
                updated_fields.append(f"pattern_type={pattern_type}")

            if increment_count:
                updates.append("occurrence_count = occurrence_count + 1")
                updates.append("last_occurred_at = ?")
                now = datetime.now().isoformat()
                params.append(now)
                updated_fields.append("occurrence_count+1")

            # updated_atは常に更新
            updates.append("updated_at = ?")
            now = datetime.now().isoformat()
            params.append(now)

            if not updated_fields:
                return UpdateBugResult(
                    success=False,
                    error="更新するフィールドが指定されていません"
                )

            # 3. UPDATE実行
            params.append(bug_id)
            query = f"""
                UPDATE bugs
                SET {', '.join(updates)}
                WHERE id = ?
            """

            execute_query(conn, query, tuple(params))

            result = UpdateBugResult(
                success=True,
                bug_id=bug_id,
                updated_fields=updated_fields,
                message=f"バグパターンを更新しました: {bug_id}"
            )

        return result

    except DatabaseError as e:
        return UpdateBugResult(
            success=False,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return UpdateBugResult(
            success=False,
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
        description="バグパターンを更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # ステータスをFIXEDに更新
  python update.py BUG_001 --status FIXED --solution "○○を修正することで解決"

  # 発生回数をインクリメント
  python update.py BUG_002 --increment-count

  # バグパターンをアーカイブ
  python update.py BUG_003 --status ARCHIVED
"""
    )

    parser.add_argument(
        "bug_id",
        help="BUG ID（例: BUG_001）"
    )
    parser.add_argument(
        "--status", "-s",
        choices=VALID_STATUSES,
        help="ステータス更新"
    )
    parser.add_argument(
        "--severity",
        choices=VALID_SEVERITIES,
        help="深刻度更新"
    )
    parser.add_argument(
        "--solution",
        help="解決方法を追加/更新"
    )
    parser.add_argument(
        "--increment-count", "-i",
        action="store_true",
        help="発生回数をインクリメント"
    )
    parser.add_argument(
        "--title", "-t",
        help="タイトル更新"
    )
    parser.add_argument(
        "--description", "-d",
        help="説明更新"
    )
    parser.add_argument(
        "--pattern-type",
        help="パターン分類更新"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    result = update_bug(
        bug_id=args.bug_id,
        status=args.status,
        severity=args.severity,
        solution=args.solution,
        increment_count=args.increment_count,
        title=args.title,
        description=args.description,
        pattern_type=args.pattern_type,
    )

    if args.json:
        output = {
            "success": result.success,
            "bug_id": result.bug_id,
            "updated_fields": result.updated_fields,
            "message": result.message,
            "error": result.error,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            print(f"  更新フィールド: {', '.join(result.updated_fields)}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
