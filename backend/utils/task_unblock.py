"""
AI PM Framework - Task Unblock Utility

Handles automatic re-evaluation and kicking of waiting tasks when dependencies
or file locks are released.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from utils.db import (
    get_connection, execute_query, fetch_one, fetch_all,
    row_to_dict, rows_to_dicts, DatabaseError
)

logger = logging.getLogger(__name__)


class TaskUnblocker:
    """Manages automatic task unblocking and re-evaluation"""

    @staticmethod
    def find_unblocked_tasks(
        project_id: str,
        order_id: str,
        exclude_task_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find all tasks that can now be executed after lock/dependency release

        Args:
            project_id: Project ID
            order_id: ORDER ID to search within
            exclude_task_id: Task ID to exclude (e.g., the just-completed task)

        Returns:
            List of task info dicts that are now executable
        """
        conn = get_connection()
        try:
            # Get all QUEUED and BLOCKED tasks in the same ORDER
            query = """
                SELECT id, title, status, priority, target_files
                FROM tasks
                WHERE project_id = ?
                  AND order_id = ?
                  AND status IN ('QUEUED', 'BLOCKED')
            """
            params = [project_id, order_id]

            if exclude_task_id:
                query += " AND id != ?"
                params.append(exclude_task_id)

            query += """
                ORDER BY
                    CASE priority
                        WHEN 'P0' THEN 0
                        WHEN 'P1' THEN 1
                        WHEN 'P2' THEN 2
                        ELSE 3
                    END,
                    created_at ASC
            """

            tasks = fetch_all(conn, query, tuple(params))

            # Check each task for executability
            executable_tasks = []
            for task in tasks:
                task_dict = row_to_dict(task) if not isinstance(task, dict) else task
                task_id = task_dict["id"]

                if TaskUnblocker._is_task_now_executable(conn, project_id, task_id):
                    executable_tasks.append(task_dict)
                    logger.info(f"Task {task_id} is now executable")

            return executable_tasks

        finally:
            conn.close()

    @staticmethod
    def _is_task_now_executable(conn, project_id: str, task_id: str) -> bool:
        """
        Check if a task is now executable (all dependencies completed, no file conflicts)

        Args:
            conn: Database connection
            project_id: Project ID
            task_id: Task ID to check

        Returns:
            True if task can be executed now
        """
        # Check dependencies
        if not TaskUnblocker._check_dependencies_completed(conn, project_id, task_id):
            logger.debug(f"Task {task_id}: Dependencies not completed")
            return False

        # Check file locks
        if not TaskUnblocker._check_file_locks_available(conn, project_id, task_id):
            logger.debug(f"Task {task_id}: File locks not available")
            return False

        return True

    @staticmethod
    def _check_dependencies_completed(conn, project_id: str, task_id: str) -> bool:
        """
        Check if all dependencies are completed

        Returns:
            True if all dependencies are COMPLETED
            (DONE tasks are NOT sufficient - review approval is required)
        """
        pending_deps = fetch_one(
            conn,
            """
            SELECT COUNT(*) as count
            FROM task_dependencies td
            JOIN tasks t ON td.depends_on_task_id = t.id AND td.project_id = t.project_id
            WHERE td.task_id = ? AND td.project_id = ?
            AND t.status NOT IN ('COMPLETED')
            """,
            (task_id, project_id)
        )

        return pending_deps is None or pending_deps["count"] == 0

    @staticmethod
    def find_successor_tasks(
        project_id: str,
        completed_task_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find all tasks that depend on the completed task

        Args:
            project_id: Project ID
            completed_task_id: Task ID that was just completed

        Returns:
            List of successor task info dicts
        """
        conn = get_connection()
        try:
            # Find all tasks that have this task as a dependency
            successors = fetch_all(
                conn,
                """
                SELECT DISTINCT t.id, t.title, t.status, t.priority, t.order_id, t.target_files
                FROM task_dependencies td
                JOIN tasks t ON td.task_id = t.id AND td.project_id = t.project_id
                WHERE td.depends_on_task_id = ? AND td.project_id = ?
                ORDER BY
                    CASE t.priority
                        WHEN 'P0' THEN 0
                        WHEN 'P1' THEN 1
                        WHEN 'P2' THEN 2
                        ELSE 3
                    END,
                    t.created_at ASC
                """,
                (completed_task_id, project_id)
            )

            return rows_to_dicts(successors) if successors else []

        finally:
            conn.close()

    @staticmethod
    def check_successor_dependencies(
        project_id: str,
        completed_task_id: str
    ) -> List[Dict[str, Any]]:
        """
        Check successor tasks and return those ready to execute

        Args:
            project_id: Project ID
            completed_task_id: Task ID that was just completed

        Returns:
            List of successor tasks that are now ready to execute
        """
        conn = get_connection()
        try:
            # Find all successor tasks
            successors = TaskUnblocker.find_successor_tasks(project_id, completed_task_id)

            if not successors:
                logger.info(f"No successor tasks found for {completed_task_id}")
                return []

            logger.info(f"Found {len(successors)} successor tasks for {completed_task_id}")

            # Check each successor for executability
            ready_tasks = []
            for task in successors:
                task_id = task["id"]

                # Check if all dependencies are completed
                if TaskUnblocker._check_dependencies_completed(conn, project_id, task_id):
                    # Check file lock availability
                    if TaskUnblocker._check_file_locks_available(conn, project_id, task_id):
                        ready_tasks.append(task)
                        logger.info(f"Successor task {task_id} is ready to execute")
                    else:
                        logger.debug(f"Successor task {task_id} blocked by file locks")
                else:
                    logger.debug(f"Successor task {task_id} still has pending dependencies")

            return ready_tasks

        finally:
            conn.close()

    @staticmethod
    def _check_file_locks_available(conn, project_id: str, task_id: str) -> bool:
        """
        Check if required files are not locked by other tasks

        Returns:
            True if no file lock conflicts
        """
        try:
            from utils.file_lock import FileLockManager
            can_start, blocking_tasks = FileLockManager.can_task_start(project_id, task_id)

            if not can_start:
                logger.debug(
                    f"Task {task_id} blocked by file locks from: {', '.join(blocking_tasks)}"
                )

            return can_start

        except ImportError:
            # If FileLockManager not available, assume no conflicts
            logger.warning("FileLockManager not available, skipping file lock check")
            return True
        except Exception as e:
            logger.warning(f"Error checking file locks for {task_id}: {e}")
            return False

    @staticmethod
    def update_task_status_if_unblocked(
        project_id: str,
        task_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Update task status from BLOCKED to QUEUED if it's now unblocked

        Args:
            project_id: Project ID
            task_id: Task ID to check and update

        Returns:
            Tuple of (updated: bool, new_status: Optional[str])
        """
        conn = get_connection()
        try:
            # Get current task status
            task = fetch_one(
                conn,
                "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
                (task_id, project_id)
            )

            if not task:
                return (False, None)

            current_status = task["status"]

            # Only update if currently BLOCKED
            if current_status != "BLOCKED":
                return (False, current_status)

            # Check if task is now executable
            if TaskUnblocker._is_task_now_executable(conn, project_id, task_id):
                # Update to QUEUED
                execute_query(
                    conn,
                    """
                    UPDATE tasks
                    SET status = 'QUEUED', updated_at = datetime('now')
                    WHERE id = ? AND project_id = ?
                    """,
                    (task_id, project_id)
                )
                conn.commit()

                logger.info(f"Task {task_id} status updated: BLOCKED → QUEUED")
                return (True, "QUEUED")

            return (False, current_status)

        except Exception as e:
            logger.error(f"Error updating task status for {task_id}: {e}")
            conn.rollback()
            return (False, None)

        finally:
            conn.close()

    @staticmethod
    def auto_kick_unblocked_tasks(
        project_id: str,
        order_id: str,
        exclude_task_id: Optional[str] = None,
        max_kicks: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Automatically find and kick (start execution of) unblocked tasks

        Args:
            project_id: Project ID
            order_id: ORDER ID to search within
            exclude_task_id: Task ID to exclude (e.g., the just-completed task)
            max_kicks: Maximum number of tasks to kick at once

        Returns:
            List of kicked task info dicts
        """
        # Find executable tasks
        executable_tasks = TaskUnblocker.find_unblocked_tasks(
            project_id, order_id, exclude_task_id
        )

        if not executable_tasks:
            logger.info("No unblocked tasks found to kick")
            return []

        kicked_tasks = []

        # Update BLOCKED → QUEUED for executable tasks
        for task in executable_tasks[:max_kicks]:
            task_id = task["id"]
            updated, new_status = TaskUnblocker.update_task_status_if_unblocked(
                project_id, task_id
            )

            if updated:
                task["new_status"] = new_status
                kicked_tasks.append(task)

        logger.info(f"Auto-kicked {len(kicked_tasks)} tasks: {[t['id'] for t in kicked_tasks]}")

        return kicked_tasks
