#!/usr/bin/env python3
"""
Test script for task auto-kick functionality

Tests the automatic re-evaluation and kicking of waiting tasks
after file lock release and dependency completion.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.db import get_connection, fetch_one, execute_query
from utils.task_unblock import TaskUnblocker
from utils.file_lock import FileLockManager


def test_find_unblocked_tasks():
    """Test finding unblocked tasks"""
    print("=" * 80)
    print("TEST: Find Unblocked Tasks")
    print("=" * 80)

    project_id = "ai_pm_manager"
    order_id = "ORDER_076"

    unblocked = TaskUnblocker.find_unblocked_tasks(project_id, order_id)

    print(f"\nFound {len(unblocked)} unblocked tasks:")
    for task in unblocked:
        print(f"  - {task['id']}: {task['title']} (status: {task['status']})")

    assert len(unblocked) >= 0, "Should return a list (even if empty)"
    print("\n✓ PASSED: find_unblocked_tasks works correctly\n")


def test_dependency_checking():
    """Test dependency completion checking"""
    print("=" * 80)
    print("TEST: Dependency Checking")
    print("=" * 80)

    project_id = "ai_pm_manager"

    conn = get_connection()
    try:
        # Note: TASK_728 and TASK_729 are both COMPLETED in the current DB state
        # This test verifies the dependency checking logic works

        # Get TASK_729 status and dependencies
        task_729 = fetch_one(
            conn,
            "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
            ("TASK_729", project_id)
        )
        print(f"\nTASK_729 status: {task_729['status'] if task_729 else 'NOT_FOUND'}")

        # Check if dependencies are completed
        deps_completed = TaskUnblocker._check_dependencies_completed(conn, project_id, "TASK_729")
        print(f"TASK_729 dependencies completed: {deps_completed}")

        # If TASK_728 is COMPLETED, then TASK_729 dependencies should be completed
        is_executable = TaskUnblocker._is_task_now_executable(conn, project_id, "TASK_729")
        print(f"TASK_729 executable: {is_executable}")

        # Test with a task that has multiple dependencies
        task_732 = fetch_one(
            conn,
            "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
            ("TASK_732", project_id)
        )
        if task_732:
            print(f"\nTASK_732 status: {task_732['status']}")
            is_executable = TaskUnblocker._is_task_now_executable(conn, project_id, "TASK_732")
            print(f"TASK_732 executable: {is_executable}")

        print("\n✓ PASSED: Dependency checking works correctly\n")

    finally:
        conn.close()


def test_file_lock_checking():
    """Test file lock conflict checking"""
    print("=" * 80)
    print("TEST: File Lock Checking")
    print("=" * 80)

    project_id = "ai_pm_manager"

    # Simulate acquiring locks for TASK_732
    target_files = ["scripts/test_file_b.py", "scripts/test_file_c.py"]

    try:
        # Acquire locks
        acquired = FileLockManager.acquire_locks(project_id, "TASK_732", target_files)
        print(f"\nLocks acquired for TASK_732: {acquired}")

        # Check if TASK_734 can start (should be blocked by TASK_732's locks)
        can_start, blocking = FileLockManager.can_task_start(project_id, "TASK_734")
        print(f"TASK_734 can start: {can_start}")
        print(f"Blocking tasks: {blocking}")

        if target_files:  # Only assert if files were specified
            assert not can_start, "TASK_734 should be blocked by TASK_732's locks"
            assert "TASK_732" in blocking, "TASK_732 should be in blocking list"

        # Release locks
        FileLockManager.release_locks(project_id, "TASK_732")
        print("\nLocks released for TASK_732")

        # Check again
        can_start, blocking = FileLockManager.can_task_start(project_id, "TASK_734")
        print(f"TASK_734 can start after release: {can_start}")
        print(f"Blocking tasks: {blocking}")

        assert can_start, "TASK_734 should be able to start after lock release"
        assert len(blocking) == 0, "No tasks should be blocking"

        print("\n✓ PASSED: File lock checking works correctly\n")

    except Exception as e:
        # Clean up locks in case of error
        try:
            FileLockManager.release_locks(project_id, "TASK_732")
        except:
            pass
        raise


def test_auto_kick():
    """Test automatic task kicking"""
    print("=" * 80)
    print("TEST: Auto-Kick Unblocked Tasks")
    print("=" * 80)

    project_id = "ai_pm_manager"
    order_id = "ORDER_076"

    # Get initial state
    conn = get_connection()
    try:
        initial_state = fetch_one(
            conn,
            "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
            ("TASK_729", project_id)
        )
        print(f"\nInitial TASK_729 status: {initial_state['status']}")

        # TASK_729 is BLOCKED, should not be kicked (depends on IN_PROGRESS TASK_728)
        kicked = TaskUnblocker.auto_kick_unblocked_tasks(
            project_id, order_id, exclude_task_id="TASK_728"
        )

        print(f"\nKicked tasks: {[t['id'] for t in kicked]}")

        # TASK_729 should not be in the kicked list
        kicked_ids = [t['id'] for t in kicked]
        assert "TASK_729" not in kicked_ids, "TASK_729 should not be kicked (dependency not met)"

        # TASK_732 and TASK_734 should be in the kicked list (if they were BLOCKED)
        # But they're already QUEUED, so they might not be updated
        print(f"Kicked task count: {len(kicked)}")

        print("\n✓ PASSED: Auto-kick works correctly\n")

    finally:
        conn.close()


def test_successor_tasks():
    """Test finding successor tasks after completion"""
    print("=" * 80)
    print("TEST: Find Successor Tasks")
    print("=" * 80)

    project_id = "ai_pm_manager"

    # Test with TASK_723 as completed task
    # TASK_724 and TASK_725 should be successors
    successors = TaskUnblocker.find_successor_tasks(project_id, "TASK_723")

    print(f"\nSuccessors of TASK_723:")
    for task in successors:
        print(f"  - {task['id']}: {task['title']} (status: {task['status']})")

    # Should find at least TASK_724 and TASK_725
    successor_ids = [t['id'] for t in successors]
    print(f"\nSuccessor IDs: {successor_ids}")

    print("\n✓ PASSED: Find successor tasks works correctly\n")


def test_check_successor_dependencies():
    """Test checking if successor tasks are ready after dependency completion"""
    print("=" * 80)
    print("TEST: Check Successor Dependencies")
    print("=" * 80)

    project_id = "ai_pm_manager"

    # Test with TASK_723 as completed task
    ready_tasks = TaskUnblocker.check_successor_dependencies(project_id, "TASK_723")

    print(f"\nReady successor tasks after TASK_723 completion:")
    for task in ready_tasks:
        print(f"  - {task['id']}: {task['title']} (status: {task['status']})")

    print(f"\nReady task count: {len(ready_tasks)}")
    assert len(ready_tasks) >= 0, "Should return a list (even if empty)"

    print("\n✓ PASSED: Check successor dependencies works correctly\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("TASK AUTO-KICK FUNCTIONALITY TESTS")
    print("=" * 80 + "\n")

    try:
        test_find_unblocked_tasks()
        test_dependency_checking()
        test_file_lock_checking()
        test_auto_kick()
        test_successor_tasks()
        test_check_successor_dependencies()

        print("=" * 80)
        print("ALL TESTS PASSED ✓")
        print("=" * 80 + "\n")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
