import { app, BrowserWindow, dialog, ipcMain } from 'electron';
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
 * ORDER_164: パッケージ版起動時にresources/内リソースをSquirrelルートに展開
 * 展開対象: backend/, python-embed/, .claude/, CLAUDE.md, data/schema_v2.sql
 * 保護対象: data/aipm.db, PROJECTS/（永続データは上書きしない）
 */
function deployResources(): void {
  if (!app.isPackaged) return;

  const squirrelRoot = path.resolve(path.dirname(process.execPath), '..');
  const resourcesDir = process.resourcesPath;
  console.log('[Main] Deploying resources to Squirrel root:', squirrelRoot);

  // ディレクトリごと削除→コピーする対象
  const dirTargets = ['backend', 'python-embed', '.claude'];
  for (const dir of dirTargets) {
    const src = path.join(resourcesDir, dir);
    const dest = path.join(squirrelRoot, dir);
    if (!fs.existsSync(src)) {
      console.log(`[Main] Deploy skip (not found): ${src}`);
      continue;
    }
    try {
      if (fs.existsSync(dest)) {
        fs.rmSync(dest, { recursive: true, force: true });
      }
      fs.cpSync(src, dest, { recursive: true });
      console.log(`[Main] Deployed: ${src} -> ${dest}`);
    } catch (err) {
      console.error(`[Main] Deploy error for ${dir}:`, err);
    }
  }

  // 単体ファイルコピー: CLAUDE.md
  const claudeMdSrc = path.join(resourcesDir, 'CLAUDE.md');
  if (fs.existsSync(claudeMdSrc)) {
    try {
      fs.copyFileSync(claudeMdSrc, path.join(squirrelRoot, 'CLAUDE.md'));
      console.log('[Main] Deployed: CLAUDE.md');
    } catch (err) {
      console.error('[Main] Deploy error for CLAUDE.md:', err);
    }
  }

  // data/schema_v2.sql のみコピー（data/aipm.db は保護）
  const dataDir = path.join(squirrelRoot, 'data');
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

  // ORDER_164: パッケージ版起動時にresources/内リソースをSquirrelルートに展開
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

  // ORDER_164: ターミナル起動IPCハンドラ
  ipcMain.handle('terminal:open', () => {
    const cwd = configService.getActiveFrameworkPath();
    console.log('[Main] Opening terminal at:', cwd);
    spawn('cmd.exe', ['/c', 'start', 'cmd.exe'], {
      cwd,
      detached: true,
      stdio: 'ignore',
    });
  });

  createWindow();
});

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
