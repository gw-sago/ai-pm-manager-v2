/**
 * OrderAddForm - DRAFT ORDER作成フォームコンポーネント
 *
 * ORDER_065: ORDER追加からDRAFT ORDER作成に移行。
 * 内部的には createDraftOrder IPC を呼び出し、バックエンド側で DRAFT ORDER として作成される。
 *
 * - タイトル（必須）
 * - 説明（Markdownテキストエリア）
 * - 優先度（High/Medium/Low）
 * - カテゴリ選択（オプション）
 * - バリデーションとIPC呼び出しロジック
 *
 * @deprecated 旧バックログ専用APIは非推奨。DRAFT ORDER統合APIへ移行中（ORDER_065）
 * @module OrderAddForm
 * @created 2026-02-10
 * @order ORDER_139
 * @task TASK_1160, TASK_314
 */

import React, { useState } from 'react';

/**
 * OrderAddFormのProps
 */
export interface OrderAddFormProps {
  /** プロジェクトID */
  projectId: string;
  /** 閉じるコールバック */
  onClose: () => void;
  /** 追加成功時のコールバック */
  onSuccess?: () => void;
}

/**
 * DRAFT ORDER新規作成フォーム
 *
 * DRAFT ORDERの新規作成フォームを表示します。
 * モーダルダイアログとして表示され、入力バリデーションとIPC呼び出しを実行します。
 *
 * @example
 * ```tsx
 * <OrderAddForm
 *   projectId="ai_pm_manager"
 *   onClose={() => setShowAddForm(false)}
 *   onSuccess={() => handleRefresh()}
 * />
 * ```
 */
export const OrderAddForm: React.FC<OrderAddFormProps> = ({
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

  // ORDER_104: dev_workspace_path未設定時の確認ダイアログ状態
  const [showDevWorkspaceWarning, setShowDevWorkspaceWarning] = useState(false);

  /**
   * ORDER_104: dev_workspace_path未設定チェック付き送信処理
   */
  const doSubmit = async () => {
    setSubmitting(true);
    setError(null);

    try {
      // IPC呼び出し（createDraftOrder）
      const result = await window.electronAPI.createDraftOrder(
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
        setError(result?.error || 'DRAFT ORDERの作成に失敗しました');
      }
    } catch (err) {
      console.error('[OrderAddForm] Failed to create DRAFT ORDER:', err);
      setError('DRAFT ORDERの作成に失敗しました');
    } finally {
      setSubmitting(false);
    }
  };

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

    // ORDER_104: dev_workspace_path未設定チェック
    try {
      const projectInfo = await window.electronAPI.getProjectInfo(projectId);
      if (!projectInfo?.dev_workspace_path) {
        // dev_workspace_pathが未設定の場合は確認ダイアログを表示
        setShowDevWorkspaceWarning(true);
        return;
      }
    } catch (err) {
      console.warn('[OrderAddForm] Failed to check dev_workspace_path:', err);
      // チェック失敗時は警告を表示して続行を促す
      setShowDevWorkspaceWarning(true);
      return;
    }

    await doSubmit();
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
      {/* ORDER_104: dev_workspace_path未設定時の確認ダイアログ */}
      {showDevWorkspaceWarning && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black bg-opacity-60">
          <div
            className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start mb-4">
              <div className="flex-shrink-0 w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center mr-3">
                <svg className="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-gray-900 mb-1">警告</h3>
                <p className="text-sm text-gray-700">
                  dev_workspace_pathが未設定のため本番DBに直接影響します。続行しますか？
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowDevWorkspaceWarning(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                キャンセル
              </button>
              <button
                type="button"
                onClick={async () => {
                  setShowDevWorkspaceWarning(false);
                  await doSubmit();
                }}
                disabled={submitting}
                className="px-4 py-2 text-sm font-medium text-white bg-yellow-600 rounded-lg hover:bg-yellow-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                続行
              </button>
            </div>
          </div>
        </div>
      )}
      {/* モーダルコンテナ */}
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">DRAFT ORDER 新規作成</h2>
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
          {/* ORDER_065: DRAFT ORDER説明 */}
          <div className="mb-4 bg-slate-50 border border-slate-200 rounded-lg p-3 text-slate-700 text-sm">
            <div className="flex items-start">
              <svg className="w-5 h-5 mr-2 flex-shrink-0 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>DRAFT ORDERとして作成されます。PM処理を実行するとPLANNINGステータスに昇格し、タスク分割が行われます。</span>
            </div>
          </div>

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
                ORDER項目の分類に使用できます（50文字以内）
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
            {submitting ? '作成中...' : 'DRAFT作成'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OrderAddForm;
