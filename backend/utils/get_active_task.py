#!/usr/bin/env python3
"""
AI PM Framework - 実行中タスク情報取得スクリプト

DBから実行中（status='IN_PROGRESS'）のタスクを検索し、
対応するログファイルパスを解決する機能を実装。
Worker/PM/Reviewの各種別に対応。

Usage:
    python backend/utils/get_active_task.py [options]

Options:
    --project PROJECT_ID    プロジェクトID（指定時はそのプロジェクトのみ検索）
    --task-id TASK_ID       タスクID（指定時はそのタスクの情報を取得）
    --json                  JSON形式で出力
    --all                   全ての実行中タスクを表示（デフォルトは最新1件）

Example:
    python backend/utils/get_active_task.py
    python backend/utils/get_active_task.py --project ai_pm_manager
    python backend/utils/get_active_task.py --task-id TASK_756 --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# aipm-db は Python パッケージ名として使えないためモジュール直接参照
try:
    # パッケージとしてインストールされている場合
    from aipm_db.utils.db import (
        get_connection, fetch_one, fetch_all, row_to_dict, DatabaseError
    )
    from aipm_db.utils.validation import ValidationError
except ImportError:
    # 直接実行の場合
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from utils.db import (
        get_connection, fetch_one, fetch_all, row_to_dict, DatabaseError
    )
    from utils.validation import ValidationError


def get_ai_pm_root() -> Path:
    """AI_PM_ROOT パスを取得"""
    # backend/utils から2階層上がルート
    return Path(__file__).resolve().parent.parent.parent


def resolve_log_path(
    task_id: str,
    project_id: str,
    order_id: str,
    phase: Optional[str] = None,
) -> Optional[Path]:
    """
    タスクに対応するログファイルパスを解決

    Args:
        task_id: タスクID
        project_id: プロジェクトID
        order_id: ORDER ID
        phase: 実行フェーズ（Worker/PM/Review）

    Returns:
        Optional[Path]: ログファイルパス（存在しない場合はNone）

    Note:
        ログファイル命名規則:
        - ORDER配下: PROJECTS/{PROJECT_ID}/RESULT/{ORDER_ID}/LOGS/execution_*.log
        - プロジェクト共通: logs/aipm_auto/{PROJECT_ID}/execution_*.log

        実際のログファイルは execution_{timestamp}.log の形式で保存される
    """
    root = get_ai_pm_root()

    # 探索対象のログディレクトリ（優先順位順）
    log_dirs = [
        # ORDER配下のLOGSディレクトリ（優先）
        root / "PROJECTS" / project_id / "RESULT" / order_id / "LOGS",
        # プロジェクト共通のログディレクトリ
        root / "logs" / "aipm_auto" / project_id,
    ]

    # 各ディレクトリで execution_*.log を探索（最新のものを返す）
    for log_dir in log_dirs:
        if not log_dir.exists():
            continue

        # execution_*.log の中から最新を探す
        execution_logs = sorted(
            log_dir.glob("execution_*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if execution_logs:
            return execution_logs[0]

    return None


def get_active_tasks(
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
    limit: int = 1,
) -> List[Dict[str, Any]]:
    """
    実行中タスクを取得

    Args:
        project_id: プロジェクトID（指定時はそのプロジェクトのみ）
        task_id: タスクID（指定時はそのタスクのみ）
        limit: 取得件数（0=全件）

    Returns:
        List[Dict[str, Any]]: タスク情報のリスト

    Raises:
        DatabaseError: DB操作エラー
    """
    with get_connection() as conn:
        # クエリ構築
        if task_id:
            # 特定タスクを取得（status問わず）
            query = """
                SELECT * FROM tasks
                WHERE id = ?
            """
            params = [task_id]
            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)

            result = fetch_one(conn, query, tuple(params))
            if not result:
                return []
            return [row_to_dict(result)]

        # 実行中タスクを取得
        query = """
            SELECT * FROM tasks
            WHERE status = 'IN_PROGRESS'
        """
        params = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY started_at DESC"

        if limit > 0:
            query += f" LIMIT {limit}"

        results = fetch_all(conn, query, tuple(params) if params else None)
        return [row_to_dict(row) for row in results]


def get_active_task_info(
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
    all_tasks: bool = False,
) -> List[Dict[str, Any]]:
    """
    実行中タスク情報とログパスを取得

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        all_tasks: 全タスクを取得（デフォルト: 最新1件のみ）

    Returns:
        List[Dict[str, Any]]: タスク情報（log_pathフィールド追加）
    """
    limit = 0 if all_tasks else 1
    tasks = get_active_tasks(project_id, task_id, limit)

    # ログパス解決
    for task in tasks:
        log_path = resolve_log_path(
            task["id"],
            task["project_id"],
            task["order_id"],
            task.get("phase"),
        )
        task["log_path"] = str(log_path) if log_path else None
        task["log_exists"] = log_path.exists() if log_path else False

    return tasks


def format_task_info(task: Dict[str, Any], verbose: bool = False) -> str:
    """
    タスク情報を整形して出力用文字列に変換

    Args:
        task: タスク情報
        verbose: 詳細表示

    Returns:
        str: 整形された文字列
    """
    lines = []
    lines.append(f"タスクID: {task['id']}")
    lines.append(f"  プロジェクト: {task['project_id']}")
    lines.append(f"  ORDER: {task['order_id']}")
    lines.append(f"  タイトル: {task['title']}")
    lines.append(f"  ステータス: {task['status']}")

    if task.get("phase"):
        lines.append(f"  フェーズ: {task['phase']}")

    if task.get("started_at"):
        lines.append(f"  開始時刻: {task['started_at']}")

    if task.get("log_path"):
        lines.append(f"  ログファイル: {task['log_path']}")
        lines.append(f"  ログ存在: {'Yes' if task.get('log_exists') else 'No'}")
    else:
        lines.append(f"  ログファイル: (見つかりません)")

    if verbose:
        lines.append(f"  優先度: {task.get('priority', 'N/A')}")
        lines.append(f"  担当: {task.get('assignee', 'N/A')}")
        if task.get("description"):
            lines.append(f"  説明: {task['description']}")

    return "\n".join(lines)


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
        description="実行中タスクの情報を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--project",
        help="プロジェクトID（指定時はそのプロジェクトのみ検索）"
    )
    parser.add_argument(
        "--task-id",
        help="タスクID（指定時はそのタスクの情報を取得）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="全ての実行中タスクを表示（デフォルトは最新1件）"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="詳細情報を表示"
    )

    args = parser.parse_args()

    try:
        tasks = get_active_task_info(
            project_id=args.project,
            task_id=args.task_id,
            all_tasks=args.all,
        )

        if not tasks:
            if args.task_id:
                print(f"タスクが見つかりません: {args.task_id}", file=sys.stderr)
            else:
                print("実行中のタスクはありません", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(tasks, ensure_ascii=False, indent=2, default=str))
        else:
            for i, task in enumerate(tasks):
                if i > 0:
                    print()
                    print("-" * 60)
                    print()
                print(format_task_info(task, verbose=args.verbose))

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
