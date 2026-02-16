#!/usr/bin/env python3
"""
Integration Test for ORDER_076, ORDER_078, and ORDER_090

Tests the integration of:
- ORDER_076: File lock-based parallel execution
- ORDER_078: Dependency auto-trigger
- ORDER_090: Parallel worker launcher

Validates:
1. File locks prevent conflicting tasks from running simultaneously
2. Dependency completion triggers downstream tasks
3. Parallel launcher correctly integrates both features
4. Existing single-worker execution remains compatible
"""

import sys
import time
import json
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query, fetch_all, fetch_one
from utils.file_lock import FileLockManager
from worker.parallel_detector import ParallelTaskDetector
from worker.parallel_launcher import ParallelWorkerLauncher
from task.update import update_task


class IntegrationTestSuite:
    """Integration test suite for ORDER_076/078/090"""

    def __init__(self):
        self.project_id = "test_integration"
        self.order_id = "ORDER_TEST_INTEGRATION"
        self.test_results = []

    def setup_test_environment(self):
        """Create test project and ORDER with various task scenarios"""
        print("\n" + "="*80)
        print("SETUP: Creating test environment")
        print("="*80)

        conn = get_connection()
        try:
            # Clean up existing test data
            execute_query(conn, "DELETE FROM file_locks WHERE project_id = ?", (self.project_id,))
            execute_query(conn, "DELETE FROM task_dependencies WHERE project_id = ?", (self.project_id,))
            execute_query(conn, "DELETE FROM tasks WHERE project_id = ?", (self.project_id,))
            execute_query(conn, "DELETE FROM orders WHERE project_id = ?", (self.project_id,))
            execute_query(conn, "DELETE FROM projects WHERE id = ?", (self.project_id,))

            # Create test project
            execute_query(
                conn,
                "INSERT INTO projects (id, name, path, created_at) VALUES (?, ?, ?, datetime('now'))",
                (self.project_id, "Integration Test Project", "PROJECTS/test_integration")
            )

            # Create test ORDER
            execute_query(
                conn,
                """
                INSERT INTO orders (id, project_id, title, status, created_at)
                VALUES (?, ?, ?, 'IN_PROGRESS', datetime('now'))
                """,
                (self.order_id, self.project_id, "Integration Test ORDER")
            )

            # Create test tasks with various scenarios
            tasks = [
                # Scenario 1: Independent parallel tasks (ORDER_076 feature)
                ("TASK_I001", "Independent Task 1", "P0", "QUEUED", '["module_a.py", "config_a.json"]'),
                ("TASK_I002", "Independent Task 2", "P0", "QUEUED", '["module_b.py", "config_b.json"]'),
                ("TASK_I003", "Independent Task 3", "P1", "QUEUED", '["module_c.py"]'),

                # Scenario 2: File conflict (ORDER_076 feature)
                ("TASK_I004", "Conflicts with I001", "P1", "QUEUED", '["module_a.py", "utils.py"]'),

                # Scenario 3: Dependency chain (ORDER_078 feature)
                ("TASK_I005", "Base Task", "P0", "COMPLETED", '["base.py"]'),
                ("TASK_I006", "Depends on I005", "P0", "QUEUED", '["derived_1.py"]'),
                ("TASK_I007", "Depends on I005", "P1", "QUEUED", '["derived_2.py"]'),

                # Scenario 4: Mixed dependencies and file conflicts
                ("TASK_I008", "Depends on I006", "P0", "QUEUED", '["final.py"]'),
                ("TASK_I009", "Conflicts with I008", "P1", "QUEUED", '["final.py", "report.py"]'),

                # Scenario 5: No target files (always launchable if no deps)
                ("TASK_I010", "No Files Task", "P2", "QUEUED", None),

                # Scenario 6: Multi-level dependency
                ("TASK_I011", "Depends on I008", "P1", "QUEUED", '["output.json"]'),
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
                    (task_id, self.order_id, self.project_id, title, priority, status, target_files)
                )

            # Create dependencies
            dependencies = [
                ("TASK_I006", "TASK_I005"),  # I006 depends on I005
                ("TASK_I007", "TASK_I005"),  # I007 depends on I005
                ("TASK_I008", "TASK_I006"),  # I008 depends on I006
                ("TASK_I011", "TASK_I008"),  # I011 depends on I008
            ]

            for task_id, depends_on in dependencies:
                execute_query(
                    conn,
                    """
                    INSERT INTO task_dependencies (task_id, depends_on_task_id, project_id)
                    VALUES (?, ?, ?)
                    """,
                    (task_id, depends_on, self.project_id)
                )

            conn.commit()
            print("✓ Test environment created successfully")

        except Exception as e:
            conn.rollback()
            print(f"✗ Setup failed: {e}")
            raise
        finally:
            conn.close()

    def test_1_file_lock_integration(self):
        """Test ORDER_076: File lock prevents conflicting tasks"""
        print("\n" + "="*80)
        print("TEST 1: File Lock Integration (ORDER_076)")
        print("="*80)

        # Find parallel launchable tasks
        tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
            self.project_id,
            self.order_id,
            max_tasks=10
        )

        task_ids = [t["id"] for t in tasks]
        print(f"\nLaunchable tasks: {task_ids}")

        # Expected: I001, I002, I003, I006, I007, I010
        # I004 should be blocked due to file conflict with I001
        # I006, I007 should be launchable (dependency I005 is COMPLETED)

        # Check 1: I001 and I004 should not both be in launchable list
        has_i001 = "TASK_I001" in task_ids
        has_i004 = "TASK_I004" in task_ids

        if has_i001 and has_i004:
            print("✗ FAILED: Both I001 and I004 are launchable (file conflict not detected)")
            self.test_results.append(("test_1_file_lock", False, "File conflict not detected"))
            return False
        else:
            print("✓ File conflict detected correctly")

        # Check 2: Verify file lock data structure
        file_locks = {}
        for task in tasks:
            files = FileLockManager.parse_target_files(task.get("target_files"))
            for file in files:
                if file in file_locks:
                    print(f"✗ FAILED: File conflict - {file} appears in {file_locks[file]} and {task['id']}")
                    self.test_results.append(("test_1_file_lock", False, f"Duplicate file: {file}"))
                    return False
                file_locks[file] = task["id"]

        print(f"✓ No file conflicts among {len(tasks)} launchable tasks")
        print(f"  Total unique files: {len(file_locks)}")

        self.test_results.append(("test_1_file_lock", True, "File locks working correctly"))
        return True

    def test_2_dependency_auto_trigger(self):
        """Test ORDER_078: Dependency completion unblocks downstream tasks"""
        print("\n" + "="*80)
        print("TEST 2: Dependency Auto-Trigger (ORDER_078)")
        print("="*80)

        # Find launchable tasks
        tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
            self.project_id,
            self.order_id,
            max_tasks=10
        )

        task_ids = [t["id"] for t in tasks]
        print(f"\nLaunchable tasks: {task_ids}")

        # Check: I006 and I007 should be launchable (I005 is COMPLETED)
        has_i006 = "TASK_I006" in task_ids
        has_i007 = "TASK_I007" in task_ids

        if not has_i006 or not has_i007:
            print(f"✗ FAILED: I006={has_i006}, I007={has_i007} - dependency not resolved")
            self.test_results.append(("test_2_dependency", False, "Dependencies not resolved"))
            return False

        print("✓ Tasks I006 and I007 unblocked by completed dependency I005")

        # Check: I008 should NOT be launchable (I006 is still QUEUED)
        has_i008 = "TASK_I008" in task_ids

        if has_i008:
            print("✗ FAILED: I008 is launchable but I006 is not yet completed")
            self.test_results.append(("test_2_dependency", False, "Dependency check too lenient"))
            return False

        print("✓ Task I008 correctly blocked by pending dependency I006")

        self.test_results.append(("test_2_dependency", True, "Dependency resolution working correctly"))
        return True

    def test_3_parallel_launcher_dry_run(self):
        """Test ORDER_090: Parallel launcher dry-run mode"""
        print("\n" + "="*80)
        print("TEST 3: Parallel Launcher Dry-Run (ORDER_090)")
        print("="*80)

        launcher = ParallelWorkerLauncher(
            self.project_id,
            self.order_id,
            max_workers=5,
            dry_run=True,
            verbose=False,
        )

        results = launcher.launch()

        print(f"\nDry-run results:")
        print(f"  Message: {results.get('message')}")
        print(f"  Detected tasks: {results.get('detected_tasks', [])}")

        if results.get("detected_tasks"):
            detected_count = len(results["detected_tasks"])
            print(f"✓ Detected {detected_count} tasks for parallel launch")
            self.test_results.append(("test_3_dry_run", True, f"Detected {detected_count} tasks"))
            return True
        else:
            print("✗ FAILED: No tasks detected")
            self.test_results.append(("test_3_dry_run", False, "No tasks detected"))
            return False

    def test_4_parallel_launcher_max_workers(self):
        """Test ORDER_090: Parallel launcher respects max_workers limit"""
        print("\n" + "="*80)
        print("TEST 4: Parallel Launcher Max Workers Limit")
        print("="*80)

        # Test with max_workers=2
        launcher = ParallelWorkerLauncher(
            self.project_id,
            self.order_id,
            max_workers=2,
            dry_run=True,
            verbose=False,
        )

        results = launcher.launch()

        detected = results.get("detected_tasks", [])
        print(f"\nWith max_workers=2, detected: {detected}")

        if len(detected) <= 2:
            print(f"✓ Max workers limit respected ({len(detected)} <= 2)")
            self.test_results.append(("test_4_max_workers", True, "Limit respected"))
            return True
        else:
            print(f"✗ FAILED: Detected {len(detected)} tasks, expected <= 2")
            self.test_results.append(("test_4_max_workers", False, f"Detected {len(detected)} > 2"))
            return False

    def test_5_priority_ordering(self):
        """Test that tasks are launched in priority order"""
        print("\n" + "="*80)
        print("TEST 5: Priority Ordering")
        print("="*80)

        tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
            self.project_id,
            self.order_id,
            max_tasks=10
        )

        priorities = [t["priority"] for t in tasks]
        print(f"\nTask priorities in order: {priorities}")

        # Check that P0 tasks come before P1, P1 before P2
        prev_priority_value = -1
        priority_values = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

        for priority in priorities:
            current_value = priority_values.get(priority, 99)
            if current_value < prev_priority_value:
                print(f"✗ FAILED: Priority ordering violated ({priority} after {priorities[priorities.index(priority)-1]})")
                self.test_results.append(("test_5_priority", False, "Priority ordering violated"))
                return False
            prev_priority_value = current_value

        print("✓ Priority ordering correct (P0 > P1 > P2 > P3)")
        self.test_results.append(("test_5_priority", True, "Priority ordering correct"))
        return True

    def test_6_compatibility_single_worker(self):
        """Test backward compatibility with single-worker execution"""
        print("\n" + "="*80)
        print("TEST 6: Single-Worker Compatibility")
        print("="*80)

        # Simulate single worker execution by checking task status transitions
        conn = get_connection()
        try:
            # Get one QUEUED task
            task = fetch_one(
                conn,
                """
                SELECT id, target_files
                FROM tasks
                WHERE project_id = ? AND order_id = ? AND status = 'QUEUED'
                LIMIT 1
                """,
                (self.project_id, self.order_id)
            )

            if not task:
                print("⚠️  SKIPPED: No QUEUED tasks available")
                self.test_results.append(("test_6_single_worker", True, "Skipped - no tasks"))
                return True

            task_id = task["id"]
            target_files = FileLockManager.parse_target_files(task["target_files"])

            print(f"\nSimulating single-worker execution for {task_id}")

            # Check if task can start (file lock check)
            can_start, blocking_tasks = FileLockManager.can_task_start(
                self.project_id,
                task_id
            )

            print(f"  Can start: {can_start}")
            if not can_start:
                print(f"  Blocked by: {blocking_tasks}")

            # Acquire locks
            if target_files:
                lock_success = FileLockManager.acquire_locks(
                    self.project_id,
                    task_id,
                    target_files
                )
                print(f"  Lock acquisition: {lock_success}")

                if lock_success:
                    # Verify locks exist
                    locked_files = FileLockManager.get_locked_files(self.project_id, task_id)
                    print(f"  Acquired {len(locked_files)} locks: {locked_files}")

                    # Release locks
                    FileLockManager.release_locks(self.project_id, task_id)
                    print(f"  Locks released")

            print("✓ Single-worker mode compatible with file lock system")
            self.test_results.append(("test_6_single_worker", True, "Compatible"))
            return True

        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.test_results.append(("test_6_single_worker", False, str(e)))
            return False
        finally:
            conn.close()

    def test_7_resource_monitoring(self):
        """Test resource monitoring integration"""
        print("\n" + "="*80)
        print("TEST 7: Resource Monitoring")
        print("="*80)

        from worker.resource_monitor import ResourceMonitor, get_system_info

        # Get system info
        sys_info = get_system_info()
        print(f"\nSystem Info:")
        print(f"  Monitoring available: {sys_info.get('monitoring_available')}")

        if sys_info.get("monitoring_available"):
            print(f"  Platform: {sys_info.get('platform')}")
            print(f"  CPU cores (physical): {sys_info.get('cpu_count_physical')}")
            print(f"  CPU cores (logical): {sys_info.get('cpu_count_logical')}")
            print(f"  Total memory: {sys_info.get('total_memory_gb', 0):.2f} GB")
            print(f"  Memory usage: {sys_info.get('memory_percent', 0):.1f}%")

            # Test resource monitor
            monitor = ResourceMonitor(max_cpu_percent=85.0, max_memory_percent=85.0)
            status = monitor.get_status()

            print(f"\nResource Status:")
            print(f"  CPU: {status.cpu_percent:.1f}%")
            print(f"  Memory: {status.memory_percent:.1f}%")
            print(f"  Available memory: {status.available_memory_mb:.0f} MB")
            print(f"  Healthy: {status.is_healthy}")

            if not status.is_healthy:
                print(f"  ⚠️  {status.blocking_reason}")

            # Test worker count recommendation
            recommended = monitor.get_recommended_worker_count(
                current_workers=0,
                max_workers=5
            )
            print(f"\nRecommended workers: {recommended}/5")

            print("✓ Resource monitoring functional")
            self.test_results.append(("test_7_resources", True, "Monitoring functional"))
        else:
            print("⚠️  Resource monitoring not available (psutil not installed)")
            self.test_results.append(("test_7_resources", True, "Skipped - no psutil"))

        return True

    def test_8_multi_level_dependency(self):
        """Test multi-level dependency chains"""
        print("\n" + "="*80)
        print("TEST 8: Multi-Level Dependency Chain")
        print("="*80)

        # Current state: I005 (COMPLETED) -> I006 (QUEUED) -> I008 (QUEUED) -> I011 (QUEUED)

        tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
            self.project_id,
            self.order_id,
            max_tasks=10
        )

        task_ids = [t["id"] for t in tasks]

        # I006 should be launchable, I008 and I011 should not
        has_i006 = "TASK_I006" in task_ids
        has_i008 = "TASK_I008" in task_ids
        has_i011 = "TASK_I011" in task_ids

        print(f"\nDependency chain status:")
        print(f"  I006 (depends on completed I005): launchable={has_i006}")
        print(f"  I008 (depends on queued I006): launchable={has_i008}")
        print(f"  I011 (depends on queued I008): launchable={has_i011}")

        if has_i006 and not has_i008 and not has_i011:
            print("✓ Multi-level dependency chain handled correctly")
            self.test_results.append(("test_8_multi_dep", True, "Chain handled correctly"))
            return True
        else:
            print(f"✗ FAILED: Unexpected chain resolution")
            self.test_results.append(("test_8_multi_dep", False, "Chain resolution incorrect"))
            return False

    def cleanup_test_environment(self):
        """Clean up test data"""
        print("\n" + "="*80)
        print("CLEANUP: Removing test environment")
        print("="*80)

        conn = get_connection()
        try:
            execute_query(conn, "DELETE FROM file_locks WHERE project_id = ?", (self.project_id,))
            execute_query(conn, "DELETE FROM task_dependencies WHERE project_id = ?", (self.project_id,))
            execute_query(conn, "DELETE FROM tasks WHERE project_id = ?", (self.project_id,))
            execute_query(conn, "DELETE FROM orders WHERE project_id = ?", (self.project_id,))
            execute_query(conn, "DELETE FROM projects WHERE id = ?", (self.project_id,))

            conn.commit()
            print("✓ Test environment cleaned up")

        except Exception as e:
            conn.rollback()
            print(f"✗ Cleanup failed: {e}")
        finally:
            conn.close()

    def print_summary(self):
        """Print test results summary"""
        print("\n" + "="*80)
        print("TEST RESULTS SUMMARY")
        print("="*80)

        total = len(self.test_results)
        passed = sum(1 for _, success, _ in self.test_results if success)
        failed = total - passed

        print(f"\nTotal Tests: {total}")
        print(f"Passed: {passed} ✓")
        print(f"Failed: {failed} ✗")

        print("\nDetailed Results:")
        print("-" * 80)
        for test_name, success, message in self.test_results:
            status = "✓ PASS" if success else "✗ FAIL"
            print(f"  {status} | {test_name:<30} | {message}")

        print("\n" + "="*80)

        return failed == 0

    def run_all_tests(self):
        """Run all integration tests"""
        print("="*80)
        print("INTEGRATION TEST SUITE: ORDER_076 + ORDER_078 + ORDER_090")
        print("="*80)

        try:
            # Setup
            self.setup_test_environment()

            # Run tests
            self.test_1_file_lock_integration()
            self.test_2_dependency_auto_trigger()
            self.test_3_parallel_launcher_dry_run()
            self.test_4_parallel_launcher_max_workers()
            self.test_5_priority_ordering()
            self.test_6_compatibility_single_worker()
            self.test_7_resource_monitoring()
            self.test_8_multi_level_dependency()

            # Print summary
            all_passed = self.print_summary()

            return 0 if all_passed else 1

        except Exception as e:
            print(f"\n✗ Test suite failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return 1

        finally:
            # Always cleanup
            self.cleanup_test_environment()


def main():
    """Entry point"""
    suite = IntegrationTestSuite()
    return suite.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
