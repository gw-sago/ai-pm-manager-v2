import { app, BrowserWindow, dialog } from 'electron';
import path from 'node:path';
import fs from 'node:fs';
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

// DB初期化エラー情報を保持（レンダラーへの通知用）
let dbInitError: string | null = null;

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

  // Open the DevTools (temporarily always open for debugging)
  mainWindow.webContents.openDevTools();
};

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.on('ready', async () => {
  // V2統合: PROJECTSディレクトリを確保
  const configService = getConfigService();
  configService.ensureProjectsDirectory();
  console.log('[Main] Framework path:', configService.getActiveFrameworkPath());

  // Initialize database (data/aipm.db に一元化)
  let dbInitialized = false;
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

    // ユーザーにエラーを通知
    dialog.showErrorBox(
      'Database Initialization Error',
      `Failed to initialize database.\n\n` +
        `Error: ${errorMessage}\n\n` +
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
