-- ============================================================================
-- Migration 002: tasksテーブルのCHECK制約にREJECTEDを追加
-- ============================================================================
-- 目的: tasksテーブルのstatus CHECK制約にREJECTEDステータスを追加する。
--
-- 背景:
--   初期スキーマではCHECK制約にREJECTEDが含まれておらず、
--   REWORK回数超過時のREJECTED遷移が制約違反でエラーになる問題があった。
--
-- 方式:
--   SQLiteではCHECK制約の変更にはテーブル再作成が必要。
--   手順: RENAME → CREATE → INSERT → DROP
--
-- 重要な注意:
--   SQLiteのALTER TABLE RENAMEは、参照元テーブル（FK）やVIEWの定義内の
--   テーブル名を自動的に追従変更する。そのため、tasksをリネームすると
--   以下が影響を受ける:
--     テーブル: task_dependencies, review_queue, escalations, file_locks, interactions
--     ビュー: v_active_tasks, v_pending_reviews, v_task_dependencies,
--             v_interaction_history, v_pending_interactions
--   これらは全てDROP→再CREATEが必要。
--
-- 冪等性について:
--   run_migrations() の schema_version テーブルで適用済み管理されるため、
--   2回実行されることはない。既に手動修正済みのDBに対して初めて
--   マイグレーションを適用する場合でも、CHECK制約の内容が同一であれば
--   データ損失なく再作成される（冪等ではないが安全）。
--   ただし、手動修正済みのDBでは schema_version に記録しておくことを推奨:
--     INSERT INTO schema_version (version, description)
--     VALUES ('002', 'fix_tasks_check_constraint');
--
-- 適用対象: CHECK制約にREJECTEDが含まれていないDB
-- ============================================================================

-- ============================================================================
-- Step 0: 外部キー制約を一時的に無効化（テーブル再作成のため）
-- ============================================================================
PRAGMA foreign_keys = OFF;

-- ============================================================================
-- Step 1: 影響を受けるVIEWを全てDROP
-- ============================================================================
-- RENAMEにより参照先が tasks_old に変わるため、先にDROPしておく
DROP VIEW IF EXISTS v_active_tasks;
DROP VIEW IF EXISTS v_pending_reviews;
DROP VIEW IF EXISTS v_task_dependencies;
DROP VIEW IF EXISTS v_interaction_history;
DROP VIEW IF EXISTS v_pending_interactions;

-- ============================================================================
-- Step 2: 影響を受ける参照テーブルを全てDROP
-- ============================================================================
-- RENAMEにより FK が tasks_old を参照するようになるため、先にデータ退避→再作成

-- task_dependencies のデータを退避
CREATE TABLE IF NOT EXISTS _tmp_task_dependencies AS SELECT * FROM task_dependencies;
DROP TABLE IF EXISTS task_dependencies;

-- review_queue のデータを退避
CREATE TABLE IF NOT EXISTS _tmp_review_queue AS SELECT * FROM review_queue;
DROP TABLE IF EXISTS review_queue;

-- escalations のデータを退避
CREATE TABLE IF NOT EXISTS _tmp_escalations AS SELECT * FROM escalations;
DROP TABLE IF EXISTS escalations;

-- file_locks のデータを退避
CREATE TABLE IF NOT EXISTS _tmp_file_locks AS SELECT * FROM file_locks;
DROP TABLE IF EXISTS file_locks;

-- interactions のデータを退避
CREATE TABLE IF NOT EXISTS _tmp_interactions AS SELECT * FROM interactions;
DROP TABLE IF EXISTS interactions;

-- ============================================================================
-- Step 3: tasksテーブルを再作成（CHECK制約にREJECTEDを追加）
-- ============================================================================

-- 旧テーブルをリネーム
ALTER TABLE tasks RENAME TO tasks_old;

-- 新テーブルを作成（REJECTEDを含むCHECK制約）
-- NOTE: 現在のDBにある追加カラム (phase, markdown_created, target_files) も含める
CREATE TABLE tasks (
    id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT DEFAULT 'P1',
    status TEXT NOT NULL DEFAULT 'QUEUED',
    recommended_model TEXT DEFAULT 'Opus',
    assignee TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    phase TEXT,
    markdown_created INTEGER NOT NULL DEFAULT 0,
    reject_count INTEGER NOT NULL DEFAULT 0,
    target_files TEXT DEFAULT NULL,

    PRIMARY KEY (id, project_id),
    FOREIGN KEY (order_id, project_id) REFERENCES orders(id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
    CHECK (status IN ('QUEUED', 'BLOCKED', 'IN_PROGRESS', 'DONE', 'IN_REVIEW',
                      'REWORK', 'COMPLETED', 'CANCELLED', 'SKIPPED', 'REJECTED'))
);

-- データを移行
INSERT INTO tasks (id, order_id, project_id, title, description, priority, status,
                   recommended_model, assignee, started_at, completed_at, created_at,
                   updated_at, phase, markdown_created, reject_count, target_files)
SELECT id, order_id, project_id, title, description, priority, status,
       recommended_model, assignee, started_at, completed_at, created_at,
       updated_at, phase, markdown_created, reject_count, target_files
FROM tasks_old;

-- 旧テーブルを削除
DROP TABLE tasks_old;

-- ============================================================================
-- Step 4: tasksのインデックスを再作成
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_tasks_order_id ON tasks(order_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);

-- ============================================================================
-- Step 5: 参照テーブルを再作成してデータを復元
-- ============================================================================

-- task_dependencies を再作成
CREATE TABLE task_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
    UNIQUE (task_id, depends_on_task_id, project_id)
);
INSERT INTO task_dependencies (id, task_id, depends_on_task_id, project_id, created_at)
SELECT id, task_id, depends_on_task_id, project_id, created_at FROM _tmp_task_dependencies;
DROP TABLE _tmp_task_dependencies;

