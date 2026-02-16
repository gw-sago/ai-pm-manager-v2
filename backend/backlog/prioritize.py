#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG優先度自動整理スクリプト

全アクティブBACKLOGと直近のインシデント・エスカレーション履歴を取得し、
Claude Code CLI経由で優先度判断を実行。優先度とsort_orderをDB更新する。

判断基準（優先度順）:
1. 自動実行安定性 - システムの安定稼働に直結
2. 運用改善 - 開発効率・運用効率向上
3. 新機能 - 機能追加・拡張
4. 将来構想 - 中長期的な改善

Usage:
    python backend/backlog/prioritize.py PROJECT_NAME [options]

Options:
    --dry-run       実際の更新は行わず、プレビューのみ表示
    --json          JSON形式で出力
    --verbose       詳細情報を表示
    --days          エスカレーション履歴を取得する日数（デフォルト: 30日）

Example:
    python backend/backlog/prioritize.py ai_pm_manager
    python backend/backlog/prioritize.py ai_pm_manager --dry-run --verbose
    python backend/backlog/prioritize.py ai_pm_manager --json --days 60
"""

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    rows_to_dicts,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    project_exists,
    ValidationError,
)


@dataclass
class PrioritizeResult:
    """BACKLOG優先度整理結果"""
    success: bool
    updated_count: int = 0
    total_count: int = 0
    changes: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    analysis: Optional[str] = None  # AI判断の詳細説明


def get_active_backlogs(conn, project_name: str) -> List[Dict[str, Any]]:
    """
    全アクティブBACKLOG項目を取得

    Args:
        conn: データベース接続
        project_name: プロジェクト名

    Returns:
        BACKLOG項目のリスト
    """
    rows = fetch_all(
        conn,
        """
        SELECT
            b.id,
            b.title,
            b.description,
            b.priority,
            b.status,
            b.sort_order,
            b.related_order_id,
            b.created_at,
            b.updated_at
        FROM backlog_items b
        WHERE b.project_id = ?
          AND b.status NOT IN ('DONE', 'CANCELED', 'EXTERNAL')
        ORDER BY b.sort_order, b.id
        """,
        (project_name,)
    )
    return rows_to_dicts(rows)


def get_recent_escalations(conn, project_name: str, days: int = 30) -> List[Dict[str, Any]]:
    """
    直近のエスカレーション履歴を取得

    Args:
        conn: データベース接続
        project_name: プロジェクト名
        days: 取得する日数

    Returns:
        エスカレーション履歴のリスト
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    rows = fetch_all(
        conn,
        """
        SELECT
            e.id,
            e.task_id,
            e.title,
            e.description,
            e.status,
            e.created_at,
            e.resolved_at,
            ch.new_value as escalation_type
        FROM escalations e
        LEFT JOIN change_history ch
            ON e.id = ch.entity_id
            AND ch.entity_type = 'escalation'
            AND ch.field_name = 'escalation_type'
        WHERE e.project_id = ?
          AND e.created_at >= ?
        ORDER BY e.created_at DESC
        LIMIT 50
        """,
        (project_name, cutoff_date)
    )
    return rows_to_dicts(rows)


def get_recent_incidents(conn, project_name: str, days: int = 30) -> List[Dict[str, Any]]:
    """
    直近のインシデント履歴を取得（incidents テーブルが存在する場合）

    Args:
        conn: データベース接続
        project_name: プロジェクト名
        days: 取得する日数

    Returns:
        インシデント履歴のリスト（テーブルが存在しない場合は空リスト）
    """
    # incidents テーブルの存在確認
    table_check = fetch_one(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' AND name='incidents'",
        ()
    )

    if not table_check:
        return []

    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    rows = fetch_all(
        conn,
        """
        SELECT
            incident_id,
            task_id,
            order_id,
            severity,
            category,
            description,
            resolution,
            created_at,
            timestamp
        FROM incidents
        WHERE project_id = ?
          AND created_at >= ?
        ORDER BY created_at DESC
        LIMIT 50
        """,
        (project_name, cutoff_date)
    )
    return rows_to_dicts(rows)


