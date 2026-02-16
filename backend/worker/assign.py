#!/usr/bin/env python3
"""
AI PM Framework - Worker識別子割当スクリプト

Usage:
    python backend/worker/assign.py PROJECT_NAME [options]

Options:
    --json          JSON形式で出力（デフォルト）
    --table         テーブル形式で出力
    --used-only     使用中Workerのみ表示

Example:
    python backend/worker/assign.py AI_PM_PJ
    python backend/worker/assign.py AI_PM_PJ --used-only --table
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Set

# aipm-db は Python パッケージ名として使えないためモジュール直接参照
try:
    from aipm_db.utils.db import (
        get_connection, fetch_all, DatabaseError
    )
    from aipm_db.utils.validation import (
        validate_project_name, ValidationError
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from utils.db import (
        get_connection, fetch_all, DatabaseError
    )
    from utils.validation import (
        validate_project_name, ValidationError
    )


# Worker識別子パターン（Worker A〜Worker Z）
WORKER_IDS = [f"Worker {chr(65 + i)}" for i in range(26)]  # Worker A〜Worker Z


class WorkerAssignmentError(Exception):
    """Worker割当エラー"""
    pass


def get_used_workers_from_db(project_id: str) -> Set[str]:
    """
    DBからIN_PROGRESSタスクの担当Workerを取得

    Args:
        project_id: プロジェクトID

    Returns:
        使用中Worker識別子のセット

    Raises:
        DatabaseError: DB操作エラー
    """
    conn = get_connection()
    try:
        # 複合キー対応: tasksテーブルから直接project_idを参照
        rows = fetch_all(
            conn,
            """
            SELECT DISTINCT t.assignee
            FROM tasks t
            WHERE t.project_id = ?
              AND t.status = 'IN_PROGRESS'
              AND t.assignee IS NOT NULL
              AND t.assignee != ''
              AND t.assignee != '-'
            """,
            (project_id,)
        )
        return {row["assignee"] for row in rows if row["assignee"]}
    finally:
        conn.close()


def get_used_workers(project_id: str) -> Set[str]:
    """
    使用中Worker識別子を取得

    Args:
        project_id: プロジェクトID

    Returns:
        使用中Worker識別子のセット

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    validate_project_name(project_id)
    return get_used_workers_from_db(project_id)


def get_next_worker(project_id: str) -> str:
    """
    次の利用可能なWorker識別子を返す

    Args:
        project_id: プロジェクトID

    Returns:
        次の利用可能なWorker識別子（例: "Worker A"）

    Raises:
        ValidationError: 入力検証エラー
        WorkerAssignmentError: 全Workerが使用中の場合
    """
    used_workers = get_used_workers(project_id)

    for worker_id in WORKER_IDS:
        if worker_id not in used_workers:
            return worker_id

    raise WorkerAssignmentError("All workers are in use (Worker A〜Z)")


def get_worker_status(project_id: str) -> Dict[str, Any]:
    """
    Worker割当状況を取得

    Args:
        project_id: プロジェクトID

    Returns:
        Worker状況の辞書
    """
    used_workers = get_used_workers(project_id)
    available_workers = [w for w in WORKER_IDS if w not in used_workers]

    try:
        next_worker = get_next_worker(project_id)
    except WorkerAssignmentError:
        next_worker = None

    return {
        "project_id": project_id,
        "used_workers": sorted(list(used_workers)),
        "used_count": len(used_workers),
        "available_workers": available_workers,
        "available_count": len(available_workers),
        "next_worker": next_worker,
        "max_workers": len(WORKER_IDS),
    }


def format_table(status: Dict[str, Any]) -> str:
    """
    Worker状況をテーブル形式でフォーマット
    """
    lines = [
        f"【Worker割当状況】プロジェクト: {status['project_id']}",
        "",
        f"使用中: {status['used_count']} / {status['max_workers']}",
        "",
    ]

    if status["used_workers"]:
        lines.append("使用中Worker:")
        for w in status["used_workers"]:
            lines.append(f"  - {w}")
        lines.append("")

    if status["next_worker"]:
        lines.append(f"次の割当: {status['next_worker']}")
    else:
        lines.append("次の割当: なし（全Worker使用中）")

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
        description="Worker識別子を割り当て",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--table", action="store_true", help="テーブル形式で出力")
    parser.add_argument("--used-only", action="store_true", help="使用中Workerのみ表示")
    parser.add_argument("--next", action="store_true", help="次のWorker識別子のみ表示")

    args = parser.parse_args()

    try:
        if args.next:
            # 次のWorker識別子のみ出力
            next_worker = get_next_worker(args.project_id)
            print(next_worker)
        elif args.used_only:
            # 使用中Workerのみ出力
            used_workers = get_used_workers(args.project_id)
            if args.json or (not args.table):
                print(json.dumps(sorted(list(used_workers)), ensure_ascii=False))
            else:
                if used_workers:
                    for w in sorted(used_workers):
                        print(w)
                else:
                    print("使用中Workerなし")
        else:
            # 全状況を出力
            status = get_worker_status(args.project_id)
            if args.table:
                print(format_table(status))
            else:
                # デフォルトはJSON
                print(json.dumps(status, ensure_ascii=False, indent=2))

    except (ValidationError, WorkerAssignmentError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
