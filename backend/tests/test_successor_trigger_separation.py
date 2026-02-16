#!/usr/bin/env python3
"""
Test: Successor Task Trigger Separation

Tests the separation of successor task triggering from the main Worker→Review cycle.

Test scenario:
1. Create a task with successors (dependencies)
2. Complete the task
3. Verify trigger_successors.py can be called independently
4. Verify successor tasks are correctly triggered (BLOCKED → QUEUED)
"""

import json
import subprocess
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.db import get_connection, execute_query, fetch_one, fetch_all
from task.create import create_task
from task.update import update_task
from review_queue.update import approve_review


def setup_test_scenario(project_id: str = "ai_pm_manager", order_id: str = "ORDER_084"):
    """
    Setup test scenario with task dependencies

    Creates:
    - TASK_900: Independent task (no dependencies)
    - TASK_901: Depends on TASK_900
    - TASK_902: Depends on TASK_900
    - TASK_903: Depends on TASK_901 and TASK_902
    """
    print("\n=== Setting up test scenario ===")

    # Clean up any existing test tasks
    conn = get_connection()
    try:
        execute_query(
            conn,
            """
            DELETE FROM tasks
            WHERE id IN ('TASK_900', 'TASK_901', 'TASK_902', 'TASK_903')
            AND project_id = ?
            """,
            (project_id,)
        )
        execute_query(
            conn,
            """
            DELETE FROM task_dependencies
            WHERE task_id IN ('TASK_900', 'TASK_901', 'TASK_902', 'TASK_903')
            AND project_id = ?
            """,
            (project_id,)
        )
        conn.commit()
        print("  Cleaned up existing test tasks")
    finally:
        conn.close()

    # Create TASK_900 (no dependencies)
    task_a = create_task(
        project_id,
        order_id,
        "Test Task 900 - Independent",
        task_id="TASK_900",
        description="Independent test task",
        priority="P0",
        depends_on=None,
        render=False,
    )
    print(f"  Created {task_a['id']}: {task_a['title']} (status={task_a['status']})")

    # Create TASK_901 (depends on TASK_900)
    task_b = create_task(
        project_id,
        order_id,
        "Test Task 901 - Depends on 900",
        task_id="TASK_901",
        description="Task depending on TASK_900",
        priority="P0",
        depends_on=["TASK_900"],
        render=False,
    )
    print(f"  Created {task_b['id']}: {task_b['title']} (status={task_b['status']})")

    # Create TASK_902 (depends on TASK_900)
    task_c = create_task(
        project_id,
        order_id,
        "Test Task 902 - Depends on 900",
        task_id="TASK_902",
        description="Task depending on TASK_900",
        priority="P0",
        depends_on=["TASK_900"],
        render=False,
    )
    print(f"  Created {task_c['id']}: {task_c['title']} (status={task_c['status']})")

    # Create TASK_903 (depends on TASK_901 and TASK_902)
    task_d = create_task(
        project_id,
        order_id,
        "Test Task 903 - Depends on 901 and 902",
        task_id="TASK_903",
        description="Task depending on TASK_901 and TASK_902",
        priority="P0",
        depends_on=["TASK_901", "TASK_902"],
        render=False,
    )
    print(f"  Created {task_d['id']}: {task_d['title']} (status={task_d['status']})")

    print("\nDependency graph:")
    print("  TASK_900 (QUEUED)")
    print("  ├─ TASK_901 (BLOCKED)")
    print("  │  └─ TASK_903 (BLOCKED)")
    print("  └─ TASK_902 (BLOCKED)")
    print("     └─ TASK_903 (BLOCKED)")

    return {
        "task_a": task_a,
        "task_b": task_b,
        "task_c": task_c,
        "task_d": task_d,
    }


def complete_task(project_id: str, task_id: str):
    """Complete a task (IN_PROGRESS → DONE → PENDING → APPROVED → COMPLETED)"""
    print(f"\n=== Completing {task_id} ===")

    # Step 1: QUEUED → IN_PROGRESS
    result = update_task(
        project_id,
        task_id,
        status="IN_PROGRESS",
        role="Worker",
        reason="Test task execution start",
        render=False,
    )
    print(f"  {task_id}: QUEUED → IN_PROGRESS")

    # Step 2: IN_PROGRESS → DONE
    result = update_task(
        project_id,
        task_id,
        status="DONE",
        role="Worker",
        reason="Test task execution complete",
        render=False,
    )
    print(f"  {task_id}: IN_PROGRESS → DONE")

    # Step 3: Add to review queue (DONE → PENDING)
    script_path = Path(__file__).resolve().parent.parent / "review_queue" / "add.py"
    subprocess.run(
        [sys.executable, str(script_path), project_id, task_id],
        capture_output=True,
        check=True,
    )
    print(f"  {task_id}: Added to review queue (PENDING)")

    # Step 4: Approve review (PENDING → IN_REVIEW → APPROVED → COMPLETED)
    approve_result = approve_review(
        project_id,
        task_id,
        reviewer="PM",
        comment="Test approval",
    )
    print(f"  {task_id}: Review approved → COMPLETED")

    return approve_result.success


