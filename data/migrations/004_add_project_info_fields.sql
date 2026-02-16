-- ============================================================================
-- Migration 004: Add project information fields (description, purpose, metadata)
-- Created: 2026-02-16
-- Description: Adds description, purpose, and metadata columns to projects table
--              for storing comprehensive project information (概要、目的、技術スタック等)
-- ============================================================================

-- Add description column (プロジェクト概要)
ALTER TABLE projects ADD COLUMN description TEXT;

-- Add purpose column (プロジェクト目的)
ALTER TABLE projects ADD COLUMN purpose TEXT;

-- Add metadata column (メタデータ: JSON形式で技術スタック等を格納)
ALTER TABLE projects ADD COLUMN metadata TEXT;

-- ============================================================================
-- NOTES:
-- - description: プロジェクトの簡潔な説明
-- - purpose: プロジェクトの目的・達成目標
-- - metadata: JSON形式でtech_stack, repository_url, dependencies等を格納可能
--   例: {"tech_stack": ["Python", "Electron", "TypeScript"], "repo_url": "..."}
-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
