/**
 * Task Service
 *
 * タスクの状態遷移ロジックを提供
 * ADR-001に基づき、状態遷移ルールを一元管理
 *
 * 状態遷移図:
 * ┌─────────┐    ┌─────────┐    ┌───────────┐    ┌──────┐
 * │ BLOCKED │───▶│ QUEUED  │───▶│IN_PROGRESS│───▶│ DONE │
 * └─────────┘    └─────────┘    └───────────┘    └──┬───┘
 *      ▲          依存解決        startTask()       │
 *      │                                   ┌───────┴───────┐
 *      │                                   │               │
 *      │                                   ▼               ▼
 *      │                            ┌──────────┐    ┌──────────┐
 *      │                            │ REWORK   │    │COMPLETED │
 *      │                            └────┬─────┘    └──────────┘
 *      │                                 │        approveReview()
 *      │                   resubmitTask()│
 *      └─────────────────────────────────┘
 */

import type Database from 'better-sqlite3';
import { TaskRepository, type Task } from '../database/repositories/TaskRepository';
import { ReviewRepository } from '../database/repositories/ReviewRepository';
import type { TaskStatus, Priority } from '../database/schema';

/**
 * 状態遷移エラー
 */
export class StateTransitionError extends Error {
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

/**
 * 有効な状態遷移のマップ
 */
const VALID_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  QUEUED: ['IN_PROGRESS', 'BLOCKED'],
  BLOCKED: ['QUEUED'],
  IN_PROGRESS: ['DONE', 'BLOCKED'],
  DONE: ['COMPLETED', 'REWORK'],
  REWORK: ['DONE'],
  COMPLETED: [],
};

/**
 * タスク状態遷移の結果
 */
export interface TaskTransitionResult {
  task: Task;
  previousStatus: TaskStatus;
  unblocked: Task[];
}

/**
 * タスク開始の入力
 */
export interface StartTaskInput {
  taskId: number;
  assignee: string;
}

/**
 * タスク完了の入力
 */
export interface CompleteTaskInput {
  taskId: number;
  reviewPriority?: Priority;
}

/**
 * TaskService
 */
export class TaskService {
  private taskRepo: TaskRepository;
  private reviewRepo: ReviewRepository;
  private db: Database.Database;

  constructor(db: Database.Database) {
    this.db = db;
    this.taskRepo = new TaskRepository(db);
    this.reviewRepo = new ReviewRepository(db);
  }

  /**
   * 状態遷移が有効かどうかをチェック
   */
  isValidTransition(from: TaskStatus, to: TaskStatus): boolean {
    return VALID_TRANSITIONS[from]?.includes(to) ?? false;
  }

  /**
   * タスクを開始（QUEUED -> IN_PROGRESS）
   */
  startTask(input: StartTaskInput): TaskTransitionResult {
    return this.db.transaction(() => {
      const task = this.taskRepo.findById(input.taskId);
      if (!task) {
        throw new Error(`Task not found: ${input.taskId}`);
      }

      // 依存関係チェック
      if (!this.taskRepo.areDependenciesComplete(task)) {
        throw new StateTransitionError(
          input.taskId,
          task.status,
          'IN_PROGRESS',
          'Dependencies not completed'
        );
      }

      // 状態遷移チェック
      if (!this.isValidTransition(task.status, 'IN_PROGRESS')) {
        throw new StateTransitionError(input.taskId, task.status, 'IN_PROGRESS');
      }

      const previousStatus = task.status;

      // ステータス更新と担当者割り当て
      const updatedTask = this.taskRepo.update(input.taskId, {
        status: 'IN_PROGRESS',
        assignee: input.assignee,
        started_at: new Date().toISOString(),
      });

      return {
        task: updatedTask!,
        previousStatus,
        unblocked: [],
      };
    })();
  }

  /**
   * タスクを完了（IN_PROGRESS -> DONE）
   * レビューキューにエントリを追加
   */
  completeTask(input: CompleteTaskInput): TaskTransitionResult {
    return this.db.transaction(() => {
      const task = this.taskRepo.findById(input.taskId);
      if (!task) {
        throw new Error(`Task not found: ${input.taskId}`);
      }

      // 状態遷移チェック
      if (!this.isValidTransition(task.status, 'DONE')) {
        throw new StateTransitionError(input.taskId, task.status, 'DONE');
      }

      const previousStatus = task.status;

      // ステータス更新
      const updatedTask = this.taskRepo.update(input.taskId, {
        status: 'DONE',
      });

      // レビューキューに追加
      this.reviewRepo.getOrCreateForTask(
        input.taskId,
        input.reviewPriority ?? 'P1'
      );

      return {
        task: updatedTask!,
        previousStatus,
        unblocked: [],
      };
    })();
  }

  /**
   * レビュー承認（DONE -> COMPLETED）
   * 依存タスクのBLOCKED解除をチェック
   */
  approveReview(taskId: number, reviewer: string, comment?: string): TaskTransitionResult {
    return this.db.transaction(() => {
      const task = this.taskRepo.findById(taskId);
      if (!task) {
        throw new Error(`Task not found: ${taskId}`);
      }

      // 状態遷移チェック
      if (!this.isValidTransition(task.status, 'COMPLETED')) {
        throw new StateTransitionError(taskId, task.status, 'COMPLETED');
      }

      const previousStatus = task.status;

      // タスクステータス更新
      const updatedTask = this.taskRepo.update(taskId, {
        status: 'COMPLETED',
        completed_at: new Date().toISOString(),
      });

      // レビュー承認
      const review = this.reviewRepo.findByTaskId(taskId);
      if (review) {
        this.reviewRepo.approve(review.id, reviewer, comment);
      }

      // 依存タスクのBLOCKED解除
      const unblocked = this.checkAndUnblockDependents(taskId);

      return {
        task: updatedTask!,
        previousStatus,
        unblocked,
      };
    })();
  }

