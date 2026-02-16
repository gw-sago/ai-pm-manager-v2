/**
 * PortfolioView.tsx
 *
 * ポートフォリオ統合ビュー - 全プロジェクトのORDER・バックログを一覧表示
 * ORDER_068 / BACKLOG_116
 */

import React, { useState, useEffect } from 'react';
import type { SupervisorProject } from '../preload';

// ポートフォリオ用のORDER型定義
interface PortfolioOrder {
  id: string;
  portfolioId: string; // "projectName/ORDER_XXX"
  projectId: string;
  projectName: string;
  title: string;
  status: string;
  priority: string;
  progress: number;
  taskCount: number;
  completedTaskCount: number;
  createdAt: string;
  updatedAt: string;
}

// ポートフォリオ用のバックログ型定義
interface PortfolioBacklog {
  id: string;
  portfolioId: string; // "projectName/BACKLOG_XXX"
  projectId: string;
  projectName: string;
  title: string;
  status: string;
  priority: string;
  description: string | null;
  createdAt: string;
  updatedAt: string;
}

// ORDER配下のタスク型定義
interface PortfolioTask {
  id: string;
  orderId: string;
  title: string;
  status: string;
  priority: string;
  createdAt: string;
}

// ポートフォリオデータ型定義
interface PortfolioData {
  orders: PortfolioOrder[];
  backlogs: PortfolioBacklog[];
}

interface PortfolioViewProps {
  supervisorId: string;
  projects: SupervisorProject[];
}

// ステータスカラーマップ
const statusColors: Record<string, string> = {
  // ORDER/TASK ステータス
  QUEUED: 'bg-gray-100 text-gray-700',
  IN_PROGRESS: 'bg-blue-100 text-blue-700',
  DONE: 'bg-green-100 text-green-700',
  COMPLETED: 'bg-green-200 text-green-800',
  REWORK: 'bg-orange-100 text-orange-700',
  BLOCKED: 'bg-red-100 text-red-700',
  INTERRUPTED: 'bg-yellow-100 text-yellow-700',
  // BACKLOG ステータス
  TODO: 'bg-gray-100 text-gray-700',
  ORDERED: 'bg-purple-100 text-purple-700',
  // デフォルト
  default: 'bg-gray-100 text-gray-700',
};

// 優先度カラーマップ
const priorityColors: Record<string, string> = {
  P0: 'bg-red-500 text-white',
  P1: 'bg-orange-500 text-white',
  P2: 'bg-yellow-500 text-white',
  High: 'bg-red-500 text-white',
  Medium: 'bg-orange-500 text-white',
  Low: 'bg-gray-500 text-white',
  default: 'bg-gray-400 text-white',
};

const getStatusColor = (status: string): string => statusColors[status] || statusColors.default;
const getPriorityColor = (priority: string): string => priorityColors[priority] || priorityColors.default;

/** ポートフォリオビューアイコン */
const PortfolioIcon: React.FC = () => (
  <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
  </svg>
);

