-- ============================================================================
-- Migration 003: Add is_destructive_db_change column to tasks table
-- Created: 2026-02-16
-- Description: Adds is_destructive_db_change flag to tasks table for tracking
--              tasks that perform destructive database operations (DROP TABLE,
--              ALTER TABLE DROP COLUMN, etc.)
-- ============================================================================

-- Add is_destructive_db_change column to tasks table
ALTER TABLE tasks ADD COLUMN is_destructive_db_change INTEGER NOT NULL DEFAULT 0;

-- Create index for filtering destructive DB change tasks
CREATE INDEX IF NOT EXISTS idx_tasks_is_destructive_db_change ON tasks(is_destructive_db_change);

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
