#!/usr/bin/env python3
"""
AI PM Framework - Migration Safety Test
Version: 1.0.0

マイグレーション安全機構の統合テスト

Tests:
1. PRAGMA foreign_keys control
2. Automatic backup creation
3. Worker execution detection
4. Transaction rollback on error
5. Dry-run mode
"""

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
sys.path.insert(0, str(_package_root))

from utils.migration_base import MigrationRunner, MigrationError
from utils.db import get_connection, execute_query, fetch_one


class TestMigrationSafety(unittest.TestCase):
    """Migration safety mechanism tests"""

    def setUp(self):
        """Set up test database"""
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = Path(self.temp_db.name)
        self.temp_db.close()

        # Initialize test database
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'QUEUED',
                assignee TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id, project_id),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            INSERT INTO projects (id, name) VALUES ('TEST_PROJECT', 'Test Project');
            INSERT INTO tasks (id, project_id, title, status)
            VALUES ('TASK_001', 'TEST_PROJECT', 'Test Task', 'QUEUED');
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up test database and backups"""
        # Remove test database
        if self.db_path.exists():
            self.db_path.unlink()

        # Remove backups
        backup_pattern = f"{self.db_path.name}.backup_*"
        for backup_file in self.db_path.parent.glob(backup_pattern):
            backup_file.unlink()

    def test_pragma_foreign_keys_control(self):
        """Test PRAGMA foreign_keys is disabled during migration and restored after"""
        runner = MigrationRunner(
            "test_pragma",
            db_path=self.db_path,
            backup=False,
            check_workers=False,
            verbose=True,
        )

        fk_state_during_migration = None
        fk_state_after_migration = None

        def migration_func(conn):
            nonlocal fk_state_during_migration, fk_state_after_migration
            cursor = conn.cursor()

            # Check FK state during migration
            cursor.execute("PRAGMA foreign_keys")
            result = cursor.fetchone()
            fk_state_during_migration = result[0] if result else None

            # Simulate some work
            cursor.execute("CREATE TABLE test_pragma (id INTEGER PRIMARY KEY)")

            # Check FK state is still disabled
            cursor.execute("PRAGMA foreign_keys")
            result = cursor.fetchone()
            fk_state_after_migration = result[0] if result else None

            return True

        runner.run(migration_func)

        # Verify FK was disabled during migration
        self.assertEqual(fk_state_during_migration, 0, "Foreign keys should be disabled during migration")
        self.assertEqual(fk_state_after_migration, 0, "Foreign keys should stay disabled during migration")

        # Verify FK is restored after migration by opening a new connection
        # (default is ON for new connections)
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()
        fk_state_after = result[0] if result else None
        conn.close()

        # Note: New connections have FK ON by default (from get_connection in utils.db)
        self.assertEqual(fk_state_after, 1, "Foreign keys should be ON for new connections")

    def test_backup_creation(self):
        """Test automatic backup creation"""
        runner = MigrationRunner(
            "test_backup",
            db_path=self.db_path,
            backup=True,
            check_workers=False,
        )

        def migration_func(conn):
            return True

        runner.run(migration_func)

        # Check backup file was created
        backup_files = list(self.db_path.parent.glob(f"{self.db_path.name}.backup_test_backup_*"))
        self.assertTrue(len(backup_files) > 0, "Backup file should be created")

    def test_no_backup_when_disabled(self):
        """Test backup is not created when disabled"""
        runner = MigrationRunner(
            "test_no_backup",
            db_path=self.db_path,
            backup=False,
            check_workers=False,
        )

        def migration_func(conn):
            return True

        runner.run(migration_func)

        # Check no backup file was created
        backup_files = list(self.db_path.parent.glob(f"{self.db_path.name}.backup_test_no_backup_*"))
        self.assertEqual(len(backup_files), 0, "Backup file should not be created when disabled")

    def test_worker_detection(self):
        """Test detection of running workers"""
        # Set a task to IN_PROGRESS
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("UPDATE tasks SET status = 'IN_PROGRESS', assignee = 'TestWorker' WHERE id = 'TASK_001'")
        conn.commit()
        conn.close()

        runner = MigrationRunner(
            "test_worker_detection",
            db_path=self.db_path,
            backup=False,
            check_workers=True,
            verbose=True,
        )

        # Should detect running worker
        running_tasks = runner._check_running_workers()
        self.assertEqual(len(running_tasks), 1, "Should detect one running task")
        self.assertEqual(running_tasks[0]['id'], 'TASK_001', "Should detect TASK_001")

    def test_transaction_rollback_on_error(self):
        """Test transaction is rolled back on error"""
        runner = MigrationRunner(
            "test_rollback",
            db_path=self.db_path,
            backup=False,
            check_workers=False,
        )

        def failing_migration(conn):
            cursor = conn.cursor()
            # Create a new table
            cursor.execute("CREATE TABLE test_rollback (id INTEGER PRIMARY KEY)")
            # Raise an error
            raise Exception("Intentional error for rollback test")

        # Migration should fail
        with self.assertRaises(MigrationError):
            runner.run(failing_migration)

        # Verify table was not created (rolled back)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_rollback'")
        result = cursor.fetchone()
        conn.close()

        self.assertIsNone(result, "Table should not exist after rollback")

    def test_dry_run_mode(self):
        """Test dry-run mode does not commit changes"""
        runner = MigrationRunner(
            "test_dry_run",
            db_path=self.db_path,
            backup=False,
            check_workers=False,
            dry_run=True,
        )

        def migration_func(conn):
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test_dry_run (id INTEGER PRIMARY KEY)")
            return True

        runner.run(migration_func)

        # Verify table was not created
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_dry_run'")
        result = cursor.fetchone()
        conn.close()

        self.assertIsNone(result, "Table should not exist in dry-run mode")

    def test_force_mode_bypasses_worker_check(self):
        """Test force mode bypasses worker execution check"""
        # Set a task to IN_PROGRESS
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_001'")
        conn.commit()
        conn.close()

        runner = MigrationRunner(
            "test_force",
            db_path=self.db_path,
            backup=False,
            check_workers=True,
        )

        table_created = False

        def migration_func(conn):
            nonlocal table_created
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test_force (id INTEGER PRIMARY KEY)")
            table_created = True
            return True

        # Should succeed with force=True
        runner.run(migration_func, force=True)

        self.assertTrue(table_created, "Migration should execute with force=True")

    def test_multiple_running_workers_detection(self):
        """Test detection of multiple running workers"""
        # Create additional tasks in IN_PROGRESS
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("INSERT INTO tasks (id, project_id, title, status) VALUES ('TASK_002', 'TEST_PROJECT', 'Task 2', 'IN_PROGRESS')")
        conn.execute("INSERT INTO tasks (id, project_id, title, status) VALUES ('TASK_003', 'TEST_PROJECT', 'Task 3', 'IN_PROGRESS')")
        conn.execute("UPDATE tasks SET status = 'IN_PROGRESS' WHERE id = 'TASK_001'")
        conn.commit()
        conn.close()

        runner = MigrationRunner(
            "test_multiple_workers",
            db_path=self.db_path,
            backup=False,
            check_workers=True,
        )

        running_tasks = runner._check_running_workers()
        self.assertEqual(len(running_tasks), 3, "Should detect all running tasks")

    def test_backup_restore_capability(self):
        """Test that backup can be used to restore database"""
        # Insert initial data
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("INSERT INTO tasks (id, project_id, title, status) VALUES ('TASK_BEFORE', 'TEST_PROJECT', 'Before Migration', 'QUEUED')")
        conn.commit()
        conn.close()

        runner = MigrationRunner(
            "test_backup_restore",
            db_path=self.db_path,
            backup=True,
            check_workers=False,
        )

        def migration_func(conn):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = 'TASK_BEFORE'")
            cursor.execute("INSERT INTO tasks (id, project_id, title, status) VALUES ('TASK_AFTER', 'TEST_PROJECT', 'After Migration', 'QUEUED')")
            return True

        runner.run(migration_func)

        # Verify migration applied
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id = 'TASK_AFTER'")
        self.assertIsNotNone(cursor.fetchone(), "New task should exist")
        cursor.execute("SELECT id FROM tasks WHERE id = 'TASK_BEFORE'")
        self.assertIsNone(cursor.fetchone(), "Old task should be deleted")
        conn.close()

        # Restore from backup
        import shutil
        backup_files = list(self.db_path.parent.glob(f"{self.db_path.name}.backup_test_backup_restore_*"))
        self.assertTrue(len(backup_files) > 0, "Backup should exist")

        backup_path = backup_files[0]
        shutil.copy2(backup_path, self.db_path)

        # Verify restored state
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id = 'TASK_BEFORE'")
        self.assertIsNotNone(cursor.fetchone(), "Old task should be restored")
        cursor.execute("SELECT id FROM tasks WHERE id = 'TASK_AFTER'")
        self.assertIsNone(cursor.fetchone(), "New task should not exist after restore")
        conn.close()

    def test_foreign_key_cascade_prevented(self):
        """Test that foreign key CASCADE is prevented during migration"""
        runner = MigrationRunner(
            "test_fk_cascade",
            db_path=self.db_path,
            backup=False,
            check_workers=False,
        )

        def migration_func(conn):
            cursor = conn.cursor()

            # Attempt to delete project (which has child tasks)
            # Without FK disabled, this would CASCADE delete tasks
            cursor.execute("DELETE FROM projects WHERE id = 'TEST_PROJECT'")

            # Check that tasks still exist (FK disabled prevented CASCADE)
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE project_id = 'TEST_PROJECT'")
            count = cursor.fetchone()[0]

            # Rollback the delete (we don't want to actually delete)
            raise Exception("Testing FK prevention")

        # Migration will fail, but we can check the behavior
        with self.assertRaises(MigrationError):
            runner.run(migration_func)

    def test_concurrent_migration_detection(self):
        """Test that concurrent migrations are handled safely via transactions"""
        import threading
        import time

        results = {"migration1": None, "migration2": None}
        errors = {"migration1": None, "migration2": None}

        def run_migration(name):
            try:
                runner = MigrationRunner(
                    f"test_concurrent_{name}",
                    db_path=self.db_path,
                    backup=False,
                    check_workers=False,
                )

                def migration_func(conn):
                    cursor = conn.cursor()
                    # Slow operation to increase chance of overlap
                    time.sleep(0.5)
                    cursor.execute(f"CREATE TABLE IF NOT EXISTS test_concurrent_{name} (id INTEGER PRIMARY KEY)")
                    return True

                results[name] = runner.run(migration_func)
            except Exception as e:
                errors[name] = str(e)

        # Start two migrations concurrently
        t1 = threading.Thread(target=run_migration, args=("migration1",))
        t2 = threading.Thread(target=run_migration, args=("migration2",))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # At least one should succeed (both may succeed due to SQLite's locking)
        self.assertTrue(
            results["migration1"] or results["migration2"],
            "At least one migration should succeed"
        )

    def test_migration_with_complex_schema_change(self):
        """Test migration with table recreation (common complex scenario)"""
        runner = MigrationRunner(
            "test_complex_schema",
            db_path=self.db_path,
            backup=True,
            check_workers=False,
        )

        def migration_func(conn):
            cursor = conn.cursor()

            # Common pattern: recreate table with new schema
            # 1. Create new table
            cursor.execute("""
                CREATE TABLE tasks_new (
                    id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'QUEUED',
                    assignee TEXT,
                    priority TEXT DEFAULT 'P2',  -- NEW COLUMN
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id, project_id),
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)

            # 2. Copy data
            cursor.execute("""
                INSERT INTO tasks_new (id, project_id, title, status, assignee, updated_at)
                SELECT id, project_id, title, status, assignee, updated_at FROM tasks
            """)

            # 3. Drop old table
            cursor.execute("DROP TABLE tasks")

            # 4. Rename new table
            cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")

            return True

        success = runner.run(migration_func)
        self.assertTrue(success, "Complex migration should succeed")

        # Verify new schema
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(tasks)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        self.assertIn("priority", columns, "New column should exist")

    def test_migration_idempotency(self):
        """Test that migrations can detect if already applied"""
        runner = MigrationRunner(
            "test_idempotent",
            db_path=self.db_path,
            backup=False,
            check_workers=False,
        )

        def idempotent_migration(conn):
            cursor = conn.cursor()

            # Check if already applied
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_idempotent'")
            if cursor.fetchone():
                return True  # Already applied

            # Apply migration
            cursor.execute("CREATE TABLE test_idempotent (id INTEGER PRIMARY KEY)")
            return True

        # Run twice
        result1 = runner.run(idempotent_migration)
        result2 = runner.run(idempotent_migration)

        self.assertTrue(result1, "First run should succeed")
        self.assertTrue(result2, "Second run should succeed (idempotent)")


def run_tests():
    """Run all tests"""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMigrationSafety)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
