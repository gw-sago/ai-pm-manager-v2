/**
 * Database Type Definitions
 *
 * schema_v2.sql のCHECK制約と一致するステータス・型定義。
 * 旧schema.tsから移行。
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
  'IN_REVIEW',
  'REWORK',
  'COMPLETED',
  'CANCELLED',
  'SKIPPED',
  'REJECTED',
  'INTERRUPTED',
  'ESCALATED',
  'WAITING_INPUT',
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
