/**
 * Backlog Repository
 *
 * バックログのCRUD操作を提供
 */

import { BaseRepository, BaseEntity } from './BaseRepository';
import type { BacklogStatus, BacklogPriority } from '../schema';

export interface Backlog extends BaseEntity {
  project_id: number;
  backlog_number: number;
  title: string;
  description: string | null;
  priority: BacklogPriority;
  status: BacklogStatus;
  order_id: number | null;
}

export interface CreateBacklogInput {
  project_id: number;
  backlog_number: number;
  title: string;
  description?: string;
  priority?: BacklogPriority;
  status?: BacklogStatus;
}

export interface UpdateBacklogInput {
  title?: string;
  description?: string | null;
  priority?: BacklogPriority;
  status?: BacklogStatus;
  order_id?: number | null;
}

export class BacklogRepository extends BaseRepository<Backlog> {
  protected tableName = 'backlogs';

  /**
   * バックログを作成
   */
  create(input: CreateBacklogInput): Backlog {
    const now = this.now();
    const result = this.db
      .prepare(
        `INSERT INTO backlogs (project_id, backlog_number, title, description, priority, status, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run(
        input.project_id,
        input.backlog_number,
        input.title,
        input.description ?? null,
        input.priority ?? 'Medium',
        input.status ?? 'TODO',
        now,
        now
      );

    return this.findById(result.lastInsertRowid as number)!;
  }

  /**
   * バックログを更新
   */
  update(id: number, input: UpdateBacklogInput): Backlog | undefined {
    const backlog = this.findById(id);
    if (!backlog) {
      return undefined;
    }

    const updates: string[] = [];
    const values: unknown[] = [];

    if (input.title !== undefined) {
      updates.push('title = ?');
      values.push(input.title);
    }
    if (input.description !== undefined) {
      updates.push('description = ?');
      values.push(input.description);
    }
    if (input.priority !== undefined) {
      updates.push('priority = ?');
      values.push(input.priority);
    }
    if (input.status !== undefined) {
      updates.push('status = ?');
      values.push(input.status);
    }
    if (input.order_id !== undefined) {
      updates.push('order_id = ?');
      values.push(input.order_id);
    }

    if (updates.length === 0) {
      return backlog;
    }

    updates.push('updated_at = ?');
    values.push(this.now());
    values.push(id);

    this.db
      .prepare(`UPDATE backlogs SET ${updates.join(', ')} WHERE id = ?`)
      .run(...values);

    return this.findById(id);
  }

  /**
   * プロジェクトIDでバックログを検索
   */
  findByProjectId(projectId: number): Backlog[] {
    return this.db
      .prepare(
        `SELECT * FROM backlogs
         WHERE project_id = ?
         ORDER BY
           CASE priority
             WHEN 'High' THEN 1
             WHEN 'Medium' THEN 2
             WHEN 'Low' THEN 3
           END,
           backlog_number`
      )
      .all(projectId) as Backlog[];
  }

  /**
   * プロジェクトIDとバックログ番号でバックログを検索
   */
  findByProjectAndNumber(projectId: number, backlogNumber: number): Backlog | undefined {
    return this.db
      .prepare(
        `SELECT * FROM backlogs
         WHERE project_id = ? AND backlog_number = ?`
      )
      .get(projectId, backlogNumber) as Backlog | undefined;
  }

  /**
   * ステータスでバックログを検索
   */
  findByStatus(status: BacklogStatus): Backlog[] {
    return this.findBy({ status } as Partial<Backlog>);
  }

  /**
   * 優先度でバックログを検索
   */
  findByPriority(priority: BacklogPriority): Backlog[] {
    return this.findBy({ priority } as Partial<Backlog>);
  }

  /**
   * TODO状態のバックログを取得（優先度順）
   */
  findTodo(): Backlog[] {
    return this.findByStatus('TODO');
  }

  /**
   * バックログをORDERに紐付け
   */
  linkToOrder(id: number, orderId: number): Backlog | undefined {
    return this.update(id, { order_id: orderId, status: 'IN_ORDER' });
  }

  /**
   * バックログを完了にする
   */
  complete(id: number): Backlog | undefined {
    return this.update(id, { status: 'DONE' });
  }

  /**
   * プロジェクトの次のバックログ番号を取得
   */
  getNextBacklogNumber(projectId: number): number {
    const result = this.db
      .prepare(
        `SELECT MAX(backlog_number) as max_number
         FROM backlogs
         WHERE project_id = ?`
      )
      .get(projectId) as { max_number: number | null };
    return (result.max_number ?? 0) + 1;
  }

  /**
   * ORDERに紐付いたバックログを取得
   */
  findByOrderId(orderId: number): Backlog[] {
    return this.db
      .prepare(
        `SELECT * FROM backlogs
         WHERE order_id = ?
         ORDER BY backlog_number`
      )
      .all(orderId) as Backlog[];
  }
}
