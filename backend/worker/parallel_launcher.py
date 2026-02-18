#!/usr/bin/env python3
"""
AI PM Framework - Parallel Worker Launcher

Launches multiple independent Worker sessions for parallel task execution.
Integrates with parallel_detector.py to identify launchable tasks and
spawns separate Worker processes for each task.

Usage:
    python -m worker.parallel_launcher PROJECT_NAME ORDER_ID [options]

Options:
    --max-workers N     Maximum number of parallel workers (default: 5)
    --dry-run           Show execution plan without launching workers
    --verbose           Detailed logging
    --json              JSON output format
    --timeout SEC       Worker timeout in seconds (default: 1800)
    --model MODEL       AI model for workers (haiku/sonnet/opus)
    --no-review         Disable auto-review after worker completion

Example:
    python -m worker.parallel_launcher ai_pm_manager ORDER_090
    python -m worker.parallel_launcher ai_pm_manager ORDER_090 --max-workers 3
    python -m worker.parallel_launcher ai_pm_manager ORDER_090 --dry-run
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from worker.parallel_detector import ParallelTaskDetector
from worker.resource_monitor import ResourceMonitor, get_system_info
from utils.validation import validate_project_name, ValidationError
from utils.db import get_connection, execute_query, fetch_one, fetch_all, rows_to_dicts, DatabaseError
from utils.file_lock import FileLockManager
from task.update import update_task
from config.worker_config import (
    get_worker_config,
    WorkerResourceConfig,
)
from config.db_config import AI_PM_ROOT, USER_DATA_PATH

# Optional imports for event-driven daemon loop (TASK_1090)
try:
    from worker.event_notifier import EventNotifier, AdaptivePoller
    _HAS_EVENT_NOTIFIER = True
except ImportError:
    _HAS_EVENT_NOTIFIER = False

# Import crash recovery (TASK_1156)
try:
    from worker.recover_crashed import recover_crashed_task
    _HAS_RECOVER_CRASHED = True
except ImportError:
    _HAS_RECOVER_CRASHED = False

try:
    from worker.dependency_resolver import resolve_on_completion
    _HAS_DEPENDENCY_RESOLVER = True
except ImportError:
    _HAS_DEPENDENCY_RESOLVER = False

# 権限プロファイル自動判定（ORDER_121）
try:
    from worker.permission_resolver import PermissionResolver
    _HAS_PERMISSION_RESOLVER = True
except ImportError:
    _HAS_PERMISSION_RESOLVER = False

logger = logging.getLogger(__name__)


def find_orphaned_done_tasks(
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Detect orphaned DONE tasks: tasks with status='DONE' that have not been reviewed yet.

    These tasks have completed execution but have reviewed_at = NULL,
    which means they are awaiting review.

    Args:
        project_id: Optional project ID to filter by. If None, searches all projects.

    Returns:
        List of dicts, each containing: task_id, project_id, order_id, title, priority,
        assignee, updated_at.
    """
    conn = get_connection()
    try:
        if project_id:
            rows = fetch_all(
                conn,
                """
                SELECT
                    id          AS task_id,
                    project_id,
                    order_id,
                    title,
                    priority,
                    assignee,
                    updated_at
                FROM tasks
                WHERE status = 'DONE'
                  AND reviewed_at IS NULL
                  AND project_id = ?
                ORDER BY updated_at ASC
                """,
                (project_id,),
            )
        else:
            rows = fetch_all(
                conn,
                """
                SELECT
                    id          AS task_id,
                    project_id,
                    order_id,
                    title,
                    priority,
                    assignee,
                    updated_at
                FROM tasks
                WHERE status = 'DONE'
                  AND reviewed_at IS NULL
                ORDER BY updated_at ASC
                """,
            )

        # Convert sqlite3.Row objects to plain dicts (Row does NOT support .get())
        results = rows_to_dicts(rows)

        count = len(results)
        if count > 0:
            logger.warning(
                f"[orphan-detect] Found {count} orphaned DONE task(s)"
                + (f" in project '{project_id}'" if project_id else "")
            )
            for item in results:
                logger.info(
                    f"[orphan-detect]   {item['task_id']} "
                    f"({item['order_id']}) - {item['title']}"
                )
        else:
            logger.info(
                "[orphan-detect] No orphaned DONE tasks found"
                + (f" in project '{project_id}'" if project_id else "")
            )

        return results

    except Exception as e:
        logger.error(f"[orphan-detect] Failed to detect orphaned DONE tasks: {e}")
        raise
    finally:
        conn.close()


def register_orphaned_tasks_to_review_queue(
    orphaned_tasks: Optional[List[Dict[str, Any]]] = None,
    *,
    project_id: Optional[str] = None,
) -> int:
    """
    Detect orphaned DONE tasks (status='DONE' AND reviewed_at IS NULL).

    This function no longer registers tasks into review_queue.
    Instead, it simply detects and returns the count of orphaned tasks.
    The review process now directly queries tasks with reviewed_at IS NULL.

    Args:
        orphaned_tasks: List of orphaned task dicts as returned by
            ``find_orphaned_done_tasks()``. If None, the function calls
            ``find_orphaned_done_tasks(project_id=project_id)`` internally.
        project_id: Used when ``orphaned_tasks`` is None to scope the
            detection query. Ignored when ``orphaned_tasks`` is provided.

    Returns:
        Number of orphaned DONE tasks detected (not registered).
    """
    # If no task list supplied, detect orphaned tasks ourselves
    if orphaned_tasks is None:
        orphaned_tasks = find_orphaned_done_tasks(project_id=project_id)

    if not orphaned_tasks:
        logger.info("[orphan-detect] No orphaned DONE tasks found")
        return 0

    # Simply return the count - no review_queue registration needed
    count = len(orphaned_tasks)
    logger.info(
        f"[orphan-detect] Found {count} orphaned DONE task(s) awaiting review "
        f"(reviewed_at IS NULL)"
    )

    return count


