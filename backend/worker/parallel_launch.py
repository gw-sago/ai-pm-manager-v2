#!/usr/bin/env python3
"""
AI PM Framework - Parallel Task Launch CLI

Command-line tool to detect and display parallel launchable tasks within an ORDER.

Usage:
    python -m worker.parallel_launch PROJECT_NAME ORDER_ID [options]

Options:
    --max-tasks N       Maximum number of tasks to detect (default: 10)
    --json              Output in JSON format
    --summary           Show summary only (no task details)

Example:
    python -m worker.parallel_launch ai_pm_manager ORDER_090
    python -m worker.parallel_launch ai_pm_manager ORDER_090 --max-tasks 5
    python -m worker.parallel_launch ai_pm_manager ORDER_090 --json
    python -m worker.parallel_launch ai_pm_manager ORDER_090 --summary
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from worker.parallel_detector import ParallelTaskDetector
from utils.validation import validate_project_name, ValidationError
from utils.db import DatabaseError


def format_task_table(tasks):
    """Format tasks as a table"""
    if not tasks:
        return "  (なし)"

    lines = []
    lines.append("  " + "-" * 80)
    lines.append(f"  {'Task ID':<15} {'Priority':<10} {'Title':<50}")
    lines.append("  " + "-" * 80)

    for task in tasks:
        task_id = task["id"]
        priority = task["priority"]
        title = task["title"][:47] + "..." if len(task["title"]) > 50 else task["title"]
        lines.append(f"  {task_id:<15} {priority:<10} {title:<50}")

    lines.append("  " + "-" * 80)

    return "\n".join(lines)


def display_summary(summary):
    """Display summary in human-readable format"""
    print("\n" + "="*80)
    print(f"Parallel Launch Summary - {summary['order_id']}")
    print("="*80)

    print(f"\nProject: {summary['project_id']}")
    print(f"ORDER: {summary['order_id']}")
    print(f"Max Tasks: {summary['max_tasks']}")

    print(f"\n【タスク統計】")
    print(f"  Total QUEUED: {summary['total_queued']}")
    print(f"  Parallel Launchable: {summary['launchable_count']}")
    print(f"  Blocked by Dependencies: {len(summary['blocked_by_dependencies'])}")
    print(f"  Blocked by File Locks: {len(summary['blocked_by_locks'])}")

    if summary['launchable_tasks']:
        print(f"\n【並列起動可能タスク】({len(summary['launchable_tasks'])}件)")
        for task_id in summary['launchable_tasks']:
            print(f"  - {task_id}")

    if summary['blocked_by_dependencies']:
        print(f"\n【依存関係でブロック】({len(summary['blocked_by_dependencies'])}件)")
        for task_id in summary['blocked_by_dependencies']:
            print(f"  - {task_id}")

    if summary['blocked_by_locks']:
        print(f"\n【ファイルロックでブロック】({len(summary['blocked_by_locks'])}件)")
        for task_id in summary['blocked_by_locks']:
            print(f"  - {task_id}")

    print("\n" + "="*80)


def display_tasks(tasks, max_tasks):
    """Display tasks in human-readable format"""
    print("\n" + "="*80)
    print(f"Parallel Launchable Tasks (max: {max_tasks})")
    print("="*80)

    if not tasks:
        print("\n  並列起動可能なタスクはありません。")
        print("\n  理由:")
        print("    - QUEUEDタスクが存在しない")
        print("    - すべてのタスクが依存関係またはファイルロックでブロックされている")
    else:
        print(f"\n  {len(tasks)}件のタスクが並列起動可能です:\n")
        print(format_task_table(tasks))

        # Show file usage summary
        from utils.file_lock import FileLockManager

        all_files = set()
        for task in tasks:
            files = FileLockManager.parse_target_files(task.get("target_files"))
            all_files.update(files)

        if all_files:
            print(f"\n【対象ファイル】({len(all_files)}ファイル)")
            for file_path in sorted(all_files):
                print(f"  - {file_path}")

    print("\n" + "="*80)


def main():
    """CLI entry point"""
    # Windows UTF-8 output setup
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Detect parallel launchable tasks in an ORDER",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="Project ID")
    parser.add_argument("order_id", help="ORDER ID")
    parser.add_argument("--max-tasks", type=int, default=10, help="Maximum number of tasks to detect (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--summary", action="store_true", help="Show summary only")

    args = parser.parse_args()

    try:
        # Validate project
        validate_project_name(args.project_id)

        if args.summary:
            # Get summary
            summary = ParallelTaskDetector.get_parallel_launch_summary(
                args.project_id,
                args.order_id,
                max_tasks=args.max_tasks
            )

            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            else:
                display_summary(summary)

        else:
            # Get launchable tasks
            tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
                args.project_id,
                args.order_id,
                max_tasks=args.max_tasks
            )

            if args.json:
                output = {
                    "project_id": args.project_id,
                    "order_id": args.order_id,
                    "max_tasks": args.max_tasks,
                    "launchable_count": len(tasks),
                    "tasks": tasks
                }
                print(json.dumps(output, ensure_ascii=False, indent=2))
            else:
                display_tasks(tasks, args.max_tasks)

    except ValidationError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except DatabaseError as e:
        print(f"データベースエラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
