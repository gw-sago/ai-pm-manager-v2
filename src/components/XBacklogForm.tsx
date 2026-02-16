/**
 * XBacklogForm.tsx
 *
 * 横断バックログ登録フォーム
 * ORDER_060 / TASK_652
 */

import React, { useState } from 'react';

interface XBacklogFormProps {
  supervisorId: string;
  onClose: () => void;
}

export const XBacklogForm: React.FC<XBacklogFormProps> = ({
  supervisorId,
  onClose,
}) => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('Medium');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError('タイトルを入力してください');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const result = await window.electronAPI.createXBacklog(
        supervisorId,
        title.trim(),
        description.trim() || null,
        priority
      );
      if (result) {
        onClose();
      } else {
        setError('登録に失敗しました');
      }
    } catch (err) {
      console.error('[XBacklogForm] Failed to create:', err);
      setError('登録に失敗しました');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">横断バックログ登録</h2>
        </div>

        <form onSubmit={handleSubmit} className="p-6">
          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm">
              {error}
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              タイトル <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="例: 全プロジェクト共通のエラーハンドリング改善"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              説明
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="詳細な説明（任意）"
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              優先度
            </label>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="High">High - 優先度高</option>
              <option value="Medium">Medium - 通常</option>
              <option value="Low">Low - 優先度低</option>
            </select>
          </div>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded"
            >
              キャンセル
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
            >
              {submitting ? '登録中...' : '登録'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
