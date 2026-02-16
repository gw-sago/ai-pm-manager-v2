#!/usr/bin/env python3
"""
AI PM Framework - Event Notifier & Adaptive Poller

File-based event notification system for the parallel execution engine.
Tasks emit event files (JSON) upon completion or failure, and the daemon loop
consumes them to minimise polling latency.

Components:
- EventNotifier: File-based event emit / consume
- AdaptivePoller: Dynamic polling interval based on event activity

Usage (emit from Worker):
    notifier = EventNotifier("AI_PM_PJ", "ORDER_108")
    notifier.emit_task_completed("TASK_1087", metadata={"worker": "W1"})

Usage (consume from daemon_loop):
    notifier = EventNotifier("AI_PM_PJ", "ORDER_108")
    events = notifier.consume_events()
    for ev in events:
        print(ev["event_type"], ev["task_id"])

Usage (adaptive poller):
    poller = AdaptivePoller()
    interval = poller.get_next_interval()
    # ... sleep(interval) ...
    if found_events:
        poller.notify_event_detected()
    else:
        poller.notify_idle_cycle()
"""

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Resolve AI_PM_ROOT via config (same approach as parallel_launcher.py)
try:
    from config.db_config import AI_PM_ROOT
except ImportError:
    # Fallback: derive from this file's location
    # worker/event_notifier.py -> worker -> backend -> ai-pm-manager-v2
    AI_PM_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

EVENT_TASK_COMPLETED = "TASK_COMPLETED"
EVENT_TASK_FAILED = "TASK_FAILED"
EVENT_DEPENDENCY_RESOLVED = "DEPENDENCY_RESOLVED"
EVENT_RESOURCE_CHANGED = "RESOURCE_CHANGED"
EVENT_WORKER_CRASHED = "WORKER_CRASHED"

_ALL_EVENT_TYPES = {
    EVENT_TASK_COMPLETED,
    EVENT_TASK_FAILED,
    EVENT_DEPENDENCY_RESOLVED,
    EVENT_RESOURCE_CHANGED,
    EVENT_WORKER_CRASHED,
}


# ---------------------------------------------------------------------------
# EventNotifier
# ---------------------------------------------------------------------------

