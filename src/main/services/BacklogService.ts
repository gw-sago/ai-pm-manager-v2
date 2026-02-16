/**
 * Backlog Service
 *
 * バックログとORDER/タスク完了の連動ロジックを提供
 * SPEC_status_linkage.md の L-10, L-14, L-15, L-16 に対応
 */

import type Database from 'better-sqlite3';
import { BacklogRepository, type Backlog } from '../database/repositories/BacklogRepository';
import { OrderRepository, type Order } from '../database/repositories/OrderRepository';
import type { BacklogStatus, BacklogPriority } from '../database/schema';

/**
 * バックログ統計情報
 */
export interface BacklogStats {
  total: number;
  todo: number;
  inOrder: number;
  done: number;
  byPriority: {
    High: number;
    Medium: number;
    Low: number;
  };
}

/**
 * バックログ作成の入力
 */
export interface CreateBacklogInput {
  projectId: number;
  title: string;
  description?: string;
  priority?: BacklogPriority;
}

/**
 * バックログ更新の入力
 */
export interface UpdateBacklogInput {
  title?: string;
  description?: string;
  priority?: BacklogPriority;
}

/**
 * BacklogService
 */
export class BacklogService {
  private backlogRepo: BacklogRepository;
  private orderRepo: OrderRepository;
  private db: Database.Database;

  constructor(db: Database.Database) {
    this.db = db;
    this.backlogRepo = new BacklogRepository(db);
    this.orderRepo = new OrderRepository(db);
  }

  /**
   * バックログを作成（L-15: BACKLOG ID自動採番連動）
   */
  create(input: CreateBacklogInput): Backlog {
    return this.db.transaction(() => {
      const nextNumber = this.backlogRepo.getNextBacklogNumber(input.projectId);

      return this.backlogRepo.create({
        project_id: input.projectId,
        backlog_number: nextNumber,
        title: input.title,
        description: input.description,
        priority: input.priority ?? 'Medium',
      });
    })();
  }

  /**
   * バックログを更新
   */
  update(backlogId: number, input: UpdateBacklogInput): Backlog | undefined {
    return this.backlogRepo.update(backlogId, input);
  }

  /**
   * バックログをORDERに紐付け（L-14: BACKLOG ORDER化連動）
   */
  linkToOrder(backlogId: number, orderId: number): Backlog | undefined {
    return this.db.transaction(() => {
      const backlog = this.backlogRepo.findById(backlogId);
      if (!backlog) {
        throw new Error(`Backlog not found: ${backlogId}`);
      }

      const order = this.orderRepo.findById(orderId);
      if (!order) {
        throw new Error(`Order not found: ${orderId}`);
      }

      // ステータスをIN_ORDERに更新し、ORDER IDを設定
      return this.backlogRepo.linkToOrder(backlogId, orderId);
    })();
  }

  /**
   * ORDER完了時に関連バックログをDONEに更新（L-10: リリース承認・BACKLOG完了連動）
   */
  markDoneByOrder(orderId: number): Backlog[] {
    return this.db.transaction(() => {
      const relatedBacklogs = this.backlogRepo.findByOrderId(orderId);
      const updated: Backlog[] = [];

      for (const backlog of relatedBacklogs) {
        if (backlog.status !== 'DONE') {
          const result = this.backlogRepo.complete(backlog.id);
          if (result) {
            updated.push(result);
          }
        }
      }

      return updated;
    })();
  }

  /**
   * バックログを完了にする
   */
  complete(backlogId: number): Backlog | undefined {
    return this.backlogRepo.complete(backlogId);
  }

  /**
   * プロジェクトのバックログ一覧を取得
   */
  getBacklogsByProject(projectId: number): Backlog[] {
    return this.backlogRepo.findByProjectId(projectId);
  }

  /**
   * TODO状態のバックログを取得（優先度順）
   */
  getTodoBacklogs(projectId: number): Backlog[] {
    const all = this.backlogRepo.findByProjectId(projectId);
    return all.filter((b) => b.status === 'TODO');
  }

  /**
   * ORDERに紐付いたバックログを取得
   */
  getBacklogsByOrder(orderId: number): Backlog[] {
    return this.backlogRepo.findByOrderId(orderId);
  }

  /**
   * バックログ統計を計算（L-16: BACKLOG統計自動更新連動）
   */
  calculateStats(projectId: number): BacklogStats {
    const backlogs = this.backlogRepo.findByProjectId(projectId);

    const stats: BacklogStats = {
      total: backlogs.length,
      todo: 0,
      inOrder: 0,
      done: 0,
      byPriority: { High: 0, Medium: 0, Low: 0 },
    };

    for (const backlog of backlogs) {
      // ステータス別カウント
      switch (backlog.status) {
        case 'TODO':
          stats.todo++;
          break;
        case 'IN_ORDER':
          stats.inOrder++;
          break;
        case 'DONE':
          stats.done++;
          break;
      }

      // 優先度別カウント（TODO/IN_ORDERのみ）
      if (backlog.status !== 'DONE') {
        stats.byPriority[backlog.priority]++;
      }
    }

    return stats;
  }

  /**
   * バックログIDでバックログを取得
   */
  getBacklog(backlogId: number): Backlog | undefined {
    return this.backlogRepo.findById(backlogId);
  }

  /**
   * プロジェクトIDとバックログ番号でバックログを取得
   */
  getBacklogByNumber(projectId: number, backlogNumber: number): Backlog | undefined {
    return this.backlogRepo.findByProjectAndNumber(projectId, backlogNumber);
  }

  /**
   * バックログを削除
   */
  delete(backlogId: number): boolean {
    const backlog = this.backlogRepo.findById(backlogId);
    if (backlog) {
      this.backlogRepo.delete(backlogId);
      return true;
    }
    return false;
  }

  /**
   * 優先度でバックログを更新
   */
  updatePriority(backlogId: number, priority: BacklogPriority): Backlog | undefined {
    return this.backlogRepo.update(backlogId, { priority });
  }

  /**
   * バックログのORDER紐付けを解除
   */
  unlinkFromOrder(backlogId: number): Backlog | undefined {
    return this.backlogRepo.update(backlogId, { order_id: null, status: 'TODO' });
  }
}
