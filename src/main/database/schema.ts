/**
 * SQLite Database Schema Definition
 *
 * AI PM Manager のデータベーススキーマを定義します。
 * ADR-001 に基づき、状態管理をSQLiteで行います。
 */

export const SCHEMA_VERSION = 1;

/**
 * 初期スキーマ定義（v1）
 */
export const INITIAL_SCHEMA = `
-- プロジェクト
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  path TEXT NOT NULL,
  description TEXT,
  purpose TEXT,
  tech_stack TEXT,
  status TEXT NOT NULL DEFAULT 'INITIAL',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- ORDER
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  order_number INTEGER NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PLANNING',
  priority TEXT NOT NULL DEFAULT 'P2',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  UNIQUE(project_id, order_number)
);

-- タスク
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL,
  task_number INTEGER NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'QUEUED',
  assignee TEXT,
  depends_on TEXT,
  started_at TEXT,
  completed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  UNIQUE(order_id, task_number)
);

-- レビューキュー
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'PENDING',
  priority TEXT NOT NULL DEFAULT 'P1',
  reviewer TEXT,
  submitted_at TEXT NOT NULL,
  reviewed_at TEXT,
  comment TEXT,
  FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- バックログ
CREATE TABLE IF NOT EXISTS backlogs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  backlog_number INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  priority TEXT NOT NULL DEFAULT 'Medium',
  status TEXT NOT NULL DEFAULT 'TODO',
  order_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
  UNIQUE(project_id, backlog_number)
);

-- スキーマバージョン管理
CREATE TABLE IF NOT EXISTS schema_versions (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_orders_project_id ON orders(project_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_tasks_order_id ON tasks(order_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
CREATE INDEX IF NOT EXISTS idx_backlogs_project_id ON backlogs(project_id);
CREATE INDEX IF NOT EXISTS idx_backlogs_status ON backlogs(status);
`;

/**
 * ステータス定義
 */
export const PROJECT_STATUSES = [
  'INITIAL',
  'PLANNING',
  'IN_PROGRESS',
  'REVIEW',
  'REWORK',
  'ESCALATED',
  'ESCALATION_RESOLVED',
  'COMPLETED',
  'ON_HOLD',
  'CANCELLED',
] as const;

export const ORDER_STATUSES = [
  'PLANNING',
  'IN_PROGRESS',
  'REVIEW',
  'COMPLETED',
  'ON_HOLD',
  'CANCELLED',
] as const;

export const TASK_STATUSES = [
  'QUEUED',
  'BLOCKED',
  'IN_PROGRESS',
  'DONE',
  'REWORK',
  'COMPLETED',
] as const;

export const REVIEW_STATUSES = [
  'PENDING',
  'IN_REVIEW',
  'APPROVED',
  'REJECTED',
] as const;

export const BACKLOG_STATUSES = [
  'TODO',
  'IN_ORDER',
  'DONE',
] as const;

export const PRIORITIES = ['P0', 'P1', 'P2', 'P3'] as const;
export const BACKLOG_PRIORITIES = ['High', 'Medium', 'Low'] as const;

export type ProjectStatus = typeof PROJECT_STATUSES[number];
export type OrderStatus = typeof ORDER_STATUSES[number];
export type TaskStatus = typeof TASK_STATUSES[number];
export type ReviewStatus = typeof REVIEW_STATUSES[number];
export type BacklogStatus = typeof BACKLOG_STATUSES[number];
export type Priority = typeof PRIORITIES[number];
export type BacklogPriority = typeof BACKLOG_PRIORITIES[number];
