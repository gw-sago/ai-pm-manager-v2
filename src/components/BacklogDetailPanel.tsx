/**
 * BacklogDetailPanel - バックログ詳細表示パネル
 *
 * バックログカードクリック時に詳細情報を表示するパネルコンポーネント。
 * ORDER詳細やタスク詳細と同様のUI/UXを提供。
 *
 * @module BacklogDetailPanel
 * @created 2026-02-10
 * @order ORDER_123
 * @task TASK_1108
 */

import React, { useState, useEffect } from 'react';
import type { BacklogItem } from '../preload';

interface BacklogDetailPanelProps {
  /** バックログ項目 */
  item: BacklogItem;
  /** 閉じるコールバック */
  onClose: () => void;
  /** ORDER IDクリック時のコールバック */
  onOrderClick?: (orderId: string) => void;
}

/**
 * バックログ詳細表示パネル
 *
 * バックログ項目の詳細情報を表示します。
 * - タイトル
 * - 説明全文
 * - 優先度
 * - ステータス
 * - 関連ORDER（クリック可能リンク）
 * - 作成日
 * - 更新日
 * - 完了日（該当する場合）
 * - ORDER進捗情報（関連ORDERがある場合）
 *
 * @example
 * ```tsx
 * <BacklogDetailPanel
 *   item={backlogItem}
 *   onClose={() => setSelectedItem(null)}
 *   onOrderClick={(orderId) => handleOrderClick(orderId)}
 * />
 * ```
 */
