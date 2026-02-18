/**
 * Script IPC Handlers
 *
 * スクリプト実行のためのIPC通信ハンドラ
 * ORDER_039: ワンクリック自動実行機能
 */

import { ipcMain, BrowserWindow, Notification } from 'electron';
import {
  getScriptExecutionService,
  type ExecutionResult,
  type ExecutionProgress,
  type WorkerLogFileInfo,
  type WorkerLogContent,
  type WorkerLogUpdateEvent,
} from './services/ScriptExecutionService';
import { getNotificationService } from './services/NotificationService';
import { broadcastDependencyUpdate, fetchDependencyStatus } from './dependencyUpdate';

/**
 * IPC ハンドラを登録
 */
export function registerScriptHandlers(): void {
  const scriptService = getScriptExecutionService();

  // PM処理実行
  ipcMain.handle(
    'script:execute-pm',
    async (_event, projectId: string, backlogId: string): Promise<ExecutionResult> => {
      console.log('[Script] execute-pm called:', { projectId, backlogId });
      return scriptService.executePmProcess(projectId, backlogId);
    }
  );

  // Worker処理実行
  ipcMain.handle(
    'script:execute-worker',
    async (_event, projectId: string, orderId: string): Promise<ExecutionResult> => {
      console.log('[Script] execute-worker called:', { projectId, orderId });
      return scriptService.executeWorkerProcess(projectId, orderId);
    }
  );

  // 実行中ジョブ一覧取得
  ipcMain.handle('script:get-running-jobs', async () => {
    return scriptService.getRunningJobs();
  });

  // 実行中かどうか確認
  ipcMain.handle(
    'script:is-running',
    async (_event, projectId: string, targetId: string): Promise<boolean> => {
      return scriptService.isRunning(projectId, targetId);
    }
  );

  // ジョブキャンセル
  ipcMain.handle(
    'script:cancel',
    async (_event, executionId: string): Promise<boolean> => {
      console.log('[Script] cancel called:', executionId);
      return scriptService.cancelJob(executionId);
    }
  );

  // 実行履歴取得（ORDER_040追加）
  ipcMain.handle('script:get-execution-history', async (): Promise<ExecutionResult[]> => {
    return scriptService.getExecutionHistory();
  });

  // 実行履歴クリア（ORDER_040追加）
  ipcMain.handle('script:clear-execution-history', async (): Promise<void> => {
    scriptService.clearExecutionHistory();
  });

  // ORDER_098: 並列タスク検出
  ipcMain.handle(
    'script:detect-parallel-tasks',
    async (_event, projectId: string, orderId: string, maxTasks?: number): Promise<{
      success: boolean;
      tasks?: Array<{ id: string; title: string; status: string }>;
      error?: string;
    }> => {
      console.log('[Script] detect-parallel-tasks called:', { projectId, orderId, maxTasks });
      return scriptService.detectParallelTasks(projectId, orderId, maxTasks);
    }
  );

  // ORDER_101: タスクステータス取得（ポーリング用）
  ipcMain.handle(
    'script:get-task-statuses',
    async (_event, projectId: string, orderId: string) => {
      return scriptService.getTaskStatuses(projectId, orderId);
    }
  );

  // ORDER_101: タスクポーリング開始
  ipcMain.handle(
    'script:start-task-polling',
    async (_event, projectId: string, orderId: string, intervalMs?: number) => {
      scriptService.startTaskPolling(projectId, orderId, intervalMs);
      return { success: true };
    }
  );

  // ORDER_101: タスクポーリング停止
  ipcMain.handle('script:stop-task-polling', async () => {
    scriptService.stopTaskPolling();
    return { success: true };
  });

  // ORDER_119: タスク実行ステップ取得
  ipcMain.handle(
    'script:get-task-execution-steps',
    async (_event, projectId: string, taskId: string) => {
      return scriptService.getTaskExecutionSteps(projectId, taskId);
    }
  );

  // ORDER_155 TASK_1230: ORDER再実行
  ipcMain.handle(
    'script:retry-order',
    async (
      _event,
      projectId: string,
      orderId: string,
      options?: { timeout?: number; model?: string; verbose?: boolean }
    ): Promise<ExecutionResult> => {
      console.log('[Script] retry-order called:', { projectId, orderId, options });
      return scriptService.retryOrder(projectId, orderId, options);
    }
  );

  // ORDER_111: Worker ログファイル一覧取得
  ipcMain.handle(
    'script:get-worker-logs',
    async (_event, projectId: string, orderId?: string): Promise<WorkerLogFileInfo[]> => {
      console.log('[Script] get-worker-logs called:', { projectId, orderId });
      return scriptService.getWorkerLogFiles(projectId, orderId);
    }
  );

  // ORDER_111: Worker ログファイル内容読み込み
  ipcMain.handle(
    'script:read-worker-log',
    async (
      _event,
      filePath: string,
      options?: { tailLines?: number; fromPosition?: number }
    ): Promise<WorkerLogContent | null> => {
      console.log('[Script] read-worker-log called:', { filePath, options });
      return scriptService.readWorkerLogFile(filePath, options);
    }
  );

  // ORDER_111: Worker ログファイル監視開始
  ipcMain.handle(
    'script:watch-worker-log',
    async (_event, filePath: string): Promise<void> => {
      console.log('[Script] watch-worker-log called:', filePath);
      scriptService.watchWorkerLog(filePath);
    }
  );

  // ORDER_111: Worker ログファイル監視停止
  ipcMain.handle(
    'script:unwatch-worker-log',
    async (_event, filePath: string): Promise<void> => {
      console.log('[Script] unwatch-worker-log called:', filePath);
      scriptService.unwatchWorkerLog(filePath);
    }
  );

  // ORDER_111: Worker ログ更新イベントをレンダラーに転送
  scriptService.on('worker-log-update', (data: WorkerLogUpdateEvent) => {
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      if (!win.isDestroyed()) {
        win.webContents.send('script:worker-log-update', data);
      }
    }
  });

  // 進捗イベントをレンダラーに転送
  scriptService.on('progress', (progress: ExecutionProgress) => {
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      win.webContents.send('script:progress', progress);
    }
  });

  // 完了イベントをレンダラーに転送 + デスクトップ通知 + メニュー更新 + DB変更通知
  scriptService.on('complete', (result: ExecutionResult) => {
    // レンダラーに転送
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      win.webContents.send('script:complete', result);

      // ORDER_063: 左メニュー自動更新イベントを発火
      // PM/Worker/Review完了時にサイドバーのプロジェクト一覧・ORDER一覧を更新
      win.webContents.send('menu:update');
      console.log('[Script] menu:update event sent');

      // ORDER_004 TASK_009: DB変更通知
      // スクリプト実行完了時にDB変更を通知し、レンダラー側でデータを再取得させる
      win.webContents.send('db:changed', {
        source: result.type || 'unknown',
        projectId: result.projectId || '',
        targetId: result.targetId || '',
        timestamp: new Date().toISOString(),
      });
      console.log('[Script] db:changed event sent:', { source: result.type, projectId: result.projectId, targetId: result.targetId });
    }

    // デスクトップ通知を表示
    const notificationService = getNotificationService();
    notificationService.showExecutionResult(result);
  });

  // ORDER_101: タスクステータス変更イベントをレンダラーに転送
  scriptService.on('task-status-changed', (data) => {
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      win.webContents.send('script:task-status-changed', data);

      // ORDER_004 TASK_009: タスクステータス変更時もDB変更を通知
      win.webContents.send('db:changed', {
        source: 'task-status-changed',
        projectId: data.projectId || '',
        targetId: data.taskId || '',
        timestamp: new Date().toISOString(),
      });
    }

    // TASK_1103: タスク完了時に依存関係更新を通知
    if (['COMPLETED', 'DONE', 'SKIPPED'].includes(data.newStatus)) {
      console.log(
        `[Script] Task ${data.taskId} completed, triggering dependency update`
      );
      // 依存関係更新イベントを発行（非同期でステータスを取得して通知）
      fetchDependencyStatus(data.projectId, data.taskId)
        .then((statuses: any[]) => {
          if (statuses.length > 0) {
            broadcastDependencyUpdate({
              projectId: data.projectId,
              orderId: data.orderId,
              taskId: data.taskId,
              dependencyStatus: statuses[0],
              timestamp: new Date().toISOString(),
            });
          }
        })
        .catch((error: Error) => {
          console.error(
            `[Script] Failed to get dependency status for ${data.taskId}:`,
            error
          );
        });
    }
  });

  // ORDER_101 TASK_971: task-timeout event forwarding
  scriptService.on('task-timeout', (data) => {
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      win.webContents.send('script:task-timeout', data);
    }
  });

  // ORDER_101 TASK_971: task-error event forwarding
  scriptService.on('task-error', (data) => {
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      win.webContents.send('script:task-error', data);
    }
  });

  // ORDER_101: 全タスク完了イベントをレンダラーに転送
  scriptService.on('all-tasks-completed', (data) => {
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      win.webContents.send('script:all-tasks-completed', data);
      win.webContents.send('menu:update');

      // ORDER_004 TASK_009: 全タスク完了時もDB変更を通知
      win.webContents.send('db:changed', {
        source: 'all-tasks-completed',
        projectId: data.projectId || '',
        targetId: data.orderId || '',
        timestamp: new Date().toISOString(),
      });
    }
  });

  // ORDER_109: タスククラッシュイベントをレンダラーに転送 + デスクトップ通知
  scriptService.on('task-crash', (data: {
    taskId: string;
    projectId: string;
    orderId: string;
    pid: number;
    logFile: string;
    message: string;
  }) => {
    // レンダラーに転送
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      win.webContents.send('script:task-crash', data);
      win.webContents.send('menu:update');

      // ORDER_004 TASK_009: タスククラッシュ時もDB変更を通知
      win.webContents.send('db:changed', {
        source: 'task-crash',
        projectId: data.projectId || '',
        targetId: data.taskId || '',
        timestamp: new Date().toISOString(),
      });
    }

    // デスクトップ通知を表示
    if (Notification.isSupported()) {
      const notification = new Notification({
        title: 'Worker異常終了',
        body: `${data.taskId}: プロセスが異常終了しました`,
        silent: false,
      });
      notification.show();
    }

    console.log(`[Script] Task crash notification sent for ${data.taskId} (PID: ${data.pid})`);
  });

  console.log('[Script] IPC handlers registered');
}
