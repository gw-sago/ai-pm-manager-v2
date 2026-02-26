import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron';
import path from 'node:path';
import fs from 'node:fs';
import { spawn } from 'node:child_process';
import started from 'electron-squirrel-startup';
import {
  initDatabase,
  closeDatabase,
  getDatabaseInfo,
  getDatabasePath,
} from './main/database';
import { registerDialogHandlers } from './main/dialog';
import { registerWatcherHandlers, cleanupWatcher } from './main/watcher';
import { registerConfigHandlers } from './main/config';
import { registerProjectHandlers, cleanupProject } from './main/project';
import { registerScriptHandlers } from './main/script';
import { registerAipmAutoLogHandlers, cleanupAipmAutoLog } from './main/aipmAutoLog';
import { registerSupervisorHandlers, cleanupSupervisor } from './main/supervisor';
import { registerDependencyUpdateHandlers, cleanupDependencyUpdate } from './main/dependencyUpdate';
import { registerRecoverHandlers } from './main/recover';
import { getAipmDbService } from './main/services/AipmDbService';
import { getConfigService } from './main/services/ConfigService';
import { migrateFromLocalAppData } from './main/utils/migrate-data';

// DB初期化ステータスを保持（レンダラーへの通知用）
let dbInitError: string | null = null;
let dbInitialized = false;

// ログファイルへの出力を設定
const logFile = path.join(app.getPath('userData'), 'main-debug.log');
const originalConsoleLog = console.log;
const originalConsoleError = console.error;

console.log = (...args) => {
  const msg = `[${new Date().toISOString()}] LOG: ${args.join(' ')}\n`;
  fs.appendFileSync(logFile, msg);
  originalConsoleLog.apply(console, args);
};

console.error = (...args) => {
  const msg = `[${new Date().toISOString()}] ERROR: ${args.join(' ')}\n`;
  fs.appendFileSync(logFile, msg);
  originalConsoleError.apply(console, args);
};

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (started) {
  app.quit();
}

/**
 * パッケージ版起動時にresources/内リソースをuserDataPath（Roaming）に展開
 * 展開対象: backend/, python-embed/, .claude/, CLAUDE.md, data/schema_v2.sql
 * 保護対象: data/aipm.db, PROJECTS/（永続データは上書きしない）
 *
 * 重要: Squirrelルート（Local）には展開しない。
 * Squirrelは再インストール時にルートを全削除するため、ロックされたファイルが
 * あるとfatalエラーでインストール失敗する。
 * userDataPath（%APPDATA%/Roaming）はSquirrelの管理外なので安全。
 */
function deployResources(): void {
  if (!app.isPackaged) return;

  const userDataPath = app.getPath('userData');
  const resourcesDir = process.resourcesPath;
  console.log('[Main] Deploying resources to userData:', userDataPath);

  // ディレクトリごとコピーする対象
  const dirTargets = ['backend', 'python-embed', '.claude'];
  for (const dir of dirTargets) {
    const src = path.join(resourcesDir, dir);
    const dest = path.join(userDataPath, dir);
    if (!fs.existsSync(src)) {
      console.log(`[Main] Deploy skip (not found): ${src}`);
      continue;
    }
    try {
      if (fs.existsSync(dest)) {
        try {
          fs.rmSync(dest, { recursive: true, force: true });
        } catch (rmErr) {
          console.warn(`[Main] Deploy: rmSync failed for ${dir} (will overwrite):`, rmErr);
        }
      }
      fs.cpSync(src, dest, { recursive: true, force: true });
      console.log(`[Main] Deployed: ${src} -> ${dest}`);
    } catch (err) {
      console.error(`[Main] Deploy error for ${dir}:`, err);
    }
  }

  // 単体ファイルコピー: CLAUDE.md
  const claudeMdSrc = path.join(resourcesDir, 'CLAUDE.md');
  if (fs.existsSync(claudeMdSrc)) {
    try {
      fs.copyFileSync(claudeMdSrc, path.join(userDataPath, 'CLAUDE.md'));
      console.log('[Main] Deployed: CLAUDE.md');
    } catch (err) {
      console.error('[Main] Deploy error for CLAUDE.md:', err);
    }
  }

  // data/schema_v2.sql のみコピー（data/aipm.db は保護）
  const dataDir = path.join(userDataPath, 'data');
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  const schemaSrc = path.join(resourcesDir, 'data', 'schema_v2.sql');
  if (fs.existsSync(schemaSrc)) {
    try {
      fs.copyFileSync(schemaSrc, path.join(dataDir, 'schema_v2.sql'));
      console.log('[Main] Deployed: data/schema_v2.sql');
    } catch (err) {
      console.error('[Main] Deploy error for schema_v2.sql:', err);
    }
  }

  console.log('[Main] Resource deployment completed');
}

