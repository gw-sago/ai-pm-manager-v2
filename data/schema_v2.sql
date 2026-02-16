-- ============================================================================
-- AI PM Framework Database Schema
-- Version: 2.2.0
-- Created: 2026-01-29
-- Updated: 2026-02-16
-- Description: SQLite schema with composite primary keys for multi-project support
-- ============================================================================
--
-- CHANGELOG from v1.0.0:
-- - orders: PRIMARY KEY changed from (id) to (id, project_id)
-- - tasks: PRIMARY KEY changed from (id) to (id, project_id)
-- - task_dependencies: Added project_id column, updated foreign keys
-- - views: Updated JOINs to use composite keys
-- - Removed triggers for orders/tasks (handled by application)
--
-- CHANGELOG v2.1.0 (2026-02-16):
-- - Removed review_queue table and related objects (ORDER_145)
--   * Dropped review_queue table, indexes, and triggers
--   * Removed status_transitions for 'review' entity type
--   * Reviews are now handled directly via DONE status tasks
--
-- CHANGELOG v2.2.0 (2026-02-16):
-- - Added is_destructive_db_change column to tasks table (ORDER_146)
--   * Integer flag (0/1) to mark tasks performing destructive DB operations
--   * Added index idx_tasks_is_destructive_db_change for filtering
--   * Used for PM planning, Worker execution warnings, and release flow control
--
-- ============================================================================

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- ============================================================================
-- 1. PROJECTS TABLE
-- ============================================================================
-- Manages project information (top-level entity)
-- Primary key: id (single column, as projects are the root)

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,                          -- Project ID (e.g., AI_PM_PJ)
    name TEXT NOT NULL,                           -- Project name
    path TEXT NOT NULL,                           -- Project directory path
    status TEXT NOT NULL DEFAULT 'INITIAL',       -- Project status
    current_order_id TEXT,                        -- Currently active ORDER
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CHECK (status IN ('INITIAL', 'PLANNING', 'IN_PROGRESS', 'REVIEW', 'REWORK',
                      'ESCALATED', 'ESCALATION_RESOLVED', 'COMPLETED', 'ON_HOLD',
                      'CANCELLED', 'INTERRUPTED'))
);

-- ============================================================================
-- 2. ORDERS TABLE
-- ============================================================================
-- Manages ORDER information
-- Primary key: (id, project_id) - Composite key for multi-project support
-- This allows ORDER_001 in AI_PM_PJ and ORDER_001 in another project to coexist

CREATE TABLE IF NOT EXISTS orders (
    id TEXT NOT NULL,                             -- ORDER ID (e.g., ORDER_036)
    project_id TEXT NOT NULL,                     -- Parent project
    title TEXT NOT NULL,                          -- ORDER title
    priority TEXT DEFAULT 'P1',                   -- Priority (P0/P1/P2/P3)
    status TEXT NOT NULL DEFAULT 'PLANNING',      -- ORDER status
    started_at DATETIME,                          -- Start timestamp
    completed_at DATETIME,                        -- Completion timestamp
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Composite Primary Key
    PRIMARY KEY (id, project_id),

    -- Foreign keys
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,

    -- Constraints
    CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
    CHECK (status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW', 'COMPLETED',
                      'ON_HOLD', 'CANCELLED'))
);

