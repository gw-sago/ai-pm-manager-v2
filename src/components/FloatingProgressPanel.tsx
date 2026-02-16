/**
 * FloatingProgressPanel - フローティング進捗パネル
 *
 * バックグラウンドで実行中のPM/Worker処理の進捗をリアルタイム表示する
 * 画面下部に固定表示され、他の画面操作を妨げない
 *
 * ORDER_101 (TASK_970): 並列Worker非同期起動時のタスクステータスポーリング表示を追加
 *
 * @module FloatingProgressPanel
 * @created 2026-02-05
 * @order ORDER_042, ORDER_101
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { ExecutionProgress, ExecutionResult } from '../preload';

// =============================================================================
// 型定義
// =============================================================================

interface RunningJob {
  executionId: string;
  type: 'pm' | 'worker';
  projectId: string;
  targetId: string;
  status: 'running' | 'completed' | 'failed';
  startedAt: Date;
  lastOutput?: string;
  error?: string;
}

// ORDER_101: 並列実行タスクの型定義
interface ParallelTask {
  id: string;
  title: string;
  status: string;
  startedAt: Date;
  /** ORDER_109: エラーメッセージ（クラッシュ検知時） */
  errorMessage?: string;
  /** ORDER_109: ログファイルパス（クラッシュ検知時） */
  logFile?: string;
  /** ORDER_128: 最新ログ行 */
  latestLogLine?: string;
  /** ORDER_128: 進捗ステップ情報 */
  currentStep?: string | null;
  stepIndex?: number;
  totalSteps?: number;
  progressPercent?: number;
}

// =============================================================================
// メインコンポーネント
// =============================================================================

