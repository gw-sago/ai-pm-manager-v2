/**
 * Shared Type Definitions
 *
 * ORDER_141 / TASK_1171: Shared types for IPC communication
 *
 * This file contains type definitions shared between the main process
 * and renderer process to ensure type safety across IPC boundaries.
 *
 * @see BUG_009 - IPC type mismatch prevention
 */

/**
 * タスク進捗情報（ORDER_128 / TASK_1127）
 *
 * This type is used by:
 * - preload.ts: TaskProgressInfo interface
 * - AipmDbService.getTaskProgressInfo(): return type
 * - project.ts IPC handler 'project:get-task-progress-info': return type
 */
export interface TaskProgressInfo {
  /** 実行中タスクリスト */
  runningTasks: Array<{
    id: string;
    title: string;
    status: string;
    currentStep: string | null;
    stepIndex: number;
    totalSteps: number;
    progressPercent: number;
  }>;
  /** 完了タスク数 */
  completedCount: number;
  /** 総タスク数 */
  totalCount: number;
  /** ORDER進捗率 (0-100) */
  overallProgress: number;
}
