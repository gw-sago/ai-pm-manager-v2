#!/usr/bin/env python3
"""
AI PM Framework - バックログ自動提案スクリプト

プロジェクトの現状（タスク完了率・未対応バグ・ORDER進捗等）を分析し、
次に着手すべきバックログ項目を提案する。

Usage:
    python backend/backlog/suggest.py PROJECT_ID [--json]

Arguments:
    PROJECT_ID    プロジェクトID（例: ai_pm_manager_v2）

Options:
    --json        JSON形式で出力

Output:
    成功時:
        {"success": true, "suggestions": [{"title": "...", "description": "...", "priority": "...", "category": "...", "rationale": "..."}]}
    エラー時:
        {"success": false, "error": "..."}

Example:
    python backend/backlog/suggest.py ai_pm_manager_v2 --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    fetch_one,
    fetch_all,
    rows_to_dicts,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    project_exists,
    ValidationError,
)


def _get_project_stats(conn, project_id: str) -> Dict[str, Any]:
    """
    プロジェクトの統計情報を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        統計情報の辞書
    """
    stats: Dict[str, Any] = {}

    # タスク統計
    task_row = fetch_one(
        conn,
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress,
            SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) as rejected
        FROM tasks WHERE project_id = ?
        """,
        (project_id,)
    )
    if task_row:
        stats["task_total"] = task_row["total"] or 0
        stats["task_completed"] = task_row["completed"] or 0
        stats["task_in_progress"] = task_row["in_progress"] or 0
        stats["task_rejected"] = task_row["rejected"] or 0
    else:
        stats["task_total"] = 0
        stats["task_completed"] = 0
        stats["task_in_progress"] = 0
        stats["task_rejected"] = 0

    # ORDER統計
    order_row = fetch_one(
        conn,
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW') THEN 1 ELSE 0 END) as active
        FROM orders WHERE project_id = ?
        """,
        (project_id,)
    )
    if order_row:
        stats["order_total"] = order_row["total"] or 0
        stats["order_completed"] = order_row["completed"] or 0
        stats["order_active"] = order_row["active"] or 0
    else:
        stats["order_total"] = 0
        stats["order_completed"] = 0
        stats["order_active"] = 0

    # 既存バックログ統計
    backlog_row = fetch_one(
        conn,
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'TODO' THEN 1 ELSE 0 END) as todo,
            SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress,
            SUM(CASE WHEN status = 'DONE' THEN 1 ELSE 0 END) as done
        FROM backlog_items WHERE project_id = ?
        """,
        (project_id,)
    )
    if backlog_row:
        stats["backlog_total"] = backlog_row["total"] or 0
        stats["backlog_todo"] = backlog_row["todo"] or 0
        stats["backlog_in_progress"] = backlog_row["in_progress"] or 0
        stats["backlog_done"] = backlog_row["done"] or 0
    else:
        stats["backlog_total"] = 0
        stats["backlog_todo"] = 0
        stats["backlog_in_progress"] = 0
        stats["backlog_done"] = 0

    # バグ統計（bugs テーブルが存在する場合）
    try:
        bug_row = fetch_one(
            conn,
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_bugs
            FROM bugs WHERE project_id = ?
            """,
            (project_id,)
        )
        if bug_row:
            stats["bug_total"] = bug_row["total"] or 0
            stats["bug_open"] = bug_row["open_bugs"] or 0
        else:
            stats["bug_total"] = 0
            stats["bug_open"] = 0
    except Exception:
        stats["bug_total"] = 0
        stats["bug_open"] = 0

    return stats


def _generate_suggestions(
    project_id: str,
    stats: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    統計情報に基づいてバックログ提案を生成

    Args:
        project_id: プロジェクトID
        stats: プロジェクト統計情報

    Returns:
        提案リスト
    """
    suggestions: List[Dict[str, str]] = []

    # 1. 未解決バグがある場合
    if stats.get("bug_open", 0) > 0:
        suggestions.append({
            "title": f"未解決バグの対応（{stats['bug_open']}件）",
            "description": f"プロジェクト {project_id} に {stats['bug_open']} 件の未解決バグがあります。品質向上のため対応を検討してください。",
            "priority": "High",
            "category": "バグ修正",
            "rationale": f"未解決バグが {stats['bug_open']} 件あり、品質リスクが高い状態です。",
        })

    # 2. 差し戻しタスクが多い場合
    if stats.get("task_rejected", 0) >= 3:
        suggestions.append({
            "title": "レビュープロセスの改善",
            "description": "差し戻しタスクが多数発生しています。タスク定義の明確化やレビュー基準の整備を行い、差し戻し率を低減させましょう。",
            "priority": "Medium",
            "category": "改善",
            "rationale": f"差し戻しタスクが {stats['task_rejected']} 件あり、開発効率に影響しています。",
        })

    # 3. タスク完了率に基づく提案
    task_total = stats.get("task_total", 0)
    task_completed = stats.get("task_completed", 0)
    if task_total > 0:
        completion_rate = (task_completed / task_total) * 100
        if completion_rate >= 80:
            suggestions.append({
                "title": "リリース準備・ドキュメント整備",
                "description": f"タスク完了率が {completion_rate:.0f}% に達しています。リリースに向けたドキュメント整備やテスト強化を検討してください。",
                "priority": "Medium",
                "category": "ドキュメント",
                "rationale": f"タスク完了率 {completion_rate:.0f}%（{task_completed}/{task_total}）でリリース準備フェーズに適しています。",
            })

    # 4. バックログが少ない場合
    if stats.get("backlog_todo", 0) < 3:
        suggestions.append({
            "title": "次フェーズの計画策定",
            "description": "TODO状態のバックログが少なくなっています。次フェーズの機能追加や改善項目を計画しましょう。",
            "priority": "Low",
            "category": "調査",
            "rationale": f"TODO状態のバックログが {stats.get('backlog_todo', 0)} 件と少なく、計画の追加が必要です。",
        })

    # 5. テスト・品質関連（常に提案）
    if task_total >= 10 and not any(s["category"] == "バグ修正" for s in suggestions):
        suggestions.append({
            "title": "テストカバレッジの向上",
            "description": "プロジェクトの規模が大きくなっています。ユニットテストやインテグレーションテストの追加を検討してください。",
            "priority": "Medium",
            "category": "改善",
            "rationale": f"タスク総数 {task_total} 件のプロジェクトに対し、テスト品質の確保が重要です。",
        })

    # 提案が0件の場合のデフォルト
    if not suggestions:
        suggestions.append({
            "title": "コードベースのリファクタリング",
            "description": "定期的なコードベースの整理と最適化を行い、保守性を向上させましょう。",
            "priority": "Low",
            "category": "リファクタリング",
            "rationale": "特に緊急の課題はありませんが、コード品質の維持は継続的に重要です。",
        })

    return suggestions


def suggest_backlogs(
    project_id: str,
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    バックログ提案を生成

    Args:
        project_id: プロジェクトID
        db_path: データベースパス（テスト用）

    Returns:
        提案結果の辞書
    """
    try:
        validate_project_name(project_id)

        conn = get_connection(db_path=db_path)
        try:
            if not project_exists(conn, project_id):
                return {
                    "success": False,
                    "error": f"プロジェクトが見つかりません: {project_id}",
                }

            stats = _get_project_stats(conn, project_id)
            suggestions = _generate_suggestions(project_id, stats)

            return {
                "success": True,
                "suggestions": suggestions,
            }
        finally:
            conn.close()

    except ValidationError as e:
        return {"success": False, "error": f"入力検証エラー: {e}"}
    except DatabaseError as e:
        return {"success": False, "error": f"データベースエラー: {e}"}
    except Exception as e:
        return {"success": False, "error": f"予期しないエラー: {e}"}


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
        description="バックログ自動提案",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # JSON形式で提案を取得
  python suggest.py ai_pm_manager_v2 --json

  # テキスト形式で提案を表示
  python suggest.py ai_pm_manager_v2
"""
    )

    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: ai_pm_manager_v2）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    try:
        args = parser.parse_args()
    except (SystemExit, argparse.ArgumentError) as e:
        error_msg = str(e) if str(e) else "引数エラー"
        print(json.dumps({
            "success": False,
            "error": f"引数エラー: {error_msg}",
        }, ensure_ascii=False))
        sys.exit(1)

    result = suggest_backlogs(project_id=args.project_id)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            suggestions = result.get("suggestions", [])
            print(f"バックログ提案: {len(suggestions)} 件")
            print("-" * 50)
            for i, s in enumerate(suggestions, 1):
                print(f"\n[{i}] {s['title']}")
                print(f"    優先度: {s['priority']}  カテゴリ: {s['category']}")
                print(f"    説明: {s['description']}")
                print(f"    理由: {s['rationale']}")
        else:
            print(f"[ERROR] {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
