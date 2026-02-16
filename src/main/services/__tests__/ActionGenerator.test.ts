/**
 * ActionGenerator Unit Tests
 *
 * TASK_025: 推奨アクション生成ロジック実装 - 単体テスト
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { ActionGenerator, getActionGenerator, resetActionGenerator } from '../ActionGenerator';
import type { RecommendedAction } from '../ActionGenerator';
import type { ParsedState, TaskInfo, ReviewQueueItem } from '../StateParser';

/**
 * テスト用のモックParsedStateを生成するヘルパー
 */
function createMockState(overrides?: Partial<ParsedState>): ParsedState {
  return {
    projectInfo: {
      name: 'Test Project',
      status: 'IN_PROGRESS',
      activeOrderCount: 1,
      currentOrderId: 'ORDER_001',
    },
    tasks: [],
    reviewQueue: [],
    progressSummary: {
      completed: 0,
      inProgress: 0,
      reviewWaiting: 0,
      queued: 0,
      blocked: 0,
      rework: 0,
      total: 0,
    },
    orders: [],
    ...overrides,
  };
}

/**
 * テスト用のモックTaskInfoを生成するヘルパー
 */
function createMockTask(overrides?: Partial<TaskInfo>): TaskInfo {
  return {
    id: 'TASK_001',
    title: 'テストタスク',
    status: 'QUEUED',
    assignee: 'Worker A',
    dependencies: [],
    ...overrides,
  };
}

