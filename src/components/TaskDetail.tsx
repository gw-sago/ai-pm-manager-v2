/**
 * TaskDetail.tsx - タスク詳細表示コンポーネント
 *
 * TASK_XXX.mdとREVIEW_XXX.mdの内容を表示するモーダル/パネルコンポーネント。
 * REVIEWタブにはREPORT内容（実施内容）と判定結果が統合表示される。
 * MarkdownViewerコンポーネントを使用したMarkdownレンダリング。
 *
 * TASK_023: タスク詳細表示UI実装
 * TASK_962: 3タブ(TASK/REPORT/REVIEW)から2タブ(TASK/REVIEW)に変更
 * TASK_1123: MarkdownViewerへのリファクタリング（重複コード解消）
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { TaskInfo } from '../preload';
import { MarkdownViewer } from './MarkdownViewer';

/**
 * タブの種類
 */
type TabType = 'task' | 'review';

/**
 * TaskDetailProps
 */
interface TaskDetailProps {
  /** プロジェクト名 */
  projectName: string;
  /** タスク情報 */
  task: TaskInfo;
  /** 閉じるボタンのコールバック */
  onClose: () => void;
}

/**
 * タスク詳細表示コンポーネント
 */
export const TaskDetail: React.FC<TaskDetailProps> = ({ projectName, task, onClose }) => {
  const [activeTab, setActiveTab] = useState<TabType>('task');
  const [taskContent, setTaskContent] = useState<string | null>(null);
  const [reviewContent, setReviewContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // ファイル内容の読み込み
  useEffect(() => {
    const loadFiles = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const [taskFile, reviewFile] = await Promise.all([
          window.electronAPI.getTaskFile(projectName, task.id),
          window.electronAPI.getReviewFile(projectName, task.id),
        ]);

        setTaskContent(taskFile);
        setReviewContent(reviewFile);
      } catch (err) {
        console.error('[TaskDetail] Failed to load files:', err);
        setError('ファイルの読み込みに失敗しました');
      } finally {
        setIsLoading(false);
      }
    };

    loadFiles();
  }, [projectName, task.id]);

  // ESCキーで閉じる
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // タブ切り替え
  const handleTabChange = useCallback((tab: TabType) => {
    setActiveTab(tab);
  }, []);

  // 現在のコンテンツ
  const currentContent = useMemo(() => {
    if (activeTab === 'task') {
      return taskContent;
    }
    return reviewContent;
  }, [activeTab, taskContent, reviewContent]);

  // REVIEWが存在するかどうか
  const hasReview = reviewContent !== null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="task-detail-title"
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col m-4">
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            <span className="text-sm font-mono text-gray-500">{task.id}</span>
            <h2 id="task-detail-title" className="text-lg font-semibold text-gray-900 truncate max-w-[500px]">
              {task.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-full hover:bg-gray-100 transition-colors"
            aria-label="閉じる"
          >
            <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* タブ */}
        <div className="flex border-b border-gray-200">
          <button
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === 'task'
                ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            }`}
            onClick={() => handleTabChange('task')}
          >
            TASK
          </button>
          <button
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === 'review'
                ? 'text-green-600 border-b-2 border-green-600 bg-green-50'
                : hasReview
                ? 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                : 'text-gray-300 cursor-not-allowed'
            }`}
            onClick={() => hasReview && handleTabChange('review')}
            disabled={!hasReview}
            title={!hasReview ? 'REVIEWファイルがありません' : ''}
          >
            REVIEW
            {!hasReview && <span className="ml-1 text-xs">(なし)</span>}
          </button>
        </div>

        {/* コンテンツ */}
        <div className="flex-1 overflow-auto p-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-48">
              <div className="flex items-center space-x-2">
                <svg className="w-5 h-5 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                <span className="text-gray-500">読み込み中...</span>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-48">
              <div className="text-center">
                <svg className="w-12 h-12 text-red-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <p className="text-gray-500">{error}</p>
              </div>
            </div>
          ) : currentContent ? (
            <MarkdownViewer content={currentContent} />
          ) : (
            <div className="flex items-center justify-center h-48">
              <div className="text-center">
                <svg className="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                <p className="text-gray-400">
                  {activeTab === 'task' && 'TASKファイルが見つかりません'}
                  {activeTab === 'review' && 'REVIEWファイルが見つかりません'}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* フッター */}
        <div className="flex items-center justify-end px-6 py-3 border-t border-gray-200 bg-gray-50">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors"
          >
            閉じる
          </button>
        </div>
      </div>
    </div>
  );
};
