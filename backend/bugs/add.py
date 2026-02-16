#!/usr/bin/env python3
"""
AI PM Framework - Bug Pattern追加スクリプト

Usage:
    python -m bugs.add --title "タイトル" --description "説明" [options]

Options:
    --title         バグタイトル（必須）
    --description   バグの詳細説明（必須）
    --project-id    プロジェクトID（省略時はNULL=汎用パターン）
    --pattern-type  パターン分類（例: default_override, module_conflict）
    --severity      深刻度（Critical/High/Medium/Low、デフォルト: Medium）
    --solution      解決方法・回避策
    --related-files 関連ファイルパス（カンマ区切り）
    --tags          タグ（カンマ区切り）
    --bug-id        BUG ID指定（省略時は自動採番）
    --json          JSON形式で出力

Example:
    # 汎用バグパターン登録
    python -m bugs.add --title "デフォルト値上書きバグ" --description "..." --pattern-type default_override

    # プロジェクト固有バグ登録
    python -m bugs.add --project-id ai_pm_manager --title "..." --description "..." --severity High
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
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
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    project_exists,
    ValidationError,
)

# 深刻度定義
VALID_SEVERITIES = ["Critical", "High", "Medium", "Low"]

# ステータス定義
VALID_STATUSES = ["ACTIVE", "FIXED", "ARCHIVED"]


@dataclass
class AddBugResult:
    """バグ追加結果"""
    success: bool
    bug_id: str = ""
    title: str = ""
    severity: str = "Medium"
    pattern_type: str = ""
    message: str = ""
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def get_next_bug_number(conn) -> str:
    """
    次のBUG番号を取得

    Args:
        conn: データベース接続

    Returns:
        次のBUG ID（例: BUG_001）
    """
    row = fetch_one(
        conn,
        """
        SELECT MAX(CAST(SUBSTR(id, 5) AS INTEGER)) as max_num
        FROM bugs
        """
    )

    max_num = row["max_num"] if row and row["max_num"] else 0
    next_num = max_num + 1

    return f"BUG_{next_num:03d}"


def add_bug(
    title: str,
    description: str,
    *,
    project_id: Optional[str] = None,
    pattern_type: Optional[str] = None,
    severity: str = "Medium",
    solution: Optional[str] = None,
    related_files: Optional[str] = None,
    tags: Optional[str] = None,
    bug_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> AddBugResult:
    """
    バグパターンを追加

    Args:
        title: バグタイトル
        description: バグの詳細説明
        project_id: プロジェクトID（NULLの場合は汎用パターン）
        pattern_type: パターン分類
        severity: 深刻度（Critical/High/Medium/Low）
        solution: 解決方法・回避策
        related_files: 関連ファイルパス（カンマ区切り）
        tags: タグ（カンマ区切り）
        bug_id: BUG ID（省略時は自動採番）
        db_path: データベースパス（テスト用）

    Returns:
        AddBugResult: 追加結果
    """
    try:
        # 入力検証
        if not title or not description:
            return AddBugResult(
                success=False,
                error="タイトルと説明は必須です"
            )

        if severity not in VALID_SEVERITIES:
            return AddBugResult(
                success=False,
                error=f"無効な深刻度: {severity}\n有効な深刻度: {', '.join(VALID_SEVERITIES)}"
            )

        with transaction(db_path=db_path) as conn:
            # 1. プロジェクトID指定時は存在確認
            if project_id:
                validate_project_name(project_id)
                if not project_exists(conn, project_id):
                    return AddBugResult(
                        success=False,
                        error=f"プロジェクトが見つかりません: {project_id}"
                    )

            # 2. BUG ID決定（指定がなければ自動採番）
            if not bug_id:
                bug_id = get_next_bug_number(conn)
            else:
                # BUG ID重複チェック
                existing = fetch_one(conn, "SELECT id FROM bugs WHERE id = ?", (bug_id,))
                if existing:
                    return AddBugResult(
                        success=False,
                        error=f"BUG IDが既に存在します: {bug_id}"
                    )

            # 3. DB INSERT
            now = datetime.now().isoformat()
            execute_query(
                conn,
                """
                INSERT INTO bugs (
                    id, project_id, title, description, pattern_type,
                    severity, status, solution, related_files, tags,
                    occurrence_count, last_occurred_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    bug_id, project_id, title, description, pattern_type,
                    severity, solution, related_files, tags,
                    now, now, now
                )
            )

            scope_label = f"プロジェクト固有({project_id})" if project_id else "汎用パターン"
            result = AddBugResult(
                success=True,
                bug_id=bug_id,
                title=title,
                severity=severity,
                pattern_type=pattern_type or "",
                message=f"バグパターンを登録しました: {bug_id} [{scope_label}]",
            )

        return result

    except ValidationError as e:
        return AddBugResult(
            success=False,
            error=f"入力検証エラー: {e}"
        )
    except DatabaseError as e:
        return AddBugResult(
            success=False,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return AddBugResult(
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
        description="バグパターンを追加",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 汎用バグパターン登録
  python add.py --title "デフォルト値上書きバグ" --description "..." --pattern-type default_override

  # プロジェクト固有バグ登録
  python add.py --project-id ai_pm_manager --title "..." --description "..." --severity High

深刻度:
  Critical, High, Medium（デフォルト）, Low
"""
    )

    parser.add_argument(
        "--title", "-t",
        required=True,
        help="バグタイトル"
    )
    parser.add_argument(
        "--description", "-d",
        required=True,
        help="バグの詳細説明"
    )
    parser.add_argument(
        "--project-id", "-p",
        help="プロジェクトID（省略時はNULL=汎用パターン）"
    )
    parser.add_argument(
        "--pattern-type",
        help="パターン分類（例: default_override, module_conflict）"
    )
    parser.add_argument(
        "--severity", "-s",
        choices=VALID_SEVERITIES,
        default="Medium",
        help="深刻度（デフォルト: Medium）"
    )
    parser.add_argument(
        "--solution",
        help="解決方法・回避策"
    )
    parser.add_argument(
        "--related-files",
        help="関連ファイルパス（カンマ区切り）"
    )
    parser.add_argument(
        "--tags",
        help="タグ（カンマ区切り）"
    )
    parser.add_argument(
        "--bug-id",
        help="BUG ID（省略時は自動採番）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    result = add_bug(
        title=args.title,
        description=args.description,
        project_id=args.project_id,
        pattern_type=args.pattern_type,
        severity=args.severity,
        solution=args.solution,
        related_files=args.related_files,
        tags=args.tags,
        bug_id=args.bug_id,
    )

    if args.json:
        output = {
            "success": result.success,
            "bug_id": result.bug_id,
            "title": result.title,
            "severity": result.severity,
            "pattern_type": result.pattern_type,
            "message": result.message,
            "error": result.error,
            "warnings": result.warnings,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            print(f"  ID: {result.bug_id}")
            print(f"  タイトル: {result.title}")
            print(f"  深刻度: {result.severity}")
            if result.pattern_type:
                print(f"  パターン分類: {result.pattern_type}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
