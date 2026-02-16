"""
AI PM Framework - File Lock Management Utility

Manages file locks for parallel task execution to prevent conflicts.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from utils.db import (
    get_connection, execute_query, fetch_one, fetch_all,
    row_to_dict, rows_to_dicts, DatabaseError
)


class FileLockError(Exception):
    """File lock operation error"""
    pass


class FileLockManager:
    """Manages file locks for parallel task execution"""

    @staticmethod
    def acquire_locks(project_id: str, task_id: str, file_paths: List[str]) -> bool:
        """
        Acquire locks for specified files

        Args:
            project_id: Project ID
            task_id: Task ID that wants to acquire locks
            file_paths: List of file paths to lock

        Returns:
            True if all locks acquired successfully, False otherwise

        Raises:
            FileLockError: If lock acquisition fails
        """
        if not file_paths:
            return True

        conn = get_connection()
        try:
            # Check for conflicts
            conflicts = FileLockManager.check_conflicts(project_id, file_paths)
            if conflicts:
                # Locks are held by other tasks
                return False

            # Acquire all locks
            now = datetime.now().isoformat()
            for file_path in file_paths:
                execute_query(
                    conn,
                    """
                    INSERT INTO file_locks (project_id, task_id, file_path, locked_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (project_id, task_id, file_path, now)
                )

            conn.commit()
            return True

        except DatabaseError as e:
            conn.rollback()
            raise FileLockError(f"Failed to acquire locks: {e}")
        finally:
            conn.close()

    @staticmethod
    def release_locks(project_id: str, task_id: str) -> None:
        """
        Release all locks held by a task

        Args:
            project_id: Project ID
            task_id: Task ID that holds locks

        Raises:
            FileLockError: If lock release fails
        """
        conn = get_connection()
        try:
            execute_query(
                conn,
                "DELETE FROM file_locks WHERE project_id = ? AND task_id = ?",
                (project_id, task_id)
            )
            conn.commit()

        except DatabaseError as e:
            conn.rollback()
            raise FileLockError(f"Failed to release locks: {e}")
        finally:
            conn.close()

    @staticmethod
    def check_conflicts(project_id: str, file_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Check if any of the specified files are locked by other tasks

        Args:
            project_id: Project ID
            file_paths: List of file paths to check

        Returns:
            List of conflicting locks (each containing task_id, file_path, locked_at)
        """
        if not file_paths:
            return []

        conn = get_connection()
        try:
            # Auto-cleanup: remove stale locks from completed/done/rejected tasks
            execute_query(
                conn,
                """
                DELETE FROM file_locks
                WHERE project_id = ? AND task_id IN (
                    SELECT t.id FROM tasks t
                    WHERE t.status IN ('COMPLETED', 'DONE', 'REJECTED')
                    AND t.id IN (SELECT fl.task_id FROM file_locks fl WHERE fl.project_id = ?)
                )
                """,
                (project_id, project_id)
            )
            conn.commit()

            # Build query with multiple file paths
            placeholders = ",".join(["?"] * len(file_paths))
            query = f"""
                SELECT task_id, file_path, locked_at
                FROM file_locks
                WHERE project_id = ? AND file_path IN ({placeholders})
            """
            params = [project_id] + file_paths

            rows = fetch_all(conn, query, params)
            return rows_to_dicts(rows)

        finally:
            conn.close()

    @staticmethod
    def get_locked_files(project_id: str, task_id: str) -> List[str]:
        """
        Get list of files locked by a specific task

        Args:
            project_id: Project ID
            task_id: Task ID

        Returns:
            List of locked file paths
        """
        conn = get_connection()
        try:
            rows = fetch_all(
                conn,
                "SELECT file_path FROM file_locks WHERE project_id = ? AND task_id = ?",
                (project_id, task_id)
            )
            return [row["file_path"] for row in rows]

        finally:
            conn.close()

    @staticmethod
    def get_all_locks(project_id: str) -> List[Dict[str, Any]]:
        """
        Get all locks for a project

        Args:
            project_id: Project ID

        Returns:
            List of all locks (each containing task_id, file_path, locked_at)
        """
        conn = get_connection()
        try:
            rows = fetch_all(
                conn,
                "SELECT task_id, file_path, locked_at FROM file_locks WHERE project_id = ? ORDER BY locked_at",
                (project_id,)
            )
            return rows_to_dicts(rows)

        finally:
            conn.close()

    @staticmethod
    def parse_target_files(target_files_json: Optional[str]) -> List[str]:
        """
        Parse target_files JSON string to list

        Args:
            target_files_json: JSON string containing file paths

        Returns:
            List of file paths, empty list if invalid or None
        """
        if not target_files_json:
            return []

        try:
            files = json.loads(target_files_json)
            if isinstance(files, list):
                return [str(f) for f in files]
            return []
        except (json.JSONDecodeError, ValueError):
            return []

    @staticmethod
    def can_task_start(project_id: str, task_id: str) -> tuple[bool, List[str]]:
        """
        Check if a task can start based on file lock conflicts

        Args:
            project_id: Project ID
            task_id: Task ID to check

        Returns:
            Tuple of (can_start: bool, blocking_tasks: List[str])
            - can_start: True if task can start (no conflicts)
            - blocking_tasks: List of task IDs that are blocking this task
        """
        conn = get_connection()
        try:
            # Get target files for this task
            task_row = fetch_one(
                conn,
                "SELECT target_files FROM tasks WHERE id = ? AND project_id = ?",
                (task_id, project_id)
            )

            if not task_row or not task_row["target_files"]:
                # No target files specified, can start
                return (True, [])

            target_files = FileLockManager.parse_target_files(task_row["target_files"])
            if not target_files:
                # No valid target files, can start
                return (True, [])

            # Check for conflicts
            conflicts = FileLockManager.check_conflicts(project_id, target_files)
            if not conflicts:
                # No conflicts, can start
                return (True, [])

            # Extract blocking task IDs
            blocking_tasks = list(set(conflict["task_id"] for conflict in conflicts))
            return (False, blocking_tasks)

        finally:
            conn.close()