-- ============================================================================
-- 3. TASKS TABLE
-- ============================================================================
-- Manages task information
-- Primary key: (id, project_id) - Composite key for multi-project support
-- This allows TASK_001 in AI_PM_PJ and TASK_001 in another project to coexist

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT NOT NULL,                             -- Task ID (e.g., TASK_188)
    order_id TEXT NOT NULL,                       -- Parent ORDER
    project_id TEXT NOT NULL,                     -- Parent project (denormalized for efficiency)
    title TEXT NOT NULL,                          -- Task title
    description TEXT,                             -- Task description
    status TEXT NOT NULL DEFAULT 'QUEUED',        -- Task status
    assignee TEXT,                                -- Assigned worker (Worker A, etc.)
    priority TEXT DEFAULT 'P1',                   -- Priority (P0/P1/P2/P3)
    recommended_model TEXT DEFAULT 'Opus',        -- Recommended AI model (Haiku/Sonnet/Opus)
    reject_count INTEGER NOT NULL DEFAULT 0,      -- Number of review rejections
    static_analysis_score INTEGER DEFAULT NULL,   -- Static analysis quality score (0-100)
    complexity_score INTEGER DEFAULT NULL,        -- Task complexity score (0-100)
    estimated_tokens INTEGER DEFAULT NULL,        -- Estimated token count
    actual_tokens INTEGER DEFAULT NULL,           -- Actual token usage
    cost_usd REAL DEFAULT NULL,                   -- Task cost in USD
    is_destructive_db_change INTEGER NOT NULL DEFAULT 0, -- Flag for destructive DB operations (DROP TABLE, etc.)
    started_at DATETIME,                          -- Start timestamp
    completed_at DATETIME,                        -- Completion timestamp
    reviewed_at DATETIME,                         -- Review completion timestamp
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Composite Primary Key
    PRIMARY KEY (id, project_id),

    -- Foreign keys (composite reference to orders)
    FOREIGN KEY (order_id, project_id) REFERENCES orders(id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,

    -- Constraints
    CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
    CHECK (status IN ('QUEUED', 'BLOCKED', 'IN_PROGRESS', 'DONE', 'IN_REVIEW',
                      'REWORK', 'COMPLETED', 'CANCELLED', 'SKIPPED', 'REJECTED',
                      'INTERRUPTED', 'ESCALATED', 'WAITING_INPUT'))
);

-- ============================================================================
-- 4. TASK_DEPENDENCIES TABLE
-- ============================================================================
-- Manages task dependencies (normalized many-to-many relationship)
-- Note: project_id is required to reference tasks with composite primary key

CREATE TABLE IF NOT EXISTS task_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,                        -- Dependent task
    depends_on_task_id TEXT NOT NULL,             -- Dependency (prerequisite task)
    project_id TEXT NOT NULL,                     -- Project ID (required for composite FK)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys (composite references to tasks)
    FOREIGN KEY (task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,

    -- Unique constraint to prevent duplicate dependencies within a project
    UNIQUE (task_id, depends_on_task_id, project_id)
);

-- ============================================================================
-- 5. BACKLOG_ITEMS TABLE
-- ============================================================================
-- Manages backlog items
-- Note: Primary key is single (id) as backlog IDs are already project-scoped by convention

CREATE TABLE IF NOT EXISTS backlog_items (
    id TEXT PRIMARY KEY,                          -- Backlog ID (e.g., BACKLOG_029)
    project_id TEXT NOT NULL,                     -- Parent project
    title TEXT NOT NULL,                          -- Backlog item title
    description TEXT,                             -- Description
    category TEXT,                                -- Category for grouping
    priority TEXT DEFAULT 'Medium',               -- Priority (High/Medium/Low)
    status TEXT NOT NULL DEFAULT 'TODO',          -- Status
    related_order_id TEXT,                        -- Related ORDER (after conversion)
    converted_to_order_id TEXT,                   -- ORDER ID when converted
    sort_order INTEGER DEFAULT 999,               -- Custom sort order (lower = higher priority)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,                        -- Completion timestamp
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    -- Note: related_order_id FK is not enforced due to composite key complexity

    -- Constraints
    CHECK (priority IN ('High', 'Medium', 'Low')),
    CHECK (status IN ('TODO', 'IN_PROGRESS', 'DONE', 'CANCELED', 'EXTERNAL'))
);

-- ============================================================================
-- 7. ESCALATIONS TABLE
-- ============================================================================
-- Manages escalations

CREATE TABLE IF NOT EXISTS escalations (
    id TEXT PRIMARY KEY,                          -- Escalation ID (e.g., ESC_001)
    task_id TEXT NOT NULL,                        -- Related task
    project_id TEXT,                              -- Project ID (optional, for filtering)
    title TEXT NOT NULL,                          -- Escalation title
    description TEXT,                             -- Description
    status TEXT NOT NULL DEFAULT 'OPEN',          -- Status
    resolution TEXT,                              -- Resolution content
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,                         -- Resolution timestamp

    -- Constraints
    CHECK (status IN ('OPEN', 'RESOLVED', 'CANCELED'))
);