describe('ActionGenerator', () => {
  let generator: ActionGenerator;

  beforeEach(() => {
    resetActionGenerator();
    generator = new ActionGenerator();
  });

  describe('constructor', () => {
    it('should use default maxActions of 3', () => {
      const gen = new ActionGenerator();
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_002', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_003', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_004', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_005', status: 'QUEUED' }),
        ],
      });

      const actions = gen.generate('TestProject', state);
      expect(actions).toHaveLength(3);
    });

    it('should respect custom maxActions', () => {
      const gen = new ActionGenerator({ maxActions: 5 });
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_002', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_003', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_004', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_005', status: 'QUEUED' }),
        ],
      });

      const actions = gen.generate('TestProject', state);
      expect(actions).toHaveLength(5);
    });
  });

  describe('REWORK tasks (priority 1)', () => {
    it('should generate worker action for REWORK task', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_025', title: '差し戻しタスク', status: 'REWORK' }),
        ],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      expect(actions).toHaveLength(1);
      expect(actions[0].type).toBe('worker');
      expect(actions[0].command).toBe('/aipm-worker AI_PM_PJ 025');
      expect(actions[0].description).toContain('差し戻しタスクを修正');
      expect(actions[0].priority).toBe(1);
      expect(actions[0].taskId).toBe('TASK_025');
    });

    it('should generate multiple worker actions for multiple REWORK tasks', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_100', title: '差し戻し1', status: 'REWORK' }),
          createMockTask({ id: 'TASK_101', title: '差し戻し2', status: 'REWORK' }),
        ],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      expect(actions).toHaveLength(2);
      expect(actions.every(a => a.priority === 1)).toBe(true);
    });

    it('should prioritize REWORK over other statuses', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_002', status: 'REWORK' }),
          createMockTask({ id: 'TASK_003', status: 'DONE' }),
        ],
      });

      const actions = generator.generate('TestProject', state);

      // 最初のアクションはREWORKタスク
      expect(actions[0].taskId).toBe('TASK_002');
      expect(actions[0].priority).toBe(1);
    });
  });


  describe('IN_PROGRESS tasks (priority 0)', () => {
    it('should generate retry action for IN_PROGRESS task', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_042', title: '中断タスク', status: 'IN_PROGRESS' }),
        ],
      });

      const actions = generator.generate('ai_pm_manager', state);

      expect(actions).toHaveLength(1);
      expect(actions[0].id).toBe('retry-TASK_042-0');
      expect(actions[0].type).toBe('worker');
      expect(actions[0].command).toBe('/aipm-worker ai_pm_manager 042');
      expect(actions[0].description).toBe('中断タスクを再実行: 中断タスク');
      expect(actions[0].priority).toBe(0);
      expect(actions[0].taskId).toBe('TASK_042');
    });

    it('should prioritize IN_PROGRESS over REWORK', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', status: 'REWORK' }),
          createMockTask({ id: 'TASK_002', title: '中断', status: 'IN_PROGRESS' }),
        ],
      });

      const actions = generator.generate('TestProject', state);

      // IN_PROGRESS(優先度0)がREWORK(優先度1)より先
      expect(actions[0].priority).toBe(0);
      expect(actions[0].taskId).toBe('TASK_002');
      expect(actions[1].priority).toBe(1);
      expect(actions[1].taskId).toBe('TASK_001');
    });

    it('should generate retry actions for multiple IN_PROGRESS tasks', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', title: '中断1', status: 'IN_PROGRESS' }),
          createMockTask({ id: 'TASK_002', title: '中断2', status: 'IN_PROGRESS' }),
        ],
      });

      const actions = generator.generate('TestProject', state);

      expect(actions).toHaveLength(2);
      expect(actions.every(a => a.priority === 0)).toBe(true);
      expect(actions.every(a => a.id.startsWith('retry-'))).toBe(true);
    });
  });

    describe('Review waiting tasks (priority 2)', () => {
    it('should generate review action for DONE task', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_050', status: 'DONE' }),
        ],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      expect(actions.length).toBeGreaterThanOrEqual(1);
      const reviewAction = actions.find(a => a.type === 'review');
      expect(reviewAction).toBeDefined();
      expect(reviewAction?.command).toBe('/aipm-review AI_PM_PJ --next');
      expect(reviewAction?.priority).toBe(2);
    });

    it('should generate review action for PENDING in review queue', () => {
      const state = createMockState({
        reviewQueue: [
          {
            taskId: 'TASK_100',
            submittedAt: '2026-01-26 10:00',
            status: 'PENDING',
            priority: 'P1',
          },
        ],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      expect(actions.length).toBeGreaterThanOrEqual(1);
      const reviewAction = actions.find(a => a.type === 'review');
      expect(reviewAction).toBeDefined();
      expect(reviewAction?.description).toContain('1件');
    });

    it('should add specific action for P0 priority review', () => {
      const state = createMockState({
        reviewQueue: [
          {
            taskId: 'TASK_100',
            submittedAt: '2026-01-26 10:00',
            status: 'PENDING',
            priority: 'P0',
          },
        ],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      const p0Action = actions.find(a => a.command.includes('100'));
      expect(p0Action).toBeDefined();
      expect(p0Action?.description).toContain('P0');
    });
  });

  describe('QUEUED tasks (priority 3)', () => {
    it('should generate worker action for QUEUED task', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_025', title: '次のタスク', status: 'QUEUED' }),
        ],
      });

      const actions = generator.generate('ai_pm_manager', state);

      expect(actions).toHaveLength(1);
      expect(actions[0].type).toBe('worker');
      expect(actions[0].command).toBe('/aipm-worker ai_pm_manager 025');
      expect(actions[0].description).toContain('次のタスクを開始');
      expect(actions[0].priority).toBe(3);
    });

    it('should generate actions for all QUEUED tasks', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_002', status: 'QUEUED' }),
          createMockTask({ id: 'TASK_003', status: 'QUEUED' }),
        ],
      });

      const actions = generator.generate('TestProject', state);

      expect(actions).toHaveLength(3);
      expect(actions.every(a => a.priority === 3)).toBe(true);
    });
  });

  describe('All completed (priority 5)', () => {
    it('should generate status action when all tasks are COMPLETED', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', status: 'COMPLETED' }),
          createMockTask({ id: 'TASK_002', status: 'COMPLETED' }),
        ],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      expect(actions).toHaveLength(1);
      expect(actions[0].type).toBe('status');
      expect(actions[0].command).toBe('/aipm-status AI_PM_PJ');
      expect(actions[0].description).toContain('全タスク完了');
      expect(actions[0].priority).toBe(5);
    });

    it('should generate status action when no tasks exist', () => {
      const state = createMockState({
        tasks: [],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      expect(actions).toHaveLength(1);
      expect(actions[0].type).toBe('status');
    });

    it('should generate retry action when IN_PROGRESS exists (not status action)', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', title: '中断タスク', status: 'IN_PROGRESS' }),
        ],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      // IN_PROGRESSは再実行アクションを生成（優先度0）
      expect(actions).toHaveLength(1);
      expect(actions[0].id).toMatch(/^retry-/);
      expect(actions[0].type).toBe('worker');
      expect(actions[0].priority).toBe(0);
      expect(actions[0].command).toBe('/aipm-worker AI_PM_PJ 001');
      expect(actions[0].description).toContain('中断タスクを再実行');
      expect(actions[0].taskId).toBe('TASK_001');
    });
  });

  describe('Priority sorting', () => {
    it('should sort actions by priority', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', status: 'QUEUED' }),  // priority 3
          createMockTask({ id: 'TASK_002', status: 'REWORK' }), // priority 1
          createMockTask({ id: 'TASK_003', status: 'DONE' }),   // priority 2 (review)
        ],
      });

      const actions = generator.generate('TestProject', state);

      // 優先度順: REWORK(1) -> Review(2) -> QUEUED(3)
      expect(actions[0].priority).toBe(1); // REWORK
      expect(actions[1].priority).toBe(2); // Review
      expect(actions[2].priority).toBe(3); // QUEUED
    });
  });

  describe('max actions limit', () => {
    it('should limit actions to maxActions', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', status: 'REWORK' }),
          createMockTask({ id: 'TASK_002', status: 'REWORK' }),
          createMockTask({ id: 'TASK_003', status: 'REWORK' }),
          createMockTask({ id: 'TASK_004', status: 'REWORK' }),
          createMockTask({ id: 'TASK_005', status: 'REWORK' }),
        ],
      });

      const actions = generator.generate('TestProject', state);

      expect(actions).toHaveLength(3); // デフォルトは3件
    });
  });

  describe('command format', () => {
    it('should extract task number correctly', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_025', status: 'QUEUED' }),
        ],
      });

      const actions = generator.generate('ai_pm_manager', state);

      expect(actions[0].command).toBe('/aipm-worker ai_pm_manager 025');
    });

    it('should handle interrupt task IDs', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_075_INT', status: 'QUEUED' }),
        ],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      expect(actions[0].command).toBe('/aipm-worker AI_PM_PJ 075_INT');
    });

    it('should handle interrupt task IDs with number', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_075_INT_02', status: 'QUEUED' }),
        ],
      });

      const actions = generator.generate('AI_PM_PJ', state);

      expect(actions[0].command).toBe('/aipm-worker AI_PM_PJ 075_INT_02');
    });
  });

  describe('singleton', () => {
    it('should return same instance from getActionGenerator', () => {
      const instance1 = getActionGenerator();
      const instance2 = getActionGenerator();

      expect(instance1).toBe(instance2);
    });

    it('should reset instance with resetActionGenerator', () => {
      const instance1 = getActionGenerator();
      resetActionGenerator();
      const instance2 = getActionGenerator();

      expect(instance1).not.toBe(instance2);
    });
  });

  describe('action id uniqueness', () => {
    it('should generate unique action IDs', () => {
      const state = createMockState({
        tasks: [
          createMockTask({ id: 'TASK_001', status: 'REWORK' }),
          createMockTask({ id: 'TASK_002', status: 'REWORK' }),
          createMockTask({ id: 'TASK_003', status: 'QUEUED' }),
        ],
        reviewQueue: [
          {
            taskId: 'TASK_004',
            submittedAt: '2026-01-26 10:00',
            status: 'PENDING',
            priority: 'P1',
          },
        ],
      });

      const actions = generator.generate('TestProject', state);

      const ids = actions.map(a => a.id);
      const uniqueIds = new Set(ids);

      expect(uniqueIds.size).toBe(ids.length);
    });
  });
});