export const FloatingProgressPanel: React.FC = () => {
  const [jobs, setJobs] = useState<Map<string, RunningJob>>(new Map());
  const [isExpanded, setIsExpanded] = useState(true);
  const [isMinimized, setIsMinimized] = useState(false);

  // ORDER_101: 並列実行タスクのステータス管理
  const [parallelTasks, setParallelTasks] = useState<Map<string, ParallelTask>>(new Map());
  const [allTasksCompletedMessage, setAllTasksCompletedMessage] = useState<string | null>(null);

  // ORDER_101 TASK_971: task warnings (timeout/error)
  const [taskWarnings, setTaskWarnings] = useState<Map<string, string>>(new Map());
  const pollingCleanupRef = useRef<boolean>(false);

  // ORDER_128: タスクローテーション表示用（複数並列タスク時）
  const [rotationIndex, setRotationIndex] = useState(0);

  // 進捗イベントをリッスン
  useEffect(() => {
    const unsubscribeProgress = window.electronAPI.onExecutionProgress((progress: ExecutionProgress) => {
      console.log('[FloatingProgressPanel] Progress received:', progress);

      setJobs((prev) => {
        const next = new Map(prev);
        const existing = next.get(progress.executionId);

        if (progress.status === 'running') {
          next.set(progress.executionId, {
            executionId: progress.executionId,
            type: progress.type,
            projectId: progress.projectId,
            targetId: progress.targetId,
            status: 'running',
            startedAt: existing?.startedAt || new Date(),
            lastOutput: progress.lastOutput || existing?.lastOutput,
          });
        }

        return next;
      });

      // 実行中のジョブがある場合、自動展開
      setIsMinimized(false);
    });

    const unsubscribeComplete = window.electronAPI.onExecutionComplete((result: ExecutionResult) => {
      console.log('[FloatingProgressPanel] Complete received:', result);

      setJobs((prev) => {
        const next = new Map(prev);
        const job = next.get(result.executionId);

        if (job) {
          next.set(result.executionId, {
            ...job,
            status: result.success ? 'completed' : 'failed',
            error: result.error,
          });

          // 5秒後に完了したジョブを削除
          setTimeout(() => {
            setJobs((current) => {
              const updated = new Map(current);
              updated.delete(result.executionId);
              return updated;
            });
          }, 5000);
        }

        return next;
      });

      // ORDER_101: start polling for parallel async launch
      if (result.success && result.type === "worker") {
        try {
          const meta = JSON.parse(result.stdout);
          if (meta.taskIds && Array.isArray(meta.taskIds) && meta.taskIds.length > 0) {
            console.log("[FloatingProgressPanel] Parallel launch detected:", meta.taskIds);
            const initialTasks = new Map<string, ParallelTask>();
            for (const tid of meta.taskIds) {
              initialTasks.set(tid, { id: tid, title: "", status: "IN_PROGRESS", startedAt: new Date() });
            }
            setParallelTasks(initialTasks);
            window.electronAPI.startTaskPolling(result.projectId, result.targetId).catch((err) => {
              console.error("[FloatingProgressPanel] Failed to start task polling:", err);
            });
          }
        } catch (_e) {
          // JSON parse failure ignored
        }
        // ORDER_098: detect via launched_tasks field
        if (result.launched_tasks && Array.isArray(result.launched_tasks) && result.launched_tasks.length > 0) {
          console.log("[FloatingProgressPanel] Parallel launch via launched_tasks:", result.launched_tasks);
          const lt = new Map<string, ParallelTask>();
          for (const task of result.launched_tasks) {
            lt.set(task.task_id, { id: task.task_id, title: task.title || "", status: "IN_PROGRESS", startedAt: new Date() });
          }
          setParallelTasks((prev) => {
            const merged = new Map(prev);
            for (const [id, task] of lt) {
              const existing = merged.get(id);
              merged.set(id, existing ? { ...existing, title: task.title || existing.title } : task);
            }
            return merged;
          });
          window.electronAPI.startTaskPolling(result.projectId, result.targetId).catch((err) => {
            console.error("[FloatingProgressPanel] Failed to start task polling:", err);
          });
        }
      }
    });

    // ORDER_101: task status change event
    const unsubTaskChange = window.electronAPI.onTaskStatusChanged((data) => {
      console.log("[FloatingProgressPanel] Task status changed:", data);
      setParallelTasks((prev) => {
        const next = new Map(prev);
        const existing = next.get(data.taskId);
        next.set(data.taskId, {
          id: data.taskId,
          title: data.title || existing?.title || "",
          status: data.newStatus,
          startedAt: existing?.startedAt || new Date(),
        });
        return next;
      });
    });

    // ORDER_101: all tasks completed event
    const unsubAllComplete = window.electronAPI.onAllTasksCompleted((data) => {
      console.log("[FloatingProgressPanel] All tasks completed:", data);
      window.electronAPI.stopTaskPolling().catch((err) => {
        console.error("[FloatingProgressPanel] Failed to stop task polling:", err);
      });
      setAllTasksCompletedMessage(
        "全 " + data.tasks.length + " タスク完了 (" + data.orderId + ")"
      );
      setTimeout(() => {
        setParallelTasks(new Map());
        setAllTasksCompletedMessage(null);
      }, 5000);
    });

    // ORDER_101 TASK_971: task timeout warning
    const unsubTimeout = window.electronAPI.onTaskTimeout((data) => {
      console.warn('[FloatingProgressPanel] Task timeout:', data);
      setTaskWarnings(prev => {
        const next = new Map(prev);
        next.set(data.taskId, `タイムアウト警告: ${Math.round(data.elapsedMs / 60000)}分経過`);
        return next;
      });
    });

    // ORDER_101 TASK_971: task error
    const unsubError = window.electronAPI.onTaskError((data) => {
      console.error('[FloatingProgressPanel] Task error:', data);
      setTaskWarnings(prev => {
        const next = new Map(prev);
        next.set(data.taskId, `エラー: ${data.status}`);
        return next;
      });
      // ORDER_109: CRASHEDステータスの場合、parallelTasksにエラー情報を反映
      if (data.status === 'CRASHED') {
        setParallelTasks(prev => {
          const next = new Map(prev);
          const existing = next.get(data.taskId);
          next.set(data.taskId, {
            id: data.taskId,
            title: existing?.title || data.title || '',
            status: 'ERROR',
            startedAt: existing?.startedAt || new Date(),
            errorMessage: data.message || 'プロセス異常終了 - 自動復旧済み（QUEUED）',
            logFile: data.logFile,
          });
          return next;
        });
      }
    });

    // ORDER_109: task crash event (PID monitoring)
    const unsubCrash = window.electronAPI.onTaskCrash((data) => {
      console.error('[FloatingProgressPanel] Task crash detected:', data);
      setParallelTasks(prev => {
        const next = new Map(prev);
        const existing = next.get(data.taskId);
        next.set(data.taskId, {
          id: data.taskId,
          title: existing?.title || `PID ${data.pid}`,
          status: 'ERROR',
          startedAt: existing?.startedAt || new Date(),
          errorMessage: data.message || 'プロセス異常終了 - 自動復旧済み（QUEUED）',
          logFile: data.logFile,
        });
        return next;
      });
      setTaskWarnings(prev => {
        const next = new Map(prev);
        next.set(data.taskId, `クラッシュ検知 (PID: ${data.pid})`);
        return next;
      });
    });

    return () => {
      unsubscribeProgress();
      unsubscribeComplete();
      unsubTaskChange();
      unsubAllComplete();
      unsubTimeout();
      unsubError();
      unsubCrash();
    };
  }, []);

  // ORDER_101: stop polling on component unmount
  useEffect(() => {
    return () => {
      if (pollingCleanupRef.current) {
        window.electronAPI.stopTaskPolling().catch(() => {});
      }
    };
  }, []);

  // ORDER_101: track polling cleanup ref
  useEffect(() => {
    pollingCleanupRef.current = parallelTasks.size > 0;
  }, [parallelTasks]);

  // ORDER_128: ログ・進捗情報ポーリング（3-5秒間隔）
  useEffect(() => {
    if (parallelTasks.size === 0) return;

    const pollingInterval = 4000; // 4秒間隔
    let currentProjectId: string | null = null;
    let currentOrderId: string | null = null;

    // 実行中のプロジェクト・ORDERを特定
    for (const task of parallelTasks.values()) {
      if (task.status === 'IN_PROGRESS') {
        // タスクIDからプロジェクトとORDERを推測（既存のジョブ情報から取得）
        for (const job of jobs.values()) {
          if (job.type === 'worker' && job.status === 'running') {
            currentProjectId = job.projectId;
            currentOrderId = job.targetId;
            break;
          }
        }
        break;
      }
    }

    if (!currentProjectId || !currentOrderId) return;

    const fetchLogAndProgress = async () => {
      try {
        // 進捗情報を取得
        const progressInfo = await window.electronAPI.getTaskProgressInfo(
          currentProjectId!,
          currentOrderId!
        );

        if (progressInfo) {
          setParallelTasks(prev => {
            const next = new Map(prev);
            for (const runningTask of progressInfo.runningTasks) {
              const existing = next.get(runningTask.id);
              if (existing) {
                next.set(runningTask.id, {
                  ...existing,
                  currentStep: runningTask.currentStep,
                  stepIndex: runningTask.stepIndex,
                  totalSteps: runningTask.totalSteps,
                  progressPercent: runningTask.progressPercent,
                });
              }
            }
            return next;
          });
        }

        // 各タスクのログを取得
        for (const task of parallelTasks.values()) {
          if (task.status === 'IN_PROGRESS') {
            try {
              const logData = await window.electronAPI.getTaskLogTail(
                currentProjectId!,
                currentOrderId!,
                task.id,
                2 // 末尾2行を取得
              );

              if (logData && logData.logLines && logData.logLines.length > 0) {
                setParallelTasks(prev => {
                  const next = new Map(prev);
                  const existing = next.get(task.id);
                  if (existing) {
                    next.set(task.id, {
                      ...existing,
                      latestLogLine: logData.logLines[logData.logLines.length - 1],
                    });
                  }
                  return next;
                });
              }
            } catch (err) {
              // ログ取得エラーは無視（タスクがまだログを生成していない可能性がある）
              console.debug(`[FloatingProgressPanel] Log fetch failed for ${task.id}:`, err);
            }
          }
        }
      } catch (err) {
        console.error('[FloatingProgressPanel] Polling failed:', err);
      }
    };

    // 初回実行
    fetchLogAndProgress();

    // 定期実行
    const intervalId = setInterval(fetchLogAndProgress, pollingInterval);

    return () => clearInterval(intervalId);
  }, [parallelTasks, jobs]);

  // ORDER_128: タスクローテーション（5秒ごとに次のIN_PROGRESSタスクを表示）
  useEffect(() => {
    const runningTasks = Array.from(parallelTasks.values()).filter(
      t => t.status === 'IN_PROGRESS'
    );

    if (runningTasks.length <= 1) {
      // 実行中タスクが1つ以下の場合はローテーション不要
      setRotationIndex(0);
      return;
    }

    const rotationInterval = 5000; // 5秒ごとにローテーション
    const intervalId = setInterval(() => {
      setRotationIndex(prev => (prev + 1) % runningTasks.length);
    }, rotationInterval);

    return () => clearInterval(intervalId);
  }, [parallelTasks]);

  // ジョブをキャンセル
  const handleCancel = useCallback(async (executionId: string) => {
    try {
      await window.electronAPI.cancelJob(executionId);
      setJobs((prev) => {
        const next = new Map(prev);
        next.delete(executionId);
        return next;
      });
    } catch (err) {
      console.error('[FloatingProgressPanel] Failed to cancel job:', err);
    }
  }, []);

  // ORDER_128: タスククリック時のハンドラ（詳細ログ表示）
  const handleTaskClick = useCallback((taskId: string, projectId?: string) => {
    console.log('[FloatingProgressPanel] Task clicked:', taskId, projectId);

    // カスタムイベントを発行してLayout側で処理
    // タスクIDとプロジェクトIDを渡す
    const task = parallelTasks.get(taskId);

    // プロジェクトIDを特定（並列タスクから取得、または実行中ジョブから推測）
    let resolvedProjectId = projectId;
    if (!resolvedProjectId) {
      for (const job of jobs.values()) {
        if (job.type === 'worker' && job.status === 'running') {
          resolvedProjectId = job.projectId;
          break;
        }
      }
    }

    if (resolvedProjectId) {
      const event = new CustomEvent('open-task-log', {
        detail: {
          taskId,
          projectId: resolvedProjectId,
          logFile: task?.logFile,
          hasError: task?.status === 'ERROR',
        },
      });
      window.dispatchEvent(event);
    } else {
      console.warn('[FloatingProgressPanel] Could not determine projectId for task:', taskId);
    }
  }, [parallelTasks, jobs]);

  // ジョブがない場合は非表示
  if (jobs.size === 0 && parallelTasks.size === 0 && !allTasksCompletedMessage) {
    return null;
  }

  const jobList = Array.from(jobs.values());
  const runningCount = jobList.filter((j) => j.status === 'running').length;
  const parallelTaskList = Array.from(parallelTasks.values());
  const parallelRunningCount = parallelTaskList.filter((t) => t.status === "IN_PROGRESS").length;

  // ORDER_119: 完了タスク数/総タスク数の計算
  const parallelCompletedCount = parallelTaskList.filter((t) =>
    t.status === "COMPLETED" || t.status === "DONE"
  ).length;
  const parallelTotalCount = parallelTaskList.length;
  const parallelProgressPercent = parallelTotalCount > 0
    ? Math.round((parallelCompletedCount / parallelTotalCount) * 100)
    : 0;

  // ORDER_128: エラー・警告タスクの検出
  // エラー条件:
  // 1. タスクステータスが ERROR
  // 2. ジョブステータスが failed
  // 3. タスクステータスが CRASHED
  // 4. タスクステータスが REJECTED
  // 5. タスクにerrorMessageが含まれる
  const hasErrors = parallelTaskList.some(t =>
    t.status === 'ERROR' ||
    t.status === 'CRASHED' ||
    t.status === 'REJECTED' ||
    !!t.errorMessage
  ) || jobList.some(j => j.status === 'failed');

  // 警告条件:
  // 1. taskWarningsにエントリがある（タイムアウト・エラー通知）
  // 2. タスクステータスが REWORK
  // 3. タスクが5分以上IN_PROGRESSのまま（長時間実行）
  const hasWarnings = taskWarnings.size > 0 ||
    parallelTaskList.some(t => t.status === 'REWORK') ||
    parallelTaskList.some(t => {
      if (t.status !== 'IN_PROGRESS') return false;
      const elapsed = Math.floor((Date.now() - t.startedAt.getTime()) / 1000);
      return elapsed >= 300; // 5分以上
    });

  return (
    <div
      className={`
        fixed bottom-4 right-4 z-50
        bg-white rounded-lg shadow-lg border border-gray-200
        transition-all duration-300 ease-in-out
        ${isMinimized ? 'w-auto' : 'w-80'}
      `}
    >
      {/* ヘッダー */}
      <div
        className={`flex items-center justify-between px-3 py-2 rounded-t-lg border-b cursor-pointer ${
          hasErrors
            ? 'bg-red-50 border-red-200'
            : hasWarnings
            ? 'bg-yellow-50 border-yellow-200'
            : 'bg-gray-50 border-gray-100'
        }`}
        onClick={() => setIsMinimized(!isMinimized)}
      >
        <div className="flex items-center gap-2">
          {(runningCount > 0 || parallelRunningCount > 0) && !hasErrors && (
            <div className={`w-2 h-2 rounded-full animate-pulse ${
              hasWarnings ? 'bg-yellow-500' : 'bg-blue-500'
            }`} />
          )}
          {hasErrors && (
            <svg className="w-4 h-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
          <span className={`text-sm font-medium ${
            hasErrors ? 'text-red-700' : hasWarnings ? 'text-yellow-700' : 'text-gray-700'
          }`}>
            {hasErrors ? 'エラー発生 ' : hasWarnings ? '警告 ' : '実行中 '}
            ({runningCount}{parallelRunningCount > 0 ? ` + ${parallelRunningCount} tasks` : ""})
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            title={isExpanded ? '折りたたむ' : '展開する'}
          >
            <svg
              className={`w-4 h-4 text-gray-500 transition-transform ${isExpanded ? '' : 'rotate-180'}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsMinimized(true);
            }}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            title="最小化"
          >
            <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
            </svg>
          </button>
        </div>
      </div>

      {/* ジョブリスト */}
      {!isMinimized && isExpanded && (
        <div className="max-h-64 overflow-y-auto">
          {jobList.map((job) => (
            <JobItem
              key={job.executionId}
              job={job}
              onCancel={() => handleCancel(job.executionId)}
            />
          ))}
        </div>
      )}

      {/* ORDER_101: 並列実行中タスク一覧 */}
      {!isMinimized && isExpanded && parallelTaskList.length > 0 && (
        <div className="border-t border-gray-200 px-3 py-2">
          <div className="flex items-center justify-between mb-1">
            <div className="text-xs font-medium text-gray-500">
              並列実行タスク ({parallelCompletedCount}/{parallelTotalCount})
            </div>
            <span className="text-[10px] text-gray-400">{parallelProgressPercent}%</span>
          </div>
          {/* ORDER_119: プログレスバー */}
          <div className="w-full bg-gray-200 rounded-full h-1.5 mb-1.5">
            <div
              className={`h-1.5 rounded-full transition-all duration-500 ease-out ${
                parallelProgressPercent === 100 ? 'bg-green-500' : 'bg-blue-500'
              }`}
              style={{ width: `${parallelProgressPercent}%` }}
            />
          </div>
          {/* ORDER_128: ローテーション表示 - 複数実行中タスクがある場合 */}
          {(() => {
            const runningTasks = parallelTaskList.filter(t => t.status === 'IN_PROGRESS');
            const completedTasks = parallelTaskList.filter(t => t.status !== 'IN_PROGRESS');

            if (runningTasks.length > 1) {
              // 複数実行中: フィーチャータスク1つ + その他（省略表示）
              const featuredTask = runningTasks[rotationIndex % runningTasks.length];
              const otherRunningCount = runningTasks.length - 1;

              return (
                <>
                  {/* フィーチャータスク（詳細表示） */}
                  <ParallelTaskItem
                    key={featuredTask.id}
                    task={featuredTask}
                    warning={taskWarnings.get(featuredTask.id)}
                    onTaskClick={handleTaskClick}
                  />

                  {/* その他の実行中タスク（簡易表示） */}
                  {otherRunningCount > 0 && (
                    <div className="text-xs text-gray-400 py-0.5 ml-4">
                      他 {otherRunningCount} タスク実行中...
                    </div>
                  )}

                  {/* 完了済みタスク */}
                  {completedTasks.map((task) => (
                    <ParallelTaskItem
                      key={task.id}
                      task={task}
                      warning={taskWarnings.get(task.id)}
                      onTaskClick={handleTaskClick}
                    />
                  ))}
                </>
              );
            } else {
              // 実行中タスクが1つ以下: 全タスク表示
              return parallelTaskList.map((task) => (
                <ParallelTaskItem
                  key={task.id}
                  task={task}
                  warning={taskWarnings.get(task.id)}
                  onTaskClick={handleTaskClick}
                />
              ));
            }
          })()}
        </div>
      )}

      {/* ORDER_101: 全タスク完了メッセージ */}
      {!isMinimized && allTasksCompletedMessage && (
        <div className="border-t border-gray-200 px-3 py-2 bg-green-50">
          <div className="flex items-center gap-2 text-xs text-green-700">
            <svg className="w-4 h-4 text-green-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>{allTasksCompletedMessage}</span>
          </div>
        </div>
      )}

      {/* 最小化時の表示 */}
      {isMinimized && (
        <div className="px-3 py-2 flex items-center gap-2">
          {(runningCount > 0 || parallelRunningCount > 0) && (
            <>
              <svg className="w-4 h-4 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span className="text-xs text-gray-600">
                {runningCount > 0 ? `${runningCount} 件実行中` : ""}
                {runningCount > 0 && parallelRunningCount > 0 ? " / " : ""}
                {parallelRunningCount > 0 ? `${parallelCompletedCount}/${parallelTotalCount} (${parallelRunningCount} 実行中)` : ""}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
};

// =============================================================================
// サブコンポーネント
// =============================================================================

interface JobItemProps {
  job: RunningJob;
  onCancel: () => void;
}

const JobItem: React.FC<JobItemProps> = ({ job, onCancel }) => {
  const typeLabel = job.type === 'pm' ? 'PM' : 'Worker';

  // ORDER_042: 経過時間をリアルタイム更新するためのstate
  const [elapsed, setElapsed] = useState(0);

  // 1秒ごとに経過時間を更新
  useEffect(() => {
    // 初回計算
    const calcElapsed = () => Math.floor((Date.now() - job.startedAt.getTime()) / 1000);
    setElapsed(calcElapsed());

    // 実行中のみタイマーを動作
    if (job.status !== 'running') return;

    const timer = setInterval(() => {
      setElapsed(calcElapsed());
    }, 1000);

    return () => clearInterval(timer);
  }, [job.startedAt, job.status]);

  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const elapsedStr = minutes > 0 ? `${minutes}:${seconds.toString().padStart(2, '0')}` : `${seconds}s`;

  // ステータスに応じたスタイル
  const statusStyles = {
    running: {
      bg: 'bg-blue-50',
      border: 'border-blue-100',
      icon: (
        <svg className="w-4 h-4 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      ),
    },
    completed: {
      bg: 'bg-green-50',
      border: 'border-green-100',
      icon: (
        <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      ),
    },
    failed: {
      bg: 'bg-red-50',
      border: 'border-red-100',
      icon: (
        <svg className="w-4 h-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      ),
    },
  };

  const style = statusStyles[job.status];

  return (
    <div className={`p-3 border-b last:border-b-0 ${style.bg} ${style.border}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 flex-1 min-w-0">
          {style.icon}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                job.type === 'pm' ? 'bg-green-100 text-green-700' : 'bg-indigo-100 text-indigo-700'
              }`}>
                {typeLabel}
              </span>
              <span className="text-xs text-gray-600 truncate">{job.targetId}</span>
            </div>
            <div className="text-[10px] text-gray-400 mt-0.5">
              {job.projectId}
            </div>
            {/* 最新出力 */}
            {job.lastOutput && job.status === 'running' && (
              <div className="text-[10px] text-gray-500 mt-1 truncate" title={job.lastOutput}>
                {job.lastOutput}
              </div>
            )}
            {/* エラーメッセージ */}
            {job.error && (
              <div className="text-[10px] text-red-500 mt-1 truncate" title={job.error}>
                {job.error}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-400">{elapsedStr}</span>
          {job.status === 'running' && (
            <button
              onClick={onCancel}
              className="p-1 hover:bg-red-100 rounded transition-colors"
              title="キャンセル"
            >
              <svg className="w-3.5 h-3.5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

// =============================================================================
// ORDER_101: ParallelTaskItem component
// =============================================================================

interface ParallelTaskItemProps {
  task: ParallelTask;
  warning?: string; // ORDER_101 TASK_971
  onTaskClick?: (taskId: string) => void; // ORDER_128: クリックハンドラ
}

const ParallelTaskItem: React.FC<ParallelTaskItemProps> = ({ task, warning, onTaskClick }) => {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const calcElapsed = () => Math.floor((Date.now() - task.startedAt.getTime()) / 1000);
    setElapsed(calcElapsed());
    if (task.status !== "IN_PROGRESS") return;
    const timer = setInterval(() => { setElapsed(calcElapsed()); }, 1000);
    return () => clearInterval(timer);
  }, [task.startedAt, task.status]);

  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const elapsedStr = minutes > 0 ? `${minutes}:${seconds.toString().padStart(2, "0")}` : `${seconds}s`;
  const isLongRunning = task.status === "IN_PROGRESS" && elapsed >= 300;
  const isError = task.status === "ERROR";

  const dotColor =
    task.status === "COMPLETED" ? "bg-green-400" :
    task.status === "ERROR" ? "bg-red-500" :
    task.status === "CRASHED" ? "bg-red-600" :
    task.status === "IN_PROGRESS" ? (isLongRunning ? "bg-yellow-400 animate-pulse" : "bg-blue-400 animate-pulse") :
    task.status === "DONE" ? "bg-yellow-400" :
    task.status === "REWORK" ? "bg-orange-400" :
    task.status === "REJECTED" ? "bg-red-400" :
    "bg-gray-400";

  // ORDER_128: ログ行の省略処理（80文字以上で切り詰め）
  const truncateLog = (log: string | undefined): string => {
    if (!log) return '';
    const maxLength = 80;
    if (log.length <= maxLength) return log;
    return log.substring(0, maxLength) + '...';
  };

  // ORDER_128: クリック可能な場合のスタイル（エラー・長時間実行・実行中タスク・差戻し・リジェクト）
  const isClickable =
    task.status === 'IN_PROGRESS' ||
    task.status === 'ERROR' ||
    task.status === 'CRASHED' ||
    task.status === 'REWORK' ||
    task.status === 'REJECTED' ||
    isLongRunning;
  const cursorClass = isClickable && onTaskClick ? 'cursor-pointer hover:bg-gray-50' : '';

  const handleClick = () => {
    if (isClickable && onTaskClick) {
      onTaskClick(task.id);
    }
  };

  return (
    <div
      className={`text-xs py-0.5 ${isError ? "bg-red-50 rounded px-1" : ""} ${cursorClass} transition-colors`}
      onClick={handleClick}
      title={isClickable ? 'クリックして詳細ログを表示' : undefined}
    >
      <div className="flex items-center">
        <span className={`w-2 h-2 rounded-full mr-2 flex-shrink-0 ${dotColor}`} />
        <span className={`truncate flex-1 ${isError ? "text-red-600 font-medium" : "text-gray-600"}`} title={`${task.id}: ${task.title}`}>
          {task.id}{task.title ? `: ${task.title}` : ""}
        </span>
        <span className="text-gray-400 ml-1 flex-shrink-0">{elapsedStr}</span>
        <span className={`ml-2 flex-shrink-0 ${
          isError ? "text-red-600 font-medium" :
          isLongRunning ? "text-yellow-600 font-medium" : "text-gray-400"
        }`}>
          {task.status}
          {isLongRunning && !isError ? " (!)" : ""}
        </span>
        {warning && (
          <span className={`text-xs ml-1 flex-shrink-0 ${
            warning.startsWith("\u30a8\u30e9\u30fc") || warning.startsWith("\u30af\u30e9\u30c3\u30b7\u30e5") ? "text-red-400 font-medium" : "text-yellow-400"
          }`}>{warning}</span>
        )}
      </div>
      {/* ORDER_128: 実行ステップ表示 */}
      {task.status === "IN_PROGRESS" && task.currentStep && (
        <div className="ml-4 mt-0.5">
          <div className="text-blue-600 text-[10px]">
            Step {task.stepIndex !== undefined && task.totalSteps !== undefined
              ? `${task.stepIndex + 1}/${task.totalSteps}`
              : ''}: {task.currentStep}
          </div>
        </div>
      )}
      {/* ORDER_128: 最新ログ行表示 */}
      {task.status === "IN_PROGRESS" && task.latestLogLine && (
        <div className="ml-4 mt-0.5">
          <div className="text-gray-500 text-[10px] truncate" title={task.latestLogLine}>
            {truncateLog(task.latestLogLine)}
          </div>
        </div>
      )}
      {/* ORDER_109: エラーメッセージとログファイルパスの表示 */}
      {isError && task.errorMessage && (
        <div className="ml-4 mt-0.5">
          <div className="text-red-500 text-[10px]">{task.errorMessage}</div>
          {task.logFile && (
            <div className="text-gray-400 text-[10px] truncate" title={task.logFile}>
              Log: {task.logFile}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default FloatingProgressPanel;
