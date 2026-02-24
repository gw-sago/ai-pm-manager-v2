/**
 * useRecoverOrder
 *
 * ORDER/TASKの失敗状態検出・修復操作を管理するカスタムhook。
 * recoverOrder IPC呼び出しの状態管理（ローディング・成功・エラー）を行う。
 *
 * @module useRecoverOrder
 * @created 2026-02-24
 * @order ORDER_060
 * @task TASK_205
 */

import { useState, useCallback } from 'react';

/**
 * リカバリ検出結果
 */
export interface RecoverDetected {
  order: Record<string, unknown> | null;
  stalled_tasks: Array<Record<string, unknown>>;
  rejected_tasks: Array<Record<string, unknown>>;
  has_failure: boolean;
  failure_reasons: string[];
}

/**
 * リカバリされたタスク情報
 */
export interface RecoveredTask {
  task_id: string;
  previous_status: string;
  new_status: string | null;
  reason: string;
  locks_released?: number;
  reject_count_reset?: boolean;
  error?: string;
}

/**
 * リカバリ結果
 */
export interface RecoverOrderResult {
  success: boolean;
  project_id: string;
  order_id: string;
  dry_run?: boolean;
  detected?: RecoverDetected;
  recovered_tasks?: RecoveredTask[];
  order_recovered?: boolean;
  message?: string;
  error?: string;
}

/**
 * useRecoverOrderの引数
 */
export interface UseRecoverOrderOptions {
  /** プロジェクトID */
  projectId: string;
  /** ORDER ID */
  orderId: string;
  /** スタック判定閾値（分、デフォルト: 30） */
  stallMinutes?: number;
  /** 成功時のコールバック（ORDER一覧リフレッシュ等） */
  onSuccess?: () => void;
}

/**
 * useRecoverOrderの戻り値
 */
export interface UseRecoverOrderResult {
  /** リカバリ実行中フラグ */
  isRecovering: boolean;
  /** エラーメッセージ（エラー時） */
  recoverError: string | null;
  /** 成功フラグ */
  recoverSuccess: boolean;
  /** 最後のリカバリ結果 */
  lastResult: RecoverOrderResult | null;
  /** リカバリ実行ハンドラ */
  handleRecoverOrder: () => void;
  /** 状態リセット（ORDER切替時等） */
  clearRecoverState: () => void;
}

/**
 * ORDER/TASKリカバリhook
 *
 * @example
 * ```tsx
 * const { isRecovering, recoverError, recoverSuccess, handleRecoverOrder, clearRecoverState } = useRecoverOrder({
 *   projectId: 'ai_pm_manager',
 *   orderId: 'ORDER_060',
 *   onSuccess: () => refreshOrders(),
 * });
 * ```
 */
export const useRecoverOrder = ({
  projectId,
  orderId,
  stallMinutes,
  onSuccess,
}: UseRecoverOrderOptions): UseRecoverOrderResult => {
  const [isRecovering, setIsRecovering] = useState(false);
  const [recoverError, setRecoverError] = useState<string | null>(null);
  const [recoverSuccess, setRecoverSuccess] = useState(false);
  const [lastResult, setLastResult] = useState<RecoverOrderResult | null>(null);

  const handleRecoverOrder = useCallback(async () => {
    if (isRecovering) return;

    setIsRecovering(true);
    setRecoverError(null);
    setRecoverSuccess(false);

    try {
      console.log('[useRecoverOrder] Calling recoverOrder:', { projectId, orderId, stallMinutes });
      const options: { stallMinutes?: number } = {};
      if (stallMinutes !== undefined) {
        options.stallMinutes = stallMinutes;
      }

      const result = await window.electronAPI.recoverOrder(projectId, orderId, options);
      setLastResult(result);

      if (result.success) {
        console.log('[useRecoverOrder] recoverOrder succeeded:', result.message);
        setRecoverSuccess(true);
        // 成功時にコールバック（ORDER一覧リフレッシュ等）
        onSuccess?.();
      } else {
        const errorMsg = result.error || 'ORDER/TASKリカバリに失敗しました';
        console.error('[useRecoverOrder] recoverOrder failed:', errorMsg);
        setRecoverError(errorMsg);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'ORDER/TASKリカバリ中に予期しないエラーが発生しました';
      console.error('[useRecoverOrder] recoverOrder exception:', err);
      setRecoverError(errorMsg);
    } finally {
      setIsRecovering(false);
    }
  }, [projectId, orderId, stallMinutes, isRecovering, onSuccess]);

  const clearRecoverState = useCallback(() => {
    setIsRecovering(false);
    setRecoverError(null);
    setRecoverSuccess(false);
    setLastResult(null);
  }, []);

  return {
    isRecovering,
    recoverError,
    recoverSuccess,
    lastResult,
    handleRecoverOrder,
    clearRecoverState,
  };
};

export default useRecoverOrder;
