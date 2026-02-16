import React from 'react';
import type { OrderRelatedInfo } from '../preload';

interface RelatedInfoSectionProps {
  /** 関連情報 */
  relatedInfo: OrderRelatedInfo;
}

/**
 * 関連情報セクションコンポーネント
 *
 * ORDER_045: ORDER成果物タブの情報充実化
 * TASK_600: RelatedInfoSection実装
 *
 * 関連バックログ、依存ORDERを表示するセクション。
 */
export const RelatedInfoSection: React.FC<RelatedInfoSectionProps> = ({
  relatedInfo,
}) => {
  const hasRelatedBacklogs = relatedInfo.relatedBacklogs.length > 0;
  const hasDependentOrders = relatedInfo.dependentOrders.length > 0;

  // 関連情報がない場合
  if (!hasRelatedBacklogs && !hasDependentOrders) {
    return (
      <div className="mb-4">
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          関連情報
        </h4>
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
          <div className="flex items-center text-sm text-gray-500">
            <svg
              className="w-4 h-4 mr-2 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            関連情報はありません
          </div>
        </div>
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    const statusColors: Record<string, string> = {
      TODO: 'bg-gray-100 text-gray-700',
      IN_PROGRESS: 'bg-blue-100 text-blue-700',
      DONE: 'bg-green-100 text-green-700',
      COMPLETED: 'bg-green-100 text-green-700',
      CANCELED: 'bg-red-100 text-red-700',
      PLANNING: 'bg-purple-100 text-purple-700',
      REVIEW: 'bg-yellow-100 text-yellow-700',
    };

    const colorClass = statusColors[status.toUpperCase()] || 'bg-gray-100 text-gray-700';

    return (
      <span className={`px-1.5 py-0.5 text-xs rounded ${colorClass}`}>
        {status}
      </span>
    );
  };

  return (
    <div className="mb-4">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
        関連情報
      </h4>

      <div className="space-y-3">
        {/* 関連バックログ */}
        {hasRelatedBacklogs && (
          <div className="bg-white border border-gray-200 rounded-lg p-3">
            <div className="flex items-center mb-2">
              <svg
                className="w-4 h-4 text-blue-500 mr-2"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                />
              </svg>
              <span className="text-sm font-medium text-gray-700">
                関連バックログ ({relatedInfo.relatedBacklogs.length})
              </span>
            </div>
            <ul className="space-y-1.5">
              {relatedInfo.relatedBacklogs.map((backlog) => (
                <li
                  key={backlog.id}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="flex items-center min-w-0">
                    <span className="font-mono text-xs text-blue-600 mr-2 flex-shrink-0">
                      {backlog.id}
                    </span>
                    <span className="text-gray-600 truncate">
                      {backlog.title}
                    </span>
                  </div>
                  {getStatusBadge(backlog.status)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 依存ORDER */}
        {hasDependentOrders && (
          <div className="bg-white border border-gray-200 rounded-lg p-3">
            <div className="flex items-center mb-2">
              <svg
                className="w-4 h-4 text-purple-500 mr-2"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
                />
              </svg>
              <span className="text-sm font-medium text-gray-700">
                依存ORDER ({relatedInfo.dependentOrders.length})
              </span>
            </div>
            <ul className="space-y-1.5">
              {relatedInfo.dependentOrders.map((order) => (
                <li
                  key={order.id}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="flex items-center min-w-0">
                    <span className="font-mono text-xs text-purple-600 mr-2 flex-shrink-0">
                      {order.id}
                    </span>
                    <span className="text-gray-600 truncate">{order.title}</span>
                  </div>
                  {getStatusBadge(order.status)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};
