import React, { useState, useMemo } from 'react';
import { TaskList } from './TaskList';
import { ProgressBar } from './ProgressBar';
import type { OrderInfo, TaskInfo, ParsedState } from '../preload';

interface OrderListProps {
  state: ParsedState;
  onTaskClick?: (task: TaskInfo) => void;
}

interface OrderItemProps {
  order: OrderInfo;
  isExpanded: boolean;
  onToggle: () => void;
  onTaskClick?: (task: TaskInfo) => void;
}

/**
 * ORDERステータスに応じた色定義
 */
const orderStatusColors: Record<string, { bg: string; text: string }> = {
  COMPLETED: {
    bg: 'bg-green-100',
    text: 'text-green-800',
  },
  IN_PROGRESS: {
    bg: 'bg-blue-100',
    text: 'text-blue-800',
  },
  REVIEW: {
    bg: 'bg-yellow-100',
    text: 'text-yellow-800',
  },
  PLANNING: {
    bg: 'bg-purple-100',
    text: 'text-purple-800',
  },
  ON_HOLD: {
    bg: 'bg-gray-100',
    text: 'text-gray-800',
  },
};

/**
 * ORDER進捗率を計算
 */
const calculateProgress = (tasks: TaskInfo[]): { completed: number; total: number; percentage: number } => {
  const total = tasks.length;
  const completed = tasks.filter(t => t.status === 'COMPLETED').length;
  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
  return { completed, total, percentage };
};

/**
 * ORDERアイテムコンポーネント
 */
const OrderItem: React.FC<OrderItemProps> = ({
  order,
  isExpanded,
  onToggle,
  onTaskClick,
}) => {
  const colors = orderStatusColors[order.status] || orderStatusColors.IN_PROGRESS;
  const progress = calculateProgress(order.tasks);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
      {/* ORDERヘッダー（クリックで展開・折りたたみ） */}
      <div
        className="flex items-center p-4 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={onToggle}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            onToggle();
          }
        }}
      >
        {/* 展開・折りたたみアイコン */}
        <div className="flex-shrink-0 mr-3">
          <svg
            className={`w-5 h-5 text-gray-500 transition-transform duration-200 ${
              isExpanded ? 'transform rotate-90' : ''
            }`}
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </div>

        {/* ORDER情報 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center space-x-3">
            <span className="font-semibold text-gray-900">{order.id}</span>
            {order.title && (
              <span className="text-gray-600 truncate">- {order.title}</span>
            )}
          </div>

          {/* 進捗バー */}
          <div className="mt-2">
            <ProgressBar
              value={progress.completed}
              max={progress.total}
              color={order.status === 'COMPLETED' ? 'green' : 'blue'}
              size="sm"
              showLabel={true}
            />
          </div>
        </div>

        {/* ステータスバッジ */}
        <div className="flex-shrink-0 ml-4">
          <span
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}
          >
            {order.status}
          </span>
        </div>
      </div>

      {/* タスク一覧（展開時のみ表示） */}
      {isExpanded && (
        <div className="border-t border-gray-200 p-4 bg-gray-50">
          <TaskList
            tasks={order.tasks}
            onTaskClick={onTaskClick}
            emptyMessage="このORDERにはタスクがありません"
          />
        </div>
      )}
    </div>
  );
};

/**
 * ORDER一覧コンポーネント
 *
 * プロジェクトのORDER一覧を表示し、各ORDERを展開・折りたたみできます。
 * 各ORDERには進捗率とステータスが表示され、展開するとタスク一覧が表示されます。
 */
export const OrderList: React.FC<OrderListProps> = ({
  state,
  onTaskClick,
}) => {
  // 展開状態を管理（ORDER IDをキーとしたSet）
  const [expandedOrders, setExpandedOrders] = useState<Set<string>>(
    // アクティブORDERがある場合は最初から展開
    () => new Set(state.projectInfo.currentOrderId ? [state.projectInfo.currentOrderId] : [])
  );

  // ORDERをソート（IN_PROGRESS/REVIEW > その他 > COMPLETED、同じステータス内ではID降順）
  const sortedOrders = useMemo(() => {
    return [...state.orders].sort((a, b) => {
      const statusPriority: Record<string, number> = {
        IN_PROGRESS: 0,
        REVIEW: 1,
        REWORK: 2,
        PLANNING: 3,
        ON_HOLD: 4,
        COMPLETED: 5,
      };

      const aPriority = statusPriority[a.status] ?? 3;
      const bPriority = statusPriority[b.status] ?? 3;

      if (aPriority !== bPriority) {
        return aPriority - bPriority;
      }

      // 同じステータスの場合、ORDER IDを降順（新しい順）
      return b.id.localeCompare(a.id);
    });
  }, [state.orders]);

  /**
   * ORDER展開・折りたたみトグル
   */
  const handleToggle = (orderId: string) => {
    setExpandedOrders((prev) => {
      const next = new Set(prev);
      if (next.has(orderId)) {
        next.delete(orderId);
      } else {
        next.add(orderId);
      }
      return next;
    });
  };

  /**
   * 全て展開
   */
  const handleExpandAll = () => {
    setExpandedOrders(new Set(state.orders.map((o) => o.id)));
  };

  /**
   * 全て折りたたみ
   */
  const handleCollapseAll = () => {
    setExpandedOrders(new Set());
  };

  if (state.orders.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="text-center py-8">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-gray-100 rounded-full mb-4">
            <svg
              className="w-6 h-6 text-gray-400"
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
          </div>
          <h3 className="text-sm font-medium text-gray-900 mb-1">
            ORDERがありません
          </h3>
          <p className="text-xs text-gray-500">
            STATE.mdにタスク一覧セクションが見つかりません
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      {/* ヘッダー */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800">
          ORDER一覧
        </h2>
        <div className="flex items-center space-x-2">
          <button
            onClick={handleExpandAll}
            className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
            title="全て展開"
          >
            全て展開
          </button>
          <span className="text-gray-300">|</span>
          <button
            onClick={handleCollapseAll}
            className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
            title="全て折りたたみ"
          >
            全て折りたたみ
          </button>
        </div>
      </div>

      {/* ORDER一覧 */}
      <div className="p-4 space-y-3">
        {sortedOrders.map((order) => (
          <OrderItem
            key={order.id}
            order={order}
            isExpanded={expandedOrders.has(order.id)}
            onToggle={() => handleToggle(order.id)}
            onTaskClick={onTaskClick}
          />
        ))}
      </div>

      {/* フッター */}
      <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 text-xs text-gray-500 text-center">
        {state.orders.length} ORDER / {state.tasks.length} タスク
      </div>
    </div>
  );
};
