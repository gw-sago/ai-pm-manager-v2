# INCIDENTS Table Migration

## Overview

This migration adds the `INCIDENTS` table to the AI PM Framework database for tracking and analyzing failure patterns.

## Migration Details

**Migration Script**: `add_incidents_table.py`
**Version**: 1.0.0
**Created**: 2026-02-06
**Related ORDER**: ORDER_088

## Table Schema

### INCIDENTS Table

```sql
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,                 -- Incident ID (e.g., INC_001)
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, -- Incident occurrence timestamp
    project_id TEXT,                              -- Related project (nullable)
    order_id TEXT,                                -- Related ORDER (nullable)
    task_id TEXT,                                 -- Related task (nullable)
    category TEXT NOT NULL,                       -- Incident category
    severity TEXT NOT NULL DEFAULT 'MEDIUM',      -- Severity level (HIGH/MEDIUM/LOW)
    description TEXT NOT NULL,                    -- Incident description
    root_cause TEXT,                              -- Root cause analysis
    resolution TEXT,                              -- Resolution details
    affected_records TEXT,                        -- JSON array of affected record IDs
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys (nullable - incidents may occur without specific entities)
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,

    -- Constraints
    CHECK (severity IN ('HIGH', 'MEDIUM', 'LOW')),
    CHECK (category IN ('MIGRATION_ERROR', 'CASCADE_DELETE', 'CONSTRAINT_VIOLATION',
                        'DATA_INTEGRITY', 'CONCURRENCY_ERROR', 'FILE_LOCK_ERROR',
                        'WORKER_FAILURE', 'REVIEW_ERROR', 'SYSTEM_ERROR', 'OTHER'))
);
```

### Indexes

The migration creates 6 indexes for performance optimization:

- `idx_incidents_project_id` - For querying by project
- `idx_incidents_order_id` - For querying by order
- `idx_incidents_task_id` - For querying by task
- `idx_incidents_category` - For filtering by category
- `idx_incidents_severity` - For filtering by severity
- `idx_incidents_timestamp` - For time-based queries

## Incident Categories

- **MIGRATION_ERROR**: Database migration failures
- **CASCADE_DELETE**: Unintended cascade deletion events
- **CONSTRAINT_VIOLATION**: Database constraint violations
- **DATA_INTEGRITY**: Data integrity issues
- **CONCURRENCY_ERROR**: Concurrent execution errors
- **FILE_LOCK_ERROR**: File locking issues
- **WORKER_FAILURE**: Worker task execution failures
- **REVIEW_ERROR**: Review process errors
- **SYSTEM_ERROR**: System-level errors
- **OTHER**: Other incident types

## Severity Levels

- **HIGH**: Critical incidents requiring immediate attention
- **MEDIUM**: Moderate incidents that should be addressed
- **LOW**: Minor incidents for tracking purposes

## Usage

### Dry Run (Recommended First)

Test the migration without making changes:

```bash
python backend/migrate/add_incidents_table.py --dry-run --verbose
```

### Execute Migration

Run the migration with automatic backup:

```bash
python backend/migrate/add_incidents_table.py
```

### Force Execution (During Worker Activity)

If workers are running and you need to proceed:

```bash
python backend/migrate/add_incidents_table.py --force
```

### Options

- `--dry-run`: Test migration without committing changes
- `--force`: Execute even if workers are running
- `--no-backup`: Skip backup creation (not recommended)
- `--no-worker-check`: Skip worker execution check
- `--verbose`, `-v`: Show detailed logs
- `--db PATH`: Specify custom database path

## Safety Features

This migration uses `MigrationRunner` which provides:

1. **Automatic Backup**: Creates timestamped backup before execution
2. **Worker Detection**: Warns if workers are running to prevent conflicts
3. **PRAGMA Control**: Manages foreign key constraints safely
4. **Transaction Management**: Automatic commit/rollback
5. **Idempotent**: Safe to run multiple times

## Post-Migration

After running this migration:

1. The `incidents` table will be available for incident tracking
2. Use `utils/incident_logger.py` (TASK_917) for recording incidents
3. Integration with pipeline scripts (TASK_918) will be added next
4. Analysis tools (TASK_919) will leverage this table

## Rollback

If rollback is needed, restore from the automatically created backup:

```bash
# Find the backup file
ls -lt data/*.backup_add_incidents_table_*

# Restore the backup
cp data/aipm.db.backup_add_incidents_table_YYYYMMDD_HHMMSS data/aipm.db
```

## Verification

After migration, verify the table exists:

```bash
sqlite3 data/aipm.db "SELECT sql FROM sqlite_master WHERE type='table' AND name='incidents';"
```

Check indexes:

```bash
sqlite3 data/aipm.db "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='incidents';"
```

## Related Tasks

- **TASK_916**: This migration (COMPLETED)
- **TASK_917**: Incident logger utility module
- **TASK_918**: Pipeline integration for incident recording
- **TASK_919**: Incident pattern analysis scripts

## Schema Version

This migration is part of schema version 1.1.0, adding incident tracking capabilities to the AI PM Framework.
