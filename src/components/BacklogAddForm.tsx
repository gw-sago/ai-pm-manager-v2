/**
 * BacklogAddForm - バックログ新規追加フォームコンポーネント
 *
 * バックログ項目の新規追加フォームを提供します。
 * - タイトル（必須）
 * - 説明（Markdownテキストエリア）
 * - 優先度（High/Medium/Low）
 * - カテゴリ選択（オプション）
 * - バリデーションとIPC呼び出しロジック
 *
 * @module BacklogAddForm
 * @created 2026-02-10
 * @order ORDER_139
 * @task TASK_1160
 */

import React, { useState } from 'react';

/**
 * BacklogAddFormのProps
 */
export interface BacklogAddFormProps {
  /** プロジェクトID */
  projectId: string;
  /** 閉じるコールバック */
  onClose: () => void;
  /** 追加成功時のコールバック */
  onSuccess?: () => void;
}

/**
 * バックログ新規追加フォーム
 *
 * バックログ項目の新規追加フォームを表示します。
 * モーダルダイアログとして表示され、入力バリデーションとIPC呼び出しを実行します。
 *
 * @example
 * ```tsx
 * <BacklogAddForm
 *   projectId="ai_pm_manager"
 *   onClose={() => setShowAddForm(false)}
 *   onSuccess={() => handleRefresh()}
 * />
 * ```
 */
export const BacklogAddForm: React.FC<BacklogAddFormProps> = ({
  projectId,
  onClose,
  onSuccess,
}) => {
  // フォーム状態
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<'High' | 'Medium' | 'Low'>('Medium');
  const [category, setCategory] = useState('');

  // UI状態
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * フォーム送信ハンドラ
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // バリデーション
    if (!title.trim()) {
      setError('タイトルを入力してください');
      return;
    }

    if (title.trim().length > 200) {
      setError('タイトルは200文字以内で入力してください');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      // IPC呼び出し（addBacklog）
      const result = await window.electronAPI.addBacklog(
        projectId,
        title.trim(),
        description.trim() || null,
        priority,
        category.trim() || undefined
      );

      if (result && result.success) {
        // 成功時
        if (onSuccess) {
          onSuccess();
        }
        onClose();
      } else {
        setError(result?.error || 'バックログの追加に失敗しました');
      }
    } catch (err) {
      console.error('[BacklogAddForm] Failed to add backlog:', err);
      setError('バックログの追加に失敗しました');
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * バックドロップクリックで閉じる
   */
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  /**
   * ESCキーで閉じる
   */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
      onClick={handleBackdropClick}
      onKeyDown={handleKeyDown}
    >
      {/* モーダルコンテナ */}
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">バックログ新規追加</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-md transition-colors"
            title="閉じる"
            aria-label="閉じる"
          >
            <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* フォーム */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6">
          {/* エラーメッセージ */}
          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-sm">
              <div className="flex items-start">
                <svg className="w-5 h-5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <span>{error}</span>
              </div>
            </div>
          )}

          <div className="space-y-4">
            {/* プロジェクトID（読み取り専用） */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                プロジェクト
              </label>
              <input
                type="text"
                value={projectId}
                disabled
                className="w-full border border-gray-300 rounded-lg px-3 py-2 bg-gray-50 text-gray-600 cursor-not-allowed"
              />
            </div>

            {/* タイトル（必須） */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                タイトル <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="例: ユーザー認証機能の実装"
                maxLength={200}
                required
              />
              <p className="mt-1 text-xs text-gray-500">
                {title.length}/200文字
              </p>
            </div>

            {/* 説明（Markdownテキストエリア） */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                説明（Markdown対応）
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={8}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
                placeholder="詳細な説明を記述してください（任意）&#10;&#10;## 背景&#10;- 現状の課題&#10;- 解決したい問題&#10;&#10;## 実装内容&#10;- 実装する機能の詳細&#10;&#10;## 受け入れ条件&#10;- [ ] 条件1&#10;- [ ] 条件2"
              />
              <p className="mt-1 text-xs text-gray-500">
                Markdown記法が使用できます（**太字**、`コード`、# 見出し、など）
              </p>
            </div>

            {/* 優先度 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                優先度
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as 'High' | 'Medium' | 'Low')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="High">High - 優先度高（緊急・重要）</option>
                <option value="Medium">Medium - 通常</option>
                <option value="Low">Low - 優先度低</option>
              </select>
            </div>

            {/* カテゴリ（オプション） */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                カテゴリ（オプション）
              </label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="例: Feature, Bug, Refactoring, Documentation"
                maxLength={50}
              />
              <p className="mt-1 text-xs text-gray-500">
                バックログ項目の分類に使用できます（50文字以内）
              </p>
            </div>
          </div>
        </form>

        {/* フッター */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            disabled={submitting}
          >
            キャンセル
          </button>
          <button
            type="submit"
            onClick={handleSubmit}
            disabled={submitting || !title.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? '追加中...' : '追加'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default BacklogAddForm;
