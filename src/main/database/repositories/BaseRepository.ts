/**
 * Base Repository
 *
 * 共通のCRUD操作を提供するベースリポジトリ
 */

import type Database from 'better-sqlite3';

export interface BaseEntity {
  id: number;
  created_at: string;
  updated_at: string;
}

export abstract class BaseRepository<T extends BaseEntity> {
  protected abstract tableName: string;
  protected db: Database.Database;

  constructor(db: Database.Database) {
    this.db = db;
  }

  protected now(): string {
    return new Date().toISOString();
  }

  /**
   * IDで検索
   */
  findById(id: number): T | undefined {
    return this.db
      .prepare(`SELECT * FROM ${this.tableName} WHERE id = ?`)
      .get(id) as T | undefined;
  }

  /**
   * 全件取得
   */
  findAll(): T[] {
    return this.db
      .prepare(`SELECT * FROM ${this.tableName} ORDER BY id`)
      .all() as T[];
  }

  /**
   * 条件で検索
   */
  findBy(conditions: Partial<T>): T[] {
    const keys = Object.keys(conditions);
    if (keys.length === 0) {
      return this.findAll();
    }

    const whereClause = keys.map((k) => `${k} = ?`).join(' AND ');
    const values = keys.map((k) => conditions[k as keyof T]);

    return this.db
      .prepare(`SELECT * FROM ${this.tableName} WHERE ${whereClause}`)
      .all(...values) as T[];
  }

  /**
   * 条件で1件検索
   */
  findOneBy(conditions: Partial<T>): T | undefined {
    const results = this.findBy(conditions);
    return results[0];
  }

  /**
   * 削除
   */
  delete(id: number): boolean {
    const result = this.db
      .prepare(`DELETE FROM ${this.tableName} WHERE id = ?`)
      .run(id);
    return result.changes > 0;
  }

  /**
   * 全削除
   */
  deleteAll(): number {
    const result = this.db.prepare(`DELETE FROM ${this.tableName}`).run();
    return result.changes;
  }

  /**
   * 件数取得
   */
  count(conditions?: Partial<T>): number {
    if (!conditions || Object.keys(conditions).length === 0) {
      const result = this.db
        .prepare(`SELECT COUNT(*) as count FROM ${this.tableName}`)
        .get() as { count: number };
      return result.count;
    }

    const keys = Object.keys(conditions);
    const whereClause = keys.map((k) => `${k} = ?`).join(' AND ');
    const values = keys.map((k) => conditions[k as keyof T]);

    const result = this.db
      .prepare(`SELECT COUNT(*) as count FROM ${this.tableName} WHERE ${whereClause}`)
      .get(...values) as { count: number };
    return result.count;
  }

  /**
   * 存在確認
   */
  exists(id: number): boolean {
    const result = this.db
      .prepare(`SELECT 1 FROM ${this.tableName} WHERE id = ? LIMIT 1`)
      .get(id);
    return !!result;
  }

  /**
   * トランザクション内で処理を実行
   */
  protected transaction<R>(fn: () => R): R {
    return this.db.transaction(fn)();
  }
}
