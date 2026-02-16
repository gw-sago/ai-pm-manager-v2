/**
 * Order Repository
 *
 * ORDERのCRUD操作を提供
 */

import { BaseRepository, BaseEntity } from './BaseRepository';
import type { OrderStatus, Priority } from '../schema';

export interface Order extends BaseEntity {
  project_id: number;
  order_number: number;
  title: string;
  status: OrderStatus;
  priority: Priority;
}

export interface CreateOrderInput {
  project_id: number;
  order_number: number;
  title: string;
  status?: OrderStatus;
  priority?: Priority;
}

export interface UpdateOrderInput {
  title?: string;
  status?: OrderStatus;
  priority?: Priority;
}

export class OrderRepository extends BaseRepository<Order> {
  protected tableName = 'orders';

  /**
   * ORDERを作成
   */
  create(input: CreateOrderInput): Order {
    const now = this.now();
    const result = this.db
      .prepare(
        `INSERT INTO orders (project_id, order_number, title, status, priority, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      )
      .run(
        input.project_id,
        input.order_number,
        input.title,
        input.status ?? 'PLANNING',
        input.priority ?? 'P2',
        now,
        now
      );

    return this.findById(result.lastInsertRowid as number)!;
  }

  /**
   * ORDERを更新
   */
  update(id: number, input: UpdateOrderInput): Order | undefined {
    const order = this.findById(id);
    if (!order) {
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
    if (input.priority !== undefined) {
      updates.push('priority = ?');
      values.push(input.priority);
    }

    if (updates.length === 0) {
      return order;
    }

    updates.push('updated_at = ?');
    values.push(this.now());
    values.push(id);

    this.db
      .prepare(`UPDATE orders SET ${updates.join(', ')} WHERE id = ?`)
      .run(...values);

    return this.findById(id);
  }

  /**
   * プロジェクトIDでORDERを検索
   */
  findByProjectId(projectId: number): Order[] {
    return this.db
      .prepare(
        `SELECT * FROM orders
         WHERE project_id = ?
         ORDER BY order_number`
      )
      .all(projectId) as Order[];
  }

  /**
   * プロジェクトIDとORDER番号でORDERを検索
   */
  findByProjectAndNumber(projectId: number, orderNumber: number): Order | undefined {
    return this.db
      .prepare(
        `SELECT * FROM orders
         WHERE project_id = ? AND order_number = ?`
      )
      .get(projectId, orderNumber) as Order | undefined;
  }

  /**
   * ステータスでORDERを検索
   */
  findByStatus(status: OrderStatus): Order[] {
    return this.findBy({ status } as Partial<Order>);
  }

  /**
   * アクティブなORDERを取得
   */
  findActive(): Order[] {
    return this.db
      .prepare(
        `SELECT * FROM orders
         WHERE status NOT IN ('COMPLETED', 'CANCELLED')
         ORDER BY priority, order_number`
      )
      .all() as Order[];
  }

  /**
   * ORDERのステータスを更新
   */
  updateStatus(id: number, status: OrderStatus): Order | undefined {
    return this.update(id, { status });
  }

  /**
   * プロジェクトの次のORDER番号を取得
   */
  getNextOrderNumber(projectId: number): number {
    const result = this.db
      .prepare(
        `SELECT MAX(order_number) as max_number
         FROM orders
         WHERE project_id = ?`
      )
      .get(projectId) as { max_number: number | null };
    return (result.max_number ?? 0) + 1;
  }
}
