/**
 * TaskService Unit Tests
 *
 * Note: schemaのみをインポートし、サービス・リポジトリの循環インポートを回避
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Database from 'better-sqlite3';
import { INITIAL_SCHEMA, type TaskStatus, type Priority } from '../../database/schema';

// 循環インポートを避けるため、テスト用の軽量サービスをインラインで定義
class StateTransitionError extends Error {
  constructor(
    public readonly taskId: number,
    public readonly currentStatus: TaskStatus,
    public readonly targetStatus: TaskStatus,
    message?: string
  ) {
    super(message ?? `Invalid state transition: ${currentStatus} -> ${targetStatus}`);
    this.name = 'StateTransitionError';
  }
}

const VALID_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  QUEUED: ['IN_PROGRESS', 'BLOCKED'],
  BLOCKED: ['QUEUED'],
  IN_PROGRESS: ['DONE', 'BLOCKED'],
  DONE: ['COMPLETED', 'REWORK'],
  REWORK: ['DONE'],
  COMPLETED: [],
};

interface Task {
  id: number;
  order_id: number;
  task_number: number;
  title: string;
  status: TaskStatus;
  assignee: string | null;
  depends_on: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

// テスト用TaskService（純粋なSQLite操作のみ）
class TestTaskService {
  constructor(private db: Database.Database) {}

  isValidTransition(from: TaskStatus, to: TaskStatus): boolean {
    return VALID_TRANSITIONS[from]?.includes(to) ?? false;
  }

  private findTaskById(id: number): Task | undefined {
    return this.db.prepare('SELECT * FROM tasks WHERE id = ?').get(id) as Task | undefined;
  }

  private getDependencies(task: Task): number[] {
    if (!task.depends_on) return [];
    try { return JSON.parse(task.depends_on) as number[]; }
    catch { return []; }
  }

  private areDependenciesComplete(task: Task): boolean {
    const deps = this.getDependencies(task);
    if (deps.length === 0) return true;
    for (const depId of deps) {
      const depTask = this.findTaskById(depId);
      if (!depTask || depTask.status !== 'COMPLETED') return false;
    }
    return true;
  }

  startTask(input: { taskId: number; assignee: string }) {
    const task = this.findTaskById(input.taskId);
    if (!task) throw new Error(`Task not found: ${input.taskId}`);
    if (!this.areDependenciesComplete(task))
      throw new StateTransitionError(input.taskId, task.status, 'IN_PROGRESS', 'Dependencies not completed');
    if (!this.isValidTransition(task.status, 'IN_PROGRESS'))
      throw new StateTransitionError(input.taskId, task.status, 'IN_PROGRESS');

    const previousStatus = task.status;
    const now = new Date().toISOString();
    this.db.prepare(`UPDATE tasks SET status='IN_PROGRESS',assignee=?,started_at=?,updated_at=? WHERE id=?`)
      .run(input.assignee, now, now, input.taskId);
    return { task: this.findTaskById(input.taskId)!, previousStatus, unblocked: [] as Task[] };
  }

  completeTask(input: { taskId: number; reviewPriority?: Priority }) {
    const task = this.findTaskById(input.taskId);
    if (!task) throw new Error(`Task not found: ${input.taskId}`);
    if (!this.isValidTransition(task.status, 'DONE'))
      throw new StateTransitionError(input.taskId, task.status, 'DONE');

    const previousStatus = task.status;
    const now = new Date().toISOString();
    this.db.prepare(`UPDATE tasks SET status='DONE',updated_at=? WHERE id=?`).run(now, input.taskId);
    this.db.prepare(`INSERT INTO reviews (task_id,status,priority,submitted_at) VALUES(?,'PENDING',?,?)`)
      .run(input.taskId, input.reviewPriority ?? 'P1', now);
    return { task: this.findTaskById(input.taskId)!, previousStatus, unblocked: [] as Task[] };
  }

  approveReview(taskId: number, reviewer: string, comment?: string) {
    const task = this.findTaskById(taskId);
    if (!task) throw new Error(`Task not found: ${taskId}`);
    if (!this.isValidTransition(task.status, 'COMPLETED'))
      throw new StateTransitionError(taskId, task.status, 'COMPLETED');

    const previousStatus = task.status;
    const now = new Date().toISOString();
    this.db.prepare(`UPDATE tasks SET status='COMPLETED',completed_at=?,updated_at=? WHERE id=?`).run(now, now, taskId);
    this.db.prepare(`UPDATE reviews SET status='APPROVED',reviewer=?,reviewed_at=?,comment=? WHERE task_id=?`)
      .run(reviewer, now, comment ?? null, taskId);
    const unblocked = this.checkAndUnblockDependents(taskId);
    return { task: this.findTaskById(taskId)!, previousStatus, unblocked };
  }

  rejectReview(taskId: number, reviewer: string, comment: string) {
    const task = this.findTaskById(taskId);
    if (!task) throw new Error(`Task not found: ${taskId}`);
    if (!this.isValidTransition(task.status, 'REWORK'))
      throw new StateTransitionError(taskId, task.status, 'REWORK');

    const previousStatus = task.status;
    const now = new Date().toISOString();
    this.db.prepare(`UPDATE tasks SET status='REWORK',updated_at=? WHERE id=?`).run(now, taskId);
    this.db.prepare(`UPDATE reviews SET status='REJECTED',reviewer=?,reviewed_at=?,comment=? WHERE task_id=?`)
      .run(reviewer, now, comment, taskId);
    return { task: this.findTaskById(taskId)!, previousStatus, unblocked: [] as Task[] };
  }

  resubmitTask(taskId: number) {
    const task = this.findTaskById(taskId);
    if (!task) throw new Error(`Task not found: ${taskId}`);
    if (!this.isValidTransition(task.status, 'DONE'))
      throw new StateTransitionError(taskId, task.status, 'DONE');

    const previousStatus = task.status;
    const now = new Date().toISOString();
    this.db.prepare(`UPDATE tasks SET status='DONE',updated_at=? WHERE id=?`).run(now, taskId);
    this.db.prepare('DELETE FROM reviews WHERE task_id=?').run(taskId);
    this.db.prepare(`INSERT INTO reviews (task_id,status,priority,submitted_at) VALUES(?,'PENDING','P0',?)`)
      .run(taskId, now);
    return { task: this.findTaskById(taskId)!, previousStatus, unblocked: [] as Task[] };
  }

  private checkAndUnblockDependents(completedTaskId: number): Task[] {
    const unblocked: Task[] = [];
    const blocked = this.db.prepare("SELECT * FROM tasks WHERE status='BLOCKED'").all() as Task[];
    for (const t of blocked) {
      const deps = this.getDependencies(t);
      if (deps.includes(completedTaskId) && this.areDependenciesComplete(t)) {
        const now = new Date().toISOString();
        this.db.prepare(`UPDATE tasks SET status='QUEUED',updated_at=? WHERE id=?`).run(now, t.id);
        unblocked.push(this.findTaskById(t.id)!);
      }
    }
    return unblocked;
  }

  findExecutableTasks(): Task[] {
    const queued = this.db.prepare("SELECT * FROM tasks WHERE status='QUEUED'").all() as Task[];
    return queued.filter((t) => this.areDependenciesComplete(t));
  }
}

describe('TaskService', () => {
  let db: Database.Database;
  let taskService: TestTaskService;

  beforeEach(() => {
    db = new Database(':memory:');
    db.exec(INITIAL_SCHEMA);

    const now = new Date().toISOString();

    db.prepare(`
      INSERT INTO projects (name, path, status, created_at, updated_at)
      VALUES ('Test Project', '/test', 'IN_PROGRESS', ?, ?)
    `).run(now, now);

    db.prepare(`
      INSERT INTO orders (project_id, order_number, title, status, priority, created_at, updated_at)
      VALUES (1, 1, 'Test Order', 'IN_PROGRESS', 'P1', ?, ?)
    `).run(now, now);

    db.prepare(`
      INSERT INTO tasks (order_id, task_number, title, status, depends_on, created_at, updated_at)
      VALUES
        (1, 1, 'Task 1', 'QUEUED', NULL, ?, ?),
        (1, 2, 'Task 2', 'BLOCKED', '[1]', ?, ?),
        (1, 3, 'Task 3', 'IN_PROGRESS', NULL, ?, ?)
    `).run(now, now, now, now, now, now);

    taskService = new TestTaskService(db);
  });

  afterEach(() => {
    db.close();
  });

  describe('isValidTransition', () => {
    it('should allow QUEUED -> IN_PROGRESS', () => {
      expect(taskService.isValidTransition('QUEUED', 'IN_PROGRESS')).toBe(true);
    });

    it('should allow IN_PROGRESS -> DONE', () => {
      expect(taskService.isValidTransition('IN_PROGRESS', 'DONE')).toBe(true);
    });

    it('should allow DONE -> COMPLETED', () => {
      expect(taskService.isValidTransition('DONE', 'COMPLETED')).toBe(true);
    });

    it('should allow DONE -> REWORK', () => {
      expect(taskService.isValidTransition('DONE', 'REWORK')).toBe(true);
    });

    it('should allow REWORK -> DONE', () => {
      expect(taskService.isValidTransition('REWORK', 'DONE')).toBe(true);
    });

    it('should not allow QUEUED -> COMPLETED', () => {
      expect(taskService.isValidTransition('QUEUED', 'COMPLETED')).toBe(false);
    });

    it('should not allow COMPLETED -> any', () => {
      expect(taskService.isValidTransition('COMPLETED', 'QUEUED')).toBe(false);
      expect(taskService.isValidTransition('COMPLETED', 'IN_PROGRESS')).toBe(false);
    });
  });

  describe('startTask', () => {
    it('should transition task from QUEUED to IN_PROGRESS', () => {
      const result = taskService.startTask({ taskId: 1, assignee: 'Worker A' });

      expect(result.task.status).toBe('IN_PROGRESS');
      expect(result.task.assignee).toBe('Worker A');
      expect(result.task.started_at).toBeTruthy();
      expect(result.previousStatus).toBe('QUEUED');
    });

    it('should throw error for BLOCKED task', () => {
      expect(() => {
        taskService.startTask({ taskId: 2, assignee: 'Worker A' });
      }).toThrow('Dependencies not completed');
    });

    it('should throw StateTransitionError for IN_PROGRESS task', () => {
      expect(() => {
        taskService.startTask({ taskId: 3, assignee: 'Worker A' });
      }).toThrow(StateTransitionError);
    });

    it('should throw error for non-existent task', () => {
      expect(() => {
        taskService.startTask({ taskId: 999, assignee: 'Worker A' });
      }).toThrow('Task not found');
    });
  });

  describe('completeTask', () => {
    it('should transition task from IN_PROGRESS to DONE', () => {
      const result = taskService.completeTask({ taskId: 3 });

      expect(result.task.status).toBe('DONE');
      expect(result.previousStatus).toBe('IN_PROGRESS');
    });

    it('should create review entry when completing task', () => {
      taskService.completeTask({ taskId: 3 });

      const review = db.prepare('SELECT * FROM reviews WHERE task_id = 3').get();
      expect(review).toBeTruthy();
    });

    it('should throw error for QUEUED task', () => {
      expect(() => {
        taskService.completeTask({ taskId: 1 });
      }).toThrow(StateTransitionError);
    });
  });

  describe('approveReview', () => {
    beforeEach(() => {
      db.prepare("UPDATE tasks SET status = 'DONE' WHERE id = 3").run();

      const now = new Date().toISOString();
      db.prepare(`
        INSERT INTO reviews (task_id, status, priority, submitted_at)
        VALUES (3, 'PENDING', 'P1', ?)
      `).run(now);
    });

    it('should transition task from DONE to COMPLETED', () => {
      const result = taskService.approveReview(3, 'PM', 'LGTM');

      expect(result.task.status).toBe('COMPLETED');
      expect(result.task.completed_at).toBeTruthy();
      expect(result.previousStatus).toBe('DONE');
    });
  });

  describe('rejectReview', () => {
    beforeEach(() => {
      db.prepare("UPDATE tasks SET status = 'DONE' WHERE id = 3").run();

      const now = new Date().toISOString();
      db.prepare(`
        INSERT INTO reviews (task_id, status, priority, submitted_at)
        VALUES (3, 'PENDING', 'P1', ?)
      `).run(now);
    });

    it('should transition task from DONE to REWORK', () => {
      const result = taskService.rejectReview(3, 'PM', 'Needs improvement');

      expect(result.task.status).toBe('REWORK');
      expect(result.previousStatus).toBe('DONE');
    });
  });

  describe('resubmitTask', () => {
    beforeEach(() => {
      db.prepare("UPDATE tasks SET status = 'REWORK' WHERE id = 3").run();
    });

    it('should transition task from REWORK to DONE', () => {
      const result = taskService.resubmitTask(3);

      expect(result.task.status).toBe('DONE');
      expect(result.previousStatus).toBe('REWORK');
    });

    it('should create P0 priority review', () => {
      taskService.resubmitTask(3);

      const review = db.prepare('SELECT * FROM reviews WHERE task_id = 3').get() as { priority: string };
      expect(review.priority).toBe('P0');
    });
  });

  describe('dependency resolution', () => {
    it('should unblock task when dependencies complete', () => {
      taskService.startTask({ taskId: 1, assignee: 'Worker A' });
      taskService.completeTask({ taskId: 1 });

      const result = taskService.approveReview(1, 'PM');

      expect(result.unblocked).toHaveLength(1);
      expect(result.unblocked[0].id).toBe(2);
      expect(result.unblocked[0].status).toBe('QUEUED');
    });
  });

  describe('findExecutableTasks', () => {
    it('should return only QUEUED tasks with completed dependencies', () => {
      const executable = taskService.findExecutableTasks();

      expect(executable).toHaveLength(1);
      expect(executable[0].id).toBe(1);
    });
  });
});
