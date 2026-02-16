#!/usr/bin/env python3
"""
AI PM Framework - Get Order ID for Task

Retrieves the ORDER_ID associated with a given task.

Usage:
    python -m task.get_order_id PROJECT_ID TASK_ID [--json]

Example:
    python -m task.get_order_id ai_pm_manager TASK_941 --json
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_one
from utils.validation import validate_project_name, ValidationError

logger = logging.getLogger(__name__)


def get_order_id(project_id: str, task_id: str) -> dict:
    """
    Get ORDER_ID for a given task

    Args:
        project_id: Project ID
        task_id: Task ID

    Returns:
        Dictionary with order_id
    """
    conn = get_connection()
    try:
        task = fetch_one(
            conn,
            """
            SELECT order_id
            FROM tasks
            WHERE project_id = ? AND id = ?
            """,
            (project_id, task_id)
        )

        if not task:
            raise ValueError(f"Task not found: {project_id}/{task_id}")

        order_id = task["order_id"]
        if not order_id:
            raise ValueError(f"Task {task_id} has no ORDER_ID")

        return {
            "project_id": project_id,
            "task_id": task_id,
            "order_id": order_id,
        }

    finally:
        conn.close()


def main():
    """CLI entry point"""
    # Windows UTF-8 output setup
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    # Logging setup
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    parser = argparse.ArgumentParser(
        description="Get ORDER_ID for a task",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="Project ID")
    parser.add_argument("task_id", help="Task ID")
    parser.add_argument("--json", action="store_true", help="JSON output format")

    args = parser.parse_args()

    try:
        # Validate project
        validate_project_name(args.project_id)

        # Get ORDER_ID
        result = get_order_id(args.project_id, args.task_id)

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"ORDER_ID: {result['order_id']}")

    except ValidationError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
