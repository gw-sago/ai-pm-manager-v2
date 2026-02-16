/**
 * Review Repository
 *
 * レビューキューのCRUD操作を提供
 */

import { BaseRepository, BaseEntity } from './BaseRepository';
import type { ReviewStatus, Priority } from '../schema';

export interface Review extends BaseEntity {
  task_id: number;
  status: ReviewStatus;
  priority: Priority;
  reviewer: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  comment: string | null;
}

export interface CreateReviewInput {
  task_id: number;
  status?: ReviewStatus;
  priority?: Priority;
}

export interface UpdateReviewInput {
  status?: ReviewStatus;
  priority?: Priority;
  reviewer?: string | null;
  reviewed_at?: string | null;
  comment?: string | null;
}

export class ReviewRepository extends BaseRepository<Review> {
  protected tableName = 'reviews';

  /**
   * レビューを作成
   */
  create(input: CreateReviewInput): Review {
    const now = this.now();
    const result = this.db
      .prepare(
        `INSERT INTO reviews (task_id, status, priority, submitted_at, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?)`
      )
      .run(
        input.task_id,
        input.status ?? 'PENDING',
        input.priority ?? 'P1',
        now,
        now,
        now
      );

    return this.findById(result.lastInsertRowid as number)!;
  }

  /**
   * レビューを更新
   */
  update(id: number, input: UpdateReviewInput): Review | undefined {
    const review = this.findById(id);
    if (!review) {
      return undefined;
    }

    const updates: string[] = [];
    const values: unknown[] = [];

    if (input.status !== undefined) {
      updates.push('status = ?');
      values.push(input.status);
    }
    if (input.priority !== undefined) {
      updates.push('priority = ?');
      values.push(input.priority);
    }
    if (input.reviewer !== undefined) {
      updates.push('reviewer = ?');
      values.push(input.reviewer);
    }
    if (input.reviewed_at !== undefined) {
      updates.push('reviewed_at = ?');
      values.push(input.reviewed_at);
    }
    if (input.comment !== undefined) {
      updates.push('comment = ?');
      values.push(input.comment);
    }

    if (updates.length === 0) {
      return review;
    }

    updates.push('updated_at = ?');
    values.push(this.now());
    values.push(id);

    this.db
      .prepare(`UPDATE reviews SET ${updates.join(', ')} WHERE id = ?`)
      .run(...values);

    return this.findById(id);
  }

  /**
   * タスクIDでレビューを検索
   */
  findByTaskId(taskId: number): Review | undefined {
    return this.findOneBy({ task_id: taskId } as Partial<Review>);
  }

  /**
   * ステータスでレビューを検索
   */
  findByStatus(status: ReviewStatus): Review[] {
    return this.db
      .prepare(
        `SELECT * FROM reviews
         WHERE status = ?
         ORDER BY priority, submitted_at`
      )
      .all(status) as Review[];
  }

  /**
   * レビュアーでレビューを検索
   */
  findByReviewer(reviewer: string): Review[] {
    return this.db
      .prepare(
        `SELECT * FROM reviews
         WHERE reviewer = ?
         ORDER BY priority, submitted_at`
      )
      .all(reviewer) as Review[];
  }

  /**
   * 保留中のレビューを取得（優先度順）
   */
  findPending(): Review[] {
    return this.findByStatus('PENDING');
  }

  /**
   * レビューを承認
   */
  approve(id: number, reviewer: string, comment?: string): Review | undefined {
    return this.update(id, {
      status: 'APPROVED',
      reviewer,
      reviewed_at: this.now(),
      comment: comment ?? null,
    });
  }

  /**
   * レビューを差し戻し
   */
  reject(id: number, reviewer: string, comment: string): Review | undefined {
    return this.update(id, {
      status: 'REJECTED',
      reviewer,
      reviewed_at: this.now(),
      comment,
    });
  }

  /**
   * レビューを開始
   */
  startReview(id: number, reviewer: string): Review | undefined {
    return this.update(id, {
      status: 'IN_REVIEW',
      reviewer,
    });
  }

  /**
   * タスクに対するレビューを作成または取得
   */
  getOrCreateForTask(taskId: number, priority?: Priority): Review {
    const existing = this.findByTaskId(taskId);
    if (existing) {
      return existing;
    }
    return this.create({ task_id: taskId, priority });
  }

  /**
   * 差し戻しされたレビューを取得
   */
  findRejected(): Review[] {
    return this.findByStatus('REJECTED');
  }
}
