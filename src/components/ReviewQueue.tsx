import React from 'react';
import type { ReviewQueueItem, ParsedState } from '../preload';

interface ReviewQueueProps {
  state: ParsedState;
  onTaskClick?: (taskId: string) => void;
}

interface ReviewQueueCardProps {
  item: ReviewQueueItem;
  onClick?: () => void;
}

/**
 * 優先度に応じた色・アイコン定義
 */
const priorityConfig: Record<string, { bg: string; text: string; icon: string; label: string }> = {
  P0: {
    bg: 'bg-red-100',
    text: 'text-red-700',
    icon: '🔴',
    label: '最優先',
  },
  P1: {
    bg: 'bg-yellow-100',
    text: 'text-yellow-700',
    icon: '🟡',
    label: '通常',
  },
  P2: {
    bg: 'bg-green-100',
    text: 'text-green-700',
    icon: '🟢',
    label: '低優先',
  },
};

/**
 * ステータスに応じた色定義
 */
const statusColors: Record<string, { bg: string; text: string }> = {
  PENDING: {
    bg: 'bg-gray-100',
    text: 'text-gray-700',
  },
  REVIEWING: {
    bg: 'bg-blue-100',
    text: 'text-blue-700',
  },
  APPROVED: {
    bg: 'bg-green-100',
    text: 'text-green-700',
  },
  REJECTED: {
    bg: 'bg-red-100',
    text: 'text-red-700',
  },
};

/**
 * レビューキューカードコンポーネント
 */
const ReviewQueueCard: React.FC<ReviewQueueCardProps> = ({ item, onClick }) => {
  const priority = priorityConfig[item.priority] || priorityConfig.P1;
  const status = statusColors[item.status] || statusColors.PENDING;
  const isRejected = item.status === 'REJECTED';

  return (
    <div
      className={`p-4 rounded-lg border transition-all duration-200 hover:shadow-md cursor-pointer ${
        isRejected
          ? 'bg-red-50 border-red-300 ring-2 ring-red-200'
          : 'bg-white border-gray-200 hover:border-gray-300'
      }`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onClick?.();
        }
      }}
    >
      {/* ヘッダー: 優先度 + Task ID */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <span className="text-lg" role="img" aria-label={priority.label}>
            {priority.icon}
          </span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded ${priority.bg} ${priority.text}`}>
            {item.priority}
          </span>
          <span className="font-mono text-sm text-gray-900 font-medium">
            {item.taskId}
          </span>
        </div>
        <span className={`text-xs font-medium px-2 py-0.5 rounded ${status.bg} ${status.text}`}>
          {item.status}
        </span>
      </div>

      {/* 提出日時 */}
      <div className="text-xs text-gray-500 mb-1">
        <span className="mr-1">提出:</span>
        <span>{item.submittedAt || '-'}</span>
      </div>

      {/* レビュアー（存在する場合） */}
      {item.reviewer && (
        <div className="text-xs text-gray-500 mb-1">
          <span className="mr-1">レビュアー:</span>
          <span className="font-medium">{item.reviewer}</span>
        </div>
      )}

      {/* 備考（存在する場合） */}
      {item.note && (
        <div className="mt-2 p-2 bg-gray-50 rounded text-xs text-gray-600">
          <span className="font-medium">備考: </span>
          {item.note}
        </div>
      )}

      {/* 差し戻しマーク */}
      {isRejected && (
        <div className="mt-2 flex items-center text-xs text-red-600 font-medium">
          <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z"
              clipRule="evenodd"
            />
          </svg>
          差し戻し - 対応が必要です
        </div>
      )}
    </div>
  );
};

/**
 * 空キューメッセージコンポーネント
 */
const EmptyQueue: React.FC = () => {
  return (
    <div className="text-center py-12">
      <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 rounded-full mb-4">
        <svg
          className="w-8 h-8 text-green-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>
      <h3 className="text-sm font-medium text-gray-900 mb-1">
        レビュー待ちタスクはありません
      </h3>
      <p className="text-xs text-gray-500">
        タスクが完了するとここにレビュー待ちとして表示されます
      </p>
    </div>
  );
};

/**
 * レビューキューコンポーネント
 *
 * レビュー待ちタスク一覧を優先度順に表示します。
 * - P0（差し戻し再提出）→ P1（通常）→ P2（低優先）の順にソート
 * - 差し戻しタスク（REJECTED）は強調表示
 * - 空キュー時は専用メッセージを表示
 */
export const ReviewQueue: React.FC<ReviewQueueProps> = ({ state, onTaskClick }) => {
  const { reviewQueue } = state;

  // 優先度順にソート（P0 > P1 > P2）
  const sortedQueue = [...reviewQueue].sort((a, b) => {
    const priorityOrder = { P0: 0, P1: 1, P2: 2 };
    const orderA = priorityOrder[a.priority as keyof typeof priorityOrder] ?? 1;
    const orderB = priorityOrder[b.priority as keyof typeof priorityOrder] ?? 1;

    // 同じ優先度の場合は提出日時の早い順
    if (orderA === orderB) {
      return (a.submittedAt || '').localeCompare(b.submittedAt || '');
    }

    return orderA - orderB;
  });

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      {/* ヘッダー */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-800 flex items-center">
            <svg
              className="w-5 h-5 mr-2 text-gray-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
              />
            </svg>
            レビューキュー
          </h2>
          <span className="text-sm text-gray-500">
            {sortedQueue.length} 件
          </span>
        </div>
      </div>

      {/* コンテンツ */}
      <div className="p-4">
        {sortedQueue.length === 0 ? (
          <EmptyQueue />
        ) : (
          <div className="space-y-3">
            {sortedQueue.map((item) => (
              <ReviewQueueCard
                key={item.taskId}
                item={item}
                onClick={() => onTaskClick?.(item.taskId)}
              />
            ))}
          </div>
        )}
      </div>

      {/* 凡例（アイテムがある場合のみ表示） */}
      {sortedQueue.length > 0 && (
        <div className="px-4 py-3 border-t border-gray-100 bg-gray-50">
          <div className="flex items-center justify-center space-x-4 text-xs text-gray-500">
            <span className="flex items-center">
              <span className="mr-1">🔴</span> P0: 最優先（差戻し）
            </span>
            <span className="flex items-center">
              <span className="mr-1">🟡</span> P1: 通常
            </span>
            <span className="flex items-center">
              <span className="mr-1">🟢</span> P2: 低優先
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
