"""
AI PM Framework - Parallel Task Detection Module

Detects tasks within an ORDER that can be launched in parallel based on:
1. No dependency conflicts (all dependencies completed)
2. No file lock conflicts (no overlapping target_files)
3. Task status is QUEUED

Integrates logic from ORDER_076 (file locks) and ORDER_078 (dependency auto-trigger).
"""

import logging
from typing import List, Dict, Any, Set, Tuple
from pathlib import Path

from utils.db import (
    get_connection, fetch_all, fetch_one,
    row_to_dict, rows_to_dicts
)
from utils.file_lock import FileLockManager
from utils.task_unblock import TaskUnblocker

logger = logging.getLogger(__name__)


class ParallelTaskDetector:
    """Detects tasks that can be launched in parallel"""

    @staticmethod
    def find_parallel_launchable_tasks(
        project_id: str,
        order_id: str,
        max_tasks: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find all QUEUED tasks in an ORDER that can be launched in parallel

        Args:
            project_id: Project ID
            order_id: ORDER ID to search within
            max_tasks: Maximum number of tasks to return (default: 10)

        Returns:
            List of task info dicts that can be launched in parallel
            Sorted by priority (P0 > P1 > P2 > P3) and creation time
        """
        conn = get_connection()
        try:
            # Get all QUEUED tasks in the ORDER
            queued_tasks = fetch_all(
                conn,
                """
                SELECT id, title, priority, status, target_files, created_at
                FROM tasks
                WHERE project_id = ?
                  AND order_id = ?
                  AND status = 'QUEUED'
                ORDER BY
                    CASE priority
                        WHEN 'P0' THEN 0
                        WHEN 'P1' THEN 1
                        WHEN 'P2' THEN 2
                        ELSE 3
                    END,
                    created_at ASC
                """,
                (project_id, order_id)
            )

            if not queued_tasks:
                logger.info(f"No QUEUED tasks found in {order_id}")
                return []

            logger.info(f"Found {len(queued_tasks)} QUEUED tasks in {order_id}")

            # Filter tasks that can be launched
            launchable_tasks = []
            locked_files: Set[str] = set()

            for task in queued_tasks:
                task_dict = row_to_dict(task) if not isinstance(task, dict) else task
                task_id = task_dict["id"]

                # Check if task can be launched
                can_launch, reason = ParallelTaskDetector._can_task_launch(
                    conn, project_id, task_id, locked_files
                )

                if can_launch:
                    launchable_tasks.append(task_dict)

                    # Add this task's target files to locked set
                    target_files = FileLockManager.parse_target_files(
                        task_dict.get("target_files")
                    )
                    locked_files.update(target_files)

                    logger.info(f"Task {task_id} can be launched: {reason}")

                    # Stop if we've reached max_tasks
                    if len(launchable_tasks) >= max_tasks:
                        break
                else:
                    logger.debug(f"Task {task_id} blocked: {reason}")

            logger.info(
                f"Found {len(launchable_tasks)} parallel launchable tasks "
                f"(max: {max_tasks})"
            )

            return launchable_tasks

        finally:
            conn.close()

    @staticmethod
    def _can_task_launch(
        conn,
        project_id: str,
        task_id: str,
        already_locked_files: Set[str]
    ) -> Tuple[bool, str]:
        """
        Check if a task can be launched in parallel

        Args:
            conn: Database connection
            project_id: Project ID
            task_id: Task ID to check
            already_locked_files: Set of files that will be locked by other parallel tasks

        Returns:
            Tuple of (can_launch: bool, reason: str)
        """
        # Check 1: All dependencies must be COMPLETED or DONE
        if not ParallelTaskDetector._check_dependencies_ready(conn, project_id, task_id):
            return (False, "pending dependencies")

        # Check 2: No file lock conflicts with existing IN_PROGRESS tasks
        can_start, blocking_tasks = FileLockManager.can_task_start(project_id, task_id)
        if not can_start:
            return (False, f"file locks held by {', '.join(blocking_tasks)}")

        # Check 3: No file conflicts with other parallel launch candidates
        if ParallelTaskDetector._has_file_conflict(
            conn, project_id, task_id, already_locked_files
        ):
            return (False, "file conflict with parallel tasks")

        return (True, "all checks passed")

    @staticmethod
    def _check_dependencies_ready(conn, project_id: str, task_id: str) -> bool:
        """
        Check if all dependencies are ready (COMPLETED or DONE)

        DONE tasks are functionally complete and can unblock dependent tasks,
        even if they're awaiting review approval.

        Args:
            conn: Database connection
            project_id: Project ID
            task_id: Task ID to check

        Returns:
            True if all dependencies are ready
        """
        pending_deps = fetch_one(
            conn,
            """
            SELECT COUNT(*) as count
            FROM task_dependencies td
            JOIN tasks t ON td.depends_on_task_id = t.id AND td.project_id = t.project_id
            WHERE td.task_id = ? AND td.project_id = ?
            AND t.status NOT IN ('COMPLETED', 'DONE')
            """,
            (task_id, project_id)
        )

        return pending_deps is None or pending_deps["count"] == 0

    @staticmethod
    def _has_file_conflict(
        conn,
        project_id: str,
        task_id: str,
        already_locked_files: Set[str]
    ) -> bool:
        """
        Check if task's target files conflict with already locked files

        Args:
            conn: Database connection
            project_id: Project ID
            task_id: Task ID to check
            already_locked_files: Set of files already locked by parallel tasks

        Returns:
            True if there's a conflict, False otherwise
        """
        if not already_locked_files:
            # No files locked yet, no conflict possible
            return False

        # Get task's target files
        task = fetch_one(
            conn,
            "SELECT target_files FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )

        if not task or not task["target_files"]:
            # No target files specified, no conflict
            return False

        target_files = FileLockManager.parse_target_files(task["target_files"])
        if not target_files:
            # No valid target files, no conflict
            return False

        # Check for intersection
        conflicts = already_locked_files.intersection(set(target_files))
        if conflicts:
            logger.debug(
                f"Task {task_id} has file conflicts: {', '.join(conflicts)}"
            )
            return True

        return False

    @staticmethod
    def get_parallel_launch_summary(
        project_id: str,
        order_id: str,
        max_tasks: int = 10
    ) -> Dict[str, Any]:
        """
        Get a summary of parallel launchable tasks

        Args:
            project_id: Project ID
            order_id: ORDER ID
            max_tasks: Maximum number of tasks to analyze

        Returns:
            Summary dict with task counts and details
        """
        conn = get_connection()
        try:
            # Get total QUEUED tasks
            total_queued = fetch_one(
                conn,
                """
                SELECT COUNT(*) as count
                FROM tasks
                WHERE project_id = ? AND order_id = ? AND status = 'QUEUED'
                """,
                (project_id, order_id)
            )

            total_count = total_queued["count"] if total_queued else 0

            # Get launchable tasks
            launchable_tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
                project_id, order_id, max_tasks
            )

            # Categorize blocked tasks
            all_queued = fetch_all(
                conn,
                """
                SELECT id, title, target_files
                FROM tasks
                WHERE project_id = ? AND order_id = ? AND status = 'QUEUED'
                ORDER BY
                    CASE priority
                        WHEN 'P0' THEN 0
                        WHEN 'P1' THEN 1
                        WHEN 'P2' THEN 2
                        ELSE 3
                    END,
                    created_at ASC
                """,
                (project_id, order_id)
            )

            blocked_by_deps = []
            blocked_by_locks = []
            locked_files: Set[str] = set()

            for task in all_queued:
                task_dict = row_to_dict(task) if not isinstance(task, dict) else task
                task_id = task_dict["id"]

                # Skip if already in launchable list
                if any(t["id"] == task_id for t in launchable_tasks):
                    target_files = FileLockManager.parse_target_files(
                        task_dict.get("target_files")
                    )
                    locked_files.update(target_files)
                    continue

                # Determine blocking reason
                if not ParallelTaskDetector._check_dependencies_ready(
                    conn, project_id, task_id
                ):
                    blocked_by_deps.append(task_id)
                elif not FileLockManager.can_task_start(project_id, task_id)[0]:
                    blocked_by_locks.append(task_id)
                elif ParallelTaskDetector._has_file_conflict(
                    conn, project_id, task_id, locked_files
                ):
                    blocked_by_locks.append(task_id)

            return {
                "project_id": project_id,
                "order_id": order_id,
                "total_queued": total_count,
                "launchable_count": len(launchable_tasks),
                "launchable_tasks": [t["id"] for t in launchable_tasks],
                "blocked_by_dependencies": blocked_by_deps,
                "blocked_by_locks": blocked_by_locks,
                "max_tasks": max_tasks,
            }

        finally:
            conn.close()
