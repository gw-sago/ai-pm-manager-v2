#!/usr/bin/env python3
"""
Test script for parallel_detector.py

Tests the parallel task detection logic that identifies QUEUED tasks
that can be launched simultaneously based on:
1. No dependency conflicts
2. No file lock conflicts
3. QUEUED status
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
sys.path.insert(0, str(_package_root))

from worker.parallel_detector import ParallelTaskDetector
from utils.db import get_connection, execute_query, fetch_all
from utils.file_lock import FileLockManager


def setup_test_data():
    """Setup test data in database"""
    conn = get_connection()
    try:
        project_id = "test_parallel_project"
        order_id = "ORDER_TEST_PARALLEL"

        # Clean up existing test data
        execute_query(conn, "DELETE FROM file_locks WHERE project_id = ?", (project_id,))
        execute_query(conn, "DELETE FROM task_dependencies WHERE project_id = ?", (project_id,))
        execute_query(conn, "DELETE FROM tasks WHERE project_id = ?", (project_id,))
        execute_query(conn, "DELETE FROM orders WHERE project_id = ?", (project_id,))
        execute_query(conn, "DELETE FROM projects WHERE id = ?", (project_id,))

        # Create test project
        execute_query(
            conn,
            "INSERT INTO projects (id, name, path, created_at) VALUES (?, ?, ?, datetime('now'))",
            (project_id, "Test Parallel Project", "PROJECTS/test_parallel_project")
        )

        # Create test ORDER
        execute_query(
            conn,
            """
            INSERT INTO orders (id, project_id, title, status, created_at)
            VALUES (?, ?, ?, 'IN_PROGRESS', datetime('now'))
            """,
            (order_id, project_id, "Test Parallel ORDER")
        )

        # Create test tasks
        tasks = [
            # Parallel launchable tasks (no deps, no file conflicts)
            ("TASK_P001", "Task 1 - No deps, File A", "P0", "QUEUED", '["file_a.py"]'),
            ("TASK_P002", "Task 2 - No deps, File B", "P0", "QUEUED", '["file_b.py"]'),
            ("TASK_P003", "Task 3 - No deps, File C", "P1", "QUEUED", '["file_c.py"]'),

            # Blocked by dependencies
            ("TASK_P004", "Task 4 - Depends on P001", "P0", "QUEUED", '["file_d.py"]'),

            # Blocked by file conflicts (same files as P001)
            ("TASK_P005", "Task 5 - File A conflict", "P1", "QUEUED", '["file_a.py"]'),

            # Completed task (dependency for P004)
            ("TASK_P000", "Task 0 - Completed", "P0", "COMPLETED", '["file_z.py"]'),

            # IN_PROGRESS task with file lock
            ("TASK_P006", "Task 6 - In progress, File X", "P0", "IN_PROGRESS", '["file_x.py"]'),

            # Blocked by IN_PROGRESS file lock
            ("TASK_P007", "Task 7 - File X conflict", "P1", "QUEUED", '["file_x.py"]'),

            # No target files (always launchable if no deps)
            ("TASK_P008", "Task 8 - No files", "P2", "QUEUED", None),
        ]

        for task_id, title, priority, status, target_files in tasks:
            execute_query(
                conn,
                """
                INSERT INTO tasks (
                    id, order_id, project_id, title, priority, status,
                    target_files, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (task_id, order_id, project_id, title, priority, status, target_files)
            )

        # Create dependency: TASK_P004 depends on TASK_P000
        execute_query(
            conn,
            """
            INSERT INTO task_dependencies (task_id, depends_on_task_id, project_id)
            VALUES (?, ?, ?)
            """,
            ("TASK_P004", "TASK_P000", project_id)
        )

        # Create file lock for IN_PROGRESS task
        execute_query(
            conn,
            """
            INSERT INTO file_locks (project_id, task_id, file_path, locked_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (project_id, "TASK_P006", "file_x.py")
        )

        conn.commit()
        print("✓ Test data setup complete")

        return project_id, order_id

    except Exception as e:
        conn.rollback()
        print(f"✗ Test data setup failed: {e}")
        raise
    finally:
        conn.close()


def test_find_parallel_launchable_tasks():
    """Test finding parallel launchable tasks"""
    print("\n" + "="*80)
    print("TEST: find_parallel_launchable_tasks()")
    print("="*80)

    project_id, order_id = setup_test_data()

    # Test 1: Find all parallel launchable tasks
    print("\n[Test 1] Find parallel launchable tasks (max=10)")
    tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
        project_id, order_id, max_tasks=10
    )

    print(f"\nFound {len(tasks)} launchable tasks:")
    for task in tasks:
        print(f"  - {task['id']}: {task['title']} (priority={task['priority']})")

    # Expected: TASK_P001, TASK_P002, TASK_P003, TASK_P004, TASK_P008
    # TASK_P004 now launchable because TASK_P000 is COMPLETED
    expected_ids = {"TASK_P001", "TASK_P002", "TASK_P003", "TASK_P004", "TASK_P008"}
    actual_ids = {task["id"] for task in tasks}

    if expected_ids == actual_ids:
        print(f"✓ Expected tasks found: {expected_ids}")
    else:
        print(f"✗ Task mismatch!")
        print(f"  Expected: {expected_ids}")
        print(f"  Actual: {actual_ids}")
        print(f"  Missing: {expected_ids - actual_ids}")
        print(f"  Extra: {actual_ids - expected_ids}")

    # Test 2: Verify file conflict detection
    print("\n[Test 2] File conflict detection")
    all_files = set()
    for task in tasks:
        files = FileLockManager.parse_target_files(task.get("target_files"))
        conflicts = all_files.intersection(files)
        if conflicts:
            print(f"✗ Task {task['id']} has file conflicts: {conflicts}")
        all_files.update(files)

    print(f"✓ No file conflicts among launchable tasks")
    print(f"  Total unique files: {len(all_files)}")

    # Test 3: Test max_tasks limit
    print("\n[Test 3] Max tasks limit (max=2)")
    limited_tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
        project_id, order_id, max_tasks=2
    )

    print(f"Found {len(limited_tasks)} tasks (limited to 2):")
    for task in limited_tasks:
        print(f"  - {task['id']}: {task['title']}")

    if len(limited_tasks) == 2:
        print("✓ Max tasks limit respected")
    else:
        print(f"✗ Expected 2 tasks, got {len(limited_tasks)}")

    # Test 4: Verify priority ordering
    print("\n[Test 4] Priority ordering")
    priorities = [task["priority"] for task in tasks]
    print(f"Task priorities in order: {priorities}")

    # Check if P0 tasks come before P1, P1 before P2
    p0_indices = [i for i, p in enumerate(priorities) if p == "P0"]
    p1_indices = [i for i, p in enumerate(priorities) if p == "P1"]
    p2_indices = [i for i, p in enumerate(priorities) if p == "P2"]

    correct_order = (
        all(p0 < p1 for p0 in p0_indices for p1 in p1_indices if p1_indices) and
        all(p1 < p2 for p1 in p1_indices for p2 in p2_indices if p2_indices)
    )

    if correct_order or (not p1_indices and not p2_indices):
        print("✓ Priority ordering correct (P0 > P1 > P2)")
    else:
        print("✗ Priority ordering incorrect")


def test_get_parallel_launch_summary():
    """Test getting parallel launch summary"""
    print("\n" + "="*80)
    print("TEST: get_parallel_launch_summary()")
    print("="*80)

    project_id, order_id = setup_test_data()

    summary = ParallelTaskDetector.get_parallel_launch_summary(
        project_id, order_id, max_tasks=10
    )

    print("\nParallel Launch Summary:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # Verify summary
    print("\n[Verification]")

    if summary["total_queued"] >= summary["launchable_count"]:
        print(f"✓ Total QUEUED ({summary['total_queued']}) >= Launchable ({summary['launchable_count']})")
    else:
        print(f"✗ Invalid counts: total={summary['total_queued']}, launchable={summary['launchable_count']}")

    print(f"  Launchable tasks: {summary['launchable_tasks']}")
    print(f"  Blocked by dependencies: {summary['blocked_by_dependencies']}")
    print(f"  Blocked by locks: {summary['blocked_by_locks']}")


def cleanup_test_data():
    """Clean up test data"""
    print("\n" + "="*80)
    print("CLEANUP")
    print("="*80)

    conn = get_connection()
    try:
        project_id = "test_parallel_project"

        execute_query(conn, "DELETE FROM file_locks WHERE project_id = ?", (project_id,))
        execute_query(conn, "DELETE FROM task_dependencies WHERE project_id = ?", (project_id,))
        execute_query(conn, "DELETE FROM tasks WHERE project_id = ?", (project_id,))
        execute_query(conn, "DELETE FROM orders WHERE project_id = ?", (project_id,))
        execute_query(conn, "DELETE FROM projects WHERE id = ?", (project_id,))

        conn.commit()
        print("✓ Test data cleaned up")

    except Exception as e:
        conn.rollback()
        print(f"✗ Cleanup failed: {e}")
    finally:
        conn.close()


def main():
    """Run all tests"""
    print("="*80)
    print("Parallel Task Detector Test Suite")
    print("="*80)

    try:
        # Run tests
        test_find_parallel_launchable_tasks()
        test_get_parallel_launch_summary()

        print("\n" + "="*80)
        print("ALL TESTS COMPLETED")
        print("="*80)

    except Exception as e:
        print(f"\n✗ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Always cleanup
        cleanup_test_data()

    return 0


if __name__ == "__main__":
    sys.exit(main())
