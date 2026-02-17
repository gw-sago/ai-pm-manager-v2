#!/usr/bin/env python3
"""
AI PM Framework - Migration Test Suite
Version: 2.0.0

Tests for composite key migration functionality.
Verifies:
1. Migration from single-key to composite-key schema
2. Multi-project ORDER ID coexistence
3. Foreign key constraint enforcement
4. Data integrity after migration
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from migrations.composite_key_migration import (
    is_composite_key_migrated,
    run_migration,
    check_migration_status,
    get_table_schema,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def test_db_path():
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def old_schema_db(test_db_path):
    """Create a database with the old (single-key) schema."""
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    # Create old schema (single primary key)
    cursor.executescript("""
        -- Projects table
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'INITIAL',
            current_order_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Orders table (OLD - single primary key)
        CREATE TABLE orders (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            priority TEXT DEFAULT 'P1',
            status TEXT NOT NULL DEFAULT 'PLANNING',
            started_at DATETIME,
            completed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        -- Tasks table (OLD - single primary key, no project_id column)
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT DEFAULT 'P1',
            status TEXT NOT NULL DEFAULT 'QUEUED',
            recommended_model TEXT DEFAULT 'Opus',
            assignee TEXT,
            started_at DATETIME,
            completed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        );

        -- Task dependencies (OLD - no project_id)
        CREATE TABLE task_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            depends_on_task_id TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            UNIQUE (task_id, depends_on_task_id)
        );
    """)

    conn.commit()
    conn.close()
    return test_db_path


@pytest.fixture
def old_schema_db_with_data(old_schema_db):
    """Create a database with old schema and test data."""
    conn = sqlite3.connect(old_schema_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    # Insert test data
    cursor.executescript("""
        -- Projects
        INSERT INTO projects (id, name, path) VALUES ('PROJECT_A', 'Project A', '/projects/a');
        INSERT INTO projects (id, name, path) VALUES ('PROJECT_B', 'Project B', '/projects/b');

        -- Orders (using globally unique IDs for old schema)
        INSERT INTO orders (id, project_id, title, status) VALUES ('ORDER_001_A', 'PROJECT_A', 'Order 1 for A', 'IN_PROGRESS');
        INSERT INTO orders (id, project_id, title, status) VALUES ('ORDER_002_A', 'PROJECT_A', 'Order 2 for A', 'PLANNING');
        INSERT INTO orders (id, project_id, title, status) VALUES ('ORDER_001_B', 'PROJECT_B', 'Order 1 for B', 'IN_PROGRESS');

        -- Tasks
        INSERT INTO tasks (id, order_id, title, status) VALUES ('TASK_001_A', 'ORDER_001_A', 'Task 1 for A', 'COMPLETED');
        INSERT INTO tasks (id, order_id, title, status) VALUES ('TASK_002_A', 'ORDER_001_A', 'Task 2 for A', 'IN_PROGRESS');
        INSERT INTO tasks (id, order_id, title, status) VALUES ('TASK_001_B', 'ORDER_001_B', 'Task 1 for B', 'QUEUED');

        -- Dependencies
        INSERT INTO task_dependencies (task_id, depends_on_task_id) VALUES ('TASK_002_A', 'TASK_001_A');
    """)

    conn.commit()
    conn.close()
    return old_schema_db


@pytest.fixture
def new_schema_db(test_db_path):
    """Create a database with the new (composite-key) schema."""
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    # Create new schema (composite primary key)
    cursor.executescript("""
        -- Projects table
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'INITIAL',
            current_order_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Orders table (NEW - composite primary key)
        CREATE TABLE orders (
            id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            priority TEXT DEFAULT 'P1',
            status TEXT NOT NULL DEFAULT 'PLANNING',
            started_at DATETIME,
            completed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, project_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        -- Tasks table (NEW - composite primary key with project_id)
        CREATE TABLE tasks (
            id TEXT NOT NULL,
            order_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT DEFAULT 'P1',
            status TEXT NOT NULL DEFAULT 'QUEUED',
            recommended_model TEXT DEFAULT 'Opus',
            assignee TEXT,
            started_at DATETIME,
            completed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, project_id),
            FOREIGN KEY (order_id, project_id) REFERENCES orders(id, project_id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        -- Task dependencies (NEW - with project_id)
        CREATE TABLE task_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            depends_on_task_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
            FOREIGN KEY (depends_on_task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
            UNIQUE (task_id, depends_on_task_id, project_id)
        );
    """)

    conn.commit()
    conn.close()
    return test_db_path


# ============================================================================
# Test: Migration Status Detection
# ============================================================================

class TestMigrationStatusDetection:
    """Tests for detecting migration status."""

    def test_detect_old_schema(self, old_schema_db):
        """Old schema should be detected as not migrated."""
        conn = sqlite3.connect(old_schema_db)
        cursor = conn.cursor()

        status = is_composite_key_migrated(cursor)

        assert status['orders'] == False
        assert status['tasks'] == False
        assert status['task_dependencies'] == False
        assert status['overall'] == False

        conn.close()

    def test_detect_new_schema(self, new_schema_db):
        """New schema should be detected as migrated."""
        conn = sqlite3.connect(new_schema_db)
        cursor = conn.cursor()

        status = is_composite_key_migrated(cursor)

        assert status['orders'] == True
        assert status['tasks'] == True
        assert status['task_dependencies'] == True
        assert status['overall'] == True

        conn.close()

    def test_check_migration_status_api(self, old_schema_db):
        """check_migration_status() should return correct status."""
        status = check_migration_status(old_schema_db)

        assert 'error' not in status
        assert status['overall'] == False

    def test_check_migration_status_nonexistent_db(self):
        """check_migration_status() should handle nonexistent database."""
        status = check_migration_status('/nonexistent/path/db.sqlite')

        assert 'error' in status


# ============================================================================
# Test: Migration Execution
# ============================================================================

class TestMigrationExecution:
    """Tests for migration execution."""

    def test_migrate_empty_db(self, old_schema_db):
        """Migration should work on empty database."""
        success = run_migration(old_schema_db, backup=False, force=True)

        assert success == True

        # Verify migration
        conn = sqlite3.connect(old_schema_db)
        cursor = conn.cursor()
        status = is_composite_key_migrated(cursor)

        assert status['overall'] == True
        conn.close()

    def test_migrate_with_data(self, old_schema_db_with_data):
        """Migration should preserve existing data."""
        # Get counts before migration
        conn = sqlite3.connect(old_schema_db_with_data)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM projects")
        project_count_before = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders")
        order_count_before = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks")
        task_count_before = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM task_dependencies")
        dep_count_before = cursor.fetchone()[0]
        conn.close()

        # Run migration
        success = run_migration(old_schema_db_with_data, backup=False, force=True)

        assert success == True

        # Get counts after migration
        conn = sqlite3.connect(old_schema_db_with_data)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM projects")
        project_count_after = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders")
        order_count_after = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks")
        task_count_after = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM task_dependencies")
        dep_count_after = cursor.fetchone()[0]
        conn.close()

        # Verify data preservation
        assert project_count_after == project_count_before
        assert order_count_after == order_count_before
        assert task_count_after == task_count_before
        assert dep_count_after == dep_count_before

    def test_migrate_already_migrated(self, new_schema_db):
        """Migration should skip already migrated database."""
        success = run_migration(new_schema_db, backup=False, force=True)

        assert success == True  # Should succeed but skip migration

    def test_dry_run_mode(self, old_schema_db_with_data):
        """Dry run should not modify database."""
        # Run dry run
        success = run_migration(old_schema_db_with_data, backup=False, dry_run=True)

        assert success == True

        # Verify not migrated
        conn = sqlite3.connect(old_schema_db_with_data)
        cursor = conn.cursor()
        status = is_composite_key_migrated(cursor)

        assert status['overall'] == False
        conn.close()


# ============================================================================
# Test: Multi-Project ORDER ID Coexistence
# ============================================================================

class TestMultiProjectCoexistence:
    """Tests for multi-project ORDER ID coexistence."""

    def test_same_order_id_different_projects(self, new_schema_db):
        """Same ORDER ID should work in different projects."""
        conn = sqlite3.connect(new_schema_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # Insert projects
        cursor.execute("INSERT INTO projects (id, name, path) VALUES ('PROJECT_A', 'A', '/a')")
        cursor.execute("INSERT INTO projects (id, name, path) VALUES ('PROJECT_B', 'B', '/b')")

        # Insert same ORDER_001 in both projects
        cursor.execute("""
            INSERT INTO orders (id, project_id, title)
            VALUES ('ORDER_001', 'PROJECT_A', 'Order 1 in A')
        """)
        cursor.execute("""
            INSERT INTO orders (id, project_id, title)
            VALUES ('ORDER_001', 'PROJECT_B', 'Order 1 in B')
        """)

        conn.commit()

        # Verify both exist
        cursor.execute("SELECT COUNT(*) FROM orders WHERE id = 'ORDER_001'")
        count = cursor.fetchone()[0]

        assert count == 2

        conn.close()

    def test_same_task_id_different_projects(self, new_schema_db):
        """Same TASK ID should work in different projects."""
        conn = sqlite3.connect(new_schema_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # Setup
        cursor.execute("INSERT INTO projects (id, name, path) VALUES ('PROJECT_A', 'A', '/a')")
        cursor.execute("INSERT INTO projects (id, name, path) VALUES ('PROJECT_B', 'B', '/b')")
        cursor.execute("INSERT INTO orders (id, project_id, title) VALUES ('ORDER_001', 'PROJECT_A', 'O1A')")
        cursor.execute("INSERT INTO orders (id, project_id, title) VALUES ('ORDER_001', 'PROJECT_B', 'O1B')")

        # Insert same TASK_001 in both projects
        cursor.execute("""
            INSERT INTO tasks (id, order_id, project_id, title)
            VALUES ('TASK_001', 'ORDER_001', 'PROJECT_A', 'Task 1 in A')
        """)
        cursor.execute("""
            INSERT INTO tasks (id, order_id, project_id, title)
            VALUES ('TASK_001', 'ORDER_001', 'PROJECT_B', 'Task 1 in B')
        """)

        conn.commit()

        # Verify both exist
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE id = 'TASK_001'")
        count = cursor.fetchone()[0]

        assert count == 2

        conn.close()


# ============================================================================
# Test: Foreign Key Constraints
# ============================================================================

class TestForeignKeyConstraints:
    """Tests for foreign key constraint enforcement."""

    def test_order_requires_valid_project(self, new_schema_db):
        """ORDER should require valid project_id."""
        conn = sqlite3.connect(new_schema_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO orders (id, project_id, title)
                VALUES ('ORDER_001', 'NONEXISTENT', 'Test Order')
            """)

        conn.close()

    def test_task_requires_valid_order(self, new_schema_db):
        """TASK should require valid order_id with matching project_id."""
        conn = sqlite3.connect(new_schema_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # Setup
        cursor.execute("INSERT INTO projects (id, name, path) VALUES ('PROJECT_A', 'A', '/a')")
        cursor.execute("INSERT INTO orders (id, project_id, title) VALUES ('ORDER_001', 'PROJECT_A', 'O1A')")
        conn.commit()

        # Try to insert task with wrong project_id
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO tasks (id, order_id, project_id, title)
                VALUES ('TASK_001', 'ORDER_001', 'WRONG_PROJECT', 'Test')
            """)

        conn.close()

    def test_task_dependency_requires_valid_tasks(self, new_schema_db):
        """Task dependency should require valid task_id with matching project_id."""
        conn = sqlite3.connect(new_schema_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # Setup
        cursor.execute("INSERT INTO projects (id, name, path) VALUES ('PROJECT_A', 'A', '/a')")
        cursor.execute("INSERT INTO orders (id, project_id, title) VALUES ('ORDER_001', 'PROJECT_A', 'O1A')")
        cursor.execute("INSERT INTO tasks (id, order_id, project_id, title) VALUES ('TASK_001', 'ORDER_001', 'PROJECT_A', 'T1')")
        conn.commit()

        # Try to insert dependency with nonexistent task
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO task_dependencies (task_id, depends_on_task_id, project_id)
                VALUES ('TASK_001', 'NONEXISTENT', 'PROJECT_A')
            """)

        conn.close()

    def test_cascade_delete_project(self, new_schema_db):
        """Deleting a project should cascade to orders and tasks."""
        conn = sqlite3.connect(new_schema_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # Setup
        cursor.execute("INSERT INTO projects (id, name, path) VALUES ('PROJECT_A', 'A', '/a')")
        cursor.execute("INSERT INTO orders (id, project_id, title) VALUES ('ORDER_001', 'PROJECT_A', 'O1A')")
        cursor.execute("INSERT INTO tasks (id, order_id, project_id, title) VALUES ('TASK_001', 'ORDER_001', 'PROJECT_A', 'T1')")
        conn.commit()

        # Delete project
        cursor.execute("DELETE FROM projects WHERE id = 'PROJECT_A'")
        conn.commit()

        # Verify cascade
        cursor.execute("SELECT COUNT(*) FROM orders WHERE project_id = 'PROJECT_A'")
        order_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE project_id = 'PROJECT_A'")
        task_count = cursor.fetchone()[0]

        assert order_count == 0
        assert task_count == 0

        conn.close()


# ============================================================================
# Test: Data Integrity After Migration
# ============================================================================

class TestDataIntegrityAfterMigration:
    """Tests for data integrity after migration."""

    def test_task_order_relationship_preserved(self, old_schema_db_with_data):
        """Task-Order relationships should be preserved after migration."""
        # Get relationships before migration
        conn = sqlite3.connect(old_schema_db_with_data)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.order_id, o.project_id
            FROM tasks t
            JOIN orders o ON t.order_id = o.id
        """)
        relationships_before = cursor.fetchall()
        conn.close()

        # Run migration
        run_migration(old_schema_db_with_data, backup=False, force=True)

        # Get relationships after migration
        conn = sqlite3.connect(old_schema_db_with_data)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.order_id, t.project_id
            FROM tasks t
        """)
        tasks_after = cursor.fetchall()
        conn.close()

        # Verify task count preserved
        assert len(tasks_after) == len(relationships_before)

        # Verify project_id properly populated
        for task_id, order_id, project_id in tasks_after:
            # Find matching task in before data
            matching = [r for r in relationships_before if r[0] == task_id]
            assert len(matching) == 1
            assert project_id == matching[0][2]  # project_id should match

    def test_dependency_project_id_populated(self, old_schema_db_with_data):
        """Task dependencies should have project_id populated after migration."""
        # Get dependency count before
        conn = sqlite3.connect(old_schema_db_with_data)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM task_dependencies")
        count_before = cursor.fetchone()[0]
        conn.close()

        # Run migration
        run_migration(old_schema_db_with_data, backup=False, force=True)

        # Check dependencies after
        conn = sqlite3.connect(old_schema_db_with_data)
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, depends_on_task_id, project_id FROM task_dependencies")
        deps_after = cursor.fetchall()
        conn.close()

        # Verify count preserved
        assert len(deps_after) == count_before

        # Verify project_id populated
        for task_id, depends_on_task_id, project_id in deps_after:
            assert project_id is not None


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
