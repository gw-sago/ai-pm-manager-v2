#!/usr/bin/env python3
"""
AI PM Framework - Successor Task Trigger Script

Separated successor task triggering that runs as an independent process.
This script is called after a task is completed and approved to trigger
successor tasks without blocking the main Worker→Review cycle.

Usage:
    python backend/task/trigger_successors.py PROJECT_NAME TASK_ID [options]

Options:
    --max-kicks     Maximum number of successor tasks to trigger (default: 5)
    --json          JSON output mode
    --verbose       Verbose logging

Example:
    python backend/task/trigger_successors.py ai_pm_manager TASK_762
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Import utilities
try:
    from aipm_db.utils.db import get_connection, fetch_one, execute_query, DatabaseError
    from aipm_db.utils.validation import validate_project_name, validate_task_id, ValidationError
    from aipm_db.utils.task_unblock import TaskUnblocker
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from utils.db import get_connection, fetch_one, execute_query, DatabaseError
    from utils.validation import validate_project_name, validate_task_id, ValidationError
    from utils.task_unblock import TaskUnblocker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)


def trigger_successor_tasks(
    project_id: str,
    completed_task_id: str,
    max_kicks: int = 5,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Trigger successor tasks after a task is completed

    Args:
        project_id: Project ID
        completed_task_id: Task ID that was just completed
        max_kicks: Maximum number of successor tasks to trigger
        verbose: Enable verbose logging

    Returns:
        Result dict containing triggered tasks info

    Process:
        1. Find successor tasks (tasks that depend on completed_task_id)
        2. Check each successor's dependencies
        3. Update BLOCKED → QUEUED for ready successors
        4. Return list of triggered tasks
    """
    if verbose:
        logger.setLevel(logging.DEBUG)

    # Validate inputs
    validate_project_name(project_id)
    validate_task_id(completed_task_id)

    logger.info(f"Checking successor tasks for {completed_task_id} in project {project_id}")

    try:
        # Get order_id of completed task
        conn = get_connection()
        try:
            task_info = fetch_one(
                conn,
                """
                SELECT order_id, title, status
                FROM tasks
                WHERE id = ? AND project_id = ?
                """,
                (completed_task_id, project_id)
            )

            if not task_info:
                raise ValidationError(
                    f"Task not found: {completed_task_id} in project {project_id}",
                    "task_id",
                    completed_task_id
                )

            order_id = task_info["order_id"]
            task_status = task_info["status"]

            logger.info(
                f"Task {completed_task_id}: status={task_status}, order={order_id}"
            )

            # Only trigger successors if task is COMPLETED
            # Note: DONE status is also acceptable (task completed but review not yet approved)
            if task_status not in ("COMPLETED", "DONE"):
                logger.warning(
                    f"Task {completed_task_id} is not COMPLETED/DONE (status={task_status}), "
                    "skipping successor triggering"
                )
                return {
                    "success": True,
                    "triggered_tasks": [],
                    "message": f"Skipped: task status is {task_status}, not COMPLETED/DONE"
                }

        finally:
            conn.close()

        # Find ready successor tasks using TaskUnblocker
        ready_successors = TaskUnblocker.check_successor_dependencies(
            project_id, completed_task_id
        )

        if not ready_successors:
            logger.info("No ready successor tasks found")
            return {
                "success": True,
                "triggered_tasks": [],
                "message": "No successor tasks ready to execute"
            }

        logger.info(f"Found {len(ready_successors)} ready successor task(s)")

        # Trigger successor tasks (update BLOCKED → QUEUED)
        triggered_tasks = []
        for successor in ready_successors[:max_kicks]:
            task_id = successor["id"]
            task_title = successor.get("title", "")

            # Update status BLOCKED → QUEUED
            updated, new_status = TaskUnblocker.update_task_status_if_unblocked(
                project_id, task_id
            )

            if updated:
                logger.info(f"Triggered successor task: {task_id} - {task_title}")
                triggered_tasks.append({
                    "task_id": task_id,
                    "title": task_title,
                    "old_status": "BLOCKED",
                    "new_status": new_status,
                    "priority": successor.get("priority", "P1"),
                })

        return {
            "success": True,
            "triggered_tasks": triggered_tasks,
            "message": f"Triggered {len(triggered_tasks)} successor task(s)"
        }

    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        return {
            "success": False,
            "triggered_tasks": [],
            "error": str(e),
            "message": f"Validation error: {e}"
        }
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        return {
            "success": False,
            "triggered_tasks": [],
            "error": str(e),
            "message": f"Database error: {e}"
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {
            "success": False,
            "triggered_tasks": [],
            "error": str(e),
            "message": f"Unexpected error: {e}"
        }


def main():
    """CLI entry point"""
    # Windows UTF-8 output setup
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="Trigger successor tasks after task completion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "project_id",
        help="Project ID (e.g., ai_pm_manager)"
    )
    parser.add_argument(
        "task_id",
        help="Completed task ID (e.g., TASK_762)"
    )
    parser.add_argument(
        "--max-kicks",
        type=int,
        default=5,
        help="Maximum number of successor tasks to trigger (default: 5)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON output mode"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging"
    )

    args = parser.parse_args()

    # Execute successor triggering
    result = trigger_successor_tasks(
        project_id=args.project_id,
        completed_task_id=args.task_id,
        max_kicks=args.max_kicks,
        verbose=args.verbose,
    )

    # Output result
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            print(f"[OK] {result['message']}")
            if result["triggered_tasks"]:
                print("\nTriggered tasks:")
                for task in result["triggered_tasks"]:
                    print(
                        f"  - {task['task_id']}: {task['title']} "
                        f"({task['old_status']} → {task['new_status']})"
                    )
        else:
            print(f"[ERROR] {result.get('message', 'Unknown error')}", file=sys.stderr)
            if result.get("error"):
                print(f"Details: {result['error']}", file=sys.stderr)
            sys.exit(1)

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
