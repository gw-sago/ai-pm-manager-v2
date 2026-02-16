/**
 * aipm_auto Log IPC Handlers
 *
 * aipm_autoの実行ログを監視・取得するためのIPC通信ハンドラ
 * ORDER_050: aipm_autoの実行ログをダッシュボードから確認可能にする
 *
 * IPC チャンネル:
 * - aipm-auto-log:list-directories - ログディレクトリ一覧取得
 * - aipm-auto-log:list-files - ログファイル一覧取得
 * - aipm-auto-log:read-file - ログファイル内容取得
 * - aipm-auto-log:watch-start - ログ監視開始
 * - aipm-auto-log:watch-stop - ログ監視停止
 * - aipm-auto-log:watch-status - 監視状態取得
 * - aipm-auto-log:update - ログ更新通知（イベント）
 */

import { ipcMain, BrowserWindow } from 'electron';
import {
  getAipmAutoLogService,
  type LogFileInfo,
  type LogContent,
  type LogUpdateEvent,
  type LogWatcherStatus,
} from './services/AipmAutoLogService';

/**
 * aipm_autoログIPCハンドラを登録
 */
export function registerAipmAutoLogHandlers(): void {
  const logService = getAipmAutoLogService();

  // ログディレクトリ一覧取得
  ipcMain.handle(
    'aipm-auto-log:list-directories',
    async (): Promise<Array<{ projectName: string; logDir: string; exists: boolean }>> => {
      console.log('[AipmAutoLog IPC] list-directories');
      return logService.getLogDirectories();
    }
  );

  // ログファイル一覧取得
  ipcMain.handle(
    'aipm-auto-log:list-files',
    async (
      _event,
      projectName: string,
      orderId?: string
    ): Promise<LogFileInfo[]> => {
      console.log(`[AipmAutoLog IPC] list-files: ${projectName}, orderId: ${orderId || 'all'}`);
      if (orderId) {
        return logService.listLogFiles(projectName, orderId);
      }
      return logService.listAllLogFiles(projectName);
    }
  );

  // ログファイル内容取得
  ipcMain.handle(
    'aipm-auto-log:read-file',
    async (
      _event,
      filePath: string,
      options?: { tailLines?: number; fromPosition?: number }
    ): Promise<LogContent | null> => {
      console.log(`[AipmAutoLog IPC] read-file: ${filePath}`, options);
      return logService.readLogFile(filePath, options);
    }
  );

  // 最新ログファイル取得
  ipcMain.handle(
    'aipm-auto-log:get-latest',
    async (_event, projectName: string): Promise<LogFileInfo | null> => {
      console.log(`[AipmAutoLog IPC] get-latest: ${projectName}`);
      return logService.getLatestLogFile(projectName);
    }
  );

  // ログ監視開始
  ipcMain.handle(
    'aipm-auto-log:watch-start',
    async (
      _event,
      projectName: string
    ): Promise<{ success: boolean; error?: string }> => {
      console.log(`[AipmAutoLog IPC] watch-start: ${projectName}`);
      return logService.startWatching(projectName);
    }
  );

  // ログ監視停止
  ipcMain.handle('aipm-auto-log:watch-stop', async (): Promise<void> => {
    console.log('[AipmAutoLog IPC] watch-stop');
    logService.stopWatching();
  });

  // 監視状態取得
  ipcMain.handle(
    'aipm-auto-log:watch-status',
    async (): Promise<LogWatcherStatus> => {
      return logService.getStatus();
    }
  );

  // ログ更新イベントをレンダラーに転送
  logService.on('update', (event: LogUpdateEvent) => {
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('aipm-auto-log:update', event);
      }
    });
  });

  // 監視準備完了イベント
  logService.on('ready', () => {
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('aipm-auto-log:ready');
      }
    });
  });

  // エラーイベント
  logService.on('error', (error: Error) => {
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('aipm-auto-log:error', { message: error.message });
      }
    });
  });

  // 監視停止イベント
  logService.on('stopped', () => {
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('aipm-auto-log:stopped');
      }
    });
  });

  console.log('[AipmAutoLog] IPC handlers registered');
}

/**
 * アプリケーション終了時のクリーンアップ
 */
export function cleanupAipmAutoLog(): void {
  const logService = getAipmAutoLogService();
  logService.stopWatching();
}
