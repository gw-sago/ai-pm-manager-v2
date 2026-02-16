#!/usr/bin/env python3
"""
AI PM Framework - Retry Handler Module

Manages retry logic for failed tasks as part of the self-healing pipeline.

- Checks INCIDENTS table for retry count
- Determines retry eligibility (max 2 retries)
- Prepares task for retry by gathering failure context

Usage:
    from retry.retry_handler import RetryHandler

    handler = RetryHandler("ai_pm_manager", "TASK_932")
    if handler.can_retry():
        result = handler.prepare_retry()
        # result.should_retry == True, result.new_status == "REWORK"
    else:
        result = handler.prepare_retry()
        # result.should_retry == False, result.new_status == "REJECTED"
"""
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_one, fetch_all, execute_query, row_to_dict, rows_to_dicts

logger = logging.getLogger(__name__)


class RetryError(Exception):
    """Retry operation error"""
    pass


@dataclass
class RetryResult:
    """Result of a retry evaluation"""
    success: bool
    task_id: str
    retry_count: int
    max_retries: int
    should_retry: bool
    new_status: str  # "REWORK" if retryable, "REJECTED" if limit exceeded
    failure_context: Optional[str] = None
    error_message: Optional[str] = None
    incident_ids: List[str] = field(default_factory=list)
    retried_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "task_id": self.task_id,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "should_retry": self.should_retry,
            "new_status": self.new_status,
            "failure_context": self.failure_context,
            "error_message": self.error_message,
            "incident_ids": self.incident_ids,
            "retried_at": self.retried_at.isoformat(),
        }


class RetryHandler:
    """Handles retry logic for failed tasks"""

    def __init__(
        self,
        project_id: str,
        task_id: str,
        max_retries: int = 2,
        verbose: bool = False
    ):
        self.project_id = project_id
        self.task_id = task_id
        self.max_retries = max_retries
        self.verbose = verbose

    def get_retry_count(self) -> int:
        """
        Get current retry count from INCIDENTS table.

        Counts incidents with category 'RETRY' or 'WORKER_FAILURE'
        for this task to determine how many retries have been attempted.

        Returns:
            int: Number of retry attempts recorded
        """
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                """
                SELECT COUNT(*) as count FROM incidents
                WHERE task_id = ? AND project_id = ?
                  AND category = 'WORKER_FAILURE'
                """,
                (self.task_id, self.project_id)
            )
            return row["count"] if row else 0
        finally:
            conn.close()

    def can_retry(self) -> bool:
        """
        Check if task can be retried (retry_count < max_retries).

        Returns:
            bool: True if retry is allowed
        """
        retry_count = self.get_retry_count()
        can = retry_count < self.max_retries
        logger.debug(
            f"Retry check for {self.task_id}: count={retry_count}, "
            f"max={self.max_retries}, can_retry={can}"
        )
        return can

    def get_failure_context(self) -> Optional[str]:
        """
        Get failure context from the most recent INCIDENTS entry.

        Returns:
            str or None: Formatted failure context string
        """
        conn = get_connection()
        try:
            incident_row = fetch_one(
                conn,
                """
                SELECT root_cause, description, category, severity, timestamp
                FROM incidents
                WHERE task_id = ? AND project_id = ?
                ORDER BY timestamp DESC LIMIT 1
                """,
                (self.task_id, self.project_id)
            )
            if not incident_row:
                return None

            incident = row_to_dict(incident_row)
            parts = []
            if incident.get("category"):
                parts.append(f"Category: {incident['category']}")
            if incident.get("severity"):
                parts.append(f"Severity: {incident['severity']}")
            if incident.get("description"):
                parts.append(f"Issue: {incident['description']}")
            if incident.get("root_cause"):
                parts.append(f"Root Cause: {incident['root_cause']}")
            if incident.get("timestamp"):
                parts.append(f"Detected At: {incident['timestamp']}")
            return "\n".join(parts) if parts else None
        finally:
            conn.close()

    def get_failure_history(self) -> List[Dict[str, Any]]:
        """
        Get all failure incidents for this task.

        Returns:
            List of incident dictionaries
        """
        conn = get_connection()
        try:
            rows = fetch_all(
                conn,
                """
                SELECT incident_id, timestamp, category, severity,
                       description, root_cause
                FROM incidents
                WHERE task_id = ? AND project_id = ?
                ORDER BY timestamp DESC
                """,
                (self.task_id, self.project_id)
            )
            return rows_to_dicts(rows)
        finally:
            conn.close()

    def prepare_retry(self) -> RetryResult:
        """
        Prepare task for retry: evaluate eligibility and build result.

        This method does NOT change DB state -- it returns a RetryResult
        that the caller uses to decide the next action (set REWORK or REJECTED).

        Returns:
            RetryResult with all information needed for the caller
        """
        retry_count = self.get_retry_count()
        should_retry = retry_count < self.max_retries
        failure_context = self.get_failure_context()

        # Collect incident IDs for reference
        history = self.get_failure_history()
        incident_ids = [h["incident_id"] for h in history if h.get("incident_id")]

        if should_retry:
            new_status = "REWORK"
            logger.info(
                f"Task {self.task_id} eligible for retry "
                f"(attempt {retry_count + 1}/{self.max_retries})"
            )
        else:
            new_status = "REJECTED"
            logger.warning(
                f"Task {self.task_id} retry limit exceeded "
                f"({retry_count}/{self.max_retries}), marking as REJECTED"
            )

        return RetryResult(
            success=True,
            task_id=self.task_id,
            retry_count=retry_count,
            max_retries=self.max_retries,
            should_retry=should_retry,
            new_status=new_status,
            failure_context=failure_context,
            incident_ids=incident_ids,
        )


def retry_task(
    project_id: str,
    task_id: str,
    max_retries: int = 2,
    verbose: bool = False
) -> RetryResult:
    """
    Convenience function: evaluate retry eligibility for a task.

    Args:
        project_id: Project ID
        task_id: Task ID
        max_retries: Maximum retry attempts (default: 2)
        verbose: Verbose logging

    Returns:
        RetryResult with retry decision and context
    """
    handler = RetryHandler(project_id, task_id, max_retries, verbose)
    return handler.prepare_retry()