const createWindow = () => {
  // Create the browser window.
  const mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      preload: MAIN_WINDOW_PRELOAD_WEBPACK_ENTRY,
    },
  });

  // and load the index.html of the app.
  mainWindow.loadURL(MAIN_WINDOW_WEBPACK_ENTRY);

  // Open the DevTools only in development mode
  if (!app.isPackaged) {
    mainWindow.webContents.openDevTools();
  }
};

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.on('ready', async () => {
  // V2統合: PROJECTSディレクトリを確保
  const configService = getConfigService();
  configService.ensureProjectsDirectory();
  console.log('[Main] Framework path:', configService.getActiveFrameworkPath());

  // パッケージ版起動時にresources/内リソースをuserDataPath（Roaming）に展開
  try {
    deployResources();
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    console.error('[Main] Resource deployment failed:', msg);
    dialog.showErrorBox(
      'Resource Deployment Error',
      `Failed to deploy resources.\n\nError: ${msg}\n\nSome features may not work correctly.`
    );
  }

  // ORDER_001 / TASK_004: 初回起動時マイグレーション（旧LOCAL→新ROAMING）
  // パッケージ時のみ実行（開発時は不要）
  if (app.isPackaged) {
    try {
      const squirrelRoot = path.resolve(path.dirname(process.execPath), '..');
      const userDataPath = app.getPath('userData');
      const migrationResult = migrateFromLocalAppData(squirrelRoot, userDataPath);
      if (migrationResult.migrated) {
        console.log('[Main] Data migration completed:', migrationResult.details.join('; '));
      } else {
        console.log('[Main] No data migration needed:', migrationResult.details.join('; '));
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      console.error('[Main] Data migration failed:', msg);
      // マイグレーション失敗は起動をブロックしない
    }
  }

  // Initialize database (data/aipm.db に一元化)
  // ORDER_157: DB自動初期化機能追加 - DBファイルが存在しない場合は自動作成
  try {
    const dbPath = getDatabasePath();
    console.log('[Main] Database path:', dbPath);
    console.log('[Main] Initializing database...');
    initDatabase();
    const dbInfo = getDatabaseInfo();
    console.log('[Main] Database initialized:', JSON.stringify(dbInfo));
    dbInitialized = true;
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    const errorStack = error instanceof Error ? error.stack : 'No stack';
    console.error('[Main] Failed to initialize database:', errorMessage);
    console.error('[Main] Stack:', errorStack);
    dbInitError = errorMessage;

    // ORDER_157: エラーメッセージを改善（自動初期化失敗時の情報を追加）
    const errorDetails = errorMessage.includes('Schema file not found')
      ? `\n\nSchema file is missing from the application resources.\nThis may indicate a packaging error.`
      : errorMessage.includes('auto-initialization failed')
      ? `\n\nThe database could not be created automatically.\nPlease check file permissions for:\n${getDatabasePath()}`
      : '';

    // ユーザーにエラーを通知
    dialog.showErrorBox(
      'Database Initialization Error',
      `Failed to initialize database.\n\n` +
        `Error: ${errorMessage}${errorDetails}\n\n` +
        `Some features may not work correctly.\n` +
        `Please check the log file for details:\n` +
        `${logFile}`
    );
  }

  if (!dbInitialized) {
    console.error('[Main] WARNING: Database not initialized. Some features may not work.');
  }

  // Auto-reorder backlogs for all active projects (ORDER_129 / TASK_1130)
  if (dbInitialized) {
    try {
      const aipmDbService = getAipmDbService();
      if (aipmDbService.isAvailable()) {
        // 非同期実行（起動をブロックしない）
        aipmDbService.autoReorderAllBacklogs().catch((error) => {
          console.error('[Main] Backlog auto-reorder failed:', error);
        });
      }
    } catch (error) {
      console.warn('[Main] Failed to initialize backlog auto-reorder:', error);
    }
  }

  // Register IPC handlers for dialog
  registerDialogHandlers();

  // Register IPC handlers for file watcher
  registerWatcherHandlers();

  // Register IPC handlers for config
  registerConfigHandlers();

  // Register IPC handlers for project
  registerProjectHandlers();

  // Register IPC handlers for script execution (ORDER_039)
  registerScriptHandlers();

  // Register IPC handlers for aipm_auto log (ORDER_050)
  registerAipmAutoLogHandlers();

  // Register IPC handlers for supervisor (ORDER_059)
  registerSupervisorHandlers();

  // Register IPC handlers for dependency updates (ORDER_122 / TASK_1103)
  registerDependencyUpdateHandlers();

  // Register IPC handlers for order recovery (ORDER_060)
  registerRecoverHandlers();

  // ORDER_157: DB初期化ステータスをレンダラーに公開するIPCハンドラ
  ipcMain.handle('db:get-init-status', () => {
    return {
      initialized: dbInitialized,
      error: dbInitError,
      dbPath: (() => {
        try {
          return getDatabasePath();
        } catch {
          return null;
        }
      })(),
    };
  });

  // CHANGELOG.md 読み込みIPCハンドラ（ORDER_049 / TASK_162）
  ipcMain.handle('changelog:read', () => {
    const changelogPaths = [
      // パッケージ版: resources/CHANGELOG.md
      app.isPackaged ? path.join(process.resourcesPath, 'CHANGELOG.md') : null,
      // 開発版: プロジェクトルートのCHANGELOG.md
      path.join(app.getAppPath(), '..', 'CHANGELOG.md'),
      path.join(app.getAppPath(), 'CHANGELOG.md'),
    ].filter(Boolean) as string[];

    for (const p of changelogPaths) {
      if (fs.existsSync(p)) {
        try {
          const content = fs.readFileSync(p, 'utf8');
          console.log('[Main] CHANGELOG.md loaded from:', p);
          return { success: true, content };
        } catch (err) {
          console.error('[Main] Failed to read CHANGELOG.md:', err);
        }
      }
    }
    return { success: false, content: null, error: 'CHANGELOG.md not found' };
  });

  // ターミナル起動IPCハンドラ
  ipcMain.handle('terminal:open', () => {
    const cwd = configService.getUserDataPath();
    console.log('[Main] Opening terminal at:', cwd);
    spawn('cmd.exe', ['/c', 'start', 'cmd.exe'], {
      cwd,
      detached: true,
      stdio: 'ignore',
    });
  });

  // ORDER_053: 成果物フォルダを開く（shell.openPath）
  // folderPath は Roaming 絶対パスを受け取る
  ipcMain.handle('shell:open-path', async (_event, folderPath: string) => {
    console.log('[Main] shell:open-path:', folderPath);
    if (!folderPath || typeof folderPath !== 'string') {
      return { success: false, error: 'Invalid path' };
    }
    if (!fs.existsSync(folderPath)) {
      return { success: false, error: `Path does not exist: ${folderPath}` };
    }
    const result = await shell.openPath(folderPath);
    // shell.openPath returns empty string on success, error message on failure
    if (result === '') {
      return { success: true };
    } else {
      return { success: false, error: result };
    }
  });

  // ORDER_053: ファイルを保存ダイアログで任意パスへコピー（dialog.showSaveDialog + fs.copyFile）
  // srcPath は Roaming 絶対パスを受け取る
  ipcMain.handle('shell:save-file-dialog', async (_event, srcPath: string, defaultFileName?: string) => {
    console.log('[Main] shell:save-file-dialog:', srcPath);
    if (!srcPath || typeof srcPath !== 'string') {
      return { success: false, error: 'Invalid source path' };
    }
    if (!fs.existsSync(srcPath)) {
      return { success: false, error: `Source file does not exist: ${srcPath}` };
    }
    const suggestedName = defaultFileName || path.basename(srcPath);
    const { canceled, filePath } = await dialog.showSaveDialog({
      defaultPath: suggestedName,
      filters: [{ name: 'All Files', extensions: ['*'] }],
    });
    if (canceled || !filePath) {
      return { success: false, canceled: true };
    }
    try {
      fs.copyFileSync(srcPath, filePath);
      console.log('[Main] File copied:', srcPath, '->', filePath);
      return { success: true, savedPath: filePath };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error('[Main] File copy error:', msg);
      return { success: false, error: msg };
    }
  });

  // ============================================================
  // ORDER_057: ドキュメントツリービュー IPC ハンドラ（TASK_196）
  // ORDER_103: ドキュメント参照パス解決拡張（TASK_360）
  // docs:list - プロジェクト設定に基づくドキュメント一覧取得
  // docs:get  - プロジェクト設定に基づくドキュメント内容取得
  // バックエンドがprojectIdからdev_workspace_pathを取得し、
  // 設定されていればdev_workspace/docs/を、なければPROJECTS/{id}/docs/を参照
  // ============================================================
  ipcMain.handle('docs:list', async (_event, projectId: string) => {
    console.log('[Main] docs:list called:', projectId);
    try {
      const backendPath = configService.getBackendPath();
      if (!backendPath) {
        return { success: false, error: 'Backend path not configured', project_id: projectId, docs_path: '', index_exists: false, files: [], total_count: 0, categories: [] };
      }
      const scriptPath = path.join(backendPath, 'project', 'docs_list.py');
      if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `docs_list.py not found: ${scriptPath}`, project_id: projectId, docs_path: '', index_exists: false, files: [], total_count: 0, categories: [] };
      }
      const pythonCommand = configService.getPythonPath();
      const { stdout } = await new Promise<{ stdout: string; stderr: string }>((resolve, reject) => {
        const proc = spawn(pythonCommand, [scriptPath, projectId, '--json'], {
          cwd: path.dirname(scriptPath),
          timeout: 30000,
        });
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (data: Buffer) => { stdout += data.toString(); });
        proc.stderr.on('data', (data: Buffer) => { stderr += data.toString(); });
        proc.on('close', (code: number | null) => {
          if (code === 0) {
            resolve({ stdout, stderr });
          } else {
            reject(new Error(`docs_list.py exited with code ${code}: ${stderr}`));
          }
        });
        proc.on('error', reject);
      });
      const result = JSON.parse(stdout);
      return result;
    } catch (error) {
      console.error('[Main] docs:list error:', error);
      return { success: false, error: error instanceof Error ? error.message : String(error), project_id: projectId, docs_path: '', index_exists: false, files: [], total_count: 0, categories: [] };
    }
  });

  ipcMain.handle('docs:get', async (_event, projectId: string, fileId: string) => {
    console.log('[Main] docs:get called:', projectId, fileId);
    try {
      const backendPath = configService.getBackendPath();
      if (!backendPath) {
        return { success: false, error: 'Backend path not configured' };
      }
      const scriptPath = path.join(backendPath, 'project', 'docs_get.py');
      if (!fs.existsSync(scriptPath)) {
        return { success: false, error: `docs_get.py not found: ${scriptPath}` };
      }
      const pythonCommand = configService.getPythonPath();
      const { stdout } = await new Promise<{ stdout: string; stderr: string }>((resolve, reject) => {
        const proc = spawn(pythonCommand, [scriptPath, projectId, fileId, '--json'], {
          cwd: path.dirname(scriptPath),
          timeout: 30000,
        });
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (data: Buffer) => { stdout += data.toString(); });
        proc.stderr.on('data', (data: Buffer) => { stderr += data.toString(); });
        proc.on('close', (code: number | null) => {
          if (code === 0) {
            resolve({ stdout, stderr });
          } else {
            reject(new Error(`docs_get.py exited with code ${code}: ${stderr}`));
          }
        });
        proc.on('error', reject);
      });
      const result = JSON.parse(stdout);
      return result;
    } catch (error) {
      console.error('[Main] docs:get error:', error);
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });

  createWindow();

  // ORDER_102 / TASK_357: アプリ起動時にログクリーンアップをバックグラウンド実行
  if (dbInitialized) {
    runLogCleanup(configService).catch((error) => {
      console.error('[Main] Log cleanup failed:', error);
    });
  }
});

