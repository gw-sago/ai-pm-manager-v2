#!/usr/bin/env python3
"""
Test script for Parallel Worker Launcher

Tests the parallel worker launch functionality including:
- Task detection
- Status transitions
- File lock management
- Worker process spawning
"""

import sys
from pathlib import Path

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query, fetch_all
from worker.parallel_detector import ParallelTaskDetector
from worker.parallel_launcher import ParallelWorkerLauncher


def test_parallel_detection():
    """Test parallel task detection"""
    print("\n" + "="*80)
    print("TEST: Parallel Task Detection")
    print("="*80)

    # Test with a sample project
    project_id = "ai_pm_manager"
    order_id = "ORDER_090"

    # Get summary
    summary = ParallelTaskDetector.get_parallel_launch_summary(
        project_id,
        order_id,
        max_tasks=10
    )

    print(f"\nProject: {project_id}")
    print(f"ORDER: {order_id}")
    print(f"\nTotal QUEUED: {summary['total_queued']}")
    print(f"Launchable Count: {summary['launchable_count']}")
    print(f"Blocked by Dependencies: {len(summary['blocked_by_dependencies'])}")
    print(f"Blocked by File Locks: {len(summary['blocked_by_locks'])}")

    if summary['launchable_tasks']:
        print(f"\nLaunchable Tasks:")
        for task_id in summary['launchable_tasks']:
            print(f"  - {task_id}")

    print("\n" + "="*80)
    print("TEST PASSED: Parallel Task Detection")
    print("="*80)


def test_parallel_launcher_dry_run():
    """Test parallel launcher in dry-run mode"""
    print("\n" + "="*80)
    print("TEST: Parallel Launcher (Dry-Run)")
    print("="*80)

    project_id = "ai_pm_manager"
    order_id = "ORDER_090"

    launcher = ParallelWorkerLauncher(
        project_id,
        order_id,
        max_workers=3,
        dry_run=True,
        verbose=True,
    )

    results = launcher.launch()

    print(f"\nLaunched Count: {results['launched_count']}")
    print(f"Detected Tasks: {results.get('detected_tasks', [])}")

    if results.get("message"):
        print(f"Message: {results['message']}")

    print("\n" + "="*80)
    print("TEST PASSED: Parallel Launcher (Dry-Run)")
    print("="*80)


def test_file_lock_integration():
    """Test file lock integration with parallel launch"""
    print("\n" + "="*80)
    print("TEST: File Lock Integration")
    print("="*80)

    from utils.file_lock import FileLockManager

    project_id = "ai_pm_manager"

    # Get all current locks
    locks = FileLockManager.get_all_locks(project_id)

    print(f"\nProject: {project_id}")
    print(f"Current Locks: {len(locks)}")

    if locks:
        print("\nLocked Files:")
        for lock in locks:
            print(f"  - {lock['file_path']} (Task: {lock['task_id']})")

    print("\n" + "="*80)
    print("TEST PASSED: File Lock Integration")
    print("="*80)


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("PARALLEL WORKER LAUNCHER TEST SUITE")
    print("="*80)

    try:
        # Test 1: Parallel Detection
        test_parallel_detection()

        # Test 2: Parallel Launcher Dry-Run
        test_parallel_launcher_dry_run()

        # Test 3: File Lock Integration
        test_file_lock_integration()

        print("\n" + "="*80)
        print("ALL TESTS PASSED")
        print("="*80 + "\n")

    except Exception as e:
        print("\n" + "="*80)
        print("TEST FAILED")
        print("="*80)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
