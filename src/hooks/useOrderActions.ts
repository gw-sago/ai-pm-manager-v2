/**
 * useOrderActions
 *
 * ORDER状態（PLANNING/IN_PROGRESS/COMPLETED）と実行中タスク状況から、
 * 現在実行可能なアクション（PM実行可/Worker実行可/リリース可）を判定するカスタムhook。
 *
 * @module useOrderActions
 * @created 2026-02-10
 * @order ORDER_131
 * @task TASK_1136, TASK_1137
 */

import { useMemo } from 'react';
import type { OrderInfo, BacklogItem } from '../preload';

/**
 * アクション判定結果
 */
export interface OrderActionsResult {
  /** PM実行可能フラグ */
  canExecutePm: boolean;
  /** Worker実行可能フラグ */
  canExecuteWorker: boolean;
  /** リリース実行可能フラグ */
  canRelease: boolean;
  /** 無効理由（ボタンが無効の場合） */
  disabledReason: string;
  /** PM無効理由（ツールチップ用） */
  pmDisabledReason: string;
  /** Worker無効理由（ツールチップ用） */
  workerDisabledReason: string;
  /** リリース無効理由（ツールチップ用） */
  releaseDisabledReason: string;
}

/**
 * useOrderActionsの引数（ORDER単位）
 */
export interface UseOrderActionsOptions {
  /** ORDER情報 */
  order: OrderInfo | null;
  /** PM実行中フラグ */
  isPmRunning?: boolean;
  /** Worker実行中フラグ */
  isWorkerRunning?: boolean;
  /** リリース実行中フラグ */
  isReleaseRunning?: boolean;
}

/**
 * useBacklogActionsの引数（バックログ項目単位）
 * TASK_1137: BacklogList.tsx向けのバックログ項目単位判定
 */
export interface UseBacklogActionsOptions {
  /** バックログ項目 */
  backlogItem: BacklogItem | null;
  /** PM実行中フラグ */
  isPmRunning?: boolean;
  /** Worker実行中フラグ */
  isWorkerRunning?: boolean;
}

/**
 * ORDER状態判定hook
 *
 * ORDER状態と実行中タスク状況から、現在実行可能なアクションを判定します。
 *
 * @example
 * ```tsx
 * const { canExecutePm, canExecuteWorker, canRelease, disabledReason } = useOrderActions({
 *   order: orderInfo,
 *   isPmRunning: false,
 *   isWorkerRunning: false,
 *   isReleaseRunning: false,
 * });
 *
 * <button disabled={!canExecutePm} title={pmDisabledReason}>PM実行</button>
 * ```
 */
export const useOrderActions = ({
  order,
  isPmRunning = false,
  isWorkerRunning = false,
  isReleaseRunning = false,
}: UseOrderActionsOptions): OrderActionsResult => {
  return useMemo(() => {
    // ORDERがない場合
    if (!order) {
      return {
        canExecutePm: false,
        canExecuteWorker: false,
        canRelease: false,
        disabledReason: 'ORDERが選択されていません',
        pmDisabledReason: 'ORDERが選択されていません',
        workerDisabledReason: 'ORDERが選択されていません',
        releaseDisabledReason: 'ORDERが選択されていません',
      };
    }

    const { status, tasks } = order;
    const totalTasks = tasks?.length ?? 0;
    const completedTasks = tasks?.filter((t) => t.status === 'COMPLETED').length ?? 0;
    const hasUncompletedTasks = totalTasks > 0 && completedTasks < totalTasks;

    // PM実行可能判定
    // - PLANNING状態
    // - PM実行中でない
    const canExecutePm = status === 'PLANNING' && !isPmRunning;

    // Worker実行可能判定
    // - IN_PROGRESS状態
    // - 未完了タスクが存在
    // - Worker実行中でない
    const canExecuteWorker =
      status === 'IN_PROGRESS' && hasUncompletedTasks && !isWorkerRunning;

    // リリース実行可能判定
    // - IN_PROGRESS状態
    // - 全タスク完了
    // - リリース実行中でない
    const canRelease =
      status === 'IN_PROGRESS' && totalTasks > 0 && completedTasks === totalTasks && !isReleaseRunning;

    // 個別無効理由の判定
    let pmDisabledReason = '';
    if (status !== 'PLANNING') {
      pmDisabledReason = `ORDERステータスが PLANNING ではありません (現在: ${status})`;
    } else if (isPmRunning) {
      pmDisabledReason = 'PM処理実行中...';
    }

    let workerDisabledReason = '';
    if (status !== 'IN_PROGRESS') {
      workerDisabledReason = `ORDERステータスが IN_PROGRESS ではありません (現在: ${status})`;
    } else if (!hasUncompletedTasks) {
      if (totalTasks === 0) {
        workerDisabledReason = 'タスクがありません';
      } else {
        workerDisabledReason = 'すべてのタスクが完了済みです';
      }
    } else if (isWorkerRunning) {
      workerDisabledReason = 'Worker実行中...';
    }

    let releaseDisabledReason = '';
    if (status !== 'IN_PROGRESS') {
      releaseDisabledReason = `ORDERステータスが IN_PROGRESS ではありません (現在: ${status})`;
    } else if (totalTasks === 0) {
      releaseDisabledReason = 'タスクがありません';
    } else if (completedTasks < totalTasks) {
      releaseDisabledReason = `残り ${totalTasks - completedTasks}/${totalTasks} タスク未完了`;
    } else if (isReleaseRunning) {
      releaseDisabledReason = 'リリース実行中...';
    }

    // 全体の無効理由（汎用メッセージ）
    let disabledReason = '';

    if (status === 'COMPLETED') {
      disabledReason = 'このORDERは既に完了しています';
    } else if (status === 'CANCELLED') {
      disabledReason = 'このORDERはキャンセルされています';
    } else if (status === 'ON_HOLD') {
      disabledReason = 'このORDERは保留中です';
    } else if (status === 'PLANNING') {
      disabledReason = isPmRunning ? 'PM処理実行中...' : 'PM処理を実行してタスクを生成してください';
    } else if (status === 'IN_PROGRESS') {
      if (isWorkerRunning) {
        disabledReason = 'Worker実行中...';
      } else if (isReleaseRunning) {
        disabledReason = 'リリース実行中...';
      } else if (!hasUncompletedTasks && totalTasks > 0) {
        disabledReason = '全タスク完了 - リリース可能です';
      } else if (totalTasks === 0) {
        disabledReason = 'タスクがありません - PM処理を実行してください';
      } else {
        disabledReason = `残り ${totalTasks - completedTasks}/${totalTasks} タスク`;
      }
    } else {
      disabledReason = `ステータス: ${status}`;
    }

    return {
      canExecutePm,
      canExecuteWorker,
      canRelease,
      disabledReason,
      pmDisabledReason,
      workerDisabledReason,
      releaseDisabledReason,
    };
  }, [order, isPmRunning, isWorkerRunning, isReleaseRunning]);
};

