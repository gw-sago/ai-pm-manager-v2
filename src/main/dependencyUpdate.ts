/**
 * Dependency Update IPC Handlers
 *
 * タスク依存関係の更新通知を処理するIPCハンドラ
 * ORDER_122 / TASK_1103
 */

import { ipcMain, BrowserWindow } from 'electron';
import { spawn } from 'child_process';
import * as path from 'node:path';
import * as fs from 'node:fs';
import { getConfigService } from './services/ConfigService';

export interface TaskDependencyStatus {
  taskId: string;
  projectId: string;
  status: string;
  title: string;
  isBlocked: boolean;
  dependencies: Array<{
    taskId: string;
    title: string;
    status: string;
    isCompleted: boolean;
  }>;
  completedCount: number;
  totalCount: number;
  completionRate: number;
}

export interface DependencyUpdateEvent {
  projectId: string;
  orderId: string;
  taskId: string;
  dependencyStatus: TaskDependencyStatus;
  timestamp: string;
}

/**
 * 依存関係状態を取得（Python APIを呼び出し）
 */
export async function fetchDependencyStatus(
  projectId: string,
  taskId?: string,
  orderId?: string
): Promise<TaskDependencyStatus[]> {
  const configService = getConfigService();
  const frameworkPath = configService.getActiveFrameworkPath();

  if (!frameworkPath) {
    console.error('[DependencyUpdate] Framework path not set');
    return [];
  }

  const scriptsDir = path.join(frameworkPath, 'backend');
  const pythonScript = path.join(scriptsDir, 'portfolio', 'dependency_status.py');

  return new Promise((resolve, reject) => {
    const args = ['-m', 'portfolio.dependency_status', projectId];

    if (taskId) {
      args.push(taskId);
    } else if (orderId) {
      args.push('--order', orderId);
    } else {
      args.push('--all');
    }

    args.push('--json');

    console.log('[DependencyUpdate] Executing:', 'python', args.join(' '));

    const proc = spawn('python', args, {
      cwd: scriptsDir,
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
      },
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    proc.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    proc.on('close', (code) => {
      if (code !== 0) {
        console.error('[DependencyUpdate] Python script failed:', stderr);
        reject(new Error(`Dependency status fetch failed with code ${code}`));
        return;
      }

      try {
        const result = JSON.parse(stdout);

        if (!result.success) {
          console.error('[DependencyUpdate] API error:', result.error);
          reject(new Error(result.error));
          return;
        }

        // 単一タスクの場合
        if (result.dependency_status) {
          resolve([
            {
              taskId: result.dependency_status.task_id,
              projectId: result.dependency_status.project_id,
              status: result.dependency_status.status,
              title: result.dependency_status.title,
              isBlocked: result.dependency_status.is_blocked,
              dependencies: result.dependency_status.dependencies,
              completedCount: result.dependency_status.completed_count,
              totalCount: result.dependency_status.total_count,
              completionRate: result.dependency_status.completion_rate,
            },
          ]);
        }
        // 複数タスクの場合
        else if (Array.isArray(result.tasks)) {
          resolve(
            result.tasks.map((task: any) => ({
              taskId: task.task_id,
              projectId: task.project_id,
              status: task.status,
              title: task.title,
              isBlocked: task.is_blocked,
              dependencies: task.dependencies,
              completedCount: task.completed_count,
              totalCount: task.total_count,
              completionRate: task.completion_rate,
            }))
          );
        } else {
          resolve([]);
        }
      } catch (error) {
        console.error('[DependencyUpdate] JSON parse error:', error);
        reject(error);
      }
    });
  });
}

/**
 * 依存関係更新IPCハンドラを登録
 */
export function registerDependencyUpdateHandlers(): void {
  // タスク依存関係状態を取得
  ipcMain.handle(
    'dependency:get-status',
    async (
      _event,
      projectId: string,
      taskId?: string,
      orderId?: string
    ): Promise<TaskDependencyStatus[]> => {
      console.log(
        `[DependencyUpdate IPC] Get status: project=${projectId}, task=${taskId}, order=${orderId}`
      );

      try {
        return await fetchDependencyStatus(projectId, taskId, orderId);
      } catch (error) {
        console.error('[DependencyUpdate IPC] Failed to get dependency status:', error);
        return [];
      }
    }
  );

  // イベント監視を開始 (ORDER_140 / TASK_1168)
  ipcMain.handle(
    'dependency:start-monitoring',
    async (_event, projectId: string, orderId: string): Promise<{ success: boolean }> => {
      console.log(`[DependencyUpdate IPC] Start monitoring: ${projectId}/${orderId}`);
      try {
        startEventMonitoring(projectId, orderId);
        return { success: true };
      } catch (error) {
        console.error('[DependencyUpdate IPC] Failed to start monitoring:', error);
        return { success: false };
      }
    }
  );

  // イベント監視を停止 (ORDER_140 / TASK_1168)
  ipcMain.handle(
    'dependency:stop-monitoring',
    async (_event, projectId: string, orderId: string): Promise<{ success: boolean }> => {
      console.log(`[DependencyUpdate IPC] Stop monitoring: ${projectId}/${orderId}`);
      try {
        stopEventMonitoring(projectId, orderId);
        return { success: true };
      } catch (error) {
        console.error('[DependencyUpdate IPC] Failed to stop monitoring:', error);
        return { success: false };
      }
    }
  );

  console.log('[DependencyUpdate] IPC handlers registered');
}

/**
 * 依存関係更新イベントを全ウィンドウに送信
 */
export function broadcastDependencyUpdate(event: DependencyUpdateEvent): void {
  const windows = BrowserWindow.getAllWindows();
  windows.forEach((win) => {
    if (!win.isDestroyed()) {
      win.webContents.send('dependency:update', event);
    }
  });

  console.log(
    `[DependencyUpdate] Broadcasted update: ${event.taskId} (${event.projectId}/${event.orderId})`
  );
}

// ============================================================
// Event File Monitoring (ORDER_140 / TASK_1168)
// ============================================================

// Map of active watchers: {projectId/orderId -> FSWatcher}
const eventWatchers = new Map<string, fs.FSWatcher>();

// Map to track processed event files to avoid duplicates
const processedEventFiles = new Set<string>();

/**
 * イベントファイルをパースして依存関係更新イベントに変換
 */
function parseEventFile(eventFilePath: string): DependencyUpdateEvent | null {
  try {
    const content = fs.readFileSync(eventFilePath, 'utf-8');
    const eventData = JSON.parse(content);

    // Only process DEPENDENCY_RESOLVED events
    if (eventData.event_type !== 'DEPENDENCY_RESOLVED') {
      return null;
    }

    // Fetch dependency status for the task
    const { project_id, order_id, task_id } = eventData;

    // Return a placeholder event - actual dependency status will be fetched asynchronously
    return {
      projectId: project_id,
      orderId: order_id,
      taskId: task_id,
      dependencyStatus: {
        taskId: task_id,
        projectId: project_id,
        status: 'UNKNOWN',
        title: '',
        isBlocked: false,
        dependencies: [],
        completedCount: 0,
        totalCount: 0,
        completionRate: 0,
      },
      timestamp: eventData.timestamp || new Date().toISOString(),
    };
  } catch (error) {
    console.error('[DependencyUpdate] Failed to parse event file:', eventFilePath, error);
    return null;
  }
}

/**
 * イベントディレクトリを監視して依存関係更新を検出
 */
export function startEventMonitoring(projectId: string, orderId: string): void {
  const configService = getConfigService();
  const frameworkPath = configService.getActiveFrameworkPath();

  if (!frameworkPath) {
    console.error('[DependencyUpdate] Framework path not set, cannot start monitoring');
    return;
  }

  const watchKey = `${projectId}/${orderId}`;

  // すでに監視中なら停止
  if (eventWatchers.has(watchKey)) {
    console.log(`[DependencyUpdate] Already watching ${watchKey}, stopping first`);
    stopEventMonitoring(projectId, orderId);
  }

  const eventsDir = path.join(
    frameworkPath,
    'PROJECTS',
    projectId,
    'RESULT',
    orderId,
    'LOGS',
    'events'
  );

  // ディレクトリが存在しない場合は作成
  if (!fs.existsSync(eventsDir)) {
    try {
      fs.mkdirSync(eventsDir, { recursive: true });
      console.log(`[DependencyUpdate] Created events directory: ${eventsDir}`);
    } catch (error) {
      console.error('[DependencyUpdate] Failed to create events directory:', error);
      return;
    }
  }

  console.log(`[DependencyUpdate] Starting event monitoring for ${watchKey}: ${eventsDir}`);

  try {
    const watcher = fs.watch(eventsDir, async (eventType, filename) => {
      if (!filename || !filename.startsWith('event_') || !filename.endsWith('.json')) {
        return;
      }

      const eventFilePath = path.join(eventsDir, filename);
      const fileKey = `${watchKey}:${filename}`;

      // 重複処理を防ぐ
      if (processedEventFiles.has(fileKey)) {
        return;
      }

      processedEventFiles.add(fileKey);

      // ファイルが完全に書き込まれるまで少し待つ
      await new Promise((resolve) => setTimeout(resolve, 100));

      // ファイルが存在するか確認
      if (!fs.existsSync(eventFilePath)) {
        return;
      }

      console.log(`[DependencyUpdate] Detected event file: ${filename}`);

      // イベントファイルをパース
      const event = parseEventFile(eventFilePath);
      if (!event) {
        return;
      }

      // 依存関係ステータスを取得してイベントを更新
      try {
        const statusList = await fetchDependencyStatus(event.projectId, event.taskId);
        if (statusList.length > 0) {
          event.dependencyStatus = statusList[0];
        }

        // レンダラープロセスにイベントをブロードキャスト
        broadcastDependencyUpdate(event);
      } catch (error) {
        console.error('[DependencyUpdate] Failed to fetch dependency status:', error);
      }
    });

    eventWatchers.set(watchKey, watcher);
    console.log(`[DependencyUpdate] Event monitoring started for ${watchKey}`);
  } catch (error) {
    console.error('[DependencyUpdate] Failed to start event monitoring:', error);
  }
}

/**
 * イベントディレクトリの監視を停止
 */
export function stopEventMonitoring(projectId: string, orderId: string): void {
  const watchKey = `${projectId}/${orderId}`;
  const watcher = eventWatchers.get(watchKey);

  if (watcher) {
    watcher.close();
    eventWatchers.delete(watchKey);
    console.log(`[DependencyUpdate] Event monitoring stopped for ${watchKey}`);
  }

  // 処理済みファイルリストをクリーンアップ
  const prefix = `${watchKey}:`;
  const fileKeys = Array.from(processedEventFiles);
  for (const fileKey of fileKeys) {
    if (fileKey.startsWith(prefix)) {
      processedEventFiles.delete(fileKey);
    }
  }
}

/**
 * すべてのイベント監視を停止
 */
export function stopAllEventMonitoring(): void {
  const entries = Array.from(eventWatchers.entries());
  for (const [watchKey, watcher] of entries) {
    watcher.close();
    console.log(`[DependencyUpdate] Event monitoring stopped for ${watchKey}`);
  }
  eventWatchers.clear();
  processedEventFiles.clear();
}

/**
 * クリーンアップ（必要に応じて）
 */
export function cleanupDependencyUpdate(): void {
  stopAllEventMonitoring();
  console.log('[DependencyUpdate] Cleanup completed');
}
