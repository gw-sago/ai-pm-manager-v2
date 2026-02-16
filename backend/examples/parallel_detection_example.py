#!/usr/bin/env python3
"""
Parallel Task Detection - Usage Example

Demonstrates how to use the ParallelTaskDetector to find tasks
that can be launched simultaneously within an ORDER.
"""

import sys
from pathlib import Path

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
sys.path.insert(0, str(_package_root))

from worker.parallel_detector import ParallelTaskDetector


def example_basic_detection():
    """Example 1: Basic parallel task detection"""
    print("="*80)
    print("Example 1: Basic Parallel Task Detection")
    print("="*80)

    project_id = "ai_pm_manager"
    order_id = "ORDER_090"

    # Find up to 10 parallel launchable tasks
    tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
        project_id=project_id,
        order_id=order_id,
        max_tasks=10
    )

    print(f"\nProject: {project_id}")
    print(f"ORDER: {order_id}")
    print(f"\nFound {len(tasks)} parallel launchable tasks:\n")

    for task in tasks:
        print(f"  {task['id']:<15} {task['priority']:<5} {task['title']}")

    print("\n" + "="*80 + "\n")


def example_summary():
    """Example 2: Get comprehensive summary"""
    print("="*80)
    print("Example 2: Parallel Launch Summary")
    print("="*80)

    project_id = "ai_pm_manager"
    order_id = "ORDER_090"

    # Get summary with blocking reasons
    summary = ParallelTaskDetector.get_parallel_launch_summary(
        project_id=project_id,
        order_id=order_id,
        max_tasks=10
    )

    print(f"\nProject: {project_id}")
    print(f"ORDER: {order_id}\n")

    print(f"Total QUEUED Tasks: {summary['total_queued']}")
    print(f"Parallel Launchable: {summary['launchable_count']}")
    print(f"Blocked by Dependencies: {len(summary['blocked_by_dependencies'])}")
    print(f"Blocked by File Locks: {len(summary['blocked_by_locks'])}")

    if summary['launchable_tasks']:
        print(f"\nLaunchable Tasks:")
        for task_id in summary['launchable_tasks']:
            print(f"  - {task_id}")

    if summary['blocked_by_dependencies']:
        print(f"\nBlocked by Dependencies:")
        for task_id in summary['blocked_by_dependencies']:
            print(f"  - {task_id}")

    if summary['blocked_by_locks']:
        print(f"\nBlocked by File Locks:")
        for task_id in summary['blocked_by_locks']:
            print(f"  - {task_id}")

    print("\n" + "="*80 + "\n")


def example_file_analysis():
    """Example 3: Analyze file usage"""
    print("="*80)
    print("Example 3: File Usage Analysis")
    print("="*80)

    project_id = "ai_pm_manager"
    order_id = "ORDER_090"

    tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
        project_id=project_id,
        order_id=order_id,
        max_tasks=10
    )

    print(f"\nProject: {project_id}")
    print(f"ORDER: {order_id}\n")

    from utils.file_lock import FileLockManager

    all_files = {}
    for task in tasks:
        files = FileLockManager.parse_target_files(task.get("target_files"))
        for file_path in files:
            if file_path not in all_files:
                all_files[file_path] = []
            all_files[file_path].append(task["id"])

    print(f"Total Unique Files: {len(all_files)}\n")

    if all_files:
        print("File Usage Map:")
        for file_path, task_ids in sorted(all_files.items()):
            print(f"  {file_path}")
            for task_id in task_ids:
                print(f"    └─> {task_id}")
        print()
    else:
        print("No target files specified for any task.\n")

    print("="*80 + "\n")


def example_priority_analysis():
    """Example 4: Analyze priority distribution"""
    print("="*80)
    print("Example 4: Priority Distribution Analysis")
    print("="*80)

    project_id = "ai_pm_manager"
    order_id = "ORDER_090"

    tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
        project_id=project_id,
        order_id=order_id,
        max_tasks=10
    )

    print(f"\nProject: {project_id}")
    print(f"ORDER: {order_id}\n")

    # Count by priority
    priority_counts = {}
    for task in tasks:
        priority = task["priority"]
        if priority not in priority_counts:
            priority_counts[priority] = []
        priority_counts[priority].append(task["id"])

    print("Priority Distribution:")
    for priority in ["P0", "P1", "P2", "P3"]:
        if priority in priority_counts:
            count = len(priority_counts[priority])
            print(f"  {priority}: {count} tasks")
            for task_id in priority_counts[priority]:
                print(f"    - {task_id}")
        else:
            print(f"  {priority}: 0 tasks")

    print("\n" + "="*80 + "\n")


def main():
    """Run all examples"""
    print("\n" + "="*80)
    print("Parallel Task Detection - Usage Examples")
    print("="*80 + "\n")

    try:
        example_basic_detection()
        example_summary()
        example_file_analysis()
        example_priority_analysis()

        print("="*80)
        print("All examples completed successfully!")
        print("="*80)

    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
