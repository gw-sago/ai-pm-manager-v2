#!/usr/bin/env python3
"""
AI PM Framework - エスカレーション履歴ビューア

Usage:
    python backend/escalation/view_escalations.py PROJECT_NAME [options]

Options:
    --task-id TASK_ID       特定タスクのみ表示
    --type TYPE            特定種別のみ表示（model_upgrade, review_rejection, etc.）
    --limit N              表示件数上限（デフォルト: 100）
    --stats                統計情報を表示

Example:
    python backend/escalation/view_escalations.py ai_pm_manager
    python backend/escalation/view_escalations.py ai_pm_manager --task-id TASK_975
    python backend/escalation/view_escalations.py ai_pm_manager --type model_upgrade
    python backend/escalation/view_escalations.py ai_pm_manager --stats
"""

import argparse
import json
import sys
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from escalation.log_escalation import (
    get_escalation_history,
    get_escalation_statistics,
    EscalationType,
)


def display_escalations(escalations: list) -> None:
    """エスカレーション一覧を表示"""
    if not escalations:
        print("エスカレーションなし")
        return

    print(f"\n{'='*80}")
    print(f"エスカレーション履歴 ({len(escalations)}件)")
    print(f"{'='*80}\n")

    for esc in escalations:
        print(f"ID: {esc.get('id', 'N/A')}")
        print(f"タスク: {esc.get('task_id', 'N/A')}")
        print(f"種別: {esc.get('escalation_type', 'N/A')}")
        print(f"タイトル: {esc.get('title', 'N/A')}")
        print(f"説明: {esc.get('description', 'N/A')}")
        print(f"ステータス: {esc.get('status', 'N/A')}")
        print(f"作成日時: {esc.get('created_at', 'N/A')}")

        # メタデータ表示（あれば）
        if esc.get('change_reason'):
            try:
                # change_reasonにメタデータが含まれる場合
                metadata_str = esc.get('new_value')
                if metadata_str and metadata_str.startswith('{'):
                    metadata = json.loads(metadata_str)
                    print(f"メタデータ:")
                    for key, value in metadata.items():
                        print(f"  - {key}: {value}")
            except (json.JSONDecodeError, AttributeError):
                pass

        print(f"{'-'*80}\n")


def display_statistics(stats: dict, project_id: str, task_id: str = None) -> None:
    """統計情報を表示"""
    print(f"\n{'='*80}")
    print(f"エスカレーション統計")
    if task_id:
        print(f"プロジェクト: {project_id}, タスク: {task_id}")
    else:
        print(f"プロジェクト: {project_id}")
    print(f"{'='*80}\n")

    print(f"総数: {stats.get('total', 0)}件\n")

    # 種別ごとの集計
    by_type = stats.get('by_type', {})
    if by_type:
        print("種別別:")
        for esc_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {esc_type}: {count}件")
        print()

    # ステータスごとの集計
    by_status = stats.get('by_status', {})
    if by_status:
        print("ステータス別:")
        for status, count in sorted(by_status.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {status}: {count}件")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="エスカレーション履歴を表示",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--task-id", help="タスクID（特定タスクのみ表示）")
    parser.add_argument("--type", help="エスカレーション種別（特定種別のみ表示）")
    parser.add_argument("--limit", type=int, default=100, help="表示件数上限（デフォルト: 100）")
    parser.add_argument("--stats", action="store_true", help="統計情報を表示")

    args = parser.parse_args()

    try:
        if args.stats:
            # 統計情報表示
            stats = get_escalation_statistics(args.project_id, args.task_id)
            display_statistics(stats, args.project_id, args.task_id)
        else:
            # エスカレーション一覧表示
            escalations = get_escalation_history(
                args.project_id,
                task_id=args.task_id,
                escalation_type=args.type,
                limit=args.limit
            )
            display_escalations(escalations)

    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
