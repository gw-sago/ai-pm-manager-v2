/**
 * XBacklogList.tsx
 *
 * 横断バックログ一覧
 * ORDER_060 / TASK_651
 */

import React, { useState } from 'react';
import type { XBacklog } from '../preload';
import { XBacklogForm } from './XBacklogForm';
import { XBacklogDispatch } from './XBacklogDispatch';

interface XBacklogListProps {
  supervisorId: string;
  xbacklogs: XBacklog[];
  onRefresh: () => void;
}

const statusLabels: Record<string, string> = {
  PENDING: '未処理',
  ANALYZING: '分析中',
  DISPATCHED: '振り分け済',
  COMPLETED: '完了',
};

const statusColors: Record<string, string> = {
  PENDING: 'bg-yellow-100 text-yellow-800',
  ANALYZING: 'bg-blue-100 text-blue-800',
  DISPATCHED: 'bg-green-100 text-green-800',
  COMPLETED: 'bg-gray-100 text-gray-800',
};

const priorityColors: Record<string, string> = {
  High: 'text-red-600',
  Medium: 'text-yellow-600',
  Low: 'text-gray-600',
};

export const XBacklogList: React.FC<XBacklogListProps> = ({
  supervisorId,
  xbacklogs,
  onRefresh,
}) => {
  const [showForm, setShowForm] = useState(false);
  const [selectedXBacklog, setSelectedXBacklog] = useState<XBacklog | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterPriority, setFilterPriority] = useState<string>('all');

  const filteredXBacklogs = xbacklogs.filter(xb => {
    if (filterStatus !== 'all' && xb.status !== filterStatus) return false;
    if (filterPriority !== 'all' && xb.priority !== filterPriority) return false;
    return true;
  });

  const handleFormClose = () => {
    setShowForm(false);
    onRefresh();
  };

  const handleDispatchClose = () => {
    setSelectedXBacklog(null);
    onRefresh();
  };

  return (
    <div>
      {/* ツールバー */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-sm"
          >
            <option value="all">全ステータス</option>
            <option value="PENDING">未処理</option>
            <option value="ANALYZING">分析中</option>
            <option value="DISPATCHED">振り分け済</option>
            <option value="COMPLETED">完了</option>
          </select>
          <select
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-sm"
          >
            <option value="all">全優先度</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700 text-sm"
        >
          + 新規登録
        </button>
      </div>

      {/* テーブル */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">タイトル</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">優先度</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ステータス</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">振り分け先</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {filteredXBacklogs.map(xb => (
              <tr key={xb.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm text-gray-900">{xb.id}</td>
                <td className="px-4 py-3 text-sm text-gray-900">{xb.title}</td>
                <td className="px-4 py-3 text-sm">
                  <span className={priorityColors[xb.priority] || 'text-gray-600'}>
                    {xb.priority}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${statusColors[xb.status] || 'bg-gray-100 text-gray-800'}`}>
                    {statusLabels[xb.status] || xb.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">
                  {xb.assignedProjectId || '-'}
                </td>
                <td className="px-4 py-3 text-sm">
                  {xb.status === 'PENDING' && (
                    <button
                      onClick={() => setSelectedXBacklog(xb)}
                      className="text-purple-600 hover:text-purple-800"
                    >
                      振り分け
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {filteredXBacklogs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                  横断バックログがありません
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 登録フォームモーダル */}
      {showForm && (
        <XBacklogForm
          supervisorId={supervisorId}
          onClose={handleFormClose}
        />
      )}

      {/* 振り分けモーダル */}
      {selectedXBacklog && (
        <XBacklogDispatch
          xbacklog={selectedXBacklog}
          onClose={handleDispatchClose}
        />
      )}
    </div>
  );
};