export const PortfolioView: React.FC<PortfolioViewProps> = ({ supervisorId, projects }) => {
  const [portfolioData, setPortfolioData] = useState<PortfolioData | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<PortfolioOrder | null>(null);
  const [selectedBacklog, setSelectedBacklog] = useState<PortfolioBacklog | null>(null);
  const [orderTasks, setOrderTasks] = useState<PortfolioTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // フィルタ状態
  const [statusFilter, setStatusFilter] = useState<string[]>(['IN_PROGRESS', 'QUEUED', 'TODO']);
  const [priorityFilter, setPriorityFilter] = useState<string[]>([]);

  // ポートフォリオデータを取得
  useEffect(() => {
    const fetchPortfolioData = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await window.electronAPI.getPortfolioData(supervisorId);
        setPortfolioData(data);
      } catch (err) {
        console.error('[PortfolioView] Failed to fetch portfolio data:', err);
        setError('ポートフォリオデータの取得に失敗しました');
      } finally {
        setLoading(false);
      }
    };
    fetchPortfolioData();
  }, [supervisorId]);

  // ORDER選択時にタスク一覧を取得
  useEffect(() => {
    if (!selectedOrder) {
      setOrderTasks([]);
      return;
    }
    const fetchTasks = async () => {
      try {
        const tasks = await window.electronAPI.getPortfolioOrderTasks(
          selectedOrder.projectId,
          selectedOrder.id
        );
        setOrderTasks(tasks);
      } catch (err) {
        console.error('[PortfolioView] Failed to fetch order tasks:', err);
        setOrderTasks([]);
      }
    };
    fetchTasks();
  }, [selectedOrder]);

  // フィルタ適用
  const filteredOrders = portfolioData?.orders.filter(order => {
    if (statusFilter.length > 0 && !statusFilter.includes(order.status)) return false;
    if (priorityFilter.length > 0 && !priorityFilter.includes(order.priority)) return false;
    return true;
  }) || [];

  const filteredBacklogs = portfolioData?.backlogs.filter(backlog => {
    if (statusFilter.length > 0 && !statusFilter.includes(backlog.status)) return false;
    if (priorityFilter.length > 0 && !priorityFilter.includes(backlog.priority)) return false;
    return true;
  }) || [];

  // ステータスフィルタのトグル
  const toggleStatusFilter = (status: string) => {
    setStatusFilter(prev =>
      prev.includes(status) ? prev.filter(s => s !== status) : [...prev, status]
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        {error}
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* ヘッダー */}
      <div className="flex items-center gap-2 mb-4">
        <PortfolioIcon />
        <h2 className="text-lg font-semibold text-gray-900">ポートフォリオビュー</h2>
        <span className="text-sm text-gray-500">
          ({filteredOrders.length} ORDER / {filteredBacklogs.length} BACKLOG)
        </span>
      </div>

      {/* フィルタバー */}
      <div className="flex gap-4 mb-4 p-3 bg-gray-50 rounded-lg">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">ステータス:</span>
          {['IN_PROGRESS', 'QUEUED', 'TODO', 'DONE', 'COMPLETED'].map(status => (
            <button
              key={status}
              onClick={() => toggleStatusFilter(status)}
              className={`px-2 py-1 text-xs rounded ${
                statusFilter.includes(status)
                  ? getStatusColor(status)
                  : 'bg-white text-gray-400 border border-gray-200'
              }`}
            >
              {status}
            </button>
          ))}
        </div>
      </div>

      {/* 3カラムレイアウト */}
      <div className="flex-1 grid grid-cols-3 gap-4 min-h-0">
        {/* 左カラム: ORDER一覧 */}
        <div className="bg-white border border-gray-200 rounded-lg flex flex-col overflow-hidden">
          <div className="p-3 bg-gray-50 border-b border-gray-200">
            <h3 className="font-medium text-gray-700">ORDER一覧</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {filteredOrders.length === 0 ? (
              <div className="text-center text-gray-400 py-8">該当なし</div>
            ) : (
              <div className="space-y-2">
                {filteredOrders.map(order => (
                  <div
                    key={order.id}
                    onClick={() => {
                      setSelectedOrder(order);
                      setSelectedBacklog(null);
                    }}
                    className={`p-3 rounded-lg cursor-pointer transition-colors ${
                      selectedOrder?.id === order.id
                        ? 'bg-indigo-50 border-2 border-indigo-400'
                        : 'bg-gray-50 hover:bg-gray-100 border border-gray-200'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-indigo-600">
                        {order.portfolioId}
                      </span>
                      <span className={`px-2 py-0.5 text-xs rounded ${getStatusColor(order.status)}`}>
                        {order.status}
                      </span>
                    </div>
                    <div className="text-sm text-gray-900 truncate">{order.title}</div>
                    <div className="flex items-center gap-2 mt-2">
                      <span className={`px-1.5 py-0.5 text-xs rounded ${getPriorityColor(order.priority)}`}>
                        {order.priority}
                      </span>
                      <span className="text-xs text-gray-500">
                        {order.completedTaskCount}/{order.taskCount} tasks
                      </span>
                      {order.taskCount > 0 && (
                        <div className="flex-1 h-1 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-green-500 rounded-full"
                            style={{ width: `${(order.completedTaskCount / order.taskCount) * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 中央カラム: バックログ一覧 */}
        <div className="bg-white border border-gray-200 rounded-lg flex flex-col overflow-hidden">
          <div className="p-3 bg-gray-50 border-b border-gray-200">
            <h3 className="font-medium text-gray-700">バックログ一覧</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {filteredBacklogs.length === 0 ? (
              <div className="text-center text-gray-400 py-8">該当なし</div>
            ) : (
              <div className="space-y-2">
                {filteredBacklogs.map(backlog => (
                  <div
                    key={backlog.id}
                    onClick={() => {
                      setSelectedBacklog(backlog);
                      setSelectedOrder(null);
                    }}
                    className={`p-3 rounded-lg cursor-pointer transition-colors ${
                      selectedBacklog?.id === backlog.id
                        ? 'bg-indigo-50 border-2 border-indigo-400'
                        : 'bg-gray-50 hover:bg-gray-100 border border-gray-200'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-purple-600">
                        {backlog.portfolioId}
                      </span>
                      <span className={`px-2 py-0.5 text-xs rounded ${getStatusColor(backlog.status)}`}>
                        {backlog.status}
                      </span>
                    </div>
                    <div className="text-sm text-gray-900 truncate">{backlog.title}</div>
                    <div className="flex items-center gap-2 mt-2">
                      <span className={`px-1.5 py-0.5 text-xs rounded ${getPriorityColor(backlog.priority)}`}>
                        {backlog.priority}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 右カラム: 詳細パネル */}
        <div className="bg-white border border-gray-200 rounded-lg flex flex-col overflow-hidden">
          <div className="p-3 bg-gray-50 border-b border-gray-200">
            <h3 className="font-medium text-gray-700">詳細</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {selectedOrder ? (
              <div>
                <div className="mb-4">
                  <div className="text-xs text-indigo-600 font-medium mb-1">
                    {selectedOrder.portfolioId}
                  </div>
                  <h4 className="text-lg font-semibold text-gray-900">{selectedOrder.title}</h4>
                </div>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-gray-50 p-2 rounded">
                    <div className="text-xs text-gray-500">ステータス</div>
                    <span className={`px-2 py-0.5 text-xs rounded ${getStatusColor(selectedOrder.status)}`}>
                      {selectedOrder.status}
                    </span>
                  </div>
                  <div className="bg-gray-50 p-2 rounded">
                    <div className="text-xs text-gray-500">優先度</div>
                    <span className={`px-1.5 py-0.5 text-xs rounded ${getPriorityColor(selectedOrder.priority)}`}>
                      {selectedOrder.priority}
                    </span>
                  </div>
                  <div className="bg-gray-50 p-2 rounded">
                    <div className="text-xs text-gray-500">タスク進捗</div>
                    <div className="text-sm font-medium">
                      {selectedOrder.completedTaskCount} / {selectedOrder.taskCount}
                    </div>
                  </div>
                  <div className="bg-gray-50 p-2 rounded">
                    <div className="text-xs text-gray-500">プロジェクト</div>
                    <div className="text-sm font-medium">{selectedOrder.projectName}</div>
                  </div>
                </div>

                {/* タスク一覧 */}
                <div className="mt-4">
                  <h5 className="text-sm font-medium text-gray-700 mb-2">タスク一覧</h5>
                  {orderTasks.length === 0 ? (
                    <div className="text-sm text-gray-400">タスクなし</div>
                  ) : (
                    <div className="space-y-2">
                      {orderTasks.map(task => (
                        <div
                          key={task.id}
                          className="p-2 bg-gray-50 rounded border border-gray-200"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-medium text-gray-600">{task.id}</span>
                            <span className={`px-2 py-0.5 text-xs rounded ${getStatusColor(task.status)}`}>
                              {task.status}
                            </span>
                          </div>
                          <div className="text-sm text-gray-900 mt-1">{task.title}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : selectedBacklog ? (
              <div>
                <div className="mb-4">
                  <div className="text-xs text-purple-600 font-medium mb-1">
                    {selectedBacklog.portfolioId}
                  </div>
                  <h4 className="text-lg font-semibold text-gray-900">{selectedBacklog.title}</h4>
                </div>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-gray-50 p-2 rounded">
                    <div className="text-xs text-gray-500">ステータス</div>
                    <span className={`px-2 py-0.5 text-xs rounded ${getStatusColor(selectedBacklog.status)}`}>
                      {selectedBacklog.status}
                    </span>
                  </div>
                  <div className="bg-gray-50 p-2 rounded">
                    <div className="text-xs text-gray-500">優先度</div>
                    <span className={`px-1.5 py-0.5 text-xs rounded ${getPriorityColor(selectedBacklog.priority)}`}>
                      {selectedBacklog.priority}
                    </span>
                  </div>
                  <div className="bg-gray-50 p-2 rounded col-span-2">
                    <div className="text-xs text-gray-500">プロジェクト</div>
                    <div className="text-sm font-medium">{selectedBacklog.projectName}</div>
                  </div>
                </div>

                {selectedBacklog.description && (
                  <div className="mt-4">
                    <h5 className="text-sm font-medium text-gray-700 mb-2">説明</h5>
                    <div className="text-sm text-gray-600 bg-gray-50 p-3 rounded whitespace-pre-wrap">
                      {selectedBacklog.description}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-gray-400">
                ORDERまたはバックログを選択してください
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
