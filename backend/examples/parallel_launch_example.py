#!/usr/bin/env python3
"""
Parallel Worker Launch - Usage Examples

Demonstrates how to use the parallel worker launch functionality.
"""

import sys
from pathlib import Path

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))


def example_1_detect_parallel_tasks():
    """Example 1: Detect parallel launchable tasks"""
    print("\n" + "="*80)
    print("EXAMPLE 1: Detect Parallel Launchable Tasks")
    print("="*80)

    from worker.parallel_detector import ParallelTaskDetector

    project_id = "ai_pm_manager"
    order_id = "ORDER_090"

    # Find parallel launchable tasks
    tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
        project_id,
        order_id,
        max_tasks=10
    )

    print(f"\nProject: {project_id}")
    print(f"ORDER: {order_id}")
    print(f"\nParallel Launchable Tasks: {len(tasks)}")

    if tasks:
        print("\nTask Details:")
        for task in tasks:
            print(f"  - {task['id']}: {task['title']} (Priority: {task['priority']})")
    else:
        print("\nNo parallel launchable tasks found.")
        print("Possible reasons:")
        print("  - All tasks have pending dependencies")
        print("  - All tasks have file lock conflicts")
        print("  - No QUEUED tasks in the ORDER")

    print("\n" + "="*80)


def example_2_get_summary():
    """Example 2: Get parallel launch summary"""
    print("\n" + "="*80)
    print("EXAMPLE 2: Get Parallel Launch Summary")
    print("="*80)

    from worker.parallel_detector import ParallelTaskDetector

    project_id = "ai_pm_manager"
    order_id = "ORDER_090"

    # Get summary with blocking reasons
    summary = ParallelTaskDetector.get_parallel_launch_summary(
        project_id,
        order_id,
        max_tasks=10
    )

    print(f"\nProject: {project_id}")
    print(f"ORDER: {order_id}")
    print(f"\n【Statistics】")
    print(f"  Total QUEUED: {summary['total_queued']}")
    print(f"  Parallel Launchable: {summary['launchable_count']}")
    print(f"  Blocked by Dependencies: {len(summary['blocked_by_dependencies'])}")
    print(f"  Blocked by File Locks: {len(summary['blocked_by_locks'])}")

    if summary['launchable_tasks']:
        print(f"\n【Launchable Tasks】")
        for task_id in summary['launchable_tasks']:
            print(f"  - {task_id}")

    if summary['blocked_by_dependencies']:
        print(f"\n【Blocked by Dependencies】")
        for task_id in summary['blocked_by_dependencies']:
            print(f"  - {task_id}")

    if summary['blocked_by_locks']:
        print(f"\n【Blocked by File Locks】")
        for task_id in summary['blocked_by_locks']:
            print(f"  - {task_id}")

    print("\n" + "="*80)


def example_3_launch_parallel_workers_dry_run():
    """Example 3: Launch parallel workers (dry-run)"""
    print("\n" + "="*80)
    print("EXAMPLE 3: Launch Parallel Workers (Dry-Run)")
    print("="*80)

    from worker.parallel_launcher import ParallelWorkerLauncher

    project_id = "ai_pm_manager"
    order_id = "ORDER_090"

    # Launch in dry-run mode
    launcher = ParallelWorkerLauncher(
        project_id,
        order_id,
        max_workers=5,
        dry_run=True,  # Don't actually launch
        verbose=True,
    )

    results = launcher.launch()

    print(f"\n【Dry-Run Results】")
    print(f"  Would launch: {len(results.get('detected_tasks', []))} tasks")
    print(f"  Message: {results.get('message', 'N/A')}")

    if results.get('detected_tasks'):
        print(f"\n【Tasks that would be launched】")
        for task_id in results['detected_tasks']:
            print(f"  - {task_id}")

    print("\n" + "="*80)


def example_4_check_file_locks():
    """Example 4: Check current file locks"""
    print("\n" + "="*80)
    print("EXAMPLE 4: Check Current File Locks")
    print("="*80)

    from utils.file_lock import FileLockManager

    project_id = "ai_pm_manager"

    # Get all locks
    locks = FileLockManager.get_all_locks(project_id)

    print(f"\nProject: {project_id}")
    print(f"Current Locks: {len(locks)}")

    if locks:
        print("\n【Locked Files】")
        # Group by task
        task_locks = {}
        for lock in locks:
            task_id = lock['task_id']
            if task_id not in task_locks:
                task_locks[task_id] = []
            task_locks[task_id].append(lock['file_path'])

        for task_id, files in task_locks.items():
            print(f"\n  Task: {task_id}")
            for file_path in files:
                print(f"    - {file_path}")
    else:
        print("\nNo file locks currently held.")

    print("\n" + "="*80)


def example_5_integration_with_execute_task():
    """Example 5: Integration with execute_task"""
    print("\n" + "="*80)
    print("EXAMPLE 5: Integration with execute_task")
    print("="*80)

    print("\nTo use parallel launch with execute_task, use the --parallel flag:")
    print("\nCommands:")
    print("  # Basic parallel launch")
    print("  python -m worker.execute_task ai_pm_manager TASK_925 --parallel")
    print()
    print("  # With max workers limit")
    print("  python -m worker.execute_task ai_pm_manager TASK_925 --parallel --max-workers 3")
    print()
    print("  # With specific model")
    print("  python -m worker.execute_task ai_pm_manager TASK_925 --parallel --model sonnet")
    print()
    print("  # Dry-run mode")
    print("  python -m worker.execute_task ai_pm_manager TASK_925 --parallel --dry-run")
    print()
    print("  # No auto-review")
    print("  python -m worker.execute_task ai_pm_manager TASK_925 --parallel --no-review")

    print("\n" + "="*80)


def main():
    """Run all examples"""
    print("\n" + "="*80)
    print("PARALLEL WORKER LAUNCH - USAGE EXAMPLES")
    print("="*80)

    try:
        # Example 1
        example_1_detect_parallel_tasks()

        # Example 2
        example_2_get_summary()

        # Example 3
        example_3_launch_parallel_workers_dry_run()

        # Example 4
        example_4_check_file_locks()

        # Example 5
        example_5_integration_with_execute_task()

        print("\n" + "="*80)
        print("ALL EXAMPLES COMPLETED")
        print("="*80 + "\n")

    except Exception as e:
        print("\n" + "="*80)
        print("EXAMPLE FAILED")
        print("="*80)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