def trigger_successors_script(project_id: str, task_id: str) -> dict:
    """Call trigger_successors.py script"""
    print(f"\n=== Triggering successors for {task_id} ===")

    script_path = Path(__file__).resolve().parent.parent / "task" / "trigger_successors.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            project_id,
            task_id,
            "--json",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  ERROR: Script failed with code {result.returncode}")
        print(f"  STDERR: {result.stderr}")
        return {"success": False, "error": result.stderr}

    output = json.loads(result.stdout)
    print(f"  Result: {output['message']}")

    if output.get("triggered_tasks"):
        print(f"  Triggered tasks:")
        for task in output["triggered_tasks"]:
            print(f"    - {task['task_id']}: {task['old_status']} → {task['new_status']}")

    return output


def check_task_status(project_id: str, task_id: str) -> str:
    """Get current task status"""
    conn = get_connection()
    try:
        task = fetch_one(
            conn,
            "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )
        return task["status"] if task else "NOT_FOUND"
    finally:
        conn.close()


def run_test():
    """Run the test"""
    print("=" * 80)
    print("Test: Successor Task Trigger Separation")
    print("=" * 80)

    project_id = "ai_pm_manager"
    order_id = "ORDER_084"

    try:
        # Setup test scenario
        tasks = setup_test_scenario(project_id, order_id)

        # Verify initial status
        print("\n=== Initial Status ===")
        for name, task in tasks.items():
            status = check_task_status(project_id, task["id"])
            print(f"  {task['id']}: {status}")

        # Complete TASK_900
        complete_task(project_id, "TASK_900")

        # Small delay to ensure DB updates are committed
        time.sleep(0.5)

        # Verify task is actually COMPLETED before triggering successors
        status_900 = check_task_status(project_id, "TASK_900")
        print(f"\nTask TASK_900 final status: {status_900}")

        # Trigger successors using the new script
        trigger_result = trigger_successors_script(project_id, "TASK_900")

        # Verify TASK_901 and TASK_902 are now QUEUED
        print("\n=== Status After TASK_900 Completion ===")
        status_b = check_task_status(project_id, "TASK_901")
        status_c = check_task_status(project_id, "TASK_902")
        status_d = check_task_status(project_id, "TASK_903")

        print(f"  TASK_900: COMPLETED")
        print(f"  TASK_901: {status_b}")
        print(f"  TASK_902: {status_c}")
        print(f"  TASK_903: {status_d}")

        # Test results
        print("\n=== Test Results ===")
        test_passed = True

        # Check trigger_result
        if not trigger_result.get("success"):
            print("  ✗ FAILED: trigger_successors.py failed")
            test_passed = False
        else:
            print("  ✓ PASSED: trigger_successors.py succeeded")

        # Check TASK_901 status
        if status_b != "QUEUED":
            print(f"  ✗ FAILED: TASK_901 status is {status_b}, expected QUEUED")
            test_passed = False
        else:
            print("  ✓ PASSED: TASK_901 status is QUEUED")

        # Check TASK_902 status
        if status_c != "QUEUED":
            print(f"  ✗ FAILED: TASK_902 status is {status_c}, expected QUEUED")
            test_passed = False
        else:
            print("  ✓ PASSED: TASK_902 status is QUEUED")

        # Check TASK_903 status (should still be BLOCKED)
        if status_d != "BLOCKED":
            print(f"  ✗ FAILED: TASK_903 status is {status_d}, expected BLOCKED")
            test_passed = False
        else:
            print("  ✓ PASSED: TASK_903 status is BLOCKED")

        # Final result
        print("\n" + "=" * 80)
        if test_passed:
            print("✓ ALL TESTS PASSED")
            print("=" * 80)
            return 0
        else:
            print("✗ SOME TESTS FAILED")
            print("=" * 80)
            return 1

    except Exception as e:
        print(f"\n✗ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_test())