-- ============================================================================
-- 8. CHANGE_HISTORY TABLE
-- ============================================================================
-- Tracks all changes to entities (audit log)

CREATE TABLE IF NOT EXISTS change_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,                    -- Entity type (project/order/task/etc.)
    entity_id TEXT NOT NULL,                      -- Entity ID
    project_id TEXT,                              -- Project ID (for filtering)
    field_name TEXT NOT NULL,                     -- Changed field name
    old_value TEXT,                               -- Previous value
    new_value TEXT,                               -- New value
    changed_by TEXT NOT NULL,                     -- Who made the change (PM/Worker A/etc.)
    change_reason TEXT,                           -- Reason for change (optional)
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CHECK (entity_type IN ('project', 'order', 'task', 'backlog', 'review', 'escalation'))
);

-- ============================================================================
-- 9. STATUS_TRANSITIONS TABLE
-- ============================================================================
-- Defines allowed state transitions (state machine rules)

CREATE TABLE IF NOT EXISTS status_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,                    -- Entity type (task/order/backlog/review)
    from_status TEXT,                             -- Source status (NULL = initial state)
    to_status TEXT NOT NULL,                      -- Target status
    allowed_role TEXT DEFAULT 'ANY',              -- Who can perform (PM/Worker/System/ANY)
    description TEXT,                             -- Transition description
    is_active INTEGER DEFAULT 1,                  -- Active flag (1=active, 0=inactive)

    -- Unique constraint to prevent duplicate transitions
    UNIQUE (entity_type, from_status, to_status),

    -- Constraints
    CHECK (entity_type IN ('project', 'order', 'task', 'backlog', 'review')),
    CHECK (allowed_role IN ('PM', 'Worker', 'System', 'ANY'))
);

-- ============================================================================
-- 10. BUGS TABLE
-- ============================================================================
-- Manages known bug patterns and lessons learned
-- project_id NULL = generic/framework-wide bug pattern
-- project_id NOT NULL = project-specific bug pattern

CREATE TABLE IF NOT EXISTS bugs (
    id TEXT PRIMARY KEY,                          -- Bug ID (e.g., BUG_001)
    project_id TEXT,                              -- Project ID (NULL = generic, NOT NULL = project-specific)
    title TEXT NOT NULL,                          -- Bug title/summary
    description TEXT NOT NULL,                    -- Detailed bug description
    pattern_type TEXT,                            -- Pattern classification (e.g., "default_override", "module_conflict")
    severity TEXT DEFAULT 'Medium',               -- Severity (Critical/High/Medium/Low)
    status TEXT NOT NULL DEFAULT 'ACTIVE',        -- Status (ACTIVE/FIXED/ARCHIVED)
    solution TEXT,                                -- Solution/workaround description
    related_files TEXT,                           -- Related file paths (comma-separated)
    tags TEXT,                                    -- Tags for categorization (comma-separated)
    occurrence_count INTEGER DEFAULT 1,           -- Number of times this pattern occurred
    effectiveness_score REAL DEFAULT 0.5,         -- Pattern effectiveness score (0.0-1.0, updated based on success/failure)
    total_injections INTEGER DEFAULT 0,           -- Total number of times this pattern was injected into Worker prompts
    related_failures INTEGER DEFAULT 0,           -- Number of task failures related to this bug pattern
    last_occurred_at DATETIME,                    -- Last occurrence timestamp
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,

    -- Constraints
    CHECK (severity IN ('Critical', 'High', 'Medium', 'Low')),
    CHECK (status IN ('ACTIVE', 'FIXED', 'ARCHIVED'))
);

-- ============================================================================
-- 11. ERROR_PATTERNS TABLE
-- ============================================================================
-- Manages error classification patterns for automated error handling
-- Used by recovery system to determine retry/skip/rollback/escalate actions