CREATE INDEX IF NOT EXISTS idx_task_dependencies_task_id ON task_dependencies(task_id);
CREATE INDEX IF NOT EXISTS idx_task_dependencies_depends_on ON task_dependencies(depends_on_task_id);
CREATE INDEX IF NOT EXISTS idx_task_dependencies_project_id ON task_dependencies(project_id);

-- review_queue を再作成
CREATE TABLE review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'PENDING',
    reviewer TEXT,
    priority TEXT DEFAULT 'P1',
    comment TEXT,
    reviewed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CHECK (priority IN ('P0', 'P1', 'P2')),
    CHECK (status IN ('PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED'))
);
INSERT INTO review_queue (id, task_id, project_id, submitted_at, status, reviewer,
                          priority, comment, reviewed_at, created_at, updated_at)
SELECT id, task_id, project_id, submitted_at, status, reviewer,
       priority, comment, reviewed_at, created_at, updated_at FROM _tmp_review_queue;
DROP TABLE _tmp_review_queue;

CREATE INDEX IF NOT EXISTS idx_review_queue_task_id ON review_queue(task_id);
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_queue_priority ON review_queue(priority);
CREATE INDEX IF NOT EXISTS idx_review_queue_project_id ON review_queue(project_id);

-- escalations を再作成
CREATE TABLE escalations (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    resolution TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,

    FOREIGN KEY (task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CHECK (status IN ('OPEN', 'RESOLVED', 'CANCELED'))
);
INSERT INTO escalations (id, task_id, project_id, title, description, status,
                         resolution, created_at, resolved_at)
SELECT id, task_id, project_id, title, description, status,
       resolution, created_at, resolved_at FROM _tmp_escalations;
DROP TABLE _tmp_escalations;

-- file_locks を再作成
CREATE TABLE file_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    locked_at DATETIME NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (task_id, project_id) REFERENCES tasks(id, project_id),
    UNIQUE(project_id, file_path)
);
INSERT INTO file_locks (id, project_id, task_id, file_path, locked_at)
SELECT id, project_id, task_id, file_path, locked_at FROM _tmp_file_locks;
DROP TABLE _tmp_file_locks;

-- interactions を再作成
CREATE TABLE interactions (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    task_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    question_text TEXT NOT NULL,
    answer_text TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    context_snapshot TEXT,
    question_type TEXT DEFAULT 'GENERAL',
    options_json TEXT,
    timeout_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    answered_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id, project_id) REFERENCES tasks(id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CHECK (status IN ('PENDING', 'ANSWERED', 'TIMEOUT', 'CANCELLED', 'SKIPPED')),
    CHECK (question_type IN ('GENERAL', 'CONFIRMATION', 'CHOICE', 'INPUT', 'FILE_SELECT'))
);
INSERT INTO interactions (id, session_id, task_id, project_id, question_text, answer_text,
                          status, context_snapshot, question_type, options_json, timeout_at,
                          created_at, answered_at, updated_at)
SELECT id, session_id, task_id, project_id, question_text, answer_text,
       status, context_snapshot, question_type, options_json, timeout_at,
       created_at, answered_at, updated_at FROM _tmp_interactions;
DROP TABLE _tmp_interactions;

-- ============================================================================
-- Step 6: VIEWを再作成
-- ============================================================================

CREATE VIEW v_active_tasks AS
SELECT t.*, o.title as order_title, o.status as order_status
FROM tasks t
JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
WHERE t.status IN ('QUEUED', 'BLOCKED', 'IN_PROGRESS', 'DONE', 'IN_REVIEW', 'REWORK', 'REJECTED');

CREATE VIEW v_pending_reviews AS
SELECT t.*, o.title as order_title
FROM tasks t
JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
WHERE t.status = 'DONE';

CREATE VIEW v_task_dependencies AS
SELECT td.task_id, td.depends_on_task_id, td.project_id,
       t1.title as task_title, t1.status as task_status,
       t2.title as depends_on_title, t2.status as depends_on_status
FROM task_dependencies td
JOIN tasks t1 ON td.task_id = t1.id AND td.project_id = t1.project_id
JOIN tasks t2 ON td.depends_on_task_id = t2.id AND td.project_id = t2.project_id;

CREATE VIEW v_interaction_history AS
SELECT i.*, t.title as task_title, t.order_id
FROM interactions i
JOIN tasks t ON i.task_id = t.id AND i.project_id = t.project_id
ORDER BY i.created_at DESC;

CREATE VIEW v_pending_interactions AS
SELECT i.*, t.title as task_title, t.order_id, t.project_id as task_project_id
FROM interactions i
JOIN tasks t ON i.task_id = t.id AND i.project_id = t.project_id
WHERE i.status = 'PENDING';

-- ============================================================================
-- Step 7: 外部キー制約を再有効化
-- ============================================================================
PRAGMA foreign_keys = ON;

-- ============================================================================
-- Step 8: 整合性チェック
-- ============================================================================
PRAGMA integrity_check;