/**
 * ORDER_102 / TASK_357: ログクリーンアップをバックグラウンドで実行
 *
 * backend/log/cleanup.py を child_process.spawn で非同期実行し、
 * UI起動をブロックしない。結果JSONをアプリログに記録する。
 * エラー時もアプリ起動を妨げない（ログ出力のみ）。
 */
async function runLogCleanup(configService: ReturnType<typeof getConfigService>): Promise<void> {
  try {
    const pythonCommand = configService.getPythonPath();
    const backendPath = configService.getBackendPath();
    if (!backendPath) {
      console.warn('[Main] Log cleanup skipped: backend path not configured');
      return;
    }

    const scriptPath = path.join(backendPath, 'log', 'cleanup.py');
    if (!fs.existsSync(scriptPath)) {
      console.warn('[Main] Log cleanup skipped: cleanup.py not found at', scriptPath);
      return;
    }

    console.log('[Main] Starting background log cleanup...');

    const result = await new Promise<string>((resolve, reject) => {
      const proc = spawn(pythonCommand, [scriptPath, '--json'], {
        cwd: backendPath,
        timeout: 60000, // 60秒タイムアウト
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data: Buffer) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      proc.on('close', (code: number | null) => {
        if (stderr) {
          console.warn('[Main] Log cleanup stderr:', stderr.trim());
        }
        if (code === 0) {
          resolve(stdout);
        } else {
          reject(new Error(`cleanup.py exited with code ${code}: ${stderr}`));
        }
      });

      proc.on('error', (err: Error) => {
        reject(new Error(`Failed to spawn cleanup.py: ${err.message}`));
      });
    });

    // JSON結果をパースしてログに記録
    try {
      const parsed = JSON.parse(result);
      if (parsed.skipped) {
        console.log('[Main] Log cleanup skipped:', parsed.skip_reason);
      } else {
        console.log(
          `[Main] Log cleanup completed: ${parsed.total_deleted} entries deleted ` +
          `(${parsed.rows_before} -> ${parsed.rows_after} rows), ` +
          `elapsed: ${parsed.elapsed_sec}s`
        );
      }
    } catch {
      // JSONパース失敗時はraw出力をログ
      console.log('[Main] Log cleanup result (raw):', result.trim());
    }
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    console.error('[Main] Log cleanup error:', msg);
    // エラー時もアプリ起動は妨げない
  }
}

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    closeDatabase();
    app.quit();
  }
});

app.on('before-quit', () => {
  cleanupProject();
  cleanupWatcher();
  cleanupAipmAutoLog();
  cleanupSupervisor();
  cleanupDependencyUpdate();
  closeDatabase();
});

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and import them here.