class EventNotifier:
    """
    File-based event notification system.

    Events are stored as individual JSON files under
    ``PROJECTS/{project_id}/RESULT/{order_id}/LOGS/events/``.

    File naming convention:
        ``event_{task_id}_{timestamp}.json``

    Consuming events reads all pending JSON files, returns their content
    sorted by timestamp, and renames each file to ``*.consumed`` so it is
    not processed twice.

    Thread / process safety is achieved via atomic write (write to a
    temporary file in the same directory, then rename).
    """

    # Suffix used for pending (unconsumed) event files
    _PENDING_SUFFIX = ".json"
    # Suffix applied after consumption
    _CONSUMED_SUFFIX = ".consumed"

    def __init__(self, project_id: str, order_id: str) -> None:
        self.project_id = project_id
        self.order_id = order_id

        # Build the events directory path
        self._events_dir: Path = (
            Path(AI_PM_ROOT)
            / "PROJECTS"
            / project_id
            / "RESULT"
            / order_id
            / "LOGS"
            / "events"
        )

        # Ensure the directory exists on construction
        self._ensure_events_dir()

    # ------------------------------------------------------------------
    # Public API - emit
    # ------------------------------------------------------------------

    def emit_task_completed(
        self,
        task_id: str,
        metadata: Optional[Dict] = None,
    ) -> Path:
        """
        Emit a TASK_COMPLETED event.

        Creates a JSON event file indicating that a task finished
        successfully (Worker -> DONE or Review -> COMPLETED).

        Args:
            task_id: The completed task identifier (e.g. ``TASK_1087``).
            metadata: Optional extra key-value pairs to include.

        Returns:
            Path to the created event file.
        """
        return self._emit_event(
            event_type=EVENT_TASK_COMPLETED,
            task_id=task_id,
            metadata=metadata,
        )

    def emit_task_failed(
        self,
        task_id: str,
        error: str,
        metadata: Optional[Dict] = None,
    ) -> Path:
        """
        Emit a TASK_FAILED event.

        Args:
            task_id: The failed task identifier.
            error: Human-readable error description.
            metadata: Optional extra key-value pairs.

        Returns:
            Path to the created event file.
        """
        meta = dict(metadata) if metadata else {}
        meta["error"] = error
        return self._emit_event(
            event_type=EVENT_TASK_FAILED,
            task_id=task_id,
            metadata=meta,
        )

    def emit_dependency_resolved(
        self,
        task_id: str,
        metadata: Optional[Dict] = None,
    ) -> Path:
        """
        Emit a DEPENDENCY_RESOLVED event.

        Indicates that all dependencies for *task_id* have been satisfied.

        Args:
            task_id: The task whose dependencies are now resolved.
            metadata: Optional extra key-value pairs.

        Returns:
            Path to the created event file.
        """
        return self._emit_event(
            event_type=EVENT_DEPENDENCY_RESOLVED,
            task_id=task_id,
            metadata=metadata,
        )

    def emit_resource_changed(
        self,
        task_id: str,
        metadata: Optional[Dict] = None,
    ) -> Path:
        """
        Emit a RESOURCE_CHANGED event.

        Indicates a change in resource availability (e.g. a worker slot
        freed up).

        Args:
            task_id: Related task identifier (may be empty string).
            metadata: Optional extra key-value pairs.

        Returns:
            Path to the created event file.
        """
        return self._emit_event(
            event_type=EVENT_RESOURCE_CHANGED,
            task_id=task_id,
            metadata=metadata,
        )

    def emit_worker_crashed(
        self,
        task_id: str,
        reason: str,
        metadata: Optional[Dict] = None,
    ) -> Path:
        """
        Emit a WORKER_CRASHED event.

        Indicates that a worker process crashed or became unresponsive
        and was recovered by the daemon health check.

        Args:
            task_id: The task whose worker crashed.
            reason: Human-readable crash reason (e.g. "pid_alive_check",
                "log_staleness", "process_timeout", "orphan_detection").
            metadata: Optional extra key-value pairs.

        Returns:
            Path to the created event file.
        """
        meta = dict(metadata) if metadata else {}
        meta["reason"] = reason
        return self._emit_event(
            event_type=EVENT_WORKER_CRASHED,
            task_id=task_id,
            metadata=meta,
        )

    # ------------------------------------------------------------------
    # Public API - consume / query
    # ------------------------------------------------------------------

    def consume_events(
        self,
        event_types: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Read and consume all pending events, optionally filtered by type.

        Consumption marks each event file by renaming it to
        ``*.consumed``, so subsequent calls will not see it again.

        Args:
            event_types: If provided, only events whose ``event_type``
                is in this list will be returned and consumed.  Events
                of other types remain pending.

        Returns:
            List of event data dicts sorted by timestamp (oldest first).
        """
        pending_files = self._list_pending_files()
        if not pending_files:
            return []

        consumed: List[Dict] = []

        for event_path in pending_files:
            try:
                data = self._read_event_file(event_path)
                if data is None:
                    continue

                # Apply type filter
                if event_types and data.get("event_type") not in event_types:
                    continue

                # Mark as consumed (rename)
                consumed_path = event_path.with_suffix(self._CONSUMED_SUFFIX)
                try:
                    event_path.rename(consumed_path)
                except OSError as rename_err:
                    # On Windows, rename may fail if another process holds a
                    # handle.  Fall back to delete-after-read.
                    logger.debug(
                        f"[event] Rename failed for {event_path.name}, "
                        f"attempting delete: {rename_err}"
                    )
                    try:
                        event_path.unlink()
                    except OSError:
                        pass

                consumed.append(data)

            except Exception as exc:
                logger.warning(
                    f"[event] Failed to consume {event_path.name}: {exc}"
                )

        # Sort by timestamp (ISO string comparison is correct for
        # lexicographic ordering of ISO-8601 timestamps).
        consumed.sort(key=lambda d: d.get("timestamp", ""))

        if consumed:
            logger.info(
                f"[event] Consumed {len(consumed)} event(s) "
                f"for {self.project_id}/{self.order_id}"
            )

        return consumed

    def has_pending_events(self) -> bool:
        """Return ``True`` if there are unconsumed event files."""
        return len(self._list_pending_files()) > 0

    def get_pending_event_count(self) -> int:
        """Return the number of unconsumed event files."""
        return len(self._list_pending_files())

    def cleanup_old_events(self, max_age_seconds: int = 3600) -> int:
        """
        Delete consumed and stale event files older than *max_age_seconds*.

        Both ``.consumed`` files and ``.json`` files that are older than
        the threshold are removed.  This prevents unbounded growth of the
        events directory.

        Args:
            max_age_seconds: Maximum age in seconds before a file is
                considered eligible for cleanup.  Defaults to 3600 (1 hour).

        Returns:
            Number of files deleted.
        """
        if not self._events_dir.exists():
            return 0

        cutoff = time.time() - max_age_seconds
        deleted = 0

        try:
            for entry in self._events_dir.iterdir():
                if not entry.is_file():
                    continue

                # Only clean up known file types
                if entry.suffix not in (self._PENDING_SUFFIX, self._CONSUMED_SUFFIX):
                    continue

                # Check prefix
                if not entry.name.startswith("event_"):
                    continue

                try:
                    mtime = entry.stat().st_mtime
                    if mtime < cutoff:
                        entry.unlink()
                        deleted += 1
                except OSError as exc:
                    logger.debug(f"[event] Cannot remove {entry.name}: {exc}")

        except OSError as exc:
            logger.warning(f"[event] cleanup_old_events error: {exc}")

        if deleted > 0:
            logger.info(
                f"[event] Cleaned up {deleted} old event file(s) "
                f"(max_age={max_age_seconds}s)"
            )

        return deleted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_events_dir(self) -> None:
        """Create the events directory if it does not exist."""
        try:
            self._events_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                f"[event] Could not create events dir "
                f"{self._events_dir}: {exc}"
            )

    def _emit_event(
        self,
        event_type: str,
        task_id: str,
        metadata: Optional[Dict] = None,
    ) -> Path:
        """
        Core emit logic: build payload and write atomically.

        Uses a temporary file in the same directory followed by
        ``os.replace`` to ensure readers never see a partially written
        file.

        Returns:
            Path to the final event file.
        """
        self._ensure_events_dir()

        now = datetime.now()
        timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")

        payload: Dict = {
            "event_type": event_type,
            "task_id": task_id,
            "project_id": self.project_id,
            "order_id": self.order_id,
            "timestamp": now.isoformat(),
            "metadata": metadata if metadata is not None else {},
        }

        filename = f"event_{task_id}_{timestamp_str}{self._PENDING_SUFFIX}"
        final_path = self._events_dir / filename

        # Atomic write: temp file -> os.replace
        fd = None
        tmp_path = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self._events_dir),
                prefix=".tmp_event_",
                suffix=self._PENDING_SUFFIX,
            )
            tmp_path = Path(tmp_path_str)

            content = json.dumps(payload, ensure_ascii=False, indent=2)
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd = None  # prevent double-close in finally

            # Atomic rename (os.replace is atomic on both Windows and Linux
            # when source and destination are on the same filesystem).
            os.replace(str(tmp_path), str(final_path))

            logger.debug(
                f"[event] Emitted {event_type} for {task_id}: "
                f"{final_path.name}"
            )

            return final_path

        except Exception:
            # Clean up temp file on failure
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def _list_pending_files(self) -> List[Path]:
        """
        Return a list of pending (unconsumed) event files, sorted by
        filename (which embeds the timestamp).
        """
        if not self._events_dir.exists():
            return []

        try:
            files = sorted(
                p
                for p in self._events_dir.iterdir()
                if p.is_file()
                and p.name.startswith("event_")
                and p.suffix == self._PENDING_SUFFIX
            )
            return files
        except OSError as exc:
            logger.warning(f"[event] Failed to list pending files: {exc}")
            return []

    @staticmethod
    def _read_event_file(path: Path) -> Optional[Dict]:
        """
        Safely read and parse a JSON event file.

        Returns:
            Parsed dict, or ``None`` on read / parse failure.
        """
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
            return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug(f"[event] Could not read {path.name}: {exc}")
            return None


# ---------------------------------------------------------------------------
# AdaptivePoller
# ---------------------------------------------------------------------------

class AdaptivePoller:
    """
    Dynamically adjust polling interval based on event activity.

    When events are detected the interval drops to ``min_interval``
    (burst mode).  During idle cycles the interval gradually increases
    (by ``backoff_factor``) up to ``max_interval``.

    Typical usage inside a daemon loop::

        poller = AdaptivePoller()
        while running:
            events = notifier.consume_events()
            if events:
                poller.notify_event_detected()
                # ... process events ...
            else:
                poller.notify_idle_cycle()

            time.sleep(poller.get_next_interval())
    """

    def __init__(
        self,
        min_interval: float = 1.0,
        max_interval: float = 30.0,
        default_interval: float = 10.0,
        backoff_factor: float = 1.5,
        cooldown_factor: float = 0.5,
    ) -> None:
        """
        Initialise the adaptive poller.

        Args:
            min_interval: Minimum polling interval in seconds (used when
                events are being detected frequently).
            max_interval: Maximum polling interval in seconds (used when
                the system is idle for an extended period).
            default_interval: Starting / reset interval in seconds.
            backoff_factor: Multiplier applied to the current interval
                after each idle cycle (must be > 1.0).
            cooldown_factor: Multiplier applied to the current interval
                when an event is detected (must be < 1.0).  The result
                is clamped to ``min_interval``.
        """
        if min_interval <= 0:
            raise ValueError("min_interval must be positive")
        if max_interval < min_interval:
            raise ValueError("max_interval must be >= min_interval")
        if backoff_factor <= 1.0:
            raise ValueError("backoff_factor must be > 1.0")
        if cooldown_factor <= 0.0 or cooldown_factor >= 1.0:
            raise ValueError("cooldown_factor must be in (0.0, 1.0)")

        self._min_interval = min_interval
        self._max_interval = max_interval
        self._default_interval = default_interval
        self._backoff_factor = backoff_factor
        self._cooldown_factor = cooldown_factor

        # Current interval starts at the default value
        self._current_interval = default_interval

        # Counters for diagnostic purposes
        self._consecutive_idle_cycles = 0
        self._total_events_detected = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_next_interval(self) -> float:
        """
        Return the current polling interval in seconds.

        This value is updated by ``notify_event_detected`` and
        ``notify_idle_cycle``.
        """
        return self._current_interval

    def notify_event_detected(self) -> None:
        """
        Notify the poller that one or more events were detected.

        Drops the interval towards ``min_interval`` using the
        ``cooldown_factor``.
        """
        self._consecutive_idle_cycles = 0
        self._total_events_detected += 1

        new_interval = self._current_interval * self._cooldown_factor
        self._current_interval = max(new_interval, self._min_interval)

        logger.debug(
            f"[poller] Event detected -> interval={self._current_interval:.1f}s"
        )

    def notify_idle_cycle(self) -> None:
        """
        Notify the poller that no events were found in this cycle.

        Gradually increases the interval towards ``max_interval`` using
        the ``backoff_factor``.
        """
        self._consecutive_idle_cycles += 1

        new_interval = self._current_interval * self._backoff_factor
        self._current_interval = min(new_interval, self._max_interval)

        logger.debug(
            f"[poller] Idle cycle #{self._consecutive_idle_cycles} "
            f"-> interval={self._current_interval:.1f}s"
        )

    def reset(self) -> None:
        """
        Reset the interval to ``default_interval`` and clear counters.
        """
        self._current_interval = self._default_interval
        self._consecutive_idle_cycles = 0

        logger.debug(
            f"[poller] Reset -> interval={self._current_interval:.1f}s"
        )

    # ------------------------------------------------------------------
    # Diagnostic properties
    # ------------------------------------------------------------------

    @property
    def consecutive_idle_cycles(self) -> int:
        """Number of consecutive idle cycles since the last event."""
        return self._consecutive_idle_cycles

    @property
    def total_events_detected(self) -> int:
        """Cumulative count of ``notify_event_detected`` calls."""
        return self._total_events_detected

    @property
    def min_interval(self) -> float:
        """Configured minimum interval."""
        return self._min_interval

    @property
    def max_interval(self) -> float:
        """Configured maximum interval."""
        return self._max_interval

    def to_dict(self) -> Dict:
        """Return a snapshot of the poller state as a dict."""
        return {
            "current_interval": round(self._current_interval, 2),
            "min_interval": self._min_interval,
            "max_interval": self._max_interval,
            "default_interval": self._default_interval,
            "backoff_factor": self._backoff_factor,
            "cooldown_factor": self._cooldown_factor,
            "consecutive_idle_cycles": self._consecutive_idle_cycles,
            "total_events_detected": self._total_events_detected,
        }