CREATE TABLE IF NOT EXISTS error_patterns (
    id TEXT PRIMARY KEY,                              -- Pattern ID (e.g., EP_001)
    pattern_name TEXT NOT NULL UNIQUE,                -- Pattern name (e.g., import_error)
    category TEXT NOT NULL CHECK (category IN ('RETRYABLE', 'SYSTEM', 'LOGIC', 'ENVIRONMENT')),
    regex_pattern TEXT NOT NULL,                      -- Regex pattern to match error messages
    description TEXT,                                 -- Human-readable description
    recommended_action TEXT NOT NULL CHECK (recommended_action IN ('RETRY', 'SKIP', 'ROLLBACK', 'ESCALATE')),
    max_retries INTEGER DEFAULT 3,                    -- Maximum retry attempts
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES
-- ============================================================================
-- Performance optimization indexes

-- Orders indexes
CREATE INDEX IF NOT EXISTS idx_orders_project_id ON orders(project_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

-- Tasks indexes
CREATE INDEX IF NOT EXISTS idx_tasks_order_id ON tasks(order_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_tasks_reviewed_at ON tasks(reviewed_at);
CREATE INDEX IF NOT EXISTS idx_tasks_is_destructive_db_change ON tasks(is_destructive_db_change);

-- Task dependencies indexes
CREATE INDEX IF NOT EXISTS idx_task_dependencies_task_id ON task_dependencies(task_id);
CREATE INDEX IF NOT EXISTS idx_task_dependencies_depends_on ON task_dependencies(depends_on_task_id);
CREATE INDEX IF NOT EXISTS idx_task_dependencies_project_id ON task_dependencies(project_id);

-- Backlog items indexes
CREATE INDEX IF NOT EXISTS idx_backlog_items_project_id ON backlog_items(project_id);
CREATE INDEX IF NOT EXISTS idx_backlog_items_status ON backlog_items(status);
CREATE INDEX IF NOT EXISTS idx_backlog_items_sort_order ON backlog_items(sort_order);

-- Change history indexes
CREATE INDEX IF NOT EXISTS idx_change_history_entity ON change_history(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_change_history_changed_at ON change_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_change_history_project_id ON change_history(project_id);

-- Status transitions indexes
CREATE INDEX IF NOT EXISTS idx_status_transitions_entity_type ON status_transitions(entity_type);
CREATE INDEX IF NOT EXISTS idx_status_transitions_lookup ON status_transitions(entity_type, from_status, to_status);

-- Bugs indexes
CREATE INDEX IF NOT EXISTS idx_bugs_project_id ON bugs(project_id);
CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status);
CREATE INDEX IF NOT EXISTS idx_bugs_pattern_type ON bugs(pattern_type);
CREATE INDEX IF NOT EXISTS idx_bugs_severity ON bugs(severity);

-- Error patterns indexes
CREATE INDEX IF NOT EXISTS idx_error_patterns_category ON error_patterns(category);
CREATE INDEX IF NOT EXISTS idx_error_patterns_recommended_action ON error_patterns(recommended_action);

-- ============================================================================
-- TRIGGERS
-- ============================================================================
-- Automatic updated_at timestamp update

-- Projects updated_at trigger
CREATE TRIGGER IF NOT EXISTS trigger_projects_updated_at
AFTER UPDATE ON projects
FOR EACH ROW
BEGIN
    UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

-- Backlog items updated_at trigger
CREATE TRIGGER IF NOT EXISTS trigger_backlog_items_updated_at
AFTER UPDATE ON backlog_items
FOR EACH ROW
BEGIN
    UPDATE backlog_items SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

-- Bugs updated_at trigger
CREATE TRIGGER IF NOT EXISTS trigger_bugs_updated_at
AFTER UPDATE ON bugs
FOR EACH ROW
BEGIN
    UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

-- Error patterns updated_at trigger
CREATE TRIGGER IF NOT EXISTS trigger_error_patterns_updated_at
AFTER UPDATE ON error_patterns
FOR EACH ROW
BEGIN
    UPDATE error_patterns SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

-- Note: orders and tasks triggers are handled by application layer
-- due to composite primary key complexity in SQLite

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Active tasks view (excludes COMPLETED and CANCELLED)
CREATE VIEW IF NOT EXISTS v_active_tasks AS
SELECT
    t.*,
    o.title as order_title,
    o.status as order_status
FROM tasks t
JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
WHERE t.status IN ('QUEUED', 'BLOCKED', 'IN_PROGRESS', 'DONE', 'IN_REVIEW', 'REWORK', 'REJECTED',
                   'INTERRUPTED', 'ESCALATED', 'WAITING_INPUT');

-- Pending reviews view
CREATE VIEW IF NOT EXISTS v_pending_reviews AS
SELECT
    t.*,
    o.title as order_title
FROM tasks t
JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
WHERE t.status = 'DONE';

-- Task dependencies view with status
CREATE VIEW IF NOT EXISTS v_task_dependencies AS
SELECT
    td.task_id,
    td.depends_on_task_id,
    td.project_id,
    t1.title as task_title,
    t1.status as task_status,
    t2.title as depends_on_title,
    t2.status as depends_on_status
FROM task_dependencies td
JOIN tasks t1 ON td.task_id = t1.id AND td.project_id = t1.project_id
JOIN tasks t2 ON td.depends_on_task_id = t2.id AND td.project_id = t2.project_id;

-- Backlog with ORDER status view
CREATE VIEW IF NOT EXISTS v_backlog_with_order AS
SELECT
    b.*,
    o.title as order_title,
    o.status as order_status
FROM backlog_items b
LEFT JOIN orders o ON b.converted_to_order_id = o.id;

-- ============================================================================
-- INITIAL DATA: STATUS TRANSITIONS
-- ============================================================================
-- Define allowed state transitions

-- Task status transitions
INSERT OR IGNORE INTO status_transitions (entity_type, from_status, to_status, allowed_role, description) VALUES
    -- Initial transitions
    ('task', NULL, 'QUEUED', 'PM', 'Create task without dependencies'),
    ('task', NULL, 'BLOCKED', 'PM', 'Create task with dependencies'),

    -- Normal workflow
    ('task', 'QUEUED', 'IN_PROGRESS', 'Worker', 'Start task execution'),
    ('task', 'BLOCKED', 'QUEUED', 'System', 'Dependencies completed - unblock task'),
    ('task', 'IN_PROGRESS', 'DONE', 'Worker', 'Complete task execution'),

    -- Review workflow
    ('task', 'DONE', 'COMPLETED', 'PM', 'Approve task after review'),
    ('task', 'DONE', 'REWORK', 'PM', 'Reject task - needs rework'),
    ('task', 'IN_PROGRESS', 'REWORK', 'PM', 'Reject during progress - needs rework'),
    ('task', 'REWORK', 'DONE', 'Worker', 'Complete rework'),
    ('task', 'REWORK', 'IN_PROGRESS', 'Worker', 'Resume rework'),

    -- REJECTED workflow
    ('task', 'REWORK', 'REJECTED', 'System', 'Reject count exceeded - mark as REJECTED'),
    ('task', 'REJECTED', 'QUEUED', 'PM', 'Manual recovery from REJECTED to QUEUED'),

    -- Interrupt/Escalation/Interaction workflow
    ('task', 'IN_PROGRESS', 'INTERRUPTED', 'ANY', 'Task interrupted (timeout, manual interrupt, etc.)'),
    ('task', 'DONE', 'INTERRUPTED', 'ANY', 'Review interrupted (timeout, etc.)'),
    ('task', 'ESCALATED', 'QUEUED', 'PM', 'PM escalation: AI redesign -> QUEUED retry'),
    ('task', 'ESCALATED', 'REJECTED', 'System', 'PM escalation: redesign failed -> REJECTED terminal'),

    -- ESCALATED transitions (from task states)
    ('task', 'DONE', 'ESCALATED', 'PM', 'Review escalated - mark task as escalated'),
    ('task', 'IN_PROGRESS', 'ESCALATED', 'ANY', 'Critical issue during execution - escalate'),
    ('task', 'REWORK', 'ESCALATED', 'ANY', 'Issue found during rework - escalate'),

    ('task', 'IN_PROGRESS', 'WAITING_INPUT', 'System', 'AI requests user input'),
    ('task', 'WAITING_INPUT', 'IN_PROGRESS', 'System', 'User provided input, resume task');

-- Order status transitions
INSERT OR IGNORE INTO status_transitions (entity_type, from_status, to_status, allowed_role, description) VALUES
    ('order', NULL, 'PLANNING', 'PM', 'Create new ORDER'),
    ('order', 'PLANNING', 'IN_PROGRESS', 'PM', 'Start ORDER execution'),
    ('order', 'IN_PROGRESS', 'REVIEW', 'PM', 'All tasks done - start review'),
    ('order', 'REVIEW', 'COMPLETED', 'PM', 'Approve ORDER'),
    ('order', 'REVIEW', 'IN_PROGRESS', 'PM', 'Reject - continue work'),
    ('order', 'IN_PROGRESS', 'ON_HOLD', 'PM', 'Put ORDER on hold'),
    ('order', 'ON_HOLD', 'IN_PROGRESS', 'PM', 'Resume ORDER'),
    ('order', 'IN_PROGRESS', 'CANCELLED', 'PM', 'Cancel ORDER');

-- Backlog status transitions
INSERT OR IGNORE INTO status_transitions (entity_type, from_status, to_status, allowed_role, description) VALUES
    ('backlog', NULL, 'TODO', 'PM', 'Create backlog item'),
    ('backlog', 'TODO', 'IN_PROGRESS', 'PM', 'Convert to ORDER'),
    ('backlog', 'IN_PROGRESS', 'DONE', 'PM', 'Complete related ORDER'),
    ('backlog', 'IN_PROGRESS', 'TODO', 'PM', 'Revert to TODO when related ORDER is cancelled'),
    ('backlog', 'IN_PROGRESS', 'CANCELED', 'PM', 'Cancel backlog item'),
    ('backlog', 'TODO', 'CANCELED', 'PM', 'Cancel backlog item'),
    ('backlog', 'TODO', 'EXTERNAL', 'PM', 'Mark as external project');

-- Project status transitions
INSERT OR IGNORE INTO status_transitions (entity_type, from_status, to_status, allowed_role, description) VALUES
    ('project', NULL, 'INITIAL', 'PM', 'Create project'),
    ('project', 'INITIAL', 'PLANNING', 'PM', 'Start planning'),
    ('project', 'PLANNING', 'IN_PROGRESS', 'PM', 'Start execution'),
    ('project', 'IN_PROGRESS', 'REVIEW', 'PM', 'All orders complete'),
    ('project', 'IN_PROGRESS', 'ESCALATED', 'PM', 'Escalate to user'),
    ('project', 'ESCALATED', 'ESCALATION_RESOLVED', 'PM', 'User responded'),
    ('project', 'ESCALATION_RESOLVED', 'IN_PROGRESS', 'PM', 'Resume after escalation'),
    ('project', 'IN_PROGRESS', 'INTERRUPTED', 'Worker', 'Session interrupted'),
    ('project', 'INTERRUPTED', 'IN_PROGRESS', 'Worker', 'Resume project'),
    ('project', 'REVIEW', 'COMPLETED', 'PM', 'Complete project'),
    ('project', 'IN_PROGRESS', 'ON_HOLD', 'PM', 'Put on hold'),
    ('project', 'ON_HOLD', 'IN_PROGRESS', 'PM', 'Resume project'),
    ('project', 'IN_PROGRESS', 'CANCELLED', 'PM', 'Cancel project');

-- ============================================================================
-- BUILDS TABLE
-- ============================================================================
-- Tracks build execution status for projects with build artifacts (e.g., Electron apps)
-- Provides DB-level visibility into build success/failure history

CREATE TABLE IF NOT EXISTS builds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    order_id TEXT,                              -- Related ORDER (NULL for manual builds)
    release_id TEXT,                            -- RELEASE_LOG release ID
    build_type TEXT NOT NULL DEFAULT 'electron',
    status TEXT NOT NULL DEFAULT 'PENDING',
    build_command TEXT,
    build_output TEXT,                          -- stdout/stderr (truncated)
    artifact_path TEXT,                         -- Path to build output
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    CHECK (build_type IN ('electron', 'python', 'other')),
    CHECK (status IN ('PENDING', 'BUILDING', 'SUCCESS', 'FAILED', 'SKIPPED'))
);

CREATE INDEX IF NOT EXISTS idx_builds_project_id ON builds(project_id);
CREATE INDEX IF NOT EXISTS idx_builds_order_id ON builds(order_id);
CREATE INDEX IF NOT EXISTS idx_builds_status ON builds(status);

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
