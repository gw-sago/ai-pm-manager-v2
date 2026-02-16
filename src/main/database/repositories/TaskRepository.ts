/**
 * Task Repository
 *
 * タスクのCRUD操作を提供
 */

import { BaseRepository, BaseEntity } from './BaseRepository';
import type { TaskStatus } from '../schema';

export interface Task extends BaseEntity {
  order_id: number;
  task_number: number;
  title: string;
  status: TaskStatus;
  assignee: string | null;
  depends_on: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface CreateTaskInput {
  order_id: number;
  task_number: number;
  title: string;
  status?: TaskStatus;
  assignee?: string;
  depends_on?: number[];
}

export interface UpdateTaskInput {
  title?: string;
  status?: TaskStatus;
  assignee?: string | null;
  depends_on?: number[];
  started_at?: string | null;
  completed_at?: string | null;
}

export class TaskRepository extends BaseRepository<Task> {
  protected tableName = 'tasks';

  /**
   * タスクを作成
   */
  create(input: CreateTaskInput): Task {
    const now = this.now();
    const dependsOn = input.depends_on
      ? JSON.stringify(input.depends_on)
      : null;

    const result = this.db
      .prepare(
        `INSERT INTO tasks (order_id, task_number, title, status, assignee, depends_on, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run(
        input.order_id,
        input.task_number,
        input.title,
        input.status ?? 'QUEUED',
        input.assignee ?? null,
        dependsOn,
        now,
        now
      );

    return this.findById(result.lastInsertRowid as number)!;
  }

  /**
   * タスクを更新
   */
  update(id: number, input: UpdateTaskInput): Task | undefined {
    const task = this.findById(id);
    if (!task) {
      return undefined;
    }

    const updates: string[] = [];
    const values: unknown[] = [];

    if (input.title !== undefined) {
      updates.push('title = ?');
      values.push(input.title);
    }
    if (input.status !== undefined) {
      updates.push('status = ?');
      values.push(input.status);
    }
    if (input.assignee !== undefined) {
      updates.push('assignee = ?');
      values.push(input.assignee);
    }
    if (input.depends_on !== undefined) {
      updates.push('depends_on = ?');
      values.push(JSON.stringify(input.depends_on));
    }
    if (input.started_at !== undefined) {
      updates.push('started_at = ?');
      values.push(input.started_at);
    }
    if (input.completed_at !== undefined) {
      updates.push('completed_at = ?');
      values.push(input.completed_at);
    }

    if (updates.length === 0) {
      return task;
    }

    updates.push('updated_at = ?');
    values.push(this.now());
    values.push(id);

    this.db
      .prepare(`UPDATE tasks SET ${updates.join(', ')} WHERE id = ?`)
      .run(...values);

    return this.findById(id);
  }

  /**
   * ORDER IDでタスクを検索
   */
  findByOrderId(orderId: number): Task[] {
    return this.db
      .prepare(
        `SELECT * FROM tasks
         WHERE order_id = ?
         ORDER BY task_number`
      )
      .all(orderId) as Task[];
  }

  /**
   * ORDER IDとタスク番号でタスクを検索
   */
  findByOrderAndNumber(orderId: number, taskNumber: number): Task | undefined {
    return this.db
      .prepare(
        `SELECT * FROM tasks
         WHERE order_id = ? AND task_number = ?`
      )
      .get(orderId, taskNumber) as Task | undefined;
  }

  /**
   * ステータスでタスクを検索
   */
  findByStatus(status: TaskStatus): Task[] {
    return this.findBy({ status } as Partial<Task>);
  }

  /**
   * 担当者でタスクを検索
   */
  findByAssignee(assignee: string): Task[] {
    return this.db
      .prepare(
        `SELECT * FROM tasks
         WHERE assignee = ?
         ORDER BY order_id, task_number`
      )
      .all(assignee) as Task[];
  }

  /**
   * タスクのステータスを更新
   */
  updateStatus(id: number, status: TaskStatus): Task | undefined {
    const updates: UpdateTaskInput = { status };

    // ステータスに応じて日時を設定
    if (status === 'IN_PROGRESS') {
      updates.started_at = this.now();
    } else if (status === 'COMPLETED') {
      updates.completed_at = this.now();
    }

    return this.update(id, updates);
  }

  /**
   * 担当者を割り当て
   */
  assignTo(id: number, assignee: string): Task | undefined {
    return this.update(id, { assignee });
  }

  /**
   * 依存タスクIDを取得
   */
  getDependencies(task: Task): number[] {
    if (!task.depends_on) {
      return [];
    }
    try {
      return JSON.parse(task.depends_on) as number[];
    } catch {
      return [];
    }
  }

  /**
   * 依存タスクがすべて完了しているかチェック
   */
  areDependenciesComplete(task: Task): boolean {
    const dependencies = this.getDependencies(task);
    if (dependencies.length === 0) {
      return true;
    }

    for (const depId of dependencies) {
      const depTask = this.findById(depId);
      if (!depTask || depTask.status !== 'COMPLETED') {
        return false;
      }
    }
    return true;
  }

  /**
   * ORDERの次のタスク番号を取得
   */
  getNextTaskNumber(orderId: number): number {
    const result = this.db
      .prepare(
        `SELECT MAX(task_number) as max_number
         FROM tasks
         WHERE order_id = ?`
      )
      .get(orderId) as { max_number: number | null };
    return (result.max_number ?? 0) + 1;
  }

  /**
   * 実行可能なタスクを取得（依存タスクが完了しているQUEUEDタスク）
   */
  findExecutable(): Task[] {
    const queuedTasks = this.findByStatus('QUEUED');
    return queuedTasks.filter((task) => this.areDependenciesComplete(task));
  }
}
