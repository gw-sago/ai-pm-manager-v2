/**
 * migrate-data.ts
 *
 * ORDER_001 / TASK_004: 初回起動時マイグレーション処理
 *
 * アプリ起動時に旧パス（%LOCALAPPDATA%/ai_pm_manager_v2/ = Squirrelルート）に
 * aipm.db や PROJECTS/ が存在し、かつ新パス（%APPDATA%/ai-pm-manager-v2/）に
 * データがまだ存在しない場合に自動コピーするマイグレーション処理。
 *
 * - 旧パス: %LOCALAPPDATA%/ai_pm_manager_v2/data/aipm.db, PROJECTS/
 * - 新パス: %APPDATA%/ai-pm-manager-v2/data/aipm.db, PROJECTS/
 * - コピー後、旧パスのファイルはそのまま残す（安全のため削除しない）
 */

import * as fs from 'node:fs';
import * as path from 'node:path';

export interface MigrationResult {
  migrated: boolean;
  details: string[];
}

/**
 * 旧パス（Squirrelルート）から新パス（userData）へデータをマイグレーションする。
 *
 * @param squirrelRoot Squirrelインストーラーのルートパス（%LOCALAPPDATA%/ai_pm_manager_v2/）
 * @param userDataPath app.getPath('userData') のパス（%APPDATA%/ai-pm-manager-v2/）
 * @returns マイグレーション結果
 */
export function migrateFromLocalAppData(
  squirrelRoot: string,
  userDataPath: string
): MigrationResult {
  const details: string[] = [];
  let migrated = false;

  console.log('[Migration] Checking migration from Squirrel root to userData...');
  console.log('[Migration] Squirrel root (old):', squirrelRoot);
  console.log('[Migration] userData (new):', userDataPath);

  // --- 1. aipm.db のマイグレーション ---
  try {
    const oldDbPath = path.join(squirrelRoot, 'data', 'aipm.db');
    const newDbPath = path.join(userDataPath, 'data', 'aipm.db');

    if (fs.existsSync(oldDbPath) && !fs.existsSync(newDbPath)) {
      // 新パス側の data/ ディレクトリを確保
      const newDataDir = path.join(userDataPath, 'data');
      if (!fs.existsSync(newDataDir)) {
        fs.mkdirSync(newDataDir, { recursive: true });
      }

      fs.copyFileSync(oldDbPath, newDbPath);
      const msg = `Migrated: ${oldDbPath} -> ${newDbPath}`;
      console.log(`[Migration] ${msg}`);
      details.push(msg);
      migrated = true;
    } else if (!fs.existsSync(oldDbPath)) {
      details.push(`Skip: aipm.db not found at old path (${oldDbPath})`);
      console.log('[Migration] Skip: aipm.db not found at old path');
    } else {
      details.push(`Skip: aipm.db already exists at new path (${newDbPath})`);
      console.log('[Migration] Skip: aipm.db already exists at new path');
    }
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    const msg = `Error migrating aipm.db: ${errMsg}`;
    console.error(`[Migration] ${msg}`);
    details.push(msg);
  }

  // --- 2. PROJECTS/ ディレクトリのマイグレーション ---
  try {
    const oldProjectsDir = path.join(squirrelRoot, 'PROJECTS');
    const newProjectsDir = path.join(userDataPath, 'PROJECTS');

    if (fs.existsSync(oldProjectsDir) && !fs.existsSync(newProjectsDir)) {
      fs.cpSync(oldProjectsDir, newProjectsDir, { recursive: true });
      const msg = `Migrated: ${oldProjectsDir} -> ${newProjectsDir}`;
      console.log(`[Migration] ${msg}`);
      details.push(msg);
      migrated = true;
    } else if (!fs.existsSync(oldProjectsDir)) {
      details.push(`Skip: PROJECTS/ not found at old path (${oldProjectsDir})`);
      console.log('[Migration] Skip: PROJECTS/ not found at old path');
    } else {
      details.push(`Skip: PROJECTS/ already exists at new path (${newProjectsDir})`);
      console.log('[Migration] Skip: PROJECTS/ already exists at new path');
    }
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    const msg = `Error migrating PROJECTS/: ${errMsg}`;
    console.error(`[Migration] ${msg}`);
    details.push(msg);
  }

  if (migrated) {
    console.log('[Migration] Migration completed successfully');
  } else {
    console.log('[Migration] No migration needed');
  }

  return { migrated, details };
}