  /**
   * レビュー差し戻し（DONE -> REWORK）
   */
  rejectReview(taskId: number, reviewer: string, comment: string): TaskTransitionResult {
    return this.db.transaction(() => {
      const task = this.taskRepo.findById(taskId);
      if (!task) {
        throw new Error(`Task not found: ${taskId}`);
      }

      // 状態遷移チェック
      if (!this.isValidTransition(task.status, 'REWORK')) {
        throw new StateTransitionError(taskId, task.status, 'REWORK');
      }

      const previousStatus = task.status;

      // タスクステータス更新
      const updatedTask = this.taskRepo.update(taskId, {
        status: 'REWORK',
      });

      // レビュー差し戻し
      const review = this.reviewRepo.findByTaskId(taskId);
      if (review) {
        this.reviewRepo.reject(review.id, reviewer, comment);
      }

      return {
        task: updatedTask!,
        previousStatus,
        unblocked: [],
      };
    })();
  }

  /**
   * タスク再提出（REWORK -> DONE）
   * レビューキューに優先度P0で追加
   */
  resubmitTask(taskId: number): TaskTransitionResult {
    return this.db.transaction(() => {
      const task = this.taskRepo.findById(taskId);
      if (!task) {
        throw new Error(`Task not found: ${taskId}`);
      }

      // 状態遷移チェック
      if (!this.isValidTransition(task.status, 'DONE')) {
        throw new StateTransitionError(taskId, task.status, 'DONE');
      }

      const previousStatus = task.status;

      // ステータス更新
      const updatedTask = this.taskRepo.update(taskId, {
        status: 'DONE',
      });

      // 既存のレビューを削除して新規作成（P0優先度）
      const existingReview = this.reviewRepo.findByTaskId(taskId);
      if (existingReview) {
        this.reviewRepo.delete(existingReview.id);
      }
      this.reviewRepo.create({
        task_id: taskId,
        priority: 'P0', // 差し戻し再提出はP0
      });

      return {
        task: updatedTask!,
        previousStatus,
        unblocked: [],
      };
    })();
  }

  /**
   * 依存タスク完了時に後続タスクのBLOCKED解除をチェック
   */
  private checkAndUnblockDependents(completedTaskId: number): Task[] {
    const unblocked: Task[] = [];
    const blockedTasks = this.taskRepo.findByStatus('BLOCKED');

    for (const task of blockedTasks) {
      const dependencies = this.taskRepo.getDependencies(task);
      if (dependencies.includes(completedTaskId)) {
        // このタスクは完了したタスクに依存している
        // 全ての依存が完了しているかチェック
        if (this.taskRepo.areDependenciesComplete(task)) {
          // BLOCKED -> QUEUED
          const updated = this.taskRepo.update(task.id, { status: 'QUEUED' });
          if (updated) {
            unblocked.push(updated);
          }
        }
      }
    }

    return unblocked;
  }

  /**
   * タスクをブロック状態にする
   */
  blockTask(taskId: number): TaskTransitionResult {
    return this.db.transaction(() => {
      const task = this.taskRepo.findById(taskId);
      if (!task) {
        throw new Error(`Task not found: ${taskId}`);
      }

      // 状態遷移チェック
      if (!this.isValidTransition(task.status, 'BLOCKED')) {
        throw new StateTransitionError(taskId, task.status, 'BLOCKED');
      }

      const previousStatus = task.status;

      const updatedTask = this.taskRepo.update(taskId, {
        status: 'BLOCKED',
      });

      return {
        task: updatedTask!,
        previousStatus,
        unblocked: [],
      };
    })();
  }

  /**
   * 依存タスクを解決してQUEUEDに戻す
   */
  resolveDependencies(taskId: number): TaskTransitionResult {
    return this.db.transaction(() => {
      const task = this.taskRepo.findById(taskId);
      if (!task) {
        throw new Error(`Task not found: ${taskId}`);
      }

      if (task.status !== 'BLOCKED') {
        throw new StateTransitionError(
          taskId,
          task.status,
          'QUEUED',
          'Task is not blocked'
        );
      }

      // 依存関係が解決されているかチェック
      if (!this.taskRepo.areDependenciesComplete(task)) {
        throw new Error('Dependencies not yet completed');
      }

      const previousStatus = task.status;

      const updatedTask = this.taskRepo.update(taskId, {
        status: 'QUEUED',
      });

      return {
        task: updatedTask!,
        previousStatus,
        unblocked: [],
      };
    })();
  }

  /**
   * 実行可能なタスクを取得
   */
  findExecutableTasks(): Task[] {
    return this.taskRepo.findExecutable();
  }

  /**
   * タスクIDでタスクを取得
   */
  getTask(taskId: number): Task | undefined {
    return this.taskRepo.findById(taskId);
  }

  /**
   * ORDERのタスク一覧を取得
   */
  getTasksByOrder(orderId: number): Task[] {
    return this.taskRepo.findByOrderId(orderId);
  }
}
