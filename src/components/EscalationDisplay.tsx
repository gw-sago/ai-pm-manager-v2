/**
 * EscalationDisplay Component
 *
 * ORDER_047 / TASK_157: エスカレーション表示コンポーネント
 *
 * rework上限到達・停止済みステータスと問題点サマリーを表示する専用コンポーネント。
 * TaskDetailPanelや他のUIから再利用可能な形で提供する。
 */

import React from 'react';
import type { TaskReviewHistory } from '../preload';

interface EscalationDisplayProps {
  /** タスクの現在ステータス */
  taskStatus: string;
  /** レビュー履歴（エスカレーション情報を含む） */
  reviewHistory: TaskReviewHistory;
  /** コンパクト表示モード（リスト表示用） */
  compact?: boolean;
}

/**
 * 日時フォーマット関数
 */
const formatDateTime = (dateStr: string | null): string => {
  if (!dateStr) return 'N/A';
  try {
    const date = new Date(dateStr);
    return date.toLocaleString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
};

/**
 * エスカレーション表示コンポーネント
 *
 * タスクがESCALATED状態の時に、rework上限到達・停止済みステータスと
 * 問題点サマリーを視覚的に表示する。
 */
export const EscalationDisplay: React.FC<EscalationDisplayProps> = ({
  taskStatus,
  reviewHistory,
  compact = false,
}) => {
  const isEscalated = taskStatus === 'ESCALATED';
  const hasEscalations = reviewHistory.escalations.length > 0;
  const openEscalations = reviewHistory.escalations.filter((e) => !e.resolvedAt);
  const latestOpenEscalation = openEscalations.sort((a, b) =>
    b.createdAt.localeCompare(a.createdAt)
  )[0];

  if (!isEscalated && !hasEscalations) {
    return null;
  }

  // コンパクトモード（ダッシュボード等での簡易表示）
  if (compact) {
    return (
      <div className="flex items-center gap-1.5 px-2 py-1 bg-yellow-100 border border-yellow-300 rounded text-xs">
        <span className="text-yellow-600">⚠</span>
        <span className="font-semibold text-yellow-800">ESC</span>
        {isEscalated && (
          <span className="text-yellow-700">
            rework上限到達 ({reviewHistory.rejectCount}/{reviewHistory.maxRework})
          </span>
        )}
        {openEscalations.length > 0 && (
          <span className="text-yellow-600">未解決: {openEscalations.length}件</span>
        )}
      </div>
    );
  }

  // フル表示モード
  return (
    <div className="space-y-3">
      {/* rework上限到達・停止済みバナー */}
      {isEscalated && (
        <div className="p-4 rounded-lg border-2 border-yellow-400 bg-yellow-50">
          <div className="flex items-start gap-3">
            <span className="text-yellow-500 text-2xl flex-shrink-0">⚠</span>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <p className="text-base font-bold text-yellow-800">
                  rework上限到達 — 自動処理を停止しました
                </p>
                <span className="text-xs font-medium bg-red-100 text-red-700 px-2 py-0.5 rounded">
                  停止済み
                </span>
              </div>
              <p className="text-sm text-yellow-700">
                差し戻し回数が上限（{reviewHistory.maxRework}回）に達したため、このタスクはエスカレーションされました。
                自動Worker処理は停止しています。手動での介入・復旧が必要です。
              </p>
              <div className="mt-2">
                <div className="flex items-center justify-between text-xs text-yellow-700 mb-1">
                  <span>差し戻し回数: {reviewHistory.rejectCount}/{reviewHistory.maxRework}</span>
                </div>
                <div className="w-full bg-yellow-200 rounded-full h-2">
                  <div
                    className="h-2 rounded-full bg-red-500"
                    style={{ width: '100%' }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 問題点サマリー（未解決エスカレーション） */}
      {openEscalations.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-600 uppercase">
            問題点サマリー（未解決）
          </h4>
          {openEscalations.map((esc) => (
            <div
              key={esc.id}
              className="p-3 rounded-lg border border-yellow-300 bg-yellow-50"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold text-yellow-700">⚠ 未解決</span>
                <span className="text-xs text-gray-500">{formatDateTime(esc.createdAt)}</span>
              </div>
              {esc.reason ? (
                <p className="text-sm text-gray-800 whitespace-pre-wrap">{esc.reason}</p>
              ) : (
                <p className="text-sm text-gray-500 italic">詳細なし</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 解決済みエスカレーション（折りたたみ表示） */}
      {reviewHistory.escalations.filter((e) => e.resolvedAt).length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-500 uppercase">
            解決済みエスカレーション
          </h4>
          {reviewHistory.escalations
            .filter((e) => e.resolvedAt)
            .sort((a, b) => (b.resolvedAt || '').localeCompare(a.resolvedAt || ''))
            .map((esc) => (
              <div
                key={esc.id}
                className="p-3 rounded-lg border border-green-200 bg-green-50"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-semibold text-green-700">✓ 解決済み</span>
                  <span className="text-xs text-gray-500">{formatDateTime(esc.createdAt)}</span>
                </div>
                {esc.reason && (
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">{esc.reason}</p>
                )}
                {esc.resolution && (
                  <div className="mt-2 pt-2 border-t border-green-200">
                    <p className="text-xs font-semibold text-green-700 mb-0.5">解決内容:</p>
                    <p className="text-sm text-green-800">{esc.resolution}</p>
                    <p className="text-xs text-gray-500 mt-1">{formatDateTime(esc.resolvedAt)}</p>
                  </div>
                )}
              </div>
            ))}
        </div>
      )}

      {/* エスカレーション詳細がない場合 */}
      {!hasEscalations && isEscalated && (
        <p className="text-sm text-yellow-700 italic px-1">
          エスカレーション詳細が記録されていません
        </p>
      )}

      {/* 最新の差し戻し理由（ESCALATEDの場合に表示） */}
      {isEscalated && latestOpenEscalation && !latestOpenEscalation.reason && (() => {
        const latestRejection = reviewHistory.reviews
          .filter((r) => r.status === 'REJECTED' && r.comment)
          .sort((a, b) => {
            const dateA = a.reviewedAt || a.submittedAt || '';
            const dateB = b.reviewedAt || b.submittedAt || '';
            return dateB.localeCompare(dateA);
          })[0];

        return latestRejection ? (
          <div className="p-3 rounded-lg border border-red-200 bg-red-50">
            <p className="text-xs font-semibold text-red-700 mb-1">最後の差し戻し理由:</p>
            <p className="text-sm text-red-800 whitespace-pre-wrap">{latestRejection.comment}</p>
            <p className="text-xs text-gray-500 mt-1">
              {formatDateTime(latestRejection.reviewedAt || latestRejection.submittedAt)}
            </p>
          </div>
        ) : null;
      })()}
    </div>
  );
};

export default EscalationDisplay;