/**
 * バックログ項目アクション判定hook
 *
 * BacklogList.tsx向けに、バックログ項目単位でPM/Worker実行可否を判定します。
 * TASK_1137: BacklogList.tsxのボタン活性制御精緻化
 *
 * @example
 * ```tsx
 * const { canExecutePm, canExecuteWorker, pmDisabledReason } = useBacklogActions({
 *   backlogItem: item,
 *   isPmRunning: false,
 *   isWorkerRunning: false,
 * });
 * ```
 */
export const useBacklogActions = ({
  backlogItem,
  isPmRunning = false,
  isWorkerRunning = false,
}: UseBacklogActionsOptions): OrderActionsResult => {
  return useMemo(() => {
    if (!backlogItem) {
      return {
        canExecutePm: false,
        canExecuteWorker: false,
        canRelease: false,
        disabledReason: 'バックログ項目がありません',
        pmDisabledReason: 'バックログ項目がありません',
        workerDisabledReason: 'バックログ項目がありません',
        releaseDisabledReason: 'リリース操作はバックログ単位ではサポートされていません',
      };
    }

    const {
      relatedOrderId,
      orderStatus,
      priority,
      status,
      totalTasks = 0,
      completedTasks = 0,
    } = backlogItem;

    // ====================================================================
    // PM実行可能判定
    // ====================================================================
    // 条件:
    // - ORDER化されていない（relatedOrderId=null）
    // - PM実行中ではない
    // - Low優先度かつTODO状態ではない（優先度の低いタスクは後回し方針）
    const isLowPriorityAndTodo = priority === 'Low' && status === 'TODO';
    const canExecutePm = !relatedOrderId && !isPmRunning && !isLowPriorityAndTodo;

    let pmDisabledReason = '';
    if (relatedOrderId) {
      pmDisabledReason = 'すでにORDER化済みです';
    } else if (isPmRunning) {
      pmDisabledReason = 'PM処理実行中...';
    } else if (isLowPriorityAndTodo) {
      pmDisabledReason =
        'Low優先度のタスクです。先にHigh/Medium優先度のタスクを完了させるか、優先度を上げてください';
    }

    // ====================================================================
    // Worker実行可能判定
    // ====================================================================
    // 条件:
    // - ORDER紐付け済み（relatedOrderId != null）
    // - ORDERステータスがIN_PROGRESS
    // - 未完了タスクが存在する（completedTasks < totalTasks）
    // - Worker実行中ではない
    const canExecuteWorker =
      !!relatedOrderId &&
      orderStatus === 'IN_PROGRESS' &&
      totalTasks > 0 &&
      completedTasks < totalTasks &&
      !isWorkerRunning;

    let workerDisabledReason = '';
    if (!relatedOrderId) {
      workerDisabledReason = 'ORDER化されていません';
    } else if (orderStatus !== 'IN_PROGRESS') {
      workerDisabledReason = `ORDERステータスが IN_PROGRESS ではありません (現在: ${orderStatus || 'unknown'})`;
    } else if (totalTasks === 0) {
      workerDisabledReason = 'タスクが存在しません';
    } else if (completedTasks >= totalTasks) {
      workerDisabledReason = 'すべてのタスクが完了済みです';
    } else if (isWorkerRunning) {
      workerDisabledReason = 'Worker実行中...';
    }

    // リリースはバックログ単位ではサポートしない
    const canRelease = false;
    const releaseDisabledReason = 'リリース操作はバックログ単位ではサポートされていません';

    return {
      canExecutePm,
      canExecuteWorker,
      canRelease,
      disabledReason: pmDisabledReason || workerDisabledReason || 'アクション実行不可',
      pmDisabledReason,
      workerDisabledReason,
      releaseDisabledReason,
    };
  }, [backlogItem, isPmRunning, isWorkerRunning]);
};

export default useOrderActions;
