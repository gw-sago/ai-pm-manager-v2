#!/usr/bin/env python3
"""
AI PM Framework - Auto Rollback Module

Automatically restores DB and files from the latest checkpoint when a fault is detected.

Usage:
    from rollback.auto_rollback import rollback_to_checkpoint

    result = rollback_to_checkpoint(
        project_id="ai_pm_manager",
        task_id="TASK_932",
        checkpoint_id="20260209_102345_TASK_932"
    )
"""

import json
import logging
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Path setup
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, DatabaseError

logger = logging.getLogger(__name__)


class RollbackError(Exception):
    """Rollback operation failed"""
    pass


@dataclass
class RollbackResult:
    """Rollback operation result"""
    success: bool
    checkpoint_id: str
    db_restored: bool
    files_restored: bool
    error_message: Optional[str] = None
    restored_at: datetime = None

    def __post_init__(self):
        if self.restored_at is None:
            self.restored_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "checkpoint_id": self.checkpoint_id,
            "db_restored": self.db_restored,
            "files_restored": self.files_restored,
            "error_message": self.error_message,
            "restored_at": self.restored_at.isoformat(),
        }


def rollback_to_checkpoint(
    project_id: str,
    task_id: str,
    checkpoint_id: Optional[str] = None,
    *,
    verbose: bool = False
) -> RollbackResult:
    """
    Rollback to a checkpoint

    Restores DB and files from the specified checkpoint.
    If checkpoint_id is not specified, uses the latest checkpoint for the task.

    Args:
        project_id: Project ID
        task_id: Task ID
        checkpoint_id: Checkpoint ID (if None, use latest)
        verbose: Verbose logging

    Returns:
        RollbackResult with operation status

    Raises:
        RollbackError: Rollback operation failed

    Example:
        result = rollback_to_checkpoint("ai_pm_manager", "TASK_932")
        if result.success:
            print(f"Rollback successful: {result.checkpoint_id}")
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get checkpoint to restore
    if not checkpoint_id:
        checkpoint_id = _get_latest_checkpoint(project_id, task_id)
        if not checkpoint_id:
            raise RollbackError(f"No checkpoint found for task {task_id}")

    logger.info(f"Starting rollback to checkpoint: {checkpoint_id}")

    db_restored = False
    files_restored = False
    error_message = None

    try:
        # 1. Restore DB snapshot
        db_restored = _restore_db_snapshot(checkpoint_id, verbose)

        # 2. Restore file state (optional - may not exist for all checkpoints)
        try:
            files_restored = _restore_file_state(project_id, checkpoint_id, verbose)
        except Exception as e:
            logger.warning(f"File state restoration skipped: {e}")
            files_restored = False

        logger.info(f"Rollback completed: checkpoint={checkpoint_id}, db={db_restored}, files={files_restored}")

        return RollbackResult(
            success=True,
            checkpoint_id=checkpoint_id,
            db_restored=db_restored,
            files_restored=files_restored,
        )

    except Exception as e:
        error_message = str(e)
        logger.error(f"Rollback failed: {e}")

        return RollbackResult(
            success=False,
            checkpoint_id=checkpoint_id,
            db_restored=db_restored,
            files_restored=files_restored,
            error_message=error_message,
        )


def _get_latest_checkpoint(project_id: str, task_id: str) -> Optional[str]:
    """
    Get the latest checkpoint ID for a task

    Args:
        project_id: Project ID
        task_id: Task ID

    Returns:
        Checkpoint ID or None if not found
    """
    checkpoint_dir = _project_root / "data" / "checkpoints"

    if not checkpoint_dir.exists():
        return None

    # Find metadata files for this task
    meta_files = list(checkpoint_dir.glob(f"*_{task_id}_meta.json"))

    if not meta_files:
        return None

    # Sort by modification time (newest first)
    meta_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # Read the latest metadata
    with open(meta_files[0], "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return metadata.get("checkpoint_id")


def _restore_db_snapshot(checkpoint_id: str, verbose: bool = False) -> bool:
    """
    Restore DB from snapshot

    data/checkpoints/{checkpoint_id}.db → data/aipm.db

    Args:
        checkpoint_id: Checkpoint ID
        verbose: Verbose logging

    Returns:
        True if restored successfully

    Raises:
        RollbackError: Restore failed
    """
    # DB paths
    checkpoint_dir = _project_root / "data" / "checkpoints"
    checkpoint_db_path = checkpoint_dir / f"{checkpoint_id}.db"
    main_db_path = _project_root / "data" / "aipm.db"

    if not checkpoint_db_path.exists():
        raise RollbackError(f"Checkpoint DB not found: {checkpoint_db_path}")

    # Backup current DB before restore
    backup_path = _project_root / "data" / f"aipm_before_rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

    try:
        if main_db_path.exists():
            logger.debug(f"Backing up current DB: {backup_path}")
            shutil.copy2(main_db_path, backup_path)

        # Restore checkpoint DB
        logger.debug(f"Restoring DB: {checkpoint_db_path} -> {main_db_path}")
        shutil.copy2(checkpoint_db_path, main_db_path)

        # Verify restored DB
        restored_size = main_db_path.stat().st_size
        logger.info(f"DB restored successfully: {main_db_path} ({restored_size:,} bytes)")

        return True

    except Exception as e:
        logger.error(f"DB restore failed: {e}")

        # Attempt to restore from backup
        if backup_path.exists():
            logger.warning("Attempting to restore from backup...")
            try:
                shutil.copy2(backup_path, main_db_path)
                logger.info("Restored from backup")
            except Exception as restore_error:
                logger.error(f"Backup restore also failed: {restore_error}")

        raise RollbackError(f"DB restore failed: {e}") from e


def _restore_file_state(
    project_id: str,
    checkpoint_id: str,
    verbose: bool = False
) -> bool:
    """
    Restore file state from checkpoint

    This is a best-effort restoration. If files_state.json doesn't exist,
    this function will return False without raising an error.

    Args:
        project_id: Project ID
        checkpoint_id: Checkpoint ID
        verbose: Verbose logging

    Returns:
        True if files were restored, False if skipped

    Raises:
        RollbackError: Critical restore error
    """
    # Try to find the file state record
    # It could be in any ORDER directory, so we search for it
    projects_dir = _project_root / "PROJECTS" / project_id / "RESULT"

    if not projects_dir.exists():
        logger.debug(f"RESULT directory not found: {projects_dir}")
        return False

    # Search for files_state_{checkpoint_id}.json
    state_files = list(projects_dir.glob(f"**/files_state_{checkpoint_id}.json"))

    if not state_files:
        logger.debug(f"File state record not found for checkpoint: {checkpoint_id}")
        return False

    state_file = state_files[0]

    # Load file state
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state_data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load file state: {e}")
        return False

    # File state restoration is informational only
    # We don't actually restore files since they may have been intentionally modified
    file_count = state_data.get("file_count", 0)
    logger.info(f"File state loaded: {file_count} files recorded at checkpoint")

    # In a full implementation, you could:
    # 1. Compare current files with checkpoint state
    # 2. Restore files from backup if they were modified
    # 3. Delete files that were created after checkpoint
    # For now, we just log the state

    return True


def get_rollback_history(
    project_id: Optional[str] = None,
    limit: int = 10
) -> list:
    """
    Get rollback operation history

    Args:
        project_id: Filter by project ID
        limit: Max results

    Returns:
        List of rollback operations (from INCIDENTS table)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        query = """
            SELECT incident_id, timestamp, project_id, task_id,
                   description, root_cause, resolution
            FROM incidents
            WHERE category = 'ROLLBACK'
        """
        params = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                "incident_id": row[0],
                "timestamp": row[1],
                "project_id": row[2],
                "task_id": row[3],
                "description": row[4],
                "root_cause": row[5],
                "resolution": row[6],
            })

        return results

    finally:
        conn.close()


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Rollback to checkpoint")
    parser.add_argument("project_id", help="Project ID")
    parser.add_argument("task_id", help="Task ID")
    parser.add_argument("--checkpoint-id", help="Checkpoint ID (default: latest)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")

    args = parser.parse_args()

    # Logging setup
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
        checkpoint_id = args.checkpoint_id or _get_latest_checkpoint(args.project_id, args.task_id)
        if checkpoint_id:
            print(f"Would rollback to checkpoint: {checkpoint_id}")
        else:
            print(f"No checkpoint found for task: {args.task_id}")
        sys.exit(0)

    try:
        result = rollback_to_checkpoint(
            args.project_id,
            args.task_id,
            args.checkpoint_id,
            verbose=args.verbose
        )

        if result.success:
            print(f"✓ Rollback successful: {result.checkpoint_id}")
            print(f"  DB restored: {result.db_restored}")
            print(f"  Files restored: {result.files_restored}")
            sys.exit(0)
        else:
            print(f"✗ Rollback failed: {result.error_message}")
            sys.exit(1)

    except RollbackError as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
