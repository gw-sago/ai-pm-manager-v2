/**
 * useRetryOrder
 *
 * PLANNING_FAILEDステータスのORDERに対する再実行操作を管理するカスタムhook。
 * retryOrder IPC呼び出しの状態管理（ローディング・成功・エラー）を行う。
 *
 * @module useRetryOrder
 * @created 2026-02-16
 * @order ORDER_155
 * @task TASK_1229
 */

import { useState, useCallback } from 'react';

/**
 * useRetryOrderの引数
 */
export interface UseRetryOrderOptions {
  /** プロジェクトID */
  projectId: string;
  /** ORDER ID */
  orderId: string;
  /** 成功時のコールバック（ORDER一覧リフレッシュ等） */
  onSuccess?: () => void;
}

/**
 * useRetryOrderの戻り値
 */
export interface UseRetryOrderResult {
  /** 再実行中フラグ */
  isRetrying: boolean;
  /** エラーメッセージ（エラー時） */
  retryError: string | null;
  /** 成功フラグ */
  retrySuccess: boolean;
  /** 再実行ハンドラ */
  handleRetryOrder: () => void;
  /** 状態リセット（ORDER切替時等） */
  clearRetryState: () => void;
}

/**
 * PLANNING_FAILEDリカバリhook
 *
 * @example
 * ```tsx
 * const { isRetrying, retryError, retrySuccess, handleRetryOrder, clearRetryState } = useRetryOrder({
 *   projectId: 'ai_pm_manager',
 *   orderId: 'ORDER_155',
 *   onSuccess: () => refreshOrders(),
 * });
 * ```
 */
export const useRetryOrder = ({
  projectId,
  orderId,
  onSuccess,
}: UseRetryOrderOptions): UseRetryOrderResult => {
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [retrySuccess, setRetrySuccess] = useState(false);

  const handleRetryOrder = useCallback(async () => {
    if (isRetrying) return;

    setIsRetrying(true);
    setRetryError(null);
    setRetrySuccess(false);

    try {
      console.log('[useRetryOrder] Calling retryOrder:', { projectId, orderId });
      const result = await window.electronAPI.retryOrder(projectId, orderId);

      if (result.success) {
        console.log('[useRetryOrder] retryOrder succeeded:', result);
        setRetrySuccess(true);
        // 成功時にコールバック（ORDER一覧リフレッシュ等）
        onSuccess?.();
      } else {
        const errorMsg = result.error || 'ORDER再実行に失敗しました';
        console.error('[useRetryOrder] retryOrder failed:', errorMsg);
        setRetryError(errorMsg);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'ORDER再実行中に予期しないエラーが発生しました';
      console.error('[useRetryOrder] retryOrder exception:', err);
      setRetryError(errorMsg);
    } finally {
      setIsRetrying(false);
    }
  }, [projectId, orderId, isRetrying, onSuccess]);

  const clearRetryState = useCallback(() => {
    setIsRetrying(false);
    setRetryError(null);
    setRetrySuccess(false);
  }, []);

  return {
    isRetrying,
    retryError,
    retrySuccess,
    handleRetryOrder,
    clearRetryState,
  };
};

export default useRetryOrder;
