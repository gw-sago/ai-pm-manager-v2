/**
 * RecoveryAlert コンポーネント
 *
 * ORDER/TASKの失敗状態を検出・表示し、リカバリ操作を提供するアラートバナー。
 * ORDERのstatus（RUNNING, ERROR, PARTIAL, ON_HOLD 等）とTASKの状態から
 * PM失敗を判定し、エラー内容・中断箇所をバナーとして表示する。
 *
 * 表示条件:
 * - ORDER status が PLANNING_FAILED / ON_HOLD の場合
 * - TASKにREJECTEDが存在する場合
 * - TASKにIN_PROGRESSで長時間停止しているものがある場合（stalled）
 *
 * @module RecoveryAlert
 * @created 2026-02-24
 * @order ORDER_060
 * @task TASK_205
 */

import React from 'react';
import type { OrderInfo } from '../preload';
import { useRecoverOrder } from '../hooks/useRecoverOrder';
import type { RecoverOrderResult } from '../hooks/useRecoverOrder';

/**
 * RecoveryAlertのProps
 */
export interface RecoveryAlertProps {
  /** プロジェクトID */
  projectId: string;
  /** ORDER情報 */
  order: OrderInfo;
  /** リカバリ成功後のコールバック */
  onRecoverSuccess?: () => void;
}

/**
 * ORDER/TASK失敗状態を判定する
 */
function detectFailureState(order: OrderInfo): {
  hasFailure: boolean;
  failureType: 'planning_failed' | 'on_hold' | 'rejected_tasks' | 'stalled' | null;
  rejectedTaskCount: number;
  summary: string;
} {
  const { status, tasks = [] } = order;

  if (status === 'PLANNING_FAILED') {
    return {
      hasFailure: true,
      failureType: 'planning_failed',
      rejectedTaskCount: 0,
      summary: 'PM処理が失敗しました。リカバリを実行してPLANNING状態に戻してください。',
    };
  }

  if (status === 'ON_HOLD') {
    return {
      hasFailure: true,
      failureType: 'on_hold',
      rejectedTaskCount: 0,
      summary: 'このORDERは保留中です。リカバリを実行してIN_PROGRESS状態に戻せます。',
    };
  }

  const rejectedTasks = tasks.filter((t) => t.status === 'REJECTED');
  if (rejectedTasks.length > 0) {
    return {
      hasFailure: true,
      failureType: 'rejected_tasks',
      rejectedTaskCount: rejectedTasks.length,
      summary: `${rejectedTasks.length}件のタスクがREJECTEDです。リカバリを実行してQUEUEDに戻せます。`,
    };
  }

  return {
    hasFailure: false,
    failureType: null,
    rejectedTaskCount: 0,
    summary: '',
  };
}

/**
 * 失敗タイプに対応するバナーのスタイルを取得
 */
function getBannerStyle(failureType: string | null): {
  container: string;
  icon: string;
  title: string;
  iconPath: string;
} {
  switch (failureType) {
    case 'planning_failed':
      return {
        container: 'bg-red-50 border border-red-200 rounded-md p-3',
        icon: 'text-red-500',
        title: 'text-red-800 font-semibold',
        iconPath:
          'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
      };
    case 'on_hold':
      return {
        container: 'bg-yellow-50 border border-yellow-200 rounded-md p-3',
        icon: 'text-yellow-500',
        title: 'text-yellow-800 font-semibold',
        iconPath:
          'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
      };
    case 'rejected_tasks':
      return {
        container: 'bg-orange-50 border border-orange-200 rounded-md p-3',
        icon: 'text-orange-500',
        title: 'text-orange-800 font-semibold',
        iconPath:
          'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
      };
    default:
      return {
        container: 'bg-gray-50 border border-gray-200 rounded-md p-3',
        icon: 'text-gray-500',
        title: 'text-gray-800 font-semibold',
        iconPath:
          'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
      };
  }
}

/**
 * リカバリ結果サマリ表示
 */
