/**
 * Database Migrations
 *
 * スキーマのバージョン管理とマイグレーションを処理します。
 */

import type Database from 'better-sqlite3';
import { SCHEMA_VERSION, INITIAL_SCHEMA } from './schema';

export interface Migration {
  version: number;
  description: string;
  up: string;
  down?: string;
}

/**
 * マイグレーション定義
 * version 1 は INITIAL_SCHEMA で処理されるため、version 2 以降をここに追加
 */
export const MIGRATIONS: Migration[] = [
  {
    version: 2,
    description: 'Add project information fields (description, purpose, tech_stack)',
    up: `
      ALTER TABLE projects ADD COLUMN description TEXT;
      ALTER TABLE projects ADD COLUMN purpose TEXT;
      ALTER TABLE projects ADD COLUMN tech_stack TEXT;
    `,
    down: `
      ALTER TABLE projects DROP COLUMN tech_stack;
      ALTER TABLE projects DROP COLUMN purpose;
      ALTER TABLE projects DROP COLUMN description;
    `,
  },
];

/**
 * 現在のスキーマバージョンを取得
 */
export function getCurrentVersion(db: Database.Database): number {
  try {
    const result = db.prepare(
      'SELECT MAX(version) as version FROM schema_versions'
    ).get() as { version: number | null } | undefined;
    return result?.version ?? 0;
  } catch {
    // テーブルが存在しない場合
    return 0;
  }
}

/**
 * スキーマバージョンを記録
 */
export function recordVersion(db: Database.Database, version: number): void {
  const now = new Date().toISOString();
  db.prepare(
    'INSERT OR REPLACE INTO schema_versions (version, applied_at) VALUES (?, ?)'
  ).run(version, now);
}

/**
 * 初期スキーマを適用
 */
export function applyInitialSchema(db: Database.Database): void {
  db.exec(INITIAL_SCHEMA);
  recordVersion(db, 1);
}

/**
 * マイグレーションを実行
 */
export function runMigrations(db: Database.Database): {
  applied: number[];
  currentVersion: number;
} {
  const currentVersion = getCurrentVersion(db);
  const applied: number[] = [];

  // 初期スキーマが未適用の場合
  if (currentVersion === 0) {
    applyInitialSchema(db);
    applied.push(1);
  }

  // version 2 以降のマイグレーションを適用
  const pendingMigrations = MIGRATIONS.filter(
    (m) => m.version > Math.max(currentVersion, 1)
  ).sort((a, b) => a.version - b.version);

  for (const migration of pendingMigrations) {
    db.transaction(() => {
      db.exec(migration.up);
      recordVersion(db, migration.version);
    })();
    applied.push(migration.version);
  }

  return {
    applied,
    currentVersion: getCurrentVersion(db),
  };
}

/**
 * スキーマが最新かどうかを確認
 */
export function isSchemaUpToDate(db: Database.Database): boolean {
  const currentVersion = getCurrentVersion(db);
  const latestVersion = MIGRATIONS.length > 0
    ? Math.max(SCHEMA_VERSION, ...MIGRATIONS.map((m) => m.version))
    : SCHEMA_VERSION;
  return currentVersion >= latestVersion;
}

/**
 * マイグレーション情報を取得
 */
export function getMigrationInfo(db: Database.Database): {
  currentVersion: number;
  targetVersion: number;
  pendingCount: number;
} {
  const currentVersion = getCurrentVersion(db);
  const targetVersion = MIGRATIONS.length > 0
    ? Math.max(SCHEMA_VERSION, ...MIGRATIONS.map((m) => m.version))
    : SCHEMA_VERSION;

  const pendingCount = currentVersion === 0
    ? MIGRATIONS.length + 1
    : MIGRATIONS.filter((m) => m.version > currentVersion).length;

  return {
    currentVersion,
    targetVersion,
    pendingCount,
  };
}
