/**
 * ファイル監視 IPC ハンドラ
 *
 * レンダラープロセスからファイル監視を制御するためのIPCハンドラを提供します。
 *
 * IPC チャンネル:
 * - watcher:start - 監視開始
 * - watcher:stop - 監視停止
 * - watcher:status - 監視状態取得
 * - watcher:on-change - 変更通知（イベント）
 */

import { ipcMain, BrowserWindow } from 'electron';
import {
  fileWatcherService,
  type FileChangeEvent,
  type WatcherStatus,
} from './services/FileWatcherService';

/**
 * ファイル監視IPCハンドラを登録
 */
export function registerWatcherHandlers(): void {
  // 監視開始
  ipcMain.handle(
    'watcher:start',
    async (
      _event,
      frameworkPath: string
    ): Promise<{ success: boolean; error?: string }> => {
      console.log(`[Watcher IPC] 監視開始リクエスト: ${frameworkPath}`);
      return fileWatcherService.start(frameworkPath);
    }
  );

  // 監視停止
  ipcMain.handle('watcher:stop', async (): Promise<void> => {
    console.log('[Watcher IPC] 監視停止リクエスト');
    fileWatcherService.stop();
  });

  // 監視状態取得
  ipcMain.handle('watcher:status', async (): Promise<WatcherStatus> => {
    return fileWatcherService.getStatus();
  });

  // ファイル変更イベントをレンダラーに転送
  fileWatcherService.on('change', (event: FileChangeEvent) => {
    // 全てのウィンドウに変更を通知
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('watcher:on-change', event);
      }
    });
  });

  // 監視準備完了イベント
  fileWatcherService.on('ready', () => {
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('watcher:ready');
      }
    });
  });

  // エラーイベント
  fileWatcherService.on('error', (error: Error) => {
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('watcher:error', { message: error.message });
      }
    });
  });

  // 監視停止イベント
  fileWatcherService.on('stopped', () => {
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('watcher:stopped');
      }
    });
  });

  console.log('[Watcher] IPC handlers registered');
}

/**
 * アプリケーション終了時のクリーンアップ
 */
export function cleanupWatcher(): void {
  fileWatcherService.stop();
}
