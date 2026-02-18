/**
 * DB Auto-Initializer
 *
 * ORDER_157: DB自動初期化機能
 * ORDER_159: スキーマパス取得をConfigService経由に統一
 * ORDER_160: コメント修正（AppData参照を削除）
 * ORDER_001: DB保存先をuserDataPath（%APPDATA%/ai-pm-manager-v2/data/）に移行
 * DBファイルが存在しない場合に、指定パス（userDataPath/data/aipm.db）へ自動作成する
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import Database from 'better-sqlite3';
import { getConfigService } from '../services/ConfigService';

/**
 * DBディレクトリとDBファイルを初期化
 *
 * @param dbPath 作成するDBファイルのパス
 * @returns 初期化成功: true, 既存DBあり/失敗: false
 * @throws スキーマファイルが見つからない場合やDB作成失敗時にエラー
 */
export function initializeDatabaseFile(dbPath: string): boolean {
  // 既存DBがあればスキップ
  if (fs.existsSync(dbPath)) {
    console.log('[DBInitializer] Database already exists:', dbPath);
    return false;
  }

  // ディレクトリを確保
  const dbDir = path.dirname(dbPath);
  if (!fs.existsSync(dbDir)) {
    console.log('[DBInitializer] Creating DB directory:', dbDir);
    fs.mkdirSync(dbDir, { recursive: true });
  }

  // スキーマファイルを読み込む（ConfigService経由）
  const configService = getConfigService();
  const schemaPath = configService.getSchemaPath();
  console.log('[DBInitializer] Reading schema from:', schemaPath);

  if (!fs.existsSync(schemaPath)) {
    throw new Error(`Schema file not found: ${schemaPath}`);
  }

  const schema = fs.readFileSync(schemaPath, 'utf-8');

  // DBを作成してスキーマを実行
  console.log('[DBInitializer] Creating database:', dbPath);
  let db: Database.Database | null = null;

  try {
    db = new Database(dbPath);

    // スキーマを実行（複数ステートメント対応）
    db.exec(schema);

    console.log('[DBInitializer] Database initialized successfully');
    return true;
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error('[DBInitializer] Failed to initialize database:', errorMessage);

    // 失敗した場合はDBファイルを削除（次回再試行できるように）
    if (fs.existsSync(dbPath)) {
      try {
        fs.unlinkSync(dbPath);
        console.log('[DBInitializer] Cleaned up failed DB file');
      } catch (cleanupError) {
        console.warn('[DBInitializer] Failed to clean up DB file:', cleanupError);
      }
    }

    throw new Error(`Database initialization failed: ${errorMessage}`);
  } finally {
    if (db) {
      try {
        db.close();
      } catch (closeError) {
        console.warn('[DBInitializer] Failed to close DB connection:', closeError);
      }
    }
  }
}

/**
 * 既存DBに対してスキーマを再適用し、不足テーブル・初期データを補完する
 *
 * CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE により安全に実行可能。
 * 既存データは上書きされない。
 *
 * @param db 接続済みのDatabaseインスタンス
 */
export function ensureSchemaAndSeedData(db: Database.Database): void {
  const configService = getConfigService();
  const schemaPath = configService.getSchemaPath();

  if (!fs.existsSync(schemaPath)) {
    console.warn('[DBInitializer] Schema file not found, skipping seed data check:', schemaPath);
    return;
  }

  try {
    // status_transitions の行数でマスターデータの有無を判定
    const row = db.prepare('SELECT COUNT(*) as cnt FROM status_transitions').get() as { cnt: number } | undefined;
    const transitionCount = row?.cnt ?? 0;

    // テーブル一覧を取得して不足テーブルがないかも確認
    const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all() as { name: string }[];
    const tableNames = new Set(tables.map(t => t.name));
    const expectedTables = ['orders', 'tasks', 'backlog_items', 'status_transitions', 'file_locks', 'incidents', 'builds'];
    const missingTables = expectedTables.filter(t => !tableNames.has(t));

    if (transitionCount > 0 && missingTables.length === 0) {
      console.log(`[DBInitializer] Schema OK: ${transitionCount} transitions, all tables present`);
      return;
    }

    console.log(`[DBInitializer] Applying schema: transitions=${transitionCount}, missing=[${missingTables.join(',')}]`);
    const schema = fs.readFileSync(schemaPath, 'utf-8');
    db.exec(schema);

    const newCount = (db.prepare('SELECT COUNT(*) as cnt FROM status_transitions').get() as { cnt: number })?.cnt ?? 0;
    console.log(`[DBInitializer] Schema applied: ${newCount} transitions now`);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error('[DBInitializer] Failed to ensure schema/seed data:', errorMessage);
    // 起動をブロックしない（ベストエフォート）
  }
}

/**
 * DB自動初期化のエントリーポイント
 *
 * @param dbPath 初期化するDBファイルのパス
 * @returns 初期化結果 { success: boolean, error?: string, created: boolean }
 */
export function autoInitializeDatabase(dbPath: string): {
  success: boolean;
  error?: string;
  created: boolean;
} {
  try {
    const created = initializeDatabaseFile(dbPath);
    return { success: true, created };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    return { success: false, error: errorMessage, created: false };
  }
}
