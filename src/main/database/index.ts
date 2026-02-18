/**
 * Database Module
 *
 * SQLite データベースの初期化・管理を行うメインモジュール。
 *
 * V2統合: AppData DBを廃止し、data/aipm.db に一元化。
 * スキーマはPython backend (data/schema_v2.sql) で管理。
 * Electron側は読み書き両方可能だが、スキーマ作成はbackend側が担当。
 */

import Database from 'better-sqlite3';
import * as fs from 'fs';
import { getConfigService } from '../services/ConfigService';
import { autoInitializeDatabase, ensureSchemaAndSeedData } from '../utils/db-initializer';

// シングルトンインスタンス
let dbInstance: Database.Database | null = null;
let currentDbPath: string | null = null;

/**
 * データベースファイルのパスを取得
 * V2: リポジトリルート/data/aipm.db
 */
export function getDatabasePath(): string {
  const configService = getConfigService();
  return configService.getAipmDbPath();
}

/**
 * データベースを初期化
 * ORDER_157: DB自動初期化対応 - DBファイルが存在しない場合は自動作成を試みる
 */
export function initDatabase(customPath?: string): Database.Database {
  if (dbInstance) {
    return dbInstance;
  }

  currentDbPath = customPath ?? getDatabasePath();

  // ORDER_157: DBファイルが存在しない場合は自動初期化を試みる
  if (!fs.existsSync(currentDbPath)) {
    console.log(`[Database] DB file not found: ${currentDbPath}`);
    console.log('[Database] Attempting auto-initialization...');

    // DB自動初期化を試みる
    try {
      const result = autoInitializeDatabase(currentDbPath);

      if (!result.success) {
        throw new Error(result.error || 'DB initialization failed');
      }

      if (result.created) {
        console.log('[Database] Database auto-initialized successfully');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error('[Database] Auto-initialization failed:', errorMessage);
      throw new Error(`Database file not found and auto-initialization failed: ${errorMessage}`);
    }
  }

  // データベース接続
  dbInstance = new Database(currentDbPath);

  // WALモードを有効化（パフォーマンス向上）
  dbInstance.pragma('journal_mode = WAL');

  // 外部キー制約を有効化
  dbInstance.pragma('foreign_keys = ON');

  console.log(`[Database] Connected to: ${currentDbPath}`);

  // 不足テーブル・初期データ（status_transitions等）を補完
  ensureSchemaAndSeedData(dbInstance);

  return dbInstance;
}

/**
 * データベースが初期化済みかどうかを確認
 */
export function isDatabaseInitialized(): boolean {
  return dbInstance !== null;
}

/**
 * データベースインスタンスを取得
 * 未初期化の場合は自動的に初期化を試みる
 */
export function getDatabase(): Database.Database {
  if (!dbInstance) {
    console.log('[Database] Auto-initializing database...');
    try {
      const db = initDatabase();
      if (!db) {
        throw new Error('initDatabase() returned null');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error('[Database] Auto-initialization failed:', errorMessage);
      throw new Error(`Database initialization failed: ${errorMessage}`);
    }
  }

  if (!dbInstance) {
    throw new Error('Database not initialized. Call initDatabase() first.');
  }

  return dbInstance;
}

/**
 * データベース接続を閉じる
 */
export function closeDatabase(): void {
  if (dbInstance) {
    dbInstance.close();
    dbInstance = null;
    currentDbPath = null;
  }
}

/**
 * トランザクション内で処理を実行
 */
export function transaction<T>(fn: () => T): T {
  const db = getDatabase();
  return db.transaction(fn)();
}

/**
 * クエリを実行して結果を取得
 */
export function query<T>(sql: string, params?: unknown[]): T[] {
  const db = getDatabase();
  const stmt = db.prepare(sql);
  return (params ? stmt.all(...params) : stmt.all()) as T[];
}

/**
 * クエリを実行して1行だけ取得
 */
export function queryOne<T>(sql: string, params?: unknown[]): T | undefined {
  const db = getDatabase();
  const stmt = db.prepare(sql);
  return (params ? stmt.get(...params) : stmt.get()) as T | undefined;
}

/**
 * INSERT/UPDATE/DELETE を実行
 */
export function run(
  sql: string,
  params?: unknown[]
): Database.RunResult {
  const db = getDatabase();
  const stmt = db.prepare(sql);
  return params ? stmt.run(...params) : stmt.run();
}

/**
 * データベース情報を取得
 */
export function getDatabaseInfo(): {
  path: string;
  tables: string[];
} {
  const db = getDatabase();
  const dbPath = getDatabasePath();

  const tables = db
    .prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    .all() as { name: string }[];

  return {
    path: dbPath,
    tables: tables.map((t) => t.name),
  };
}
