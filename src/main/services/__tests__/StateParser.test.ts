/**
 * StateParser Unit Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { StateParser, StateParseError } from '../StateParser';
import type { ParsedState, TaskInfo, ReviewQueueItem, ProgressSummary } from '../StateParser';

describe('StateParser', () => {
  let parser: StateParser;

  beforeEach(() => {
    parser = new StateParser();
  });

  describe('parseProjectInfo', () => {
    it('should parse basic project information', () => {
      const content = `
# STATE.md

## プロジェクト情報

- **プロジェクト名**: AI PM Manager - 画面開発
- **現在ステータス**: \`IN_PROGRESS\`
- **アクティブORDER数**: 2
- **アクティブORDER**: ORDER_005
- **開始日**: 2026-01-19

## 次のセクション
`;

      const result = parser.parse(content);

      expect(result.projectInfo.name).toBe('AI PM Manager - 画面開発');
      expect(result.projectInfo.status).toBe('IN_PROGRESS');
      expect(result.projectInfo.activeOrderCount).toBe(2);
      expect(result.projectInfo.currentOrderId).toBe('ORDER_005');
      expect(result.projectInfo.startDate).toBe('2026-01-19');
    });

    it('should handle status without backticks', () => {
      const content = `
## プロジェクト情報

- **プロジェクト名**: テストプロジェクト
- **現在ステータス**: COMPLETED
`;

      const result = parser.parse(content);
      expect(result.projectInfo.status).toBe('COMPLETED');
    });

    it('should use 発注ID as fallback for currentOrderId', () => {
      const content = `
## プロジェクト情報

- **発注ID**: ORDER_036
- **プロジェクト名**: フレームワークDB移行
- **現在ステータス**: \`IN_PROGRESS\`
`;

      const result = parser.parse(content);
      expect(result.projectInfo.currentOrderId).toBe('ORDER_036');
    });
  });

  describe('parseTaskSections', () => {
    it('should parse single ORDER task list', () => {
      const content = `
## タスク一覧（ORDER_005）【IN_PROGRESS】

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_017 | STATE.mdパーサー実装 | QUEUED | Worker A | - | - | - |
| TASK_018 | ProjectService実装 | BLOCKED | Worker B | TASK_017 | - | - |
`;

      const result = parser.parse(content);

      expect(result.tasks).toHaveLength(2);
      expect(result.orders).toHaveLength(1);
      expect(result.orders[0].id).toBe('ORDER_005');
      expect(result.orders[0].status).toBe('IN_PROGRESS');

      const task017 = result.tasks.find(t => t.id === 'TASK_017');
      expect(task017).toBeDefined();
      expect(task017?.title).toBe('STATE.mdパーサー実装');
      expect(task017?.status).toBe('QUEUED');
      expect(task017?.assignee).toBe('Worker A');
      expect(task017?.dependencies).toHaveLength(0);

      const task018 = result.tasks.find(t => t.id === 'TASK_018');
      expect(task018?.dependencies).toEqual(['TASK_017']);
    });

    it('should parse multiple ORDER task lists', () => {
      const content = `
## タスク一覧（ORDER_005）【IN_PROGRESS】

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_017 | パーサー実装 | IN_PROGRESS | Worker A | - | 2026-01-23 | - |

## タスク一覧（ORDER_004）【COMPLETED】

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_016 | chokidar対応 | COMPLETED | Worker A | - | 2026-01-21 | 2026-01-21 |
`;

      const result = parser.parse(content);

      expect(result.tasks).toHaveLength(2);
      expect(result.orders).toHaveLength(2);
      expect(result.orders[0].id).toBe('ORDER_005');
      expect(result.orders[1].id).toBe('ORDER_004');

      const task016 = result.tasks.find(t => t.id === 'TASK_016');
      expect(task016?.status).toBe('COMPLETED');
      expect(task016?.startDate).toBe('2026-01-21');
      expect(task016?.completedDate).toBe('2026-01-21');
    });

    it('should parse tasks with multiple dependencies', () => {
      const content = `
## タスク一覧（ORDER_001）

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_006 | 統合テスト | COMPLETED | Worker A | TASK_003,TASK_004,TASK_005 | 2026-01-20 | 2026-01-20 |
`;

      const result = parser.parse(content);

      const task006 = result.tasks.find(t => t.id === 'TASK_006');
      expect(task006?.dependencies).toEqual(['TASK_003', 'TASK_004', 'TASK_005']);
    });

    it('should parse interrupt tasks', () => {
      const content = `
## タスク一覧（ORDER_010）

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_075_INT | 割り込みタスク | DONE | Worker A | TASK_075 | 2026-01-20 | - |
| TASK_075_INT_02 | 2回目割り込み | QUEUED | - | TASK_075_INT | - | - |
`;

      const result = parser.parse(content);

      expect(result.tasks).toHaveLength(2);
      const intTask = result.tasks.find(t => t.id === 'TASK_075_INT');
      expect(intTask?.status).toBe('DONE');

      const intTask02 = result.tasks.find(t => t.id === 'TASK_075_INT_02');
      expect(intTask02?.dependencies).toEqual(['TASK_075_INT']);
    });
  });

  describe('parseReviewQueue', () => {
    it('should parse review queue with entries', () => {
      const content = `
## レビューキュー

| Task ID | 提出日時 | ステータス | レビュアー | 優先度 | 備考 |
|---------|---------|----------|-----------|--------|------|
| TASK_017 | 2026-01-23 15:30 | PENDING | - | P1 | - |
| TASK_016 | 2026-01-21 10:00 | IN_REVIEW | PM | P0 | 再提出 |
`;

      const result = parser.parse(content);

      expect(result.reviewQueue).toHaveLength(2);

      const queue017 = result.reviewQueue.find(q => q.taskId === 'TASK_017');
      expect(queue017?.submittedAt).toBe('2026-01-23 15:30');
      expect(queue017?.status).toBe('PENDING');
      expect(queue017?.reviewer).toBeUndefined();
      expect(queue017?.priority).toBe('P1');
      expect(queue017?.note).toBeUndefined();

      const queue016 = result.reviewQueue.find(q => q.taskId === 'TASK_016');
      expect(queue016?.reviewer).toBe('PM');
      expect(queue016?.priority).toBe('P0');
      expect(queue016?.note).toBe('再提出');
    });

    it('should handle empty review queue', () => {
      const content = `
## レビューキュー

| Task ID | 提出日時 | ステータス | レビュアー | 優先度 | 備考 |
|---------|---------|----------|-----------|--------|------|
| - | - | - | - | - | - |
`;

      const result = parser.parse(content);
      expect(result.reviewQueue).toHaveLength(0);
    });
  });

  describe('parseProgressSummary', () => {
    it('should parse progress summary from section', () => {
      const content = `
## 進捗サマリ

- **完了タスク数**: 5 / 8
- **進行中タスク数**: 2
- **レビュー待ちタスク数**: 1
- **待機中タスク数**: 0
- **ブロック中タスク数**: 0
- **差し戻しタスク数**: 0
`;

      const result = parser.parse(content);

      expect(result.progressSummary.completed).toBe(5);
      expect(result.progressSummary.inProgress).toBe(2);
      expect(result.progressSummary.reviewWaiting).toBe(1);
      expect(result.progressSummary.queued).toBe(0);
      expect(result.progressSummary.blocked).toBe(0);
      expect(result.progressSummary.rework).toBe(0);
    });

    it('should calculate summary from tasks when section is missing', () => {
      const content = `
## タスク一覧（ORDER_001）

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_001 | タスク1 | COMPLETED | Worker A | - | 2026-01-20 | 2026-01-20 |
| TASK_002 | タスク2 | COMPLETED | Worker A | - | 2026-01-20 | 2026-01-20 |
| TASK_003 | タスク3 | IN_PROGRESS | Worker B | - | 2026-01-20 | - |
| TASK_004 | タスク4 | QUEUED | - | TASK_003 | - | - |
| TASK_005 | タスク5 | BLOCKED | - | TASK_004 | - | - |
| TASK_006 | タスク6 | DONE | Worker A | - | 2026-01-20 | - |
| TASK_007 | タスク7 | REWORK | Worker A | - | 2026-01-20 | - |
`;

      const result = parser.parse(content);

      expect(result.progressSummary.completed).toBe(2);
      expect(result.progressSummary.inProgress).toBe(1);
      expect(result.progressSummary.reviewWaiting).toBe(1);  // DONE
      expect(result.progressSummary.queued).toBe(1);
      expect(result.progressSummary.blocked).toBe(1);
      expect(result.progressSummary.rework).toBe(1);
      expect(result.progressSummary.total).toBe(7);
    });
  });

  describe('parseOrderTasks', () => {
    it('should parse tasks for specific ORDER', () => {
      const content = `
## タスク一覧（ORDER_005）

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_017 | タスク17 | QUEUED | Worker A | - | - | - |

## タスク一覧（ORDER_004）

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_016 | タスク16 | COMPLETED | Worker A | - | 2026-01-21 | 2026-01-21 |
`;

      const tasks = parser.parseOrderTasks(content, 'ORDER_005');

      expect(tasks).toHaveLength(1);
      expect(tasks[0].id).toBe('TASK_017');
    });

    it('should return empty array for non-existent ORDER', () => {
      const content = `
## タスク一覧（ORDER_005）

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_017 | タスク17 | QUEUED | Worker A | - | - | - |
`;

      const tasks = parser.parseOrderTasks(content, 'ORDER_999');
      expect(tasks).toHaveLength(0);
    });
  });

  describe('isValidStateFile', () => {
    it('should return true for valid STATE.md', () => {
      const content = `
# STATE.md

## プロジェクト情報

- **プロジェクト名**: テスト

## ステータス定義

| Status | 説明 |
|--------|------|
| INITIAL | 初期状態 |

## タスク一覧（ORDER_001）

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_001 | テスト | QUEUED | - | - | - | - |
`;

      expect(parser.isValidStateFile(content)).toBe(true);
    });

    it('should return false for invalid content', () => {
      const content = `
# README.md

This is not a STATE.md file.
`;

      expect(parser.isValidStateFile(content)).toBe(false);
    });
  });

  describe('full STATE.md parsing', () => {
    it('should parse complete ai_pm_manager STATE.md format', () => {
      const content = `
# STATE.md

## プロジェクト状態管理

> **このファイルはプロジェクトの現在状態を記録します。PM・Workerが随時更新します。**

---

## プロジェクト情報

- **プロジェクト名**: AI PM Manager - 画面開発
- **発注ID**: ORDER_001, ORDER_002, ORDER_003, ORDER_004, ORDER_005
- **開始日**: 2026-01-19
- **目標完了日**: -
- **現在ステータス**: \`IN_PROGRESS\`
- **アクティブORDER数**: 1 / 3（推奨上限）
- **アクティブORDER**: ORDER_005

---

## 現在のフェーズ

- **Phase**: ORDER_005 画面開発（Phase 2-3）
- **次のアクション**: Worker によるTASK_017から作業開始

---

## タスク一覧（ORDER_005）【IN_PROGRESS】

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_017 | STATE.mdパーサー実装 | IN_PROGRESS | Worker A | - | 2026-01-23 | - |
| TASK_018 | ProjectService実装 | BLOCKED | Worker B | TASK_017 | - | - |
| TASK_019 | プロジェクト一覧UI | BLOCKED | Worker A | TASK_018 | - | - |

---

## タスク一覧（ORDER_004）【COMPLETED】

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_016 | chokidar対応 | COMPLETED | Worker A | - | 2026-01-21 | 2026-01-21 |

---

## レビューキュー

| Task ID | 提出日時 | ステータス | レビュアー | 優先度 | 備考 |
|---------|---------|----------|-----------|--------|------|
| - | - | - | - | - | - |

---

## 進捗サマリ

### ORDER_005（画面開発 Phase 2-3）【IN_PROGRESS】
- **完了タスク数**: 0 / 3
- **進行中タスク数**: 1
- **レビュー待ちタスク数**: 0
- **待機中タスク数**: 0
- **ブロック中タスク数**: 2
`;

      const result = parser.parse(content);

      // プロジェクト情報の検証
      expect(result.projectInfo.name).toBe('AI PM Manager - 画面開発');
      expect(result.projectInfo.status).toBe('IN_PROGRESS');
      expect(result.projectInfo.activeOrderCount).toBe(1);
      expect(result.projectInfo.currentOrderId).toBe('ORDER_005');
      expect(result.projectInfo.startDate).toBe('2026-01-19');

      // タスク一覧の検証
      expect(result.tasks).toHaveLength(4);
      expect(result.orders).toHaveLength(2);

      // ORDER_005のタスク
      const order005 = result.orders.find(o => o.id === 'ORDER_005');
      expect(order005?.tasks).toHaveLength(3);
      expect(order005?.status).toBe('IN_PROGRESS');

      // ORDER_004のタスク
      const order004 = result.orders.find(o => o.id === 'ORDER_004');
      expect(order004?.tasks).toHaveLength(1);
      expect(order004?.status).toBe('COMPLETED');

      // 進捗サマリの検証
      expect(result.progressSummary.completed).toBe(0);
      expect(result.progressSummary.inProgress).toBe(1);
      expect(result.progressSummary.blocked).toBe(2);
      expect(result.progressSummary.total).toBe(4);

      // レビューキューの検証（空）
      expect(result.reviewQueue).toHaveLength(0);
    });
  });

  describe('error handling', () => {
    it('should handle empty content', () => {
      const result = parser.parse('');

      expect(result.projectInfo.name).toBe('');
      expect(result.projectInfo.status).toBe('INITIAL');
      expect(result.tasks).toHaveLength(0);
      expect(result.reviewQueue).toHaveLength(0);
    });

    it('should handle malformed table rows', () => {
      const content = `
## タスク一覧（ORDER_001）

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_001 | 正常なタスク | QUEUED | Worker A | - | - | - |
| これは不正な行です |
| TASK_002 | もう一つの正常タスク | IN_PROGRESS | Worker B | - | 2026-01-23 | - |
`;

      const result = parser.parse(content);

      // 正常なタスクのみ抽出される
      expect(result.tasks).toHaveLength(2);
      expect(result.tasks[0].id).toBe('TASK_001');
      expect(result.tasks[1].id).toBe('TASK_002');
    });
  });
});
