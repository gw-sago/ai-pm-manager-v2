#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG追加スクリプト

Usage:
    python backend/backlog/add.py PROJECT_NAME --title "タイトル" [options]

Options:
    --title         タイトル（必須）
    --description   説明（詳細）
    --category      カテゴリ（機能追加/改善/バグ修正/ドキュメント等）
    --priority      優先度（High/Medium/Low、デフォルト: Medium）
    --backlog-id    BACKLOG ID指定（省略時は自動採番）
    --render        （廃止: 後方互換性のため引数のみ残存）
    --json          JSON形式で出力

Example:
    python backend/backlog/add.py AI_PM_PJ --title "新機能追加"
    python backend/backlog/add.py AI_PM_PJ --title "バグ修正" --priority High --category バグ修正
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
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
    validate_backlog_id,
    validate_status,
    project_exists,
    backlog_exists,
    ValidationError,
)
from utils.transition import (
    validate_transition,
    record_transition,
    TransitionError,
)


# カテゴリ定義
VALID_CATEGORIES = [
    "機能追加",
    "改善",
    "バグ修正",
    "ドキュメント",
    "リファクタリング",
    "調査",
    "その他",
]

# 優先度定義
VALID_PRIORITIES = ["High", "Medium", "Low"]


@dataclass
class AddBacklogResult:
    """BACKLOG追加結果"""
    success: bool
    backlog_id: str = ""
    title: str = ""
    priority: str = "Medium"
    category: str = ""
    message: str = ""
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def get_next_backlog_number(conn, project_id: str) -> str:
    """
    次のBACKLOG番号を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        次のBACKLOG ID（例: BACKLOG_032）
    """
    row = fetch_one(
        conn,
        """
        SELECT MAX(CAST(SUBSTR(id, 9) AS INTEGER)) as max_num
        FROM backlog_items
        WHERE project_id = ?
        """,
        (project_id,)
    )

    max_num = row["max_num"] if row and row["max_num"] else 0
    next_num = max_num + 1

    return f"BACKLOG_{next_num:03d}"


def get_next_sort_order(conn, project_id: str, priority: str) -> int:
    """
    優先度ごとの次のsort_orderを取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID
        priority: 優先度（High/Medium/Low）

    Returns:
        次のsort_order値（現在の最大値+1）
    """
    row = fetch_one(
        conn,
        """
        SELECT MAX(sort_order) as max_order
        FROM backlog_items
        WHERE project_id = ? AND priority = ?
        """,
        (project_id, priority)
    )

    max_order = row["max_order"] if row and row["max_order"] else 0
    return max_order + 1


