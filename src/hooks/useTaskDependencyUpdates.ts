/**
 * Task Dependency Real-time Updates Hook
 *
 * タスク状態変更イベントを受信し、依存関係UIを自動更新するカスタムフック
 * ORDER_122 / TASK_1103
 */

import { useEffect, useState, useCallback } from 'react';

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

export interface TaskDependencyUpdate {
  projectId: string;
  orderId: string;
  taskId: string;
  dependencyStatus: TaskDependencyStatus;
  timestamp: string;
}

/**
 * タスク依存関係のリアルタイム更新を監視するフック
 *
 * @param projectId 監視対象のプロジェクトID
 * @param orderId 監視対象のORDER ID
 * @returns 依存関係状態のマップと更新関数
 */
export function useTaskDependencyUpdates(
  projectId: string | null,
  orderId: string | null
) {
  const [dependencyMap, setDependencyMap] = useState<Map<string, TaskDependencyStatus>>(
    new Map()
  );
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  /**
   * 依存関係状態を手動でリフレッシュ
   */
  const refresh = useCallback(async () => {
    if (!projectId || !orderId) return;
    if (!window.electronAPI) {
      console.error('[useTaskDependencyUpdates] electronAPI not available');
      return;
    }

    setIsLoading(true);
    try {
      // IPC経由でPython APIを呼び出して依存関係状態を取得
      const tasks = await window.electronAPI.getDependencyStatus(projectId, undefined, orderId);

      if (Array.isArray(tasks)) {
        const newMap = new Map<string, TaskDependencyStatus>();

        for (const task of tasks) {
          newMap.set(task.taskId, {
            taskId: task.taskId,
            projectId: task.projectId,
            status: task.status,
            title: task.title,
            isBlocked: task.isBlocked,
            dependencies: task.dependencies,
            completedCount: task.completedCount,
            totalCount: task.totalCount,
            completionRate: task.completionRate,
          });
        }

        setDependencyMap(newMap);
        setLastUpdate(new Date());
      }
    } catch (error) {
      console.error('[useTaskDependencyUpdates] Error refreshing dependencies:', error);
    } finally {
      setIsLoading(false);
    }
  }, [projectId, orderId]);

  /**
   * タスク状態変更イベントを処理
   */
  const handleTaskStatusChange = useCallback(
    (data: {
      taskId: string;
      projectId: string;
      orderId: string;
      newStatus: string;
    }) => {
      // 監視対象のORDERでない場合はスキップ
      if (data.projectId !== projectId || data.orderId !== orderId) {
        return;
      }

      console.log(
        `[useTaskDependencyUpdates] Task status changed: ${data.taskId} → ${data.newStatus}`
      );

      // タスク完了系のステータスの場合、依存関係を再計算
      if (['COMPLETED', 'DONE', 'SKIPPED'].includes(data.newStatus)) {
        // 依存関係状態をリフレッシュ（非同期）
        refresh();
      }
    },
    [projectId, orderId, refresh]
  );

  /**
   * EventNotifier経由の依存関係解決イベントを処理
   */
  const handleDependencyResolved = useCallback(
    (data: { projectId: string; orderId: string; taskId: string }) => {
      if (data.projectId !== projectId || data.orderId !== orderId) {
        return;
      }

      console.log(
        `[useTaskDependencyUpdates] Dependency resolved for task: ${data.taskId}`
      );

      // 依存関係状態をリフレッシュ
      refresh();
    },
    [projectId, orderId, refresh]
  );

  // 初回ロード
  useEffect(() => {
    if (projectId && orderId) {
      refresh();
    }
  }, [projectId, orderId, refresh]);

  // イベントリスナーの登録
  useEffect(() => {
    if (!window.electronAPI) return;

    // タスク状態変更イベントを購読
    const unsubscribeStatus = window.electronAPI.onTaskStatusChanged(
      handleTaskStatusChange
    );

    // EventNotifier経由の依存関係更新イベントを購読
    const unsubscribeDependency = window.electronAPI.onDependencyUpdate(
      handleDependencyResolved
    );

    // クリーンアップ
    return () => {
      unsubscribeStatus();
      unsubscribeDependency();
    };
  }, [handleTaskStatusChange, handleDependencyResolved]);

  // イベント監視の開始・停止
  useEffect(() => {
    if (!window.electronAPI || !projectId || !orderId) return;

    // イベントファイル監視を開始
    window.electronAPI.startDependencyMonitoring(projectId, orderId).then((result) => {
      if (result.success) {
        console.log(`[useTaskDependencyUpdates] Monitoring started for ${projectId}/${orderId}`);
      }
    }).catch((error) => {
      console.error('[useTaskDependencyUpdates] Failed to start monitoring:', error);
    });

    // クリーンアップ: 監視を停止
    return () => {
      window.electronAPI.stopDependencyMonitoring(projectId, orderId).catch((error) => {
        console.error('[useTaskDependencyUpdates] Failed to stop monitoring:', error);
      });
    };
  }, [projectId, orderId]);

  return {
    dependencyMap,
    lastUpdate,
    isLoading,
    refresh,
  };
}