class ParallelWorkerLauncher:
    """Launches multiple Worker sessions in parallel"""

    def __init__(
        self,
        project_id: str,
        order_id: str,
        *,
        max_workers: int = 5,
        dry_run: bool = False,
        verbose: bool = False,
        timeout: int = 1800,
        model: Optional[str] = None,
        no_review: bool = False,
        worker_config: Optional[WorkerResourceConfig] = None,
        poll_interval: int = 10,
        stale_log_timeout: int = 600,
        worker_process_timeout: int = 1800,
        allowed_tools: Optional[List[str]] = None,
    ):
        self.project_id = project_id
        self.order_id = order_id
        self.max_workers = max_workers
        self.dry_run = dry_run
        self.verbose = verbose
        self.timeout = timeout
        self.model = model
        self.no_review = no_review
        self.poll_interval = poll_interval
        self.stale_log_timeout = stale_log_timeout  # seconds without log update → stuck
        self.worker_process_timeout = worker_process_timeout  # max seconds a worker process may run (TASK_1156)
        self.allowed_tools = allowed_tools
        self.escalated_timeout = 300  # ESCALATEDタスクのタイムアウト（秒、デフォルト5分）

        # Load worker configuration
        self.worker_config = worker_config or get_worker_config()

        # Apply resource-based limits
        if self.max_workers > self.worker_config.max_concurrent_workers:
            logger.warning(
                f"Requested max_workers ({self.max_workers}) exceeds config limit "
                f"({self.worker_config.max_concurrent_workers}). Using config limit."
            )
            self.max_workers = self.worker_config.max_concurrent_workers

        # Initialize resource monitor
        self.resource_monitor = ResourceMonitor(
            max_cpu_percent=self.worker_config.max_cpu_percent,
            max_memory_percent=self.worker_config.max_memory_percent,
        ) if self.worker_config.enable_resource_monitoring else None

        # Track open log file handles for proper cleanup
        self._log_file_handles: List = []

        # Daemon mode: track running worker processes {task_id: {"process": Popen, "pid": int, "log_file": str, "launched_at": str}}
        self._running_workers: Dict[str, Dict[str, Any]] = {}

        # Track running review_worker processes {task_id: {"process": Popen, "pid": int, "log_file": str, "launched_at": str}}
        self._running_review_workers: Dict[str, Dict[str, Any]] = {}

        # Daemon shutdown flag
        self._shutdown_requested = False

        # Event-driven daemon loop components (TASK_1090)
        # Initialized lazily in daemon_loop() so launch() is unaffected
        self._event_notifier: Optional[Any] = None
        self._adaptive_poller: Optional[Any] = None

        self.results: Dict[str, Any] = {
            "project_id": project_id,
            "order_id": order_id,
            "launched_count": 0,
            "launched_tasks": [],
            "failed_tasks": [],
            "skipped_tasks": [],
            "errors": [],
            "resource_status": None,
            "start_time": datetime.now().isoformat(),
        }

    def launch(self) -> Dict[str, Any]:
        """
        Launch parallel workers for detected tasks

        Returns:
            Results dictionary with launched task info
        """
        try:
            # Step 0: Check system resources
            if self.resource_monitor:
                logger.info("Checking system resources...")
                self.resource_monitor.log_status()

                # Adjust max_workers based on resources if auto-scaling enabled
                if self.worker_config.enable_auto_scaling:
                    recommended_workers = self.resource_monitor.get_recommended_worker_count(
                        current_workers=0,
                        max_workers=self.max_workers,
                    )
                    if recommended_workers < self.max_workers:
                        logger.warning(
                            f"Auto-scaling: Reducing max_workers from {self.max_workers} "
                            f"to {recommended_workers} due to resource constraints"
                        )
                        self.max_workers = recommended_workers

                # Record initial resource status
                status = self.resource_monitor.get_status()
                self.results["resource_status"] = status.to_dict()

            # Step 1: Detect parallel launchable tasks
            logger.info(f"Detecting parallel launchable tasks in {self.order_id}...")
            launchable_tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
                self.project_id,
                self.order_id,
                max_tasks=self.max_workers
            )

            if not launchable_tasks:
                logger.info("No parallel launchable tasks found")
                self.results["message"] = "No parallel launchable tasks found"
                return self.results

            logger.info(f"Found {len(launchable_tasks)} parallel launchable tasks")

            if self.dry_run:
                logger.info("Dry-run mode: Not launching workers")
                self.results["message"] = "Dry-run: Would launch workers for tasks"
                self.results["detected_tasks"] = [t["id"] for t in launchable_tasks]
                return self.results

            # Step 2: Transition tasks to IN_PROGRESS and acquire file locks
            tasks_to_launch = []
            for task in launchable_tasks:
                task_id = task["id"]
                try:
                    # Acquire file locks first
                    target_files = FileLockManager.parse_target_files(
                        task.get("target_files")
                    )

                    if target_files:
                        lock_acquired = FileLockManager.acquire_locks(
                            self.project_id,
                            task_id,
                            target_files
                        )

                        if not lock_acquired:
                            logger.warning(
                                f"Task {task_id}: Failed to acquire file locks, skipping"
                            )
                            self.results["failed_tasks"].append({
                                "task_id": task_id,
                                "reason": "file_lock_conflict"
                            })
                            continue

                        logger.info(
                            f"Task {task_id}: Acquired locks for {len(target_files)} files"
                        )

                    # Transition to IN_PROGRESS
                    update_task(
                        self.project_id,
                        task_id,
                        status="IN_PROGRESS",
                        assignee="ParallelWorker",
                        role="Worker",
                    )

                    logger.info(f"Task {task_id}: Transitioned to IN_PROGRESS")
                    tasks_to_launch.append(task)

                except Exception as e:
                    logger.error(f"Task {task_id}: Failed to prepare - {e}")
                    self.results["failed_tasks"].append({
                        "task_id": task_id,
                        "reason": str(e)
                    })
                    # Release locks if acquired
                    try:
                        FileLockManager.release_locks(self.project_id, task_id)
                    except:
                        pass

            if not tasks_to_launch:
                logger.warning("No tasks could be prepared for launch")
                self.results["message"] = "No tasks could be prepared for launch"
                return self.results

            # Step 3: Launch Worker sessions in parallel
            logger.info(f"Launching {len(tasks_to_launch)} Worker sessions...")

            launched_tasks = self._launch_workers(tasks_to_launch)

            self.results["launched_count"] = len(launched_tasks)
            self.results["launched_tasks"] = launched_tasks
            self.results["end_time"] = datetime.now().isoformat()

            logger.info(
                f"Successfully launched {len(launched_tasks)}/{len(tasks_to_launch)} workers"
            )

        except Exception as e:
            logger.exception("Parallel launcher failed")
            self.results["errors"].append(str(e))

        return self.results

    def _get_log_dir(self) -> Path:
        """
        Get the LOGS directory path for this order, creating it if needed.

        Returns:
            Path to PROJECTS/{project_id}/RESULT/{order_id}/LOGS/
        """
        log_dir = USER_DATA_PATH / "PROJECTS" / self.project_id / "RESULT" / self.order_id / "LOGS"
        os.makedirs(str(log_dir), exist_ok=True)
        return log_dir

    def _get_log_file_path(self, task_id: str) -> Path:
        """
        Generate a log file path for a worker task.

        Args:
            task_id: Task ID

        Returns:
            Path like PROJECTS/{project}/RESULT/{order}/LOGS/worker_{task_id}_{YYYYMMDD_HHMMSS}.log
        """
        log_dir = self._get_log_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"worker_{task_id}_{timestamp}.log"
        return log_dir / filename

    def _launch_workers(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Launch Worker processes for each task with resource monitoring

        Args:
            tasks: List of task info dicts to launch

        Returns:
            List of successfully launched task info
        """
        launched = []
        current_worker_count = 0

        for idx, task in enumerate(tasks):
            task_id = task["id"]

            try:
                # Check resource health before each launch (if monitoring enabled)
                if self.resource_monitor and current_worker_count > 0:
                    can_launch, reason = self.resource_monitor.can_launch_worker()

                    if not can_launch:
                        logger.warning(
                            f"Task {task_id}: Skipping launch - {reason}"
                        )
                        self.results["skipped_tasks"].append({
                            "task_id": task_id,
                            "reason": f"resource_constraint: {reason}",
                            "priority": task.get("priority", "P1"),
                            "title": task.get("title", ""),
                        })

                        # Don't rollback - keep task IN_PROGRESS for later pickup
                        # It will be available when resources free up
                        logger.info(
                            f"Task {task_id}: Keeping IN_PROGRESS status for later execution"
                        )
                        continue

                # Build worker command (with per-task permission profile)
                cmd = self._build_worker_command(task_id, task_info=task)

                logger.info(
                    f"Task {task_id} [{idx+1}/{len(tasks)}]: Launching worker - "
                    f"{' '.join(cmd)}"
                )

                # Create log file for stdout/stderr redirection
                log_file_path = self._get_log_file_path(task_id)
                log_fh = open(str(log_file_path), "w", encoding="utf-8")
                self._log_file_handles.append(log_fh)

                logger.info(
                    f"Task {task_id}: Log file -> {log_file_path}"
                )

                # Launch worker process in background
                # stdout goes to log file, stderr merges into stdout
                process = subprocess.Popen(
                    cmd,
                    cwd=_package_root,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                current_worker_count += 1

                launched.append({
                    "task_id": task_id,
                    "priority": task.get("priority", "P1"),
                    "title": task.get("title", ""),
                    "pid": process.pid,
                    "command": " ".join(cmd),
                    "launched_at": datetime.now().isoformat(),
                    "log_file": str(log_file_path),
                })

                logger.info(
                    f"Task {task_id}: Worker launched (PID: {process.pid}) "
                    f"[{current_worker_count} active]"
                )

                # Brief pause between launches to avoid overwhelming the system
                if idx < len(tasks) - 1:  # Don't wait after last task
                    import time
                    time.sleep(0.5)

            except Exception as e:
                logger.error(f"Task {task_id}: Failed to launch worker - {e}", exc_info=True)
                self.results["failed_tasks"].append({
                    "task_id": task_id,
                    "reason": f"launch_failed: {e}",
                    "priority": task.get("priority", "P1"),
                    "title": task.get("title", ""),
                })

                # Rollback: Release locks and revert status
                self._rollback_task(task_id)

        # Log final resource status if monitoring enabled
        if self.resource_monitor:
            logger.info("Post-launch resource status:")
            self.resource_monitor.log_status()

        return launched

    def _build_worker_command(self, task_id: str, task_info: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Build worker execution command

        Args:
            task_id: Task ID to execute
            task_info: Optional task info dict for per-task permission profile resolution

        Returns:
            Command as list of strings
        """
        cmd = [
            "python",
            "-m",
            "worker.execute_task",
            self.project_id,
            task_id,
            "--timeout",
            str(self.timeout),
        ]

        if self.model:
            cmd.extend(["--model", self.model])

        if self.no_review:
            cmd.append("--no-review")

        if self.verbose:
            cmd.append("--verbose")

        # 権限プロファイル: ランチャーレベルの明示指定 > タスクごとの自動判定 > execute_task.py側のデフォルト
        if self.allowed_tools:
            cmd.extend(["--allowed-tools", ",".join(self.allowed_tools)])
        elif task_info and _HAS_PERMISSION_RESOLVER:
            try:
                resolver = PermissionResolver()
                tools = resolver.resolve_tools(task_info)
                if tools:
                    cmd.extend(["--allowed-tools", ",".join(tools)])
                    profile = resolver.resolve(task_info)
                    logger.info(f"Task {task_id}: auto-resolved profile={profile}, tools={len(tools)}")
            except Exception as e:
                logger.warning(f"Task {task_id}: permission profile resolution failed: {e}")
                # フォールバック: execute_task.py側でデフォルト適用

        return cmd

    def _rollback_task(self, task_id: str) -> None:
        """
        Rollback task status and locks on launch failure

        Args:
            task_id: Task ID to rollback
        """
        try:
            # Release file locks
            FileLockManager.release_locks(self.project_id, task_id)
            logger.info(f"Task {task_id}: Released file locks")

            # Revert status to QUEUED
            update_task(
                self.project_id,
                task_id,
                status="QUEUED",
                role="System",
            )
            logger.info(f"Task {task_id}: Reverted to QUEUED")

        except Exception as e:
            logger.error(f"Task {task_id}: Rollback failed - {e}")

    def get_active_worker_count(self) -> int:
        """
        Get count of currently active (IN_PROGRESS) tasks in this ORDER

        Returns:
            Number of active workers
        """
        try:
            conn = get_connection()
            try:
                result = fetch_one(
                    conn,
                    """
                    SELECT COUNT(*) as count
                    FROM tasks
                    WHERE project_id = ? AND order_id = ? AND status = 'IN_PROGRESS'
                    """,
                    (self.project_id, self.order_id)
                )
                return result["count"] if result else 0
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to get active worker count: {e}")
            return 0

    def get_worker_status_summary(self) -> Dict[str, Any]:
        """
        Get summary of worker execution status

        Returns:
            Dictionary with worker status counts
        """
        try:
            conn = get_connection()
            try:
                # Get status counts
                status_counts = fetch_all(
                    conn,
                    """
                    SELECT status, COUNT(*) as count
                    FROM tasks
                    WHERE project_id = ? AND order_id = ?
                    GROUP BY status
                    """,
                    (self.project_id, self.order_id)
                )

                summary = {
                    "QUEUED": 0,
                    "IN_PROGRESS": 0,
                    "DONE": 0,
                    "COMPLETED": 0,
                    "REWORK": 0,
                    "REJECTED": 0,
                    "BLOCKED": 0,
                }

                for row in status_counts:
                    status = row["status"]
                    count = row["count"]
                    if status in summary:
                        summary[status] = count

                return summary

            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to get worker status summary: {e}")
            return {}


    # ------------------------------------------------------------------
    # Parent heartbeat (TASK_1014)
    # ------------------------------------------------------------------

    def _get_heartbeat_file_path(self) -> Path:
        """
        Return the heartbeat file path for this daemon instance.

        Location: PROJECTS/{project_id}/RESULT/{order_id}/LOGS/daemon_heartbeat.json
        """
        log_dir = self._get_log_dir()
        return log_dir / "daemon_heartbeat.json"

    def _write_heartbeat(self) -> None:
        """
        Write heartbeat to a JSON file. Called every poll cycle.

        The file contains:
        - pid: daemon process PID
        - order_id: the ORDER being managed
        - project_id: project name
        - timestamp: ISO-format last-update time
        - active_workers: count of running workers
        - active_worker_pids: list of worker PIDs
        - status: "running" or "shutting_down"
        - adaptive_poll_interval: current adaptive polling interval (if available)
        - resource_trend: resource trend status (if available)
        """
        heartbeat_path = self._get_heartbeat_file_path()
        data = {
            "pid": os.getpid(),
            "order_id": self.order_id,
            "project_id": self.project_id,
            "timestamp": datetime.now().isoformat(),
            "active_workers": len(self._running_workers),
            "active_worker_pids": [
                info["pid"] for info in self._running_workers.values()
            ],
            "status": "shutting_down" if self._shutdown_requested else "running",
            "adaptive_poll_interval": (
                self._adaptive_poller.get_next_interval()
                if self._adaptive_poller else None
            ),
            "resource_trend": (
                self.resource_monitor.get_trend_status()
                if self.resource_monitor else None
            ),
        }
        try:
            heartbeat_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug(f"[heartbeat] Failed to write heartbeat file: {e}")

    def _remove_heartbeat(self) -> None:
        """Remove the heartbeat file on clean shutdown."""
        try:
            hb_path = self._get_heartbeat_file_path()
            if hb_path.exists():
                hb_path.unlink()
                logger.debug("[heartbeat] Heartbeat file removed")
        except Exception as e:
            logger.debug(f"[heartbeat] Failed to remove heartbeat file: {e}")

    @staticmethod
    def read_heartbeat(project_id: str, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Read and validate a daemon's heartbeat file.

        This is a static/class method so it can be called from external
        code (e.g. Electron app, CLI health check) without instantiating
        the launcher.

        Args:
            project_id: Project ID
            order_id: ORDER ID

        Returns:
            Heartbeat dict if file exists and is fresh, else None.
            Returns None if the file is older than 60 seconds.
        """
        hb_path = (
            USER_DATA_PATH / "PROJECTS" / project_id / "RESULT" / order_id
            / "LOGS" / "daemon_heartbeat.json"
        )
        try:
            if not hb_path.exists():
                return None

            data = json.loads(hb_path.read_text(encoding="utf-8"))

            # Check freshness: file mtime
            age = time.time() - hb_path.stat().st_mtime
            data["age_seconds"] = round(age, 1)
            data["is_alive"] = age < 60  # considered alive if updated within 60s

            return data
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Daemon mode (--daemon): polling loop until ORDER complete
    # ------------------------------------------------------------------

    def daemon_loop(self) -> Dict[str, Any]:
        """
        Run the launcher in daemon (resident) mode.

        Polls the DB at ``poll_interval`` seconds, detects QUEUED tasks whose
        dependencies are resolved, launches Workers up to ``max_workers``,
        reaps finished processes, and exits once every task in the ORDER has
        reached a terminal state (COMPLETED / DONE / REJECTED / CANCELLED /
        SKIPPED).

        Integrates with EventNotifier for event-driven task detection,
        DependencyResolver for automatic BLOCKED->QUEUED transitions,
        ResourceMonitor trend tracking for dynamic parallelism, and
        AdaptivePoller for adaptive sleep intervals (TASK_1090).

        Returns:
            Cumulative results dict.
        """
        logger.info(
            f"[daemon] Starting daemon loop for {self.order_id} "
            f"(poll_interval={self.poll_interval}s, max_workers={self.max_workers})"
        )

        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()

        # Initialize event-driven components (TASK_1090)
        if _HAS_EVENT_NOTIFIER:
            self._event_notifier = EventNotifier(self.project_id, self.order_id)
            self._adaptive_poller = AdaptivePoller(
                min_interval=1.0,
                max_interval=30.0,
                default_interval=float(self.poll_interval),
            )
            logger.info(
                "[daemon] Event-driven mode enabled "
                f"(adaptive polling {self._adaptive_poller.min_interval:.0f}s - "
                f"{self._adaptive_poller.max_interval:.0f}s)"
            )
        else:
            self._event_notifier = None
            self._adaptive_poller = None
            logger.info("[daemon] Event-driven mode unavailable (EventNotifier not found)")

        if _HAS_DEPENDENCY_RESOLVER:
            logger.info("[daemon] DependencyResolver integration enabled")
        else:
            logger.info("[daemon] DependencyResolver not available, using DB-only task detection")

        daemon_start = datetime.now()
        loop_count = 0
        # Track time for periodic checks (orphan review) independent of adaptive interval
        last_orphan_check_time = time.time()
        orphan_check_interval = 60  # seconds

        try:
            while not self._shutdown_requested:
                loop_count += 1
                logger.debug(f"[daemon] poll #{loop_count}")

                # 1. Reap finished workers
                self._reap_finished_workers()

                # 1.5. Check worker health (PID alive, process timeout, log staleness)
                if self._running_workers:
                    self._check_worker_health()

                # 1.6. Detect orphaned IN_PROGRESS tasks (TASK_1156 R2)
                #      Tasks that are IN_PROGRESS in DB but not tracked by this daemon
                self._detect_orphaned_in_progress_tasks()

                # 1.7. Orphaned DONE task detection (adaptive-aware: every ~60s)
                now_time = time.time()
                if now_time - last_orphan_check_time >= orphan_check_interval:
                    last_orphan_check_time = now_time
                    try:
                        # Detect orphaned DONE tasks
                        orphaned_tasks = find_orphaned_done_tasks(
                            project_id=self.project_id
                        )
                        if orphaned_tasks:
                            logger.info(
                                f"[daemon] Detected {len(orphaned_tasks)} orphaned DONE task(s) "
                                f"awaiting review (reviewed_at IS NULL)"
                            )
                            # Launch review_worker for each orphaned task
                            for task in orphaned_tasks:
                                self._launch_review_worker(task)
                    except Exception as e:
                        logger.warning(f"[daemon] Orphan DONE task detection failed: {e}")

                # 1.8. Reap finished review_workers
                self._reap_finished_review_workers()

                # 2. Event consumption + dependency resolution (TASK_1090)
                if self._event_notifier:
                    events = self._event_notifier.consume_events()
                    if events:
                        self._adaptive_poller.notify_event_detected()
                        for ev in events:
                            ev_type = ev.get("event_type", "")
                            ev_task_id = ev.get("task_id", "")
                            logger.info(
                                f"[daemon] Event consumed: {ev_type} for {ev_task_id}"
                            )
                            if ev_type in ("TASK_COMPLETED", "DEPENDENCY_RESOLVED"):
                                if _HAS_DEPENDENCY_RESOLVER:
                                    try:
                                        newly_queued = resolve_on_completion(
                                            self.project_id,
                                            self.order_id,
                                            ev_task_id,
                                        )
                                        if newly_queued:
                                            logger.info(
                                                f"[daemon] DependencyResolver unblocked "
                                                f"{len(newly_queued)} task(s): {newly_queued}"
                                            )
                                    except Exception as e:
                                        logger.warning(
                                            f"[daemon] resolve_on_completion failed "
                                            f"for {ev_task_id}: {e}"
                                        )
                    else:
                        self._adaptive_poller.notify_idle_cycle()

                # 2.5. Resource trend sampling (TASK_1090)
                if self.resource_monitor:
                    self.resource_monitor.collect_sample()

                # 2.7. ESCALATED task timeout safety valve (TASK_1147)
                self._check_escalated_timeout()

                # 3. Check if ORDER is complete
                summary = self.get_worker_status_summary()
                if self._is_order_complete(summary):
                    logger.info(
                        f"[daemon] ORDER {self.order_id} complete: {summary}"
                    )
                    break

                # 4. Launch new workers if slots available (dynamic parallelism)
                active_count = len(self._running_workers)

                # Apply dynamic max_workers based on resource trends (TASK_1090)
                if self.resource_monitor and self.worker_config.enable_auto_scaling:
                    dynamic_max = self.resource_monitor.get_predicted_worker_count(
                        active_count, self.max_workers
                    )
                else:
                    dynamic_max = self.max_workers

                available_slots = dynamic_max - active_count

                if available_slots > 0:
                    launchable = ParallelTaskDetector.find_parallel_launchable_tasks(
                        self.project_id,
                        self.order_id,
                        max_tasks=available_slots,
                    )

                    if launchable:
                        logger.info(
                            f"[daemon] {len(launchable)} launchable tasks found, "
                            f"{active_count} active, {available_slots} slots "
                            f"(dynamic_max={dynamic_max})"
                        )
                        self._daemon_launch_batch(launchable)

                # 4.5. Write heartbeat
                self._write_heartbeat()

                # 5. Log periodic status (adaptive-aware: every ~60s)
                if now_time - last_orphan_check_time < 1.0:
                    # Piggyback on the orphan-check timing (~60s)
                    self._log_daemon_status(summary, daemon_start)

                # 6. Adaptive sleep (TASK_1090)
                if self._adaptive_poller:
                    sleep_interval = self._adaptive_poller.get_next_interval()
                    self._interruptible_sleep_float(sleep_interval)
                else:
                    self._interruptible_sleep(self.poll_interval)

        except KeyboardInterrupt:
            logger.info("[daemon] KeyboardInterrupt received, shutting down...")
        except Exception as e:
            logger.exception(f"[daemon] Unexpected error in daemon loop: {e}")
            self.results["errors"].append(f"daemon_loop: {e}")
        finally:
            # Final reap
            self._reap_finished_workers()
            self._cleanup_log_handles()
            self._remove_heartbeat()
            # Event cleanup (TASK_1090)
            if self._event_notifier:
                try:
                    self._event_notifier.cleanup_old_events()
                except Exception as e:
                    logger.debug(f"[daemon] Event cleanup failed: {e}")

        self.results["end_time"] = datetime.now().isoformat()
        self.results["daemon_loops"] = loop_count
        elapsed = (datetime.now() - daemon_start).total_seconds()
        self.results["daemon_elapsed_seconds"] = round(elapsed, 1)

        final_summary = self.get_worker_status_summary()
        self.results["final_status_summary"] = final_summary

        # Record adaptive poller stats (TASK_1090)
        if self._adaptive_poller:
            self.results["adaptive_poller_stats"] = self._adaptive_poller.to_dict()

        logger.info(
            f"[daemon] Daemon loop ended after {loop_count} polls "
            f"({elapsed:.0f}s). Final: {final_summary}"
        )

        return self.results

    def _register_signal_handlers(self) -> None:
        """Register signal handlers for graceful daemon shutdown."""
        def _handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info(f"[daemon] Received {sig_name}, requesting shutdown...")
            self._shutdown_requested = True

        try:
            signal.signal(signal.SIGTERM, _handle_signal)
            signal.signal(signal.SIGINT, _handle_signal)
        except (OSError, ValueError):
            # signal handling may not be available in all contexts
            pass

    def _interruptible_sleep(self, seconds: int) -> None:
        """Sleep in small increments so we can respond to shutdown quickly."""
        for _ in range(seconds * 2):
            if self._shutdown_requested:
                break
            time.sleep(0.5)

    def _interruptible_sleep_float(self, seconds: float) -> None:
        """Sleep in small increments (0.5s) for float seconds.

        Similar to ``_interruptible_sleep`` but accepts float values,
        which is required for the AdaptivePoller integration.
        """
        steps = int(seconds / 0.5)
        for _ in range(max(steps, 1)):
            if self._shutdown_requested:
                break
            time.sleep(0.5)

    def _is_order_complete(self, summary: Dict[str, Any]) -> bool:
        """
        Check whether all tasks in the ORDER have reached a terminal state.

        Terminal states: COMPLETED, REJECTED, CANCELLED, SKIPPED.
        Non-terminal: QUEUED, BLOCKED, IN_PROGRESS, DONE, REWORK, ESCALATED.
        """
        non_terminal = (
            summary.get("QUEUED", 0)
            + summary.get("BLOCKED", 0)
            + summary.get("IN_PROGRESS", 0)
            + summary.get("DONE", 0)
            + summary.get("REWORK", 0)
            + summary.get("ESCALATED", 0)
        )
        return non_terminal == 0

    def _reap_finished_workers(self) -> None:
        """
        Check running workers and reap any that have finished.

        For each finished process:
        - Record the exit code
        - Emit completion/failure event via EventNotifier (TASK_1090)
        - Remove from ``_running_workers``

        Also checks PID liveness when proc.poll() returns None (TASK_1156):
        if the PID is actually dead (zombie/orphan), treat as crashed.
        """
        finished: List[tuple] = []  # list of (task_id, retcode)
        crashed_pids: List[str] = []  # task_ids whose PID is dead but poll() returned None

        for task_id, info in self._running_workers.items():
            proc: subprocess.Popen = info["process"]
            retcode = proc.poll()  # None if still running

            if retcode is not None:
                finished.append((task_id, retcode))
                if retcode == 0:
                    logger.info(
                        f"[daemon] Worker for {task_id} finished successfully "
                        f"(PID {proc.pid})"
                    )
                else:
                    logger.warning(
                        f"[daemon] Worker for {task_id} exited with code {retcode} "
                        f"(PID {proc.pid})"
                    )
                    self.results["failed_tasks"].append({
                        "task_id": task_id,
                        "reason": f"exit_code_{retcode}",
                    })
            else:
                # proc.poll() returned None (appears running), but verify PID is alive (TASK_1156)
                pid = info["pid"]
                if not self._is_pid_alive(pid):
                    logger.warning(
                        f"[daemon] Worker for {task_id}: proc.poll() returned None "
                        f"but PID {pid} is dead (zombie/orphan). Treating as crashed."
                    )
                    crashed_pids.append(task_id)

        for task_id, retcode in finished:
            del self._running_workers[task_id]

            # ORDER_142: Worker正常終了時にREPORTファイル存在を検証
            if retcode == 0:
                report_num = task_id.replace("TASK_", "")
                report_file = (
                    USER_DATA_PATH / "PROJECTS" / self.project_id / "RESULT"
                    / self.order_id / "05_REPORT" / f"REPORT_{report_num}.md"
                )
                if not report_file.exists():
                    logger.error(
                        f"[daemon] Worker {task_id} exited 0 but REPORT missing: {report_file}. "
                        f"Reverting to REWORK."
                    )
                    self.results["failed_tasks"].append({
                        "task_id": task_id,
                        "reason": "report_missing_after_exit_0",
                        "report_file": str(report_file),
                    })
                    try:
                        update_task(
                            self.project_id,
                            task_id,
                            status="REWORK",
                            role="System",
                        )
                        logger.info(f"[daemon] Reverted {task_id} to REWORK (REPORT missing)")
                    except Exception as revert_err:
                        logger.error(f"[daemon] Failed to revert {task_id}: {revert_err}")
                    # Skip event emission for failed REPORT validation
                    continue
                else:
                    report_size = report_file.stat().st_size
                    if report_size < 100:
                        logger.warning(
                            f"[daemon] Worker {task_id} REPORT suspiciously small: "
                            f"{report_size} bytes ({report_file})"
                        )
                    else:
                        logger.info(
                            f"[daemon] Worker {task_id} finished with REPORT "
                            f"({report_size} bytes)"
                        )

            # Emit event for event-driven loop (TASK_1090)
            if self._event_notifier:
                try:
                    if retcode == 0:
                        self._event_notifier.emit_task_completed(task_id)
                        # TASK_1103: 依存関係解決イベントも送信
                        self._event_notifier.emit_dependency_resolved(task_id)
                    else:
                        self._event_notifier.emit_task_failed(
                            task_id, f"exit_code_{retcode}"
                        )
                except Exception as e:
                    logger.debug(
                        f"[daemon] Failed to emit event for {task_id}: {e}"
                    )

        # Recover workers whose PID is dead but proc.poll() missed it (TASK_1156)
        for task_id in crashed_pids:
            self._recover_stuck_worker(task_id, detection_method="pid_alive_check")

    def _daemon_launch_batch(self, tasks: List[Dict[str, Any]]) -> None:
        """
        Launch a batch of workers in daemon mode.

        Similar to ``_launch_workers`` but stores process handles in
        ``_running_workers`` for lifecycle tracking.
        """
        for task in tasks:
            task_id = task["id"]

            # Skip if already running (race condition guard)
            if task_id in self._running_workers:
                logger.debug(f"[daemon] {task_id} already running, skipping")
                continue

            try:
                # Acquire file locks
                target_files = FileLockManager.parse_target_files(
                    task.get("target_files")
                )
                if target_files:
                    lock_acquired = FileLockManager.acquire_locks(
                        self.project_id, task_id, target_files
                    )
                    if not lock_acquired:
                        logger.warning(f"[daemon] {task_id}: file lock conflict, skipping")
                        continue

                # Transition to IN_PROGRESS
                update_task(
                    self.project_id,
                    task_id,
                    status="IN_PROGRESS",
                    assignee="ParallelWorker",
                    role="Worker",
                )

                # Build command & launch (with per-task permission profile)
                cmd = self._build_worker_command(task_id, task_info=task)
                log_file_path = self._get_log_file_path(task_id)
                log_fh = open(str(log_file_path), "w", encoding="utf-8")
                self._log_file_handles.append(log_fh)

                process = subprocess.Popen(
                    cmd,
                    cwd=_package_root,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                self._running_workers[task_id] = {
                    "process": process,
                    "pid": process.pid,
                    "log_file": str(log_file_path),
                    "launched_at": datetime.now().isoformat(),
                }

                self.results["launched_count"] += 1
                self.results["launched_tasks"].append({
                    "task_id": task_id,
                    "pid": process.pid,
                    "title": task.get("title", ""),
                    "priority": task.get("priority", "P1"),
                    "log_file": str(log_file_path),
                    "launched_at": datetime.now().isoformat(),
                })

                logger.info(
                    f"[daemon] Launched {task_id} (PID {process.pid}), "
                    f"active={len(self._running_workers)}/{self.max_workers}"
                )

                # Brief pause between launches
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[daemon] Failed to launch {task_id}: {e}")
                self.results["failed_tasks"].append({
                    "task_id": task_id,
                    "reason": f"launch_failed: {e}",
                })
                self._rollback_task(task_id)

    # ------------------------------------------------------------------
    # Review Worker Management (TASK_1141)
    # ------------------------------------------------------------------

    def _launch_review_worker(self, task: Dict[str, Any]) -> bool:
        """
        Launch review_worker.py as a separate process for a DONE task.

        Args:
            task: Task dict with keys: task_id, project_id, order_id, title, etc.

        Returns:
            True if launched successfully, False otherwise
        """
        task_id = task["task_id"]
        project_id = task["project_id"]

        # Skip if already running (avoid duplicate reviews)
        if task_id in self._running_review_workers:
            logger.debug(f"[review_worker] {task_id} already under review, skipping")
            return False

        try:
            # Build command to launch review_worker.py
            review_worker_script = _package_root / "review_worker.py"

            # Use the same Python interpreter as the current process
            cmd = [
                sys.executable,
                str(review_worker_script),
                project_id,
                task_id,
                "--model", self.model or "sonnet",
                "--timeout", str(self.timeout),
            ]

            if self.verbose:
                cmd.append("--verbose")

            # Create log file for review_worker output
            log_dir = USER_DATA_PATH / "logs" / "review_workers"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file_path = log_dir / f"{task_id}_review.log"

            # Open log file
            log_fh = open(str(log_file_path), "w", encoding="utf-8")
            self._log_file_handles.append(log_fh)

            # Launch review_worker subprocess
            process = subprocess.Popen(
                cmd,
                cwd=_package_root,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Track the review_worker process
            self._running_review_workers[task_id] = {
                "process": process,
                "pid": process.pid,
                "log_file": str(log_file_path),
                "launched_at": datetime.now().isoformat(),
                "project_id": project_id,
                "order_id": task.get("order_id"),
            }

            logger.info(
                f"[review_worker] Launched review_worker for {task_id} "
                f"(PID {process.pid}, log: {log_file_path.name})"
            )
            return True

        except Exception as e:
            logger.error(f"[review_worker] Failed to launch review_worker for {task_id}: {e}")
            return False

    def _reap_finished_review_workers(self) -> None:
        """
        Check for finished review_worker processes and log their results.

        Removes completed review_workers from _running_review_workers.
        """
        finished_tasks = []

        for task_id, info in list(self._running_review_workers.items()):
            proc: subprocess.Popen = info["process"]
            retcode = proc.poll()

            if retcode is not None:
                # Process finished
                finished_tasks.append(task_id)
                log_file = info.get("log_file", "")

                if retcode == 0:
                    logger.info(
                        f"[review_worker] Review completed successfully for {task_id} "
                        f"(PID {info['pid']}, exit code {retcode})"
                    )
                else:
                    logger.warning(
                        f"[review_worker] Review failed for {task_id} "
                        f"(PID {info['pid']}, exit code {retcode}). "
                        f"Check log: {log_file}"
                    )

        # Remove finished review_workers from tracking
        for task_id in finished_tasks:
            del self._running_review_workers[task_id]

        if finished_tasks:
            logger.debug(
                f"[review_worker] Reaped {len(finished_tasks)} finished review_worker(s): "
                f"{', '.join(finished_tasks)}"
            )

    # ------------------------------------------------------------------
    # Worker health monitoring (TASK_1013)
    # ------------------------------------------------------------------

    def _check_worker_health(self) -> None:
        """
        Check the health of all running workers.

        For each tracked worker:
        1. PID liveness: is the process still alive?
        2. Process timeout: has the worker exceeded worker_process_timeout? (TASK_1156)
        3. Log staleness: has the log file been updated recently?

        If a worker is detected as stuck, initiate recovery with detection_method.
        """
        stuck_tasks: List[tuple] = []  # list of (task_id, detection_method)

        for task_id, info in list(self._running_workers.items()):
            proc: subprocess.Popen = info["process"]
            pid = info["pid"]
            log_file = info.get("log_file")

            # --- Check 1: PID liveness ---
            retcode = proc.poll()
            if retcode is not None:
                # Process already exited - will be handled by _reap_finished_workers
                continue

            # Process is running, check if it's actually making progress
            if not self._is_pid_alive(pid):
                logger.warning(
                    f"[health] {task_id}: PID {pid} is no longer alive "
                    f"(zombie / orphaned)"
                )
                stuck_tasks.append((task_id, "pid_alive_check"))
                continue

            # --- Check 2: Process timeout (TASK_1156) ---
            launched_at_str = info.get("launched_at")
            if launched_at_str and self.worker_process_timeout > 0:
                try:
                    launched_at = datetime.fromisoformat(launched_at_str)
                    elapsed = (datetime.now() - launched_at).total_seconds()
                    if elapsed > self.worker_process_timeout:
                        logger.warning(
                            f"[health] {task_id}: Process timeout exceeded "
                            f"({elapsed:.0f}s > {self.worker_process_timeout}s, PID {pid})"
                        )
                        stuck_tasks.append((task_id, "process_timeout"))
                        continue
                except (ValueError, TypeError):
                    pass

            # --- Check 3: Log staleness ---
            if log_file and self._is_log_stale(log_file):
                logger.warning(
                    f"[health] {task_id}: Log file stale for "
                    f">{self.stale_log_timeout}s (PID {pid})"
                )
                stuck_tasks.append((task_id, "log_staleness"))
                continue

        # Recover stuck workers
        for task_id, detection_method in stuck_tasks:
            self._recover_stuck_worker(task_id, detection_method=detection_method)

    def _is_pid_alive(self, pid: int) -> bool:
        """
        Check whether a process with the given PID is still alive.

        Works on both Windows and Unix.
        """
        try:
            if sys.platform == "win32":
                # Windows: use ctypes or subprocess
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                # Unix: send signal 0
                os.kill(pid, 0)
                return True
        except (OSError, ProcessLookupError, PermissionError):
            return False
        except Exception:
            # Assume alive if we can't check
            return True

    def _is_log_stale(self, log_file: str) -> bool:
        """
        Check if the log file has not been updated for longer than
        ``stale_log_timeout`` seconds.
        """
        try:
            log_path = Path(log_file)
            if not log_path.exists():
                # Log file not yet created – not stale
                return False

            mtime = log_path.stat().st_mtime
            age = time.time() - mtime
            return age > self.stale_log_timeout
        except Exception as e:
            logger.debug(f"[health] Cannot stat log file {log_file}: {e}")
            return False

    # ------------------------------------------------------------------
    # Orphaned IN_PROGRESS task detection (TASK_1156)
    # ------------------------------------------------------------------

    def _detect_orphaned_in_progress_tasks(self) -> None:
        """
        Detect IN_PROGRESS tasks in this ORDER that are NOT tracked in
        ``_running_workers``.

        These are orphans: their daemon was restarted (dict lost), the
        worker process died without being reaped, etc.

        For each orphan, use ``recover_crashed_task()`` from
        ``worker.recover_crashed`` to revert the task to QUEUED and
        release file locks.
        """
        try:
            conn = get_connection()
            try:
                rows = fetch_all(
                    conn,
                    """
                    SELECT id AS task_id
                    FROM tasks
                    WHERE project_id = ? AND order_id = ? AND status = 'IN_PROGRESS'
                    """,
                    (self.project_id, self.order_id),
                )
            finally:
                conn.close()

            if not rows:
                return

            orphans_found = 0

            for row in rows:
                task_id = row["task_id"]

                # If this task is tracked in _running_workers, it is NOT an orphan
                if task_id in self._running_workers:
                    continue

                # Orphan detected: IN_PROGRESS in DB but not tracked by daemon
                orphans_found += 1
                logger.warning(
                    f"[orphan-ip] Orphaned IN_PROGRESS task detected: {task_id} "
                    f"(not tracked in _running_workers)"
                )

                # Recover using recover_crashed_task (preferred) or fallback
                if _HAS_RECOVER_CRASHED:
                    reason = (
                        f"Orphan detection: task IN_PROGRESS but not tracked by daemon "
                        f"(detection_method=orphan_detection)"
                    )
                    result = recover_crashed_task(
                        project_id=self.project_id,
                        task_id=task_id,
                        reason=reason,
                    )
                    if result.get("success"):
                        logger.info(
                            f"[orphan-ip] Recovered orphan {task_id}: "
                            f"IN_PROGRESS -> QUEUED, locks_released={result.get('locks_released', 0)}"
                        )
                    else:
                        logger.warning(
                            f"[orphan-ip] Failed to recover orphan {task_id}: "
                            f"{result.get('error', 'unknown')}"
                        )
                else:
                    # Fallback: manual recovery (same as _recover_stuck_worker but without process kill)
                    try:
                        FileLockManager.release_locks(self.project_id, task_id)
                        update_task(
                            self.project_id,
                            task_id,
                            status="QUEUED",
                            role="System",
                            reason="Orphan IN_PROGRESS recovery (daemon restart)",
                        )
                        logger.info(f"[orphan-ip] Fallback recovery: {task_id} -> QUEUED")
                    except Exception as e:
                        logger.error(f"[orphan-ip] Fallback recovery failed for {task_id}: {e}")

                # Emit WORKER_CRASHED event (TASK_1156 R4)
                if self._event_notifier:
                    try:
                        self._event_notifier.emit_worker_crashed(
                            task_id,
                            reason="orphan_detection",
                            metadata={
                                "detection_method": "orphan_detection",
                                "project_id": self.project_id,
                                "order_id": self.order_id,
                            },
                        )
                    except Exception as e:
                        logger.debug(f"[orphan-ip] Failed to emit WORKER_CRASHED for {task_id}: {e}")

                # Track recovery event
                self.results.setdefault("recovered_tasks", []).append({
                    "task_id": task_id,
                    "pid": None,
                    "recovered_at": datetime.now().isoformat(),
                    "reason": "orphan_in_progress",
                    "detection_method": "orphan_detection",
                })

            if orphans_found > 0:
                logger.info(
                    f"[orphan-ip] Detected and recovered {orphans_found} "
                    f"orphaned IN_PROGRESS task(s)"
                )

        except Exception as e:
            logger.warning(f"[orphan-ip] Orphan IN_PROGRESS detection failed: {e}")

    def _recover_stuck_worker(self, task_id: str, detection_method: str = "unknown") -> None:
        """
        Recover a stuck worker:
        1. Kill the process
        2. Release file locks
        3. Revert task status to QUEUED
        4. Record the incident in change_history (with detection_method + elapsed_seconds)
        5. Emit WORKER_CRASHED event if EventNotifier available (TASK_1156 R4)
        """
        info = self._running_workers.get(task_id)
        if not info:
            return

        proc: subprocess.Popen = info["process"]
        pid = info["pid"]

        # Calculate elapsed time since launch (TASK_1156 R5)
        elapsed_seconds = 0.0
        launched_at_str = info.get("launched_at")
        if launched_at_str:
            try:
                launched_at = datetime.fromisoformat(launched_at_str)
                elapsed_seconds = (datetime.now() - launched_at).total_seconds()
            except (ValueError, TypeError):
                pass

        logger.warning(
            f"[health] Recovering stuck worker {task_id} (PID {pid}, "
            f"detection_method={detection_method}, elapsed={elapsed_seconds:.0f}s)"
        )

        # 1. Kill the process
        try:
            proc.kill()
            proc.wait(timeout=5)
            logger.info(f"[health] Killed PID {pid} for {task_id}")
        except Exception as e:
            logger.warning(f"[health] Failed to kill PID {pid}: {e}")
            # Try OS-level kill
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True, timeout=5,
                    )
                else:
                    os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

        # 2. Release file locks (BUG_008: always release for crashed tasks)
        try:
            FileLockManager.release_locks(self.project_id, task_id)
            logger.info(f"[health] Released file locks for {task_id}")
        except Exception as e:
            logger.warning(f"[health] Failed to release locks for {task_id}: {e}")

        # 3. Revert task status to QUEUED
        try:
            update_task(
                self.project_id,
                task_id,
                status="QUEUED",
                role="System",
                reason=(
                    f"Auto-recovery: worker stuck "
                    f"(PID {pid}, detection_method={detection_method}, "
                    f"elapsed={elapsed_seconds:.0f}s)"
                ),
            )
            logger.info(f"[health] Reverted {task_id} to QUEUED")
        except Exception as e:
            logger.error(f"[health] Failed to revert {task_id} status: {e}")

        # 4. Record in change_history (enhanced with detection_method + elapsed_seconds, TASK_1156 R5)
        try:
            conn = get_connection()
            try:
                change_reason = (
                    f"Worker stuck recovery: PID {pid} killed, "
                    f"locks released, status reverted. "
                    f"detection_method={detection_method}, "
                    f"elapsed_seconds={elapsed_seconds:.0f}"
                )
                execute_query(
                    conn,
                    """
                    INSERT INTO change_history
                        (entity_type, entity_id, field_name, old_value, new_value,
                         changed_by, change_reason, changed_at, project_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "task",
                        task_id,
                        "status",
                        "IN_PROGRESS",
                        "QUEUED",
                        "DaemonHealthCheck",
                        change_reason,
                        datetime.now().isoformat(),
                        self.project_id,
                    ),
                )
                conn.commit()
                logger.info(f"[health] Recorded recovery in change_history for {task_id}")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[health] Failed to record change_history: {e}")

        # 5. Remove from running workers
        del self._running_workers[task_id]

        # 6. Emit WORKER_CRASHED event (TASK_1156 R4)
        if self._event_notifier:
            try:
                self._event_notifier.emit_worker_crashed(
                    task_id,
                    reason=detection_method,
                    metadata={
                        "pid": pid,
                        "detection_method": detection_method,
                        "elapsed_seconds": round(elapsed_seconds, 1),
                        "project_id": self.project_id,
                        "order_id": self.order_id,
                    },
                )
            except Exception as e:
                logger.debug(f"[health] Failed to emit WORKER_CRASHED for {task_id}: {e}")

        # Track recovery event
        self.results.setdefault("recovered_tasks", []).append({
            "task_id": task_id,
            "pid": pid,
            "recovered_at": datetime.now().isoformat(),
            "reason": "stuck_worker",
            "detection_method": detection_method,
            "elapsed_seconds": round(elapsed_seconds, 1),
        })

    # ------------------------------------------------------------------
    # ESCALATED task timeout safety valve (TASK_1147)
    # ------------------------------------------------------------------

    def _check_escalated_timeout(self) -> None:
        """
        Check for ESCALATED tasks that have not transitioned within
        ``escalated_timeout`` seconds. Auto-reject them to prevent
        the daemon loop from hanging indefinitely.

        This is a safety valve: normally, process_review.py's PM auto-judge
        (TASK_1146) handles ESCALATED→QUEUED/REJECTED transitions.
        This timeout catches cases where that mechanism fails.
        """
        try:
            conn = get_connection()
            try:
                rows = fetch_all(
                    conn,
                    """
                    SELECT id, updated_at, title
                    FROM tasks
                    WHERE project_id = ? AND order_id = ? AND status = 'ESCALATED'
                    """,
                    (self.project_id, self.order_id),
                )

                if not rows:
                    return

                now = datetime.now()
                timed_out_tasks = []

                for row in rows:
                    task_id = row["id"]
                    updated_at_str = row["updated_at"]
                    title = row["title"]

                    if not updated_at_str:
                        continue

                    try:
                        updated_at = datetime.fromisoformat(updated_at_str)
                        age_seconds = (now - updated_at).total_seconds()

                        if age_seconds > self.escalated_timeout:
                            timed_out_tasks.append((task_id, title, age_seconds))
                    except (ValueError, TypeError):
                        continue

                # Auto-reject timed-out ESCALATED tasks
                for task_id, title, age_seconds in timed_out_tasks:
                    logger.warning(
                        f"[escalated-timeout] {task_id} has been ESCALATED for "
                        f"{age_seconds:.0f}s (timeout={self.escalated_timeout}s). "
                        f"Auto-rejecting."
                    )
                    self._auto_reject_escalated_task(task_id, age_seconds)

            finally:
                conn.close()

        except Exception as e:
            logger.warning(f"[escalated-timeout] Check failed: {e}")

    def _auto_reject_escalated_task(self, task_id: str, age_seconds: float) -> None:
        """
        Auto-reject an ESCALATED task that has timed out.

        Args:
            task_id: The task ID to reject
            age_seconds: How long the task has been ESCALATED
        """
        conn = get_connection()
        try:
            # Update status to REJECTED
            execute_query(
                conn,
                """
                UPDATE tasks
                SET status = 'REJECTED', updated_at = ?
                WHERE id = ? AND project_id = ? AND status = 'ESCALATED'
                """,
                (datetime.now().isoformat(), task_id, self.project_id),
            )
            conn.commit()

            # Record transition in change_history
            execute_query(
                conn,
                """
                INSERT INTO change_history
                    (entity_type, entity_id, field_name, old_value, new_value,
                     changed_by, change_reason, changed_at, project_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "task",
                    task_id,
                    "status",
                    "ESCALATED",
                    "REJECTED",
                    "DaemonTimeoutCheck",
                    f"ESCALATED timeout ({age_seconds:.0f}s > {self.escalated_timeout}s). "
                    f"Auto-rejected as safety valve.",
                    datetime.now().isoformat(),
                    self.project_id,
                ),
            )
            conn.commit()

            # Record in escalations table
            try:
                from escalation.log_escalation import log_escalation, EscalationType
                log_escalation(
                    project_id=self.project_id,
                    task_id=task_id,
                    escalation_type=EscalationType.ESCALATION_TIMEOUT,
                    description=(
                        f"ESCALATEDタイムアウト: {age_seconds:.0f}秒経過 "
                        f"(上限: {self.escalated_timeout}秒). 自動REJECTED."
                    ),
                    order_id=self.order_id,
                    metadata={
                        "timeout_seconds": self.escalated_timeout,
                        "actual_seconds": round(age_seconds, 1),
                    },
                )
            except Exception as log_err:
                logger.warning(f"[escalated-timeout] Escalation log failed: {log_err}")

            logger.info(
                f"[escalated-timeout] {task_id}: ESCALATED → REJECTED "
                f"(timeout after {age_seconds:.0f}s)"
            )

            # Track in results
            self.results.setdefault("escalated_timeouts", []).append({
                "task_id": task_id,
                "age_seconds": round(age_seconds, 1),
                "rejected_at": datetime.now().isoformat(),
            })

        except Exception as e:
            logger.error(f"[escalated-timeout] Failed to reject {task_id}: {e}")
        finally:
            conn.close()

    def _log_daemon_status(
        self, summary: Dict[str, Any], start_time: datetime
    ) -> None:
        """Log a periodic daemon status line."""
        elapsed = (datetime.now() - start_time).total_seconds()
        active = len(self._running_workers)
        active_pids = [
            f"{tid}(PID:{info['pid']})"
            for tid, info in self._running_workers.items()
        ]
        logger.info(
            f"[daemon] status: elapsed={elapsed:.0f}s, "
            f"active_workers={active}/{self.max_workers}, "
            f"running={active_pids}, summary={summary}"
        )

    def _cleanup_log_handles(self) -> None:
        """Close all open log file handles."""
        for fh in self._log_file_handles:
            try:
                fh.close()
            except Exception:
                pass
        self._log_file_handles.clear()


def display_results(results: Dict[str, Any], json_output: bool = False) -> None:
    """
    Display launch results

    Args:
        results: Results dictionary
        json_output: If True, output as JSON
    """
    if json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print("\n" + "="*80)
    print(f"Parallel Worker Launch Results - {results['order_id']}")
    print("="*80)

    print(f"\nProject: {results['project_id']}")
    print(f"ORDER: {results['order_id']}")
    print(f"Start Time: {results['start_time']}")

    if results.get("end_time"):
        print(f"End Time: {results['end_time']}")

    # Resource status
    if results.get("resource_status"):
        res = results["resource_status"]
        print(f"\n【リソース状況】")
        print(f"  CPU: {res['cpu_percent']:.1f}%")
        print(f"  Memory: {res['memory_percent']:.1f}%")
        print(f"  Available Memory: {res['available_memory_mb']:.0f} MB")
        if res.get("blocking_reason"):
            print(f"  ⚠️  {res['blocking_reason']}")

    print(f"\n【起動状況】")
    print(f"  Successfully Launched: {results['launched_count']}")
    print(f"  Skipped (Resource Constraints): {len(results.get('skipped_tasks', []))}")
    print(f"  Failed: {len(results['failed_tasks'])}")

    if results["launched_tasks"]:
        print(f"\n【起動済みWorker】({len(results['launched_tasks'])}件)")
        print("  " + "-"*76)
        print(f"  {'Task ID':<15} {'Priority':<10} {'PID':<10} {'Title':<40}")
        print("  " + "-"*76)

        for task in results["launched_tasks"]:
            task_id = task["task_id"]
            priority = task.get("priority", "P1")
            pid = task.get("pid", "N/A")
            title = task.get("title", "")[:37] + "..." if len(task.get("title", "")) > 40 else task.get("title", "")
            print(f"  {task_id:<15} {priority:<10} {pid:<10} {title:<40}")
            if task.get("log_file"):
                print(f"    Log: {task['log_file']}")

        print("  " + "-"*76)

    if results.get("skipped_tasks"):
        print(f"\n【スキップ（リソース制約）】({len(results['skipped_tasks'])}件)")
        for skip in results["skipped_tasks"]:
            print(f"  - {skip['task_id']} ({skip['priority']}): {skip['reason']}")
        print(f"  ℹ️  These tasks remain IN_PROGRESS and will execute when resources free up")

    if results["failed_tasks"]:
        print(f"\n【失敗タスク】({len(results['failed_tasks'])}件)")
        for fail in results["failed_tasks"]:
            print(f"  - {fail['task_id']}: {fail['reason']}")

    if results.get("message"):
        print(f"\n{results['message']}")

    if results["errors"]:
        print(f"\n【エラー】")
        for error in results["errors"]:
            print(f"  - {error}")

    print("\n" + "="*80)


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
        description="Launch multiple Worker sessions in parallel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="Project ID")
    parser.add_argument("order_id", help="ORDER ID")
    parser.add_argument("--max-workers", type=int, default=5, help="Maximum number of parallel workers (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Show execution plan without launching")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed logging")
    parser.add_argument("--json", action="store_true", help="JSON output format")
    parser.add_argument("--timeout", type=int, default=1800, help="Worker timeout in seconds (default: 1800)")
    parser.add_argument("--model", help="AI model for workers (haiku/sonnet/opus)")
    parser.add_argument("--no-review", action="store_true", help="Disable auto-review after worker completion")
    parser.add_argument("--max-cpu", type=float, help="Maximum CPU usage percent threshold (default: 85.0)")
    parser.add_argument("--max-memory", type=float, help="Maximum memory usage percent threshold (default: 85.0)")
    parser.add_argument("--no-resource-monitoring", action="store_true", help="Disable resource monitoring")
    parser.add_argument("--no-auto-scaling", action="store_true", help="Disable auto-scaling based on resources")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon (resident) mode: poll DB, launch workers, and exit when ORDER completes")
    parser.add_argument("--poll-interval", type=int, default=10, help="Daemon poll interval in seconds (default: 10)")
    parser.add_argument("--stale-log-timeout", type=int, default=600, help="Seconds without log update before worker is considered stuck (default: 600)")
    parser.add_argument("--worker-process-timeout", type=int, default=1800, help="Maximum seconds a worker process may run before being killed (default: 1800)")
    parser.add_argument("--allowed-tools", type=str, default=None,
                        help="Comma-separated list of allowed tools for workers (e.g. Read,Write,Bash). Uses default if not specified")
    parser.add_argument("--escalated-timeout", type=int, default=300,
                        help="Seconds before ESCALATED tasks are auto-rejected (default: 300)")

    args = parser.parse_args()

    # Enable debug logging if verbose
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Validate project
        validate_project_name(args.project_id)

        # Build worker configuration
        worker_config = get_worker_config()

        # Override with CLI arguments if provided
        if args.max_cpu is not None:
            worker_config.max_cpu_percent = args.max_cpu
        if args.max_memory is not None:
            worker_config.max_memory_percent = args.max_memory
        if args.no_resource_monitoring:
            worker_config.enable_resource_monitoring = False
        if args.no_auto_scaling:
            worker_config.enable_auto_scaling = False

        # Parse allowed_tools
        allowed_tools = None
        if args.allowed_tools:
            allowed_tools = [t.strip() for t in args.allowed_tools.split(",") if t.strip()]

        # Launch parallel workers
        launcher = ParallelWorkerLauncher(
            args.project_id,
            args.order_id,
            max_workers=args.max_workers,
            dry_run=args.dry_run,
            verbose=args.verbose,
            timeout=args.timeout,
            model=args.model,
            no_review=args.no_review,
            worker_config=worker_config,
            poll_interval=args.poll_interval,
            stale_log_timeout=args.stale_log_timeout,
            worker_process_timeout=args.worker_process_timeout,
            allowed_tools=allowed_tools,
        )
        launcher.escalated_timeout = args.escalated_timeout

        if args.daemon:
            # Daemon (resident) mode: poll, launch, wait, repeat
            results = launcher.daemon_loop()
            display_results(results, json_output=args.json)

            # Exit code: 0 if ORDER completed, 1 if errors
            if results.get("errors"):
                sys.exit(1)
            sys.exit(0)

        # Fire-and-forget mode (original behaviour)
        results = launcher.launch()

        # Display results
        display_results(results, json_output=args.json)

        # Exit code based on success
        # dry-run with detected tasks is success (exit 0)
        if results.get("detected_tasks"):
            sys.exit(0)
        if results["launched_count"] == 0 and results.get("message") != "No parallel launchable tasks found":
            sys.exit(1)

    except ValidationError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except DatabaseError as e:
        print(f"データベースエラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
