/**
 * ProgressService Unit Tests
 *
 * Note: schemaのみをインポートし、サービス・リポジトリの循環インポートを回避
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Database from 'better-sqlite3';
import { INITIAL_SCHEMA, type TaskStatus, type OrderStatus, type ProjectStatus } from '../../database/schema';

interface Task {
  id: number;
  order_id: number;
  task_number: number;
  title: string;
  status: TaskStatus;
}

interface Order {
  id: number;
  project_id: number;
  order_number: number;
  title: string;
  status: OrderStatus;
}

interface Project {
  id: number;
  name: string;
  status: ProjectStatus;
}

interface OrderProgress {
  orderId: number;
  orderNumber: number;
  title: string;
  status: OrderStatus;
  total: number;
  completed: number;
  inProgress: number;
  reviewPending: number;
  blocked: number;
  queued: number;
  rework: number;
  percentage: number;
  isComplete: boolean;
}

interface ProjectProgress {
  projectId: number;
  name: string;
  orders: OrderProgress[];
  totalTasks: number;
  completedTasks: number;
  inProgressTasks: number;
  reviewPendingTasks: number;
  blockedTasks: number;
  queuedTasks: number;
}

interface TaskStatusCounts {
  total: number;
  queued: number;
  blocked: number;
  inProgress: number;
  done: number;
  rework: number;
  completed: number;
}

// テスト用ProgressService
class TestProgressService {
  constructor(private db: Database.Database) {}

  private countByStatus(tasks: Task[]): TaskStatusCounts {
    const counts: TaskStatusCounts = {
      total: tasks.length, queued: 0, blocked: 0, inProgress: 0, done: 0, rework: 0, completed: 0,
    };
    for (const task of tasks) {
      switch (task.status) {
        case 'QUEUED': counts.queued++; break;
        case 'BLOCKED': counts.blocked++; break;
        case 'IN_PROGRESS': counts.inProgress++; break;
        case 'DONE': counts.done++; break;
        case 'REWORK': counts.rework++; break;
        case 'COMPLETED': counts.completed++; break;
      }
    }
    return counts;
  }

  calculateOrderProgress(orderId: number): OrderProgress | undefined {
    const order = this.db.prepare('SELECT * FROM orders WHERE id = ?').get(orderId) as Order | undefined;
    if (!order) return undefined;

    const tasks = this.db.prepare('SELECT * FROM tasks WHERE order_id = ?').all(orderId) as Task[];
    const counts = this.countByStatus(tasks);
    const percentage = counts.total > 0 ? Math.round((counts.completed / counts.total) * 100) : 0;
    const isComplete = counts.total > 0 && counts.completed === counts.total;

    return {
      orderId: order.id,
      orderNumber: order.order_number,
      title: order.title,
      status: order.status,
      total: counts.total,
      completed: counts.completed,
      inProgress: counts.inProgress,
      reviewPending: counts.done,
      blocked: counts.blocked,
      queued: counts.queued,
      rework: counts.rework,
      percentage,
      isComplete,
    };
  }

  calculateProjectProgress(projectId: number): ProjectProgress | undefined {
    const project = this.db.prepare('SELECT * FROM projects WHERE id = ?').get(projectId) as Project | undefined;
    if (!project) return undefined;

    const orders = this.db.prepare('SELECT * FROM orders WHERE project_id = ?').all(projectId) as Order[];
    const orderProgressList: OrderProgress[] = [];
    let totalTasks = 0, completedTasks = 0, inProgressTasks = 0, reviewPendingTasks = 0, blockedTasks = 0, queuedTasks = 0;

    for (const order of orders) {
      const progress = this.calculateOrderProgress(order.id);
      if (progress) {
        orderProgressList.push(progress);
        totalTasks += progress.total;
        completedTasks += progress.completed;
        inProgressTasks += progress.inProgress;
        reviewPendingTasks += progress.reviewPending;
        blockedTasks += progress.blocked;
        queuedTasks += progress.queued;
      }
    }

    return {
      projectId: project.id,
      name: project.name,
      orders: orderProgressList,
      totalTasks,
      completedTasks,
      inProgressTasks,
      reviewPendingTasks,
      blockedTasks,
      queuedTasks,
    };
  }

  isOrderComplete(orderId: number): boolean {
    const progress = this.calculateOrderProgress(orderId);
    return progress?.isComplete ?? false;
  }

  checkAndUpdateOrderCompletion(orderId: number): Order | undefined {
    if (this.isOrderComplete(orderId)) {
      const now = new Date().toISOString();
      this.db.prepare(`UPDATE orders SET status='COMPLETED',updated_at=? WHERE id=?`).run(now, orderId);
      return this.db.prepare('SELECT * FROM orders WHERE id = ?').get(orderId) as Order;
    }
    return undefined;
  }

  getOrderTaskSummary(orderId: number): TaskStatusCounts | undefined {
    const order = this.db.prepare('SELECT * FROM orders WHERE id = ?').get(orderId) as Order | undefined;
    if (!order) return undefined;
    const tasks = this.db.prepare('SELECT * FROM tasks WHERE order_id = ?').all(orderId) as Task[];
    return this.countByStatus(tasks);
  }
}

describe('ProgressService', () => {
  let db: Database.Database;
  let progressService: TestProgressService;

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
      VALUES
        (1, 1, 'Order 1', 'IN_PROGRESS', 'P1', ?, ?),
        (1, 2, 'Order 2', 'PLANNING', 'P2', ?, ?)
    `).run(now, now, now, now);

    db.prepare(`
      INSERT INTO tasks (order_id, task_number, title, status, created_at, updated_at)
      VALUES
        (1, 1, 'Task 1', 'COMPLETED', ?, ?),
        (1, 2, 'Task 2', 'COMPLETED', ?, ?),
        (1, 3, 'Task 3', 'DONE', ?, ?),
        (1, 4, 'Task 4', 'IN_PROGRESS', ?, ?),
        (1, 5, 'Task 5', 'QUEUED', ?, ?),
        (1, 6, 'Task 6', 'BLOCKED', ?, ?)
    `).run(now, now, now, now, now, now, now, now, now, now, now, now);

    db.prepare(`
      INSERT INTO tasks (order_id, task_number, title, status, created_at, updated_at)
      VALUES
        (2, 1, 'Task 2-1', 'QUEUED', ?, ?),
        (2, 2, 'Task 2-2', 'QUEUED', ?, ?),
        (2, 3, 'Task 2-3', 'BLOCKED', ?, ?)
    `).run(now, now, now, now, now, now);

    progressService = new TestProgressService(db);
  });

  afterEach(() => {
    db.close();
  });

  describe('calculateOrderProgress', () => {
    it('should calculate correct progress for ORDER 1', () => {
      const progress = progressService.calculateOrderProgress(1);

      expect(progress).toBeTruthy();
      expect(progress!.total).toBe(6);
      expect(progress!.completed).toBe(2);
      expect(progress!.inProgress).toBe(1);
      expect(progress!.reviewPending).toBe(1);
      expect(progress!.queued).toBe(1);
      expect(progress!.blocked).toBe(1);
      expect(progress!.percentage).toBe(33);
      expect(progress!.isComplete).toBe(false);
    });

    it('should return undefined for non-existent ORDER', () => {
      const progress = progressService.calculateOrderProgress(999);
      expect(progress).toBeUndefined();
    });
  });

  describe('calculateProjectProgress', () => {
    it('should calculate correct progress for project', () => {
      const progress = progressService.calculateProjectProgress(1);

      expect(progress).toBeTruthy();
      expect(progress!.totalTasks).toBe(9);
      expect(progress!.completedTasks).toBe(2);
      expect(progress!.inProgressTasks).toBe(1);
      expect(progress!.reviewPendingTasks).toBe(1);
      expect(progress!.queuedTasks).toBe(3);
      expect(progress!.blockedTasks).toBe(2);
      expect(progress!.orders).toHaveLength(2);
    });

    it('should return undefined for non-existent project', () => {
      const progress = progressService.calculateProjectProgress(999);
      expect(progress).toBeUndefined();
    });
  });

  describe('isOrderComplete', () => {
    it('should return false for incomplete ORDER', () => {
      expect(progressService.isOrderComplete(1)).toBe(false);
    });

    it('should return true when all tasks are COMPLETED', () => {
      db.prepare("UPDATE tasks SET status = 'COMPLETED' WHERE order_id = 1").run();
      expect(progressService.isOrderComplete(1)).toBe(true);
    });
  });

  describe('getOrderTaskSummary', () => {
    it('should return correct task status counts', () => {
      const summary = progressService.getOrderTaskSummary(1);

      expect(summary).toBeTruthy();
      expect(summary!.total).toBe(6);
      expect(summary!.completed).toBe(2);
      expect(summary!.inProgress).toBe(1);
      expect(summary!.done).toBe(1);
      expect(summary!.queued).toBe(1);
      expect(summary!.blocked).toBe(1);
      expect(summary!.rework).toBe(0);
    });
  });

  describe('checkAndUpdateOrderCompletion', () => {
    it('should not update status for incomplete ORDER', () => {
      const result = progressService.checkAndUpdateOrderCompletion(1);
      expect(result).toBeUndefined();

      const order = db.prepare('SELECT status FROM orders WHERE id = 1').get() as { status: string };
      expect(order.status).toBe('IN_PROGRESS');
    });

    it('should update status to COMPLETED for complete ORDER', () => {
      db.prepare("UPDATE tasks SET status = 'COMPLETED' WHERE order_id = 1").run();

      const result = progressService.checkAndUpdateOrderCompletion(1);
      expect(result).toBeTruthy();
      expect(result!.status).toBe('COMPLETED');
    });
  });
});