def add_backlog(
    project_name: str,
    title: str,
    *,
    description: Optional[str] = None,
    category: Optional[str] = None,
    priority: str = "Medium",
    backlog_id: Optional[str] = None,
    render: bool = True,
    db_path: Optional[Path] = None,
) -> AddBacklogResult:
    """
    BACKLOGを追加

    Args:
        project_name: プロジェクト名
        title: タイトル
        description: 説明（詳細）
        category: カテゴリ
        priority: 優先度（High/Medium/Low）
        backlog_id: BACKLOG ID（省略時は自動採番）
        render: （廃止: 後方互換性のため引数のみ残存）
        db_path: データベースパス（テスト用）

    Returns:
        AddBacklogResult: 追加結果

    Workflow:
        1. 入力検証（プロジェクト存在確認、優先度チェック）
        2. BACKLOG ID自動採番
        3. 優先度に応じたsort_order自動設定（同一優先度内での最大値+1）
        4. DB INSERT処理
        5. 変更履歴を記録
        6. （廃止: BACKLOG.md生成は実行されなくなりました）
    """
    try:
        # 入力検証
        validate_project_name(project_name)

        if priority not in VALID_PRIORITIES:
            return AddBacklogResult(
                success=False,
                error=f"無効な優先度: {priority}\n有効な優先度: {', '.join(VALID_PRIORITIES)}"
            )

        if category and category not in VALID_CATEGORIES:
            # カテゴリは緩く検証（警告のみ）
            pass

        with transaction(db_path=db_path) as conn:
            # 1. プロジェクト存在確認
            if not project_exists(conn, project_name):
                return AddBacklogResult(
                    success=False,
                    error=f"プロジェクトが見つかりません: {project_name}"
                )

            # 2. BACKLOG ID決定（指定がなければ自動採番）
            if backlog_id:
                validate_backlog_id(backlog_id)
                if backlog_exists(conn, backlog_id, project_name):
                    return AddBacklogResult(
                        success=False,
                        error=f"BACKLOG IDが既に存在します: {backlog_id}"
                    )
            else:
                backlog_id = get_next_backlog_number(conn, project_name)

            # 3. 状態遷移検証（新規作成: NULL → TODO）
            validate_transition(conn, "backlog", None, "TODO", "PM")

            # 4. 説明文にカテゴリを含める
            full_description = description or ""
            if category:
                full_description = f"カテゴリ: {category}\n\n{full_description}" if full_description else f"カテゴリ: {category}"

            # 5. 優先度に応じたsort_orderを自動設定
            sort_order = get_next_sort_order(conn, project_name, priority)

            # 6. DB INSERT
            now = datetime.now().isoformat()
            execute_query(
                conn,
                """
                INSERT INTO backlog_items (
                    id, project_id, title, description, priority, status,
                    sort_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'TODO', ?, ?, ?)
                """,
                (
                    backlog_id, project_name, title, full_description, priority,
                    sort_order, now, now
                )
            )

            # 7. 変更履歴を記録
            record_transition(
                conn,
                "backlog",
                backlog_id,
                None,
                "TODO",
                "PM",
                f"BACKLOG作成: {title}"
            )

            warnings_list: List[str] = []
            result = AddBacklogResult(
                success=True,
                backlog_id=backlog_id,
                title=title,
                priority=priority,
                category=category or "",
                message=f"BACKLOGを作成しました: {backlog_id}",
                warnings=warnings_list
            )

        # 8. render引数は後方互換性のため残すが、処理は実行しない
        # （BACKLOG.md廃止: ORDER_090）

        return result

    except ValidationError as e:
        return AddBacklogResult(
            success=False,
            error=f"入力検証エラー: {e}"
        )
    except TransitionError as e:
        return AddBacklogResult(
            success=False,
            error=f"状態遷移エラー: {e}"
        )
    except DatabaseError as e:
        return AddBacklogResult(
            success=False,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return AddBacklogResult(
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
        description="BACKLOGを追加",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 基本的な追加
  python add.py AI_PM_PJ --title "新機能追加"

  # カテゴリ・優先度を指定
  python add.py AI_PM_PJ --title "バグ修正" --priority High --category バグ修正

  # 説明付きで追加
  python add.py AI_PM_PJ --title "リファクタリング" --description "コードの整理と最適化"

カテゴリ一覧:
  機能追加, 改善, バグ修正, ドキュメント, リファクタリング, 調査, その他

優先度:
  High, Medium（デフォルト）, Low
"""
    )

    parser.add_argument(
        "project_name",
        help="プロジェクト名 (例: AI_PM_PJ)"
    )
    parser.add_argument(
        "--title", "-t",
        required=True,
        help="BACKLOGタイトル"
    )
    parser.add_argument(
        "--description", "-d",
        help="説明（詳細）"
    )
    parser.add_argument(
        "--category", "-c",
        choices=VALID_CATEGORIES,
        help="カテゴリ"
    )
    parser.add_argument(
        "--priority", "-p",
        choices=VALID_PRIORITIES,
        default="Medium",
        help="優先度（デフォルト: Medium）"
    )
    parser.add_argument(
        "--backlog-id",
        help="BACKLOG ID（省略時は自動採番）"
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

    result = add_backlog(
        project_name=args.project_name,
        title=args.title,
        description=args.description,
        category=args.category,
        priority=args.priority,
        backlog_id=args.backlog_id,
        render=not args.no_render,
    )

    if args.json:
        output = {
            "success": result.success,
            "backlog_id": result.backlog_id,
            "title": result.title,
            "priority": result.priority,
            "category": result.category,
            "message": result.message,
            "error": result.error,
            "warnings": result.warnings,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            print(f"  ID: {result.backlog_id}")
            print(f"  タイトル: {result.title}")
            print(f"  優先度: {result.priority}")
            if result.category:
                print(f"  カテゴリ: {result.category}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
