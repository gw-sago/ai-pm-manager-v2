/**
 * DB Auto-Initializer
 *
 * ORDER_157: DB自動初期化機能
 * ORDER_159: スキーマパス取得をConfigService経由に統一
 * 初回起動時に%APPDATA%/ai-pm-manager-v2/.aipm/にaipm.dbを自動作成する
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