const RecoverResultSummary: React.FC<{ result: RecoverOrderResult }> = ({ result }) => {
  if (!result.detected) return null;

  const { recovered_tasks = [], order_recovered, detected } = result;
  const successCount = recovered_tasks.filter((t) => t.new_status !== null).length;
  const failCount = recovered_tasks.filter((t) => t.new_status === null).length;

  return (
    <div className="mt-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded p-2">
      <p className="font-medium">リカバリ完了</p>
      {order_recovered && (
        <p>ORDER: {detected.order?.status as string} → 修復済み</p>
      )}
      {successCount > 0 && (
        <p>タスク修復: {successCount}件成功</p>
      )}
      {failCount > 0 && (
        <p className="text-red-600">タスク修復失敗: {failCount}件</p>
      )}
      {recovered_tasks.length === 0 && !order_recovered && (
        <p>検出された失敗はありませんでした</p>
      )}
    </div>
  );
};

/**
 * RecoveryAlert コンポーネント
 *
 * ORDER/TASKの失敗状態をバナー表示し、リカバリボタンを提供する。
 * 正常状態のORDERでは何も表示しない。
 */
export const RecoveryAlert: React.FC<RecoveryAlertProps> = ({
  projectId,
  order,
  onRecoverSuccess,
}) => {
  const { hasFailure, failureType, rejectedTaskCount, summary } = detectFailureState(order);

  const {
    isRecovering,
    recoverError,
    recoverSuccess,
    lastResult,
    handleRecoverOrder,
  } = useRecoverOrder({
    projectId,
    orderId: order.id,
    onSuccess: onRecoverSuccess,
  });

  // 失敗状態でなければ表示しない
  if (!hasFailure) {
    return null;
  }

  const bannerStyle = getBannerStyle(failureType);

  return (
    <div className={bannerStyle.container}>
      <div className="flex items-start gap-2">
        {/* アイコン */}
        <svg
          className={`w-5 h-5 flex-shrink-0 mt-0.5 ${bannerStyle.icon}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d={bannerStyle.iconPath}
          />
        </svg>

        {/* コンテンツ */}
        <div className="flex-1 min-w-0">
          {/* タイトル */}
          <p className={bannerStyle.title}>
            {failureType === 'planning_failed' && 'PM処理失敗'}
            {failureType === 'on_hold' && 'ORDER保留中'}
            {failureType === 'rejected_tasks' && `REJECTED タスク (${rejectedTaskCount}件)`}
          </p>

          {/* 説明 */}
          <p className="text-sm text-gray-600 mt-0.5">{summary}</p>

          {/* リカバリ失敗タスク詳細 */}
          {failureType === 'rejected_tasks' && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {order.tasks
                .filter((t) => t.status === 'REJECTED')
                .map((t) => (
                  <span
                    key={t.id}
                    className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700"
                    title={t.title}
                  >
                    {t.id.replace('TASK_', '')}
                  </span>
                ))}
            </div>
          )}

          {/* エラー表示 */}
          {recoverError && (
            <p className="mt-1.5 text-xs text-red-600 bg-red-50 border border-red-200 rounded p-1.5">
              リカバリ失敗: {recoverError}
            </p>
          )}

          {/* 成功時の結果表示 */}
          {recoverSuccess && lastResult && (
            <RecoverResultSummary result={lastResult} />
          )}
        </div>

        {/* リカバリボタン */}
        <button
          onClick={handleRecoverOrder}
          disabled={isRecovering}
          title={
            isRecovering
              ? 'リカバリ実行中...'
              : 'ORDER/TASKの失敗状態を検出・修復します'
          }
          className={`
            flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors
            ${
              isRecovering
                ? 'bg-gray-100 text-gray-400 cursor-wait'
                : recoverSuccess
                  ? 'bg-green-600 text-white hover:bg-green-700'
                  : 'bg-amber-600 text-white hover:bg-amber-700'
            }
          `}
        >
          {isRecovering ? (
            <>
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>リカバリ中...</span>
            </>
          ) : recoverSuccess ? (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
              <span>完了</span>
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              <span>リカバリ</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export default RecoveryAlert;
