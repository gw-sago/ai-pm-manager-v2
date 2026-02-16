-- ============================================================================
-- Migration 001: change_historyテーブルにproject_idカラムを追加
-- ============================================================================
-- 目的: change_historyテーブルにproject_idカラムを追加し、
--       プロジェクト単位でのフィルタリングを可能にする。
--
-- 冪等性について:
--   SQLiteのALTER TABLE ADD COLUMNには IF NOT EXISTS 構文がないため、
--   既にproject_idカラムが存在する場合はエラーが発生する。
--   このマイグレーションは run_migrations() の schema_version テーブルで
--   適用済み管理されるため、2回実行されることはない。
--   ただし、手動でカラムが追加済みのDBに対して初めてマイグレーションを
--   適用する場合は「duplicate column name」エラーが発生する可能性がある。
--   その場合は schema_version テーブルに手動で記録すること:
--     INSERT INTO schema_version (version, description)
--     VALUES ('001', 'add_project_id_to_change_history');
--
-- 適用対象: project_idカラムが未追加のDB（新規DBまたは手動修正前のDB）
-- 既に手動修正済みのDBでは schema_version に記録済みであればスキップされる
-- ============================================================================

-- project_idカラムを追加（NULLable、フィルタリング用）
ALTER TABLE change_history ADD COLUMN project_id TEXT;

-- project_idカラムにインデックスを追加（既にある場合はIF NOT EXISTSでスキップ）
CREATE INDEX IF NOT EXISTS idx_change_history_project_id ON change_history(project_id);