def analyze_priorities_with_llm(
    backlogs: List[Dict[str, Any]],
    escalations: List[Dict[str, Any]],
    incidents: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    LLMを使用してBACKLOG優先度を分析（簡易版 - ルールベース）

    Note: 本来はClaude Code CLIスキル経由でAI判断を実行するが、
          この実装では簡易的なルールベース判断を実装する。

    判断基準:
    1. 自動実行安定性 (High) - エスカレーション/インシデントに関連
    2. 運用改善 (High/Medium) - 効率化・改善系
    3. 新機能 (Medium) - 機能追加
    4. 将来構想 (Low) - 長期的な改善

    Args:
        backlogs: BACKLOG項目リスト
        escalations: エスカレーション履歴
        incidents: インシデント履歴

    Returns:
        {backlog_id: {"priority": "High/Medium/Low", "reason": "判断理由", "sort_order": int}}
    """
    # エスカレーション/インシデントに関連するキーワード
    stability_keywords = [
        "エラー", "バグ", "修正", "不具合", "異常", "失敗", "クラッシュ",
        "error", "bug", "fix", "crash", "fail", "exception",
        "安定", "stable", "reliability"
    ]

    improvement_keywords = [
        "改善", "効率", "最適化", "リファクタ", "パフォーマンス",
        "improve", "optimize", "refactor", "performance", "efficiency",
        "運用", "operation", "workflow"
    ]

    feature_keywords = [
        "新機能", "追加", "実装", "機能",
        "feature", "new", "add", "implement"
    ]

    # エスカレーション/インシデントから関連タスク・ORDER情報を抽出
    related_tasks = set()
    related_orders = set()

    for esc in escalations:
        if esc.get("task_id"):
            related_tasks.add(esc["task_id"])

    for inc in incidents:
        if inc.get("task_id"):
            related_tasks.add(inc["task_id"])
        if inc.get("order_id"):
            related_orders.add(inc["order_id"])

    # 各BACKLOGを分析
    priorities = {}
    current_sort_order = 1

    # 優先度グループ分け
    high_priority = []
    medium_priority = []
    low_priority = []

    for backlog in backlogs:
        backlog_id = backlog["id"]
        title = backlog.get("title", "").lower()
        description = backlog.get("description", "").lower()
        related_order = backlog.get("related_order_id")
        text = f"{title} {description}"

        # 1. エスカレーション/インシデントに直接関連
        if related_order and related_order in related_orders:
            high_priority.append({
                "backlog": backlog,
                "priority": "High",
                "reason": f"直近のインシデント・エスカレーションに関連 (ORDER: {related_order})"
            })
            continue

        # 2. 安定性関連のキーワード
        if any(kw in text for kw in stability_keywords):
            high_priority.append({
                "backlog": backlog,
                "priority": "High",
                "reason": "自動実行安定性に関連（バグ修正・エラー対応）"
            })
            continue

        # 3. 運用改善関連
        if any(kw in text for kw in improvement_keywords):
            medium_priority.append({
                "backlog": backlog,
                "priority": "Medium",
                "reason": "運用改善・効率化に関連"
            })
            continue

        # 4. 新機能追加
        if any(kw in text for kw in feature_keywords):
            medium_priority.append({
                "backlog": backlog,
                "priority": "Medium",
                "reason": "新機能追加"
            })
            continue

        # 5. その他（将来構想）
        low_priority.append({
            "backlog": backlog,
            "priority": "Low",
            "reason": "将来構想・長期的改善"
        })

    # sort_order を割り当て
    for item in high_priority:
        priorities[item["backlog"]["id"]] = {
            "priority": item["priority"],
            "reason": item["reason"],
            "sort_order": current_sort_order
        }
        current_sort_order += 1

    for item in medium_priority:
        priorities[item["backlog"]["id"]] = {
            "priority": item["priority"],
            "reason": item["reason"],
            "sort_order": current_sort_order
        }
        current_sort_order += 1

    for item in low_priority:
        priorities[item["backlog"]["id"]] = {
            "priority": item["priority"],
            "reason": item["reason"],
            "sort_order": current_sort_order
        }
        current_sort_order += 1

    return priorities


def prioritize_backlog(
    project_name: str,
    *,
    dry_run: bool = False,
    days: int = 30,
    db_path: Optional[Path] = None,
) -> PrioritizeResult:
    """
    BACKLOG優先度を自動整理

    Args:
        project_name: プロジェクト名
        dry_run: Trueの場合、実際の更新は行わずプレビューのみ
        days: エスカレーション/インシデント履歴を取得する日数
        db_path: データベースパス（テスト用）

    Returns:
        PrioritizeResult: 優先度整理結果
    """
    try:
        # 入力検証
        validate_project_name(project_name)

        with transaction(db_path=db_path) as conn:
            # プロジェクト存在確認
            if not project_exists(conn, project_name):
                return PrioritizeResult(
                    success=False,
                    error=f"プロジェクトが見つかりません: {project_name}"
                )

            # データ取得
            backlogs = get_active_backlogs(conn, project_name)

            if not backlogs:
                return PrioritizeResult(
                    success=True,
                    total_count=0,
                    message="対象のアクティブBACKLOG項目がありません"
                )

            escalations = get_recent_escalations(conn, project_name, days)
            incidents = get_recent_incidents(conn, project_name, days)

            # AI分析実行（簡易版はルールベース）
            priority_analysis = analyze_priorities_with_llm(
                backlogs,
                escalations,
                incidents
            )

            # 変更を収集
            changes = []
            now = datetime.now().isoformat()

            for backlog in backlogs:
                backlog_id = backlog["id"]
                analysis = priority_analysis.get(backlog_id)

                if not analysis:
                    continue

                new_priority = analysis["priority"]
                new_sort_order = analysis["sort_order"]
                reason = analysis["reason"]

                old_priority = backlog.get("priority", "Medium")
                old_sort_order = backlog.get("sort_order", 9999)

                # 変更があった場合のみ記録
                if old_priority != new_priority or old_sort_order != new_sort_order:
                    changes.append({
                        "backlog_id": backlog_id,
                        "title": backlog["title"],
                        "old_priority": old_priority,
                        "new_priority": new_priority,
                        "old_sort_order": old_sort_order,
                        "new_sort_order": new_sort_order,
                        "reason": reason,
                    })

                    # dry_runでない場合は更新
                    if not dry_run:
                        execute_query(
                            conn,
                            """
                            UPDATE backlog_items
                            SET priority = ?, sort_order = ?, updated_at = ?
                            WHERE id = ? AND project_id = ?
                            """,
                            (new_priority, new_sort_order, now, backlog_id, project_name)
                        )

            message = f"BACKLOG優先度整理が完了しました: {len(changes)}件を更新"
            if dry_run:
                message += " (dry-run mode)"

            analysis_summary = (
                f"分析対象: BACKLOG {len(backlogs)}件、"
                f"エスカレーション {len(escalations)}件、"
                f"インシデント {len(incidents)}件（直近{days}日間）"
            )

            return PrioritizeResult(
                success=True,
                updated_count=len(changes),
                total_count=len(backlogs),
                changes=changes,
                message=message,
                analysis=analysis_summary
            )

    except ValidationError as e:
        return PrioritizeResult(
            success=False,
            error=f"入力検証エラー: {e}"
        )
    except DatabaseError as e:
        return PrioritizeResult(
            success=False,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return PrioritizeResult(
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
        description="BACKLOG優先度自動整理（AI分析ベース）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 優先度自動整理を実行
  python prioritize.py ai_pm_manager

  # プレビューのみ（更新なし）
  python prioritize.py ai_pm_manager --dry-run --verbose

  # JSON形式で出力、60日分の履歴を使用
  python prioritize.py ai_pm_manager --json --days 60

判断基準（優先度順）:
  1. 自動実行安定性 - システムの安定稼働に直結（High）
  2. 運用改善 - 開発効率・運用効率向上（High/Medium）
  3. 新機能 - 機能追加・拡張（Medium）
  4. 将来構想 - 中長期的な改善（Low）
"""
    )

    parser.add_argument(
        "project_name",
        help="プロジェクト名 (例: ai_pm_manager)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際の更新は行わず、プレビューのみ表示"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細情報を表示"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="エスカレーション/インシデント履歴を取得する日数（デフォルト: 30）"
    )

    args = parser.parse_args()

    result = prioritize_backlog(
        project_name=args.project_name,
        dry_run=args.dry_run,
        days=args.days,
    )

    if args.json:
        output = {
            "success": result.success,
            "updated_count": result.updated_count,
            "total_count": result.total_count,
            "changes": result.changes,
            "message": result.message,
            "error": result.error,
            "warnings": result.warnings,
            "analysis": result.analysis,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            if result.analysis:
                print(f"  {result.analysis}")
            print(f"  総件数: {result.total_count}")
            print(f"  更新件数: {result.updated_count}")

            if args.verbose and result.changes:
                print()
                print("変更内容:")
                print(f"{'ID':<15} {'Priority':<15} {'Sort Order':<15} {'Title':<40}")
                print(f"{'':15} {'(Old→New)':<15} {'(Old→New)':<15} {'Reason':<40}")
                print("-" * 95)
                for change in result.changes:
                    priority_change = f"{change['old_priority']}→{change['new_priority']}"
                    sort_change = f"{change['old_sort_order']}→{change['new_sort_order']}"
                    print(
                        f"{change['backlog_id']:<15} "
                        f"{priority_change:<15} "
                        f"{sort_change:<15} "
                        f"{change['title'][:38]:<40}"
                    )
                    print(f"{'':15} {'':15} {'':15} └─ {change['reason'][:70]}")
            elif result.updated_count == 0:
                print("  （変更なし - 既に最適な状態です）")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
