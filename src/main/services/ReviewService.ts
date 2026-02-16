/**
 * Review Service
 *
 * レビューキューの管理ロジックを提供
 * SPEC_status_linkage.md の L-02, L-03, L-04 に対応
 *
 * レビューキュー状態遷移:
 * PENDING -> IN_REVIEW -> APPROVED
 *                    └-> REJECTED
 */

import type Database from 'better-sqlite3';
import { ReviewRepository, type Review } from '../database/repositories/ReviewRepository';
import { TaskRepository, type Task } from '../database/repositories/TaskRepository';
import type { ReviewStatus, Priority } from '../database/schema';

/**
 * レビュー状態遷移エラー
 */
export class ReviewTransitionError extends Error {
  constructor(
    public readonly reviewId: number,
    public readonly currentStatus: ReviewStatus,
    public readonly targetStatus: ReviewStatus,
    message?: string
  ) {
    super(message ?? `Invalid review transition: ${currentStatus} -> ${targetStatus}`);
    this.name = 'ReviewTransitionError';
  }
}

/**
 * レビューキューの統計情報
 */
export interface ReviewQueueStats {
  totalPending: number;
  totalInReview: number;
  totalApproved: number;
  totalRejected: number;
  byPriority: {
    P0: number;
    P1: number;
    P2: number;
    P3: number;
  };
}

/**
 * レビューエントリ（タスク情報付き）
 */
export interface ReviewWithTask extends Review {
  task?: Task;
}

/**
 * ReviewService
 */
export class ReviewService {
  private reviewRepo: ReviewRepository;
  private taskRepo: TaskRepository;
  private db: Database.Database;

  constructor(db: Database.Database) {
    this.db = db;
    this.reviewRepo = new ReviewRepository(db);
    this.taskRepo = new TaskRepository(db);
  }

  /**
   * レビューキューにタスクを追加（L-02: タスク完了・レビューキュー追加連動）
   */
  addToQueue(taskId: number, priority: Priority = 'P1'): Review {
    return this.db.transaction(() => {
      // 既存のレビューがあれば削除
      const existing = this.reviewRepo.findByTaskId(taskId);
      if (existing) {
        this.reviewRepo.delete(existing.id);
      }

      // 新規レビューエントリ作成
      return this.reviewRepo.create({
        task_id: taskId,
        priority,
      });
    })();
  }

  /**
   * レビューを開始
   */
  startReview(reviewId: number, reviewer: string): Review {
    return this.db.transaction(() => {
      const review = this.reviewRepo.findById(reviewId);
      if (!review) {
        throw new Error(`Review not found: ${reviewId}`);
      }

      if (review.status !== 'PENDING') {
        throw new ReviewTransitionError(
          reviewId,
          review.status,
          'IN_REVIEW',
          'Review is not pending'
        );
      }

      const updated = this.reviewRepo.startReview(reviewId, reviewer);
      if (!updated) {
        throw new Error('Failed to start review');
      }

      return updated;
    })();
  }

  /**
   * レビューを承認（L-03: レビュー承認連動）
   * 注: タスクステータス更新はTaskServiceで行う
   */
  approve(reviewId: number, reviewer: string, comment?: string): Review {
    return this.db.transaction(() => {
      const review = this.reviewRepo.findById(reviewId);
      if (!review) {
        throw new Error(`Review not found: ${reviewId}`);
      }

      if (review.status !== 'PENDING' && review.status !== 'IN_REVIEW') {
        throw new ReviewTransitionError(
          reviewId,
          review.status,
          'APPROVED',
          'Review is not in a reviewable state'
        );
      }

      const updated = this.reviewRepo.approve(reviewId, reviewer, comment);
      if (!updated) {
        throw new Error('Failed to approve review');
      }

      return updated;
    })();
  }

  /**
   * レビューを差し戻し（L-04: レビュー差戻連動）
   */
  reject(reviewId: number, reviewer: string, comment: string): Review {
    return this.db.transaction(() => {
      const review = this.reviewRepo.findById(reviewId);
      if (!review) {
        throw new Error(`Review not found: ${reviewId}`);
      }

      if (review.status !== 'PENDING' && review.status !== 'IN_REVIEW') {
        throw new ReviewTransitionError(
          reviewId,
          review.status,
          'REJECTED',
          'Review is not in a reviewable state'
        );
      }

      const updated = this.reviewRepo.reject(reviewId, reviewer, comment);
      if (!updated) {
        throw new Error('Failed to reject review');
      }

      return updated;
    })();
  }

  /**
   * 保留中のレビュー一覧を取得（優先度順）
   */
  getPendingReviews(): ReviewWithTask[] {
    const reviews = this.reviewRepo.findPending();
    return reviews.map((review) => ({
      ...review,
      task: this.taskRepo.findById(review.task_id),
    }));
  }

  /**
   * 差し戻しされたレビュー一覧を取得
   */
  getRejectedReviews(): ReviewWithTask[] {
    const reviews = this.reviewRepo.findRejected();
    return reviews.map((review) => ({
      ...review,
      task: this.taskRepo.findById(review.task_id),
    }));
  }

  /**
   * タスクのレビューを取得
   */
  getReviewByTask(taskId: number): Review | undefined {
    return this.reviewRepo.findByTaskId(taskId);
  }

  /**
   * レビューキューの統計を取得
   */
  getQueueStats(): ReviewQueueStats {
    const all = this.reviewRepo.findAll();

    const stats: ReviewQueueStats = {
      totalPending: 0,
      totalInReview: 0,
      totalApproved: 0,
      totalRejected: 0,
      byPriority: { P0: 0, P1: 0, P2: 0, P3: 0 },
    };

    for (const review of all) {
      switch (review.status) {
        case 'PENDING':
          stats.totalPending++;
          break;
        case 'IN_REVIEW':
          stats.totalInReview++;
          break;
        case 'APPROVED':
          stats.totalApproved++;
          break;
        case 'REJECTED':
          stats.totalRejected++;
          break;
      }

      // 保留中・レビュー中のみ優先度カウント
      if (review.status === 'PENDING' || review.status === 'IN_REVIEW') {
        stats.byPriority[review.priority]++;
      }
    }

    return stats;
  }

  /**
   * レビューIDでレビューを取得
   */
  getReview(reviewId: number): Review | undefined {
    return this.reviewRepo.findById(reviewId);
  }

  /**
   * レビューを削除（承認済みレビューのクリーンアップ用）
   */
  removeFromQueue(taskId: number): boolean {
    const review = this.reviewRepo.findByTaskId(taskId);
    if (review) {
      this.reviewRepo.delete(review.id);
      return true;
    }
    return false;
  }

  /**
   * 優先度でレビューを更新
   */
  updatePriority(reviewId: number, priority: Priority): Review | undefined {
    return this.reviewRepo.update(reviewId, { priority });
  }
}
