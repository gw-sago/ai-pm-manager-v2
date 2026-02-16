/**
 * Progress Service
 *
 * ORDER単位・プロジェクト単位の進捗計算を提供
 * SPEC_status_linkage.md の L-06, L-08 に対応
 */

import type Database from 'better-sqlite3';
import { TaskRepository, type Task } from '../database/repositories/TaskRepository';
import { OrderRepository, type Order } from '../database/repositories/OrderRepository';
import { ReviewRepository } from '../database/repositories/ReviewRepository';
import { ProjectRepository } from '../database/repositories/ProjectRepository';
import type { TaskStatus, OrderStatus, ProjectStatus } from '../database/schema';

/**
 * ORDER単位の進捗情報
 */
export interface OrderProgress {
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

/**
 * プロジェクト単位の進捗情報
 */
export interface ProjectProgress {
  projectId: number;
  name: string;
  status: ProjectStatus;
  orders: OrderProgress[];
  totalTasks: number;
  completedTasks: number;
  inProgressTasks: number;
  reviewPendingTasks: number;
  blockedTasks: number;
  queuedTasks: number;
  reworkTasks: number;
  percentage: number;
  activeOrders: number;
  completedOrders: number;
}

/**
 * タスクステータス別カウント
 */
export interface TaskStatusCounts {
  total: number;
  queued: number;
  blocked: number;
  inProgress: number;
  done: number;
  rework: number;
  completed: number;
}

/**
 * ProgressService
 */
export class ProgressService {
  private taskRepo: TaskRepository;
  private orderRepo: OrderRepository;
  private reviewRepo: ReviewRepository;
  private projectRepo: ProjectRepository;
  private db: Database.Database;

  constructor(db: Database.Database) {
    this.db = db;
    this.taskRepo = new TaskRepository(db);
    this.orderRepo = new OrderRepository(db);
    this.reviewRepo = new ReviewRepository(db);
    this.projectRepo = new ProjectRepository(db);
  }

  /**
   * タスクリストからステータス別カウントを計算
   */
  private countByStatus(tasks: Task[]): TaskStatusCounts {
    const counts: TaskStatusCounts = {
      total: tasks.length,
      queued: 0,
      blocked: 0,
      inProgress: 0,
      done: 0,
      rework: 0,
      completed: 0,
    };

    for (const task of tasks) {
      switch (task.status) {
        case 'QUEUED':
          counts.queued++;
          break;
        case 'BLOCKED':
          counts.blocked++;
          break;
        case 'IN_PROGRESS':
          counts.inProgress++;
          break;
        case 'DONE':
          counts.done++;
          break;
        case 'REWORK':
          counts.rework++;
          break;
        case 'COMPLETED':
          counts.completed++;
          break;
      }
    }

    return counts;
  }

  /**
   * ORDER単位の進捗を計算（L-08: 進捗サマリ自動更新連動）
   */
  calculateOrderProgress(orderId: number): OrderProgress | undefined {
    const order = this.orderRepo.findById(orderId);
    if (!order) {
      return undefined;
    }

    const tasks = this.taskRepo.findByOrderId(orderId);
    const counts = this.countByStatus(tasks);

    const percentage =
      counts.total > 0
        ? Math.round((counts.completed / counts.total) * 100)
        : 0;

    const isComplete =
      counts.total > 0 && counts.completed === counts.total;

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

  /**
   * プロジェクト単位の進捗を計算
   */
  calculateProjectProgress(projectId: number): ProjectProgress | undefined {
    const project = this.projectRepo.findById(projectId);
    if (!project) {
      return undefined;
    }

    const orders = this.orderRepo.findByProjectId(projectId);
    const orderProgressList: OrderProgress[] = [];
    let totalTasks = 0;
    let completedTasks = 0;
    let inProgressTasks = 0;
    let reviewPendingTasks = 0;
    let blockedTasks = 0;
    let queuedTasks = 0;
    let reworkTasks = 0;
    let activeOrders = 0;
    let completedOrders = 0;

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
        reworkTasks += progress.rework;

        if (progress.isComplete || order.status === 'COMPLETED') {
          completedOrders++;
        } else if (order.status !== 'CANCELLED' && order.status !== 'ON_HOLD') {
          activeOrders++;
        }
      }
    }

    const percentage =
      totalTasks > 0
        ? Math.round((completedTasks / totalTasks) * 100)
        : 0;

    return {
      projectId: project.id,
      name: project.name,
      status: project.status,
      orders: orderProgressList,
      totalTasks,
      completedTasks,
      inProgressTasks,
      reviewPendingTasks,
      blockedTasks,
      queuedTasks,
      reworkTasks,
      percentage,
      activeOrders,
      completedOrders,
    };
  }

  /**
   * ORDERの全タスク完了チェック（L-06: 全タスク完了・ORDER完了連動）
   */
  isOrderComplete(orderId: number): boolean {
    const progress = this.calculateOrderProgress(orderId);
    return progress?.isComplete ?? false;
  }

  /**
   * 全タスクが完了した場合にORDERステータスを更新
   */
  checkAndUpdateOrderCompletion(orderId: number): Order | undefined {
    if (this.isOrderComplete(orderId)) {
      return this.orderRepo.updateStatus(orderId, 'COMPLETED');
    }
    return undefined;
  }

  /**
   * プロジェクトの全ORDERが完了しているかチェック
   */
  isProjectComplete(projectId: number): boolean {
    const progress = this.calculateProjectProgress(projectId);
    if (!progress || progress.orders.length === 0) {
      return false;
    }

    return progress.orders.every(
      (order) => order.isComplete || order.status === 'COMPLETED' || order.status === 'CANCELLED'
    );
  }

  /**
   * ORDER単位のタスクステータスサマリを取得
   */
  getOrderTaskSummary(orderId: number): TaskStatusCounts | undefined {
    const order = this.orderRepo.findById(orderId);
    if (!order) {
      return undefined;
    }

    const tasks = this.taskRepo.findByOrderId(orderId);
    return this.countByStatus(tasks);
  }

  /**
   * プロジェクト単位のタスクステータスサマリを取得
   */
  getProjectTaskSummary(projectId: number): TaskStatusCounts | undefined {
    const project = this.projectRepo.findById(projectId);
    if (!project) {
      return undefined;
    }

    const orders = this.orderRepo.findByProjectId(projectId);
    const allTasks: Task[] = [];

    for (const order of orders) {
      const tasks = this.taskRepo.findByOrderId(order.id);
      allTasks.push(...tasks);
    }

    return this.countByStatus(allTasks);
  }

  /**
   * レビュー待ちのタスク数を取得
   */
  getReviewPendingCount(): number {
    return this.reviewRepo.findPending().length;
  }

  /**
   * 実行可能なタスク数を取得
   */
  getExecutableTaskCount(): number {
    return this.taskRepo.findExecutable().length;
  }
}