export const BacklogDetailPanel: React.FC<BacklogDetailPanelProps> = ({
  item,
  onClose,
  onOrderClick,
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // 編集用の状態
  const [editTitle, setEditTitle] = useState(item.title);
  const [editDescription, setEditDescription] = useState(item.description || '');
  const [editPriority, setEditPriority] = useState<'High' | 'Medium' | 'Low'>(item.priority as 'High' | 'Medium' | 'Low');
  const [editSortOrder, setEditSortOrder] = useState(item.sortOrder ?? 999);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // マウント時にフェードインアニメーションを開始
  useEffect(() => {
    // 次のフレームでアニメーション開始（DOMレンダリング後）
    requestAnimationFrame(() => {
      setIsVisible(true);
    });
  }, []);

  /**
   * 閉じるアニメーション付きハンドラ
   */
  const handleClose = () => {
    setIsVisible(false);
    // アニメーション完了後にコールバック実行
    setTimeout(() => {
      onClose();
    }, 200); // transition duration: 200ms
  };

  /**
   * バックドロップクリックで閉じる
   */
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      handleClose();
    }
  };

  /**
   * ORDER IDクリックハンドラ
   */
  const handleOrderIdClick = () => {
    if (item.relatedOrderId && onOrderClick) {
      onOrderClick(item.relatedOrderId);
      handleClose();
    }
  };

  /**
   * 編集モード開始ハンドラ
   */
  const handleStartEdit = () => {
    setIsEditing(true);
    setError(null);
  };

  /**
   * 編集キャンセルハンドラ
   */
  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditTitle(item.title);
    setEditDescription(item.description || '');
    setEditPriority(item.priority as 'High' | 'Medium' | 'Low');
    setEditSortOrder(item.sortOrder ?? 999);
    setError(null);
  };

  /**
   * 保存ハンドラ
   */
  const handleSave = async () => {
    // バリデーション
    if (!editTitle.trim()) {
      setError('タイトルを入力してください');
      return;
    }

    if (editTitle.trim().length > 200) {
      setError('タイトルは200文字以内で入力してください');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      // IPC呼び出し（updateBacklog）
      const result = await window.electronAPI.updateBacklog(
        item.projectId,
        item.id,
        {
          title: editTitle.trim(),
          description: editDescription.trim() || undefined,
          priority: editPriority,
          sortOrder: editSortOrder,
        }
      );

      if (result && result.success) {
        // 成功時：編集モードを終了
        setIsEditing(false);
        // パネルを閉じてリフレッシュを促す
        handleClose();
      } else {
        setError(result?.error || 'バックログの更新に失敗しました');
      }
    } catch (err) {
      console.error('[BacklogDetailPanel] Failed to update backlog:', err);
      setError('バックログの更新に失敗しました');
    } finally {
      setSaving(false);
    }
  };

  /**
   * 優先度に応じたバッジの色を取得
   */
  const getPriorityColor = (priority: string): string => {
    switch (priority) {
      case 'High':
        return 'bg-red-100 text-red-700 border-red-200';
      case 'Medium':
        return 'bg-yellow-100 text-yellow-700 border-yellow-200';
      case 'Low':
        return 'bg-green-100 text-green-700 border-green-200';
      default:
        return 'bg-gray-100 text-gray-600 border-gray-200';
    }
  };

  /**
   * ステータスに応じたバッジの色を取得
   */
  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'TODO':
        return 'bg-gray-100 text-gray-600';
      case 'IN_PROGRESS':
        return 'bg-blue-100 text-blue-600';
      case 'BLOCKED':
        return 'bg-orange-100 text-orange-600';
      case 'DONE':
        return 'bg-green-100 text-green-600';
      case 'CANCELLED':
        return 'bg-gray-200 text-gray-500';
      default:
        return 'bg-gray-100 text-gray-600';
    }
  };

  /**
   * ORDERステータスに応じたバッジの色を取得
   */
  const getOrderStatusColor = (status: string): string => {
    switch (status) {
      case 'PLANNING':
        return 'bg-yellow-100 text-yellow-700 border-yellow-200';
      case 'IN_PROGRESS':
        return 'bg-blue-100 text-blue-700 border-blue-200';
      case 'REVIEW':
        return 'bg-purple-100 text-purple-700 border-purple-200';
      case 'COMPLETED':
        return 'bg-green-100 text-green-700 border-green-200';
      case 'ON_HOLD':
        return 'bg-orange-100 text-orange-700 border-orange-200';
      case 'CANCELLED':
        return 'bg-red-100 text-red-700 border-red-200';
      default:
        return 'bg-gray-100 text-gray-600 border-gray-200';
    }
  };

  /**
   * 日付フォーマット
   */
  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return '-';
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

  // 進捗率計算
  const progressPercent = item.progressPercent ?? 0;
  const hasOrder = !!item.relatedOrderId;

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-black transition-opacity duration-200 ${
        isVisible ? 'bg-opacity-50' : 'bg-opacity-0'
      }`}
      onClick={handleBackdropClick}
    >
      {/* モーダルコンテナ */}
      <div
        className={`bg-white rounded-lg shadow-xl border border-gray-200 w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col transition-all duration-200 ${
          isVisible ? 'scale-100 opacity-100' : 'scale-95 opacity-0'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ヘッダー */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            <div className="flex items-center gap-2">
              {/* BACKLOG ID */}
              <span className="text-xs text-purple-600 font-medium bg-purple-50 px-2 py-1 rounded">
                {item.id}
              </span>
              {/* 優先度バッジ */}
              <span className={`inline-flex px-2 py-1 text-xs font-medium rounded border ${getPriorityColor(item.priority)}`}>
                {item.priority}
              </span>
              {/* ステータスバッジ */}
              <span className={`inline-flex px-2 py-1 text-xs font-medium rounded ${getStatusColor(item.status)}`}>
                {item.status}
              </span>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="p-2 hover:bg-gray-100 rounded-md transition-colors"
            title="閉じる"
            aria-label="閉じる"
          >
            <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* コンテンツ */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* エラーメッセージ */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-sm">
              <div className="flex items-start">
                <svg className="w-5 h-5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <span>{error}</span>
              </div>
            </div>
          )}

          {/* タイトル */}
          {isEditing ? (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                タイトル <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                maxLength={200}
                required
              />
              <p className="mt-1 text-xs text-gray-500">
                {editTitle.length}/200文字
              </p>
            </div>
          ) : (
            <div>
              <h2 className="text-xl font-semibold text-gray-900 mb-1">
                {item.title}
              </h2>
              <p className="text-sm text-gray-500">プロジェクト: {item.projectId}</p>
            </div>
          )}

          {/* 説明 */}
          {isEditing ? (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                説明（Markdown対応）
              </label>
              <textarea
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                rows={8}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
              />
            </div>
          ) : (
            item.description && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">説明</h3>
                <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap">
                  {item.description}
                </div>
              </div>
            )
          )}

          {/* 優先度（編集モード） */}
          {isEditing && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                優先度
              </label>
              <select
                value={editPriority}
                onChange={(e) => setEditPriority(e.target.value as 'High' | 'Medium' | 'Low')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="High">High - 優先度高</option>
                <option value="Medium">Medium - 通常</option>
                <option value="Low">Low - 優先度低</option>
              </select>
            </div>
          )}

          {/* ソート順序（編集モード） */}
          {isEditing && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                ソート順序
              </label>
              <input
                type="number"
                value={editSortOrder}
                onChange={(e) => setEditSortOrder(parseInt(e.target.value, 10) || 999)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                min={0}
                max={9999}
              />
              <p className="mt-1 text-xs text-gray-500">
                小さいほど上位に表示されます（デフォルト: 999）
              </p>
            </div>
          )}

          {/* 関連ORDER情報 */}
          {hasOrder ? (
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-3">関連ORDER</h3>
              <div className="bg-blue-50 rounded-lg p-4 space-y-3">
                {/* ORDER ID（クリック可能） */}
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-600">ORDER ID:</span>
                  <button
                    onClick={handleOrderIdClick}
                    className="text-sm text-blue-600 font-medium bg-blue-100 px-2 py-1 rounded hover:bg-blue-200 hover:text-blue-700 transition-colors cursor-pointer"
                    title="ORDERを表示"
                  >
                    {item.relatedOrderId}
                  </button>
                  {/* ORDERステータスバッジ */}
                  {item.orderStatus && (
                    <span className={`inline-flex px-2 py-0.5 text-xs font-medium rounded border ${getOrderStatusColor(item.orderStatus)}`}>
                      {item.orderStatus}
                    </span>
                  )}
                </div>

                {/* ORDERタイトル */}
                {item.orderTitle && (
                  <div>
                    <span className="text-sm text-gray-600">タイトル: </span>
                    <span className="text-sm text-gray-800">{item.orderTitle}</span>
                  </div>
                )}

                {/* タスク進捗 */}
                {(item.totalTasks ?? 0) > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">タスク進捗</span>
                      <span className={`font-medium ${progressPercent === 100 ? 'text-green-600' : 'text-blue-600'}`}>
                        {item.completedTasks}/{item.totalTasks} ({progressPercent}%)
                      </span>
                    </div>
                    {/* 進捗バー */}
                    <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-300 ${
                          progressPercent === 100 ? 'bg-green-500' : 'bg-blue-500'
                        }`}
                        style={{ width: `${progressPercent}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-2">関連ORDER</h3>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-500">未着手（ORDERは未作成です）</p>
              </div>
            </div>
          )}

          {/* タイムスタンプ情報 */}
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-3">タイムスタンプ</h3>
            <div className="bg-gray-50 rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">作成日時:</span>
                <span className="text-gray-800 font-mono">{formatDate(item.createdAt)}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">更新日時:</span>
                <span className="text-gray-800 font-mono">{formatDate(item.updatedAt)}</span>
              </div>
              {item.completedAt && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">完了日時:</span>
                  <span className="text-gray-800 font-mono">{formatDate(item.completedAt)}</span>
                </div>
              )}
            </div>
          </div>

          {/* ソート順序（デバッグ情報） */}
          {item.sortOrder != null && item.sortOrder !== 999 && (
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-2">ソート順序</h3>
              <div className="bg-gray-50 rounded-lg p-4">
                <span className="text-sm text-gray-600">
                  優先順位: <span className="font-mono font-medium text-gray-800">#{item.sortOrder}</span>
                </span>
              </div>
            </div>
          )}
        </div>

        {/* フッター */}
        <div className="flex items-center justify-between gap-3 p-4 border-t border-gray-200 bg-gray-50">
          <div>
            {!isEditing && (
              <button
                onClick={handleStartEdit}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                編集
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            {isEditing ? (
              <>
                <button
                  onClick={handleCancelEdit}
                  disabled={saving}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  キャンセル
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !editTitle.trim()}
                  className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {saving ? '保存中...' : '保存'}
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={handleClose}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  閉じる
                </button>
                {hasOrder && onOrderClick && (
                  <button
                    onClick={handleOrderIdClick}
                    className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    ORDERを表示
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default BacklogDetailPanel;
